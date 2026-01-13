# 📡 Meteo Radar AI (MVP)

> **Visualizador Meteorológico de Alta Precisión con Análisis Histórico y Predictivo.** - [Ver Demo Desplegada](https://meteo-radar.streamlit.app/)

![Status](https://img.shields.io/badge/Status-Beta-blue)
![License](https://img.shields.io/badge/License-NonCommercial-red)
![Stack](https://img.shields.io/badge/Tech-Streamlit%20|%20Xarray%20|%20OpenMeteo-green)

## 📋 Descripción

Meteo Radar AI es una herramienta SaaS de visualización meteorológica diseñada para ofrecer análisis detallados de precipitaciones y nubosidad. Diferenciándose de los mapas genéricos, este sistema permite interpolación avanzada y persistencia de datos inteligente.

### 🌟 Novedades (v1.2)

- **Flicker-Free Animation**: Motor de animación cliente-side (Leaflet/JS) para transiciones suaves sin recargar la página.
- **Optimistic UI & Threading**: Generación instantánea de capas locales y subida a Supabase en segundo plano para una experiencia de usuario fluida.
- **Dual Mode**: Navegación híbrida entre pasado (Histórico 10 días) y futuro (Predicción OpenMeteo).

## 🚀 Características Principales

- **Dual Timeline**: Sliders sincronizados para viajar en el tiempo (Pasado/Futuro).
- **Selector de Resolución**: Ajuste dinámico de calidad (Alta/Media/Baja) para optimizar rendimiento o detalle.
- **Cobertura Flexible**: Regiones predefinidas (Euskadi, Madrid, Cataluña, Galicia) y búsqueda por coordenadas lat/lon personalizadas.
- **Leyenda Interactiva**: Escala visual de precipitaciones integrada en el sidebar.
- **Sticky Controls**: Interfaz optimizada con controles siempre visibles.
- **Offline/Local Fallback**: Funciona incluso si la base de datos (Supabase) no está conectada, usando generación de imágenes en base64 local.

## 🛠️ Instalación y Uso

Este proyecto utiliza `uv` para la gestión de dependencias y Python 3.12+.

### Prerrequisitos

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) instalado.

### Setup Rápido

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd meteo-radar

# 2. Instalar dependencias
uv sync

# 3. Ejecutar aplicación
uv run streamlit run src/ui/app.py
```

## 🏗️ Arquitectura

El sistema sigue una arquitectura **Hexagonal (Ports & Adapters)** para garantizar mantenibilidad:

- **`src/domain`**: Lógica de negocio pura (Interfaces de proveedores, modelos de datos `Xarray`).
- **`src/adapters`**: Implementaciones externas (Cliente `OpenMeteo`, Cliente Supabase, AemetAdapter).
- **`src/application`**: Casos de uso y orquestación (`MeteorologicalFacade`).
- **`src/ui`**: Interfaz de usuario (`Streamlit`).

### Optimización de Rendimiento

Para evitar latencia en despliegues (como Streamlit Cloud), utilizamos estrategias de **Background Threading**:

1. La capa se genera localmente en RAM y se sirve de inmediato como Base64.
2. Un hilo secundario convierte el DataArray a GeoTIFF y sube tanto el PNG como el TIF a la nube (Supabase) para persistencia.

## 📄 Licencia

Este software se distribuye bajo la **PolyForm Noncommercial License 1.0.0**.

- ✅ Uso personal y educativo permitido.
- 🚫 Uso comercial prohibido sin autorización explícita.

Ver el archivo [LICENSE](LICENSE) para más detalles.

---
**Desarrollado por Alejandro Pérez Candela - 2026**
