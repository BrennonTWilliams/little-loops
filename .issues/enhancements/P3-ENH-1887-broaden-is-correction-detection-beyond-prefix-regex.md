---
id: ENH-1887
title: Broaden is_correction() detection beyond prefix regex
type: ENH
priority: P3
status: open
discovered_date: 2026-06-02
captured_at: "2026-06-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-1707
depends_on: []
blocked_by: []
labels:
  - enhancement
  - captured
---

# ENH-1887: Broaden is_correction() detection beyond prefix regex

## Summary

The current `is_correction()` function in `session_store.py` uses a narrow prefix regex that only matches messages starting with `no,`, `don't`, `stop`, `revert`, `that's wrong`, or `not like that`. The vast majority of meaningful user corrections don't use these phrases — they say things like "use snake_case instead", "actually that function is in utils.py", "wrap this in a try/except", or "you missed the import". Because `user_prompt_submit.py` only writes a `user_corrections` row when `is_correction()` returns True, most real corrections are silently discarded, making the entire consumer layer (ENH-1847: `refine-issue`, `ready-issue`, `confidence-check`) read from a nearly empty table.

## Motivation

This enhancement would:
- Unblock the consumer layer: `refine-issue`, `ready-issue`, and `confidence-check` all read from `user_corrections`, but the table stays nearly empty because ≥90% of real corrections slip past the current prefix regex
- Increase signal fidelity without over-capturing: expanding coverage to phrase-internal patterns and explicit memory signals gives consumers meaningful data while keeping false-positive rate low (precision > recall)
- Close the loop on ENH-1847: the consumer wiring is already merged; this is the upstream fix that makes the data worth consuming

## Current Behavior

```python
_CORRECTION_RE = re.compile(
    r"^\s*(no[,!]|don'?t\s|stop\s|revert|that'?s\s+wrong|not\s+like\s+that)",
    re.IGNORECASE,
)
```

The hook in `user_prompt_submit.py` calls `is_correction(user_prompt)` and only writes to `user_corrections` on a match. A message like "use snake_case for all new methods" returns `False` and is never recorded.

## Expected Behavior

`is_correction()` captures a meaningfully broader class of real corrections without becoming a catch-all that writes every user message to the table. At minimum:

- Phrase-internal patterns: "instead", "actually", "you missed", "should be", "wrong approach", "change X to Y"
- Explicit memory signals: "remember that", "always use", "never use", "from now on"
- Restatement corrections: "I meant X not Y", "not X, use Y"

False-positive rate matters: every non-correction written to `user_corrections` injects noise into the context layer. Precision > recall for this use case.

## Proposed Approaches

### Option A: Expanded regex patterns
Extend `_CORRECTION_RE` with a broader alternation covering the phrase patterns above. Zero new dependencies; fast; deterministic.

**Risk**: regexes on arbitrary user text are brittle; hard to enumerate all correction forms.

### Option B: Keyword/phrase heuristic with scoring
Replace the single regex with a set of weighted signal patterns. A message scores as a correction if its total weight exceeds a threshold. Allows tuning precision vs. recall without a single monolithic regex.

**Risk**: requires calibrating weights against real session data; still misses semantic corrections.

### Option C: LLM-assisted classification on `user_prompt_submit` hook
Classify ambiguous prompts using a fast/cheap LLM call (Haiku) when heuristics are uncertain. Only run classification when a low-confidence heuristic signal is present to avoid latency on every message.

**Risk**: adds latency + cost to every hook invocation; requires network; complicates the hook's failure modes.

### Option D: Explicit `!remember` / `!correct` user command
Add a prefix command that users can prepend to any message to force correction recording: `!remember always use snake_case`. Zero false positives; requires user awareness.

**Risk**: adoption requires users to learn a new syntax; existing natural corrections still go unrecorded.

**Recommended starting point**: Option A + D — expand the regex to cover the most common natural-language patterns (Option A), and add `!remember` as an explicit escape hatch (Option D). Option B can follow if calibration data warrants it.

## Success Metrics

- True-positive coverage: 6 prefix patterns → ≥16 distinct correction forms recognized by `is_correction()`
- False-positive guard suite: 0 guard cases → ≥5 normal-message guard cases that return `False`
- `!remember` prefix handling: absent → unconditional write on any `!remember <text>` message

## Scope Boundaries

- **In scope**: `session_store.py` `is_correction()` and `_CORRECTION_RE`; `user_prompt_submit.py` write path; unit tests in `scripts/tests/test_session_store.py` (`TestIsCorrection`)
- **Out of scope**: changing the `user_corrections` table schema; retroactive backfill of past sessions; LLM-based classification (Option C) in the initial pass

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — update `_CORRECTION_RE` (and add scoring logic if Option B)
- `scripts/little_loops/hooks/user_prompt_submit.py` — add `!remember` prefix handling if Option D chosen

### Tests
- `scripts/tests/test_session_store.py` — extend `TestIsCorrection` with true-positive examples for newly captured patterns and false-positive guard cases

## Implementation Steps

1. Extend `_CORRECTION_RE` in `session_store.py` with phrase-internal patterns (`instead`, `actually`, `you missed`, `should be`, `wrong approach`), explicit memory signals (`remember that`, `always use`, `never use`, `from now on`), and restatement forms (`I meant X not Y`, `not X, use Y`)
2. Add `!remember` prefix branch in `user_prompt_submit.py`: if the message starts with `!remember`, write a `user_corrections` row unconditionally before regex evaluation
3. Extend `TestIsCorrection` in `scripts/tests/test_session_store.py` with ≥10 true-positive cases covering newly added patterns and ≥5 false-positive guard cases (normal messages that must return `False`)
4. Run `python -m pytest scripts/tests/test_session_store.py -v` and confirm all new cases pass

## Impact

- **Priority**: P3 — prerequisite quality fix for the consumer layer to deliver its stated value
- **Effort**: Small (Option A+D) to Medium (Option B)
- **Risk**: Low (additive) — broadening detection can only add rows, not remove existing ones
- **Breaking Change**: No

## Acceptance Criteria

- At least 10 natural-language correction forms beyond the current 6 are captured by `is_correction()` true-positive tests
- At least 5 false-positive guard cases are present (normal user messages that should NOT be recorded as corrections)
- `user_prompt_submit` hook writes a correction row for `!remember <text>` unconditionally

---

**Open** | Created: 2026-06-02 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-03T01:13:40 - `8c9f6308-6202-49af-81bc-7d0b6b6978b2.jsonl`
