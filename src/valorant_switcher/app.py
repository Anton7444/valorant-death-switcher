"""PySide6 desktop application and its background observation loop."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pythoncom
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget,
)

from .capture import CaptureManager
from .logs import LogTailer, discover_log
from .settings import Settings
from .state import Coordinator
from .vision import TemplateDetector
from .windows import EdgeWindow, activate, find_game, find_game_for_restore, is_game_foreground, set_dpi_awareness

EVENT_LOGGER = logging.getLogger("valorant_switcher.events")


class Signals(QObject):
    status = Signal(dict)
    event = Signal(str, bool)
    stopped = Signal()


class Worker:
    def __init__(self, settings: Settings, signals: Signals):
        self.settings = settings
        self.signals = signals
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.actions_enabled = settings.actions_enabled
        self.coordinator = Coordinator(actions_enabled=self.actions_enabled)
        self.capture = CaptureManager()
        self.detector = TemplateDetector(Path(__file__).parent / "templates")
        self.edge = EdgeWindow()
        self.log: LogTailer | None = None
        self.last_status_at = 0.0
        self.last_capture_status = "等待游戏"
        self.last_active_capture_status = "尚未捕获"
        self.last_reason = self.detector.error or "等待画面"
        self.last_game_geometry: tuple | None = None
        self.last_capture_geometry: tuple | None = None
        self.capture_issue_since: float | None = None
        self.capture_issue_reported = False
        self.last_vision_label = ""
        self.last_game_hwnd: int | None = None
        self.first_dead_frame_at: float | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="valorant-observer", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _event(self, message: str, alert: bool = False) -> None:
        EVENT_LOGGER.info(message)
        self.signals.event.emit(message, alert)

    def _status(self, game: str, log: str) -> None:
        now = time.monotonic()
        if now - self.last_status_at < 0.25:
            return
        self.last_status_at = now
        self.signals.status.emit({
            "game": game,
            "log": log,
            "phase": {"unknown": "未知", "shopping": "购买阶段", "combat": "战斗阶段", "ended": "回合结束"}[self.coordinator.phase],
            "capture": self.last_capture_status,
            "vision": {"unknown": "未知", "alive": "存活", "suspected": "疑似死亡", "dead": "已死亡"}[self.coordinator.observation],
            "template": self.detector.error or "已加载真实画面模板",
            "reason": self.last_reason,
            "mode": ("执行切屏" if self.actions_enabled else "只记录") +
                    ("；标准回合已确认" if self.log and self.log.mode == "round_based" else "；未确认标准回合，动作禁用"),
        })

    def _handle_actions(self, actions: list[str], game_hwnd: int | None) -> None:
        for action in actions:
            if action == "open_edge":
                started = time.monotonic()
                ok, message = self.edge.open_or_activate(self.settings.douyin_url)
                elapsed_ms = round((time.monotonic() - started) * 1000)
                focus_ms = self.edge.last_focus_ms
                timing = f"窗口 {focus_ms} ms，总处理 {elapsed_ms} ms" if focus_ms is not None else f"总处理 {elapsed_ms} ms"
                if focus_ms is not None and self.first_dead_frame_at is not None:
                    evidence_ms = round((started - self.first_dead_frame_at) * 1000) + focus_ms
                    timing += f"，首帧死亡证据到窗口 {evidence_ms} ms"
                self._event(f"{message}；{timing}", not ok)
                self.first_dead_frame_at = None
            elif action == "return_game":
                target = find_game_for_restore(game_hwnd or self.last_game_hwnd)
                if self.edge.hwnd:
                    pause_ok, pause_message = self.edge.pause_video()
                    self._event(pause_message, not pause_ok)
                if not target:
                    self._event("购买阶段已开始，但未找到可恢复的游戏窗口；Edge 保持显示", True)
                    continue
                if self.edge.hwnd:
                    self.edge.minimize_for_game()
                if is_game_foreground(target):
                    self._event("游戏已在前台")
                else:
                    ok = activate(target, timeout=3.0)
                    if ok:
                        self._event("已切回游戏")
                    else:
                        restored, restore_message = self.edge.restore_after_failed_game_switch()
                        self._event("购买阶段已开始，但 Windows 未能切回游戏；" + restore_message, True)

    def run(self) -> None:
        com_initialized = False
        try:
            pythoncom.CoInitialize()
            com_initialized = True
            self._run()
        except Exception as exc:
            EVENT_LOGGER.exception("观察线程出错")
            self._event(f"程序错误：{exc}", True)
        finally:
            self.capture.close()
            if self.log:
                self.log.close()
            if com_initialized:
                pythoncom.CoUninitialize()
            self.signals.stopped.emit()

    def _run(self) -> None:
        self._event("程序已启动；" + ("自动切屏已开启" if self.actions_enabled else "仅记录模式"))
        next_log_search = 0.0
        log_status = "查找日志中"
        while not self.stop_event.is_set():
            started = time.monotonic()
            if self.log is None and started >= next_log_search:
                next_log_search = started + 3
                path = discover_log(self.settings.log_path)
                if path:
                    try:
                        self.log = LogTailer(path)
                        self.coordinator.phase = self.log.baseline()
                        if self.log.mode != "round_based":
                            self.coordinator.phase = "unknown"
                        log_status = str(path)
                        self._event(f"已连接日志：{path}；恢复阶段：{self.coordinator.phase}；模式：{self.log.mode}")
                    except OSError as exc:
                        self.log = None
                        log_status = f"日志读取失败：{exc}"
                else:
                    log_status = "未找到 ShooterGame.log；请在设置中选择"
            if self.log:
                try:
                    if not self.log.path.is_file():
                        self.log.close()
                        self.log = None
                        self.coordinator.phase = "unknown"
                        log_status = "日志暂时不可用"
                    else:
                        for event in self.log.poll():
                            if event.kind == "mode":
                                self.coordinator = Coordinator(actions_enabled=self.actions_enabled)
                                self._event("检测到标准回合模式" if event.mode == "round_based" else "当前模式无购买阶段保障；已禁用切屏")
                                continue
                            if self.log.mode == "round_based":
                                actions = self.coordinator.on_phase(event.kind)
                                self._event({"shopping": "购买阶段开始", "combat": "战斗阶段开始", "ended": "回合结束"}[event.kind])
                                self._handle_actions(actions, None)
                            else:
                                self.coordinator.phase = "unknown"
                except OSError as exc:
                    log_status = f"日志读取失败：{exc}"
                    self.coordinator.phase = "unknown"
                    self.log.close()
                    self.log = None
            if self.log and self.log.mode == "round_based" and self.coordinator.phase == "shopping" and not self.edge.prewarm_attempted:
                if self.edge.prewarm():
                    self._event("Edge 已在后台预热")
            game = find_game()
            game_status = "未找到游戏窗口"
            if game:
                self.last_game_hwnd = game.hwnd
                game_status = f"已找到：{game.monitor_name} {game.rect[2]-game.rect[0]}×{game.rect[3]-game.rect[1]}"
                geometry = (game.monitor_name, game.monitor_rect, game.rect)
                if geometry != self.last_game_geometry:
                    self.last_game_geometry = geometry
                    self._event(f"游戏窗口区域：{game_status}；显示器范围 {game.monitor_rect}")
            if game and self.log and self.log.mode == "round_based" and self.coordinator.phase == "combat" and is_game_foreground(game.hwnd):
                captured = self.capture.grab(game)
                self.last_capture_status = f"{captured.backend}：{captured.status}"
                self.last_active_capture_status = self.last_capture_status
                if captured.frame is not None:
                    self.capture_issue_since = None
                    if self.capture_issue_reported:
                        self._event("游戏画面捕获已恢复")
                        self.capture_issue_reported = False
                    frame_geometry = (captured.backend, captured.frame.shape[1], captured.frame.shape[0])
                    if frame_geometry != self.last_capture_geometry:
                        self.last_capture_geometry = frame_geometry
                        self._event(f"捕获画面尺寸：{frame_geometry[1]}×{frame_geometry[2]}；后端 {frame_geometry[0]}")
                    result = self.detector.classify(captured.frame)
                    if result.label == "dead":
                        self.first_dead_frame_at = self.first_dead_frame_at or time.monotonic()
                    else:
                        self.first_dead_frame_at = None
                    score_text = "、".join(f"{name}={score:.2f}" for name, score in result.scores.items())
                    self.last_reason = f"{result.reason}；{score_text}"
                    if result.label != self.last_vision_label:
                        self.last_vision_label = result.label
                        EVENT_LOGGER.info("识别状态=%s；原因=%s；模板分数=%s", result.label, result.reason, result.scores)
                    actions = self.coordinator.on_frame(result.label, game_foreground=True)
                    if self.coordinator.observation == "dead" and self.coordinator.death_sent and self.coordinator.dead_streak == self.coordinator.min_dead_frames:
                        self._event("画面确认本人死亡" + ("；正在切到 Edge" if self.actions_enabled else "；只记录"))
                    self._handle_actions(actions, game.hwnd)
                else:
                    self.capture_issue_since = self.capture_issue_since or time.monotonic()
                    if not self.capture_issue_reported and time.monotonic() - self.capture_issue_since >= 2:
                        self._event(f"游戏画面捕获暂停：{self.last_capture_status}")
                        self.capture_issue_reported = True
                    self.coordinator.on_frame("unknown", game_foreground=False)
                    self.first_dead_frame_at = None
                    self.last_reason = captured.status
            else:
                self.coordinator.on_frame("unknown", game_foreground=False)
                self.first_dead_frame_at = None
                self.capture.close()
                self.capture_issue_since = None
                self.capture_issue_reported = False
                self.last_capture_status = f"等待游戏处于前台战斗阶段；上次：{self.last_active_capture_status}"
            self._status(game_status, log_status)
            self.stop_event.wait(max(0.0, 0.125 - (time.monotonic() - started)))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.signals = Signals()
        self.worker: Worker | None = None
        self.setWindowTitle("无畏契约死亡自动摸鱼")
        self.resize(780, 720)
        self.setMinimumSize(670, 590)
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #0c1220; color: #e8eefb; }
            QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; }
            QLabel#title { color: #f7f9ff; font-size: 23px; font-weight: 700; }
            QLabel#fieldName { color: #f7f9ff; background: #1c2a40;
                               border-left: 3px solid #7295f3; border-radius: 4px;
                               padding: 6px 10px; font-size: 15px; font-weight: 700; }
            QLabel#section { color: #8eacdf; font-size: 14px; font-weight: 700; }
            QLabel#status { color: #e8eefb; background: #172338; border: 1px solid #293a56;
                            border-radius: 8px; padding: 7px 11px; }
            QLabel#notice { color: #a9d5ff; background: #1b2940; border: 1px solid #315271;
                            border-radius: 8px; padding: 8px 12px; }
            QLabel#notice[alert="true"] { color: #ffd3c8; background: #392326; border-color: #875147; }
            QLineEdit { background: #111b2d; color: #f2f6ff; border: 1px solid #35455d;
                        border-radius: 8px; padding: 9px 11px; selection-background-color: #5479df; }
            QLineEdit:focus { border-color: #67a7f4; }
            QLineEdit[invalid="true"] { border-color: #e08076; }
            QLineEdit:disabled { color: #91a0ba; background: #162033; }
            QPushButton { background: #263650; color: #e8eefb; border: 1px solid #3a4e6c;
                          border-radius: 8px; padding: 9px 16px; font-weight: 600; }
            QPushButton:hover { background: #324b70; }
            QPushButton:disabled { color: #8793a9; background: #233047; }
            QPushButton#runButton { background: #587ce4; color: white; border-color: #7295f3; min-width: 100px; }
            QPushButton#runButton:hover { background: #6d90ee; }
            QCheckBox { color: #d5e0f2; spacing: 9px; }
            QPlainTextEdit { background: #0c1524; color: #d3e1f6; border: 1px solid #29364e;
                             border-radius: 9px; padding: 9px; font-family: 'Consolas', 'Microsoft YaHei UI';
                             font-size: 12px; }
        """)

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(11)
        title = QLabel("无畏契约死亡自动摸鱼")
        title.setObjectName("title")
        layout.addWidget(title)

        self.overview = QLabel("●  待运行")
        self.overview.setStyleSheet("color: #a9bad4; font-weight: 600;")
        layout.addWidget(self.overview)

        section = QLabel("连接设置")
        section.setObjectName("section")
        layout.addWidget(section)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        self.url = QLineEdit(self.settings.douyin_url)
        self.url.textChanged.connect(self._clear_url_error)
        url_label = QLabel("抖音网址")
        url_label.setObjectName("fieldName")
        form.addRow(url_label, self.url)
        log_row = QHBoxLayout()
        self.log_path = QLineEdit(self.settings.log_path)
        self.log_path.setPlaceholderText("自动查找国服 ShooterGame.log")
        browse = QPushButton("选择文件")
        browse.clicked.connect(self.browse_log)
        log_row.addWidget(self.log_path)
        log_row.addWidget(browse)
        log_label = QLabel("日志路径")
        log_label.setObjectName("fieldName")
        form.addRow(log_label, log_row)
        layout.addLayout(form)

        controls = QHBoxLayout()
        self.run_button = QPushButton("开始运行")
        self.run_button.setObjectName("runButton")
        self.run_button.clicked.connect(self.toggle)
        self.action_checkbox = QCheckBox("自动切屏")
        self.action_checkbox.setChecked(self.settings.actions_enabled)
        if TemplateDetector(Path(__file__).parent / "templates").error:
            self.action_checkbox.setChecked(False)
            self.action_checkbox.setEnabled(False)
            self.action_checkbox.setToolTip("缺少真实画面模板，当前仅可使用只记录模式")
        self.action_checkbox.toggled.connect(self.set_actions)
        controls.addWidget(self.run_button)
        controls.addWidget(self.action_checkbox)
        controls.addStretch(1)
        layout.addLayout(controls)

        section = QLabel("实时状态")
        section.setObjectName("section")
        layout.addWidget(section)

        self.status_labels: dict[str, QLabel] = {}
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(5)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        for index, (key, title) in enumerate((
            ("game", "游戏"), ("log", "日志"), ("phase", "回合"),
            ("capture", "捕获"), ("vision", "识别"), ("template", "画面模板"),
            ("reason", "判断原因"), ("mode", "模式"),
        )):
            line = QLabel(f"{title}：等待启动")
            line.setObjectName("status")
            line.setWordWrap(True)
            line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.status_labels[key] = line
            status_grid.addWidget(line, index // 2, index % 2)
        layout.addLayout(status_grid)
        section = QLabel("事件记录")
        section.setObjectName("section")
        layout.addWidget(section)
        self.notice = QLabel("暂无事件")
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setPlaceholderText("运行后将在此显示事件")
        layout.addWidget(self.events, 1)
        self.setCentralWidget(root)

        self.signals.status.connect(self.update_status)
        self.signals.event.connect(self.add_event)
        self.signals.stopped.connect(self.stopped)

    def browse_log(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "选择 ShooterGame.log", str(Path.home()), "日志文件 (*.log)")
        if name:
            self.log_path.setText(name)

    def _clear_url_error(self) -> None:
        if self.url.property("invalid"):
            self.url.setProperty("invalid", False)
            self.url.style().unpolish(self.url)
            self.url.style().polish(self.url)

    def _save(self) -> bool:
        url = self.url.text().strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.url.setProperty("invalid", True)
            self.url.style().unpolish(self.url)
            self.url.style().polish(self.url)
            self.add_event("网址无效：请填写完整的 HTTP 或 HTTPS 网址", True)
            self.url.setFocus()
            return False
        self.settings.douyin_url = url
        self.settings.log_path = self.log_path.text().strip()
        self.settings.actions_enabled = self.action_checkbox.isChecked()
        self.settings.save()
        return True

    def set_actions(self, enabled: bool) -> None:
        if self.worker:
            self.worker.actions_enabled = enabled
            self.worker.coordinator.actions_enabled = enabled
            self.add_event("已启用切屏动作" if enabled else "已切到只记录模式", False)
        self.settings.actions_enabled = enabled
        self.settings.save()

    def toggle(self) -> None:
        if self.worker:
            self.worker.stop()
            self.run_button.setEnabled(False)
            return
        if not self._save():
            return
        self.worker = Worker(self.settings, self.signals)
        self.worker.start()
        self.run_button.setText("停止运行")
        self.overview.setText("●  正在观察")
        self.overview.setStyleSheet("color: #72dbb9; font-weight: 600;")
        self.url.setEnabled(False)
        self.log_path.setEnabled(False)

    def stopped(self) -> None:
        self.worker = None
        self.run_button.setText("开始运行")
        self.run_button.setEnabled(True)
        self.overview.setText("●  已停止")
        self.overview.setStyleSheet("color: #a9bad4; font-weight: 600;")
        self.url.setEnabled(True)
        self.log_path.setEnabled(True)
        self.add_event("程序已停止", False)

    def update_status(self, state: dict) -> None:
        titles = {"game": "游戏", "log": "日志", "phase": "回合", "capture": "捕获", "vision": "识别", "template": "画面模板", "reason": "判断原因", "mode": "模式"}
        for key, value in state.items():
            self.status_labels[key].setText(f"{titles[key]}：{value}")

    def add_event(self, message: str, alert: bool) -> None:
        self.events.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")
        self.notice.setText(("需要注意：" if alert else "最近事件：") + message)
        self.notice.setProperty("alert", alert)
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)

    def closeEvent(self, event) -> None:
        if self.worker:
            self.worker.stop()
            if self.worker.thread:
                self.worker.thread.join(timeout=2)
        super().closeEvent(event)


def main() -> int:
    set_dpi_awareness()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ValorantDeathSwitcher"
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(data_dir / "events.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    EVENT_LOGGER.setLevel(logging.INFO)
    EVENT_LOGGER.addHandler(handler)
    EVENT_LOGGER.propagate = False
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
