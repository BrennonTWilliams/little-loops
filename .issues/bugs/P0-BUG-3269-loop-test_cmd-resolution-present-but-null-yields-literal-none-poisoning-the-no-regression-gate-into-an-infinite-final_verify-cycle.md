---
id: BUG-3269
type: BUG
title: 'Loop test_cmd resolution: present-but-null yields literal "None", poisoning
  the no-regression gate into an infinite final_verify cycle'
priority: P0
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T22:48:59Z'
labels:
- bug
- loops
- general-task
- config
- test-cmd
- postmortem
relates_to:
- ENH-2244
- BUG-3270
- BUG-3271
- ENH-3272
---

# BUG-3269: Loop test_cmd resolution: present-but-null yields literal "None", poisoning the no-regression gate into an infinite final_verify cycle

## Summary

Every loop that resolves `project.test_cmd` from `.ll/ll-config.json` hand-rolls its own
inline `python3 -c` snippet. There are ~10 such copies and they do not agree. Two of them
(`general-task.yaml:37`, `rl-coding-agent.yaml:60`) use `dict.get(key, default)`, which
returns the default only when the key is **absent** — when the key is present with value
`null`, they return `None` and `print(None)` emits the literal string `None`, which the
shell then tries to execute.

Exactly one copy (`fix-quality-and-tests.yaml:66-72`) implements the correct
present-vs-absent semantics. This issue lifts that copy into a shared
`lib/common.yaml` fragment, converts every site to it, and adds a mirror-drift gate so the
eleventh copy cannot reintroduce the defect.

Discovered by forensic audit of `general-task` run `2026-08-20T121448` in
an external docs-oriented project with `test_cmd: null`, which spun for
2h37m / 45 identical laps on a task that had already succeeded. Postmortem:
`postmortems/general-task-final-verify-spin-2026-08-20.md` (§2, §5).

## Current Behavior

**Divergent resolution inside a single loop.** `general-task.yaml` resolves the same
config key two different ways:

`general-task.yaml:37` — `check_baseline_tests`:

```python
print(cfg.get('project',{}).get('test_cmd','pytest'))
```

`general-task.yaml:613-618` — `run_final_tests`:

```python
raw = cfg.get('project', {}).get('test_cmd')
print(raw if raw else 'pytest')
```

Reproduction of the divergence:

```
$ python3 -c "cfg={'project':{'test_cmd':None}}; print(repr(cfg.get('project',{}).get('test_cmd','pytest')))"
None
$ python3 -c "cfg={'project':{'test_cmd':None}}; raw=cfg.get('project',{}).get('test_cmd'); print(repr(raw if raw else 'pytest'))"
'pytest'
```

**Observed failure chain (verified against the run's artifacts):**

1. `check_baseline_tests` runs `eval "None"` → `bash: line 1: None: command not found`
   → writes **`127`** to `baseline-exit.txt`. Both artifacts survive in the run dir:
   `baseline-test-output.txt` = `bash: line 1: None: command not found` (38 bytes),
   `baseline-exit.txt` = `127`.
2. The state has `on_error: define_done`, so the garbage baseline is silently accepted.
3. `run_final_tests` resolves the *same* config to `pytest`, which exits **2**
   (12 pre-existing `ModuleNotFoundError` collection errors, unrelated to the task).
4. The ENH-2244 no-regression gate evaluates `[ "2" = "0" ] || [ "2" = "127" ]` →
   **false** → `on_no: continue_work`.
5. `continue_work` re-asks the model, which correctly answers `WORK_COMPLETE` →
   `final_verify` → `run_final_tests` → step 4. Forever. 45 laps until SIGKILL.

The gate logic in step 4 is correct. Its input was poisoned at second 0 and nothing
downstream could recover.

**Second, independent instance of the same defect.** `rl-coding-agent.yaml:60`:

```python
print(cfg.get('project', {}).get('test_cmd', '${context.test_cmd}'))
```

Same shape — present-but-null returns `None`, not the context override. This one feeds a
**reward signal**: `observe` computes `TEST_SCORE` from the output of `eval "$TEST_CMD"`,
so under a null config every rollout is scored against `command not found` output, yielding
`PASSED=0` and a silently meaningless composite reward. No spin, no crash — just wrong
numbers. The `lint_cmd` resolution two lines below (`:67`) has the identical shape.

**The correct semantics already exist here.** `fix-quality-and-tests.yaml:66-72`:

```python
raw = cfg.get('project', {}).get('test_cmd')
# None/null means 'no tests configured' — skip with success
# Missing key means 'not configured yet' — default to pytest
if 'project' in cfg and 'test_cmd' in cfg['project']:
    print(raw if raw else 'true')
else:
    print(raw if raw else 'pytest')
```

This is the only site out of ~10 that distinguishes present-and-null from absent.

## Steps to Reproduce

**Minimal — the resolution divergence itself:**

```
$ python3 -c "cfg={'project':{'test_cmd':None}}; print(repr(cfg.get('project',{}).get('test_cmd','pytest')))"
None
$ python3 -c "cfg={'project':{'test_cmd':None}}; raw=cfg.get('project',{}).get('test_cmd'); print(repr(raw if raw else 'pytest'))"
'pytest'
```

The first is `general-task.yaml:37`; the second is `general-task.yaml:617`. Same config,
same loop, two answers.

**Full — the infinite cycle:**

1. Create a scratch project with `.ll/ll-config.json` containing
   `{"project": {"test_cmd": null}}`. The key must be **present and null** — omitting it
   does not reproduce.
2. Ensure a bare `pytest` in that project exits non-zero (e.g. any collection error). A
   docs or diagram project with no test suite satisfies this naturally.
3. Run `general-task` with any task that will actually complete.
4. Observe `${run_dir}/baseline-test-output.txt` = `bash: line 1: None: command not found`
   and `${run_dir}/baseline-exit.txt` = `127` — written at second 0, before any work.
5. Let the run reach `final_verify`. It cycles
   `continue_work → final_verify → run_final_tests → continue_work` indefinitely, with
   `done_counts.total == 0` and `continue_result == WORK_COMPLETE` on every lap.
6. The run only ends at `max_iterations` or by manual SIGKILL.

**Frequency**: deterministic. Every run of an affected loop in a project with an explicit
`test_cmd: null` and a failing bare `pytest`.

**Observed in**: `general-task` v1.156.0, run `2026-08-20T121448`. 356 iterations,
~4h58m wall clock, terminated by user SIGKILL.

## Expected Behavior

One resolution path, three outcomes:

| Config state | Resolved command | Rationale |
|---|---|---|
| `test_cmd` absent | `pytest` | Not configured yet — the existing guess is a reasonable default. |
| `test_cmd: null` (explicit) | **no test gate** | The project deliberately opted out. Do not guess. |
| `test_cmd: "<cmd>"` | `<cmd>` | Explicit. |

For `general-task` specifically:

- `check_baseline_tests` must never write a garbage exit code. When there is no runnable
  baseline — resolved command is the opt-out sentinel, **or** the command exits 127,
  **or** `baseline-test-output.txt` matches `command not found` — write
  `baseline-exit.txt` = `SKIP`.
- `run_final_tests` must treat `baseline-exit.txt` = `SKIP` as "no baseline to compare
  against — pass on non-crash", never as a numeric exit code to match. A baseline that
  never ran must never be compared against.
- Under explicit `test_cmd: null`, `run_final_tests` routes straight to `count_final`
  without running anything.

## Motivation

**This is live in every consuming project right now.** Per `.claude/CLAUDE.md`, all
little-loops projects on this machine are `local-editable` against this checkout, so the
defect ships with no reinstall step — and so does the fix. Any project with
`test_cmd: null` (the common shape for docs, diagram, config, and non-Python projects)
that runs `general-task` will burn its full iteration budget on a task that already
succeeded. The observed cost was ~4h58m wall clock, 356 iterations, 1.72M output tokens,
of which 331 iterations produced no deliverable change.

**Fixing line 37 in place is not sufficient.** The duplication *is* the bug: nine other
sites are one careless edit from the same failure, and `rl-coding-agent` already has it.

## Proposed Solution

### 1. Shared fragment in `lib/common.yaml`

Add a `resolve_test_cmd` fragment implementing the `fix-quality-and-tests.yaml` semantics,
parameterized so callers pick their own opt-out behavior:

- `context_override` — optional `${context.test_cmd}`-style explicit override, checked first.
- `absent_default` — command when the key is absent (default `pytest`).
- `null_sentinel` — what to emit on explicit null; callers either get a
  no-op command (`true`) or a sentinel string they branch on.

Model it on the existing `shell_exit` / `retry_counter` fragments (`lib/common.yaml:15`,
`:38`), which already use the `parameters:` + `${param.x}` convention.

### 2. Convert all call sites

| File | Line | Current shape |
|---|---|---|
| `general-task.yaml` | 37 | **buggy** — `.get('test_cmd','pytest')` |
| `general-task.yaml` | 617 | correct-but-guessing |
| `rl-coding-agent.yaml` | 60 | **buggy** — `.get('test_cmd', '${context.test_cmd}')` |
| `rl-coding-agent.yaml` | 67 | **buggy** — same shape for `lint_cmd` |
| `fix-quality-and-tests.yaml` | 66 | reference implementation |
| `evaluation-quality.yaml` | 58 | correct-but-guessing |
| `dead-code-cleanup.yaml` | 76 | correct-but-guessing |
| `harness-plan-research-implement-report.yaml` | 126 | correct-but-guessing |
| `harness-multi-item.yaml` | 95 | correct-but-guessing |
| `harness-single-shot.yaml` | 66 | correct-but-guessing |
| `test-coverage-improvement.yaml` | 45, 152 | correct-but-guessing |
| `rn-refine.yaml` | 991 | already null-safe (`or ''`) — verify semantics match, then convert |

"correct-but-guessing" = null-safe (won't emit `None`) but still overrides an explicit
`null` with a `pytest` guess. Those are not blockers, but they are the BUG-3269 behavior and
should move to the shared fragment in the same pass.

Note `test-coverage-improvement.yaml` and `general-task.yaml` also carry a
`${context.test_cmd}` shell-level override ahead of the python snippet; the fragment must
preserve that precedence.

### 3. Baseline sentinel in `general-task`

`check_baseline_tests` writes `SKIP` instead of an exit code when the baseline is
unrunnable; `run_final_tests` branches on `SKIP` before its numeric comparison.

### 4. Mirror-drift gate (regression test)

A shared fragment alone does not stop the eleventh copy — nothing forces a new loop to use
it. Add a parametrized test over every `scripts/little_loops/loops/**/*.yaml` that:

- locates each `test_cmd` / `lint_cmd` resolution snippet,
- executes it against `{"project": {"test_cmd": null}}` and against `{}`,
- asserts neither yields the literal `None` and that the null case does not resolve to a
  guessed `pytest`.

Follow the parametrize-over-a-registry pattern from commit `fb747a60`
(`test(adapters): parametrize mirror-drift gate over _EMITTER_MAP hosts`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add the `resolve_test_cmd` fragment
- `scripts/little_loops/loops/general-task.yaml:37` — **buggy site** (`check_baseline_tests`)
- `scripts/little_loops/loops/general-task.yaml:617` — `run_final_tests`; also add `SKIP` handling
- `scripts/little_loops/loops/rl-coding-agent.yaml:60,67` — **buggy sites** (`test_cmd` + `lint_cmd`)
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:66` — reference impl, collapses into the fragment
- `scripts/little_loops/loops/evaluation-quality.yaml:58`
- `scripts/little_loops/loops/dead-code-cleanup.yaml:76`
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126`
- `scripts/little_loops/loops/harness-multi-item.yaml:95`
- `scripts/little_loops/loops/harness-single-shot.yaml:66`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:45,152`
- `scripts/little_loops/loops/rn-refine.yaml:991` — verify semantics before converting

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/` — fragment resolution (`fragment:` key handling); confirm
  `parameters:`/`${param.x}` binding supports the new fragment's shape without executor changes
- Any consuming project's `.ll/ll-config.json` supplying `project.test_cmd`

### Similar Patterns
- `lib/common.yaml:15` `shell_exit` and `:38` `retry_counter` — the fragment + `parameters:`
  convention to model on
- `scripts/little_loops/loops/incremental-refactor.yaml:12,33` — uses a plain
  `${context.test_cmd}` with no config read; confirm it is genuinely out of scope

### Tests
- New: mirror-drift gate parametrized over every `scripts/little_loops/loops/**/*.yaml`
  (see Proposed Solution §4)
- `scripts/tests/test_builtin_loops.py` — existing built-in-loop validation; the new gate
  belongs alongside it
- Pattern reference: commit `fb747a60` (`test(adapters): parametrize mirror-drift gate over
  _EMITTER_MAP hosts`)

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the fragment as the required way to
  resolve a project command inside a loop
- `scripts/little_loops/config-schema.json` — confirm `project.test_cmd` documents `null` as
  the explicit opt-out, not merely "unset"

### Configuration
- `.ll/ll-config.json` → `project.test_cmd` — the key whose present-vs-absent-vs-null
  semantics this issue defines

## Program Design

### Signatures

- `resolve_test_cmd(config_key, absent_default, null_value) -> str` — new `lib/common.yaml`
  fragment; the single resolution path replacing ~12 hand-rolled inline snippets.
- `check_baseline_tests() -> writes baseline-exit.txt: int | "SKIP"` — widened from
  `int` only; `SKIP` is the new no-runnable-baseline sentinel.
- `run_final_tests(baseline_exit: int | "SKIP") -> bool` — gates on `FINAL_EXIT` alone when
  the baseline is `SKIP`, on the ENH-2244 equality comparison otherwise.

Fragment parameters (following the `retry_counter` convention):

- `config_key` (string, default `test_cmd`) — which `project.*` key to resolve, so the same
  fragment serves `lint_cmd` for `rl-coding-agent.yaml:67`.
- `absent_default` (string, default `pytest`) — emitted when the key is **absent**.
- `null_value` (string, default `true`) — emitted when the key is present-and-null. Callers
  that need to branch rather than run a no-op pass a sentinel (`general-task` passes `SKIP`).

### Call Path

- `check_baseline_tests` → `resolve_test_cmd` — first resolution; writes `baseline-exit.txt`.
  Currently the buggy site at `general-task.yaml:37`.
- `check_baseline_tests` → `define_done` → `plan` → … → `final_verify` → `run_final_tests`
  — the poisoned `baseline-exit.txt` travels this far before anything reads it.
- `run_final_tests` → `resolve_test_cmd` — second resolution of the same key; reads
  `baseline-exit.txt` and must branch on `SKIP` before the numeric comparison.
- `run_final_tests` → `count_final` — the opt-out path; taken directly, running nothing,
  when the key is explicitly null.
- `run_final_tests` → `continue_work` — the gate-failed edge; the entry point of the
  infinite cycle when the baseline is garbage.
- `observe` → `resolve_test_cmd` (in `rl-coding-agent.yaml`) — the second buggy site;
  its result feeds `TEST_SCORE` in the composite reward.
- `resolve_fragments` (`scripts/little_loops/fsm/fragments.py:66`) — the existing
  fragment-resolution entry point that expands every `fragment: <name>` / `with:`
  call site at load time, including the new `resolve_test_cmd` fragment once it is
  added to `lib/common.yaml`. No executor change is required; this confirms the
  fragment mechanism the fix depends on already exists and needs no modification.

### Resolution contract

**`lib/common.yaml` — new fragment `resolve_test_cmd`**

Parameters (following the `retry_counter` convention at `lib/common.yaml:38`):

- `config_key` (string, default `test_cmd`) — which `project.*` key to resolve, so the same
  fragment serves `lint_cmd` for `rl-coding-agent.yaml:67`.
- `absent_default` (string, default `pytest`) — emitted when the key is **absent**.
- `null_value` (string, default `true`) — emitted when the key is present-and-null. Callers
  that need to branch rather than run a no-op pass a sentinel (`general-task` passes `SKIP`).

Resolution order, all three cases distinguished:

1. Non-empty `${context.<key>}` shell-level override → use it verbatim.
2. `.ll/ll-config.json` missing, or `project` absent, or key absent → `absent_default`.
3. Key present and falsy (`null` / `""`) → `null_value`.
4. Key present and truthy → its value.

The python snippet is the `fix-quality-and-tests.yaml:66-72` body, generalized — the
present-vs-absent test is `'<key>' in cfg.get('project', {})`, never
`dict.get(key, default)`.

**`general-task.yaml` — baseline sentinel contract**

- `check_baseline_tests` writes `baseline-exit.txt` = `SKIP` when the resolved command is
  the opt-out sentinel, **or** the command exits `127`, **or** `baseline-test-output.txt`
  matches `command not found`. Otherwise it writes the numeric exit code as today.
- `run_final_tests` reads `baseline-exit.txt` and branches **before** its numeric
  comparison: `SKIP` → treat as pass-on-non-crash (gate on `FINAL_EXIT` alone, never on
  equality with the baseline). This preserves the ENH-2244 comparison for every run that
  has a real baseline.
- Under the opt-out, `run_final_tests` routes straight to `count_final` without running
  anything.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Confirmed current anchors (line numbers below reflect the file as it stands today; the issue's original citations have drifted)**:
  - `scripts/little_loops/loops/general-task.yaml:37` — **buggy site**, `check_baseline_tests` (state header `:35`): `print(cfg.get('project',{}).get('test_cmd','pytest'))` — emits literal `None` on present-but-null.
  - `scripts/little_loops/loops/general-task.yaml:613-620` (state header `run_final_tests` `:596`) — the correct-but-guessing sibling: `raw = cfg.get('project', {}).get('test_cmd')` / `print(raw if raw else 'pytest')`. Within this one file the two sites already disagree with each other.
  - `scripts/little_loops/loops/rl-coding-agent.yaml:60` (`test_cmd`) and `:68` (`lint_cmd`) — both **buggy sites**, state `observe` (header `:53`): `print(cfg.get('project', {}).get('<key>', '${context.<key>}'))`.
  - `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — reference implementation, state `check-tests`. `raw = cfg.get('project', {}).get('test_cmd')` at `:66`; three-way branch (`'project' in cfg and 'test_cmd' in cfg['project']` → `raw if raw else 'true'`, else `raw if raw else 'pytest'`) at `:69-72`.
  - Correct-but-guessing sites confirmed at current lines: `evaluation-quality.yaml:58` (raw, snippet `55-61`); `dead-code-cleanup.yaml:76` (snippet `73-79`); `harness-plan-research-implement-report.yaml:126` (snippet `122-129`); `harness-multi-item.yaml:95` (snippet `91-98`); `harness-single-shot.yaml:66` (snippet `63-69`); `test-coverage-improvement.yaml` two sites — `38-48` (override-guarded, raw at `45`) and `149-155` (raw at `152`).
  - `rn-refine.yaml:988-994` is a **distinct third fallback convention**, not the raw/if-else idiom: `print(cfg.get('project', {}).get('test_cmd') or '')` wrapped in `try/except`, degrading to `''` (not `'pytest'`) on any error. Converting this site must account for a different downstream contract than the other sites.
- **Fragment mechanism** (`scripts/little_loops/loops/lib/common.yaml`): top-level key is `fragments:` (`:14`); a fragment supplies state-level keys merged into the caller. Parameterized fragments declare `parameters:` (each entry has `type` + `required` or `default`) and are referenced via `${param.<name>}` inside the fragment body; the caller supplies values via a `with:` block at the `fragment: <name>` call site. Reference example: `retry_counter` (`lib/common.yaml:38-60`) — `counter_key` (required string) and `max_retries` (default 3). Unparameterized fragments (`shell_exit`, etc.) take no `with:` block. Resolution is implemented in `scripts/little_loops/fsm/fragments.py` (`resolve_fragments`, imported at `scripts/tests/test_builtin_loops.py:18`).
- **Call path, `baseline-exit.txt`**: `check_baseline_tests` (`:35-43`) writes `${context.run_dir}/baseline-test-output.txt` and `${context.run_dir}/baseline-exit.txt` via `eval "$CMD" > ... 2>&1; echo $? > baseline-exit.txt` (`:38-39`); `on_error: define_done` (`:43`) means even a shell-level failure still proceeds. `run_final_tests` (`:596-627`) later reads `baseline-exit.txt` (`:623`) and gates on `[ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "$BASELINE_EXIT" ]` (`:624`) — `on_no: continue_work` (`:626`).
- **Mirror-drift gate precedent — correction to the Proposed Solution's citation**: the `fb747a60` pattern actually lives in `scripts/tests/test_wiring_skills_and_commands.py:376-424` (`GATED_HOSTS` list + `@pytest.mark.parametrize("host", GATED_HOSTS)` over `resolve_emitter`'s own registry), not in `test_builtin_loops.py`'s generic `builtin_loops` fixture (`:34-40`). A new mirror-drift gate for `test_cmd`/`lint_cmd` resolution should follow the `test_wiring_skills_and_commands.py` registry-parametrize shape — a `GATED_LOOPS` constant plus one assertion per site that it delegates to `fragment: resolve_test_cmd` rather than an inline snippet — while `builtin_loops` remains the right fixture if a blanket scan-every-loop-file approach is preferred instead.

## Implementation Steps

1. **Add the fragment.** Write `resolve_test_cmd` in `lib/common.yaml` per Program Design.
   Unit-test it standalone against all four resolution cases before touching any loop.
2. **Fix the two blockers.** Convert `general-task.yaml:37` and `rl-coding-agent.yaml:60,67`
   — these are the sites that emit literal `None` today.
3. **Add the baseline sentinel.** Implement the `SKIP` contract in
   `check_baseline_tests` + `run_final_tests`.
4. **Convert the remaining sites.** The nine correct-but-guessing copies, one file at a
   time, running `ll-loop validate` after each.
5. **Land the mirror-drift gate.** Parametrized over every loop YAML; assert no snippet
   yields literal `None` under `{"project": {"test_cmd": null}}` and that the null case does
   not resolve to a guessed `pytest`. Confirm it fails before step 2's fix and passes after.
6. **Verify.** `python -m pytest scripts/tests/` exits 0; `ll-loop validate` clean on every
   converted loop; manual smoke of `general-task` in a scratch project with
   `test_cmd: null` reaching a terminal state instead of cycling.

## Impact

- **Severity**: P0. Silently burns a full iteration budget and the user's tokens on
  already-completed work; requires manual SIGKILL to stop. Corrupts RL reward signal in a
  second loop.
- **Blast radius**: `general-task` is the most-used built-in loop and is live in every
  local-editable consuming project.
- **Risk of the fix**: low-moderate. The fragment itself is small; the risk is in
  converting 12 call sites across 10 loop files. Each conversion is mechanically checkable
  by the new gate.
- **Backward compatibility**: projects with a non-null `test_cmd` see no behavior change.
  Projects with `test_cmd: null` change from "guess pytest" to "no test gate" — that is
  the intended fix, and matches what `fix-quality-and-tests.yaml` already does.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` — full forensic audit
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop design rules
- ENH-2244 — the baseline-comparison gate whose null-config failure mode this is
- ENH-2225 — final-only whole-suite gate (`run_final_tests`)

## Status

**Open** | Created: 2026-08-20 | Priority: P0


## Session Log
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
