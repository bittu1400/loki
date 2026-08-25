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

