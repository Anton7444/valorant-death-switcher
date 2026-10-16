"""The application reports validation and runtime alerts inside its window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from valorant_switcher.app import MainWindow


def test_invalid_url_is_inline_and_alerts_do_not_use_tray():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.windowTitle() == "无畏契约死亡自动摸鱼"
        assert sorted(label.text() for label in window.findChildren(QLabel)
                      if label.objectName() == "fieldName") == ["Threads 网址", "日志路径"]
        assert window.run_button.text() == "开始运行"
        assert window.action_checkbox.text() == "自动切屏"
        window.url.setText("invalid-url")
        assert window._save() is False
        assert window.url.property("invalid") is True
        assert "网址无效" in window.notice.text()
        assert not hasattr(window, "tray")

        window.add_event("捕获暂停", True)
        assert "捕获暂停" in window.notice.text()
        assert "捕获暂停" in window.events.toPlainText()
    finally:
        window.close()
        app.processEvents()
