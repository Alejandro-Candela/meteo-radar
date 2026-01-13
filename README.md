# 📡 Meteo Radar AI (MVP)

> **High-Precision Meteorological Visualizer with Historical and Predictive Analysis.** - [View Deployed Demo](https://meteo-radar.streamlit.app/)

![Status](https://img.shields.io/badge/Status-Beta-blue)
![License](https://img.shields.io/badge/License-NonCommercial-red)
![Stack](https://img.shields.io/badge/Tech-Streamlit%20|%20Xarray%20|%20OpenMeteo-green)

## 📋 Description

Meteo Radar AI is a SaaS meteorological visualization tool designed to offer detailed analysis of precipitation and cloud cover. Differentiating itself from generic maps, this system allows for advanced interpolation and smart data persistence.

### 🌟 New Features (v1.2)

- **Flicker-Free Animation**: Client-side animation engine (Leaflet/JS) for smooth transitions without page reloads.
- **Optimistic UI & Threading**: Instant generation of local layers and background Supabase uploads for a fluid user experience.
- **Dual Mode**: Hybrid navigation between past (10-day History) and future (OpenMeteo Forecast).

## 🚀 Key Features

- **Dual Timeline**: Synchronized sliders to travel through time (Past/Future).
- **Resolution Selector**: Dynamic quality adjustment (High/Medium/Low) to optimize performance or detail.
- **Flexible Coverage**: Predefined regions (Basque Country, Madrid, Catalonia, Galicia) and custom lat/lon coordinate search.
- **Interactive Legend**: Integrated visual precipitation scale in the sidebar.
- **Sticky Controls**: Optimized interface with always-visible controls.
- **Offline/Local Fallback**: Works even if the database (Supabase) is unconnected, using local base64 image generation.

## 🛠️ Installation and Usage

This project uses `uv` for dependency management and Python 3.12+.

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) installed.

### Quick Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd meteo-radar

# 2. Install dependencies
uv sync

# 3. Run application
uv run streamlit run src/ui/app.py
```

## 🏗️ Architecture

The system follows a **Hexagonal Architecture (Ports & Adapters)** to ensure maintainability:

- **`src/domain`**: Pure business logic (Provider interfaces, `Xarray` data models).
- **`src/adapters`**: External implementations (`OpenMeteo` Client, Supabase Client, AemetAdapter).
- **`src/application`**: Use cases and orchestration (`MeteorologicalFacade`).
- **`src/ui`**: User Interface (`Streamlit`).

### Performance Optimization

To avoid latency in deployments (like Streamlit Cloud), we use **Background Threading** strategies:

1. The layer is generated locally in RAM and served immediately as Base64.
2. A secondary thread converts the DataArray to GeoTIFF and uploads both the PNG and TIF to the cloud (Supabase) for persistence.

## 📄 License

This software is distributed under the **PolyForm Noncommercial License 1.0.0**.

- ✅ Personal and educational use permitted.
- 🚫 Commercial use prohibited without explicit authorization.

See the [LICENSE](LICENSE) file for more details.

---
**Developed by Alejandro Pérez Candela - 2026**
