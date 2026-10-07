from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from aethernet import cli
from aethernet.backup import read_manifest
from aethernet.config import default_paths
from aethernet.data.db import MIGRATIONS, Database
from aethernet.data.repository import Repository
from helpers import ap, scan


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg" / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg" / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg" / "cache"))


def _seed() -> None:
    paths = default_paths().ensure()
    db = Database(paths.db_path)
    db.migrate()
    try:
        Repository(db).save_wifi_scan(scan(ap("A", "AA:BB:CC:00:00:01", dbm=-42)), my_bssids=None)
    finally:
        db.close()


def test_cli_backup_and_restore_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)
    _seed()

    assert cli.main(["backup", "--json"]) == 0
    paths = default_paths()
    bundle = next(paths.data_dir.glob("aethernet-backup-*.tar.gz"))
    assert bundle.exists()

    copied = tmp_path / "copy.tar.gz"
    shutil.copy2(bundle, copied)
    assert cli.main(["restore", "--verify", str(copied), "--json"]) == 0

    paths.db_path.unlink()
    assert cli.main(["restore", str(copied), "--json"]) == 0

    check = Database(paths.db_path)
    check.migrate()
    try:
        assert Repository(check).wifi_scan_count() == 1
    finally:
        check.close()


def test_cli_backup_includes_config_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)
    _seed()

    assert cli.main(["backup", "--no-config", "--json"]) == 0
    paths = default_paths()
    bundle = next(paths.data_dir.glob("aethernet-backup-*.tar.gz"))
    assert read_manifest(bundle).includes_config is False


def test_cli_db_info_reports_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolate(tmp_path, monkeypatch)

    assert cli.main(["db", "info", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == len(MIGRATIONS)


def test_cli_restore_verify_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)

    assert cli.main(["restore", "--verify", str(tmp_path / "nope.tar.gz")]) == 1


def test_cli_doctor_reports_backup_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolate(tmp_path, monkeypatch)
    _seed()
    assert cli.main(["backup", "--json"]) == 0
    capsys.readouterr()

    assert cli.main(["doctor", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["backup"]["exists"] is True
    assert payload["backup"]["file"].endswith(".tar.gz")
