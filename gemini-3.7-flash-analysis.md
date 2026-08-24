# Gemini 3.7 Flash Analysis — Multi-Model Novel Writing Automation

## 1. Executive Summary & Architectural Understanding

### Core Thesis
The architecture described in `prompt.md` is a **stateless-compute, stateful-git novel engine**. It deliberately decouples long-form generative execution from human review and presentation. By treating a structured Markdown directory (Obsidian vault) as the authoritative database and leveraging Git for versioning, diffing, and audit trails, the system sidesteps expensive database infrastructure and vendor lock-in.

### The System Topology
```mermaid
graph TD
    subgraph Local_or_CI ["Execution Context (Local CLI / GitHub Actions Runner)"]
        NB["new_book.py (Interactive Intake)"] -->|Initializes| V[("Markdown Vault (/vault/<book-slug>)")]
        
        WS["write_session.py (Session Orchestrator)"]
        V -->|Reads Canon, POV Sheet, Beat, Log| WS
        
        subgraph Drafting_Phase ["Drafting Engine"]
            WS -->|Lookup POV Model| Router{"Provider Router"}
            Router -->|Primary| P1["Gemini AI Studio / OpenRouter / Groq"]
            Router -->|Fallback on 429/5xx| P2["Fallback Chain"]
            P1 -->|Chapter Draft N & N+1| CH["/chapters/chapter-XXX.md"]
            P2 -->|Chapter Draft N & N+1| CH
        end
        
        subgraph Editorial_Phase ["Consistency & State Reconciliation Engine"]
            CH --> EP["Editor Pass (Gemini Pro / Strict JSON Delta)"]
            V -->|Continuity + Style Guide| EP
            EP -->|Append-Only Locked Facts| CT["canon/continuity-tracker.md"]
            EP -->|Append Rolling Synopsis| CS["log/chapter-summary.md"]
            EP -->|Log Narrative Gaps| DQ["canon/deepen_queue.md"]
            EP -->|Suggested Diffs (No Auto-write)| PO_DIFF["Diffs: plot-outline / characters"]
        end
        
        WS -->|Status: pending-review| GH_COMMIT["Git Commit & Push"]
    end
    
    subgraph Review_Gate ["Human-in-the-Loop Approval Gate"]
        GH_COMMIT --> GH_ISSUE["GitHub Issue / PR (Session Summary + Flags)"]
        AUTHOR(["Author / Reviewer"]) -->|Reads & Approves /publish| GH_ISSUE
    end
    
    subgraph Publishing_Layer ["Publishing Layer (Cousins Platform)"]
        GH_ISSUE -->|Trigger Dispatch| PWF["Publish Workflow (.github/workflows)"]
        PWF -->|POST Chapter JSON + Bearer Auth| API["Vercel API Route (/api/publish-chapter)"]
        API --> DB[("Cousins Storage (Vercel Postgres / Blob)")]
    end
```

---

## 2. Deep-Dive Architectural Evaluation

### 2.1 What Makes This Design Exceptionally Strong
1. **Compute Placed Where It Belongs**: Running multi-minute LLM generation and consistency passes inside a GitHub Actions runner rather than inside serverless functions (e.g., Vercel Hobby 60s cap) directly eliminates timeout failures.
2. **Context Budget Discretion**: Injecting only targeted character sheets, active beats, locked facts, and the last ~2 chapter summaries (rather than the entire novel history) prevents token explosion, mitigates context distraction, and keeps API latency minimal.
3. **Asymmetric State Authority**:
   - *Autonomous Write-Back*: Low-risk cumulative logs (`chapter-summary.md`, `continuity-tracker.md`, `deepen_queue.md`).
   - *Human Gate Protected*: High-stakes structural artifacts (`plot-outline.md`, `characters/*.md`, and published chapter state).
4. **Zero-Cost Architectural Realism**: Multi-provider fallback and retry policies are built into the foundational design rather than bolted on as an afterthought.

---

## 3. Critical Technical Vulnerabilities & Latent Risks

While the macro-architecture is clean, several low-level implementation details will trigger fatal breakdowns if not hardened upfront.

### 3.1 The "Model-per-POV" Fallacy vs. Deterministic Steering
* **The Assumption**: Assigning Character A to Gemini Flash and Character B to Qwen-235B creates distinct, consistent voices.
* **The Reality**: Base LLMs do not possess fixed fictional personalities. A model’s "natural voice" is generic conversational prose. Model versioning on free endpoints (`:free` tags on OpenRouter) changes dynamically without notice. 
* **The Fix**: Voice differentiation must be driven by **explicit stylistic constraints** in the prompt (sentence length distribution, vocabulary restrictions, banned metaphors, internal monologue frequency, sensory priorities) and temperature/seed pinning, with model assignment serving as a secondary sandbox.

### 3.2 The Silent Degradation of the Story Bible (The Full-File Overwrite Trap)
* **The Risk**: If the editorial pass is prompted to "return the updated `continuity-tracker.md`", the LLM will inevitably summarize, truncate, or hallucinate-away older locked facts across successive sessions. Over 30 chapters, early canon will be wiped out.
* **The Fix**: The editor pass must **never emit full Markdown files**. It must output a strict **Delta JSON schema** (e.g., `{"new_facts": [...], "contradictions": [...], "deepen_questions": [...]}`). The local Python orchestrator handles appending and auditing facts deterministically in code.

### 3.3 Free-Tier Quota Cliffs & Token Ceilings
* **Gemini Free Tier (AI Studio)**: High token context, but strict RPM (Requests Per Minute) and RPD (Requests Per Day) ceilings depending on the model tier (`gemini-2.5-pro` has significantly tighter limits than `flash`).
* **Groq Free Tier**: Extremely fast, but strict TPM (Tokens Per Minute) and RPM limits on `llama-3.3-70b`.
* **OpenRouter Free Pool**: Shared community pool subject to high contention, frequent 429s, and unannounced deprecations.
* **The Fix**:
  - Implement **exponential backoff with jitter** (`retry-after` header compliance).
  - Track session token spend locally before dispatching requests.
  - Maintain a **dual-tier fallback matrix** that maps both across models and across distinct provider endpoints.

### 3.4 Outline Ambiguity & Manifest Deserialization
* **The Risk**: Step 2 states: *"Determine today's target: which POV/character is next per plot-outline"*. If `plot-outline.md` is free-form prose, regex or LLM parsing to determine the next chapter beat is non-deterministic and prone to off-by-one errors.
* **The Fix**: Structure the plot outline with a machine-readable frontmatter/table manifest:
```markdown
| Chapter | POV Key | Arc | Beat Summary | Status |
|---|---|---|---|---|
| 001 | protagonist | Arc 1 | Inciting incident at docks | completed |
| 002 | antagonist | Arc 1 | Reaction to dock breach | draft |
```

### 3.5 Idempotency & Workflow Interruption Recovery
* **The Risk**: If Chapter N succeeds, Chapter N+1 succeeds, but the editor pass fails on a 500 error or GitHub Action runner cancellation, rerunning the workflow could re-draft Chapter N and N+1, overwriting the prose and creating state desynchronization.
* **The Fix**: The orchestrator must implement a **resumable state machine** (`state.json` or frontmatter status in `chapter-XXX.md`: `drafted` -> `evaluated` -> `committed` -> `published`).

---

## 4. Architectural Enhancements & Specifications

### 4.1 Canonical Multi-Book Vault Structure
Standardize the directory layout to ensure clean multi-book isolation:

```text
vault/
  └── <book-slug>/
      ├── canon/
      │   ├── story-bible.md
      │   ├── style-guide.md
      │   ├── plot-outline.md          # Includes Markdown Table Manifest
      │   ├── worldbuilding.md
      │   ├── power-system.md
      │   ├── continuity-tracker.md    # Append-only ledger with session tags
      │   ├── open-threads.md          # Tagged [OPEN: ch-001], [RESOLVED: ch-005]
      │   └── deepen-queue.md          # Generated queries for author review
      ├── characters/
      │   ├── index.yaml               # Map of character_id -> file & POV model
      │   ├── kaelen.md
      │   └── lyra.md
      ├── log/
      │   ├── chapter-summary.md       # Chronological summary ledger
      │   ├── next-step.md             # Immediate operational pointer & state
      │   └── sessions/
      │       └── session-001.json     # Audit log: models used, tokens, diffs
      ├── chapters/
      │   ├── chapter-001.md
      │   └── chapter-002.md
      └── config/
          ├── models.yaml              # POV mapping & fallback configuration
          └── prompt-template.md       # Master prompt with variable slots
```

### 4.2 Structured Output Schema for Editorial Pass
The consistency pass must enforce structured JSON output (via Gemini / OpenRouter JSON schema mode or Pydantic validation):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EditorialPassDelta",
  "type": "object",
  "required": [
    "chapter_evaluations",
    "new_locked_facts",
    "continuity_violations",
    "style_violations",
    "chapter_summaries",
    "thread_updates",
    "deepen_questions",
    "suggested_canon_patches"
  ],
  "properties": {
    "chapter_evaluations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "chapter_number": { "type": "integer" },
          "word_count_actual": { "type": "integer" },
          "pacing_score": { "type": "integer", "minimum": 1, "maximum": 10 },
          "critique": { "type": "string" }
        },
        "required": ["chapter_number", "word_count_actual", "pacing_score", "critique"]
      }
    },
    "new_locked_facts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "category": { "type": "string", "enum": ["character", "world", "magic", "timeline"] },
          "fact": { "type": "string" },
          "source_chapter": { "type": "integer" }
        },
        "required": ["category", "fact", "source_chapter"]
      }
    },
    "continuity_violations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "severity": { "type": "string", "enum": ["critical", "warning"] },
          "locked_fact_ref": { "type": "string" },
          "chapter_excerpt": { "type": "string" },
          "explanation": { "type": "string" }
        },
        "required": ["severity", "locked_fact_ref", "chapter_excerpt", "explanation"]
      }
    },
    "style_violations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "pov_character": { "type": "string" },
          "banned_phrase_or_pattern": { "type": "string" },
          "occurrences": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["pov_character", "banned_phrase_or_pattern", "occurrences"]
      }
    },
    "chapter_summaries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "chapter_number": { "type": "integer" },
          "summary_paragraph": { "type": "string" }
        },
        "required": ["chapter_number", "summary_paragraph"]
      }
    },
    "thread_updates": {
      "type": "object",
      "properties": {
        "opened": { "type": "array", "items": { "type": "string" } },
        "progressed": { "type": "array", "items": { "type": "string" } },
        "resolved": { "type": "array", "items": { "type": "string" } }
      },
      "required": ["opened", "progressed", "resolved"]
    },
    "deepen_questions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "suggested_canon_patches": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "target_file": { "type": "string" },
          "suggested_diff": { "type": "string" },
          "rationale": { "type": "string" }
        },
        "required": ["target_file", "suggested_diff", "rationale"]
      }
    }
  }
}
```

### 4.3 Chapter Frontmatter Specification
Every generated chapter in `/vault/<book-slug>/chapters/chapter-XXX.md` must record immutable execution provenance:

```markdown
---
chapter_number: 14
title: "The Broken Siphon"
pov_character: "kaelen"
target_word_count: 1000
actual_word_count: 1042
status: "pending-review" # draft | pending-review | approved | published
session_id: "sess-20260824-001"
timestamp: "2026-08-24T10:07:00Z"
execution_provenance:
  assigned_model: "gemini/gemini-2.5-flash"
  actual_model_used: "gemini/gemini-2.5-flash"
  fallback_triggered: false
  generation_duration_sec: 14.2
  input_tokens: 3120
  output_tokens: 1450
editorial_provenance:
  editor_model: "gemini/gemini-2.5-pro"
  continuity_flags_count: 0
  style_flags_count: 1
hash: "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
---

# Chapter 14: The Broken Siphon

The copper conduits hummed with a frequency that vibrated directly against Kaelen's teeth...
```

---

## 5. Resilience & Quality Guardrails

| Subsystem | Failure Scenario | Automated Safeguard |
|---|---|---|
| **Drafting Engine** | Model returns <750 words (hallucinating chapter finish early) | **Continuation Loop**: The client inspects token/word count; if short, dispatches a `continue_chapter` prompt passing the last 200 words until target threshold (±10%) is met. |
| **Provider Router** | Rate limit (429) or Endpoint Outage (503) | **Backoff Matrix**: Exponential backoff (1s, 2s, 4s, 8s) followed by stepping to the next provider in `fallback_chain`. The fallback event is recorded in chapter frontmatter. |
| **State Updater** | Editor model hallucinates or corrupts locked facts | **Deterministic File Appender**: Python code parses the JSON delta and appends new lines (`- [Ch.14] Kaelen cannot channel through iron`) without modifying prior lines. |
| **CI Scheduler** | Workflow runs while previous session unapproved | **Concurrency Gate**: `write-session.yml` inspects git history. If an existing `pending-review` issue is open, it pauses generation or posts a notification rather than stacking unreviewed chapters. |
| **Publish Endpoint** | Replay attack, duplicate publishing, or malformed payload | **Idempotent Webhook Receiver**: `POST /api/publish-chapter` verifies `Authorization: Bearer <COUSINS_PUBLISH_KEY>`, validates SHA256 content hash, and performs an `UPSERT` on `(book_slug, chapter_number)`. |

---

## 6. Recommended Modular Codebase Architecture

Rather than monolithic scripts, structure the repository into cohesive Python modules:

```text
├── .github/
│   └── workflows/
│       ├── write-session.yml      # Scheduled / dispatch runner
│       └── publish-chapter.yml    # Triggered on issue comment / label
├── config/
│   └── default_models.yaml        # Global fallback configurations
├── src/
│   └── novel_engine/
│       ├── __init__.py
│       ├── cli/
│       │   ├── new_book.py        # Interactive CLI intake interview
│       │   └── write_session.py   # CLI entrypoint for session orchestration
│       ├── core/
│       │   ├── config.py          # Pydantic settings & models.yaml parser
│       │   ├── vault.py           # Safe Markdown I/O, frontmatter, & append locks
│       │   ├── outline.py         # Beat sheet parser & next chapter targeter
│       │   ├── context_builder.py # Dynamic prompt token budgeting & injection
│       │   └── state_machine.py   # Idempotency & session progress manager
│       ├── providers/
│       │   ├── base.py            # Abstract Base Provider (generate, retry, count)
│       │   ├── gemini.py          # Google GenAI / AI Studio SDK wrapper
│       │   ├── groq_client.py     # Groq SDK wrapper
│       │   ├── openrouter.py      # OpenRouter OpenAI-compatible wrapper
│       │   └── router.py          # Fallback chain & provider dispatcher
│       ├── editorial/
│       │   ├── schema.py          # Pydantic validation for editor response
│       │   ├── analyzer.py        # Consistency & voice drift inspector
│       │   └── reconciler.py      # Delta applicator (safe appends to vault)
│       └── publishing/
│           ├── payload.py         # Chapter export & hash generator
│           └── client.py          # Cousins API client
├── cousins_endpoint/
│   └── api/
│       └── publish-chapter.ts     # Minimal Next.js / Vercel API Route
├── templates/                     # Blank starter vault structure
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 7. Implementation Roadmap & Execution Order

To minimize development friction and validate free-tier API integrations early, build in seven focused stages:

1. **Stage 1: Core Foundation & Vault Manager (`src/novel_engine/core/`)**
   - Implement `vault.py` (Markdown + YAML frontmatter parser/serializer) and `config.py`.
   - Create template files for `/vault/<book-slug>/` with Notion/Obsidian compliant markdown.
2. **Stage 2: Provider Abstraction & Router (`src/novel_engine/providers/`)**
   - Build unified clients for Gemini, Groq, and OpenRouter with backoff, jitter, and mockable dry-run modes.
   - Test free tier quotas, rate-limit handlers, and token counting across all three endpoints.
3. **Stage 3: Context Builder & Drafting Loop (`context_builder.py`, `write_session.py`)**
   - Implement token-budgeted prompt injection and chapter generation loop with word-count auto-continuation.
4. **Stage 4: Structured Editorial Engine (`src/novel_engine/editorial/`)**
   - Implement Pydantic schema validation for the consistency pass.
   - Build delta-only append logic for `continuity-tracker.md`, `chapter-summary.md`, and `deepen_queue.md`.
5. **Stage 5: Interactive Author Intake CLI (`new_book.py`)**
   - Build rich terminal interview with grouped questions, input validation, and automated vault initialization.
6. **Stage 6: CI/CD Automation & GitHub Issue Approval Gate (`.github/workflows/`)**
   - Configure `write-session.yml` with secrets, git commit actions, and issue creation.
7. **Stage 7: Cousins Publishing Endpoint & Action (`cousins_endpoint/`)**
   - Build authenticated, idempotent Next.js API route and dispatch action for live publishing.

---

## 8. Final Verdict

The build specification in `prompt.md` is **exceptionally well-conceived**. It establishes clean architectural boundaries:
* **Storage**: Git-tracked Markdown vault.
* **Compute**: Scheduled GitHub Actions runner.
* **Intelligence**: Multi-tier free LLMs with dedicated drafting vs. editorial roles.
* **Gatekeeping**: Human approval before publication.
* **Serving**: Simple, decoupled Vercel endpoint.

By enforcing **delta-only JSON patches** for editorial updates, **token-budgeted context assembly**, **word-count continuation loops**, and **resumable session state**, this pipeline will reliably produce high-continuity long-form fiction on a true $0 infrastructure budget.
