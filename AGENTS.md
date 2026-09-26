# AGENTS.md — Aethernet

Instrumento local para auditar WiFi doméstico. Python 3.11+, sin nube ni telemetría.
Docs, changelog y mensajes de commit en **español**; Conventional Commits
(`feat(...)`, `fix(...)`, `chore(release)`, `docs(...)`).

## Comandos

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,ui]'        # dev = pytest/ruff/mypy/vulture; ui = NiceGUI
./scripts/ci.sh                   # GATE REAL: ruff + mypy --strict + vulture + pytest
./scripts/smoke.sh                # E2E UI headless: 7 rutas + monitor status
pytest tests/test_spectrum.py::test_x   # un solo test
ruff check src tests
mypy --strict src/aethernet
vulture src/aethernet/core src/aethernet/data
aethernet doctor                  # veredicto honesto de hardware (útil aun sin hardware)
aethernet-ui                      # o: python -m aethernet.ui --web --port 8080
```

El CI no tolera deuda: `mypy --strict src/aethernet` = 0 y `vulture` = 0 en
`core/`+`data/`. `./scripts/ci.sh` detecta `.venv/bin/python` automáticamente.

El workflow instala solo `.[dev,ui]`: **no** trae los extras `reports`/`speedtest`,
así que los tests que hacen `pytest.importorskip("reportlab")` (PDF) se saltan. Para
cubrirlos de verdad: `pip install -e '.[dev,ui,reports,speedtest]'`.

## Arquitectura (capas, cero acoplamiento)

- `core/` lógica pura y testeable **sin hardware ni GUI** (parsers, reglas, espectro, monitor).
- `data/` SQLite WAL + migraciones + repositorio. `service/` daemon de vigilancia (nunca dibuja).
- `alerts/`, `report/`, `api/` (FastAPI local), `integration/` (speedtest, import JSON).
- `ui/` (NiceGUI "AETHERNET") **solo lee la DB / consume servicios**; nunca los reimplementa.
- Dependencias pesadas (`scapy`, `reportlab`, `matplotlib`, `fastapi`, `nicegui`) son
  **extras opcionales** y deben degradar con gracia, no romper.

## Reglas no negociables

- **Pasivo por defecto**; activo solo si el usuario lo pide. El monitor crea una
  interfaz **virtual** (`iw phy … interface add … type monitor`, `aemon0`) y **nunca**
  cambia el tipo de la interfaz gestionada (no puede cortar el WiFi).
- No inyectar tráfico ni volcar material sensible a disco. Sin red saliente.
- Honestidad: si no se puede medir, mostrar `n/d`; no inventar etiquetas ni amenazas.
- El secreto de sesión UI sale de `AETHERNET_STORAGE_SECRET` (o se persiste por
  instalación); el token de la API local, de `AETHERNET_API_TOKEN` (o `api.token` 0600).
  Nunca hardcodear.

## Convenciones

- Un cambio lógico por PR; si el cambio es visible, actualiza `CHANGELOG.md` en la
  sección `## [Unreleased]` (Keep a Changelog). Commits solo si se piden.
- `docs/history/` y `docs/design/` son **snapshots históricos** y aún citan el nombre
  antiguo `homenet-audit`; la fuente actual de arquitectura es `README.md`,
  `docs/GUIA_USO.md` y `docs/ROADMAP.md`. No los tomes como verdad.

## Gotchas

- `mypy` fija `python_version = "3.12"` (para stubs PEP 695) y `ruff` apunta a `py311`:
  es deliberado, no lo "arregles".
- `data/db.py`: `MIGRATIONS` es **append-only**; añade una migración nueva, jamás edites
  una aplicada. Versión actual: v4. La tabla de control es `schema_version`.
- Rutas XDG: config `~/.config/aethernet/config.toml`, datos/DB `~/.local/share/aethernet/`.
  Honor a `XDG_*` (el smoke test los redirige a un temp dir). Migración legacy desde
  `homenet-audit` → `aethernet`; no reintroduzcas el nombre antiguo.
- Tests sin hardware: usa las fixtures `db`, `repo`, `tmp_paths` (`tests/conftest.py`) y los
  constructores de `tests/helpers.py`. Los tests corren con `sys.path` a `src/` (no exigen `pip install -e`).
- `packaging/` + `scripts/build_deb.sh` son scaffold del `.deb` (requieren `debhelper`); no es el build principal.
- `ui/fonts/` se sirve en `/ae-fonts` (sin red): `_faces.css` + woff2, declarados en
  `[tool.setuptools.package-data]`. Si un nombre de icono no existe en Material Symbols
  se pinta el texto crudo (p. ej. `data_object` no está → usa `data_array`): verifícalo
  midiendo el ancho del glifo en el navegador (`ui/fonts` usa el set completo). El
  auto-hospedado se generó con `fontTools.varLib.instancer` (fijar FILL/wght/GRAD/opsz)
  + `ttLib.woff2 compress` (~311 KB; el original pesa ~4 MB).
- El venv puede tener un editable install apuntando a otro checkout: si `python -m aethernet`
  o `./scripts/smoke.sh` fallan con `No module named aethernet`, ejecuta con `PYTHONPATH=src`.
