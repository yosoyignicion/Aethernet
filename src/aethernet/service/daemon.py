"""Daemon de vigilancia continua y servicio embebible (hilo).

Puede correr como proceso independiente (``aethernet daemon start``) o como
hilo dentro de la GUI. En ambos casos la lógica es la misma y la GUI solo lee la
base de datos: nunca se bloquea y el daemon nunca dibuja.
"""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..alerts.queue import AlertQueue, AlertResult
from ..config import Paths, Settings, default_paths
from ..core.adapter import list_wireless_interfaces
from ..core.analysis import AnalysisContext, MonitorEvent, run_rules
from ..core.health import score_health
from ..core.lan_scan import scan_lan
from ..core.monitor.capture import MonitorCapture
from ..core.wifi_scan import scan_wifi
from ..logging_setup import get_logger
from ..models import Finding, HealthScore, LanScan, WifiScan
from ..utils import atomic_write
from .control import ControlChannel

log = get_logger(__name__)

ScannerFn = Callable[..., WifiScan]
LanScannerFn = Callable[..., LanScan]


@dataclass(slots=True)
class ScanResult:
    timestamp: float
    scan: WifiScan | None = None
    lan_scan: LanScan | None = None
    health: HealthScore | None = None
    findings: list[Finding] = field(default_factory=list)
    alerts: AlertResult | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "networks": self.scan.count if self.scan else 0,
            "devices": self.lan_scan.count if self.lan_scan else 0,
            "health": self.health.total if self.health else None,
            "findings": len(self.findings),
            "alerts": self.alerts.to_dict() if self.alerts else None,
            "error": self.error,
        }


class MonitorService:
    """Orquesta escaneos, análisis, alertas y estado. Sin hilos por defecto."""

    def __init__(
        self,
        repo,
        settings: Settings,
        paths: Paths | None = None,
        *,
        scanner: ScannerFn = scan_wifi,
        lan_scanner: LanScannerFn = scan_lan,
        alerts: AlertQueue | None = None,
        monitor: MonitorCapture | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.paths = paths or default_paths()
        self.scanner = scanner
        self.lan_scanner = lan_scanner
        self.alerts = alerts or AlertQueue(repo, settings)
        self.control = ControlChannel(self.paths.control_file)
        self._capture = monitor

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._paused = False
        self._as_process = False
        self._lock = threading.Lock()
        self.scan_count = 0
        self.last_result: ScanResult | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ #
    # Un escaneo completo
    # ------------------------------------------------------------------ #
    def scan_once(
        self,
        *,
        active: bool | None = None,
        include_lan: bool | None = None,
        monitor_events: list[MonitorEvent] | None = None,
    ) -> ScanResult:
        started = time.time()
        result = ScanResult(timestamp=started)
        drained: list[MonitorEvent] = []
        try:
            if self._capture is not None and self._capture.status().running:
                drained = list(self._capture.drain())
            if monitor_events:
                drained.extend(monitor_events)
            previous = self.repo.latest_wifi_scan()
            known_bssids = self.repo.all_bssids()
            known_lan = {device.mac for device in self.repo.devices()}

            use_active = (self.settings.scan_mode == "active") if active is None else active
            scan = self.scanner(self.settings.interface, active=use_active)
            result.scan = scan

            history: dict[str, list[int]] = {}
            for ap in scan.aps:
                history[ap.bssid] = [signal for _, signal in self.repo.signal_series(ap.bssid, hours=24)]

            self.repo.save_wifi_scan(scan, my_bssids=set(self.settings.my_bssids))

            do_lan = self.settings.lan_scan_enabled if include_lan is None else include_lan
            if do_lan:
                lan = self.lan_scanner(self.settings.interface, active=False)
                self.repo.save_lan_scan(lan)
                result.lan_scan = lan

            context = AnalysisContext(
                scan=scan,
                previous=previous,
                lan_scan=result.lan_scan,
                my_ssids=tuple(self.settings.my_ssids),
                my_bssids=tuple(self.settings.my_bssids),
                known_bssids=known_bssids,
                known_lan_macs=known_lan,
                trusted_macs=set(self.settings.trusted_macs) | set(self.repo.trusted_macs()),
                signal_history=history,
                monitor_events=drained,
                disabled_rules=set(self.settings.muted_rules),
            )
            result.findings = run_rules(context)
            result.health = score_health(
                scan,
                my_ssids=tuple(self.settings.my_ssids),
                my_bssids=tuple(self.settings.my_bssids),
                signal_history=history,
                now=started,
            )
            result.alerts = self.alerts.submit_findings(result.findings)

            self.scan_count += 1
            self.last_result = result
            self.last_error = None
            self._update_status()
        except Exception as exc:  # el daemon nunca debe morir por un escaneo
            self.last_error = str(exc)
            result.error = str(exc)
            self._update_status()
            log.exception("escaneo falló: %s", exc)
        return result

    # ------------------------------------------------------------------ #
    # Control
    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        if self._as_process:
            return not self._stop_event.is_set()
        return self._thread is not None and self._thread.is_alive()

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="aethernet-monitor", daemon=True)
        self._thread.start()
        log.info("servicio de vigilancia iniciado")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._capture is not None:
            self._capture.stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        log.info("servicio de vigilancia detenido")

    def pause(self) -> None:
        self._paused = True
        self._update_status()

    def resume(self) -> None:
        self._paused = False
        self._update_status()

    def toggle_pause(self) -> bool:
        if self._paused:
            self.resume()
        else:
            self.pause()
        return self._paused

    def request_scan(self) -> None:
        self._wake_event.set()

    def interval_seconds(self) -> int:
        return max(60, min(3600, self.settings.scan_interval_min * 60))

    # ------------------------------------------------------------------ #
    # Monitor pasivo (no disruptivo)
    # ------------------------------------------------------------------ #
    def _base_interface(self) -> str:
        if self.settings.monitor_interface:
            return self.settings.monitor_interface
        if self.settings.interface:
            return self.settings.interface
        interfaces = list_wireless_interfaces()
        return interfaces[0] if interfaces else ""

    def monitor(self) -> MonitorCapture:
        if self._capture is None:
            self._capture = MonitorCapture(
                self.repo,
                self._base_interface(),
                list(self.settings.monitor_channels),
                self.settings.monitor_dwell_ms,
                window_s=float(self.settings.deauth_window_s),
                deauth_threshold=self.settings.deauth_threshold,
                probe_min_rssi=self.settings.probe_min_rssi,
            )
        return self._capture

    def start_monitor(self) -> dict:
        return self.monitor().start().to_dict()

    def stop_monitor(self) -> dict:
        if self._capture is None:
            return {}
        return self._capture.stop().to_dict()

    def monitor_status(self) -> dict:
        if self._capture is None:
            return self.monitor().status().to_dict()
        return self._capture.status().to_dict()

    def monitor_running(self) -> bool:
        return self._capture is not None and self._capture.running

    # ------------------------------------------------------------------ #
    # Bucle
    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            command = self.control.poll()
            if command:
                self._handle_command(command)
            self._sync_monitor()
            if not self._paused and not self._stop_event.is_set():
                self.scan_once()
            self._wait(self.interval_seconds())

    def _sync_monitor(self) -> None:
        """Arranca o detiene la captura según la configuración, sin bloquear."""
        running = self._capture is not None and self._capture.status().running
        if self.settings.monitor_enabled and not running:
            self.start_monitor()
        elif not self.settings.monitor_enabled and running:
            self.stop_monitor()

    def _handle_command(self, command: str) -> None:
        if command == "pause":
            self.pause()
        elif command == "resume":
            self.resume()
        elif command == "scan":
            self.request_scan()
        elif command == "monitor-start":
            self.start_monitor()
        elif command == "monitor-stop":
            self.stop_monitor()
        elif command == "stop":
            self._stop_event.set()

    def _wait(self, seconds: float) -> None:
        """Espera interrumpible por stop o por una petición de escaneo."""
        deadline = time.monotonic() + seconds
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self._wake_event.is_set():
                break
            self._stop_event.wait(timeout=min(1.0, remaining))
        self._wake_event.clear()

    # ------------------------------------------------------------------ #
    # Estado persistido (lo que la GUI lee sin tocar el daemon)
    # ------------------------------------------------------------------ #
    def status(self) -> dict:
        return {
            "running": self.running,
            "paused": self._paused,
            "scan_count": self.scan_count,
            "interval_min": self.settings.scan_interval_min,
            "last_scan": self.last_result.timestamp if self.last_result else None,
            "last_health": self.last_result.health.total if self.last_result and self.last_result.health else None,
            "last_error": self.last_error,
            "pid": None,
            "monitor": self._capture.status().to_dict() if self._capture is not None else None,
        }

    def _update_status(self) -> None:
        try:
            self.repo.kv_set("daemon_status", {**self.status(), "updated_at": time.time()})
        except Exception:  # nunca romper por no poder escribir estado
            log.debug("no se pudo persistir el estado del daemon")


# --------------------------------------------------------------------------- #
# Proceso daemon
# --------------------------------------------------------------------------- #
def run_daemon(repo, settings: Settings, paths: Paths | None = None) -> int:
    """Bloquea ejecutando el servicio como proceso independiente."""
    paths = paths or default_paths()
    service = MonitorService(repo, settings, paths)
    service._as_process = True
    service.control.clear()  # órdenes viejas de una ejecución anterior
    _install_signal_handlers(service)
    _write_pid(paths.pid_file)
    try:
        service._loop()
    finally:
        _remove_pid(paths.pid_file)
        service.stop()
    return 0


def _install_signal_handlers(service: MonitorService) -> None:
    def handle_stop(_signum, _frame) -> None:
        service._stop_event.set()
        service._wake_event.set()

    def handle_scan(_signum, _frame) -> None:
        service.request_scan()

    def handle_toggle(_signum, _frame) -> None:
        service.toggle_pause()

    try:
        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)
        signal.signal(signal.SIGUSR1, handle_scan)
        signal.signal(signal.SIGUSR2, handle_toggle)
    except ValueError:
        # no estamos en el hilo principal (embedido): usar ControlChannel
        pass


def _write_pid(path: Path) -> None:
    import contextlib

    with contextlib.suppress(OSError):
        atomic_write(path, f"{__import__('os').getpid()}\n")


def _remove_pid(path: Path) -> None:
    path.unlink(missing_ok=True)


def daemon_is_running(paths: Paths | None = None) -> int | None:
    """Devuelve el PID si el proceso daemon parece vivo."""
    paths = paths or default_paths()
    if not paths.pid_file.exists():
        return None
    try:
        pid = int(paths.pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    import os

    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return None
    return pid
