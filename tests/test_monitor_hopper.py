from __future__ import annotations

import itertools
import threading

from aethernet.core.monitor.hopper import ChannelHopper
from aethernet.utils import CommandResult


class _Runner:
    def __init__(self, ok: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.ok = ok

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(argv)
        return CommandResult(argv, 0 if self.ok else 1, "", "", 0.0)


def test_sequence_cycles():
    hopper = ChannelHopper("aemon0", [1, 6, 11], dwell_ms=10)
    seq = list(itertools.islice(hopper.sequence(), 5))
    assert seq == [1, 6, 11, 1, 6]


def test_hop_runs_iw_command():
    runner = _Runner()
    hopper = ChannelHopper("aemon0", [1, 6], dwell_ms=10, executor=runner)
    assert hopper.hop(6) is True
    assert runner.calls == [["iw", "dev", "aemon0", "set", "channel", "6"]]


def test_hop_reports_failure():
    runner = _Runner(ok=False)
    hopper = ChannelHopper("aemon0", [1], dwell_ms=10, executor=runner)
    assert hopper.hop(1) is False


def test_run_publishes_current_channel_and_stops():
    runner = _Runner()
    hopper = ChannelHopper("aemon0", [1, 6], dwell_ms=5, executor=runner)
    stop = threading.Event()
    current = [0]

    def cancel() -> None:
        # deja circular un par de canales y luego detiene
        while len(runner.calls) < 2:
            stop.wait(0.01)
        stop.set()

    thread = threading.Thread(target=cancel)
    thread.start()
    hopper.run(stop, current=current)
    thread.join()
    assert current[0] in (1, 6)
    assert len(runner.calls) >= 2
