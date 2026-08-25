# Continuity Tracker — The Salt Almanac

Append-only ledger of locked facts. The engine only ever adds lines.
Editing or removing a line is an author action.

Line grammar:

- `[<category>]` `[ch-<NNN>]` `[<origin>]` <fact sentence>

Categories: world · character:<id> · magic · timeline · object · location.
Origin: author (authoritative) · model (provisional until confirmed).

Compaction is a manual author ritual. No automated pass, no model, ever
rewrites this file.

<!-- FACTS:BEGIN -->
- `[world]` `[ch-001]` `[author]` Driftglass forms only where the tide crosses old stone.
- `[location]` `[ch-001]` `[author]` The Almanac Office sits on the cut-water, one door in from the Rope Walk stairs.
- `[character:ovist-rhoam]` `[ch-001]` `[author]` Ovist Rhoam has kept the echo ledger for eleven years.
- `[object]` `[ch-001]` `[author]` The spring-tide almanac page carries two corrections in Ovist's hand that he did not write.
- `[character:brannec-tull]` `[ch-002]` `[model]` Brannec Tull has been unseen at the Office for eleven years, since the last full flood of the drowned quarter. (provisional)
- `[timeline]` `[ch-002]` `[model]` The drowned quarter last flooded within Brannec's diving career, not once a generation as folklore holds. (provisional)
- `[magic]` `[ch-002]` `[model]` Office lead seals are stapled to stone with square-nailed iron when a level is formally closed. (provisional)
- `[character:sela-vosk]` `[ch-002]` `[model]` Sela Vosk pays triple for unlogged driftglass that never passes the Office. (provisional)
<!-- FACTS:END -->
