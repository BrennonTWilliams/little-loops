---
discovered_date: 2026-02-07
discovered_by: capture_issue
---

# FEAT-270: Ship built-in loops with the plugin

## Summary

The plugin should include a set of ready-to-run loop YAML files that users can immediately execute via `ll-loop run` without needing to author loops from scratch or go through the `/ll:create_loop` wizard.

## Context

User description: "Create built-in loops that ship with the plugin"

Investigation confirmed that while `ll-loop run` is fully functional infrastructure and `/ll:create_loop` offers template-guided creation (ENH-126), the plugin ships zero runnable `.yaml` loop files. The `.loops/` directory doesn't even exist. Users must create every loop themselves before they can use the loop system at all.

This creates a cold-start problem: the most powerful automation feature requires manual setup before it demonstrates any value.

## Current Behavior

- `ll-loop list` shows nothing — no loops exist out of the box
- `ll-loop run <name>` requires users to have already created `.loops/<name>.yaml`
- The loop-suggester skill generates suggestions to `.claude/loop-suggestions/` but doesn't install them
- ENH-126 added templates to the wizard prompt, but these produce loops interactively, not pre-installed

## Expected Behavior

After installing the plugin, users should be able to:
1. Run `ll-loop list` and see available built-in loops
2. Run `ll-loop run <name>` immediately on a built-in loop
3. Customize built-in loops by copying and modifying them

## Proposed Solution

1. **Create a `loops/` directory in the plugin** containing canonical loop definitions
2. **Ship 4-6 built-in loops** covering common little-loops workflows:

| Loop | Paradigm | Description |
|------|----------|-------------|
| `issue-readiness-cycle` | imperative | Process issues through `/ll:ready_issue` then `/ll:manage_issue` |
| `pre-pr-checks` | invariants | Run `/ll:check_code` + `/ll:run_tests` before PR |
| `issue-verification` | invariants | Verify + normalize issues until clean |
| `codebase-scan` | imperative | Scan codebase, verify, and prioritize discovered issues |
| `quality-gate` | invariants | Lint + types + format + tests must all pass |

3. **Update `ll-loop` resolution logic** (`cli.py:resolve_loop_path`) to search the plugin's bundled `loops/` directory as a fallback after checking the project's `.loops/`
4. **Add `ll-loop init`** or integrate with `/ll:init` to optionally copy built-in loops into the project's `.loops/` directory for customization
5. **Mark built-in loops clearly** in `ll-loop list` output (e.g., `[built-in]` tag)

### Resolution Priority

```
1. Project .loops/<name>.fsm.yaml  (compiled, highest priority)
2. Project .loops/<name>.yaml      (project paradigm)
3. Plugin  loops/<name>.yaml       (built-in fallback)
```

## Impact

- **Priority**: P3
- **Effort**: Medium (author loops, update resolution logic, add tests)
- **Risk**: Low (additive — built-in loops don't affect existing behavior)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Plugin structure and file layout |
| guidelines | CONTRIBUTING.md | Development conventions for new files |

## Related Issues

- ENH-126 (completed): Added loop templates to `/ll:create_loop` wizard — complementary but different scope

## Labels

`feature`, `loops`, `developer-experience`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `loops/` (new directory): 5 built-in loop YAML files (issue-readiness-cycle, pre-pr-checks, issue-verification, codebase-scan, quality-gate)
- `scripts/little_loops/cli.py`: Added `get_builtin_loops_dir()`, extended `resolve_loop_path()` with built-in fallback, updated `cmd_list()` to show `[built-in]` tags, added `cmd_install()` subcommand
- `scripts/tests/test_builtin_loops.py` (new): 12 tests covering loop validation, resolution, list display, and install
- `scripts/tests/test_ll_loop_integration.py`: Updated `test_list_empty_loops_dir` for built-in loop awareness

### Verification Results
- Tests: PASS (2619 passed)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-02-07 | Completed: 2026-02-07 | Priority: P3
