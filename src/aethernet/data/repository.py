"""Acceso a datos de alto nivel: escaneos, dispositivos, eventos y snapshots.

La UI y el service hablan con este repositorio, nunca con SQL. Todas las
escrituras usan transacciones y ``executemany`` para mantener la DB rápida.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

from ..logging_setup import get_logger
from ..models import (
    AccessPoint,
    AdapterInfo,
    Band,
    Event,
    LanDevice,
    LanScan,
    Severity,
    Snapshot,
    WifiObservation,
    WifiScan,
)
from .db import Database

log = get_logger(__name__)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | bytes | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def _adapter_from_dict(data: dict[str, Any] | None) -> AdapterInfo | None:
    if not data:
        return None
    bands = tuple(Band(b) for b in data.get("bands", []) if b in Band._value2member_map_)
    return AdapterInfo(
        interface=data.get("interface", ""),
        driver=data.get("driver"),
        chipset=data.get("chipset"),
        phy=data.get("phy"),
        mode=data.get("mode", "managed"),
        bands=bands,
        supports_monitor=bool(data.get("supports_monitor")),
        supports_injection=bool(data.get("supports_injection")),
        supports_ap=bool(data.get("supports_ap")),
        supports_5ghz=bool(data.get("supports_5ghz")),
        raw=data.get("raw") or {},
    )


class Repository:
    """Fachada de persistencia sobre :class:`Database`."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # WiFi
    # ------------------------------------------------------------------ #
    def save_wifi_scan(self, scan: WifiScan, my_bssids: set[str] | None = None) -> str:
        my_bssids = my_bssids or set()
        scan_id = scan.id
        ap_rows = []
        upserts = []
        for ap in scan.aps:
            upserts.append(
                (
                    ap.bssid,
                    ap.ssid,
                    ap.vendor,
                    ap.security,
                    1 if ap.hidden else 0,
                    1 if ap.wps else 0,
                    1 if ap.bssid in my_bssids else 0,
                    _dumps(list(ap.tags)),
                    ap.first_seen or scan.timestamp,
                    ap.last_seen or scan.timestamp,
                )
            )
            ap_rows.append(
                (
                    scan_id,
                    ap.bssid,
                    scan.timestamp,
                    ap.ssid,
                    ap.channel,
                    ap.frequency_mhz,
                    ap.signal_dbm,
                    ap.quality,
                    ap.security,
                )
            )
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO wifi_scans (id, timestamp, interface, source, adapter_json, payload, ap_count)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET timestamp=excluded.timestamp, payload=excluded.payload
                """,
                (
                    scan_id,
                    scan.timestamp,
                    scan.interface,
                    scan.source,
                    _dumps(scan.adapter.to_dict()) if scan.adapter else None,
                    _dumps(scan.to_dict()),
                    scan.count,
                ),
            )
            if upserts:
                conn.executemany(
                    """
                    INSERT INTO access_points
                        (bssid, ssid, vendor, security, hidden, wps, is_mine, tags, first_seen, last_seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(bssid) DO UPDATE SET
                        ssid=excluded.ssid,
                        vendor=COALESCE(excluded.vendor, access_points.vendor),
                        security=excluded.security,
                        hidden=excluded.hidden,
                        wps=excluded.wps,
                        is_mine=MAX(excluded.is_mine, access_points.is_mine),
                        last_seen=excluded.last_seen
                    """,
                    upserts,
                )
                conn.executemany(
                    """
                    INSERT INTO ap_observations
                        (scan_id, bssid, timestamp, ssid, channel, frequency_mhz, signal_dbm, quality, security)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    ap_rows,
                )
        return scan_id

    def latest_wifi_scan(self) -> WifiScan | None:
        row = self.db.query_one("SELECT payload FROM wifi_scans ORDER BY timestamp DESC LIMIT 1")
        return self._payload_to_scan(row["payload"]) if row is not None else None

    def wifi_scan_count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM wifi_scans", default=0))

    def all_bssids(self) -> set[str]:
        return {str(r["bssid"]) for r in self.db.query("SELECT bssid FROM access_points")}

    def get_wifi_scan(self, scan_id: str) -> WifiScan | None:
        row = self.db.query_one("SELECT payload FROM wifi_scans WHERE id=?", (scan_id,))
        if row is None:
            return None
        return self._payload_to_scan(row["payload"])

    def _payload_to_scan(self, payload: str | None) -> WifiScan | None:
        data = _loads(payload)
        if not data:
            return None
        aps = tuple(AccessPoint.from_dict(a) for a in data.get("aps", []))
        return WifiScan(
            timestamp=data.get("timestamp", 0.0),
            interface=data.get("interface", ""),
            aps=aps,
            adapter=_adapter_from_dict(data.get("adapter")),
            source=data.get("source", "db"),
        )

    def recent_scans(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT id, timestamp, ap_count, source, interface FROM wifi_scans ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def wifi_history(
        self, bssid: str, *, since: float | None = None, limit: int = 1000
    ) -> list[WifiObservation]:
        sql = "SELECT bssid, scan_id, timestamp, channel, signal_dbm, security, ssid FROM ap_observations WHERE bssid = ?"
        params: list[Any] = [bssid]
        if since is not None:
            sql += " AND timestamp >= ?"
            params.append(since)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.db.query(sql, params)
        return [
            WifiObservation(
                bssid=r["bssid"],
                scan_id=r["scan_id"],
                timestamp=r["timestamp"],
                channel=r["channel"],
                signal_dbm=r["signal_dbm"],
                security=r["security"],
                ssid=r["ssid"] or "",
            )
            for r in rows
        ]

    def signal_series(self, bssid: str, hours: float = 24.0) -> list[tuple[float, int]]:
        since = time.time() - hours * 3600
        rows = self.db.query(
            "SELECT timestamp, signal_dbm FROM ap_observations WHERE bssid=? AND timestamp>=? ORDER BY timestamp",
            (bssid, since),
        )
        return [(r["timestamp"], r["signal_dbm"]) for r in rows]

    def signal_history(self, bssids: Iterable[str], hours: float = 24.0) -> dict[str, list[int]]:
        """Serie de RSSI por BSSID en una sola consulta (evita el patrón N+1)."""
        ids = [b for b in dict.fromkeys(bssids) if b]
        if not ids:
            return {}
        since = time.time() - hours * 3600
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.query(
            f"SELECT bssid, signal_dbm FROM ap_observations "
            f"WHERE bssid IN ({placeholders}) AND timestamp >= ? "
            f"ORDER BY bssid, timestamp",
            [*ids, since],
        )
        history: dict[str, list[int]] = {bssid: [] for bssid in ids}
        for row in rows:
            history[row["bssid"]].append(row["signal_dbm"])
        return history

    def channel_stats(self, hours: float = 24.0) -> list[dict[str, Any]]:
        """Ocupación media por canal en la ventana indicada."""
        since = time.time() - hours * 3600
        rows = self.db.query(
            """
            SELECT channel,
                   COUNT(*) AS samples,
                   COUNT(DISTINCT bssid) AS aps,
                   AVG(signal_dbm) AS avg_signal,
                   MAX(signal_dbm) AS max_signal
            FROM ap_observations
            WHERE timestamp >= ? AND channel IS NOT NULL AND channel > 0
            GROUP BY channel
            ORDER BY channel
            """,
            (since,),
        )
        return [dict(r) for r in rows]

    def hourly_channel_matrix(self, hours: float = 168.0) -> list[dict[str, Any]]:
        """Matriz hora-del-día × canal para el heatmap temporal."""
        since = time.time() - hours * 3600
        rows = self.db.query(
            """
            SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                   channel,
                   COUNT(*) AS samples
            FROM ap_observations
            WHERE timestamp >= ? AND channel IS NOT NULL AND channel > 0
            GROUP BY hour, channel
            ORDER BY hour, channel
            """,
            (since,),
        )
        return [dict(r) for r in rows]

    def hourly_congestion(self, hours: float = 24.0) -> list[dict[str, Any]]:
        """Observaciones por hora del día y banda, para el histórico de congestión."""
        since = time.time() - hours * 3600
        rows = self.db.query(
            """
            SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                   frequency_mhz
            FROM ap_observations
            WHERE timestamp >= ?
            """,
            (since,),
        )
        buckets: dict[int, dict[str, int]] = {
            h: {"hour": h, "total": 0, "band24": 0, "band5": 0} for h in range(24)
        }
        for row in rows:
            hour = int(row["hour"])
            freq = int(row["frequency_mhz"] or 0)
            buckets[hour]["total"] += 1
            if 2400 <= freq <= 2500:
                buckets[hour]["band24"] += 1
            elif 4900 <= freq <= 7125:
                buckets[hour]["band5"] += 1
        return [buckets[h] for h in range(24)]

    def known_aps(self) -> list[AccessPoint]:
        rows = self.db.query(
            """
            SELECT a.*,
                   (SELECT signal_dbm FROM ap_observations o WHERE o.bssid=a.bssid ORDER BY timestamp DESC LIMIT 1) AS signal_dbm,
                   (SELECT channel     FROM ap_observations o WHERE o.bssid=a.bssid ORDER BY timestamp DESC LIMIT 1) AS channel,
                   (SELECT frequency_mhz FROM ap_observations o WHERE o.bssid=a.bssid ORDER BY timestamp DESC LIMIT 1) AS frequency_mhz,
                   (SELECT quality     FROM ap_observations o WHERE o.bssid=a.bssid ORDER BY timestamp DESC LIMIT 1) AS quality
            FROM access_points a
            ORDER BY last_seen DESC
            """
        )
        result: list[AccessPoint] = []
        for r in rows:
            result.append(
                AccessPoint(
                    ssid=r["ssid"] or "",
                    bssid=r["bssid"],
                    signal_dbm=r["signal_dbm"] or 0,
                    channel=r["channel"] or 0,
                    frequency_mhz=r["frequency_mhz"] or 0,
                    security=r["security"] or "open",
                    quality=r["quality"] or 0,
                    vendor=r["vendor"],
                    hidden=bool(r["hidden"]),
                    wps=bool(r["wps"]),
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                    tags=tuple(_loads(r["tags"]) or ()),
                )
            )
        return result

    def distinct_ssids(self) -> list[str]:
        rows = self.db.query("SELECT DISTINCT ssid FROM access_points WHERE ssid != '' ORDER BY ssid")
        return [r["ssid"] for r in rows]

    # ------------------------------------------------------------------ #
    # LAN
    # ------------------------------------------------------------------ #
    def save_lan_scan(self, scan: LanScan) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO lan_scans (timestamp, subnet, source, device_count) VALUES (?,?,?,?)",
                (scan.timestamp, scan.subnet, scan.source, scan.count),
            )
            scan_id = int(cursor.lastrowid or 0)
            device_rows = []
            for device in scan.devices:
                conn.execute(
                    """
                    INSERT INTO devices
                        (mac, ip, hostname, vendor, alias, trusted, online, is_gateway,
                         observation_count, first_seen, last_seen)
                    VALUES (?,?,?,?,?,?,?,?,1,?,?)
                    ON CONFLICT(mac) DO UPDATE SET
                        ip=excluded.ip,
                        hostname=COALESCE(excluded.hostname, devices.hostname),
                        vendor=COALESCE(excluded.vendor, devices.vendor),
                        online=excluded.online,
                        is_gateway=MAX(excluded.is_gateway, devices.is_gateway),
                        observation_count=devices.observation_count + 1,
                        last_seen=excluded.last_seen
                    """,
                    (
                        device.mac,
                        device.ip,
                        device.hostname,
                        device.vendor,
                        device.alias,
                        1 if device.trusted else 0,
                        1 if device.online else 0,
                        1 if device.is_gateway else 0,
                        device.first_seen or scan.timestamp,
                        device.last_seen or scan.timestamp,
                    ),
                )
                device_rows.append((scan_id, device.mac, scan.timestamp, device.ip, 1 if device.online else 0))
            if device_rows:
                conn.executemany(
                    "INSERT INTO device_observations (scan_id, mac, timestamp, ip, online) VALUES (?,?,?,?,?)",
                    device_rows,
                )
        return scan_id

    def latest_lan_scan(self) -> LanScan | None:
        row = self.db.query_one("SELECT id, timestamp, subnet, source FROM lan_scans ORDER BY timestamp DESC LIMIT 1")
        if row is None:
            return None
        scan_id = row["id"]
        obs = self.db.query(
            """
            SELECT d.*, o.ip AS obs_ip
            FROM device_observations o
            JOIN devices d ON d.mac = o.mac
            WHERE o.scan_id = ?
            """,
            (scan_id,),
        )
        devices = tuple(
            LanDevice(
                mac=r["mac"],
                ip=r["obs_ip"] or r["ip"] or "",
                hostname=r["hostname"],
                vendor=r["vendor"],
                alias=r["alias"],
                trusted=bool(r["trusted"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                online=bool(r["online"]),
                is_gateway=bool(r["is_gateway"]),
            )
            for r in obs
        )
        return LanScan(
            timestamp=row["timestamp"], subnet=row["subnet"] or "", devices=devices, source=row["source"] or "db"
        )

    def devices(self, *, online_only: bool = False) -> list[LanDevice]:
        sql = "SELECT * FROM devices"
        if online_only:
            sql += " WHERE online = 1"
        sql += " ORDER BY is_gateway DESC, last_seen DESC"
        rows = self.db.query(sql)
        return [
            LanDevice(
                mac=r["mac"],
                ip=r["ip"] or "",
                hostname=r["hostname"],
                vendor=r["vendor"],
                alias=r["alias"],
                trusted=bool(r["trusted"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                online=bool(r["online"]),
                is_gateway=bool(r["is_gateway"]),
            )
            for r in rows
        ]

    def ghost_devices(self, min_age_hours: float = 24.0) -> list[LanDevice]:
        threshold = time.time() - min_age_hours * 3600
        rows = self.db.query(
            "SELECT * FROM devices WHERE observation_count = 1 AND last_seen < ? ORDER BY last_seen DESC",
            (threshold,),
        )
        return [
            LanDevice(
                mac=r["mac"],
                ip=r["ip"] or "",
                hostname=r["hostname"],
                vendor=r["vendor"],
                alias=r["alias"],
                trusted=bool(r["trusted"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                online=False,
                is_gateway=bool(r["is_gateway"]),
            )
            for r in rows
        ]

    def set_device_trusted(self, mac: str, trusted: bool, alias: str | None = None) -> None:
        with self.db.transaction() as conn:
            if alias is not None:
                conn.execute(
                    "UPDATE devices SET trusted=?, alias=? WHERE mac=?",
                    (1 if trusted else 0, alias, mac),
                )
            else:
                conn.execute("UPDATE devices SET trusted=? WHERE mac=?", (1 if trusted else 0, mac))
        self._append_trust(mac, trusted)

    def _append_trust(self, mac: str, trusted: bool) -> None:
        current = set(self.kv_get("trusted_macs", []) or [])
        if trusted:
            current.add(mac)
        else:
            current.discard(mac)
        self.kv_set("trusted_macs", sorted(current))

    def trusted_macs(self) -> list[str]:
        return list(self.kv_get("trusted_macs", []) or [])

    def device_history(self, mac: str, hours: float = 24 * 7) -> list[dict[str, Any]]:
        since = time.time() - hours * 3600
        rows = self.db.query(
            "SELECT timestamp, ip, online FROM device_observations WHERE mac=? AND timestamp>=? ORDER BY timestamp",
            (mac, since),
        )
        return [dict(r) for r in rows]

    def new_devices_since(self, since: float) -> list[LanDevice]:
        rows = self.db.query("SELECT * FROM devices WHERE first_seen >= ? ORDER BY first_seen DESC", (since,))
        return [
            LanDevice(
                mac=r["mac"],
                ip=r["ip"] or "",
                hostname=r["hostname"],
                vendor=r["vendor"],
                alias=r["alias"],
                trusted=bool(r["trusted"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                online=bool(r["online"]),
                is_gateway=bool(r["is_gateway"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # Eventos
    # ------------------------------------------------------------------ #
    def add_event(self, event: Event, *, dedup_window_sec: int = 0) -> tuple[int, bool]:
        """Inserta un evento. Con ``dedup_window_sec`` agrupa repetidos.

        Devuelve ``(event_id, created_new)``.
        """
        if event.fingerprint and dedup_window_sec > 0:
            cutoff = time.time() - dedup_window_sec
            existing = self.db.query_one(
                "SELECT id FROM events WHERE fingerprint=? AND created_at>=? AND muted=0 ORDER BY created_at DESC LIMIT 1",
                (event.fingerprint, cutoff),
            )
            if existing is not None:
                with self.db.transaction() as conn:
                    conn.execute(
                        "UPDATE events SET dedup_count = dedup_count + 1 WHERE id = ?",
                        (existing["id"],),
                    )
                return int(existing["id"]), False
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events
                    (fingerprint, kind, severity, title, body, created_at, read, muted, dedup_count, evidence)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event.fingerprint,
                    event.kind,
                    event.severity.value,
                    event.title,
                    event.body,
                    event.created_at,
                    1 if event.read else 0,
                    1 if event.muted else 0,
                    event.dedup_count,
                    _dumps(event.evidence) if event.evidence else None,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        return event_id, True

    def list_events(
        self,
        *,
        limit: int = 100,
        min_severity: Severity | None = None,
        unread_only: bool = False,
        since: float | None = None,
        include_muted: bool = True,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list[Any] = []
        if min_severity is not None:
            allowed = [s.value for s in Severity if s.rank >= min_severity.rank]
            placeholders = ",".join("?" * len(allowed))
            clauses.append(f"severity IN ({placeholders})")
            params.extend(allowed)
        if unread_only:
            clauses.append("read = 0")
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if not include_muted:
            clauses.append("muted = 0")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self.db.query(f"SELECT * FROM events {where} ORDER BY created_at DESC LIMIT ?", params)
        return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, row: Any) -> Event:
        return Event(
            severity=Severity(row["severity"]),
            title=row["title"] or "",
            body=row["body"] or "",
            kind=row["kind"] or "general",
            fingerprint=row["fingerprint"] or "",
            created_at=row["created_at"],
            read=bool(row["read"]),
            muted=bool(row["muted"]),
            event_id=row["id"],
            dedup_count=row["dedup_count"],
            evidence=_loads(row["evidence"]) if "evidence" in row.keys() else None,  # noqa: SIM118
        )

    def mark_event_read(self, event_id: int | None = None, *, all_events: bool = False) -> int:
        with self.db.transaction() as conn:
            if all_events:
                cursor = conn.execute("UPDATE events SET read=1 WHERE read=0")
            elif event_id is not None:
                cursor = conn.execute("UPDATE events SET read=1 WHERE id=?", (event_id,))
            else:
                return 0
            return cursor.rowcount

    def mute_fingerprint(self, fingerprint: str, muted: bool = True) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE events SET muted=? WHERE fingerprint=?", (1 if muted else 0, fingerprint)
            )
            return cursor.rowcount

    def unread_count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM events WHERE read=0", default=0))

    def event_counts_by_severity(self) -> dict[str, int]:
        rows = self.db.query("SELECT severity, COUNT(*) AS n FROM events WHERE read=0 GROUP BY severity")
        return {r["severity"]: r["n"] for r in rows}

    # ------------------------------------------------------------------ #
    # Monitor pasivo
    # ------------------------------------------------------------------ #
    def start_monitor_session(self, interface: str, channels: list[int], started_at: float) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO monitor_sessions (started_at, interface, channels, status) VALUES (?,?,?,?)",
                (started_at, interface, ",".join(str(c) for c in channels), "running"),
            )
            return int(cursor.lastrowid or 0)

    def close_monitor_session(self, session_id: int, packet_count: int, status: str = "stopped") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE monitor_sessions SET ended_at=?, packet_count=?, status=? WHERE id=?",
                (time.time(), packet_count, status, session_id),
            )

    def add_monitor_event(
        self,
        *,
        session_id: int | None,
        kind: str,
        ts: float,
        bssid: str = "",
        ssid: str = "",
        source_mac: str = "",
        channel: int = 0,
        rssi: int = 0,
        count: int = 1,
        evidence: str | None = None,
    ) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO monitor_events
                    (session_id, ts, kind, bssid, ssid, source_mac, channel, rssi, count, evidence)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (session_id, ts, kind, bssid, ssid, source_mac, channel, rssi, count, evidence),
            )
            return int(cursor.lastrowid or 0)

    def list_monitor_events(
        self, *, limit: int = 200, since: float | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self.db.query(f"SELECT * FROM monitor_events {where} ORDER BY ts DESC LIMIT ?", params)
        return [dict(r) for r in rows]

    def monitor_stats(self, since: float | None = None) -> dict[str, int]:
        if since is None:
            rows = self.db.query("SELECT kind, SUM(count) AS n FROM monitor_events GROUP BY kind")
        else:
            rows = self.db.query(
                "SELECT kind, SUM(count) AS n FROM monitor_events WHERE ts>=? GROUP BY kind", (since,)
            )
        return {r["kind"]: int(r["n"] or 0) for r in rows}

    def monitor_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM monitor_sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Histórico de canal (previsión por hora/día)
    # ------------------------------------------------------------------ #
    def record_channel_advisory(
        self,
        *,
        ts: float,
        hour: int,
        weekday: int,
        band: str,
        best_channel: int,
        availability: int,
        interference: float,
        samples: int,
        ranking: list[int] | None = None,
    ) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO channel_advisory
                    (ts, hour, weekday, band, best_channel, availability, interference, samples, ranking)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    ts,
                    hour,
                    weekday,
                    band,
                    best_channel,
                    availability,
                    interference,
                    samples,
                    _dumps(ranking) if ranking else None,
                ),
            )
            return int(cursor.lastrowid or 0)

    def channel_advisory_buckets(self, band: str = "2.4 GHz", *, weeks: float | None = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT weekday, hour, best_channel, COUNT(*) AS n, "
            "AVG(availability) AS availability, MAX(interference) AS interference "
            "FROM channel_advisory WHERE band = ?"
        )
        params: list[Any] = [band]
        if weeks is not None:
            sql += " AND ts >= ?"
            params.append(time.time() - weeks * 7 * 86400)
        sql += " GROUP BY weekday, hour, best_channel"
        rows = self.db.query(sql, params)
        return [
            {
                "weekday": int(r["weekday"]),
                "hour": int(r["hour"]),
                "best_channel": int(r["best_channel"]),
                "n": int(r["n"]),
                "availability": round(float(r["availability"] or 0)),
                "interference": round(float(r["interference"] or 0), 3),
            }
            for r in rows
        ]

    def channel_advisory_count(self, band: str = "2.4 GHz") -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM channel_advisory WHERE band=?", (band,), default=0))

    # ------------------------------------------------------------------ #
    # Lista de vigilancia (watchlist)
    # ------------------------------------------------------------------ #
    def add_watch(
        self,
        bssid: str,
        *,
        ssid: str = "",
        note: str = "",
        expected_channel: int | None = None,
        expected_security: str | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO watchlist (bssid, ssid, note, expected_channel, expected_security, created_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(bssid) DO UPDATE SET
                    ssid=excluded.ssid, note=excluded.note,
                    expected_channel=excluded.expected_channel,
                    expected_security=excluded.expected_security
                """,
                (bssid.upper(), ssid or None, note or None, expected_channel, expected_security, time.time()),
            )

    def remove_watch(self, bssid: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM watchlist WHERE bssid=?", (bssid.upper(),))
            return cursor.rowcount > 0

    def list_watch(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM watchlist ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    def watch_map(self) -> dict[str, dict[str, Any]]:
        return {str(row["bssid"]): row for row in self.list_watch()}

    def channel_advisory_recent(self, limit: int = 30, band: str = "2.4 GHz") -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT ts, hour, weekday, best_channel, availability, interference, samples "
            "FROM channel_advisory WHERE band=? ORDER BY ts DESC LIMIT ?",
            (band, limit),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Snapshots
    # ------------------------------------------------------------------ #
    def save_snapshot(self, snapshot: Snapshot) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO snapshots (kind, label, digest, created_at, payload) VALUES (?,?,?,?,?)",
                (
                    snapshot.kind,
                    snapshot.label,
                    snapshot.digest,
                    snapshot.created_at,
                    _dumps(snapshot.payload),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_snapshots(self, kind: str | None = None, limit: int = 50) -> list[Snapshot]:
        if kind:
            rows = self.db.query(
                "SELECT * FROM snapshots WHERE kind=? ORDER BY created_at DESC LIMIT ?", (kind, limit)
            )
        else:
            rows = self.db.query("SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ?", (limit,))
        return [
            Snapshot(
                kind=r["kind"],
                created_at=r["created_at"],
                label=r["label"] or "",
                digest=r["digest"] or "",
                payload=_loads(r["payload"]) or {},
                snapshot_id=r["id"],
            )
            for r in rows
        ]

    def get_snapshot(self, snapshot_id: int) -> Snapshot | None:
        r = self.db.query_one("SELECT * FROM snapshots WHERE id=?", (snapshot_id,))
        if r is None:
            return None
        return Snapshot(
            kind=r["kind"],
            created_at=r["created_at"],
            label=r["label"] or "",
            digest=r["digest"] or "",
            payload=_loads(r["payload"]) or {},
            snapshot_id=r["id"],
        )

    def delete_snapshot(self, snapshot_id: int) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # KV y mantenimiento
    # ------------------------------------------------------------------ #
    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value FROM kv WHERE key=?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return row["value"]

    def kv_set(self, key: str, value: Any) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, _dumps(value)),
            )

    def counts(self) -> dict[str, int]:
        latest = self.db.query_one("SELECT ap_count FROM wifi_scans ORDER BY timestamp DESC LIMIT 1")
        return {
            "visible_networks": int(latest["ap_count"]) if latest else 0,
            "lan_devices": int(self.db.scalar("SELECT COUNT(*) FROM devices WHERE online=1", default=0)),
            "untrusted_devices": int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM devices WHERE online=1 AND trusted=0 AND is_gateway=0", default=0
                )
            ),
            "unread_events": self.unread_count(),
            "wifi_scans": int(self.db.scalar("SELECT COUNT(*) FROM wifi_scans", default=0)),
        }

    def purge_old(self, days: int = 90) -> dict[str, int]:
        cutoff = time.time() - days * 86400
        with self.db.transaction() as conn:
            obs = conn.execute("DELETE FROM ap_observations WHERE timestamp < ?", (cutoff,)).rowcount
            devobs = conn.execute("DELETE FROM device_observations WHERE timestamp < ?", (cutoff,)).rowcount
            scans = conn.execute("DELETE FROM wifi_scans WHERE timestamp < ?", (cutoff,)).rowcount
            lans = conn.execute("DELETE FROM lan_scans WHERE timestamp < ?", (cutoff,)).rowcount
            events = conn.execute("DELETE FROM events WHERE created_at < ? AND read=1", (cutoff,)).rowcount
            monev = conn.execute("DELETE FROM monitor_events WHERE ts < ?", (cutoff,)).rowcount
            monses = conn.execute("DELETE FROM monitor_sessions WHERE started_at < ?", (cutoff,)).rowcount
        return {
            "ap_observations": obs,
            "device_observations": devobs,
            "wifi_scans": scans,
            "lan_scans": lans,
            "events": events,
            "monitor_events": monev,
            "monitor_sessions": monses,
        }
