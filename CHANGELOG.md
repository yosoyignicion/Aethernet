# Changelog

Todas las novedades relevantes de Aethernet. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Versionado Semántico](https://semver.org/lang/es/).

## [1.1.0] - 2026-09-26

Enfoque: convertir el análisis en **decisiones accionables** sobre el canal y las
redes, manteniendo el principio de no tocar tu router.

### Añadido
- **Asesor de canal 2.4 GHz en vivo**: recomendación sobre histórico agregado
  (estable, sin oscilar), disponibilidad por canal y "estable desde …".
- **Previsión de canal por hora y día**: tabla `channel_advisory` (migración v3),
  recogida automática en cada escaneo, `aethernet forecast show|week|record` y
  panel con gráfico por hora. Permite adelantarse a la saturación según el reloj.
- **Gestor de canal**: selección manual de tu canal, tabla comparativa de los 13
  canales (ranking/interferencia/disponibilidad), veredicto de mejora y
  escenarios por ventana (6 h / 24 h / 7 días).
- **Tu red vs vecinos**: ocupación por canal separando tu red del entorno.
- **Informe de canal**: `aethernet report --kind channel` y botón en la UI.
- **Tarjeta de canal en el Dashboard** con semáforo y acceso al gestor.
- **Vigilancia de canal en segundo plano**: avisa (con dedup) si tu canal se
  satura y hay uno claramente mejor.
- **Lista de vigilancia de redes** (`aethernet watch add|list|remove`, botón en
  el inspector) con regla `watchlist_change`: avisa si una red vigilada cambia de
  canal/seguridad o desaparece (migración v4).
- **Identificación de dispositivos** (`core/devices.classify_device`): tipo
  reconocible por fabricante/hostname, con nivel de confianza honesto; resolución
  de nombres mejorada (`getent`, `avahi-resolve`).
- Ajustes nuevos: `my_channel`, `channel_watch_*`, `forecast_*`.

### Cambiado
- `mypy --strict src/aethernet` = 0; `vulture` = 0 en todo `src/`.
- La UI de Dispositivos usa la clasificación central (testeable) en vez de un
  heurístico local.

## [1.0.0] - 2026-09-25

Primera versión estable.

### Añadido
- **Monitor mode pasivo no disruptivo**: interfaz virtual de monitor
  (`iw phy … interface add … type monitor`) que **no** altera la interfaz
  gestionada; decoders de deauth, probe requests, beacons y EAPOL/WPS;
  agregación con ventanas y umbrales; evidencia con hexdump.
- CLI `aethernet monitor start|stop|status|events`.
- API local `/monitor/status`, `/monitor/events`, `/monitor/start`, `/monitor/stop`.
- Persistencia de `Finding.evidence` en la tabla `events`.
- Tablas `monitor_sessions` y `monitor_events` (migración de esquema v2).
- Identidad visual matrix verde y animaciones (`ae-fade-up`, `ae-sweep`,
  `ae-glitch`, `ae-glow`, `ae-scanline`) con soporte de `prefers-reduced-motion`.
- `scripts/ci.sh` (CI local) y `scripts/smoke.sh` (E2E de la UI).
- Scaffold de empaquetado: `packaging/` (`.desktop`, unidad systemd de usuario,
  `debian/`) y `scripts/build_deb.sh`.
- `docs/ROADMAP.md`.

### Cambiado
- **Renombrado total** de `homenet-audit`/`homenet_audit` a
  `aethernet` (paquete, distribución y scripts).
- Migración automática de datos XDG desde `~/.local/share/homenet-audit`
  (conserva histórico; `homenet.db` → `aethernet.db`).
- El estado `SYS` de la cabecera se deriva de la salud real (`score_health`).
- `mypy --strict` limpio en todo `src/aethernet`; `vulture` sin código muerto
  en `core/` y `data/`.

### Eliminado
- Dependencia no usada `platformdirs`.
- Ajuste muerto `monitor_mode_allowed` (sustituido por la configuración real de monitor).
- Ruta temporal hardcodeada en el exportador PDF (ahora `tempfile`).

### Seguridad
- El secreto de sesión de la UI ya no está hardcodeado: se genera y persiste
  por instalación (o se toma de `AETHERNET_STORAGE_SECRET`).
- Monitor estrictamente pasivo: sin inyección ni captura de material sensible a disco.

[1.0.0]: https://example.invalid/aethernet/releases/tag/v1.0.0
