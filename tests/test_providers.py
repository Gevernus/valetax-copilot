"""Every backend turns its failures into one of three errors; no response body is kept."""

import json
import subprocess
from typing import Any

import httpx
import pytest

from copilot.classify.jev import JEV_MODEL, JevClassifier
from copilot.classify.questions import REPLY
from copilot.errors import PermanentError, TransientError, UsageLimitError
from copilot.llm import ClaudeCli

GOOD = {
    "model": "jev-1.14.0",
    "answers": {name: {"probabilities": {"yes": 0.1, "no": 0.9}} for name in REPLY.options},
}


def jev(handler: Any, monkeypatch: pytest.MonkeyPatch) -> JevClassifier:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy-for-tests")
    return JevClassifier(REPLY, transport=httpx.MockTransport(handler))


def test_jev_is_pinned() -> None:
    assert JEV_MODEL == "jev-1.14.0"


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, TransientError), (500, TransientError), (503, TransientError), (400, PermanentError),
     (401, PermanentError), (422, PermanentError)],
)  # fmt: skip
def test_jev_http_errors(
    status: int, error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "provider body with the ticket text"
    with pytest.raises(error) as caught:
        jev(lambda r: httpx.Response(status, text=body), monkeypatch).classify("x")
    assert body not in str(caught.value)


def test_jev_timeouts_and_transport_errors_are_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for handler in (timeout, refused):
        with pytest.raises(TransientError):
            jev(handler, monkeypatch).classify("x")


@pytest.mark.parametrize(
    "body",
    ["not json", json.dumps({"answers": {}}), json.dumps({**GOOD, "answers": {"decision": {}}})],
)
def test_jev_malformed_answers_are_permanent(body: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(PermanentError):
        jev(lambda r: httpx.Response(200, text=body), monkeypatch).classify("x")


def test_jev_sends_the_pinned_model(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=GOOD)

    cls = jev(handler, monkeypatch).classify("x")
    assert seen[0]["model"] == "jev-1.14.0"
    assert cls.model == "jev-1.14.0"


def cli_returning(monkeypatch: pytest.MonkeyPatch, **result: Any) -> None:
    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "raise" in result:
            raise result["raise"]
        return subprocess.CompletedProcess(args, result.get("code", 0), result.get("out", ""), "")

    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.parametrize(
    ("result", "error"),
    [
        ({"code": 1, "out": "boom"}, TransientError),
        ({"out": "not json"}, TransientError),
        ({"out": json.dumps({"is_error": True, "subtype": "error_max_turns"})}, TransientError),
        ({"raise": subprocess.TimeoutExpired("claude", 90)}, TransientError),
        ({"code": 1, "out": "You've hit your limit"}, UsageLimitError),
    ],
)
def test_claude_cli_failures(
    result: dict[str, Any], error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_returning(monkeypatch, **result)
    with pytest.raises(error):
        ClaudeCli("haiku").complete("system", "user", {})


def test_anthropic_sdk_errors_are_normalised() -> None:
    anthropic = pytest.importorskip("anthropic")
    from copilot.llm import anthropic_error

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def status(code: int) -> Exception:
        response = httpx.Response(code, request=request, text="body with ticket text")
        error: Exception = anthropic.APIStatusError("failed", response=response, body=None)
        return error

    assert isinstance(anthropic_error(anthropic.APITimeoutError(request=request)), TransientError)
    assert isinstance(
        anthropic_error(anthropic.APIConnectionError(request=request)), TransientError
    )
    assert isinstance(anthropic_error(status(429)), TransientError)  # rate limit: retry later
    assert isinstance(anthropic_error(status(529)), TransientError)
    assert isinstance(anthropic_error(status(500)), TransientError)
    assert isinstance(anthropic_error(status(400)), PermanentError)
    assert "body with ticket text" not in str(anthropic_error(status(400)))
