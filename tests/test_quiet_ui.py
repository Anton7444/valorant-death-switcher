"""The application reports validation and runtime alerts inside its window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from valorant_switcher.app import MainWindow


def test_invalid_url_is_inline_and_alerts_do_not_use_tray():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.windowTitle() == "特戰英豪死亡自動摸魚"
        assert sorted(label.text() for label in window.findChildren(QLabel)
                      if label.objectName() == "fieldName") == ["Threads 網址", "日誌路徑"]
        assert window.run_button.text() == "開始執行"
        assert window.action_checkbox.text() == "自動切換視窗"
        window.url.setText("invalid-url")
        assert window._save() is False
        assert window.url.property("invalid") is True
        assert "網址無效" in window.notice.text()
        assert not hasattr(window, "tray")

        window.add_event("捕獲暫停", True)
        assert "捕獲暫停" in window.notice.text()
        assert "捕獲暫停" in window.events.toPlainText()
    finally:
        window.close()
        app.processEvents()
