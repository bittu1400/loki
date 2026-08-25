# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-25 · end of Session 3

---

## Current state

**Phase 0 — ✅ complete.**
**Phase 1 — ✅ complete (Session 2).**
**Phase 2 (provider layer) — ✅ complete (Session 3).**
**Phase 3 (single-chapter generation) — ⬜ next.**

The provider stack is live-verified: Router → Provider → API produced a
real generation through the primary route, with audit records captured.
66 tests pass.

---

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq, Mistral, NVIDIA | ✅ complete | — |
| 3 | Single-chapter generation + continuation loop | ⬜ next | OQ-04 done; real book still needed before generating for real |
| 4 | Deterministic style checks | ⬜ | — |
| 5 | Editorial delta pass + reconciler | ⬜ | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 3 — 2026-08-25

### Done

**OQ-02 and OQ-04 resolved empirically** (two spike rounds + JSON probes,
all recorded in open-questions.md):

- Gemini 2.5 family is **closed to new keys** (404). `gemini-3.5-flash-lite`
  works; `gemini-3.7-flash` was persistently 503 during testing.
- Prose spike winner: **minimax-m3** (925/1000 words, best voice and
  continuity). Runner-up: flash-lite (best prose-per-word).
- minimax-m3 also lives on **NVIDIA NIM directly** — the cross-provider
  fallback lane that answers the author's stability requirement.
- Author added keys over the session; final active set in `.env`:
  gemini · openrouter · groq · mistral · nvidia. Dismissed and commented
  out with reasons: cohere (thinking-block overhead, 3x overshoot),
  z.ai (flash-only free tier, overloaded), cerebras (402 despite "free").
- GitHub Models confirmed retired 2026-07-30 — never configure it.

**Phase 2 built in four batches, one commit each:**

| Batch | Delivered |
|---|---|
| 1 | Outcome taxonomy (five frozen dataclasses); fallback eligibility encoded in the type so permanent failures cannot reach the chain |
| 2 | Router: only RateLimited retries in place (honours Retry-After verbatim, then doubling+jitter); transient/unavailable move down immediately; permanent aborts everything |
| 3 | Concrete providers: one OpenAI-compat class for openrouter/groq/mistral/nvidia + a Gemini adapter; status→outcome mapping at the boundary incl. Gemini's bad-key-on-400 quirk; public build_payload() for --dry-run |
| 4 | Audit plumbing: CallRecord shaped like specs §13 `calls` arrays, CallRecorder as the Router's on_attempt subscriber, allowlist-only logging (pitfall C4) |

**Live end-to-end smoke test passed:** all five providers constructed from
env, router walked to the primary route, real generation returned, audit
records written.

### Verified

- [x] threat-model §6 Phase 2 checklist ticked (all three items)
- [x] 66 tests pass; ruff clean
- [x] Editorial JSON probes: gemini flash-lite (`responseMimeType`) and
      mistral-large (`json_object`) both emit valid delta JSON on separate
      quotas from drafting
- [x] Known parser requirements recorded: minimax wraps JSON in code fences;
      mistral normalizes character ids to Upper_Snake — both Phase 5 work

### Final routing (recorded in example-book config/models.yaml)

```
drafting:   ovist-rhoam → openrouter:minimax-m3:free
            brannec-tull → gemini:gemini-3.5-flash-lite
            fallbacks: nvidia:minimax-m3 → groq:gpt-oss-120b
editorial:  gemini:gemini-3.5-flash-lite → mistral:mistral-large-latest
```

### Not done / not attempted

- No chapter-generation logic (Phase 3), no style checks (Phase 4),
  no editorial delta schema (Phase 5), no state machine (Phase 6)
- Nothing pushed to any remote

---

## Next session — start here

**Goal: Phase 3 — single-chapter generation + continuation loop.**

### Blocked / waiting on the author

Nothing technical. But per ADR-0001/OQ-05.2: **the author's real first
book is still undefined.** Generation can be built and tested against
`example-book`, but do not run a real write-session for a real book until
that conversation happens.

### Read first

1. This file, CLAUDE.md
2. [architecture.md](architecture.md) §4 (session flow) and §5 (context assembly)
3. [specs.md](specs.md) §3 (chapter frontmatter), §7–8 (log files), §11 (state machine)
4. Pitfalls B2 (verbatim tail), B6 (episodic pre-resolution), C5 (length assumption)

### Batches (proposed)

Commit after each batch. Do not push.

**Batch 1 — context builder** (`core/context_builder.py`)
- Assemble the prompt from `config/prompt-template.md` slots in order:
  style guide, story bible excerpt, POV sheet, locked facts (retrieval by
  entity from the beat), banned phrases, recent summaries, previous tail
  (~500 words verbatim), beat + instructions
- Respect `pipeline.yaml context` budgets

**Batch 2 — outline target selection**
- Next-target = lowest `planned`; manifest status flip as the sole
  mechanical edit to plot-outline.md

**Batch 3 — drafting loop** (`drafting/generate.py`)
- Call router; measure words vs `target_words ± word_tolerance`;
  continuation rounds up to `max_continuation_rounds`
- Write chapter via vault primitives ONLY; frontmatter per specs §3 with
  assigned_model AND actual_model, generated_hash of body as generated
- Refuse overwrite without `--force`

**Batch 4 — CLI wiring** (`cli/write_session.py`)
- `--book/--chapter/--dry-run/--force` flags; dotenv loading; rich output
- Dry-run prints assembled prompt and exits before any call

### Do not do next session

- Do not generate against any real book (none exists yet)
- Do not start Phase 4 because Phase 3 finished early