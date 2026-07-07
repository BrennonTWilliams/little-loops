---
id: ENH-2532
title: "Bound Hypothesis deadlines in test_goals_parser_fuzz.py (drop deadline=None)"
type: ENH
priority: P3
status: done
captured_at: '2026-07-07T21:38:05Z'
discovered_date: 2026-07-07
discovered_by: audit
size: Small
completed_at: '2026-07-07T21:38:05Z'
labels:
- tests
- fuzz
---

# ENH-2532: Bound Hypothesis deadlines in test_goals_parser_fuzz.py (drop deadline=None)

## Summary

All 4 fuzz test configs in `scripts/tests/test_goals_parser_fuzz.py` (lines
176, 199, 220, 242) set `deadline=None`, defeating the hypothesis-level hang
detection their docstrings explicitly claim ("Uses Hypothesis's deadline to
detect hangs..."). Hangs were bounded only by `pytest-timeout=120s`. Replaced
all 4 with `deadline=5000` (5s per example) per docstring intent.

Source: audit run `.loops/runs/general-task-20260707T133447/audit-report.md`
(C3 / Finding #3 / Recommendation R3).

## Implementation

- `deadline=None` → `deadline=5000` in the 4 `@settings(...)` decorators:
  `test_from_content_never_crashes`, `test_yaml_bomb_protection`,
  `test_deep_nesting_protection`, `test_from_file_with_various_content`.
- No other changes; `pytest-timeout=120` remains the outer bound.

## Verification

- `py_compile` syntax check passed; `deadline=5000` x4, `deadline=None` x0.
- Full fuzz-file pytest run pending locally (sandbox Python 3.10 <
  required 3.11). If a fuzz example legitimately exceeds 5s, bump that one
  deadline rather than reverting to `None`.
