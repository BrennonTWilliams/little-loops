---
id: FEAT-1689
type: FEAT
title: add ll-harness CLI for one-shot runner evaluation
priority: P2
status: done
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
decision_needed: false
implementation_order_risk: true
size: Very Large
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
| `cmd <shell>` | `subprocess.run(["bash", "-c", shell_string], capture_output=True, text=True)` | Pattern from `fsm/runners.py:131:DefaultActionRunner.run()` (shell branch — `cmd = ["bash", "-c", action]`) |
| `mcp <server:tool>` | `call_mcp_tool(server, tool, params, timeout, cwd) -> tuple[dict, int]` | `mcp_call.py:117:call_mcp_tool()` — returns (response_envelope, exit_code) |
| `prompt <text>` | `resolve_host().build_blocking_json(prompt=text)` → subprocess | Same path as `evaluate_llm_structured()` at `fsm/evaluators.py:740` |

**Evaluator wiring details:**

- **`--exit-code INT`**: Simple inline comparator in `harness.py` — `captured_exit_code == expected`. Do NOT route through `evaluate_exit_code()` at `fsm/evaluators.py:135`, which encodes a fixed Unix 0/1/2+ semantic that belongs to the FSM and would be conflated by adding an `expected` parameter. The harness only needs a one-liner equality check.

- **`--semantic TEXT`**: Call `evaluate_llm_structured(output=captured_output, prompt=user_criterion)` at `fsm/evaluators.py:740`. The function uses `DEFAULT_LLM_SCHEMA` (line 61) with verdict enum `["yes", "no", "blocked", "partial"]`. Map `"yes"` → PASS (exit 0), all others → FAIL (exit 1). Returns `EvaluationResult(verdict, details)` (dataclass at line 48).

**Output formatting:**

- **Text mode**: Use `status_block()` from `cli/output.py:266` for aligned key-value runner report
- **JSON mode**: Use `print_json()` from `cli/output.py:146`
- Color helpers: `success()`, `error()`, `warning()` at `cli/output.py:183-210`

**Test patterns to follow:**

- `scripts/tests/test_cli_doctor.py` — `TestMainDoctor` class structure, `patch("sys.argv", [...])` for CLI args, `_capture_print()` helper
- `scripts/tests/test_cli_ctx_stats.py` — `TestParser` for parser isolation + `TestMainCtxStats` for integration, `monkeypatch.chdir(tmp_path)` for isolated filesystem

**Additional anchor references verified 2026-06-01:**
- `configure_output()` — `cli/output.py:88`
- `use_color_enabled()` — `cli/output.py:134`
- `resolve_host()` — `host_runner.py:751`
- `ClaudeCodeRunner.build_streaming()` — `host_runner.py:233`
- `ClaudeCodeRunner.build_blocking_json()` — `host_runner.py:274`
- `add_timeout_arg()` — `cli_args.py:100`; `add_json_arg()` — `cli_args.py:197`; `add_config_arg()` — `cli_args.py:35`
- `cli/__init__.py` imports span lines 35–66; `main_harness` not yet present — add after line 43 (after `main_doctor`)
- `commands/help.md` CLI TOOLS block: lines 243–273; 29 entries currently; `ll-harness` not yet listed

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
- `scripts/little_loops/fsm/evaluators.py:740` — `evaluate_llm_structured()` for `--semantic` checks; returns `EvaluationResult(verdict, details)` (dataclass at line 48); verdict enum: `"yes"`, `"no"`, `"blocked"`, `"partial"` — map `"yes"` to PASS, others to FAIL
- `scripts/little_loops/fsm/evaluators.py:135` — `evaluate_exit_code()` exists but is NOT used for `--exit-code INT`; it encodes FSM Unix convention (0→yes, 1→no, 2+→error) only; the harness uses an inline `captured == expected` check instead
- `scripts/little_loops/fsm/evaluators.py:61` — `DEFAULT_LLM_SCHEMA` defines structured output format `{verdict, confidence, reason}`
- `scripts/little_loops/mcp_call.py:117` — `call_mcp_tool(server_name, tool_name, params, timeout, cwd) -> tuple[dict, int]`
- `scripts/little_loops/cli/output.py:146` — `print_json()` for `--output json`; `status_block()` (line 266) for human-readable text output
- `scripts/little_loops/cli_args.py` — shared argument helpers: `add_timeout_arg()`, `add_json_arg()`, `add_config_arg()`
- `scripts/little_loops/logger.py:17` — `Logger` class for structured CLI logging

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` module docstring (lines 1–33) — add `ll-harness` bullet to the tool listing in the module-level docstring; this is a third distinct edit in the same file beyond the `main_harness` import (after line 43) and the `__all__` entry (lines 68–102)
- `commands/help.md` — CLI TOOLS block (lines 243-272): add `ll-harness` one-line entry
- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions block (line ~529); add to both CLAUDE.md boilerplate blocks (lines ~600, ~633)
- `skills/configure/areas.md` — add `ll-harness` to allowed-tools enumeration (line 825); **"Authorize all 27" count is already current** — only the tool name entry needs adding
- `README.md` — **"30 typed CLI tools" count (lines 46, 162) is already current** — no bump needed
- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` to Orchestration CLI table (line ~135); uses `resolve_host()` via all four runner types; update footnote count from "six" to "seven"
- `docs/codex/README.md` — add `ll-harness` to orchestration CLIs list (line 28)
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools parenthetical (line 7)
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` directory tree listing
- `CONTRIBUTING.md` — add `harness.py` to project structure tree (line ~190); also follows checklist at lines 338-353 ("Documentation wiring for new CLI tools")
- `CHANGELOG.md` — add FEAT-1689 entry under next release section

### Similar Patterns
- `scripts/little_loops/cli/action.py:189` — `main_action()` subcommand dispatch pattern (subparsers + if/elif chain); closest structural analog for FEAT-1689
- `scripts/little_loops/cli/doctor.py:97` — `main_doctor(argv=None) -> int` pattern for standalone CLI with `configure_output()` (line 88 of `output.py`) + `Logger(use_color=use_color_enabled())` (line 133 of `doctor.py`) initialization
- `scripts/little_loops/cli/ctx_stats.py` — `_build_parser()` + `_parse_args(argv)` pattern for parser testability
- `scripts/little_loops/cli/loop/__init__.py` — subcommand aliases (`aliases=["r"]`) and `set_defaults(command="...")` patterns
- `scripts/little_loops/cli_args.py` — shared argument helpers: `add_timeout_arg()`, `add_json_arg()`, `add_config_arg()`

### Tests
- `scripts/tests/test_cli_harness.py` — new test file (follows `test_cli_doctor.py`, `test_cli_ctx_stats.py` naming convention); cover all four runner types + both evaluator criteria
- `scripts/tests/test_cli_doctor.py` — model for test structure: `TestMainDoctor` class, `patch("sys.argv", ...)` for CLI args, `_capture_print()` helper, `monkeypatch.chdir(tmp_path)` for isolated filesystem

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — `FakeRunner` class (line 25) and `_make_completed()` helper (line 203) patterns for mocking `resolve_host()` + `subprocess.run` in skill/prompt runner tests
- `scripts/tests/test_mcp_call.py` — `_make_mcp_json()` (line 21), `_make_proc_mock()` (line 138) patterns for mocking `call_mcp_tool()` in MCP runner tests
- `scripts/tests/test_fsm_evaluators.py` — `_cli_stdout()` helper and `mock_cli` fixture patterns for mocking `evaluate_llm_structured()` in `--semantic` tests; `--exit-code` tests use direct integer comparison, not `evaluate_exit_code()`
- `scripts/tests/test_cli_e2e.py` — E2E test pattern: `E2ETestFixture` base class (line 24), `@pytest.mark.integration` marker, `subprocess.run` for real CLI invocation; consider adding `ll-harness cmd "echo hello" --exit-code 0` E2E test
- `scripts/tests/test_create_extension_wiring.py` — add `TestFeat1689LlHarnessWiring` class verifying `ll-harness` presence in CLI_REFERENCE, HELP_MD, CLAUDE_MD, CONFIGURE_AREAS; **count assertions already at target values** — `"Authorize all 27"` (lines 57, 196) and `"30 typed CLI tools"` (lines 79, 192) need no bumping

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `scripts/tests/test_enh1846_doc_wiring.py` — also asserts `"Authorize all 27"` (line 46) and `"30 typed CLI tools"` (line 66); the `"Authorize all 27"` assertion at line 46 must be bumped to `"Authorize all 28"` alongside `test_create_extension_wiring.py` lines 57 and 196 when `areas.md` count is corrected (see Count Assertion Correction section below)

### Documentation
- `docs/reference/API.md` — add `ll-harness` section
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list (currently lists 28 tools)
- `docs/reference/CLI.md` — add ll-harness entry

### Configuration
- N/A — no new config keys required; inherits `orchestration.host_cli` for skill/prompt runners

### Count Assertion Correction (2nd wiring pass)

_Added by `/ll:wire-issue` (2nd pass):_

The prior wiring pass (step 7) stated `"Authorize all 27"` count is "already current — only the tool name entry needs adding." This is **incorrect**: `skills/configure/areas.md` line 825 currently enumerates exactly 27 named tools and the count string reads `"Authorize all 27"`. Adding `ll-harness` makes 28 named tools, so:

- `skills/configure/areas.md` line 825: change `"Authorize all 27"` → `"Authorize all 28"` AND append `ll-harness` to the named enumeration
- `scripts/tests/test_create_extension_wiring.py` lines 57 and 196: update assertion string from `"Authorize all 27"` → `"Authorize all 28"`
- `scripts/tests/test_enh1846_doc_wiring.py` line 46: same update

Note: `"30 typed CLI tools"` in `README.md` (lines 46, 162) and the corresponding test assertions (lines 79, 192 of `test_create_extension_wiring.py`; line 66 of `test_enh1846_doc_wiring.py`) do **not** need bumping — `ll-harness` was pre-counted when the "30" target was set and those tests currently pass.

## Implementation Steps

1. **Scaffold CLI entry point**: Create `scripts/little_loops/cli/harness.py` with `main_harness(argv=None) -> int`, using argparse subparser dispatch (`skill`, `cmd`, `mcp`, `prompt`). Follow `action.py:189:main_action()` pattern (`subparsers.required = True`, if/elif dispatch chain to `cmd_*` handlers). Initialize with `configure_output()` + `Logger(use_color=use_color_enabled())` per `doctor.py:97` pattern. Model parser structure on `ctx_stats.py:_build_parser()` + `_parse_args()` for testability.
2. **Implement runner adapters**:
   - `skill`: `resolve_host().build_streaming(prompt="/ll:<name>")` → `subprocess.run([inv.binary, *inv.args], capture_output=True, text=True, timeout=...)` — pattern from `subprocess_utils.py:221:run_claude_command()`
   - `cmd`: `subprocess.run(["bash", "-c", shell], capture_output=True, text=True, timeout=...)` — pattern from `fsm/runners.py:131:DefaultActionRunner.run()` shell branch
   - `mcp`: `call_mcp_tool(server, tool, params, timeout, cwd) -> tuple[dict, int]` — from `mcp_call.py:117`
   - `prompt`: `resolve_host().build_blocking_json(prompt=text)` → subprocess — uses same host-runner path as `evaluate_llm_structured()` at `fsm/evaluators.py:740`
3. **Implement evaluator**: Simple integer comparator for `--exit-code INT`; call `evaluate_llm_structured(output=captured, prompt=criterion)` at `fsm/evaluators.py:740` for `--semantic TEXT`. Map verdicts: `"yes"` → PASS, `"no"`/`"blocked"`/`"partial"` → FAIL. AND the results when both criteria are supplied.
4. **Wire output formatter**: Text mode uses `status_block()` from `cli/output.py:266`; JSON mode uses `print_json()` from `cli/output.py:146`. Exit code protocol: 0=PASS, 1=FAIL, 2=internal error/timeout.
5. **Register and test**: Add `ll-harness = "little_loops.cli:main_harness"` to `pyproject.toml` `[project.scripts]`; import and export in `cli/__init__.py`; create `scripts/tests/test_cli_harness.py` following `test_cli_doctor.py` patterns; add entry to CLAUDE.md CLI Tools list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis (Caller Tracer, Side-Effect Tracer, Test Gap Finder) and must be included in the implementation:_

6. **Doc-wiring sweep**: Update all documentation surfaces per the CONTRIBUTING.md checklist (lines 341-355): `docs/reference/CLI.md` (full `### ll-harness` section), `commands/help.md` (one-line entry in CLI TOOLS block, after line 273), `.claude/CLAUDE.md` (one-line entry in CLI Tools list). `README.md` counts already at 30 — no increment needed. Add `harness.py` to `cli/` tree in `docs/ARCHITECTURE.md` (line ~201) and to `CONTRIBUTING.md` directory tree (line ~186).
7. **Permissions and init wiring**: Add `"Bash(ll-harness:*)"` to `skills/init/SKILL.md` permissions block (after line 551) and both CLAUDE.md boilerplate blocks (lines ~600, ~633). Add `ll-harness` to the allowed-tools enumeration in `skills/configure/areas.md` (line 825); **"Authorize all 27" count is already current** — only the tool name entry needs adding.
8. **Orchestration CLI registration**: Add `ll-harness` row to the Orchestration CLI table in `docs/reference/HOST_COMPATIBILITY.md` (after line 141; table currently has 5 entries — ll-auto, ll-parallel, ll-action, ll-loop, FSM evaluators). Add to orchestration CLIs lists in `docs/codex/README.md` (line 28) and `docs/codex/usage.md` (line 7).
9. **Wiring test**: Add `TestFeat1689LlHarnessWiring` class to `scripts/tests/test_create_extension_wiring.py` verifying `ll-harness` presence in CLI_REFERENCE, HELP_MD, CLAUDE_MD, and CONFIGURE_AREAS. **Count assertions already at target values** — `"Authorize all 27"` (lines 57, 196) and `"30 typed CLI tools"` (lines 79, 192) need no bumping.
10. **E2E smoke test** (optional, `@pytest.mark.integration`): Add `ll-harness cmd "echo hello" --exit-code 0` to `scripts/tests/test_cli_e2e.py` following the `E2ETestFixture` pattern.
11. **Changelog**: Add FEAT-1689 entry to `CHANGELOG.md` under the next release section.
12. **Count bumps** _(2nd wiring pass correction)_: In `skills/configure/areas.md` line 825, change `"Authorize all 27"` → `"Authorize all 28"` and append `ll-harness` to the named enumeration. Update the corresponding test assertions in `test_create_extension_wiring.py` (lines 57, 196) and `test_enh1846_doc_wiring.py` (line 46) from `"Authorize all 27"` → `"Authorize all 28"`. Also add `ll-harness` bullet to `cli/__init__.py` module docstring (lines 1–33) — a third distinct edit in that file beyond the import (after line 43) and `__all__` entry (lines 68–102).
13. **Complete `TestFeat1689LlHarnessWiring`** _(2nd wiring pass)_: The test class in step 9 must include INIT_SKILL assertions per the established pattern (`TestFeat1229LlActionWiring`, `TestFeat1526LlAdaptAgentsWiring`): `assert '"Bash(ll-harness:*)"' in INIT_SKILL.read_text()` and `assert INIT_SKILL.read_text().count("ll-harness") >= 3`.
14. **Patch paths in `test_cli_harness.py`** _(2nd wiring pass)_: Mock at the harness module's import site, not the source module: `"little_loops.cli.harness.evaluate_llm_structured"` (not FSM paths), `"little_loops.cli.harness.call_mcp_tool"`, and `"little_loops.cli.harness.resolve_host"`. Follow the pattern in `test_action.py` which patches `"little_loops.cli.action.resolve_host"`.

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
- ~~Minor unresolved implementation choice for `--exit-code` comparator~~ — **resolved**: use inline `captured == expected` in `harness.py`; do not touch `evaluate_exit_code()` (FSM-only semantic)

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: VALID** — Core claims confirmed against current codebase:
- `ll-harness` CLI does not yet exist (`harness.py` absent from `cli/`) ✓
- `call_mcp_tool()` at `mcp_call.py:117` ✓
- `evaluate_llm_structured()` at `evaluators.py:740` (previously cited 572, then 608 — function has continued to grow; 2026-06-01 refresh confirms line 740) ~
- `print_json()` at `cli/output.py:146` ✓; `status_block()` at `cli/output.py:266` ✓
- All referenced infrastructure (`host_runner.resolve_host()`, `cli/action.py` pattern, `cli/doctor.py` pattern) exists ✓

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session (size score 11/11)

### Decomposed Into
- FEAT-1851: ll-harness CLI — core runner implementation (steps 1–5, 14)
- FEAT-1852: ll-harness CLI — doc, wiring, and count correction sweep (steps 6–13)

---

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1ebc34f-6a74-4ed8-b570-856978fc59ce.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9d6444b-ae99-4db8-9651-f85fa0072ba3.jsonl`
- `/ll:wire-issue` - 2026-06-01T15:07:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1863742e-c8f8-4be4-b311-7846314b933b.jsonl`
- `/ll:refine-issue` - 2026-06-01T15:00:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa8f3c24-5078-4643-8c92-8e40de4d18b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-05-29 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current-session>.jsonl`
- `/ll:confidence-check` - 2026-05-30T00:04:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4163028-cdde-4009-bd1a-333f94a89225.jsonl`
- `/ll:wire-issue` - 2026-05-29T23:59:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c48c4a24-7429-4435-9ebf-a7001106b920.jsonl`
- `/ll:format-issue` - 2026-05-25T00:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/416c5fec-1865-4920-b2f5-18bbcefc1861.jsonl`
- `/ll:capture-issue` - 2026-05-25T00:00:03Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1c5270a-50e9-4065-961e-edfcb5f51b85.jsonl`
- `/ll:refine-issue` - 2026-05-29T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current-session>.jsonl`

---

**Open** | Created: 2026-05-25 | Priority: P2
