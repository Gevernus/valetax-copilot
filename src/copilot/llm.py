"""Structured-output LLM calls behind one interface.

`claude-cli` shells out to `claude -p` and runs on a Claude subscription (development and evals).
`anthropic` calls the Messages API with an API key (production).
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Protocol

MODEL_IDS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """Tokens as reported by the backend. For claude-cli they include the CLI's own overhead."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True, slots=True)
class LlmResult:
    data: dict[str, Any]
    usage: LlmUsage
    model: str
    latency_ms: int


class LlmError(RuntimeError):
    pass


class Llm(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LlmResult: ...


class ClaudeCli:
    name = "claude-cli"

    def __init__(self, model: str = "haiku", timeout_s: float = 120.0) -> None:
        self.model = MODEL_IDS.get(model, model)
        self._timeout_s = timeout_s

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LlmResult:
        cmd = [
            "claude", "-p", user,
            "--model", self.model,
            "--system-prompt", system,
            "--tools", "",
            "--json-schema", json.dumps(schema),
            "--output-format", "json",
        ]  # fmt: skip
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout_s, check=False
            )
        except subprocess.TimeoutExpired as e:
            raise LlmError(f"claude CLI timed out after {self._timeout_s:.0f}s") from e
        latency_ms = int((time.perf_counter() - started) * 1000)
        if proc.returncode != 0:
            # stderr can echo the prompt; keep only the exit code.
            raise LlmError(f"claude CLI exited with {proc.returncode}")
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LlmError("claude CLI returned non-JSON output") from e
        data = out.get("structured_output")
        if out.get("is_error") or not isinstance(data, dict):
            raise LlmError(f"claude CLI returned no structured output ({out.get('subtype')})")
        u = out.get("usage", {})
        usage = LlmUsage(
            input_tokens=int(u.get("input_tokens", 0)),
            output_tokens=int(u.get("output_tokens", 0)),
            cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
            cache_write_tokens=int(u.get("cache_creation_input_tokens", 0)),
        )
        return LlmResult(data, usage, self.model, latency_ms)


class AnthropicApi:
    """Messages API with the system prompt cached. Written against the SDK docs; not run here."""

    name = "anthropic"

    def __init__(self, model: str = "haiku", max_tokens: int = 2048) -> None:
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = MODEL_IDS.get(model, model)
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LlmResult:
        started = time.perf_counter()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.stop_reason != "end_turn":
            raise LlmError(f"stop_reason={response.stop_reason}")
        text = next(b.text for b in response.content if b.type == "text")
        u = response.usage
        usage = LlmUsage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
        )
        return LlmResult(json.loads(text), usage, self.model, latency_ms)


def make_llm(backend: str, model: str) -> Llm:
    if backend == "claude-cli":
        return ClaudeCli(model)
    if backend == "anthropic":
        return AnthropicApi(model)
    raise ValueError(f"unknown LLM backend {backend!r}; expected claude-cli or anthropic")
