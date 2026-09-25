# Changelog

Todas las novedades relevantes de Aethernet. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Versionado Semántico](https://semver.org/lang/es/).

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
