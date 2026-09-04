"""Shared test doubles: scripted providers sized for the shrunk pipeline."""

from novel_engine.providers.base import (
    GenerationRequest,
    Outcome,
    Provider,
    RateLimited,
)


class FakeProvider(Provider):
    """Serves a scripted list of outcomes, repeating the last one."""

    name = "fake"

    def __init__(self, *outcomes: Outcome):
        self.script = list(outcomes)
        # Repeat the final scripted outcome once the script runs dry.
        self._default = self.script[-1] if self.script else RateLimited("exhausted")
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> Outcome:
        self.calls.append(request)
        if self.script:
            return self.script.pop(0)
        return self._default

    def serve(self, *outcomes: Outcome, default: Outcome) -> None:
        self.script = list(outcomes)
        self._default = default


def full_providers(**named: FakeProvider) -> dict[str, FakeProvider]:
    """Every provider the fixture routes mention — drafting chain and
    editor routes both, since Phase 6 runs them in one session. Unrouted
    ones never fire (the Router validates the whole chain up front)."""
    providers = {
        name: FakeProvider(RateLimited("unused"))
        for name in ("openrouter", "nvidia", "groq", "local", "gemini", "mistral")
    }
    providers.update(named)
    return providers


def editorial_delta(chapter_number: int, **overrides) -> dict:
    """A valid, clean delta for the fixture — nothing critical, so it
    reconciles. Tests that want a refusal override `continuity_violations`."""
    delta = {
        "chapter_number": chapter_number,
        "continuity_violations": [],
        "new_locked_facts": [
            {
                "category": "character",
                "entity": "ovist-rhoam",
                "fact": "Ovist counts driftglass by weight.",
                "source_chapter": chapter_number,
            }
        ],
        "thread_updates": {
            "opened": [{"text": "Someone reset the ebb ledge."}],
            "progressed": [],
            "resolved": [],
        },
        "chapter_summary": "Ovist walked the ledge and read the seal.",
        "next_step_note": "Sela has not been told.",
        "deepen_questions": ["Who issues the lead seals?"],
        "suggested_canon_patches": [],
        "beat_adherence": {"hit": True, "notes": "The beat lands."},
    }
    delta.update(overrides)
    return delta


def text_of(words: int, seed: str = "w") -> str:
    return " ".join(f"{seed}{i}" for i in range(words))


def reset_fixture_state(book_root) -> None:
    """Force a copied example-book back to the canonical drafting-test
    state: chapters 001-002 written, 003 planned, nothing else.

    The committed fixture legitimately grows as real-run verification
    drafts more chapters into it; tests must not be coupled to that.
    """
    from pathlib import Path

    root = Path(book_root)

    # Manifest: 001-002 written, 003 planned, later rows removed.
    outline = root / "canon" / "plot-outline.md"
    text = outline.read_text(encoding="utf-8")
    begin = text.index("<!-- MANIFEST:BEGIN -->")
    end = text.index("<!-- MANIFEST:END -->")
    section_lines = text[begin:end].splitlines()
    rebuilt: list[str] = []
    for line in section_lines:
        stripped = line.strip()
        if not stripped.startswith("| 00"):
            rebuilt.append(line)  # markers, blanks, header, separator
            continue
        number = int(stripped.strip("|").split("|")[0].strip())
        if number > 3:
            continue
        if number == 3:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells[3] = "planned"
            line = "| " + " | ".join(cells) + " |"
        rebuilt.append(line)
    outline.write_text(
        text[:begin] + "\n".join(rebuilt) + "\n" + text[end:], encoding="utf-8"
    )

    # Chapters beyond 002 and their session audits do not exist yet.
    for path in sorted((root / "chapters").glob("chapter-*.md")):
        number = int(path.stem.removeprefix("chapter-"))
        if number > 2:
            path.unlink()
    for audit in (root / "log" / "sessions").glob("sess-*.json"):
        audit.unlink()
