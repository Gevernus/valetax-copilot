"""Sectioned knowledge base: loading, version hash and the prompt rendering."""

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KB = Path(__file__).resolve().parents[2] / "kb" / "valetax.toml"


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    text: str
    urls: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    sections: dict[str, Section]
    issue_kinds: dict[str, str]
    version: str  # first 12 hex digits of the file's SHA-256; goes into every trace line

    def has_conflict(self, section_id: str) -> bool:
        section = self.sections.get(section_id)
        if section is None:
            return False
        return any(self.issue_kinds.get(i) == "conflict" for i in section.issues)

    @property
    def prompt_block(self) -> str:
        """The whole KB as one stable string: identical bytes on every call, so it caches."""
        parts = [f"[{s.id}] {s.title}\n{s.text}" for s in self.sections.values()]
        return "\n\n".join(parts)


def load_kb(path: Path = DEFAULT_KB) -> KnowledgeBase:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode())
    pages: dict[str, str] = data["pages"]
    sections: dict[str, Section] = {}
    for item in data["section"]:
        if item["id"] in sections:
            raise ValueError(f"duplicate section id {item['id']}")
        sections[item["id"]] = Section(
            id=item["id"],
            title=item["title"],
            text=" ".join(item["text"].split()),
            urls=tuple(pages[p] for p in item["sources"]),
            issues=tuple(item.get("issues", ())),
        )
    issue_kinds: dict[str, str] = data["issues"]
    for section in sections.values():
        unknown = set(section.issues) - issue_kinds.keys()
        if unknown:
            raise ValueError(f"{section.id}: unknown issues {sorted(unknown)}")
    return KnowledgeBase(sections, issue_kinds, hashlib.sha256(raw).hexdigest()[:12])
