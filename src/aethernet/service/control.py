"""Canal de control del daemon mediante archivo.

La GUI (o el CLI) escribe una orden en un archivo; el daemon la lee y la borra.
Sin sockets ni permisos: un archivo en el directorio de datos del usuario.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from ..utils import atomic_write

VALID_COMMANDS = {
    "pause",
    "resume",
    "scan",
    "stop",
    "status",
    "monitor-start",
    "monitor-stop",
    "monitor-status",
}


class ControlChannel:
    def __init__(self, path: Path) -> None:
        self.path = path

    def send(self, command: str) -> bool:
        command = command.strip().lower()
        if command not in VALID_COMMANDS:
            raise ValueError(f"orden no válida: {command}")
        atomic_write(self.path, command + "\n")
        return True

    def poll(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            content = self.path.read_text(encoding="utf-8").strip().lower()
        except OSError:
            return None
        with contextlib.suppress(OSError):
            self.path.unlink(missing_ok=True)
        return content or None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
