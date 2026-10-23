"""Provider failures in three kinds, and the one retry policy that uses them.

Every backend (the drafter's LLM, the decision-model classifiers) turns its own failures into
one of these, with the error class and status only: never a response body, which can echo the
ticket. The pipeline retries a transient error within an attempt budget and a per-ticket
deadline that also bounds every call, and sends the ticket to a person when the budget runs out.
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


def for_status(status: int) -> ProviderError:
    """An HTTP failure by status: 429 and 5xx are worth retrying, other 4xx are not."""
    if status == 429 or status >= 500:
        return TransientError(f"HTTP {status}")
    return PermanentError(f"HTTP {status}")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Attempts per stage, backoff and the per-ticket deadline."""

    attempts: int = 3  # calls per stage, the first one included
    backoff_s: float = 1.0  # wait before the second call; doubles after that
    deadline_s: float = 120.0  # per ticket, measured from the start of processing


class Budget:
    """One ticket's time and calls.

    Every call, the first included, gets the time left as its timeout; with no time left it is not
    made (TransientError "deadline"). Only a transient error is retried, within the attempt budget
    and the time left.
    """

    def __init__(
        self,
        policy: RetryPolicy,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy
        self._clock, self._sleep = clock, sleep
        self._deadline = clock() + policy.deadline_s
        self.attempts: dict[str, int] = {}  # calls made per stage, for the trace

    def remaining(self) -> float:
        return self._deadline - self._clock()

    def call[T](self, stage: str, fn: Callable[[float], T]) -> T:
        """`fn(timeout_s)`, retried on a TransientError while calls and time are left."""
        wait = self.policy.backoff_s
        for attempt in range(1, self.policy.attempts + 1):
            left = self.remaining()
            if left <= 0:
                raise TransientError("deadline")
            self.attempts[stage] = attempt
            try:
                return fn(left)
            except TransientError:
                if attempt == self.policy.attempts or self.remaining() - wait <= 0:
                    raise
                self._sleep(wait)
                wait *= 2
        raise AssertionError("unreachable: the loop returns or raises")
