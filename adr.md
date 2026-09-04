# Architecture Decision Records

Each ADR captures one decision: the situation that forced it, what was
chosen, what was rejected and why, and what the choice costs us.

**Status values:** `Proposed` · `Accepted` · `Superseded by ADR-NNNN` · `Deprecated`

An ADR is never edited to change its decision. If a decision changes, a new
ADR supersedes it and the old one is marked `Superseded`. The history of
wrong turns is as useful as the current answer.

---

## ADR-0001 — v1 Scope Boundary

- **Status:** Accepted
- **Date:** 2026-08-24
- **Deciders:** Author

### Context

`prompt.md` specifies seven areas of work: vault templates, a session
pipeline, a consistency/editorial pass, an interactive `new_book.py`
intake interview, GitHub Actions scheduling, an approval gate, and a
Cousins/Vercel publishing endpoint.

Three problems with building all of it:

1. **Cousins is undefined.** `prompt.md` says to write chapters into
   "whatever Cousins uses for storage." There is no specification of what
   Cousins is, what it stores, or where it runs. Building against it means
   building against an assumption.
2. **Publishing delivers nothing until the prose is good.** The value of a
   publish endpoint is zero if the generator upstream produces chapters
   nobody wants to read. That question is currently untested.
3. **A rigid CLI questionnaire is a poor interview instrument.** The story
   bible is the single artifact that determines all downstream quality. A
   fixed sequence of prompts cannot follow up on an interesting answer,
   cannot notice a contradiction, and cannot push back on a vague premise.
   A conversation can.

### Decision

v1 builds the core local pipeline only:

| Phase | Deliverable |
|-------|-------------|
| 1 | Vault templates + config loader |
| 2 | Provider layer (Gemini, OpenRouter, Groq) with retry, fallback, dry-run |
| 3 | Single-chapter generation with word-count continuation |
| 4 | Deterministic style checks (pure Python, zero API cost) |
| 5 | Editorial delta pass (schema-validated, append-only apply) |
| 6 | Session state machine + resume |

Deferred, explicitly not built in v1:

- GitHub Actions scheduling and the approval-gate workflow
- `new_book.py` as an interactive CLI interview
- The Cousins `POST /api/publish-chapter` endpoint and its client

`new_book.py` is reduced to a scaffolder: it creates
`vault/<book-slug>/` with blank templates and exits. The interview itself
is conducted conversationally with Claude, which writes the answers
directly into the vault files.

### Consequences

**Positive**

- The critical path is short: the first thing built is the first thing that
  can be judged.
- No design effort is spent on an undefined external dependency.
- One deliverable (`new_book.py` interactive CLI) is deleted outright, and
  the replacement is better at the job.

**Negative**

- No automation in v1. Every session is run by hand. This is intentional
  (see ADR-0003) but it means the project does not feel "automatic" for a
  while.
- Chapters accumulate in the vault with nowhere to go. Acceptable: they are
  readable markdown.

**Neutral**

- Deferred work is documented, not discarded. Phases 7+ are sketched in
  [architecture.md](architecture.md) so the code does not paint itself into
  a corner.

### Alternatives considered

- **Core + GitHub Actions, defer only publishing.** Rejected: puts CI
  debugging on the critical path before the local pipeline is proven, which
  reliably doubles iteration time. Every failure becomes a runner failure.
- **Everything in `prompt.md`, phased.** Rejected: commits documentation and
  design effort to Cousins, which is undefined, and to an interview CLI that
  is inverted effort.

---

## ADR-0002 — Python Toolchain

- **Status:** Accepted
- **Date:** 2026-08-24
- **Deciders:** Author

### Context

Every future session needs to know, without asking, how to add a
dependency, run the test suite, format code, and enter the environment. An
unstated toolchain gets re-litigated every session and drifts.

There is also a specific technical driver. The editorial pass is the
highest-risk component in the system: an LLM returns a structured delta that
is then applied to the story bible. If that delta is malformed and applied
anyway, canon is corrupted silently. Schema validation is not optional
there, so the toolchain must make it cheap.

### Decision

| Concern | Choice |
|---------|--------|
| Environment + dependencies | `uv` with `uv.lock` |
| Project config | `pyproject.toml`, single source |
| Data validation | Pydantic v2 |
| HTTP | `httpx` |
| YAML | `pyyaml` |
| Terminal output | `rich` |
| Env loading | `python-dotenv` |
| Lint + format | `ruff` (both) |
| Tests | `pytest` |

Pydantic v2 is used for three distinct jobs: parsing and validating
`models.yaml`, validating the editorial pass JSON response against a strict
schema before any file is touched, and typing the chapter frontmatter.

### Consequences

**Positive**

- One binary (`uv`) for env, install, lock, and run. No Poetry/pipenv/conda
  drift across sessions.
- Lockfile from day one, so a session six weeks from now resolves the same
  versions.
- Pydantic gives the editorial-pass validation gate essentially for free,
  and its `ValidationError` is the natural place to hang a JSON-repair retry.
- `ruff` replaces black + isort + flake8, so there is one formatter config
  and one lint config.

**Negative**

- `uv` is newer than Poetry. If it is not installed, the first step of any
  session is installing it.
- Pydantic v2 has real API differences from v1. Any snippet found online
  must be checked for which major version it targets.

**Neutral**

- All of these work identically in a GitHub Actions runner when Phase 7
  arrives.

### Alternatives considered

- **pip + `requirements.txt`.** Rejected: no lockfile by default, manual
  pinning, and dependency drift between the author's machine and CI is
  exactly the class of problem that wastes a session.
- **Poetry.** Rejected: slower resolution, heavier CI install, and its
  resolver occasionally stalls on loose constraints. `uv` is strictly faster
  at the same job.

---

## ADR-0003 — Session Shape

- **Status:** Accepted
- **Date:** 2026-08-24
- **Deciders:** Author

### Context

`prompt.md` specifies two chapters per session on a daily cron. Two problems.

**Coupling.** Two chapters in one session creates an intra-session
sequential dependency. If chapter N is bad, chapter N+1 was written on top
of it and is also wasted. A partial failure between them leaves the vault in
a half-updated state that the resume logic must handle. Neither cost buys
throughput: running a one-chapter session twice produces the same two
chapters with half the blast radius.

**Cadence mismatch.** A daily cron producing 2000 words requires the author
to read and review 2000 words per day, indefinitely. The scarce resource in
this system is author attention, not free-tier API quota. Sizing the
automation to the API's capacity guarantees an ever-growing queue of
unreviewed chapters, which is the failure mode where the whole project
quietly dies.

### Decision

**One chapter per session. Manually triggered.**

```
write-session --book <slug>
```

runs exactly one chapter: assemble context → generate → continuation loop
if short → deterministic style checks → editorial delta pass → apply delta →
write `status: pending-review` → session report.

No cron in v1. The author runs the command when ready for the next chapter.

Automation is not abandoned — it is sequenced. When it arrives (Phase 7+),
the cadence is chosen to match sustainable review throughput, and a
concurrency gate refuses to generate while an unreviewed session is
outstanding.

### Consequences

**Positive**

- The state machine is markedly simpler: one chapter has one status, and
  resume has one thing to resume.
- One editorial pass per chapter means a clean 1:1 mapping between a
  chapter and its continuity delta, which makes the delta auditable.
- Generation rate is naturally bounded by the author's willingness to run
  the command, so the review queue cannot silently grow.

**Negative**

- More editorial-pass calls per chapter written than the 2-chapter batch
  would need. The editorial model is the tightest-rationed free tier in the
  stack, so this consumes the scarcest quota faster per chapter.
  Mitigation: Phase 4's deterministic style checks are pure Python and
  remove the largest category of work from the LLM editorial pass entirely.
- Nothing happens unless the author does something. This is the point, but
  it is also a real cost.

### Alternatives considered

- **2 chapters per session, manual trigger.** Rejected: retains the
  coupling and blast-radius problems to save editorial-pass calls, and
  Phase 4 addresses that quota pressure more directly.
- **1 chapter per session, weekly cron.** Rejected for v1 only. This is the
  most likely shape for Phase 7 and the code should not preclude it.

---

## ADR-0004 — Vault Location and What Gets Committed

- **Status:** Accepted
- **Date:** 2026-08-24
- **Deciders:** Author

### Context

The vault is the story bible, the chapters, and all continuity state. Two
questions: where does it live relative to the engine, and what part of it
enters git.

The engine needs vault content to test against — a config loader, an outline
parser, and a delta applier cannot be tested without files to parse. But the
author's actual manuscript is private work in progress.

### Decision

**Location:** `vault/<book-slug>/` inside this repository. Book-scoped from
day one, so no two books can ever contaminate each other's continuity.

**What is committed:**

- Real manuscripts are **gitignored**. They stay local.
- A dummy book, `vault/example-book/`, is **committed**. It is a complete,
  realistic vault — story bible, style guide, a chapter manifest, two or
  three short chapters, a populated continuity tracker — and it is the
  fixture every test and every future CI run exercises.

`.gitignore` implements this as an ignore-all-then-unignore-one rule so that
adding a new real book never requires touching `.gitignore` again.

**Path resolution:** the vault root is resolved from configuration and is
never hardcoded. Splitting the vault into a separate repository later is a
config change, not a refactor.

### Consequences

**Positive**

- The manuscript never leaves the author's machine.
- Tests and CI have a real, committed fixture to run against, so "does the
  outline parser work" is answerable without private data.
- One repo means development is a single checkout with no cross-repo
  coordination.

**Negative — the significant one**

- **Git is no longer the safety net for real vault content.** Several
  mitigations in this project's design assume git history can recover a
  corrupted continuity tracker: "keep the tracker append-only and commit
  each version so git is the safety net." With the real vault gitignored,
  that recovery path does not exist for real books. It exists only for
  `example-book/`.

  This is an accepted risk, not an oversight. A replacement snapshot or
  backup mechanism is required before the pipeline is allowed to write to a
  real vault. Tracked as an open question — see
  [open-questions.md](open-questions.md), OQ-01. **Phase 5 (the editorial
  delta pass, the component that writes to canon) must not ship against a
  real vault until OQ-01 is resolved.**

- Engine and manuscript share a repo, so open-sourcing the engine later
  requires a history split.

### Alternatives considered

- **Separate vault repo.** Rejected for now: two-repo commits are not
  atomic, so "chapter written + continuity updated" can no longer be one
  recoverable unit, and CI needs a second checkout with its own token.
  Because paths are configurable, this remains available later at low cost.
- **Commit everything including real books.** Rejected by the author: the
  manuscript is private.

---

## ADR-0005 — All Providers Failed → Stub Draft

- **Status:** Accepted
- **Date:** 2026-08-25
- **Deciders:** Author

### Context

The pipeline's availability strategy is layered fallback across six
providers, with retries only for rate-limits. But fallback chains are
finite: an extreme session can exhaust every route (simultaneous quota
exhaustion, a regional outage, all keys revoked). The router then returns
a terminal outcome and the drafting loop must decide what to do. Three
bad options exist:

1. **Write nothing.** The session dies silently; the author returns to no
   artifact, no record of what failed, and no way to distinguish "never
   ran" from "ran and died".
2. **Retry forever.** Burns quota against providers that are already
   refusing, and violates the permanent-failure rule (best-practices §8.3).
3. **Pretend success.** Flip the manifest to `written` on nothing. This
   poisons canon state — the worst possible outcome in a system whose
   whole point is trustworthy continuity.

### Decision

When every route is exhausted, the session **still writes output**: a
clearly-marked stub draft at `chapters/chapter-NNN.md`, produced locally
at zero cost, containing:

- frontmatter with `status: failed-stub`, `fallback_triggered: true`, and
  the terminal failure summary (last error per provider attempted);
- a placeholder body stating that generation failed and must be re-run
  with `--force`.

Hard guarantees around it:

- The manifest status **stays `planned`** — the stub never counts as
  written.
- Downstream phases (summaries, editorial deltas, continuation tails)
  treat `failed-stub` chapters as absent.
- No API calls are made producing the stub; the cost of total failure is
  exactly zero.

A re-run with `--force` replaces the stub with a real attempt.

### Consequences

**Positive**

- Every session leaves an auditable artifact: what was attempted, what
  failed, where to resume.
- The invariant "the engine never lies about what it wrote" holds even at
  total failure.
- Zero-cost guarantee survives the worst case, not just the happy path.

**Negative**

- A stub file exists where a reader expects prose; mitigated by the
  explicit `failed-stub` status and placeholder body.
- Downstream code must remember to skip `failed-stub` chapters — this is
  now a spec requirement (specs.md §3), not an implementation detail.

### Alternatives considered

- **Exit non-zero, write nothing.** Simplest, but loses the audit trail
  and makes automated resumption harder. Rejected by the author: "write
  something out, even if trash."
- **Quarantine directory for stubs.** Cleaner vault hygiene, but splits
  the "one chapter number, one file" rule that makes the vault legible.

### Implementation note (2026-08-26, Session 5)

Implemented in `drafting/generate.py::_write_failed_stub` with two
deliberate refinements, recorded so the ADR and code do not drift:

- `fallback_triggered` is written as `false`, not `true` — on a terminal
  failure nothing ever succeeded, so "fallback fired" would be a lie.
  The stub instead carries the terminal outcome in its body (last error
  per provider attempted) and an empty `actual_model`.
- The session exits 1 after writing the stub and audit JSON, so
  automation observes failure while the artifact still exists.

Verified against live providers via fakes:
`test_all_routes_exhausted_writes_stub_manifest_untouched`,
`test_permanent_failure_never_walks_the_chain`,
`test_stub_replaced_by_rerun_with_overwrite`.



## ADR-0006 — Local model lane

**Date:** 2026-08-31 · **Status:** accepted · **Session:** 7

### Context

Every provider lane in this project has the same structural weakness:
someone else decides whether it still exists. AiHubMix's free tier turned
out to be ~10 lifetime requests (#12). TokenRouter's token quota was dead
on arrival and its catalog held three zero-priced models (#21). `:free`
slugs are renamed and pulled without notice — the reason model IDs are
configuration and never literals in code.

The author has a gemma-4-12b QAT model served locally by llama.cpp. A
spike drafted the identical ch-003 prompt twice: once as-is, once with a
rhythm instruction appended. The second draft passed every threshold the
example-book declares — the only one of three drafts to do so, against a
committed minimax-m3 chapter that fails on sentence-length mean.

### Decision

Add `providers/local.py` as an OpenAI-compatible provider pointed at the
local server, and place it at the END of the drafting fallback chain,
below groq.

Last-resort, not primary. The prose evidence is one prompt, one seed, one
run. What the lane is being adopted for is availability: it is the only
route in the stack that no third party can revoke.

### Consequences

- The chain gains a lane that never rate-limits and never costs anything.
- **It is dead whenever the laptop's server is not running.** Every other
  lane fails on the network; this one fails on the host. A session that
  reaches it on a machine with no server gets a connection error, which
  the router must classify as model-unavailable (fallback-eligible),
  never as a permanent failure (invariant 3).
- The server's context window (8192 today) is smaller than the book-wide
  `token_budget` of 12000. The budget is a per-book creative/config
  value; the context window is a per-route physical limit. They are
  different things and the smaller must win at call time.
- Model identity is weaker than a hosted lane's: whatever GGUF is loaded
  answers to whatever `model` string is sent. Provenance records what was
  requested, not what actually ran — a real gap, accepted because the
  lane is last-resort.

### Alternatives considered

- **Promote above groq.** models.yaml already calls gpt-oss-120b the
  weakest prose, and gemma+rhythm beat it on every measured metric — but
  against one prompt and one seed. Rejected until there is more evidence
  than a single spike.
- **Primary drafting lane.** Rejected outright: latency is 35–46s on
  this hardware, quality is unproven across POVs, and the author's
  standing rule is that routing does not change unless a newcomer
  clearly beats minimax-m3.
- **No lane, keep the spike script.** Rejected: a quota emergency is
  exactly when nobody wants to go find a shell script.

---

## ADR-0007 — Canon changes are transactional

**Date:** 2026-09-01 · **Status:** accepted · **Session:** 8

### Context

Invariant 2 says a delta is applied completely or not at all. Until
Phase 5 that was a policy with no mechanism behind it, because nothing
wrote to canon.

Applying a delta is not one write. It is a summary appended to the
ledger, N facts appended to the tracker, M threads opened, K threads
flipped, and J questions queued — across four files. Each primitive
verifies its own write, so a bad write cannot land. What no primitive
can see is the *fourth* append failing after the first three succeeded:
a thread ID that does not exist, a summary that duplicates one already
present, a disk that fills. Canon is then in a state matching no
session, no chapter, and no audit record, while the run reports partial
success — pitfall A2 exactly.

### Decision

`vault.canon_transaction(paths)` — a context manager that copies every
canon file it is given to a scratch directory, yields, and on **any**
exception restores all of them and re-raises as `VaultError`. The
reconciler runs the entire apply inside it.

Two properties make this safe to have in a codebase whose central rule
is that no model writes a canon body:

- **The only bytes it can write are bytes it read from the same file
  moments earlier.** There is no path from model output to a restore.
- **On failure it KEEPS the snapshot directory and names it in the
  error.** A restore that itself failed is diagnosable rather than
  silent.

### Consequences

- Invariant 2 becomes a mechanism instead of an aspiration, and the
  failure paths are the tested ones — a delta that fails at the fourth
  step leaves canon byte-identical.
- Canon files are copied on every reconcile. At vault sizes this project
  will ever see, that cost is invisible.
- **It is not a resolution of OQ-01.** It recovers one interrupted
  apply. It does not give an author yesterday's canon back, and nothing
  in it survives the process exiting between the restore and the raise.
- It is a general file-restoring function living in the module whose
  rule is "no general canon writer". The scoping above is what keeps
  that honest, and it is the first thing to re-check if the function
  ever grows a parameter.

### Alternatives considered

- **Pre-flight validation only** — check every thread ID and summary
  slot before writing anything. Cheaper, and it would have caught the
  common cases. Rejected as the *only* mechanism: it cannot catch a
  disk error, and "we validated hard enough" is how half-applied state
  arrives in every system that has it.
- **Write to temp files and rename at the end.** Atomic per file, and
  genuinely better if the four files were being rewritten wholesale.
  They are not — each primitive appends one line and re-parses to prove
  it, and staging that would mean reimplementing every primitive
  against a shadow tree.
- **Accept partial application and report it.** Rejected by invariant 2,
  and by pitfall A2's argument that a partial apply is worse than a
  lost one because it reports success.

---

## ADR-0008 — Continuity checking is not exclusively the model's job

**Date:** 2026-09-01 · **Status:** accepted · **Session:** 8

### Context

The editorial pass exists to catch what a human re-reader would not.
Its first real test was the original ch-005 (`git show d518b74:...`),
which says "nine corrections on the spring-tide page" against ch-001's
locked fact that the page carries **two**. That fact was retrieved into
the prompt, six lines above the chapter text.

`gemini-3.5-flash-lite` returned an empty violation list, and the
chapter summary it wrote — which the reconciler appends to canon —
repeated "nine corrections". A tightened prompt made it perform a
check and report a *different*, wrong violation. `mistral-medium-latest`
caught it unaided, at 2.7x the output tokens and with 8-9 proposed facts
including set dressing.

Two things were now true at once: the machinery was verified end to end,
and a pass returning `[]` was indistinguishable from a clean chapter.

### Decision

Move the narrowest, most mechanical slice of continuity checking into
Python, and hand its findings to the model as evidence.

`quality/continuity_numbers.py` compares quantities in the chapter
against quantities in the **retrieved** locked facts — the same set the
model is shown — and renders the disagreements into the editorial
prompt beside the Phase 4 style metrics. It is evidence, never a gate,
and never a verdict on prose (specs §14's rule, extended).

### Consequences

- With the finding in its prompt, the model that missed the case twice
  caught it on both subsequent runs. That let routing go back to the
  cheaper editor (decision #31) — the judgement now lives partly in
  code, where no free tier can withdraw it.
- The check is free, runs every chapter, and works identically whichever
  editor answers, including a fallback lane that demonstrably misses
  things.
- **Its false-positive guards are tuned to measured failures, not to
  theory.** One shared word between the fact and the chapter sentence
  let all three "years" conflicts in ch-005 through — including the
  exact false positive the live model reported — so it requires two; and
  a sentence that also states the canonical number is treated as
  consistent. Both thresholds are string-matching sensitivity, not
  creative constants, so decision #22 does not apply.
- The tuning is the maintenance burden. A fixture test asserts one
  finding on the pre-fix ch-005 and zero on every committed chapter, so
  a loosened guard that starts crying wolf fails the suite rather than
  training the author to ignore findings.
- **Only bare numbers are covered.** Names, dates, orderings, rewritten
  quantities ("half a dozen"), and capabilities are untouched, and there
  is no evidence yet about whether a model catches those (OQ-10's
  remaining scope).

### Alternatives considered

- **Better prompt only.** Tried first, measured, and insufficient: it
  changed behaviour without changing accuracy.
- **Stronger model only** (keep mistral-medium primary). It works, and
  it is the only model that has caught a contradiction unaided — kept as
  the fallback for exactly that reason. Rejected as the primary answer
  because it puts the project's core guarantee on someone else's free
  tier, at 2.7x tokens, with a fact list that grows the ledger.
- **Ask fact-by-fact** — one call per locked fact, or a per-fact verdict
  list in the schema. N× the quota on the tightest-rationed model in the
  stack, to do deterministically what a regex does for free on the
  commonest class.
- **Accept and re-scope the feature** — call the pass a summariser and
  fact-proposer and stop claiming it catches contradictions. Honest and
  free; rejected because it gives up the feature the project was built
  around without first trying the cheap engineering.

---

## ADR-0009 — A chapter that contradicts locked canon is not reconcilable

**Date:** 2026-09-01 · **Status:** accepted · **Session:** 8

### Context

In the live run that first caught the ch-005 contradiction,
`mistral-medium-latest` returned a delta that flagged "nine corrections"
against the locked "two" as a **critical** violation and, in the same
object, proposed:

```json
{ "category": "object", "entity": "",
  "fact": "The spring-tide almanac page carries nine corrections in Ovist's hand that he did not write.",
  "source_chapter": 5 }
```

Nothing in the reconciler stopped that. A later run went further and
suggested a canon patch reading "Update the spring-tide almanac page
correction count to nine" — the model proposing to edit the author's
canon so the contradiction would stop being one.

The pass that detects a contradiction was the fastest route for that
contradiction to become canon.

### Decision

`reconcile()` refuses a delta carrying any `critical` continuity
violation, before the transaction opens. Nothing is appended, no patches
report is written, the chapter stays `editorial-pending`, and the error
names the violated fact, the chapter text, and what a human has to do.

**There is no override flag.** The fix is an author action either way —
correct the prose, or demote the fact the prose disagrees with — after
which the pass re-runs cleanly. A caller able to skip the check would
only ever use it to write the thing the check exists to stop.

Warnings remain advisory and reconcile normally.

### Consequences

- A critical violation can no longer become canon by any route: not as a
  fact, not as a summary paragraph, not as a thread.
- **A false-positive critical violation blocks reconciliation until a
  human looks.** That is a real cost, and it is the right direction to
  fail: the alternative is canon that quietly disagrees with itself.
  Live evidence says both editors over-report as readily as they
  under-report, so this will fire on chapters that are fine.
- The engine now has a state where a drafted, style-checked chapter
  cannot complete without an author. Phase 6 must surface that as a
  distinct outcome, not as a generic error.
- Severity is chosen by the model, so the boundary between "blocks
  everything" and "advisory" is a model's word. `warning` is the safe
  default for anything the editor is unsure about, and the prompt says
  so.

### Alternatives considered

- **Drop only the contradicting facts, apply the rest.** Requires
  matching model text against model text to decide which fact a
  violation refers to, and it half-applies a delta the model itself says
  describes a broken chapter — invariant 2 in spirit if not in letter.
- **Append everything; the `[model]` origin tag makes it demotable**
  (pitfall A4). Zero code. Rejected because retrieval would then feed
  both sides of the contradiction into the next chapter's prompt, which
  is how one wrong number becomes three chapters of wrong plot.
- **Refuse only when the violated fact is `[author]`-origin.** Tempting
  and more surgical. Rejected for now: it makes the rule depend on a
  distinction the author has not yet had reason to maintain, and no case
  exists to tune it against.

---

## ADR-0010 — Session pointer persistence and resumption state machine

**Date:** 2026-09-03 · **Status:** accepted · **Session:** 9

### Context

Specs §11 specifies a phase lifecycle for each chapter session:

```
target -> drafted -> styled -> [editorial-pending | reconciled] -> complete
```

A crash, network timeout, or kill signal during drafting, style checking,
editorial review, or reconciliation leaves the vault in an intermediate
state. Without an authoritative, persistently updated pointer:

1. A subsequent run cannot distinguish an interrupted draft from a completed
   one that simply hasn't been reviewed yet.
2. A crash during style checking or editorial review would risk silently
   re-running drafting, generating new prose and orphaning the existing chapter.
3. Architecture §3 identifies `log/next-step.md` as the single file whose
   mode is overwrite: a pure operational pointer with no history value.
   Yet the one-writer rule (invariant 1) requires all disk writes to go
   through narrowly-scoped primitives in `core/vault.py`.

### Decision

1. **`write_next_step` is the only overwrite primitive in `core/vault.py`.**
   It writes `log/next-step.md` and immediately re-reads and re-parses the
   file from disk, verifying that the on-disk content matches the input
   `NextStep` object. No general "write canon file" primitive exists.
2. **Strict schema enforcement (`core/state_machine.py`).** Frontmatter
   fields (`next_chapter`, `next_pov`, `last_session_id`, `last_session_phase`,
   `last_session_status`, `blocked`, `blocked_reason`) are validated with
   `extra="forbid"`. The prose note sits below the frontmatter.
3. **Persist before entering the next phase.** `SessionStateMachine.transition`
   enforces legal phase transitions (`validate_transition`) and writes the
   new phase pointer to disk *before* the subsequent work begins (specs §11).
4. **Fail closed on blocked sessions.** When `blocked: true`, any phase
   transition is refused with `StateMachineError` until explicitly unblocked.

### Consequences

- **Positive:** Every crash between phases is fully resumable; the pipeline
  always knows the exact phase reached.
- **Positive:** Overwrite authority is strictly confined to `log/next-step.md`;
  all canon files remain append-only or single-cell status flips.
- **Negative:** Every phase step incurs a disk write and verification read.
  Since this touches a single small markdown file locally, latency is
  negligible (< 1 ms).
- **Residual:** Resumption orchestration in `cli/write_session.py` (reading
  the pointer on startup and branching) is deferred to Batches 3 & 4.

### Alternatives considered

- **General file-writer primitive.** Rejected: opens the door to overwriting
  canon files, defeating invariants 1 and 5.
- **Write `next-step.md` only on session completion.** Rejected: a crash during
  editorial pass or reconciliation would leave the session in an untracked
  state, making resumption impossible.
- **In-memory state machine only.** Rejected: does not survive process
  termination.


---

## ADR-0011 — `write-session` orchestration, resume gate, and outcome contract

**Date:** 2026-09-04 · **Status:** accepted · **Session:** 10

### Context

ADR-0010 built the pointer and the state machine and deliberately left the
orchestration out: nothing read `log/next-step.md` on startup, and nothing
invoked the editorial pass from a shell. That was correct while the pass was
untested library code, and it stops being correct now — Phase 6 Batches 3
and 4 exist to close exactly that gap.

Wiring it up forces four questions the earlier ADRs left open, because each
of them only becomes answerable once a single command owns the whole
lifecycle:

1. `complete` is defined (specs §11) as "chapter status = pending-review",
   and no primitive can set a chapter's status. specs §3 already records
   this as Phase 6 work.
2. `editorial.enabled` has been parsed and unread since Phase 5. The specs
   §11 diagram has no exit from `styled` that does not pass through the
   editorial pass, so honouring the key requires a lifecycle edge that does
   not exist.
3. specs §15 defines exit codes 0 and 1 only. A chapter that drafted
   successfully but did not reconcile is neither.
4. specs §15 lists `--resume`, and specs §11 says a re-run "resumes from the
   recorded phase, or refuses with a precise message". Something has to
   select between resuming and refusing.

### Decision

1. **`vault.flip_chapter_status(book_root, chapter_number, new_status,
   expected_current=...)`** — the second single-cell mechanical edit, beside
   `flip_manifest_status`. It rewrites one frontmatter key and re-parses the
   file to verify. It never touches the body, so `generated_hash` (computed
   over post-frontmatter bytes) is unaffected and a hand-edited chapter stays
   detectably hand-edited (decision #25).
2. **`editorial.enabled: false` is honoured**, and `styled -> complete` joins
   `LEGAL_TRANSITIONS` as the edge that path takes. It is the only way to
   reach `complete` without canon being written, and it is what a real vault
   can safely run while OQ-01 is open.
3. **Exit code 2 = drafted, not reconciled.** `editorial-pending` from any of
   its three §11 routes exits 2, and the CLI names which route was taken. 0
   stays "drafted and finished", 1 stays "refused, or all routes exhausted".
4. **`--resume` is required to continue an interrupted session.** Without it,
   a run whose pointer records a mid-flight phase for an existing chapter
   refuses, naming the chapter, the phase, and the flag. `--resume` re-enters
   the pipeline at the recorded phase and never re-drafts existing prose;
   replacing prose is still `--force` plus a typed confirmation (invariant 5).
   `--force` on a mid-flight session abandons it through
   `SessionStateMachine.restart()`, which writes a fresh `target` pointer
   without validating a transition — abandoning a session is not a
   lifecycle step, and `validate_transition` correctly refuses
   `drafted -> target`. It is the only write that skips validation, it is
   named for what it does, and the automatic path never calls it.

### Consequences

- **Positive:** one command owns the documented lifecycle end to end, and
  every phase it reaches is on disk before the next one starts.
- **Positive:** a caller can tell the three outcomes apart without parsing
  prose — 0 finished, 1 nothing happened, 2 prose written and canon clean.
- **Positive:** `enabled: false` is a real drafting-only mode, so the engine
  has a configuration in which it provably cannot write canon.
- **Negative:** the writer allowlist grows by one, and every future reader of
  `vault.py` has one more primitive to account for. Mitigated by the
  allowlist test, which fails until the addition is made deliberately.
- **Negative:** `--resume` is a flag the author must remember. The refusal
  message carries the exact command, so the cost is one re-run, not a
  guessing game.
- **Residual:** exit 2 is a new contract for automation that does not exist
  yet (ADR-0001 defers scheduling). It is cheap to define now and expensive
  to retrofit once something depends on 0-or-1.
- **Residual:** resuming at `styled` or `editorial-pending` re-runs the
  editorial call and spends quota. Resuming at `reconciled` spends nothing.

### Alternatives considered

- **Leave chapter status at `draft`.** Rejected: `complete` would then be a
  phase with no observable effect on the chapter it completes, and specs §3's
  note would stay unimplemented with nothing scheduled to implement it.
- **Route disabled-editorial to `editorial-pending`.** Rejected: no pass is
  pending. The pointer would report a state the author cannot resolve by
  re-running, and exit 2 would fire on a configuration working as intended.
- **Exit 1 for `editorial-pending`.** Rejected: it is the same code as "the
  chapter already exists and I refused", so no script could distinguish
  "nothing happened" from "1000 words landed and canon is clean".
- **Exit 0 for `editorial-pending`.** Rejected for the mirror reason: a
  chapter whose continuity was never checked is not a finished chapter, and
  OQ-10 is precisely the reason not to let that read as success.
- **Automatic resumption with no flag.** Rejected: bare re-runs would spend
  free-tier calls on a chapter the author may not remember starting. Daily
  caps are the hardest constraint in the project.

---

## ADR-0012 — The deterministic layer extends to entity disagreements

**Date:** 2026-09-04 · **Status:** accepted · **Session:** 10

### Context

ADR-0008 established that continuity checking is not exclusively the
model's job, and specs §16 implemented that for exactly one class: a bare
number disagreement. Everything else was left to the editorial model, and
OQ-10 recorded honestly that nothing else had been tested.

The experiment OQ-10 asked for was run on 2026-09-04. One sentence was
planted in a scratch copy of ch-005 contradicting a locked fact by
identity, with no digit changed: *"Brannec Tull had kept it since before
Ovist's clerkship"* against `[character:ovist-rhoam]` *Ovist Rhoam has
kept the echo ledger for eleven years* — a fact retrieval puts in this
chapter's prompt, one of only two it selects.

| Run | Prompt | Result |
|---|---|---|
| 1 | packaged | 0 violations, and proposed the contradicted fact as NEW canon |
| 2 | packaged | 0 violations, same re-proposal, plus a summary naming an office that does not exist |
| 3 | packaged + one simulated entity finding | 1 `critical`, correctly quoted, no re-proposal |

The instructions were identical in all three. The only variable that
changed the outcome was evidence. `mistral-medium` — the one model that
has ever caught a contradiction unaided — returned HTTP 429 on eight
consecutive attempts and could not be measured.

### Decision

**`quality/continuity_entities.py` runs before the editorial call, beside
the number check, and its findings go into the prompt as evidence.**

1. It compares the **retrieved** facts against the chapter, so a finding
   always points at something the prompt actually contains.
2. It scans **paragraphs**, not sentences. An identity claim routinely
   spans a full stop; sentence scoping missed the planted case.
3. Its false-positive guard is **proximity, not presence**: the name the
   fact's own wording sits nearest is the one the paragraph is making the
   claim about.
4. It measures and never judges (specs §14's rule). No exit code, no
   gate, no threshold in the engine that is about prose.

### Consequences

- **Positive:** the class that was demonstrably invisible to the primary
  editor is now handed to it as evidence, and the live re-run confirms
  the catch with the generated finding rather than a hand-written one.
- **Positive:** it also suppressed the model's habit of re-proposing the
  contradicted fact as canon — which decision #29 could never have
  refused, because nothing was reported as violated.
- **Negative:** a second heuristic to keep tuned, with its own stoplist
  and its own floor. Both are pinned by a test asserting zero findings on
  every committed chapter.
- **Negative:** it can only see names it can match to
  `characters/index.yaml`. A book whose prose uses nicknames, titles, or
  surnames absent from the index gets a quieter check without being told.
- **Residual:** dates, orderings and capabilities remain unaddressed by
  any deterministic layer and untested in the model. OQ-10 stays open for
  exactly that, and no wording may imply otherwise.
- **Residual:** the fallback editor was never measured on this case.

### Alternatives considered

- **Prompt wording alone.** Rejected on measurement, twice over: run 3
  isolated the variable, and Session 8's run 2 showed a tightened prompt
  producing a violation — the wrong one.
- **Route editorial to a stronger model.** That is the #28 → #31 loop
  already fought once. The stronger model is a fallback precisely because
  it is a free tier that disappears, and on this very case it returned
  429 on every attempt.
- **Suppress any paragraph naming the fact's own character.** Tried
  first; it killed the true positive, because denying someone a role
  means naming them.
- **Do nothing and keep OQ-10 open.** Rejected: the experiment had
  already produced the evidence, and leaving a measured, cheap, quota-free
  fix unbuilt while the pass silently missed the class is the failure
  mode pitfall A6 describes.
