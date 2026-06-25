---
id: ENH-2285
type: ENH
priority: P3
status: done
parent: EPIC-2279
relates_to:
- BUG-2271
- FEAT-2274
- ENH-2272
captured_at: '2026-06-25T00:00:00Z'
completed_at: '2026-06-25T07:42:45Z'
discovered_date: 2026-06-25
discovered_by: issue-size-review
confidence_score: 93
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# ENH-2285: Unified 4-tier template resolver in issue_template.py

## Summary

Add `resolve_templates_dir(config: BRConfig) -> Path` to `scripts/little_loops/issue_template.py`
implementing the 4-tier precedence lookup. This is the shared foundation that the
`ll-issues sections` CLI (ENH-2286) and the init deploy (ENH-2287) both depend on.

## Current Behavior

No public function exists for resolving the templates directory from configuration. Callers
use the private `_default_templates_dir()` helper (which only checks `CLAUDE_PLUGIN_ROOT` env
var and the in-package bundle) or pass explicit directory paths to `load_issue_sections()`.
The 4-tier precedence (config override → `.ll/templates/` → env-var → bundled) is not codified
in a reusable public function; each future callsite would have to re-implement the lookup chain.

## Expected Behavior

A public `resolve_templates_dir(config: BRConfig) -> Path` function exists in
`scripts/little_loops/issue_template.py` that implements the full 4-tier precedence lookup.
ENH-2286 (`ll-issues sections` CLI) and ENH-2287 (`ll-init` deploy) both call this single
function instead of independently reimplementing the resolution logic.

## Parent Issue

Decomposed from ENH-2272: ll-issues sections accessor + project-local template deploy

## Proposed Solution

Add a new public function to `issue_template.py`:

```python
def resolve_templates_dir(config: BRConfig) -> Path:
    # tier 1: explicit config override
    if explicit := (config.issues.templates_dir if hasattr(config, "issues") else None):
        return Path(explicit)
    # tier 2: per-project deployed copy
    ll_dir = Path(config.ll_dir if hasattr(config, "ll_dir") else ".ll") / "templates"
    if ll_dir.exists():
        return ll_dir
    # tier 3: in-package bundle (always available via FEAT-2274 / existing path)
    return get_bundled_templates_dir()
```

`_default_templates_dir()` remains unchanged as a private helper for legacy callers
(callers passing `None` to `load_issue_sections()` still work until migrated).

## Files to Modify

- `scripts/little_loops/issue_template.py` — add `resolve_templates_dir(config: BRConfig) -> Path`
- `scripts/tests/test_issue_template.py` — extend `TestLoadIssueSections` with 4-tier resolver
  precedence tests; ensure `test_load_custom_dir` and `test_load_missing_file` do not regress.
  New tests: `test_uses_config_templates_dir`, `test_uses_ll_templates_dir`, `test_falls_back_to_bundle`.
  Tier-ordering risk: `test_uses_claude_plugin_root_when_set` and `test_falls_back_to_file_relative`
  assume the env-var tier has exclusive priority — confirm they still pass or monkeypatch to
  suppress the new `.ll/templates/` tier check (only active when `ll_dir` has a `templates/`
  subdir in the test's CWD).

## Acceptance Criteria

- `resolve_templates_dir(config)` returns config override when `issues.templates_dir` is set
- Returns `.ll/templates/` path when that directory exists and no explicit override is set
- Falls back to `get_bundled_templates_dir()` when neither tier 1 nor tier 2 applies
- All existing `test_issue_template.py` tests still pass
- New parametrized tests cover all three return paths

## Implementation Steps

1. Add `resolve_templates_dir(config: BRConfig) -> Path` to `issue_template.py` (after `get_bundled_templates_dir()`)
2. Export it alongside `load_issue_sections` and `get_bundled_templates_dir` from the module
3. Add 4-tier resolver tests to `scripts/tests/test_issue_template.py`
4. Run `python -m pytest scripts/tests/test_issue_template.py -v` to confirm all pass

## Scope Boundaries

- Does NOT modify `_default_templates_dir()` (legacy callers are unaffected)
- Does NOT wire into CLI or init (those are ENH-2286 and ENH-2287)
- Does NOT migrate existing callers of `load_issue_sections(type, templates_dir=None)` — that
  migration is within BUG-2271 scope

## Impact

- **Priority**: P3 — Foundation enabler; no direct user-facing feature until ENH-2286/ENH-2287 ship
- **Effort**: Small — Single function addition (~15–20 lines) plus 3 new parametrized tests
- **Risk**: Low — `_default_templates_dir()` stays unchanged; no existing callers are migrated
- **Breaking Change**: No

## Labels

`enhancement`, `template-resolver`, `issue-template`, `python`

## Status

**Open** | Created: 2026-06-25 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-25T07:38:35 - `15c26235-57d9-458e-8e41-3af57ae03497.jsonl`
- `/ll:issue-size-review` - 2026-06-25T00:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
- `/ll:confidence-check` - 2026-06-25T00:00:00Z - `dae3a2b0-93f7-447d-bfa7-f0e0614af2dc.jsonl`
