import time
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from typing import List, Dict, Any

from utils import (
    fetch_live_flights,
    fetch_sigmet_geojson,
    routes_to_linestrings,
    route_buffers,
    hazards_intersecting_route,
    flights_to_layer,
    sigmet_geojson_layer,
    sigmet_pulse_layers,
)

# --------------------
# CONSTANTS / CONFIG
# --------------------
N_POINTS = 100
CYCLE_DURATION_MS = 3000
FRAME_RATE = 30
SLEEP_TIME = 1 / FRAME_RATE
PLANE_SPEED_FACTOR = 2

ROUTE_COLOR = [0, 150, 255]
PLANE_COLOR = [255, 255, 255]
PLANE_RADIUS = 25000
ARC_WIDTH = 3

VIEW_LAT = 22
VIEW_LON = 78
VIEW_ZOOM = 5
VIEW_PITCH = 30

ROUTES = [
    {"from": [77.1, 28.6], "to": [72.87, 19.07]},  # Delhi → Mumbai
    {"from": [77.1, 28.6], "to": [77.59, 12.97]},  # Delhi → Bengaluru
    {"from": [77.59, 12.97], "to": [88.36, 22.57]},  # Bengaluru → Kolkata
]

# --------------------
# HELPERS
# --------------------
def precompute_route_points(routes: List[Dict]) -> List[pd.DataFrame]:
    route_points = []
    for route in routes:
        lons = np.linspace(route["from"][0], route["to"][0], N_POINTS)
        lats = np.linspace(route["from"][1], route["to"][1], N_POINTS)
        route_points.append(pd.DataFrame({"lon": lons, "lat": lats}))
    return route_points
# Precomputing reduces per-frame overhead for animation [web:11].

def get_route_layers(routes: List[Dict]) -> List[pdk.Layer]:
    layers = []
    for route in routes:
        df = pd.DataFrame([{
            "from_lon": route["from"][0], "from_lat": route["from"][1],
            "to_lon": route["to"][0], "to_lat": route["to"][1]
        }])
        layers.append(
            pdk.Layer(
                "ArcLayer",
                data=df,
                get_source_position='[from_lon, from_lat]',
                get_target_position='[to_lon, to_lat]',
                get_source_color=ROUTE_COLOR,
                get_target_color=ROUTE_COLOR,
                get_width=ARC_WIDTH
            )
        )
    return layers
# ArcLayer draws clean curves between origin and destination points [web:11].

def get_plane_layers(route_points: List[pd.DataFrame]) -> List[pdk.Layer]:
    layers = []
    now = time.time()
    for points in route_points:
        frame = int(now * PLANE_SPEED_FACTOR % N_POINTS)
        plane_pos = points.iloc[frame:frame+1]
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=plane_pos,
                get_position='[lon, lat]',
                get_fill_color=PLANE_COLOR,
                get_radius=PLANE_RADIUS
            )
        )
    return layers
# White markers simulate planes moving along routes frame-by-frame [web:11].

# --------------------
# STREAMLIT APP
# --------------------
st.set_page_config(page_title="Flight Radar + SIGMETs", layout="wide")
st.title("✈️ Flight Radar with Live SIGMET Hazards")

# Sidebar controls
col1, col2 = st.columns(2)
with col1:
    flights_limit = st.slider("Max flights", 10, 200, 50, 10)
with col2:
    buffer_km = st.slider("Route buffer (km)", 20, 150, 60, 10)

# Initial data fetch (cached with TTL inside utils)
with st.spinner("Fetching hazards and flights..."):
    sigmet_geo = fetch_sigmet_geojson()
    live_flights = fetch_live_flights({"limit": flights_limit})
# AWC Data API provides SIGMET GeoJSON, and AviationStack provides live flights [web:60][web:90].

# Geometry for relevance filter
route_lines = routes_to_linestrings(ROUTES)
buffers = route_buffers(route_lines, km=buffer_km)
sigmet_hits = hazards_intersecting_route(sigmet_geo, buffers)
hit_collection = {"type": "FeatureCollection", "features": sigmet_hits}
# Intersecting filters ensure only relevant hazards near the route corridor render [web:60].

# Build layers
route_layers = get_route_layers(ROUTES)
plane_traces = precompute_route_points(ROUTES)
plane_layers = get_plane_layers(plane_traces)
hazard_layer = sigmet_geojson_layer(hit_collection)
flights_layer = flights_to_layer(live_flights)
# GeoJsonLayer renders polygons, ScatterplotLayer renders points for flights/planes [web:11].

# Animation placeholder
chart_placeholder = st.empty()

# NOTE: Keep API calls out of the animation loop; only animate local layers
# Streamlit reruns the script on each interaction; an infinite loop is acceptable here
# for a demo, but consider using st.autorefresh pattern for production [web:92].

try:
    while True:
        t = (time.time() * 1000) % CYCLE_DURATION_MS
        scale = t / CYCLE_DURATION_MS

        pulse_layers = sigmet_pulse_layers(sigmet_hits, scale)

        view_state = pdk.ViewState(
            latitude=VIEW_LAT,
            longitude=VIEW_LON,
            zoom=VIEW_ZOOM,
            pitch=VIEW_PITCH
        )

        layers = []
        layers += route_layers
        layers += plane_layers
        if flights_layer:
            layers.append(flights_layer)
        if hazard_layer:
            layers.append(hazard_layer)
        layers += pulse_layers

        deck = pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            map_style=None  # choose default or a style of choice
        )
        chart_placeholder.pydeck_chart(deck)
        time.sleep(1 / FRAME_RATE)
except Exception as e:
    st.error(f"Animation error: {e}")
