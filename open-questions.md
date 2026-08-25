# Open Questions

Unresolved items. Each has an ID, a blocking status, a recommendation, and
enough scope to be answerable without reading the code.

Resolved questions move to [decisions.md](decisions.md) and, if
architectural, get an ADR. They are struck through here, not deleted — the
record of what was once uncertain is useful.

**Blocking status**
- 🔴 **Blocks a phase** — that phase cannot start or ship until resolved
- 🟠 **Blocks a choice** — work continues, but a later decision depends on it
- 🟡 **Open** — worth answering, blocks nothing

---

## 🔴 OQ-01 — What replaces git as the recovery path for real vault content?

**Blocks:** Phase 5 (editorial delta pass) against any real vault.
**Referenced by:** [ADR-0004](adr.md#adr-0004--vault-location-and-what-gets-committed),
[threat-model.md](threat-model.md) T2.

**The situation.** ADR-0004 gitignores real manuscripts. That was the right
call for privacy, but it has a consequence that was not part of the
question asked: several safeguards in this design assume git history can
recover a corrupted continuity tracker. For `vault/example-book/` that is
true. For a real book it is not — there is no history, no diff, and no undo.

Phase 5 is the first component that writes to canon. Running it against an
unbacked real vault means a bad delta, an errant `--force`, or a disk
failure is unrecoverable.

**Scope of the question.** Only: how do we get a restorable history of real
vault content without committing it to this repository? Not about privacy
(settled), not about vault location (settled).

**Options**

| Option | How it works | Cost |
|---|---|---|
| **Local git repo inside the vault (recommended)** | `vault/<slug>/` is its own git repository, nested and ignored by the outer repo. The engine commits after every session automatically. | ~20 lines of code. Full diff/restore per session. Never pushed anywhere, so privacy is unchanged. Nested repos are mildly unusual but here they are invisible to the outer repo. |
| Timestamped snapshot directory | Copy the vault to `.snapshots/<timestamp>/` before each canon write. | Simplest to implement. No diffs, no messages, grows on disk, manual pruning. |
| Private remote vault repo | The vault is its own repo with a private GitHub remote. | Off-machine backup too. Costs the two-repo coordination that ADR-0004 rejected, and puts the manuscript on GitHub's servers. |
| Rely on existing backup | Assume Time Machine / Syncthing / an existing scheme covers it. | Zero work. Unverified, no per-session granularity, and the failure mode is discovered at the worst moment. |

**Recommendation:** local git repo inside the vault. It restores the exact
property ADR-0004 removed, costs almost nothing, and changes nothing about
privacy.

**Until resolved:** all Phase 5 development and testing runs against
`vault/example-book/` only.

---

## 🔴 OQ-02 — Which free-tier models and IDs actually work right now?

**Blocks:** Phase 2 (provider layer) completion.
**Owner:** Author — in progress.

**The situation.** Every model ID in `prompt.md` and in
[specs.md](specs.md) §9 is an assumption. `:free` slugs get renamed,
rate-limited to uselessness, and pulled without notice. Building a fallback
chain on unverified IDs means the first real failure is a confusing 404
mid-session.

**Scope.** For each of Gemini AI Studio, OpenRouter, and Groq, what is
needed before Phase 2 can be finished:

1. **Which model IDs are live and free** — exact slug strings, verified by a
   real call, not from documentation.
2. **Rate limits** — requests per minute and per day, and tokens per minute
   where it applies. The daily cap is what determines whether a session can
   run at all.
3. **Max output tokens per call** — this decides whether a 1000-word chapter
   is one call or needs the continuation loop routinely.
4. **Structured-output support** — does the model honour a JSON schema or
   JSON mode? This matters most for the editorial pass and its fallback
   (pitfall C2).
5. **`gemini-2.5-pro` free-tier status specifically** — it is proposed as
   the editorial model, is called every session, and is the tightest-rationed
   model in the stack. If its free tier is absent or too limited, the
   editorial model choice changes.
6. **Data-use terms** — confirm the current posture per provider
   ([threat-model.md](threat-model.md) §3).

**Recommendation:** record findings directly into `config/models.yaml` with
a dated comment per entry, so the next session knows when each was last
verified.

---

## ~~🟠 OQ-03 — Confirm the `models.yaml` / `pipeline.yaml` split~~ — RESOLVED 2026-08-25

**Resolved:** split confirmed (decisions.md #5). `models.yaml` = routing
only; `pipeline.yaml` = behaviour. The `PROPOSED` marker in
[specs.md](specs.md) §9–10 has been removed.

**Blocks:** Phase 1 (config loader) — low risk either way.

**The situation.** `prompt.md` puts `auto_publish` inside `models.yaml`.
That mixes pipeline behaviour with model routing. [specs.md](specs.md) §9–10
proposes splitting them: `models.yaml` for routing only, `pipeline.yaml` for
behaviour.

**Scope.** Purely file organisation. No behaviour change either way.

**Recommendation:** take the split. It keeps `models.yaml` small enough to
read at a glance, which matters because it is the file touched when voice
goes wrong. Marked **PROPOSED** in specs.md until confirmed.

---

## 🟠 OQ-04 — Has the prose spike been run, and what did it show?

**Blocks:** the decision to continue at all. Also informs OQ-06.

**The situation.** No one has verified that free-tier models writing
1000-word chapters from a beat sheet produce prose worth reading. This is
the project's core untested assumption (pitfall B1), and all three model
analyses of `prompt.md` skipped it.

**Scope.** Hand-paste a realistic prompt — story bible excerpt, style guide,
character sheet, one beat — into each of the three providers. Generate three
chapters. Read them. Answer:

1. Is any of it worth automating?
2. Which provider's output is closest to the target voice?
3. Does the model hold ~1000 words, or does it resolve the scene early?
4. What does it get wrong that a better prompt could fix, versus what is a
   model ceiling?

**Why it matters beyond go/no-go.** The answers directly set `target_words`
(OQ-06), the initial `pov_models` assignment, and the first draft of the
banned-phrase list in `style-guide.md`.

**Recommendation:** run it before Phase 3. It costs one evening and no code,
and it can save weeks.

---

## 🟠 OQ-05 — What is the book? (needed for `vault/example-book/`)

**Blocks:** Phase 1 — the committed fixture needs content.

**The situation.** ADR-0004 commits `vault/example-book/` as the fixture
every test and CI run exercises. A toy fixture only proves the code works on
toys, so it needs realistic content: a story bible, a style guide with real
banned phrases, a manifest with mixed statuses, two or three short chapters
with full frontmatter, and a populated continuity tracker.

**Scope.** Two sub-questions:

1. ~~**Should `example-book` be a throwaway invented story, or a stripped-down
   version of the author's real book?**~~ **RESOLVED 2026-08-25:** invented
   throwaway (decisions.md #6). Deliberately awkward — odd names, tricky
   continuity — to exercise edge cases a real book might not hit.
2. **What is the author's actual first book?** Still open. Not needed for
   Phase 1, but needed before Phase 3 generates anything real, and it is the
   input to the conversational intake interview that replaced `new_book.py`
   (ADR-0001).

---

## 🟡 OQ-06 — Is 1000 words the right chapter unit?

**Blocks:** nothing. Revisit after OQ-04.

**The situation.** `prompt.md` specifies ~1000 words. That is a scene rather
than a chapter, and prose generated at that granularity with a fresh context
each time tends to arrive pre-resolved and episodic (pitfall B6).

**Scope.** `target_words` is already a `pipeline.yaml` tunable, so nothing
is locked. The question is what the default should be, and it is answerable
only with real output in hand.

**Recommendation:** leave at 1000 for now, revisit with OQ-04's chapters on
the table.

---

## 🟡 OQ-07 — Where is this published, and what is that platform's AI policy?

**Blocks:** Phase 9 (deferred). Worth knowing far earlier.

**The situation.** Serially published AI-generated fiction is governed by
platform rules that vary widely: Amazon KDP requires AI disclosure; several
serial-fiction platforms range from disclosure-required to prohibited
outright. If a public serial platform is the destination, that constraint
shapes the project more than any technical decision in this repository.

**Scope.** Three questions: what is Cousins (it is never defined in
`prompt.md`); is anything published anywhere public; and if so, what is that
destination's stated policy on AI-assisted or AI-generated work?

**Recommendation:** answer before Phase 9 is designed, not before it is
built. If the destination is private or personal, this closes immediately.

---

## 🟡 OQ-08 — Editorial pass every chapter, or every N chapters?

**Blocks:** nothing. Revisit after OQ-02.

**The situation.** ADR-0003 chose one chapter per session, which means one
editorial pass per chapter — more calls against the tightest-rationed model
in the stack than a batched approach would need. Phase 4's deterministic
style checks mitigate this by removing the largest category of work from the
LLM pass, but if `gemini-2.5-pro`'s free tier turns out to be very tight
(OQ-02), an every-other-chapter cadence for the *continuity* pass may be
forced.

**Scope.** Only the cadence of the LLM editorial pass. Deterministic style
checks are free and always run every chapter.

**Recommendation:** every chapter by default. Add a `pipeline.yaml` knob
rather than deciding now. The continuity tracker's value degrades quickly if
contradictions are caught two chapters late.
