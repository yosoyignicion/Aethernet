# Contribuir a Aethernet

Gracias por el interés. Este documento resume cómo montar el entorno, qué
comprobaciones debe pasar cualquier cambio y las reglas que no se negocian.

## Entorno

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,ui]'        # dev: pytest/ruff/mypy/vulture · ui: NiceGUI
```

## Gate obligatorio

Antes de abrir un Pull Request, ejecuta:

```bash
./scripts/ci.sh                   # ruff + mypy --strict + vulture + pytest
./scripts/smoke.sh                # E2E UI headless (7 rutas + monitor status)
```

- `mypy --strict src/aethernet` debe dar **0**.
- `vulture` debe dar **0** en `core/` + `data/`.
- Un solo test: `pytest tests/test_spectrum.py::test_x`.

El venv puede tener un *editable install* apuntando a otro checkout; si
`python -m aethernet` falla con `No module named aethernet`, usa `PYTHONPATH=src`.

## Arquitectura (no acoplar)

- `core/` lógica pura y testeable **sin hardware ni GUI**.
- `data/` SQLite + migraciones + repositorio. `service/` daemon (nunca dibuja).
- `ui/` solo lee la DB / consume servicios; **no reimplementes** lógica ahí.
- Dependencias pesadas (`scapy`, `reportlab`, `matplotlib`, `fastapi`, `nicegui`)
  son extras **opcionales** y deben degradar con gracia, no romper.

## Reglas no negociables

- **Pasivo por defecto.** Nada de inyectar tráfico ni cambiar el tipo de la
  interfaz gestionada del usuario. El monitor usa interfaz virtual.
- **Sin red saliente** ni telemetría.
- **Honestidad:** si no se puede medir, muestra `n/d`; no inventes etiquetas ni amenazas.
- **Migraciones append-only** (`data/db.py`): añade una nueva, jamás edites una aplicada.
- No commitear secretos, MACs ni datos personales.

## Estilo y commits

- Documentación, changelog y mensajes de commit en **español**.
- [Conventional Commits](https://www.conventionalcommits.org/es/):
  `feat(...)`, `fix(...)`, `docs(...)`, `refactor(...)`, `chore(release)`, `test(...)`.
- Sin comentarios innecesarios en el código. UTF-8 estricto.
- `ruff` fija `line-length = 100` y `target-version = py311`; `mypy` apunta a
  `python_version = "3.12"` (stubs PEP 695). Es deliberado.

## Pull Requests

- Un cambio lógico por PR, con tests cuando aplique.
- Rellena la plantilla y marca el gate ejecutado.
- Actualiza `CHANGELOG.md` en la sección `Unreleased` si el cambio es visible.

¿Dudas? Abre una discusión o un issue de tipo *Propuesta de mejora*.
