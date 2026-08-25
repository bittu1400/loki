# Continuity Tracker

Append-only ledger of locked facts. The engine only ever adds lines.
Editing or removing a line is an author action.

Line grammar:

- `[<category>]` `[ch-<NNN>]` `[<origin>]` <fact sentence>

Categories: world · character:<id> · magic · timeline · object · location.
Origin: author (authoritative) · model (provisional until confirmed).

Compaction is a manual author ritual. No automated pass, no model, ever
rewrites this file.

<!-- FACTS:BEGIN -->
<!-- FACTS:END -->
