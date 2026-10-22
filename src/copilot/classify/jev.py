"""TypeSafe Jev, hosted: POST /v1/systemone."""

import os

import httpx

from copilot.classify import Classification, Usage, answers_from_probabilities
from copilot.classify.questions import TICKET, QuestionSet

URL = "https://api.typesafe.ai/v1/systemone"


class JevClassifier:
    name = "jev"

    def __init__(
        self, questions: QuestionSet = TICKET, model: str = "jev-latest", timeout_s: float = 30.0
    ) -> None:
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise RuntimeError("TYPESAFE_API_KEY is not set")
        self._questions = questions
        self._model = model
        self._client = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {key}"})

    def classify(self, text: str) -> Classification:
        body = {
            "model": self._model,
            "state": text,
            "questions": self._questions.systemone(),
        }
        response = self._client.post(URL, json=body)
        response.raise_for_status()
        data = response.json()
        answers = answers_from_probabilities(
            {name: a["probabilities"] for name, a in data["answers"].items()}, self._questions
        )
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
