"""Salto de canales para la captura pasiva.

Secuencia determinista y ejecutor inyectable: se testea sin hardware ni root.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

from ...logging_setup import get_logger
from ...utils import CommandResult, run_command

log = get_logger(__name__)

Executor = Callable[[list[str]], CommandResult]


def default_executor(argv: list[str]) -> CommandResult:
    return run_command(argv, timeout=8)


class ChannelHopper:
    """Recorre los canales indicados con un tiempo de escucha por canal."""

    def __init__(
        self,
        interface: str,
        channels: list[int],
        dwell_ms: int = 220,
        executor: Executor | None = None,
    ) -> None:
        self.interface = interface
        self.channels = [c for c in channels if c > 0] or [1, 6, 11]
        self.dwell_s = max(0.05, dwell_ms / 1000.0)
        self._executor = executor or default_executor
        self._index = 0

    def sequence(self) -> Iterator[int]:
        """Generador cíclico de canales (infinito)."""
        while True:
            channel = self.channels[self._index % len(self.channels)]
            self._index += 1
            yield channel

    def hop(self, channel: int) -> bool:
        result = self._executor(["iw", "dev", self.interface, "set", "channel", str(channel)])
        if not result.ok:
            log.debug("no se pudo fijar canal %s: %s", channel, result.stderr.strip())
        return result.ok

    def run(self, stop_event: threading.Event, *, current: list[int] | None = None) -> None:
        """Bucle de hopping hasta que ``stop_event`` se active.

        ``current`` es una lista mutable de un elemento donde se publica el
        canal actual (para el estado expuesto a la UI).
        """
        for channel in self.sequence():
            if stop_event.is_set():
                return
            self.hop(channel)
            if current is not None:
                current[0] = channel
            stop_event.wait(self.dwell_s)
