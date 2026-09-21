from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return base / "ValorantDeathSwitcher" / "settings.json"


@dataclass
class Settings:
    douyin_url: str = "https://www.douyin.com/"
    log_path: str = ""
    actions_enabled: bool = False

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(settings_path().read_text(encoding="utf-8"))
            return cls(**{key: raw[key] for key in cls.__dataclass_fields__ if key in raw})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
