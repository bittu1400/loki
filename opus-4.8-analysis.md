# Opus 4.8 Analysis — Multi-Model Novel Writing Automation

## 1. Do I understand the core architecture?

Yes. The spec describes a **file-based, git-native novel-generation pipeline** with four moving parts:

1. **State layer (the "story bible")** — a `/vault` of plain markdown files split into `canon`, `characters`, `log`, `chapters`, `config`. This is the single source of truth and the thing that gets read *into* and written *back out of* every session. Nothing lives in a database; markdown files + git history *are* the database.

2. **Generation layer (`write_session.py`)** — one command produces 2 chapters (~1000 words each). It assembles a tight prompt from a curated slice of the vault, routes each chapter to a model chosen by POV character, retries with a fallback chain on rate-limits, then runs a separate **editor/consistency pass** on a stronger model.

3. **Feedback loop (self-updating state)** — the consistency pass writes `continuity-tracker.md` and appends to `chapter-summary.md` automatically, but only *suggests* diffs for high-stakes files (plot outline, character sheets). This is the key idea that makes "no context ever manually re-entered" true.

4. **Orchestration + publishing (GitHub Actions → Vercel/Cousins)** — a cron Action does the expensive LLM work on its own runner (dodging Vercel's 60s function limit), commits results behind an **approval gate**, and a second step POSTs approved chapters to a deliberately dumb `/api/publish-chapter` endpoint.

Plus a fifth, offline-ish component: **`new_book.py`**, an interactive interview that seeds a fresh book's vault.

### The load-bearing design decisions

- **Model-per-POV pinning** for voice stability. One chapter = one POV = one model, never mixed mid-chapter. This is the single most opinionated and most interesting choice in the whole spec.
- **Tight, current context injection** — only the last ~2 chapter summaries, not the whole book. Bounds the prompt and controls cost/latency.
- **Separation of generation and judgment** — the writing models draft; a distinct `editor_pass_model` audits. Never the same call.
- **Asymmetric write-back** — auto-write low-stakes state (continuity, summaries), human-approve high-stakes state (plot, characters). Correct instinct.
- **Compute where it's free** — generation runs in the Actions runner; Vercel only receives and displays. Clean separation that respects each platform's real constraint.

## 2. What I think — strengths

- **The architecture is sound and the boundaries are drawn in the right places.** The author clearly learned from a real failure mode (Vercel timeouts) and designed around it rather than fighting it.
- **File-based state is the right call for a solo author.** Git gives free versioning, diffing, rollback, and Obsidian gives a free editing UI. No infra to run.
- **The self-updating continuity tracker is the genuine innovation.** Most "AI writes a novel" attempts die on continuity drift. Making the editor pass emit structured state that feeds the *next* prompt is the mechanism that could actually keep a long work coherent.
- **The approval-gate-default-ON posture is mature.** Auto-publish off until trust is earned, human-in-the-loop on the irreversible step.
- **Zero-cost constraint is treated as a first-class design input,** not an afterthought — fallback chains, free-tier-only, retry/backoff are baked into the pipeline shape.

## 3. What I think — risks and gaps (where this will actually hurt)

These are ranked by how likely they are to bite, worst first.

### Tier 1 — will break or disappoint early

1. **Voice stability from model-pinning is an unproven assumption.** Pinning `character_b` to `qwen3-235b:free` gives you a *consistent model*, not a *consistent voice*. The real voice-drift lever is the style guide + character sheet in the prompt, not which endpoint answers. Two different free models can read more alike than one model on two different days (temperature, provider-side updates, silent version bumps on `:free` slugs). **Recommendation:** treat model-pinning as a weak nice-to-have, invest the real effort in the style-guide/character-sheet prompt and few-shot voice samples. Pin `temperature`/`seed` where the provider supports it.

2. **1000 words from free-tier models in a single call is optimistic.** Free Gemini Flash / OpenRouter `:free` / Groq models frequently under-deliver on length, pad, or truncate at max_tokens. The spec has no length-enforcement loop. **Recommendation:** add a "continue if short" loop or generate in 2 beats per chapter, and validate word count before accepting.

3. **The consistency pass writing files back is the highest-risk automation in the system.** An LLM emitting "an updated continuity-tracker.md" can silently *drop* previously locked facts, not just add. If it overwrites rather than appends, the story bible degrades over time — the exact failure the system exists to prevent. **Recommendation:** never let the model emit the *whole* file. Make it emit a structured **delta only** (append-facts / flag-contradictions), apply the delta in code, keep the tracker append-only, and commit each version so git is the safety net.

4. **`:free` OpenRouter slugs are unstable identifiers.** They get renamed, rate-limited to near-uselessness, or pulled. `deepseek/deepseek-v3:free` today ≠ next month. **Recommendation:** the fallback chain must be per-provider AND cross-provider, and a model-unavailable error (not just 429) must trigger fallback. Log which model actually served each chapter into the chapter file's frontmatter for reproducibility.

### Tier 2 — will cause friction

5. **Rate-limit reality vs. daily cron.** Free tiers have low RPM *and* low daily caps. Two 1000-word chapters + one editor pass = at least 3 large calls, possibly more with retries/length loops. A daily run is probably fine; anything faster will hit daily caps. Worth stating the budget explicitly per provider.

6. **No idempotency / partial-failure handling described.** If the Action dies after writing chapter N but before the editor pass, re-running must not double-write or skip. The pipeline needs a resumable state marker (`next-step.md` is close, but its contract isn't defined). **Recommendation:** make `next-step.md` a machine-readable pointer (next chapter number, next POV, phase) and check it on entry.

7. **Secrets in GitHub Actions + auto-commit is a leak surface.** Fine as designed *if* nothing ever logs the key or the raw request. Retry/backoff logging is the usual place a key leaks. Flag: scrub logs.

8. **"Determine today's POV from plot-outline" needs a parseable outline.** Step 2 of the pipeline reads a human-written beat sheet to decide POV and model. Free-form markdown is hard to parse deterministically. **Recommendation:** give `plot-outline.md` (or a sidecar) a small structured block per chapter: `chapter, pov, beat`. Keep prose beats human-readable, keep the routing data machine-readable.

### Tier 3 — worth noting, not blocking

9. **Editor pass on `gemini-2.5-pro` free tier** is the tightest-rationed model of the set; it's also the one you call every session. It'll be the first bottleneck. Consider a cheaper judge or making the editor pass every-other-session.
10. **Notion-import-friendliness** constrains markdown format subtly (Notion mangles some frontmatter, nested bullets, callouts). Cheap to honor now, annoying to retrofit — keep frontmatter simple.
11. **No test/dry-run mode mentioned.** A `--dry-run` that assembles the prompt and prints it without spending a call will save enormous iteration cost while tuning.
12. **Cousins endpoint auth is a single static key.** Fine for a hobby project; just ensure it's a bearer check with constant-time compare and the endpoint rejects on missing/mismatched header before doing any work.

## 4. Suggested build order

The spec bundles a lot. I'd sequence it to de-risk the unproven parts first:

1. **Vault templates + config loader** — cheap, unblocks everything, no API cost.
2. **Provider client wrapper** with retry/backoff/fallback + a `--dry-run` and a length-check loop. Test against all three free tiers *before* building pipeline logic on top.
3. **`write_session.py` single-chapter path** — prove one chapter end-to-end, including the frontmatter logging of which model served it.
4. **Consistency pass as a delta-only, append-safe operation** — this is the risky core; get it right in isolation.
5. **`new_book.py` interview** — independent, can be built in parallel.
6. **GitHub Actions + approval gate** — only after the local pipeline is trustworthy.
7. **Cousins `/api/publish-chapter`** — last; it's deliberately dumb and decoupled.

## 5. One-line verdict

Architecturally strong and unusually well-scoped for a hobby project — the boundaries, the compute-placement, and the human-in-the-loop instincts are all right. The two things that will decide whether it actually produces a coherent novel are **(a) making the consistency-pass write-back append-only and delta-based** so the story bible can't silently rot, and **(b) not over-trusting model-pinning for voice** — the prompt does that job, not the endpoint. Fix those two and the rest of the spec is a solid build.
