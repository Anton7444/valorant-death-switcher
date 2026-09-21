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
    parser = argparse.ArgumentParser(description="无畏契约切屏诊断（只读，不执行切屏）")
    parser.add_argument("--log", help="ShooterGame.log 路径；省略时自动查找")
    parser.add_argument("--image", type=Path, help="对一张原始截图运行当前模板识别器")
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
        print(f"日志：{path}")
        print(f"日志行数量：server=0 阶段候选 {counts['shopping']}，战斗阶段候选 {counts['combat']}，回合结束 {counts['ended']}")
        print(f"最后检测的模式：{mode}")
        for kind, line in latest.items():
            print(f"最后一条 {kind}：{line}")
    else:
        print("未找到日志；可用 --log 指定路径")
    if args.image:
        frame = cv2.imdecode(np.fromfile(str(args.image), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            print(f"无法读取截图：{args.image}")
            return 2
        detector = TemplateDetector(Path(__file__).parent / "templates")
        result = detector.classify(frame)
        print(f"截图：{args.image}，尺寸 {frame.shape[1]}×{frame.shape[0]}")
        print(f"识别：{result.label}；原因：{result.reason}；分数：{result.scores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
