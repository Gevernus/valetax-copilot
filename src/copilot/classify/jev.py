"""TypeSafe Jev, hosted: POST /v1/systemone."""

import os
from typing import Any

import httpx

from copilot.classify import Classification, Usage, answers_from_probabilities
from copilot.classify.questions import TICKET, QuestionSet
from copilot.errors import PermanentError, TransientError, for_status

URL = "https://api.typesafe.ai/v1/systemone"
# The model the thresholds and the reply-check measurements were made with. A new version is a
# re-measurement (evals.run, evals.run_drafts), not a silent upgrade.
JEV_MODEL = "jev-1.14.0"


class JevClassifier:
    """TypeSafe Jev over HTTP; needs TYPESAFE_API_KEY."""

    name = "jev"

    def __init__(
        self,
        questions: QuestionSet = TICKET,
        model: str = JEV_MODEL,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,  # tests pass a mock
    ) -> None:
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise RuntimeError("TYPESAFE_API_KEY is not set")
        self.questions = questions
        self._model = model
        self._timeout_s = timeout_s
        self._client = httpx.Client(
            timeout=timeout_s, headers={"Authorization": f"Bearer {key}"}, transport=transport
        )

    def classify(self, text: str, timeout_s: float | None = None) -> Classification:
        body = {
            "model": self._model,
            "state": text,
            "questions": self.questions.systemone(),
        }
        data = self._post(body, min(self._timeout_s, timeout_s or self._timeout_s))
        try:
            answers = answers_from_probabilities(
                {name: a["probabilities"] for name, a in data["answers"].items()}, self.questions
            )
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            raise PermanentError(f"malformed answer ({type(e).__name__})") from None
        usage = data.get("usage", {})
        return Classification(
            answers=answers,
            backend=self.name,
            model=data.get("model", self._model),
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
        )

    def _post(self, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        """The response as JSON.

        Failures become our errors by status only: the body can echo the text that was sent.
        """
        try:
            response = self._client.post(URL, json=body, timeout=timeout_s)
        except httpx.TimeoutException:
            raise TransientError("timeout") from None
        except httpx.TransportError as e:
            raise TransientError(type(e).__name__) from None
        if response.status_code >= 400:
            raise for_status(response.status_code)
        try:
            data = response.json()
        except ValueError:
            raise PermanentError("the response is not JSON") from None
        if not isinstance(data, dict):
            raise PermanentError("the response is not an object")
        return data
