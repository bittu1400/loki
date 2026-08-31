# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-08-31 · end of Session 7

---

## Current state

**Phases 0–2 — ✅ complete.**
**Phase 3 (single-chapter generation) — ✅ complete (Session 5), verified
against live providers.**
**Phase 4 (deterministic style checks) — ✅ complete (Session 7), run
live against the committed chapters at zero cost.**
**Phase 5 (editorial delta pass + reconciler) — ⬜ next.** Fixture-safe;
still blocked against any real vault by OQ-01.

The full drafting path works end-to-end: `write-session --book
example-book` resolves the manifest target, assembles context, drafts via
minimax-m3 (openrouter → nvidia → groq fallback), writes a hash-verified
chapter, flips the manifest, and records an audit JSON. Real-run proof:
chapters 003 and 004 were generated and committed into the fixture.

`check-style --book example-book --chapter N` now measures any existing
chapter with no API key present at all. **187 tests pass, ruff clean.**

Provider stack gained one lane this session (ADR-0006): drafting
openrouter:minimax-m3:free → nvidia → groq → **local llama.cpp**;
editorial gemini flash-lite → mistral-large, unchanged. The prompt
template gained a rhythm block (decision #23), verified live on both
gemma-4-12b and minimax-m3.

---

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq, Mistral, NVIDIA (+AiHubMix S4, demoted from routing same day) | ✅ complete | — |
| 3 | Single-chapter generation + continuation loop | ✅ complete (S5) | — |
| 4 | Deterministic style checks | ✅ complete (S7) | — |
| 5 | Editorial delta pass + reconciler | ⬜ next | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 7 — 2026-08-31

**Phase 4 complete in three batches, all committed separately.** One
author decision was taken first and written before any code (OQ-09).

### Done

**Decision first (decisions.md #22, `d194f5b`).** Style-check thresholds
live in a `<!-- THRESHOLDS -->` delimited block in each book's
`canon/style-guide.md`, parsed with the same marker discipline as
MANIFEST and FACTS. **No block ⇒ metrics reported, verdicts skipped;
there are no built-in numeric defaults in code.** Built-in defaults were
the tempting shortcut — every chapter would get a verdict — and were
rejected because an untuned book would then look tuned, and the creative
constant would live in the engine. OQ-09 struck through.

**Batch 1 — `quality/metrics.py` (`9344685`).** All nine specs §14
metrics as pure functions over a chapter body: no IO, no provider
imports, no verdicts. Tokenisation calls that hand-computed tests depend
on: headings, list items and block quotes are dropped before counting
(the chapter title never becomes a sentence); the sentence splitter
over-splits on abbreviations, accepted because a few extra boundaries
move a rhythm mean by well under a word; `word_count` re-implements
`generate.word_count`'s `split()` convention rather than importing it,
so `quality/` stays free of provider imports.

**Batch 2 — thresholds + report (`dc658fb`).** `parse_thresholds`,
`judge`, `build_report`, `StyleCheckError`. Absence is silent;
malformation raises (unknown metric, non-numeric bound, inverted band,
row bounding nothing, duplicate row, unterminated block). Collection
metrics and `target_words` are unbandable by construction. The fixture
style guide gained a block that deliberately leaves `type_token_ratio`
and `words_vs_target` unbanded, with the reason written beside it — TTR
falls with chapter length, and shortfall is already the continuation
loop's job.

**Batch 3 — `cli/check_style.py` (`b41c930`).** `check-style --book
--chapter [--vault-root]`, rich table, advisory output. Bypasses
`load_book_config` (which validates provider keys) on purpose:
`target_words` comes from the chapter's own frontmatter, so a
measurement pass runs on a machine with no keys. Entry point moved from
`quality.style_checks:main` to `cli.check_style:main`.

**Doc pass:** specs §14 gained the THRESHOLDS block format and the
absent/malformed rule; specs §15 gained the `check-style` behaviour and
an updated status line; architecture §8 module map updated (and a
duplicated "Layout rationale" paragraph removed).

### Verified

- [x] 187 tests pass (132 → 150 → 170 → 177 across Phase 4's batches, 186
      with the local lane, 187 with the author-edit hash test), ruff clean
      after every batch
- [x] `check-style --book example-book --chapter 4` run live: 1474 words,
      flags `sentence_length_mean` low and `dialogue_ratio` high, exit 0
- [x] A test deletes every provider key from the environment and asserts
      the CLI still measures — Phase 4's "no API dependency" criterion
- [x] Fixture bands leave hand-written chapters 001–002 clean and flag
      only the two live-generated chapters, on exactly the drifts the
      style guide's prose warns about
- [x] Exit codes: 0 for out-of-band metrics, 1 for missing chapter and
      for a malformed thresholds block

### Addendum — local model spike, rhythm block, local lane (same session)

Author-requested, out of phase: "I have gemma 4 12B loaded locally, try it
once." It turned into two decisions and one routing change.

**The spike (`/tmp` scratchpad, ephemeral).** Identical ch-003 prompt,
local llama.cpp on `localhost:8080`, measured with the Phase 4 metrics
that had just been built. Full table in open-questions.md OQ-04.

| Draft | Words | Sentence mean | "He" openings | Thresholds failed |
|---|---|---|---|---|
| minimax-m3 ch-003 (committed) | 1451 | 19.6 | 24 / 74 | 1 |
| gemma-4-12b, prompt as-is | 1389 | 9.7 | 58 / ~143 | 1 |
| gemma-4-12b + rhythm block | 1140 | 12.4 | 35 / ~92 | 0 |
| minimax-m3 ch-005 + rhythm block (live) | 1128 | 17.1 | 19 / 66 | 0 |

**Decision #23 — rhythm block in the prompt template (`548f028`).** The
staccato was the prompt, not the model. The block now ships in both the
packaged scaffolder template and the fixture, at the very end of the
prompt where it was measured. Verified live on minimax-m3 (`aa83831`,
ch-005): its opposite defect corrected too, 19.6 → 17.1 mean and 1.45x →
1.13x of target, every threshold met.

**Decision #24 / ADR-0006 — local lane (`548f028`).** `providers/local.py`
over the existing OpenAI-compatible client, keyless, appended to the
drafting fallback chain BELOW groq. Adopted for availability, not prose:
no quota, no rate limit, nobody else can withdraw it. Dead whenever the
laptop server is not running, which is why it is last.

Implementation notes worth keeping:

- `api_key=None` now means "send no Authorization header" (an empty
  bearer token is worse than none).
- A refused connection is `ModelUnavailable`, not `TransientFailure`,
  across every OpenAI-compatible provider — retrying in place cannot
  start a server, but another provider can answer. Both are
  fallback-eligible, so invariant 3 is unaffected; this is about the
  audit log being truthful.
- The local provider clamps `max_tokens` to fit the server's context
  window and refuses before the request leaves the machine when under
  512 tokens remain. This matters for the continuation loop, which
  re-sends the full prompt plus the partial draft.
- `LOCAL_BASE_URL` / `LOCAL_CONTEXT_WINDOW` documented in `.env.example`;
  `LOCAL_CONTEXT_WINDOW` must match the server's `-c`.
- Live smoke through our own provider class succeeded. The server echoes
  the **GGUF file path** as the model ID, so provenance records what was
  requested, not what ran — the weakness ADR-0006 predicted, confirmed.

**Reasoning check (author-requested follow-up).** gemma-4-12b is a
reasoning model and its thinking was suppressed for both earlier drafts —
not by our code but by the GGUF's chat template, which defaults
`enable_thinking` to false and emits a pre-closed thought channel when
off. Enabled it via `chat_template_kwargs` and re-ran the same prompt:

| | Tokens | Seconds | Words | Sentence mean | Thresholds failed |
|---|---|---|---|---|---|
| thinking OFF | 1406 | 35 | 1140 | 12.4 | 0 |
| thinking ON | 2875 | 70 | 1101 | 10.9 | 1 |

2x cost for a worse draft. The trace restated every rule and checked each
banned phrase by name, then broke the rhythm rule anyway — awareness is
not obedience. Stays off for drafting; recorded as pitfalls C8 (the
template silently deciding capability) and C9 (reasoning ≠ compliance).
Worth measuring for the Phase 5 editorial pass, where the deliverable is
a judgement rather than prose. No code changed: our provider does not
send `chat_template_kwargs`, and llama.cpp returns reasoning in a
separate `reasoning_content` field, so a chapter body could never have
been polluted by it.

**Read-through of all five drafts (author-requested).** Craft ranking:
minimax ch-005 (rhythm) > minimax ch-003 > gemma+rhythm > gemma plain >
gemma+thinking. The metrics ranked gemma+rhythm FIRST and minimax ch-003
below it — the opposite order. Metrics catch AI-prose tells, not quality;
a draft can pass every threshold while over-explaining its own theme.
Concrete support for specs §14 keeping them advisory forever.

Three defects only reading caught: gemma+thinking referring to "Chapter 1"
inside the prose and describing the POV's own hair from outside; gemma
plain naming Brannec Tull in Ovist's head against the outline's premise;
and **ch-005 contradicting itself — "Both of them" then "There were nine"
against ch-001's two corrections.** That last one is committed in the
fixture and is a ready-made Phase 5 test case.

**ch-005 contradiction fixed (decision #25).** One sentence rewritten by
hand so nine countersignings and two corrections stop being the same
number. `generated_hash` was deliberately **left stale**: specs §3 makes
it immutable so the mismatch reports "the author edited this" (pitfalls
B5), and recomputing it to make a test pass would have destroyed the
Phase 6 signal. `tests/test_vault_writing.py` now asserts both halves of
that contract — unedited chapters match, `AUTHOR_EDITED_CHAPTERS` must
not — so a broken edit-detector fails a test instead of passing quietly.

**Two gaps this surfaced (neither fixed):**

1. The banned-phrase check matches literal strings, so descriptive rules
   ("'symphony' applied to anything not musical") do not catch cousins
   like "a recurring silence in the music of the Office".
2. Both rhythm-block drafts came in at ~zero dialogue (0.002, 0.000).
   Defensible per beat, but only `dialogue_ratio`'s upper bound is
   banded. A minimum would catch it if the pattern holds.

Also noted, not changed: `--dry-run` is refused when the target chapter
already exists, because the overwrite gate runs first. A dry-run writes
nothing, so this is stricter than decision #17 requires.

### Not done / not attempted

- Hand-computed expected values are asserted on a small purpose-built
  sample (paragraph lengths, sentence count, every rate). Against the
  committed chapters 001–004 the tests assert invariants and
  frontmatter agreement (`actual_words` vs measured body) plus exact
  flag sets — not a hand-count of all nine metrics per chapter
- No editorial or Phase 5 work
- The local lane's prose evidence is ONE prompt and ONE seed. It has
  never drafted a brannec-tull chapter, never run through the
  continuation loop, and never been reached by a real fallback
- The two gaps above are recorded, not fixed
- Reasoning was NOT measured for the editorial pass — only for drafting
- Nothing pushed

---

## Session 6 — 2026-08-29

Out-of-phase session. The author added a new provider key and asked which
of its free models the project could use. No Phase 4 work was started, and
no code was touched.

### Done

**TokenRouter evaluated and dismissed (decisions.md #21).**

| Finding | Detail |
|---|---|
| Base URL | `https://api.tokenrouter.com/v1` — a one-api relay, OpenAI-compatible. |
| Namespace trap | `api.tokenrouter.**io**` is an unrelated service that rejects these keys and demands `tr_...`. Three of the five hosts probed responded at all; only the `.com` one recognised the key. |
| Key state | **Dead.** Every call returns `[sk-gec***EZY] 该令牌额度已用尽 … RemainQuota = 0`. |
| Why free models do not escape it | one-api checks the *token's own* RemainQuota **before** it consults model pricing, so `model_ratio: 0` is not an exemption. Verified with live POSTs against all three zero-priced models, not inferred from the `/models` 401. |
| Catalog ceiling | 3 of 133 models are $0: `z-ai/glm-5.3-free` (only plausible drafting lane), `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (nano reasoning — the thinking-block overhead that dismissed Cohere), `stealth/ox-alpha` (unnamed, no metadata, no stability guarantee). Cheapest paid lane `openai/gpt-oss-120b` at ratio 0.0195 — still fails the 0-cost bar. |
| Verdict | Dismissed even though the quota is repairable (panel → token → unlimited quota). One free model behind a relay whose quota already died once is the AiHubMix shape from #12 and fails the same stability condition. |

Catalog came from the provider's public `/api/pricing` endpoint, which
needs no auth — worth remembering for future one-api relays: the model
list is readable even when the key is not usable.

**Docs:** `.env` key commented out with a dated block in the house style
(decision #8 requires this); decisions.md #21 recorded. Committed as
`74ee8e1` (docs-only; `.env` is gitignored).

### Verified

- [x] All three free models POSTed live — identical quota rejection
- [x] Five candidate hosts probed before settling on the `.com` relay
- [x] Catalog counts (133 total / 3 free) read from the live pricing endpoint

### Not done / not attempted

- Phase 4: still nothing started — this session added no code and no tests
- Test suite not re-run (no code changed; last known state 132 pass, ruff clean)
- No routing change, no provider module, no `.env.example` entry — a
  dismissed provider gets no scaffolding
- Nothing pushed

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

- [x] 132 tests pass; ruff clean (after every batch; one more added when
      `DRY_RUN=1` support closed a specs §15 gap in the code)
- [x] All Phase 3 exit criteria ticked, including the two live-provider
      items and the simulated failure paths (fakes)
- [x] threat-model §6 Phase 3 items: capped loop tested, overwrite
      refusal tested live

**End-of-session doc pass (this session's closing batch):**

- decisions.md #13–20 recorded: loud-fail canon reads, retrieval rule,
  generated_hash stored-bytes ownership, byte-surgical flips, two-layer
  overwrite protection, plain-print dry-run, exit-code policy, fixture
  growth + test decoupling
- specs.md §3 (hash convention as implemented, failed-stub fields) and
  §15 (flag behaviours, exit codes, audit JSON shape) reconciled with
  code; the one mismatch found (`DRY_RUN=1` promised but unimplemented)
  was fixed in code, not bent in docs (+1 test)
- architecture.md §8 module map rewritten to the exact file list;
  threat-model §6 Phase 3 checklist items ticked with evidence
- open-questions.md OQ-09 added (style thresholds — blocks Phase 4
  Batches 2–3)

### Not done / not attempted

- Phase 4 (style checks): nothing started beyond planning notes below
- No next-step.md state machine wiring (Phase 6 concern)
- Nothing left unpushed: all commits are on origin/main

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

**Goal: Phase 5 — editorial delta pass + reconciler
(`editorial/{schema,pass_runner,reconciler}.py` + the four vault append
primitives). Nothing started. Begin by reading specs.md §5–7 and
invariant 1 in CLAUDE.md.**

Phase 5 is the first component that writes to canon. Invariant 1 (no
model ever writes a canon file body) and invariant 2 (fail closed) are
the whole design, not commentary.

### Blocked / waiting on the author

1. **OQ-01 is still open and still binds.** Phase 5 may be built and run
   against `vault/example-book/` (git-recoverable). It must NOT be run
   against any real vault until OQ-01 gives real content a restore path.
   No real book exists yet, so this does not block the phase — but the
   CLI must not quietly acquire the ability either.
2. Non-blocking: author may still supply a real Requesty key
   (`rqy_...`) → spike its 12 free models before any routing change.
3. Nothing else technical blocks Phase 5. The editorial route
   (gemini flash-lite → mistral-large) has been live-verified since
   Session 4 and is untouched.

### Read first

1. This file, CLAUDE.md (especially invariants 1–3 and the vault
   primitive list)
2. decisions.md #13–25 — do not relitigate. #15/#16 (hash ownership,
   byte-surgical flips) are the shape the append primitives must copy;
   #22 is the no-defaults thresholds rule; #23/#24 are the rhythm block
   and the local lane; #25 is why ch-005's hash is deliberately stale
3. [specs.md](specs.md) §4 (fact-line grammar — the reconciler must emit
   lines `context_builder.parse_facts` can read back), §5–7 (delta
   schema, editorial pass, reconciliation)
4. Pitfalls A1/A2 (delta validation, partial application) and B1
5. [architecture.md](architecture.md) §3 (authority model) and §6
6. [threat-model.md](threat-model.md) §6 Phase 5 checklist
7. [adr.md](adr.md) ADR-0004 (why the fixture is the only safe target)
   and ADR-0006 (the local lane, its offline dependency, and why its
   provenance is weaker than a hosted lane's)
8. pitfalls C8/C9 before touching the local server or enabling reasoning
   for the editorial pass

### What now exists (module map)

```
src/novel_engine/
  core/config.py        # BookConfig.load_book_config(vault_root, slug, env)
  core/outline.py       # parse_manifest(), next_target(), resolve_target()
  core/context_builder.py  # parse_facts, select_facts, previous_chapter_tail,
                        #   recent_summaries, banned_phrases, build_prompt
  core/vault.py         # THE ONLY WRITER. Exactly: scaffold_book,
                        #   generated_hash, chapter_path, split_chapter_file,
                        #   write_chapter, flip_manifest_status.
                        #   append_fact/append_summary/append_thread/
                        #   flip_thread_status are Phase 5 work — NOT built
  core/errors.py        # NovelEngineError, ConfigError, ContextError, VaultError
  core/state_machine.py # STUB — Phase 6 work
  drafting/generate.py  # draft_chapter(): continuation loop, ADR-0005 stubs
  drafting/provenance.py# make_session_id, chapter_frontmatter, utc_timestamp
  providers/*           # + local.py (keyless llama.cpp lane, ADR-0006);
                        #   openai_compat now allows api_key=None and maps
                        #   connect-refused to ModelUnavailable
  quality/metrics.py    # compute_metrics() + the nine specs §14 metrics as
                        #   pure functions; ChapterMetrics dataclass
  quality/style_checks.py # parse_thresholds, judge, build_report, Threshold,
                        #   Verdict, StyleReport, StyleCheckError,
                        #   COMPARABLE_METRICS, THRESHOLDS_BEGIN/END.
                        #   No numeric defaults live here, by design
  cli/new_book.py       # uv run new-book --slug X [--vault-root D]
  cli/write_session.py  # --book --chapter --dry-run --force; DRY_RUN=1
  cli/check_style.py    # WORKING: check-style --book X --chapter N
                        #   [--vault-root D]; no API key required; exit 0 even
                        #   when metrics are out of band
  editorial/{schema,pass_runner,reconciler}.py # STUBS — Phase 5 work
src/novel_engine/templates/book/  # packaged scaffolder source
vault/example-book/     # fixture: 001-002 hand-written, 003-004 generated in
                        #   Session 5, 005 generated in Session 7 (first draft
                        #   with the rhythm block); manifest fully written;
                        #   style-guide.md carries a THRESHOLDS block;
                        #   models.yaml fallback chain ends with local
tests/                  # 16 files, 187 tests. fakes.py holds FakeProvider,
                        #   full_providers (openrouter/nvidia/groq/local),
                        #   text_of, reset_fixture_state
```

Entry points (`pyproject.toml`), all three implemented:

```
new-book     = novel_engine.cli.new_book:main
write-session = novel_engine.cli.write_session:main
check-style  = novel_engine.cli.check_style:main
```

NOTE: the fixture manifest is fully written (001-005). To exercise
drafting paths again, add a ch-006 row to plot-outline.md first.
Tests never depend on live fixture state: reset_fixture_state() forces
any copied book back to "001-002 written, 003 planned".

NOTE: `src/novel_engine/templates/book/` ships the scaffolder's
style-guide template. It does NOT carry a THRESHOLDS block — deliberately, per decision #22:
a new book starts untuned and visibly so. If that is ever changed, the
block must ship commented out, never with numbers.

Env keys active in `.env`: gemini, openrouter, groq, mistral, nvidia,
aihubmix (emergency lane only). The local lane needs no key and is always
built. Routing truth: `vault/example-book/config/models.yaml`.

### Batches (proposed for Phase 5)

Commit after each batch. Do not push.

**Batch 1 — `editorial/schema.py`**: Pydantic models for the delta
(specs §5). Reject anything that is not exactly the schema — extra
keys, missing provenance, malformed fact lines. Pure validation, no IO.

**Batch 2 — vault append primitives**: `append_fact`, `append_summary`,
`append_thread`, `flip_thread_status` in `core/vault.py`, each
narrowly-scoped and each verifying its own write, in the shape of
decisions #15/#16. Round-trip test: every appended fact line must parse
back through `context_builder.parse_facts`.

**Batch 3 — `editorial/pass_runner.py`**: build the editorial prompt,
call through the router, validate the response into a delta, fail
closed on anything invalid (invariant 2 — an invalid delta is applied
not at all, never partially).

**Batch 4 — `editorial/reconciler.py`**: apply a validated delta through
the primitives only, all-or-nothing, with the pre-application state
recorded so a failure is diagnosable.

### The Phase 5 test case (fixed in the vault, preserved in git)

ch-005 contradicted itself — "Both of them" and, twelve paragraphs later,
"nine corrections on the spring-tide page" — against ch-001's canonical
two. The prose was **hand-corrected** (decision #25) so the fixture is not
shipped knowingly wrong.

The case itself is not lost. Recover the original with:

```bash
git show d518b74:vault/example-book/chapters/chapter-005.md
```

That text is the first thing the editorial pass should be pointed at: a
real model-made contradiction against a real locked fact, which no Phase 4
metric can see. Feed it to the reconciler and confirm the delta names the
contradiction rather than rewriting the chapter.

### Phase 5 exit criteria

- [ ] pytest passes; ruff clean (every session)
- [ ] A deliberately invalid delta leaves every canon file byte-identical
- [ ] A partially-valid delta is applied not at all (invariant 2)
- [ ] No model output is ever written to a canon body — only Python-built
      lines from validated fields (invariant 1)
- [ ] Every appended fact line round-trips through `parse_facts`
- [ ] Ran end-to-end against `vault/example-book/` only

### Do not do next session

- Do not run the editorial pass against any real book (OQ-01 unresolved;
  no real book exists yet either)
- Do not let a model regenerate `continuity-tracker.md` or any canon
  file body — that is invariant 1 and the reason the project exists
- Do not add a general "write canon file" vault primitive
- Do not re-add aihubmix to routing (cap is lifetime, not daily)
- Do not chase the dismissed providers without NEW evidence; reasons are
  dated in `.env`
- Do not wire next-step.md resume state (Phase 6)
- Do not add built-in threshold defaults to `quality/` (decision #22)
- Do not promote the local lane above groq on the current evidence — one
  prompt, one seed (ADR-0006 alternatives)
- Do not enable model reasoning for drafting (pitfalls C9: 2x cost, worse
  prose, measured). Measuring it for the EDITORIAL pass is legitimate and
  is an open experiment, not a decision
- Do not recompute a stale `generated_hash` to make a test pass — the
  staleness is the author-edit signal (decision #25, pitfalls B5)
- Do not turn style metrics into a gate. They rank a threshold-passing
  draft above a better-written one; specs §14 keeps them advisory
