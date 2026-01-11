# Roadmap de Ejecución: MVP Radar Meteorológico (8 Semanas)

## Objetivo

Lanzar un MVP funcional que visualice datos de precipitación interpolados ("Falso Radar") a partir de Open-Meteo en una interfaz Streamlit, con una arquitectura preparada para escalar.

## Mes 1: Fundamentos y "Falso Radar"

### Semana 1: Configuración y Núcleo Arquitectónico

- **Objetivos**: Setup del entorno, definición de interfaces.
- [ ] Inicializar proyecto `uv` y repositorio Git.
- [ ] Definir estructura de carpetas (Hexagonal).
- [ ] Implementar clase abstracta `WeatherDataProvider` (Pattern Strategy).
- [ ] Configurar CI/CD básico (Linter/Tests).

### Semana 2: Ingesta de Datos y Normalización (Open-Meteo)

- **Objetivos**: Traer datos y estandarizarlos.
- [ ] Implementar `OpenMeteoStrategy` usando `openmeteo-requests` y `FlatBuffers`.
- [ ] Implementar conversión a `xarray.Dataset`.
- [ ] Normalización de unidades y coordenadas (WGS84).

### Semana 3: Motor de Interpolación y Facade

- **Objetivos**: Convertir puntos en campos visuales.
- [ ] Crear `MeteorologicalFacade`.
- [ ] Implementar algoritmos de interpolación (`scipy.griddata`) para generar la malla regular.
- [ ] Optimización básica (caching de mallas estáticas).

### Semana 4: Visualización MVP (Streamlit)

- **Objetivos**: Primera interfaz de usuario.
- [ ] Setup de Streamlit con `st.session_state` para gestión de estado.
- [ ] Integración de `leafmap` para renderizar capas raster.
- [ ] Visualización estática del campo de precipitación actual.

---

## Mes 2: Robustez, Animación e Integración Real

### Semana 5: Animación Temporal y UX

- **Objetivos**: Experiencia de usuario fluida.
- [ ] Implementar slider temporal (24h predicción).
- [ ] Generación de assets para animación (GIF backend o capas dinámicas).
- [ ] Optimización de carga (Lazy evaluation).

### Semana 6: Worker Asíncrono y Persistencia

- **Objetivos**: Preparación para datos pesados.
- [ ] Implementar sistema de caché persistente (`Zarr` o disco local estructurado).
- [ ] Desacoplar la descarga de datos de la visualización (Background worker simple).

### Semana 7: Hardening y Preparación AEMET

- **Objetivos**: Estabilidad y deuda técnica.
- [ ] Implementar manejo de errores robusto (Circuit Breaker para APIs).
- [ ] Setup de pruebas de integración e infraestructura para ingesta de HDF5 (Investigación AEMET).
- [ ] Refactorización basada en feedback del MVP.

### Semana 8: Lanzamiento y Documentación Final

- **Objetivos**: Entrega del MVP.
- [ ] Dockerización completa (Dockerfile, docker-compose).
- [ ] Documentación de usuario y técnica final.
- [ ] Planificación de la Fase 2 (Integración real AEMET).
