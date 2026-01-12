import streamlit as st
import os
from datetime import datetime, timedelta
from src.application.exporter import BulkExportService
from src.ui.utils.helpers import get_radar_legend_html

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

@st.dialog("Leyenda de Capas")
def show_legend_dialog():
    st.markdown("### 🌧️ Precipitación")
    st.markdown(get_radar_legend_html(), unsafe_allow_html=True)
    
    st.markdown("### 🌡️ Temperatura (ºC)")
    st.markdown("""
    <div style="display: flex; align-items: center;">
      <span style='margin-right:8px'>Frío</span>
      <div style='flex-grow:1; height:20px; background: linear-gradient(to right, #313695, #4575b4, #74add1, #abd9e9, #e0f3f8, #ffffbf, #fee090, #fdae61, #f46d43, #d73027, #a50026); border-radius: 4px;'></div>
      <span style='margin-left:8px'>Calor</span>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: gray;">
        <span>-20ºC</span><span>0ºC</span><span>20ºC</span><span>40ºC</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### ⏲️ Presión (hPa)")
    st.markdown("""
    <div style="display: flex; align-items: center;">
      <span style='margin-right:8px'>Baja</span>
      <div style='flex-grow:1; height:20px; background: linear-gradient(to right, #440154, #3b528b, #21908d, #5dc863, #fde725); border-radius: 4px;'></div>
      <span style='margin-left:8px'>Alta</span>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: gray;">
        <span>980</span><span>1000</span><span>1020</span><span>1040</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 💨 Viento (km/h)")
    st.markdown("""
    <div style="display: flex; align-items: center;">
      <span style='margin-right:8px'>Calma</span>
      <div style='flex-grow:1; height:20px; background: linear-gradient(to right, #ffffb2, #fecc5c, #fd8d3c, #f03b20, #bd0026); border-radius: 4px;'></div>
      <span style='margin-left:8px'>Fuerte</span>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: gray;">
        <span>0</span><span>20</span><span>50</span><span>100+</span>
    </div>
    """, unsafe_allow_html=True)
