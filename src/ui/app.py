import streamlit as st
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import pandas as pd

# Fix for imports when running from subfolder
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from src.ui.utils.helpers import inject_custom_css, get_supabase
from src.ui.utils.data_loader import fetch_data_blocks
from src.ui.components.sidebar import render_sidebar
from src.ui.components.map_view import display_map
from src.ui.components.dialogs import show_export_dialog

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar AI - Dual Mode")

def main():
    inject_custom_css()
    st.title("📡 Meteo Radar: MeteoGrid + FiClima")
    
    # --- Sidebar & Config ---
    if 'map_refresh_trigger' not in st.session_state:
        st.session_state.map_refresh_trigger = 0

    # Render sidebar and get user config
    config = render_sidebar()
    
    # Dialog Trigger
    if config.get('show_export'):
         min_lat, max_lat, min_lon, max_lon = config['bbox']
         show_export_dialog(min_lat, max_lat, min_lon, max_lon, config['resolution'])

    # --- Data Loading ---
    with st.spinner("Sincronizando modelos meteorológicos..."):
        min_lat, max_lat, min_lon, max_lon = config['bbox']
        ds_history, ds_forecast = fetch_data_blocks(
            min_lat, max_lat, min_lon, max_lon, 
            config['resolution']
        )
    
    # --- State Management (Defaults) ---
    if 'active_mode' not in st.session_state:
        st.session_state['active_mode'] = 'history' # Default to history as per user req
        
    # --- Timeline Limits ---
    min_hist, max_hist = datetime.now(timezone.utc), datetime.now(timezone.utc)
    if ds_history and ds_history.time.size > 0:
        times = ds_history.time.values
        min_hist = pd_to_datetime(times.min())
        max_hist = pd_to_datetime(times.max())

    min_fore, max_fore = datetime.now(timezone.utc), datetime.now(timezone.utc)
    if ds_forecast and ds_forecast.time.size > 0:
        times = ds_forecast.time.values
        min_fore = pd_to_datetime(times.min())
        max_fore = pd_to_datetime(times.max())

    # --- Shadow State Initialization ---
    if 'internal_hist' not in st.session_state:
        st.session_state['internal_hist'] = min_hist # Start from beginning
    # Ensure internal state is within bounds (if data reloaded)
    # Ensure internal state is within bounds (if data reloaded)
    if st.session_state['internal_hist'] < min_hist or st.session_state['internal_hist'] > max_hist:
        st.session_state['internal_hist'] = max_hist

    if 'internal_fore' not in st.session_state:
        st.session_state['internal_fore'] = min_fore
    if st.session_state['internal_fore'] < min_fore or st.session_state['internal_fore'] > max_fore:
        st.session_state['internal_fore'] = min_fore

    # Callbacks
    def update_hist():
        st.session_state['internal_hist'] = st.session_state.slider_history
        st.session_state['active_mode'] = 'history'
    
    def update_fore():
        st.session_state['internal_fore'] = st.session_state.slider_forecast
        st.session_state['active_mode'] = 'forecast'

    # --- Dual Column Sliders ---
    slider_col1, slider_col2 = st.columns(2)
    
    with slider_col1:
        st.markdown("##### 📜 Histórico")
        sel_hist = st.slider(
            "Seleccionar hora pasada",
            min_value=min_hist,
            max_value=max_hist,
            value=st.session_state['internal_hist'],
            format="DD/MM HH:mm",
            key="slider_history",
            step=timedelta(hours=2),
            label_visibility="collapsed",
            on_change=update_hist
        )
        if st.button("Ver Histórico", key="btn_activate_hist", use_container_width=True):
             st.session_state['active_mode'] = 'history'

    with slider_col2:
        st.markdown("##### 🔮 Predicción")
        sel_fore = st.slider(
            "Seleccionar hora futura",
            min_value=min_fore,
            max_value=max_fore,
            value=st.session_state['internal_fore'],
            format="DD/MM HH:mm",
            key="slider_forecast",
            label_visibility="collapsed",
            on_change=update_fore
        )
        if st.button("Ver Predicción", key="btn_activate_fore", use_container_width=True, type="primary"):
             st.session_state['active_mode'] = 'forecast'

    # --- Active Logic ---
    active_ds = None
    active_time = None
    start_msg = ""
    
    if st.session_state['active_mode'] == 'history':
        active_ds = ds_history
        active_time = st.session_state['internal_hist']
        if active_time.tzinfo is None: active_time = active_time.replace(tzinfo=timezone.utc)
        start_msg = f"📜 Histórico: {active_time.strftime('%H:%M')}"
    else:
        active_ds = ds_forecast
        active_time = st.session_state['internal_fore']
        if active_time.tzinfo is None: active_time = active_time.replace(tzinfo=timezone.utc)
        start_msg = f"🔮 Predicción: {active_time.strftime('%H:%M')}"

    st.info(f"{start_msg} | Cargando datos...", icon="⏳")

    # Render Map and hold result
    supabase_client = get_supabase()
    
    display_map(
        active_ds, 
        active_time,
        config['bbox'],
        config['layers'],
        supabase_client
    )

    # --- Animation Logic ---
    if config['auto_play']:
        # Block execution to let user see the map
        # time.sleep happens ON SERVER. 
        # We assume client renders in parallel.
        time.sleep(config['play_speed'])
        
        # Increment logic
        current_time = active_time
        
        if st.session_state['active_mode'] == 'history':
             next_time = current_time + timedelta(hours=2)
             if next_time > max_hist:
                 next_time = min_hist
             
             st.session_state['internal_hist'] = next_time 
             
        else:
             next_time = current_time + timedelta(hours=1)
             if next_time > max_fore:
                 next_time = min_fore
             
             st.session_state['internal_fore'] = next_time
        
        st.rerun()
    # --- Info Bar ---
    col_info1, col_info2, col_info3 = st.columns([2, 1, 1])
    col_info1.info(f"{start_msg}: **{active_time.strftime('%d/%m/%Y %H:%M')} UTC**")

    # --- Metrics ---
    if active_ds and 'precipitation' in active_ds:
        try:
            layer_data = active_ds['precipitation'].sel(time=active_time, method="nearest")
            max_precip = layer_data.max().item()
            mean_precip = layer_data.mean().item()
            col_info2.metric("Lluvia Máxima", f"{max_precip:.2f} mm/h")
            col_info3.metric("Promedio", f"{mean_precip:.2f}")
        except:
             col_info2.metric("Lluvia Máxima", "N/A")
             col_info3.metric("Promedio", "N/A")

    # --- End of Main ---

def pd_to_datetime(pd_dt):
    """Helper to convert numpy/pandas datetime to py datetime with utc"""
    return pd.to_datetime(pd_dt).to_pydatetime().replace(tzinfo=timezone.utc)

if __name__ == "__main__":
    main()
