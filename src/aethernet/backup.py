"""Copia de seguridad y restauración offline (*recovery*) de Aethernet.

Un *backup* no es un *export*: exportar demuestra que los datos se leen;
restaurar demuestra que el estado se puede reconstruir en una **máquina limpia**,
sin la instalación original. Este módulo empaqueta en un único ``.tar.gz``:

* ``aethernet.db`` — copia **consistente** de la base (``sqlite3.Connection.backup``),
  no una copia de fichero a pelo de una base en modo WAL.
* ``config.toml`` — ajustes del usuario (redes propias, alias, retención…).
* ``manifest.json`` — versión de formato, versión de la app, versión de esquema,
  hash SHA-256 de la base y qué incluye el paquete.

Los secretos **no** viajan: el token de la API (``api.token``) se regenera y el
secreto de sesión de la UI no es necesario. Por eso ``secrets_required`` va vacío.

Sin dependencias externas; solo la stdlib.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .config import Paths, default_paths
from .data.db import MIGRATIONS, Database
from .logging_setup import get_logger

log = get_logger(__name__)

#: Versión del formato del paquete. Se incrementa si cambia su estructura.
BUNDLE_FORMAT_VERSION = 1
BUNDLE_APP = "aethernet"
BUNDLE_DB = "aethernet.db"
BUNDLE_CONFIG = "config.toml"
BUNDLE_MANIFEST = "manifest.json"
BUNDLE_REPORTS = "reports"

_ALLOWED_TOP = frozenset({BUNDLE_DB, BUNDLE_CONFIG, BUNDLE_MANIFEST, BUNDLE_REPORTS})
_REQUIRED_MEMBERS = frozenset({BUNDLE_DB, BUNDLE_MANIFEST})


class BackupError(RuntimeError):
    """Error genérico de copia o restauración."""


class ManifestError(BackupError):
    """El manifiesto falta o no es válido."""


class SchemaTooNewError(BackupError):
    """La copia viene de una versión de esquema más nueva que esta app."""


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Metadatos de un paquete de copia. Todo lo necesario para restaurar con criterio."""

    format_version: int
    app_version: str
    schema_version: int
    created_at: float
    hostname: str
    includes_config: bool
    includes_reports: bool
    db_sha256: str
    db_bytes: int
    members: tuple[str, ...]
    secrets_required: tuple[str, ...] = ()
    notes: str = ""
    app: str = BUNDLE_APP

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "format_version": self.format_version,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "created_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)),
            "hostname": self.hostname,
            "includes_config": self.includes_config,
            "includes_reports": self.includes_reports,
            "db_sha256": self.db_sha256,
            "db_bytes": self.db_bytes,
            "members": list(self.members),
            "secrets_required": list(self.secrets_required),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupManifest:
        try:
            members = data.get("members", [])
            secrets_required = data.get("secrets_required", [])
            return cls(
                format_version=int(data["format_version"]),
                app_version=str(data["app_version"]),
                schema_version=int(data["schema_version"]),
                created_at=float(data["created_at"]),
                hostname=str(data["hostname"]),
                includes_config=bool(data["includes_config"]),
                includes_reports=bool(data["includes_reports"]),
                db_sha256=str(data["db_sha256"]),
                db_bytes=int(data["db_bytes"]),
                members=tuple(str(m) for m in members),
                secrets_required=tuple(str(s) for s in secrets_required),
                notes=str(data.get("notes", "")),
                app=str(data.get("app", BUNDLE_APP)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"manifiesto inválido: {exc}") from exc


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    manifest: BackupManifest


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    manifest: BackupManifest | None
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RestoreResult:
    db_path: Path
    config_restored: bool
    reports_restored: bool
    schema_version: int
    previous_backup: Path | None
    manifest: BackupManifest


# --------------------------------------------------------------------------- #
# Utilidades internas
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_version(db_path: Path) -> int:
    """Versión de esquema aplicada en una base; 0 si no existe o no está migrada."""
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        except sqlite3.Error:
            return 0
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _consistent_copy(source: Path, destination: Path) -> None:
    """Copia consistente de una base SQLite (funde el WAL, admite escritor activo)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _member_is_safe(name: str) -> bool:
    """Rechaza rutas absolutas o con ``..`` y limita a los miembros conocidos."""
    if not name or name.startswith(("/", "\\")):
        return False
    parts = PurePosixPath(name).parts
    if not parts or parts[0] not in _ALLOWED_TOP:
        return False
    return not any(part in ("..", "") for part in parts)


def _backup_existing(db_path: Path) -> Path | None:
    """Resguarda la base actual antes de sobrescribirla. Devuelve la ruta o ``None``."""
    if not db_path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    _consistent_copy(db_path, target)
    return target


def _remove_sidecars(db_path: Path) -> None:
    """Elimina los ficheros WAL/SHM huérfanos de una base.

    Al reemplazar el ``.db`` hay que descartar su ``-wal``/``-shm``: si sobreviven,
    SQLite reaplica una transacción ajena sobre la base restaurada y la deja vacía.
    """
    for suffix in ("-wal", "-shm"):
        with contextlib.suppress(OSError):
            Path(f"{db_path}{suffix}").unlink()


def _safe_extract(bundle: Path, destination: Path) -> list[str]:
    """Extrae solo miembros permitidos, con rutas saneadas. Devuelve lo extraído."""
    extracted: list[str] = []
    with tarfile.open(bundle, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not _member_is_safe(name):
                continue
            target = destination / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                shutil.copyfileobj(handle, out)
            extracted.append(name)
    return extracted


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def create_backup(
    paths: Paths | None = None,
    destination: Path | None = None,
    *,
    include_config: bool = True,
    include_reports: bool = False,
) -> BackupResult:
    """Crea un paquete de copia consistente. No incluye secretos."""
    paths = (paths or default_paths()).ensure()
    db_path = paths.db_path
    if not db_path.exists():
        raise BackupError(f"no hay base de datos que copiar en {db_path}")
    if destination is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        destination = paths.data_dir / f"aethernet-backup-{stamp}.tar.gz"
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix="aethernet-backup-"))
    tmp_bundle = destination.with_suffix(destination.suffix + ".tmp")
    try:
        staged_db = staging / BUNDLE_DB
        _consistent_copy(db_path, staged_db)

        members: list[str] = [BUNDLE_DB]
        if include_config and paths.config_file.exists():
            shutil.copy2(paths.config_file, staging / BUNDLE_CONFIG)
            members.append(BUNDLE_CONFIG)
        if include_reports and paths.report_dir.exists():
            shutil.copytree(paths.report_dir, staging / BUNDLE_REPORTS)
            members.append(BUNDLE_REPORTS)

        manifest = BackupManifest(
            format_version=BUNDLE_FORMAT_VERSION,
            app_version=__version__,
            schema_version=_schema_version(staged_db),
            created_at=time.time(),
            hostname=socket.gethostname(),
            includes_config=BUNDLE_CONFIG in members,
            includes_reports=BUNDLE_REPORTS in members,
            db_sha256=_sha256_file(staged_db),
            db_bytes=staged_db.stat().st_size,
            members=(*members, BUNDLE_MANIFEST),
            secrets_required=(),
            notes="aethernet backup",
        )
        (staging / BUNDLE_MANIFEST).write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with tarfile.open(tmp_bundle, "w:gz") as tar:
            for name in members:
                tar.add(staging / name, arcname=name)
            tar.add(staging / BUNDLE_MANIFEST, arcname=BUNDLE_MANIFEST)
        os.replace(tmp_bundle, destination)
    except (OSError, tarfile.TarError, sqlite3.Error) as exc:
        with contextlib.suppress(OSError):
            tmp_bundle.unlink()
        raise BackupError(f"no se pudo crear la copia: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    log.info("copia creada en %s (%d bytes de base)", destination, manifest.db_bytes)
    return BackupResult(path=destination, manifest=manifest)


def latest_backup(paths: Paths | None = None) -> Path | None:
    """Devuelve la copia más reciente del directorio de datos, si existe."""
    data_dir = (paths or default_paths()).data_dir
    candidates = sorted(
        data_dir.glob("aethernet-backup-*.tar.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_manifest(bundle: Path) -> BackupManifest:
    """Lee y valida el manifiesto de un paquete."""
    bundle = Path(bundle)
    if not bundle.exists():
        raise ManifestError(f"no existe el paquete: {bundle}")
    try:
        with tarfile.open(bundle, "r:gz") as tar:
            try:
                handle = tar.extractfile(BUNDLE_MANIFEST)
            except KeyError as exc:
                raise ManifestError("el paquete no contiene manifest.json") from exc
            if handle is None:
                raise ManifestError("no se pudo leer manifest.json")
            raw = handle.read()
    except tarfile.TarError as exc:
        raise ManifestError(f"paquete ilegible: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest.json no es JSON válido: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest.json debe ser un objeto JSON")
    return BackupManifest.from_dict(data)


def verify_backup(bundle: Path) -> VerifyResult:
    """Comprueba integridad y compatibilidad *sin escribir nada* (dry-run)."""
    bundle = Path(bundle)
    try:
        manifest = read_manifest(bundle)
    except ManifestError as exc:
        return VerifyResult(ok=False, manifest=None, problems=(str(exc),))

    problems: list[str] = []
    if manifest.format_version > BUNDLE_FORMAT_VERSION:
        problems.append(
            f"formato de paquete v{manifest.format_version} más nuevo que el soportado "
            f"v{BUNDLE_FORMAT_VERSION}"
        )

    try:
        with tarfile.open(bundle, "r:gz") as tar:
            names = set(tar.getnames())
            for name in sorted(_REQUIRED_MEMBERS - names):
                problems.append(f"falta el miembro obligatorio: {name}")
            for name in sorted(names):
                if (name in _ALLOWED_TOP or name.startswith(BUNDLE_REPORTS + "/")) and (
                    not _member_is_safe(name)
                ):
                    problems.append(f"miembro con ruta insegura: {name}")
            if BUNDLE_DB in names:
                handle = tar.extractfile(BUNDLE_DB)
                if handle is None:
                    problems.append("no se pudo leer aethernet.db del paquete")
                else:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
                    if digest.hexdigest() != manifest.db_sha256:
                        problems.append("el hash de aethernet.db no coincide con el manifiesto")
    except tarfile.TarError as exc:
        problems.append(f"paquete ilegible: {exc}")

    return VerifyResult(ok=not problems, manifest=manifest, problems=tuple(problems))


def restore_backup(
    bundle: Path,
    paths: Paths | None = None,
) -> RestoreResult:
    """Restaura un paquete sobre ``paths``.

    Valida antes de tocar nada; resguarda la base actual y aplica migraciones
    pendientes si la copia es más antigua. Una copia de un esquema más nuevo
    se rechaza siempre.
    """
    paths = (paths or default_paths()).ensure()
    bundle = Path(bundle)

    verification = verify_backup(bundle)
    if not verification.ok or verification.manifest is None:
        raise BackupError("copia no válida: " + "; ".join(verification.problems))
    manifest = verification.manifest
    if manifest.schema_version > len(MIGRATIONS):
        raise SchemaTooNewError(
            f"la copia usa el esquema v{manifest.schema_version}, más nuevo que el soportado "
            f"v{len(MIGRATIONS)}: actualiza Aethernet antes de restaurar"
        )

    previous = _backup_existing(paths.db_path)
    # El staging vive en el directorio de datos para que el reemplazo sea atómico
    # (mismo sistema de ficheros); ``/tmp`` puede ser tmpfs y romper ``os.replace``.
    staging = Path(tempfile.mkdtemp(prefix=".aethernet-restore-", dir=paths.data_dir))
    try:
        _safe_extract(bundle, staging)
        staged_db = staging / BUNDLE_DB
        if not staged_db.exists():
            raise BackupError("el paquete no contiene aethernet.db")
        _remove_sidecars(paths.db_path)
        os.replace(staged_db, paths.db_path)
        _remove_sidecars(paths.db_path)

        config_restored = False
        staged_config = staging / BUNDLE_CONFIG
        if staged_config.exists():
            paths.config_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(staged_config, paths.config_file)
            config_restored = True

        reports_restored = False
        staged_reports = staging / BUNDLE_REPORTS
        if staged_reports.exists():
            paths.report_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged_reports, paths.report_dir, dirs_exist_ok=True)
            reports_restored = True

        db = Database(paths.db_path)
        try:
            db.migrate()
            schema_version = _schema_version(paths.db_path)
        finally:
            db.close()

        log.info("copia restaurada desde %s (esquema v%s)", bundle, schema_version)
        return RestoreResult(
            db_path=paths.db_path,
            config_restored=config_restored,
            reports_restored=reports_restored,
            schema_version=schema_version,
            previous_backup=previous,
            manifest=manifest,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


__all__ = [
    "BUNDLE_FORMAT_VERSION",
    "BackupError",
    "BackupManifest",
    "BackupResult",
    "ManifestError",
    "RestoreResult",
    "SchemaTooNewError",
    "VerifyResult",
    "create_backup",
    "latest_backup",
    "read_manifest",
    "restore_backup",
    "verify_backup",
]
