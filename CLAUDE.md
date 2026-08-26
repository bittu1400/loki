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
ADR, never a shortcut.

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
   and explicit confirmation.

---

## Structural facts worth knowing before you edit anything

- **`core/vault.py` is the only module that writes to disk.** Everything
  else returns data. This is what makes the authority model reviewable.
- **`vault.py` exposes narrowly-scoped primitives only** — as of Phase 3:
  `scaffold_book`, `write_chapter` (create-only, hash-verified), and
  `flip_manifest_status` (single-cell mechanical edit). The append
  primitives the editorial reconciler will need — `append_fact`,
  `append_summary`, `append_thread`, `flip_thread_status` — are Phase 5
  work. There is deliberately no general "write canon file" function.
- **`generated_hash` is computed by `vault.write_chapter`, never by its
  callers** — callers who supply one are rejected. It hashes the exact
  post-frontmatter bytes as stored (leading blank lines stripped,
  trailing newline included), then the file is re-read and verified.
- **Model IDs, paths, thresholds, and word counts are configuration, never
  literals in code.** `:free` slugs are renamed and pulled without notice.
- **Chapter numbers come from the manifest in `plot-outline.md`**, never
  from counting files in `chapters/`.
- **Real vault content is gitignored** (ADR-0004). All development touching
  destructive paths runs against the committed `vault/example-book/`
  fixture.
- **Phase 5 is blocked against real vaults** until OQ-01 resolves the
  missing backup path.

---

## Commands

```bash
uv sync                       # environment from uv.lock
uv run pytest
uv run ruff check --fix .
uv run ruff format .
uv add <package>              # never pip install

uv run write-session --book <slug> --dry-run   # assemble prompt, spend nothing
uv run write-session --book <slug>
uv run new-book --slug <slug>
uv run check-style --book <slug> --chapter N
```

`--dry-run` is the default way to iterate on prompts. Free-tier daily caps
are the hardest constraint in the project; assembling and reading a prompt
costs nothing, generating costs a call.

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

## The thing most likely to go wrong

Not a bug. The project builds a resumable, provenance-tracked,
hash-verified pipeline around a generator whose output quality has never
been tested, and discovers at chapter thirty that the prose is competent and
forgettable.

The architecture makes state safe. It does not make prose good — that comes
from the story bible, the style guide, the beat sheet, and the base model,
none of which are engineering problems. Keep OQ-04 (the prose spike) visible
and do not let it slip behind the interesting work.
