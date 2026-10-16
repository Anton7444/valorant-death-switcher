from valorant_switcher.edge_cdp import EdgeDevTools


def test_closed_threads_tab_is_reopened(monkeypatch, tmp_path):
    browser = EdgeDevTools(tmp_path)
    pages = [
        [{"id": "other", "type": "page", "url": "https://example.com/"}],
        [{"id": "other", "type": "page", "url": "https://example.com/"}],
    ]
    monkeypatch.setattr(browser, "pages", lambda: pages.pop(0) if pages else [])
    monkeypatch.setattr("valorant_switcher.edge_cdp.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("valorant_switcher.edge_cdp.time.monotonic", iter([0, 3]).__next__)
    calls = []

    def request(path, *, method="GET"):
        calls.append((path, method))
        return {"id": "new", "type": "page", "url": "https://www.threads.com/"} if path.startswith("/json/new") else "Target activated"

    monkeypatch.setattr(browser, "_request", request)
    page = browser.ensure_page("https://www.threads.com/")
    assert page["id"] == "new"
    assert calls[0][0].startswith("/json/new?https%3A%2F%2Fwww.threads.com")
    assert calls[0][1] == "PUT"


def test_pause_checks_video_state(monkeypatch, tmp_path):
    browser = EdgeDevTools(tmp_path)
    monkeypatch.setattr(browser, "find_page", lambda _url: {"id": "threads"})
    monkeypatch.setattr(browser, "_command", lambda *_args: {"result": {"value": {"found": 1, "paused": 1}}})
    assert browser.pause_video("https://www.threads.com/") == (True, "已暫停Threads頁面中的 1 個影片")
