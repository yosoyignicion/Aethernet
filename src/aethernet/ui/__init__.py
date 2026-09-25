"""Capa UI (NiceGUI): traduce el diseño retro-futurista de Stitch a Python.

Consume exactamente los mismos servicios que el CLI (core, data, service,
alerts, report). La UI nunca contiene lógica de análisis.
"""

from __future__ import annotations

from .app import main

__all__ = ["main"]
