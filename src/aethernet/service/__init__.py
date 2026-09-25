"""Capa de servicio: vigilancia continua. Nunca dibuja; solo escribe en la DB."""

from .control import ControlChannel
from .daemon import MonitorService, ScanResult

__all__ = ["ControlChannel", "MonitorService", "ScanResult"]
