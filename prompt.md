# Build Spec: Multi-Model Novel Writing Automation

Paste everything below to Claude Code as the initial instruction.

---

## Objective

Build a local automation pipeline that drafts a novel session by session (2 chapters, ~1000 words each, per session), using a persistent "story bible" as context and free-tier LLM APIs only. The system must assign a consistent model per POV character/thread for voice stability, and automatically update its own continuity/state pages after every session so no context is ever manually re-entered.

## Hard constraints

- Zero cost. Only use free API tiers: Google Gemini (AI Studio), OpenRouter's free model pool, and Groq. No paid keys, no assumption of credits.
- Build in retry/backoff and automatic fallback to a secondary free model if the primary hits a rate limit.
- All story data lives in plain markdown files (works with Obsidian natively; can sync to Notion later via its API — don't build Notion integration yet, just keep the file format Notion-import-friendly).

## Vault structure to create

```
/vault
  /canon
    story-bible.md        # premise, themes, tone, target length
    style-guide.md         # POV rules, tense, banned "AI-slop" phrases, sentence rhythm notes
    plot-outline.md        # act structure + chapter beat sheet
    worldbuilding.md
    power-system.md
    continuity-tracker.md  # flat list of locked facts, updated every session
    open-threads.md        # planted setups awaiting payoff
  /characters
    <character-name>.md    # bio, arc, speech patterns, vocabulary, relationships
  /log
    chapter-summary.md     # rolling one-paragraph-per-chapter synopsis, appended every session
    next-step.md           # what happens next / where we left off
  /chapters
    chapter-001.md, chapter-002.md, ...
  /config
    models.yaml             # POV character -> model assignment (see below)
    prompt-template.md       # the fixed session instruction
```

## Model assignment (config/models.yaml)

Map each POV character to one model, consistently, for the whole book. Example:

```yaml
pov_models:
  character_a: { provider: gemini, model: gemini-2.5-flash }
  character_b: { provider: openrouter, model: qwen/qwen3-235b-a22b:free }
  character_c: { provider: openrouter, model: deepseek/deepseek-v3:free }
fallback_chain:
  - { provider: groq, model: llama-3.3-70b-versatile }
editor_pass_model: { provider: gemini, model: gemini-2.5-pro }  # used only for the consistency pass below
```

Never mix models mid-chapter. One chapter = one POV = one model, start to finish.

## Session pipeline (single command, e.g. `python write_session.py`)

1. Read `/config/prompt-template.md` and inject: story-bible, style-guide, relevant character sheet(s) for this chapter's POV, plot-outline's next beat, continuity-tracker, open-threads, and the last ~2 entries from chapter-summary.md (not the whole book — keep the injected context tight and current).
2. Determine today's target: which POV/character is next per plot-outline, look up its assigned model from models.yaml.
3. Generate chapter N (~1000 words) via that model's API. Retry with fallback_chain on failure/rate-limit.
4. Repeat for chapter N+1 (may be same or different POV/model per plot-outline).
5. Save each chapter to `/chapters/chapter-XXX.md`.
6. Run a consistency pass: send both new chapters + continuity-tracker + style-guide to `editor_pass_model`, asking it to (a) flag any contradictions with locked facts, (b) flag any voice drift from the style guide, (c) output an updated continuity-tracker.md and a one-paragraph addition to chapter-summary.md.
7. Auto-write those updates back to the files. Do not overwrite plot-outline or character sheets automatically — print a diff/suggestion for those instead, since those are higher-stakes edits the author should approve.
8. Print a session report: chapters written, word count, any consistency flags.

## Deliverables from Claude Code

- The Python scripts (config loader, API client wrapper per provider, pipeline runner).
- A `.env.example` for the three API keys.
- The starter markdown templates for every file in the vault structure above, pre-filled with placeholder headers so I just fill in content.
- A README explaining how to run a session and how to swap/add a POV-to-model mapping.

## New Book Intake (interactive interview, run live per book)

Build `new_book.py` as an interactive CLI session (run directly by/with Claude Code, not scheduled) that interviews the author and writes answers straight into the matching `/vault/canon/*.md` and `/vault/characters/*.md` files, creating a new book subfolder each run (`/vault/<book-slug>/...`).

Ask in these grouped batches, in order, one batch at a time (don't dump all 20+ questions at once):

1. **Identity** — working title, genre/tropes, one-sentence premise, comp titles, target tone.
2. **Story engine** — one-sentence summary; expand to one paragraph (setup/conflict/ending); protagonist goal + flaw + what's at stake; antagonist/opposing force; intended ending (rough is fine).
3. **World — story-first, 5 questions only at this pass**: what's different from our world; what does that cost and who pays it; where the story physically happens; who holds power now; what's getting worse as the story opens.
4. **Power system — ask ONLY if genre answer indicates fantasy/sci-fi/progression/cultivation.** Source, cost/limit, who can access it, what it explicitly CANNOT do. If genre is progression-fantasy/LitRPG-style, also ask about power tiers and how progress is shown to readers.
5. **Core cast** — loop per main POV character: name, role, one want, one fear/flaw, a dialogue speech quirk, arc direction. Ask "how many POV characters?" first to know how many loops to run.
6. **Plot skeleton** — act/arc structure, first arc's inciting incident + midpoint + arc-climax, series-level endgame, rough chapter count per arc.
7. **Style & voice** — POV, tense, chapter-ending convention, pacing preference, words/phrases to avoid.

After the core pass, write all answers to their vault files and stop — do not chase every worldbuilding detail up front. Print a note: "Deepen questions (religion, economy, minor factions, secondary character backstories) will surface automatically when the consistency-pass model flags a gap during actual chapter generation." Add a `deepen_queue.md` file that the consistency-pass step can append flagged gaps to, for you to answer later in a short follow-up session.

## Publishing & Scheduling (Cousins platform, $0 cost)

Architecture: GitHub Actions does the writing work on a schedule; Vercel (hosting Cousins) only receives and displays finished chapters. Do not run LLM generation inside a Vercel function — Hobby plan functions time out at ~60s, and generation will exceed that.

1. **Scheduler:** a GitHub Actions workflow (`.github/workflows/write-session.yml`) on a cron trigger (e.g. daily) runs the full session pipeline above inside the Action's own runner (no timeout issue there).
2. **Approval gate (default ON):** after the consistency pass, the Action does NOT publish automatically. It commits the new chapters + a `status: pending-review` flag to the repo and opens a GitHub Issue (or sends a notification) summarizing the session + any consistency flags, so you can read/edit before it goes live. Add a config flag `auto_publish: false` in `config/models.yaml` to control this — flip to `true` later once you trust the pipeline.
3. **Publish step:** a second small workflow (or a manual "approve" trigger, e.g. commenting `/publish` on the Issue, or just flipping `status: approved` in the file) POSTs the approved chapter's content to `https://<your-cousins-domain>/api/publish-chapter`, authenticated with a secret API key stored in GitHub Actions secrets.
4. **Cousins-side endpoint:** build a minimal Next.js API route on Vercel — `POST /api/publish-chapter` — that checks the auth header, validates payload (title, body, chapter number, POV character), and writes it into whatever Cousins uses for storage (Vercel Postgres free tier, or even a JSON/Markdown-in-repo approach if Cousins is simple). Keep this endpoint dumb on purpose — no AI logic lives here, just "receive and store."
5. **Secrets needed:** the three free LLM API keys, plus one `COUSINS_PUBLISH_KEY` — all stored as GitHub Actions repo secrets, never committed to files.

## Not in scope yet (don't build)

- Notion live sync — file-based only for now.
- A UI beyond the GitHub Issue approval flow — command line + Issues is fine.
- Full auto-publish without review — leave the approval gate on by default.
