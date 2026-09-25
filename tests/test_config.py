from __future__ import annotations

from aethernet.config import (
    Paths,
    Settings,
    load_settings,
    save_settings,
)


def test_settings_roundtrip(tmp_paths):
    settings = Settings()
    settings.my_ssids = ["MiRed", "Otra"]
    settings.scan_interval_min = 30
    settings.quiet_enabled = True
    settings.device_aliases = {"AA:BB": "Router"}
    save_settings(settings, tmp_paths)
    loaded = load_settings(tmp_paths)
    assert loaded.my_ssids == ["MiRed", "Otra"]
    assert loaded.scan_interval_min == 30
    assert loaded.quiet_enabled is True
    assert loaded.device_aliases == {"AA:BB": "Router"}


def test_load_missing_returns_defaults(tmp_paths):
    assert load_settings(tmp_paths).scan_interval_min == 15


def test_quiet_hours_parsing():
    settings = Settings(quiet_enabled=True, quiet_start="23:00", quiet_end="07:00")
    assert settings.quiet_hours() == (23 * 60, 7 * 60)
    settings.quiet_enabled = False
    assert settings.quiet_hours() is None
    settings.quiet_enabled = True
    settings.quiet_start = "bad"
    assert settings.quiet_hours() is None


def test_paths_are_under_dirs(tmp_path):
    paths = Paths(data_dir=tmp_path / "d", config_dir=tmp_path / "c", cache_dir=tmp_path / "k")
    assert paths.db_path.parent == tmp_path / "d"
    assert paths.config_file.name == "config.toml"
    paths.ensure()
    assert paths.data_dir.exists()
