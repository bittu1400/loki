# Threat Model

Scope: this repository, the vault it manages, the three free-tier LLM
providers it calls, and (deferred) the GitHub Actions runner and Cousins
publish endpoint.

This is a single-author hobby project handling an unpublished manuscript and
three free API keys. It is not handling user PII, payments, or
multi-tenant data. The threat model is sized accordingly — but two assets
are genuinely worth protecting, and one class of risk is routinely
underestimated in projects of exactly this shape.

---

## 1. Assets

| # | Asset | Why it matters | Loss impact |
|---|---|---|---|
| A1 | The manuscript (`vault/<slug>/`) | Months of creative work, unpublished | **High** — irreplaceable |
| A2 | Canon integrity (continuity tracker, threads) | Silent corruption invalidates everything downstream | **High** — and hard to detect |
| A3 | API keys (3 free-tier + publish key) | Account abuse, quota theft, tier ban | Medium |
| A4 | The engine code | Reproducible from this repo | Low |
| A5 | Author's account standing with providers | ToS violation could cost tier access | Medium |

A1 and A2 are the assets. Everything else is replaceable.

---

## 2. Trust boundaries

```
┌──────────────────────────────────────────────────────┐
│ TRUSTED — author's machine                           │
│   vault/  ·  .env  ·  engine code                    │
└────────────────────┬─────────────────────────────────┘
                     │  prompts out (manuscript content)
                     │  completions in (untrusted text)
                     ▼
┌──────────────────────────────────────────────────────┐
│ UNTRUSTED — free-tier provider APIs                  │
│   Gemini AI Studio · OpenRouter pool · Groq          │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ DEFERRED (Phase 7+) — GitHub Actions runner          │
│   secrets in env · public build logs · git push       │
└────────────────────┬─────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────┐
│ DEFERRED (Phase 9) — Cousins / Vercel endpoint       │
└──────────────────────────────────────────────────────┘
```

**The load-bearing boundary is the second arrow: completions coming back in
are untrusted input.** Model output is data, never instruction, and never a
file body. Every countermeasure in §4 flows from that one sentence.

---

## 3. Data exposure — the accepted trade

This is the risk most easily missed because it is not an attack. It is the
normal, documented operation of the free tiers.

| Provider | Free-tier data posture |
|---|---|
| Google Gemini (AI Studio) | Free-tier submissions **may be used to improve Google products**, and may be human-reviewed. The paid tier does not carry this. |
| OpenRouter `:free` pool | Varies per upstream model. A substantial portion of free endpoints log and/or train on submitted content. |
| Groq free tier | Check current terms; treat as non-private by default. |

**What this means concretely.** Every chapter drafted, every locked fact,
the story bible, the character sheets, and the plot outline are sent to
third parties who may retain and train on them. The unpublished manuscript
is, functionally, training data.

**Decision.** For a hobby novel this is an acceptable trade in exchange for
$0 operating cost — but it must be a **conscious** trade, not a discovery
made after fifty chapters. It is recorded here so it cannot be discovered
later.

**Mitigations available if the posture changes:**

- Route the most sensitive canon (the ending, major twists) through the
  provider with the strongest terms, or exclude it from context entirely.
- Keep the "intended ending" out of the routine context slice — the context
  builder already injects only the premise/tone header of the story bible,
  not the whole file.
- Move to a paid tier for the editorial pass alone if the manuscript's value
  ever exceeds the cost.
- Run a local model for drafting once hardware allows.

**Verify before committing to a provider**, since terms change: read the
current data-use terms for each of the three. Tracked as an open question.

---

## 4. Threats

Rated **Likelihood × Impact**. Ordered by priority, not by category.

### T1 — Canon corruption by model write-back 🔴 High × High

**Vector.** The editorial model returns a file body, or a malformed delta,
and it is written to the continuity tracker. Facts are summarised away or
invented. The failure is silent: every session reports success.

**Why it is a security concern and not just a bug.** It is an integrity
attack on A2 where the untrusted party is the model itself. It has no
malicious actor and needs none — normal model behaviour produces it.

**Countermeasures**
- Model emits a **validated delta only**, never a file body.
- Pydantic schema validation before any write.
- Python performs the write; the append is deterministic and reviewable.
- Append-only: no engine code path edits or deletes an existing fact line.
- `origin: author|model` tag on every fact, so model-proposed canon is
  visibly provisional.
- Fail closed: invalid delta ⇒ append nothing, mark `editorial-pending`.
- Committed diffs for `example-book`; a snapshot mechanism for real vaults
  (see T2).

**Residual risk.** A *well-formed* but factually wrong delta still gets
appended. Accepted — the `origin` tag and the session audit record make it
findable and reversible by hand.

### T2 — Manuscript loss with no recovery path 🟠 Medium × High

**Vector.** ADR-0004 gitignores real vault content. Several safeguards in
this design assume git history can recover a corrupted tracker. For real
books, that history does not exist. A bad delta, an errant `--force`, or a
disk failure has no undo.

**Countermeasures**
- **Blocking:** Phase 5 (the editorial delta pass — the first component that
  writes to canon) must not run against a real vault until a snapshot
  mechanism exists. Tracked as OQ-01, and referenced from ADR-0004.
- Until then, all destructive-path development runs against
  `vault/example-book/`, which *is* committed.
- `--force` prints the destructive action and requires confirmation.

**Residual risk.** High until OQ-01 is resolved. This is the single most
important unresolved item in the project.

### T3 — API key disclosure 🟠 Medium × Medium

**Vectors**
1. `.env` committed to git.
2. A key logged while debugging a 429 — the classic case, since retry paths
   are written under pressure.
3. Phase 7: a key echoed into a public GitHub Actions log.
4. A key pasted into an issue or a chat while asking for help.

**Countermeasures**
- `.env` is gitignored; only `.env.example` is committed, and it contains no
  values. *(In place.)*
- **Redaction by allowlist, not blocklist.** The logger emits only fields it
  explicitly knows are safe. A blocklist fails the moment a new field
  appears; an allowlist fails closed.
- Never log raw request headers, raw request bodies, or full exception
  objects from the HTTP client.
- Session audit records (`log/sessions/*.json`) are built from an explicit
  field list, never by dumping a request object.
- Phase 7: keys live in GitHub Actions repository secrets. Actions masks
  known secret values in logs, but that masking is a backstop, not a
  control — do not rely on it.

**Response if a key leaks.** Revoke and reissue at the provider console
immediately; a free-tier key has no billing exposure but does carry the
author's account standing (A5). Rotating is cheap. Do it on any suspicion.

### T4 — Prompt injection via vault content 🟡 Low × Medium

**Vector.** Vault files are assembled into prompts. Text inside a character
sheet or a beat — whether pasted from an outside source or produced by a
previous model call — can contain instructions aimed at the model, e.g. a
"fact" that reads as a directive to the editorial pass.

**Why the likelihood is low but not zero.** This is a single-author project
with no external contributors, so there is no obvious hostile input path.
But **model output flows back into vault files**, which are then re-injected
into later prompts. That is a genuine feedback path from untrusted output to
future input.

**Countermeasures**
- Model output is never treated as instruction. The editorial response is
  parsed as JSON against a strict schema; free text arrives only in fields
  whose meaning is fixed by the schema.
- No engine code path executes, evaluates, or shells out to anything derived
  from model output or vault content.
- File paths in `suggested_canon_patches.target_file` are **never used to
  write**. Suggestions go to `log/sessions/<id>-patches.md` regardless of
  what path the model names — so a model naming `../../.env` or
  `.github/workflows/x.yml` achieves nothing.
- Vault paths resolve under the book root; a resolved path escaping that
  root aborts the run.

### T5 — Publishing unreviewed content 🟠 Medium × Medium *(Phase 8)*

**Vector.** Approval is granted on a GitHub Issue. The draft changes
afterwards. The publish workflow sends "the approved chapter," which is now
different content carrying a reviewed chapter's blessing.

**Countermeasures**
- Approval binds to a specific **commit SHA and chapter content hash**.
- The publish step recomputes the hash and refuses on mismatch.
- The Issue is a notification surface; the committed status field plus hash
  is the source of truth.

### T6 — Cousins publish endpoint abuse 🟡 Low × Medium *(Phase 9)*

**Vectors.** Unauthenticated publish, replay, oversized payload, chapter
overwrite.

**Countermeasures**
- Bearer token, **constant-time comparison**, checked before any other work.
- Reject on missing or malformed header before parsing the body.
- Strict payload schema validation.
- Request size limit.
- Idempotent upsert keyed on `(book_slug, chapter_number)` with a defined
  conflict policy for republication.
- No AI logic behind that endpoint, ever. It receives and stores.

### T7 — Quota exhaustion / denial of progress 🟡 Medium × Low

**Vector.** A retry storm, an unbounded continuation loop, or a fallback
misclassification (see pitfall C1) burns a daily cap. Work stops until reset.

**Countermeasures**
- Fallback only on eligible outcomes; permanent failures never retry.
- `max_continuation_rounds` and `retry.max_attempts` are hard caps.
- `--dry-run` for all prompt iteration, so tuning costs nothing.
- Deterministic style checks remove the largest category of work from the
  LLM editorial pass, conserving the tightest-rationed quota.

### T8 — Provider ToS and platform content policy 🟡 Low × Medium

**Two separate issues, both non-technical, both capable of invalidating
downstream plans:**

1. **Provider terms.** Automated bulk generation on a free tier may sit
   awkwardly with acceptable-use terms. A one-chapter, manually triggered
   session (ADR-0003) is well within ordinary usage; a high-frequency cron
   is where this would become a question.
2. **Publication platform policy.** Serially published AI-generated fiction
   is governed by platform rules that vary widely — Amazon KDP requires AI
   disclosure; several serial-fiction platforms range from
   disclosure-required to prohibited outright. **If a public serial platform
   is the destination, that constraint shapes the project more than any
   technical decision in this repository.**

**Countermeasure.** Confirm the intended publication destination and its
policy *before* Phase 9 is built. Tracked as an open question.

---

## 5. Non-threats

Stated so effort is not spent here.

- **Multi-user access control.** Single author, single machine.
- **Encryption at rest.** Delegated to the operating system's disk
  encryption.
- **Network interception.** All provider APIs are HTTPS; no custom transport.
- **Supply-chain pinning beyond a lockfile.** `uv.lock` is proportionate for
  a project of this size.
- **Availability / uptime.** Nothing here is a service. A failed session is
  retried later.

---

## 6. Security checklist per phase

Verified before a phase is marked complete in [progress.md](progress.md).

**Phase 1 — vault + config**
- [x] `.env` gitignored; `git check-ignore -v .env` confirms
- [x] `.env.example` contains no real values
- [x] Vault path resolution rejects any path escaping the book root

**Phase 2 — providers**
- [x] Logger redacts by allowlist; no raw headers or bodies logged
- [x] Keys read from environment only; never a default, never a literal
- [x] Permanent failures do not trigger fallback

**Phase 3 — drafting** *(all verified 2026-08-26, Session 5)*
- [x] Continuation loop is hard-capped
      (`max_continuation_rounds` from pipeline.yaml; test:
      `test_continuation_hard_capped_and_short_draft_still_accepted`)
- [x] Chapter writes refuse to overwrite without explicit `--force`
      (`vault.write_chapter` refuses; CLI additionally requires typed
      interactive confirmation, and refuses closed with no TTY;
      verified live: `--chapter 3` exits 1)
- [x] All-providers-failed terminal case writes a marked `failed-stub`
      chapter, manifest stays `planned`, zero API cost (ADR-0005)
      (`test_all_routes_exhausted_writes_stub_manifest_untouched`;
      permanent failure additionally short-circuits the chain —
      `test_permanent_failure_never_walks_the_chain`)

**Phase 5 — editorial** *(blocked on OQ-01)*
- [ ] Delta schema-validated before any write
- [ ] Append-only enforced in `vault.py`; no edit or delete path to canon
- [ ] Fail-closed verified by a test that feeds it malformed JSON
- [ ] `suggested_canon_patches.target_file` is never used as a write path
- [ ] Snapshot/backup mechanism exists and is tested

**Phase 7+ — automation** *(deferred)*
- [ ] Secrets in Actions secrets, never in the repo
- [ ] Approval binds to commit SHA + content hash
- [ ] Publish endpoint: constant-time auth compare, size limit, idempotent
