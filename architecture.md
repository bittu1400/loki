# Architecture

> Scope of this document: the system as it exists in v1 (ADR-0001), plus a
> sketch of deferred phases so the code does not paint itself into a corner.
> Concrete file formats and schemas live in [specs.md](specs.md), not here.

## 1. Core thesis

This is a **stateful-vault, stateless-compute** system.

The novel is not stored in a database and is not stored in an LLM's context
window. It is a directory of plain markdown files. That directory is the
single source of truth. Every model call is a stateless worker that reads a
bounded slice of the vault and returns a bounded change to it.

Two properties follow from that and everything else in this document is
downstream of them:

1. **The vault survives the tooling.** If every script in this repo were
   deleted, the novel would still be there, readable, editable in Obsidian,
   and complete. The engine is an accelerator, not a container.
2. **No model is ever trusted to hold state.** Models draft prose and
   propose structured deltas. Python decides what actually gets written.

## 2. Topology

```mermaid
graph TD
    subgraph vault ["Vault — source of truth (vault/&lt;book-slug&gt;/)"]
        CANON["canon/<br/>story-bible · style-guide<br/>plot-outline · worldbuilding<br/>power-system · continuity-tracker<br/>open-threads · deepen-queue"]
        CHARS["characters/<br/>index.yaml + one file per character"]
        LOG["log/<br/>chapter-summary · next-step<br/>sessions/"]
        CHAPS["chapters/<br/>chapter-XXX.md"]
        CFG["config/<br/>models.yaml · pipeline.yaml<br/>prompt-template.md"]
    end

    subgraph engine ["Engine — stateless compute (local CLI)"]
        SM["state_machine<br/>resume · status transitions"]
        OUT["outline<br/>parse manifest, pick next target"]
        CTX["context_builder<br/>bounded assembly + token budget"]
        DRAFT["drafting<br/>generate + continuation loop"]
        ROUTER["provider router<br/>retry · backoff · fallback"]
        STYLE["style_checks<br/>pure Python · zero API cost"]
        EDIT["editorial<br/>schema-validated delta"]
        RECON["reconciler<br/>deterministic append-only apply"]
    end

    subgraph providers ["Free-tier providers"]
        GEM["Gemini<br/>AI Studio"]
        ORT["OpenRouter<br/>:free pool"]
        GRQ["Groq"]
    end

    CFG --> SM
    SM --> OUT
    OUT --> CTX
    CANON --> CTX
    CHARS --> CTX
    LOG --> CTX
    CHAPS --> CTX

    CTX --> DRAFT
    DRAFT <--> ROUTER
    ROUTER <--> GEM
    ROUTER <--> ORT
    ROUTER <--> GRQ

    DRAFT --> CHAPS
    CHAPS --> STYLE
    STYLE --> EDIT
    EDIT <--> ROUTER
    EDIT --> RECON

    RECON -->|append only| CANON
    RECON -->|append only| LOG
    RECON -->|suggestions, never applied| PATCH["log/sessions/&lt;id&gt;-patches.md"]
```

## 3. The authority model

This is the most important table in the document. It answers: *who is
allowed to write what?*

| Artifact | Written by | Mode | Rationale |
|---|---|---|---|
| `chapters/chapter-XXX.md` | Engine | Create once, then author-owned; ONE later exception | Generated prose; the author edits freely afterwards. The exception is `flip_chapter_status`, which promotes `draft` -> `pending-review` when a session completes — one frontmatter cell, never the body, so `generated_hash` and the author-edit signal survive (decision #35) |
| `canon/continuity-tracker.md` | Engine | **Append only** | Locked facts must never be summarised away |
| `canon/open-threads.md` | Engine | **Append + status flip** | A thread may be marked resolved, never deleted |
| `canon/deepen-queue.md` | Engine | **Append only** | Queue of gaps for the author to answer later |
| `log/chapter-summary.md` | Engine | **Append only** | Chronological ledger |
| `log/next-step.md` | Engine | Overwrite | Pure operational pointer, no history value |
| `log/sessions/*.json` | Engine | Create once, immutable | Audit record of what actually happened |
| `log/sessions/<id>-patches.md` | Engine | Create once | Model suggestions about author-owned files, as text; never a write path (threat-model T4) |
| `vault/<slug>/.git` | Engine | Append-only history | Per-session commits, created on demand for a book no enclosing repo tracks. The engine only adds and commits; it never checks out, so this records content and cannot change it (ADR-0013) |
| `canon/plot-outline.md` | **Author only**, with ONE exception | Engine flips a single `status` cell; never writes prose, beats, or rows | High-stakes structural artifact — the exception is mechanical and byte-verified (decision #16, specs §2) |
| `characters/*.md` | **Author only** | Engine may suggest, never write | High-stakes; voice depends on these |
| `canon/story-bible.md` | **Author only** | Never touched by engine | Premise and themes are not the model's business |
| `canon/style-guide.md` | **Author only** | Engine may suggest | See §7, the feedback loop |
| `config/*` | **Author only** | Never touched by engine | — |

Two rules generalise the whole table:

- **The engine never overwrites a file that contains author-written prose.**
- **Every engine write to canon is an append of a new line, computed in
  Python from a validated delta — never a model-emitted file body.**

Two clarifications the table does not carry on its face:

- The **drafting** prompt template lives in each book's `config/` and is
  author-owned like the rest of that directory. The **editorial** prompt
  does not: it is engine-owned and packaged with the code (decision #26),
  because it is a JSON contract rather than a creative artifact.
- `log/chapter-summary.md` is engine-append-only, and its paragraph is
  model prose. That is the single place model text legitimately enters a
  canon file — as a new entry under a Python-written heading, never as a
  rewrite of an existing one (specs §7).

The second rule exists because of the single most likely way this project
fails. If the editorial model is asked to "return the updated
continuity-tracker.md", it will, over successive sessions, quietly summarise,
compress, or drop older locked facts. Thirty chapters in, early canon has
evaporated — which is precisely the failure the tracker exists to prevent.
The model therefore emits a **delta**, and Python appends.

## 4. One session, end to end

`write-session --book <slug>` executes one chapter (ADR-0003).

```
 1. LOAD        config/models.yaml + config/pipeline.yaml, validate with
                Pydantic. Fail fast on a missing key or unknown provider —
                before spending any API call.

 2. RESUME      Read log/next-step.md. If a prior session is mid-flight,
                resume at its recorded phase or refuse with an explicit
                reason. Never silently regenerate an existing chapter.

 3. TARGET      Parse the chapter manifest in canon/plot-outline.md.
                Determine chapter number, POV key, and beat. Look up the
                POV's assigned model in models.yaml.

 4. ASSEMBLE    Build a bounded context (see §5). Under DRY_RUN, print it
                and stop here — zero API cost.

 4b. SNAPSHOT   Last moment before the first write: make sure the book has
                its own git repo, and commit the author's edits since the
                last session as their own commit (ADR-0013). If there is
                no recovery path and this session would write canon,
                refuse here — exit 1, nothing written.

 5. DRAFT       Call the assigned model. On an eligible failure, walk the
                fallback chain. Never switch model mid-chapter.

 6. EXTEND      If the draft is short of target, run a continuation loop
                passing the tail of the draft, until within tolerance or a
                loop cap is hit.

 7. PERSIST     Write chapters/chapter-XXX.md with provenance frontmatter
                recording which model actually served it. Status: drafted.

 8. INSPECT     Run deterministic checks in pure Python, zero API cost:
                the §14 style metrics, the §16 number check (quantities in
                the chapter against quantities in the retrieved facts) and
                the §17 entity check (a fact's claim given to a different
                NAME). All three feed the session report and are handed to
                the editorial pass as evidence rather than re-derived by
                an LLM. The two continuity checks exist because the model
                was measured missing each class unaided and catching it
                with the finding in its prompt (ADR-0008, ADR-0012).

 9. EDITORIAL   Send retrieved locked facts + open threads + the beat it
                was supposed to hit + the POV's character sheet + style
                guide + step 8's findings + the chapter to the editor
                model. Require a strict JSON delta. Validate with Pydantic.
                On invalid output: repair-and-retry from the BASE prompt,
                then FAIL CLOSED — leave the chapter at editorial-pending
                and apply nothing.

10. RECONCILE   REFUSE outright if the delta reports a critical continuity
                violation (invariant 6, ADR-0009) — the chapter contradicts
                canon and an author has to resolve it. Otherwise apply the
                validated delta deterministically inside a snapshot
                (ADR-0007): append the summary paragraph, append new locked
                facts, open threads, flip thread statuses, append
                deepen-queue gaps — all of it or none of it. Write
                suggested patches for plot-outline and character sheets to
                a session file, never to the targets themselves, and never
                to stdout.

11. REPORT      Set chapter status to pending-review, update next-step.md,
                write log/sessions/<session-id>.json, then commit the
                whole book as this session's snapshot — the audit is
                inside the commit that describes it. Print a human
                summary. Exit 0 complete, 1 nothing usable, 2
                editorial-pending.
```

Step 9's fail-closed behaviour matters more than it looks. A half-applied
delta is worse than no delta: it corrupts canon while reporting success.

**Implementation status (2026-09-04).** All twelve steps run from
`write-session`. Phase 6 Session 9 built the `log/next-step.md` contract,
`vault.write_next_step()`, and `SessionStateMachine` (Batches 1 & 2);
Session 10 added `vault.flip_chapter_status`, the resume gate, the review
phases (Batches 3 & 4), the §17 entity check, and step 4b's snapshots.
Step 2 resumes from the recorded phase only with `--resume`; a bare
re-run of an interrupted session refuses and names the phase (decision
#38). Step 11 sets `pending-review`, carries the delta's
`next_step_note` into the pointer, and commits the session.

What this does NOT mean. The pipeline is exercised end to end against
`vault/example-book/` with fake providers, plus live editorial runs in
Sessions 8 and 10. **It has never drafted and reconciled a chapter
against a real book.** OQ-01 no longer forbids that (ADR-0013 gives every
real book a per-session history), but "no longer forbidden" is not "has
been done".

## 5. Context assembly — what the model actually sees

The context budget is the second-most consequential design surface after the
authority model, because it determines whether chapter 40 reads like it
belongs in the same book as chapter 39.

Assembled per chapter, in priority order:

| Slice | Source | Bound |
|---|---|---|
| Style guide | `canon/style-guide.md` | Whole file (kept short by design) |
| POV character sheet | `characters/<pov>.md` | Whole file |
| This chapter's beat | Manifest row + beat prose | One beat only |
| **Verbatim tail of the previous chapter** | `chapters/chapter-(N-1).md` | Final ~500 words |
| Recent summaries | `log/chapter-summary.md` | Last ~2 entries |
| Relevant locked facts | `canon/continuity-tracker.md` | **Retrieved, not dumped** — see below |
| Open threads | `canon/open-threads.md` | Unresolved only |
| Story bible | `canon/story-bible.md` | Premise/tone header only |

Two entries in that table are deliberate departures from `prompt.md`.

**The verbatim tail.** `prompt.md` injects only chapter summaries. A summary
preserves *what happened* and destroys *how it read*. A model handed a
synopsis of chapter 19 writes chapter 20 as though it had read a synopsis —
episodic, tonally reset, no momentum across the seam. Injecting the previous
chapter's actual closing prose costs a few hundred tokens and is the single
highest-leverage lever on perceived continuity.

**Retrieved facts, not dumped facts.** An append-only continuity tracker
grows without bound; by chapter 60 it may hold several hundred locked facts.
Injecting all of them contradicts the "tight, current context" principle the
whole design rests on. Facts are therefore tagged by category and entity at
write time, and only facts touching the POV and the entities named in the
upcoming beat are injected. Compaction of the tracker, when it becomes
necessary, is a **manual author ritual** — never an automated model pass,
because that reintroduces exactly the silent-degradation failure §3 exists
to prevent.

## 6. Provider layer

Seven provider modules, one interface: gemini, openrouter, groq, mistral,
nvidia, aihubmix (built and live-verified in Phase 2; aihubmix demoted out
of routing the same day, decisions #12), plus `local` (Session 7,
[ADR-0006](adr.md#adr-0006--local-model-lane)). cohere, z.ai, cerebras,
github-models, chutes, siliconflow, nanogpt, fireworks, portkey, and
tokenrouter were evaluated and dismissed — see OQ-02 and decisions #11,
#12, #21; requesty has no valid key yet. **Six of the seven share an
OpenAI-compatible wire format** and one parameterised class serves them
all; only Gemini needs its own adapter. The router normalises every
response into one of five outcomes:

| Outcome | Fallback eligible? |
|---|---|
| Success | — |
| Rate limited (429, quota) | **Yes** |
| Transient failure (5xx, timeout, connection reset) | **Yes** |
| Model unavailable (unknown slug, deprecated, 404) | **Yes** |
| Permanent failure (bad request, auth, malformed prompt, invalid schema) | **No** |

The last row is a correctness requirement, not an optimisation. A malformed
prompt or an invalid editorial response must not trigger a different model
as if it were a rate limit — that turns a bug into a silent, expensive,
non-deterministic retry storm across providers. In the shipped router the
policy is sharper still: only RateLimited retries the *same* route (it
carries `Retry-After`); transient failures and pulled slugs move down the
chain at once; permanent failure aborts the entire chain.

**Stability principle (decisions.md #8).** Every route needs a fallback on
a different provider, ideally the same model served twice — minimax-m3 runs
on both OpenRouter and NVIDIA NIM, so a `:free` slug pull degrades quality
instead of ending the session.

Three provider-specific realities the layer must absorb:

- **Gemini is not OpenAI-shaped.** OpenRouter, Groq, Mistral, and NVIDIA NIM
  speak an OpenAI-compatible schema; Gemini's native API does not, and system-prompt
  handling differs. The adapter absorbs this; nothing above it knows.
- **Structured-output support is uneven.** Most OpenRouter `:free` models do
  not reliably honour a JSON schema. This matters precisely when the
  editorial pass falls back off its primary model. Hence the repair-retry
  plus fail-closed policy in step 9.
- **`:free` slugs are unstable identifiers.** They get renamed,
  rate-limited to uselessness, or pulled without notice. Model IDs are
  therefore configuration data validated at startup, never constants in
  code, and the model that *actually* served a chapter is recorded in that
  chapter's frontmatter.
- **A listing is not an entitlement.** `mistral-large-latest` — verified
  live in Session 4 and written into `models.yaml` as the editorial
  fallback — began returning `403 tier_not_allowed` while still appearing
  in that provider's `/v1/models`. A catalog probe would have said it was
  fine. Only a real generation call proves a lane, and a fallback lane is
  by definition the one nothing exercises (pitfall C10).

## 7. Quality loops

Continuity is checked. Craft is not — unless we build for it. Two loops
exist for that.

**Deterministic style checks (Phase 4 — built).** Asking an LLM "does this
violate the style guide?" produces agreeable mush. These signals are
computable in Python at zero API cost and are far sharper: banned-phrase and
banned-pattern hits, sentence-length distribution, adverb rate, type-token
ratio, dialogue-to-narration ratio, paragraph-length distribution, and
repeated sentence openings. The LLM editorial pass is then reserved for the
one job where it genuinely has an edge — detecting contradiction against
locked facts. This also conserves the tightest-rationed quota in the stack.

**What these checks cannot see, measured 2026-08-31.** Five drafts of the
same chapter were measured and then read. The metrics ranked a
threshold-passing draft first; reading ranked it third. They caught none of
the three real defects: prose that referred to "Chapter 1" out loud, a POV
character described from outside his own head, and a chapter contradicting
canon within twelve paragraphs. The metrics measure AI-prose *tells*, not
quality — which is why specs §14 keeps them advisory, and why promoting
them to a gate would be a mistake dressed as rigour. Contradiction is the
editorial pass's job (§6); voice is the author's.

**Deterministic continuity check (Phase 5 — built, and a revision of the
sentence above).** "Contradiction is the editorial pass's job" was
measured and found half true. Given a chapter saying "nine corrections"
against a locked fact saying two — with that fact in the same prompt —
the editor returned an empty violation list, twice, and wrote the
contradiction into the summary. So the narrowest slice of the job moved
into Python: `quality/continuity_numbers.py` compares quantities in the
chapter against quantities in the retrieved facts, and its findings go
into the editorial prompt as evidence
([ADR-0008](adr.md#adr-0008--continuity-checking-is-not-exclusively-the-models-job),
specs §16). With the finding in front of it, the same model caught the
same case on both later runs.

**And again for names (2026-09-04, decision #39).** The same experiment
on an identity contradiction — a locked fact says Ovist keeps the echo
ledger, the chapter says Brannec does — produced the same shape: two
misses at temperature 0.2 with the fact in the prompt, and a first-call
`critical` catch once a deterministic finding was added. So
`quality/continuity_entities.py` joined it (specs §17,
[ADR-0012](adr.md#adr-0012--the-deterministic-layer-extends-to-entity-disagreements)).
Two classes now work because Python finds them first, which is the
strongest available reason to distrust the classes where nothing does —
dates, orderings, rewritten quantities, capabilities (OQ-10).

The division is now: **Python finds what is mechanical** (style tells,
number disagreements), **the model judges what is not** (does this
contradict, did the beat land, what is newly true), and **neither is a
gate** — style verdicts are advisory, and the one thing that does stop
the pipeline is a critical violation blocking reconciliation
([ADR-0009](adr.md#adr-0009--a-chapter-that-contradicts-locked-canon-is-not-reconcilable)),
which is a canon-integrity rule rather than a quality judgement.

**The author-edit feedback loop (Phase 6+).** When the author edits a
generated chapter, that diff is the highest-quality voice signal the system
will ever have — a direct demonstration of "wrong" versus "right" in the
author's own hand. Today that signal is discarded. The loop captures it:
diff the author's edited chapter against the generated original, and surface
notable corrections as *suggested* additions to the style guide, for the
author to accept. Suggested, never applied — the style guide is
author-owned per §3.

## 8. Module layout

```text
src/novel_engine/
  __init__.py
  cli/
    write_session.py     # single-chapter session: dry-run, force gate, audit JSON
    new_book.py          # scaffolds a blank vault/<slug>/ and exits
    check_style.py       # check-style: measures one chapter, no API keys needed
  core/
    config.py            # Pydantic settings; models.yaml + pipeline.yaml + startup validation
    vault.py             # THE ONLY WRITER: scaffold_book, write_chapter,
                         #   flip_manifest_status, flip_chapter_status,
                         #   generated_hash, canon appends, write_next_step
    outline.py           # manifest parsing; next_target(), resolve_target()
    context_builder.py   # fact parsing/retrieval by entity; verbatim tail;
                         #   template slot filling in file order
    errors.py            # NovelEngineError, ConfigError, ContextError,
                         #   VaultError, EditorialError. (ManifestError
                         #   subclasses ConfigError and lives in outline.py,
                         #   next to the parser that raises it)
    state_machine.py     # next-step.md schema, LEGAL_TRANSITIONS,
                         #   SessionStateMachine (transition/restart/block)
    snapshot.py          # per-session git history for a book (ADR-0013).
                         #   Writes .git only; add+commit, never checkout
  providers/
    base.py              # abstract provider; five normalised outcome types
    openai_compat.py     # shared OpenAI-shaped client (openrouter/groq/mistral/
                         #   nvidia/aihubmix/local); api_key=None sends no auth
    gemini.py            # generateContent adapter
    openrouter.py groq.py mistral.py nvidia.py aihubmix.py   # base URLs + build()
    local.py             # llama.cpp on localhost, keyless, context-clamped (ADR-0006)
    router.py            # fallback chain; rate-limit-only in-place retries; jitter
    audit.py             # CallRecord / CallRecorder / allowlist logging
  drafting/
    generate.py          # draft_chapter(): continuation loop, ADR-0005 failed-stub
    provenance.py        # make_session_id, chapter_frontmatter, utc_timestamp
  quality/
    metrics.py           # specs §14 metrics as pure functions; no IO, no verdicts
    style_checks.py      # THRESHOLDS parsing, judge(), build_report()
    continuity_numbers.py # number-disagreement finder (decision #30); evidence
                         #   for the editorial prompt, never a gate
    continuity_entities.py # name-disagreement finder (decision #39, specs §17);
                         #   paragraph-scoped, proximity-guarded, same rule:
                         #   evidence for the prompt, never a gate
  editorial/
    schema.py            # delta models; extra="forbid"; canon-line text guards
    pass_runner.py       # prompt/call/validate/repair; fail-closed, writes nothing
    reconciler.py        # the only caller of the canon appends; all-or-nothing
templates/book/          # packaged scaffolder source (vault templates)
templates/editorial-prompt.md  # engine-owned editorial prompt (decision #26)
vault/
  example-book/          # committed fixture (ADR-0004); chapters 001-005 on disk,
                         #   001-002 hand-written, 003-005 generated live
tests/                   # fakes.py holds the scripted Provider doubles
```

Layout rationale: `providers/` knows nothing about novels, `quality/` and
`editorial/` know nothing about HTTP, and `vault.py` is the only module
that writes vault content. That last constraint is what makes the
authority model in §3 enforceable rather than aspirational. `snapshot.py`
is the single deliberate neighbour: it writes `.git` and nothing else,
records history rather than changing content, and has no restore path
(ADR-0013).

## 9. Deferred phases

Not built in v1 (ADR-0001). Sketched only so v1 does not preclude them.

- **Phase 7 — GitHub Actions.** Generation runs in the Actions runner, not
  a Vercel function; Hobby-plan functions time out around 60s and generation
  will exceed that. A concurrency gate must refuse to generate while an
  unreviewed session is outstanding, or the review queue silently stacks.
- **Phase 8 — Approval gate.** A GitHub Issue is a fine *notification*
  surface but must not be the source of truth. Approval binds to a specific
  commit and chapter content hash; otherwise a draft edited after approval
  publishes as though it had been reviewed.
- **Phase 9 — Cousins publish endpoint.** Deliberately dumb: bearer auth
  with constant-time compare, schema validation, request size limit,
  idempotent upsert on `(book_slug, chapter_number)`, and a defined conflict
  policy for republishing. No AI logic on that side of the wire, ever.

## 10. What this architecture does not solve

Stated plainly so it is not mistaken for a solved problem.

This design makes state transitions safe, deltas auditable, continuity
recoverable, and provenance traceable. **It does not make the prose good.**
Prose quality is a function of the story bible, the style guide, the beat
sheet, and the base model — none of which are engineering problems. The
architecture is a well-built machine around a generator whose output quality
is currently untested. That test is the author's, and it comes first.
