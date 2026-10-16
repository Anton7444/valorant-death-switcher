"""Extract UI-only templates from the user's 1920x1080 labeled screenshots (zh-TW international client).

The source screenshots stay in local-data and are never included in the app.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "local-data" / "samples"
OUTPUT = ROOT / "src" / "valorant_switcher" / "templates"

REF_W, REF_H = 1920, 1080

SPECS = {
    # Static white HUD bracket right of the HP number; excludes the number and armor icon.
    "alive": ("alive.png", (645, 1000, 745, 1058), (0.28, 0.9, 0.45, 1.0), 0.65),
    # "你遭到擊殺" under the combat report; excludes killer name, portrait and damage numbers.
    "dead": ("dead.png", (1830, 624, 1897, 644), (0.9, 0.52, 1.0, 0.68), 0.80),
    # "< mouse > 切換玩家" prompt shown while spectating; excludes the spectated player's name.
    "spectating": ("spectating.png", (118, 852, 218, 876), (0.0, 0.72, 0.2, 0.85), 0.80),
    # Scoreboard header strip only; excludes all player rows and names.
    "scoreboard": ("scoreboard.png", (640, 447, 1345, 463), (0.25, 0.38, 0.75, 0.47), 0.80),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "templates": []}
    for name, (source, box, region, threshold) in SPECS.items():
        path = SAMPLES / source
        frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (REF_H, REF_W):
            raise ValueError(f"截圖缺失或不是 1920×1080：{path}")
        x1, y1, x2, y2 = box
        patch = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        result, encoded = cv2.imencode(".png", patch)
        if not result:
            raise RuntimeError(f"無法編碼模板 {name}")
        file_name = f"{name}.png"
        encoded.tofile(str(OUTPUT / file_name))
        manifest["templates"].append({
            "name": name,
            "file": file_name,
            "region": region,
            "threshold": threshold,
            "reference_width": REF_W,
            "reference_height": REF_H,
        })
    (OUTPUT / "templates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(SPECS)} 個不含玩家姓名的 UI 模板：{OUTPUT}")


if __name__ == "__main__":
    main()
