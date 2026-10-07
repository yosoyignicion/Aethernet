from __future__ import annotations

from pathlib import Path

import pytest

from aethernet.backup import create_backup
from aethernet.config import default_paths
from aethernet.data.db import MIGRATIONS
from aethernet.ui.state import UIContext
from helpers import ap, scan


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg" / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg" / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg" / "cache"))


def test_ui_context_restore_rebuilds_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    ctx = UIContext.build()
    try:
        ctx.repo.save_wifi_scan(scan(ap("A", "AA:BB:CC:00:00:01", dbm=-42)), my_bssids=None)
        assert ctx.repo.wifi_scan_count() == 1
        bundle = create_backup(ctx.paths, ctx.paths.data_dir / "aethernet-backup-test.tar.gz")

        ctx.db.close()
        default_paths().db_path.unlink()
        fresh = UIContext.build()
        try:
            assert fresh.repo.wifi_scan_count() == 0
            result = fresh.restore(bundle.path)
            assert result.schema_version == len(MIGRATIONS)
            assert fresh.repo.wifi_scan_count() == 1
        finally:
            fresh.db.close()
    finally:
        ctx.db.close()
