"""Punto de entrada de la interfaz AETHERNET (NiceGUI).

Uso:
    aethernet-ui                 # ventana nativa si hay pywebview, si no navegador
    python -m aethernet.ui       # equivalente
    python -m aethernet.ui --web --port 8080
"""

from __future__ import annotations

import argparse
import contextlib
import os
import secrets
from pathlib import Path


def _persist_secret(data_dir: Path) -> str:
    """Secreto de sesión estable por instalación (env, fichero 0600 o nuevo)."""
    env = os.environ.get("AETHERNET_STORAGE_SECRET")
    if env:
        return env
    secret_file = data_dir / ".storage_secret"
    with contextlib.suppress(OSError):
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value
    value = secrets.token_hex(32)
    with contextlib.suppress(OSError):
        secret_file.write_text(value, encoding="utf-8")
        secret_file.chmod(0o600)
    return value


def _native_available() -> bool:
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aethernet-ui", description="Interfaz AETHERNET de Aethernet")
    parser.add_argument("--web", action="store_true", help="forzar render en el navegador")
    parser.add_argument("--native", action="store_true", help="forzar ventana nativa (pywebview)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true", help="recarga automática en desarrollo")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from nicegui import ui

    from . import theme
    from .state import get_context

    context = get_context()  # inicializa DB, settings y servicios reales
    theme.install_shared()

    # Importar las páginas registra las rutas @ui.page.
    from .pages import (  # noqa: F401
        alerts,
        dashboard,
        devices,
        networks,
        reports,
        settings,
        spectrum,
    )

    native = args.native or (not args.web and _native_available())

    ui.run(
        host=args.host,
        port=args.port,
        title="AETHERNET · Monitor RF",
        dark=True,
        favicon="📡",
        reload=args.reload,
        show=(not native and not args.no_browser),
        native=native,
        window_size=(1440, 900) if native else None,
        storage_secret=_persist_secret(context.paths.data_dir),
        binding_refresh_interval=0.15,
        reconnect_timeout=4.0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
