---
id: BUG-2266
title: detect_installation discards plugin scope and mislabels project installs as
  global
type: bug
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to:
- EPIC-2257
- ENH-2256
labels:
- host-compat
- init
- install-check
confidence_score: 98
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 20
blocks:
- FEAT-2267
---

# BUG-2266: detect_installation discards plugin scope and mislabels project installs as global

## Summary

`detect_installation()` in `scripts/little_loops/init/install_check.py` parses
`claude plugin list --json` but **never reads the per-plugin `scope` field**,
hardcoding the source label as `"global-claude-code"` for any plugin install.
A **project-scoped** plugin install is therefore silently mislabeled as global.

## Evidence

`claude plugin list --json` returns a `scope` field per plugin (`"user"` or
`"project"`) plus an `installPath`:

```json
{
  "id": "cli-anything@cli-anything",
  "version": "7862c920c995",
  "scope": "user",
  "installPath": "/Users/.../cache/cli-anything/cli-anything/7862c920c995"
}
```

But `install_check.py:69-71` ignores both:

```python
if isinstance(plugin, dict) and plugin.get("name") == "ll@little-loops":
    return "global-claude-code", plugin.get("version")
```

## Current Behavior

`detect_installation()` in `scripts/little_loops/init/install_check.py` ignores the
`scope` field from `claude plugin list --json` and always returns the hardcoded
source label `"global-claude-code"` for any matched plugin, regardless of whether
the install is user-scoped or project-scoped.

## Expected Behavior

`detect_installation()` should read the `scope` field from the matched plugin entry
and return a distinct source label per scope:
- `"project-claude-code"` for `scope: "project"` installs
- `"global-claude-code"` for `scope: "user"` installs

`installPath` from the plugin entry should also be propagated in the return value for
use by scope-aware upgrade logic.

## Steps to Reproduce

1. Install little-loops as a project-scoped plugin: `claude plugin install . --scope project`
2. Call `detect_installation()` from `scripts/little_loops/init/install_check.py`
3. Observe: function returns `("global-claude-code", <version>)` — scope is mislabeled

## Root Cause

- **File**: `scripts/little_loops/init/install_check.py`
- **Anchor**: `in function detect_installation()` (lines 40–79)
- **Cause**: The `scope` and `installPath` fields from `claude plugin list --json` are
  never read. The match at lines 69–71 returns a hardcoded `"global-claude-code"` string
  without consulting the plugin's `scope` key.

## Proposed Solution

In `detect_installation()` (`install_check.py`), after matching the plugin by name:

1. Read `plugin.get("scope")` — map `"project"` → `"project-claude-code"`,
   `"user"` → `"global-claude-code"` (default fallback for unknown scopes).
2. Read `plugin.get("installPath")` and include it in the return value.
3. Update `config-schema.json` `install_source` enum to add `"project-claude-code"`.
4. Update any callers that consume the install-source value to handle the new variant.

## Impact

- **Correctness**: project-scoped installs are reported as global.
- **Blocks** scope-aware upgrade behavior (FEAT-2267): the headless `--upgrade`
  flow can only safely auto-update a *project*-scoped plugin vs. *advise* on a
  *user*-scoped one if detection preserves the distinction. Without scope, the
  generic upgrade dispatcher can't tell project-local surface from shared
  global state.
- **Effort**: Small. **Risk**: Low. **Breaking change**: the `install_source`
  return value gains a `project-claude-code` variant (config-schema enum
  already lists install sources — add the new value there too).

## Acceptance Criteria

- `detect_installation()` reads `scope` from the matched plugin entry and
  returns a distinct source for project- vs user-scoped installs
  (e.g. `project-claude-code` vs `global-claude-code`).
- `installPath` is propagated (needed by FEAT-2267 to re-substitute
  `plugin_root` and to detect a dangling version-stamped path after upgrade).
- `config-schema.json` `install_source` enum updated.
- Tests cover both scopes (extend `TestDetectInstallation` in
  `scripts/tests/test_init_install.py`).

## Implementation Steps

1. Update `detect_installation()` in `install_check.py` to read `scope` and map to
   `"project-claude-code"` / `"global-claude-code"` accordingly.
2. Propagate `installPath` in the return value alongside the source label.
3. Update `config-schema.json` `install_source` enum to include `"project-claude-code"`.
4. Update all 9 existing test methods in `TestDetectInstallation` (`test_init_install.py`) that unpack as `source, version = detect_installation(...)` — all break on 3-tuple return; change to `source, version, install_path = ...`; then add a `test_project_claude_code_installation_detected` case covering `scope: "project"` JSON input.
5. Update `tui.py:184` — expand `install_source == "global-claude-code"` to
   `install_source in ("global-claude-code", "project-claude-code")` so project-scoped
   plugin installs also trigger `fetch_latest_plugin()`.
6. If `installPath` is propagated (3-tuple), update both unpack sites (`cli.py:160`,
   `tui.py:172`) and all mock `return_value=` tuples in `test_init_core.py` (~10 sites,
   lines 1106–1400) and `test_init_tui.py` `mock_detect_installation` autouse fixture
   (line 31).
7. Extend `test_config_schema.py:578` `test_install_source_in_schema()` to also assert
   `"project-claude-code" in install_source["enum"]` (follow the pattern in `test_issues_next_issue_in_schema()` at lines 39–54).
8. Update `docs/reference/API.md:7563` table row and docstring for `detect_installation`.
9. Run tests and verify the mislabeling is resolved.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Ensure ALL return sites in `detect_installation()` return a consistent 3-tuple — the plain-text fallback at `install_check.py:74–75` (`if "ll@little-loops" in result.stdout: return "global-claude-code", None`) must become `return "global-claude-code", None, None`; callers (`cli.py:160`, `tui.py:172`) must both unpack to 3-tuple (step 6, made definitive here).
11. Add a new integration test in `test_init_core.py` (`TestMainInit`) — mock `detect_installation` returning `("project-claude-code", "1.0.0", "/path/to/install")` and assert `config["install_source"] == "project-claude-code"` is written to the output config file.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/install_check.py` — `detect_installation()` function
- `config-schema.json` — `install_source` enum (add `"project-claude-code"`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:160` — `install_source, installed_version = detect_installation(project_root)`; stores to config dict at line 277; upgrade logic at lines 183–230 branches on `"local-editable"` but does not branch on `"global-claude-code"` — no caller-side change needed here
- `scripts/little_loops/init/tui.py:172` — same 2-tuple unpack; line 184 gates plugin freshness check on `install_source == "global-claude-code"` — **must expand to `install_source in ("global-claude-code", "project-claude-code")`**; stores to config at line 565
- `scripts/little_loops/init/__init__.py:8` — re-exports `detect_installation`; no direct call, no change required

### Similar Patterns
- `config-schema.json:1563` — enum already includes `"global-codex"` and `"global-pi"` as precedent for host-scoped labels alongside `"global-claude-code"`; add `"project-claude-code"` next to `"global-claude-code"` and update the description string

### Tests
- `scripts/tests/test_init_install.py` — extend `TestDetectInstallation` class

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py` — 10 mock `return_value=` 2-tuple sites (lines 1106–1402, all patch `"little_loops.init.install_check.detect_installation"`); all will fail at the production unpack when return becomes 3-tuple; update all to 3-tuple [Agent 2/3 finding]
- `scripts/tests/test_init_tui.py` — `mock_detect_installation` autouse fixture (lines 23–34) returns `(None, None)`; the production `tui.py:172` unpack will break; update `return_value=(None, None)` → `(None, None, None)` [Agent 2/3 finding]
- `scripts/tests/test_config_schema.py` — `test_install_source_in_schema()` (line 578) only checks key presence and `type: string`; does not assert enum membership; extend with `assert "enum" in install_source` and `assert "project-claude-code" in install_source["enum"]` following pattern from `test_issues_next_issue_in_schema` (lines 39–54) [Agent 3 finding]
- `scripts/tests/test_init_core.py` — add a new `TestMainInit` headless `--yes` test where `detect_installation` returns `("project-claude-code", "1.0.0", "/path/to/install")`; assert `config["install_source"] == "project-claude-code"` is written to output config (integration test for new scope variant, no existing coverage) [Agent 3 finding]

### Documentation
- `docs/reference/API.md:7553–7567` — `detect_installation` entry: lists `"global-claude-code"` in return-value table; needs a `"project-claude-code"` row and updated description
- `config-schema.json:1563` — `install_source.description` string: "Values: 'local-editable', 'pypi', 'global-claude-code', 'global-codex', 'global-pi', or null" needs `'project-claude-code'` added

### Configuration
- `config-schema.json` — `install_source` enum

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`tui.py:184` scope-sensitive gate**: `if "claude-code" in _selected_hosts and install_source == "global-claude-code":` — this is the only caller that would silently skip the plugin-freshness check for project-scoped installs. Must be updated to `install_source in ("global-claude-code", "project-claude-code")`.
- **`installPath` return-type impact**: Adding `installPath` to the return value changes the current 2-tuple `(source, version)` signature. Both callers unpack as `install_source, installed_version = detect_installation(...)`. They would each need updating. Additionally, ~10 mock sites in `test_init_core.py` (lines ~1106–1400) and `test_init_tui.py` (line 31) use `return_value=(None, None)` or `return_value=("pypi", "1.0.0")` 2-tuples; each would need a third element. Consider using a `NamedTuple` or keeping as a 3-tuple — both require the same set of updates to callers and mocks.
- **Plain-text fallback**: `install_check.py:74-75` — the non-JSON fallback path (`if "ll@little-loops" in result.stdout: return "global-claude-code", None`) cannot determine scope; should remain `"global-claude-code"` since no structured data is available.
- **`test_config_schema.py:578`**: The existing schema test only asserts `"install_source"` key exists and `type: string`; it does NOT assert enum membership. A new assertion `assert "project-claude-code" in install_source["enum"]` must be added to catch future enum regressions, following `test_issues_next_issue_in_schema` (lines 39–54) as the pattern.
- **All 9 `TestDetectInstallation` test methods unpack as 2-tuples**: Lines 44, 62, 78, 95, 135, 154, 188 all use `source, version = detect_installation(...)`. These will ALL break (ValueError) when the return becomes a 3-tuple — step 4 must update all existing unpacks, not just add new cases.

## Reference

- `scripts/little_loops/init/install_check.py:40-79` — `detect_installation`.
- ENH-2256 (`a16d8f7d`) — introduced the current detection; this corrects it.

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:confidence-check` - 2026-06-24T00:00:00 - `fa7c169d-eb54-4677-82b2-e67621565732.jsonl`
- `/ll:wire-issue` - 2026-06-24T21:12:34 - `be894440-8cde-464b-8d81-175113fcffbe.jsonl`
- `/ll:wire-issue` - 2026-06-24T20:41:00 - `cab00745-6580-45c4-87b5-4d107e68bd28.jsonl`
- `/ll:refine-issue` - 2026-06-24T20:24:51 - `3eaafc1f-779c-4470-b381-fdd0d770bfa4.jsonl`
- `/ll:format-issue` - 2026-06-24T20:01:28 - `062df68d-565a-4685-8017-4ee73cfc2c7d.jsonl`
