"""Contexto compartido de la UI: servicios reales + ejecución en segundo plano.

La UI nunca bloquea: los escaneos corren en un hilo y las páginas leen la DB.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..alerts.queue import AlertQueue
from ..capabilities import CapabilityReport, detect
from ..config import Paths, Settings, bootstrap_paths, load_settings
from ..core.adapter import probe_adapter
from ..core.health import score_health
from ..data.db import Database
from ..data.repository import Repository
from ..logging_setup import get_logger, setup_logging
from ..models import AdapterInfo, HealthScore, Severity, WifiScan
from ..report import build_report_data, export
from ..service.daemon import MonitorService, ScanResult
from ..utils import humanize_age

log = get_logger(__name__)


@dataclass
class UIContext:
    paths: Paths
    settings: Settings
    db: Database
    repo: Repository
    service: MonitorService
    capabilities: CapabilityReport
    adapter: AdapterInfo
    _scanning: bool = False
    _last_result: ScanResult | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # -- servicios ------------------------------------------------------ #
    @classmethod
    def build(cls) -> UIContext:
        paths = bootstrap_paths()
        setup_logging(paths.log_path, console=False)
        db = Database(paths.db_path)
        db.migrate()
        settings = load_settings(paths)
        repo = Repository(db)
        service = MonitorService(repo, settings, paths, alerts=AlertQueue(repo, settings))
        return cls(
            paths=paths,
            settings=settings,
            db=db,
            repo=repo,
            service=service,
            capabilities=detect(settings.interface),
            adapter=probe_adapter(settings.interface or ""),
        )

    def reload_settings(self) -> None:
        self.settings = load_settings(self.paths)
        self.service.settings = self.settings
        self.service.alerts.settings = self.settings

    # -- estado --------------------------------------------------------- #
    @property
    def scanning(self) -> bool:
        return self._scanning

    @property
    def last_result(self) -> ScanResult | None:
        return self._last_result

    def last_scan(self) -> WifiScan | None:
        return self.repo.latest_wifi_scan()

    def health(self) -> HealthScore | None:
        scan = self.last_scan()
        if scan is None:
            return None
        history = {ap.bssid: [s for _, s in self.repo.signal_series(ap.bssid, hours=48)] for ap in scan.aps}
        return score_health(
            scan,
            my_ssids=tuple(self.settings.my_ssids),
            my_bssids=tuple(self.settings.my_bssids),
            signal_history=history,
        )

    def refresh_capabilities(self) -> None:
        self.capabilities = detect(self.settings.interface)
        self.adapter = probe_adapter(self.settings.interface or "")

    # -- monitor pasivo ------------------------------------------------- #
    def monitor_status(self) -> dict[str, Any]:
        return self.service.monitor_status()

    def monitor_running(self) -> bool:
        return self.service.monitor_running()

    def set_monitor_enabled(
        self, enabled: bool, *, on_done: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        """Activa/desactiva la captura pasiva en segundo plano."""
        self.settings.monitor_enabled = enabled

        def worker() -> None:
            result = self.service.start_monitor() if enabled else self.service.stop_monitor()
            if on_done is not None:
                on_done(result)

        threading.Thread(target=worker, name="aethernet-monitor-toggle", daemon=True).start()

    # -- acciones ------------------------------------------------------- #
    def scan_async(
        self,
        *,
        active: bool | None = None,
        include_lan: bool | None = None,
        on_done: Callable[[ScanResult], None] | None = None,
    ) -> bool:
        """Lanza un escaneo en segundo plano. Devuelve False si ya había uno."""
        with self._lock:
            if self._scanning:
                return False
            self._scanning = True

        def worker() -> None:
            try:
                result = self.service.scan_once(active=active, include_lan=include_lan)
                self._last_result = result
                if on_done is not None:
                    on_done(result)
            except Exception as exc:  # nunca romper el hilo de UI
                log.exception("escaneo UI falló: %s", exc)
            finally:
                with self._lock:
                    self._scanning = False

        threading.Thread(target=worker, name="ae-scan", daemon=True).start()
        return True

    def export_report(self, fmt: str, destination: Path | None = None) -> list[Path]:
        data = build_report_data(self.repo, self.settings)
        if destination is None:
            ext = {"markdown": "md", "md": "md", "json": "json", "csv": "csv", "pdf": "pdf"}[fmt]
            destination = self.paths.report_dir / f"aethernet-report-{time.strftime('%Y%m%d-%H%M%S')}.{ext}"
        return export(data, fmt, destination)  # type: ignore[arg-type]

    def counts(self) -> dict[str, int]:
        return self.repo.counts()

    def uptime(self) -> str:
        status = self.repo.kv_get("daemon_status", {}) or {}
        last = status.get("last_scan")
        if not last:
            return "sin ciclos"
        return humanize_age(time.time() - last)


_context: UIContext | None = None


def get_context() -> UIContext:
    global _context
    if _context is None:
        _context = UIContext.build()
    return _context


# --------------------------------------------------------------------------- #
# Formato
# --------------------------------------------------------------------------- #
def severity_label(severity: Severity) -> str:
    return {
        Severity.INFO: "INFORMATIVA",
        Severity.WARNING: "ADVERTENCIA",
        Severity.ALERT: "ALERTA",
        Severity.CRITICAL: "CRÍTICA",
    }[severity]


def fmt_age(timestamp: float | None) -> str:
    return humanize_age(time.time() - timestamp) if timestamp else "—"


def fmt_dbm(value: int | None) -> str:
    return f"{value} dBm" if value is not None else "—"


def fmt_signal_bars(dbm: int) -> str:
    quality = max(0, min(100, 2 * (dbm + 100)))
    filled = max(0, min(4, round(quality / 25)))
    return "▁▃▅█"[:filled] or "·"


def security_label(security: str) -> str:
    return {
        "wpa3": "WPA3-SAE",
        "wpa2": "WPA2-PSK",
        "wpa": "WPA",
        "wep": "WEP",
        "open": "OPEN",
    }.get(security, security.upper())
