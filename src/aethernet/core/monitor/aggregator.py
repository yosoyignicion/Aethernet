"""Agregación temporal de tramas decodificadas → :class:`MonitorEvent`.

Lógica pura (sin scapy, sin red): agrupa por ventana y aplica umbrales para no
generar ruido. Cada evento emitido alimenta el motor de reglas existente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..analysis import MonitorEvent
from .frames import KIND_BEACON, KIND_DEAUTH, KIND_EAPOL, KIND_PROBE, DecodedFrame


@dataclass(slots=True)
class MonitorAggregator:
    window_s: float = 10.0
    deauth_threshold: int = 20
    probe_min_rssi: int = -80

    _deauth: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    _probe: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    _beacon: dict[str, float] = field(default_factory=dict)
    _eapol: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    # -- API ------------------------------------------------------------ #
    def add(self, frame: DecodedFrame, ts: float) -> list[MonitorEvent]:
        self._counters[frame.kind] = self._counters.get(frame.kind, 0) + 1
        if frame.kind == KIND_DEAUTH:
            return self._add_deauth(frame, ts)
        if frame.kind == KIND_PROBE:
            return self._add_probe(frame, ts)
        if frame.kind == KIND_BEACON:
            return self._add_beacon(frame, ts)
        if frame.kind == KIND_EAPOL:
            return self._add_eapol(frame, ts)
        return []

    def flush(self, ts: float) -> list[MonitorEvent]:
        """Emite eventos de probes pendientes y limpia ventanas antiguas."""
        events: list[MonitorEvent] = []
        for (source, ssid), bucket in list(self._probe.items()):
            if bucket["last"] < ts - self.window_s:
                events.append(self._probe_event(source, ssid, bucket, ts))
                del self._probe[(source, ssid)]
        self._prune(ts)
        return events

    def stats(self) -> dict[str, int]:
        return dict(self._counters)

    def reset(self) -> None:
        self._deauth.clear()
        self._probe.clear()
        self._beacon.clear()
        self._eapol.clear()

    # -- internos ------------------------------------------------------- #
    def _add_deauth(self, frame: DecodedFrame, ts: float) -> list[MonitorEvent]:
        key = (frame.bssid, frame.source_mac)
        stamps = self._deauth.setdefault(key, [])
        stamps.append(ts)
        cutoff = ts - self.window_s
        while stamps and stamps[0] < cutoff:
            stamps.pop(0)
        count = len(stamps)
        if count and count % self.deauth_threshold == 0:
            return [
                MonitorEvent(
                    kind=KIND_DEAUTH,
                    timestamp=ts,
                    bssid=frame.bssid,
                    source_mac=frame.source_mac,
                    count=count,
                    detail=f"{count} deauth en {self.window_s:.0f}s",
                )
            ]
        return []

    def _add_probe(self, frame: DecodedFrame, ts: float) -> list[MonitorEvent]:
        if frame.rssi and frame.rssi < self.probe_min_rssi:
            return []
        key = (frame.source_mac, frame.ssid)
        bucket = self._probe.get(key)
        if bucket is None:
            bucket = {"count": 1.0, "first": ts, "last": ts, "rssi": float(frame.rssi)}
            self._probe[key] = bucket
            return [self._probe_event(frame.source_mac, frame.ssid, bucket, ts)]
        bucket["count"] += 1
        bucket["last"] = ts
        if bucket["count"] % 10 == 0:
            return [self._probe_event(frame.source_mac, frame.ssid, bucket, ts)]
        return []

    def _probe_event(self, source: str, ssid: str, bucket: dict[str, float], ts: float) -> MonitorEvent:
        return MonitorEvent(
            kind=KIND_PROBE,
            timestamp=ts,
            ssid=ssid,
            source_mac=source,
            count=int(bucket["count"]),
            detail=f"rssi={int(bucket['rssi'])}",
        )

    def _add_beacon(self, frame: DecodedFrame, ts: float) -> list[MonitorEvent]:
        if not frame.bssid:
            return []
        last = self._beacon.get(frame.bssid)
        self._beacon[frame.bssid] = ts
        if last is not None and last >= ts - self.window_s:
            return []
        return [
            MonitorEvent(
                kind=KIND_BEACON,
                timestamp=ts,
                bssid=frame.bssid,
                ssid=frame.ssid,
                channel=frame.channel,
                rssi=frame.rssi,
                count=1,
                detail=frame.detail,
            )
        ]

    def _add_eapol(self, frame: DecodedFrame, ts: float) -> list[MonitorEvent]:
        key = (frame.bssid, frame.source_mac)
        bucket = self._eapol.setdefault(key, {"count": 0.0, "last": ts})
        bucket["count"] += 1
        bucket["last"] = ts
        if bucket["count"] == 1 or bucket["count"] % 4 == 0:
            return [
                MonitorEvent(
                    kind=KIND_EAPOL,
                    timestamp=ts,
                    bssid=frame.bssid,
                    source_mac=frame.source_mac,
                    count=int(bucket["count"]),
                    detail="handshake",
                )
            ]
        return []

    def _prune(self, ts: float) -> None:
        cutoff = ts - self.window_s
        for deauth_key, stamps in list(self._deauth.items()):
            while stamps and stamps[0] < cutoff:
                stamps.pop(0)
            if not stamps:
                del self._deauth[deauth_key]
        for beacon_key, seen in list(self._beacon.items()):
            if seen < cutoff:
                del self._beacon[beacon_key]
