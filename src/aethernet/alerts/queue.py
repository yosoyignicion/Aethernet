"""Cola de alertas: persiste hallazgos, deduplica y notifica."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Event, Finding, Severity
from .filters import AlertFilter
from .notifier import Notifier

log = get_logger(__name__)


@dataclass(slots=True)
class AlertResult:
    created: list[Finding] = field(default_factory=list)
    created_ids: list[int] = field(default_factory=list)
    deduped_ids: list[int] = field(default_factory=list)
    notified: int = 0
    muted: int = 0

    @property
    def created_count(self) -> int:
        return len(self.created)

    @property
    def deduped_count(self) -> int:
        return len(self.deduped_ids)

    def to_dict(self) -> dict[str, int]:
        return {
            "created": self.created_count,
            "deduped": self.deduped_count,
            "notified": self.notified,
            "muted": self.muted,
        }


class AlertQueue:
    """Punto único de entrada de eventos hacia la DB y el escritorio."""

    def __init__(self, repo, settings: Settings, notifier: Notifier | None = None) -> None:
        self.repo = repo
        self.settings = settings
        self.filter = AlertFilter(settings)
        self.notifier = notifier or Notifier(settings)

    def submit_findings(self, findings: list[Finding], *, when: float | None = None) -> AlertResult:
        result = AlertResult()
        window = self.settings.dedup_window_min * 60
        for finding in findings:
            muted = self.filter.is_muted_finding(finding)
            body = finding.description
            if finding.suggestion:
                body = f"{body}\n{finding.suggestion}"
            event = Event(
                severity=finding.severity,
                title=finding.title,
                body=body,
                kind=finding.rule_id,
                fingerprint=finding.fingerprint,
                created_at=finding.timestamp,
                muted=muted,
                evidence=finding.evidence or None,
            )
            event_id, created_new = self.repo.add_event(event, dedup_window_sec=window)
            if created_new:
                result.created.append(finding)
                result.created_ids.append(event_id)
            else:
                result.deduped_ids.append(event_id)
            if muted:
                result.muted += 1
                continue
            if created_new and self.filter.should_notify(finding, when):
                try:
                    self.notifier.notify(finding.title, finding.description, finding.severity)
                    result.notified += 1
                except Exception as exc:  # notificar nunca debe romper el escaneo
                    log.warning("fallo al notificar: %s", exc)
        return result

    def add_event(
        self,
        title: str,
        body: str = "",
        severity: Severity = Severity.INFO,
        kind: str = "general",
        fingerprint: str = "",
        notify: bool = False,
    ) -> int:
        event = Event(
            severity=severity,
            title=title,
            body=body,
            kind=kind,
            fingerprint=fingerprint,
            created_at=time.time(),
        )
        event_id, _ = self.repo.add_event(event)
        if notify and self.settings.notifications and not self.filter.quiet_now():
            try:
                self.notifier.notify(title, body, severity)
            except Exception as exc:
                log.warning("fallo al notificar evento: %s", exc)
        return event_id

    # Delegaciones de bandeja ------------------------------------------- #
    def list(self, **kwargs):
        return self.repo.list_events(**kwargs)

    def unread_count(self) -> int:
        return self.repo.unread_count()

    def mark_read(self, event_id: int | None = None, *, all_events: bool = False) -> int:
        return self.repo.mark_event_read(event_id, all_events=all_events)

    def mute(self, fingerprint: str, muted: bool = True) -> int:
        return self.repo.mute_fingerprint(fingerprint, muted)
