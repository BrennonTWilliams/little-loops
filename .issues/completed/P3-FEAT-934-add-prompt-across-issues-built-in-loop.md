---
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-934: Add prompt-across-issues Built-in Loop

## Summary

A new built-in loop `prompt-across-issues` that accepts an arbitrary prompt string via
the `input` parameter and runs that prompt sequentially against each open/active issue,
one at a time, using the FSM loop engine.

## Current Behavior

There is no built-in loop for bulk prompt execution across all open issues. Users who
want to run an ad-hoc command or skill against every issue must either script it
manually, use `ll-auto` (which is opinionated about processing order and issue
state), or write a custom loop YAML. There is no low-friction way to say "run
`/ll:refine-issue` (or any other prompt) on every open issue."

## Expected Behavior

Running `ll-loop run prompt-across-issues "<prompt>"` will:
1. Discover all open/active issues (all categories, excluding completed and deferred)
2. For each issue, inject the issue ID into the prompt and execute it as a Claude Code
   agent step
3. Advance to the next issue after each completes, respecting loop timeout and
   max_iterations guards
4. Report a summary of issues processed and any failures

The `input` parameter (the prompt string) is required. The loop exits with an error
if no prompt is provided.

## Motivation

Power users frequently want to run a single command across all issues (e.g.,
`/ll:normalize-issues`, `/ll:ready-issue`, or a custom refine prompt) without setting
up a full sprint or custom loop. This loop provides a zero-config way to do bulk
issue processing with the full FSM harness (timeout, retry, stall detection) but
without the opinionated structure of `ll-auto` or `ll-sprint`.

## Use Case

A developer wants to run `/ll:refine-issue` across all 15 open issues before a sprint
planning session. Instead of running it manually 15 times or writing a shell script,
they run:

```
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
```

The loop discovers all open issues, runs the refine skill on each in priority order,
and prints a completion summary.

## Acceptance Criteria

- [ ] `ll-loop run prompt-across-issues "<prompt>"` discovers all open/active issues
  and runs the prompt for each, sequentially
- [ ] The `{issue_id}` placeholder in the prompt string is substituted with the
  current issue's ID (e.g., `FEAT-042`) before execution
- [ ] If `input` is empty or missing, the loop exits in the initial state with a
  descriptive error message
- [ ] Issues in `completed/` and `deferred/` directories are excluded
- [ ] Loop respects `max_iterations` and `timeout` guards from standard FSM config
- [ ] Loop is discoverable via `ll-loop list` with a clear description
- [ ] A `ll-loop test prompt-across-issues` dry-run passes without errors

## Proposed Solution

Create `scripts/little_loops/loops/prompt-across-issues.yaml` modeled on
`harness-multi-item.yaml` but simplified:

- **`discover` state**: Use `ll-issues list --json` to get open issues sorted by
  priority; pop the first issue ID into a temp file (same pattern as
  `harness-multi-item`)
- **`execute` state**: Run the `input` prompt with `{issue_id}` substituted using the
  FSM's `input` context variable; delegate to Claude Code via the standard `claude`
  action type
- **`advance` state**: Remove the processed issue from the working list and loop back
  to `discover`
- **`done` state**: Print summary of processed issues
- **`error` state**: Handle missing input or empty issue list gracefully

The loop should not include the full evaluation pipeline (check_stall, check_concrete,
etc.) by default — keep it simple. Users who need quality gates can fork
`harness-multi-item`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `{issue_id}` substitution requires an extra shell state**

The FSM interpolation engine (`scripts/little_loops/fsm/interpolation.py:25`) uses
`VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")` — it exclusively matches `${...}`
syntax. Single-brace `{issue_id}` passes through literally without substitution or
error. The FSM engine will NOT automatically replace `{issue_id}` in the user's input
string.

To substitute the captured issue ID into the user-supplied prompt string, add a
`prepare_prompt` shell state between `discover` and `execute`:

```yaml
prepare_prompt:
  action: |
    ISSUE_ID="${captured.current_item.output}"
    PROMPT="${context.input}"
    echo "$PROMPT" | sed -e "s/{issue_id}/$ISSUE_ID/g"
  action_type: shell
  capture: final_prompt
  next: execute
  on_error: advance

execute:
  action: "${captured.final_prompt.output}"
  action_type: prompt
  max_retries: 3
  on_retry_exhausted: advance
  next: advance
```

State flow: `init → discover → prepare_prompt → execute → advance → (loop: discover | done)`

**Critical: status filter must use `"active"` not `"open"`**

`ll-issues list --json` returns `status: "active"` for open/active issues (not `"open"`).
`harness-multi-item.yaml` has a latent bug where it filters `i.get('status') == 'open'`
which matches nothing — it works only because the default `--status active` flag ensures
the list contains only active issues regardless. The new loop should either:
- Rely on the default (no filter needed — all returned items are already active), or
- Filter `i.get('status') == 'active'` explicitly for clarity

**`init` state pattern for validating required `context.input`**

Based on `scripts/little_loops/loops/greenfield-builder.yaml:21-27`, guard against
missing input in an `init` shell state:

```yaml
init:
  action: |
    if [ -z "${context.input}" ]; then
      echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
      exit 1
    fi
  action_type: shell
  on_yes: discover
  on_error: error
  evaluate:
    type: exit_code
```

### Codebase Research Findings — Round 2

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `discover → advance → discover` will infinite-loop without a temp file**

`harness-multi-item.yaml:28-51` `discover` runs `ll-issues list --json` fresh each
iteration and prints `issues[0]`. For `harness-multi-item` this is safe because its
quality gates (`check_stall`, `check_concrete`, `check_skill`, `check_semantic`,
`check_invariants`) control advancement — the FSM keeps refining the same item until
all gates pass and only then calls `advance → discover`. For `prompt-across-issues`,
running an arbitrary prompt rarely changes issue `status`, so `discover` would always
return the same first issue and the loop would never terminate.

**Fix: Build a pending-list temp file in `init`; pop head in `advance`**

Combine input validation and list initialization in a single `init` shell state:

```yaml
init:
  action: |
    if [ -z "${context.input}" ]; then
      echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
      exit 1
    fi
    mkdir -p .loops/tmp
    ll-issues list --json | python3 -c "
    import json, sys
    issues = json.load(sys.stdin)
    for i in issues:
        print(i['id'])
    " > .loops/tmp/prompt-across-issues-pending.txt
    COUNT=$(wc -l < .loops/tmp/prompt-across-issues-pending.txt | tr -d ' ')
    echo "Found $${COUNT} issues to process"
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: discover
  on_error: error

discover:
  action: |
    if [ ! -s .loops/tmp/prompt-across-issues-pending.txt ]; then
      exit 1
    fi
    head -1 .loops/tmp/prompt-across-issues-pending.txt
  action_type: shell
  capture: current_item
  evaluate:
    type: exit_code
  on_yes: prepare_prompt
  on_no: done
  on_error: done

advance:
  action: |
    sed -i '' '1d' .loops/tmp/prompt-across-issues-pending.txt
    echo "Completed ${captured.current_item.output}"
  action_type: shell
  next: discover
```

Note: `sed -i '' '1d'` is the macOS form; Linux uses `sed -i '1d'`. If cross-platform
support is needed, use `tail -n +2 file > file.tmp && mv file.tmp file` instead.

**Shell variable escaping: `$${...}` for non-FSM shell variables in action strings**

`greenfield-builder.yaml:30` uses `$${SPEC_LIST[@]}` — the double `$$` escapes the
FSM template engine so it renders as `${SPEC_LIST[@]}` in the actual shell command.
Any shell variable that is NOT an FSM context variable must be prefixed with `$$`
(e.g., `$${COUNT}` → `${COUNT}` in the shell). Variables set and used within the same
heredoc action (like `ISSUE_ID` and `PROMPT` in `prepare_prompt`) do not need escaping
since they are not referenced in a separate FSM interpolation pass.

**Complete corrected state flow:**
`init → discover → prepare_prompt → execute → advance → (loop: discover | done | error)`

## API/Interface

```yaml
# Usage
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
ll-loop run prompt-across-issues "/ll:normalize-issues {issue_id} --quick"
ll-loop test prompt-across-issues  # dry-run validation

# YAML loop parameters
name: prompt-across-issues
input: "<prompt-string>"   # required; {issue_id} placeholder substituted per issue
```

The `{issue_id}` substitution is the only template variable. Prompt strings without
`{issue_id}` are valid (the raw prompt is executed unchanged for each issue).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` ← new file

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — executes loop YAML; no changes expected if
  `{issue_id}` substitution is handled via existing FSM context variable injection
- `scripts/little_loops/fsm.py` — FSM engine; verify `input` context variable is
  accessible in action templates

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — primary template to adapt
- `scripts/little_loops/loops/issue-refinement.yaml` — shows issue-focused loop pattern

### Tests
- `scripts/tests/test_loop_runner.py` — add dry-run test for `prompt-across-issues`
- New fixture: mock `ll-issues list --json` returning 2-3 test issues

### Documentation
- `scripts/little_loops/loops/README.md` — add entry for new loop
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — consider referencing as a simpler
  alternative to `harness-multi-item`

### Configuration
- N/A — no config changes; loop is self-contained YAML

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**File path corrections — `fsm.py` and `loop_runner.py` do not exist:**
- `scripts/little_loops/fsm/` is a package, not a single file. Key modules:
  - `scripts/little_loops/fsm/interpolation.py` — variable substitution engine (`${...}` only)
  - `scripts/little_loops/fsm/executor.py` — FSM execution loop; `_run_action()` at line 404 calls `interpolate()` on every action string
  - `scripts/little_loops/fsm/schema.py:487` — `input_key: str = "input"` default; the positional CLI arg maps to `fsm.context["input"]`
  - `scripts/little_loops/fsm/validation.py:432` — `load_and_validate(path)` entry point
- `scripts/little_loops/cli/loop/run.py:59-65` — injects the positional `input` CLI arg into `fsm.context["input"]` before execution; accessible as `${context.input}` in all action templates

**Test file correction — structural tests for built-in loops are in `test_builtin_loops.py`:**
- `scripts/tests/test_builtin_loops.py:48-82` — `test_expected_loops_exist` defines an exact set of 33 stem names (verified); add `"prompt-across-issues"` before `"prompt-regression-test"` (alphabetically, around line 78)
- `scripts/tests/test_builtin_loops.py:36-44` — `test_all_validate_as_valid_fsm` globs `loops/*.yaml` automatically; the new file is validated for free with no test changes
- `scripts/tests/test_builtin_loops.py:277-375` — `TestEvaluationQualityLoop` is the model class; pattern: class-level `LOOP_FILE` constant, single `data` pytest fixture (`yaml.safe_load`), `test_required_top_level_fields` (`name`/`initial`/`states`), `test_required_states_exist` (set comparison), `test_done_state_is_terminal`, plus loop-specific assertions on `action_type`, `capture`, and `action` string content
- No base classes — all structural test classes are plain pytest classes with only a `data` fixture; `conftest.py` fixtures are not used
- `test_loop_runner.py` does not exist as a test file; skip creating it

**Callers of the discovery and execution infrastructure:**
- `scripts/little_loops/cli/loop/info.py:41-140` — `cmd_list` globs `loops/*.yaml` automatically; no registry update needed, the new file is discovered immediately
- `scripts/little_loops/cli/issues/list_cmd.py:96-111` — `ll-issues list --json` output schema: `{id, priority, type, title, path, status, discovered_date}`; status value is `"active"` (not `"open"`)

## Implementation Steps

1. Read `harness-multi-item.yaml` and `issue-refinement.yaml` to understand
   discover/advance patterns and how `input` is threaded through FSM states
2. Verify FSM context variable injection supports `{issue_id}` substitution in action
   strings (check `fsm.py` / `loop_runner.py`)
3. Create `prompt-across-issues.yaml` with `discover → execute → advance → done/error`
   states; wire `input` substitution
4. Add `ll-loop test prompt-across-issues` dry-run test case
5. Update `loops/README.md` with new entry

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Read `scripts/little_loops/loops/harness-multi-item.yaml` (discover/advance/capture
   pattern) and `scripts/little_loops/loops/greenfield-builder.yaml` (required input
   guard pattern) — these are the two primary templates to combine

2. **No engine verification needed** — `scripts/little_loops/fsm/interpolation.py:25`
   confirms `${...}` is the only syntax. `{issue_id}` substitution must be done with
   shell `sed` in a `prepare_prompt` state (see Proposed Solution above).

3. Create `scripts/little_loops/loops/prompt-across-issues.yaml` with this state flow:
   `init → discover → prepare_prompt → execute → advance → (loop: discover | done | error)`

   **⚠ Use temp-file iteration, NOT live `ll-issues list` on every `discover` call** (see
   Proposed Solution → Round 2 findings for why and the corrected YAML):
   - `init`: validate `${context.input}`; build pending list at `.loops/tmp/prompt-across-issues-pending.txt`; `on_yes: discover`, `on_error: error`
   - `discover`: read `head -1` of pending file; exit 1 if empty → `on_no: done`; `capture: current_item`; `on_yes: prepare_prompt`
   - `prepare_prompt`: shell `sed` substitution of `{issue_id}` in `${context.input}`; `capture: final_prompt`; `next: execute`
   - `execute`: `action: "${captured.final_prompt.output}"`; `action_type: prompt`; `max_retries: 3`; `on_retry_exhausted: advance`; `next: advance`
   - `advance`: `sed -i '' '1d'` removes processed item from pending file; `next: discover`
   - `done` / `error`: `terminal: true`

   Shell variables that are not FSM context variables must use `$$` prefix in YAML action
   strings (e.g., `$${COUNT}` renders as `${COUNT}` in the shell — see `greenfield-builder.yaml:30`).

4. Add structural tests to `scripts/tests/test_builtin_loops.py`:
   - **Line 78**: Add `"prompt-across-issues"` to the `expected` set in `test_expected_loops_exist` (insert before `"prompt-regression-test"` alphabetically)
   - Add `TestPromptAcrossIssuesLoop` class modeled on `TestEvaluationQualityLoop` (lines 277-375):
     - `LOOP_FILE = BUILTIN_LOOPS_DIR / "prompt-across-issues.yaml"`
     - `data` fixture: `yaml.safe_load(self.LOOP_FILE.read_text())`
     - `test_required_top_level_fields`: assert `name`, `initial`, `states`
     - `test_required_states_exist`: assert `{"init", "discover", "prepare_prompt", "execute", "advance", "done", "error"}` ⊆ `states`
     - `test_done_state_is_terminal`: `data["states"]["done"]["terminal"] is True`
     - `test_discover_captures_current_item`: `data["states"]["discover"]["capture"] == "current_item"`
     - `test_prepare_prompt_captures_final_prompt`: `data["states"]["prepare_prompt"]["capture"] == "final_prompt"`
     - `test_execute_uses_final_prompt`: assert `"${captured.final_prompt.output}"` in `data["states"]["execute"]["action"]`
     - `test_advance_removes_from_pending_file`: assert `"pending.txt"` in `data["states"]["advance"]["action"]`

5. Update `scripts/little_loops/loops/README.md` with entry for `prompt-across-issues`

## Impact

- **Priority**: P3 - Useful quality-of-life loop; no blockers, no urgency
- **Effort**: Small - New YAML file + 1 test; no engine changes expected
- **Risk**: Low - Additive only; no changes to existing loops or FSM engine
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `captured`

## Verification Notes

_Added by `/ll:verify-issues` — 2026-04-03; updated by `/ll:ready-issue` — 2026-04-03_

**Verdict: VERIFIED**

All file paths, line numbers, and implementation guidance verified accurate. Previously noted count discrepancy (32 vs 33 stem names) was resolved in round-2 refine pass — Codebase Research Findings now correctly states **33** entries.

All claims verified valid against current codebase:
- `interpolation.py:25` VARIABLE_PATTERN ✓, `schema.py:487` input_key ✓, `validation.py:432` load_and_validate ✓, `executor.py:404` _run_action ✓
- `run.py:59-65` input injection ✓, `info.py:41-140` cmd_list ✓, `list_cmd.py:96-111` JSON output ✓
- `_load_issues_with_status` returns `"active"` (not `"open"`) ✓
- `harness-multi-item.yaml:40` filters `status == 'open'` (latent bug confirmed) ✓
- `greenfield-builder.yaml:30` `$${SPEC_LIST[@]}` escaping ✓, init guard pattern ✓
- `test_loop_runner.py` does not exist ✓, `loops/README.md` exists ✓
- `TestEvaluationQualityLoop` lines 277–378 (issue says 277–375, off by 3 — trivial)

---

## Session Log
- `/ll:ready-issue` - 2026-04-03T21:31:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/781cd409-1287-4ed8-8538-160976825726.jsonl`
- `/ll:verify-issues` - 2026-04-03T21:12:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da412530-a136-4ca2-8ad0-561ef83f8cfa.jsonl`
- `/ll:refine-issue` - 2026-04-03T20:38:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9fb6d8e-2848-4332-aa27-d55b2a74404d.jsonl`
- `/ll:verify-issues` - 2026-04-03T06:30:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc85b7a5-3260-4421-838d-a5b229e66e87.jsonl`
- `/ll:refine-issue` - 2026-04-03T06:27:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T06:22:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`

---

## Resolution

**Implemented** on 2026-04-03.

### Changes Made

- `scripts/little_loops/loops/prompt-across-issues.yaml` — new loop with state flow:
  `init → discover → prepare_prompt → execute → advance → (loop: discover | done | error)`
- `scripts/tests/test_builtin_loops.py` — added `"prompt-across-issues"` to
  `test_expected_loops_exist` and `TestPromptAcrossIssuesLoop` structural test class
- `scripts/little_loops/loops/README.md` — added entry under Issue Management section

### Acceptance Criteria Verification

- [x] `ll-loop run prompt-across-issues "<prompt>"` discovers all open/active issues and runs the prompt for each, sequentially — implemented via temp-file pending list
- [x] `{issue_id}` placeholder substituted with current issue's ID via `prepare_prompt` shell sed state
- [x] Empty/missing `input` exits in init state with descriptive error message
- [x] `completed/` and `deferred/` issues excluded — `ll-issues list --json` defaults to `--status active`
- [x] Loop respects `max_iterations` (500) and `timeout` (28800s) guards
- [x] Discoverable via `ll-loop list` — globbed automatically by `info.py`
- [x] `ll-loop test prompt-across-issues` dry-run passes — covered by `test_all_validate_as_valid_fsm`

## Session Log
- `/ll:manage-issue` - 2026-04-03T00:00:00Z - current session

## Status

**Completed** | Created: 2026-04-03 | Priority: P3
