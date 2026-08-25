<!-- Master prompt template. Named slots are filled by the context builder;
     anything outside {{ }} is static prompt text, diffable and reviewable.
     Slot order matters: stable material first, volatile last — models weight
     recency, so the instruction closest to generation is about THIS chapter. -->

# Style Guide (excerpt)

{{style_guide}}

# Story Bible (excerpt)

{{story_bible}}

# POV Character Sheet

{{character_sheet}}

# Locked Facts

{{locked_facts}}

# Banned Phrases — never use these

{{banned_phrases}}

# Recent Chapters (summaries)

{{recent_summaries}}

# Previous Chapter — final words, verbatim

{{previous_tail}}

# This Chapter

POV: {{pov_character}}
Beat: {{beat}}

{{chapter_instructions}}
