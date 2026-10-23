"""Append-only JSONL traces: one line per processed ticket."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TraceWriter:
    """Appends trace lines with a timestamp; safe across threads."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, line: dict[str, Any]) -> None:
        record = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), **line}
        data = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._path.open("a") as f:
            f.write(data + "\n")
