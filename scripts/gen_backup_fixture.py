#!/usr/bin/env python3
"""Genera la *fixture* de copia histórica que usa ``tests/test_backup_compat.py``.

La fixture se crea **siempre con la versión actual** de la app: es una instantánea
real del formato que produce este código. Al subir ``schema_version`` (nueva
migración append-only) o ``BUNDLE_FORMAT_VERSION``, vuelve a ejecutar el script:
añadirá un paquete nuevo y **conservará los anteriores**. Así las migraciones
dejan de ser una promesa y pasan a tener un test de restauración real en CI.

Uso::

    python scripts/gen_backup_fixture.py

Produce, bajo ``tests/fixtures/backups/``::

    aethernet-<app>-schema<esquema>.tar.gz   # paquete real (DB + config + manifiesto)
    aethernet-<app>-schema<esquema>.expected.json

El ``.expected.json`` documenta procedencia (versión de SQLite, ``page_size``,
hash de la base) y las aserciones de la prueba (conteos, SSIDs de la config).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "src", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from aethernet import __version__  # noqa: E402
from aethernet import backup as backup_mod  # noqa: E402
from aethernet.backup import create_backup  # noqa: E402
from aethernet.config import Paths, Settings, save_settings  # noqa: E402
from aethernet.data.db import MIGRATIONS, Database  # noqa: E402
from aethernet.data.repository import Repository  # noqa: E402
from aethernet.models import Event, LanScan, Severity  # noqa: E402
from helpers import ap, device, scan  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "backups"

#: Timestamp fijo para que la base sea reproducible bit a bit en una misma máquina.
EPOCH = 1_700_000_000.0


def _populate(paths: Paths) -> dict[str, int]:
    """Rellena una base con datos representativos y deterministas."""
    db = Database(paths.db_path)
    db.migrate()
    try:
        repo = Repository(db)
        repo.save_wifi_scan(
            scan(
                ap("AethernetLab", "AA:BB:CC:00:00:01", dbm=-42, channel=6),
                ap("Vecino", "AA:BB:CC:00:00:02", dbm=-71, channel=11, security="wpa3"),
                ts=EPOCH,
            ),
            my_bssids=None,
        )
        repo.save_wifi_scan(
            scan(ap("AethernetLab", "AA:BB:CC:00:00:01", dbm=-45, channel=6), ts=EPOCH + 60),
            my_bssids=None,
        )
        repo.save_lan_scan(
            LanScan(
                timestamp=EPOCH,
                subnet="192.168.1.0/24",
                devices=(
                    device("DE:AD:BE:EF:00:01", "192.168.1.1", gateway=True),
                    device("DE:AD:BE:EF:00:02", "192.168.1.24"),
                ),
            )
        )
        repo.add_event(
            Event(
                severity=Severity.WARNING,
                title="Canal saturado",
                body="El canal 6 concentra demasiados puntos de acceso.",
                created_at=EPOCH,
            )
        )
        repo.kv_set("fixture_marker", {"project": "aethernet", "purpose": "golden"})
        return repo.counts()
    finally:
        db.close()


def _page_size(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA page_size").fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="aethernet-fixture-"))
    try:
        paths = Paths(
            data_dir=work / "data",
            config_dir=work / "config",
            cache_dir=work / "cache",
        ).ensure()
        counts = _populate(paths)
        ssids = ["AethernetLab"]
        save_settings(Settings(my_ssids=ssids, scan_interval_min=15), paths)

        name = f"aethernet-{__version__}-schema{len(MIGRATIONS)}.tar.gz"
        # Congela reloj y hostname: el paquete queda reproducible y no filtra el
        # nombre de la máquina de quien lo genera.
        real_time = backup_mod.time.time
        real_hostname = backup_mod.socket.gethostname
        backup_mod.time.time = lambda: EPOCH
        backup_mod.socket.gethostname = lambda: "aethernet-fixture"
        try:
            bundle = create_backup(paths, FIXTURES / name, include_config=True)
        finally:
            backup_mod.time.time = real_time
            backup_mod.socket.gethostname = real_hostname
        expected: dict[str, Any] = {
            "app_version": __version__,
            "schema_version": len(MIGRATIONS),
            "format_version": bundle.manifest.format_version,
            "db_sha256": bundle.manifest.db_sha256,
            "db_bytes": bundle.manifest.db_bytes,
            "sqlite_version": sqlite3.sqlite_version,
            "page_size": _page_size(paths.db_path),
            "counts": counts,
            "config_ssids": ssids,
            "kv_marker": "golden",
        }
        expected_path = bundle.path.with_name(bundle.path.name[: -len(".tar.gz")] + ".expected.json")
        expected_path.write_text(
            json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)

    print(f"fixture:  {bundle.path}")
    print(f"expected: {expected_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
