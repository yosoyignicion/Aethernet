from __future__ import annotations

import pytest

from aethernet.core.monitor import interface as iface_mod
from aethernet.core.monitor.interface import (
    MonitorInterface,
    MonitorPermissionError,
    MonitorUnsupportedError,
)
from aethernet.models import AdapterInfo, Band
from aethernet.utils import CommandResult


class _Runner:
    def __init__(self, ok: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.ok = ok

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(argv)
        return CommandResult(argv, 0 if self.ok else 1, "", "", 0.0)


def _adapter(supports_monitor: bool, phy: str = "phy0") -> AdapterInfo:
    return AdapterInfo(interface="wlan0", phy=phy, supports_monitor=supports_monitor, bands=(Band.GHZ_24,))


def test_preflight_requires_monitor_support(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(False))
    checker = MonitorInterface("wlan0", executor=_Runner(), root_checker=lambda: True, which=lambda _n: "/usr/bin/iw")
    ok, reason = checker.preflight()
    assert not ok and "monitor" in reason


def test_preflight_requires_root(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(True))
    checker = MonitorInterface("wlan0", executor=_Runner(), root_checker=lambda: False, which=lambda _n: "/usr/bin/iw")
    ok, reason = checker.preflight()
    assert not ok and "root" in reason.lower()


def test_preflight_requires_iw(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(True))
    checker = MonitorInterface("wlan0", executor=_Runner(), root_checker=lambda: True, which=lambda _n: None)
    ok, reason = checker.preflight()
    assert not ok and "iw" in reason


def test_create_uses_virtual_interface_not_disruptive(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(True))
    runner = _Runner()
    checker = MonitorInterface(
        "wlan0", "aemon0", executor=runner, root_checker=lambda: True, which=lambda _n: "/usr/bin/iw"
    )
    name = checker.create()
    assert name == "aemon0"
    assert ["iw", "dev", "wlan0", "interface", "add", "aemon0", "type", "monitor"] in runner.calls
    # jamás se cambia el tipo de la interfaz gestionada
    assert not any("set" in call and "type" in call and "monitor" in call for call in runner.calls)
    assert ["ip", "link", "set", "aemon0", "up"] in runner.calls
    checker.destroy()
    assert ["iw", "dev", "aemon0", "del"] in runner.calls


def test_create_raises_permission(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(True))
    checker = MonitorInterface(
        "wlan0", executor=_Runner(), root_checker=lambda: False, which=lambda _n: "/usr/bin/iw"
    )
    with pytest.raises(MonitorPermissionError):
        checker.create()


def test_create_raises_when_vif_unsupported(monkeypatch):
    monkeypatch.setattr(iface_mod, "probe_adapter", lambda _if: _adapter(True))
    checker = MonitorInterface(
        "wlan0", executor=_Runner(ok=False), root_checker=lambda: True, which=lambda _n: "/usr/bin/iw"
    )
    with pytest.raises(MonitorUnsupportedError):
        checker.create()
