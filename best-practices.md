# Best Practices

Conventions for this repository. Two audiences: the author, and every future
Claude session. Where a rule exists to prevent a specific failure, that
failure is linked — a rule without a reason gets discarded under pressure.

---

## 1. Code conventions

**Toolchain** (ADR-0002): `uv`, `pyproject.toml`, Pydantic v2, `httpx`,
`pyyaml`, `rich`, `python-dotenv`. Lint and format with `ruff`. Test with
`pytest`.

```bash
uv sync                      # create/refresh env from uv.lock
uv run write-session --help  # run without activating anything
uv run pytest
uv run ruff check --fix .
uv run ruff format .
uv add <package>             # never pip install
```

**Typing.** Every public function is annotated. Pydantic models for anything
crossing a boundary — config files, API responses, the editorial delta.
Plain dataclasses are fine for internal-only structures.

**Errors.** Define the project's own exception hierarchy in `core/errors.py`
and raise those, not bare `Exception`. The provider layer must distinguish
its five outcomes as distinct types — that distinction is a correctness
requirement, not stylistic (pitfall C1).

Never write a bare `except:` or a silent `except Exception: pass`. If a
failure is genuinely ignorable, log it at `DEBUG` with the reason.

**The one-writer rule.** `core/vault.py` is the only module permitted to
write to disk. Everything else returns data. This is what makes the
authority model in [architecture.md](architecture.md) §3 enforceable rather
than aspirational — a reviewer checks one file, not the whole tree.

**Narrowly-scoped primitives.** `vault.py` exposes only what a phase
needs, each refusing everything else: as of Phase 3, `scaffold_book`,
`write_chapter` (create-only, hash-verified), and
`flip_manifest_status` (single-cell mechanical edit). The append
primitives the editorial reconciler will need — `append_fact()`,
`append_summary()`, `append_thread()`, `flip_thread_status()` — arrive in
Phase 5. It exposes no general "write canon file" function, and if a
caller wants to overwrite canon there must be no API for it beyond the
one explicit opt-in `write_chapter` already gates.

**Layering.** `providers/` knows nothing about novels. `quality/` and
`editorial/` know nothing about HTTP. `cli/` contains no logic, only
argument parsing and orchestration calls.

**Configuration over constants.** No model ID, path, threshold, or word
count is a literal in code. Model IDs especially — `:free` slugs are renamed
and pulled without notice (pitfall C3).

---

## 2. Prompt conventions

**Every prompt is a file, never an f-string buried in code.** Templates live
in `config/prompt-template.md` with named slots. This is what makes prompts
diffable, reviewable, and improvable — the highest-iteration surface in the
project should be the easiest to change.

**Slot order matters.** Put stable material first (style guide, character
sheet) and volatile material last (the beat, the previous chapter's tail).
Models weight recency; the instruction closest to generation should be the
one about *this* chapter.

**Always include the verbatim tail.** The previous chapter's final ~500
words, not just its summary. Summaries preserve what happened and destroy
how it read (pitfall B2).

**Be explicit about what not to do.** Banned phrases from `style-guide.md`
are injected as an explicit list. Negative constraints are weak on their own
but measurably better than absent, and the deterministic checks catch what
slips through.

**Ask for JSON only when you validate JSON.** Any prompt requesting
structured output must have a Pydantic model on the receiving end and a
repair-retry path. Never parse a model's JSON with `json.loads` and hope.

**Iterate with `--dry-run`.** Prompt tuning is the highest-iteration
activity in the project and free-tier quota is the hardest constraint on it.
Assembling and reading the prompt costs nothing; generating costs a call
from a daily cap.

---

## 3. Working with model output

**Model output is data, never instruction.** It is parsed, validated,
and applied by code that decided in advance what it would accept.

**Never let a model emit a file body destined for canon.** Delta only
(pitfall A1). This is the single rule most likely to be softened under
deadline pressure and the one that kills the project when it is.

**Fail closed.** An invalid delta means append nothing and mark
`editorial-pending`. A half-applied delta is worse than a lost one: it
corrupts canon while reporting success (pitfall A2).

**Record what actually happened.** `assigned_model` and `actual_model` are
both written to every chapter's frontmatter, always. When a chapter's voice
is wrong, the first question is which model wrote it, and that must be
answerable months later.

**Never derive a filesystem path from model output.** Model-named paths are
recorded as text in the patches file and never used to write
([threat-model.md](threat-model.md) T4).

---

## 4. Vault discipline

**Append-only means no code path can edit or delete.** Not "we choose not
to" — there is no function that does it.

**Kebab-case filenames everywhere.** Enforced by a startup vault validation
check, so a typo fails immediately rather than producing a silently ignored
file.

**Flat frontmatter.** Scalars and simple lists only. Notion mangles nested
structures on import, and Notion-import friendliness is a `prompt.md` hard
constraint (pitfall E2).

**Chapter numbers come from the manifest, never from the filesystem**
(pitfall A5).

**Real vault content is never committed** (ADR-0004). All development
against destructive paths uses `vault/example-book/`, which is committed and
is the fixture every test runs on.

---

## 5. Testing

**Test the destructive paths first.** The delta reconciler, the append
primitives, the resume logic, and the path-escape guard. These are where a
bug loses work rather than producing a wrong answer.

**No test may call a live API.** The provider layer takes an injectable
transport; tests use recorded fixtures. A test suite that burns free-tier
quota will stop being run.

**Test malformed input explicitly.** Feed the editorial reconciler truncated
JSON, valid JSON that violates the schema, a delta naming a nonexistent
thread ID, and a `target_file` of `../../.env`. Each must fail closed and
write nothing.

**Test both halves of a signal.** A test that only asserts "the hashes
match" passes just as happily when the author-edit signal is broken. The
fixture therefore carries a deliberately edited chapter whose hash must
*not* match (decision #25). Any invariant that exists to detect a
condition needs a test that the detection actually fires.

**Do not chase coverage.** Prompt assembly, style metrics, and the state
machine deserve thorough tests. CLI argument plumbing does not.

**`vault/example-book/` is the fixture.** Keep it realistic — a populated
tracker, a manifest with mixed statuses, chapters with real frontmatter.
A toy fixture only proves the code works on toys.

---

## 6. Git discipline

**Commit after every task.** Small, revertible units. Rollback should never
cost more than one task's work.

**Never push without asking.** Explicit author approval each time.

**Conventional commit types:** `feat` · `fix` · `docs` · `chore` ·
`refactor` · `test`.

**The body explains why, not what.** The diff already shows what changed.
Record the reasoning that will not be reconstructible in three months —
especially any deliberate departure from `prompt.md`.

**Never commit `.env`.** Verify with `git check-ignore -v .env` if there is
any doubt.

---

## 7. Session discipline

Rules for how work proceeds across sessions. These exist because this
project is built in batches by sessions that do not share memory.

**Decisions are written the moment they are made.** Into
[decisions.md](decisions.md) and [adr.md](adr.md), before any other work
continues. A decision held in conversation is a decision lost.

**One phase per session.** Complete the phase's batches fully. Do not start
the next phase because there is time left.

**Every session ends by preparing the next one.** Update
[progress.md](progress.md): what was done, what was verified, what is
blocked, and precisely what the next session should pick up. The next
session must be able to start from the docs alone, with no conversational
context.

**Ask rather than assume.** When a question arises, first do everything that
does not depend on the answer, then ask — with a recommendation, the
alternatives, and enough scope for the question to be answerable without
reading the code.

**No sub-agents.** All work inline.

**Report honestly.** If something is untested, say untested. If a phase is
partially done, say which part. A phase marked complete in
[progress.md](progress.md) is a claim that its verification steps were
actually run.

---

## 8. Rules that must not be softened

Everything above is a convention. These five are invariants. If one is about
to be broken, that is an ADR, not a shortcut.

1. **No model ever writes a canon file body.** Delta only, Python appends.
2. **Fail closed.** Never half-apply a validated-then-invalid change.
3. **Permanent failures never trigger fallback.** Only rate-limit,
   transient, and model-unavailable outcomes are eligible.
4. **`.env` is never committed.** Logs redact by allowlist.
5. **The engine never overwrites author-written prose without `--force`
   and confirmation.**
