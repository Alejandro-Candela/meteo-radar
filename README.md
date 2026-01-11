# 📡 Meteo Radar AI (MVP)

> **Visualizador Meteorológico de Alta Precisión con Análisis Histórico y Predictivo.**

![Status](https://img.shields.io/badge/Status-Beta-blue)
![License](https://img.shields.io/badge/License-NonCommercial-red)
![Stack](https://img.shields.io/badge/Tech-Streamlit%20|%20Xarray%20|%20OpenMeteo-green)

## 📋 Descripción

Meteo Radar AI es una herramienta SaaS de visualización meteorológica diseñada para ofrecer análisis detallados de precipitaciones y nubosidad. Diferenciándose de los mapas genéricos, este sistema permite:

1. **Exploración Dual**: Navegar por datos históricos (últimos 10 días) y predicciones futuras (+24h) en una misma interfaz.
2. **Alta Resolución**: Interpolación espacial avanzada para visualizar datos en micro-escala (hasta 1.1km).
3. **Visualización Profesional**: Capas de radar dinámicas, leyenda de intensidad y controles temporales intuitivos.

## 🚀 Características Principales

- **Dual Timeline**: Sliders sincronizados para viajar en el tiempo (Pasado/Futuro).
- **Selector de Resolución**: Ajuste dinámico de calidad (Alta/Media/Baja) para optimizar rendimiento o detalle.
- **Cobertura Flexible**: Regiones predefinidas (Euskadi, Madrid, Cataluña, Galicia) y búsqueda por coordenadas lat/lon personalizadas.
- **Leyenda Interactiva**: Escala visual de precipitaciones integrada en el sidebar.
- **Sticky Controls**: Interfaz optimizada con controles siempre visibles (Layout 2 columnas).

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
- **`src/adapters`**: Implementaciones externas (Cliente `OpenMeteo`, Caché).
- **`src/application`**: Casos de uso y orquestación (`MeteorologicalFacade`).
- **`src/ui`**: Interfaz de usuario (`Streamlit`).

## 📄 Licencia

Este software se distribuye bajo la **PolyForm Noncommercial License 1.0.0**.

- ✅ Uso personal y educativo permitido.
- 🚫 Uso comercial prohibido sin autorización explícita.

Ver el archivo [LICENSE](LICENSE) para más detalles.

---
**Desarrollado por Alejandro Pérez Candela - 2026**
