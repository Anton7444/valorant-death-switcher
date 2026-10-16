"""Control only the app's dedicated Chrome profile through local DevTools."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import ProxyHandler, Request, build_opener

import websocket


class DevToolsError(RuntimeError):
    pass


class EdgeDevTools:
    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = profile_dir
        self.port: int | None = None
        self.page_id: str | None = None
        self.paused_page_id: str | None = None
        self._opener = build_opener(ProxyHandler({}))

    def _read_port(self) -> int | None:
        try:
            lines = (self.profile_dir / "DevToolsActivePort").read_text().splitlines()
            port = int(lines[0])
            if not 0 < port < 65536:
                return None
            self.port = port
            version = self._request("/json/version")
            if urlparse(version.get("webSocketDebuggerUrl", "")).path != lines[1].strip():
                raise DevToolsError("Chrome 除錯埠與專用資料目錄不匹配")
            return port
        except (OSError, ValueError, IndexError, AttributeError, DevToolsError):
            self.port = None
            return None

    def wait_for_port(self, seconds: float = 8.0) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._read_port():
                return True
            time.sleep(0.1)
        return False

    def _request(self, path: str, *, method: str = "GET"):
        if self.port is None:
            raise DevToolsError("Chrome 除錯埠不可用")
        try:
            request = Request(f"http://127.0.0.1:{self.port}{path}", method=method)
            with self._opener.open(request, timeout=2) as response:
                body = response.read().decode("utf-8")
                try:
                    return json.loads(body)
                except ValueError:
                    return body
        except (OSError, ValueError) as exc:
            raise DevToolsError(f"Chrome 頁面連線失敗：{exc}") from exc

    def pages(self) -> list[dict]:
        return [item for item in self._request("/json/list") if item.get("type") == "page"]

    def find_page(self, url: str) -> dict | None:
        host = urlparse(url).hostname
        if not host:
            return None
        matches = [item for item in self.pages() if urlparse(item.get("url", "")).hostname == host]
        return next((item for item in matches if item.get("id") == self.page_id), None) or (
            matches[0] if matches else None
        )

    def ensure_page(self, url: str) -> dict:
        deadline = time.monotonic() + 2
        page = self.find_page(url)
        while page is None and time.monotonic() < deadline:
            time.sleep(0.1)
            page = self.find_page(url)
        if page is None:
            page = self._request(f"/json/new?{quote(url, safe='')}", method="PUT")
        self.page_id = page["id"]
        self._request(f"/json/activate/{quote(self.page_id, safe='')}")
        return page

    @staticmethod
    def _command(page: dict, method: str, params: dict | None = None) -> dict:
        address = page.get("webSocketDebuggerUrl")
        if not address:
            raise DevToolsError("Chrome 頁面沒有除錯連線")
        try:
            connection = websocket.create_connection(address, timeout=2, suppress_origin=True)
            try:
                connection.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
                while True:
                    answer = json.loads(connection.recv())
                    if answer.get("id") == 1:
                        if "error" in answer:
                            raise DevToolsError(str(answer["error"]))
                        return answer.get("result", {})
            finally:
                connection.close()
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            raise DevToolsError(f"Chrome 頁面命令失敗：{exc}") from exc

    def pause_video(self, url: str) -> tuple[bool, str]:
        page = self.find_page(url)
        if page is None:
            return False, "Threads標籤已關閉，無法暫停影片"
        expression = """(() => {
          const videos = new Set();
          function scan(root) {
            root.querySelectorAll('video').forEach(v => videos.add(v));
            root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) scan(e.shadowRoot); });
            root.querySelectorAll('iframe').forEach(f => {
              try { if (f.contentDocument) scan(f.contentDocument); } catch (_) {}
            });
          }
          scan(document);
          const wasPlaying = [...videos].filter(v => !v.paused && !v.ended);
          function visibleArea(video) {
            const r = video.getBoundingClientRect();
            return Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) *
                   Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
          }
          const candidates = wasPlaying.length ? wasPlaying : [...videos];
          candidates.sort((a, b) => visibleArea(b) - visibleArea(a));
          if (candidates.length) window.__valorantSwitcherResumeVideo = candidates[0];
          for (const video of videos) if (!video.paused) video.pause();
          return {found: videos.size, paused: [...videos].filter(v => v.paused).length,
                  resumeQueued: !!window.__valorantSwitcherResumeVideo};
        })()"""
        result = self._command(page, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in result:
            return False, "Threads頁面拒絕暫停命令"
        value = result.get("result", {}).get("value", {})
        found = value.get("found", 0)
        paused = value.get("paused", 0)
        if value.get("resumeQueued"):
            self.paused_page_id = page["id"]
        if found and paused == found:
            return True, f"已暫停Threads頁面中的 {found} 個影片"
        if not found:
            return False, "Threads頁面目前沒有可暫停的影片"
        return False, f"Threads頁面有 {found} 個影片，僅 {paused} 個已暫停"

    def resume_video(self, url: str) -> tuple[bool, str]:
        if self.paused_page_id is None:
            return True, ""
        page = self.find_page(url)
        if page is None:
            self.paused_page_id = None
            return True, ""
        expression = """(async () => {
          function visibleArea(video) {
            const r = video.getBoundingClientRect();
            return Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) *
                   Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
          }
          let video = window.__valorantSwitcherResumeVideo;
          if (!video || !video.isConnected || visibleArea(video) === 0) {
            const videos = [];
            function scan(root) {
              root.querySelectorAll('video').forEach(v => videos.push(v));
              root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) scan(e.shadowRoot); });
              root.querySelectorAll('iframe').forEach(f => {
                try { if (f.contentDocument) scan(f.contentDocument); } catch (_) {}
              });
            }
            scan(document);
            videos.sort((a, b) => visibleArea(b) - visibleArea(a));
            video = videos[0];
          }
          if (!video) return {state: 'missing'};
          if (!video.paused) return {state: 'playing'};
          try {
            await Promise.race([
              video.play(),
              new Promise((_, reject) => setTimeout(() => reject(Error('timeout')), 900))
            ]);
            return {state: video.paused ? 'paused' : 'playing'};
          } catch (error) {
            return {state: 'failed', reason: String(error)};
          }
        })()"""
        result = self._command(page, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True, "userGesture": True,
        })
        if "exceptionDetails" in result:
            return False, "影片自動播放失敗：頁面指令碼報錯"
        value = result.get("result", {}).get("value", {})
        state = value.get("state")
        if state == "playing":
            self.paused_page_id = None
            return True, "已恢復上次播放的影片"
        if state == "missing":
            self.paused_page_id = None
            return False, "原影片已離開頁面，無法自動恢復播放"
        return False, "影片未能自動恢復播放"
