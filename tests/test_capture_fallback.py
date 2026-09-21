import numpy as np

from valorant_switcher.capture import CaptureManager
from valorant_switcher.windows import GameWindow


WINDOW = GameWindow(1, (0, 0, 800, 600), (0, 0, 800, 600), r"\\.\DISPLAY1")


class FakeCamera:
    def __init__(self):
        self.released = False

    def grab(self, *, region):
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        frame[:, :400] = 200
        return frame

    def release(self):
        self.released = True


def test_winrt_is_tried_when_dxgi_initialization_fails(monkeypatch):
    manager = CaptureManager()
    monkeypatch.setattr(manager, "_output_indices", lambda _: (0, 0))
    calls = []

    def create(*, backend, **_kwargs):
        calls.append(backend)
        if backend == "dxgi":
            raise RuntimeError("DXGI unavailable")
        return FakeCamera()

    monkeypatch.setattr("valorant_switcher.capture.dxcam.create", create)
    result = manager.grab(WINDOW)
    assert calls == ["dxgi", "winrt"]
    assert result.frame is not None
    assert result.backend == "winrt"
    manager.close()


def test_two_initialization_failures_reported_without_retrying_each_frame(monkeypatch):
    manager = CaptureManager()
    monkeypatch.setattr(manager, "_output_indices", lambda _: (0, 0))
    calls = []

    def fail(*, backend, **_kwargs):
        calls.append(backend)
        raise RuntimeError(backend)

    monkeypatch.setattr("valorant_switcher.capture.dxcam.create", fail)
    first = manager.grab(WINDOW)
    second = manager.grab(WINDOW)
    assert first.frame is None and second.frame is None
    assert "DXGI" in first.status and "WinRT" in first.status
    assert calls == ["dxgi", "winrt"]


def test_resolution_change_recreates_capture_even_on_same_monitor(monkeypatch):
    manager = CaptureManager()
    monkeypatch.setattr(manager, "_output_indices", lambda _: (0, 0))
    cameras = []

    def create(**_kwargs):
        camera = FakeCamera()
        cameras.append(camera)
        return camera

    monkeypatch.setattr("valorant_switcher.capture.dxcam.create", create)
    manager.grab(WINDOW)
    resized = GameWindow(1, (0, 0, 1568, 1080), WINDOW.monitor_rect, WINDOW.monitor_name)
    manager.grab(resized)
    assert len(cameras) == 2
    assert cameras[0].released
    manager.close()
