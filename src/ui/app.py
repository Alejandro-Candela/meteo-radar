import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import shutil
import xarray as xr
import rioxarray
import numpy as np
from datetime import datetime, timedelta
import pandas as pd

# Fix for imports when running from subfolder
import sys
from pathlib import Path
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

import folium

from src.adapters.openmeteo import OpenMeteoAdapter
from src.application.facade import MeteorologicalFacade
from src.domain.model import BoundingBox, TimeRange

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar MVP")

# --- Dependency Injection (Cached) ---
@st.cache_resource
def get_facade():
    adapter = OpenMeteoAdapter()
    return MeteorologicalFacade(provider=adapter)

# --- Data Loading (Cached) ---
@st.cache_data(ttl=3600)
def fetch_data(min_lat, max_lat, min_lon, max_lon):
    facade = get_facade()
    
    bbox = BoundingBox(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon
    )
    
    # Predecir 24 horas desde ahora
    now = datetime.now()
    # Redondeamos a la hora anterior para alinearnos con modelos
    start_hour = now.replace(minute=0, second=0, microsecond=0)
    
    time_window = TimeRange(
        start=start_hour,
        end=start_hour + timedelta(hours=24)
    )
    
    ds = facade.get_radar_view(bbox, time_window, high_resolution=True)
    return ds

# --- Visualization Helper ---
def create_geotiff(da: xr.DataArray, filename: str):
    """
    Escribe un DataArray 2D a GeoTIFF usando rioxarray.
    Necesitamos asegurar que tenga CRS y Transform.
    """
    # Xarray interp no preserva CRS/Transform perfectamente a veces si no estaba seteado
    # Reconstruimos coord system
    da = da.rio.write_crs("EPSG:4326")
    
    # Guardar
    da.rio.to_raster(filename)

# --- Main UI ---
def main():
    st.title("📡 Meteo Radar AI - MVP")
    
    with st.sidebar:
        st.header("📍 Configuración")
        
        # Presets de Regiones
        region_options = {
            "Madrid": (40.0, 40.8, -4.2, -3.3),
            "Barcelona": (41.0, 41.8, 1.5, 2.5),
            "Galicia": (42.0, 43.5, -9.0, -7.0),
        }
        
        selected_region = st.selectbox("Región", list(region_options.keys()))
        min_lat, max_lat, min_lon, max_lon = region_options[selected_region]
        
        # O controles manuales
        with st.expander("Ajuste Fino"):
            min_lat = st.number_input("Min Lat", value=min_lat, format="%.2f")
            max_lat = st.number_input("Max Lat", value=max_lat, format="%.2f")
            min_lon = st.number_input("Min Lon", value=min_lon, format="%.2f")
            max_lon = st.number_input("Max Lon", value=max_lon, format="%.2f")
            
        if st.button("🔄 Actualizar Radar"):
            st.cache_data.clear()
            st.rerun()

    # Layout Principal
    
    # 1. Cargar Datos
    with st.spinner("Descargando e Interpolando datos meteorológicos..."):
        ds = fetch_data(min_lat, max_lat, min_lon, max_lon)
        
    if ds is None:
        st.error("No se pudieron cargar los datos.")
        return

    # 2. Time Slider
    st.subheader("🕒 Control Temporal")
    
    # Extraer timestamps disponibles
    times = pd.to_datetime(ds.time.values)
    min_time = times[0].to_pydatetime()
    max_time = times[-1].to_pydatetime()
    
    # Slider
    selected_time = st.slider(
        "Línea de tiempo",
        min_value=min_time,
        max_value=max_time,
        value=min_time,
        format="DD/MM HH:mm"
    )
    
    # Fix TZ mismatch: Streamlit slider returns naive datetime, but Xarray is UTC aware
    if selected_time.tzinfo is None:
        from datetime import timezone
        selected_time = selected_time.replace(tzinfo=timezone.utc)
    
    # Selection logic using method='nearest' directly for robustness
    layer_data = ds['precipitation'].sel(time=selected_time, method="nearest")
    actual_time = layer_data.time.values
    
    # Mostrar hora exacta seleccionada
    st.info(f"Mostrando predicción para: **{pd.to_datetime(actual_time).strftime('%Y-%m-%d %H:%M')}**")
    
    # Crear temp file para el raster
    # Streamlit/Leafmap necesita un path físico a veces para ser mas unifrome
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "radar_layer.tif")
    
    try:
        create_geotiff(layer_data, tmp_path)
        
        m = leafmap.Map(
            center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
            zoom=9,
            draw_control=False,
            measure_control=False,
        )
        
        # Mapa base oscuro
        m.add_basemap("CARTODB_DARK_MATTER")
        
        # Añadir capa de radar
        # Paleta de colores: 'nws_radar' es standard, o 'jet', 'blues'.
        # Usamos una paleta custom si leafmap lo permite facil, si no una built-in
        m.add_raster(
            tmp_path, 
            layer_name="Precipitación (mm/h)", 
            colormap="jet", 
            opacity=0.6,
            nodata=np.nan
        )
        
        # Render en Streamlit
        m.to_streamlit(height=600)
        
    finally:
        # Cleanup
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # 4. Debug Data Expander
    with st.expander("🛠️ Debug Data View"):
        st.write(ds)

if __name__ == "__main__":
    main()
