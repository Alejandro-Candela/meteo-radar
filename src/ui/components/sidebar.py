import streamlit as st
from src.ui.utils.helpers import get_supabase
from src.ui.components.dialogs import show_legend_dialog

def render_sidebar():
    """
    Renders the sidebar and returns a configuration dictionary.
    """
    config = {}
    
    with st.sidebar:
        # Status Indicator
        supabase = get_supabase()
        if supabase:
            st.success("✅ Cloud Cache: Conectado")
        else:
            st.error("❌ Cloud Cache: Off (Local Mode)")        
        config['supabase'] = supabase
        
        st.header("📍 Región")
        region_options = {
            "Norte (Mungia/Euskadi)": (38.0, 48.0, -8.0, 2.0),
            "Centro (Madrid)": (35.0, 45.0, -9.0, 1.0),
            "Este (Barcelona/Cat)": (36.0, 46.0, -3.0, 7.0),
            "Noroeste (Galicia)": (38.0, 48.0, -14.0, -4.0),
        }
        selected_region_name = st.selectbox("Seleccionar Zona", list(region_options.keys()), index=0)
        
        # Adjustable Coverage Radius
        radius_delta = st.slider("📡 Radio de Cobertura (Grados)", 2.0, 30.0, 10.0, 0.5, help="Define medio lado del cuadrado de visión. 10.0 = 20x20 grados.")
        
        # Custom Coordinates Input
        st.divider()
        custom_coords = st.text_input("📍 Coordenadas (Lat, Lon)", placeholder="Ej: 43.470, -3.839")
        
        # Logic to determine BBox
        if custom_coords:
            try:
                parts = [float(p.strip()) for p in custom_coords.split(',')]
                if len(parts) == 2:
                    c_lat, c_lon = parts
                    delta = radius_delta 
                    min_lat, max_lat = c_lat - delta, c_lat + delta
                    min_lon, max_lon = c_lon - delta, c_lon + delta
                    st.toast(f"Usando coordenadas personalizadas: {c_lat}, {c_lon} (Radio: {delta})", icon="🎯")
                else:
                    st.error("Formato inválido. Use: 'Lat, Lon'")
                    min_lat, max_lat, min_lon, max_lon = region_options[selected_region_name]
            except ValueError:
                st.error("Error numérico. Asegúrese de usar puntos decimales.")
                min_lat, max_lat, min_lon, max_lon = region_options[selected_region_name]
        else:
            preset_bbox = region_options[selected_region_name]
            p_min_lat, p_max_lat, p_min_lon, p_max_lon = preset_bbox
            # Center
            c_lat = (p_min_lat + p_max_lat) / 2
            c_lon = (p_min_lon + p_max_lon) / 2
            
            delta = radius_delta
            min_lat, max_lat = c_lat - delta, c_lat + delta
            min_lon, max_lon = c_lon - delta, c_lon + delta
            
        config['bbox'] = (min_lat, max_lat, min_lon, max_lon)
        
        if st.button("🔄 Recargar Datos"):
            st.cache_data.clear()
            st.rerun()
            
        st.divider()
        resolution_options = {
            "Detalle (5.5 km/px)": 0.05,
            "Local (11 km/px)": 0.1,
            "Nacional (22 km/px)": 0.2,
            "Continental (28 km/px)": 0.25,
            "Hemisférica (55 km/px)": 0.5,
            "Global (110 km/px)": 1.0
        }
        selected_res_name = st.selectbox("Resolución del radar", list(resolution_options.keys()), index=4) # Adjusted index default 
        config['resolution'] = resolution_options[selected_res_name]
        
        # --- Legend ---
        if st.button("📝 Ver Leyenda", use_container_width=True):
             show_legend_dialog()
        
        # --- Layer Control ---
        st.divider()
        st.subheader("🗺️ Capas")
        config['layers'] = {
            'precip': st.checkbox("🌧️ Precipitación", value=True),
            'temp': st.checkbox("🌡️ Temperatura", value=False),
            'pressure': st.checkbox("⏲️ Presión", value=False),
            'wind': st.checkbox("💨 Viento", value=False)
        }

        st.divider()
        st.subheader("▶️ Animación")
        config['auto_play'] = st.checkbox("Reproducción Automática", key="auto_play")
        config['play_speed'] = st.slider("Velocidad (seg/frame)", 0.2, 2.0, 2.0)
        
        st.divider()
        if st.button("📁 Exportar Datos..."):
            config['show_export'] = True
        else:
            config['show_export'] = False
            
    return config
