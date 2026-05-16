---
id: FEAT-1525
type: FEAT
priority: P4
status: open
captured_at: '2026-05-16T00:00:00Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1503
blocked_by:
- FEAT-1523
labels:
- host-compat
- preflight
---

# FEAT-1525: ll-action capabilities — emit full CapabilityReport + doc update

## Summary

Update `action.py:cmd_capabilities()` to serialize the full `CapabilityReport` dataclass to JSON, update `test_action.py` to match the new shape, and update `docs/reference/CLI.md` to document the new output.

## Parent Issue

Decomposed from FEAT-1503: ll-doctor — CLI tool and ll-action capabilities update

## Scope

Covers implementation steps 3, 4, 6 from the parent issue.

**Depends on**: FEAT-1523 (CapabilityReport dataclass must land first)

## Current Behavior

`ll-action capabilities` (`scripts/little_loops/cli/action.py:140` — `cmd_capabilities()`) emits only a minimal JSON shape:
```json
{"available": true, "version": "...", "supported_skills": [...]}
```
It does not surface invocation-mode capabilities, hook installation status, or per-feature gaps.

## Expected Behavior

`ll-action capabilities --json` emits the full `CapabilityReport` dataclass serialized to JSON, identical in structure to what `ll-doctor` consumes — one data source, two presentations:

```json
{
  "host": "claude-code",
  "binary": "claude",
  "version": "...",
  "invocation_modes": [{"name": "agent_select", "supported": true, "description": "..."}, ...],
  "hooks": [{"intent": "session_start", "status": "installed"}, ...],
  "critical_gaps": []
}
```

## Proposed Solution

### Step 3: Update `scripts/little_loops/cli/action.py:140`

`cmd_capabilities()` currently emits minimal JSON; update to serialize the full `CapabilityReport` via `dataclasses.asdict()`. **Do this atomically with step 4** (test updates) to avoid a broken-tests window.

### Step 4: Update `scripts/tests/test_action.py`

Must be done in the same pass as step 3:

- **`FakeRunner` (lines 25-48)**: Add `describe_capabilities()` stub returning a minimal `CapabilityReport` matching FEAT-1523's shape. Existing stub pattern: each `build_*` method returns `HostInvocation(binary="claude", args=[...])`.
- **`TestCmdCapabilities` (lines 308-404, `TestCmdList` starts at 405)**: Update assertions using `capsys.readouterr().out` → `json.loads(...)` to match the new `CapabilityReport` JSON shape. Each test patches: `little_loops.cli.action.resolve_host`, `little_loops.cli.action.subprocess.run`, and `little_loops.cli.action._find_plugin_root`.
- **`TestMainAction.test_capabilities_subcommand_dispatch` (lines 452-468)**: Update accordingly.

### Step 6: Update `docs/reference/CLI.md`

The `#### capabilities` section (lines 63-68) contains a verbatim JSON code block showing the old shape. Update to reflect the new `CapabilityReport` shape in the same pass as step 3 — this documents the changed output and must not be deferred to FEAT-1496.

## Acceptance Criteria

- [ ] `ll-action capabilities --json` emits the full `CapabilityReport` shape (not the old `{available, version, supported_skills}` shape)
- [ ] `scripts/tests/test_action.py` updated: `FakeRunner` gets `describe_capabilities()` stub; `TestCmdCapabilities` (lines 308-404) assertions updated for new JSON shape; `TestMainAction.test_capabilities_subcommand_dispatch` (lines 452-468) updated accordingly
- [ ] `docs/reference/CLI.md` `#### capabilities` section reflects new JSON shape
- [ ] All existing tests pass: `python -m pytest scripts/tests/test_action.py -v && ruff check scripts/ && python -m mypy scripts/little_loops/`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/action.py` — update `cmd_capabilities()` (line 140) to serialize full `CapabilityReport`
- `scripts/tests/test_action.py` — add `describe_capabilities()` stub to `FakeRunner` (lines 25-48); update `TestCmdCapabilities` (lines 308-404) and `TestMainAction.test_capabilities_subcommand_dispatch` (lines 452-468)
- `docs/reference/CLI.md` — update `#### capabilities` section (lines 63-68) JSON block

### Dependent Files (Callers)

**Zero runtime consumers confirmed**: Full codebase grep found no callers of `ll-action capabilities` in `.loops/` FSM YAML files, `hooks/`, `skills/`, or `commands/`. The JSON shape change carries no downstream breakage risk beyond `test_action.py` assertions.

### Anchor References

- `cmd_capabilities()` at `scripts/little_loops/cli/action.py:140`
- `FakeRunner` at `scripts/tests/test_action.py:25-48`
- `TestCmdCapabilities` at `scripts/tests/test_action.py:308-404`
- `TestMainAction.test_capabilities_subcommand_dispatch` at `scripts/tests/test_action.py:452-468`
- `docs/reference/CLI.md` `#### capabilities` at lines 63-68

## Impact

- **Priority**: P4 — Enables downstream tooling to consume authoritative capability data
- **Effort**: Small — Refactor of existing function + test updates + one doc block
- **Risk**: Low — No runtime consumers outside test suite (confirmed by codebase grep)
- **Breaking Change**: Yes (minor) — `ll-action capabilities --json` output shape changes; only `test_action.py` requires updates

## Session Log
- `/ll:issue-size-review` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e46d252d-d6ba-4cf5-9954-c3c6cea402e5.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P4
