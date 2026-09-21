import json

import cv2
import numpy as np

from valorant_switcher.capture import valid_frame
from valorant_switcher.vision import TemplateDetector, content_bounds


def test_black_or_flat_capture_rejected():
    assert not valid_frame(np.zeros((400, 600, 3), dtype=np.uint8))
    assert not valid_frame(np.full((400, 600, 3), 50, dtype=np.uint8))
    image = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(image, (40, 40), (400, 250), (220, 110, 40), -1)
    assert valid_frame(image)


def test_missing_templates_fail_closed(tmp_path):
    detector = TemplateDetector(tmp_path)
    result = detector.classify(np.ones((480, 640, 3), dtype=np.uint8))
    assert result.label == "unknown"


def test_letterbox_bounds_and_conflicting_evidence(tmp_path):
    # An artificial distinctive pattern tests scaling, aspect ratio and the
    # rule that conflicting HUD/death evidence is never a confirmed death.
    rng = np.random.default_rng(42)
    alive = rng.integers(20, 240, (40, 80), dtype=np.uint8)
    dead = rng.integers(20, 240, (40, 80), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "alive.png"), alive)
    cv2.imwrite(str(tmp_path / "dead.png"), dead)
    (tmp_path / "templates.json").write_text(json.dumps({"templates": [
        {"name": "alive", "file": "alive.png", "region": [0, 0, 1, 1], "threshold": 0.9, "reference_width": 640},
        {"name": "dead", "file": "dead.png", "region": [0, 0, 1, 1], "threshold": 0.9, "reference_width": 640},
    ]}), encoding="utf-8")
    detector = TemplateDetector(tmp_path)
    frame = np.full((480, 640, 3), 100, dtype=np.uint8)
    frame[380:420, 30:110] = cv2.cvtColor(alive, cv2.COLOR_GRAY2BGR)
    frame[60:100, 240:320] = cv2.cvtColor(dead, cv2.COLOR_GRAY2BGR)
    assert detector.classify(frame).label == "unknown"
    frame[380:420, 30:110] = 100
    assert detector.classify(frame).label == "dead"
    letterboxed = np.zeros((600, 640, 3), dtype=np.uint8)
    letterboxed[60:540] = frame
    assert content_bounds(letterboxed)[1] == 60
    assert detector.classify(letterboxed).label == "dead"
