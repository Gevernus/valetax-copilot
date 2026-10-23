"""Provider failures in three kinds, and the one retry policy that uses them.

Every backend (the drafter's LLM, the decision-model classifiers) turns its own failures into
one of these, with the error class and status only: never a response body, which can echo the
ticket. The pipeline retries a transient error within an attempt budget and a per-ticket
deadline, and sends the ticket to a person when the budget runs out.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """A failed call to a model provider."""


class TransientError(ProviderError):
    """Worth retrying: a timeout, a dropped connection, 429, 5xx, a malformed sampled answer."""


class PermanentError(ProviderError):
    """Retrying will not help: a rejected request (4xx), a malformed decision-model answer."""


class UsageLimitError(ProviderError):
    """The account is out of quota. Not a ticket failure: callers stop instead of recording it."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3  # calls per stage, the first one included
    backoff_s: float = 1.0  # wait before the second call; doubles after that
    deadline_s: float = 120.0  # per ticket, measured from the start of processing


def with_retry[T](
    call: Callable[[], T],
    policy: RetryPolicy,
    deadline: float,
    attempts: dict[str, int],
    stage: str,
) -> T:
    """Calls `call`, retrying only a TransientError while the attempt budget and the deadline (a
    time.perf_counter() value) allow; anything else, or the last failure, is raised. The number of
    calls made is kept in `attempts[stage]`, for the trace."""
    wait = policy.backoff_s
    for attempt in range(1, policy.attempts + 1):
        attempts[stage] = attempt
        try:
            return call()
        except TransientError:
            if attempt == policy.attempts or time.perf_counter() + wait > deadline:
                raise
            time.sleep(wait)
            wait *= 2
    raise AssertionError("unreachable: the loop returns or raises")
