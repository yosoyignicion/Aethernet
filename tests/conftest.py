from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aethernet.config import Paths  # noqa: E402
from aethernet.data.db import Database  # noqa: E402
from aethernet.data.repository import Repository  # noqa: E402


@pytest.fixture
def db():
    database = Database(":memory:")
    database.migrate()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def tmp_paths(tmp_path) -> Paths:
    return Paths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
    ).ensure()
