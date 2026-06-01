---
id: FEAT-1851
type: FEAT
title: "ll-harness CLI \u2014 core runner implementation"
priority: P2
status: done
parent: FEAT-1689
relates_to:
- FEAT-1852
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-01 15:38:05+00:00
---

# FEAT-1851: ll-harness CLI — core runner implementation

## Summary

Create the `ll-harness` CLI binary: four runner adapters (skill, cmd, mcp, prompt), two evaluator criteria (--exit-code, --semantic), structured output formatting, and the full unit test suite. This child covers everything needed for a working, tested CLI binary.

## Parent Issue

Decomposed from FEAT-1689: add ll-harness CLI for one-shot runner evaluation

## Implementation Steps

Implements steps 1, 2, 3, 4, 5, and 14 from the parent issue.

### Step 1: Scaffold CLI entry point

Create `scripts/little_loops/cli/harness.py` with `main_harness(argv=None) -> int`, using argparse subparser dispatch (`skill`, `cmd`, `mcp`, `prompt`). Follow `action.py:189:main_action()` pattern (`subparsers.required = True`, if/elif dispatch chain to `cmd_*` handlers). Initialize with `configure_output()` + `Logger(use_color=use_color_enabled())` per `doctor.py:97` pattern. Model parser structure on `ctx_stats.py:_build_parser()` + `_parse_args()` for testability.

### Step 2: Implement runner adapters

| Subcommand | Mechanism | Key function/API |
|---|---|---|
| `skill <name> [args]` | `resolve_host().build_streaming(prompt="/ll:<name>")` → `subprocess.run([inv.binary, *inv.args])` | `host_runner.py:resolve_host()`, `subprocess_utils.py:238:run_claude_command()` |
| `cmd <shell-string>` | `subprocess.Popen(["bash", "-c", shell_string], stdout=PIPE, stderr=PIPE, text=True)` with a daemon stderr-drain thread (see `fsm/runners.py:148:DefaultActionRunner.run()` shell branch — do NOT use `subprocess.run(..., capture_output=True)` because it deadlocks when stdout and stderr both fill) | `fsm/runners.py:148:DefaultActionRunner.run()` (shell branch, threading model) |
| `mcp <server:tool> --args <JSON>` | `call_mcp_tool(server, tool, params, timeout, cwd) -> tuple[dict, int]` | `mcp_call.py:117:call_mcp_tool()` |
| `prompt <text>` | `resolve_host().build_blocking_json(prompt=text)` → subprocess | Same path as `evaluate_llm_structured()` at `fsm/evaluators.py:740` |

### Step 3: Implement evaluator

- **`--exit-code INT`**: Inline `captured_exit_code == expected` — do NOT route through `evaluate_exit_code()` at `fsm/evaluators.py:135` (FSM-only semantic).
- **`--semantic TEXT`**: Call `evaluate_llm_structured(output=captured_output, prompt=user_criterion)` at `fsm/evaluators.py:740`. Map `"yes"` → PASS (exit 0), all others (`"no"`, `"blocked"`, `"partial"`) → FAIL (exit 1). Returns `EvaluationResult(verdict, details)` (dataclass at line 48; `DEFAULT_LLM_SCHEMA` at line 61 defines the allowed verdict enum — there is no `"fail"` or `"needs_work"` verdict in this schema).
- Criteria are ANDed when both supplied.
- No criteria = always pass if runner completed.

### Step 4: Wire output formatter

Text mode: `status_block()` from `cli/output.py:266` for aligned key-value runner report. JSON mode: `print_json()` from `cli/output.py:146`. Exit code protocol: 0=PASS, 1=FAIL, 2=internal error/timeout.

> **`--output` flag implementation note**: The API spec shows `--output {text,json}` (choices), but `add_json_arg()` at `cli_args.py:197` adds `-j/--json` as a boolean flag — these are inconsistent. Implement `--output` as a proper `argparse` choices arg (`choices=["text", "json"], default="text"`) directly in `_build_harness_parser()` rather than delegating to `add_json_arg()`. The `add_json_arg()` reference in Key Anchors is a pattern reference only; do not call it for this flag.

Output format (text):
```
Runner:   skill ll:check-code
Exit:     0
Semantic: [not checked]
Result:   PASS
---
[captured stdout]
```

### Step 5: Register entry point

- `scripts/pyproject.toml` — add `ll-harness = "little_loops.cli:main_harness"` to `[project.scripts]`
- `scripts/little_loops/cli/__init__.py` — import and re-export `main_harness` (add import after line 43, add to `__all__` at lines 68–102, add `ll-harness` bullet to module docstring lines 1–33)

### Step 14: Fix test patch paths in test_cli_harness.py

Mock at the harness module's import site, not the source module:
- `"little_loops.cli.harness.evaluate_llm_structured"` (not FSM paths)
- `"little_loops.cli.harness.call_mcp_tool"`
- `"little_loops.cli.harness.resolve_host"`

Follow the pattern in `test_action.py` which patches `"little_loops.cli.action.resolve_host"`.

## Tests

Create `scripts/tests/test_cli_harness.py` following `test_cli_doctor.py` and `test_cli_ctx_stats.py` patterns:
- `TestParser` class for parser isolation
- `TestMainHarness` class for integration tests
- `patch("sys.argv", [...])` for CLI args
- `monkeypatch.chdir(tmp_path)` for isolated filesystem
- Cover all four runner types + both evaluator criteria
- Additional test patterns from:
  - `test_action.py:25` — `FakeRunner` class and `_make_completed()` helper for mocking `resolve_host()`
  - `test_mcp_call.py:31` — `_make_mcp_json()`, `_make_proc_mock()` for mocking `call_mcp_tool()`
  - `test_fsm_evaluators.py` — `_cli_stdout()` helper and `mock_cli` fixture for mocking `evaluate_llm_structured()`

## Acceptance Criteria

- `ll-harness skill <name>` invokes the skill via `host_runner.py` and exits 0 when no evaluator criteria are supplied and the runner completed without error
- `ll-harness cmd <shell-string>` executes the shell command and captures stdout, stderr, and exit code
- `ll-harness mcp <server:tool> --args <JSON>` calls the MCP tool and captures its result
- `ll-harness prompt <text>` sends a raw prompt to Claude and captures the completion
- `--exit-code INT`: exits 1 when captured exit code does not match INT; exits 0 when it matches
- `--semantic TEXT`: exits 1 when the LLM judge returns `no`, `blocked`, or `partial`; exits 0 when it returns `yes` (the `DEFAULT_LLM_SCHEMA` verdict enum is `["yes", "no", "blocked", "partial"]` — `fail`/`needs_work` are not valid verdicts)
- When both `--exit-code` and `--semantic` are supplied, both must pass for exit 0
- When no criteria are supplied, the tool exits 0 if the runner completed and 2 on timeout/internal error
- Structured pass/fail report always printed to stdout
- `--output json` produces machine-readable JSON with all fields
- `--timeout SECONDS` kills the runner after the specified time and exits 2
- All unit tests in `test_cli_harness.py` pass

## API

```
usage: ll-harness <runner-type> <target> [runner-args...] [evaluator-flags]

Runner types:
  skill <name> [args...]        Invoke a little-loops skill
  cmd <shell-string>            Run a shell command
  mcp <server:tool> [--args J]  Call an MCP tool with JSON args
  prompt <text>                 Send a raw prompt to Claude

Evaluator flags:
  --exit-code INT               Expected exit code (default: not checked)
  --semantic TEXT               Natural-language criterion for output evaluation

Global flags:
  --timeout SECONDS             Runner timeout (default: 120)
  --output {text,json}          Output format (default: text)
  --verbose                     Show full captured output even on pass

Exit codes:
  0  PASS
  1  FAIL
  2  Internal error / timeout
```

## Files to Modify

- `scripts/little_loops/cli/harness.py` — new file (create)
- `scripts/little_loops/cli/__init__.py` — import/export `main_harness`; add bullet to module docstring
- `scripts/pyproject.toml` — register `ll-harness` in `[project.scripts]`
- `scripts/tests/test_cli_harness.py` — new test file (create)

## Integration Map

### Files to Create
- `scripts/little_loops/cli/harness.py` — main implementation: `main_harness()`, `_build_harness_parser()`, `_parse_harness_args()`, `cmd_skill()`, `cmd_cmd()`, `cmd_mcp()`, `cmd_prompt()`
- `scripts/tests/test_cli_harness.py` — full unit test suite: `TestParser`, `TestMainHarness`

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.harness import main_harness` after line 43 (after `main_doctor`); add `"main_harness"` to `__all__` (lines 68–102); add `ll-harness` bullet to module docstring (lines 1–33)
- `scripts/pyproject.toml` — add `ll-harness = "little_loops.cli:main_harness"` to `[project.scripts]` (lines 49–81)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:43` — imports all `main_*` entry points; `main_harness` will be added here
- `scripts/pyproject.toml` — `[project.scripts]` registers all CLI binaries; `ll-harness` will be added here

### Similar Patterns (Follow These)
- `scripts/little_loops/cli/action.py:189` — `main_action()`: subparser dispatch pattern (`subparsers.required = True`, if/elif `cmd_*` handlers)
- `scripts/little_loops/cli/doctor.py:97` — `main_doctor(argv=None)`: initialization pattern (`configure_output()` + `Logger(use_color=use_color_enabled())`)
- `scripts/little_loops/cli/ctx_stats.py:33` — `_build_parser()` / `_parse_args(argv)`: testable parser convention (both exposed for test imports)

### Tests
- `scripts/tests/test_cli_doctor.py` — `TestParser` + `TestMainDoctor` class structure with `patch("sys.argv", ...)` pattern
- `scripts/tests/test_cli_ctx_stats.py` — `_build_parser()` testability pattern; `monkeypatch.chdir(tmp_path)` isolation
- `scripts/tests/test_action.py:25` — `FakeRunner` class and `_make_completed()` helper for mocking `resolve_host()`
- `scripts/tests/test_mcp_call.py:31` — `_make_mcp_json()` and `_make_proc_mock()` for mocking `call_mcp_tool()`
- `scripts/tests/test_fsm_evaluators.py:654` — `_cli_stdout()` static method and `mock_cli` pytest fixture for mocking `evaluate_llm_structured()`
- `scripts/tests/conftest.py` — shared fixtures: `temp_project_dir`, `sample_config`; check before duplicating in `test_cli_harness.py`

### Sibling Issue — CI-Enforced Wiring (FEAT-1852 scope, NOT this issue)

_Wiring pass added by `/ll:wire-issue`:_

Per `CONTRIBUTING.md` § "Documentation wiring for new CLI tools," every new `ll-` binary triggers five CI-enforced wiring checks. All five are owned by FEAT-1852 and must be resolved before tests pass end-to-end:

| File | What changes | Test that enforces it |
|------|-------------|----------------------|
| `commands/help.md` | One-liner in CLI TOOLS block | `test_create_extension_wiring.py` `HELP_MD` assertions |
| `.claude/CLAUDE.md` | Entry in `## CLI Tools` list | `test_create_extension_wiring.py` + `test_enh1846_doc_wiring.py` `CLAUDE_MD` assertions |
| `docs/reference/CLI.md` | New `### ll-harness` section | `test_create_extension_wiring.py` `CLI_REFERENCE` assertions |
| `skills/configure/areas.md` | Add tool name; bump count from `"Authorize all 27"` → `"Authorize all 28"` | Three assertions across both wiring test files |
| `skills/init/SKILL.md` | `"Bash(ll-harness:*)"` in permissions block; ≥3 occurrences in CLAUDE.md boilerplate | `TestFeat1689LlHarnessWiring` class (to be added in FEAT-1852) |

`scripts/tests/test_create_extension_wiring.py` and `scripts/tests/test_enh1846_doc_wiring.py` will fail until FEAT-1852 is complete. Implement FEAT-1851 first, then FEAT-1852 immediately after.

**Note on `cli/__init__.py` module docstring (lines 1–33):** Step 5 of this issue claims the docstring bullet for `ll-harness`. FEAT-1852 Step 13 also references this edit. Treat Step 5 here as authoritative — FEAT-1852 Step 13 is a cross-check only; do not edit the docstring twice.

### Mock Patch Paths (Critical)
All mocks must patch at the harness module's import site (not the source module):
- `"little_loops.cli.harness.evaluate_llm_structured"` — not `"little_loops.fsm.evaluators.evaluate_llm_structured"`
- `"little_loops.cli.harness.call_mcp_tool"` — not `"little_loops.mcp_call.call_mcp_tool"`
- `"little_loops.cli.harness.resolve_host"` — not `"little_loops.host_runner.resolve_host"`

Follow `test_action.py` which patches `"little_loops.cli.action.resolve_host"`.

## Key Anchors

- `host_runner.py:751` — `resolve_host()`
- `host_runner.py:233` — `ClaudeCodeRunner.build_streaming()`
- `host_runner.py:274` — `ClaudeCodeRunner.build_blocking_json()`
- `mcp_call.py:117` — `call_mcp_tool()`
- `fsm/evaluators.py:740` — `evaluate_llm_structured()`
- `fsm/evaluators.py:48` — `EvaluationResult` dataclass
- `fsm/evaluators.py:61` — `DEFAULT_LLM_SCHEMA`
- `cli/output.py:146` — `print_json()`
- `cli/output.py:266` — `status_block()`
- `cli/output.py:88` — `configure_output()`
- `cli/output.py:134` — `use_color_enabled()`
- `cli_args.py:100` — `add_timeout_arg()`
- `cli_args.py:197` — `add_json_arg()`
- `cli_args.py:35` — `add_config_arg()`
- `cli/__init__.py:35–66` — existing imports (add `main_harness` after line 43)
- `cli/action.py:189` — `main_action()` subcommand dispatch pattern
- `cli/doctor.py:97` — `main_doctor()` initialization pattern

## Session Log
- `/ll:ready-issue` - 2026-06-01T15:30:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13122f11-0ee8-4710-a336-a7937a2b62fe.jsonl`
- `/ll:wire-issue` - 2026-06-01T15:24:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a031dcc2-52b8-4984-967d-57ec61735487.jsonl`
- `/ll:refine-issue` - 2026-06-01T15:19:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a576143-16f9-4d6e-b5ab-6ae3bcc9684f.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1ebc34f-6a74-4ed8-b570-856978fc59ce.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7aa651d3-f8bd-4692-b1ba-bb391584ca95.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P2
