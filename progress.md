# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-25 · end of Session 4

---

## Current state

**Phase 0 — ✅ complete.**
**Phase 1 — ✅ complete (Session 2).**
**Phase 2 — ✅ complete (Session 3), extended in Session 4.**
**Phase 3 (single-chapter generation) — ⬜ next. Nothing started.**

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
| 3 | Single-chapter generation + continuation loop | ⬜ next | OQ-04 done; real book still needed before generating for real |
| 4 | Deterministic style checks | ⬜ | — |
| 5 | Editorial delta pass + reconciler | ⬜ | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

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

**Goal: Phase 3 — single-chapter generation + continuation loop.
Nothing has been started; begin at Batch 1.**

### Blocked / waiting on the author

1. Nothing technical blocks Batches 1–4 against `example-book`.
2. Per ADR-0001/OQ-05.2: the author's real first book is still undefined.
   Build and test against `example-book`; do NOT run write-session on a
   real book until that conversation happens.
3. Optional, non-blocking: author may supply a real Requesty key
   (must literally start `rqy_`) → then spike its 12 free models first.

### Read first

1. This file, CLAUDE.md
2. decisions.md #9–12 (provider verdicts — do not relitigate)
3. [architecture.md](architecture.md) §4 (session flow), §5 (context assembly), §6 (provider layer)
4. [specs.md](specs.md) §3 (chapter frontmatter), §7–8 (log files), §11 (state machine)
5. Pitfalls B2 (verbatim tail), B6 (episodic pre-resolution), C5 (length assumption), C7 (NVIDIA key expiry)
6. [adr.md](adr.md) ADR-0005 (failed-stub terminal case — Batch 3 must implement it)

### What now exists (module map)

```
src/novel_engine/
  core/config.py        # BookConfig.load_book_config(vault_root, slug, env) — DONE+TESTED
                        # KNOWN_PROVIDERS now includes aihubmix
  core/outline.py       # parse_manifest(), next_target() — DONE+TESTED
  core/vault.py         # scaffold_book() only; chapter primitives are Phase 3 work
  core/errors.py        # NovelEngineError, ConfigError
  providers/base.py     # Outcome taxonomy + Provider ABC
  providers/openai_compat.py  # serves openrouter/groq/mistral/nvidia/aihubmix
  providers/gemini.py   # generateContent adapter
  providers/{openrouter,groq,mistral,nvidia,aihubmix}.py  # base URLs + build()
  providers/router.py   # Router(providers, routes, retry, generation_params, on_attempt=...)
  providers/audit.py    # CallRecord / CallRecorder / allowlist logging
  cli/new_book.py       # WORKING: uv run new-book --slug X [--vault-root D]
templates/book/         # packaged vault templates (scaffolder source)
vault/example-book/     # fixture; next planned chapter is ch-003 (ovist-rhoam)
```

Env keys active in `.env`: gemini, openrouter, groq, mistral, nvidia,
aihubmix (emergency lane only — ~10-request lifetime cap hit; do NOT put
it back in routing). Dismissed/commented with reasons: cohere, z.ai,
cerebras, chutes, siliconflow, nanogpt, fireworks, portkey, requesty.
Routing truth: `vault/example-book/config/models.yaml`.

### Batches (proposed — unchanged from Session 3 planning)

Commit after each batch. Do not push.

**Batch 1 — context builder** (`core/context_builder.py`)
- Fill `config/prompt-template.md` slots IN FILE ORDER (stable→volatile):
  `{{style_guide}}`, `{{story_bible}}`, `{{character_sheet}}`,
  `{{locked_facts}}`, `{{banned_phrases}}`, `{{recent_summaries}}`,
  `{{previous_tail}}`, `{{pov_character}}`, `{{beat}}`,
  `{{chapter_instructions}}`
- Locked facts retrieved by entity: select tracker lines whose category
  touches the POV id or entities named in the beat; cap at
  `pipeline.yaml context.max_locked_facts`
- Previous tail = last `context.previous_chapter_tail_words` words of the
  highest existing chapter, VERBATIM (pitfall B2)
- Parse FACTS lines with the line grammar from continuity-tracker.md header

**Batch 2 — outline target + vault chapter primitive**
- `outline.next_target()` already exists and is tested; wire it
- Add a chapter-writing primitive to `core/vault.py` (the one-writer rule
  means cli/drafting may not open files for writing): create
  `chapters/chapter-NNN.md` only if it does not exist; refuse overwrite
  unless told otherwise by the caller. Also flip manifest status via the
  MANIFEST section's single permitted mechanical edit (status field only)
- `generated_hash` convention (established Session 2, used by fixture):
  SHA-256 of everything after frontmatter, leading blank lines stripped

**Batch 3 — drafting loop** (`drafting/generate.py`)
- Build router from `build_providers(env)` + book's models.yaml routes:
  pov route first, then fallback_chain
- Measure words vs `target_words ± word_tolerance`; if short, continuation
  prompt appends the partial draft and asks to continue; hard-capped at
  `max_continuation_rounds`
- Frontmatter per specs §3: BOTH `assigned_model` and `actual_model`
  (Success.model_id), `fallback_triggered`, `continuation_rounds`,
  token counts from the outcome, `generated_hash` of body-as-generated
- **Implement ADR-0005**: when every route is exhausted, still write a
  clearly-marked failed-stub chapter locally (zero cost, manifest stays
  `planned`, status `failed-stub`, last error per provider in frontmatter);
  re-run with `--force` replaces it
- Word-count reality check (OQ-06/C5): flash-lite undershoots (~78%),
  mistral large badly (~35%) — continuation loop is load-bearing, not
  cosmetic

**Batch 4 — CLI wiring** (`cli/write_session.py`)
- Flags per specs §15: `--book --chapter --dry-run --force`; load dotenv
  before building providers; rich console output; audit records written to
  `log/sessions/<id>.json` on real runs
- Dry-run prints assembled prompt and exits BEFORE any provider call

### Phase 3 exit criteria

- [ ] `uv run pytest` passes; ruff clean (every session)
- [ ] `write-session --book example-book --dry-run` prints a complete
      assembled prompt using the template slots and spends nothing
- [ ] A full real run against `example-book` produces `chapter-003.md`
      (next planned target, pov ovist-rhoam) with valid frontmatter, hash
      matching its body, both model fields recorded, and an audit JSON in
      `log/sessions/`
- [ ] Second run without `--force` refuses to overwrite chapter-003
- [ ] Manifest status flips planned→written for ch-003 and nothing else in
      plot-outline.md changes (verify with git diff)
- [ ] Simulated failure: primary route returns RateLimited → fallback fires
      and `fallback_triggered: true` lands in frontmatter (test with fakes)
- [ ] Simulated total failure: ALL routes fail → failed-stub chapter per
      ADR-0005, manifest unchanged (test with fakes)
- [ ] threat-model §6 Phase 3 checklist items pass (hard-capped loop;
      overwrite refusal)

Tick only after actually running each item. The real-run item spends 1–4
requests of the OpenRouter daily cap — do it once, not repeatedly;
iterate on the prompt with --dry-run first.

### Do not do next session

- Do not generate against any real book (none exists yet)
- Do not re-add aihubmix to routing (cap is lifetime, not daily)
- Do not chase the dismissed providers (chutes/siliconflow/nanogpt/
  fireworks/portkey) without NEW evidence; reasons are dated in `.env`
- Do not start Phase 4 because Phase 3 finished early