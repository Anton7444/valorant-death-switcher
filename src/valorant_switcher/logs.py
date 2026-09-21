"""Append-only ShooterGame.log reader. No client API or game-memory access."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

import psutil


Phase = Literal["unknown", "shopping", "combat", "ended"]
MatchMode = Literal["unknown", "round_based", "unsupported"]
_GAMEPLAY = re.compile(
    r"Gameplay started at local time\s+([\d.]+)\s+\(server time\s+([\d.]+)\)", re.I
)
_ROUND_END = re.compile(r"OnRoundEnded for round\s+'(\d+)'", re.I)
_GAME_MODE = re.compile(r"\?game=/Game/GameModes/([^ #\]]+)", re.I)


@dataclass(frozen=True)
class LogEvent:
    kind: Literal["shopping", "combat", "ended", "mode"]
    line: str
    round_index: int | None = None
    mode: MatchMode | None = None


def parse_line(line: str) -> LogEvent | None:
    if "LogMapLoadModel: Update:" in line:
        mode_match = _GAME_MODE.search(line)
        if mode_match:
            name = mode_match.group(1).lower()
            supported = (name.startswith("bomb/bombgamemode.") or "swiftplay_eorcredits_gamemode." in name)
            return LogEvent("mode", line, mode="round_based" if supported else "unsupported")
    match = _GAMEPLAY.search(line)
    if match:
        local_time, server_time = map(float, match.groups())
        if server_time == 0 and local_time < 2:
            return LogEvent("shopping", line)
        if server_time >= 10 and local_time >= 10:
            return LogEvent("combat", line)
    match = _ROUND_END.search(line)
    if match:
        return LogEvent("ended", line, int(match.group(1)))
    return None


def discover_log(configured: str = "") -> Path | None:
    """Find a known install layout; a user-selected path remains the fallback."""
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    env = os.environ.get("VALORANT_LOG_PATH")
    if env and Path(env).is_file():
        return Path(env)
    for process in psutil.process_iter():
        try:
            if process.name().lower() != "valorant-win64-shipping.exe":
                continue
            exe = process.exe()
            if exe:
                for parent in Path(exe).parents:
                    if parent.name.lower() == "shootergame":
                        candidate = parent / "Saved/Logs/ShooterGame.log"
                        if candidate.is_file():
                            return candidate
        except (psutil.Error, OSError):
            continue
    suffix = Path("Tencent Games/VALORANT/live/ShooterGame/Saved/Logs/ShooterGame.log")
    candidates: list[Path] = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        candidates.extend((root / suffix, root / "无畏契约" / suffix))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "VALORANT/Saved/Logs/ShooterGame.log")
    present = [p for p in candidates if p.is_file()]
    return max(present, key=lambda p: p.stat().st_mtime) if present else None


class LogTailer:
    """Reads complete new lines; handles replacement and truncation."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None
        self._identity: tuple[int, int] | None = None
        self._pending = b""
        self.phase: Phase = "unknown"
        self.mode: MatchMode = "unknown"

    def _open(self) -> None:
        if self._handle:
            self._handle.close()
        self._handle = self.path.open("rb")
        stat = self.path.stat()
        self._identity = (stat.st_dev, stat.st_ino)
        self._pending = b""

    def baseline(self) -> Phase:
        """Restore state without emitting historical actions."""
        self._open()
        for raw in self._handle:
            event = parse_line(raw.decode("utf-8", errors="replace"))
            if event:
                if event.kind == "mode":
                    self.mode = event.mode or "unknown"
                else:
                    self.phase = event.kind
        self._pending = b""
        return self.phase

    def poll(self) -> list[LogEvent]:
        if not self.path.is_file():
            self.close()
            self.phase = "unknown"
            return []
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self._handle is None:
            self._open()
        elif identity != self._identity or stat.st_size < self._handle.tell():
            # New file starts a new stream. Read its existing bytes, which may
            # already contain the first shopping-phase event.
            self._open()
            self.phase = "unknown"
            self.mode = "unknown"
        data = self._pending + self._handle.read()
        parts = data.split(b"\n")
        self._pending = parts.pop()
        events = []
        for raw in parts:
            event = parse_line(raw.decode("utf-8", errors="replace"))
            if event:
                if event.kind == "mode":
                    self.mode = event.mode or "unknown"
                else:
                    self.phase = event.kind
                events.append(event)
        return events

    def close(self) -> None:
        if self._handle:
            self._handle.close()
        self._handle = None
        self._identity = None
        self._pending = b""
