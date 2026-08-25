# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-25 · end of Session 2

---

## Current state

**Phase 0 (documentation foundation) — ✅ complete (Session 1).**
**Phase 1 (vault templates + config loader) — ✅ complete (Session 2).**
**Phase 2 (provider layer) — ⬜ next, but see "Blocked / waiting" below.**

All five Phase 1 exit criteria were run and passed at end of Session 2
(see below). Python package exists with working config loader, manifest
parser, scaffolder, and 30 passing tests.

---

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq + retry/fallback/dry-run | ⬜ next | OQ-02 to finish; author API keys |
| 3 | Single-chapter generation + continuation loop | ⬜ | OQ-04 recommended first |
| 4 | Deterministic style checks | ⬜ | — |
| 5 | Editorial delta pass + reconciler | ⬜ | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 2 — 2026-08-25

### Done

**Decisions recorded first** (per CLAUDE.md rule), then all five Phase 1
batches in order, one commit each:

1. **OQ-03 resolved:** config split confirmed — `models.yaml` routing only,
   `pipeline.yaml` behaviour only. `PROPOSED` marker removed from specs §10.
2. **OQ-05.1 resolved:** `example-book` is an invented throwaway story.
   OQ-05.2 (the real book) stays open until Phase 3 nears.

| Batch | Delivered | Commit |
|---|---|---|
| 1 | `pyproject.toml` (ADR-0002 deps, three console scripts), `uv.lock`, ruff config, full package tree as docstring stubs per architecture §8, smoke tests | feat: project skeleton |
| 2 | Templates for every specs §1 file inside `src/novel_engine/templates/book/`; delimited sections empty; prompt template slots ordered stable→volatile | feat: vault templates |
| 3 | `vault/example-book/` — *The Salt Almanac* (tidal-harbour fantasy): 3 characters, 4-chapter manifest (2 written/2 planned), threads T-001 resolved + T-002/T-003 open, author + provisional model facts, 2 chapters with real SHA-256 `generated_hash` values, session audit JSONs incl. a fallback-fired case | feat: example-book fixture |
| 4 | `core/config.py` (Pydantic v2 models + fail-fast validation), `core/outline.py` (manifest parser + next_target), `core/errors.py`; 21 loader/parser tests incl. seeded failures | feat: config loader |
| 5 | `vault.py scaffold_book()` + `cli/new_book.py`; refuses overwrite and bad slugs; freshly scaffolded book passes the loader as-is | feat: new-book scaffolder |

### Verified (Phase 1 exit criteria)

- [x] `uv sync` succeeds from clean state (verified via `git stash -u`)
- [x] `uv run pytest` — 30 passed
- [x] `uv run ruff check .` clean; `ruff format --check` clean
- [x] `new-book --slug test-book` produces a valid tree; second run exits 1
      with actionable message
- [x] Loader validates `example-book`; rejects each seeded malformed case
      (unknown provider, empty model ID, missing env var ×3, POV not in
      index, POV without route, missing character file, missing required
      file, non-kebab filename, bad slug, symlink traversal, duplicate /
      non-contiguous / illegal-status manifest rows)
- [x] `git check-ignore`: no `vault/example-book/` path ignored;
      `vault/real-book/…` still ignored
- [x] threat-model §6 Phase 1 checklist ticked (all three items)
- [x] Fail-fast demonstrated end-to-end: loading without keys raises
      ConfigError naming all three missing vars before any call

### Design notes worth keeping

- `generated_hash` convention: SHA-256 of the body text starting at its
  first heading (everything after frontmatter, leading blanks stripped).
  Fixture hashes are recomputed from committed bodies, so the "has the
  author edited this?" comparison is truthful.
- Empty YAML documents parse as `{}` so the all-comments template index is
  valid; an empty index + empty `pov_models` is legal together, and real
  constraints engage once a manifest names its first POV.
- Env mapping is injected into `load_book_config(..., env=...)`;
  dotenv loading remains a CLI concern (Phase 3 wiring).

### Not done / not attempted

- No provider code, no HTTP calls of any kind (Phase 2)
- No generation logic, no state machine, no style checks
- Nothing pushed to any remote

---

## Next session — start here

**Goal: start Phase 2 — provider layer (base outcomes, router,
Gemini/OpenRouter/Groq).**

### Blocked / waiting on the author

Phase 2 can be *started* without these but not *finished*:

1. **API keys** in local `.env` (all three providers).
2. **OQ-02 verification**: which model IDs are live/free right now, rate
   limits, max output tokens, structured-output support, and specifically
   `gemini-2.5-pro` free-tier status. Record findings as dated comments in
   each book's `config/models.yaml`.

### Read first

1. This file
2. [CLAUDE.md](CLAUDE.md) — operating rules
3. [architecture.md](architecture.md) §6 — provider layer design
4. [pitfalls.md](pitfalls.md) C1–C5 — the outcome taxonomy is a correctness
   requirement, not style
5. [threat-model.md](threat-model.md) §6 Phase 2 checklist

### Batches (proposed)

Commit after each batch. Do not push.

**Batch 1 — outcome types + abstract provider**
- Five normalised outcomes as distinct types (`core/errors.py` or
  `providers/base.py`): success · rate_limited · transient_failure ·
  permanent_failure · model_unavailable
- Only the first three are fallback-eligible; encode that in the type, so
  permanent failure cannot reach the fallback chain by construction

**Batch 2 — router with backoff**
- Fallback chain from `models.yaml`, exponential backoff + jitter +
  `Retry-After` respect from `pipeline.yaml`
- Permanent failure aborts the whole chain immediately

**Batch 3 — concrete providers**
- Gemini AI Studio, OpenRouter, Groq via httpx; dry-run path returns the
  assembled request without sending
- Tests mock HTTP (no live calls); live verification waits on OQ-02

**Batch 4 — audit plumbing**
- Call records shaped like the fixture's session JSONs (provider, model,
  outcome, latency, tokens); redact-by-allowlist logger

### Do not do next session

- Do not write chapter generation logic — Phase 3
- Do not run the prose spike yet (OQ-04) unless the author asks; it needs
  their hand-pasted prompts to be meaningful
