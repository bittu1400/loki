# Architecture Review: Multi-Model Novel Writing Automation

## Bottom line

Yes—the core architecture is clear, and it is a strong fit for the stated constraints. It treats a novel as a durable, human-readable state store (the Markdown vault), and treats model calls as replaceable workers that produce a small, reviewable set of changes per session. Separating scheduled generation on GitHub Actions from publication on Cousins/Vercel is especially important and correctly scoped.

The design should be built as a **book-scoped pipeline**: every command receives (or discovers) one book directory, and no generation state is shared accidentally between books.

## Mental model

```text
Author-maintained Markdown vault                 External services
--------------------------------                 -----------------
canon / characters / outline / logs  ──────>    selected free-tier LLM
             │                                      │
             │ context assembly                     │ chapter draft
             v                                      v
       session orchestrator  <──────────────── API adapters + retry/fallback
             │
             ├── chapters/chapter-XXX.md
             ├── continuity, summary, next-step, deepen queue
             ├── proposed-only edits for outline/character sheets
             └── session report + pending-review status
                          │
             GitHub Actions commits and opens review issue
                          │
                    explicit human approval
                          │
             small authenticated Cousins publish endpoint
```

There are three deliberately separate responsibilities:

1. **Creative state** lives in Markdown and remains inspectable/editable without the program.
2. **Generation and continuity work** happen in a local CLI or scheduled GitHub Actions runner, where longer-running requests and retries are acceptable.
3. **Publication** is a narrow, authenticated transport operation. Cousins receives approved content but does not decide what to write.

## What is particularly good

- The persistent story bible avoids pretending that an LLM conversation is a reliable database.
- Injecting only relevant material plus recent summaries is the right context-budget strategy. It is much more scalable than repeatedly sending all previous chapters.
- A stable model per POV is a sensible attempt at voice consistency. The style guide and editor pass remain necessary because model identity alone cannot guarantee voice.
- Fallback is correctly constrained to happen between requests, never partway through a chapter. This preserves provenance and avoids a visibly mixed draft.
- The consistency pass updates low-risk operational records while keeping plot and character sheets author-approved. That is an excellent authority boundary.
- The default approval gate makes scheduled drafting safe enough to operate before the pipeline has earned trust.

## Decisions to lock down before implementation

### 1. Make the vault layout unambiguous

The prompt first shows `/vault/canon/...`, then says each new book should be created as `/vault/<book-slug>/...`. Use the latter as the canonical layout:

```text
vault/
  <book-slug>/
    canon/  characters/  log/  chapters/  config/
```

`new_book.py` should create the full tree inside one book directory. `write_session.py` should require `--book <slug>` (with an optional configured default), rather than silently using a global vault. This prevents cross-book continuity contamination.

### 2. Make the outline machine-readable enough to schedule from

The runner needs a reliable answer to “what is chapter N’s POV and beat?” A prose outline alone is ambiguous. Keep `plot-outline.md` readable, but include a small stable chapter manifest section, for example a Markdown table with chapter number, POV key, beat, status, and optional title. The code should parse that controlled section only.

### 3. Treat model/provider configuration as data, not assumptions

The example identifiers and availability of free tiers can change. The configuration loader should validate providers, model IDs, and required environment variables before starting a session. It should also record the actual provider/model used in each chapter’s front matter and the session report—particularly when fallback occurred.

The editor pass needs its own fallback policy or a clear failure mode. If drafting succeeds but editorial reconciliation fails, do not publish and do not overwrite state blindly; save the drafts as pending review and report that state reconciliation is incomplete.

### 4. Use structured output for operational updates

Asking the editor model to emit whole Markdown files is convenient but fragile. Prefer a strict JSON response (validated with a schema) containing:

- contradictions and voice flags;
- new locked facts;
- resolved and newly opened threads;
- one summary paragraph;
- next-step guidance;
- deepen-queue gaps;
- suggested, non-applied outline/character edits.

The program can then deterministically update Markdown sections. Preserve author-written content and append/audit generated facts rather than replacing an entire file based on a single model response.

### 5. Add idempotency and recovery semantics

Scheduled automation will eventually be interrupted after one chapter or after a draft is saved but before continuity updates. Each session needs a session ID and explicit status files/front matter, such as `draft`, `editorial-pending`, `pending-review`, `approved`, and `published`. On rerun, the program should resume or refuse with a precise explanation; it should never silently generate duplicate chapter numbers.

### 6. Keep approval authoritative and verifiable

The GitHub Issue is a useful notification and review surface, but the source of truth should be a committed status change in the book vault (or a signed/manual workflow dispatch tied to a specific commit). The publish workflow must publish a specific approved commit and chapter hash, making it impossible for a later changed draft to be published under an earlier approval.

The Cousins endpoint should enforce authentication, schema validation, idempotency by chapter number/content hash, request-size limits, and a clear conflict policy for re-publishing an existing chapter.

## Recommended implementation shape

Use a small Python package rather than one large script:

```text
src/novel_pipeline/
  config.py          # YAML/env validation; book paths
  vault.py           # Markdown layout, reads, safe section updates
  outline.py          # chapter-manifest parsing and next-target selection
  context.py          # bounded context assembly
  providers/          # Gemini, OpenRouter, Groq adapters behind one interface
  drafting.py         # one-chapter generation and provenance metadata
  editorial.py        # schema-validated consistency response
  session.py          # two-chapter orchestration and state transitions
write_session.py      # CLI entry point
new_book.py           # interactive intake entry point
```

The provider interface should normalize success, rate limit, transient failure, permanent failure, usage/provenance, and retry-after information. Fallback should occur only for eligible failures; malformed prompts, missing configuration, or invalid editorial output should not trigger a different model as if they were rate limits.

## Suggested Markdown conventions

Use YAML front matter for generated chapters and session state, with human-readable body content beneath it. For example, generated chapter provenance can include chapter number, POV key, primary assigned model, actual model used, session ID, draft status, and content hash. This is useful for auditability and the publishing workflow without making the prose unpleasant to edit in Obsidian.

For continuity, distinguish author-locked facts from model-proposed facts. A conservative first version can append generated facts with source chapter/session metadata, then let the author promote, edit, or remove them during review.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Free-tier limits or provider changes | Provider-specific backoff, fallback, startup validation, and clear partial-session recovery. |
| Voice drift despite fixed POV model | Strong character/style context, editorial checks, and provenance for diagnosing drift. |
| LLM corrupts canon | Structured patches; only auto-update designated operational files; never overwrite author-controlled canon. |
| Context becomes stale or too large | Read exact relevant files, cap summaries, and use a rolling `next-step.md`. |
| Duplicate/premature publishing | Explicit status transitions, commit/hash binding, idempotent publish endpoint. |
| Secrets leak | `.env.example` only, secrets in local environment/GitHub Actions, redaction in reports/logs. |

## Overall assessment

I would proceed with this architecture. It has the right boundaries: Markdown is the durable source of truth, models are swappable and fallible workers, GitHub Actions performs the long-running work, and the web app only publishes approved artifacts.

The main implementation challenge is not generating prose; it is making the state transitions and model-produced updates safe, deterministic, and recoverable. If those pieces are designed first—book scoping, chapter manifest, structured editorial patches, provenance, and approval/publish state—the rest of the pipeline is straightforward to extend.
