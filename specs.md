# Specifications

> Concrete contracts. Where [architecture.md](architecture.md) says *why*,
> this says *exactly what*. Anything marked **PROPOSED** is my
> recommendation awaiting author confirmation and is tracked in
> [open-questions.md](open-questions.md).

---

## 1. Vault layout

Canonical, book-scoped (ADR-0004). `prompt.md` shows two conflicting layouts
— a root-level `/vault/canon/` and a per-book `/vault/<book-slug>/`. The
per-book form is authoritative; the root form is void.

```text
vault/
  <book-slug>/
    canon/
      story-bible.md          # premise, themes, tone, target length
      style-guide.md          # POV rules, tense, banned phrases, rhythm
      plot-outline.md         # prose acts + machine-readable manifest (§2)
      worldbuilding.md
      power-system.md         # omitted if genre has no power system
      continuity-tracker.md   # append-only locked-fact ledger (§4)
      open-threads.md         # planted setups awaiting payoff (§5)
      deepen-queue.md         # gaps flagged for the author to answer (§6)
    characters/
      index.yaml              # character_id -> file, pov flag, model key
      <character-id>.md       # bio, arc, speech pattern, vocabulary
    log/
      chapter-summary.md      # append-only rolling synopsis (§7)
      next-step.md            # operational pointer + resume state (§8)
      sessions/
        <session-id>.json     # immutable audit record (§13)
        <session-id>-patches.md  # suggested canon edits, never auto-applied
    chapters/
      chapter-001.md          # zero-padded to 3 digits
    config/
      models.yaml             # model routing only (§9)
      pipeline.yaml           # pipeline behaviour only (§10)
      prompt-template.md      # master prompt with named slots
```

**Naming rules**

- All filenames are **kebab-case**. `prompt.md` writes `deepen_queue.md` with
  an underscore while every sibling uses hyphens; the hyphenated form wins.
- `<book-slug>` and `<character-id>` are lowercase, hyphenated, ASCII,
  matching `^[a-z0-9]+(-[a-z0-9]+)*$`.
- Chapter files are `chapter-NNN.md`, zero-padded to three digits, extending
  to four only past chapter 999.

**Notion-import friendliness** (a `prompt.md` hard constraint): keep YAML
frontmatter flat and scalar-or-simple-list, avoid deeply nested bullets,
avoid callout syntax. Notion mangles nested structures on import. Honouring
this now is free; retrofitting it is not.

---

## 2. Chapter manifest — `canon/plot-outline.md`

The runner must deterministically answer "what is chapter N's POV and beat?"
Parsing free prose for that is non-deterministic and produces off-by-one
errors. The outline therefore stays human-readable prose, with **one
controlled section** the parser reads and nothing else.

````markdown
# Plot Outline

## Act I — <prose, human-authored, ignored by the parser>

...

<!-- MANIFEST:BEGIN -->
| chapter | pov | arc | status | beat |
|---------|-----|-----|--------|------|
| 001 | kaelen | arc-1 | written  | Inciting incident at the docks. |
| 002 | lyra   | arc-1 | written  | She learns of the breach secondhand. |
| 003 | kaelen | arc-1 | planned  | Confrontation with the harbour master. |
<!-- MANIFEST:END -->
````

**Parser contract**

- Only content strictly between `<!-- MANIFEST:BEGIN -->` and
  `<!-- MANIFEST:END -->` is parsed. Everything else in the file is prose for
  humans and for the model, never for the parser.
- Required columns: `chapter`, `pov`, `arc`, `status`, `beat`. Extra columns
  are permitted and ignored.
- `pov` must match a `character_id` in `characters/index.yaml`. Startup
  validation fails loudly on a mismatch.
- `status` ∈ `planned` · `drafting` · `written` · `revised`.
- **Next target** = the lowest chapter number with status `planned`. If the
  chapter numbers are non-contiguous or duplicated, the run aborts with an
  explicit message rather than guessing.
- The engine may flip `status` in this section as a mechanical bookkeeping
  update. It may not touch any other part of the file. This is the sole
  exception to "plot-outline is author-only" in the authority model, and it
  is a status field, not content.

---

## 3. Chapter file — `chapters/chapter-NNN.md`

```markdown
---
chapter_number: 14
title: "The Broken Siphon"
book_slug: "example-book"
pov: "kaelen"
arc: "arc-1"
status: "pending-review"
session_id: "sess-20260824-1042-a3f1"
created_at: "2026-08-24T10:42:11Z"
target_words: 1000
actual_words: 1042
assigned_model: "gemini:gemini-2.5-flash"
actual_model: "gemini:gemini-2.5-flash"
fallback_triggered: false
continuation_rounds: 1
input_tokens: 3120
output_tokens: 1450
generated_hash: "sha256:7f83b165…"
---

# Chapter 14 — The Broken Siphon

The copper conduits hummed against Kaelen's teeth…
```

**Field notes**

- `assigned_model` vs `actual_model`: both are recorded always. When they
  differ, a fallback fired, and that is the first thing to look at when a
  chapter's voice is off.
- `generated_hash` is the SHA-256 of the **body as originally generated**,
  and is **immutable**. It is not a checksum of the current file.
  Recomputing the current body's hash and comparing to `generated_hash`
  answers "has the author edited this chapter?" — which is precisely the
  trigger for the author-edit feedback loop
  ([architecture.md](architecture.md) §7). A hash that silently invalidates
  on every edit would be useless; this one carries information *because* it
  goes stale.
- `status` values and legal transitions are defined in §11.
- Frontmatter is flat and scalar-only for Notion compatibility (§1).

---

## 4. Continuity tracker — `canon/continuity-tracker.md`

**Append-only.** No line is ever edited or removed by the engine. Every line
is one atomic, checkable fact.

```markdown
# Continuity Tracker

Append-only ledger of locked facts. The engine only ever adds lines.
Editing or removing a line is an author action.

<!-- FACTS:BEGIN -->
- `[world]` `[ch-001]` `[author]` The harbour district floods at every spring tide.
- `[character:kaelen]` `[ch-014]` `[model]` Kaelen cannot channel through iron.
- `[timeline]` `[ch-014]` `[model]` The siphon broke three days after the breach.
<!-- FACTS:END -->
```

**Line grammar**

```
- `[<category>]` `[ch-<NNN>]` `[<origin>]` <fact sentence>
```

| Token | Values |
|---|---|
| `category` | `world` · `character:<id>` · `magic` · `timeline` · `object` · `location` |
| `ch-NNN` | Source chapter that established the fact |
| `origin` | `author` (hand-written, authoritative) · `model` (proposed by an editorial pass, provisional until the author confirms) |

The `origin` tag exists so the author can distinguish canon they wrote from
canon a model inferred, and demote the latter when it is wrong. Without it,
model-invented facts become indistinguishable from real canon within a
handful of sessions.

`category` and the `character:<id>` qualifier are what make **retrieval**
possible ([architecture.md](architecture.md) §5) — the context builder
selects facts touching the current POV and the entities named in the beat,
rather than dumping a ledger that grows without bound.

**Compaction is a manual author ritual.** No automated pass, no model, ever
rewrites this file. That is the failure mode the whole design exists to
prevent.

---

## 5. Open threads — `canon/open-threads.md`

Append plus status flip. A thread is never deleted.

```markdown
<!-- THREADS:BEGIN -->
- `[T-003]` `[open]` `[ch-002]` Lyra's brother was not on the crew manifest.
- `[T-001]` `[resolved:ch-011]` `[ch-001]` The unlit lamp in the north tower.
<!-- THREADS:END -->
```

Thread IDs are `T-` plus a zero-padded counter, allocated by the engine and
never reused. The engine may flip `[open]` to `[resolved:ch-NNN]` from a
validated delta; it may not rewrite the thread text.

---

## 6. Deepen queue — `canon/deepen-queue.md`

Append-only. Gaps the editorial pass noticed that the intake interview did
not cover. `prompt.md`'s intent: do not chase every worldbuilding detail up
front — let real gaps surface during generation.

```markdown
<!-- QUEUE:BEGIN -->
- `[open]` `[ch-014]` What currency do the harbour crews get paid in?
- `[answered:2026-08-30]` `[ch-009]` Who appoints the harbour master?
<!-- QUEUE:END -->
```

---

## 7. Chapter summary — `log/chapter-summary.md`

Append-only. One paragraph per chapter, in chapter order, each under a
stable heading so the context builder can slice the last N deterministically.

```markdown
## ch-014
Kaelen reaches the siphon house before dawn and finds the regulator
already broken…
```

---

## 8. Session pointer — `log/next-step.md`

Both a human note and the machine resume record. Frontmatter is the machine
contract; the prose below it is for the author and for the next prompt.

```markdown
---
next_chapter: 15
next_pov: "lyra"
last_session_id: "sess-20260824-1042-a3f1"
last_session_phase: "complete"
last_session_status: "pending-review"
blocked: false
blocked_reason: ""
---

Kaelen has left the siphon house knowing the break was deliberate but not
who caused it. Chapter 15 picks up with Lyra, who does not yet know.
```

`last_session_phase` ∈ `target` · `drafted` · `styled` · `editorial-pending`
· `reconciled` · `complete`. On startup the engine reads this to decide
whether to run fresh, resume, or refuse.

---

## 9. `config/models.yaml` — routing only

```yaml
pov_models:
  kaelen: { provider: gemini,     model: gemini-2.5-flash }
  lyra:   { provider: openrouter, model: qwen/qwen3-235b-a22b:free }

fallback_chain:
  - { provider: groq,       model: llama-3.3-70b-versatile }
  - { provider: openrouter, model: deepseek/deepseek-v3:free }

editor_model:
  primary:  { provider: gemini, model: gemini-2.5-pro }
  fallback: { provider: gemini, model: gemini-2.5-flash }

generation_params:
  temperature: 0.9
  top_p: 0.95
  seed: 20260824        # pinned where the provider supports it; ignored otherwise
```

> **Every model ID above is an assumption until verified.** Free-tier
> availability changes without notice, `:free` slugs are renamed or pulled,
> and `gemini-2.5-pro`'s free-tier quota is the tightest in the stack while
> also being the model called every single session. `config.py` validates
> providers, model IDs, and required environment variables at startup,
> before any generation begins. Author verification is tracked as OQ-02.

**`editor_model` has its own fallback, deliberately.** If drafting succeeds
but editorial reconciliation fails, the correct behaviour is to keep the
draft and mark it `editorial-pending` — never to publish and never to
half-apply state.

---

## 10. `config/pipeline.yaml` — behaviour only  **[PROPOSED]**

```yaml
target_words: 1000
word_tolerance: 0.10          # accept 900–1100
max_continuation_rounds: 3

context:
  previous_chapter_tail_words: 500
  recent_summaries: 2
  max_locked_facts: 40
  token_budget: 12000

retry:
  max_attempts: 4
  base_delay_seconds: 1
  jitter: true
  respect_retry_after: true

editorial:
  enabled: true
  max_repair_attempts: 2
  fail_closed: true           # never half-apply a delta

# Deferred (ADR-0001) — present so the shape is fixed early
auto_publish: false
```

**Why two config files.** `prompt.md` places `auto_publish` inside
`models.yaml`. That is a category error: `auto_publish` is pipeline
behaviour, not model routing, and mixing the two means every behaviour tweak
touches the file that governs which model writes which character. Splitting
them keeps `models.yaml` small enough to reason about at a glance. Tracked
as OQ-03.

---

## 11. Session state machine

```
        ┌─────────┐
        │ target  │  chapter number + POV + beat resolved
        └────┬────┘
             ▼
        ┌─────────┐
        │ drafted │  prose written to chapters/chapter-NNN.md
        └────┬────┘
             ▼
        ┌─────────┐
        │ styled  │  deterministic checks complete (no API cost)
        └────┬────┘
             ▼
   ┌───────────────────┐
   │ editorial-pending │◄── terminal-until-retried on invalid delta
   └────────┬──────────┘
            ▼
      ┌────────────┐
      │ reconciled │  delta validated and appended
      └─────┬──────┘
            ▼
      ┌──────────┐
      │ complete │  chapter status = pending-review
      └──────────┘
```

**Chapter status** (frontmatter): `draft` → `pending-review` → `approved` →
`published`. Only the first two are reachable in v1 (ADR-0001).

**Rules**

- Every phase transition is persisted to `log/next-step.md` before the next
  phase begins. A crash between phases is therefore always resumable.
- Re-running a session whose chapter already exists on disk **never
  overwrites it**. The engine resumes from the recorded phase, or refuses
  with a precise message naming the chapter and its current phase.
- Chapter numbers are allocated from the manifest, never from
  `len(listdir(chapters/))`. A gap in the chapter files must not silently
  shift numbering.
- `session_id` format: `sess-YYYYMMDD-HHMM-<4 hex>`. Unique per invocation,
  recorded in the chapter frontmatter and the session audit file.

---

## 12. Editorial delta schema

The editorial model returns **JSON only**, validated with Pydantic before a
single byte is written. It never returns markdown file bodies.

```jsonc
{
  "chapter_number": 14,
  "continuity_violations": [
    {
      "severity": "critical",          // critical | warning
      "violated_fact": "Kaelen cannot channel through iron.",
      "chapter_excerpt": "…he pressed his palm to the iron band and pulled…",
      "explanation": "Directly contradicts a locked fact from ch-014."
    }
  ],
  "new_locked_facts": [
    {
      "category": "timeline",          // world|character|magic|timeline|object|location
      "entity": "kaelen",              // "" when not entity-scoped
      "fact": "The siphon broke three days after the breach.",
      "source_chapter": 14
    }
  ],
  "thread_updates": {
    "opened":    [{ "text": "Someone reset the regulator deliberately." }],
    "progressed":[{ "thread_id": "T-003", "note": "Lyra's brother named again." }],
    "resolved":  [{ "thread_id": "T-001", "resolved_in_chapter": 14 }]
  },
  "chapter_summary": "Kaelen reaches the siphon house before dawn…",
  "next_step_note": "Lyra does not yet know the break was deliberate.",
  "deepen_questions": ["What currency do the harbour crews get paid in?"],
  "suggested_canon_patches": [
    {
      "target_file": "characters/kaelen.md",
      "rationale": "He now has a stated aversion to iron; the sheet omits it.",
      "suggested_text": "Adds: physically flinches from worked iron."
    }
  ],
  "beat_adherence": {
    "hit": true,
    "notes": "Confrontation occurs but is resolved faster than the beat implies."
  }
}
```

**Deliberate design points**

- **No `pacing_score`.** A 1–10 score from an LLM is noise wearing the
  costume of a metric — unanchored, unstable across calls, and impossible to
  act on. Prose critique that cannot be acted on does not earn its tokens.
- **No `style_violations` field.** Style is measured deterministically in
  Python (§14) and handed to the editorial pass as evidence. Asking a model
  to re-derive what a regex already knows wastes the scarcest quota in the
  stack and produces a vaguer answer.
- **`beat_adherence` is new.** `prompt.md` step 6 sends the editor only the
  chapters, continuity tracker, and style guide — not the beat and not the
  character sheet. So it structurally *cannot* detect "this chapter did not
  do what it was supposed to do" or "this character acted out of character",
  which are the two commonest ways an AI chapter goes wrong. The editorial
  prompt therefore includes both, and this field reports the result.
- **`suggested_canon_patches` are written to
  `log/sessions/<id>-patches.md`**, never applied and never printed only to
  stdout. `prompt.md` says to "print a diff" — in an automated runner stdout
  is a log nobody reads, and a high-stakes suggestion would be lost.

**Failure policy**

1. Invalid JSON or schema violation → one repair prompt quoting the
   validation error, up to `max_repair_attempts`.
2. Still invalid → **fail closed**. Chapter stays `editorial-pending`.
   Nothing is appended to canon. The session report says so explicitly.
3. A schema failure is a **permanent** failure and must not walk the
   drafting fallback chain (see [architecture.md](architecture.md) §6).

---

## 13. Session audit record — `log/sessions/<session-id>.json`

Immutable, written once at session end. Records: session id, book slug,
chapter number, POV, every model call attempted with provider, model ID,
outcome, latency, and token counts; whether fallback fired and why;
continuation rounds; all style-check metric values; the raw validated
editorial delta; and the final phase reached.

**No secrets, no raw prompts containing keys, no `Authorization` headers.**
Retry and backoff logging is the classic place an API key leaks; the logger
redacts by allowlist, not by blocklist.

---

## 14. Deterministic style checks

Pure Python, zero API cost, run on every chapter before the editorial pass.

| Metric | What it catches |
|---|---|
| Banned phrase / pattern hits | The explicit "AI-slop" list from `style-guide.md` |
| Sentence-length mean and stdev | Monotone rhythm; models drift toward uniform mid-length |
| Adverb rate (`-ly` per 1000 words) | The single most reliable AI-prose tell |
| Type–token ratio | Vocabulary collapse |
| Dialogue-to-narration ratio | Drift away from the POV's specified balance |
| Repeated sentence openings | "He …" / "She …" pileups |
| Paragraph-length distribution | Wall-of-text drift |
| Em-dash and semicolon rate | House-style tells |
| Word count vs target | Feeds the continuation loop |

Thresholds live in `style-guide.md` per book, not in code — they are a
creative choice, not an engineering constant. Metrics are advisory: they
populate the session report and the editorial evidence, and never block a
chapter automatically.

---

## 15. CLI surface (v1)

```bash
# Scaffold a blank vault for a new book, then exit.
# The interview itself is conversational (ADR-0001), not a questionnaire.
new-book --slug <book-slug>

# Run one chapter (ADR-0003).
write-session --book <book-slug> [--dry-run] [--chapter N] [--resume|--force]

# Assemble and print the prompt, spend nothing.
write-session --book <book-slug> --dry-run

# Run only the deterministic style checks over an existing chapter.
check-style --book <book-slug> --chapter N
```

| Flag | Behaviour |
|---|---|
| `--dry-run` | Assemble context, print the exact prompt, exit before any API call. Also settable via `DRY_RUN=1`. |
| `--chapter N` | Override manifest target selection. Refuses if chapter N already exists unless `--force`. |
| `--resume` | Continue an interrupted session from its recorded phase. |
| `--force` | Permit overwriting an existing chapter. Prints the destructive action and requires confirmation. |

`--dry-run` is not a nicety. Prompt tuning is the highest-iteration activity
in the project and the free-tier quota is the hardest constraint on it;
being able to iterate on the assembled prompt for free is what makes tuning
affordable at all.
