# Auditoría y seguimiento — HomeNet Audit / AETHERNET

> Documento vivo de estado. Refleja qué está construido, qué falta y con qué
> evidencia se ha verificado. Última actualización: 2026-09-25.

## 0. Resumen ejecutivo

| Capa | Estado | Evidencia |
| --- | --- | --- |
| Backend (core + data + service + alerts + report + api) | ✅ Completo | `pytest`: 81 passed · `ruff`: clean · escaneo real de 54 redes |
| Frontend (traducción de Stitch → NiceGUI) | ✅ Completo funcional | 7 rutas responden HTTP 200 sin errores en servidor real |
| Diseño visual (tokens, tipografía, shell) | ✅ Implementado | `src/homenet_audit/ui/theme.py`, `shell.py` |

Decisiones tomadas:
- **Librería GUI:** NiceGUI 3 (motor web real: Quasar + Tailwind + ECharts). Es
  la traducción más fiel del mockup Tailwind/Material-3 de Stitch y ofrece
  ventana nativa vía pywebview con fallback a navegador.
- **Datos reales, no maquetas:** donde el backend no puede medir algo sin
  monitor mode (SNR, noise floor, paquetes/s, dwell), la UI muestra `n/d` con
  nota, en coherencia con el principio de honestidad de la app.

## 1. Mapa Stitch → implementación

| Pantalla Stitch | Ruta | Archivo | Estado |
| --- | --- | --- | --- |
| `dashboard_telemetr_a_rf` | `/` | `ui/pages/dashboard.py` | ✅ Gauge salud, 4 tarjetas, congestión 24 h |
| `espectro_an_lisis_espectral_2.4ghz` | `/espectro` | `ui/pages/spectrum.py` | ✅ Barras por canal, heatmap, diagnóstico, co-interferencia |
| `redes_inventario_y_se_al` | `/redes` | `ui/pages/networks.py` | ✅ Tabla, filtros, búsqueda, inspector RSSI |
| `dispositivos_gesti_n_de_nodos_lan` | `/dispositivos` | `ui/pages/devices.py` | ✅ Tarjetas, confianza/alias, regla MAC |
| `alertas_l_nea_temporal_de_incidentes` | `/alertas` | `ui/pages/alerts.py` | ✅ Contadores, timeline, inspector de evento |
| `informes_generaci_n_y_exportaci_n_de_telemetr_a` | `/informes` | `ui/pages/reports.py` | ✅ Presets, módulos, export md/pdf/json/csv, preview |
| `ajustes_calibraci_n_de_firmware_y_sistema` | `/ajustes` | `ui/pages/settings.py` | ✅ Hardware, muestreo, triggers, paletas, persistencia |
| `aethernet_telemetry_logo` | shell | `ui/shell.py` | ✅ Logo SVG inline |

## 2. Sistema de diseño implementado

- **Tokens**: `ui/theme.py:COLORS` (paleta exacta del mockup: void `#0A0E14`,
  surface `#181c22`, mint `#00E5A0`, cyan `#84cfff`, amber `#ffbe36`, coral `#FF4D6D`).
- **Tipografía**: Space Grotesk (títulos), Inter (interfaz), JetBrains Mono
  (telemetría), Material Symbols Outlined (iconos), vía Google Fonts.
- **Componentes**: clases semánticas `ae-panel`, `ae-card`, `ae-sub`, `ae-chip`,
  `ae-label`, `ae-metric`, `ae-divider`, `ae-pulse`, `ae-ping`; override del
  `q-table` de Quasar para el look de rejilla de instrumento.
- **Shell**: cabecera 64 px, sidebar 220 px con navegación activa, pie de estado
  40 px; actualización en vivo de adaptador/última-vez/estado de escaneo.

## 3. Gráficas (ECharts) y datos que las alimentan

| Gráfica | Opción | Fuente real |
| --- | --- | --- |
| Gauge de salud | `charts.gauge` | `core.health.score_health` |
| Congestión 24 h | `charts.congestion_area` | `Repository.hourly_congestion` |
| Barras por canal | `charts.channel_bars` | `core.spectrum.occupancy` |
| Heatmap hora×canal | `charts.heatmap` | `Repository.hourly_channel_matrix` |
| Radar polar | `charts.polar` | `core.spectrum.polar_points` |
| Sparkline RSSI | `charts.sparkline` | `Repository.signal_series` |
| Ocupación informe | `charts.occupancy_report_bars` | `core.spectrum.occupancy` |

## 4. Auditoría funcional (spec.md)

| # | Función | Estado backend | Estado UI |
| --- | --- | --- | --- |
| 1 | Dashboard | ✅ | ✅ gauge + contadores + histórico |
| 2 | Espectro | ✅ | ✅ barras + heatmap + recomendación; radar polar disponible en `charts.polar` (no montado en página) |
| 3 | Inventario WiFi | ✅ | ✅ tabla + filtros + inspector |
| 4 | Anomalías | ✅ 12 reglas | ✅ timeline de eventos (evidencia textual) |
| 5 | Inventario LAN | ✅ | ✅ tarjetas + confianza/alias |
| 6 | Vigilancia continua | ✅ daemon | ✅ estado en pie; control por CLI/API |
| 7 | Alertas | ✅ | ✅ contadores + filtros + leer/silenciar |
| 8 | Informes | ✅ md/json/csv/pdf* | ✅ export + preview en vivo |
| 9 | Comparador snapshots | ✅ | ⏳ pendiente de UI (CLI `compare` disponible) |
| 10 | Módulo didáctico | ✅ | ✅ glosario en Ajustes |
| 11 | Configuración honesta | ✅ `doctor` | ✅ autotest + límites de hardware |
| 12 | Integraciones | ✅ | ⏳ speedtest/importer solo CLI |

\* PDF requiere extra `reportlab`+`matplotlib`.

## 5. Verificación (gates)

```bash
python3 -m pytest            # 81 passed
python3 -m ruff check src tests   # All checks passed
homenet-audit-ui --web       # 7 rutas -> HTTP 200, 0 errores
```

## 6. Brechas y próximos pasos

- [ ] **Captura monitor mode real** (deauth/probes/WPS/handshake): reglas listas,
      falta módulo de captura con scapy + root y montar sus datos en Alertas.
- [ ] **UI del comparador de escaneos** (página `/comparar` o pestaña en Redes).
- [ ] **Persistir evidencia cruda** en `events` (hoy solo título/cuerpo) para el
      inspector de evidencia estilo hexdump.
- [ ] **Radar polar** como gráfica propia en Espectro.
- [ ] **Aislar dispositivo** requiere integración router/firewall (botón disabled honesto).
- [ ] **Métricas de monitor** (SNR, noise floor, paquetes/s, dwell) → `n/d` hasta
      implementar captura.
- [ ] **Empaquetado** `.deb`/AppImage con `flet`-style build o pywebview + systemd.
- [ ] **Accesibilidad**: revisar contraste AA y navegación por teclado completa.
- [ ] **typecheck** `mypy` (declarado en extras, no ejecutado aún).

## 7. Changelog

- **2026-09-25** — Backend completo (capas core/data/service/alerts/report/api),
  81 tests, lint limpio.
- **2026-09-25** — Traducción del frontend Stitch a NiceGUI: shell + 7 páginas +
  ECharts + tema AETHERNET. Verificado con servidor real.
