"""Criterio de aceptación del feedback: recuperación *offline* en máquina limpia.

No basta con exportar: aquí se demuestra que un usuario puede restaurar una copia
en una instalación nueva (sin acceso a la original) y aun así **examinar el
historial** y **generar un informe**.
"""

from __future__ import annotations

from pathlib import Path

from aethernet.backup import create_backup, restore_backup
from aethernet.config import Paths, Settings, load_settings, save_settings
from aethernet.data.db import MIGRATIONS, Database
from aethernet.data.repository import Repository
from aethernet.models import Event, Severity
from aethernet.report import build_report_data, export
from helpers import ap, scan


def _paths(tmp_path: Path, root: str) -> Paths:
    return Paths(
        data_dir=tmp_path / root / "data",
        config_dir=tmp_path / root / "config",
        cache_dir=tmp_path / root / "cache",
    ).ensure()


def test_offline_recovery_on_clean_machine(tmp_path: Path) -> None:
    # 1. Estado de origen: historial + ajustes.
    source = _paths(tmp_path, "origin")
    db = Database(source.db_path)
    db.migrate()
    try:
        repo = Repository(db)
        repo.save_wifi_scan(scan(ap("MiRed", "AA:BB:CC:00:00:01", dbm=-42)), my_bssids=None)
        repo.save_wifi_scan(scan(ap("MiRed", "AA:BB:CC:00:00:01", dbm=-55), ts=2000.0), my_bssids=None)
        repo.add_event(Event(severity=Severity.WARNING, title="Canal saturado", body="canal 6"))
    finally:
        db.close()
    save_settings(Settings(my_ssids=["MiRed"]), source)

    # 2. Copia.
    bundle = create_backup(source, tmp_path / "aethernet-backup.tar.gz")
    assert bundle.manifest.schema_version == len(MIGRATIONS)

    # 3. Máquina limpia: otra instalación, sin nada de la original.
    clean = _paths(tmp_path, "clean")
    assert not clean.db_path.exists()

    result = restore_backup(bundle.path, clean)
    assert result.schema_version == len(MIGRATIONS)
    assert result.config_restored is True
    assert not list(clean.data_dir.glob(".aethernet-restore-*"))

    # 4. Se lee el historial y se genera un informe desde cero.
    restored = Database(clean.db_path)
    restored.migrate()
    try:
        repo = Repository(restored)
        assert repo.wifi_scan_count() == 2
        latest = repo.latest_wifi_scan()
        assert latest is not None
        assert latest.count == 1
        assert load_settings(clean).my_ssids == ["MiRed"]

        data = build_report_data(repo, load_settings(clean), event_limit=10)
        output = clean.report_dir / "recovery.md"
        files = export(data, "md", output)
        assert files
        assert files[0].exists()
        assert "MiRed" in files[0].read_text(encoding="utf-8")
    finally:
        restored.close()
