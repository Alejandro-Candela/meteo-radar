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
from src.application.exporter import BulkExportService
from src.domain.model import BoundingBox, TimeRange

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar AI - Dual Mode")

# --- Helper Functions ---
@st.cache_resource
def get_facade():
    adapter = OpenMeteoAdapter()
    return MeteorologicalFacade(provider=adapter)

@st.cache_data(ttl=3600)
def fetch_data_blocks(min_lat, max_lat, min_lon, max_lon, resolution):
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
    ds_history = facade.get_history_view(bbox, history_window, resolution=resolution)
    
    # 2. Forecast Block (Next 24h)
    forecast_end = now + timedelta(hours=24)
    forecast_window = TimeRange(start=now, end=forecast_end)
    ds_forecast = facade.get_forecast_view(bbox, forecast_window, resolution=resolution)
    
    return ds_history, ds_forecast

def create_geotiff(da: xr.DataArray, filename: str):
    da = da.rio.write_crs("EPSG:4326")
    da.rio.to_raster(filename)

def inject_custom_css():
    st.markdown("""
        <style>
        /* Compact Sliders */
        .stSlider {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
        }
        div[data-testid="stSliderTickBar"] {
            display: none;
        }
        
        /* Legend Table Styles */
        .sidebar-legend {
            background-color: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 5px;
            margin-top: 20px;
            border: 1px solid rgba(0,0,0,0.1);
        }
        .legend-gradient {
            height: 10px;
            width: 100%;
            background: linear-gradient(to right, 
                rgba(0,0,0,0), 
                #7CFC00, 
                #32CD32, 
                #FFFF00, 
                #FF8C00, 
                #FF0000
            );
            border-radius: 5px;
            margin-bottom: 5px;
            border: 1px solid #ccc;
        }
        .legend-labels {
            display: flex;
            justify-content: space-between;
            color: gray;
            font-size: 0.8em;
        }
        
        /* Blue Slider for Prediction (Targeting by Label content) */
        /* Use :has() to find the slider container that has the specific label */
        div.stSlider:has(div[aria-label="Seleccionar hora futura"]) {
            --streamlit-theme-primary-color: #00BFFF !important;
            --primary-color: #00BFFF !important;
        }
        
        /* Force track and thumb colors for this specific slider */
        div.stSlider:has(div[aria-label="Seleccionar hora futura"]) div[data-testid="stSliderTickBar"] + div,
        div.stSlider:has(div[aria-label="Seleccionar hora futura"]) div[role="slider"] {
            background-color: #00BFFF !important;
        }
        
        /* Also target the button "Ver Predicción" */
        div.stButton button:has(div:contains("Ver Predicción")), /* Pseudo-selector :contains not in Std CSS, use logic */
        div.stButton button p:contains("Ver Predicción") { /* Try general sibling or just nth-of-type for button if possible */
             /* :contains is NOT valid CSS. We must use position or JS. Using nth-of-type for button */
        }
        
        /* Reliable Button Targeting via Column Index */
        div[data-testid="column"]:nth-of-type(2) div.stButton button {
            border-color: #00BFFF !important;
            color: #00BFFF !important;
        }
        div[data-testid="column"]:nth-of-type(2) div.stButton button:hover {
            border-color: #00BFFF !important;
            color: #00BFFF !important;
            background-color: rgba(0, 191, 255, 0.1) !important;
        }
        div[data-testid="column"]:nth-of-type(2) div.stButton button:focus:not(:active) {
            border-color: #00BFFF !important;
            color: #00BFFF !important;
        }
        </style>
    """, unsafe_allow_html=True)

def get_radar_legend_html():
    return """
        <div class="sidebar-legend">
            <div style="font-weight: bold; margin-bottom: 5px;">🌧️ Intensidad (mm/h)</div>
            <div class="legend-gradient"></div>
            <div class="legend-labels">
                <span>0</span>
                <span>2</span>
                <span>5</span>
                <span>10+</span>
            </div>
        </div>
    """

@st.dialog("📁 Exportar Datos")
def show_export_dialog(min_lat, max_lat, min_lon, max_lon, resolution):
    st.write("Configura el rango de descarga:")
    
    # 1. Date Range
    today = datetime.now().date()
    # Default: today and tomorrow
    date_range = st.date_input(
        "Rango de Fechas (Máx 10 días)",
        value=(today, today + timedelta(days=1)),
        min_value=today - timedelta(days=365),
        max_value=today + timedelta(days=365),
        format="DD/MM/YYYY"
    )
    
    # Validate range
    start_date, end_date = today, today
    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            start_date = end_date = date_range[0]
            
    days_diff = (end_date - start_date).days + 1
    
    if days_diff > 10:
        st.error(f"⚠️ El rango seleccionado ({days_diff} días) excede el máximo permitido de 10 días.")
        valid_config = False
    elif days_diff < 1:
        st.error("Selecciona al menos 1 día.")
        valid_config = False
    else:
        valid_config = True
        
    # 2. Interval
    interval = st.slider("Intervalo (horas)", 1, 3, 1)
    
    # Estimate
    if valid_config:
        total_hours = days_diff * 24
        est_images = int(total_hours / interval)
        st.info(f"📸 Se generarán aproximadamente **{est_images}** imágenes TIFF.")
    
    st.divider()
    
    if st.button("🚀 Confirmar Exportación", disabled=not valid_config, type="primary"):
        if valid_config:
            exporter = BulkExportService()
            with st.spinner("Generando y comprimiendo imágenes..."):
                try:
                    # Convert date to datetime for service (Time 00:00)
                    dt_start = datetime.combine(start_date, datetime.min.time())
                    dt_end = datetime.combine(end_date, datetime.min.time())
                    
                    zip_path, count = exporter.generate_bulk_zip(
                        dt_start, dt_end, interval, 
                        (min_lat, max_lat, min_lon, max_lon), 
                        resolution
                    )
                    
                    st.success(f"✅ ¡Exportación completada! {count} imágenes.")
                    
                    # Read zip for download
                    with open(zip_path, "rb") as fp:
                        st.download_button(
                            label="📥 Descargar ZIP",
                            data=fp,
                            file_name=os.path.basename(zip_path),
                            mime="application/zip"
                        )
                except Exception as e:
                    st.error(f"Error: {e}")

def main():
    inject_custom_css()
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
            
        st.divider()
        resolution_options = {
            "Alta (1.1 km/px)": 0.01,
            "Media (2.2 km/px)": 0.02,
            "Baja (5.5 km/px)": 0.05
        }
        selected_res_name = st.selectbox("Calidad de Imagen", list(resolution_options.keys()), index=0)
        selected_resolution = resolution_options[selected_res_name]
        
        # --- Legend in Sidebar ---
        st.markdown(get_radar_legend_html(), unsafe_allow_html=True)
        
        st.divider()
        if st.button("📁 Exportar Datos..."):
            show_export_dialog(min_lat, max_lat, min_lon, max_lon, selected_resolution)

    # --- Data Loading ---
    with st.spinner("Sincronizando modelos meteorológicos..."):
        ds_history, ds_forecast = fetch_data_blocks(min_lat, max_lat, min_lon, max_lon, selected_resolution)

    if ds_history is None or ds_forecast is None:
        st.error("Error cargando datasets")
        return

    # --- Time Control (Top Layout) ---
    current_time_utc = datetime.now(timezone.utc)
    
    # Prepare Timelines
    hist_times = pd.to_datetime(ds_history.time.values)
    min_hist = hist_times[0].to_pydatetime()
    max_hist = hist_times[-1].to_pydatetime()
    
    fore_times = pd.to_datetime(ds_forecast.time.values)
    min_fore = fore_times[0].to_pydatetime()
    max_fore = fore_times[-1].to_pydatetime()

    # Use session state to track which slider is "Active"
    if 'active_mode' not in st.session_state:
        st.session_state['active_mode'] = 'forecast' # Default to forecast

    # Dual Column Layout above Map
    # Use columns to put them side-by-side
    slider_col1, slider_col2 = st.columns(2)
    
    with slider_col1:
        st.markdown("##### 📜 Histórico")
        sel_hist = st.slider(
            "Seleccionar hora pasada",
            min_value=min_hist,
            max_value=max_hist,
            value=max_hist,
            format="DD/MM HH:mm",
            key="slider_history",
            label_visibility="collapsed" # Compact
        )
        if st.session_state.slider_history != max_hist: # Simple heuristic: if user moved it
             st.session_state['active_mode'] = 'history'
        # Or explicit button? User asked for just sliders. Let's infer mode from last changed or keep button?
        # User said: "historico a la izquierda, seguido de prediccion a la derecha"
        # Let's keep the logic simple: The slider value drives the map. 
        # But we need to know WHICH one to show. 
        # For now, let's keep the Buttons below or integrated? 
        # User didn't mention buttons, just sliders. I will auto-detect interaction if possible.
        # But Streamlit doesn't give "event source" easily.
        # I will add small 'Activar' buttons or just assume if one is changed it becomes active.
        if st.button("Ver Histórico", key="btn_activate_hist", use_container_width=True):
             st.session_state['active_mode'] = 'history'

    with slider_col2:
        st.markdown("##### 🔮 Predicción")
        sel_fore = st.slider(
            "Seleccionar hora futura",
            min_value=min_fore,
            max_value=max_fore,
            value=min_fore,
            format="DD/MM HH:mm",
            key="slider_forecast",
            label_visibility="collapsed"
        )
        if st.button("Ver Predicción", key="btn_activate_fore", use_container_width=True, type="primary"):
             st.session_state['active_mode'] = 'forecast'

    # --- Active Logic ---
    active_ds = None
    active_time = None
    
    if st.session_state['active_mode'] == 'history':
        active_ds = ds_history
        if sel_hist.tzinfo is None: sel_hist = sel_hist.replace(tzinfo=timezone.utc)
        active_time = sel_hist
        start_msg = "📜 Visualizando Histórico"
    else:
        active_ds = ds_forecast
        if sel_fore.tzinfo is None: sel_fore = sel_fore.replace(tzinfo=timezone.utc)
        active_time = sel_fore
        start_msg = "🔮 Visualizando Predicción"

    # Info Bar
    col_info1, col_info2, col_info3 = st.columns([2, 1, 1])
    col_info1.info(f"{start_msg}: **{active_time.strftime('%d/%m/%Y %H:%M')} UTC**")

    # --- Map Rendering ---
    # Select Data
    try:
        layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
    except KeyError:
        st.warning("Hora fuera de rango para el dataset seleccionado.")
        return

    # Calculate Stats
    max_precip = layer_data.max().item()
    mean_precip = layer_data.mean().item()
    col_info2.metric("Lluvia Máxima", f"{max_precip:.2f} mm/h")
    col_info3.metric("Promedio", f"{mean_precip:.2f}")

    # Generate TIFF
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "active_radar.tif")
    create_geotiff(layer_data, tmp_path)

    # Map
    m = leafmap.Map(
        center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
        zoom=7, # Macro zoom
        draw_control=False,
        measure_control=False,
    )
    m.add_basemap("CARTODB_POSITRON")
    
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
    
    # Display Map - Static Key to prevent full reload
    # We use a static key 'main_map'. Streamlit might cache the iframe.
    # If the iframe is cached, it might NOT update the content inside.
    # NOTE: leafmap.to_streamlit writes HTML to a file/string. 
    # If we call it again, strict re-render is needed for the new HTML to show.
    # If we use a static key, Streamlit replaces the component if the args (html) changed?
    # Actually, the 'key' in st.components.v1.html is for state preservation.
    m.to_streamlit(height=600) 
    
    # Cleanup
    # shutil.rmtree(tmp_dir) 

if __name__ == "__main__":
    main()
