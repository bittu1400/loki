# Style Guide — The Salt Almanac

## POV and tense

Third limited, past tense. One POV per chapter, never head-hop. The POV
notices procedure before feeling: an emotional beat lands through what the
character catalogues, counts, or fails to log.

## Banned phrases

- "a testament to"
- "little did he know"
- "the air was thick with"
- "she let out a breath she didn't know she was holding"
- "palpable"
- "dance" as a verb for non-dancers
- "symphony" applied to anything not musical

## Rhythm

Sentence-length mean near 14 words with visible variance: at least one
sentence under 6 words per paragraph group, at least one over 30 per page.
Dialogue sparse and transactional; characters answer the question they
wish had been asked.

## Thresholds

Machine-read. Only the table strictly between the THRESHOLDS markers is
parsed; the prose above is for humans and the drafting model. An empty
or `-` cell means unbounded on that side. Delete the whole block to run
the checks as metrics-only, with no verdicts.

Two metrics are deliberately left unbanded and report-only.
`type_token_ratio` falls as a chapter gets longer, so one band cannot be
fair to a 200-word scene and a 1500-word one. `words_vs_target` is
already governed by the continuation loop, and the hand-written opening
chapters here are short excerpts by intent, not shortfalls.

<!-- THRESHOLDS:BEGIN -->
| metric | min | max |
|--------|-----|-----|
| sentence_length_mean | 11 | 18 |
| sentence_length_stdev | 6 | - |
| adverb_rate_per_1000 | - | 12 |
| dialogue_ratio | - | 0.35 |
| em_dash_rate_per_1000 | - | 10 |
| semicolon_rate_per_1000 | - | 5 |
| paragraph_length_max | - | 180 |
<!-- THRESHOLDS:END -->
