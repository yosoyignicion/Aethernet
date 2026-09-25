# Aethernet

Instrumento local para auditar tu WiFi doméstico. No es un script con botones
pegados: es una arquitectura en capas, sin nube, sin telemetría y honesta sobre
lo que el hardware realmente puede hacer.

> Pasiva por defecto, activa cuando tú lo pides. Backend completo (CLI + API) e
> interfaz gráfica "AETHERNET" en NiceGUI, traducida del diseño retro-futurista
> de Stitch.

## Arquitectura (tres capas, cero acoplamiento)

| Capa | Paquete | Responsabilidad |
| --- | --- | --- |
| Core | `aethernet.core` | Lógica pura y testeable: parseo `nmcli`/`iw`, ARP, motor de reglas, salud, espectro, snapshots, OUI, didáctica. |
| Datos | `aethernet.data` | SQLite con WAL, migraciones, histórico, snapshots y eventos. |
| Servicio | `aethernet.service` | Daemon de vigilancia continua; nunca dibuja. La GUI solo lee la DB. |
| Alertas | `aethernet.alerts` | Cola, deduplicación, filtros (horas silenciosas, mutings) y `notify-send`. |
| Informes | `aethernet.report` | Exportadores Markdown / JSON / CSV / PDF. |
| API | `aethernet.api` | FastAPI opcional en `127.0.0.1` para tus scripts. |
| Integraciones | `aethernet.integration` | `speedtest-cli` e importación de JSON de WiFi Analyzer. |

Principios: los *parsers* son funciones puras (se testean sin hardware), las
reglas son clases independientes, y las dependencias pesadas (`scapy`,
`reportlab`, `matplotlib`, `fastapi`) son **opcionales** con degradación
graciosa.

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                 # solo stdlib
pip install -e '.[lan,reports,api,speedtest,ui]'   # extras opcionales (ui = NiceGUI)
```

Requisitos del sistema: `nmcli` (NetworkManager). Recomendado: `iw`, `ethtool`,
`notify-send`. `scapy` + root habilitan el ARP scan activo; `iw` habilita el
diagnóstico de bandas y monitor mode.

## Uso rápido

```bash
aethernet doctor                      # qué puede y qué no tu hardware
aethernet scan --no-lan               # escaneo pasivo
aethernet scan --active --lan         # barrido activo + inventario LAN
aethernet status                      # saludo, contadores y última amenaza
aethernet networks --open             # inventario con filtros
aethernet analyze                     # motor de reglas sobre el último escaneo
aethernet events --unread             # bandeja de eventos
aethernet report --format md          # informe Markdown
aethernet compare                     # diff entre los dos últimos escaneos
aethernet daemon start                # vigilancia continua en background
aethernet config set my_ssids MiRed    # define tu red para evil twin/health
aethernet monitor status              # monitor pasivo (honesto si falta hardware)
aethernet monitor start               # captura deauth/probes/beacons/EAPOL
aethernet monitor events              # eventos capturados
```

### Monitor pasivo (no disruptivo)

Aethernet nunca cambia el tipo de tu interfaz gestionada: crea una **interfaz
virtual** de monitor (`iw phy … interface add … type monitor`). Si el driver no
lo permite, se deshabilita con mensaje claro en lugar de cortar tu WiFi. Solo
escucha — no inyecta ni captura material sensible a disco.

Requiere: adaptador con monitor mode, `iw`, `scapy` (`pip install 'aethernet[monitor]'`)
y privilegios (root / `CAP_NET_ADMIN`). `aethernet doctor` reporta el veredicto.

Todos los comandos aceptan `--json` para integrarlos con otras herramientas.

## Interfaz gráfica (AETHERNET)

```bash
pip install -e '.[ui]'
aethernet-ui              # ventana nativa si hay pywebview; si no, navegador
python -m aethernet.ui --web --port 8080
```

Pantallas: Dashboard (`/`), Espectro (`/espectro`), Redes (`/redes`),
Dispositivos (`/dispositivos`), Alertas (`/alertas`), Informes (`/informes`) y
Ajustes (`/ajustes`). Consume los mismos servicios que el CLI; los escaneos
corren en segundo plano y la UI nunca bloquea. Las métricas que no se pueden
medir se muestran como `n/d` (honestidad por diseño).

Identidad visual "AETHERNET": paleta matrix verde sobre negro profundo y
animaciones sutiles (`ae-fade-up`, `ae-sweep`, `ae-glitch`, `ae-glow`), todas
respetando `prefers-reduced-motion`.

## Dónde vive todo

- Configuración: `~/.config/aethernet/config.toml`
- Datos y DB: `~/.local/share/aethernet/aethernet.db`
- Informes: `~/.local/share/aethernet/reports/`
- Caché OUI: `~/.cache/aethernet/oui.tsv`

## Tests

```bash
pip install -e '.[dev]'
pytest
ruff check src tests
```

La suite cubre parseo, reglas, salud, espectro, snapshots, repositorio,
filtros de alerta y el servicio con escáneres simulados.
