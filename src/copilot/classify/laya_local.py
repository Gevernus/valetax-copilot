"""Laya, open-source and local (Apache-2.0): the multilingual checkpoint, zero-shot.

Nothing leaves the machine. The first call downloads the checkpoint from Hugging Face.
"""

import threading
from typing import Any

from copilot.classify import Classification, answers_from_probabilities
from copilot.classify.questions import TICKET, QuestionSet

CHECKPOINT = "multilingual"


class LayaClassifier:
    name = "laya"

    def __init__(self, questions: QuestionSet = TICKET) -> None:
        from laya import Router

        self._questions = questions
        self._router = Router(max_loaded=1)
        self._lock = threading.Lock()  # one model instance; torch inference is not re-entrant here

    def classify(self, text: str) -> Classification:
        questions = self._questions.systemone()
        with self._lock:
            result: dict[str, Any] = self._router.predict(text, questions, model=CHECKPOINT)
        answers = answers_from_probabilities(
            {name: a["probabilities"] for name, a in result["answers"].items()}, self._questions
        )
        return Classification(answers=answers, backend=self.name, model=f"laya-{CHECKPOINT}")
