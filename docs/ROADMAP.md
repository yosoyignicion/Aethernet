# Aethernet — Roadmap y estado

> Documento vivo. Última actualización: 2026-09-25 (rename + monitor pasivo + identidad matrix).

## Identidad del proyecto

- Nombre: **Aethernet** · paquete `aethernet` · scripts `aethernet` / `aethernet-ui`.
- Filosofía: instrumento local, pasivo por defecto, honesto sobre el hardware.
- Monitor mode: **solo pasivo y no disruptivo** (interfaz virtual; nunca cambia el
  tipo de la interfaz gestionada, así que **no corta tu WiFi**).

## Estado por bloque

| Bloque | Estado | Evidencia |
| --- | --- | --- |
| Rename total a `aethernet` | ✅ | `python -m aethernet`, `aethernet-ui`; `grep homenet` = 0 en src/tests |
| Migración de datos `homenet-audit` → `aethernet` | ✅ | `config.migrate_legacy` + `bootstrap_paths` |
| Calidad núcleo | ✅ | `mypy --strict` 0 en core/data; `vulture` 0; `ruff` 0 |
| Honestidad UI | ✅ | `SYS` derivado de salud; sin etiquetas inventadas |
| Monitor pasivo | ✅ | `core/monitor/*`, DB v2, CLI/API/UI, 13 tests nuevos |
| Identidad matrix | ✅ | paleta viva + `ae-fade-up`, `ae-sweep`, `ae-glitch`, `ae-glow` |
| Empaquetado `.deb` | 🟡 scaffold | `packaging/debian/*`, `scripts/build_deb.sh` (requiere debhelper) |
| Tests | ✅ | `pytest` (ver §Verificación) |

## Monitor pasivo — diseño

- `core/monitor/interface.py`: crea `aemon0` con `iw phy … interface add … type monitor`
  y `ip link set up`. **Nunca** `set type monitor` sobre la interfaz base.
- `core/monitor/hopper.py`: salto de canales con dwell configurable.
- `core/monitor/frames.py`: decoders deauth / probe / beacon / EAPOL + WPS IE.
- `core/monitor/aggregator.py`: ventanas y umbrales → `MonitorEvent`.
- `core/monitor/capture.py`: `AsyncSniffer` en hilo + ring de evidencia.
- `core/monitor/evidence.py`: hexdump para el inspector.
- Integración: `MonitorService` arranca/detiene según `settings.monitor_enabled`,
  drena eventos en cada tick y los pasa a `run_rules`. CLI `aethernet monitor …`,
  API `/monitor/*`, UI (Ajustes + Alertas + Shell + Espectro).

## Verificación

```bash
pytest -q                 # ver salida real en CI/local
ruff check src tests      # limpio
mypy --strict src/aethernet/core src/aethernet/data   # 0 errores
vulture src/aethernet/core src/aethernet/data          # 0
aethernet monitor status  # honesto si falta scapy/iw/root
```

## Pendiente (backlog)

- [ ] **Captura verificada en hardware real** con adaptador monitor-capable + `iw` +
      root (en este equipo falta `iw`/`scapy`/root; los decoders se testean con
      tramas sintéticas).
- [ ] **UI del comparador de escaneos** (`diff_scans` ya está en core).
- [ ] **Histórico de monitor en UI**: gráfica temporal de deauth/probes.
- [ ] **Aislar dispositivo**: requiere integración router/firewall.
- [ ] **PDF**: validar con `reportlab`+`matplotlib` instalados.
- [ ] **Empaquetado**: instalar `debhelper dh-python` y publicar `.deb` + `.desktop`.
- [ ] **Accesibilidad AA**: auditoría de contraste y navegación por teclado.
- [ ] **`mypy --strict` en `ui/`** (hoy con overrides por decoradores NiceGUI).

## Changelog

- **2026-09-25** — Rename total a Aethernet + migración de datos.
- **2026-09-25** — Monitor mode pasivo no disruptivo (core + DB v2 + CLI/API/UI).
- **2026-09-25** — Endurecimiento: mypy strict núcleo, vulture, evidencia persistida.
- **2026-09-25** — Identidad matrix verde y sistema de animaciones.
