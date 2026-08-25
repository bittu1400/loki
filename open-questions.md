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
**Owner:** Author — mostly resolved 2026-08-25 by live API probes (listing +
generation). Remaining unknowns marked below.

**Verified 2026-08-25** (all three keys valid):

| Provider | Finding |
|---|---|
| Gemini | **Entire 2.5 family is closed to new keys** (`gemini-2.5-flash`, `-flash-lite`, `-pro` all return 404 "no longer available to new users"). Working: `gemini-3.5-flash-lite` (fast, free). `gemini-3.7-flash` exists but returned persistent 503 high-demand during testing. |
| OpenRouter | Key valid, free tier. Limits: 20 RPM / **50 requests/day** (1000/day after one-time $10 credits — author cannot purchase; design to 50/day). `thinkingmachines/inkling:free` returns 403 "only available on agentic harnesses" — unusable via plain API. `z-ai/glm-5.2:free` was upstream-saturated (429) across two attempts hours apart — treat as unreliable. `minimax/minimax-m3:free` works well. |
| Groq | Key valid. **`llama-3.3-70b-versatile` no longer exists.** `openai/gpt-oss-120b` works (very fast: ~5s). |

**Consequence for specs.md §9:** every default in that section is now known
to be wrong or dead. The editorial model especially: `gemini-2.5-pro` is not
obtainable, so the editorial primary must be re-chosen from live options.
Structured-output support among free models is rare — only `glm-5.2`,
`nemotron-3-super`, and `dots-3-note` advertise it, and the first was
saturated during testing.

**Still unverified:** exact daily quotas per Gemini model on this key;
whether `glm-5.2:free` recovers; Groq daily token ceilings.

**Second round 2026-08-25 (author added four more keys; all verified):**

| Provider | Status |
|---|---|
| Mistral | ✅ Free Experiment tier works, no card (phone verify only). `mistral-small-latest` + `mistral-large-latest` both generate. Large resolves scenes early when drafting (347 words vs 1000 target) — fine for editorial calls, needs the continuation loop for drafting. |
| NVIDIA NIM | ✅ Key works; **hosts `minimaxai/minimax-m3` and `meta/llama-3.3-70b` directly** — same model as our spike winner on an independent quota. This is the stable-fallback answer: cross-provider duplication beats betting on any one provider's free pool. |
| Cohere | ⚠️ Works (~1,000 calls/mo) but Command A+ emits a thinking block that must be disabled via request param; even then it wrote 3,248 words against a 1,000-word target. Usable in extremis, poor length discipline. |
| Z.ai | ⚠️ Only GLM-Flash tier is free (`glm-4.7-flash`); larger models return "insufficient balance". Flash was overloaded during testing. |
| Cerebras | ❌ Returns 402 payment-required for generation despite a working free listing and "free tier" marketing. Dead for us. |
| GitHub Models | ❌ Fully retired 2026-07-30 (changelog-confirmed). Never configure it. |

**Stability principle recorded:** every route must have a fallback that is
(a) on a different provider, and ideally (b) the same model family served
by two providers, so a slug pull or free-pool collapse degrades quality
rather than ending the session. minimax-m3 currently satisfies this;
nothing else does yet — Phase 2's router should treat provider diversity
as a requirement, not an optimization.

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
**Status:** RUN 2026-08-25. Identical assembled prompt (Salt Almanac ch-003
beat, full context per best-practices §2) sent to four live free models.

**Raw outputs:** session transcript; not committed (they are experiments,
not canon).

**Results, ranked:**

| Model | Words | Latency | Verdict |
|---|---|---|---|
| `minimax/minimax-m3:free` | 925 | 16s | **Best overall.** Held the POV's procedural voice and counting habit, respected continuity (nine-year suspension), ended on a concrete image that mirrors ch-001's ending. Closest to target length. |
| `gemini-3.5-flash-lite` | 781 | 7s | **Best prose-per-word**, fastest. Used ledger-ear from the power-system doc unprompted. Under length (fails ±10% check). Invented an apprentice and a King — mild canon drift. |
| `nvidia/nemotron-3-ultra:free` | 1587 | 111s | Interesting but broken: overshot by 58%, fragment-heavy rhythm (mean sentence 7.7 words), slow, and **had the driftglass echo speak to Ovist directly — violates power-system.md rule that echoes are not interactive**. |
| `openai/gpt-oss-120b` (Groq) | 1281 | 5s | Weakest. Exposition via dialogue, repeated tide metaphors, used the city name *Mirek* as a person, inserted Gregorian dates (1843) into an invented calendar. |

**Answers to the four questions:**

1. **Worth automating? Provisionally yes.** Two of four outputs are
   competent published-fiction-grade prose. The architecture is not building
   on a false premise.
2. **Closest to target voice:** minimax-m3, with flash-lite a close second
   at better quality-per-word.
3. **~1000-word adherence:** only minimax-m3 held it. The others need either
   per-model word instructions or the continuation loop routinely.
4. **Prompt-fixable vs ceiling:** word-count discipline and "do not invent
   named characters or real-world dates" are prompt-fixable. gpt-oss's
   exposition habit and nemotron's fragmentation look like model ceilings.

**Consequence for OQ-06:** 1000 words remains reasonable as a target, but
`word_tolerance` needs to be enforced by the continuation loop rather than
assumed.

**Recommendation:** assign minimax-m3:free as primary drafting route;
flash-lite as the fast fallback. Re-verify monthly — this roster will rot.

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
