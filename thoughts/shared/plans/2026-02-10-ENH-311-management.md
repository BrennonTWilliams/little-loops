# ENH-311: Add run_cmd to config and wire into manage_issue verification - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-311-add-run-cmd-and-wire-into-manage-issue.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

There is no `run_cmd` field anywhere in the codebase. The `build_cmd` field (added in ENH-310/BUG-312) provides the exact pattern to follow. After implementing changes via `manage_issue`, verification covers tests, lint, types, and build — but there's no check that the project actually starts successfully.

### Key Discoveries
- `build_cmd` at `config-schema.json:50-54` — nullable field pattern: `type: ["string", "null"]`, `default: null`
- `ProjectConfig` at `config.py:65-88` — field + `from_dict()` + `to_dict()` pattern
- `manage_issue.md:470-491` — Phase 4 null-guard verification pattern
- All 9 templates explicitly list every project command field
- `check_code.md` should NOT include `run_cmd` (per issue scope)

## Desired End State

1. `run_cmd` exists in `config-schema.json` as nullable string defaulting to `null`
2. `ProjectConfig` dataclass has `run_cmd: str | None = None`
3. All 9 templates populate `run_cmd` with appropriate values
4. `/ll:init` and `/ll:configure` support configuring `run_cmd`
5. `manage_issue` Phase 4 runs `run_cmd` as a smoke test (with null-guard)
6. Tests, docs, and README updated

### How to Verify
- `python -m pytest scripts/tests/` passes
- `ruff check scripts/` passes
- `python -m mypy scripts/little_loops/` passes
- Templates validate against updated schema
- `run_cmd` appears in configure --show output and init summary

## What We're NOT Doing

- Not adding `run_cmd` to `check_code` — that's for static checks only
- Not building a server manager — just a quick smoke test
- Not handling complex startup verification (health checks, port detection)
- Not modifying the init.md per-type inline presets beyond Java (matching existing `build_cmd` approach where most presets don't include it)

## Solution Approach

Mechanically replicate the `build_cmd` pattern across all touchpoints. The `run_cmd` is a simple nullable string command. For verification, follow the same null-guard prose pattern established by BUG-312. The `manage_issue` smoke test instruction will note that for long-running processes, the executor should start the process, wait briefly for startup, then terminate it.

## Code Reuse & Integration

- **Reuse**: Exact `build_cmd` pattern in all files — extend, not create new
- **Patterns**: Null-guard pattern from BUG-312 (`config.py:75`, `manage_issue.md:472`)
- **New code justification**: Only new code is the `run_cmd` field declaration and its references — no new abstractions needed

## Implementation Phases

### Phase 1: Schema and Python Config

#### Overview
Add `run_cmd` to the JSON schema and Python dataclass.

#### Changes Required

**File**: `config-schema.json`
Add after `build_cmd` (line 54), before the closing `}` and `additionalProperties`:
```json
"run_cmd": {
  "type": ["string", "null"],
  "description": "Command to run/start project (smoke test)",
  "default": null
}
```

**File**: `scripts/little_loops/config.py`
1. Add field to `ProjectConfig` dataclass after `build_cmd` (line 75):
   ```python
   run_cmd: str | None = None
   ```
2. Add to `from_dict()` after `build_cmd` line (line 87):
   ```python
   run_cmd=data.get("run_cmd"),
   ```
3. Add to `to_dict()` after `build_cmd` line (line 599):
   ```python
   "run_cmd": self._project.run_cmd,
   ```

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Templates

#### Overview
Add `run_cmd` to all 9 project templates.

#### Changes Required

| Template | `run_cmd` value | Rationale |
|---|---|---|
| `templates/typescript.json` | `"npm start"` | Standard Node.js start |
| `templates/javascript.json` | `"npm start"` | Standard Node.js start |
| `templates/python-generic.json` | `null` | No standard run command |
| `templates/go.json` | `"go run ."` | Standard Go run |
| `templates/rust.json` | `"cargo run"` | Standard Cargo run |
| `templates/java-maven.json` | `"mvn exec:java"` | Maven exec plugin |
| `templates/java-gradle.json` | `"./gradlew run"` | Gradle application plugin |
| `templates/dotnet.json` | `"dotnet run"` | Standard dotnet CLI |
| `templates/generic.json` | `null` | Unknown project type |

Each template: add `"run_cmd": <value>` after `"build_cmd"` line in the `project` object.

#### Success Criteria
- [ ] All templates are valid JSON
- [ ] Templates validate against updated schema

---

### Phase 3: Tests and Fixtures

#### Overview
Update test fixtures and assertions to include `run_cmd`.

#### Changes Required

**File**: `scripts/tests/test_config.py`
1. In `test_from_dict_with_all_fields` (line 68): add `"run_cmd": "npm start"` to data dict, add `assert config.run_cmd == "npm start"` after build_cmd assertion
2. In `test_from_dict_with_defaults` (line 90): add `assert config.run_cmd is None`

**File**: `scripts/tests/conftest.py`
In `sample_config` fixture (line 76): add `"run_cmd": None` after `"build_cmd": None`

**File**: `scripts/tests/test_issue_discovery.py`
In fixture (line 46): add `"run_cmd": None` after `"build_cmd": None`

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 4: Commands — manage_issue.md

#### Overview
Wire `run_cmd` into manage_issue Phase 4 verification, verification results templates, and final report.

#### Changes Required

**File**: `commands/manage_issue.md`

1. **Phase 4 verification block** (after line 485, before custom verification):
   ```
   # Run smoke test if run_cmd is configured (non-null). For long-running processes (servers), start in background, wait briefly for startup, then terminate.
   {{config.project.run_cmd}}
   ```

2. **Resolution verification results** (line 556): add `- Run: PASS` (or SKIP)

3. **Final report VERIFICATION section** (line 630): add `- run: PASS`

#### Success Criteria
- [ ] manage_issue.md is well-formed markdown
- [ ] Null-guard comment follows established pattern

---

### Phase 5: Commands — init.md and configure.md

#### Overview
Add `run_cmd` to init wizard, init summary, configure --show, configure current values, and configure interactive round.

#### Changes Required

**File**: `commands/init.md`

1. **Step 5h Round 7** (after line 735): Add a 3rd question for `run_cmd`:
   ```yaml
   - header: "Run Cmd"
     question: "Do you have a run/start command?"
     options:
       - label: "Skip (Recommended)"
         description: "No run command needed"
       - label: "npm start"
         description: "Node.js start"
       - label: "python app.py"
         description: "Python application"
       - label: "go run ."
         description: "Go application"
     multiSelect: false
   ```

2. **Configuration from Round 7 responses** (after line 764): Add:
   ```
   If user selected a run command (not "Skip"), add to configuration:
   {
     "project": {
       "run_cmd": "<selected command>"
     }
   }
   ```
   And add note: `- Only include `run_cmd` if user selected a command (not "Skip")`

3. **Display summary** (after line 959): Add:
   ```
   project.run_cmd:  [run_cmd]               # Only show if configured
   ```

**File**: `commands/configure.md`

1. **Area mapping** (line 43): Update description to include "run":
   ```
   | `project` | `project` | Test, lint, format, type-check, build, run commands |
   ```

2. **--show output** (after line 112): Add:
   ```
   run_cmd:  {{config.project.run_cmd}}     (default: none)
   ```

3. **Current values** (after line 386): Add:
   ```
   run_cmd:  {{config.project.run_cmd}}
   ```

4. **Round 2 title** (line 446): Rename to "Format, Build, and Run (3 questions)"

5. **Round 2 questions** (after line 474): Add 3rd question:
   ```yaml
   - header: "Run cmd"
     question: "Which run/start command should be used?"
     options:
       - label: "{{current run_cmd}} (keep)"
         description: "Keep current setting"
       - label: "npm start"
         description: "Node.js start"
       - label: "go run ."
         description: "Go application"
       - label: "none"
         description: "No run command"
     multiSelect: false
   ```

#### Success Criteria
- [ ] init.md is well-formed markdown
- [ ] configure.md is well-formed markdown

---

### Phase 6: Documentation

#### Overview
Update API docs and README to include `run_cmd`.

#### Changes Required

**File**: `docs/API.md`
1. Line 223: Add `run_cmd: str | None = None` to `ProjectConfig` dataclass listing

**File**: `README.md`
1. Line 130: Add `"run_cmd": null` to example JSON
2. Line 202: Add `| \`run_cmd\` | \`null\` | Optional run/start command (smoke test) |` to table

#### Success Criteria
- [ ] Docs are accurate and consistent with code

---

## Testing Strategy

### Unit Tests
- `test_from_dict_with_all_fields`: verify `run_cmd` is parsed from dict
- `test_from_dict_with_defaults`: verify `run_cmd` defaults to `None`
- Existing `BRConfig` tests via `sample_config` fixture: verify `to_dict()` serialization

### Integration
- Validate templates against updated schema (manual check)

## References

- Original issue: `.issues/enhancements/P3-ENH-311-add-run-cmd-and-wire-into-manage-issue.md`
- `build_cmd` pattern: `config-schema.json:50-54`, `config.py:75`, `config.py:87`, `config.py:599`
- Null-guard pattern: `manage_issue.md:472`, `manage_issue.md:484-485`
- BUG-312 (null guards): `.issues/completed/P2-BUG-312-commands-crash-on-null-project-commands.md`
- ENH-310 (build_cmd): `.issues/completed/P3-ENH-310-wire-build-cmd-into-check-code.md`
