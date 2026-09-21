"""Visible game/Edge window discovery and foreground changes."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import psutil
import pywintypes
import win32api
import win32con
import win32gui
import win32process

from .edge_cdp import DevToolsError, EdgeDevTools


GAME_EXE = "valorant-win64-shipping.exe"


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


def process_name(hwnd: int) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except (psutil.Error, OSError):
        return ""


def visible_windows(process: str) -> list[int]:
    found: list[int] = []

    def visit(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return
        if process_name(hwnd) != process:
            return
        x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
        if x2 - x1 >= 640 and y2 - y1 >= 360:
            found.append(hwnd)

    try:
        win32gui.EnumWindows(visit, None)
    except pywintypes.error:
        return []
    return found


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    rect: tuple[int, int, int, int]
    monitor_rect: tuple[int, int, int, int]
    monitor_name: str


def find_game() -> GameWindow | None:
    windows = visible_windows(GAME_EXE)
    if not windows:
        return None
    foreground = win32gui.GetForegroundWindow()
    hwnd = foreground if foreground in windows else max(
        windows,
        key=lambda w: (win32gui.GetWindowRect(w)[2] - win32gui.GetWindowRect(w)[0])
        * (win32gui.GetWindowRect(w)[3] - win32gui.GetWindowRect(w)[1]),
    )
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    right, bottom = win32gui.GetClientRect(hwnd)[2:]
    rect = (left, top, left + right, top + bottom)
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    info = win32api.GetMonitorInfo(monitor)
    return GameWindow(hwnd, rect, tuple(info["Monitor"]), info["Device"])


def is_game_foreground(hwnd: int) -> bool:
    fg = win32gui.GetForegroundWindow()
    return bool(fg and (fg == hwnd or process_name(fg) == GAME_EXE))


def find_game_for_restore(preferred: int | None = None) -> int | None:
    """Find the game even when exclusive fullscreen has minimized its window."""
    if preferred and win32gui.IsWindow(preferred) and process_name(preferred) == GAME_EXE:
        return preferred
    candidates: list[int] = []

    def visit(hwnd: int, _extra: object) -> None:
        if process_name(hwnd) == GAME_EXE:
            candidates.append(hwnd)

    try:
        win32gui.EnumWindows(visit, None)
    except pywintypes.error:
        return None
    return max(candidates, key=lambda hwnd: (
        (win32gui.GetWindowRect(hwnd)[2] - win32gui.GetWindowRect(hwnd)[0])
        * (win32gui.GetWindowRect(hwnd)[3] - win32gui.GetWindowRect(hwnd)[1])
    ), default=None)


def activate(hwnd: int, *, timeout: float = 1.0) -> bool:
    if not win32gui.IsWindow(hwnd):
        return False
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    was_minimized = win32gui.IsIconic(hwnd)
    try:
        if was_minimized:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except (OSError, RuntimeError, pywintypes.error):
        pass
    if win32gui.GetForegroundWindow() != hwnd:
        # Windows may deny a foreground request from our observer thread. Briefly
        # share its input queue with the current foreground thread, then detach.
        attached = False
        try:
            foreground = win32gui.GetForegroundWindow()
            current_thread = win32api.GetCurrentThreadId()
            foreground_thread, _ = win32process.GetWindowThreadProcessId(foreground)
            if foreground_thread and foreground_thread != current_thread:
                win32process.AttachThreadInput(current_thread, foreground_thread, True)
                attached = True
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except (OSError, RuntimeError, pywintypes.error):
            pass
        finally:
            if attached:
                try:
                    win32process.AttachThreadInput(current_thread, foreground_thread, False)
                except (OSError, RuntimeError, pywintypes.error):
                    pass
    deadline = time.monotonic() + timeout
    next_retry = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        if was_minimized and time.monotonic() >= next_retry:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except (OSError, RuntimeError, pywintypes.error):
                pass
            next_retry = time.monotonic() + 0.4
        time.sleep(0.05)
    return win32gui.GetForegroundWindow() == hwnd


def find_edge_exe() -> Path | None:
    paths = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    return next((p for p in paths if p.is_file()), None)


class EdgeWindow:
    def __init__(self) -> None:
        self.hwnd: int | None = None
        self.pid: int | None = None
        self.url: str | None = None
        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ValorantDeathSwitcher" / "edge-profile"
        self.devtools = EdgeDevTools(profile)
        self.topmost = False
        self.last_focus_ms: int | None = None
        self.prewarm_attempted = False

    def prewarm(self) -> bool:
        """Start the dedicated Edge process without opening a window or page."""
        if self.devtools._read_port():
            return True
        if self.prewarm_attempted:
            return False
        self.prewarm_attempted = True
        edge = find_edge_exe()
        if not edge:
            return False
        try:
            self.devtools.profile_dir.mkdir(parents=True, exist_ok=True)
            (self.devtools.profile_dir / "DevToolsActivePort").unlink(missing_ok=True)
            process = subprocess.Popen([
                str(edge), f"--user-data-dir={self.devtools.profile_dir}",
                "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
                "--no-startup-window", "--no-first-run", "--no-default-browser-check",
            ])
            self.pid = process.pid
        except OSError:
            return False
        return self.devtools.wait_for_port(5)

    @staticmethod
    def _maximize(hwnd: int) -> None:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except pywintypes.error:
            # A visible window can still be activated if maximizing fails.
            pass

    def pause_video(self) -> tuple[bool, str]:
        if not self.url:
            return False, "未打开过抖音页面，无法暂停视频"
        try:
            if not self.devtools._read_port():
                return False, "Edge 页面连接已断开，无法暂停视频"
            return self.devtools.pause_video(self.url)
        except DevToolsError as exc:
            return False, str(exc)

    def release_topmost(self) -> None:
        if self.topmost and self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.SetWindowPos(
                    self.hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                )
            except pywintypes.error:
                pass
        self.topmost = False

    def minimize_for_game(self) -> None:
        self.release_topmost()
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.ShowWindow(self.hwnd, win32con.SW_MINIMIZE)
            except pywintypes.error:
                pass

    def restore_after_failed_game_switch(self) -> tuple[bool, str]:
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            return self._focus(opened=False)
        return False, "Edge 窗口已关闭，无法恢复"

    def _focus(self, opened: bool, *, fast: bool = False) -> tuple[bool, str]:
        assert self.hwnd is not None
        self._maximize(self.hwnd)
        focus_timeout = 0.08 if fast else 1.0
        if activate(self.hwnd, timeout=focus_timeout):
            return True, "已打开并切到 Edge" if opened else "已切到 Edge 专用窗口"
        try:
            win32gui.SetWindowPos(
                self.hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
            )
            self.topmost = True
        except pywintypes.error:
            return False, "Windows 拒绝激活 Edge，置顶也失败"
        if activate(self.hwnd, timeout=focus_timeout):
            return True, "Edge 已置顶并取得焦点"
        return False, "已尝试将 Edge 置顶，但 Windows 仍未交出键盘焦点"

    def _owns_window(self, hwnd: int) -> bool:
        if not win32gui.IsWindow(hwnd) or process_name(hwnd) != "msedge.exe":
            return False
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == self.pid:
                return True
            return str(self.devtools.profile_dir).lower() in " ".join(psutil.Process(pid).cmdline()).lower()
        except (psutil.Error, OSError):
            return False

    def _find_own_window(self, before: set[int]) -> int | None:
        if self.hwnd and self._owns_window(self.hwnd):
            return self.hwnd
        windows: list[int] = []

        def visit(hwnd: int, _extra: object) -> None:
            if win32gui.IsWindowVisible(hwnd) and process_name(hwnd) == "msedge.exe":
                windows.append(hwnd)

        try:
            win32gui.EnumWindows(visit, None)
        except pywintypes.error:
            return None
        for hwnd in windows:
            if self._owns_window(hwnd):
                return hwnd
        return None

    def open_or_activate(self, url: str) -> tuple[bool, str]:
        started = time.monotonic()
        self.last_focus_ms = None
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "网址必须是有效的 HTTP 或 HTTPS 地址"
        self.url = url
        warm_focus: tuple[bool, str] | None = None
        if self.hwnd and self._owns_window(self.hwnd):
            # Put the already open browser on screen before any HTTP or CDP work.
            warm_focus = self._focus(opened=False, fast=True)
            self.last_focus_ms = round((time.monotonic() - started) * 1000)
        edge = find_edge_exe()
        if not edge:
            return False, "未找到 Microsoft Edge"
        before = set(visible_windows("msedge.exe"))
        opened = False
        port_ready = bool(self.devtools._read_port())
        if not port_ready:
            try:
                self.devtools.profile_dir.mkdir(parents=True, exist_ok=True)
                (self.devtools.profile_dir / "DevToolsActivePort").unlink(missing_ok=True)
                process = subprocess.Popen([
                    str(edge), f"--user-data-dir={self.devtools.profile_dir}",
                    "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
                    "--no-first-run", "--no-default-browser-check",
                    "--new-window", "--start-maximized", url,
                ])
            except OSError as exc:
                return False, f"Edge 启动失败：{exc}"
            self.pid = process.pid
            opened = True
            # Show Edge as soon as its native window exists. Page setup can
            # continue afterward without delaying the visible switch.
            window_deadline = time.monotonic() + 8
            while time.monotonic() < window_deadline:
                self.hwnd = self._find_own_window(before)
                if self.hwnd:
                    warm_focus = self._focus(opened=True, fast=True)
                    self.last_focus_ms = round((time.monotonic() - started) * 1000)
                    break
                time.sleep(0.05)
            if not self.devtools.wait_for_port():
                return False, "Edge 已打开，但页面控制连接失败；请检查 Edge 调试策略"
        elif not self.hwnd or not win32gui.IsWindow(self.hwnd):
            self.hwnd = self._find_own_window(before)
            if self.hwnd:
                warm_focus = self._focus(opened=False, fast=True)
                self.last_focus_ms = round((time.monotonic() - started) * 1000)
        if port_ready and not self.hwnd:
            # A prewarmed browser has a CDP port but no visible window yet.
            try:
                process = subprocess.Popen([
                    str(edge), f"--user-data-dir={self.devtools.profile_dir}",
                    "--new-window", "--start-maximized", url,
                ])
            except OSError as exc:
                return False, f"Edge 窗口打开失败：{exc}"
            opened = True
            if self.pid is None:
                self.pid = process.pid
            window_deadline = time.monotonic() + 8
            while time.monotonic() < window_deadline:
                self.hwnd = self._find_own_window(before)
                if self.hwnd:
                    warm_focus = self._focus(opened=True, fast=True)
                    self.last_focus_ms = round((time.monotonic() - started) * 1000)
                    break
                time.sleep(0.05)
        try:
            page = self.devtools.ensure_page(url)
            self.devtools._command(page, "Page.bringToFront")
        except DevToolsError as exc:
            return False, str(exc)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.hwnd = self._find_own_window(before)
            if self.hwnd:
                if warm_focus is None:
                    focused, message = self._focus(opened)
                    self.last_focus_ms = round((time.monotonic() - started) * 1000)
                elif win32gui.GetForegroundWindow() == self.hwnd:
                    focused, message = True, "已切到 Edge 专用窗口"
                elif not warm_focus[0]:
                    focused, message = self._focus(opened=False, fast=True)
                    self.last_focus_ms = round((time.monotonic() - started) * 1000)
                else:
                    focused, message = warm_focus
                if focused:
                    try:
                        resumed, resume_message = self.devtools.resume_video(url)
                    except DevToolsError as exc:
                        return False, f"{message}；视频恢复失败：{exc}"
                    if resume_message:
                        return focused and resumed, f"{message}；{resume_message}"
                return focused, message
            time.sleep(0.1)
        return False, "Edge 页面已打开，但未找到专用窗口"
