"""Configuración y rutas XDG. Sin dependencias externas.

La configuración vive en ``~/.config/aethernet/config.toml`` y los datos
(DB, informes, logs) en ``~/.local/share/aethernet``. Todo local.
"""

from __future__ import annotations

import contextlib
import hmac
import os
import re
import secrets
import shutil
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from . import APP_NAME
from .logging_setup import get_logger

log = get_logger(__name__)

LEGACY_APP_NAME = "homenet-audit"
_LEGACY_DB_NAME = "homenet.db"

#: Variable de entorno que fuerza el token de la API local (si se define).
API_TOKEN_ENV = "AETHERNET_API_TOKEN"
_API_TOKEN_FILE = "api.token"


def _xdg(env: str, default: str) -> Path:
    base = os.environ.get(env)
    if base:
        return Path(base).expanduser()
    return Path.home() / default


@dataclass(frozen=True, slots=True)
class Paths:
    """Rutas canónicas de la aplicación."""

    data_dir: Path = field(default_factory=lambda: _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME)
    config_dir: Path = field(default_factory=lambda: _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME)
    cache_dir: Path = field(default_factory=lambda: _xdg("XDG_CACHE_HOME", ".cache") / APP_NAME)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aethernet.db"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "aethernet.log"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def pid_file(self) -> Path:
        return self.data_dir / "daemon.pid"

    @property
    def control_file(self) -> Path:
        return self.data_dir / "daemon.control"

    @property
    def oui_cache(self) -> Path:
        return self.cache_dir / "oui.tsv"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure(self) -> Paths:
        for path in (self.data_dir, self.config_dir, self.cache_dir, self.report_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self


def default_paths() -> Paths:
    return Paths()


def api_token_path(paths: Paths | None = None) -> Path:
    """Ruta del token de la API local (fichero privado 0600)."""
    return (paths or default_paths()).data_dir / _API_TOKEN_FILE


def _write_private(path: Path, content: str) -> None:
    """Escribe un fichero de forma atómica con permisos 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def resolve_api_token(paths: Paths | None = None) -> str:
    """Token de la API local: ``AETHERNET_API_TOKEN`` > fichero 0600 > nuevo.

    Se genera una sola vez por instalación y se persiste en el directorio de
    datos; nunca se codifica en el código. Es obligatorio para los endpoints que
    mutan estado o activan hardware (el resto son de solo lectura en loopback).
    """
    env = os.environ.get(API_TOKEN_ENV)
    if env and env.strip():
        return env.strip()
    paths = (paths or default_paths()).ensure()
    path = paths.data_dir / _API_TOKEN_FILE
    with contextlib.suppress(OSError):
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(32)
    with contextlib.suppress(OSError):
        _write_private(path, token + "\n")
    return token


def tokens_match(expected: str, provided: str | None) -> bool:
    """Comparación en tiempo constante para no filtrar el token por temporización."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


def _legacy_dir(env: str, default: str) -> Path:
    return _xdg(env, default) / LEGACY_APP_NAME


def migrate_legacy(paths: Paths | None = None) -> list[str]:
    """Migra datos de la instalación previa ``homenet-audit`` si existe.

    Idempotente y no destructiva: nunca borra el directorio antiguo. Devuelve
    las rutas creadas. Copia la DB renombrada a ``aethernet.db``.
    """
    paths = paths or default_paths()
    migrated: list[str] = []

    legacy_data = _legacy_dir("XDG_DATA_HOME", ".local/share")
    if legacy_data.exists():
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        for item in sorted(legacy_data.iterdir()):
            name = _LEGACY_DB_NAME if item.name == _LEGACY_DB_NAME else item.name
            target = paths.data_dir / name
            if not target.exists():
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
                migrated.append(str(target))

    legacy_config = _legacy_dir("XDG_CONFIG_HOME", ".config")
    if legacy_config.exists():
        paths.config_dir.mkdir(parents=True, exist_ok=True)
        for item in sorted(legacy_config.iterdir()):
            target = paths.config_dir / item.name
            if not target.exists():
                shutil.copy2(item, target) if item.is_file() else shutil.copytree(item, target)
                migrated.append(str(target))

    if migrated:
        log.info("migrados %d elementos desde %s", len(migrated), LEGACY_APP_NAME)
    return migrated


def bootstrap_paths() -> Paths:
    """Punto de entrada real: migra datos heredados y garantiza directorios."""
    paths = default_paths()
    migrate_legacy(paths)
    return paths.ensure()


@dataclass(slots=True)
class Settings:
    """Preferencias del usuario con valores por defecto sensatos."""

    my_ssids: list[str] = field(default_factory=list)
    my_bssids: list[str] = field(default_factory=list)
    interface: str | None = None
    scan_mode: str = "passive"  # passive | active
    scan_interval_min: int = 15
    dwell_ms: int = 110
    rssi_floor_dbm: int = -85
    lan_scan_enabled: bool = True
    trusted_macs: list[str] = field(default_factory=list)
    device_aliases: dict[str, str] = field(default_factory=dict)

    notifications: bool = True
    sound: bool = False
    quiet_enabled: bool = False
    quiet_start: str = "23:00"
    quiet_end: str = "07:00"
    muted_rules: list[str] = field(default_factory=list)
    muted_bssids: list[str] = field(default_factory=list)
    dedup_window_min: int = 30
    notify_min_severity: str = "warning"

    theme: str = "dark"  # dark | light | terminal
    ui_scale: int = 100
    cursor_style: str = "block"  # block | line
    compact: bool = False
    scanline_effect: bool = True

    api_enabled: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    redact_macs_in_reports: bool = False
    report_template_title: str = "Estado de mi WiFi"
    # Retención del histórico: purga automática de registros más antiguos (0 = off).
    retention_days: int = 90

    # Monitor pasivo (nunca exclusivo: usa interfaz virtual, no corta tu WiFi)
    monitor_enabled: bool = False
    monitor_interface: str | None = None
    monitor_channels: list[int] = field(default_factory=lambda: list(range(1, 14)))
    monitor_dwell_ms: int = 220
    deauth_threshold: int = 20
    deauth_window_s: int = 10
    probe_min_rssi: int = -80
    consent_monitor: bool = False

    # Previsión de canal: guarda el mejor canal por hora/día para anticipar saturación
    forecast_enabled: bool = True
    forecast_window_hours: int = 6
    # Canal en el que está tu router (para comparar y ver cuánto mejorarías)
    my_channel: int = 0

    # Vigilancia de canal en segundo plano: avisa si tu canal se satura y hay uno mejor
    channel_watch_enabled: bool = True
    channel_watch_hours: int = 3
    channel_watch_min_improvement: int = 15

    def merged_with(self, data: dict[str, Any]) -> Settings:
        known = {f.name for f in fields(self)}
        for key, value in data.items():
            if key in known:
                setattr(self, key, value)
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        return cls().merged_with(data)

    def quiet_hours(self) -> tuple[int, int] | None:
        if not self.quiet_enabled:
            return None
        start = _parse_hhmm(self.quiet_start)
        end = _parse_hhmm(self.quiet_end)
        if start is None or end is None:
            return None
        return start, end


def _parse_hhmm(value: str) -> int | None:
    try:
        hours, minutes = value.strip().split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# Persistencia TOML (lectura stdlib, escritura mínima)
# --------------------------------------------------------------------------- #
def load_settings(paths: Paths | None = None) -> Settings:
    paths = paths or default_paths()
    config_file = paths.config_file
    if not config_file.exists():
        return Settings()
    try:
        with config_file.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return Settings()
    return Settings.from_dict(raw)


def save_settings(settings: Settings, paths: Paths | None = None) -> None:
    paths = (paths or default_paths()).ensure()
    config_file = paths.config_file
    lines: list[str] = ["# Aethernet — configuración", ""]
    plain: list[tuple[str, Any]] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in settings.to_dict().items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            plain.append((key, value))
    for key, value in plain:
        lines.append(f"{key} = {_toml_value(value)}")
    for table, values in tables:
        lines.append("")
        lines.append(f"[{_toml_key(table)}]")
        for key, value in values.items():
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_key(key: object) -> str:
    text = str(key)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if value is None:
        return '""'
    return '"' + str(value) + '"'
