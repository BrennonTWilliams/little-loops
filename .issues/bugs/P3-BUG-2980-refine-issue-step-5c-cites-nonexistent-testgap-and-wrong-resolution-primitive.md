---
id: BUG-2980
title: refine-issue Step 5c cites nonexistent TestGap and the wrong resolution primitive
type: BUG
priority: P3
status: done
discovered_date: '2026-08-01'
discovered_by: capture-issue
captured_at: '2026-08-01T23:57:20Z'
completed_at: '2026-08-01T23:57:20Z'
relates_to:
- ENH-2971
labels:
- refine-issue
- commands
- docs-drift
decision_needed: false
testable: false
---

# BUG-2980: `refine-issue` Step 5c cites nonexistent `TestGap` and the wrong resolution primitive

## Summary

Two stale references in `commands/refine-issue.md` Step 5c ("Gap-Analysis
Mode") pointed refiners at a class that does not exist and at a primitive
that cannot answer the question being asked. Found during pre-implementation
review of ENH-2971, which depends on Step 5c's definition of "resolves"; both
were fixed in the same pass rather than deferred.

## Current Behavior

_As of the fix — this section describes the pre-fix state._

Step 5c instructed the refiner to adopt a priority model from
`models.py:TestGap` (no such class) and to detect stale anchors via
`_sweep_file()` → `skipped_refs` (an aggregate counter that cannot name a
failing reference). A refiner following either instruction literally either
found nothing at the anchor or had no way to act on the result, so the
staleness check in gap-analysis mode was effectively unimplementable as
written.

## Expected Behavior

Step 5c cites the class that exists (`Gap`) and names the primitive that can
actually answer "which reference went stale" (`resolve_anchor()`), including
the line-bound check that `resolve_anchor()` does not perform itself.

## Steps to Reproduce

1. `grep -n "models.py:TestGap" commands/refine-issue.md` → hit at line 524
   (pre-fix).
2. `grep -n "class TestGap" scripts/little_loops/issue_history/models.py` →
   no hits; the class is `Gap` at `models.py:259`.
3. `grep -n "skipped_refs" scripts/little_loops/issues/anchor_sweep.py` →
   `skipped_refs: int = 0`, incremented in aggregate with the per-reference
   detail going only to `warnings.warn(...)`.
4. Run `/ll:refine-issue <ID> --auto --gap-analysis` and attempt Step 5c's
   Integration Map staleness check: there is no readable per-reference result
   to score.

## Root Cause

**1. `models.py:TestGap` does not exist.** Step 5c said:

> Adopt the `"critical"/"high"/"medium"/"low"` priority model from
> `scripts/little_loops/issue_history/models.py:TestGap`

The dataclass is `Gap` (`scripts/little_loops/issue_history/models.py:259`).
`TestGap` appears in the repo only as pytest class names
(`test_issue_history_advanced_analytics.py:959`) and in ENH-390's prose. A
refiner following the reference finds nothing at that anchor.

**2. `skipped_refs` cannot identify a stale reference.** Step 5c said to use
`anchor_sweep.py:_sweep_file()` → `skipped_refs` to detect `file:N` anchors
that no longer resolve. `SweepResult.skipped_refs`
(`anchor_sweep.py:37`) is an **aggregate integer counter** across a whole
sweep run — it carries no data on which reference failed, in which file, or
under which heading. The per-reference detail exists only in a
`warnings.warn(...)` call (`anchor_sweep.py:75-80`), which callers cannot
read. `_sweep_file()` also only accepts a filesystem `Path` and reads the
full file, so it cannot be pointed at a single section's text.

The reusable per-reference primitive is `resolve_anchor()`
(`scripts/little_loops/issues/anchors.py:59`).

**3. (Found while fixing 2.) `resolve_anchor()` alone is not sufficient
either.** It computes `scan_end = min(line_number, len(lines))`
(`anchors.py:80`), so a line number past EOF silently resolves against the
tail of the file instead of failing. "Resolves" needs an explicit
`line_number <= len(lines)` bound.

## Program Design

Prose-only change to a command body plus its generated mirrors — no Python
touched, no new code path. The correctness constraint is that the rule stated
in Step 5c must be the same rule ENH-2971's `triage_research_axes()` will
implement, since both answer "does this reference resolve?" over the same
issue sections. Stating it once in Step 5c, in terms of a primitive that is
callable (`resolve_anchor()`) rather than one that is not
(`skipped_refs`), is what makes the shared definition possible.

Mirrors are generated artifacts: `commands/refine-issue.md` is the source and
`ll-adapt` regenerates the per-host copies. No mirror is hand-edited.

### Signatures

No signature changed. The two referenced by the corrected prose:

```python
def resolve_anchor(file_path: str, line_number: int) -> str | None:
    """Return the enclosing function, class, or section for the given file:line."""
    # anchors.py:59 — returns None only when the file is unreadable or no
    # definition matches; an out-of-range line_number still resolves via
    # scan_end = min(line_number, len(lines)) at anchors.py:80

@dataclass
class Gap:  # issue_history/models.py:259 — was miscited as `TestGap`
    priority: str = "low"  # "critical", "high", "medium", "low"
```

### Call Path

- `commands/refine-issue.md` Step 5c §2 "Check Each Section Against Codebase
  Reality" (line 512) — anchor-staleness rule, now stated in terms of
  `resolve_anchor()` (`scripts/little_loops/issues/anchors.py:59`) plus a
  `line_number <= len(lines)` bound
- `commands/refine-issue.md` Step 5c §2 "Proposed Solution / Implementation
  Steps" (line 516) — same rule, now cross-referenced rather than restated
- `commands/refine-issue.md` Step 5c §3 "Score Gaps by Impact" (line 524) —
  priority model, now citing `issue_history/models.py:Gap`
- `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` (line 59) —
  still the bulk path; `SweepResult.skipped_refs` (line 37) now described
  accurately as an aggregate counter rather than a per-reference result
- `ll-adapt` → `.gemini/commands/refine-issue.toml`,
  `.kimi-code/skills/ll-refine-issue/SKILL.md`

## Fix Applied

`commands/refine-issue.md` Step 5c:

- `models.py:TestGap` → `models.py:Gap`
- The two `_sweep_file()` → `skipped_refs` bullets now state the actual rule:
  an anchor resolves when `resolve_anchor()` returns non-`None` **and** the
  line number is within the file's line count, with the EOF-clamp called out
  explicitly. `skipped_refs` is described accurately as an aggregate counter,
  with `resolve_anchor()` named as the primitive to use when you need to know
  *which* reference went stale.

Host mirrors regenerated via `ll-adapt --host {gemini,kimi-code} --apply`:

- `.gemini/commands/refine-issue.toml`
- `.kimi-code/skills/ll-refine-issue/SKILL.md`

## Impact

Beyond correcting the references, this gives Step 5c and ENH-2971's planned
`triage_research_axes()` predicate **one shared definition of "resolves"** —
which was ENH-2971's Implementation Step 1 intent. ENH-2971's Scope
Boundaries records this as already fixed.

Left uncorrected, ENH-2971 would have either re-derived the rule inline
(two definitions, the thing Step 1 exists to prevent) or inherited the
EOF-clamp bug into its triage predicate, where it would have caused the exact
failure mode ENH-2971 is designed against: skipping a research agent because
a stale reference appeared to resolve.

## Verification

- `python -m pytest scripts/tests/test_refine_issue_command.py` — 26 passed
- `grep -rn "models.py:TestGap" commands/ .gemini/ .kimi-code/` — no hits
- Mirrors confirmed byte-identical to the updated command body for the
  changed lines

## Notes

`ll-adapt` also regenerated unrelated drift in the `help` and
`normalize-issues` mirrors (pre-existing, from the ENH-2944 `ll-issues
normalize` work). Not caused by this fix.

`ll-adapt` registers four hosts (`codex`, `gemini`, `kimi-code`, `omp`).
Only `gemini` and `kimi-code` carry a `refine-issue` artifact today; ENH-2971's
Integration Map lists only `.gemini` and should be widened to "regenerate all
host mirrors via `ll-adapt`".

## Session Log
- `hook:posttooluse-status-done` - 2026-08-01T23:57:57 - `32b51a1d-fa82-4643-8752-c279ed2e4f04.jsonl`

---

## Status

**Done** | Created: 2026-08-01 | Completed: 2026-08-01 | Priority: P3
