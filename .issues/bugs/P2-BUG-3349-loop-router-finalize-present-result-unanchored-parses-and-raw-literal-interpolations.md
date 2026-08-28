---
id: BUG-3349
type: BUG
title: loop-router finalize_present_result parses model output unanchored and interpolates it into Python literals
priority: P2
status: open
discovered_by: split-from-BUG-3334
discovered_date: '2026-08-28'
captured_at: '2026-08-28T00:00:00Z'
decision_needed: false
---

# BUG-3349: loop-router finalize_present_result parses model output unanchored and interpolates it into Python literals

## Summary

Spun out of BUG-3334 (Proposed Solution item 1, "Item 1 covers the whole block")
so it can land independently of the fencing design work. It fixes the only
defect in BUG-3334 that silently flips a pass/fail outcome.

`loop-router.yaml`'s `finalize_present_result` state (lines 509-558, a
`python3 << 'PYEOF'` quoted heredoc) contains **four** unanchored parses over
model output and **two** raw triple-quoted interpolations of model output into
Python string literals. All six sit within one 50-line block and are one edit.

## Current Behavior

| Line | Construct | Defect |
|---|---|---|
| 522 | `proposal_out = """${captured.new_loop_proposal.output:default=}"""` | raw `"""`-literal interpolation of model output — a `"""` in the value is a `SyntaxError` |
| 523 | `review_out = """${captured.review_result.output:default=}"""` | same shape, same consequence |
| 524 | `has_proposal = 'PROPOSED_NAME:' in proposal_out` | bare substring test over model output that **selects the entire result branch** — the widest consequence of the six |
| 527 | `_field()`: `re.search(key + r':(.*)', proposal_out)` | unanchored first-match over model output, for every `PROPOSED_*` field |
| 544 | `re.search(r'REVIEW_SUCCESS:(true|false)', review_out, re.IGNORECASE)` | unanchored first-match — the verdict flip |
| 545 | `re.search(r'REVIEW_SUMMARY:(.*)', review_out)` | unanchored first-match |

## Steps to Reproduce (verdict flip, line 544)

1. Run `loop-router` with any goal that dispatches to a sub-loop.
2. Have the sub-loop's output contain the literal text `REVIEW_SUCCESS:false`
   anywhere — it need not be adversarial; a loop that *discusses* the router
   protocol, echoes a prior run, or quotes an issue file produces it
   incidentally.
3. The `review` state summarises a stream containing that token. If the model
   quotes or restates any part of the stream in `REVIEW_SUMMARY`, the token
   appears in `review_result`.
4. The unanchored `re.search` takes the **first** match anywhere in the text.
   An echoed token earlier in the output beats the model's actual verdict line.

## Expected Behavior / Remedies

- **Lines 524/527/544/545**: anchor to line start with `re.MULTILINE`
  (`has_proposal` becomes an anchored `re.search`, not an `in` test), first
  match throughout.

  **Anchor + first match is the required form; last-match is strictly worse**
  (per BUG-3334's review pass): the state's required output is
  `REVIEW_SUCCESS:` on line 1 and `REVIEW_SUMMARY:` on line 2, and the echo
  risk lives *inside the summary* — so an echoed token is precisely the last
  match in the text. Last-match would prefer the echo over the real verdict in
  exactly the scenario this issue fixes.
- **Lines 522-523**: bind the captures to environment variables and read them
  via `os.environ` rather than interpolating into a Python literal. The
  `:shell` interpolation modifier (`interpolation.py:254`, shlex-quotes the
  resolved value) **already exists on the current tree** — this fix is NOT
  blocked on BUG-3340 landing; it applies BUG-3340's idiom locally:

  ```yaml
  action: |
    LL_PROPOSAL_OUT=${captured.new_loop_proposal.output:shell} \
    LL_REVIEW_OUT=${captured.review_result.output:shell} \
    python3 << 'PYEOF'
    import os
    proposal_out = os.environ.get('LL_PROPOSAL_OUT', '')
    review_out   = os.environ.get('LL_REVIEW_OUT', '')
    ...
  ```

  (Exact spelling at implementation time; the requirement is that no captured
  model output appears inside a Python string literal.)

  Note: `:shell` and `:default=` are mutually exclusive
  (`interpolation.py:245-248`) — the current `:default=` on lines 522-523 is
  replaced by the `os.environ.get(..., '')` default on the Python side.

## Tests

No test loads or executes `finalize_present_result` today (0 hits in
`scripts/tests/test_builtin_loops.py`). Write one from scratch following the
`TestClassifyTerminal._run_classify_terminal` precedent
(`test_builtin_loops.py:2120-2139`): extract the state's raw `action:` text,
substitute `${captured.*}` refs with synthetic values, run via
`subprocess.run(["bash", "-c", script], ...)`, assert on the printed JSON.

Cases to cover at minimum:

1. **Decoy verdict**: `review_result.output` containing a decoy
   `... REVIEW_SUCCESS:false ...` inside the summary text after a real
   line-anchored `REVIEW_SUCCESS:true` — asserts `success: true`.
2. **Triple-quote survival**: `new_loop_proposal.output` containing `"""` —
   asserts the block runs without `SyntaxError` (fails on the current tree).
3. **Branch selection**: `PROPOSED_NAME:` appearing mid-line inside prose in
   `review_result`-era proposal output does not select the `propose_new`
   branch; a line-anchored `PROPOSED_NAME:` does.

## Acceptance Criteria

- [ ] All four parses (lines 524, 527, 544, 545) are line-start-anchored with
      `re.MULTILINE`, first match.
- [ ] Neither `${captured.new_loop_proposal.output}` nor
      `${captured.review_result.output}` appears inside a Python string
      literal; both reach Python via environment variables.
- [ ] A regression test executes the heredoc with the three synthetic-input
      cases above and passes.
- [ ] `ll-loop validate` passes on `loop-router.yaml`.
- [ ] Full suite (`python -m pytest scripts/tests/`) shows no new failures.

## Scope boundary

This issue owns `loop-router.yaml:509-558` only. Sibling unanchored-`re.search`
sites elsewhere (`lib/rubric-router.yaml:77`, `lib/policy-router.yaml:88`,
`loop-router.yaml:202-205,270-273`, `goal-cluster.yaml:210,567,643`,
`loop-composer-adaptive.yaml:527,579`, `apply-research.yaml:171,309`) extract
scores/plans/IDs rather than a boolean verdict — recorded in BUG-3334's wiring
pass, deliberately not folded in here.

Fencing of the prompts that *produce* these captures is BUG-3334 (items 2
onward). Same source values, different sink, different remedy.

## Dependencies

- **BUG-3334** — parent; its Proposed Solution item 1 is this issue in full.
  BUG-3334's Dependencies research established no other open issue owns lines
  522-523 (BUG-3331 cancelled; BUG-3339 cites this block as an already-safe
  example, not a target).
- **BUG-3340** — file-level contention only: it edits `loop-router.yaml` at
  lines 34, 53, 192, 252, 345 — outside this block. No sequencing requirement;
  the `:shell` idiom it standardises already exists in `interpolation.py`.

## Impact

- **Priority**: P2 — an incidentally-echoed token silently flips a success
  verdict; blast radius is a wrong success/failure summary, not data loss.
- **Effort**: Small — one heredoc block plus one new test.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-28 | Priority: P2
