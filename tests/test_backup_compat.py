"""Compatibilidad histórica de copias: la *escalera* de restauración.

Cada paquete real commitear en ``tests/fixtures/backups/`` se restaura sobre una
máquina limpia y debe migrar al esquema actual sin perder datos. Si alguien rompe
una migración append-only o el formato del paquete, el test falla.

Las fixtures se generan con ``scripts/gen_backup_fixture.py`` (una por versión de
esquema). Ver ``tests/fixtures/backups/README.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aethernet.backup import read_manifest, restore_backup, verify_backup
from aethernet.config import Paths, load_settings
from aethernet.data.db import MIGRATIONS, Database
from aethernet.data.repository import Repository
from aethernet.report import build_report_data, export

FIXTURES = Path(__file__).parent / "fixtures" / "backups"
BUNDLES = sorted(FIXTURES.glob("*.tar.gz"))


def _expected_path(bundle: Path) -> Path:
    return bundle.with_name(bundle.name[: -len(".tar.gz")] + ".expected.json")


def _load_expected(bundle: Path) -> dict[str, Any]:
    return json.loads(_expected_path(bundle).read_text(encoding="utf-8"))


@pytest.mark.skipif(not BUNDLES, reason="no hay fixtures de copia histórica")
@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda path: path.name)
def test_historical_backup_restores_on_clean_machine(bundle: Path, tmp_path: Path) -> None:
    expected = _load_expected(bundle)

    manifest = read_manifest(bundle)
    assert manifest.app_version == expected["app_version"]
    assert manifest.schema_version == expected["schema_version"]
    assert manifest.format_version == expected["format_version"]
    assert manifest.db_sha256 == expected["db_sha256"]
    assert verify_backup(bundle).ok is True

    clean = Paths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
    )
    result = restore_backup(bundle, clean)

    assert result.manifest.schema_version == expected["schema_version"]
    assert result.schema_version == len(MIGRATIONS)

    restored = Database(clean.db_path)
    try:
        repo = Repository(restored)
        counts = repo.counts()
        for key, value in expected["counts"].items():
            assert counts[key] == value, f"conteo '{key}' no sobrevivió"
        assert repo.kv_get("fixture_marker")["purpose"] == expected["kv_marker"]

        settings = load_settings(clean)
        data = build_report_data(repo, settings)
        written = export(data, "markdown", tmp_path / "informe.md")
        assert written and written[0].exists()
        assert "AethernetLab" in written[0].read_text(encoding="utf-8")
    finally:
        restored.close()

    assert result.config_restored is True
    assert load_settings(clean).my_ssids == expected["config_ssids"]
    assert list(clean.data_dir.glob(".aethernet-restore-*")) == []
