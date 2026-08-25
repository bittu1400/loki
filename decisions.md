# Decisions Log

Fast-scan ledger. One line per decision, newest at the bottom.
Full context, alternatives, and consequences live in [adr.md](adr.md).

**Rule:** every decision the author makes is written here the moment it is
made, in the same session, before any other work continues. Nothing waits
for "later". If it is not in this file, it was not decided.

| # | Date | Decision | ADR |
|---|------|----------|-----|
| 1 | 2026-08-24 | v1 = core pipeline only. Publishing endpoint, GitHub Actions cron, and `new_book.py` as an interactive CLI are all deferred. | [ADR-0001](adr.md#adr-0001--v1-scope-boundary) |
| 2 | 2026-08-24 | Python toolchain is `uv` + `pyproject.toml` + Pydantic v2 + ruff + pytest. | [ADR-0002](adr.md#adr-0002--python-toolchain) |
| 3 | 2026-08-24 | One chapter per session, manually triggered. Not two, not scheduled. | [ADR-0003](adr.md#adr-0003--session-shape) |
| 4 | 2026-08-24 | Vault lives at `vault/<book-slug>/` in this repo. Real manuscripts are gitignored; a committed `vault/example-book/` fixture serves tests and CI. | [ADR-0004](adr.md#adr-0004--vault-location-and-what-gets-committed) |
| 5 | 2026-08-25 | Config is split: `models.yaml` for model routing only, `pipeline.yaml` for behaviour (`target_words`, `auto_publish`, etc.). Resolves OQ-03 in favour of the specs.md §9–10 proposal; removes the `PROPOSED` marker there. | — |
| 6 | 2026-08-25 | `vault/example-book/` fixture is an invented throwaway story, deliberately awkward (odd names, tricky continuity), not the author's real book. Resolves OQ-05.1; OQ-05.2 (the real book) stays open until Phase 3 nears. | — |

## Pending

Decisions that are known to be needed but not yet made are tracked in
[open-questions.md](open-questions.md), not here. This file records only
what has actually been settled.
