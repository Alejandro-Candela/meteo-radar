import folium
import leafmap.foliumap as leafmap
import streamlit as st
import tempfile
import xarray as xr
import json
import pandas as pd
from datetime import datetime, timezone
from branca.element import MacroElement
from jinja2 import Template
from src.ui.utils.helpers import get_or_upload_layer
from src.adapters.aemet import AemetAdapter

class ImageOverlayAnimation(MacroElement):
    """
    A custom Folium Element that handles client-side animation of ImageOverlays.
    It preloads all images as hidden layers and cycles their opacity.
    """
    _template = Template(u"""
        {% macro script(this, kwargs) %}
            var animation_layers_{{this.get_name()}} = {{this.layers_json}};
            var time_labels_{{this.get_name()}} = {{this.labels_json}};
            var interval_{{this.get_name()}} = null;
            var currentIndex_{{this.get_name()}} = 0;
            var isPlaying_{{this.get_name()}} = true;
            var frameDuration_{{this.get_name()}} = {{this.period}};
            
            // Storage for Leaflet Layer objects
            var leaf_layers_{{this.get_name()}} = [];

            // 1. Initialize Layers (Hidden)
            animation_layers_{{this.get_name()}}.forEach(function(frame, index) {
                var img = L.imageOverlay(frame.url, frame.bounds, {
                    opacity: 0,
                    interactive: false,
                    crossOrigin: true,
                    zIndex: {{this.zindex}}
                });
                img.addTo({{this._parent.get_name()}});
                leaf_layers_{{this.get_name()}}.push(img);
            });

            // 2. Add Custom Control for Time Display / Progress
            var infoControl = L.control({position: 'bottomleft'});

            infoControl.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'info legend');
                div.style.backgroundColor = "rgba(255, 255, 255, 0.8)";
                div.style.padding = "10px";
                div.style.borderRadius = "5px";
                div.style.boxShadow = "0 0 15px rgba(0,0,0,0.2)";
                div.style.fontFamily = "sans-serif";
                div.style.fontSize = "14px";
                div.style.minWidth = "200px";
                
                div.innerHTML = `
                    <div style="font-weight: bold; margin-bottom: 5px;">Tiempo: <span id="time-label-${this._name}">--:--</span></div>
                    <div style="width: 100%; height: 5px; background: #ddd; border-radius: 3px;">
                        <div id="time-progress-${this._name}" style="width: 0%; height: 100%; background: #007bff; border-radius: 3px; transition: width 0.2s;"></div>
                    </div>
                `;
                return div;
            };
            infoControl.addTo({{this._parent.get_name()}});

            // 3. Function to Update Frame & UI
            function showFrame_{{this.get_name()}}(index) {
                leaf_layers_{{this.get_name()}}.forEach(function(layer, i) {
                    if (i === index) {
                        layer.setOpacity({{this.opacity}});
                    } else {
                        layer.setOpacity(0);
                    }
                });
                
                // Update Control
                if (time_labels_{{this.get_name()}}.length > index) {
                     var label = time_labels_{{this.get_name()}}[index];
                     var pct = ((index + 1) / time_labels_{{this.get_name()}}.length) * 100;
                     
                     var lblEl = document.getElementById(`time-label-${this._name}`);
                     if(lblEl) lblEl.innerText = label;
                     
                     var barEl = document.getElementById(`time-progress-${this._name}`);
                     if(barEl) barEl.style.width = pct + "%";
                }
            }

            // 4. Animation Loop
            function startAnimation_{{this.get_name()}}() {
                if (interval_{{this.get_name()}}) clearInterval(interval_{{this.get_name()}});
                interval_{{this.get_name()}} = setInterval(function() {
                    currentIndex_{{this.get_name()}} = (currentIndex_{{this.get_name()}} + 1) % leaf_layers_{{this.get_name()}}.length;
                    showFrame_{{this.get_name()}}(currentIndex_{{this.get_name()}});
                }, frameDuration_{{this.get_name()}});
            }

            // Start immediately
            showFrame_{{this.get_name()}}(0);
            startAnimation_{{this.get_name()}}();

        {% endmacro %}
    """)

    def __init__(self, data, bounds, time_labels=None, period=500, zindex=1, opacity=0.6):
        super(ImageOverlayAnimation, self).__init__()
        self._name = 'ImageOverlayAnimation'
        
        # Prepare JSON data: [{url: '...', bounds: [[lat1, lon1], [lat2, lon2]]}, ...]
        self.layers_json = json.dumps([
            {'url': url, 'bounds': bounds} for url in data
        ])
        
        # Prepare labels
        self.labels_json = json.dumps(time_labels if time_labels else [])
        
        self.period = period
        self.zindex = zindex
        self.opacity = opacity

def display_map(
    active_ds: xr.Dataset, 
    active_time: datetime,
    bbox_config: tuple, 
    layers_state: dict,
    supabase_client=None,
    aemet_key: str = None,
    animate: bool = False,
    animation_speed: int = 500
):
    """
    Renders the map. Supports static mode (single time) or animation mode (full timeline).
    """
    min_lat, max_lat, min_lon, max_lon = bbox_config
    
    # Base Map
    m = leafmap.Map(
        center=[(max_lat+min_lat)/2, (max_lon+min_lon)/2],
        zoom=5.5,
        draw_control=False,
        measure_control=False,
    )
    m.add_basemap("CartoDB.Positron")
    
    if active_ds is None:
         m.to_streamlit(height=600, key="radar_map")
         return

    # --- 1. Calculate Bounds ---
    try:
        lat_dim = 'latitude' if 'latitude' in active_ds.coords else 'lat' if 'lat' in active_ds.coords else 'y'
        lon_dim = 'longitude' if 'longitude' in active_ds.coords else 'lon' if 'lon' in active_ds.coords else 'x'
        
        lats = active_ds[lat_dim].values
        lons = active_ds[lon_dim].values
        
        lat_res = abs(float(lats[1] - lats[0])) if len(lats) > 1 else 0.01
        lon_res = abs(float(lons[1] - lons[0])) if len(lons) > 1 else 0.01
            
        actual_min_lat = float(lats.min())
        actual_max_lat = float(lats.max())
        actual_min_lon = float(lons.min())
        actual_max_lon = float(lons.max())
        
        # Adjustments
        lat_offset = 0.10 
        lon_offset = 0.43
        half_res_lat = lat_res / 2.0
        half_res_lon = lon_res / 2.0
        
        overlay_bounds = [
            [(actual_min_lat - half_res_lat) - lat_offset, (actual_min_lon - half_res_lon) + lon_offset], 
            [(actual_max_lat + half_res_lat) - lat_offset, (actual_max_lon + half_res_lon) + lon_offset]
        ]
    except Exception as e:
        print(f"Error calculating bounds: {e}")
        overlay_bounds = [[min_lat, min_lon], [max_lat, max_lon]]

    bbox_tuple = (min_lat, max_lat, min_lon, max_lon)

    # --- 2. Render Layers ---
    
    # Helper to process a layer (Static or Animation)
    def add_layer(var_name, display_name, colormap, vmin, vmax, zindex, opacity=0.5):
        if var_name not in active_ds: return

        if animate:
            # Generate ALL frames
            urls = []
            labels = []
            times = active_ds.time.values
            
            # Limit to reasonable number if needed
            for t in times:
                # Convert numpy time/int to py datetime safely using pandas
                dt = pd.to_datetime(t).to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                # Format label for UI
                labels.append(dt.strftime("%d/%m %H:%M"))
                
                # Use the clean python datetime 'dt' for selection to avoid int64 vs datetime64 mismatch
                layer_data = active_ds[var_name].sel(time=dt, method="nearest")
                
                url = get_or_upload_layer(
                    supabase_client, layer_data, var_name, bbox_tuple, dt,
                    colormap=colormap, vmin=vmin, vmax=vmax
                )
                urls.append(url)
            
            # Add Animation Element
            anim = ImageOverlayAnimation(urls, overlay_bounds, time_labels=labels, period=animation_speed, zindex=zindex, opacity=opacity)
            m.add_child(anim)
            
        else:
            # Static Single Frame
            layer_data = active_ds[var_name].sel(time=active_time, method="nearest")
            path = get_or_upload_layer(
                 supabase_client, layer_data, var_name, bbox_tuple, active_time,
                 colormap=colormap, vmin=vmin, vmax=vmax
            )
            folium.raster_layers.ImageOverlay(
                image=path, bounds=overlay_bounds, name=display_name,
                opacity=opacity, interactive=False, cross_origin=False, zindex=zindex
            ).add_to(m)

    # --- 3. Add Active Layers ---
    
    # Precipitation
    if layers_state.get('precip', True):
        # Calculate Global Max for consistent animation scale
        global_max = 5.0
        if 'precipitation' in active_ds:
            global_max = max(5.0, float(active_ds['precipitation'].max().item()))
            
        add_layer('precipitation', "Radar Precipitación", 
                 ["#00000000", "#7CFC00", "#32CD32", "#FFFF00", "#FF8C00", "#FF0000"], 
                 0, global_max, 1, 0.6)

    # Temperature
    if layers_state.get('temp', False):
        add_layer('temperature', "Temperatura (ºC)", "RdYlBu_r", None, None, 2, 0.5)

    # Pressure
    if layers_state.get('pressure', False):
        add_layer('pressure', "Presión (hPa)", "viridis", None, None, 3, 0.5)

    # Wind
    if layers_state.get('wind', False):
        add_layer('wind_speed', "Viento (km/h)", "YlOrRd", None, None, 4, 0.5)

    # Clouds
    if layers_state.get('cloud', False):
        add_layer('cloud_cover', "Nubes (%)", "Greys", 0, 100, 5, 0.5)

    # Humidity
    if layers_state.get('humidity', False):
        add_layer('humidity', "Humedad (%)", "GnBu", 0, 100, 6, 0.5)

    # AEMET Radar (Static Overlay only)
    if layers_state.get('aemet_radar', False) and aemet_key:
        try:
            adapter = AemetAdapter(aemet_key)
            overlay_url = adapter.get_radar_composite_url()
            if overlay_url:
                folium.raster_layers.ImageOverlay(
                    image=overlay_url, 
                    bounds=adapter.national_bounds, 
                    name="AEMET Radar (Oficial)",
                    opacity=0.7, 
                    interactive=False, 
                    cross_origin=True, 
                    zindex=10
                ).add_to(m)
        except Exception:
            pass

    # Render
    m.to_streamlit(height=600, key="radar_map")
