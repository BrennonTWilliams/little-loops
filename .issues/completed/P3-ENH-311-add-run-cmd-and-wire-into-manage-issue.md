---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# ENH-311: Add run_cmd to config and wire into manage_issue verification

## Summary

Add a `run_cmd` field to the project config schema for starting/running the project (e.g., `npm start`, `python app.py`, `go run .`). Wire it into `/ll:manage_issue` verification phase so that after implementation, the project can be smoke-tested to confirm it still runs.

## Context

Identified from conversation discussing whether `ll-config` should capture the run command alongside the existing build command. `build_cmd` is a one-shot compilation check, while `run_cmd` covers actually starting the project — important for web apps, APIs, and CLI tools.

## Current Behavior

There is no `run_cmd` in the config schema. After implementing an issue via `manage_issue`, verification only covers tests, lint, and type checking — there's no check that the project actually starts successfully.

## Expected Behavior

1. `run_cmd` exists in `config-schema.json` under `project` (nullable string, default null)
2. Project templates populate `run_cmd` where applicable (e.g., `npm start` for TS, `go run .` for Go)
3. `/ll:init` and `/ll:configure` support configuring `run_cmd`
4. `/ll:manage_issue` verification phase runs `run_cmd` (if configured) as a smoke test

## Proposed Solution

### Schema & Config
- Add `run_cmd` to `config-schema.json` `project.properties` (type: `["string", "null"]`, default: `null`)
- Add `run_cmd` to `ProjectConfig` dataclass in `config.py`
- Update templates that have meaningful run commands (typescript, go, java, rust, dotnet)
- Update `commands/init.md` and `commands/configure.md` to include `run_cmd`

### Verification Integration
- In `manage_issue` verification phase, if `run_cmd` is configured (non-null):
  - Run the command with a short timeout (e.g., 10s)
  - Check for startup success (exit code 0 or expected output)
  - For long-running processes (servers), start in background, wait briefly for startup, then kill
  - If `run_cmd` is null, skip silently and report `SKIP` status — do NOT attempt to execute
- This is the trickiest part — need to handle both one-shot CLIs and long-running servers

### Null Guard Pattern
Follow the same null-guard pattern established by BUG-312 for other nullable commands. The `manage_issue` verification block for `run_cmd` must include an explicit instruction: "Run smoke test if `run_cmd` is configured (non-null). Skip silently if not configured." This prevents the template from interpolating a null value into a bash command.

## Current Pain Point

After implementing changes via `manage_issue`, there's no automated check that the project still starts. Build verification (if wired) catches compilation errors, but runtime startup failures (missing env vars, broken imports, config errors) go undetected until manual testing.

## Scope Boundaries

- Keep `run_cmd` simple — a single string command, not a complex server management system
- Don't build a full "dev server manager" — just a quick smoke test
- Don't add `run_cmd` to `check_code` (that's for static checks only)
- Don't attempt to verify application behavior beyond startup success

## Backwards Compatibility

- `run_cmd` defaults to `null`, so existing configs are unaffected
- Verification phase only uses it if configured — no change for projects without it

## Impact

- **Priority**: P3
- **Effort**: Medium — schema, config, templates, init, configure, and manage_issue changes
- **Risk**: Low-Medium — the server smoke test logic needs care to handle timeouts and background processes correctly

## Dependencies

- **BUG-312**: Adds null guards to existing commands (`lint_cmd`, `type_cmd`, `format_cmd`, `test_cmd`, `build_cmd`). ENH-311 should follow the same pattern for `run_cmd`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `config-schema.json`: Added `run_cmd` property (nullable string, default null)
- `scripts/little_loops/config.py`: Added `run_cmd` field to ProjectConfig dataclass, from_dict, to_dict
- `templates/*.json` (9 files): Added `run_cmd` to all project templates
- `commands/manage_issue.md`: Added `run_cmd` smoke test to Phase 4 verification with null-guard
- `commands/init.md`: Added `run_cmd` to interactive wizard (Round 7), summary display
- `commands/configure.md`: Added `run_cmd` to --show, current values, interactive Round 2
- `scripts/tests/test_config.py`: Added `run_cmd` test assertions
- `scripts/tests/conftest.py`: Added `run_cmd` to sample_config fixture
- `scripts/tests/test_issue_discovery.py`: Added `run_cmd` to test fixture
- `docs/API.md`: Added `run_cmd` to ProjectConfig listing
- `README.md`: Added `run_cmd` to config example and table

### Verification Results
- Tests: PASS (2660 passed)
- Lint: PASS
- Types: PASS
- Run: SKIP (not configured for this project)
- Integration: PASS
