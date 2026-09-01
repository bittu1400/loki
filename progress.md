# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-09-01 · end of Session 8

---

## Current state

**Phases 0–4 — ✅ complete.**
**Phase 5 (editorial delta pass + reconciler) — ✅ complete (Session 8)**
against `vault/example-book/`, including one live end-to-end run on the
real editor route. Still must NOT run against a real vault: OQ-01 is
unresolved and no real book exists yet.
**Phase 6 (session state machine + resume) — ⬜ next.**

The full path now exists: `write-session` drafts and writes a chapter;
`check-style` measures it for free; `editorial.pass_runner` reviews it
and returns a schema-validated delta or a refusal; `editorial.reconciler`
applies that delta to canon all-or-nothing through the vault primitives.
**262 tests pass, ruff clean.**

**The one thing to carry forward:** the machinery is verified and the
judgement is not. Pointed live at the original ch-005 — "nine
corrections" against ch-001's locked "two", with that fact in the prompt
— the editor model returned an empty violation list and wrote the
contradiction into the summary it appended to canon. A tightened prompt
made it perform the check and report a *different*, wrong violation.
Recorded as **OQ-10**, which is the most important open item in the
project right now: a pass that returns `[]` is indistinguishable from a
clean chapter.

Nothing is wired into a CLI yet — Phase 6 wires the pass and the
reconciler into a session and persists the phase pointer.

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq, Mistral, NVIDIA (+AiHubMix S4, demoted from routing same day) | ✅ complete | — |
| 3 | Single-chapter generation + continuation loop | ✅ complete (S5) | — |
| 4 | Deterministic style checks | ✅ complete (S7) | — |
| 5 | Editorial delta pass + reconciler | ✅ complete (S8) | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ⬜ next | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 8 — 2026-09-01

**Phase 5 complete in four batches, all committed separately.** Two
author decisions were taken mid-phase and written before the code that
depended on them.

### Done

**Batch 1 — `editorial/schema.py` (`dca6ccf`).** Pydantic models for the
specs §12 delta, `extra="forbid"` everywhere. Scalars required,
collections default to empty — a chapter that raised no violation is the
normal case, and spending a repair attempt on an omitted empty list
burns the scarcest quota in the stack. Anything destined for a canon
line must be a single line free of HTML comment syntax (a fact
containing `<!-- FACTS:END -->` would close the block it lands in).
**No `origin` field**: every fact through this schema came from a model
and is tagged `[model]` unconditionally, because a model able to claim
`[author]` defeats pitfall A4 in one call. A test composes the line for
every validated fact and matches it against `context_builder.FACT_LINE`.

**Decisions #26 and #27 (`0e1e081`), written before Batch 3.** #26: the
editorial prompt is engine-owned and packaged, not per-book — it is a
JSON contract plus assembled evidence, and a book-local edit could break
the contract silently, spending every repair attempt before failing
closed. #27: thread IDs are one above the highest in the file; that
never repeats under engine operation, and an author hand-deleting a line
frees the number back — an author action outside the engine's guarantee.
specs §5 was corrected, since it claimed a stronger guarantee than the
code makes.

**Batch 2 — five vault append primitives (`9fae20e`).** `append_fact`,
`append_thread`, `append_deepen_question`, `append_summary`,
`flip_thread_status`. Five, not the four CLAUDE.md listed: the delta
carries `deepen_questions` and architecture §3 makes the deepen queue
engine-append-only, so the reconciler cannot apply a validated delta
without it. Each verifies its own write by **re-parsing the file**, not
by trusting the string it built — facts through `parse_facts`, summaries
through `recent_summaries`, threads through the thread grammar — with
the byte-level check from decision #16 underneath (exactly one line
inserted at the expected index, every other byte identical).

**Batch 3 — `editorial/pass_runner.py` + packaged template (`16a4b37`).**
Assembles the prompt (retrieved facts, open threads with their real IDs,
the beat, the character sheet, the style guide, and the Phase 4 metrics
already computed), calls through the editor routes with `json_mode`,
validates, and repairs up to `max_repair_attempts` before failing
closed. Repairs rebuild from the BASE prompt rather than compounding —
otherwise every repair re-sends every rejected answer. Temperature 0.2,
not the book's 0.9: the deliverable is a JSON verdict, not prose.
`context_builder._fill_template` became `fill_template` (two modules use
it now).

**Batch 4 — `editorial/reconciler.py` + `vault.canon_transaction`
(`31f4181`).** The first code in the project that changes canon. Takes an
`EditorialDelta` — never a string, never a dict — and builds every line
in Python from typed fields. The whole apply runs inside
`canon_transaction`, which snapshots all four canon files and restores
every one of them on any failure, keeping the snapshot directory and
naming it in the error. `suggested_canon_patches` go to
`log/sessions/<id>-patches.md` as text, written only after the canon
change succeeded. `progressed` thread updates deliberately write nothing
(specs §5 forbids rewriting thread text).

**Live run (`13a6550`), author-approved spend.** Original ch-005 from
`d518b74`, real editor route, temp copy of the fixture.

### Verified

- [x] 262 tests pass (235 → 248 → 262 across the batches), ruff clean
      after every batch
- [x] Live: delta validated on the FIRST call, zero repairs, no fallback,
      3430 in / 400 out tokens on `gemini:gemini-3.5-flash-lite`
- [x] Live: the reconciler applied it all-or-nothing — two facts, one
      deepen question, one summary — and every appended line reads back
      through the parser that retrieves it
- [x] Every Phase 5 exit criterion: invalid delta leaves canon
      byte-identical; a delta that fails at the fourth step undoes the
      three that landed; no model output reaches a canon body; every
      appended fact round-trips through `parse_facts`; fixture only
- [x] threat-model §6 Phase 5 checklist ticked with test names, including
      the snapshot mechanism

### The live run's real finding — OQ-10

The test case was chosen because it is the one thing a Phase 4 metric
cannot see: ch-005 says "nine corrections on the spring-tide page"
against ch-001's locked fact that the page carries **two**. That fact was
retrieved into the prompt, six lines above the chapter text.

| Run | Prompt | `continuity_violations` | Result |
|---|---|---|---|
| 1 | "an invented violation is worse than a missed one" | `[]` | missed it — and the summary it wrote repeated "nine corrections", putting the contradiction INTO canon |
| 2 | "check the chapter against every locked fact, one at a time; numbers are the commonest case" | one | still missed nine-vs-two; reported "twelve years of rolls" against "kept the ledger for eleven years", which is arguably not a contradiction |

The tightened wording is kept (the first version actively discouraged
the check) but it is not a fix. Everything else in the delta was good:
the new facts were concrete and correct, the deepen question was real,
`beat_adherence` was accurate. It is specifically the violation list
that is unproven, and that is the feature the project was built around.

### Not done / not attempted

- No CLI for the editorial pass. Nothing calls `pass_runner` or
  `reconciler` in a session — that is Phase 6 wiring
- The fallback editor (`mistral-large-latest`) was never exercised live;
  only the fakes cover it. OQ-10's recommended first step is to run the
  same case on it
- Reasoning-on for the editorial pass was NOT measured (still the open
  experiment from Session 7)
- `next_step_note` is validated and returned but written nowhere —
  `log/next-step.md` is Phase 6
- OQ-01 untouched. `canon_transaction` recovers one interrupted apply,
  NOT a session an author wants to undo tomorrow
- The two Session 7 gaps (descriptive banned-phrase rules, no
  `dialogue_ratio` minimum) remain open
- Nothing pushed

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

**Two things compete for this session. Ask the author which one first.**

**Option A — OQ-10 (recommended).** The editorial pass's continuity
judgement is unproven and it is the feature the project exists for.
OQ-10's first step is two live calls: run the same ch-005 case on the
fallback editor (`mistral:mistral-large-latest`), and if it also misses,
prototype the deterministic pre-filter (Python finds number
disagreements between a locked fact and the chapter, and hands the
candidates to the model). That is engineering, not prompt roulette, and
it attacks exactly the class that was missed twice.

**Option B — Phase 6: session state machine + resume**
(`core/state_machine.py`, `log/next-step.md` persistence, and wiring
`pass_runner` + `reconciler` into `write-session`). Nothing started.
specs §11 has the state diagram; §8 has the `next-step.md` contract.

Phase 6 is the phase the tracker says is next. OQ-10 is the phase the
evidence says is next. They are not in conflict — Phase 6 wires up a
pass whose verdicts we do not yet trust, which is fine as long as the
CLI reports the violation list as advisory.

### Reproduce the OQ-10 case in one command

```bash
git show d518b74:vault/example-book/chapters/chapter-005.md
```

That is the draft with the contradiction. The live harness used this
session was ephemeral (scratchpad); rebuilding it is ~40 lines:
copytree the fixture to a temp dir, `load_book_config`, take the
manifest entry for chapter 5, `run_editorial_pass(book, entry, body,
build_providers(os.environ))`. It prints the delta; `reconcile` applies
it. Nothing touches the committed fixture.

### Blocked / waiting on the author

1. **OQ-01 still binds.** Phase 5 code exists and works, and it must
   still never run against a real vault. `canon_transaction` is NOT the
   answer to OQ-01 — it recovers one interrupted apply, not a session an
   author wants to undo tomorrow. No real book exists yet.
2. **OQ-10 needs a direction** — see the two options above.
3. Non-blocking: author may still supply a real Requesty key
   (`rqy_...`) → spike its 12 free models before any routing change.
4. Non-blocking, still open from Session 7: reasoning-on for the
   EDITORIAL pass has never been measured. Now that the pass exists and
   the ch-005 case is a known miss, this is a cheap, well-posed
   experiment rather than a vague one (pitfalls C8/C9 apply to drafting
   only).

### Read first

1. This file, CLAUDE.md (invariants 1–3, the vault primitive list, and
   the two new structural facts about the editorial pass)
2. decisions.md #13–27 — do not relitigate. #15/#16 are the shape every
   write primitive copies; #22 is the no-defaults thresholds rule;
   #25 is why ch-005's hash is deliberately stale; #26 is why the
   editorial prompt is packaged rather than per-book; #27 is thread ID
   allocation and its one honest gap
3. [open-questions.md](open-questions.md) **OQ-10 first**, then OQ-01
4. [specs.md](specs.md) §11 (state machine) and §8 (`next-step.md`
   contract) for Phase 6; §12's status note for what Phase 5 actually
   built
5. Pitfalls A1/A2 stay live — every future canon writer answers to them

### What now exists (module map)

```
src/novel_engine/
  core/config.py        # BookConfig.load_book_config(vault_root, slug, env)
  core/outline.py       # parse_manifest(), next_target(), resolve_target()
  core/context_builder.py  # parse_facts, select_facts, previous_chapter_tail,
                        #   recent_summaries, banned_phrases, build_prompt,
                        #   fill_template (public since Phase 5 — two callers)
  core/vault.py         # THE ONLY WRITER. scaffold_book, generated_hash,
                        #   chapter_path, split_chapter_file, write_chapter,
                        #   flip_manifest_status, append_fact, append_thread,
                        #   append_deepen_question, append_summary,
                        #   flip_thread_status, canon_transaction.
                        #   Still no general "write canon file" function, and
                        #   a test asserts the exact set of public writers
  core/errors.py        # + EditorialError (permanent, never fallback-eligible)
  core/state_machine.py # STUB — Phase 6 work
  drafting/generate.py  # draft_chapter(): continuation loop, ADR-0005 stubs
  drafting/provenance.py# make_session_id, chapter_frontmatter, utc_timestamp
  providers/*           # unchanged this session
  quality/*             # unchanged this session
  editorial/schema.py   # EditorialDelta + parse_delta(). extra="forbid";
                        #   canon-line text guards; no origin field (A4)
  editorial/pass_runner.py # build_editorial_prompt, run_editorial_pass,
                        #   repair loop, EDITORIAL_PARAMS (temp 0.2).
                        #   Returns data; writes nothing, ever
  editorial/reconciler.py  # reconcile(book, delta, session_id) -> Reconciliation.
                        #   The only caller of the canon appends
  cli/{new_book,write_session,check_style}.py  # unchanged; NONE of them
                        #   calls the editorial pass yet (Phase 6)
src/novel_engine/templates/book/            # packaged scaffolder source
src/novel_engine/templates/editorial-prompt.md  # engine-owned (decision #26)
vault/example-book/     # fixture, unchanged this session — the live run used
                        #   a temp copy, so the committed fixture still has
                        #   chapters 001-005 with summaries for 001-002 only
tests/                  # 19 files, 262 tests. New: test_editorial_schema.py,
                        #   test_vault_appends.py, test_editorial_pass.py,
                        #   test_reconciler.py
```

Entry points (`pyproject.toml`) are unchanged: `new-book`,
`write-session`, `check-style`. There is deliberately no
`editorial-pass` entry point — wiring the pass into a session is Phase 6
work, and adding a CLI that can write canon on a real vault before
OQ-01 resolves would hand the engine the ability the docs say it must
not have.

### Phase 6 batches (proposed)

Commit after each batch. Do not push.

**Batch 1 — `log/next-step.md` read/write**: the frontmatter contract in
specs §8, with a vault primitive for the write (it is the one canon-
adjacent file whose mode is *overwrite* — architecture §3 — so it needs
its own narrowly-scoped primitive, not a general writer).

**Batch 2 — `core/state_machine.py`**: the specs §11 phases, the legal
transitions, and persisting the phase pointer before each next phase
begins.

**Batch 3 — resume**: re-running a session whose chapter exists resumes
from the recorded phase or refuses with a precise message. Never
overwrites.

**Batch 4 — wire the editorial pass into `write-session`**: draft →
style → editorial → reconcile → complete, with the violation list
reported as ADVISORY until OQ-10 says otherwise, and an
`editorial-pending` exit that is visibly distinct from success.

### Do not do next session

- Do not run the editorial pass against any real book (OQ-01)
- Do not present the violation list as a guarantee anywhere in the CLI
  or the docs (OQ-10)
- Do not let a model regenerate any canon file body (invariant 1)
- Do not add a general "write canon file" vault primitive
- Do not "fix" OQ-10 by loosening the schema or letting the model write
  the summary paragraph straight into the tracker
- Do not re-add aihubmix to routing; do not chase dismissed providers
  without new evidence
- Do not add built-in threshold defaults to `quality/` (decision #22)
- Do not promote the local lane above groq on the current evidence
- Do not enable model reasoning for DRAFTING (pitfalls C9, measured).
  Measuring it for the editorial pass is a legitimate open experiment
- Do not recompute a stale `generated_hash` (decision #25, pitfalls B5)
- Do not turn style metrics into a gate (specs §14)
