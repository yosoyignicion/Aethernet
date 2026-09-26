from __future__ import annotations

import stat

import pytest

from aethernet.config import Settings, api_token_path, resolve_api_token, tokens_match


def test_resolve_api_token_persists_private(tmp_paths, monkeypatch):
    monkeypatch.delenv("AETHERNET_API_TOKEN", raising=False)
    first = resolve_api_token(tmp_paths)
    assert len(first) >= 32
    path = api_token_path(tmp_paths)
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert resolve_api_token(tmp_paths) == first


def test_resolve_api_token_env_override(tmp_paths, monkeypatch):
    monkeypatch.setenv("AETHERNET_API_TOKEN", "s3cret")
    assert resolve_api_token(tmp_paths) == "s3cret"


def test_tokens_match():
    assert tokens_match("abc", "abc") is True
    assert tokens_match("abc", "abd") is False
    assert tokens_match("abc", None) is False
    assert tokens_match("", "x") is False


def test_mutating_endpoints_require_token(tmp_paths, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from aethernet.api.server import create_app
    from aethernet.data.db import Database
    from aethernet.data.repository import Repository

    db = Database(tmp_paths.data_dir / "api-test.db")
    db.migrate()
    repo = Repository(db)

    monkeypatch.setenv("AETHERNET_API_TOKEN", "test-token")
    client = TestClient(create_app(repo, Settings(), paths=tmp_paths))

    assert client.get("/health").status_code == 200

    for path in ("/scan", "/monitor/start", "/monitor/stop", "/events/1/read"):
        assert client.post(path).status_code == 401, path

    headers = {"X-Aethernet-Token": "test-token"}
    assert client.post("/scan", headers=headers).status_code == 503
    assert client.post("/monitor/start", headers=headers).status_code == 503
    db.close()
