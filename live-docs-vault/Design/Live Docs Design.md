---
type: design
status: draft
authority: specifies
summary: "Draft v0.3: a guarantee that an agent reading a note about code is told when that code has changed since the note was verified. Phase 1 measures whether the guarantee holds on a real repo."
created: 2026-09-21
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, design]
---

# Live Docs Design

> **Status: draft v0.3, 2026-09-22.** v0.2 was revised after [[2026-09-21 Design Review]]; v0.3 applies the user's answers to the contested points (D4–D8 in [[Decision Log]]). The remaining proposals (P10–P18) are still unreviewed by the user.
> - Because this note is a draft, it doesn't bind anything yet ([[Vault Conventions]]).

## 1. Summary

Agents working on a codebase over many sessions need memory that outlives any single session. Markdown notes in a repo, browsed through Obsidian, suit this well. The trouble is that notes describing code go stale silently as the code changes, and agents act on them anyway.

**What Live Docs provides is a guarantee** (the user's requirement, D5): *an agent reading a note about code is told whether that code has changed since the note was last verified.* Not a warning it may ignore, but the current facts pinned to the lines of the note that mention them:
- what the code was when the note was verified;
- what it is now;
- that the code is authoritative about what the system does.

The mechanism is narrow on purpose. It covers **documentation of code only** (D4). Decisions, specs and invariants are a different system and out of scope.

The guarantee has two conditions, stated up front so nobody mistakes it for more than it is:
1. **It covers reads that go through the gate.** A read that bypasses the gate (§6.6) gets no guarantee. Phase 1 measures how often that happens.
2. **It covers claims that mention code.** A prose claim with no code mention has nothing to fingerprint. Such notes are reported `unknown`, never `fresh`.

Within those conditions the check **fails closed**: a note is `fresh` only when positively verified.

Fiberplane drift does the fingerprinting; a thin wrapper adds the read-time gate and note hashes. Phase 1 (§8) measures on a copy of one of the user's real projects whether the guarantee holds, with kill criteria written in advance.

## 2. Problem

- An agent reads a note, trusts it and makes decisions from it. If the code has changed since the note was written, those decisions are wrong.
- The evidence (details in [[Evidence - Agents and Stale Context]]):
  - **Stale docs are common.** 28.9% of the top-1000 GitHub projects currently have docs that reference deleted code, and those references survive 4.7 years on average.
  - **Agents don't catch it themselves.** The best model scored 55% at acting correctly on memories that had been silently invalidated (STALE, 2026).
  - **Agents don't go and check.** In a preliminary 2026 benchmark, agents given a confident but outdated summary opened no source files at all. What reliably fixed this was a *complete, assertive correction*: the old value, the value in force, and which one wins. Hedged warnings failed on some models.
  - **Today's agent memory systems handle staleness with an instruction to "verify", or not at all** ([[Prior Art - Agent Memory Systems]]).
- **Counter-evidence.** Context files written by an LLM reduced agent task success by about 3% and raised cost by more than 20% (ETH, 2026). Notes can hurt. The user's position (D5) is that they will have notes regardless; the question this project answers is whether agents can be told when those notes are out of date.

## 3. Goals and non-goals

**Goals**
- G1 **(primary). The guarantee:** an agent never receives a code-dependent note marked `fresh` unless the checker positively verified it, and a `changed` note comes with the current facts. The check fails closed.
- G2. **Correction, not warning:** was / now for the code the note mentions, pinned to the note's lines (§6.7).
- G3. **Precision:** false alarms are rare enough that agents and humans don't learn to ignore them. Measured in Phase 1a.
- G4. **Coverage is known:** Phase 1 reports how often reads bypass the gate, so the guarantee's first condition is quantified rather than assumed.
- G5. The vault stays plain markdown in the repo, with Obsidian as the human interface (D6).

**Non-goals**
- **Decisions, specs, invariants** (D4). A hash can't check that code conforms to a spec, and routing invariants to agents is a different system.
- **Proving a note is correct.** A matching fingerprint only shows the code hasn't changed since someone vouched for the note.
- **Generating documentation.**
- **Tamper-proof stamps.** The threat model is agents that cooperate but take shortcuts.
- **Replacing tests, types or code comments.**

## 4. Concepts

| Term | Meaning |
|---|---|
| Vault | Markdown notes inside the repo they document, browsed in Obsidian (§6.10). |
| Code note | A note that mentions code. Only code notes are checked. |
| Anchor | A code symbol the note mentions, in drift's syntax, e.g. `src/auth/session.py#SessionManager.refresh`. Derived from the note's code mentions by default (§6.3). |
| Fingerprint | drift's hash of a symbol's normalized syntax tree (§6.4). |
| Stamp | An append-only record that a note was verified: the note's own hash plus the fingerprint of each anchor at that moment (§6.3). |
| Diff base | The code as it was when stamped, found through the git history of `drift.lock` (§6.4). |
| Freshness | `fresh`, `changed`, `broken` or `unknown` (§6.5). |

## 5. Prior art and positioning

The short version is below; the research notes have the details.
- **Fiberplane drift** (MIT license, March 2026) uses the same core mechanism:
  - It anchors to `path#Symbol` and fingerprints the parsed syntax tree (tree-sitter).
  - Fingerprints live in a `drift.lock` file.
  - `drift check` runs in CI, and `drift refs` lists which docs point at a file.
  - It ships a skill for Claude Code and Codex.
  - It has no read-time check and no note hash. Phase 1 uses it unmodified (§7).
- **Swimm Auto-sync** (commercial) stores a copy of the referenced code and uses git history. That lets it fix moves and renames automatically.
- **GitHub Copilot Memory** gives each memory citations to code and checks them against the current branch before use. The check is the model's judgment, not a hash.
- **Kage, ctx-memory, OMP and true-memory-fragments** already check memories against code when they're recalled. They are tiny and unadopted.
- **What is different here:** a read-time gate that delivers corrections rather than warnings, freshness that fails closed, and a measured answer to whether the guarantee holds on a real repo. The contribution worth aiming for is that measurement plus upstream fixes to drift; a new tool isn't the default.

## 6. Design

### 6.1 Components (Phase 1)

```
  repo ─┬─ src/ …
        ├─ drift.lock                     (drift: anchors + fingerprints)
        └─ vault/
            ├─ notes (.md, flat frontmatter)
            └─ .livedocs/stamps.jsonl     (append-only: note hash + binding sigs)

  livedocs (thin wrapper over drift; checks never write)
    stamp · check · affected

  git hooks
    pre-commit                          → block on changed/broken notes in the index (§6.6)
  Claude Code hooks
    PostToolUse on Read of vault paths  → read-time gate (§6.7)
    Stop                                → non-blocking heads-up: notes affected by this task (§6.6)
    logging of Grep/Bash reads of vault paths → bypass rate
```

1. **drift, unmodified:** anchors, fingerprints, `drift.lock`, `drift check` and `drift refs`.
2. **The livedocs wrapper:**
   - `livedocs stamp <note>`: derives anchors from the note's mentions, runs `drift link`, and appends a stamp holding the note's hash.
   - `livedocs check <note>`: read-only. Returns freshness plus was / now excerpts.
   - `livedocs affected`: runs `drift refs` over `git diff --name-only`.
3. **Claude Code hooks,** as listed above.
4. **Vault conventions:** flat frontmatter ([[Vault Conventions]]).

Everything else is deferred (§11): CI gating, an MCP gateway, reports, Bases views and non-code anchors.

### 6.2 What gets checked

- **Only code notes are checked:** notes that mention code and therefore have anchors. This is a property of the note's content, not a declared kind.
- **Notes without code mentions are never `fresh`.** They are reported `unknown` with the reason `unbound`. A `reviewed` date in frontmatter is the only freshness signal for them, and it isn't shown at read time.
- **Authority is gone from the mechanism** (D4). v0.1–v0.2 had `describes` / `specifies` / `log` / `reference`. The mechanism now has one rule, stated to the agent at read time: **the code decides what the system *does*.** Whether the system *should* do that is out of scope, so an agent must never treat a `changed` note as licence to rewrite a design intent to match the code. (This vault's own notes still carry an `authority` property; that's a convention for how agents treat *this* vault, not something the mechanism reads.)

### 6.3 Declaring dependencies

- **Anchors are derived, not declared.**
  - At stamp time, `livedocs stamp` extracts code mentions from the note (backtick spans, paths, identifiers).
  - It resolves them to symbols and binds each one with drift.
  - The agent prunes the list rather than writing it.
- **`depends_on` in frontmatter is an optional override** that adds or excludes anchors. It's a flat list of quoted strings in drift's syntax, e.g. `"src/auth/session.py#SessionManager.refresh"`.
- **A note with zero anchors is `unbound`,** reported as `unknown` and never as `fresh` (guarantee condition 2).
- **Anchor syntax follows drift.** The checker can tell signature changes from body changes itself, so there is no aspect suffix.
- **Where stamps are stored:**
  - `drift.lock` holds bindings and fingerprints, in drift's format.
  - livedocs adds `.livedocs/stamps.jsonl`, which Obsidian hides, with one line per stamp.
  - Stamps are append-only and never edited:

```json
{"note": "Modules/Auth Session.md", "note_hash": "3b1f…", "bindings": {"src/auth/tokens.py#rotate": "e4f8a2c10b3d7890"}, "stamped": "2026-09-21T14:30:00Z", "by": "claude-code:<session-id>", "verdict": "update", "reason": ""}
```

### 6.4 Fingerprints and diffs

- **Phase 1 uses drift's fingerprints unmodified:** a tree-sitter syntax tree reduced to node kinds and token text, with no whitespace or positions. It covers six languages and falls back to raw content for the rest.
- **Known gaps: measure them in Phase 1a, don't fix them.** Tag each miss and false flag with its cause:
  - Python decorators sit outside `function_definition` (in `decorated_definition`), so a changed decorator may be missed. Rust `#[cfg]` has the same problem. Report it upstream if confirmed.
  - Meaningful comments are stripped: `# type:`, JSDoc types under `@ts-check`, `//go:embed`.
  - A flat token stream may not notice a statement dedented out of an `if`.
  - Formatter churn (trailing commas, quote styles) may flip fingerprints across many notes at once.
  - *Unverified:* whether drift hashes the outermost node and preserves nesting. Check this in Phase 1.
- **Any change to an anchored symbol makes the note `changed`.** The diff metadata shows whether the signature changed or only the body. "Technically out of date" (D5) means exactly this: an anchored symbol's fingerprint differs from the stamp.
- **The diff base is the commit that last wrote the binding:** `git log -S<sig> -- drift.lock`.
  - That commit contains the code as it was stamped, and it survives squash-merges.
  - A commit can't record its own SHA, so a stored `verified_at` would always have pointed at the parent commit instead.
  - Limitation: a stamp that hasn't been committed yet has no diff base, so only the current code is shown.
- **Checks never write.** Updating stamps during reads would dirty the tree, lose stamps between subagents, and could move the baseline past a real change. Any caching goes in a gitignored file.
- **Moves and renames** are offered as suggestions only, never re-bound automatically. A trivial body like `return True` can match an unrelated symbol. Deferred.
- **Don't fold dependencies' hashes into a symbol's hash** the way Unison does, or one edit deep in the call graph marks half the vault stale.

### 6.5 Freshness states

| State | Meaning |
|---|---|
| `fresh` | The note's hash matches a stamp, and every anchor's current fingerprint matches that same stamp. Positively verified. |
| `changed` | At least one anchored symbol changed since the stamp. Comes with was / now excerpts. |
| `broken` | An anchored symbol or file no longer resolves. |
| `unknown` | The checker couldn't verify the note. It always gives a reason (listed below). |

`unknown` reasons:
- the note was edited since its last stamp;
- the note was never stamped;
- it has zero anchors (`unbound`);
- a symbol is ambiguous (overloads, trait impls) — never pick the first match;
- a file doesn't parse;
- the hook errored or timed out.

- **Order, worst first:** `broken` > `changed` > `unknown` > `fresh`. A note takes the worst state across its anchors.
- **Fail closed:** anything short of positive verification is `unknown`, never `fresh`. A false `fresh` is the one failure that makes the system worse than having none, because agents trust a checked note more than an unchecked one.
- **Which tree is checked:** at read time, the working tree. In the Stop hook, the working tree against `HEAD`. In pre-commit, the index. In CI, the commit.

### 6.6 Where checks run, and the coverage of the guarantee

**Read time.** A Claude Code `PostToolUse` hook on `Read` of vault paths runs `livedocs check`, which is read-only.
- The output goes through `additionalContext` in the §6.7 format.
- If the hook errors or times out, it emits `unknown`, never silence.

**Bypasses, and what to do about them.** `Grep`, `Bash` (`cat`, `sed`, `grep`), `@` mentions and CLAUDE.md imports don't go through `Read`. A guarantee with unmeasured holes isn't one, so:
- **Phase 1 logs** every Grep and Bash access to vault paths and reports a bypass rate.
- **If the rate is material** (proposed: above 5% of vault reads), Phase 2 closes the holes in order of cost:
  1. a `PreToolUse` hook on `Bash` that denies reads of vault paths with a message pointing at `Read` (cheap, Claude Code only);
  2. tagging `Grep` hits in vault paths with their state;
  3. an MCP gateway as the only sanctioned way into the vault (portable, but agents can still go around it unless Bash is restricted).
- [[Start Here]] currently tells agents to grep summaries. Accept that for Phase 1 and measure it; summaries are frontmatter, not code claims.

**Tiers (D14, 2026-09-23).** The guarantee is a mechanism of the development framework: Tier 0 is the versioned git gate plus CI, always; Tier 1 is the harness's end-of-turn heads-up, recommended; Tier 2 is the read gate, opt-in; Tier 3 is measurement only. Under block-at-commit a committed note is always vouched for, so the read gate only ever has work on uncommitted changes and unstamped vaults. The failed commit's own output is the channel every harness has.

**Write time: block at commit (D11).** The commit is the collection point.
- **Pre-commit hook.** Compares the *staged* blobs, not the working tree: a note fixed but unstaged doesn't count as fixed, and an unstaged code change doesn't flag. Every `changed` or `broken` note in the staged tree must be updated or acked (§6.8) before the commit goes through. `unknown` never blocks, or every new note would block its own first commit.
- **Why commit:** it's harness-agnostic (fires for any agent or human); acks land in the diff next to the code change, so rubber-stamping is visible in review; batching is natural; and in this workflow the human is the one who says "commit", so they're present for the reconciliation.
- **The invariant it buys:** every commit's notes are vouched for against that commit's code. The diff base for a note is therefore always the last commit that touched its stamp, always resolvable, and a read-time `changed` means exactly "the working tree has moved since the last commit that vouched for this note".
- **Stop hook: non-blocking heads-up.** At the end of the agent's task it runs `livedocs affected` on `git diff --name-only` and lists the notes whose anchors changed, so nothing is a surprise at commit time. It also catches `sed -i`, formatters and `git pull`, which an `Edit|Write` matcher misses. One hook per edit would give a 20-edit refactor 20 interruptions.
- **CI backstop.** `livedocs check` runs in CI to catch `--no-verify`, merge commits and rebases, which pre-commit doesn't cover. (In Phase 1 the testbench has no CI; the replay harness plays that role.)
- **Debt in uncommitted sessions** is a debt problem, not a safety problem: the read gate still delivers corrections against the working tree.

**Phase 1 exception.** 1a is list-only, so it measures what agents do unprompted. 1b includes commit tasks and measures reconciliation under block-at-commit: update vs. ack vs. `--no-verify`, with ack reasons graded from the testbench history.

### 6.7 What the agent sees

**Evidence** (Meetless, preliminary): complete, assertive correction ("X was stated, Y is in force, Y wins") worked on every model tested. Hedged framing, or naming both values without saying which wins, failed on some models. In the baseline arm, agents read zero files. So the gate delivers corrections about *code facts*, which the tool knows exactly.

**Rules:**
- **Facts only, pinned to note lines,** e.g. "L14 mentions `rotate`; the signature was X and is now Y". The tool never says a note line is *wrong*.
  - Mapping code changes onto prose claims is the hard problem (DocPrism, READU).
  - A wrong mapping delivered as a correction does more harm than a banner.
- **The code decides what the system does,** not what it should do.
- **Show each change once per session.** Later notes that share it get a single line.
- **Stay under 1,500 characters per note.** Claude Code offloads `additionalContext` over 10,000 characters to a file and shows only a preview.
- **No info-level flags at read time,** e.g. overdue reviews or style lints.
- **`broken`:** serve the note with a tombstone header. Don't withhold it; that would block the agent sent to fix it.
- **`unknown`:** one line giving the reason.

Example:
```
LIVE-DOCS: "Auth Session" CHANGED since last verified (stamp 2026-09-21).
The code decides what the system does; where this note disagrees about that, the code is right.
src/auth/tokens.py#rotate: signature changed
  was: rotate(token, ttl)
  now: rotate(token, *, ttl: int, reason: str) -> Token
Note lines that mention rotate: L14, L22.
Other anchors in this note are unchanged.
Not your task? Leave it; the Stop hook will list it. To re-verify: livedocs stamp "Auth Session"
```
A second note affected by the same change gets: `LIVE-DOCS: "Token Lifecycle" CHANGED: same rotate() change as above; mentioned at L8.`

**Trust caveat:** `additionalContext` arrives as a system reminder, which carries more weight than ordinary tool output, and here it carries repo content. Phase 1 keeps it to this fixed template. Moving the excerpts into tool output is deferred (§11).

### 6.8 Reconciliation

- **`update`:** edit the note, then run `livedocs stamp`. The stamp records the new note hash. **Re-stamping a `changed` note without editing it is not an update;** it needs `--ack`.
- **`ack`:** the text is still accurate. Run `livedocs stamp --ack --reason "…"`.
- **`retire`:** only for `broken` notes, or with the user's sign-off. Retiring is the cheapest way to silence a warning.
- **Measure gaming before policing it.** Phase 1 logs:
  - stamps, acks and retires;
  - updates that remove code mentions, which make a note vaguer so it never goes stale.

  An LLM judge is deferred until the logs show gaming worth the cost.
- **Stamps are a set.** A note is `fresh` if *any* stamp matches its current hash and all its current fingerprints. Reverting to a stamped state therefore makes the note fresh again.

### 6.9 Catching undeclared dependencies

- **Mostly handled by derived anchors (§6.3):** a note is bound to whatever code it mentions, and a note with no mentions is `unknown`.
- **Remaining gap:** claims made only in prose (guarantee condition 2). Phase 1a's unflagged sample measures how often such claims go wrong without a flag.
- **Deferred:** a lint for mentions that no longer resolve anywhere (the dangling-reference check from Tan et al.).

### 6.10 Vault placement, branches and concurrency

- **The vault lives inside the repo it documents,** as plain markdown (D6). Notes and stamps branch and merge along with the code.
- **Commit the vault,** but ignore `.obsidian/workspace.json` and other per-machine UI state.
- **Obsidian caveats:** don't nest vaults. obsidian-git misbehaves when the vault is a subfolder of the repo (issue #1172, still open as of 2026-09-05).
- **Concurrency:** the last write to disk wins. Appends to `stamps.jsonl` from two branches can conflict. git's `merge=union` driver is deferred, because Phase 1 is a single-branch replay.

### 6.11 Obsidian as the interface

Obsidian is how the user browses and edits the notes (D6); nothing in the mechanism depends on it, and every check runs outside the app. Constraints respected so the vault stays pleasant in Obsidian:
- Keep frontmatter flat; Obsidian can't display nested YAML and rewrites the block when properties are edited.
- Keep machine data in the hidden `.livedocs/` folder.
- Quote hashes.
- **Renaming a note in Obsidian orphans stamps keyed by path.** A stable `livedocs_id` is deferred, and Phase 1 avoids renames.
- **Editing a note in Obsidian changes its hash,** so the note becomes `unknown` (edited since stamp) until re-stamped. That is the guarantee working as intended, not a bug; the read-time line says so.

### 6.12 Beyond code

Out of scope for now (D4). Other anchor types (package versions, other notes, external docs) remain plausible extensions once the code guarantee is proven.

## 7. Build vs. adopt

- **Phase 1:** drift unmodified plus the thin livedocs wrapper.
- **If Phase 1 passes, go upstream first.** Report the fingerprint gaps (decorators and the others in §6.4), and propose read-time and note-hash features to drift.
- **Fork or build our own** only if drift can't take those changes.

## 8. Plan

### Phase 1: does the guarantee hold?

**Testbench (D8, D9).** A detached clone of **hpc-bridge** at `testbench/hpc-bridge` (gitignored; origin removed). Why it fits: 324 commits (2026-05-30 → 2026-09-22), 189 Python files under `src/hpc_bridge/`, and a vault at `docs/hpc-bridge-vault/` whose `Modules/` folder (27 notes: `server.md`, `facility-remote.md`, `login.md`, …) describes code by symbol name, e.g. `_connect_facility`, `SshTarget.preauth_command()`, `config._control_settings()`. Several notes even carry line-number hints (`:1115`) with the caveat "exact line numbers drift — grep the symbol": the author already knows the problem.

**Setup**
- **N = the commit that created the vault** (`0ff0646`, 2026-06-25). The vault didn't exist at tip−200, so the window is N → tip, about 249 commits, over which the vault grew from its first notes to 70.
- Check out N. For every note that mentions code, run `livedocs stamp` (anchors derived from mentions, §6.3).
- **Real note edits are re-stamps (P22).** When the replay reaches a commit that edits a note, treat that as the author verifying it: re-stamp against the code at that commit. Between edits, the check runs against the note as last stamped. This yields two datasets for free: flags between edits (1a proper), and the author's own edits (which changes did a human think warranted updating the note?).
- A read-only `Read` hook serves the §6.7 output. It fails closed and logs bypasses.

**1a. Signal quality (primary; no agents).** This is the test of the guarantee.
- Replay commits N → tip, running `livedocs check` at each commit.
- Grade every flag, plus a random sample of unflagged notes, on one question: *is the note now wrong about the code?*
- **Grading (D10):** an agent applies a written rubric to everything ("for each code mention in the note, does the claim still hold at this commit?"); the user grades every miss and 25 random flag verdicts, 25 more if agreement is below 85%.
- Tag each false flag and each miss with its cause: a §6.4 gap, formatter churn, or a claim made only in prose.
- **Kill criteria** (strict, per D7):
  - **Misses:** more than 10% of notes that became wrong were never flagged, *excluding* prose-only claims (condition 2). Report the prose-only miss rate separately; it bounds what the guarantee can ever cover.
  - **Precision:** fewer than 50% of flags are real.
  - **Bypass:** above 25% of vault reads in 1b went around the gate with no cheap fix available.
- Below those thresholds but above 30% miss or 30% precision, fix the tagged causes and re-run before deciding.

**1b. Behaviour (secondary; agent trials).** Does the correction change what agents do?
- **Tasks:** about 12 tasks at the tip that depend on code the agent won't open. Examples:
  - navigation;
  - behaviour across modules;
  - a call site after a signature change;
  - a config file that moved.
- **Notes go stale naturally** from the replayed history.
- **At least one false-alarm probe:** an accurate note that gets flagged.
- **Runs:** 2 models × 5 runs per arm, compared task by task.
- **Arms:**
  - **A:** no notes.
  - **B:** notes plus a CLAUDE.md rule: "Notes may be stale; the code decides what the system does."
  - **C:** notes plus the read-time gate.
- **Metrics:** pass rate; how often stale claims are adopted; how often correct information is discarded after the false alarm; bypass rate; tokens per task; stamp, ack and retire behaviour.
- **Decision rules (D7, strict):**
  - **1b does not kill the guarantee.** If 1a passes, the gate ships as the minimal guarantee regardless.
  - **Phase 2 investment** (closing bypasses, upstream work, reconciliation tooling) proceeds only if C beats B by at least 15 points of pass rate *and* fewer than 20% of runs discard correct information after the false alarm.
  - **If A does at least as well as C,** report it plainly: the notes in this vault aren't helping, and the user should know before writing more.

### Phase 2 and later (only if Phase 1 passes)

Work through §11, in the order that Phase 1's cause tags and logs show matters most. Closing bypasses (§6.6) comes first if the bypass rate was material.

## 9. Open questions

**For the user:**
1. **Would you rather contribute to drift or own a tool,** if Phase 1 passes?

**Resolved 2026-09-22:** testbench = hpc-bridge, detached clone (D9). Grading: agent by rubric, user grades every miss + 25 calibration flags (D10). Write-time posture: block at commit; Stop hook is a non-blocking heads-up (D11).

**Technical** (agents can settle these later):
- The merge strategy for `stamps.jsonl` across branches.
- How class-level anchors and docstrings are treated, with one rule for every language.
- Parsing scoped paths like `packages/@scope/x.ts#f`: split on the rightmost `#`.

**Resolved on 2026-09-22** (see [[Decision Log]] D4–D8): code documentation only; the guarantee is the product; markdown in the repo with Obsidian as interface; testbench is a copy of a real project; strict thresholds.

## 10. Risks

| Risk | Mitigation |
|---|---|
| A false `fresh` (worse than no system) | Fail closed: `unknown` unless positively verified |
| Misses: notes that are wrong but never flagged | 1a measures the miss rate with human grading; kill above 10% |
| Prose-only claims can't be covered | Reported separately in 1a; `unbound` notes are never `fresh` |
| Reads bypass the gate (Grep, `cat`) | Measured in 1b; Phase 2 closes holes in cost order (§6.6) |
| False alarms get ignored | 1a precision with cause tags; kill below 50% |
| A wrong line mapping delivered as a correction | Facts only; the tool never says a line is wrong |
| Notes describing code don't help at all | 1b arm A; reported plainly, doesn't block the guarantee |
| Gaming: acks, trivial updates, retires, vaguer notes | Note hash in stamps; restricted retire; log and measure before building a judge |
| Grading bias inflates 1a | Human grades all misses and a calibration sample |
| Design intent rewritten to match code | "Code wins" limited to what the system does |
| Renaming a note in Obsidian orphans its stamps | Deferred `livedocs_id`; Phase 1 avoids renames |

## 11. Deferred until Phase 1 passes

| Item | Raised by | Why it waits |
|---|---|---|
| Closing read bypasses: Bash deny, Grep tagging, MCP gateway | engineer, advocate | Phase 1 measures the rate first |
| A normalization spec per language, with golden tests and `fp_version` | engineer | drift's job first; 1a measures the gaps |
| Append-only stamps with `merge=union`, stable `livedocs_id`, `livedocs gc` | engineer | Phase 1 is a single-branch replay |
| Tamper resistance: deny agent writes to `.livedocs/**`; CI recomputes stamps | engineer | the threat model assumes cooperative agents |
| Moving excerpts out of the system-reminder channel into tool output | engineer | Phase 1 uses a fixed template |
| Move and rename suggestions | engineer | not needed to answer Phase 1 |
| An LLM judge for acks and updates | advocate | measure gaming first |
| CI gate, freshness report, Bases view | v0.1 | not needed to answer Phase 1 |
| Lint for dangling mentions | v0.1 | anchors are derived for now |
| Non-code anchors: packages, notes, URLs | v0.1 | out of scope until the code guarantee is proven |
| Generated session-log skeletons; an auto-maintained Start Here map | advocate | vault ergonomics, not the core question |
| A lint for heading links | advocate | cheap; can be done at any time |

**Cut, not deferred (D4):** `specifies` notes and invariant routing; per-section `[!spec]` callouts; arm D and invariant tasks. These belong to a different system.

## 12. References

- Design review: [[2026-09-21 Design Review]].
- Sources: [[Evidence - Agents and Stale Context]], [[Prior Art - Code-Coupled Documentation]], [[Prior Art - Agent Memory Systems]] and [[Obsidian Platform Constraints]].

## Changelog

- **v0.3 (2026-09-22):** the user's answers to the contested points.
  - Scope narrowed to documentation of code; authority removed from the mechanism.
  - Reframed around the guarantee, with its two conditions stated. 1a (signal quality) is now primary; 1b (behaviour) is secondary and no longer a kill criterion for the guarantee.
  - Stricter thresholds: 10% misses, 50% precision, 15 points for Phase 2 investment.
  - Testbench: a detached copy of one of the user's projects and its vault.
  - Bypass handling given a concrete escalation path.
  - Grading method proposed (§9 Q2).
- **v0.2 (2026-09-21):** revised after [[2026-09-21 Design Review]].
  - Phase 1 rebuilt around baselines and kill criteria.
  - The read-time output delivers was / now facts, after re-reading the evidence.
  - Freshness cut to four states, failing closed.
  - Checks are read-only, and stamps include the note hash.
  - Anchors are derived from mentions, and the diff base comes from the history of `drift.lock`.
  - Deferred: the sig/impl split, the LLM judge, early cutoff, move detection, non-code anchors and most hardening.
- **v0.1 (2026-09-21):** first draft.
