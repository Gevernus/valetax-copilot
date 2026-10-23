"""Every backend turns its failures into one of three errors; no response body is kept."""

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from copilot.classify.jev import JevClassifier
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


def cli_returning(monkeypatch: pytest.MonkeyPatch, **result: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        if "raise" in result:
            raise result["raise"]
        out, err = result.get("out", ""), result.get("err", "")
        return subprocess.CompletedProcess(args, result.get("code", 0), out, err)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def cli_error(text: str) -> str:
    return json.dumps({"type": "result", "is_error": True, "subtype": "success", "result": text})


@pytest.mark.parametrize(
    ("result", "error"),
    [
        ({"code": 1, "out": "boom"}, TransientError),
        ({"out": "not json"}, TransientError),
        ({"out": json.dumps({"is_error": True, "subtype": "error_max_turns"})}, TransientError),
        ({"raise": subprocess.TimeoutExpired("claude", 90)}, TransientError),
        # Only the CLI's own result field can say "usage limit"; free text and stderr cannot.
        (
            {"code": 1, "out": cli_error("Claude AI usage limit reached|1761200000")},
            UsageLimitError,
        ),
        ({"code": 1, "out": cli_error("You've hit your limit · resets 5pm")}, UsageLimitError),
        ({"code": 1, "out": cli_error("API Error: 429 rate limit exceeded")}, TransientError),
        ({"code": 1, "out": cli_error("You've reached your monthly spend limit")}, UsageLimitError),
        ({"code": 1, "out": cli_error("Your team's shared budget is used up")}, UsageLimitError),
        ({"code": 1, "out": cli_error("You've reached your Fable limit")}, UsageLimitError),
        ({"code": 1, "out": cli_error("You've hit your weekly limit")}, UsageLimitError),
        ({"code": 1, "out": cli_error("You're out of usage credits")}, UsageLimitError),
        ({"code": 1, "out": cli_error("You're out of extra usage")}, UsageLimitError),
        ({"code": 1, "out": cli_error("Your org is out of usage")}, UsageLimitError),
        ({"code": 1, "out": cli_error("Credit balance is too low")}, UsageLimitError),
        (
            {"code": 1, "out": cli_error("You reached your destination server too slowly")},
            TransientError,
        ),
        (
            {
                "code": 1,
                "out": json.dumps(
                    {
                        "is_error": True,
                        "api_error_status": 429,
                        "result": "You've reached your limit",
                    }
                ),
            },
            TransientError,
        ),
        ({"code": 1, "out": "You've hit your limit"}, TransientError),
        (
            {
                "code": 1,
                "out": json.dumps(
                    {
                        "is_error": True,
                        "api_error_status": 429,
                        "api_error": "usage_limit_reached",
                        "result": "You've hit your weekly limit",
                    }
                ),
            },
            UsageLimitError,
        ),
        ({"code": 1, "err": "usage limit reached"}, TransientError),
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


def test_every_backend_gets_the_time_left(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = cli_returning(monkeypatch, out=json.dumps({"structured_output": {}, "usage": {}}))
    ClaudeCli("haiku").complete("system", "user", {}, timeout_s=7.0)
    assert calls[0]["timeout"] == 7.0

    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json=GOOD)

    jev(handler, monkeypatch).classify("x", timeout_s=5.0)
    assert seen[0]["read"] == 5.0


def test_the_cli_runs_in_a_private_dir_with_a_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy-for-tests")
    monkeypatch.setenv("HOME", "/home/agent")
    calls = cli_returning(monkeypatch, out=json.dumps({"structured_output": {}, "usage": {}}))
    client = ClaudeCli("haiku")  # its directory lives as long as it does
    client.complete("system", "user", {})
    env, cwd = calls[0]["env"], Path(calls[0]["cwd"])
    assert "TYPESAFE_API_KEY" not in env
    assert env["HOME"] == "/home/agent"
    assert cwd.stat().st_mode & 0o077 == 0  # nobody else can read or plant files in it


def test_anthropic_client_does_not_retry_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("anthropic")
    from copilot.llm import AnthropicApi

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-for-tests")
    api = AnthropicApi("haiku")
    assert api._client.max_retries == 0
    seen: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        seen.update(kwargs)
        raise TransientError("stop here")

    monkeypatch.setattr(api._client.messages, "create", create)
    with pytest.raises(TransientError):
        api.complete("system", "user", {}, timeout_s=9.0)
    assert seen["timeout"] == 9.0


def test_a_reply_cut_at_max_tokens_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Three identical calls would stop at the same place: no retry.
    pytest.importorskip("anthropic")
    from types import SimpleNamespace

    from copilot.llm import AnthropicApi

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-for-tests")
    api = AnthropicApi("haiku")
    cut = SimpleNamespace(stop_reason="max_tokens", content=[], usage=None)
    monkeypatch.setattr(api._client.messages, "create", lambda **_: cut)
    with pytest.raises(PermanentError):
        api.complete("system", "user", {})
