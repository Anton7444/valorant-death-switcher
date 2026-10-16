from types import SimpleNamespace
from pathlib import Path

import pywintypes

from valorant_switcher import windows
from valorant_switcher.app import Worker
from valorant_switcher.settings import Settings


def test_set_foreground_refusal_returns_false_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "IsIconic", lambda _hwnd: False)
    monkeypatch.setattr(windows.win32gui, "GetForegroundWindow", lambda: 0)

    def refuse(_hwnd):
        raise pywintypes.error(0, "SetForegroundWindow", "No error message is available")

    monkeypatch.setattr(windows.win32gui, "SetForegroundWindow", refuse)
    assert windows.activate(123, timeout=0) is False


def test_foreground_error_does_not_hide_successful_activation(monkeypatch):
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "IsIconic", lambda _hwnd: False)
    monkeypatch.setattr(windows.win32gui, "GetForegroundWindow", lambda: 123)
    monkeypatch.setattr(
        windows.win32gui,
        "SetForegroundWindow",
        lambda _hwnd: (_ for _ in ()).throw(pywintypes.error(0, "SetForegroundWindow", "No error message is available")),
    )
    assert windows.activate(123, timeout=0) is True


def test_foreground_refusal_is_reported_without_stopping_observer(monkeypatch):
    messages = []
    signals = SimpleNamespace(event=SimpleNamespace(emit=lambda message, alert: messages.append((message, alert))))
    worker = Worker(Settings(actions_enabled=True), signals)
    monkeypatch.setattr(worker.edge, "open_or_activate", lambda _url: (False, "Windows 拒绝激活 Edge 窗口"))
    worker._handle_actions(["open_edge"], None)
    assert len(messages) == 1
    assert messages[0][1]
    assert "Windows 拒绝激活" in messages[0][0]


def test_first_edge_launch_uses_controllable_maximized_window(monkeypatch, tmp_path):
    launched = []
    maximized = []
    monkeypatch.setattr(windows, "find_edge_exe", lambda: Path(r"C:\Edge\msedge.exe"))
    monkeypatch.setattr(windows, "visible_windows", lambda _name: [])
    monkeypatch.setattr(windows.subprocess, "Popen", lambda args: launched.append(args) or SimpleNamespace(pid=12))
    monkeypatch.setattr(windows.win32gui, "ShowWindow", lambda hwnd, how: maximized.append((hwnd, how)))
    monkeypatch.setattr(windows, "activate", lambda _hwnd, **_kwargs: True)

    edge = windows.EdgeWindow()
    edge.devtools.profile_dir = tmp_path
    monkeypatch.setattr(edge.devtools, "_read_port", lambda: None)
    monkeypatch.setattr(edge.devtools, "wait_for_port", lambda: True)
    monkeypatch.setattr(edge.devtools, "ensure_page", lambda _url: {"id": "page"})
    monkeypatch.setattr(edge.devtools, "_command", lambda *_args: {})
    monkeypatch.setattr(edge.devtools, "resume_video", lambda _url: (True, ""))
    monkeypatch.setattr(edge, "_find_own_window", lambda _before: 456)
    ok, _message = edge.open_or_activate("https://www.threads.com/")
    assert ok
    assert edge.hwnd == 456
    assert launched[0][0] == r"C:\Edge\msedge.exe"
    assert f"--user-data-dir={tmp_path}" in launched[0]
    assert "--remote-debugging-port=0" in launched[0]
    assert launched[0][-1] == "https://www.threads.com/"
    assert maximized == [(456, windows.win32con.SW_MAXIMIZE)]


def test_existing_edge_focus_precedes_page_control(monkeypatch):
    order = []
    edge = windows.EdgeWindow()
    edge.hwnd = 456
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "GetForegroundWindow", lambda: 456)
    monkeypatch.setattr(edge, "_owns_window", lambda _hwnd: True)
    monkeypatch.setattr(windows, "find_edge_exe", lambda: Path(r"C:\Edge\msedge.exe"))
    monkeypatch.setattr(windows, "visible_windows", lambda _name: [])
    monkeypatch.setattr(edge, "_focus", lambda **_kwargs: (order.append("focus") or True, "focused"))
    monkeypatch.setattr(edge.devtools, "_read_port", lambda: order.append("port") or 12345)
    monkeypatch.setattr(edge.devtools, "ensure_page", lambda _url: order.append("page") or {"id": "page"})
    monkeypatch.setattr(edge.devtools, "_command", lambda *_args: {})
    monkeypatch.setattr(edge.devtools, "resume_video", lambda _url: (True, ""))
    assert edge.open_or_activate("https://www.threads.com/")[0]
    assert order[:3] == ["focus", "port", "page"]


def test_activation_retries_with_attached_input_and_always_detaches(monkeypatch):
    calls = []
    foreground = [999]
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "IsIconic", lambda _hwnd: False)
    monkeypatch.setattr(windows.win32gui, "GetForegroundWindow", lambda: foreground[0])
    monkeypatch.setattr(windows.win32api, "GetCurrentThreadId", lambda: 10)
    monkeypatch.setattr(windows.win32process, "GetWindowThreadProcessId", lambda _hwnd: (20, 30))
    monkeypatch.setattr(windows.win32process, "AttachThreadInput", lambda a, b, attach: calls.append((a, b, attach)))
    monkeypatch.setattr(windows.win32gui, "BringWindowToTop", lambda hwnd: calls.append(("top", hwnd)))

    def set_foreground(hwnd):
        if not calls:
            raise pywintypes.error(0, "SetForegroundWindow", "Access denied")
        foreground[0] = hwnd

    monkeypatch.setattr(windows.win32gui, "SetForegroundWindow", set_foreground)
    assert windows.activate(123, timeout=0)
    assert calls == [(10, 20, True), ("top", 123), (10, 20, False)]


def test_pause_confirms_page_video_paused(monkeypatch):
    edge = windows.EdgeWindow()
    edge.url = "https://www.threads.com/"
    edge.hwnd = 456
    monkeypatch.setattr(edge.devtools, "_read_port", lambda: 12345)
    monkeypatch.setattr(edge.devtools, "pause_video", lambda _url: (True, "已暂停Threads页面中的 1 个视频"))
    assert edge.pause_video() == (True, "已暂停Threads页面中的 1 个视频")


def test_failed_focus_places_edge_on_top_and_later_clears_it(monkeypatch):
    edge = windows.EdgeWindow()
    edge.hwnd = 456
    calls = []
    monkeypatch.setattr(windows, "activate", lambda _hwnd, **_kwargs: False)
    monkeypatch.setattr(windows.win32gui, "ShowWindow", lambda *_args: None)
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "SetWindowPos", lambda *args: calls.append(args))
    ok, message = edge._focus(opened=False)
    assert not ok
    assert "置顶" in message
    assert calls[0][1] == windows.win32con.HWND_TOPMOST
    edge.release_topmost()
    assert calls[1][1] == windows.win32con.HWND_NOTOPMOST


def test_edge_minimizes_after_topmost_is_removed(monkeypatch):
    edge = windows.EdgeWindow()
    edge.hwnd = 456
    actions = []
    monkeypatch.setattr(edge, "release_topmost", lambda: actions.append("lower"))
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows.win32gui, "ShowWindow", lambda hwnd, how: actions.append((hwnd, how)))
    edge.minimize_for_game()
    assert actions == ["lower", (456, windows.win32con.SW_MINIMIZE)]


def test_return_pauses_edge_before_game_activation(monkeypatch):
    calls = []
    signals = SimpleNamespace(event=SimpleNamespace(emit=lambda *_args: None))
    worker = Worker(Settings(actions_enabled=True), signals)
    worker.edge.hwnd = 456
    monkeypatch.setattr(worker.edge, "pause_video", lambda: (calls.append("pause") or True, "已发送"))
    monkeypatch.setattr(worker.edge, "minimize_for_game", lambda: calls.append("minimize"))
    monkeypatch.setattr("valorant_switcher.app.find_game_for_restore", lambda _hwnd: 123)
    monkeypatch.setattr("valorant_switcher.app.is_game_foreground", lambda _hwnd: False)
    monkeypatch.setattr("valorant_switcher.app.activate", lambda _hwnd, **_kwargs: calls.append("activate") or True)
    worker._handle_actions(["return_game"], 123)
    assert calls == ["pause", "minimize", "activate"]


def test_missing_game_does_not_minimize_edge(monkeypatch):
    calls = []
    messages = []
    signals = SimpleNamespace(event=SimpleNamespace(emit=lambda msg, _alert: messages.append(msg)))
    worker = Worker(Settings(actions_enabled=True), signals)
    worker.edge.hwnd = 456
    monkeypatch.setattr(worker.edge, "pause_video", lambda: (True, "已暂停"))
    monkeypatch.setattr(worker.edge, "minimize_for_game", lambda: calls.append("minimize"))
    monkeypatch.setattr("valorant_switcher.app.find_game_for_restore", lambda _hwnd: None)
    worker._handle_actions(["return_game"], None)
    assert calls == []
    assert any("Edge 保持显示" in message for message in messages)


def test_failed_game_activation_restores_edge(monkeypatch):
    calls = []
    signals = SimpleNamespace(event=SimpleNamespace(emit=lambda *_args: None))
    worker = Worker(Settings(actions_enabled=True), signals)
    worker.edge.hwnd = 456
    monkeypatch.setattr(worker.edge, "pause_video", lambda: (True, "已暂停"))
    monkeypatch.setattr(worker.edge, "minimize_for_game", lambda: calls.append("minimize"))
    monkeypatch.setattr(worker.edge, "restore_after_failed_game_switch", lambda: (calls.append("restore") or True, "Edge 已恢复"))
    monkeypatch.setattr("valorant_switcher.app.find_game_for_restore", lambda _hwnd: 123)
    monkeypatch.setattr("valorant_switcher.app.is_game_foreground", lambda _hwnd: False)
    monkeypatch.setattr("valorant_switcher.app.activate", lambda _hwnd, **_kwargs: calls.append("activate") or False)
    worker._handle_actions(["return_game"], 123)
    assert calls == ["minimize", "activate", "restore"]


def test_minimized_game_is_eligible_for_restore(monkeypatch):
    monkeypatch.setattr(windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(windows, "process_name", lambda _hwnd: windows.GAME_EXE)
    assert windows.find_game_for_restore(123) == 123
