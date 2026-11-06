from __future__ import annotations

from .clock_control import NativeClock
from .general_speed import GeneralSpeedWorker


class IndependentBattleSpeedWorker(GeneralSpeedWorker):
    """Use the existing battle clock with ownership separate from Start/Stop bot."""

    mode = "battle"
    title = "Speed en combate independiente"

    def __init__(self, session, window, rate: float):
        super().__init__(session, window, rate)
        self.report["independent"] = True

    def _make_clock(self, signal):
        return NativeClock(self.session, self.window, signal, self.rate)
