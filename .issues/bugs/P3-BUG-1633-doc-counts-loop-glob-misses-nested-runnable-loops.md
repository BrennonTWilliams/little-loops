---
id: BUG-1633
title: doc_counts loop glob misses nested runnable loops (oracles/)
type: bug
priority: P3
status: open
labels: [docs, verification, loops]
---

# doc_counts loop glob misses nested runnable loops

## Problem

`scripts/little_loops/doc_counts.py:28` defines:

```python
COUNT_TARGETS = {
    ...
    "loops": ("scripts/little_loops/loops", "*.yaml"),
}
```

The glob pattern `*.yaml` is non-recursive, so `count_files()` only sees top-level YAML files (51). Runnable nested loops are ignored — currently `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml`, which `ll-loop validate oracles/oracle-capture-issue` confirms is a valid 4-state FSM.

Result: `ll-verify-docs` reports "All counts match" even when README.md says `51 FSM loops` while the runnable count is `52`. This silently degrades the verifier from a guard into a rubber stamp.

## Reproduction

```bash
$ ll-loop validate oracles/oracle-capture-issue
oracles/oracle-capture-issue is valid
  States: check_mechanical, route_phase1, score_semantic, done

$ python3 -c "from scripts.little_loops.doc_counts import count_files; \
  print(count_files('scripts/little_loops/loops', '*.yaml'))"
51

$ find scripts/little_loops/loops -name '*.yaml' | wc -l
57
```

The 6-file gap is 5 library fragments under `lib/` (genuinely not runnable — they're missing required FSM fields) plus 1 runnable oracle that should be counted.

## Acceptance criteria

- [ ] `count_files()` (or its caller in `verify_documentation()`) enumerates loops recursively
- [ ] Library fragments under `lib/` are excluded — either by directory allowlist/denylist, or by filtering to YAMLs whose top-level keys include `name` + `initial` + (`states` or `flow`)
- [ ] `oracles/oracle-capture-issue.yaml` is counted; `lib/*.yaml` are not
- [ ] Total reported count = 52 (today) and tracks future additions of nested runnable loops
- [ ] Existing tests in `scripts/tests/` still pass; new test covers a nested-runnable-loop fixture and a library-fragment fixture

## Notes

Found during `/ll:audit-docs` (2026-05-23). Manually fixed README.md:167 (51 → 52); this issue prevents the regression from reappearing.

Related: `ll-loop list` also omits nested runnable loops — same root cause but in CLI enumeration, not doc verification. See [[BUG-1634]] (sibling issue).
