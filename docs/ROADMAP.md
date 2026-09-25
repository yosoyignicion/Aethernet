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
./scripts/ci.sh           # ruff + mypy --strict + vulture + pytest
./scripts/smoke.sh        # UI headless: 7 rutas + monitor status
aethernet monitor status  # honesto si falta scapy/iw/root
```

Estado de gates (v1.0.0): `ruff` limpio · `mypy --strict src/aethernet` = 0 ·
`vulture` core/data = 0 · `pytest` 117 passed · UI 7/7 rutas HTTP 200.

## Validación de monitor en hardware (pendiente, bloqueante externo)

En este equipo no se pudo verificar (falta `iw`, `scapy` y root). Checklist para
cerrarlo en un equipo con adaptador monitor-capable:

- [ ] `iw dev` lista la interfaz; `aethernet doctor` muestra "Monitor pasivo: disponible".
- [ ] `aethernet monitor start` crea `aemon0` y **no corta** la conexión WiFi gestionada.
- [ ] `aethernet monitor status` muestra `running=true` y canal actual cambiando.
- [ ] Generar tráfico (otro dispositivo) y ver eventos: `aethernet monitor events`.
- [ ] `aethernet monitor stop` elimina `aemon0` y restaura el estado.
- [ ] Sin `iw`/`scapy`/root: `monitor status` reporta motivo claro y no falla.

Capabilities para el monitor pasivo (no necesario para el resto):

```bash
# opción A: ejecutar bajo demanda
sudo -E aethernet monitor start

# opción B: unidad de SISTEMA con capabilities (no de usuario)
# [Service]
# AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
# CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
```

## Pendiente (backlog)

- [ ] **Captura verificada en hardware real** (ver checklist arriba).
- [ ] **UI del comparador de escaneos** (`diff_scans` ya está en core).
- [ ] **Histórico de monitor en UI**: gráfica temporal de deauth/probes.
- [ ] **Aislar dispositivo**: requiere integración router/firewall.
- [ ] **PDF**: validar con `reportlab`+`matplotlib` instalados.
- [ ] **Empaquetado `.deb`**: instalar `debhelper dh-python pybuild-plugin-pyproject`
      y ejecutar `scripts/build_deb.sh` (decisión: aparcado).
- [ ] **systemd user**: instalar `packaging/aethernet.service` en
      `~/.config/systemd/user/` y `systemctl --user enable --now aethernet`.
- [ ] **CI en GitHub Actions** (tras feedback humano).
- [ ] **Accesibilidad AA**: auditoría de contraste y navegación por teclado.
- [x] **`mypy --strict`** en todo `src/aethernet` (0 errores).

## Asesor de canal 2.4 GHz (en vivo)

En `/espectro`: recomienda el mejor canal (1/6/11) a partir de **histórico
agregado** (`channel_stats`) y no de un escaneo suelto, para no inducir cambios
que desestabilicen la red. Muestra disponibilidad por canal, "estable desde …" y
botón para copiar el canal. **Aethernet no cambia tu router**; tú lo aplicas.

Interpretación en UI: redes vecinas con SSID repetido o MAC virtual se etiquetan
como *malla/multi-banda (informativo)*, no como amenaza; solo sería sospechoso
imitar tu propio SSID con otro BSSID.

## Changelog

- **2026-09-26** — Asesor de canal 2.4 GHz en vivo (histórico, estable) e
  interpretación de SSID compartido / MAC virtual en la UI.
- **2026-09-25** — Rename total a Aethernet + migración de datos.
- **2026-09-25** — Monitor mode pasivo no disruptivo (core + DB v2 + CLI/API/UI).
- **2026-09-25** — Endurecimiento: mypy strict núcleo, vulture, evidencia persistida.
- **2026-09-25** — Identidad matrix verde y sistema de animaciones.
