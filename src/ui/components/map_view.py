import folium
import leafmap.foliumap as leafmap
import streamlit as st
import tempfile
import xarray as xr
from datetime import datetime
from src.ui.utils.helpers import get_or_upload_layer
from src.adapters.aemet import AemetAdapter

def display_map(
    active_ds: xr.Dataset, 
    active_time: datetime,
    bbox_config: tuple, # (min_lat, max_lat, min_lon, max_lon) from widgets
    layers_state: dict, # {'precip': True, 'temp': False, ...}
    supabase_client=None,
    aemet_key: str = None
):
    """
    Renders the map with active layers.
    """
    min_lat, max_lat, min_lon, max_lon = bbox_config
    
    # Base Map
    # Toggle 'Dark Matter' or 'Positron' based on preference? Stick to Positron for visibility of colors.
    m = leafmap.Map(
        center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
        zoom=6,
        draw_control=False,
        measure_control=False,
    )
    m.add_basemap("CARTODB_POSITRON")
    
    # No data check
    if active_ds is None:
         m.to_streamlit(height=600, key="radar_map")
         return

    # Calculate actual bounds (fixes alignment)
    try:
        # Determine dimension names
        lat_dim = 'latitude' if 'latitude' in active_ds.coords else 'lat' if 'lat' in active_ds.coords else 'y'
        lon_dim = 'longitude' if 'longitude' in active_ds.coords else 'lon' if 'lon' in active_ds.coords else 'x'
        
        lats = active_ds[lat_dim].values
        lons = active_ds[lon_dim].values
        
        import numpy as np
        
        # Calculate resolution (safely)
        lat_res = 0.0
        if len(lats) > 1:
            lat_res = abs(float(lats[1] - lats[0]))
        else:
             lat_res = 0.01 # Default fallback
             
        lon_res = 0.0
        if len(lons) > 1:
            lon_res = abs(float(lons[1] - lons[0]))
        else:
            lon_res = 0.01 # Default fallback
            
        actual_min_lat = float(lats.min())
        actual_max_lat = float(lats.max())
        actual_min_lon = float(lons.min())
        actual_max_lon = float(lons.max())
        
        # FIX: The coordinates represent the CENTER of the pixel.
        # ImageOverlay expects the outer EDGES of the image.
        # We must expand the bounds by half-resolution in all directions.
        half_res_lat = lat_res / 2.0
        half_res_lon = lon_res / 2.0
        
        overlay_bounds = [
            [actual_min_lat - half_res_lat, actual_min_lon - half_res_lon], 
            [actual_max_lat + half_res_lat, actual_max_lon + half_res_lon]
        ]
        
    except Exception as e:
        # Fallback
        overlay_bounds = [[min_lat, min_lon], [max_lat, max_lon]]

    # --- Render Layers ---
    bbox_tuple = (min_lat, max_lat, min_lon, max_lon)
    
    # 1. Precip
    if layers_state.get('precip', True) and 'precipitation' in active_ds:
        try:
            layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
            max_val = layer_data.max().item()
            path = get_or_upload_layer(
                 supabase_client, layer_data, "precipitation", bbox_tuple, active_time,
                 colormap=["#00000000", "#7CFC00", "#32CD32", "#FFFF00", "#FF8C00", "#FF0000"],
                 vmin=0, vmax=max(5.0, max_val)
            )
            folium.raster_layers.ImageOverlay(
                image=path, bounds=overlay_bounds, name="Radar Precipitación",
                opacity=0.6, interactive=False, cross_origin=False, zindex=1
            ).add_to(m)
        except Exception:
            pass

    # 2. Temp
    if layers_state.get('temp', False) and 'temperature' in active_ds:
        try:
            layer_data = active_ds['temperature'].sel(time=active_time, method="nearest")
            path = get_or_upload_layer(
                 supabase_client, layer_data, "temperature", bbox_tuple, active_time,
                 colormap="RdYlBu_r", vmin=None, vmax=None
            )
            folium.raster_layers.ImageOverlay(
                image=path, bounds=overlay_bounds, name="Temperatura (ºC)",
                opacity=0.5, interactive=False, cross_origin=False, zindex=2
            ).add_to(m)
        except Exception:
            pass
            
    # 3. Pressure
    if layers_state.get('pressure', False) and 'pressure' in active_ds:
        try:
            layer_data = active_ds['pressure'].sel(time=active_time, method="nearest")
            path = get_or_upload_layer(
                 supabase_client, layer_data, "pressure", bbox_tuple, active_time,
                 colormap="viridis", vmin=None, vmax=None
            )
            folium.raster_layers.ImageOverlay(
                image=path, bounds=overlay_bounds, name="Presión (hPa)",
                opacity=0.5, interactive=False, cross_origin=False, zindex=3
            ).add_to(m)
        except Exception:
            pass
            
    # 4. Wind
    if layers_state.get('wind', False) and 'wind_speed' in active_ds: # Verify var name if it's 'wind' or 'wind_speed'
        try:
            layer_data = active_ds['wind_speed'].sel(time=active_time, method="nearest")
            path = get_or_upload_layer(
                 supabase_client, layer_data, "wind", bbox_tuple, active_time,
                 colormap="YlOrRd", vmin=None, vmax=None
            )
            folium.raster_layers.ImageOverlay(
                image=path, bounds=overlay_bounds, name="Viento (km/h)",
                opacity=0.5, interactive=False, cross_origin=False, zindex=4
            ).add_to(m)
        except Exception:
            pass

    # 5. AEMET Radar (Overlay)
    if layers_state.get('aemet_radar', False) and aemet_key:
        try:
            adapter = AemetAdapter(aemet_key)
            # Fetch Image URL
            overlay_url = adapter.get_radar_composite_url()
            # Fetch Bounds
            overlay_bounds = adapter.national_bounds
            
            if overlay_url:
                folium.raster_layers.ImageOverlay(
                    image=overlay_url, 
                    bounds=overlay_bounds, 
                    name="AEMET Radar (Oficial)",
                    opacity=0.7, 
                    interactive=False, 
                    cross_origin=True, 
                    zindex=10 # Top Layer
                ).add_to(m)
        except Exception as e:
            print(f"Error AEMET Layer: {e}")

    # Display - STATIC KEY to prevent blinking
    m.to_streamlit(height=600, key="radar_map")
