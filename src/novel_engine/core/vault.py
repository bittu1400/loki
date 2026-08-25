"""Markdown and frontmatter IO; safe append primitives.

THE ONE-WRITER RULE: this is the only module in the project permitted to
write to disk. Everything else returns data. Exposes append primitives
only — append_fact, append_summary, append_thread, flip_thread_status —
and deliberately no general "write canon file" function (invariant 1).
"""
