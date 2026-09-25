from __future__ import annotations

from aethernet.core.analysis import (
    AnalysisContext,
    BssidSsidMismatchRule,
    ChannelChangeRule,
    CongestionRule,
    DeauthFloodRule,
    EvilTwinRule,
    MonitorEvent,
    NewLanDeviceRule,
    NewOpenNetworkRule,
    NewStrongApRule,
    ProbeRequestRule,
    SignalDropRule,
    SimilarSsidRule,
    WpsDetectionRule,
    run_rules,
)
from aethernet.models import LanScan, Severity
from helpers import ap, device, scan

MINE = "AA:AA:AA:AA:AA:AA"
EVIL = "BB:BB:BB:BB:BB:BB"


def _ctx(**kwargs) -> AnalysisContext:
    kwargs.setdefault("my_ssids", ("MiRed",))
    kwargs.setdefault("my_bssids", (MINE,))
    return AnalysisContext(**kwargs)


def test_evil_twin_detected():
    ctx = _ctx(scan=scan(ap("MiRed", MINE, dbm=-40), ap("MiRed", EVIL, dbm=-55)))
    findings = EvilTwinRule().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].severity is Severity.CRITICAL
    assert findings[0].subject == EVIL


def test_evil_twin_needs_known_legit():
    ctx = AnalysisContext(scan=scan(ap("MiRed", EVIL)), my_ssids=("MiRed",))
    assert EvilTwinRule().evaluate(ctx) == []


def test_bssid_ssid_mismatch():
    ctx = _ctx(scan=scan(ap("Otra", MINE)))
    findings = BssidSsidMismatchRule().evaluate(ctx)
    assert findings and findings[0].severity is Severity.ALERT


def test_similar_ssid():
    ctx = _ctx(scan=scan(ap("MiRed", MINE), ap("MiRedd", EVIL)))
    findings = SimilarSsidRule().evaluate(ctx)
    assert any(f.subject == EVIL for f in findings)


def test_new_strong_ap_requires_known_history():
    first = NewStrongApRule().evaluate(_ctx(scan=scan(ap("Nueva", EVIL, dbm=-40)), known_bssids=set()))
    assert first == []
    second = NewStrongApRule().evaluate(
        _ctx(scan=scan(ap("Nueva", EVIL, dbm=-40)), known_bssids={MINE})
    )
    assert len(second) == 1


def test_channel_change():
    previous = scan(ap("MiRed", MINE, channel=6), ts=900)
    current = scan(ap("MiRed", MINE, channel=11), ts=1000)
    findings = ChannelChangeRule().evaluate(_ctx(scan=current, previous=previous))
    assert len(findings) == 1
    assert findings[0].evidence == {"from": 6, "to": 11, "bssid": MINE}


def test_signal_drop():
    ctx = _ctx(scan=scan(ap("MiRed", MINE, dbm=-75)), signal_history={MINE: [-40, -41, -40, -42]})
    findings = SignalDropRule().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].severity is Severity.ALERT


def test_new_open_network():
    ctx = _ctx(scan=scan(ap("Libre", EVIL, security="open")), known_bssids={MINE})
    findings = NewOpenNetworkRule().evaluate(ctx)
    assert len(findings) == 1


def test_wps_on_mine():
    ctx = _ctx(scan=scan(ap("MiRed", MINE, wps=True)))
    findings = WpsDetectionRule().evaluate(ctx)
    assert findings and findings[0].severity is Severity.WARNING


def test_congestion_flags_saturated_channel():
    target = ap("MiRed", MINE, channel=6)
    neighbors = [ap(f"Vecino{i}", f"0{i}:00:00:00:00:0{i}", channel=6) for i in range(1, 6)]
    findings = CongestionRule().evaluate(_ctx(scan=scan(target, *neighbors)))
    assert len(findings) == 1
    assert "6" in findings[0].title


def test_new_lan_device_severity():
    lan = LanScan(timestamp=1000.0, devices=(device("00:11:22:33:44:55", "192.168.1.20", trusted=False),))
    first = NewLanDeviceRule().evaluate(_ctx(scan=scan(ap("MiRed", MINE)), lan_scan=lan))
    assert first and first[0].severity is Severity.INFO  # primer escaneo: sin alarma
    known = NewLanDeviceRule().evaluate(
        _ctx(scan=scan(ap("MiRed", MINE)), lan_scan=lan, known_lan_macs={"AA:AA:AA:AA:AA:AA"})
    )
    assert known and known[0].severity is Severity.WARNING


def test_deauth_and_probe_events():
    deauth = MonitorEvent(kind="deauth", timestamp=1.0, bssid=MINE, source_mac=EVIL, count=30)
    probe = MonitorEvent(kind="probe", timestamp=1.0, ssid="MiRed", source_mac=EVIL)
    ctx = _ctx(scan=scan(ap("MiRed", MINE)), monitor_events=[deauth, probe])
    assert len(DeauthFloodRule().evaluate(ctx)) == 1
    assert len(ProbeRequestRule().evaluate(ctx)) == 1


def test_run_rules_respects_disabled_and_orders_by_severity():
    ctx = _ctx(
        scan=scan(ap("MiRed", MINE), ap("MiRed", EVIL, dbm=-55), ap("MiRedd", "CC:CC:CC:CC:CC:CC")),
        known_bssids={MINE},
    )
    findings = run_rules(ctx)
    assert findings[0].severity is Severity.CRITICAL
    disabled = run_rules(
        AnalysisContext(
            scan=ctx.scan,
            my_ssids=ctx.my_ssids,
            my_bssids=ctx.my_bssids,
            known_bssids=ctx.known_bssids,
            disabled_rules={"evil_twin"},
        )
    )
    assert all(f.rule_id != "evil_twin" for f in disabled)


def test_a_broken_rule_does_not_break_the_engine(monkeypatch):
    import aethernet.core.analysis as analysis

    class Broken:
        rule_id = "broken"
        severity = Severity.INFO

        def evaluate(self, ctx):
            raise RuntimeError("boom")

    monkeypatch.setattr(analysis, "DEFAULT_RULES", (Broken, EvilTwinRule))
    ctx = _ctx(scan=scan(ap("MiRed", MINE), ap("MiRed", EVIL)))
    findings = analysis.run_rules(ctx)
    assert any(f.rule_id == "evil_twin" for f in findings)
