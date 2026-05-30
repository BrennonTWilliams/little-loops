---
id: FEAT-1689
type: FEAT
title: add ll-harness CLI for one-shot runner evaluation
priority: P2
status: open
discovered_date: 2026-05-25
discovered_by: capture-issue
captured_at: '2026-05-25T00:00:03Z'
labels:
- cli
- harness
- evaluation
- captured
parent: EPIC-1744
confidence_score: 100
outcome_confidence: 74
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
decision_needed: true
implementation_order_risk: true
---

# FEAT-1689: add ll-harness CLI for one-shot runner evaluation

## Summary

Add an `ll-harness` CLI that runs any supported runner (skill, shell command, MCP tool, or raw prompt) once, evaluates the output against user-supplied criteria, and exits 0 on pass / non-zero on fail. Unlike `ll-loop run`, there is no FSM retry machinery — this is a gate tool for CI, spot-checking, and quick iteration feedback.

## Current Behavior

There is no way to evaluate a single skill invocation (or any other runner) against pass/fail criteria without authoring a full FSM loop YAML. The closest tools are `ll-loop run` (requires a loop file), `ll-action` (invokes a skill as one-shot but produces no evaluation), and the eval harness skill `/ll:create-eval-from-issues` (generates a YAML, doesn't run an inline check).

## Expected Behavior

```
ll-harness skill ll:check-code               # run skill, evaluate exit code
ll-harness cmd "python -m pytest scripts/"   # run shell command, evaluate exit code
ll-harness mcp pencil:get_screenshot --args '{"node_id":"123"}' --semantic "screenshot shows a login form"
ll-harness prompt "Summarize this file: ..."  --semantic "summary mentions Python"
```

The CLI:
1. Dispatches to the appropriate runner based on the first positional argument (`skill`, `cmd`, `mcp`, `prompt`)
2. Captures stdout, stderr, and exit code
3. Evaluates the output against the supplied criteria (`--exit-code INT`, `--semantic TEXT`, or both)
4. Prints a structured pass/fail report to stdout
5. Exits 0 on pass, 1 on fail, 2 on internal error

## Acceptance Criteria

- `ll-harness skill <name>` invokes the skill via `host_runner.py` and exits 0 when no evaluator criteria are supplied and the runner completed without error
- `ll-harness cmd <shell-string>` executes the shell command and captures stdout, stderr, and exit code
- `ll-harness mcp <server:tool> --args <JSON>` calls the MCP tool and captures its result
- `ll-harness prompt <text>` sends a raw prompt to Claude and captures the completion
- `--exit-code INT`: exits 1 when captured exit code does not match INT; exits 0 when it matches
- `--semantic TEXT`: exits 1 when the LLM judge returns `fail` or `needs_work`; exits 0 on `pass`
- When both `--exit-code` and `--semantic` are supplied, both must pass for exit 0 (criteria are ANDed)
- When no criteria are supplied, the tool exits 0 if the runner completed and 2 on timeout/internal error
- Structured pass/fail report is always printed to stdout in the format specified under "Output format"
- `--output json` produces machine-readable JSON with all fields (runner, exit, semantic, result, output)
- `--timeout SECONDS` kills the runner after the specified time and exits 2

## Motivation

Fills the gap between "run a thing" and "evaluate a thing" without requiring loop authorship. Key use cases:
- **CI gates**: `ll-harness skill ll:check-code --exit-code 0` in a pre-push hook
- **Spot-checking**: quickly verify a skill or prompt meets a bar during development without creating a loop YAML
- **Debugging**: isolate a single runner to confirm output before wiring it into a loop
- **Prompt evaluation**: test a raw prompt against criteria before promoting it to a skill

## Use Case

A developer adds a new skill and wants to confirm it produces acceptable output before publishing. They run `ll-harness skill ll:my-new-skill --semantic "output contains a summary section"`. The CLI invokes the skill, runs a semantic check against the criterion, prints `PASS` or `FAIL` with the captured output, and exits appropriately. No loop file needed, no issue required.

## Proposed Solution

### Runner dispatch

Four runner types, each mapping to existing infrastructure:

| Subcommand | Mechanism | Notes |
|---|---|---|
| `skill <name> [args]` | `resolve_host().build_streaming(...)` + skill invocation | Reuses `host_runner.py` |
| `cmd <shell-string>` | `subprocess.run(shell=True)` | Escape hatch for anything else |
| `mcp <server:tool> --args <JSON>` | MCP client call via existing MCP machinery | Returns JSON result |
| `prompt <text>` | Direct Claude API call via `anthropic` SDK | Raw completion, no skill wrapper |

### Evaluator

Two independent criteria, both optional (no criteria = always pass after run):
- `--exit-code INT` — compare captured exit code
- `--semantic TEXT` — call `check_semantic` (existing FSM evaluator logic) on captured output; structured LLM judge returning `pass`/`fail`/`needs_work`

Criteria are ANDed when both supplied.

### Output format

```
Runner:   skill ll:check-code
Exit:     0
Semantic: [not checked]
Result:   PASS
---
[captured stdout]
```

### Entry point

New script `scripts/little_loops/cli/harness.py` registered as `ll-harness = "little_loops.cli:main_harness"` in `pyproject.toml` `[project.scripts]`.

Naming convention note: all existing CLI modules drop the `ll_` prefix (`action.py`, `doctor.py`, `deps.py`), unlike the issue's initial draft of `ll_harness.py`. The console script name retains the `ll-` prefix (`ll-harness`), matching all other tools.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Runner wiring details:**

| Subcommand | Implementation approach | Key function/API |
|---|---|---|
| `skill <name>` | `resolve_host().build_streaming(prompt="/ll:<name>")` → `subprocess.run([invocation.binary, *invocation.args])` | `host_runner.py:resolve_host()`, `subprocess_utils.py:221:run_claude_command()` |
| `cmd <shell>` | `subprocess.run(["bash", "-c", shell_string], capture_output=True, text=True)` | Pattern from `fsm/runners.py:125:DefaultActionRunner.run()` (shell branch) |
| `mcp <server:tool>` | `call_mcp_tool(server, tool, params, timeout, cwd) -> tuple[dict, int]` | `mcp_call.py:117:call_mcp_tool()` — returns (response_envelope, exit_code) |
| `prompt <text>` | `resolve_host().build_blocking_json(prompt=text)` → subprocess | Same path as `evaluate_llm_structured()` at `fsm/evaluators.py:609` |

**Evaluator wiring details:**

- **`--exit-code INT`**: Simple integer comparison (`captured_exit_code == expected`). The existing `evaluate_exit_code()` at `fsm/evaluators.py:98` maps Unix convention (0→yes, 1→no, 2+→error), which is different from the arbitrary-target match needed here. Either add a new comparator or parameterize the existing one.

- **`--semantic TEXT`**: Call `evaluate_llm_structured(output=captured_output, prompt=user_criterion)` at `fsm/evaluators.py:572`. The function uses `DEFAULT_LLM_SCHEMA` (line 59) with verdict enum `["yes", "no", "blocked", "partial"]`. Map `"yes"` → PASS (exit 0), all others → FAIL (exit 1). The function truncates output to last 4000 chars (line 605) and invokes `resolve_host().build_blocking_json()` with `--json-schema` (line 609). Returns `EvaluationResult(verdict, details)` (dataclass at line 45).

**Output formatting:**

- **Text mode**: Use `status_block()` from `cli/output.py:266` for aligned key-value runner report
- **JSON mode**: Use `print_json()` from `cli/output.py:146`
- Color helpers: `success()`, `error()`, `warning()` at `cli/output.py:183-210`

**Test patterns to follow:**

- `scripts/tests/test_cli_doctor.py` — `TestMainDoctor` class structure, `patch("sys.argv", [...])` for CLI args, `_capture_print()` helper
- `scripts/tests/test_cli_ctx_stats.py` — `TestParser` for parser isolation + `TestMainCtxStats` for integration, `monkeypatch.chdir(tmp_path)` for isolated filesystem

## API/Interface

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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/harness.py` — new entry point (create; follows naming convention: `action.py`, `doctor.py`, `deps.py` — no `ll_` prefix)
- `scripts/little_loops/cli/__init__.py` — import and re-export `main_harness` (line ~34-64)
- `scripts/pyproject.toml` — register `ll-harness = "little_loops.cli:main_harness"` in `[project.scripts]` (line ~49)
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `resolve_host()` returns `HostRunner` protocol; `build_streaming()` for skill/prompt dispatch, `build_blocking_json()` for semantic eval; always go through `HostInvocation(binary, args)` dataclass
- `scripts/little_loops/subprocess_utils.py:221` — `run_claude_command()` used by existing `ll-action` for skill invocations
- `scripts/little_loops/fsm/evaluators.py:572` — `evaluate_llm_structured()` for `--semantic` checks; returns `EvaluationResult(verdict, details)`; verdict enum: `"yes"`, `"no"`, `"blocked"`, `"partial"` — map `"yes"` to PASS, others to FAIL
- `scripts/little_loops/fsm/evaluators.py:98` — `evaluate_exit_code()` for exit code mapping; existing function maps 0→yes, 1→no, 2+→error; `--exit-code INT` needs a simple comparator (`captured == expected`)
- `scripts/little_loops/fsm/evaluators.py:59` — `DEFAULT_LLM_SCHEMA` defines structured output format `{verdict, confidence, reason}`
- `scripts/little_loops/mcp_call.py:117` — `call_mcp_tool(server_name, tool_name, params, timeout, cwd) -> tuple[dict, int]`
- `scripts/little_loops/cli/output.py:146` — `print_json()` for `--output json`; `status_block()` (line 266) for human-readable text output
- `scripts/little_loops/cli_args.py` — shared argument helpers: `add_timeout_arg()`, `add_json_arg()`, `add_config_arg()`
- `scripts/little_loops/logger.py:17` — `Logger` class for structured CLI logging

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — CLI TOOLS block (lines 243-272): add `ll-harness` one-line entry
- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions block (line ~529); add to both CLAUDE.md boilerplate blocks (lines ~600, ~633)
- `skills/configure/areas.md` — add `ll-harness` to allowed-tools enumeration (line 823); bump "Authorize all 26" → "Authorize all 27"
- `README.md` — bump "29 typed CLI tools" → "30" (line 46) and "29 CLI tools" → "30" (line 162)
- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` to Orchestration CLI table (line ~135); uses `resolve_host()` via all four runner types; update footnote count from "six" to "seven"
- `docs/codex/README.md` — add `ll-harness` to orchestration CLIs list (line 28)
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools parenthetical (line 7)
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` directory tree listing
- `CONTRIBUTING.md` — add `harness.py` to project structure tree (line ~190); also follows checklist at lines 338-353 ("Documentation wiring for new CLI tools")
- `CHANGELOG.md` — add FEAT-1689 entry under next release section

### Similar Patterns
- `scripts/little_loops/cli/action.py:187` — `main_action()` subcommand dispatch pattern (subparsers + if/elif chain); closest structural analog for FEAT-1689
- `scripts/little_loops/cli/doctor.py:34` — `main_doctor(argv=None) -> int` pattern for standalone CLI with `configure_output()` + `Logger(...)` initialization
- `scripts/little_loops/cli/ctx_stats.py` — `_build_parser()` + `_parse_args(argv)` pattern for parser testability
- `scripts/little_loops/cli/loop/__init__.py` — subcommand aliases (`aliases=["r"]`) and `set_defaults(command="...")` patterns
- `scripts/little_loops/cli_args.py` — shared argument helpers: `add_timeout_arg()`, `add_json_arg()`, `add_config_arg()`

### Tests
- `scripts/tests/test_cli_harness.py` — new test file (follows `test_cli_doctor.py`, `test_cli_ctx_stats.py` naming convention); cover all four runner types + both evaluator criteria
- `scripts/tests/test_cli_doctor.py` — model for test structure: `TestMainDoctor` class, `patch("sys.argv", ...)` for CLI args, `_capture_print()` helper, `monkeypatch.chdir(tmp_path)` for isolated filesystem

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — `FakeRunner` class (line 25) and `_make_completed()` helper (line 203) patterns for mocking `resolve_host()` + `subprocess.run` in skill/prompt runner tests
- `scripts/tests/test_mcp_call.py` — `_make_mcp_json()` (line 21), `_make_proc_mock()` (line 138) patterns for mocking `call_mcp_tool()` in MCP runner tests
- `scripts/tests/test_fsm_evaluators.py` — `_cli_stdout()` helper and `mock_cli` fixture patterns for mocking `evaluate_llm_structured()` in `--semantic` tests; `evaluate_exit_code()` parametrized tests (line 46) for `--exit-code` tests
- `scripts/tests/test_cli_e2e.py` — E2E test pattern: `E2ETestFixture` base class (line 24), `@pytest.mark.integration` marker, `subprocess.run` for real CLI invocation; consider adding `ll-harness cmd "echo hello" --exit-code 0` E2E test
- `scripts/tests/test_create_extension_wiring.py` — add `TestFeat1689LlHarnessWiring` class verifying `ll-harness` presence in CLI_REFERENCE, HELP_MD, CLAUDE_MD, CONFIGURE_AREAS; bump `"Authorize all 26"` → `"Authorize all 27"` (line 194); bump `"29 typed CLI tools"` → `"30 typed CLI tools"` in both count assertions (lines 77, 190)

### Documentation
- `docs/reference/API.md` — add `ll-harness` section
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list (currently lists 28 tools)
- `docs/reference/CLI.md` — add ll-harness entry

### Configuration
- N/A — no new config keys required; inherits `orchestration.host_cli` for skill/prompt runners

## Implementation Steps

1. **Scaffold CLI entry point**: Create `scripts/little_loops/cli/harness.py` with `main_harness(argv=None) -> int`, using argparse subparser dispatch (`skill`, `cmd`, `mcp`, `prompt`). Follow `action.py:187:main_action()` pattern (`subparsers.required = True`, if/elif dispatch chain to `cmd_*` handlers). Initialize with `configure_output()` + `Logger(use_color=use_color_enabled())` per `doctor.py:34` pattern. Model parser structure on `ctx_stats.py:_build_parser()` + `_parse_args()` for testability.
2. **Implement runner adapters**:
   - `skill`: `resolve_host().build_streaming(prompt="/ll:<name>")` → `subprocess.run([inv.binary, *inv.args], capture_output=True, text=True, timeout=...)` — pattern from `subprocess_utils.py:221:run_claude_command()`
   - `cmd`: `subprocess.run(["bash", "-c", shell], capture_output=True, text=True, timeout=...)` — pattern from `fsm/runners.py:125:DefaultActionRunner.run()` shell branch
   - `mcp`: `call_mcp_tool(server, tool, params, timeout, cwd) -> tuple[dict, int]` — from `mcp_call.py:117`
   - `prompt`: `resolve_host().build_blocking_json(prompt=text)` → subprocess — pattern from `fsm/evaluators.py:609`
3. **Implement evaluator**: Simple integer comparator for `--exit-code INT`; call `evaluate_llm_structured(output=captured, prompt=criterion)` at `fsm/evaluators.py:572` for `--semantic TEXT`. Map verdicts: `"yes"` → PASS, `"no"`/`"blocked"`/`"partial"` → FAIL. AND the results when both criteria are supplied.
4. **Wire output formatter**: Text mode uses `status_block()` from `cli/output.py:266`; JSON mode uses `print_json()` from `cli/output.py:146`. Exit code protocol: 0=PASS, 1=FAIL, 2=internal error/timeout.
5. **Register and test**: Add `ll-harness = "little_loops.cli:main_harness"` to `pyproject.toml` `[project.scripts]`; import and export in `cli/__init__.py`; create `scripts/tests/test_cli_harness.py` following `test_cli_doctor.py` patterns; add entry to CLAUDE.md CLI Tools list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis (Caller Tracer, Side-Effect Tracer, Test Gap Finder) and must be included in the implementation:_

6. **Doc-wiring sweep**: Update all documentation surfaces per the CONTRIBUTING.md checklist (line 338): `docs/reference/CLI.md` (full `### ll-harness` section), `commands/help.md` (one-line entry in CLI TOOLS block), `.claude/CLAUDE.md` (one-line entry in CLI Tools list). Bump `README.md` tool counts from 29→30 (lines 46, 162). Add to `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` directory trees.
7. **Permissions and init wiring**: Add `"Bash(ll-harness:*)"` to `skills/init/SKILL.md` permissions block and both CLAUDE.md boilerplate blocks. Add `ll-harness` to the allowed-tools enumeration in `skills/configure/areas.md` (line 823), bump "Authorize all 26" → "27".
8. **Orchestration CLI registration**: Add `ll-harness` to the Orchestration CLI table in `docs/reference/HOST_COMPATIBILITY.md` (update footnote count "six"→"seven"). Add to orchestration CLIs lists in `docs/codex/README.md` (line 28) and `docs/codex/usage.md` (line 7).
9. **Wiring test**: Add `TestFeat1689LlHarnessWiring` class to `scripts/tests/test_create_extension_wiring.py` verifying presence in CLI_REFERENCE, HELP_MD, CLAUDE_MD, and CONFIGURE_AREAS. Bump existing count assertions: `"Authorize all 26"`→`"27"`, `"29 typed CLI tools"`→`"30"` (in both locations).
10. **E2E smoke test** (optional, `@pytest.mark.integration`): Add `ll-harness cmd "echo hello" --exit-code 0` to `scripts/tests/test_cli_e2e.py` following the `E2ETestFixture` pattern.
11. **Changelog**: Add FEAT-1689 entry to `CHANGELOG.md` under the next release section.

## Impact

- **Priority**: P2 — fills a real gap in the CLI landscape; enables CI gates and prompt-dev workflows that currently require a full loop YAML
- **Effort**: Medium — four runner adapters + evaluator reuse; `skill` and `--semantic` have the most unknowns
- **Risk**: Low — additive new CLI; no changes to existing runner or FSM paths
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `harness`, `evaluation`, `captured`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-29_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Wide enumeration across 16+ change sites (4 core code + ~11 doc wiring + 2 test files) — mechanical doc changes are low-risk individually but completeness requires discipline; use the enumerated file list in the integration map as a checklist
- Test-first sequencing recommended — `test_cli_harness.py` is a co-deliverable; implement tests first so the CI gate (`ll-harness cmd "python -m pytest scripts/tests/test_cli_harness.py" --exit-code 0`) can catch regressions during implementation
- Minor unresolved implementation choice for `--exit-code` comparator: add a new comparator vs. parameterize the existing `evaluate_exit_code()` — resolve before starting implementation

## Session Log
- `/ll:confidence-check` - 2026-05-29 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current-session>.jsonl`
- `/ll:confidence-check` - 2026-05-30T00:04:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4163028-cdde-4009-bd1a-333f94a89225.jsonl`
- `/ll:wire-issue` - 2026-05-29T23:59:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c48c4a24-7429-4435-9ebf-a7001106b920.jsonl`
- `/ll:format-issue` - 2026-05-25T00:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/416c5fec-1865-4920-b2f5-18bbcefc1861.jsonl`
- `/ll:capture-issue` - 2026-05-25T00:00:03Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1c5270a-50e9-4065-961e-edfcb5f51b85.jsonl`
- `/ll:refine-issue` - 2026-05-29T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current-session>.jsonl`

---

**Open** | Created: 2026-05-25 | Priority: P2
