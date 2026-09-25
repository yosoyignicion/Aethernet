"""Integraciones opcionales: test de velocidad e importación de escaneos."""

from .importer import import_wifi_analyzer, security_from_capabilities
from .speedtest import SpeedTestResult, run_speedtest

__all__ = ["SpeedTestResult", "run_speedtest", "import_wifi_analyzer", "security_from_capabilities"]
