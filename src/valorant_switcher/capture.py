"""DXGI capture with WinRT fallback; fail closed on missing/black/stale frames."""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import dxcam
import numpy as np

from .windows import GameWindow


@dataclass(frozen=True)
class CaptureResult:
    frame: np.ndarray | None
    status: str
    backend: str


def valid_frame(frame: np.ndarray | None) -> bool:
    if frame is None or frame.size == 0 or frame.ndim != 3:
        return False
    sample = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    # Solid black, stale placeholder, minimized output and flat color all fail.
    return bool(np.mean(gray) >= 5 and np.std(gray) >= 7)


class CaptureManager:
    def __init__(self) -> None:
        self.camera = None
        self.backend = "dxgi"
        self.monitor_name = ""
        self.monitor_rect: tuple[int, int, int, int] | None = None
        self.window_rect: tuple[int, int, int, int] | None = None
        self.fail_since: float | None = None
        self.last_signature: np.ndarray | None = None
        self.still_since: float | None = None
        self.last_error = ""
        self.retry_at = 0.0

    def close(self) -> None:
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception:
                pass
        self.camera = None
        self.window_rect = None
        self.last_signature = None
        self.still_since = None
        self.fail_since = None

    def _output_indices(self, monitor_name: str) -> tuple[int, int]:
        # DXcam 0.3 keeps the Windows display device name on each output.
        # Match it explicitly, including when displays use different adapters.
        factory = getattr(dxcam, "__factory", None)
        if factory is not None:
            for device_idx, outputs in enumerate(factory.outputs):
                for output_idx, output in enumerate(outputs):
                    if output.devicename.lower() == monitor_name.lower():
                        return device_idx, output_idx
        raise RuntimeError(f"DXcam 無法匹配遊戲顯示器 {monitor_name}")

    def _make_camera(self, window: GameWindow) -> None:
        self.close()
        self.monitor_name = window.monitor_name
        self.monitor_rect = window.monitor_rect
        self.window_rect = window.rect
        device_idx, output_idx = self._output_indices(window.monitor_name)
        self.camera = dxcam.create(
            device_idx=device_idx,
            output_idx=output_idx,
            backend=self.backend,
            output_color="BGR",
        )

    def _fallback(self, window: GameWindow) -> None:
        self.backend = "winrt" if self.backend == "dxgi" else "dxgi"
        self.fail_since = time.monotonic()
        self._make_camera(window)

    def grab(self, window: GameWindow) -> CaptureResult:
        now = time.monotonic()
        if (self.camera is None or self.monitor_name != window.monitor_name
                or self.monitor_rect != window.monitor_rect or self.window_rect != window.rect):
            if self.camera is None and now < self.retry_at:
                return CaptureResult(None, self.last_error, self.backend)
            self.backend = "dxgi"
            try:
                self._make_camera(window)
            except Exception as dxgi_exc:
                self.backend = "winrt"
                try:
                    self._make_camera(window)
                except Exception as winrt_exc:
                    self.last_error = f"兩個捕獲後端初始化失敗：DXGI {dxgi_exc}；WinRT {winrt_exc}"
                    self.retry_at = now + 3
                    self.fail_since = self.fail_since or now
                    return CaptureResult(None, self.last_error, self.backend)
            self.retry_at = 0.0
        try:
            left, top, right, bottom = window.rect
            ml, mt, mr, mb = window.monitor_rect
            region = (max(ml, left) - ml, max(mt, top) - mt,
                      min(mr, right) - ml, min(mb, bottom) - mt)
            if region[2] - region[0] < 320 or region[3] - region[1] < 240:
                return CaptureResult(None, "遊戲視窗區域無效", self.backend)
            frame = self.camera.grab(region=region)
            if valid_frame(frame):
                signature = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_AREA)
                if self.last_signature is not None and np.array_equal(signature, self.last_signature):
                    self.still_since = self.still_since or now
                    if now - self.still_since > 3:
                        frame = None
                else:
                    self.still_since = None
                self.last_signature = signature
            else:
                frame = None
            if frame is not None:
                self.fail_since = None
                return CaptureResult(frame, "畫面正常", self.backend)
            self.fail_since = self.fail_since or now
            if now - self.fail_since > 2:
                try:
                    self._fallback(window)
                except Exception as exc:
                    self.last_error = str(exc)
                    return CaptureResult(None, f"兩個捕獲後端均不可用：{exc}", self.backend)
            return CaptureResult(None, "無新幀、黑屏或畫面凍結；死亡判斷已暫停", self.backend)
        except Exception as exc:
            self.last_error = str(exc)
            self.fail_since = self.fail_since or now
            if now - self.fail_since > 2:
                try:
                    self._fallback(window)
                except Exception as fallback_exc:
                    self.last_error = str(fallback_exc)
            return CaptureResult(None, f"捕獲失敗：{exc}", self.backend)
