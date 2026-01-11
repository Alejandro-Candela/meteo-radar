# Architectural Decision Record (ADR) - Sistema de Radar Meteorológico Modular

## 1. Contexto y Visión

El objetivo es construir un sistema de predicción inmediata (nowcasting) que evolucione desde el consumo de APIs (Open-Meteo) hacia datos de radar real (AEMET/ODIM) y finalmente modelos de IA Generativa. La prioridad actual es un MVP en 2 meses que simule la experiencia de un radar utilizando datos numéricos interpolados.

## 2. Decisiones de Arquitectura de Software

### 2.1 Patrón Core: Arquitectura Hexagonal (Ports & Adapters)

- **Dominio**: Lógica pura de negocio (alertas, umbrales). Sin dependencias externas.
- **Puertos**: `WeatherDataProvider` (Interfaz abstracta).
- **Adaptadores**: `OpenMeteoAdapter`, `AemetAdapter`, `MockAdapter`.
- **Beneficio**: Permite cambiar el backend de datos sin tocar el frontend ni la lógica de negocio.

### 2.2 Patrón de Diseño: Estrategia (Strategy Pattern)

- Define una familia de algoritmos (Fuentes de datos) intercambiables.
- Permite inyección de dependencias en tiempo de ejecución (ej. cambiar de API a IA si la latencia es alta).

### 2.3 Orquestación: Facade Pattern

- `MeteorologicalFacade`: Unifica la complejidad de sistemas de coordenadas, unidades y orígenes de datos.
- Responsable de la normalización final antes de entregar datos al frontend.

## 3. Stack Tecnológico (The "Velocity" Stack)

### 3.1 Lenguaje y Gestión de Paquetes

- **Python 3.12+**
- **Gestor**: `uv` (Strict). Rendimiento y gestión de dependencias determinista.
- **Linting/Formatting**: `ruff` (vía `uv`).

### 3.2 Ciencia de Datos & "Universal Grid"

- **Estructura de Datos**: `xarray`. Estándar N-dimensional (Time, Lat, Lon, Variable).
- **Persistencia**: `Zarr` (Cloud-native, chunked storage) para Data Lake local. `GeoTIFF` efímeros para visualización.
- **Interpolación**: `scipy.interpolate.griddata` (Método lineal/cúbico).
- **Entorno Geoespacial**: `pyproj`, `rasterio`.

### 3.3 Interfaz de Usuario (MVP)

- **Framework**: `Streamlit`.
- **Mapas**: `leafmap` (Backend folium/ipyleaflet ligero). Soporte de capas raster.
- **Gráficos**: `plotly` o `altair` nativo de Streamlit.

### 3.4 API & Backend

- **Framework**: `FastAPI` (Futuro/Integrado en contenedores). Para el MVP inicial, Streamlit puede consumir directamente la Facade, pero se diseñará desacoplado.

## 4. Estándares de Código

- **Type Safety**: Type hints obligatorios en todo el código.
- **Testing**: `pytest`. Estructura espejo en `tests/`.
- **Configuración**: Variables de entorno (`.env`) manejadas con `pydantic-settings`.
