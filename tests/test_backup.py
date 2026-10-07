from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from aethernet import backup as backup_mod
from aethernet.backup import (
    BUNDLE_FORMAT_VERSION,
    BackupError,
    BackupManifest,
    ManifestError,
    SchemaTooNewError,
    create_backup,
    read_manifest,
    restore_backup,
    verify_backup,
)
from aethernet.config import Paths, Settings, save_settings
from aethernet.data.db import MIGRATIONS, Database
from aethernet.data.repository import Repository
from aethernet.models import Event, Severity
from helpers import ap, scan


def _populate(paths: Paths) -> None:
    db = Database(paths.db_path)
    db.migrate()
    try:
        repo = Repository(db)
        repo.save_wifi_scan(scan(ap("A", "AA:BB:CC:00:00:01", dbm=-42)), my_bssids=None)
        repo.add_event(Event(severity=Severity.WARNING, title="Canal saturado", body="x"))
    finally:
        db.close()


def _manifest_for(db_bytes: bytes, **overrides: object) -> BackupManifest:
    base: dict[str, object] = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "app_version": "test",
        "schema_version": len(MIGRATIONS),
        "created_at": 1000.0,
        "hostname": "test",
        "includes_config": False,
        "includes_reports": False,
        "db_sha256": hashlib.sha256(db_bytes).hexdigest(),
        "db_bytes": len(db_bytes),
        "members": ("aethernet.db", "manifest.json"),
    }
    base.update(overrides)
    return BackupManifest(**base)  # type: ignore[arg-type]


def _write_bundle(
    dest: Path,
    *,
    db_bytes: bytes,
    manifest: BackupManifest,
    extra: tuple[tuple[str, bytes], ...] = (),
    include_db: bool = True,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        if include_db:
            db_tmp = dest.parent / "db.tmp"
            db_tmp.write_bytes(db_bytes)
            tar.add(db_tmp, arcname="aethernet.db")
        manifest_tmp = dest.parent / "manifest.tmp"
        manifest_tmp.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
        tar.add(manifest_tmp, arcname="manifest.json")
        for index, (arcname, data) in enumerate(extra):
            extra_tmp = dest.parent / f"extra-{index}.tmp"
            extra_tmp.write_bytes(data)
            tar.add(extra_tmp, arcname=arcname)
    return dest


def _clean_paths(tmp_path: Path) -> Paths:
    return Paths(
        data_dir=tmp_path / "clean" / "data",
        config_dir=tmp_path / "clean" / "config",
        cache_dir=tmp_path / "clean" / "cache",
    )


def test_create_backup_writes_bundle(tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    result = create_backup(tmp_paths, tmp_paths.data_dir / "b.tar.gz")

    assert result.path.exists()
    manifest = read_manifest(result.path)
    assert manifest.format_version == BUNDLE_FORMAT_VERSION
    assert manifest.schema_version == len(MIGRATIONS)
    assert manifest.db_sha256 == result.manifest.db_sha256
    assert manifest.db_bytes > 0
    assert manifest.includes_config is False
    assert "aethernet.db" in manifest.members


def test_create_backup_includes_config(tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    save_settings(Settings(my_ssids=["A"]), tmp_paths)

    result = create_backup(tmp_paths, tmp_paths.data_dir / "b.tar.gz")

    assert result.manifest.includes_config is True


def test_verify_ok(tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    result = create_backup(tmp_paths, tmp_paths.data_dir / "b.tar.gz")

    verification = verify_backup(result.path)

    assert verification.ok is True
    assert verification.problems == ()
    assert verification.manifest is not None


def test_read_manifest_missing(tmp_paths: Paths) -> None:
    bundle = tmp_paths.data_dir / "empty.tar.gz"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, "w:gz"):
        pass

    with pytest.raises(ManifestError):
        read_manifest(bundle)


def test_verify_missing_db(tmp_paths: Paths) -> None:
    db_bytes = b"SQLite format 3\x00"
    manifest = _manifest_for(db_bytes)
    bundle = _write_bundle(
        tmp_paths.data_dir / "b.tar.gz", db_bytes=db_bytes, manifest=manifest, include_db=False
    )

    verification = verify_backup(bundle)

    assert verification.ok is False
    assert any("obligatorio" in problem for problem in verification.problems)


def test_verify_detects_hash_mismatch(tmp_paths: Paths) -> None:
    db_bytes = b"not a real database"
    manifest = _manifest_for(db_bytes, db_sha256="0" * 64)
    bundle = _write_bundle(tmp_paths.data_dir / "b.tar.gz", db_bytes=db_bytes, manifest=manifest)

    verification = verify_backup(bundle)

    assert verification.ok is False
    assert any("hash" in problem for problem in verification.problems)


def test_restore_skips_unsafe_member(tmp_path: Path, tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    db_bytes = tmp_paths.db_path.read_bytes()
    bundle = _write_bundle(
        tmp_path / "malicious.tar.gz",
        db_bytes=db_bytes,
        manifest=_manifest_for(db_bytes),
        extra=(("../evil.txt", b"pwned"),),
    )
    clean = _clean_paths(tmp_path)

    restore_backup(bundle, clean)

    assert clean.db_path.exists()
    assert not (clean.data_dir.parent / "evil.txt").exists()


def test_restore_rejects_future_schema(tmp_path: Path, tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    db_bytes = tmp_paths.db_path.read_bytes()
    bundle = _write_bundle(
        tmp_path / "future.tar.gz",
        db_bytes=db_bytes,
        manifest=_manifest_for(db_bytes, schema_version=len(MIGRATIONS) + 5),
    )

    with pytest.raises(SchemaTooNewError):
        restore_backup(bundle, _clean_paths(tmp_path))


def test_restore_backs_up_existing(tmp_path: Path, tmp_paths: Paths) -> None:
    _populate(tmp_paths)
    bundle = create_backup(tmp_paths, tmp_path / "b.tar.gz")

    result = restore_backup(bundle.path, tmp_paths)

    assert result.previous_backup is not None
    assert result.previous_backup.exists()


def test_restore_over_open_wal_connection(tmp_path: Path, tmp_paths: Paths) -> None:
    """Regresión: un ``-wal`` huérfano no debe vaciar la base restaurada."""
    _populate(tmp_paths)
    bundle = create_backup(tmp_paths, tmp_path / "b.tar.gz")

    tmp_paths.db_path.unlink()
    live = Database(tmp_paths.db_path)  # base vacía en WAL, como una app abierta
    live.migrate()
    try:
        restore_backup(bundle.path, tmp_paths)
    finally:
        live.close()

    check = Database(tmp_paths.db_path)
    check.migrate()
    try:
        assert Repository(check).wifi_scan_count() == 1
    finally:
        check.close()


def test_restore_falls_back_on_page_size_mismatch(tmp_path: Path, tmp_paths: Paths) -> None:
    """El backup inverso exige mismo ``page_size``; si no, cae al reemplazo atómico."""
    _populate(tmp_paths)
    bundle = create_backup(tmp_paths, tmp_path / "b.tar.gz")

    # Destino legado con page_size 8192 (el de la copia es 4096).
    tmp_paths.db_path.unlink()
    legacy = sqlite3.connect(str(tmp_paths.db_path))
    legacy.execute("PRAGMA page_size=8192")
    legacy.execute("VACUUM")
    legacy.execute("CREATE TABLE legacy(x)")
    legacy.commit()
    legacy.close()
    assert _page_size_of(tmp_paths.db_path) == 8192

    result = restore_backup(bundle.path, tmp_paths)

    assert result.schema_version == len(MIGRATIONS)
    assert _page_size_of(tmp_paths.db_path) == 4096
    check = Database(tmp_paths.db_path)
    check.migrate()
    try:
        assert Repository(check).wifi_scan_count() == 1
    finally:
        check.close()


def _page_size_of(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA page_size").fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def test_restore_prefers_reverse_backup(
    tmp_path: Path, tmp_paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con ``page_size`` compatible, la restauración no toca el fallback atómico."""
    _populate(tmp_paths)
    bundle = create_backup(tmp_paths, tmp_path / "b.tar.gz")

    # El fallback solo aparece para limpiar sidecars; el backup inverso no lo
    # necesita, así que parchearlo delata si el reemplazo atómico se usara.
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("no debería usarse el fallback atómico")

    monkeypatch.setattr(backup_mod, "_remove_sidecars", explode)

    result = restore_backup(bundle.path, tmp_paths)

    assert result.schema_version == len(MIGRATIONS)
    check = Database(tmp_paths.db_path)
    check.migrate()
    try:
        assert Repository(check).wifi_scan_count() == 1
    finally:
        check.close()


def test_restore_refuses_when_target_locked(
    tmp_path: Path, tmp_paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con la base en uso no se reemplaza a ciegas: se avisa y se aborta."""
    _populate(tmp_paths)
    bundle = create_backup(tmp_paths, tmp_path / "b.tar.gz")
    real = backup_mod._consistent_copy

    # Simula un destino en uso justo en el reemplazo, no en el resguardo previo.
    def guarded(source: Path, destination: Path) -> None:
        if Path(destination) == tmp_paths.db_path:
            raise sqlite3.OperationalError("database is locked")
        real(source, destination)

    monkeypatch.setattr(backup_mod, "_consistent_copy", guarded)

    with pytest.raises(BackupError, match="uso"):
        restore_backup(bundle.path, tmp_paths)
