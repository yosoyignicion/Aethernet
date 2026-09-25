"""Configuración central de logging.

La GUI nunca imprime a stdout: escribe a archivo rotado. El CLI usa un handler
de consola legible. Ambos comparten formato monoespaciado apto para datos.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(
    log_file: Path | None = None,
    level: int = logging.INFO,
    console: bool = False,
) -> logging.Logger:
    """Configura el logger raíz una sola vez (idempotente)."""
    global _configured
    root = logging.getLogger("aethernet")
    if _configured:
        return root

    root.setLevel(level)
    root.propagate = False
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if console or log_file is None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger hijo bajo ``aethernet``."""
    if not name.startswith("aethernet"):
        name = f"aethernet.{name}"
    return logging.getLogger(name)
