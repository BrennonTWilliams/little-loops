---
id: ENH-1887
title: Broaden is_correction() detection beyond prefix regex
type: ENH
priority: P3
status: done
discovered_date: 2026-06-02
captured_at: '2026-06-02T00:00:00Z'
completed_at: '2026-06-03T03:14:28Z'
discovered_by: capture-issue
parent: EPIC-1707
depends_on: []
blocked_by: []
decision_needed: false
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 79
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
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

> **Selected:** Option A + D — expanded regex patterns (`_PHRASE_RE`) plus `!remember` explicit escape hatch (`_REMEMBER_RE`)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Option A + D — Expanded regex patterns + `!remember` prefix escape hatch

**Reasoning**: Option A scores 12/12 — the `tuple[re.Pattern[str], ...] + any(p.search(...))` idiom is already in use in `fsm/validation.py:108–113`, the single call site at `user_prompt_submit.py:71` requires no changes, and `TestIsCorrectionHeuristic` needs only list appends to extend. Option D scores 10/12, adds zero false positives, and fits cleanly via one new `_REMEMBER_RE` constant inside `is_correction()`. Options B and C are deferred: B lacks calibration data (the table is nearly empty until A+D populates it), and C contradicts the synchronous zero-network hook design with a documented p95 ≤ 200ms target and a 5-second test ceiling.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (Expanded regex) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option D (!remember prefix) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| Option B (Weighted scoring) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| Option C (LLM classification) | 0/3 | 0/3 | 1/3 | 0/3 | 1/12 |

**Key evidence**:
- Option A: `_MULTIMODAL_EVAL_PATTERNS` idiom (`fsm/validation.py:108–113`) is the exact `tuple[re.Pattern, ...] + any(p.search(...))` pattern to follow; single call site unchanged; test class ready for list-append extension
- Option D: `bypass_prefix` precedent in `user_prompt_submit.py:101` shows prefix routing is established; one new `_REMEMBER_RE` constant in `session_store.py` suffices
- Option B: No calibration corpus exists; `ScoringWeightsConfig` is scoped to dependency mapping; all three required pieces (registry, config surface, calibration data) must be built from scratch
- Option C: Entire hooks layer is synchronous/zero-network (p95 ≤ 200ms target); test suite enforces 5s hard ceiling (`test_hooks_integration.py:785`); no hook makes any LLM call

## Success Metrics

- True-positive coverage: 6 prefix patterns → ≥16 distinct correction forms recognized by `is_correction()`
- False-positive guard suite: 0 guard cases → ≥5 normal-message guard cases that return `False`
- `!remember` prefix handling: absent → unconditional write on any `!remember <text>` message

## Scope Boundaries

- **In scope**: `session_store.py` `is_correction()` and `_CORRECTION_RE`; `user_prompt_submit.py` write path; unit tests in `scripts/tests/test_session_store.py` (`TestIsCorrectionHeuristic`)
- **Out of scope**: changing the `user_corrections` table schema; retroactive backfill of past sessions; LLM-based classification (Option C) in the initial pass

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — update `_CORRECTION_RE` (and/or add `_PHRASE_RE`, `_REMEMBER_RE` siblings); update `is_correction()` at line ~103 to call all pattern sets
- `scripts/little_loops/hooks/user_prompt_submit.py` — add `!remember` prefix handling in `handle()` if Option D chosen

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py` — only caller of `is_correction()`; imports via `from little_loops.session_store import is_correction, record_correction`

### Consumer Layer (Read Path — context only, no changes needed)
- `scripts/little_loops/history_reader.py:find_user_corrections()` — LIKE search on `user_corrections` table; stale-filtered at 30 days; used by `ll-history-context`
- `scripts/little_loops/session_store.py:recent()` — raw `SELECT * FROM user_corrections ORDER BY id DESC LIMIT ?`; used by `ll-session` CLI

### Tests
- `scripts/tests/test_session_store.py` — extend `TestIsCorrectionHeuristic` class (currently 6 true-positive + 6 true-negative parametrized cases) with new pattern coverage
- `scripts/tests/test_hook_user_prompt_submit.py` — add integration test for `!remember` unconditional write path: send `"!remember always use snake_case"` via `handle()` and verify a `user_corrections` row is written. This test is needed regardless of whether `handle()` itself changes — `!remember` is routed through `is_correction()` internally, so the hook integration path `handle() → is_correction("!remember...") → True → record_correction()` is currently untested.
- `scripts/tests/test_hook_user_prompt_submit.py` — `test_non_correction_writes_no_db_row` acts as a false-positive guard (sends `"implement the login feature"`, asserts no DB row); re-verify this case passes after `_PHRASE_RE` is added, since it must not match any new phrase-internal patterns.

_Wiring pass added by `/ll:wire-issue`:_
- No new test files are needed; the above are extensions to existing files.

### Documentation
- `docs/reference/API.md` — documents `is_correction()` and `record_correction()`; update if function signature changes

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key constraint**: `_CORRECTION_RE` uses `re.match` (prefix-anchored via `^\s*`). Phrase-internal signals like "actually" or "instead" require `re.search` on a separate regex, because removing `^` from the prefix patterns would allow them to match anywhere and inflate false positives. The recommended structure is two (or three) separate module-level pattern sets, following the `tuple[re.Pattern[str], ...]` + `any(p.search(text) for p in patterns)` idiom already used in `scripts/little_loops/fsm/validation.py:_MULTIMODAL_EVAL_PATTERNS`.

**Recommended `session_store.py` shape (Option A + D)**:
```python
_CORRECTION_RE = re.compile(                          # existing — prefix-anchored
    r"^\s*(no[,!]|don'?t\s|stop\s|revert|that'?s\s+wrong|not\s+like\s+that)",
    re.IGNORECASE,
)
_PHRASE_RE = re.compile(                              # new — phrase-internal, re.search
    r"\b(instead|actually|you missed|should be|wrong approach"
    r"|remember that|always use|never use|from now on"
    r"|I meant\b.*\bnot\b|not\b.*\buse\b)\b",
    re.IGNORECASE,
)
_REMEMBER_RE = re.compile(r"^!remember\b", re.IGNORECASE)  # new — explicit escape hatch

def is_correction(text: str) -> bool:
    t = text[:512]
    return bool(_REMEMBER_RE.match(t) or _CORRECTION_RE.match(t) or _PHRASE_RE.search(t))
```

**`user_prompt_submit.py:handle()` gating**: the `!remember` case is handled by `_REMEMBER_RE` inside `is_correction()` itself rather than at the call site — this avoids duplicating the analytics gate logic and keeps all detection logic in `session_store.py`.

**Existing test class**: `TestIsCorrectionHeuristic` (NOT `TestIsCorrection`) at `scripts/tests/test_session_store.py`; currently has two `@pytest.mark.parametrize` blocks (`test_true_positives` — 6 cases; `test_true_negatives` — 6 cases). Follow Pattern 11 from the codebase pattern catalog.

1. In `scripts/little_loops/session_store.py` (lines ~97–103): keep `_CORRECTION_RE` unchanged; add `_PHRASE_RE` (phrase-internal, non-anchored) and `_REMEMBER_RE` (`^!remember\b`) as sibling module-level constants; update `is_correction()` to return `bool(_REMEMBER_RE.match(t) or _CORRECTION_RE.match(t) or _PHRASE_RE.search(t))`
2. No changes needed to `scripts/little_loops/hooks/user_prompt_submit.py:handle()` if `!remember` is handled inside `is_correction()` — the existing analytics gate at lines ~70–80 already delegates fully to `is_correction()`
3. Extend `TestIsCorrectionHeuristic` in `scripts/tests/test_session_store.py` with ≥10 new true-positive cases covering: `_PHRASE_RE` patterns (e.g., `"use snake_case instead"`, `"actually that function is in utils.py"`, `"you missed the import"`, `"should be a try/except"`, `"remember that we always use dataclasses"`, `"never use bare except"`, `"from now on always add type hints"`), `_REMEMBER_RE` (e.g., `"!remember always use snake_case"`, `"!Remember use absolute imports"`) and ≥5 false-positive guard cases (e.g., `"that should be fine"`, `"use it as-is"`, `"this is actually a good idea"` — subtle near-misses for `_PHRASE_RE`)
4. Add integration test in `scripts/tests/test_hook_user_prompt_submit.py`: send `"!remember always use snake_case"` via `handle()` with analytics enabled and verify `user_corrections` row written — this exercises the `handle() → is_correction("!remember...") → True → record_correction()` path which is currently untested. Re-run `test_non_correction_writes_no_db_row` to confirm `"implement the login feature"` still returns False after `_PHRASE_RE` is added.
5. Run `python -m pytest scripts/tests/test_session_store.py::TestIsCorrectionHeuristic scripts/tests/test_hook_user_prompt_submit.py -v` and confirm all new cases pass

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
- `/ll:ready-issue` - 2026-06-03T03:10:38 - `588d66b0-c8d7-4950-9a19-8140e43b67e8.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `1f3e2c1f-928d-49df-9f88-076d123bed4f.jsonl`
- `/ll:decide-issue` - 2026-06-03T03:04:32 - `e42431df-160c-48e8-95ff-02e142b6d570.jsonl`
- `/ll:wire-issue` - 2026-06-03T02:57:26 - `5d1e935f-a524-4a99-896f-bc491c8c9f90.jsonl`
- `/ll:refine-issue` - 2026-06-03T02:51:48 - `5f8be02f-9c45-4d21-a4a9-e456e040a263.jsonl`
- `/ll:format-issue` - 2026-06-03T01:13:40 - `8c9f6308-6202-49af-81bc-7d0b6b6978b2.jsonl`
