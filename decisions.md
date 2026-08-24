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

## Pending

Decisions that are known to be needed but not yet made are tracked in
[open-questions.md](open-questions.md), not here. This file records only
what has actually been settled.
