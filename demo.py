import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import time

st.title("✈️ Flight Radar with Animated Pulses")

# ----- ROUTES -----
routes = [
    {"from": [77.1, 28.6], "to": [72.87, 19.07]},  # Delhi → Mumbai
    {"from": [77.1, 28.6], "to": [77.59, 12.97]},  # Delhi → Bengaluru
    {"from": [77.59, 12.97], "to": [88.36, 22.57]} # Bengaluru → Kolkata
]

n_points = 100

# ----- RADAR ANOMALIES (with severity) -----
radar_anomalies = [
    {"lon": 76.0, "lat": 23.5, "severity": 1, "color": [255, 255, 0]},  # Minimal - yellow
    {"lon": 78.0, "lat": 22.0, "severity": 2, "color": [255, 165, 0]},  # Medium - orange
    {"lon": 80.0, "lat": 21.0, "severity": 3, "color": [255, 0, 0]},    # Severe - red
]

# Map severity to maximum radius
severity_radius = {1: 150000, 2: 250000, 3: 400000}

# Placeholder for updating chart
chart_placeholder = st.empty()

# ----- ANIMATION LOOP -----
while True:
    t = (time.time() * 1000) % 3000  # 3-second cycle
    scale = t / 3000

    route_layers = []
    plane_layers = []
    pulse_layers = []

    # --- ROUTES & PLANES ---
    for r in routes:
        lons = np.linspace(r["from"][0], r["to"][0], n_points)
        lats = np.linspace(r["from"][1], r["to"][1], n_points)
        route_points = pd.DataFrame({"lon": lons, "lat": lats})

        # Plane position
        frame = int(time.time() * 2 % n_points)
        plane_pos = route_points.iloc[frame:frame+1]

        # Arc layer
        route_layers.append(
            pdk.Layer(
                "ArcLayer",
                data=pd.DataFrame([{
                    "from_lon": r["from"][0], "from_lat": r["from"][1],
                    "to_lon": r["to"][0], "to_lat": r["to"][1]
                }]),
                get_source_position='[from_lon, from_lat]',
                get_target_position='[to_lon, to_lat]',
                get_source_color=[0, 150, 255],
                get_target_color=[0, 150, 255],
                get_width=3
            )
        )

        # Plane moving along route
        plane_layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=plane_pos,
                get_position='[lon, lat]',
                get_fill_color=[255, 255, 255],
                get_radius=25000
            )
        )

    # --- RADAR PULSES (Severity-based, concentric, animated) ---
    for anomaly in radar_anomalies:
        max_radius = severity_radius.get(anomaly["severity"], 150000)
        for i in range(3):  # 3 concentric circles
            radius = max_radius * (scale + i * 0.2)
            if radius > max_radius:
                radius = radius - max_radius
            # Higher severity => more opacity
            opacity = int(100 + 50 * anomaly["severity"] * (1 - scale - i * 0.2))
            if opacity < 0: opacity = 0

            pulse_layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([{"lon": anomaly["lon"], "lat": anomaly["lat"]}]),
                    get_position='[lon, lat]',
                    get_fill_color=anomaly["color"] + [opacity],
                    get_radius=radius,
                    stroked=False,
                    filled=True,
                )
            )

    # ----- VIEW -----
    view_state = pdk.ViewState(
        latitude=22,
        longitude=78,
        zoom=5,
        pitch=30
    )

    # Combine all layers
    deck = pdk.Deck(
        layers=route_layers + plane_layers + pulse_layers,
        initial_view_state=view_state
    )

    # Render chart
    chart_placeholder.pydeck_chart(deck)
    time.sleep(0.03)  # ~30 FPS
