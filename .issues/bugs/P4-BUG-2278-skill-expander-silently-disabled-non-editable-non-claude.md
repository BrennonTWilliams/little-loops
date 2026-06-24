---
id: BUG-2278
type: BUG
priority: P4
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2257
relates_to: [BUG-2275, FEAT-2274, ENH-2272, BUG-2273]
labels: [bug, host-compat, cross-host, skill-expander, automation, path-resolution]
---

# BUG-2278: `skill_expander` silently disables prompt pre-expansion on non-editable / non-Claude installs (no host-skill-dir awareness)

## Summary

`skill_expander._find_plugin_root()` (`skill_expander.py:22`) is env-var-first
(`CLAUDE_PLUGIN_ROOT`) — the "correct" pattern the templates-cluster issues cite
— but its `__file__` fallback (`parent.parent.parent`, line 32) escapes the
package and resolves to a repo root that does not exist on a non-editable
`pip install`. `_resolve_content_path()` then looks for `skills/<name>/SKILL.md`
and `commands/<name>.md` under that non-existent root, finds nothing, and
`expand_skill()` returns `None`. Callers in `issue_manager.py` fall back to the
raw slash command (e.g. `expand_skill("ready-issue", …) or _ready_slash`), so
this **degrades gracefully** — but the pre-expansion optimization (which exists
to eliminate the ToolSearch→Skill deferred-tool round-trip when `ll-auto` /
`ll-parallel` spawn subprocesses) is **silently disabled**.

Two distinct gaps:
1. On non-editable installs with `CLAUDE_PLUGIN_ROOT` unset (e.g. `ll-auto` from
   a plain shell), expansion never happens.
2. The resolver has **no awareness of host-specific skill directories**. On
   Codex, skills are adapted into `~/.codex/skills/` (see
   `ll-adapt-skills-for-codex`); `_resolve_content_path()` only ever probes the
   plugin-root `skills/` / `commands/`, so even with a valid root it cannot find
   host-adapted skills. The slash-command fallback it drops to may itself be
   unresolvable on a non-Claude host.

## Motivation

- **Silent performance/reliability regression** in the core automation loops
  (`ll-auto`, `ll-parallel`) on the dominant `pip install` path and on every
  non-Claude host — the deferred-tool round-trip the expander was built to avoid
  comes back, invisibly.
- **Cross-host correctness**: the expander encodes a Claude-only view of where
  skills live; the host-generalization roadmap (EPIC-2257) needs it to resolve
  per-host skill locations or to explicitly report that expansion is unavailable.

## Steps to Reproduce

1. `pip install little-loops` (non-editable) into a fresh venv; `CLAUDE_PLUGIN_ROOT`
   unset.
2. Run `ll-auto` (or call `expand_skill("ready-issue", ["BUG-1"], config)`).
3. Observe: `expand_skill` returns `None` (the `__file__` fallback root has no
   `skills/`); callers silently use the slash-command fallback. The expansion
   optimization is disabled with no log line.

(Variant: set `LL_HOST_CLI=codex` with skills adapted into `~/.codex/skills/` —
`_resolve_content_path` still probes only the plugin-root `skills/` and returns
`None`.)

## Root Cause

- **File**: `scripts/little_loops/skill_expander.py`
- **Anchors**: `_find_plugin_root()` (line 22), `_resolve_content_path()` (line 35)

```python
def _find_plugin_root() -> Path:
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent  # escapes the package
```

```python
skill_path = plugin_root / "skills" / name / "SKILL.md"      # plugin-root only
command_path = plugin_root / "commands" / f"{name}.md"
```

The `__file__` fallback escapes `little_loops/` (broken in non-editable installs,
same class as BUG-2275); and `_resolve_content_path` has no notion of
host-specific skill directories.

## Current Behavior

`expand_skill()` returns `None` on non-editable / non-Claude contexts;
`issue_manager.py` falls back to the slash command (`issue_manager.py:621, 675,
837, 877`). Functional but the optimization is silently off, and the fallback's
viability on non-Claude hosts is unverified. Editable dev installs (or a set
`CLAUDE_PLUGIN_ROOT`) mask the issue.

## Expected Behavior

`expand_skill()` resolves skill/command source across install modes and hosts —
or, when it genuinely cannot, emits a debug/warn signal so the disabled
optimization is observable rather than silent. The resolver should consult
host-specific skill locations (e.g. `~/.codex/skills/`) consistent with the
host abstraction (`resolve_host()`), not only the Claude plugin root.

## Proposed Solution

1. Replace the escaping `__file__` fallback with the shared in-package/env-var
   resolver (BUG-2271 / BUG-2273 / ENH-2272). Note: `skills/` / `commands/` are
   host-plugin assets and are **not** in the wheel — so unlike templates, the
   in-package tier won't contain them; the resolver must fall through to
   host-specific locations.
2. Extend `_resolve_content_path()` to probe host-adapted skill dirs based on the
   resolved host (`LL_HOST_CLI` / `orchestration.host_cli`), e.g.
   `~/.codex/skills/<name>/SKILL.md` for Codex.
3. When no source resolves, log at debug/warn that pre-expansion is unavailable
   (so the fallback is observable), instead of a fully silent `None`.

## Integration Map

### Files to Modify
- `scripts/little_loops/skill_expander.py` — `_find_plugin_root()` +
  `_resolve_content_path()`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:621, 675, 837, 877` — `expand_skill`
  call sites with slash-command fallbacks.
- `scripts/little_loops/cli/action.py`,
  `scripts/little_loops/cli/adapt_skills_for_codex.py`,
  `scripts/little_loops/cli/adapt_agents_for_codex.py`,
  `scripts/little_loops/cli/generate_skill_descriptions.py` — all import
  `_find_plugin_root`; verify the resolver change is safe for these (they operate
  on the source repo, so the editable path must still resolve).

### Similar Patterns
- BUG-2275 / BUG-2273 — `__file__`-escape resolver fixes (shared resolver).
- `host_runner.resolve_host()` — the host-selection source of truth for choosing
  which host skill dir to probe.

### Tests
- `scripts/tests/` — assert resolution on a simulated non-editable path; assert
  a debug/warn signal (not silent `None`) when no source resolves; assert
  host-specific dir probing for Codex.

### Documentation
- `docs/reference/API.md` — `skill_expander` resolution precedence.
- `docs/reference/HOST_COMPATIBILITY.md` — per-host skill-dir resolution.

### Configuration
- N/A

## Implementation Steps

1. Swap the escaping fallback for the shared resolver.
2. Add host-specific skill-dir probing keyed off the resolved host.
3. Add an observable signal when expansion is unavailable.
4. Add tests for the non-editable and Codex paths.
5. `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P4 — graceful degradation (no crash); but a silent perf/
  reliability regression in core automation on `pip install` / non-Claude, and a
  cross-host correctness gap. Verified: callers fall back to the slash command,
  so no hard break today.
- **Effort**: Small–Medium — resolver swap + host-dir probing + observability.
- **Risk**: Low — additive; existing fallback preserved.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/API.md` — `skill_expander` module and resolution precedence.
- `docs/reference/HOST_COMPATIBILITY.md` — per-host skill-dir resolution and `LL_HOST_CLI` env var.

## Related

- BUG-2275 — `hooks/` package data (same `__file__`-escape class).
- BUG-2273 — `_plugin_root()` resolver fix (shared resolver).
- ENH-2272 — shared resolver this should consume.
- FEAT-2274 — wheel packaging (note: `skills/` stays out of the wheel, so this
  resolver must fall through to host dirs, not the in-package tier).
- ENH-2277 — the `__file__`-escape lint that would have flagged this.

## Labels

`bug`, `host-compat`, `cross-host`, `skill-expander`, `automation`,
`path-resolution`

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-24T23:23:17 - `f6b59a7a-7a33-46b0-b1e5-64bbc39e6087.jsonl`
