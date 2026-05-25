from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace

from conftest import load_example


launcher = load_example("rest_api_examples_launcher", "main.py")


class FakeResponse:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_prompt_returns_exit_choice_on_eof(monkeypatch) -> None:
    def raise_eof(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert launcher.prompt("Choose:") == "0"


def test_request_json_handles_success_and_json_error(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fake_urlopen)

    status_code, body = launcher.request_json(
        "POST",
        "http://example.test/v1/items/",
        {"name": "Widget"},
        {"X-Test": "yes"},
    )

    assert status_code == 200
    assert body == {"ok": True}
    assert captured == {"method": "POST", "body": b'{"name": "Widget"}', "timeout": 5}


def test_request_json_handles_http_error_with_plain_text(monkeypatch) -> None:
    def fake_urlopen(request, timeout: int):
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            hdrs={},
            fp=io.BytesIO(b"temporarily unavailable"),
        )

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fake_urlopen)

    status_code, body = launcher.request_json("GET", "http://example.test/down", None, None)

    assert status_code == 503
    assert body == {"raw": "temporarily unavailable"}


def test_run_server_tests_counts_passes_and_failures(monkeypatch, capsys) -> None:
    responses = iter([(200, {"ok": True}), (500, {"error": "nope"})])

    def fake_request_json(method, url, body, headers):
        return next(responses)

    monkeypatch.setattr(launcher, "request_json", fake_request_json)
    module = {
        "name": "Example",
        "port": 1234,
        "tests": [
            {"name": "passes", "method": "GET", "path": "/ok", "expect": 200},
            {"name": "fails", "method": "GET", "path": "/bad", "expect": 200},
        ],
    }

    launcher.run_server_tests(module)

    output = capsys.readouterr().out
    assert "passes -> 200" in output
    assert "expected 200, got 500" in output


def test_stop_server_terminates_running_process() -> None:
    proc = SimpleNamespace(terminated=False, waited=False)
    proc.poll = lambda: None

    def terminate() -> None:
        proc.terminated = True

    def wait(timeout: int) -> None:
        proc.waited = timeout == 10

    proc.terminate = terminate
    proc.wait = wait

    launcher.stop_server(proc)

    assert proc.terminated is True
    assert proc.waited is True
