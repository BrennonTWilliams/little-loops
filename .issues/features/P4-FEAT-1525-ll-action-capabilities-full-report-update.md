---
id: FEAT-1525
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T00:00:00Z'
completed_at: '2026-05-16T18:29:43Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1503
blocked_by: []
labels:
- host-compat
- preflight
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
  "version": "1.0.3",
  "capabilities": [
    {"name": "streaming", "status": "full", "note": ""},
    {"name": "permission_skip", "status": "full", "note": ""},
    {"name": "agent_select", "status": "full", "note": ""},
    {"name": "tool_allowlist", "status": "full", "note": ""},
    {"name": "json_schema", "status": "unsupported", "note": "claude CLI does not accept an inline schema flag; parameter is silently dropped"}
  ],
  "hooks": [
    {"name": "session_start", "status": "installed", "note": ""}
  ]
}
```

> **Note**: The actual `CapabilityReport` dataclass fields are `capabilities` (not `invocation_modes`) and `hooks` with `{name, status, note}` entries. There is no `critical_gaps` field. The `version` field in `CapabilityReport` is always `""` from `describe_capabilities()` — the live version must still be fetched via the existing `build_version_check()` subprocess call and merged into the serialized output.

## Proposed Solution

### Step 3: Update `scripts/little_loops/cli/action.py:140`

`cmd_capabilities()` currently emits minimal JSON; update to serialize the full `CapabilityReport` using manual dict construction — **do not use `dataclasses.asdict()`** (unused in this codebase). **Do this atomically with step 4** (test updates) to avoid a broken-tests window.

Implementation pattern (follow `doctor.py:_print_report()` at `scripts/little_loops/cli/doctor.py:29-43`):

```python
runner = resolve_host()
report = runner.describe_capabilities()

# Still run version check subprocess — describe_capabilities() always returns version=""
available = runner.detect()
version = ""
if available:
    try:
        inv = runner.build_version_check()
        proc = subprocess.run([inv.binary, *inv.args], capture_output=True, text=True, timeout=5)
        version = proc.stdout.strip()
    except (TimeoutExpired, FileNotFoundError, OSError):
        available = False

data = {
    "host": report.host,
    "binary": report.binary,
    "version": version,
    "capabilities": [
        {"name": c.name, "status": c.status, "note": c.note}
        for c in report.capabilities
    ],
    "hooks": [
        {"name": h.name, "status": h.status, "note": h.note}
        for h in report.hooks
    ],
}
print_json(data)
return 0
```

### Step 4: Update `scripts/tests/test_action.py`

Must be done in the same pass as step 3:

- **`FakeRunner` (lines 25-51)**: `describe_capabilities()` stub **already exists** at line 49-50, returning `CapabilityReport(host="fake", binary="fake", version="0.0")`. No change needed to `FakeRunner` itself.
- **`TestCmdCapabilities` (lines 311-401)**: Update assertions using `capsys.readouterr().out` → `json.loads(...)` to match the new JSON shape. Tests currently assert `output["available"]`, `output["version"]`, `output["supported_skills"]` — update to assert `output["host"]`, `output["binary"]`, `output["version"]`, `output["capabilities"]`, `output["hooks"]`. Pattern for nested entry assertions: `by_name = {e["name"]: e for e in output["capabilities"]}` (analogous to `by_name = {e.name: e for e in report.capabilities}` in `test_host_runner.py:TestDescribeCapabilities`).
- **`TestMainAction.test_capabilities_subcommand_dispatch` (lines 455-471)**: Update accordingly.

> **Imports in test_action.py already available**: `CapabilityReport, HostCapabilities, HostInvocation` are already imported from `little_loops.host_runner`.

### Step 6: Update `docs/reference/CLI.md`

The `#### capabilities` section (lines 63-68) contains a verbatim JSON code block showing the old shape. Update to reflect the new `CapabilityReport` shape in the same pass as step 3 — this documents the changed output and must not be deferred to FEAT-1496.

### Step 7: Update subparser help strings in `main_action()` (added by `/ll:wire-issue`)

In the same pass as Step 3, update the `add_parser()` call for the `capabilities` subcommand (~line 231-232 of `action.py`):
- `help=` from "Check Claude availability and list supported skills" → "Emit full CapabilityReport as JSON (host, binary, version, capabilities, hooks)"
- `description=` from "Probe claude availability and return supported skill names as JSON" → "Call describe_capabilities() and serialize the full CapabilityReport to JSON"

### Step 8: Update `docs/reference/API.md` consumer annotations (added by `/ll:wire-issue`)

After the implementation lands, update two "Used by" annotations in `docs/reference/API.md`:
- `### CapabilityReport` section (~line 5838): append `ll-action capabilities` to the "consumed by" list alongside `ll-doctor`
- `### describe_capabilities` section (~line 5785): append `ll-action` to the "Used by" annotation

Also update `docs/ARCHITECTURE.md` HostRunner table row (~line 565): `describe_capabilities()` annotation → mention both `ll-doctor` and `ll-action`.

## Acceptance Criteria

- [ ] `ll-action capabilities --json` emits the full `CapabilityReport` shape (not the old `{available, version, supported_skills}` shape)
- [ ] `scripts/tests/test_action.py` updated: `FakeRunner` gets `describe_capabilities()` stub; `TestCmdCapabilities` (lines 311-401) assertions updated for new JSON shape; `TestMainAction.test_capabilities_subcommand_dispatch` (lines 455-471) updated accordingly
- [ ] `docs/reference/CLI.md` `#### capabilities` section reflects new JSON shape
- [ ] All existing tests pass: `python -m pytest scripts/tests/test_action.py -v && ruff check scripts/ && python -m mypy scripts/little_loops/`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/action.py` — update `cmd_capabilities()` (line 140) to serialize full `CapabilityReport`
- `scripts/tests/test_action.py` — add `describe_capabilities()` stub to `FakeRunner` (lines 25-48); update `TestCmdCapabilities` (lines 311-401) and `TestMainAction.test_capabilities_subcommand_dispatch` (lines 455-471)
- `docs/reference/CLI.md` — update `#### capabilities` section (lines 63-68) JSON block

### Dependent Files (Callers)

**Zero runtime consumers confirmed**: Full codebase grep found no callers of `ll-action capabilities` in `.loops/` FSM YAML files, `hooks/`, `skills/`, or `commands/`. The JSON shape change carries no downstream breakage risk beyond `test_action.py` assertions.

### CLI Help Text Coupling

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — `main_action()` subparser for `capabilities` at lines ~231-232 has stale `help=` ("Check Claude availability and list supported skills") and `description=` ("Probe claude availability and return supported skill names as JSON") strings that describe the old output; update in the same pass as `cmd_capabilities()` (Step 3)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### CapabilityReport` section (~line 5838): "consumed by `ll-doctor`" becomes incomplete — add `ll-action capabilities` as a second consumer
- `docs/reference/API.md` — `### describe_capabilities` section (~line 5785): "Used by `ll-doctor`" becomes incomplete — add `ll-action` as a second caller
- `docs/ARCHITECTURE.md` — `HostRunner` table row (~line 565): `describe_capabilities()` annotation says "Used by `ll-doctor`" only — add `ll-action` after FEAT-1525 lands

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — `TestMainAction.test_capabilities_subcommand_dispatch` (line ~455) patches `_find_plugin_root` which is used for `_load_skills()` (the old `supported_skills` path); once `cmd_capabilities()` no longer calls `_load_skills()`, this patch becomes unnecessary — verify and remove the `_find_plugin_root` patch (and the `subprocess.run` mock for version check if version now comes from `describe_capabilities()`) to keep the test clean

### Anchor References

- `cmd_capabilities()` at `scripts/little_loops/cli/action.py:140`
- `FakeRunner` at `scripts/tests/test_action.py:25-51` (includes `describe_capabilities()` stub at line 49-50)
- `TestCmdCapabilities` at `scripts/tests/test_action.py:311-401`
- `TestMainAction.test_capabilities_subcommand_dispatch` at `scripts/tests/test_action.py:455-471`
- `docs/reference/CLI.md` `#### capabilities` at lines 63-69

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/doctor.py:29-43` — `_print_report()` is the sole existing `CapabilityReport` → JSON serializer; use manual dict construction (not `dataclasses.asdict`) following this exact pattern
- `scripts/little_loops/host_runner.py` — `CapabilityReport` fields are `host`, `binary`, `version`, `capabilities: list[CapabilityEntry]`, `hooks: list[HookEntry]`; `CapabilityEntry` has `name`, `status: Literal["full","partial","unsupported"]`, `note: str = ""`; `HookEntry` has `name`, `status: Literal["installed","registered","deferred","absent"]`, `note: str = ""`
- `scripts/tests/test_action.py:49-50` — `FakeRunner.describe_capabilities()` stub already exists; returns `CapabilityReport(host="fake", binary="fake", version="0.0")`; no new stub code needed
- `scripts/tests/test_host_runner.py:TestDescribeCapabilities` — established assertion pattern: `by_name = {e.name: e for e in report.capabilities}` for per-entry status checks
- `scripts/little_loops/cli/action.py:output.py` — `print_json()` from `little_loops.cli.output` wraps `json.dumps(data, indent=2)` — preferred over direct `json.dumps` call in action.py context

## Impact

- **Priority**: P4 — Enables downstream tooling to consume authoritative capability data
- **Effort**: Small — Refactor of existing function + test updates + one doc block
- **Risk**: Low — No runtime consumers outside test suite (confirmed by codebase grep)
- **Breaking Change**: Yes (minor) — `ll-action capabilities --json` output shape changes; only `test_action.py` requires updates

## Resolution

Implemented in a single atomic pass:

- `scripts/little_loops/cli/action.py`: `cmd_capabilities()` now calls `describe_capabilities()` and serializes the full `CapabilityReport` (host, binary, version, capabilities, hooks). The `_load_skills()` call is removed. Subparser help/description strings updated.
- `scripts/tests/test_action.py`: `TestCmdCapabilities` rewritten with 3 tests asserting the new JSON shape; `_find_plugin_root` patch removed from all capabilities tests (no longer needed). `test_capabilities_subcommand_dispatch` cleaned up likewise.
- `docs/reference/CLI.md`: `#### capabilities` section updated with full `CapabilityReport` JSON example.
- `docs/reference/API.md`: `describe_capabilities()` and `CapabilityReport` annotations updated to mention `ll-action` as a second consumer.
- `docs/ARCHITECTURE.md`: `CapabilityReport` table row updated to mention `ll-action`.

All 29 tests pass; ruff and mypy clean (pre-existing wcwidth stub error unaffected).

## Session Log
- `/ll:manage-issue` - 2026-05-16T18:29:43Z
- `/ll:ready-issue` - 2026-05-16T18:27:49 - `4d0b9e47-0438-4e1a-bf13-271f02560f60.jsonl`
- `/ll:wire-issue` - 2026-05-16T17:58:09 - `fa4d9ca8-62c1-4c40-8c54-f81e3acfa41f.jsonl`
- `/ll:refine-issue` - 2026-05-16T17:53:27 - `521cf227-5d1b-4bb2-9f7e-ccbe7e166f81.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `ea1ee27a-726a-42ef-9081-31c93c65115f.jsonl`
- `/ll:issue-size-review` - 2026-05-16T00:00:00Z - `e46d252d-d6ba-4cf5-9954-c3c6cea402e5.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P4
