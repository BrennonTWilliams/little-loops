# Loop Audit: cli-anything-bootstrap

**Date**: 2026-06-04
**Run**: `2026-06-04T012659`
**Target**: `mermaid`
**Loop definition**: `.loops/cli-anything-bootstrap.yaml`

---

## Goal-vs-Outcome Scorecard

**Goal**: "Meta-loop that bootstraps an agent-native CLI for a target software (local path or repo URL) by delegating to CLI-Anything's `/cli-anything` skill, bakes a per-target rubric, caches the result, and emits a project-local task loop to `.loops/generated/` that downstream loops invoke to drive the target software toward user goals."

**Contract**:

| Key | Value | Source |
|---|---|---|
| `min_help_coverage` | 0.9 | `context` |
| `min_test_pass_rate` | 0.85 | `context` |
| `install_clean` threshold | 1.0 (exit code 0) | rubric (via `bake-rubric` prompt) |
| `json_output` threshold | 1.0 (every command supports `--json`) | rubric |
| `deterministic` threshold | 1.0 (same inputs → same outputs) | rubric |

**Artifacts checked**:

| Path | Expected | Actual |
|---|---|---|
| `.loops/generated/*-task.yaml` | Present (the task loop) | **MISSING** — directory empty |
| `.loops/cli-anything/c3fe5b17b883/manifest.yaml` | Present (created by `publish-cache`) | **MISSING** |
| `.loops/cli-anything/c3fe5b17b883/rubric.yaml` | Present (copied by `delegate-bootstrap` step 4) | **MISSING** |
| `.loops/cli-anything/c3fe5b17b883/classification.yaml` | Present | **MISSING** |
| `.loops/cli-anything/c3fe5b17b883/pyproject.toml` | Present | Exists ✅ |
| `.loops/cli-anything/c3fe5b17b883/mermaid_cli/` | Present | Exists ✅ (working CLI, 7 command groups, 13 leaf commands) |
| `.loops/cli-anything/c3fe5b17b883/tests/` | Present | Exists ✅ (85 tests, 100% pass rate) |

**Phase 1 fault signals**: 2 detected

1. **Evaluate failures** — `score-bootstrap` returned `no` (ITERATE) on 3 consecutive visits (iterations 10, 13, 17), preventing convergence to `ALL_PASS`
2. **`verify-cli` exit_code=1** on iterations 9 and 12 — `reason=MISSING_SETUP` on first visit, then the same pattern repeated due to the `Activate.ps1` grep bug (see root cause below)

**Verdict**: **`partial`**

**Rationale**: The loop terminated by `max_iterations` at iteration 20 with final state `score-bootstrap` — a non-terminal state in the `score-bootstrap → delegate-refine → verify-cli → run-cli-tests → score-bootstrap` cycle. The generated CLI harness actually works correctly (85/85 tests passing, 7 command groups with 13 leaf commands, all supporting `--json` with deterministic output), but the `verify-cli` shell script has a **case-sensitive grep pattern bug** that makes it always detect `Activate.ps1` as the CLI binary instead of `mermaid-cli`. Consequently, `help_coverage` is always reported as `0.0` against threshold `0.9`, `score-bootstrap` never emits `ALL_PASS`, and the loop never transitions to `publish-cache` → `emit-task-loop` → `done`. No task loop YAML was generated in `.loops/generated/`.

---

## Root Cause: `verify-cli` Grep Pattern Bug

The critical bug is on this line of the `verify-cli` shell action:

```bash
CLI_NAME=$(ls "$VENV/bin" | grep -v -E '^(python|pip|activate|wheel)' | head -1)
```

The pattern `activate` only matches **lowercase** `activate`. On macOS (and other platforms), Python venvs include `Activate.ps1` (capital 'A', PowerShell activation script), which:

1. **Passes through the grep filter** — does not match `^(python|pip|activate|wheel)` because `Activate` starts with uppercase 'A'
2. **Sorts alphabetically before `mermaid-cli`** in the `ls` output:
   ```
   Activate.ps1    ← picked by head -1
   activate        ← excluded by grep
   activate.csh    ← excluded by grep
   activate.fish   ← excluded by grep
   mermaid-cli     ← the actual CLI, never reached
   pip             ← excluded by grep
   ...
   ```
3. **Is not an executable** → `$VENV/bin/Activate.ps1 --help` returns exit code 126
4. **Has no subcommands** → `help_coverage=0.0`, `subcommand_total=0`

### Reproduction

```bash
$ ls .loops/cli-anything/c3fe5b17b883/.venv/bin/ | grep -v -E '^(python|pip|activate|wheel)' | head -1
Activate.ps1

$ ls .loops/cli-anything/c3fe5b17b883/.venv/bin/ | sort
Activate.ps1      # <-- alphabetically first non-filtered entry
activate          # filtered out
activate.csh      # filtered out
activate.fish     # filtered out
mermaid-cli       # the real CLI, never seen by the script
pip               # filtered out
...
```

### The Inescapable Cycle

This bug creates a loop that can **never** converge, regardless of how many refine iterations run:

```
verify-cli → reports help_coverage=0.0 (always, due to Activate.ps1)
    ↓
run-cli-tests → passes (85/85) → routes to score-bootstrap
    ↓
score-bootstrap → reads verify-cli.txt, sees help_coverage=0.0 < 0.9
    → outputs ITERATE → routes to delegate-refine
    ↓
delegate-refine → refines the working CLI (but can't fix the harness bug)
    → routes to verify-cli
    ↓
(cycle repeats until max_iterations)
```

The bitter irony: `delegate-refine` actually built a fully functional CLI — 85 tests, 7 command groups, 13 leaf commands, all with `--json` support and deterministic output. The harness just couldn't see it.

---

## Event Trace (key states)

| Iter | State | Result | routing |
|---|---|---|---|
| 1 | `init` | run_dir created | → `compute-hash` |
| 2 | `compute-hash` | cache_path = `.../c3fe5b17b883` | → `check-cache` |
| 3 | `check-cache` | cache miss (exit 1 → no) | → `classify-target` |
| 4 | `classify-target` | classified as `data-lib` | → `validate-classification` |
| 5 | `validate-classification` | validated (exit 0 → yes) | → `bake-rubric` |
| 6 | `bake-rubric` | rubric.yaml written | → `validate-rubric` |
| 7 | `validate-rubric` | validated (exit 0 → yes) | → `delegate-bootstrap` |
| 8 | `delegate-bootstrap` | **CLI_ANYTHING_PLUGIN_MISSING** | → `verify-cli` |
| 9 | `verify-cli` | exit 1 (MISSING_SETUP) → no | → `score-bootstrap` |
| 10 | `score-bootstrap` | ITERATE (all FAIL) → no | → `delegate-refine` |
| 11 | `delegate-refine` | built CLI from scratch (97s) | → `verify-cli` |
| 12 | `verify-cli` | exit 1 (MISSING_SETUP) → no | → `score-bootstrap` |
| 13 | `score-bootstrap` | ITERATE → no | → `delegate-refine` |
| 14 | `delegate-refine` | **discovered Activate.ps1 bug, built full CLI** (328s) | → `verify-cli` |
| 15 | `verify-cli` | exit 0 → yes | → `run-cli-tests` |
| 16 | `run-cli-tests` | exit 0, 33/33 passed → yes | → `score-bootstrap` |
| 17 | `score-bootstrap` | ITERATE (`help_coverage=0.0`) → no | → `delegate-refine` |
| 18 | `delegate-refine` | expanded CLI to 13 commands, 85 tests (419s) | → `verify-cli` |
| 19 | `verify-cli` | exit 0 → yes (**cli_name still Activate.ps1**) | → `run-cli-tests` |
| 20 | `run-cli-tests` | exit 0, 85/85 passed → yes | → `score-bootstrap` |
| — | **`loop_complete`** | `terminated_by: max_iterations` | (never reached `emit-task-loop`) |

---

## Rubric Audit

**Skipped** — no states use `evaluate.type: llm_structured`. All evaluators are `exit_code` or `output_contains`.

---

## Sub-Loop Verdict Laundering Check

**Skipped** — no states define `loop:` (no sub-loop invocations).

---

## Improvement Proposals

### 1. [BUG] Fix `verify-cli` grep pattern to exclude `Activate.ps1` and other activation scripts

**Rationale**: The grep filter `'^(python|pip|activate|wheel)'` misses `Activate.ps1` because of case sensitivity. This is the root cause of the entire audit finding.

**YAML diff**:
```yaml
# In states.verify-cli.action, change:
#   CLI_NAME=$(ls "$VENV/bin" | grep -v -E '^(python|pip|activate|wheel)' | head -1)
# To:
#   CLI_NAME=$(ls "$VENV/bin" | grep -v -iE '^(python|pip|activate|wheel)' | grep -v '\.ps1$' | head -1)
```

The `-i` flag handles case-insensitive matching. The additional `grep -v '\.ps1$'` is a defense-in-depth measure for any other activation scripts that might slip through.

### 2. [STRUCTURAL] Prefer executables from `entry_points.txt` over `ls` heuristics

**Rationale**: Even with the grep fix, `ls | grep -v | head -1` is fragile — it relies on alphabetical ordering to find the right binary. The script should inspect the package's `entry_points.txt` to find the declared console_scripts entry point, which is the authoritative source.

**YAML diff**:
```yaml
# In states.verify-cli.action, replace the CLI_NAME detection block:
#   # Find the actual console_scripts entry point from package metadata
#   CLI_NAME=$(ls "$VENV/bin" | grep -v -iE '^(python|pip|activate|wheel)' | grep -v '\.(ps1|csh|fish)$' | while read f; do [ -x "$VENV/bin/$f" ] && echo "$f"; done | head -1)
```

### 3. [STRUCTURAL] `delegate-bootstrap` should fail explicitly when plugin is missing

**Rationale**: When the delegate writes `CLI_ANYTHING_PLUGIN_MISSING` to `delegate-error.txt`, it still routes unconditionally to `verify-cli`. This launches the loop into the inescapable refine cycle even though no bootstrap CLI was produced. The `delegate-bootstrap` state should detect the error marker and route to `diagnose` instead.

**YAML diff**:
```yaml
# In states.delegate-bootstrap:
#   evaluate:
#     type: shell
#     command: "test -f ${captured.run_dir.output}/delegate-error.txt && exit 1 || exit 0"
#   on_yes: verify-cli
#   on_no: diagnose
```

Or more simply, add an `on_error: diagnose` transition to catch failures.

### 4. [STRUCTURAL] Add convergence detection to prevent infinite refine cycles

**Rationale**: The loop cycled `score-bootstrap → delegate-refine → verify-cli → run-cli-tests → score-bootstrap` three times with no measurable improvement in `help_coverage` (always `0.0`). The FSM should detect when metrics stagnate across refine iterations and route to `diagnose` instead of looping until `max_iterations`.

**YAML diff**:
```yaml
# Add to context:
#   max_refine_cycles: 3

# In states.score-bootstrap, add a counter check before routing to delegate-refine.
# If a capture of prior critique scores shows no improvement, route to diagnose.
```

---

## Final Summary

```
Assessment complete for loop: cli-anything-bootstrap

Verdict: partial
  - Terminal state not reached (terminated_by: max_iterations)
  - All 3 contract thresholds unmet (help_coverage stuck at 0.0)
  - Task loop artifact (.loops/generated/*.yaml) never generated
  - CLI harness itself is functional (85 tests passing) — harness verification is broken

Rubric audit: skipped (no llm_structured evaluators)
Laundering check: skipped (no sub-loop states)

Root cause: Case-sensitive grep in verify-cli picks Activate.ps1 over mermaid-cli.
One-line fix: add -i flag to grep and exclude .ps1 files.
```
