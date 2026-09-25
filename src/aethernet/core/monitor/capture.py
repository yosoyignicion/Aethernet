"""Captura pasiva en monitor mode: sniffer + hopping + agregación.

Se ejecuta en hilos propios y nunca toca la UI. Cada evento agregado se
persiste y se encola para el motor de reglas. Solo escucha.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...logging_setup import get_logger
from .aggregator import MonitorAggregator
from .frames import DecodedFrame, decode_frame
from .hopper import ChannelHopper
from .interface import MonitorError, MonitorInterface

log = get_logger(__name__)

EventCallback = Callable[[Any], None]


@dataclass(slots=True)
class MonitorStatus:
    capable: bool = False
    running: bool = False
    paused: bool = False
    interface: str = ""
    base_interface: str = ""
    channels: tuple[int, ...] = ()
    current_channel: int = 0
    packet_count: int = 0
    event_count: int = 0
    session_id: int | None = None
    error: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capable": self.capable,
            "running": self.running,
            "paused": self.paused,
            "interface": self.interface,
            "base_interface": self.base_interface,
            "channels": list(self.channels),
            "current_channel": self.current_channel,
            "packet_count": self.packet_count,
            "event_count": self.event_count,
            "session_id": self.session_id,
            "error": self.error,
            "reason": self.reason,
        }


class MonitorCapture:
    """Orquesta interfaz de monitor, sniffer scapy y agregador."""

    def __init__(
        self,
        repo: Any,
        base_interface: str,
        channels: list[int],
        dwell_ms: int = 220,
        *,
        window_s: float = 10.0,
        deauth_threshold: int = 20,
        probe_min_rssi: int = -80,
        monitor_name: str = "aemon0",
        on_event: EventCallback | None = None,
        evidence_limit: int = 64,
    ) -> None:
        self.repo = repo
        self.base_interface = base_interface
        self.channels = [c for c in channels if c > 0] or [1, 6, 11]
        self.dwell_ms = dwell_ms
        self.interface = MonitorInterface(base_interface, monitor_name)
        self.aggregator = MonitorAggregator(
            window_s=window_s, deauth_threshold=deauth_threshold, probe_min_rssi=probe_min_rssi
        )
        self.on_event = on_event
        self._mon_iface = ""
        self._session_id: int | None = None
        self._pending: list[Any] = []
        self._pending_lock = threading.Lock()
        self._evidence: deque[dict[str, Any]] = deque(maxlen=evidence_limit)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._current = [self.channels[0]]
        self._packet_count = 0
        self._event_count = 0
        self._error: str | None = None
        self._running = False
        self._paused = False
        self._sniffer: Any = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        """Estado ligero (sin preflight) para sondeos frecuentes de la UI."""
        return self._running

    # -- preflight / estado -------------------------------------------- #
    def preflight(self) -> tuple[bool, str]:
        try:
            import scapy  # noqa: F401
        except ImportError:
            return False, "Falta scapy (pip install 'aethernet[monitor]')."
        return self.interface.preflight()

    def status(self) -> MonitorStatus:
        capable, reason = self.preflight()
        return MonitorStatus(
            capable=capable,
            running=self._running,
            paused=self._paused,
            interface=self._mon_iface,
            base_interface=self.base_interface,
            channels=tuple(self.channels),
            current_channel=self._current[0],
            packet_count=self._packet_count,
            event_count=self._event_count,
            session_id=self._session_id,
            error=self._error,
            reason=reason,
        )

    # -- ciclo de vida -------------------------------------------------- #
    def start(self) -> MonitorStatus:
        with self._lock:
            if self._running:
                return self.status()
            capable, reason = self.preflight()
            if not capable:
                self._error = reason
                log.warning("monitor no disponible: %s", reason)
                return self.status()
            try:
                self._mon_iface = self.interface.create()
            except MonitorError as exc:
                self._error = str(exc)
                return self.status()

            self._session_id = self.repo.start_monitor_session(self._mon_iface, self.channels, time.time())
            self._stop = threading.Event()
            self._paused = False
            self._error = None
            hopper = ChannelHopper(self._mon_iface, self.channels, self.dwell_ms)
            self._threads = [
                threading.Thread(
                    target=hopper.run, args=(self._stop,), kwargs={"current": self._current},
                    name="aethernet-hop", daemon=True,
                ),
                threading.Thread(target=self._flush_loop, name="aethernet-flush", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
            try:
                from scapy.all import AsyncSniffer

                self._sniffer = AsyncSniffer(prn=self._on_packet, store=False, iface=self._mon_iface)
                self._sniffer.start()
            except Exception as exc:  # noqa: BLE001 - scapy/permisos
                self._error = f"Sniffer no iniciado: {exc}"
                self.stop()
                return self.status()
            self._running = True
            log.info("monitor pasivo activo en %s", self._mon_iface)
            return self.status()

    def stop(self) -> MonitorStatus:
        with self._lock:
            if not self._running:
                return self.status()
            self._stop.set()
            if self._sniffer is not None:
                with contextlib.suppress(Exception):
                    self._sniffer.stop()
                self._sniffer = None
            for thread in self._threads:
                thread.join(timeout=2.0)
            self._flush_events(time.time())
            if self._session_id is not None:
                self.repo.close_monitor_session(self._session_id, self._packet_count)
            self.interface.destroy()
            self._running = False
            self._mon_iface = ""
            log.info("monitor pasivo detenido")
            return self.status()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # -- datos ---------------------------------------------------------- #
    def drain(self) -> list[Any]:
        with self._pending_lock:
            events, self._pending = self._pending, []
        return events

    def recent_evidence(self, limit: int = 20) -> list[dict[str, Any]]:
        items = list(self._evidence)[-limit:]
        return list(reversed(items))

    # -- internos ------------------------------------------------------- #
    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.aggregator.window_s)
            if not self._stop.is_set():
                self._flush_events(time.time())

    def _flush_events(self, ts: float) -> None:
        for event in self.aggregator.flush(ts):
            self._emit(event)

    def _on_packet(self, pkt: Any) -> None:
        if self._paused:
            return
        self._packet_count += 1
        frame = decode_frame(pkt)
        if frame is None:
            return
        now = time.time()
        for event in self.aggregator.add(frame, now):
            self._emit(event, frame=frame)

    def _emit(self, event: Any, frame: DecodedFrame | None = None) -> None:
        self._event_count += 1
        evidence_text = self._build_evidence(event, frame)
        if self.repo is not None:
            try:
                self.repo.add_monitor_event(
                    session_id=self._session_id,
                    kind=event.kind,
                    ts=event.timestamp,
                    bssid=event.bssid,
                    ssid=event.ssid,
                    source_mac=event.source_mac,
                    channel=event.channel,
                    rssi=event.rssi,
                    count=event.count,
                    evidence=evidence_text,
                )
            except Exception as exc:  # noqa: BLE001 - persistencia no debe romper captura
                log.debug("no se pudo persistir evento de monitor: %s", exc)
        with self._pending_lock:
            self._pending.append(event)
        self._evidence.append(
            {
                "ts": event.timestamp,
                "kind": event.kind,
                "summary": frame.summary if frame else event.detail,
                "channel": event.channel,
                "count": event.count,
                "hexdump": evidence_text,
            }
        )
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception as exc:  # noqa: BLE001
                log.debug("callback de evento falló: %s", exc)

    @staticmethod
    def _build_evidence(event: Any, frame: DecodedFrame | None) -> str:
        if frame is None:
            return str(event.detail)
        header = f"{frame.kind} {frame.bssid or frame.source_mac} ch={frame.channel} rssi={frame.rssi}"
        return f"{header}\n{event.detail}"
