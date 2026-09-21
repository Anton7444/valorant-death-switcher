"""Extract UI-only templates from the user's 2560x1440 labeled screenshots.

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

SPECS = {
    # Static white HUD bracket; excludes numeric HP and armor icon.
    "alive": ("alive.png", (870, 1320, 1010, 1415), (0.21, 0.85, 0.47, 1.0), 0.82),
    # Fixed combat-report title; excludes player names, portraits and damage.
    "dead": ("dead.png", (2195, 748, 2375, 795), (0.73, 0.42, 1.0, 0.71), 0.83),
    # Fixed spectator prompt text; excludes the spectated player's name.
    "spectating": ("spectating.png", (218, 1138, 435, 1170), (0.0, 0.71, 0.31, 0.91), 0.83),
    # Scoreboard header only; excludes all player rows and names.
    "scoreboard": ("scoreboard.png", (1255, 615, 1530, 655), (0.29, 0.36, 0.73, 0.54), 0.83),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "templates": []}
    for name, (source, box, region, threshold) in SPECS.items():
        path = SAMPLES / source
        frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (1440, 2560):
            raise ValueError(f"截图缺失或不是 2560×1440：{path}")
        x1, y1, x2, y2 = box
        patch = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        result, encoded = cv2.imencode(".png", patch)
        if not result:
            raise RuntimeError(f"无法编码模板 {name}")
        file_name = f"{name}.png"
        encoded.tofile(str(OUTPUT / file_name))
        manifest["templates"].append({
            "name": name,
            "file": file_name,
            "region": region,
            "threshold": threshold,
            "reference_width": 2560,
            "reference_height": 1440,
        })
    (OUTPUT / "templates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(SPECS)} 个不含玩家姓名的 UI 模板：{OUTPUT}")


if __name__ == "__main__":
    main()
