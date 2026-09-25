"""Notificaciones de escritorio vía ``notify-send`` (sin dependencias Python)."""

from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Severity
from ..utils import run_command, which

log = get_logger(__name__)

_URGENCY = {
    Severity.INFO: "low",
    Severity.WARNING: "normal",
    Severity.ALERT: "critical",
    Severity.CRITICAL: "critical",
}

_ICONS = {
    Severity.INFO: "dialog-information",
    Severity.WARNING: "dialog-warning",
    Severity.ALERT: "dialog-error",
    Severity.CRITICAL: "security-high",
}

_SOUND_CANDIDATES = (
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
)


class Notifier:
    """Envía notificaciones con icono y urgencia por severidad."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._notify_send = which("notify-send")

    @property
    def available(self) -> bool:
        return self._notify_send is not None

    def notify(self, title: str, body: str, severity: Severity = Severity.INFO) -> bool:
        sent = False
        notify_send = self._notify_send
        if notify_send:
            argv = [
                notify_send,
                "--app-name=Aethernet",
                f"--urgency={_URGENCY.get(severity, 'normal')}",
                f"--icon={_ICONS.get(severity, 'dialog-information')}",
                f"--category=network.{severity.value}",
                title,
                body,
            ]
            result = run_command(argv, timeout=8)
            sent = result.ok
            if not result.ok:
                log.debug("notify-send falló: %s", result.stderr.strip())
        if self.settings.sound and severity.at_least(Severity.ALERT):
            self._play_sound()
        return sent

    def _play_sound(self) -> None:
        if which("canberra-gtk-play"):
            run_command(["canberra-gtk-play", "-i", "bell"], timeout=5)
            return
        for candidate in _SOUND_CANDIDATES:
            if Path(candidate).exists() and which("paplay"):
                run_command(["paplay", candidate], timeout=5)
                return
