"""Conexión SQLite endurecida, migraciones y helpers de consulta.

Decisiones de rendimiento:
* WAL + ``synchronous=NORMAL``: lecturas concurrentes sin bloquear al daemon.
* Una conexión por hilo (``threading.local``): la GUI y el service no comparten.
* Sentencias parametrizadas siempre; ``executemany`` en escrituras por lote.
* ``PRAGMA optimize`` al cerrar para que el planner aprenda.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from ..logging_setup import get_logger

log = get_logger(__name__)

MIGRATIONS: tuple[str, ...] = (
    # v1 — esquema inicial
    """
    CREATE TABLE IF NOT EXISTS wifi_scans (
        id          TEXT PRIMARY KEY,
        timestamp   REAL NOT NULL,
        interface   TEXT,
        source      TEXT,
        adapter_json TEXT,
        payload     TEXT,
        ap_count    INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS access_points (
        bssid       TEXT PRIMARY KEY,
        ssid        TEXT,
        vendor      TEXT,
        security    TEXT,
        hidden      INTEGER NOT NULL DEFAULT 0,
        wps         INTEGER NOT NULL DEFAULT 0,
        is_mine     INTEGER NOT NULL DEFAULT 0,
        ignored     INTEGER NOT NULL DEFAULT 0,
        tags        TEXT,
        first_seen  REAL NOT NULL,
        last_seen   REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ap_observations (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id       TEXT NOT NULL REFERENCES wifi_scans(id) ON DELETE CASCADE,
        bssid         TEXT NOT NULL,
        timestamp     REAL NOT NULL,
        ssid          TEXT,
        channel       INTEGER,
        frequency_mhz INTEGER,
        signal_dbm    INTEGER,
        quality       INTEGER,
        security      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_apobs_bssid_ts ON ap_observations(bssid, timestamp);
    CREATE INDEX IF NOT EXISTS idx_apobs_ts        ON ap_observations(timestamp);
    CREATE INDEX IF NOT EXISTS idx_apobs_channel   ON ap_observations(channel, timestamp);

    CREATE TABLE IF NOT EXISTS lan_scans (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp    REAL NOT NULL,
        subnet       TEXT,
        source       TEXT,
        device_count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS devices (
        mac               TEXT PRIMARY KEY,
        ip                TEXT,
        hostname          TEXT,
        vendor            TEXT,
        alias             TEXT,
        trusted           INTEGER NOT NULL DEFAULT 0,
        online            INTEGER NOT NULL DEFAULT 0,
        is_gateway        INTEGER NOT NULL DEFAULT 0,
        observation_count INTEGER NOT NULL DEFAULT 1,
        first_seen        REAL NOT NULL,
        last_seen         REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS device_observations (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id   INTEGER NOT NULL REFERENCES lan_scans(id) ON DELETE CASCADE,
        mac       TEXT NOT NULL,
        timestamp REAL NOT NULL,
        ip        TEXT,
        online    INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_devobs_mac_ts ON device_observations(mac, timestamp);

    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT,
        kind        TEXT,
        severity    TEXT,
        title       TEXT,
        body        TEXT,
        created_at  REAL NOT NULL,
        read        INTEGER NOT NULL DEFAULT 0,
        muted       INTEGER NOT NULL DEFAULT 0,
        dedup_count INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_events_fp      ON events(fingerprint);
    CREATE INDEX IF NOT EXISTS idx_events_read    ON events(read);

    CREATE TABLE IF NOT EXISTS snapshots (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        kind       TEXT NOT NULL,
        label      TEXT,
        digest     TEXT,
        created_at REAL NOT NULL,
        payload    TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_snapshots_kind ON snapshots(kind, created_at DESC);

    CREATE TABLE IF NOT EXISTS kv (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """,
    # v2 — evidencia cruda en eventos + monitor pasivo
    """
    ALTER TABLE events ADD COLUMN evidence TEXT;

    CREATE TABLE IF NOT EXISTS monitor_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at   REAL NOT NULL,
        ended_at     REAL,
        interface    TEXT,
        channels     TEXT,
        packet_count INTEGER NOT NULL DEFAULT 0,
        status       TEXT NOT NULL DEFAULT 'running'
    );

    CREATE TABLE IF NOT EXISTS monitor_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER REFERENCES monitor_sessions(id) ON DELETE CASCADE,
        ts         REAL NOT NULL,
        kind       TEXT NOT NULL,
        bssid      TEXT,
        ssid       TEXT,
        source_mac TEXT,
        channel    INTEGER,
        rssi       INTEGER,
        count      INTEGER NOT NULL DEFAULT 1,
        evidence   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_monev_ts   ON monitor_events(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_monev_kind ON monitor_events(kind, ts);
    """,
)


class Database:
    """Envoltura fina y thread-safe sobre SQLite."""

    def __init__(self, path: Path | str, *, timeout: float = 10.0) -> None:
        self.path = Path(path)
        self._timeout = timeout
        self._local = threading.local()
        self._write_lock = threading.RLock()
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- conexiones ------------------------------------------------------- #
    @property
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_connection()
            self._local.conn = conn
        return conn

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=self._timeout,
            isolation_level=None,  # autocommit; transacciones explícitas
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-8000")  # ~8 MB
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("PRAGMA optimize")
            conn.close()
            self._local.conn = None

    # -- migraciones ------------------------------------------------------ #
    def migrate(self) -> int:
        conn = self.connection
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
                )
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                current = row["version"] if row else 0
                for index, script in enumerate(MIGRATIONS[current:], start=current + 1):
                    conn.executescript(script)
                    if row is None and index == 1:
                        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (index,))
                        row = True
                    else:
                        conn.execute("UPDATE schema_version SET version = ?", (index,))
                    log.info("migración aplicada: v%s", index)
                return len(MIGRATIONS)
            except sqlite3.Error:
                conn.execute("ROLLBACK")
                raise
            finally:
                if conn.in_transaction:
                    conn.execute("COMMIT")

    # -- helpers ---------------------------------------------------------- #
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connection
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
        return self.connection.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        row = self.connection.execute(sql, params).fetchone()
        return cast("sqlite3.Row | None", row)

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    def vacuum(self) -> None:
        self.connection.execute("VACUUM")
