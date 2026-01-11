import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import shutil
import xarray as xr
import rioxarray
import numpy as np
from datetime import datetime, timedelta, timezone
import pandas as pd
import sys
from pathlib import Path

# Fix for imports when running from subfolder
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from src.adapters.openmeteo import OpenMeteoAdapter
from src.application.facade import MeteorologicalFacade
from src.domain.model import BoundingBox, TimeRange

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar AI - Dual Mode")

# --- Helper Functions ---
@st.cache_resource
def get_facade():
    adapter = OpenMeteoAdapter()
    return MeteorologicalFacade(provider=adapter)

@st.cache_data(ttl=3600)
def fetch_data_blocks(min_lat, max_lat, min_lon, max_lon):
    """
    Fetches both History (Past 10 days) and Forecast (Next 24h).
    Returns two separate datasets.
    """
    facade = get_facade()
    bbox = BoundingBox(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon
    )
    
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    
    # 1. History Block (Last 10 days)
    history_start = now - timedelta(days=10)
    history_window = TimeRange(start=history_start, end=now)
    ds_history = facade.get_history_view(bbox, history_window, high_resolution=True)
    
    # 2. Forecast Block (Next 24h)
    forecast_end = now + timedelta(hours=24)
    forecast_window = TimeRange(start=now, end=forecast_end)
    ds_forecast = facade.get_forecast_view(bbox, forecast_window, high_resolution=True)
    
    return ds_history, ds_forecast

def create_geotiff(da: xr.DataArray, filename: str):
    da = da.rio.write_crs("EPSG:4326")
    da.rio.to_raster(filename)

def main():
    st.title("📡 Meteo Radar - Dual Timeline")
    
    # --- Sidebar State Management ---
    if 'map_refresh_trigger' not in st.session_state:
        st.session_state.map_refresh_trigger = 0

    with st.sidebar:
        st.header("📍 Región")
        # Define Regions as Macros areas (large coverage ~4x4 degrees or more)
        # Mungia Center: 43.3, -2.7. 
        # Box: Lat 41.3-45.3, Lon -4.7 to -0.7 covers huge part of N.Spain/Bay of Biscay
        region_options = {
            "Norte (Mungia/Euskadi)": (41.5, 45.0, -5.0, -0.5),
            "Centro (Madrid)": (38.0, 42.0, -6.0, -1.0),
            "Este (Barcelona/Cat)": (39.5, 43.5, -1.0, 5.0),
            "Noroeste (Galicia)": (41.0, 44.5, -10.0, -6.0),
        }
        # Default to Mungia/Norte
        selected_region_name = st.selectbox("Seleccionar Zona", list(region_options.keys()), index=0)
        
        # Custom Coordinates Input
        st.divider()
        custom_coords = st.text_input("📍 Coordenadas (Lat, Lon)", placeholder="Ej: 43.470, -3.839")
        
        # Logic to determine BBox
        if custom_coords:
            try:
                # Parse "lat, lon"
                parts = [float(p.strip()) for p in custom_coords.split(',')]
                if len(parts) == 2:
                    c_lat, c_lon = parts
                    # Create a MACRO window (approx 400x400km) to ensure "full map" feel
                    delta = 2.0 # +/- 2.0 deg = 4.0 deg span
                    min_lat, max_lat = c_lat - delta, c_lat + delta
                    min_lon, max_lon = c_lon - delta, c_lon + delta
                    st.toast(f"Usando coordenadas personalizadas: {c_lat}, {c_lon}", icon="🎯")
                else:
                    st.error("Formato inválido. Use: 'Lat, Lon'")
                    min_lat, max_lat, min_lon, max_lon = region_options[selected_region_name]
            except ValueError:
                st.error("Error numérico. Asegúrese de usar puntos decimales.")
                min_lat, max_lat, min_lon, max_lon = region_options[selected_region_name]
        else:
            min_lat, max_lat, min_lon, max_lon = region_options[selected_region_name]
        
        if st.button("🔄 Recargar Datos"):
            st.cache_data.clear()
            st.rerun()

    # --- Data Loading ---
    with st.spinner("Sincronizando modelos meteorológicos..."):
        ds_history, ds_forecast = fetch_data_blocks(min_lat, max_lat, min_lon, max_lon)

    if ds_history is None or ds_forecast is None:
        st.error("Error cargando datasets")
        return

    # --- Dual Sliders Logic ---
    st.markdown("### 1. Análisis Histórico (Últimos 10 Días)")
    
    # Prepare History Slider
    hist_times = pd.to_datetime(ds_history.time.values)
    # Convert to pydatetime and ensure UTC awareness for slider comparison if needed, 
    # but Streamlit slider usually likes native python datetimes.
    # Xarray times are np.datetime64.
    min_hist = hist_times[0].to_pydatetime()
    max_hist = hist_times[-1].to_pydatetime()
    
    # Use session state to track which slider is "Active"
    if 'active_mode' not in st.session_state:
        st.session_state['active_mode'] = 'forecast' # Default to forecast

    # History Slider
    col1, col2 = st.columns([3, 1])
    with col1:
        sel_hist = st.slider(
            "Retroceder en el tiempo",
            min_value=min_hist,
            max_value=max_hist,
            value=max_hist,
            format="DD/MM HH:mm",
            key="slider_history"
        )
    with col2:
        if st.button("Ver Histórico", key="btn_hist"):
            st.session_state['active_mode'] = 'history'
            st.session_state.map_refresh_trigger += 1

    st.markdown("### 2. Predicción (Próximas 24 Horas)")
    
    # Prepare Forecast Slider
    fore_times = pd.to_datetime(ds_forecast.time.values)
    min_fore = fore_times[0].to_pydatetime()
    max_fore = fore_times[-1].to_pydatetime()
    
    col3, col4 = st.columns([3, 1])
    with col3:
        sel_fore = st.slider(
            "Futuro (+24h)",
            min_value=min_fore,
            max_value=max_fore,
            value=min_fore,
            format="DD/MM HH:mm",
            key="slider_forecast"
        )
    with col4:
        if st.button("Ver Predicción", key="btn_fore"):
            st.session_state['active_mode'] = 'forecast'
            st.session_state.map_refresh_trigger += 1

    # --- Active Logic ---
    active_ds = None
    active_time = None
    
    # Determine what to show based on what slider was last interacted with or button pressed
    # Simple heuristic: If active_mode is history, use hist slider value.
    
    if st.session_state['active_mode'] == 'history':
        active_ds = ds_history
        # Ensure TZ
        if sel_hist.tzinfo is None: sel_hist = sel_hist.replace(tzinfo=timezone.utc)
        active_time = sel_hist
        st.info(f"📜 Modo: **HISTÓRICO** | Visualizando: {active_time.strftime('%Y-%m-%d %H:%M')}")
        
    else:
        active_ds = ds_forecast
        if sel_fore.tzinfo is None: sel_fore = sel_fore.replace(tzinfo=timezone.utc)
        active_time = sel_fore
        st.success(f"🔮 Modo: **PREDICCIÓN** | Visualizando: {active_time.strftime('%Y-%m-%d %H:%M')}")

    # --- Map Rendering ---
    # Select Data
    try:
        layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
    except KeyError:
        st.warning("Hora fuera de rango para el dataset seleccionado.")
        return

    # Calculate Stats for Feedback
    max_precip = layer_data.max().item()
    mean_precip = layer_data.mean().item()
    
    col_stat1, col_stat2 = st.columns(2)
    col_stat1.metric("Lluvia Máxima (mm/h)", f"{max_precip:.2f}")
    col_stat2.metric("Promedio Zona", f"{mean_precip:.2f}")

    if max_precip == 0:
        st.caption("🌤️ No se detecta lluvia en este momento para esta zona.")

    # Generate TIFF
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "active_radar.tif")
    create_geotiff(layer_data, tmp_path)

    # Force Leafmap refresh by using a dynamic key or just re-rendering
    # Leafmap in streamlit is a bit sticky.
    # We will use the 'key' argument in to_streamlit if available, or recreate the object.
    
    m = leafmap.Map(
        center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
        zoom=10, # Zoom in for local view
        draw_control=False,
        measure_control=False,
    )
    m.add_basemap("CARTODB_POSITRON") # Light map to match reference better (usually radar overlay looks better on light)
    
    # Custom Colormap for Radar (Standard Ref)
    # 0 -> Transparent
    # Low -> Light Green
    # Med -> Dark Green
    # High -> Yellow/Red
    radar_palette = ["#00000000", "#7CFC00", "#32CD32", "#FFFF00", "#FF8C00", "#FF0000"]
    
    m.add_raster(
        tmp_path, 
        layer_name="Radar Precipitación", 
        colormap=radar_palette, 
        opacity=0.6,
        nodata=np.nan,
        vmin=0,
        vmax=max(5.0, max_precip) 
    )
    
    # Display
    # Using a unique key based on time forces full re-mount of the map component
    # This is heavy but ensures the image updates.
    unique_map_key = f"map_{st.session_state['active_mode']}_{active_time.isoformat()}"
    m.to_streamlit(height=600, key=unique_map_key)
    
    # Cleanup (Delayed to ensure serve happens)
    # In prod, use a dedicated temp manager. For now, we leave it or rely on OS cleanup
    # shutil.rmtree(tmp_dir) # Removing immediately might break localtileserver serving

if __name__ == "__main__":
    main()
