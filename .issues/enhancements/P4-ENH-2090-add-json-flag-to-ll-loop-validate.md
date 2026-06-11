---
id: ENH-2090
title: Add --json flag to ll-loop validate
type: ENH
priority: P4
status: done
captured_at: '2026-06-11T14:16:07Z'
completed_at: '2026-06-11T15:37:32Z'
discovered_date: '2026-06-11'
discovered_by: capture-issue
decision_needed: false
confidence_score: 98
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2090: Add --json flag to ll-loop validate

## Summary

`ll-loop validate` is the only subcommand in the `ll-loop` CLI that lacks a `-j`/`--json` output flag. Every other subcommand (`list`, `show`, `events`, `inspect`, `calibrate-budget`, `audit-meta`, `diagnose-evaluators`, etc.) supports structured JSON output, but `validate` emits plain text only.

## Current Behavior

`ll-loop validate <loop>` emits human-readable plain text only (e.g., `"my-loop is valid"`, warning lines, state/initial/max-iterations summary). There is no machine-parseable output mode. Automation scripts and CI pipelines that need violation details (severity, path, message) must screen-scrape this text.

## Expected Behavior

`ll-loop validate [-j | --json] <loop>` supports structured JSON output. The `-j`/`--json` flag emits `{"loop": "<name>", "valid": true/false, "violations": [...]}` to stdout. Exit code is unchanged: 0 on valid, 1 on ERROR violations. Plain-text output (no flag) is identical to current behavior.

## Motivation

Automation scripts and CI pipelines that want to programmatically consume validation results (violation severity, rule IDs, loop name) currently have to screen-scrape the human-readable output. A `--json` flag would allow tools like `ll-loop validate --json my-loop | jq '.violations[]'` to work without fragile text parsing.

## Implementation Steps

1. **Add argparse argument** (`scripts/little_loops/cli/loop/__init__.py`, after line 270): add `validate_parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")` — identical wording to `audit-meta` at line 593 and `diagnose-evaluators` at line 677.

2. **Update dispatch** (`scripts/little_loops/cli/loop/__init__.py`, line 719): change `cmd_validate(args.loop, loops_dir, logger)` to `cmd_validate(args.loop, args, loops_dir, logger)` — mirroring `cmd_audit_meta(args.loop, args, loops_dir)` at line 743 and `cmd_diagnose_evaluators(args.loop, args, loops_dir)` at line 747.

3. **Update handler** (`scripts/little_loops/cli/loop/config_cmds.py`, `cmd_validate`):
   - Add `args: argparse.Namespace` parameter (before `logger`).
   - Import `print_json` from `little_loops.cli.output`.
   - When `getattr(args, "json", False)`: call `validate_fsm(fsm)` directly (from `little_loops.fsm.validation`) on the parsed FSM dict — do NOT rely on `load_and_validate`'s `ValueError` path, since that joins all error messages into a single string and discards individual `ValidationError` objects. Calling `validate_fsm` directly returns the full `list[ValidationError]` for both ERROR and WARNING items.
   - Build output: `{"loop": loop_name, "valid": bool, "violations": [{"severity": v.severity.value, "path": v.path, "message": v.message} for v in violations]}`. Note: `ValidationError` has no `rule` field — the rule ID (e.g. `MR-1`) appears in `v.message` only; drop the `"rule"` key from the schema or parse it out of the message string.
   - Call `print_json(result)` and return `0` if valid, `1` if any ERROR violations (matching existing exit-code contract).

4. **Add tests** to `scripts/tests/test_ll_loop_commands.py` in class `TestCmdValidate`:
   - `test_validate_json_output_valid_loop` — `args = argparse.Namespace(json=True)`, assert `json.loads(out)` has `valid: true, violations: []`.
   - `test_validate_json_output_invalid_loop` — loop with an ERROR violation, assert `valid: false, violations` non-empty.
   - `test_validate_json_no_flag_unchanged` — `args = argparse.Namespace(json=False)`, assert existing plain-text output is unmodified.
   - Also add dispatch coverage to `scripts/tests/test_cli_loop_dispatch.py` for `--json` flag threading.

## Acceptance Criteria

- `ll-loop validate <loop>` (no flag) output is unchanged
- `ll-loop validate --json <loop>` exits 0 on valid loop and prints JSON: `{"loop": "...", "valid": true, "violations": []}`
- `ll-loop validate --json <loop>` exits non-zero on invalid loop and prints JSON: `{"loop": "...", "valid": false, "violations": [{"severity": "ERROR", "path": "...", "message": "..."}]}`
- `-j` short form works as alias

## API/Interface

### CLI Flag

```
ll-loop validate [-j | --json] <loop>
```

### JSON Output Schema

Success (exit 0):
```json
{"loop": "<loop-name>", "valid": true, "violations": []}
```

Failure (exit non-zero):
```json
{"loop": "<loop-name>", "valid": false, "violations": [{"severity": "ERROR", "path": "...", "message": "..."}]}
```

## Proposed Solution

_Added by `/ll:refine-issue` — codebase research confirms two viable implementation paths; pick one before wiring._

### Option A: Omit `rule` field — keep `ValidationError` unchanged

> **Selected:** Option A — zero infrastructure changes; serializes directly from `ValidationError`'s existing 3 fields, matching all existing JSON output patterns exactly.

`ValidationError` at `validation.py:42` has only `message`, `path`, and `severity`. Do not add a `rule` field. Emit violations without rule codes:

```json
{"loop": "my-loop", "valid": false, "violations": [{"severity": "ERROR", "path": "states.check", "message": "[ERROR] states.check: ..."}]}
```

Implementation delta beyond step 3: none — serialize `v.severity.value`, `v.path`, `v.message` directly. Update Acceptance Criteria to drop `"rule"` from the output spec.

**Trade-off**: Minimal scope (0 additional file touches); `"rule"` key absent from output, which differs from the original Acceptance Criteria spec. Filtering by rule in CI still works via `jq 'select(.message | test("MR-1"))'`.

### Option B: Add `rule: str | None = None` to `ValidationError`

Extend `@dataclass class ValidationError` at `validation.py:42` with `rule: str | None = None`. Populate rule codes at each `_validate_*` call site that creates a `ValidationError` for an MR-coded rule (approximately 7 sites: `_validate_meta_loop_self_eval`, `_validate_per_run_isolation`, `_validate_partial_routes`, `_validate_artifact_overwrite`, `_validate_generator_fix_discipline`, and related helpers). Emits:

```json
{"loop": "my-loop", "valid": false, "violations": [{"rule": "MR-1", "severity": "ERROR", "message": "..."}]}
```

**Trade-off**: Matches the original Acceptance Criteria exactly; extends `ValidationError` API and touches ~7 validation functions — higher change surface (contradicts `score_change_surface: 23` which assumed no dataclass change).

---

**Note on getting structured violations**: Both options require calling `validate_fsm(fsm: FSMLoop)` directly (`validation.py:865`) rather than catching the `ValueError` from `load_and_validate` — the exception path joins all `ValidationError` objects into a single string and discards the structured objects (`validation.py:1957`). The cleanest approach is to add `raise_on_error: bool = True` to `load_and_validate`; when `False`, return `(fsm, all_violations)` including ERROR-severity items instead of raising. This is a 2-line change with full backward compatibility.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-11.

**Selected**: Option A — Omit `rule` field

**Reasoning**: Every existing JSON-output subcommand in `cli/loop/` (`cmd_audit_meta`, `cmd_diagnose_evaluators`, `cmd_calibrate_budget`) uses the identical `getattr(args, "json", False)` → plain dict → `print_json()` pattern, and none include rule-code keys in their output dicts. `ValidationError`'s existing `severity.value`, `path`, and `message` fields serialize directly with zero dataclass changes, while Option B requires modifying 6+ call sites and introducing a `rule` concept with no existing precedent in the codebase. CI rule-based filtering remains fully supported via `jq 'select(.message | test("MR-1"))'`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- **Option A**: `print_json` has 15 call sites in `cli/loop/` with no rule-code fields; `ValidationError` 3-field serialization has direct precedent in `docs.py` violations output; reuse score 3/3.
- **Option B**: Only 6 MR-coded `ValidationError(` call sites in `validation.py` (not 7 as estimated); adds `rule` field concept with no existing dataclass precedent; reuse score 2/3.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `-j`/`--json` argument to `validate` subparser (~line 270)
- `scripts/little_loops/cli/loop/config_cmds.py` — update `cmd_validate` to accept `json_output: bool` and return structured dict serialized via `json.dumps`
- `scripts/little_loops/cli/loop/__init__.py` — thread `args.json` flag through dispatch (~line 719)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:719` — the only caller, via the `main_loop` dispatch table; no other callers of `cmd_validate` exist in the codebase

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py:593` — `audit_meta_parser.add_argument("-j", "--json", ...)` — closest match: same `(loop_name, args, loops_dir)` dispatch signature
- `scripts/little_loops/cli/loop/__init__.py:677` — `diagnose_eval_parser.add_argument("-j", "--json", ...)` — another close match with identical dispatch shape
- `scripts/little_loops/cli/loop/info.py:cmd_audit_meta` — uses `as_json = getattr(args, "json", False)` then `print_json(result)` where result is a plain dict
- `scripts/little_loops/cli/output.py:146` — `print_json(data: Any)` utility: `print(json.dumps(data, indent=2))`; import via `from little_loops.cli.output import print_json`
- `scripts/tests/test_ll_loop_commands.py:4143` — `TestCmdAuditMeta.test_json_output` — canonical test shape: `args = argparse.Namespace(json=True, ...)`, `data = json.loads(capsys.readouterr().out)`, field assertions

### Tests
- `scripts/tests/test_ll_loop_commands.py:TestCmdValidate` (line 32) — add `test_validate_json_output_valid_loop`, `test_validate_json_output_invalid_loop`, `test_validate_json_no_flag_unchanged`; model after `TestCmdAuditMeta.test_json_output` at line 4143
- `scripts/tests/test_cli_loop_dispatch.py` (line 113) — add test that `--json` argument is forwarded to `cmd_validate`; model after existing `test_validate_routes_to_handler` at line 113

### Documentation
- No user-facing documentation updates required; the `--json` flag follows the established pattern shared by all other `ll-loop` subcommands and needs no separate doc entry

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Add `-j`/`--json` flag to `ll-loop validate` only
- **Out of scope**: Adding a `rule` field to `ValidationError` dataclass (Option B, rejected in decision)
- **Out of scope**: Changing existing plain-text output format or exit-code contract
- **Out of scope**: Adding `--json` to other subcommands not yet supporting it

## Impact

- **Priority**: P4 — Low-priority convenience enhancement; human-readable output already works; unblocks CI consumption without workarounds
- **Effort**: Small — 3 file touches (~30 LOC total), zero new patterns introduced; mirrors `cmd_audit_meta` / `cmd_diagnose_evaluators` exactly
- **Risk**: Low — additive change only; no-flag path is unchanged; no dataclass modifications; `validate_fsm` return type already matches required shape
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `ll-loop`, `json-output`

## Status

**Open** | Created: 2026-06-11 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-11_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 84/100 → MODERATE

### Concerns
- `ValidationError` (`validation.py:42`) has no `rule` field — only `message`, `path`, and `severity`. The proposed JSON schema's `"rule": "MR-1"` field requires either extending the `ValidationError` dataclass or adjusting the output contract (omitting the field).
- `load_and_validate` raises `ValueError` for ERROR violations rather than returning them (`validation.py:2026-2030`); `cmd_validate` currently catches that string. To emit structured JSON violations, the implementation must call `validate_fsm(fsm)` directly (returns `list[ValidationError]`) rather than relying on the exception path.

## Session Log
- `/ll:manage-issue` - 2026-06-11T15:37:32Z - `47e0b897-3dc6-4117-9ba4-1222707b8b98`
- `/ll:ready-issue` - 2026-06-11T15:20:50 - `a01fec71-0a4e-4029-8c18-edc40ce7717c.jsonl`
- `/ll:confidence-check` - 2026-06-11T16:00:00Z - `0febcaae-9365-490a-b446-2b30c08b4e9c.jsonl`
- `/ll:confidence-check` - 2026-06-11T15:00:00Z - `dcc36295-fb1b-49bd-bb72-f68aff2d3419.jsonl`
- `/ll:decide-issue` - 2026-06-11T14:43:56 - `b908eae0-baef-4dab-8828-7fd57d5505a4.jsonl`
- `/ll:refine-issue` - 2026-06-11T14:36:04 - `41d139e6-44f8-448f-95a0-11a5cf951d59.jsonl`
- `/ll:refine-issue` - 2026-06-11T14:29:23 - `35c55bfd-d6d9-4537-b69b-ecb638a3f67e.jsonl`
- `/ll:format-issue` - 2026-06-11T14:18:31 - `d3fa518c-9d69-470c-ab22-c70fc207d941.jsonl`
- `/ll:capture-issue` - 2026-06-11T14:16:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
