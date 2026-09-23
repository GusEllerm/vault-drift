# 1a grading rubric

Each item in `items.md` / `items.jsonl` asks one question about one note at one commit. Answer with a line in
`verdicts.jsonl`:

```json
{"id": "<item id>", "verdict": "wrong" | "still-right", "cause": "<tag>", "by": "agent" | "user", "note": "<optional>"}
```

## The question

**Is any claim the note makes about the code wrong at this commit?**

- Judge only claims *about the code*: what a function takes or returns, what a class holds, what a path is, what
  happens in what order, which names exist. Ignore opinions, plans, history ("we decided on 2026-09-03"), and
  prose that doesn't assert anything checkable.
- Judge against the code as shown (the `was`/`now` excerpts, or the diff). If you need more context, the replay
  branch holds the full tree at that commit; do not guess.
- "Wrong" means an agent following the note would do or believe something the code contradicts. A note that is
  merely incomplete (doesn't mention a new parameter) is **still-right** unless the omission makes a stated claim
  false.
- Line-number hints in notes (`:1115`) are explicitly disclaimed by the vault ("exact line numbers drift"); never
  count them.

## Item kinds

| kind | what happened | `wrong` means |
|---|---|---|
| `episode` | the checker flagged the note (an anchored symbol changed / vanished) | a real catch |
| `at_risk` | the note read FRESH but a file it anchors changed in this commit | a **miss** |
| `pre_edit_fresh` | the author edited the note although it read FRESH, and an anchored file changed | a **miss** |

## Cause tags (one per verdict)

For `episode` + `still-right` (false flag), say why the flag was noise:
- `class-granularity` — the class changed, but not the member the note mentions
- `formatter` — whitespace, quotes, trailing commas
- `comment-only` — comments or docstrings only
- `decorator` — decorator change with no effect on the claim
- `ambiguous-superset` — the anchor bound extra candidates the note wasn't about
- `attribute-guess` — a short field name bound to the wrong class
- `file-anchor` — whole-file anchor; the change was elsewhere in the file
- `moved` — the symbol moved/renamed but the claim still holds
- `other`

For `at_risk` / `pre_edit_fresh` + `wrong` (miss), say why the checker missed it:
- `prose-only-claim` — the claim names no code the checker could anchor (excluded from the miss rate; reported separately)
- `decorator` — a decorator change drift didn't fingerprint
- `unbound-mention` — the note mentions the symbol but resolution failed
- `other`

For `episode` + `wrong` (a real catch) use `real`. For `at_risk`/`pre_edit_fresh` + `still-right` use `ok`.

## Split (D10)

1. An agent grades **every** item against this rubric, `"by": "agent"`.
2. The user grades every item the agent marked as a miss (`at_risk`/`pre_edit_fresh` + `wrong`), plus 25 random
   `episode` items, `"by": "user"`. If user/agent agreement on those 25 is below 85%, the user grades 25 more.
3. `livedocs grade summarize` uses the user's verdict where both exist.
