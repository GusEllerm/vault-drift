---
type: research
status: active
authority: reference
summary: "Why the problem matters: how common stale docs are, and evidence that LLM agents trust stale context and outdated API knowledge."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, research, evidence]
---

# Evidence - Agents and Stale Context

> **Provenance.** Research subagents gathered this by web search on 2026-09-21. Figures are as reported by the cited sources and haven't been independently re-checked. Items marked *preliminary* come from drafts or non-peer-reviewed work.

## Stale documentation is common

- **Tan, Wagner & Treude, "Detecting outdated code element references in software repository documentation"** (Empirical Software Engineering 2023; ICSE 2024 journal-first). Covers the top-1000 GitHub repos. https://arxiv.org/abs/2212.01479
  - Currently outdated: 28.9% of projects, 19.2% of documents and 3.9% of references.
  - 82.3% of projects had outdated references at some point in their history.
  - Outdated references went unfixed for 4.7 years on average. A new one has about a 55% chance of surviving past one month.
  - How they were eventually fixed: 47.6% by changing the code, 39.1% by editing the doc and 13.3% by deleting the doc. **Drift gets resolved in both directions.**
  - The authors filed 19 reports in 15 projects. 5 were fixed, and maintainers in 4 projects called theirs false positives.
- **Radmanesh et al. (2024):** changes that leave comments inconsistent with the code are about 1.5× more likely to introduce bugs, and the effect is strongest right after the change. https://arxiv.org/abs/2409.10781

## Agents trust stale context

- **STALE (May 2026):** the best model scored only 55.2% at acting correctly on memories that later observations had silently invalidated. https://arxiv.org/abs/2605.06527
- **Meetless stale-context benchmark (July 2026, labelled "DRAFT Preliminary").** https://research.meetless.ai/stale-context/
  - **Setup:** a fixture of 6 facts in a prose task, 10 models from 3 vendors, 3 trials each.
  - **Baseline:** agents given a confident but outdated summary read **zero files**, on every model.
  - **What worked:** only a *complete, assertive correction* ("X was stated, Y is in force, Y wins") held across models: 6/6 on Opus 4.8 and Haiku 4.5, and 5.67/6 on Opus 5.
  - **What failed on some models:**
    - Naming both values without saying which wins: 0/6 on Opus 4.8 and Haiku 4.5.
    - Hedged framing ("may be unverified"): 0/6 on Opus 4.8 and Opus 5.
  - **A "verify" instruction was unpredictable:** agents read anywhere from 0 to 6 files depending on the model.
  - *Correction, 2026-09-21:* an earlier version of this note said stating "which source takes precedence" was the fix. That was a misreading, caught in [[2026-09-21 Design Review]] and re-checked against the source. The fix is delivering the value in force.
- **ClashEval (NeurIPS 2024):** models adopt incorrect retrieved content more than 60% of the time. https://arxiv.org/abs/2404.10198
- **Chroma, "Context Rot" (2025):** all 18 models tested got worse as input length grew. This argues against loading the whole vault into context. https://www.trychroma.com/research/context-rot

## Context files for coding agents

- **ETH, "Evaluating AGENTS.md" (Feb 2026):** context files written by an LLM cut task success by about 3% and raised cost by more than 20%. Files written by developers gave a small gain that wasn't statistically significant. https://arxiv.org/abs/2602.11988
- **Agent READMEs study (Nov 2025, 2,303 files):** 59–67% of the files are edited repeatedly, which the authors call "context debt". https://arxiv.org/abs/2511.12884
- **Codified Context (Feb 2026):** outdated specs were the main failure mode. The author built a session-start hook that compares recent commits against a map of subsystems to files. https://arxiv.org/html/2602.20478v1

## Outdated API knowledge

- **"When LLMs Lag Behind" (Apr 2026):** only 42.6% of generated code for updated APIs executed, rising to 66.4% when structured docs were provided. https://arxiv.org/abs/2604.09515
- **CodeUpdateArena (2024):** putting documentation of the API update into the prompt did not let open code models use the new API. https://arxiv.org/abs/2407.06249
- **VersiCode (2024):** GPT-4o scored more than 50 points lower on version-specific code completion. https://arxiv.org/abs/2406.07411
- **LibEvolutionEval (NAACL 2025):** deprecated APIs are the hardest case, and retrieving the docs for the right version closes much of the gap. https://arxiv.org/abs/2412.04478
- **GitChameleon 2.0:** the top models score 48–51%. https://arxiv.org/abs/2507.12367
- **Deprecated API usage (ICSE 2025):** models frequently suggest deprecated APIs. https://arxiv.org/abs/2406.09834

## What this means for the design

- **The check must be mechanical.** Telling agents to verify isn't enough (STALE, Meetless). See [[Live Docs Design#6.6 Where checks run, and the coverage of the guarantee]].
- **Deliver the correction, not a warning.** Give the old value, the value in force, and which one wins. See [[Live Docs Design#6.7 What the agent sees]].
- **Notes themselves can hurt** (ETH: context files written by an LLM cut success). Their value has to be measured against baselines. See [[Live Docs Design#8. Plan]].
- **Serve notes on demand,** with summaries for triage, rather than loading the whole vault into context (Context Rot).
- **Package-version anchors** target the outdated-API failures. See [[Live Docs Design#6.12 Beyond code]].
- **Drift gets fixed in both directions** (47.6% of fixes changed the code). Since v0.3 scopes Live Docs to code documentation, this is why the read-time rule is limited to what the system *does*, never what it *should* do. See [[Live Docs Design#6.2 What gets checked]].
