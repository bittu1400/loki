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

**Blocks:** running `write-session` against any real vault at all —
widened 2026-09-04. Until Session 10 this blocked the Phase 5 library
code, which nothing invoked; now `write-session` runs the editorial pass
and the reconciler as part of every session, so the blocked surface is
the main command rather than an unreachable module.
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

**Until resolved:** all development and testing runs against
`vault/example-book/` only, which git can restore.

**One partial mitigation exists (2026-09-04).** `editorial.enabled: false`
in a book's `pipeline.yaml` runs drafting and the style checks and takes
the `styled -> complete` edge, writing no canon at all (decision #36).
That makes a real book *draftable* today. It is not a resolution: it buys
safety by switching off the continuity layer, and the moment the author
wants that layer on, this question is load-bearing again.
`canon_transaction` is not the resolution either — it recovers one
interrupted apply, not a session the author wants to undo tomorrow.

---

## ~~🔴 OQ-02 — Which free-tier models and IDs actually work right now?~~ — RESOLVED 2026-08-25

**Resolved by live probes over two rounds** (see findings tables below).
Every default in specs.md §9 was found dead or wrong; verified routes are
recorded in `vault/example-book/config/models.yaml` with dated comments,
and the final routing is in decisions.md #7. Residual unknowns (exact
per-model daily quotas on this Gemini key, whether `glm-5.2:free`
recovers, Groq TPM ceilings) do not block anything and are noted at the
end of this entry.

---

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

## ~~🟠 OQ-04 — Has the prose spike been run, and what did it show?~~ — RUN 2026-08-25

**Blocks:** nothing any more — go/no-go answered **provisionally yes**.
Re-run recommended monthly or whenever a route dies; this roster rots.

**Results, ranked:**

| Model | Words | Latency | Verdict |
|---|---|---|---|
| `minimax/minimax-m3:free` | 925 | 16s | **Best overall.** Held the POV's procedural voice and counting habit, respected continuity (nine-year suspension), ended on a concrete image that mirrors ch-001's ending. Closest to target length. |
| `gemini-3.5-flash-lite` | 781 | 7s | **Best prose-per-word**, fastest. Used ledger-ear from the power-system doc unprompted. Under length (fails ±10% check). Invented an apprentice and a King — mild canon drift. |
| `nvidia/nemotron-3-ultra:free` | 1587 | 111s | Interesting but broken: overshot by 58%, fragment-heavy rhythm (mean sentence 7.7 words), slow, and **had the driftglass echo speak to Ovist directly — violates power-system.md rule that echoes are not interactive**. |
| `openai/gpt-oss-120b` (Groq) | 1281 | 5s | Weakest. Exposition via dialogue, repeated tide metaphors, used the city name *Mirek* as a person, inserted Gregorian dates (1843) into an invented calendar. |

**Third run — 2026-08-31, local gemma-4-12b (Session 7).** First spike
run with the Phase 4 metrics instead of by eye, and the first one that
changed the prompt rather than the model. Identical ch-003 prompt, local
llama.cpp (`gemma-4-12B-it-qat-UD-Q4_K_XL`, 8192 ctx), temp 0.9 /
top_p 0.95 / seed 20260825 as models.yaml specifies.

| Draft | Words | Sentence mean | Stdev | TTR | "He" openings | Thresholds failed |
|---|---|---|---|---|---|---|
| minimax-m3 ch-003 (committed) | 1451 | 19.6 | 22.0 | 0.281 | 24 / 74 | 1 (mean high) |
| gemma-4-12b, prompt as-is | 1389 | 9.7 | 6.3 | 0.354 | 58 / ~143 | 1 (mean low) |
| gemma-4-12b + rhythm block | 1140 | 12.4 | 7.6 | 0.392 | 35 / ~92 | **0** |
| minimax-m3 ch-005 + rhythm block (live) | 1128 | 17.1 | 17.5 | 0.335 | 19 / 66 | **0** |

The finding is about the prompt, not the roster: the staccato was fixable
with an instruction, and the same instruction pulled the long-winded
model down and the short-winded one up. Recorded as decisions.md #23; the
block now ships in the packaged prompt template.

Local gemma was adopted as the last-resort drafting fallback for
availability rather than prose ([ADR-0006](adr.md#adr-0006--local-model-lane)):
35–46s per draft on this hardware, no quota, no rate limit, and nobody
else can withdraw it. It is dead whenever the server is not running.

Two things the run surfaced that no metric catches. The banned-phrase
check matches literal strings, so a descriptive rule like "'symphony'
applied to anything not musical" did not catch "a recurring silence in
the music of the Office". And both rhythm-block drafts came in at
essentially zero dialogue (0.002 and 0.000) — defensible per beat, worth
watching as a pattern, and an argument for a dialogue_ratio minimum.

**Fourth run — 2026-08-31, gemma with its thinking channel ON.** The
author asked whether reasoning was blocked. It was, by the GGUF's own
chat template (`enable_thinking | default(false)`, plus a pre-closed
thought channel when off — pitfalls C8). Same ch-003 prompt, thinking
enabled via `chat_template_kwargs`.

| Draft | Completion tokens | Seconds | Words | Sentence mean | Thresholds failed |
|---|---|---|---|---|---|
| gemma + rhythm, thinking OFF | 1406 | 35 | 1140 | 12.4 | **0** |
| gemma + rhythm, thinking ON | 2875 (874 reasoning words) | 70 | 1101 | 10.9 | 1 (mean low) |

Twice the tokens, twice the time, worse rhythm. The reasoning trace is
the interesting part: it restated every constraint correctly, listed each
banned phrase and checked it off, and measured a sample sentence at "34
words - Good" — then wrote prose with a 10.9-word mean and 40 "He"
openings. It also explicitly decided "let's keep it internal/solitary",
which is a plausible mechanism for the near-zero dialogue seen in both
rhythm-block drafts: the style guide asks for sparse dialogue and the
model resolves sparse as none.

Conclusion: thinking stays OFF for drafting (decisions.md #11's Cohere
finding, reproduced locally with numbers). It is worth measuring for the
Phase 5 editorial pass, where the deliverable is a judgement about
contradiction rather than prose — but that is a Phase 5 experiment, not a
routing change now.

**Read-through, 2026-08-31 (all five drafts, by eye).** The metrics and
the reading disagree, which is the most useful thing this spike produced.

Craft ranking: minimax ch-005 (rhythm) > minimax ch-003 > gemma+rhythm >
gemma plain > gemma+thinking. Metric ranking put gemma+rhythm first (zero
thresholds failed) and minimax ch-003 below it (one failed).

The metrics measure AI-prose *tells* — rhythm, repetition, vocabulary
spread. A draft can clear all of them and still be thematically
over-explained and dramatically inert, which is what gemma+rhythm is:
"The Office was not just a record-keeper; it was a gardener", then a
paragraph extending the metaphor. minimax fails a threshold and is far
better, because it stages a discovery physically and lets a minor
character puncture the POV's register ("It's a person standing up.").
This is the concrete argument for specs §14 keeping metrics advisory and
never letting them gate a chapter.

Three defects no metric caught, all found only by reading:

- **gemma+thinking breaks the fourth wall**: "the corrections he had
  found in Chapter 1". It also describes "the salt-grey of his hair" from
  outside a third-limited POV. The reasoning draft was the worst of the
  five despite its trace checking every rule by name.
- **gemma plain drifts on canon**: puts "A man named Brannec Tull,
  perhaps" in Ovist's head, when the outline's premise is that neither
  man knows the other.
- **minimax ch-005 contradicts itself internally**: "The corrections were
  there. Both of them." and later "There were nine. Nine corrections on
  the spring-tide page." Canon (ch-001) says two. This is a ready-made
  test case for the Phase 5 editorial pass — the exact failure class it
  exists to catch, sitting in the committed fixture.

The rhythm block did not cost minimax anything in voice: ch-005 is the
strongest chapter in the vault and 22% shorter than ch-003.

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

### Re-run 2026-08-25 — new-provider sweep (partial; blocked by caps)

Author requested a full sweep of every untested model on the new providers
(aihubmix, chutes, siliconflow). Same assembled ch-003 prompt, ~1000-word
target. Outcome: **no challenger beats minimax-m3; routing unchanged** —
and the sweep itself exposed that AiHubMix's free tier is not sustainable.

| Model | Provider | Words | Latency | Verdict |
|---|---|---|---|---|
| `gemini-3.7-flash-free` | aihubmix | 878 | 27s | Best of the new batch. Held procedural voice, counting habit, ledger-ear, continuity. Truncated mid-sentence at the end. Invented Brannec's age (mild drift). Under target (-12%). Not clearly better than minimax-m3 → no change. |
| `gemini-3-flash-preview-free` | aihubmix | 605 | 25s | Decent voice; -40% length; invented a two-clerk rule. Out. |
| `nemotron-3-super-120b-a12b-free` | aihubmix | 324 | 30s | Severe undershoot (-68%); claimed spring tides are ~14 months apart (false). Out. |
| `nemotron-3.5-lightning-free` | aihubmix | 1616 | 50s | Leaked chain-of-thought into prose; +62% overshoot. Family pattern confirmed: out. |
| `gemini-3.6-flash-free` | aihubmix | 76 | 30s | Truncated almost immediately (thinking consumed budget). Untestable at this setting. |

Untested (~20 aihubmix models, all coding/image/tiny/omni variants
excluded up front): **blocked — see cap finding below.**
Chutes: real catalog is paid TEE models only; account balance $0 → nothing
testable at zero cost. SiliconFlow: its permanently-$0 list has rotated away
(Qwen3-8B → 402 insufficient balance; R1-Distill → model disabled).

**Key finding — AiHubMix free tier is capped at ~10 lifetime requests per
unrecharged account**, after which every free model returns an abuse-warning
string instead of prose. Our smoke tests plus this spike exhausted it in one
day. It therefore fails the author's stability condition for fallback lanes.

**Consequences:** aihubmix demoted out of the drafting fallback chain
(decisions.md #12); minimax-m3's stable lanes return to openrouter → nvidia.
Requesty remains the only untested provider, pending a regenerated key.

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

**Blocks:** nothing. Partially informed by OQ-04 (2026-08-25): only
minimax-m3 held ~1000 words unaided; flash-lite undershot (781), mistral
large undershot badly (347), command-a overshot 3×. So 1000 stays the
default, but `word_tolerance` must be **enforced by the continuation
loop**, not assumed of any model. Revisit after Phase 3 produces real
continuation behaviour.

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
LLM pass, and Phase 5's number check (specs §16) removes a slice of the
continuity work too, so the pass is cheaper per chapter than this question
assumed.

**Updated 2026-09-01.** The model named here originally
(`gemini-2.5-pro`) is unobtainable and the editorial route is now
`gemini-3.5-flash-lite` → `mistral-medium-latest` (decision #31). One
measured data point on cost: a full editorial pass over a ~1500-word
chapter cost 3708 input / 476 output tokens on flash-lite and 3457 /
1091 on mistral-medium. Nothing has hit a quota ceiling yet.
Phase 6 Session 10 wired the pass into `write-session`, so every real
session now spends an editorial call — but no real book exists to run
them against (OQ-01), so the numbers that would answer this question
still do not exist. What did change: `editorial.enabled: false` is now a
working per-book switch, which is the crudest possible version of the
cadence knob this question recommends.

**Scope.** Only the cadence of the LLM editorial pass. Deterministic style
checks are free and always run every chapter.

**Recommendation:** every chapter by default. Add a `pipeline.yaml` knob
rather than deciding now. The continuity tracker's value degrades quickly if
contradictions are caught two chapters late.

---

## ~~🟡 OQ-09 — Do style checks get numeric thresholds, and where do they live?~~ — RESOLVED 2026-08-31

**Blocks:** Phase 4 Batches 2–3 (threshold comparison + `check-style` CLI).
Raised 2026-08-26 at Phase 4 planning.

**The situation.** specs.md §14 says thresholds live in each book's
`style-guide.md` per book, never in code — they are creative choices. The
example-book style guide currently carries rhythm targets in prose
("sentence-length mean near 14 words") but no machine-readable threshold
block for adverb rate, type–token ratio, dialogue ratio, or paragraph
length. The metrics can be computed without it; the *comparison and
flagging* layer cannot.

**Scope.** Whether a fixture gains a structured thresholds block (e.g. a
`<!-- THRESHOLDS -->` delimited section parsed like the manifest), what
its exact keys are, and whether absent thresholds mean "report metric,
skip verdict" or "apply built-in defaults" (the latter would violate the
thresholds-live-in-config rule).

**Recommendation:** delimited block in style-guide.md, parsed with the
same marker discipline as MANIFEST/FACTS; absent block ⇒ metrics are
reported, verdicts are skipped. Keeps thresholds author-owned and makes
"no thresholds yet" an explicit, visible state rather than hidden
defaults.

**RESOLVED 2026-08-31 (decisions.md #22):** recommendation adopted as
written. `<!-- THRESHOLDS -->` block in `style-guide.md`; no block ⇒
metrics reported, verdicts skipped; no numeric defaults in code. The
example-book fixture gains a block so Batches 2–3 are testable.

---

## 🟠 OQ-10 — Can the editor model catch a continuity contradiction?

**Numeric contradictions: ANSWERED 2026-09-01** (decisions #29, #30,
#31). **Identity contradictions: MEASURED and CLOSED 2026-09-04** — the
answer was "no, not unaided; yes with a deterministic finding", and the
check that supplies that finding is built (decision #39, specs §17).
**Dates, orderings, rewritten quantities and capabilities: still open,
still untested by anything.** That remainder is now the whole question.

**The case.** The original ch-005 (`git show
d518b74:vault/example-book/chapters/chapter-005.md`) says "nine
corrections on the spring-tide page" against ch-001's locked fact that
the page carries **two**. That fact was retrieved into the prompt, six
lines above the chapter text.

**What five live runs showed**

| Run | Editor | Prompt | Result |
|---|---|---|---|
| 1 | gemini flash-lite | original | `[]` — missed it, and the summary it wrote repeated "nine corrections", putting the contradiction INTO canon |
| 2 | gemini flash-lite | "check every locked fact, one at a time" | one violation, the WRONG one ("twelve years of rolls" against "eleven years keeping the ledger") — planted one still missed |
| 3 | mistral-large-latest | — | **403 `tier_not_allowed`.** The Session 4 fallback is dead; `/v1/models` still lists it |
| 4 | mistral-medium-latest | same as run 2 | **caught it unaided** — quoted the sentence, named the fact, first call, zero repairs. Also proposed "The page carries nine corrections" as a NEW LOCKED FACT (→ decision #29) and 8-9 facts including set dressing (→ decision #32) |
| 5 | gemini flash-lite | run 2 + the #30 number check finding | **caught it, both runs**, and decision #29's refusal fired end to end: nothing appended |

**What that settles.** Prompt wording alone did not fix it. A better
model did (run 4). A deterministic pre-filter fixed it on the weaker
model too, more cheaply (run 5), which is why routing went back to
flash-lite in #31 — the judgement is now partly in Python, where it
does not depend on a free tier staying alive.

**What is still open.** Every catch so far is a bare number
disagreement, which is exactly the class `quality/continuity_numbers.py`
finds and hands over. Nothing has tested whether either model catches a
contradiction the regex cannot see:

- a **name** ("Ferain Hoss" where canon says the predecessor was someone
  else)
- a **date or ordering** ("the seal predates the flood" against a locked
  timeline fact)
- a **rewritten quantity** ("a handful of corrections", "half a dozen")
- a **capability** (a character doing what a locked fact says they
  cannot)

Run 4 is the only evidence that a model finds a contradiction the
pre-filter is not already pointing at, and it is one run on one case.

**Scope of the remaining question.** Only: does the pass catch
contradictions outside the numeric class, and if not, what is the
cheapest thing that does?

**Recommendation.** Plant one non-numeric contradiction in a scratch
copy of a fixture chapter — a name is cheapest to author and the hardest
for a regex — and run both editors on it. Two calls, one session, and it
decides whether the answer is "the model is fine, the prompt was the
problem" or "extend the deterministic layer to entity names next".

### The name experiment — run 2026-09-04

**Setup.** One sentence added to a scratch copy of ch-005, contradicting
a locked fact by **identity**, with no digit touched:

> The echo ledger itself had never been his. Brannec Tull had kept it
> since before Ovist's clerkship, and Ovist had never once been trusted
> to write in it.

against `[character:ovist-rhoam]` `[ch-001]` `[author]` *Ovist Rhoam has
kept the echo ledger for eleven years* — which retrieval puts in the
prompt (it is one of only **two** facts selected for this chapter).
`find_number_conflicts` reports nothing, as designed: no quantity
disagrees, so the deterministic layer is blind to it by construction.

| Run | Editor | Prompt | Violations | Also did |
|---|---|---|---|---|
| 1 | gemini flash-lite | packaged | **0 — missed** | proposed the contradicted fact, verbatim, as a NEW locked fact |
| 2 | gemini flash-lite | packaged | **0 — missed** | same again; and its summary relocated the scene to the "Vhal Mirek Office", a place that does not exist |
| 3 | gemini flash-lite | packaged + a simulated ENTITY finding | **1, `critical`** — quoted the sentence, named the fact | proposed two reasonable facts, neither of them the contradicted one |
| — | mistral-medium | packaged | **not obtained** | HTTP 429 `Rate limit exceeded` on every attempt across ~10 minutes and 8+ router retries |

**What this settles.**

- The miss is **stable, not sampling noise** — two identical runs at
  temperature 0.2.
- It is **not a prompt-wording problem**. Run 3 changed nothing about the
  instructions; it added one block of evidence in the shape ADR-0008
  already established for numbers, and the same model on the same chapter
  went from `[]` to a correctly-quoted `critical` violation.
- So the answer to "prompt, or deterministic layer?" is
  **deterministic layer**, on the same evidence pattern that settled the
  numeric case.

**A sharper finding than "it missed".** In both unaided runs the model
proposed *the very fact the chapter contradicts* as a new locked fact —
`Ovist Rhoam has kept the echo ledger for eleven years` — while the
chapter three paragraphs below said someone else kept it. It reproduced
the fact it was supposed to check against, as confirmation. Decision
#29's refusal cannot fire here, because nothing was reported as
violated: the reconciler would have appended a duplicate of the
contradicted fact, plus (run 2) a summary naming an office that does not
exist. That is pitfall A6 and pitfall A3 arriving together.

**The fallback lane was unreachable.** mistral-medium — the only model
that has ever caught a contradiction unaided (run 4, 2026-09-01) —
returned 429 on every attempt. That is worth recording on its own: the
lane the routing depends on for the unaided catch is a free tier that
was simply not there when it was wanted (pitfall C10's cousin). The
comparison it would have provided is the one piece of this experiment
still missing.

**Decided and built the same session (decision #39, ADR-0012).**
`quality/continuity_entities.py` (specs §17) now finds this class before
the call and hands it over as evidence. Re-running the live pass with the
generated finding: flash-lite reported it `critical`, quoted the
sentence, named the fact, and stopped proposing the contradicted fact as
new canon. Two classes are now covered by a deterministic pre-filter.

**What is STILL open, and is the whole of OQ-10 now.** Dates, orderings,
rewritten quantities ("a handful of corrections") and capabilities. No
deterministic check sees them and the model has never been tested on
them. The pattern is now established twice over — the model misses a
class unaided and catches it with a finding in the prompt — which should
raise, not lower, suspicion about every class where no finding exists.

**Carried into the CLI (2026-09-04).** `write-session` now prints the
violation list on every reconciled chapter, and prints the caveat with
it: an empty list means nothing was reported, not that the chapter is
clean. That wording is load-bearing while this question is open — the
one thing the pipeline must never do is make "no violations" read as a
guarantee (pitfall A6).

**Until resolved:** do not describe the editorial pass as a continuity
guarantee. It reliably proposes facts, writes summaries, surfaces
questions, and — since #30 — catches number disagreements. Everything
else is unproven.
