"""Test de velocidad puntual con ``speedtest-cli``, correlacionado con congestión."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SpeedTestResult:
    download_mbps: float | None = None
    upload_mbps: float | None = None
    ping_ms: float | None = None
    server: str | None = None
    timestamp: float = field(default_factory=time.time)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.download_mbps is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "download_mbps": round(self.download_mbps, 2) if self.download_mbps else None,
            "upload_mbps": round(self.upload_mbps, 2) if self.upload_mbps else None,
            "ping_ms": round(self.ping_ms, 1) if self.ping_ms else None,
            "server": self.server,
            "timestamp": self.timestamp,
            "ok": self.ok,
            "error": self.error,
        }


def run_speedtest(timeout: float = 60.0) -> SpeedTestResult:
    """Ejecuta speedtest-cli si está instalado; devuelve error legible si no."""
    try:
        import speedtest
    except ImportError:
        return SpeedTestResult(error="speedtest-cli no está instalado (pip install 'aethernet[speedtest]')")

    try:
        client = speedtest.Speedtest(secure=True)
        client.get_best_server()
        client.download()
        client.upload()
        results = client.results.dict()
    except Exception as exc:  # red caída, sin servidores, etc.
        return SpeedTestResult(error=str(exc))

    return SpeedTestResult(
        download_mbps=results.get("download", 0) / 1_000_000,
        upload_mbps=results.get("upload", 0) / 1_000_000,
        ping_ms=results.get("ping"),
        server=(results.get("server") or {}).get("name"),
    )


def correlate_with_congestion(result: SpeedTestResult, congestion_index: float) -> dict[str, Any]:
    """Interpretación honesta: la velocidad baja puede ser congestión o ISP."""
    payload = result.to_dict()
    if not result.ok:
        payload["interpretation"] = "No se pudo medir; revisa la conexión o instala speedtest-cli."
        return payload
    if congestion_index >= 0.7 and (result.download_mbps or 0) < 50:
        payload["interpretation"] = (
            "Velocidad baja con canal muy congestionado: cambiar de canal podría ayudar."
        )
    elif congestion_index < 0.3 and (result.download_mbps or 0) < 50:
        payload["interpretation"] = (
            "Canal libre pero velocidad baja: el cuello de botella parece del ISP o del router."
        )
    else:
        payload["interpretation"] = "Velocidad coherente con el estado del espectro."
    return payload
