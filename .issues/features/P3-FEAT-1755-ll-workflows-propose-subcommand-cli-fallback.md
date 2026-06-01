---
id: FEAT-1755
title: ll-workflows propose subcommand as CLI fallback for Step 3 automation proposals
type: FEAT
status: open
priority: P3
captured_at: '2026-05-27T21:20:05Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
relates_to:
- BUG-1754
decision_needed: false
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1755: ll-workflows propose subcommand as CLI fallback for Step 3 automation proposals

## Summary

Add a `propose` subcommand to `ll-workflows` that runs the Step 3 automation proposal logic directly from the CLI. Currently Step 3 is only accessible via the `workflow-automation-proposer` skill invoked from `commands/analyze-workflows.md`. A CLI-native `propose` subcommand provides a robust fallback when the skill invocation is unavailable (e.g., BUG-1754: `disable-model-invocation` breakage) and makes the full 3-step pipeline scriptable end-to-end.

## Use Case

A developer wants to run the full workflow analysis pipeline non-interactively:

```bash
# Step 1: extract messages
ll-messages --output .ll/workflow-analysis/messages.jsonl

# Step 2: analyze patterns (exists today)
ll-workflows analyze --input .ll/workflow-analysis/messages.jsonl \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --output .ll/workflow-analysis/step2-workflows.yaml

# Step 3: propose automations (NEW — currently only works via skill)
ll-workflows propose \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --workflows .ll/workflow-analysis/step2-workflows.yaml \
  --output .ll/workflow-analysis/step3-proposals.yaml
```

Without the `propose` subcommand, Step 3 requires an interactive Claude Code session and the skill to be invocable — both preconditions that may fail (BUG-1754).

## Expected Behavior

`ll-workflows propose` reads the Step 1 patterns and Step 2 workflow YAML, calls the same proposal logic used by `workflow-automation-proposer`, and writes the proposals to an output file (default: `.ll/workflow-analysis/step3-proposals.yaml`). Supports `--format json` to match existing `analyze` flag parity.

## API/Interface

```
usage: ll-workflows propose [-h] -p PATTERNS -w WORKFLOWS [-o OUTPUT] [--format {yaml,json}]

positional arguments:
  propose               Run Step 3 automation proposals from workflow analysis output

options:
  -p, --patterns PATH   Step 1 patterns YAML (from ll-messages or workflow-pattern-analyzer)
  -w, --workflows PATH  Step 2 workflows YAML (from ll-workflows analyze)
  -o, --output PATH     Output path (default: .ll/workflow-analysis/step3-proposals.yaml)
  --format {yaml,json}  Output format (default: yaml)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence/__init__.py` — add `propose` subparser and handler in `main()` alongside the existing `analyze` dispatch block; no other entry-point file needs changes
- `docs/reference/CLI.md` — document the new `ll-workflows propose` subcommand (current `ll-workflows` section is at lines 1384–1413)
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — update Step 3 documentation to show the CLI path alongside the skill path

### Files to Read (No Modification)
- `scripts/little_loops/workflow_sequence/__init__.py` — `main()` function; copy the `analyze` subparser structure as the pattern for `propose`
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` function; use this for all LLM calls (not the anthropic SDK — there are zero `import anthropic` statements in this codebase)
- `scripts/little_loops/workflow_sequence/io.py` — `_load_patterns()`: existing helper to load step1 YAML; `propose` handler should reuse it
- `scripts/little_loops/cli/output.py` — `configure_output()`, `use_color_enabled()`, `print_json()`: call once after `parse_args()`, same as `analyze`
- `skills/workflow-automation-proposer/SKILL.md` — the complete Step 3 prompt logic and output schema definition; distill this into the `propose` handler's prompt string

### Entry Point Registration
- `scripts/pyproject.toml` — **no change needed**; `ll-workflows = "little_loops.workflow_sequence:main"` (line 58) already points to `main()`, so the new subcommand surfaces automatically

### Dependent Files (Callers)
- `commands/analyze-workflows.md` — orchestrates Steps 1–3 sequentially; Step 3 currently invokes the skill directly. Update to offer `ll-workflows propose` as a fallback path.

### Tests

- `scripts/tests/test_workflow_sequence_analyzer.py` — existing test file; add `propose` subcommand tests here following `TestMainDefaultInput` patterns (use `patch.object(sys, "argv", ["ll-workflows", "propose", ...])` + `capsys.readouterr()`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_workflow_sequence_analyzer.py` — new test class `TestMainProposeSubcommand` needed with these specific cases:
  - missing `--patterns` or `--workflows` path → exit 1 with clear error (follow `test_default_input_missing_shows_ll_messages_hint` shape)
  - bare `propose` with no arguments → exit 1
  - successful mock: patch `subprocess.Popen` + `selectors.DefaultSelector` (use `_patch_selector_cm` pattern from `test_subprocess_utils.py`) AND patch `little_loops.subprocess_utils.resolve_host` (module-level in that file); set `mock_process.stdout = io.StringIO("proposals:\n  ...")` + `returncode = 0`
  - `--format json` output: assert the written file contains valid JSON with top-level keys `analysis_metadata`, `summary`, `proposals`, `existing_command_suggestions`, `implementation_roadmap`
  - Note: existing 3 `TestMainDefaultInput` tests are unaffected — they patch argv with `"analyze"` and hit early-exit paths before any subprocess call

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — section `### /ll:workflow-automation-proposer` (line ~849) describes the skill as "Final step (Step 3) of the `/ll:analyze-workflows` pipeline" with no CLI alternative; add a cross-reference note pointing to `ll-workflows propose` once this feature lands

## Implementation Notes

### Subcommand Structure (Follow `analyze` exactly)

The `propose` subparser goes into `main()` in `scripts/little_loops/workflow_sequence/__init__.py` as a second `subparsers.add_parser("propose", ...)` block. The dispatch pattern:

```python
propose_parser = subparsers.add_parser("propose", help="Run Step 3 automation proposals")
propose_parser.add_argument("-p", "--patterns", type=Path, required=True, metavar="PATH", ...)
propose_parser.add_argument("-w", "--workflows", type=Path, required=True, metavar="PATH", ...)
propose_parser.add_argument("-o", "--output", type=Path, default=None, metavar="PATH", ...)
propose_parser.add_argument("-f", "--format", choices=["yaml", "json"], default="yaml", ...)

# ... after parse_args() / configure_output() / logger setup ...
if args.command == "propose":
    # validate inputs exist; derive default output_path; invoke LLM; write output
    ...
    return 0
```

### LLM Invocation — Two Options

**No Python proposal-generation function currently exists.** `skills/workflow-automation-proposer/SKILL.md` is pure LLM reasoning. The `propose` handler must choose one of:

**Option A — Invoke the skill via `run_claude_command()`**

> **Selected:** Option A — Invoke the skill via `run_claude_command()` — highest codebase consistency (3/3); matches `cmd_invoke()` canonical pattern; BUG-1754 is separately fixable.

```python
from little_loops.subprocess_utils import run_claude_command

# Build the slash-command string exactly as ll-action/cmd_invoke does:
skill_cmd = f"/ll:workflow-automation-proposer {args.patterns} {args.workflows}"
result = run_claude_command(command=skill_cmd, timeout=120)
if result.returncode != 0:
    logger.error("Proposal generation failed")
    return 1
# Parse result.stdout (YAML text) and write to args.output
```

This keeps the skill as the single source of truth for proposal logic. Downside: if the skill is broken (BUG-1754 scenario), this inherits the same failure.

**Option B — Send the skill's prompt inline as a raw LLM call**

```python
from little_loops.subprocess_utils import run_claude_command

# Read the two input files, embed their contents into a prompt that replicates
# the skill's reasoning steps directly — no dependency on the skill framework.
prompt = build_proposal_prompt(patterns_data, workflows_data)  # raw NL prompt
result = run_claude_command(command=prompt, timeout=120)
```

This achieves true independence from the skill framework (the stated goal of this feature). Downside: the prompt logic is duplicated from the skill and must be kept in sync.

_Option B is the stronger CLI-fallback implementation since it eliminates the skill dependency._

### Output File Handling (Follow `analyze` exactly)

```python
output_path = args.output
if output_path is None:
    ext = "json" if args.format == "json" else "yaml"
    output_path = Path(f".ll/workflow-analysis/step3-proposals.{ext}")
output_path.parent.mkdir(parents=True, exist_ok=True)
```

Parse `result.stdout` as YAML (the skill writes YAML by default), then re-serialize in the requested `--format`. The top-level output schema keys (from the skill): `analysis_metadata`, `summary`, `proposals`, `existing_command_suggestions`, `implementation_roadmap`.

### Note on SDK

The codebase does **not** use the `anthropic` Python SDK anywhere. Use `run_claude_command()` from `scripts/little_loops/subprocess_utils.py` for all LLM invocations.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option A — Invoke the skill via `run_claude_command()`

**Reasoning**: Option A matches the canonical `cmd_invoke()` pattern used across the codebase — 7 production modules and 95 total call sites — with a reuse score of 3/3. The slash-command string construction (`f"/ll:workflow-automation-proposer {args.patterns} {args.workflows}"`) and `run_claude_command()` call are identical to established patterns in `action.py`, `issue_manager.py`, and the FSM executor. Option B requires authoring a new `build_proposal_prompt()` function by distilling `skills/workflow-automation-proposer/SKILL.md` (no Python equivalent exists), adding maintenance overhead. While Option A inherits BUG-1754-type failures in theory, BUG-1754 is a separately fixable config bug; Option A still achieves the feature's core goal of making Step 3 fully scriptable end-to-end.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (selected) | 3/3 | 3/3 | 3/3 | 1/3 | 10/12 |
| Option B | 2/3 | 1/3 | 2/3 | 3/3 | 8/12 |

**Key evidence**:
- **Option A**: `cmd_invoke()` in `scripts/little_loops/cli/action.py` is the exact template; test pattern `patch("little_loops.subprocess_utils.run_claude_command", ...)` is established in `scripts/tests/test_action.py`
- **Option B**: One direct precedent in `scripts/little_loops/cli/generate_skill_descriptions.py:119`; requires new `build_proposal_prompt()` from `skills/workflow-automation-proposer/SKILL.md`; achieves full skill-independence (risk 3/3) but at simplicity cost (1/3)

## Acceptance Criteria

- `ll-workflows propose --patterns p.yaml --workflows w.yaml` succeeds and writes `.ll/workflow-analysis/step3-proposals.yaml`
- `ll-workflows propose --patterns p.yaml --workflows w.yaml --format json -o out.json` writes valid JSON
- Missing required `--patterns` or `--workflows` paths exit 1 with a clear error
- `ll-workflows propose` with no arguments prints help and exits non-zero
- The output YAML contains the expected top-level keys: `analysis_metadata`, `summary`, `proposals`, `existing_command_suggestions`, `implementation_roadmap`
- The subcommand is documented in `docs/reference/CLI.md`
- Tests added to `scripts/tests/test_workflow_sequence_analyzer.py` covering at least: missing-input error, successful mock output, and `--format json` output

## Related Issues

- BUG-1754: workflow-automation-proposer disable-model-invocation breaks workflow analysis pipeline (direct motivator)
- FEAT-028: workflow-automation-proposer skill (existing skill this CLI mirrors)
- FEAT-557: Add `--format json` to `ll-workflows` (done — parity reference for output flags)

## Session Log
- `/ll:confidence-check` - 2026-06-01T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/813e2a5f-d24c-438e-a426-e4970231e347.jsonl`
- `/ll:decide-issue` - 2026-06-01T20:19:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e874e443-0b3b-43eb-88ed-57be305c96d0.jsonl`
- `/ll:wire-issue` - 2026-06-01T20:10:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/21fc4d51-9f05-467d-9e9a-9dfbe2765d14.jsonl`
- `/ll:refine-issue` - 2026-06-01T20:05:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b5da24-54cf-4b03-8f0f-1659be02c409.jsonl`
- `/ll:refine-issue` - 2026-06-01T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cc00c83-84fd-4f43-9f5f-608dd241e0d5.jsonl`
- `/ll:capture-issue` - 2026-05-27T21:20:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d76f6684-f28b-48e1-8feb-af054e035afe.jsonl`

---

## Status

`open`
