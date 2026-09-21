"""Pure event coordinator. Window side effects are requested as actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Phase = Literal["unknown", "shopping", "combat", "ended"]
Observation = Literal["alive", "suspected", "dead", "unknown"]
Action = Literal["open_edge", "return_game"]


@dataclass
class Coordinator:
    phase: Phase = "unknown"
    observation: Observation = "unknown"
    death_sent: bool = False
    awaiting_return: bool = False
    dead_streak: int = 0
    alive_streak: int = 0
    min_dead_frames: int = 2
    actions_enabled: bool = False

    def on_phase(self, phase: Phase) -> list[Action]:
        actions: list[Action] = []
        if phase == "shopping":
            if self.awaiting_return and self.actions_enabled:
                actions.append("return_game")
            self.awaiting_return = False
            self.death_sent = False
            self.dead_streak = 0
            self.alive_streak = 0
            self.observation = "unknown"
        elif phase != "combat":
            self.dead_streak = 0
            self.alive_streak = 0
            self.observation = "unknown"
        self.phase = phase
        return actions

    def on_frame(self, observed: Observation, *, game_foreground: bool) -> list[Action]:
        if self.phase != "combat" or not game_foreground:
            self.dead_streak = 0
            self.observation = "unknown"
            return []
        if observed == "alive":
            self.alive_streak += 1
            self.dead_streak = 0
            self.observation = "alive"
            return []
        if observed == "dead" and self.alive_streak > 0:
            self.dead_streak += 1
            self.observation = "suspected"
            if self.dead_streak >= self.min_dead_frames:
                self.observation = "dead"
                if not self.death_sent:
                    self.death_sent = True
                    if self.actions_enabled:
                        self.awaiting_return = True
                        return ["open_edge"]
            return []
        self.dead_streak = 0
        self.observation = "unknown" if observed == "unknown" else "suspected"
        return []
