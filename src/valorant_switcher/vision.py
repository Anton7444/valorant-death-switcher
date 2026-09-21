"""Template-based HUD classifier with explicit positive death evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np


Label = Literal["alive", "dead", "unknown"]


@dataclass(frozen=True)
class VisionResult:
    label: Label
    reason: str
    scores: dict[str, float]


@dataclass(frozen=True)
class Template:
    name: str
    image: np.ndarray
    region: tuple[float, float, float, float]
    threshold: float
    reference_width: int
    reference_height: int | None = None


def content_bounds(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Ignore genuine flat-black letterbox bars without clipping dark scenes."""
    height, width = frame.shape[:2]
    # cvtColor runs in native code; a full-frame NumPy RGB reduction costs
    # most of the 125 ms/frame observation budget at 2560×1440.
    near_black = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) < 4
    rows = np.mean(near_black, axis=1) < 0.985
    cols = np.mean(near_black, axis=0) < 0.985
    if not np.any(rows) or not np.any(cols):
        return 0, 0, width, height
    top, bottom = np.flatnonzero(rows)[[0, -1]]
    left, right = np.flatnonzero(cols)[[0, -1]]
    if right - left < width * 0.55 or bottom - top < height * 0.55:
        return 0, 0, width, height
    return int(left), int(top), int(right + 1), int(bottom + 1)


class TemplateDetector:
    """A missing or ambiguous template pack always produces UNKNOWN."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.templates: dict[str, Template] = {}
        self.error = "缺少已验证画面模板；请先提供存活、死亡、观战截图"
        self.reload()

    def reload(self) -> None:
        self.templates.clear()
        manifest = self.directory / "templates.json"
        if not manifest.is_file():
            return
        try:
            config = json.loads(manifest.read_text(encoding="utf-8"))
            for item in config["templates"]:
                name = item["name"]
                if name not in {"alive", "dead", "spectating", "scoreboard"}:
                    raise ValueError(f"未知模板名称：{name}")
                image_path = self.directory / item["file"]
                image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if image is None or min(image.shape) < 8:
                    raise ValueError(f"模板无法读取：{image_path}")
                region = tuple(float(x) for x in item["region"])
                if len(region) != 4 or any(not 0 <= x <= 1 for x in region):
                    raise ValueError(f"搜索区域无效：{name}")
                self.templates[name] = Template(
                    name, image, region, float(item.get("threshold", 0.83)),
                    int(item["reference_width"]),
                    int(item["reference_height"]) if item.get("reference_height") else None,
                )
            if "alive" not in self.templates or not ({"dead", "spectating"} & self.templates.keys()):
                raise ValueError("模板包必须包含存活和至少一种死亡正面特征")
            self.error = ""
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.templates.clear()
            self.error = f"画面模板错误：{exc}"

    @staticmethod
    def _score(gray: np.ndarray, spec: Template) -> float:
        height, width = gray.shape
        x1, y1, x2, y2 = spec.region
        roi = gray[int(y1 * height):int(y2 * height), int(x1 * width):int(x2 * width)]
        if roi.size == 0:
            return 0.0
        width_scale = width / spec.reference_width
        height_scale = height / spec.reference_height if spec.reference_height else width_scale
        best = 0.0
        sizes: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        # Width/height can scale independently in a stretched 4:3 mode.
        for sx, sy in ((width_scale, height_scale), (height_scale, height_scale), (width_scale, width_scale)):
            for factor in (1.0, 0.9, 1.1, 0.8, 1.2):
                size = (round(spec.image.shape[1] * sx * factor),
                        round(spec.image.shape[0] * sy * factor))
                if size not in seen:
                    seen.add(size)
                    sizes.append(size)
        for target_width, target_height in sizes:
            if min(target_width, target_height) < 8 or target_width > roi.shape[1] or target_height > roi.shape[0]:
                continue
            scaled = cv2.resize(spec.image, (target_width, target_height), interpolation=cv2.INTER_AREA)
            if np.std(scaled) < 5:
                continue
            score = cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED).max()
            best = max(best, float(score))
            if best >= max(0.97, spec.threshold):
                break
        return best

    def classify(self, frame: np.ndarray) -> VisionResult:
        if not self.templates:
            return VisionResult("unknown", self.error, {})
        if frame is None or frame.ndim != 3 or frame.size == 0:
            return VisionResult("unknown", "画面无效", {})
        left, top, right, bottom = content_bounds(frame)
        active = frame[top:bottom, left:right]
        gray = cv2.cvtColor(active, cv2.COLOR_BGR2GRAY)
        scores = {name: self._score(gray, spec) for name, spec in self.templates.items()}
        visible = {name for name, score in scores.items() if score >= self.templates[name].threshold}
        if "scoreboard" in visible:
            return VisionResult("unknown", "计分板遮挡", scores)
        alive = "alive" in visible
        report = "dead" in visible
        spectating = "spectating" in visible
        if spectating:
            return VisionResult("dead", "观战切换提示可见", scores)
        if alive and not report:
            return VisionResult("alive", "本人血量 HUD 可见", scores)
        if report and not alive:
            return VisionResult("dead", "战斗记录可见，且本人血量 HUD 不可见", scores)
        return VisionResult("unknown", "证据不足或相互冲突", scores)
