# novel-engine

A local automation pipeline that drafts a novel one chapter at a time using
free-tier LLM APIs, with a markdown vault as the single source of truth.

- The vault is the database.
- Models are stateless, fallible workers.
- Python — never a model — decides what gets written to disk.

See `CLAUDE.md`, `architecture.md`, and `specs.md` for how it works.

```bash
uv sync
uv run pytest
```

## One session

```bash
uv run new-book --slug my-book
uv run write-session --book my-book --dry-run   # assemble the prompt, spend nothing
uv run write-session --book my-book             # draft, check, review, reconcile
uv run write-session --book my-book --resume    # continue an interrupted session
uv run check-style --book my-book --chapter 3   # measure a chapter, no API key needed
```

A session takes one chapter from the manifest through
`target → drafted → styled → [editorial-pending | reconciled] → complete`,
writing every phase to `log/next-step.md` before the next one starts, so an
interruption is always resumable.

**Exit codes:** `0` the chapter is finished and pending review · `1` nothing
usable happened · `2` the prose is on disk but the continuity review did not
reconcile, canon deliberately untouched, resumable with `--resume`.

## Recovery

Each book is its own git repository, and every session leaves two commits —
the author's edits before it starts, the engine's writes after it ends. No
remote is configured and nothing is ever pushed.

```bash
git -C vault/<slug> log --oneline      # every session, newest first
git -C vault/<slug> show HEAD          # what the last session changed
git -C vault/<slug> checkout HEAD~1    # undo the last session
```

This is local history on one disk. It is not an off-machine backup.

## What it does not claim

The continuity pass catches number and identity contradictions, because a
deterministic check finds those before the model is asked and hands them over
as evidence. Dates, orderings, rewritten quantities and capabilities are
caught by nothing that has been tested. An empty violation list means nothing
was reported — not that the chapter is clean.
