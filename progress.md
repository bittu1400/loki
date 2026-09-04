# Progress

Single source of truth for project state. Updated at the end of every
session. The next session must be able to start from this file alone,
with no conversational context.

**Last updated:** 2026-09-04 · Session 10 (Phase 6 complete)

---

## Current state

**Phases 0–6 — ✅ complete.** Phase 5 (editorial pass + reconciler) and
Phase 6 (state machine, resume, CLI orchestration) are both built and
tested against `vault/example-book/`. Neither has ever run against a real
vault, and must not while OQ-01 is open.

`write-session` now runs one chapter end to end: target, draft, style,
editorial, reconcile, complete — persisting each phase to
`log/next-step.md` before the next begins, promoting the chapter to
`pending-review`, and advancing the pointer to the next planned manifest
row. Three exit codes: 0 complete, 1 nothing usable happened, 2
`editorial-pending` (prose on disk, canon deliberately untouched,
resumable with `--resume`).

**325 tests pass, ruff clean.**

**What changed about OQ-01's blast radius.** Through Phase 5 the
canon-writing code had no caller, so "do not run it against a real vault"
was a rule about modules nobody could invoke. It is now a rule about
`write-session` itself. The one shape a real book can safely take today
is `editorial.enabled: false` (decision #36), which drafts and completes
without touching canon — safety bought by switching the continuity layer
off, which is not a resolution.

**OQ-10 is unchanged and still half-answered.** Bare number
disagreements are caught. Names, dates, orderings, rewritten quantities
and capabilities have never been tested. Every "no violations" line the
CLI prints carries that caveat, deliberately.

Next: nothing in the phase plan. See the next-session section — the
candidates are the OQ-10 experiment, OQ-01, and the first live run of the
wired pipeline.

## Phase tracker

| Phase | Deliverable | Status | Blocked by |
|---|---|---|---|
| 0 | Documentation foundation | ✅ complete | — |
| 1 | Vault templates + config loader + `example-book` fixture | ✅ complete | — |
| 2 | Provider layer: Gemini, OpenRouter, Groq, Mistral, NVIDIA (+AiHubMix S4, demoted from routing same day) | ✅ complete | — |
| 3 | Single-chapter generation + continuation loop | ✅ complete (S5) | — |
| 4 | Deterministic style checks | ✅ complete (S7) | — |
| 5 | Editorial delta pass + reconciler | ✅ complete (S8) | **OQ-01 (real vaults only)** |
| 6 | Session state machine + resume | ✅ complete (S10) | — |
| — | *Deferred (ADR-0001):* GitHub Actions, approval gate, Cousins endpoint, `new_book.py` interview | ⏸ | — |

---

## Session 10 — 2026-09-04

**Phase 6 complete — Batches 3 and 4 landed.** `write-session` now runs
the whole specs §11 lifecycle for one chapter and every phase it reaches
is on disk before the next one starts, so any interruption is resumable.
The editorial pass and the reconciler have a caller for the first time.

**325 tests pass, ruff clean.**

### Decisions taken before any code was written

Four questions had to be answered by the author, because each one changes
a document and not just a module. All four went to the recommendation.

- **#35** — `flip_chapter_status`, the second single-cell mechanical edit.
  Until it existed nothing could set a chapter to `pending-review`, so
  `complete` was a phase with no observable effect on the chapter it
  completed. It rewrites one frontmatter key and never the body, so
  `generated_hash` and the author-edit signal survive it.
- **#36** — `editorial.enabled: false` is honoured, and `styled ->
  complete` joins the legal transitions as the edge that path takes.
  Without the edge, a book that switched the pass off would park its
  pointer at `styled` and resume the same chapter forever.
- **#37** — exit code 2 for `editorial-pending`. 0 and 1 could not both
  be true of a chapter that drafted successfully and reconciled nothing.
- **#38** — `--resume` is required; a bare re-run of an interrupted
  session refuses and names the chapter, the phase, and the flag.
- All four are consolidated in **ADR-0011**.

### Done

**Primitives (`f2f9d21`).** `vault.flip_chapter_status` with
`LEGAL_CHAPTER_STATUSES = {draft, pending-review}` (specs §11's `approved`
and `published` are unreachable in v1 per ADR-0001, so they are not legal
here yet); the `styled -> complete` edge; and
`SessionStateMachine.restart()`, the one write that skips
`validate_transition` — abandoning a session is not a transition, and the
author has already paid `--force`'s typed confirmation to get there.
The writer allowlist test was updated on purpose.

**CLI orchestration (`5a13aec`).** `cli/write_session.py` reads the
pointer on startup and:
- refuses when `blocked: true`, before anything runs;
- takes its target from the pointer whenever a session is mid-flight —
  **the manifest cannot supply it**, because drafting already flipped the
  row to `written` and `next_target()` would skip straight past the
  chapter whose review never finished;
- refuses a `--chapter` override that names a different chapter from the
  one the pointer has open;
- refuses an interrupted session without `--resume`, and refuses
  `--resume` when there is nothing to resume;
- refuses when the pointer says `drafted` but the chapter is not on disk;
- persists `target`, `drafted`, `styled`, then `editorial-pending` or
  `reconciled`, then `complete`.

**Audit consolidation (`49a352f`).** Two gaps found by re-reading specs
rather than by a failing test. §13 asks for one record per session,
written at session end, carrying the style metrics and the raw validated
delta; the code was writing it immediately after drafting (which stopped
being session end the moment review phases existed) and I had briefly
invented a second `-editorial.json` file. The raw delta matters because
it is the only place a `progressed` thread note ever reaches the author.
§12 gives `next_step_note` a destination — the prose half of
`log/next-step.md` — and nothing was carrying it there, so a completed
session left the previous chapter's note standing over the next one.

### Verified

- [x] 325 tests pass (304 → 325), ruff clean and formatted.
- [x] Full lifecycle against `vault/example-book/` with fake providers:
      chapter written, canon appended (append-only, every prior line
      still present), chapter promoted to `pending-review`, pointer
      advanced to the next planned manifest row with the delta's note.
- [x] Resume: a run whose editor is dead exits 2 at `editorial-pending`
      with canon byte-identical; the resumed run reaches `complete`
      **without calling the drafting provider once** and with the stored
      body unchanged.
- [x] A `critical` violation refuses the whole delta through the CLI
      (invariant 6, ADR-0009) — canon byte-identical, exit 2.
- [x] `editorial.enabled: false` completes without asking the editor
      anything and without touching canon.
- [x] Every refusal path asserted by message, not just by exit code.
- [x] The real `write-session` binary driven against a scratch copy of
      the fixture (deleted afterwards; the committed fixture was never
      touched), with deliberately invalid keys: `--dry-run` exits 0 and
      prints the prompt; an interrupted pointer refuses with the exact
      three-line message; `--resume` skips drafting, runs style, fails
      the editorial call, exits **2**, leaves `continuity-tracker.md`
      byte-identical, and parks the pointer at `editorial-pending`.
      This proves the plumbing and the exit contract, not model
      behaviour — the keys were junk and every route returned 400.

### The OQ-10 name experiment — run this session

The two-call experiment that has been sitting in the next-session brief
since Session 8. It took four calls and it answered the question.

**Setup.** A scratch copy of the fixture (deleted afterwards; the
committed fixture was never touched). One sentence added to ch-005
contradicting a locked fact by identity, no digit changed:

> The echo ledger itself had never been his. Brannec Tull had kept it
> since before Ovist's clerkship, and Ovist had never once been trusted
> to write in it.

against `[character:ovist-rhoam]` *Ovist Rhoam has kept the echo ledger
for eleven years* — one of only two facts retrieval puts in this
chapter's prompt. `find_number_conflicts` reports nothing, by
construction.

**Results.** flash-lite missed it **twice** (0 violations, temperature
0.2, identical outcome). A third run, with one block of simulated
ENTITY-check evidence appended in exactly the shape ADR-0008 uses for
numbers, caught it as `critical`, quoted the sentence and named the
fact — first call, no repairs, 554 output tokens. mistral-medium never
answered: HTTP 429 on every attempt across ~10 minutes.

**So the branch OQ-10 posed is decided by measurement:** it is not the
prompt wording, it is the evidence. The same model, the same
instructions, the same chapter — the only variable that changed the
outcome was a deterministic finding handed to it.

**The finding I did not expect.** In both unaided runs the model
proposed *the fact the chapter contradicts*, verbatim, as a NEW locked
fact. It echoed the fact it was supposed to check against, as
confirmation. Decision #29's refusal cannot fire on that, because
nothing is reported as violated — the reconciler would have appended a
duplicate of the contradicted fact and, in run 2, a summary that moved
the scene to the "Vhal Mirek Office", a place that does not exist in
this book. Pitfall A6 and pitfall A3 arriving in the same delta.

**Nothing was reconciled and no canon was written** — the harness runs
the pass and prints the delta; it never calls `reconcile`.

### Not done, and deliberately

- **No live API run with working keys.** The smoke run above reached real
  endpoints, but only to be rejected, so it exercised the failure lane and
  nothing else. The one live editorial evidence in the project is still
  Session 8's five runs, and those went through a throwaway script rather
  than `write-session`. A chapter has never been drafted AND reconciled by
  the wired command.
- **The OQ-10 experiment is now run** (above), so what is left of that
  question is a decision rather than an experiment: whether to build a
  deterministic entity/name check as a sibling of specs §16. Unbuilt,
  unplanned, and now evidenced.
- **mistral-medium was never reached.** The comparison run against the
  one model that has caught a contradiction unaided is still missing,
  because the free tier returned 429 throughout.

---

## Session 9 — 2026-09-03

**Phase 6 in progress — Batches 1 and 2 complete and committed.** The machine
contract for the session pointer, its vault primitives, the lifecycle
transition engine, and crash-resumption persistence are fully built and
tested.

### Done

**Batch 1 — `log/next-step.md` read/write (`11780f4`).**
- Implemented the specs §8 machine contract in `core/state_machine.py`:
  `NextStepFrontmatter` and `NextStep` with `extra="forbid"`, validating
  all seven frontmatter fields (`next_chapter`, `next_pov`, `last_session_id`,
  `last_session_phase`, `last_session_status`, `blocked`, `blocked_reason`) and
  the prose markdown note below it. `parse_next_step()` rejects unclosed or
  invalid YAML, non-mapping frontmatter, and unrecognized fields with `ContextError`.
  `serialize_next_step()` formats the markdown preserving field order.
- Added `StateMachineError` to `core/errors.py`.
- Added narrowly-scoped primitives in `core/vault.py`: `next_step_path()`,
  `read_next_step()`, and `write_next_step()`. In accordance with architecture
  §3 and the one-writer rule (invariant 1), `log/next-step.md` is the only
  canon-adjacent file whose mode is overwrite. `write_next_step()` verifies its
  own write by re-reading and re-parsing what landed on disk (**decision #33**,
  **ADR-0010**).
- Updated `test_vault_exposes_no_general_canon_writer` in
  `tests/test_vault_appends.py` to assert `write_next_step`. Added 16 tests in
  `tests/test_next_step.py`.

**Batch 2 — `core/state_machine.py` lifecycle transitions (`fa79024`).**
- Implemented the specs §11 phase lifecycle:
  `target` → `drafted` → `styled` → `[editorial-pending | reconciled]` → `complete`.
  `LEGAL_TRANSITIONS` defines all valid edges.
- Added `validate_transition()` and `build_next_step()`. Illegal transitions
  raise `StateMachineError` naming the attempted transition and all valid
  options.
- Added `SessionStateMachine` with `.load(book_root)` and `.transition()`.
  Crucial guarantee: **every phase transition is persisted to `log/next-step.md`
  via `write_next_step()` before the subsequent phase begins** (specs §11
  crash-resumption rule, **decision #34**, **ADR-0010**).
- Added explicit blocker support: `.mark_blocked(reason)` and `.unblock()`.
  Transitions fail closed if the pointer is marked `blocked: true`.
- Added 11 tests in `tests/test_state_machine.py`.

### Verified

- [x] 304 tests pass (277 → 293 → 304 across the batches), ruff clean and formatted.
- [x] `vault/example-book/log/next-step.md` and template `next-step.md` both parse cleanly.
- [x] Full happy-path lifecycle walkthrough (`complete` → `target` → `drafted` →
      `styled` → `reconciled` → `complete`) verified against disk.
- [x] `editorial-pending` retry and recovery branches verified against disk.
- [x] Blocker enforcement verified: transitions are refused when blocked and succeed once unblocked.
- [x] Re-parsing post-write verification in `write_next_step` ensures zero write corruption.

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

### Continued the same session — OQ-10 chased down

The author asked for the mistral run and for OQ-10 to continue. Five
live runs total on the ch-005 case; the full table is in
open-questions.md OQ-10.

**`mistral-large-latest` is dead** — 403 `tier_not_allowed` (code 1910)
on the key that verified it in Session 4, while `/v1/models` still lists
it. The editorial fallback from decision #7 had been gone for some time
and nothing had noticed, because nothing had called it. Confirmed live
in passing: a PermanentFailure did NOT walk to the second route
(invariant 3, working).

**`mistral-medium-latest` caught the contradiction unaided** — quoted
"There were nine corrections on the spring-tide page", named the locked
fact, first call, zero repairs. It also did two things that became
decisions:

- proposed `The spring-tide page carries nine corrections` as a NEW
  LOCKED FACT in the same delta that flagged it → **decision #29**:
  a delta with a critical violation is not reconcilable at all.
- proposed 8-9 facts including set dressing ("the Almanac Office uses
  green tape to tie countersigning rolls") → **decision #32**: the
  prompt now says a locked fact is something a later chapter could
  contradict.

**The deterministic number check (#30) closed the gap on the weak
model.** `quality/continuity_numbers.py` compares quantities in the
chapter against quantities in the retrieved facts and hands the findings
to the prompt as evidence. On the fixture it reports exactly one finding
on the pre-fix ch-005 and zero on every committed chapter, including the
hand-corrected one — both halves asserted by tests. With that finding in
its prompt, `gemini-3.5-flash-lite` caught the contradiction on **both**
runs, having missed it twice without.

Its two false-positive guards are tuned to measured failures, not
imagined ones: one shared word between fact and sentence let all three
"years" conflicts through — including the exact false positive the live
model reported — so it requires two; and a sentence that also states the
canonical number ("eleven years of his tenure, then one year of his
predecessor") is treated as consistent.

**Routing went back to gemini (#31, superseding #28 the same day).**
Once the pre-filter existed, #28's premise stopped being true.
flash-lite costs 476 output tokens against mistral-medium's 1091 and
proposed 1 fact against 8-9. Mistral-medium stays as fallback because it
is the only model that has caught a contradiction unaided.

Also seen and worth remembering: in run 5 the delta suggested a canon
patch reading "Update the spring-tide almanac page correction count to
nine" — the model proposing to edit the author's canon to match its
chapter. It went nowhere, because suggestions are text in a log and
`reconcile` had already refused the delta.

### Documentation pass (end of session)

Every doc audited line by line against the code, not just updated where
the new code touched. Three claims were **false before this session
started** and are now fixed:

- architecture §3's authority table said the engine never writes
  `canon/plot-outline.md`. It flips one `status` cell and has since
  Phase 3 (decision #16). The row now says so, and says what it still
  may not touch.
- architecture §6 counted "six provider modules ... five of the six
  share an OpenAI-compatible wire format". There are seven and six since
  ADR-0006 added the local lane in Session 7.
- specs §9's verified-reality note still named `mistral-large` as the
  editorial fallback, and OQ-08 still reasoned about `gemini-2.5-pro`'s
  quota — a model that has been unobtainable since Session 4.

One **live bug** was found by the audit, not by a test:
`src/novel_engine/templates/book/config/models.yaml` — the scaffolder's
own template — still routed the editorial pass to
`openrouter:z-ai/glm-5.2:free` (dismissed as upstream-saturated) with
`gemini:gemini-2.5-flash` as fallback (a family closed to new keys since
Session 4). **Every book scaffolded since then would have failed its
first editorial call**, and nothing caught it because the fixture has its
own models.yaml and the tests use fakes. Now points at the verified pair
with dated per-entry comments; `tests/test_new_book.py` gained the
mistral key its scaffolded book now legitimately demands at startup.

New this session:

- **[ADR-0007](adr.md#adr-0007--canon-changes-are-transactional)** —
  canon changes are transactional. The mechanism behind invariant 2,
  with the scoping that keeps a file-restoring function honest inside
  the module whose rule is "no general canon writer".
- **[ADR-0008](adr.md#adr-0008--continuity-checking-is-not-exclusively-the-models-job)**
  — continuity checking is not exclusively the model's job. The full
  evidence chain from "the pass returned `[]`" to "Python finds what is
  mechanical, the model judges what is not".
- **[ADR-0009](adr.md#adr-0009--a-chapter-that-contradicts-locked-canon-is-not-reconcilable)**
  — a contradicting chapter is not reconcilable, and why there is no
  override flag.
- **Invariant 6** added to best-practices §8 and CLAUDE.md. The first
  new invariant since the project started; ADR-0009 is its record.
- **specs §16** — the number check gets a real spec: algorithm, both
  tuned guards with the measurements behind them, what is permanently
  out of scope, and the regression contract its tests enforce.
- **specs §12** rewritten from a status note into the actual validation
  contract — a rule-and-why table matching `schema.py` line for line,
  plus a delta-field-to-destination table for the reconciler.
- **specs §4-§7** gained "Engine behaviour" blocks: what each append
  primitive refuses and re-parses, why `origin` is always `model`, why
  the engine never writes `answered:`, and why `progressed` writes
  nothing.
- **pitfalls A6, A7, C10** — the three measured failures of this
  session, written as traps rather than as history: an empty violation
  list read as a clean chapter, the pass proposing its own contradiction
  as canon, and a verified model leaving your tier while still appearing
  in the catalog.
- **threat-model T1/T4** — residual risk sharpened with what was
  actually observed, including the delta that suggested editing canon so
  its chapter would stop being wrong.
- **CLAUDE.md** gained two working rules this session earned:
  *supersede, do not defend* (#28 lived four hours) and *verify doc
  claims against the code before repeating them* (see the three false
  claims above).

### Not done / not attempted

- No CLI for the editorial pass. Nothing calls `pass_runner` or
  `reconciler` in a session — that is Phase 6 wiring
- Two cosmetic frontmatter gaps found during the doc audit, recorded and
  NOT fixed (both are Phase 6's business, and neither is read by any
  code): the engine writes no `title` key — a generated chapter's title
  lives only in its `# Chapter N — …` heading — and it writes
  `status: draft` where architecture §4 step 11 says a completed session
  should end at `pending-review`. specs §3 now documents both as the
  actual shape rather than the intended one
- Non-numeric contradictions have never been tested — no name, date,
  rewritten quantity, or capability case exists. That is all of OQ-10
  that is left, and it is the part the deterministic layer cannot help
  with
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

**Phase 6 is done. There is no Phase 7 in the plan** — everything left in
`prompt.md`'s original scope is deferred by ADR-0001 (GitHub Actions, the
approval gate, the publishing endpoint, `new_book.py` as an interview).
So this session picks work rather than continuing a phase, and the three
candidates are below in the order I would take them.

### 1. The first live run of the wired pipeline (recommended first)

Everything Session 10 verified used fake providers. The pass and the
reconciler have one live outing between them, from Session 8, and that
was through a throwaway script — not through `write-session`. Nothing
about the wiring itself has met a real provider.

```bash
uv run write-session --book example-book --dry-run   # free; confirms the target
uv run write-session --book example-book             # one real chapter, end to end
```

The fixture is committed, so git restores it either way — `git checkout
vault/example-book` undoes everything a bad run does. Watch for:

- the pointer at each phase (`cat vault/example-book/log/next-step.md`
  mid-run if you can, or read the audit's `final_phase` after)
- the exit code: 0, 1 and 2 all mean specific things now (specs §15)
- whether the delta's `next_step_note` reads sensibly as the pointer note
- the violation list, and whether the caveat wording still reads honestly
  next to a real result

The manifest in the committed fixture has rows through 005; chapters 001
through 005 exist. A live run needs a `planned` row — add one, or run
with `--force` on an existing chapter and accept the confirmation prompt.

### 2. The OQ-10 experiment — two calls, still the only untested class

Unchanged from the last two sessions. Plant ONE non-numeric
contradiction in a scratch copy of a fixture chapter — a name is cheapest
to author and the hardest for a regex — and run both editors on it. It
decides whether the answer is "the prompt was the problem" or "extend
the deterministic layer to entity names next".

The pre-fix ch-005 with the numeric contradiction is still at:

```bash
git show d518b74:vault/example-book/chapters/chapter-005.md
```

And the free half of that case needs no key at all:

```python
find_number_conflicts(parse_facts(tracker_text), chapter_body)
```

one finding on the pre-fix ch-005, zero on every committed chapter.

### 3. OQ-01 — now blocking the main command, not a library

Read the widened scope note in [open-questions.md](open-questions.md)
OQ-01 before deciding. The recommendation there (a local git repo inside
the vault, ~20 lines, never pushed) has not changed and nothing has
argued against it. What changed is the cost of leaving it open: until
Session 10 it blocked modules nothing could invoke; now it blocks
`write-session` against any real book unless that book sets
`editorial.enabled: false`.

### Blocked / waiting on the author

1. **OQ-01.** Needs an author decision, not code. Everything else can
   proceed without it as long as work stays on `vault/example-book/`.
2. Non-blocking: a real Requesty key (`rqy_...`) would be worth a spike
   of its 12 free models before any routing change.
3. Non-blocking, open since Session 7: reasoning-on for the EDITORIAL
   pass has never been measured. Cheap and well-posed now that the pass
   has a caller (pitfalls C8/C9 are about drafting only).

### Read first

1. This file, then CLAUDE.md — the invariants, the vault primitive list,
   and the structural facts about the pointer owning the target, the
   resume gate, and exit code 2
2. decisions.md #13–38 — do not relitigate. #15/#16 are the shape every
   write primitive copies; #22 is the no-defaults thresholds rule; #25 is
   why ch-005's hash is deliberately stale; #26 is why the editorial
   prompt is packaged; #27 is thread ID allocation; #28 was superseded by
   #31 the same day; #29/#30/#32 came out of the live editorial runs;
   #33/#34 are the pointer and phase persistence; **#35–#38 are Session
   10: the chapter-status writer, the editorial-disabled escape, exit
   code 2, and the resume gate**
3. [open-questions.md](open-questions.md) — **OQ-01 first now** (its
   scope widened), then OQ-10
4. [specs.md](specs.md) §11 (lifecycle, including the `styled ->
   complete` edge), §15 (three exit codes, `--resume`), §13 (the session
   record, now complete as specified), §12 (where each delta field goes)
5. [adr.md](adr.md) **ADR-0011** for Session 10's four decisions, then
   0007–0010 for the transactional/continuity/pointer rules underneath
   them
6. Pitfalls A1/A2 stay live for every future canon writer. **A6, A7 and
   C10** are live and all three are measured, not hypothetical
7. best-practices §8 lists **six** invariants

### What now exists (module map)

```
src/novel_engine/
  core/config.py        # BookConfig.load_book_config(vault_root, slug, env)
  core/outline.py       # parse_manifest(), next_target(), resolve_target()
  core/context_builder.py  # parse_facts, select_facts, previous_chapter_tail,
                        #   recent_summaries, banned_phrases, build_prompt,
                        #   fill_template
  core/vault.py         # THE ONLY WRITER. scaffold_book, generated_hash,
                        #   chapter_path, split_chapter_file, write_chapter,
                        #   flip_manifest_status, flip_chapter_status (S10),
                        #   append_fact, append_thread, append_deepen_question,
                        #   append_summary, flip_thread_status,
                        #   canon_transaction (ADR-0007),
                        #   next_step_path, read_next_step, write_next_step.
                        #   Still no general "write canon file" function, and
                        #   a test asserts the exact set of public writers
  core/errors.py        # + EditorialError, + StateMachineError
  core/state_machine.py # NextStepFrontmatter, NextStep, parse/serialize,
                        #   LEGAL_TRANSITIONS (incl. styled -> complete, #36),
                        #   validate_transition, build_next_step,
                        #   SessionStateMachine (load, transition, restart,
                        #   mark_blocked, unblock)
  drafting/generate.py  # draft_chapter(): continuation loop, ADR-0005 stubs
  drafting/provenance.py# make_session_id, chapter_frontmatter, utc_timestamp
  providers/*           # unchanged
  quality/metrics.py, style_checks.py   # unchanged
  quality/continuity_numbers.py  # find_number_conflicts(facts, body).
                        #   Tuned false-positive guards — read the docstring
                        #   and specs §16 before touching them
  editorial/schema.py   # EditorialDelta + parse_delta(). extra="forbid"
  editorial/pass_runner.py # build_editorial_prompt, run_editorial_pass,
                        #   repair loop. Returns data; writes nothing, ever
  editorial/reconciler.py  # reconcile(). The only caller of the canon
                        #   appends. Refuses any critical violation (#29)
  cli/write_session.py  # THE lifecycle: pointer -> target -> draft -> style
                        #   -> editorial -> reconcile -> complete. Exit 0/1/2
  cli/{new_book,check_style}.py  # unchanged
src/novel_engine/templates/book/            # packaged scaffolder source
src/novel_engine/templates/editorial-prompt.md  # engine-owned (decision #26)
vault/example-book/     # fixture, unchanged
tests/                  # 22 files, 325 tests
```

Entry points (`pyproject.toml`) are unchanged: `new-book`,
`write-session`, `check-style`. There is deliberately no
`editorial-pass` entry point — the pass runs as one phase of
`write-session`, which is the only place a delta has a chapter, a phase,
and a pointer to record itself against.

### Do not do next session

- Do not run `write-session` against any real book while OQ-01 is open,
  unless that book sets `editorial.enabled: false` — the command writes
  canon now
- Do not present the violation list as a guarantee anywhere in the CLI or
  the docs (OQ-10). Number disagreements are covered; nothing else is
- Do not loosen `continuity_numbers`' false-positive guards without
  re-running the test that asserts zero findings on every committed
  chapter — both guards are tuned to failures that actually happened
- Do not add an override that lets a critical-violation delta reconcile
  (invariant 6, ADR-0009). If it must change, that is a new ADR
- Do not make exit 2 mean anything other than "prose written, canon
  untouched, resumable", and do not fold it back into 0 or 1
- Do not make `--resume` implicit. A bare re-run spending free-tier calls
  on a forgotten session is the surprise decision #38 exists to prevent
- Do not re-add `mistral-large-latest` anywhere: 403 `tier_not_allowed`,
  still listed in `/v1/models` (pitfall C10). Probe any fallback lane
  with a real generation call, never a catalog listing
- Do not let a model regenerate any canon file body (invariant 1)
- Do not add a general "write canon file" vault primitive
- Do not re-add aihubmix to routing; do not chase dismissed providers
  without new evidence
- Do not add built-in threshold defaults to `quality/` (decision #22)
- Do not promote the local lane above groq on the current evidence
- Do not enable model reasoning for DRAFTING (pitfalls C9, measured).
  Measuring it for the editorial pass is a legitimate open experiment
- Do not recompute a stale `generated_hash` (decision #25, pitfalls B5)
- Do not turn style metrics into a gate (specs §14)
