from __future__ import annotations

from aethernet.alerts.filters import AlertFilter, in_quiet_hours
from aethernet.alerts.notifier import Notifier
from aethernet.alerts.queue import AlertQueue
from aethernet.config import Settings
from aethernet.models import Finding, Severity


def _finding(severity=Severity.WARNING, rule="new_open_network", subject="AA:BB:CC:00:00:01") -> Finding:
    return Finding(
        rule_id=rule,
        severity=severity,
        title="t",
        description="d",
        subject=subject,
        subject_type="bssid",
    )


def test_in_quiet_hours_crosses_midnight():
    assert in_quiet_hours(23 * 60 + 30, 23 * 60, 7 * 60)
    assert in_quiet_hours(2 * 60, 23 * 60, 7 * 60)
    assert not in_quiet_hours(12 * 60, 23 * 60, 7 * 60)


def test_in_quiet_hours_same_day():
    assert in_quiet_hours(13 * 60, 12 * 60, 14 * 60)
    assert not in_quiet_hours(15 * 60, 12 * 60, 14 * 60)


def test_filter_mutes_rules_and_bssids():
    settings = Settings(muted_rules=["new_open_network"], muted_bssids=["BB:BB:BB:BB:BB:BB"])
    alert_filter = AlertFilter(settings)
    assert alert_filter.is_muted_finding(_finding())
    assert alert_filter.is_muted_finding(_finding(rule="other", subject="bb:bb:bb:bb:bb:bb"))


def test_filter_severity_threshold_and_quiet():
    settings = Settings(notify_min_severity="alert")
    alert_filter = AlertFilter(settings)
    assert not alert_filter.should_notify(_finding(severity=Severity.WARNING))
    assert alert_filter.should_notify(_finding(severity=Severity.CRITICAL))

    settings.quiet_enabled = True
    settings.quiet_start = "00:00"
    settings.quiet_end = "23:59"
    assert not alert_filter.should_notify(_finding(severity=Severity.CRITICAL))


def test_filter_disabled_notifications():
    settings = Settings(notifications=False)
    assert not AlertFilter(settings).should_notify(_finding(severity=Severity.CRITICAL))


class _RecordingNotifier(Notifier):
    def __init__(self):
        super().__init__(Settings())
        self.calls = []

    def notify(self, title, body, severity=Severity.INFO):  # noqa: D102
        self.calls.append((title, severity))
        return True


def test_queue_dedup_and_notify(repo):
    settings = Settings(notifications=True, notify_min_severity="warning", dedup_window_min=30)
    notifier = _RecordingNotifier()
    queue = AlertQueue(repo, settings, notifier=notifier)
    result = queue.submit_findings([_finding(), _finding()])
    assert result.created_count == 1
    assert result.deduped_count == 1
    assert result.notified == 1
    assert len(notifier.calls) == 1
    assert len(repo.list_events()) == 1


def test_queue_respects_muted_rules(repo):
    settings = Settings(muted_rules=["new_open_network"], notifications=True)
    queue = AlertQueue(repo, settings, notifier=_RecordingNotifier())
    result = queue.submit_findings([_finding()])
    assert result.muted == 1
    assert result.notified == 0
