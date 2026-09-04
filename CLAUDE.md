# CLAUDE.md

Operating instructions for any Claude session working in this repository.
Read this first, then [progress.md](progress.md).

---

## What this project is

A local automation pipeline that drafts a novel one chapter at a time using
free-tier LLM APIs, with a markdown vault as the single source of truth and
a self-updating continuity layer.

**One sentence that explains most design decisions:** the vault is the
database, models are stateless and fallible workers, and Python — never a
model — decides what gets written to disk.

---

## Read order at session start

1. **[progress.md](progress.md)** — current state and the next-session brief.
   This is the handoff. Start here.
2. **[decisions.md](decisions.md)** — what is already settled. Do not
   relitigate anything in this file.
3. **[open-questions.md](open-questions.md)** — what is not settled, and
   what is blocked on it.
4. **[specs.md](specs.md)** — exact formats and schemas for whatever you are
   about to build.
5. **[pitfalls.md](pitfalls.md)** — before starting any phase.

Reference as needed: [architecture.md](architecture.md),
[best-practices.md](best-practices.md), [threat-model.md](threat-model.md),
[adr.md](adr.md).

Background: `prompt.md` is the original build spec. `*-analysis.md` are
three independent model reviews of it. **`prompt.md` is not authoritative
where these docs contradict it** — every deliberate departure is listed in
[progress.md](progress.md) with its rationale.

---

## Working rules

These are the author's explicit instructions. They are not suggestions.

**Write decisions immediately.** The moment the author makes a decision, it
goes into [decisions.md](decisions.md), and into [adr.md](adr.md) if it is
architectural — before any other work continues. Never carry a decision in
conversation and record it later.

**No sub-agents.** All work inline. Do not dispatch the Agent tool.

**Supersede, do not defend.** A decision is only as good as the evidence
under it. Decision #28 lived four hours: it routed editorial to a
stronger model because the cheaper one missed a contradiction, and #31
reversed it the same day once a deterministic check made the cheaper one
catch that same case. Write the new decision, mark the old one
superseded, and leave both in the ledger — the pair is more useful than
either row alone. This applies to docs as much as code: a doc sentence
that measurement has falsified gets rewritten with the measurement, not
quietly deleted.

**Verify doc claims against the code before repeating them.** This
repository's docs are load-bearing and they do drift: a full audit on
2026-09-01 found the authority table claiming the engine never writes
`plot-outline.md` (it flips one status cell), the provider layer counting
six modules when there were seven, and a dead model still named as the
editorial fallback. Grep the code before trusting a sentence about it.

**One phase per session.** Work in batches within the phase. Complete each
batch fully. Do not start the next phase because the current one finished
early.

**Commit after every task.** Small revertible units, so rollback is never
expensive. **Never push without asking.**

**Prepare the next session before ending this one.** Update
[progress.md](progress.md): what was done, what was verified, what is
blocked, and precisely what comes next. The next session starts from the
docs alone, with no conversational context. Leaving this incomplete is the
one failure that costs the most.

**Do not assume — ask.** But do everything that does not depend on the
answer first, then ask at the right moment. When asking:

- Explain what is actually being asked and its scope, so the question is
  answerable without reading the code
- Give real alternatives, not a rubber stamp
- Give a recommendation and say why
- Batch related questions together rather than interrupting repeatedly

**Report honestly.** Untested means untested. Partially done means say which
part. A phase marked complete in [progress.md](progress.md) is a claim that
its exit criteria were actually run and passed.

---

## Invariants

From [best-practices.md](best-practices.md) §8. Breaking one of these is an
ADR, never a shortcut. There are six.

1. **No model ever writes a canon file body.** The editorial model emits a
   schema-validated delta; Python appends. A model regenerating
   `continuity-tracker.md` will quietly summarise old facts away, and the
   system built to prevent continuity drift becomes the cause of it.
2. **Fail closed.** An invalid or partially-valid change is applied not at
   all. A half-applied delta corrupts canon while reporting success.
3. **Permanent failures never trigger fallback.** Only rate-limit,
   transient, and model-unavailable outcomes are fallback-eligible. A
   malformed prompt retried across three providers is a quota-burning
   retry storm that looks like a network problem.
4. **`.env` is never committed. Logs redact by allowlist, not blocklist.**
5. **The engine never overwrites author-written prose** without `--force`
   and explicit confirmation. Prose is the subject: the two mechanical
   cell edits (`flip_manifest_status`, `flip_chapter_status`) rewrite one
   cell each, byte-verify everything else, and never touch a body.
6. **A chapter that contradicts locked canon is not reconcilable.** A
   delta carrying a `critical` continuity violation is refused whole
   (ADR-0009). Added Session 8, after a live pass flagged a contradiction
   and proposed it as a new locked fact in the same delta. No override
   flag exists, and adding one would be an ADR.

---

## Structural facts worth knowing before you edit anything

- **`core/vault.py` is the only module that writes to disk.** Everything
  else returns data. This is what makes the authority model reviewable.
- **`vault.py` exposes narrowly-scoped primitives only** — as of Phase 6:
  `scaffold_book`, `write_chapter` (create-only, hash-verified), two
  single-cell mechanical edits — `flip_manifest_status` (one manifest
  row's status) and `flip_chapter_status` (one chapter's frontmatter
  `status`, never the body, so `generated_hash` is untouched) — five
  canon appends: `append_fact`, `append_thread`, `append_deepen_question`,
  `append_summary`, `flip_thread_status`, and one overwrite primitive:
  `write_next_step` (`log/next-step.md` pointer, specs §8, ADR-0010).
  **Each verifies its own write by re-parsing the file**, not by
  trusting the string it built. `canon_transaction` (ADR-0007) snapshots
  and restores canon around a multi-file apply; the only bytes it can write
  are bytes it just copied. There is deliberately no general "write canon
  file" function, and `test_vault_appends.py` asserts the exact set of
  public writers — add a primitive and that test fails until the list is
  updated on purpose.
- **`generated_hash` is computed by `vault.write_chapter`, never by its
  callers** — callers who supply one are rejected. It hashes the exact
  post-frontmatter bytes as stored (leading blank lines stripped,
  trailing newline included), then the file is re-read and verified.
- **A stale `generated_hash` is a feature, not a bug.** The hash is
  immutable (specs §3): when the author hand-edits a chapter, the
  mismatch is how the Phase 6 feedback loop learns an edit happened
  (pitfalls B5). Never "fix" a mismatch by recomputing the hash.
  `vault/example-book/chapters/chapter-005.md` is deliberately edited and
  deliberately stale (decision #25); `tests/test_vault_writing.py` asserts
  both halves — unedited chapters match, edited ones must not.
- **The editorial pass never writes.** `pass_runner` returns a validated
  delta or a refusal; `reconciler` is the only caller of the canon
  appends, and it runs the whole delta inside `canon_transaction` so a
  failure at the fourth append restores the three that landed. A delta
  is applied completely or not at all (invariant 2, pitfall A2).
- **The editorial prompt is engine-owned** (decision #26):
  `novel_engine/templates/editorial-prompt.md`, not per-book config. A
  test parses the example object it shows the model through
  `parse_delta`, so schema and prompt cannot drift apart silently.
- **A chapter that contradicts locked canon is not reconcilable**
  (decision #29). `reconcile()` refuses a delta carrying any `critical`
  violation, before the transaction opens. This exists because a live
  editor flagged "nine corrections" against a locked "two" AND proposed
  "the page carries nine corrections" as a new locked fact in the same
  delta. There is no override flag, deliberately.
- **The number check runs before the editorial call** (decision #30,
  `quality/continuity_numbers.py`). Quantities in the chapter against
  quantities in the retrieved facts; findings go into the prompt as
  evidence. It is what made the primary editor catch the case it had
  missed twice unaided. Its false-positive guards are TUNED to measured
  failures — two shared words beyond the counted noun, and a sentence
  that also states the canonical number is consistent. Do not loosen
  them without re-running the fixture check that asserts zero findings
  on every committed chapter.
- **The editorial pass catches number disagreements and nothing proven
  beyond that** (OQ-10). Names, dates, rewritten quantities and
  capabilities have never been tested. Do not describe the pass as a
  continuity guarantee.
- **`quality/` holds no numbers.** `metrics.py` measures and never judges;
  thresholds live in each book's `canon/style-guide.md` between
  `THRESHOLDS` markers. A book with no block gets metrics and no verdicts
  — there are no built-in numeric defaults anywhere in code (decision
  #22), and adding one would put a creative constant in the engine.
- **Editorial routing changed twice on 2026-09-01 and the pair is worth
  reading together** (decisions #28 then #31). It is now
  `gemini:gemini-3.5-flash-lite` → `mistral:mistral-medium-latest`.
  `mistral-large-latest` is DEAD — 403 `tier_not_allowed` on the key that
  verified it, while still listed in `/v1/models`. Probe a fallback lane
  with a real generation call before trusting it; a catalog listing
  proves nothing (pitfall C10).
- **The `local` provider needs no key and is always built.** It is the
  only entry in `core.config.KEYLESS_PROVIDERS`. A dead server surfaces as
  `ModelUnavailable` at call time, so the chain moves on (ADR-0006).
- **Model IDs, paths, thresholds, and word counts are configuration, never
  literals in code.** `:free` slugs are renamed and pulled without notice.
- **Chapter numbers come from the manifest in `plot-outline.md`**, never
  from counting files in `chapters/`.
- **Real vault content is gitignored** (ADR-0004). All development touching
  destructive paths runs against the committed `vault/example-book/`
  fixture.
- **`write-session` writes canon now, and OQ-01 blocks the whole command
  against a real vault** — not just the editorial modules, as it did
  through Phase 5. It runs against `vault/example-book/`, which git can
  restore. `canon_transaction` is NOT the resolution of OQ-01: it
  recovers one interrupted apply, not a session an author wants to undo
  tomorrow. The one safe shape for a real book today is
  `editorial.enabled: false`, which drafts and takes the `styled ->
  complete` edge without touching canon (decision #36).
- **The session pointer owns the target whenever a session is
  mid-flight**, not the manifest. Drafting flips the manifest row to
  `written`, so `next_target()` would skip straight past a chapter whose
  editorial pass never finished. `log/next-step.md` is what makes that
  chapter findable.
- **Resuming is opt-in.** A bare re-run of an interrupted session refuses
  and names the chapter, its phase, and `--resume` (decision #38).
  `--force` abandons the session instead, through
  `SessionStateMachine.restart()` — the one write that skips
  `validate_transition`, because abandoning is not a transition.
- **Exit 2 means editorial-pending**: prose on disk, canon deliberately
  untouched, resumable. 0 is `complete`, 1 is "nothing usable happened"
  (decision #37). A caller that treats 2 as failure will re-draft a
  chapter that already exists.
- **Reasoning/thinking stays OFF for drafting.** Measured 2026-08-31: 2x
  tokens, 2x wall time, worse prose, and the only draft that broke the
  fourth wall (pitfalls C8/C9). A local GGUF's chat template — not our
  code — decides this; read `/props` before trusting a local lane.

---

## Commands

```bash
uv sync                       # environment from uv.lock
uv run pytest
uv run ruff check --fix .
uv run ruff format .
uv add <package>              # never pip install

uv run write-session --book <slug> --dry-run   # assemble prompt, spend nothing
uv run write-session --book <slug>             # full lifecycle; 0/1/2
uv run write-session --book <slug> --resume    # continue from the recorded phase
uv run new-book --slug <slug>
uv run check-style --book <slug> --chapter N
```

`--dry-run` is the default way to iterate on prompts. Free-tier daily caps
are the hardest constraint in the project; assembling and reading a prompt
costs nothing, generating costs a call.

**There is no separate editorial command and there should not be one.**
`write-session` runs the pass as one phase of the lifecycle — the only
context where a delta has a chapter, a phase, and a pointer to record
itself against:

```bash
uv run write-session --book <slug>            # target -> ... -> complete
uv run write-session --book <slug> --resume   # continue an interrupted one
```

The free half of the continuity check still needs no key and no call:
`find_number_conflicts(parse_facts(tracker_text), chapter_body)`.

---

## Commit conventions

Types: `feat` · `fix` · `docs` · `chore` · `refactor` · `test`.

The body explains **why**, not what — especially for any deliberate
departure from `prompt.md`. The diff already shows what changed; what will
not be reconstructible in three months is the reasoning.

Trailer:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## The two things most likely to go wrong

**The original one.** Not a bug. The project builds a resumable,
provenance-tracked, hash-verified pipeline around a generator whose output
quality has never been tested, and discovers at chapter thirty that the
prose is competent and forgettable.

The architecture makes state safe. It does not make prose good — that comes
from the story bible, the style guide, the beat sheet, and the base model,
none of which are engineering problems. Keep OQ-04 (the prose spike) visible
and do not let it slip behind the interesting work.

**The one that stopped being hypothetical on 2026-09-01.** The continuity
layer catches nothing and says so in a way that reads as success. Pointed
at its first real case — a chapter saying "nine corrections" against a
locked fact saying two, with that fact in the same prompt — the editorial
pass returned an empty violation list and then wrote the contradiction
into the summary it appended to canon.

That specific case is now caught, by a deterministic check that runs
before the call (specs §16) and by a refusal to reconcile a chapter that
contradicts canon (invariant 6). Neither of those makes the general
problem go away. Every contradiction that is not a bare number — a name,
a date, an ordering, a capability — is still judged by a model that has
demonstrably returned `[]` on an easier case, and an empty violation list
is indistinguishable from a clean chapter (pitfall A6, OQ-10). Treat
every "no violations" result as unproven, and be suspicious of any
change that makes the pass cheaper or quieter.
