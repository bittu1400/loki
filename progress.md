# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-24 · end of Session 1

---

## Current state

**Phase 0 (documentation foundation) — ✅ complete.**
**Phase 1 (vault templates + config loader) — ⬜ not started. Next up.**

No Python code exists yet. The repository contains the build spec, three
independent model analyses of it, and the documentation set that turns
those analyses into a buildable plan.

---

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ⬜ next | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq + retry/fallback/dry-run | ⬜ | OQ-02 to finish |
| 3 | Single-chapter generation + continuation loop | ⬜ | OQ-04 recommended first |
| 4 | Deterministic style checks | ⬜ | — |
| 5 | Editorial delta pass + reconciler | ⬜ | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 1 — 2026-08-24

### Done

**Audit.** Read `prompt.md` and the three model analyses
(`opus-4.8-analysis.md`, `gpt-5.6-terra-analysis.md`,
`gemini-3.7-flash-analysis.md`). Identified their five points of
consensus, graded each analysis, and found the failure mode shared by all
three: they audited the architecture and none questioned whether the core
assumption — that free-tier models produce prose worth reading — holds.
Fourteen additional findings are recorded in [pitfalls.md](pitfalls.md).

**Scaffolding.**
- `.gitignore` — excludes `.env`, Python artefacts, and all real vault
  content except the committed `example-book` fixture
- `.env.example` — three free-tier providers plus deferred publishing
  secrets, with per-key acquisition URLs and data-use warnings
- `.env` — created locally, untracked, awaiting the author's keys

**Documentation.** Ten documents, committed in four batches:

| File | Purpose |
|---|---|
| [decisions.md](decisions.md) | Fast-scan ledger of settled decisions |
| [adr.md](adr.md) | ADR-0001…0004 with context, alternatives, consequences |
| [architecture.md](architecture.md) | Topology, authority model, session flow, context strategy, module layout |
| [specs.md](specs.md) | Concrete contracts: layouts, formats, schemas, state machine, CLI |
| [pitfalls.md](pitfalls.md) | Failure catalogue with severity and countermeasures |
| [threat-model.md](threat-model.md) | Assets, trust boundaries, eight threats, per-phase checklist |
| [best-practices.md](best-practices.md) | Code, prompt, vault, testing, git, session conventions |
| [open-questions.md](open-questions.md) | OQ-01…08 with blocking status and recommendations |
| [progress.md](progress.md) | This file |
| [CLAUDE.md](CLAUDE.md) | Operating instructions for future sessions |

### Decisions made

Four ADRs, recorded at the moment each was made:

1. **ADR-0001** — v1 is the core pipeline only. Publishing endpoint,
   Actions cron, and the `new_book.py` interview CLI are deferred.
2. **ADR-0002** — `uv` + `pyproject.toml` + Pydantic v2 + `ruff` + `pytest`.
3. **ADR-0003** — one chapter per session, manually triggered.
4. **ADR-0004** — vault at `vault/<book-slug>/` in-repo; real manuscripts
   gitignored, `vault/example-book/` committed as the test fixture.

### Deliberate departures from `prompt.md`

Each is documented with rationale at the point of use. Listed here so they
are not mistaken for oversights:

| Departure | Where |
|---|---|
| Previous chapter's final ~500 words injected verbatim, not just summaries | [architecture.md](architecture.md) §5 |
| Locked facts retrieved by entity, not dumped wholesale | [architecture.md](architecture.md) §5 |
| `models.yaml` split from `pipeline.yaml`; `auto_publish` moves out of model config | [specs.md](specs.md) §10 |
| Editorial pass also receives the beat and the POV character sheet | [specs.md](specs.md) §12 |
| Style measured deterministically in Python, not judged by an LLM | [specs.md](specs.md) §14 |
| Suggested canon patches written to a file, not printed to stdout | [specs.md](specs.md) §12 |
| `deepen_queue.md` → `deepen-queue.md` (kebab-case throughout) | [specs.md](specs.md) §1 |
| Per-book vault layout is authoritative; the root-level layout is void | [specs.md](specs.md) §1 |
| One chapter per session, not two | ADR-0003 |
| No `pacing_score` in the editorial schema | [specs.md](specs.md) §12 |

### Verified

- `git check-ignore -v .env` → confirms `.env` is ignored
- `git status --short` → clean after every commit
- Five commits, each one task, none pushed

### Not done / not attempted

- No Python code, no `pyproject.toml`, no tests — Phase 1 work
- No vault directory created yet, including `example-book`
- No API keys present; no provider has been called
- Nothing pushed to any remote

---

## Next session — start here

**Goal: complete Phase 1 — vault templates, config loader, and the
`example-book` fixture.**

### Read first

1. This file
2. [CLAUDE.md](CLAUDE.md) — operating rules
3. [decisions.md](decisions.md) — what is already settled, do not relitigate
4. [specs.md](specs.md) §1–10 — the exact formats to implement
5. [open-questions.md](open-questions.md) — OQ-03 and OQ-05 are in scope

### Ask before starting

- **OQ-03** — confirm the `models.yaml` / `pipeline.yaml` split. Low risk,
  one-line answer, but it shapes the config loader.
- **OQ-05.1** — confirm that `example-book` should be an invented throwaway
  story rather than the author's real one. Recommended: invented.

Ask both together in one batch, with recommendations, before writing code.

### Batches

Commit after each batch. Do not push.

**Batch 1 — project skeleton**
- `pyproject.toml` with the ADR-0002 dependency set, console-script entry
  points for `write-session` / `new-book` / `check-style`
- `uv.lock` via `uv sync`
- `ruff` configuration
- `src/novel_engine/` package tree per [architecture.md](architecture.md) §8,
  modules stubbed with docstrings only
- `tests/` with one smoke test that imports the package

**Batch 2 — vault templates**
- Blank markdown templates for every file in [specs.md](specs.md) §1, with
  the delimited sections (`MANIFEST`, `FACTS`, `THREADS`, `QUEUE`) already
  present and empty
- `characters/index.yaml` template
- `config/prompt-template.md` with named slots in the order specified in
  [best-practices.md](best-practices.md) §2

**Batch 3 — `example-book` fixture**
- A complete, realistic, invented book under `vault/example-book/`
- Manifest with mixed statuses (`written`, `planned`), non-trivial names,
  at least one resolved thread and one open one, at least one
  `origin: model` fact alongside `origin: author` facts
- Two or three short chapters with full frontmatter per
  [specs.md](specs.md) §3
- Verify it is actually committed despite the `vault/*` ignore rule:
  `git check-ignore -v vault/example-book/canon/story-bible.md` must
  report **no match**

**Batch 4 — config loader**
- Pydantic models for `models.yaml` and `pipeline.yaml`
- Startup validation: providers known, model IDs present, required env vars
  set, every manifest `pov` resolves to a character in `index.yaml`, all
  filenames kebab-case, vault paths resolve under the book root
- Fail fast with actionable messages, before any API call
- Tests against `vault/example-book/`, including the failure cases

**Batch 5 — `new-book` scaffolder**
- Creates `vault/<slug>/` from the templates and exits (ADR-0001 — it is a
  scaffolder, not an interview)
- Refuses to overwrite an existing book directory

### Phase 1 exit criteria

- [ ] `uv sync` succeeds from a clean checkout
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` clean
- [ ] `new-book --slug test-book` produces a valid tree
- [ ] Config loader validates `example-book` and rejects each seeded
      malformed case with a clear message
- [ ] `vault/example-book/` is committed; real vault paths are still ignored
- [ ] [threat-model.md](threat-model.md) §6 Phase 1 checklist passes
- [ ] `progress.md` updated for Session 3

### Do not do next session

- Do not call any provider API — that is Phase 2
- Do not write generation logic — that is Phase 3
- Do not start Phase 2 because Phase 1 finished early
