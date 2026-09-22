---
type: review
status: active
authority: log
summary: "Two-round critique of Live Docs Design v0.1 by three critic agents (pragmatist, systems engineer, agent's advocate): consensus, resolved and open disagreements, questions for the user."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, review]
---

# 2026-09-21 Design Review

> **Provenance.** Three critic subagents each reviewed [[Live Docs Design]] v0.1 and the research notes. They had read-only access and each took a different perspective.
> - **Round 1:** each critic wrote an independent critique.
> - **Round 2:** each critic read the other two critiques and responded.
>
> The orchestrating agent summarized both rounds and re-checked the Meetless evidence correction directly against the source. The outcome was folded into design **v0.2**.

## Outcome

All three critics agreed the hashing idea is sound. They also agreed the draft was built to succeed rather than to find out whether the idea works.

v0.2 therefore makes these changes:
- **Phase 1 now tests value first.** It asks whether notes that describe code help agents at all, compares against two cheap baselines, and writes the kill criteria down in advance.
- **The read-time output is reshaped.** Instead of a warning, it delivers the current code facts (was / now), because that's what the evidence supports.
- **Checks become read-only and fail closed.**
- **Most hardening is deferred** until the idea survives Phase 1.

## The critics

| Critic | Lens | Round-1 verdict | Round-2 non-negotiable |
|---|---|---|---|
| Skeptical pragmatist | Value, scope, sequencing | The design builds machinery before testing whether notes beat reading the code. Cut it to drift, two hooks and one sentence. | §8 must name a cheap baseline and write down kill criteria before any Phase 2 work. |
| Systems engineer | Correctness, failure modes | Not yet sound. Stamps don't cover the note's own text, reads write to the lock file, and `verified_at` records the wrong commit in the normal commit flow. | Fail closed: `fresh` only when positively verified. |
| Agent's advocate | Agents as the users | The hashing is sound, but the agent-facing layer misread its key evidence and pushes judgment calls onto agents, who will game them. | The read-time gate delivers the current truth pinned to note lines, not a verdict. |

## Round 1 key points

### Skeptical pragmatist
- **The riskiest assumption is untested:** that notes describing code help agents more than the code itself. In the ETH study, context files written by an LLM *cut* success by about 3% and raised cost by more than 20%. This vault's most valuable notes (decisions, research, logs) aren't hashed at all.
- **The v0.1 experiment was built to pass.** Planted stale notes and a "no gate" baseline make success too easy. The fair baseline is drift in CI plus a one-line CLAUDE.md rule, with notes that go stale naturally by replaying real history.
- **False positives kill tools like this,** and Phase 1's whole-file anchors were the noisiest option. That also contradicted §7, since wrapping drift gives symbol anchors for free.
- **Novelty is thin,** because Kage and OMP already check memory against code on recall. Aim for a measured result plus upstream PRs to drift.
- **Obsidian isn't load-bearing,** since every check runs outside it.
- **Cut list:**
  - seven freshness states down to three;
  - only the `describes` authority;
  - defer the sig/impl split, the LLM judge, move detection, non-code anchors, Bases, the report and the MCP gateway.

### Systems engineer
- **The stamp has no note hash.** A human edit in Obsidian stays `fresh`, and `stamp --verdict update` with no edit clears a stale note.
- **Early cutoff writes the lock file on read.** That dirties the tree, loses stamps between subagents, causes merge conflicts, and can move the baseline past a real change.
- **`verified_at` is wrong in the normal flow.** A commit can't contain its own SHA, so edit, stamp and commit records the parent, marked dirty. After a squash-merge or rebase the SHA may not exist at all.
- **Normalization has gaps:**
  - Python decorators sit outside `function_definition`; Rust `#[cfg]` has the same problem.
  - Meaningful comments get stripped: `# type:`, JSDoc types, `//go:embed`.
  - A flat token stream misses a statement dedented out of an `if`.
  - Formatter churn (trailing commas, quote styles) flips fingerprints across many notes at once.
- **Severity was inverted for `impl` anchors.** A body change was only a soft state, so rewriting the very logic a note documents never failed anything.
- **Other problems:**
  - Auto-move can bind the wrong symbol, e.g. an unrelated `return True`.
  - Stamps keyed by path are orphaned when a note is renamed.
  - The gate fails open: a hook error is silent, Grep, `cat` and `@` mentions bypass it, and `sed -i`, formatters and `git pull` go unseen.
  - Anyone can forge a stamp, and `additionalContext` arrives as a system reminder with repo content in it.

### Agent's advocate
- **§6.7 misread the evidence.** What worked in Meetless was delivering the *correct current value* in a complete, assertive correction. Hedged warnings fail. `drifted`, `unstamped` and `overdue` are exactly such hedges.
- **The maintenance burden invites gaming.** Agents will skip `depends_on`, anchor whole files and write fluent ack reasons. Cheapest of all, they'll make a trivial edit and re-stamp, or retire the note. Over time the pressure is toward vague notes that never go stale.
- **Mixed-authority notes.** A module note with one invariant paragraph can't have a single authority. The draft design note itself was `specifies` while still a draft.
- **The experiment tested the wrong thing.** Agents open the file they're editing, so stale notes hurt in what they *don't* open: navigation, invariants, behaviour across modules.
- **Volume:** 20 edits produce 20 interruptions, `additionalContext` over 10,000 characters is offloaded to a file, and duplicate diffs pile up. Grep is ungated even though [[Start Here]] tells agents to grep.
- **Discovery:** agents arrive from the code, but the vault can only be navigated from the top down.

## Consensus after round 2 (adopted into v0.2)

1. **Phase 1 tests value against cheap baselines, with kill criteria written down in advance.** The arms are no notes; notes plus a CLAUDE.md rule; and notes plus the gate. See [[Live Docs Design#8. Plan]].
2. **Signal quality is measured before any agent trials (1a).** Replay real history, grade the flags, and tag the cause of every miss or false flag.
3. **Use drift's symbol anchors, not whole-file blobs.** Use drift unmodified in Phase 1.
4. **The read-time output delivers was / now facts pinned to the note lines that mention them.** It's capped at 1,500 characters, shows each change once per session, and has no info-level flags. See [[Live Docs Design#6.7 What the agent sees]].
5. **"Code wins" is limited.** It covers what the system *does*, never what it *should* do.
6. **Checks are read-only.** Stamps are append-only and include the note's own hash.
7. **Three states plus `unknown`,** and the check fails closed.
8. **Tasks depend on code the agent won't open.**
9. **Write-time output is batched into one Stop hook,** not one per edit.
10. **Hardening is deferred** (see [[Live Docs Design#11. Deferred until Phase 1 passes]]).

## Disagreements resolved in round 2

- **Line verdicts vs. facts only → facts only (engineer).** Mapping code changes onto a note's prose claims is the hard problem that DocPrism and READU struggle with. A wrong mapping delivered as a correction does more harm than a banner. The tool says "L14 mentions `rotate`; was X, now Y", and never "L14 is wrong".
- **The advocate's large test matrix (5 arms × 7 task types × 10 trials × 3 models) → too big for Phase 1** (pragmatist and engineer). The core stays at three arms; the extensions are contested (below).
- **The engineer's production hardening → deferred** (pragmatist). The engineer agreed, keeping only these for Phase 1: fail closed, logging of bypasses, a read-only check, cause tags and the diff base.
- **Failing CI on any body change → not until 1a measures precision** (advocate).
- **Withholding `broken` notes → serve with a tombstone header** (advocate). Withholding blocks the agent sent to fix the note.
- **Diff base → `git log -S<sig> -- drift.lock`** (engineer). The pragmatist withdrew `git log -L`, which breaks under squash-merge and rebase.
- **Anchors derived from mentions become the default,** but a note with zero anchors is `unknown` (unbound), never `fresh` (engineer). Claims made only in prose have no mentions to anchor.
- **1a grading must be done by a human or against a tight rubric** (engineer). An open-ended LLM flags over 90% of notes (DocPrism), which would fake the precision number.

## Still contested (needs the user)

1. **`specifies` notes:** the pragmatist would cut them. The advocate would keep them for *routing only*: put an invariant in front of any agent touching the code it governs, with no conformance checking or escalation.
2. **Phase 1 size:** the advocate wants to add arm D (show notes when an agent reads a source file they're anchored to) plus about 5 invariant tasks with hidden tests. The pragmatist and engineer want to stay at 3 arms and about 12 tasks.
3. **Obsidian's role:** the pragmatist, with the engineer agreeing, says it's an optional viewer. The user's decision D1 frames the idea around Obsidian.
4. **The threshold to continue:**
   - The pragmatist wants C to beat B by at least 15 points.
   - The advocate would accept 10 points, or invariant violations halved.
   - The advocate also warns that small task counts can't resolve a 10-point difference.

## Evidence correction

v0.1 said the Meetless benchmark showed that "stating which source takes precedence" fixed stale-context behaviour. **The orchestrating agent re-checked the source on 2026-09-21.** The page is labelled "DRAFT Preliminary".
- **What worked** was complete, assertive correction ("X was stated, Y is in force, Y wins"): 6/6 on Opus 4.8 and Haiku 4.5, and 5.67/6 on Opus 5.
- **What failed on some models:**
  - Naming both values without saying which wins: 0/6 on Opus 4.8 and Haiku 4.5.
  - Hedged framing ("may be unverified"): 0/6 on Opus 4.8 and Opus 5.
- **In the baseline arm,** agents read zero files, on all 10 models.

The advocate also reported that a correction covering only some facts fixed only those facts. The re-check didn't confirm or rule this out. [[Evidence - Agents and Stale Context]] has been updated.

## Questions for the user

These are merged from all three critics and appear in [[Live Docs Design#9. Open questions]].
