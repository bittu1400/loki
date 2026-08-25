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
| 7 | 2026-08-25 | Model routing settled after live spikes: drafting primary `openrouter:minimax-m3:free` with `nvidia:minimaxai/minimax-m3` as same-model mirror; `gemini:gemini-3.5-flash-lite` for brannec-tull POV chapters; editorial `gemini flash-lite` → `mistral:mistral-large`. Full table in example-book `config/models.yaml`. | — |
| 8 | 2026-08-25 | Provider stability principle: every route needs a fallback on a **different provider**, ideally the same model served twice. Provider diversity is a requirement, not an optimisation. Dismissed providers (cohere, z.ai, cerebras, github-models) are commented out of `.env` with reasons and must not be re-added without new evidence. | — |
| 9 | 2026-08-25 | AiHubMix added as sixth provider (`AIHUBMIX_API_KEY`), slotted into the drafting fallback chain between nvidia and groq. Direct MiniMax platform key was evaluated and rejected: pay-as-you-go only, violates the hard 0-cost constraint. Free lanes for minimax-m3 are now openrouter → nvidia → aihubmix. | — |
| 10 | 2026-08-25 | Terminal case — every provider exhausted: the session still writes output, never silently fails and never fakes success. It writes a clearly-marked failed-draft stub chapter (manifest status stays `planned`, stub is excluded from continuity) at zero cost. | [ADR-0005](adr.md#adr-0005--all-providers-failed-stub-draft) |
| 11 | 2026-08-25 | Six new provider keys evaluated: chutes, siliconflow, nanogpt, fireworks, portkey all **dismissed** with dated reasons in `.env` (no needed models on free terms / no free tier / account suspended / redundant gateway). Requesty **kept but key invalid** — regenerate it; its 12 zero-priced models are a candidate last-resort lane pending a prose check of nemotron-3-super-120b (ultra variant already dismissed as canon-breaking). No routing changes until the key works and a spike passes. | — |
| 12 | 2026-08-25 | AiHubMix demoted out of routing: its free tier is ~10 lifetime requests unrecharged (empirically exhausted during the OQ-04 re-run spike), after which all free models return an abuse string. Fails the author's stability condition. Drafting fallback chain returns to nvidia → groq. Spike re-run found no model beating minimax-m3 → primary unchanged. Chutes ($0 balance, paid-only TEE catalog) and SiliconFlow ($0 list rotated away) confirmed dismissed. Full table in open-questions.md OQ-04. | — |

## Pending

Decisions that are known to be needed but not yet made are tracked in
[open-questions.md](open-questions.md), not here. This file records only
what has actually been settled.
