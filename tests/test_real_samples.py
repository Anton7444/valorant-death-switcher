"""Opt-in replay of the user's original full-screen screenshots.

The private source images are kept in local-data and omitted from distribution.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from valorant_switcher.vision import TemplateDetector
from valorant_switcher.state import Coordinator


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "local-data" / "samples"
TEMPLATES = ROOT / "src" / "valorant_switcher" / "templates"


def read_sample(name: str) -> np.ndarray:
    path = SAMPLES / f"{name}.png"
    if not path.is_file():
        pytest.skip(f"本机未提供 {path.name}")
    frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None
    return frame


@pytest.mark.parametrize("name,expected", [
    ("alive", "alive"),
    ("dead", "dead"),
    ("spectating", "dead"),
])
def test_labeled_full_resolution_samples(name: str, expected: str) -> None:
    detector = TemplateDetector(TEMPLATES)
    assert not detector.error
    result = detector.classify(read_sample(name))
    assert result.label == expected, result


@pytest.mark.parametrize("name,expected", [
    ("alive", "alive"),
    ("dead", "dead"),
    ("spectating", "dead"),
])
def test_uniform_1080p_resize(name: str, expected: str) -> None:
    frame = cv2.resize(read_sample(name), (1920, 1080), interpolation=cv2.INTER_AREA)
    result = TemplateDetector(TEMPLATES).classify(frame)
    assert result.label == expected, result


def test_letterbox_resize_preserves_death_evidence() -> None:
    frame = cv2.resize(read_sample("dead"), (1600, 900), interpolation=cv2.INTER_AREA)
    padded = np.zeros((1200, 1600, 3), dtype=np.uint8)
    padded[150:1050] = frame
    result = TemplateDetector(TEMPLATES).classify(padded)
    assert result.label == "dead", result


@pytest.mark.parametrize("name,expected", [
    ("alive", "alive"),
    ("dead", "dead"),
    ("spectating", "dead"),
])
def test_synthetic_4_by_3_stretch(name: str, expected: str) -> None:
    # This verifies the matcher math, not real game HUD placement in 4:3.
    frame = cv2.resize(read_sample(name), (1920, 1440), interpolation=cv2.INTER_AREA)
    result = TemplateDetector(TEMPLATES).classify(frame)
    assert result.label == expected, result


@pytest.mark.parametrize("name,expected", [
    ("alive", "alive"),
    ("dead", "dead"),
    ("spectating", "dead"),
    ("scoreboard", "unknown"),
])
def test_synthetic_1568_by_1080_fullscreen(name: str, expected: str) -> None:
    # The user's new resolution is 1568×1080. This tests resampling and
    # letterbox handling, but real HUD positions still require fresh images.
    resized = cv2.resize(read_sample(name), (1568, 1080), interpolation=cv2.INTER_AREA)
    padded = np.zeros((1080, 1920, 3), dtype=np.uint8)
    padded[:, 176:1744] = resized
    detector = TemplateDetector(TEMPLATES)
    assert detector.classify(resized).label == expected
    assert detector.classify(padded).label == expected


def test_scoreboard_is_not_death_when_sample_available() -> None:
    path = SAMPLES / "scoreboard.png"
    if not path.is_file():
        pytest.skip("等待计分板原始截图")
    result = TemplateDetector(TEMPLATES).classify(read_sample("scoreboard"))
    assert result.label != "dead", result


def test_scoreboard_gate_survives_missing_health_hud() -> None:
    frame = read_sample("scoreboard").copy()
    frame[1320:1415, 870:1010] = 0
    result = TemplateDetector(TEMPLATES).classify(frame)
    assert result.label == "unknown", result
    assert result.scores["scoreboard"] >= 0.83


def test_labeled_frames_drive_one_death_and_next_round_return() -> None:
    detector = TemplateDetector(TEMPLATES)
    states = {name: detector.classify(read_sample(name)).label
              for name in ("alive", "scoreboard", "dead", "spectating")}
    flow = Coordinator(actions_enabled=True)
    assert flow.on_phase("combat") == []
    assert flow.on_frame(states["alive"], game_foreground=True) == []
    assert flow.on_frame(states["scoreboard"], game_foreground=True) == []
    assert flow.on_frame(states["dead"], game_foreground=True) == []
    assert flow.on_frame(states["dead"], game_foreground=True) == ["open_edge"]
    assert flow.on_frame(states["dead"], game_foreground=True) == []
    assert flow.on_frame(states["spectating"], game_foreground=True) == []
    assert flow.on_phase("shopping") == ["return_game"]
    assert flow.on_phase("shopping") == []
