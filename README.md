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
