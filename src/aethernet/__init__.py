"""Aethernet — instrumento local para auditar tu WiFi doméstico.

Arquitectura en tres capas con cero acoplamiento:

* :mod:`aethernet.core`     — lógica pura, testeable sin GUI ni hardware.
* :mod:`aethernet.data`     — persistencia SQLite (histórico, snapshots, eventos).
* :mod:`aethernet.service`  — daemon de vigilancia continua (nunca dibuja).
* :mod:`aethernet.alerts`   — cola de eventos y notificaciones.
* :mod:`aethernet.report`   — exportadores Markdown/PDF/JSON/CSV.
* :mod:`aethernet.api`      — API local opcional (FastAPI en localhost).
* :mod:`aethernet.integration` — speedtest e importación de escaneos externos.

La UI (NiceGUI, "AETHERNET") vive en :mod:`aethernet.ui` y solo consume estas capas.
"""

from __future__ import annotations

__version__ = "1.0.0"

APP_NAME = "aethernet"
APP_TITLE = "Aethernet"

__all__ = ["APP_NAME", "APP_TITLE", "__version__"]
