"""Gestión **no disruptiva** de la interfaz de monitor.

Regla de oro: nunca se ejecuta ``iw dev <if> set type monitor`` sobre la
interfaz gestionada. Solo se crea una interfaz virtual de monitor con
``iw phy <phy> interface add``. Si el driver no lo permite, se lanza
:class:`MonitorUnsupportedError` y no se toca tu conexión.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

from ...logging_setup import get_logger
from ...utils import CommandResult, run_command
from ..adapter import probe_adapter

log = get_logger(__name__)

Executor = Callable[[list[str]], CommandResult]
RootChecker = Callable[[], bool]


class MonitorError(RuntimeError):
    """Error genérico de monitor mode."""


class MonitorPermissionError(MonitorError):
    """Faltan privilegios (root/CAP_NET_ADMIN)."""


class MonitorUnsupportedError(MonitorError):
    """El adaptador o el sistema no soportan monitor mode no disruptivo."""


def default_executor(argv: list[str]) -> CommandResult:
    return run_command(argv, timeout=8)


def _default_root_checker() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:  # pragma: no cover - Windows
        return False


class MonitorInterface:
    """Crea y destruye una vif de monitor sin alterar la interfaz gestionada."""

    def __init__(
        self,
        base_interface: str,
        monitor_name: str = "aemon0",
        *,
        executor: Executor | None = None,
        root_checker: RootChecker | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> None:
        self.base_interface = base_interface
        self.monitor_name = monitor_name
        self._executor = executor or default_executor
        self._root = root_checker or _default_root_checker
        self._which = which or shutil.which
        self._created = False

    def preflight(self) -> tuple[bool, str]:
        """Comprueba sin efectos si el monitor no disruptivo es posible."""
        if not self.base_interface:
            return False, "No hay interfaz WiFi base."
        if self._which("iw") is None:
            return False, "Falta 'iw' para crear la interfaz de monitor."
        adapter = probe_adapter(self.base_interface)
        if not adapter.supports_monitor:
            return False, "El adaptador no soporta monitor mode."
        if not self._root():
            return False, "Monitor mode requiere root (nunca se activa tu conexión)."
        return True, "ok"

    def create(self) -> str:
        ok, reason = self.preflight()
        if not ok:
            if "root" in reason:
                raise MonitorPermissionError(reason)
            raise MonitorUnsupportedError(reason)

        adapter = probe_adapter(self.base_interface)
        phy = adapter.phy or ""
        attempts = [
            ["iw", "dev", self.base_interface, "interface", "add", self.monitor_name, "type", "monitor"],
            ["iw", "phy", phy, "interface", "add", self.monitor_name, "type", "monitor"],
        ]
        last_error = ""
        for argv in attempts:
            if "phy" in argv and not phy:
                continue
            result = self._executor(argv)
            if result.ok:
                self._created = True
                break
            last_error = result.stderr.strip()
        else:
            raise MonitorUnsupportedError(
                "No se pudo crear la interfaz virtual de monitor (driver sin soporte de vif). "
                "Tu conexión WiFi no se ha tocado."
            )
        self._executor(["ip", "link", "set", self.monitor_name, "up"])
        log.info("interfaz de monitor creada: %s (base %s)", self.monitor_name, self.base_interface)
        if last_error:
            log.debug("aviso al crear monitor: %s", last_error)
        return self.monitor_name

    def destroy(self) -> None:
        if not self._created:
            return
        self._executor(["iw", "dev", self.monitor_name, "del"])
        self._created = False
        log.info("interfaz de monitor eliminada: %s", self.monitor_name)
