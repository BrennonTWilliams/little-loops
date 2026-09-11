---
id: BUG-3451
title: "VerdictCache found-entries never revalidate — stale local cache masks evidence-gate regressions that CI then fails"
type: BUG
priority: P1
status: done
captured_at: '2026-09-11T00:00:00Z'
completed_at: '2026-09-11T19:30:00Z'
discovered_date: '2026-09-11'
relates_to:
- ENH-3441
size: Small
confidence_score: 95
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 20
labels:
- verify-evidence
- cache
- ci
---

# BUG-3451: VerdictCache found-entries never revalidate — stale local cache masks evidence-gate regressions that CI then fails

## Summary

`ll-verify-evidence`'s gitignored memo (`.ll/evidence-verdict-cache.json`) stored found
verdicts as bare `"1"` entries that `lookup()` returned unconditionally — no
working-tree or revision-set fingerprint check. When a quoted span's source later
changed (README rewrite, `CONFIG_DIR` migration to `.ll`, ALLOWLIST restructuring),
every warm-cache developer machine kept verifying the stale span, while CI's cold
checkout recomputed and failed `test_no_new_unverifiable_evidence`. This masked real
regressions for the entire life of the cache file and produced CI failures that could
not be reproduced locally (2026-09-11 run 34628255906: 5 spans, 4 stale-`"1"`-masked).

## Steps to Reproduce

1. Have a span verify once (recorded as `"1"` in the local verdict cache).
2. Edit the quoted source so the span disappears; commit.
3. Run `python -m pytest scripts/tests/test_verify_evidence.py` locally — passes
   (stale `"1"` serves the verdict).
4. Push; CI (cold checkout, no cache) fails `test_no_new_unverifiable_evidence`.

## Root Cause

`VerdictCache.lookup()` in `scripts/little_loops/cli/verify_evidence.py`:

```python
if entry == "1":
    return True   # no fingerprint revalidation, ever
```

The class docstring claimed "a stale entry can only cause redundant work — never a
suppressed finding", which is exactly backwards for found entries: a hit can come
from the working tree (edited freely) or from a blob reachable only via a ref a later
prune deletes. "Git history only grows" does not cover either.

## Fix

Both verdict forms now carry fingerprints (`"<v>:<blob_fp>:<wt_sha>"`) and revalidate
identically in `lookup()`; `record()` writes the found form the same way;
`_CACHE_VERSION` bumped 1 → 2 so old-format caches are discarded on load.
Regression test: `test_found_verdict_invalidated_by_working_tree_edit` (working-tree-only
span, edited out; the CI-failure shape).

The five masked spans from the 2026-09-11 run were resolved in the same commit with
`<!-- ll-evidence-ok: reason -->` markers (all four issues `done`, quoting at-filing
state): BUG-2111 (×2, Steps to Reproduce line), BUG-3065, ENH-1441, FEAT-959.

## Resolution

Implemented and verified: full cold-cache gate run reports ok, 0 findings;
`test_verify_evidence.py` 59/59 pass; mypy + ruff clean.


## Session Log
- `hook:posttooluse-status-done` - 2026-09-11T23:26:57 - `ab4f2b86-d6b4-4723-ad9c-ba7889e2e627.jsonl`
