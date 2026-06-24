---
id: BUG-2266
title: detect_installation discards plugin scope and mislabels project installs as global
type: bug
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [EPIC-2257, ENH-2256]
labels: [host-compat, init, install-check]
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

## Reference

- `scripts/little_loops/init/install_check.py:40-79` — `detect_installation`.
- ENH-2256 (`a16d8f7d`) — introduced the current detection; this corrects it.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
