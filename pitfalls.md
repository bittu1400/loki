# Pitfalls

The catalogue of ways this project fails. Each entry: the trap, why it is
tempting, what it costs, and the countermeasure.

Read this before starting any phase. Most of these are cheap to prevent and
expensive to discover.

**Severity:** 🔴 breaks the project · 🟠 causes real damage · 🟡 friction

---

## A. Continuity and state

### 🔴 A1 — Letting a model emit a whole canon file

**The trap.** Asking the editorial model to "return the updated
continuity-tracker.md" is the obvious, convenient design, and it is what
`prompt.md` step 6 literally describes.

**Why it kills the project.** An LLM regenerating a file will summarise,
compress, reword, and drop. Not maliciously — it is doing what models do.
Each session loses a little. Thirty chapters in, the early canon has quietly
evaporated, and the system that exists to prevent continuity drift has
become the mechanism causing it. Worst of all it fails *silently*: every
session reports success.

**Countermeasure.** The model emits a validated **delta** only
([specs.md](specs.md) §12). Python appends lines. No model ever writes a
file body to canon. Non-negotiable.

### 🔴 A2 — Half-applying an editorial delta

**The trap.** The delta partially validates, or the process dies midway
through applying it. Appending the good parts feels better than losing them.

**Cost.** Worse than losing them. Canon is now in a state that matches no
session, no chapter, and no audit record, while the run reported success.

**Countermeasure.** Fail closed. Chapter stays `editorial-pending`, nothing
is appended, the report says so explicitly. Apply the whole validated delta
or none of it.

### 🟠 A3 — Append-only tracker becomes the context hog

**The trap.** A2 and A1 push you correctly toward append-only. Then nobody
follows the consequence: an append-only ledger grows without bound, and
dumping all of it into every prompt directly contradicts the "tight, current
context" principle the entire design rests on.

**Cost.** By chapter 60 you are spending most of your token budget on facts
irrelevant to the current scene, degrading both cost and output quality.

**Countermeasure.** Tag facts by category and entity at write time; retrieve
only facts touching the current POV and the entities in the upcoming beat.
Cap at `context.max_locked_facts`. Compaction, when needed, is a **manual
author ritual** — never an automated model pass, which would reintroduce A1.

### 🟠 A4 — Model-invented facts becoming indistinguishable from canon

**The trap.** The editorial pass proposes a locked fact. It gets appended.
Six sessions later nobody can tell whether the author decided it or a model
hallucinated it.

**Countermeasure.** Every fact line carries an `origin` tag —
`author` or `model` ([specs.md](specs.md) §4). Model-origin facts are
provisional until promoted.

### 🟠 A5 — Chapter numbering from the filesystem

**The trap.** `next_chapter = len(os.listdir("chapters/")) + 1`.

**Cost.** One deleted or renamed file silently shifts all subsequent
numbering, and the chapter file no longer matches its manifest row or its
summary entry.

**Countermeasure.** Chapter numbers come from the manifest, always. Abort
loudly on non-contiguous or duplicate numbers rather than guessing.

---

## B. Prose quality — the risks nobody instruments

### 🔴 B1 — Building the machine before testing the generator

**The trap.** The architecture is interesting and the prose question is
uncomfortable, so the pipeline gets built first and the output gets judged
later.

**Cost.** Weeks of work on a resumable, provenance-tracked, hash-verified
system wrapped around a generator that produces prose nobody wants to read.
Every structural fix in this repo is irrelevant if that is the outcome.

**Countermeasure.** Hand-paste the real prompt into the actual free models
and read three generated chapters *before* building. Zero code, one evening.
This is the highest-value action available at any point in the project.

### 🔴 B2 — Summary-only context, producing seam-less-ness

**The trap.** Injecting only chapter summaries is clean, bounded, and
obviously correct for token budget.

**Cost.** A summary preserves *what happened* and destroys *how it read*. A
model handed a synopsis of chapter 19 writes chapter 20 as though it had
read a synopsis: tonally reset, no momentum across the seam, episodic. The
book becomes a series of competent, unconnected scenes.

**Countermeasure.** Inject the previous chapter's **final ~500 words
verbatim** alongside the summaries. Few hundred tokens. Largest single
lever on perceived continuity in the whole system.

### 🟠 B3 — Trusting an LLM to detect voice drift

**The trap.** "Send the chapter and the style guide to a model, ask if it
drifted." It reads like a check.

**Cost.** Models are agreeable. You get plausible, non-committal prose about
tone that does not correlate with actual drift — while burning your
tightest-rationed quota to get it.

**Countermeasure.** Measure style deterministically in Python — banned
phrases, sentence-length distribution, adverb rate, type–token ratio,
dialogue ratio, repeated openings. Free, sharp, reproducible. Reserve the
LLM for contradiction detection, where it genuinely has an edge.

### 🟠 B4 — Model-per-POV mistaken for voice control

**The trap.** Pinning a character to a model feels like assigning an actor.

**Cost.** Base models have no fixed fictional voice — their untuned register
is generic conversational prose. Two different free models often read more
alike than one model on two different days. And `:free` slugs version-bump
silently, so even the illusion of stability is not stable.

**Countermeasure.** Treat model pinning as a weak nice-to-have. Voice comes
from the style guide, the character sheet, explicit stylistic constraints,
and few-shot voice samples. Pin `temperature` and `seed` where supported.
Record `actual_model` per chapter so drift can be *diagnosed*.

### 🟠 B5 — Discarding the author's edits

**The trap.** Author edits a generated chapter to fix its voice. The edit is
saved. That is the end of it.

**Cost.** That diff is the highest-quality voice signal the system will ever
possess — a direct paired demonstration of wrong versus right, in the
author's hand. Throwing it away means the system's output quality is flat
forever, no matter how many chapters are written.

**Countermeasure.** `generated_hash` in the frontmatter detects that an edit
occurred. Diff edited against generated, surface notable corrections as
*suggested* style-guide additions for the author to accept.

### 🟡 B6 — 1000-word chapters as a fixed unit

**The trap.** The number is in the spec, so it is treated as settled.

**Cost.** 1000 words is a scene, not a chapter. Generated at that granularity
with a fresh context each time, prose tends to arrive pre-resolved and
episodic.

**Countermeasure.** Treat `target_words` as a tunable in `pipeline.yaml`,
not a constant, and revisit it after B1.

---

## C. Providers and free tiers

### 🔴 C1 — Falling back on a permanent failure

**The trap.** One `except` around the model call, one fallback path.

**Cost.** A malformed prompt, an auth error, or an invalid editorial schema
gets retried across three providers as though it were a rate limit. A
deterministic bug becomes a non-deterministic, quota-burning retry storm
that is nearly impossible to diagnose from logs.

**Countermeasure.** Normalise every response into one of five outcomes.
Rate-limited, transient, and model-unavailable are fallback-eligible.
Permanent failure is not ([architecture.md](architecture.md) §6).

### 🔴 C2 — Structured output breaking exactly when fallback fires

**The trap.** The editorial pass is designed around strict JSON schema mode
on the primary model. Correct. But most OpenRouter `:free` models do not
reliably honour a JSON schema.

**Cost.** The structured-output safeguard evaporates at the precise moment
it is needed most — when the primary is rate-limited.

**Countermeasure.** Editorial fallback prefers a same-family model known to
support structured output. Add a JSON repair-and-retry loop. Fail closed
after that. Never accept "close enough" JSON into canon.

### 🟠 C3 — Hardcoding model IDs

**The trap.** `MODEL = "deepseek/deepseek-v3:free"` somewhere in the code.

**Cost.** `:free` slugs are renamed, rate-limited to uselessness, and pulled
without notice. The failure surfaces as a confusing 404 mid-session.

**Countermeasure.** Model IDs are configuration data, validated at startup
before any call. `actual_model` recorded in every chapter's frontmatter.

### 🟠 C4 — Leaking a key through retry logging

**The trap.** Debugging a 429 by logging the full request.

**Cost.** The key lands in a log file — and in Phase 7, in a public GitHub
Actions log.

**Countermeasure.** Redact by **allowlist**, not blocklist: the logger emits
only fields it explicitly knows are safe. Never log raw headers or raw
request bodies. See [threat-model.md](threat-model.md).

### 🟡 C5 — Assuming a request returns the requested length

**The trap.** Ask for 1000 words, assume you got roughly 1000 words.

**Cost.** Free-tier models routinely under-deliver, pad, or truncate at
`max_tokens`. Short chapters silently enter canon.

**Countermeasure.** Count words. If short of tolerance, run a continuation
loop passing the draft's tail, capped at `max_continuation_rounds`. Record
`continuation_rounds` in frontmatter.

### 🟡 C6 — Ignoring `Retry-After`

**Countermeasure.** Exponential backoff **with jitter**, and honour the
`Retry-After` header when present. Without jitter, retries synchronise and
re-collide.

---

## D. Automation and workflow

### 🔴 D1 — Approval that does not bind to content

**The trap.** Approve via a GitHub Issue comment; a later workflow publishes
"the approved chapter."

**Cost.** The draft can change between approval and publication. Unreviewed
content publishes carrying a reviewed chapter's blessing. This is a
correctness bug, not a process nicety.

**Countermeasure.** Approval binds to a specific commit **and** chapter
content hash. The publish step verifies the hash before sending, and refuses
on mismatch. (Deferred to Phase 8, specified now so nothing precludes it.)

### 🟠 D2 — Automation cadence set by API capacity

**The trap.** Free tier allows a daily run, so the cron is daily.

**Cost.** The scarce resource is author attention, not quota. A daily cron
producing reviewable prose outruns any human reader within a week; the
unreviewed queue grows monotonically, and that is the shape in which hobby
projects quietly die.

**Countermeasure.** Manual trigger in v1 (ADR-0003). If a cron arrives, its
cadence matches sustainable review throughput, and a concurrency gate
refuses to generate while an unreviewed session is outstanding.

### 🟠 D3 — High-stakes suggestions printed to stdout

**The trap.** `prompt.md` step 7 says to print a diff for plot-outline and
character-sheet changes.

**Cost.** In an automated runner, stdout is a log nobody opens. The
suggestions the author most needs to see are the ones most reliably lost.

**Countermeasure.** Write them to `log/sessions/<id>-patches.md` and commit.
Print a pointer, not the content.

### 🟠 D4 — Non-resumable sessions

**The trap.** The happy path is written first and interruption is handled
"later".

**Cost.** A run dies after the draft but before reconciliation. Re-running
regenerates the chapter, overwriting prose the author may have already read,
and desynchronises the vault.

**Countermeasure.** Persist the phase to `next-step.md` before each
transition. On restart: resume, or refuse with a precise message. Never
silently regenerate.

### 🟡 D5 — Two chapters per session

**Cost.** If chapter N is bad, N+1 built on it is wasted too; a partial
failure between them doubles the states resume must handle. No throughput
gain — running a one-chapter session twice produces the same output.

**Countermeasure.** One chapter per session (ADR-0003).

---

## E. Parsing and format

### 🟠 E1 — Parsing prose to find the next chapter

**Cost.** Regexing a human-written beat sheet is non-deterministic and
produces off-by-one errors that surface as a chapter written from the wrong
beat, in the wrong POV, by the wrong model.

**Countermeasure.** A delimited manifest section
([specs.md](specs.md) §2). Prose stays prose; the parser reads only between
the markers.

### 🟡 E2 — Frontmatter that Notion cannot import

**Countermeasure.** Flat, scalar-or-simple-list frontmatter. No deep
nesting, no callouts. Free now, annoying later.

### 🟡 E3 — Inconsistent filenames

**The trap.** `prompt.md` writes `deepen_queue.md` while every sibling is
hyphenated.

**Countermeasure.** Kebab-case everywhere, enforced by a startup vault
validation check.

### 🟡 E4 — A content hash that silently invalidates

**The trap.** Frontmatter carries `hash:` of the file. The author edits the
chapter. The hash is now wrong and means nothing.

**Countermeasure.** `generated_hash` is the hash of the body **as
generated**, immutable. Comparing it to the current body's hash is how the
system detects an author edit — the staleness is the signal (B5).

---

## F. Project shape

### 🟠 F1 — Building against an undefined dependency

**The trap.** `prompt.md` says to write into "whatever Cousins uses for
storage." Cousins is never specified.

**Countermeasure.** Deferred out of v1 (ADR-0001). Not designed against
until it is defined.

### 🟠 F2 — A questionnaire where a conversation belongs

**The trap.** Build `new_book.py` as a fixed interview because the spec
describes one.

**Cost.** The story bible determines all downstream quality. A fixed script
cannot follow up on an interesting answer, notice a contradiction, or push
back on a vague premise. Significant effort spent building a worse instrument
than the one already available.

**Countermeasure.** `new_book.py` scaffolds blank templates and exits. The
interview is conversational.

### 🟡 F3 — Config files that mix concerns

**The trap.** `auto_publish` in `models.yaml`, per `prompt.md`.

**Countermeasure.** `models.yaml` = routing. `pipeline.yaml` = behaviour.

### 🟡 F4 — Reviewer capture

**The trap.** A confident, well-written spec invites agreement. All three
model analyses of `prompt.md` graded the architecture and none questioned
whether the premise held (B1).

**Countermeasure.** For any review, ask explicitly: *what would make this
project not worth building?* If the answer is "nothing", the review has not
happened yet.
