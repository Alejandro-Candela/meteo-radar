import streamlit as st
import leafmap.foliumap as leafmap
import folium
import tempfile
import os
import shutil
import xarray as xr
import rioxarray
import numpy as np
import time
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
from src.adapters.supabase_client import SupabaseClient

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar AI - Dual Mode")

# --- Helper Functions ---
@st.cache_resource
def get_supabase():
    try:
        return SupabaseClient()
    except:
        return None

@st.cache_resource
def get_facade():
    adapter = OpenMeteoAdapter()
    return MeteorologicalFacade(provider=adapter)

@st.cache_resource(ttl=3600, show_spinner=False)
def fetch_data_blocks(min_lat, max_lat, min_lon, max_lon, resolution):
    """
    Fetches both History (Past 3 days) and Forecast (Next 3 days).
    Returns two separate datasets.
    Uses cache_resource to avoid pickling large Xarray datasets.
    """
    facade = get_facade()
    bbox = BoundingBox(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon
    )
    
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    
    # 1. History Block (Last 15 days)
    history_start = now - timedelta(days=15)
    history_window = TimeRange(start=history_start, end=now)
    ds_history = facade.get_history_view(bbox, history_window, resolution=resolution)
    
    # Subsample History to every 2 hours
    # Slicing: [start:stop:step]
    if ds_history is not None:
         ds_history = ds_history.sel(time=slice(None, None, 2))
    
    # 2. Forecast Block (Next 10 days)
    forecast_end = now + timedelta(days=10)
    forecast_window = TimeRange(start=now, end=forecast_end)
    ds_forecast = facade.get_forecast_view(bbox, forecast_window, resolution=resolution)
    
    return ds_history, ds_forecast

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

def generate_colored_png(da: xr.DataArray, filename: str, colormap='viridis', vmin=None, vmax=None):
    """
    Saves the data array as a colored PNG image without geospatial metadata embedded.
    Enforces Lat Descending (North -> South) to match origin='upper'.
    Handles 'latitude'/'lat'/'y' and 'longitude'/'lon'/'x'.
    """
    # Identify coords
    lat_dim = None
    lon_dim = None
    
    for dim in ['latitude', 'lat', 'y']:
        if dim in da.coords:
            lat_dim = dim
            break
            
    for dim in ['longitude', 'lon', 'x']:
        if dim in da.coords:
            lon_dim = dim
            break

    # Sort Lat Descending (North -> South)
    if lat_dim:
        da = da.sortby(lat_dim, ascending=False)
        
    # Transpose to (Lat, Lon)
    if lat_dim and lon_dim and len(da.dims) >= 2:
        try:
            da = da.transpose(lat_dim, lon_dim)
        except Exception:
            pass

    # Normalize data
    data = da.values
    if vmin is None: vmin = np.nanmin(data)
    if vmax is None: vmax = np.nanmax(data)
    
    # Handle NaN for transparency
    # Create matplotlib Normalize
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    
    # Choose colormap
    if isinstance(colormap, list):
         cmap = mcolors.LinearSegmentedColormap.from_list("custom", colormap)
    else:
         cmap = plt.get_cmap(colormap)
         
    # Apply colormap (returns RGBA)
    colored_data = cmap(norm(data))
    
    # Set Alpha for NaNs
    mask = np.isnan(data)
    colored_data[mask] = [0, 0, 0, 0] # Transparent
    
    # Save using imsave (origin='upper' matches lat descending)
    plt.imsave(filename, colored_data, origin='upper', format='png')


def get_or_upload_layer(client, da: xr.DataArray, variable: str, bbox: tuple, timestamp: datetime, colormap='viridis', vmin=None, vmax=None) -> str:
    """
    Ensures BOTH PNG (for map) and TIFF (for download) exist in Supabase.
    Returns: URL of the PNG for rendering.
    """
    
    # 1. Local Fallback (if no client)
    if client is None:
        # Just generate PNG locally for map
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        generate_colored_png(da, tmp.name, colormap, vmin, vmax)
        return tmp.name
        
    # 2. Check Exists (PNG is the critical one for map)
    # Use "radar_pngs" bucket
    png_url = client.get_layer_url(bbox, variable, timestamp, ext=".png", bucket="radar_pngs")
    
    # Check if TIFF also exists? Ideally yes, but for Map performance we only care about PNG.
    # However, user wants "Always upload both". 
    # Strategy: If PNG is missing, we assume we need to generate EVERYTHING.
    # If PNG exists, we assume TIFF exists (or we skip it to save time).
    # To be safe/strict as per user request: "Implementing all this... always".
    # We could check TIFF too but that doubles latency. 
    # Let's trust that if PNG is missing, we do the full process.
    if png_url:
        return png_url
        
    # 3. Not found, Generate & Upload BOTH
    
    # A) Generate PNG (Local)
    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_png.close()
    
    # B) Generate TIFF (Local)
    tmp_tif = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
    tmp_tif.close()
    
    try:
        # Create PNG
        generate_colored_png(da, tmp_png.name, colormap, vmin, vmax)
        
        # Create TIFF (using existing logic pattern or rioxarray)
        # We need to ensure CRS is set for rioxarray
        if da.rio.crs is None:
             da.rio.write_crs("EPSG:4326", inplace=True)
        
        da.rio.to_raster(tmp_tif.name)
        
        # C) Upload TIFF (to radar_tiffs)
        # We don't need the URL returned, just ensure it's up.
        client.upload_file(tmp_tif.name, bbox, variable, timestamp, ext=".tif", mime="image/tiff", bucket="radar_tiffs")
        
        # D) Upload PNG (to radar_pngs) - This returns the URL we need
        final_url = client.upload_file(tmp_png.name, bbox, variable, timestamp, ext=".png", mime="image/png", bucket="radar_pngs")
        
        # Cleanup
        try:
            os.remove(tmp_png.name)
            os.remove(tmp_tif.name)
        except:
            pass
            
        return final_url if final_url else tmp_png.name

    except Exception as e:
        print(f"Error dual-uploading: {e}")
        # Fallback to local path if upload fails
        return tmp_png.name

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
        "Rango de Fechas (Máx 15 días)",
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
    
    if days_diff > 15:
        st.error(f"⚠️ El rango seleccionado ({days_diff} días) excede el máximo permitido de 15 días.")
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
        # Status Indicator
        supabase = get_supabase()
        if supabase:
            st.success("✅ Cloud Cache: Conectado")
        else:
            st.error("❌ Cloud Cache: Off (Local Mode)")
            st.caption("Faltan Secretos de Supabase. La app en la nube puede no mostrar capas.")
        
        st.header("📍 Región")
        # Define Regions as Macros areas (large coverage ~4x4 degrees or more)
        # Mungia Center: 43.3, -2.7. 
        # Box: Lat 41.3-45.3, Lon -4.7 to -0.7 covers huge part of N.Spain/Bay of Biscay
        region_options = {
            "Norte (Mungia/Euskadi)": (38.0, 48.0, -8.0, 2.0),   # 10x10 roughly centered on North
            "Centro (Madrid)": (35.0, 45.0, -9.0, 1.0),          # 10x10 centered on center
            "Este (Barcelona/Cat)": (36.0, 46.0, -3.0, 7.0),     # 10x10 centered on East
            "Noroeste (Galicia)": (38.0, 48.0, -14.0, -4.0),     # 10x10 centered on NW
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
                    # Create a MACRO window (approx 1000x1000km)
                    delta = 5.0 # +/- 5.0 deg = 10.0 deg span (Huge area)
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
        selected_res_name = st.selectbox("Resolución del radar", list(resolution_options.keys()), index=2)
        selected_resolution = resolution_options[selected_res_name]
        
        # --- Legend in Sidebar ---
        st.markdown(get_radar_legend_html(), unsafe_allow_html=True)
        
        # --- Layer Control ---
        st.divider()
        st.subheader("🗺️ Capas")
        show_precip = st.checkbox("🌧️ Precipitación", value=True)
        show_temp = st.checkbox("🌡️ Temperatura", value=False)
        show_pressure = st.checkbox("⏲️ Presión", value=False)
        show_wind = st.checkbox("💨 Viento", value=False)

        st.divider()
        st.subheader("▶️ Animación")
        # Use key to persist state across reruns for animation logic
        auto_play = st.checkbox("Reproducción Automática", key="auto_play")
        play_speed = st.slider("Velocidad (seg/frame)", 0.2, 2.0, 1.0)
        
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

    # --- Animation Logic (Update State BEFORE Widgets) ---
    # Must run before sliders are instantiated
    if st.session_state.get("auto_play"):
         mode = st.session_state.get('active_mode', 'forecast')
         if mode == 'history':
             times = hist_times
             key = 'slider_history'
             default_val = max_hist
         else:
             times = fore_times
             key = 'slider_forecast'
             default_val = min_fore
         
         # Get current value from state or default
         curr = st.session_state.get(key, default_val)
         curr = pd.to_datetime(curr).to_pydatetime()
         
         # Find and increment
         matches = np.where(times == np.datetime64(curr))
         if len(matches[0]) > 0:
             idx = matches[0][0]
             next_idx = (idx + 1) % len(times)
             next_val = times[next_idx].to_pydatetime()
             st.session_state[key] = next_val  # Safe to update here before slider render

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
            step=timedelta(hours=2),
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
        if show_precip and 'precipitation' in active_ds:
             layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
        elif 'precipitation' in active_ds:
             # Logic if precip is OFF but other layer is ON? 
             # Just use precip for Stats, but don't error.
             layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
        else:
             # Should not happen if fetch works
             layer_data = None
             
    except KeyError:
        st.warning("Hora fuera de rango para el dataset seleccionado.")
        return
        
    if layer_data is not None:
        # Calculate Stats (Precipitation is primary)
        max_precip = layer_data.max().item()
        mean_precip = layer_data.mean().item()
        col_info2.metric("Lluvia Máxima", f"{max_precip:.2f} mm/h")
        col_info3.metric("Promedio", f"{mean_precip:.2f}")

        # Cloud Cache for Precipitation
        bbox_tuple = (min_lat, max_lat, min_lon, max_lon)
        supabase = get_supabase()
        
        path_to_render = None
        radar_palette = ["#00000000", "#7CFC00", "#32CD32", "#FFFF00", "#FF8C00", "#FF0000"]
        
        if show_precip:
             path_to_render = get_or_upload_layer(
                 supabase, layer_data, "precipitation", bbox_tuple, active_time,
                 colormap=radar_palette, vmin=0, vmax=max(5.0, max_precip)
             )
        else:
             # Just create temp for others logic to hold if needed?
             # No, if hidden we don't render. 
             path_to_render = None
    else:
        tmp_dir = tempfile.mkdtemp()
        max_precip = 0

    # Map
    m = leafmap.Map(
        center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
        zoom=7, # Macro zoom
        draw_control=False,
        measure_control=False,
    )
    m.add_basemap("CARTODB_POSITRON")
    
    # --- Overlay Bounds Calculation ---
    # Determine actual rendering bounds from the dataset, not the requested bbox.
    # This prevents misalignment if the grid is snapped or resolution causes valid pixels to not fill the box.
    try:
        # Determine dimension names
        lat_dim = 'latitude' if 'latitude' in active_ds.coords else 'lat' if 'lat' in active_ds.coords else 'y'
        lon_dim = 'longitude' if 'longitude' in active_ds.coords else 'lon' if 'lon' in active_ds.coords else 'x'
        
        lats = active_ds[lat_dim].values
        lons = active_ds[lon_dim].values
        
        # Calculate bounds: [South-West, North-East] -> [MinLat, MinLon], [MaxLat, MaxLon]
        # BUT Leaflet/Folium ImageOverlay expects corners: [[lat_min, lon_min], [lat_max, lon_max]]
        # Wait, for ImageOverlay we usually give [[min_lat, min_lon], [max_lat, max_lon]]
        
        actual_min_lat = float(lats.min())
        actual_max_lat = float(lats.max())
        actual_min_lon = float(lons.min())
        actual_max_lon = float(lons.max())
        
        # We must extend the bounds by half-pixel to cover the area "around" the point?
        # xarray coordinates are usually centers.
        # Resolution is assumed from input or calculated?
        # Let's trust the corners of the points for now, or check resolution.
        # If we just use point min/max, we lose half a pixel on each side.
        # Let's try point-bounds first.
        
        overlay_bounds = [[actual_min_lat, actual_min_lon], [actual_max_lat, actual_max_lon]]
        # st.caption(f"Debug Bounds: {overlay_bounds}")
        
    except Exception as e:
        print(f"Bounds Error: {e}")
        # Fallback
        overlay_bounds = [[min_lat, min_lon], [max_lat, max_lon]]

    if path_to_render:
         folium.raster_layers.ImageOverlay(
             image=path_to_render,
             bounds=overlay_bounds,
             name="Radar Precipitación",
             opacity=0.6,
             interactive=False,
             cross_origin=False,
             zindex=1
         ).add_to(m)
    
    # --- New Layers Rendering ---
    
    # 1. Temperature
    if show_temp and 'temperature' in active_ds:
        try:
            temp_data = active_ds['temperature'].sel(time=active_time, method="nearest")
            t_min = temp_data.min().item()
            t_max = temp_data.max().item()
            
            t_path = get_or_upload_layer(supabase, temp_data, "temperature", bbox_tuple, active_time, 
                                        colormap="RdYlBu_r", vmin=t_min, vmax=t_max)
            
            folium.raster_layers.ImageOverlay(
                image=t_path,
                bounds=overlay_bounds,
                name="Temperatura (ºC)",
                opacity=0.5,
                interactive=False,
                cross_origin=False,
                zindex=2
            ).add_to(m)
        except Exception as e:
            # st.error(f"Temp Error: {e}") 
            pass

    # 2. Pressure
    if show_pressure and 'pressure' in active_ds:
        try:
            press_data = active_ds['pressure'].sel(time=active_time, method="nearest")
            p_min = press_data.min().item()
            p_max = press_data.max().item()
            
            p_path = get_or_upload_layer(supabase, press_data, "pressure", bbox_tuple, active_time,
                                        colormap="viridis", vmin=p_min, vmax=p_max)
            
            folium.raster_layers.ImageOverlay(
                image=p_path,
                bounds=overlay_bounds,
                name="Presión (hPa)",
                opacity=0.5,
                interactive=False,
                cross_origin=False,
                zindex=3
            ).add_to(m)
        except Exception:
            pass

    # 3. Wind Speed
    if show_wind and 'wind_speed' in active_ds:
        try:
            wind_data = active_ds['wind_speed'].sel(time=active_time, method="nearest")
            w_max = wind_data.max().item()
            
            w_path = get_or_upload_layer(supabase, wind_data, "wind_speed", bbox_tuple, active_time,
                                        colormap="YlOrRd", vmin=0, vmax=max(10.0, w_max))
            
            folium.raster_layers.ImageOverlay(
                image=w_path,
                bounds=overlay_bounds,
                name="Viento (km/h)",
                opacity=0.6,
                interactive=False,
                cross_origin=False,
                zindex=4
            ).add_to(m)
        except Exception:
            pass
    
    # --- Animation Trigger (At end of script to control Loop) ---
    if st.session_state.get("auto_play"):
        time.sleep(play_speed)
        st.rerun()
    
    # Display Map - Static Key to prevent full reload
    # We use a static key 'main_map'. Streamlit might cache the iframe.
    # If the iframe is cached, it might NOT update the content inside.
    # NOTE: leafmap.to_streamlit writes HTML to a file/string. 
    # If we call it again, strict re-render is needed for the new HTML to show.
    # If we use a static key, Streamlit replaces the component if the args (html) changed?
    # Actually, the 'key' in st.components.v1.html is for state preservation.
    # Display Map - Use static key to prevent full reload (blinking)
    # Streamlit-folium/Leafmap should detect the diff in the Folium object (new overlay) and update the layer.
    st.caption(f"Debug: Rendering {active_time}")
    # m.to_streamlit(height=600, key=f"map_{active_time.isoformat()}") 
    m.to_streamlit(height=600, key="radar_map") 
    
    # Cleanup
    # shutil.rmtree(tmp_dir) 

if __name__ == "__main__":
    main()
