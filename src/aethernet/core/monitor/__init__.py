"""Monitor mode **pasivo** de Aethernet.

Diseño no disruptivo: nunca se cambia el tipo de la interfaz gestionada. Se
crea una interfaz virtual de monitor (``iw phy <phy> interface add``) y, si el
driver no lo permite, la función se deshabilita en lugar de cortar tu WiFi.

Solo escucha: deauth, probe requests, beacons y tramas EAPOL. No inyecta, no
captura material sensible a disco y no altera la red.
"""

from __future__ import annotations

from .aggregator import MonitorAggregator
from .capture import MonitorCapture, MonitorStatus
from .evidence import format_hexdump
from .frames import DecodedFrame, decode_frame, is_wps
from .hopper import ChannelHopper
from .interface import (
    MonitorError,
    MonitorInterface,
    MonitorPermissionError,
    MonitorUnsupportedError,
)

__all__ = [
    "ChannelHopper",
    "DecodedFrame",
    "MonitorAggregator",
    "MonitorCapture",
    "MonitorError",
    "MonitorInterface",
    "MonitorPermissionError",
    "MonitorStatus",
    "MonitorUnsupportedError",
    "decode_frame",
    "format_hexdump",
    "is_wps",
]
