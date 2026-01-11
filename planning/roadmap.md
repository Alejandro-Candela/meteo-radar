# Roadmap de Ejecución: MVP Radar Meteorológico (Revisión Semana 8)

## Objetivo

Lanzar un MVP funcional que visualice datos de precipitación interpolados y variables meteorológicas (Falso Radar) a partir de Open-Meteo en una interfaz Streamlit, con una arquitectura preparada para escalar.

## Mes 1: Fundamentos y "Falso Radar" (COMPLETADO)

### Semana 1-4: Core Architecture & MVP V1

- [x] **Arquitectura**: Setup Hexagonal, `uv` manager.
- [x] **Datos**: Ingesta Open-Meteo, Xarray, Interpolación Scipy.
- [x] **UI**: Streamlit + Leafmap (Renderizado estático).
- [x] **Caching**: `requests-cache`.

---

## Mes 2: UX, Dual-Mode y Productos de Datos (EN PROGRESO)

### Semana 5-6: Dual Mode & Advanced UX (COMPLETADO)

- [x] Refactor Dual-Mode (Histórico/Forecast).
- [x] Sliders independientes (Past -24h / Future +24h).
- [x] Expansión a Escala Macro (Península Ibérica + Francia).
- [x] Visualización optimizada (Color palettes, Non-zero filtering).

### Semana 7: Visual Refinements & Housekeeping (COMPLETADO)

- [x] Selector de Resolución (High/Medium/Low).
- [x] Leyenda en Sidebar.
- [x] Layout UI mejorado (Sliders on top).
- [x] Licenciamiento (PolyForm Noncommercial).

### Semana 8: Data Products & New Layers (ACTUAL)

- **Objetivo**: Ampliar variables y horizonte temporal.
- [ ] **Multi-Variable Layers**: Temperatura, Presión, Viento (Checkboxes UI).
- [ ] **Extended Range**: Ampliar histórico y forecast a 15 días.
- [ ] **Animation**: Reproducción temporal (Time-series playback).

### Semana 9-10: Reliability, Export & Production (FINAL)

- [ ] **Bulk Export**: Descarga de series temporales (ZIP/TIFF) [En Pausa - Bugfix pendiente].
- [ ] **Testing**: Unit & Integration Tests.
- [ ] **Containerization**: Docker.
- [ ] **Optimization**: Binary Workers para cargas pesadas.
