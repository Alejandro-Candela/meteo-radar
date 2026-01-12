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
        st.session_state['internal_hist'] = max_hist # Start from LATEST time
    # Ensure internal state is within bounds (if data reloaded)
    if st.session_state['internal_hist'] < min_hist or st.session_state['internal_hist'] > max_hist:
        st.session_state['internal_hist'] = max_hist

    if 'internal_fore' not in st.session_state:
        st.session_state['internal_fore'] = min_fore
    if st.session_state['internal_fore'] < min_fore or st.session_state['internal_fore'] > max_fore:
        st.session_state['internal_fore'] = min_fore
        
    # --- Animation State ---
    if 'playing_hist' not in st.session_state: st.session_state['playing_hist'] = False
    if 'playing_fore' not in st.session_state: st.session_state['playing_fore'] = False

    # Callbacks
    def update_hist():
        st.session_state['internal_hist'] = st.session_state.slider_history
        st.session_state['active_mode'] = 'history'
    
    def update_fore():
        st.session_state['internal_fore'] = st.session_state.slider_forecast
        st.session_state['active_mode'] = 'forecast'
        
    def toggle_play_hist():
        st.session_state['playing_hist'] = not st.session_state['playing_hist']
        if st.session_state['playing_hist']:
            st.session_state['playing_fore'] = False # Stop others
            st.session_state['active_mode'] = 'history'
            
    def toggle_play_fore():
        st.session_state['playing_fore'] = not st.session_state['playing_fore']
        if st.session_state['playing_fore']:
            st.session_state['playing_hist'] = False # Stop others
            st.session_state['active_mode'] = 'forecast'

    # --- Sync Sliders with Internal State (for Animation) ---
    # We must update the slider key BEFORE the widget is rendered to avoid StreamlitAPIException
    if 'slider_history' in st.session_state and st.session_state['slider_history'] != st.session_state['internal_hist']:
        st.session_state['slider_history'] = st.session_state['internal_hist']
        
    if 'slider_forecast' in st.session_state and st.session_state['slider_forecast'] != st.session_state['internal_fore']:
        st.session_state['slider_forecast'] = st.session_state['internal_fore']

    # --- Active Logic Setup ---
    active_ds = None
    active_time = None
    start_msg = ""
    
    if st.session_state['active_mode'] == 'history':
        active_ds = ds_history
        active_time = st.session_state['internal_hist']
        if active_time.tzinfo is None: active_time = active_time.replace(tzinfo=timezone.utc)
        start_msg = f"📜 Histórico"
    else:
        active_ds = ds_forecast
        active_time = st.session_state['internal_fore']
        if active_time.tzinfo is None: active_time = active_time.replace(tzinfo=timezone.utc)
        start_msg = f"🔮 Predicción"

    # --- LAYOUT: 2/3 Map, 1/3 Controls ---
    col_map, col_controls = st.columns([2, 1], gap="medium")
    
    # --- RIGHT COLUMN: Controls & Metrics ---
    with col_controls:
        st.markdown("### 🎛️ Controles")
        
        # 1. History Control
        with st.expander("📜 Histórico (Pasado)", expanded=(st.session_state['active_mode'] == 'history')):
            c_sl, c_btn = st.columns([5, 1])
            with c_sl:
                sel_hist = st.slider(
                    "Hora",
                    min_value=min_hist,
                    max_value=max_hist,
                    value=st.session_state['internal_hist'],
                    format="DD/MM HH:mm",
                    key="slider_history",
                    step=timedelta(hours=1),
                    label_visibility="collapsed",
                    on_change=update_hist
                )
            with c_btn:
                icon = "⏸️" if st.session_state['playing_hist'] else "▶️"
                st.button(icon, key="btn_play_hist", on_click=toggle_play_hist)
            
            if st.button("Activar Histórico", key="btn_activate_hist", use_container_width=True):
                 st.session_state['active_mode'] = 'history'
                 st.session_state['playing_hist'] = False
                 st.session_state['playing_fore'] = False

        # 2. Forecast Control
        with st.expander("🔮 Predicción (Futuro)", expanded=(st.session_state['active_mode'] == 'forecast')):
            c_sl_f, c_btn_f = st.columns([5, 1])
            with c_sl_f:
                sel_fore = st.slider(
                    "Hora",
                    min_value=min_fore,
                    max_value=max_fore,
                    value=st.session_state['internal_fore'],
                    format="DD/MM HH:mm",
                    key="slider_forecast",
                    label_visibility="collapsed",
                    on_change=update_fore
                )
            with c_btn_f:
                icon_f = "⏸️" if st.session_state['playing_fore'] else "▶️"
                st.button(icon_f, key="btn_play_fore", on_click=toggle_play_fore)

            if st.button("Activar Predicción", key="btn_activate_fore", use_container_width=True, type="primary"):
                 st.session_state['active_mode'] = 'forecast'
                 st.session_state['playing_hist'] = False
                 st.session_state['playing_fore'] = False

        # 3. Metrics
        st.divider()
        with st.expander("📊 Datos en Tiempo Real", expanded=True):
            st.caption(f"**Fecha:** {active_time.strftime('%d/%m/%Y %H:%M')} UTC | **Fuente:** OpenMeteo")
            
            if active_ds:
                try:
                    # Helper to get scalar value safely
                    def get_val(var_name, method="nearest"):
                        if var_name in active_ds:
                            val = active_ds[var_name].sel(time=active_time, method=method).mean().item()
                            return val
                        return None
                        
                    def fmt(val, unit="", decimal=1):
                        if val is None: return "N/A"
                        return f"{val:.{decimal}f}{unit}"

                    # --- Fetching Values (Mean across view or specific point) ---
                    # Currently fetching MEAN across the visible region for simplicity
                    # ideally this should be "Point" value if user clicked, but "Mean" is good for region overview
                    
                    temp = get_val('temperature')
                    app_temp = get_val('apparent_temp')
                    precip = get_val('precipitation') # Mean precip might be low, MAX often better for precip
                    max_precip = active_ds['precipitation'].sel(time=active_time, method="nearest").max().item() if 'precipitation' in active_ds else 0
                    
                    humidity = get_val('humidity')
                    clouds = get_val('cloud_cover')
                    
                    wind = get_val('wind_speed')
                    gusts = get_val('wind_gusts')
                    wind_dir = get_val('wind_direction')
                    
                    pressure = get_val('pressure')

                    # --- Rendering Compact Grid ---
                    
                    # Row 1: Temperature
                    st.markdown("**🌡️ Temperatura**")
                    c1, c2 = st.columns(2)
                    c1.markdown(f"<span style='font-size:0.9em; color:#666'>Temperatura</span><br>**{fmt(temp, 'ºC')}**", unsafe_allow_html=True)
                    c2.markdown(f"<span style='font-size:0.9em; color:#666'>Sensación</span><br>**{fmt(app_temp, 'ºC')}**", unsafe_allow_html=True)
                    
                    st.divider()
                    
                    # Row 2: Conditions
                    st.markdown("**🌧️ Condiciones**")
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"<span style='font-size:0.8em; color:#666'>Lluvia Max</span><br>**{max_precip:.1f}** <span style='font-size:0.8em'>mm</span>", unsafe_allow_html=True)
                    c2.markdown(f"<span style='font-size:0.8em; color:#666'>Humedad</span><br>**{fmt(humidity, '%', 0)}**", unsafe_allow_html=True)
                    c3.markdown(f"<span style='font-size:0.8em; color:#666'>Nubes</span><br>**{fmt(clouds, '%', 0)}**", unsafe_allow_html=True)
                    
                    st.divider()
                    
                    # Row 3: Wind
                    st.markdown("**💨 Viento**")
                    c1, c2 = st.columns(2)
                    c1.markdown(f"<span style='font-size:0.9em; color:#666'>Velocidad</span><br>**{fmt(wind, '')}** km/h", unsafe_allow_html=True)
                    c2.markdown(f"<span style='font-size:0.9em; color:#666'>Rachas</span><br>**{fmt(gusts, '')}** km/h", unsafe_allow_html=True)
                    
                    st.divider()
                    
                    # Row 4: Pressure
                    st.markdown(f"**⏲️ Presión:** {fmt(pressure, ' hPa', 0)}")

                except Exception as e:
                    st.warning(f"Error calculando métricas: {e}")
            else:
                st.info("Sin datos cargados.")

    # --- LEFT COLUMN: Map ---
    with col_map:
        # Render Map
        supabase_client = get_supabase()
        display_map(
            active_ds, 
            active_time,
            config['bbox'],
            config['layers'],
            supabase_client,
            aemet_key=config.get('aemet_key')
        )

    # --- Animation Logic ---
    if st.session_state['playing_hist'] or st.session_state['playing_fore']:
        # Block execution to let user see the map
        time.sleep(config['play_speed'])
        
        if st.session_state['playing_hist']:
             next_time = st.session_state['internal_hist'] + timedelta(hours=1)
             if next_time > max_hist:
                 next_time = min_hist
             st.session_state['internal_hist'] = next_time
             st.session_state['active_mode'] = 'history'
             
        elif st.session_state['playing_fore']:
             next_time = st.session_state['internal_fore'] + timedelta(hours=1)
             if next_time > max_fore:
                 next_time = min_fore
             st.session_state['internal_fore'] = next_time
             st.session_state['active_mode'] = 'forecast'
        
        st.rerun()

    # --- End of Main ---

def pd_to_datetime(pd_dt):
    """Helper to convert numpy/pandas datetime to py datetime with utc"""
    return pd.to_datetime(pd_dt).to_pydatetime().replace(tzinfo=timezone.utc)

if __name__ == "__main__":
    main()
