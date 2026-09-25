"""Filtros de alertas: modo silencioso, umbral de severidad y mutings."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..config import Settings
from ..models import Finding, Severity


def in_quiet_hours(minutes_now: int, start: int, end: int) -> bool:
    """Ventana silenciosa que puede cruzar la medianoche (23:00 → 07:00)."""
    if start == end:
        return False
    if start < end:
        return start <= minutes_now < end
    return minutes_now >= start or minutes_now < end


@dataclass(slots=True)
class AlertFilter:
    """Decide qué se guarda enmudecido y qué merece notificación de escritorio."""

    settings: Settings

    def is_muted_finding(self, finding: Finding) -> bool:
        if finding.rule_id in self.settings.muted_rules:
            return True
        muted_bssids = {b.upper() for b in self.settings.muted_bssids}
        return bool(finding.subject and finding.subject.upper() in muted_bssids)

    def severity_at_least_threshold(self, severity: Severity) -> bool:
        try:
            threshold = Severity(self.settings.notify_min_severity)
        except ValueError:
            threshold = Severity.WARNING
        return severity.at_least(threshold)

    def quiet_now(self, when: float | None = None) -> bool:
        window = self.settings.quiet_hours()
        if window is None:
            return False
        start, end = window
        local = time.localtime(when if when is not None else time.time())
        minutes_now = local.tm_hour * 60 + local.tm_min
        return in_quiet_hours(minutes_now, start, end)

    def should_notify(self, finding: Finding, when: float | None = None) -> bool:
        if not self.settings.notifications:
            return False
        if self.is_muted_finding(finding):
            return False
        if not self.severity_at_least_threshold(finding.severity):
            return False
        return not self.quiet_now(when)
