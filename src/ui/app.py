import streamlit as st
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import pandas as pd

# Fix for imports when running from subfolder
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from src.ui.utils.helpers import inject_custom_css
from src.ui.utils.data_loader import fetch_data_blocks
from src.ui.components.sidebar import render_sidebar
from src.ui.components.map_view import display_map
from src.ui.components.dialogs import show_export_dialog

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Meteo Radar AI - Dual Mode")

def main():
    inject_custom_css()
    st.title("📡 Meteo Radar - Dual Timeline")
    
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
        st.session_state['active_mode'] = 'forecast' # Default to prediction
        
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
        
    # --- Dual Column Sliders ---
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
            label_visibility="collapsed"
        )
        # Activate on interaction check (Heuristic)
        if st.session_state.slider_history != max_hist:
             st.session_state['active_mode'] = 'history'
             
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
    start_msg = ""
    
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

    # --- Animation Logic ---
    if config['auto_play']:
        time.sleep(config['play_speed'])
        # Increment logic
        current_time = active_time
        if st.session_state['active_mode'] == 'history':
             next_time = current_time + timedelta(hours=2)
             if next_time > max_hist:
                 # Loop or switch? Loop history
                 next_time = min_hist
             # Update session state for slider to pick up next run
             # Getting Key Error if we try to set widget directly possibly?
             # No, standard way is update session state key.
             # st.session_state['slider_history'] = next_time # This might cause loop issues with widget
             st.warning("Animación en refactorización. Usa el slider manual por ahora.")
        else:
             next_time = current_time + timedelta(hours=1)
             if next_time > max_fore:
                 next_time = min_fore
             # st.session_state['slider_forecast'] = next_time
             st.warning("Animación en refactorización.")
        
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

    # --- Map Display ---
    display_map(
        active_ds, 
        active_time, 
        config['bbox'], 
        config['layers'], 
        supabase_client=config['supabase']
    )

def pd_to_datetime(pd_dt):
    """Helper to convert numpy/pandas datetime to py datetime with utc"""
    return pd.to_datetime(pd_dt).to_pydatetime().replace(tzinfo=timezone.utc)

if __name__ == "__main__":
    main()
