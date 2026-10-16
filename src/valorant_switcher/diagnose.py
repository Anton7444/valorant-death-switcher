"""Read-only checks for log parsing and screenshot-template matching."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from .logs import discover_log, parse_line
from .vision import TemplateDetector


def main() -> int:
    parser = argparse.ArgumentParser(description="特戰英豪切換視窗診斷（只讀，不執行切換視窗）")
    parser.add_argument("--log", help="ShooterGame.log 路徑；省略時自動查詢")
    parser.add_argument("--image", type=Path, help="對一張原始截圖執行目前模板辨識器")
    args = parser.parse_args()
    path = discover_log(args.log or "")
    if path:
        counts: Counter[str] = Counter()
        latest = {}
        mode = "unknown"
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                event = parse_line(line)
                if event:
                    counts[event.kind] += 1
                    if event.kind == "mode":
                        mode = event.mode or "unknown"
                    else:
                        latest[event.kind] = line.strip()
        print(f"日誌：{path}")
        print(f"日誌行數量：server=0 階段候選 {counts['shopping']}，戰鬥階段候選 {counts['combat']}，回合結束 {counts['ended']}")
        print(f"最後檢測的模式：{mode}")
        for kind, line in latest.items():
            print(f"最後一條 {kind}：{line}")
    else:
        print("未找到日誌；可用 --log 指定路徑")
    if args.image:
        frame = cv2.imdecode(np.fromfile(str(args.image), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            print(f"無法讀取截圖：{args.image}")
            return 2
        detector = TemplateDetector(Path(__file__).parent / "templates")
        result = detector.classify(frame)
        print(f"截圖：{args.image}，尺寸 {frame.shape[1]}×{frame.shape[0]}")
        print(f"辨識：{result.label}；原因：{result.reason}；分數：{result.scores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
