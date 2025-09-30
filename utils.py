import time
import requests
import pandas as pd
import pydeck as pdk
from typing import List, Dict, Any, Optional

from shapely.geometry import LineString, shape, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

import streamlit as st

# --------------------
# API FETCHERS
# --------------------

@st.cache_data(ttl=90)
def fetch_live_flights(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetch live flights from AviationStack.
    Example params: {"limit": 50, "airline_iata": "AI"} or geographic bounds.
    Requires secrets: aviationstack_key.
    """
    url = "https://api.aviationstack.com/v1/flights"
    q = {"access_key": st.secrets["aviationstack_key"], **params}
    r = requests.get(url, params=q, timeout=20)
    r.raise_for_status()
    data = r.json()
    # Aviationstack returns in 'data'
    return data.get("data", [])  # list of flights
    # See docs for fields like 'live.latitude/longitude' and schedule info [web:90].

@st.cache_data(ttl=180)
def fetch_sigmet_geojson() -> Dict[str, Any]:
    """
    Fetch SIGMETs as GeoJSON from NOAA AWC Data API.
    Free, no key required.
    """
    url = "https://aviationweather.gov/api/data/sigmet?format=geojson"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()
    # AWC provides aviation hazards like turbulence/icing/convective polygons [web:60].

# --------------------
# GEOMETRY HELPERS
# --------------------

def routes_to_linestrings(routes: List[Dict[str, Any]]) -> List[LineString]:
    lines = []
    for r in routes:
        # coords are [lon, lat]
        lines.append(LineString([(r["from"][0], r["from"][1]), (r["to"][0], r["to"][1])]))
    return lines
    # Linestrings let us buffer and intersect with hazard polygons [web:11].

def route_buffers(lines: List[LineString], km: float = 60.0) -> List[Polygon]:
    # Approximate degrees per km near mid-latitudes (1 deg ~ 111 km)
    deg = km / 111.0
    return [ln.buffer(deg) for ln in lines]
    # Buffer creates a corridor around routes to detect nearby hazards [web:11].

def hazards_intersecting_route(sigmet_geojson: Dict[str, Any],
                               buffers: List[Polygon]) -> List[Dict[str, Any]]:
    if not sigmet_geojson or "features" not in sigmet_geojson:
        return []
    union_buf = unary_union(buffers)
    hits = []
    for feat in sigmet_geojson["features"]:
        geom_json = feat.get("geometry")
        if not geom_json:
            continue
        try:
            geom = shape(geom_json)
        except Exception:
            continue
        if geom.is_valid and geom.intersects(union_buf):
            hits.append(feat)
    return hits
    # Only hazards that affect the route corridor are returned, reducing noise [web:60].

def polygon_centroid(feature: Dict[str, Any]) -> Optional[Dict[str, float]]:
    try:
        geom = shape(feature.get("geometry"))
        c = geom.centroid
        return {"lon": float(c.x), "lat": float(c.y)}
    except Exception:
        return None
    # Centroids help place pulses/markers inside hazard polygons [web:11].

# --------------------
# PYDECK LAYER BUILDERS
# --------------------

def flights_to_layer(flights: List[Dict[str, Any]]) -> Optional[pdk.Layer]:
    """
    Build a ScatterplotLayer for flight positions.
    Prefers live positions if present; falls back to arrival/airport coords if available.
    """
    pts = []
    for f in flights:
        live = f.get("live") or {}
        lon = live.get("longitude")
        lat = live.get("latitude")
        # fallback to known coordinates if live absent (varies by plan/endpoint)
        if lon is None or lat is None:
            arr = f.get("arrival") or {}
            lon = arr.get("longitude")
            lat = arr.get("latitude")
        if lon is None or lat is None:
            continue
        pts.append({"lon": float(lon), "lat": float(lat)})
    if not pts:
        return None
    df = pd.DataFrame(pts)
    return pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position='[lon, lat]',
        get_fill_color=[0, 255, 180],
        get_radius=12000,
        pickable=True,
    )
    # ScatterplotLayer is efficient for many points with per-point styling [web:11].

def sigmet_geojson_layer(geojson: Dict[str, Any]) -> Optional[pdk.Layer]:
    if not geojson:
        return None
    return pdk.Layer(
        "GeoJsonLayer",
        geojson,
        stroked=True,
        filled=True,
        pickable=True,
        get_fill_color=[255, 0, 0, 40],
        get_line_color=[255, 0, 0, 160],
        line_width_min_pixels=1,
        auto_highlight=True,
    )
    # GeoJsonLayer renders hazard polygons directly with stroke/fill styling [web:11].

def sigmet_pulse_layers(features: List[Dict[str, Any]], scale: float) -> List[pdk.Layer]:
    """
    Optional: derive animated pulses at hazard centroids.
    scale: 0..1 cycling phase (from app).
    """
    layers = []
    for feat in features:
        c = polygon_centroid(feat)
        if not c:
            continue
        # Simple animated radius + fade
        max_radius = 250000.0  # 250 km generic pulse
        radius = max_radius * (0.2 + 0.8 * scale)
        opacity = int(160 * (1.0 - scale))
        opacity = max(0, min(255, opacity))
        df = pd.DataFrame([c])
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df,
                get_position='[lon, lat]',
                get_fill_color=[255, 60, 0, opacity],
                get_radius=radius,
                stroked=False,
                filled=True,
            )
        )
    return layers
    # Pulses provide a radar-like cue on top of polygons for attention [web:11].
