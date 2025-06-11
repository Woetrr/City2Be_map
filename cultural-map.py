# -*- coding: utf-8 -*-
"""
Created on Tue May 27 10:57:06 2025

@author: woute
"""

import streamlit as st
import folium
import pandas as pd
import requests
from streamlit_folium import st_folium
import random
from geopy.distance import geodesic

# GeoJSON style function
def style_function(color):
    return lambda feature: dict(color=color, weight=3, opacity=0.5)

# Set up the fundamentals
api_key = '5b3ce3597851110001cf62489246434e7b0d4505a18991d2ce9906be'  # API key

map_params = {'location': ([52.090833, 5.122222]), 'zoom_start': 15}

dataset = "HMdb_data_utrecht.csv"
lat_col = "Latitude (minus=S)"
lon_col = "Longitude (minus=W)"

# Layout
col1, col2, col3 = st.columns([1, 3, 1])

if 'route_tour' not in st.session_state:
    st.session_state.route_tour = None
if 'map_result' not in st.session_state:
    st.session_state.map_result = None
if 'route_created' not in st.session_state:
    st.session_state.route_created = False

    
# Sidebar for inputs
with st.sidebar:
    st.header("Route Preferences")
    route_profile = "foot-walking"
    max_distance_km = st.slider("Select distance for walk (m)", 100, 2000, 500, 5)
    create_route = st.button("Create route")

# Function to get a single route segment
def get_single_route(start_coords, end_coords, route_profile, api_key):
    base_url = f"https://api.openrouteservice.org/v2/directions/{route_profile}/geojson"  # ✅ use /geojson
    headers = {
        'Accept': 'application/geo+json', 
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }

    body = {
        "coordinates": [start_coords, end_coords],
        "instructions": False
    }

    try:
        response = requests.post(base_url, json=body, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"Error getting route: {response.status_code}"
            try:
                error_data = response.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_msg += f", {error_data['error']['message']}"
            except:
                error_msg += f", {response.text}"
            st.warning(error_msg)
            return None
    except Exception as e:
        st.error(f"Error requesting route: {e}")
        return None


# Function to create a tour of points under a max distance
def get_tour_route(file_path, lat_col, lon_col):
    df = pd.read_csv(file_path)
    df = df.dropna(subset=[lat_col, lon_col]).copy()

    if df.empty:
        raise ValueError("No valid coordinates in dataset.")

    df["coords"] = list(zip(df[lat_col], df[lon_col]))
    current_idx = random.choice(df.index.tolist())
    current_point = df.loc[current_idx, "coords"]

    visited = [{"coords" : current_point,
                "title" : df.loc[current_idx, "Title"]}]
                
    remaining = df.drop(index=current_idx)
    total_distance = 0.0

    while not remaining.empty:
        remaining["distance"] = remaining["coords"].apply(lambda x: geodesic(current_point, x).km)
        nearest_idx = remaining["distance"].idxmin()
        nearest_distance = remaining.loc[nearest_idx, "distance"]

        if total_distance + nearest_distance > (max_distance_km/1000):
            break

        current_point = remaining.loc[nearest_idx, "coords"]
        title = remaining.loc[nearest_idx, "Title"]
        visited.append({"coords": current_point, "title": title})
        total_distance += nearest_distance
        remaining = remaining.drop(index=nearest_idx)

    return visited, total_distance

# Function to get routing between all points
def tour_to_ors(coords_titles, route_profile, api_key):
    all_segments = []
    min_lat, min_lon, max_lat, max_lon = 90.0, 180.0, -90.0, -180.0

    for i in range(len(coords_titles) - 1):
        start_coords = coords_titles[i]["coords"]
        end_coords = coords_titles[i + 1]["coords"]
        
        start = [start_coords[1], start_coords[0]]  # [lon, lat]
        end = [end_coords[1], end_coords[0]]        # [lon, lat]


        segment = get_single_route(start, end, route_profile, api_key)

        if segment and 'features' in segment:
            for feature in segment['features']:
                geojson_coords = feature['geometry']['coordinates']  # [[lon, lat], [lon, lat], ...]

                # Convert to [[lat, lon], ...]
                decoded = [[latlng[1], latlng[0]] for latlng in geojson_coords]

                for lat, lon in decoded:
                    min_lat = min(min_lat, lat)
                    min_lon = min(min_lon, lon)
                    max_lat = max(max_lat, lat)
                    max_lon = max(max_lon, lon)

                all_segments.append({
                    'geometry': feature['geometry'],
                    'decoded_route': decoded,
                    'summary': feature['properties']['summary'],
                    'segments': feature['properties'].get('segments', []),
                    'start_title': coords_titles[i]['title']
                })
        else:
            st.error(f"Could not calculate route for segment {i+1}: {coords_titles[i]} → {coords_titles[i+1]}")
            return None

    return all_segments


# Function to display the map
def display_map_with_routes(routes):
    if not routes:
        return None

    all_lats = [coord[0] for route in routes for coord in route['decoded_route']]
    all_lons = [coord[1] for route in routes for coord in route['decoded_route']]
    center_lat = sum(all_lats) / len(all_lats)
    center_lng = sum(all_lons) / len(all_lons)

    m = folium.Map(location=[center_lat, center_lng], zoom_start=15)

    for i, route in enumerate(routes):
        route_coords = route['decoded_route']
        weight = 4
        folium.PolyLine(
            route_coords,
            weight=weight,
            color="green",
            opacity=0.8 if i == 0 else 0.6,
            tooltip=f"Route {i+1}: {route['summary']['duration']/60:.0f} min"
        ).add_to(m)
        
        if i == 0: pin_icon = "🏃‍"
        else: pin_icon = "📍"
        
        folium.Marker(
            location=routes[i]['decoded_route'][0],
            popup=f"{i+1}. {route['start_title']}",
            icon= folium.DivIcon(html=f'<div style="font-size:20px; text-align:center;">{pin_icon}<span style="font-size:15px;"><br><b> {i+1}</b></span></div>')
        ).add_to(m)

    folium.Marker(
        location=routes[-1]['decoded_route'][-1],
        popup=f"{i+1}. {route['start_title']}",
        icon=folium.DivIcon(html='<div style="font-size:24px;">🏁</div>')
    ).add_to(m)

    return m

#main function of routing app
if create_route:
    try:
        Geo_route, total_km = get_tour_route(dataset, lat_col, lon_col)
        st.session_state.route_tour = tour_to_ors(Geo_route, route_profile, api_key)
        if st.session_state.route_tour:
            st.session_state.map_result = display_map_with_routes(st.session_state.route_tour)
            st.session_state.route_created = True
        else:
            st.session_state.map_result = None
            st.session_state.route_created = False
            st.error("Could not generate a valid route.")
    except Exception as e:
        st.session_state.map_result = None
        st.session_state.route_created = False
        st.error(f"Failed to create route: {e}")

# Safe, non-flickering display of the map
with col2:
    if st.session_state.get('map_result'):
        st_folium(st.session_state.map_result, width=800, returned_objects=[])
    else:
        st.subheader("How to use this app")
        st.markdown("""
        1. Choose a travel mode and distance in the sidebar  
        2. Click 'Create route'  
        3. View your walking or cycling route on the map  
        """)
        st_folium(folium.Map(**map_params), width=800, returned_objects=[])
