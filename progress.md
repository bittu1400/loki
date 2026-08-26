# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-26 · end of Session 5

---

## Current state

**Phases 0–2 — ✅ complete.**
**Phase 3 (single-chapter generation) — ✅ complete (Session 5), verified
against live providers.**
**Phase 4 (deterministic style checks) — ⬜ next. Nothing started.**

The full drafting path works end-to-end: `write-session --book
example-book` resolves the manifest target, assembles context, drafts via
minimax-m3 (openrouter → nvidia → groq fallback), writes a hash-verified
chapter, flips the manifest, and records an audit JSON. Real-run proof:
chapters 003 and 004 were generated and committed into the fixture.

Provider stack final state after Session 4: six provider modules built;
routing is **unchanged from Session 3** for drafting
(openrouter:minimax-m3:free primary, nvidia → groq fallbacks) and
editorial (gemini flash-lite → mistral-large). The aihubmix fallback slot
added earlier on Session 4 was **removed again the same day** after its
free tier proved to be ~10 lifetime requests unrecharged. 67 tests pass,
ruff clean.

---

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq, Mistral, NVIDIA (+AiHubMix S4, demoted from routing same day) | ✅ complete | — |
| 3 | Single-chapter generation + continuation loop | ✅ complete (S5) | — |
| 4 | Deterministic style checks | ⬜ next | — |
| 5 | Editorial delta pass + reconciler | ⬜ | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 5 — 2026-08-26

### Done

**Phase 3 complete in four batches, all committed separately:**

1. **Batch 1 — `core/context_builder.py`**: strict fact-line parsing
   (malformed line → ContextError, never silently dropped); entity
   retrieval (POV-scoped + beat-named character facts first, then
   unscoped facts naming them; capped at max_locked_facts); verbatim
   previous-chapter tail via regex word spans; summary slicing; banned-
   phrase extraction; template filling strictly in file order with
   unknown-slot/value-without-slot failing loudly.
2. **Batch 2 — vault write primitives + `outline.resolve_target()`**:
   `write_chapter` create-only with O_EXCL semantics, owns
   generated_hash (hashes exact stored bytes, re-reads to verify);
   `flip_manifest_status` byte-surgical single-cell splice with post-write
   verification; override selects existing manifest rows only.
3. **Batch 3 — `drafting/generate.py` + provenance**: continuation loop
   (full prompt + partial draft re-sent, hard-capped), fallback tracking,
   ADR-0005 failed-stub terminal case, frontmatter per specs §3.
4. **Batch 4 — `cli/write_session.py`**: --dry-run prints prompt and
   exits before provider construction; overwrite refusal; --force needs
   interactive typed confirmation (no TTY → refuse closed); audit JSON;
   exit 1 on failed-stub.

**Real-run verification (author approved the quota spend):**

- ch-003: 1459 words via openrouter:minimax-m3:free, no fallback,
  hash verified, audit sess-20260826-0251-f873.
- ch-004: 1474 words via gemini:gemini-3.5-flash-lite (the second run
  correctly advanced to the next planned target — this was accidental
  but exercised exactly the right behaviour).
- Overwrite refusal confirmed live: `--chapter 3` without `--force`
  exits 1.
- Manifest git diff shows only the two status cells changed.
- Both chapters + audits + manifest flip COMMITTED into the fixture
  (author decision) so future context runs retrieve a richer vault.

### Verified

- [x] 131 tests pass; ruff clean (after every batch)
- [x] All Phase 3 exit criteria ticked, including the two live-provider
      items and the simulated failure paths (fakes)
- [x] threat-model §6 Phase 3 items: capped loop tested, overwrite
      refusal tested live

### Not done / not attempted

- Phase 4 (style checks): nothing started
- No next-step.md state machine wiring (Phase 6 concern)
- Nothing pushed to any remote

---

## Session 4 — 2026-08-25

### Done

**Provider roster settled empirically (decisions.md #9–12):**

| Provider | Verdict |
|---|---|
| AiHubMix | Built as 6th provider (`providers/aihubmix.py`, live-verified) — then **demoted from routing**: free tier = ~10 lifetime requests unrecharged, then abuse-string responses. Kept only as emergency manual lane. |
| Requesty | Two keys tried, both rejected; **both start `rqsty-sk-` but real Requesty keys start `rqy_`** (requesty.ai/auth.md). Commented out of `.env` with instructions. Its 12 genuinely $0 models remain interesting IF a valid key ever appears — then run the prose spike on nemotron-3-super-120b-a12b / gemma-4-31b-it before any routing change. |
| Chutes | Dismissed: real catalog is paid TEE models at llm.chutes.ai (NOT api.chutes.ai); account balance $0. |
| SiliconFlow | Dismissed: MiniMax-M3 is paid (~$1 starter grant); permanently-$0 list rotated away mid-week (402 / model disabled, verified live). |
| NanoGPT | Dismissed: zero free models in 628-model catalog, balance $0. |
| Fireworks | Dismissed: account suspended (billing). |
| Portkey | Dismissed: paid gateway fronting other providers' keys; redundant with our Router. |

**OQ-04 spike re-run (author-requested full sweep of new catalogs):**
identical ch-003 prompt, ~1000-word target, zero-cost models only.
Best newcomer `gemini-3.7-flash-free` (878 words, good voice, truncated
ending, invented Brannec's age) — a **draw vs minimax-m3**, so per the
author's rule routing did not change. Full results table in
open-questions.md OQ-04. Spike harness: `/tmp/opencode/spike/run_spike.py`
(ephemeral; methodology documented in open-questions.md).

**NVIDIA NIM key expiry recorded** (pitfalls.md C7 + .env + .env.example):
NIM keys die ~6 months after creation; sudden nvidia 401s = check calendar
first.

**ADR-0005 written:** all-providers-failed terminal case → write clearly-
marked `failed-stub` chapter at zero cost, manifest stays `planned`,
downstream treats stubs as absent. Implementation is Phase 3 Batch 3 work.

### Verified

- [x] 67 tests pass; ruff clean (after every change)
- [x] aihubmix live generation through our provider class succeeded before
      its cap exhausted (later confirmed dead same day)
- [x] Every dismissal above verified against the live API, not docs alone
- [x] Routing after all changes: drafting minimax-m3 via openrouter →
      nvidia → groq; editorial gemini flash-lite → mistral-large

### Not done / not attempted

- Phase 3 itself: no context builder, no chapter primitive, no drafting
  loop, no CLI — nothing started
- No valid Requesty key (author to supply an `rqy_...` key if desired)
- Nothing pushed to any remote

---


## Next session — start here

**Goal: Phase 4 — deterministic style checks (`quality/style_checks.py`
+ `check-style` CLI). Nothing started; begin by reading specs.md §14.**

### Blocked / waiting on the author

1. Nothing technical blocks Phase 4: it is pure Python over existing
   chapters, zero API cost.
2. Style thresholds live in each book's style-guide.md, not in code
   (specs §14). The example-book style guide currently has rhythm
   targets but no explicit numeric thresholds for adverb rate,
   type-token ratio, or dialogue ratio — decide whether the fixture
   gains a thresholds block (recommended) or checks stay advisory-only
   with defaults.
3. Non-blocking: author may still supply a real Requesty key
   (`rqy_...`) → spike its 12 free models before any routing change.

### Read first

1. This file, CLAUDE.md
2. [specs.md](specs.md) §14 (metrics table) and §15 (`check-style` flags)
3. Pitfalls B3 (measure, don't ask a model) and B5 (author-edit diff via
   generated_hash — feeds suggested style-guide additions)
4. [architecture.md](architecture.md) §7 (quality loops)

### What now exists (module map)

```
src/novel_engine/
  core/config.py        # BookConfig.load_book_config(vault_root, slug, env)
  core/outline.py       # parse_manifest(), next_target(), resolve_target()
  core/context_builder.py  # parse_facts, select_facts, previous_chapter_tail,
                        #   recent_summaries, banned_phrases, build_prompt
  core/vault.py         # scaffold_book, write_chapter, flip_manifest_status,
                        #   generated_hash, split_chapter_file, chapter_path
  core/errors.py        # NovelEngineError, ConfigError, ContextError, VaultError
  core/state_machine.py # STUB — Phase 6 work
  drafting/generate.py  # draft_chapter(): continuation loop, ADR-0005 stubs
  drafting/provenance.py# make_session_id, chapter_frontmatter, utc_timestamp
  providers/*           # unchanged since Session 4
  cli/new_book.py       # uv run new-book --slug X [--vault-root D]
  cli/write_session.py  # WORKING: --book --chapter --dry-run --force
  quality/style_checks.py # STUB — Phase 4 next session
vault/example-book/     # fixture; chapters 001-004 exist, next planned: NONE
```

NOTE: the fixture manifest is now fully written (001-004). To exercise
drafting paths again, add a ch-005 row to plot-outline.md first.

Env keys active in `.env`: gemini, openrouter, groq, mistral, nvidia,
aihubmix (emergency lane only). Routing truth:
`vault/example-book/config/models.yaml`.

### Batches (proposed for Phase 4)

Commit after each batch. Do not push.

**Batch 1 — metrics module** (`quality/metrics.py`, pure functions):
banned-phrase hits, sentence-length mean/stdev, adverb rate per 1000,
type-token ratio, dialogue ratio, repeated openings, paragraph-length
distribution, em-dash/semicolon rate, word count vs target. No IO.

**Batch 2 — threshold parsing + report**: read optional numeric
thresholds from style-guide.md; compare and flag; produce a structured
report dict.

**Batch 3 — CLI wiring** (`check-style --book <slug> --chapter N`):
print the report via rich; exit non-zero only on hard errors, never on
metric values (advisory per specs §14).

### Phase 4 exit criteria

- [ ] pytest passes; ruff clean (every session)
- [ ] All metrics computed correctly against committed chapters 001-004
      with hand-computed expected values in tests
- [ ] check-style runs zero-cost on any existing chapter
- [ ] No API dependency anywhere in the quality package

### Do not do next session

- Do not generate against any real book (none exists yet)
- Do not re-add aihubmix to routing (cap is lifetime, not daily)
- Do not chase the dismissed providers without NEW evidence; reasons are
  dated in `.env`
- Do not start Phase 5 (editorial pass) — blocked on OQ-01 real vaults
- Do not wire next-step.md resume state (Phase 6)
