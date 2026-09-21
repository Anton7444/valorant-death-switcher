import sys

if "--self-test" in sys.argv:
    # Qt must initialize before the WinRT projection on this Windows runtime.
    from PySide6 import QtWidgets

    import cv2
    import dxcam
    import numpy
    import win32gui
    import winrt.windows.graphics.capture
    from pathlib import Path
    from valorant_switcher.vision import TemplateDetector

    detector = TemplateDetector(Path(__file__).parent / "src" / "valorant_switcher" / "templates")
    if detector.error:
        # In a PyInstaller build __file__ points into _internal; templates are
        # bundled with the imported package instead of beside this launcher.
        import valorant_switcher
        detector = TemplateDetector(Path(valorant_switcher.__file__).parent / "templates")
    if detector.error:
        raise RuntimeError(detector.error)

    raise SystemExit(0)

try:
    from valorant_switcher.app import main

    raise SystemExit(main())
except Exception:
    # A windowed PyInstaller build has no console. Keep startup failures in a
    # local diagnostic file instead of showing its native traceback dialog.
    import os
    import traceback
    from pathlib import Path

    crash_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ValorantDeathSwitcher"
    crash_dir.mkdir(parents=True, exist_ok=True)
    with (crash_dir / "crash.log").open("a", encoding="utf-8") as crash_file:
        crash_file.write(traceback.format_exc())
    raise SystemExit(1)
