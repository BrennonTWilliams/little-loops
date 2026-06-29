---
id: BUG-2383
priority: P2
type: BUG
status: done
captured_at: '2026-06-28T19:07:41Z'
completed_at: '2026-06-29T04:09:26Z'
discovered_date: 2026-06-28
discovered_by: capture-issue
relates_to:
- ENH-2356
- ENH-2384
confidence_score: 95
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2383: Tagged-JSON parse states silently swallow malformed JSON, yielding zero results

## Summary

Three built-in loops that parse a tagged `*_JSON:` line from LLM output —
`brainstorm`, `assumption-firewall`, and the `enumerate-and-prove` oracle —
catch `JSONDecodeError`/`ValueError` and immediately `print(0); sys.exit(0)`.
A single malformed line (e.g. the model drops the closing `]` of a long
single-line array) is swallowed silently with exit code 0, so the FSM sees
**success** and routes downstream as if zero results were the legitimate
answer. Diagnosed concretely on `brainstorm-20260628T134036`: the LLM produced
45 strong ideas, every `IDEAS_JSON:` line was missing its trailing `]`, and
`ideas.jsonl` ended up 0 bytes with no log line, no stderr, and no non-zero
exit anywhere in the run.

## Current Behavior

In `scripts/little_loops/loops/brainstorm.yaml` (`dedup_novelty` state,
lines 135-141):

```python
try:
    new_ideas = json.loads(ideas_json_str)
    if not isinstance(new_ideas, list):
        new_ideas = []
except (json.JSONDecodeError, ValueError):
    print(0)
    sys.exit(0)            # ← silent, exit 0; FSM reads this as "0 novel ideas"
```

Because the script exits before the `ideas.jsonl` append and the
`saturation.txt` write, **no ideas are persisted and saturation never
increments**. The run proceeds through `cluster → rank → converge`, which
honestly emit "0 ideas" stubs. The only externally visible signal is empty
output — there is no test, assertion, or log line that catches this.

The same swallow-and-exit-0 pattern is duplicated in:
- `scripts/little_loops/loops/assumption-firewall.yaml` (ASSUMPTIONS_JSON /
  CLASSIFIED_JSON parse blocks)
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` (ENUMERATE_JSON
  parse block, ~line 53-59)

The shared `parse_tagged_json` fragment (`loops/lib/common.yaml:92`) is
structural only — it documents the contract but supplies no code, so each
caller reinvented the same fragile parser.

## Expected Behavior

1. A malformed-but-recoverable tagged-JSON line (missing trailing `]`/`}`,
   unbalanced brackets) is repaired and parsed, recovering the model's output.
2. An unrecoverable parse failure is **surfaced, not swallowed**: write a
   diagnostic (the failing tail) to stderr and exit non-zero so the FSM can
   route via `on_error` to a repair/log state instead of treating it as a
   legitimate empty result.
3. The fragile single-line-array contract is removed at the source for
   `brainstorm` (see Implementation Steps #3).

## Steps to Reproduce

1. Run `ll-loop run brainstorm` on a topic that generates many ideas (long LLM
   output increases likelihood of truncation on the `IDEAS_JSON:` line).
2. After the run completes, inspect output artifacts:
   `cat .loops/runs/brainstorm-<timestamp>/ideas.jsonl`
3. Observe: `ideas.jsonl` is 0 bytes despite the LLM visibly producing ideas
   in the session transcript.
4. Verify: exit code is 0, no error messages in the run log, no stderr output —
   the FSM reports "0 novel ideas" as if that were the legitimate result.

The `brainstorm-20260628T134036` run is a confirmed reproduction: 45 ideas
generated, every `IDEAS_JSON:` line missing its trailing `]`, `ideas.jsonl`
0 bytes.

## Root Cause

**Anchor:** `brainstorm.yaml` → `dedup_novelty` state → inline `python3`
heredoc `except (json.JSONDecodeError, ValueError): print(0); sys.exit(0)`.

Two layered causes:
- **Amplifier (primary):** the `except` clause swallows the error and exits 0,
  making the failure invisible to the FSM and to CI.
- **Trigger:** the `diverge` prompt asks the model to emit the entire idea set
  as one 2000-2900-char single-line JSON array terminated by `]`. The closing
  `]` is dropped 9/9 iterations — consistent with a stop-sequence / max-tokens
  boundary on a long terminal line with no trailing newline.

## Implementation Steps

1. **Shared tolerant parser** — add `extract_tagged_json(raw: str, tag: str)
   -> tuple[list | dict | None, str | None]` to
   `scripts/little_loops/output_parsing.py`: scan for the last `TAG:` line,
   `json.loads`, and on failure attempt bounded structural repair (balance
   trailing `]`/`}`). Return `(data, error)` — never swallow. Loops already
   `from little_loops.… import …` inside heredocs (precedent:
   `sft-corpus.yaml`, `migrate-sdk-version.yaml`), so this is importable from
   the loop runtime.
2. **Surface-don't-swallow** in all three callers — on unrecoverable failure,
   write the failing tail to stderr and `sys.exit(2)`; add `on_error:` routing
   so the FSM branches to a repair/log state rather than dead-ending on a
   false "0 results."
3. **NDJSON `diverge` prompt** (`brainstorm.yaml`) — emit one
   `{"text":…,"rationale":…}` object per line instead of a single wrapping
   array. Removes the single fragile terminator that triggers the bug.
4. **Unit test** — feed `extract_tagged_json` a known-bad input (missing `]`)
   and assert it either repairs or raises/returns an error — never silently
   returns empty.

## Motivation

Silent parse failures make brainstorm (and other affected loops) undebuggable:
the run exits with code 0 and "0 ideas", indistinguishable from a legitimate
empty result. Operators cannot distinguish "the model had nothing to say" from
"the model said plenty but the parser crashed". Re-running does not help — the
same stop-sequence/max-tokens truncation recurs on the same long JSON line
(9/9 iterations in the diagnosed run). Fixing this also removes the fragile
single-line-array contract from the `brainstorm` `diverge` prompt, improving
output reliability for all future runs beyond just the error-surfacing fix.

## Affected Files

- `scripts/little_loops/loops/brainstorm.yaml`
- `scripts/little_loops/loops/assumption-firewall.yaml`
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`
- `scripts/little_loops/output_parsing.py`
- `scripts/little_loops/loops/lib/common.yaml` (fragment doc note)
- `scripts/tests/test_output_parsing.py`

## Impact

- **Priority**: P2 — Silent data loss on every malformed-JSON run; impossible to
  distinguish from a legitimate zero-result without inspecting artifacts manually.
- **Effort**: Medium — Add `extract_tagged_json` to `output_parsing.py` (new
  shared utility), update three YAML callers, add `on_error:` routing, write
  unit tests. Existing `test_output_parsing.py` infrastructure reduces test setup.
- **Risk**: Low — Change is localised to `except` blocks in parse heredocs; all
  well-formed JSON paths are unchanged; unit tests guard regressions.
- **Breaking Change**: No

## Labels

`bug`, `loops`, `json-parsing`, `captured`

## Related

- `ENH-2356` — saturation gate inert. Diagnoses the *same symptom*
  (saturation stuck at 0) via a different root cause (difflib never flags
  dups). This bug shows the dedup never even runs in the failing case — parse
  fails first — which partly supersedes ENH-2356's premise that ideas are
  being written.
- `ENH-2384` — validator rule to catch this swallow pattern in CI.
- `BUG-794` (done) — same failure *class* (loop JSON parse → premature
  terminate) at a different site (`general-task` `check_done` llm_structured).
- Diagnosis artifact: `brainstorm-zero-ideas-diagnosis-20260628.md` (repo root).

## Session Log
- `/ll:ready-issue` - 2026-06-29T03:54:27 - `7dd76920-765a-4cff-9611-a52aa03157fb.jsonl`
- `/ll:confidence-check` - 2026-06-28T00:00:00Z - `75982e78-60cc-4fcf-896d-3455dec6a27e.jsonl`
- `/ll:format-issue` - 2026-06-29T03:49:00 - `22bf7394-8fa1-41f7-a1fa-75ab387564bd.jsonl`
- `/ll:capture-issue` - 2026-06-28T19:07:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b88673d-6bf0-48cb-a5d7-7d07fc889091.jsonl`

---

## Status

- **Created**: 2026-06-28
- **Status**: open
