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
- BUG-3274
confidence_score: 88
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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
present-vs-absent semantics — but the existing `ll-config get` CLI already implements those
semantics *and* honors `.ll/ll.local.md`, which all 13 inline copies silently ignore. This
issue deletes every inline snippet in favor of `ll-config get project.<key>` and adds a
static mirror-drift gate so the fourteenth copy cannot reintroduce the defect.

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
  against", never as a numeric exit code to match. A baseline that never ran must never be
  compared against. **"Pass on non-crash" is defined precisely as: pass when
  `FINAL_EXIT` is `0` *or* `127`.** The `127` arm is load-bearing — see below.
- **`test_cmd` may be present, non-null, and still unrunnable** (e.g. `"make test"` in a
  project without `make`). Then the baseline exits 127 → `SKIP`, and `run_final_tests`
  exits 127 too. If `SKIP` meant only "require `FINAL_EXIT = 0`", that run spins on the
  exact BUG-3269 cycle with a *non-null* config — this fix would close only the
  `test_cmd: null` path. Admitting `127` under `SKIP` closes it: an unrunnable command
  never gates. A command that runs and genuinely fails (exit 1, 2, …) still gates
  normally. BUG-3270's spin guard remains the backstop for any residual cycle, but this
  issue must not rely on it to be correct.
- Under explicit `test_cmd: null`, `run_final_tests` runs nothing and passes. (It is a
  `shell_exit` state evaluated by exit code, so "route to `count_final`" means the action
  exits 0 without invoking a command — not a distinct routing edge.)

Note the opt-out must be declared in `.ll/ll-config.json`. An explicit `null` in
`.ll/ll.local.md` frontmatter means *remove this override* under the documented local-merge
semantics, which resolves to the absent-default (`pytest`), not to opt-out — verified
below. That asymmetry is expected, not a second defect, but it must be documented.

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

> **Revised 2026-08-20 after design review.** The original plan proposed a
> `resolve_test_cmd` fragment in `lib/common.yaml`. That mechanism cannot express this
> fix (see *Rejected approach* below), and it also missed an existing helper that already
> implements the required semantics correctly. The plan now routes every site through
> `ll-config get`.

### 1. Delegate to the existing `ll-config get` CLI

`ll-config get project.test_cmd` (`scripts/little_loops/cli/config.py`) **already
implements the exact three-way contract** from Expected Behavior. Verified empirically:

| `.ll/ll-config.json` | `ll-config get project.test_cmd` |
|---|---|
| `{"project":{"test_cmd":null}}` | *(empty)* — opt-out |
| `{"project":{}}` | `pytest` |
| `{"project":{"test_cmd":"make test"}}` | `make test` |
| file absent entirely | `pytest` |

`project.lint_cmd` behaves identically (absent-default `ruff check .`) — checked, **no
gap**. So the same call serves `rl-coding-agent.yaml:68`.

The three-way split arises because `ProjectConfig.from_dict` uses
`data.get("test_cmd", "pytest")` (`config/core.py:215`) — absent yields the default
string, present-and-null yields `None` — and `BRConfig.resolve_variable` returns `None`
for a null value (`config/core.py:1056-1057`), which `main_config` prints as nothing
(`cli/config.py:75-76`). This is correct but **load-bearing and unpinned**: the field is
annotated `str` while holding `None`, exactly the BUG-3274 defect shape. A future
type-correctness cleanup that coerces `None → "pytest"` would silently destroy the opt-out.
Step 5 pins it with a regression test.

**Each call site collapses to one line:**

```bash
CMD=$(ll-config get project.test_cmd)
[ -z "$CMD" ] && { : "no test command configured — skip"; }
```

`ll-config` is on PATH by construction: the loop is being executed by `ll-loop` from the
same installed package.

**This is a new convention, not an established one.** No loop YAML currently invokes
`ll-config` — verified by grep over `scripts/little_loops/loops/**`; every existing
reference is either a prose comment or an inline `.ll/ll-config.json` read. There is no
in-repo precedent to copy, which is why the harness-guide documentation in Step 6's wiring
list is part of the deliverable rather than a nicety.

**Cost per call**: ~0.17s wall (measured), and each invocation opens a
`cli_event_context` against `history.db` (`cli/config.py:66`), so under
`analytics.capture.cli_commands: ["*"]` every resolution writes an event row. Negligible for
`general-task` (2 calls/run), but `rl-coding-agent`'s `observe` fires 2 calls **per
rollout**. Acceptable — the inline `python3 -c` it replaces costs the same order — but it
should not be pushed into a tighter inner loop without re-measuring.

### 1b. Second bug this closes: local overrides are ignored today

All 13 inline snippets parse `.ll/ll-config.json` raw, bypassing `BRConfig`'s
`.ll/ll.local.md` merge (`config/core.py:272-276`, BUG-3123) — the mechanism
`.claude/CLAUDE.md` documents *specifically* for overriding `project.test_cmd`. Verified:

```
.ll/ll-config.json: "from-json"   .ll/ll.local.md: "from-local-md"
ll-config get   → from-local-md
inline snippet  → from-json          ← today's behavior in all 13 loops
```

A shared YAML fragment that still parsed raw JSON would have frozen this defect into a
single blessed implementation. Delegating to `ll-config` fixes it everywhere at once.

### 1c. Rejected approach: a `lib/common.yaml` fragment

Recorded so it is not re-proposed. Fragments cannot express a *substring* of a shell
action, for three independent reasons:

1. **Fragments merge whole state-level keys, not fragments of an action.**
   `resolve_fragments` deep-merges the fragment body into the state with **state keys
   winning** (`fsm/fragments.py:139-147`). Every call site embeds the snippet *inside* a
   larger action (resolve → `eval` → write artifacts); a fragment's `action:` would be
   clobbered by the state's own `action:`. There is no splice primitive.
2. **One `fragment:` key per state.** `run_final_tests` already declares
   `fragment: shell_exit` (`general-task.yaml:605`) and cannot also declare
   `resolve_test_cmd`.
3. **Some states need two resolutions.** `rl-coding-agent.yaml`'s `observe` resolves
   `test_cmd` *and* `lint_cmd` in one action; a parameterized fragment binds once per state.

### 1d. Explicitly out of scope: `oracles/code-run-gate.yaml`

Its `get_value()` convention (`:143-154`) reads the same file but is **not** convertible,
and converting it would be a regression:

- It resolves the config path from `${context.project_root}` (`:134`), whereas
  `ll-config get` resolves from `Path.cwd()` with no upward walk
  (`config/core.py:256`). Behavior would change whenever cwd ≠ project root.
- It resolves **alias pairs** (`typecheck_cmd|type_cmd`, `start_cmd|run_cmd`, per
  ARCHITECTURE-123). `ll-config get` has no alias support, and `typecheck_cmd`/`start_cmd`
  are not `ProjectConfig` fields at all.
- Its contract is deliberately *absent ≡ null ≡ skip, never guess*. Under `ll-config`,
  absent `type_cmd` resolves to the dataclass default `mypy` and absent `lint_cmd` to
  `ruff check .` — so a project that never configured them would suddenly start running
  them. Verified: `ll-config get project.type_cmd` → `mypy` on `{"project":{}}`.

Leave it as-is and register it as a documented exemption in the mirror-drift gate (§4).

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
should move to `ll-config get` in the same pass. All of them additionally ignore
`.ll/ll.local.md` today (§1b).

**Precedence is NOT uniform across call sites — there is no single snippet.** `ll-config
get` knows nothing about loop context, so the ordering must be written explicitly in shell,
and the correct ordering differs per loop:

| Site | Context default | Documented precedence today | Required shell |
|---|---|---|---|
| `general-task.yaml:610-616` (`run_final_tests`) | empty | context override → config → `pytest` | context-first |
| `general-task.yaml:36-40` (`check_baseline_tests`) | **no override at all** | config only | context-first (**new** — see below) |
| `test-coverage-improvement.yaml:38-48` | `""` (`:23`) | context override → config → `pytest` | context-first |
| `rl-coding-agent.yaml:60,68` | **non-empty** (`:17-18`) | **config → context → default** (`:55` comment) | **config-first** |

Context-first sites:

```bash
if [ -n "${context.test_cmd}" ]; then CMD="${context.test_cmd}"; else CMD=$(ll-config get project.test_cmd); fi
```

**The context-first shape is wrong for `rl-coding-agent.yaml` and must not be pasted
there.** Its context defaults are non-empty literals (`test_cmd: "python -m pytest"`,
`lint_cmd: "ruff check"`, `:17-18`), so `[ -n "${context.test_cmd}" ]` is *always* true,
`ll-config get` would never execute, and the two buggy sites would silently stop reading
`project.test_cmd` altogether — trading an emitted `None` for a total loss of project
configuration. Use config-first there:

```bash
CMD=$(ll-config get project.test_cmd)
[ -z "$CMD" ] && SKIP_TESTS=1   # explicit null → opt out of test scoring
```

**Decision required before implementation (rl-coding-agent only).** `ll-config get` collapses
absent and null into "empty vs the field default", so config-first cannot fall back to the
context override on *absent* — absent resolves to `pytest` / `ruff check .` from
`ProjectConfig`, and the `${context.test_cmd}` / `${context.lint_cmd}` defaults at `:17-18`
become dead. Two options: **(a)** accept that, delete the two context defaults, and document
`ProjectConfig`'s field defaults as the only fallback (recommended — one authority, matches
§1); or **(b)** keep the overrides by testing them separately with a second probe. Pick (a)
unless a consumer is known to rely on those context values.

Behavior change for `rl-coding-agent.yaml` under option (a): with the key **absent** it
resolves to `pytest` / `ruff check .` rather than the context literal; with the key
**present and null** it now skips test/lint scoring instead of scoring against
`command not found`.

**`check_baseline_tests` gains an override it does not have today.** `general-task.yaml:37`
reads config directly with no `${context.test_cmd}` check, while `run_final_tests:610-616`
checks the override first. That is a *second* divergence axis inside the same file, distinct
from the null-handling one: with `context.test_cmd` set, the baseline and the final gate
resolve to different commands, and the ENH-2244 equality comparison then compares two
different test suites. Converting only the null semantics leaves this intact. Both states
must end up with byte-identical resolution shell.

### 3. Baseline sentinel in `general-task`

`check_baseline_tests` writes `SKIP` instead of an exit code when the baseline is
unrunnable; `run_final_tests` branches on `SKIP` before its numeric comparison. With
`ll-config get`, the opt-out signal is an **empty string**, tested with `[ -z "$CMD" ]` —
not a `SKIP` command string that could collide with a real command. `SKIP` remains the
sentinel written to `baseline-exit.txt`, where it cannot collide with an exit code.

This also removes the `rn-refine.yaml:988-994` conversion caveat: that site already
branches on `[ -z "$TEST_CMD" ]`, so it becomes a drop-in.

### 4. Mirror-drift gate (regression test)

Delegating to a CLI alone does not stop the fourteenth copy — nothing forces a new loop to
use it. Because there is now a single canonical call, the gate becomes **static** rather
than snippet-extracting-and-executing:

- Scan every `scripts/little_loops/loops/**/*.yaml`; assert none contains an inline
  `.ll/ll-config.json` read for `test_cmd` / `lint_cmd` (i.e. no `get('test_cmd'`-style
  pattern) outside an explicit exemption list.
- Exemption list: `oracles/code-run-gate.yaml` only, with the §1d rationale as a comment.
- Pair it with behavioral tests on `ll-config get` itself (Implementation Step 5), which
  are ordinary Python tests rather than bash-extraction gymnastics.

This is strictly stronger than the originally-proposed execute-each-snippet gate: it also
catches the `ll.local.md` bypass, which an execute-the-snippet check cannot see.

Follow the registry-parametrize pattern from `scripts/tests/test_wiring_skills_and_commands.py:376-424`
(a `GATED_*` constant plus `@pytest.mark.parametrize`) — see the correction in Codebase
Research Findings; commit `fb747a60`'s pattern lives there, not in `test_builtin_loops.py`.

## Integration Map

### Files to Modify

_Revised: no `lib/common.yaml` fragment is added, and `scripts/little_loops/cli/config.py`
needs no change — `ll-config get` already behaves correctly. The change is entirely in the
loop YAMLs plus tests/docs._

- `scripts/little_loops/loops/general-task.yaml:37` — **buggy site** (`check_baseline_tests`)
- `scripts/little_loops/loops/general-task.yaml:617` — `run_final_tests`; also add `SKIP` handling
- `scripts/little_loops/loops/rl-coding-agent.yaml:60,68` — **buggy sites** (`test_cmd` + `lint_cmd`)
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — reference impl; the
  three-way python body is deleted outright
- `scripts/little_loops/loops/evaluation-quality.yaml:58`
- `scripts/little_loops/loops/dead-code-cleanup.yaml:76`
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126`
- `scripts/little_loops/loops/harness-multi-item.yaml:95`
- `scripts/little_loops/loops/harness-single-shot.yaml:66`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:45,152`
- `scripts/little_loops/loops/rn-refine.yaml:991` — verify semantics before converting

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436,679-680` — a **13th
  call site** not enumerated in the original ~12-site table: `test_cmd = project.get('test_cmd')`
  / `lint_cmd = project.get('lint_cmd')` / `if not test_cmd:` in its own post-implementation
  verify pass. Not currently buggy — it already treats a falsy `test_cmd` as "skipped" (comment
  `:375-376`) — but is in scope for the Proposed Solution's "convert all call sites" mandate for
  consistency with the shared fragment. [Agent 1 finding]

### Dependent Files (Callers/Importers)
- ~~`scripts/little_loops/fsm/` — fragment resolution~~ — **no longer touched**; no fragment
  is added, so no executor or `${param.x}` binding concern
- `scripts/little_loops/config/core.py` — `ProjectConfig` field defaults (`:188-195`) become
  the single authority for absent-key defaults; `resolve_variable` (`:1044-1060`) is the
  null→opt-out path. Read-only for this issue, but pinned by Step 1's tests
- Any consuming project's `.ll/ll-config.json` and `.ll/ll.local.md` supplying
  `project.test_cmd` / `project.lint_cmd`

_Wiring pass added by `/ll:wire-issue` — partly superseded by the design review:_
- ~~`scripts/little_loops/cli/loop/info.py` — `cmd_fragments` listing~~ — **not applicable**;
  no new fragment to surface
- ~~ENH-2858 — in-flight sibling plans a `baseline-ref.txt` capture inside
  `check_baseline_tests`; sequencing risk~~ — **stale, resolved.** That
  capture has already landed: `general-task.yaml:39` is
  `git rev-parse HEAD > "${context.run_dir}/baseline-ref.txt" ...`. No sequencing risk
  remains; just preserve that line when rewriting the action. [Agent 2 finding, superseded]

### Similar Patterns
- ~~`lib/common.yaml:15` `shell_exit` / `:38` `retry_counter` — fragment `parameters:`
  convention~~ — **not the model**; see Proposed Solution §1c for why fragments cannot
  express this fix
- `scripts/little_loops/loops/incremental-refactor.yaml:12,33` — uses a plain
  `${context.test_cmd}` with no config read; confirm it is genuinely out of scope

### Tests
- New: mirror-drift gate parametrized over every `scripts/little_loops/loops/**/*.yaml`
  (see Proposed Solution §4)
- `scripts/tests/test_builtin_loops.py` — existing built-in-loop validation; the new gate
  belongs alongside it
- Pattern reference: commit `fb747a60` (`test(adapters): parametrize mirror-drift gate over
  _EMITTER_MAP hosts`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — **assertions will break, but the structural
  problem the wiring pass flagged does not arise.** Because no fragment is introduced, the
  `raw_data` fixture (`:26-31`) and `_load_state_script()` (`:439-443`) keep working as-is —
  no `resolve_fragments`/`load_and_validate` rewrite is needed.
  `TestENH2225FinalOnlyGate.test_run_final_tests_resolves_test_cmd` (`:1430-1435`) asserts
  the literal substrings `${context.test_cmd}` / `ll-config.json` / `pytest`; after
  conversion `${context.test_cmd}` survives (override precedence is preserved) but
  `ll-config.json` and `pytest` do not — retarget at `ll-config get project.test_cmd`.
  Same for `TestRunFinalTestsShellAction` (`:1447-1484`), including
  `test_falls_back_to_config_test_cmd` (`:1477-1484`). [Agent 2 finding, revised]
- `scripts/tests/test_builtin_loops.py::TestGeneralTaskLoop` — `data` fixture (`:14650-14653`)
  has the same raw-YAML bypass backing `test_check_baseline_tests_writes_baseline_exit_to_run_dir`
  (`:14679-14685`), `test_run_final_tests_reads_baseline_exit` (`:14727-14733`), and
  `test_run_final_tests_compares_final_to_baseline` (`:14735-14744`). Lower risk than the
  file above — the `BASELINE_EXIT`/`FINAL_EXIT` substrings likely survive since that
  comparison logic stays inline — but verify after conversion. [Agent 2 finding]
- ~~`scripts/tests/test_fsm_fragments.py`~~ — **drops out entirely.** No fragment is added,
  so `migration_targets` (`:992`) needs no extension and `TestWithRateLimitHandling` /
  `TestWithThrottleFragment` (`:615-781`) are not a pattern to copy. [Agent 1 + Agent 3
  findings, superseded]
- `scripts/tests/test_builtin_loops.py::TestVerifyStateConfigReadShell` (`:4938-5038`) — the
  closest existing shell-execution end-to-end pattern (writes a real `.ll/ll-config.json`,
  extracts the resolved action, runs it via `subprocess.run(["bash", "-c", ...])`). Its
  `test_cmd=None` case covers only the key-**absent** path — Step 1's tests must add the
  key-**present-with-JSON-`null`** case explicitly, since that is the axis this bug is on.
  [Agent 3 finding]
- `scripts/tests/` — locate the existing `ll-config` CLI tests (if any) and extend them
  rather than starting a new module; Step 1's contract tests belong with them.
- `scripts/tests/test_builtin_loops.py::TestCodeRunGateOptionalParams` (`~12270-12520`) —
  already exercises the "key present, value JSON null" scenario for `code-run-gate.yaml`
  (`commands.json` with `"test_cmd": null`); use as the reference for closing this gap
  elsewhere. [Agent 3 finding]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the fragment as the required way to
  resolve a project command inside a loop
- `scripts/little_loops/config-schema.json` — confirm `project.test_cmd` documents `null` as
  the explicit opt-out, not merely "unset"

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — documents `baseline-exit.txt` (`:105`) and
  `project.test_cmd`/`lint_cmd` (`:979`, `:1305`, `:1327`); needs updating for the `SKIP`
  sentinel and the corrected absent/null/value semantics [Agent 1 finding]
- `scripts/little_loops/loops/README.md:33` — describes `auto-refine-and-implement`'s own
  `test_cmd`/`lint_cmd` row [Agent 1 finding]
- `docs/reference/loops.md:829-833` — documents `code-run-gate.yaml`'s distinct `get_value()`
  resolution convention ("null skips run_test/run_build/run_lint"); review wording if that
  file converts to the shared fragment in this pass, since its `null_value` semantics differ
  from emitting a sentinel/no-op command [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:298-310,1846-1850` — `project.test_cmd` config table
  doesn't currently distinguish absent-vs-null; candidate for a clarifying note alongside the
  `config-schema.json` update [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` → `project.test_cmd` — the key whose present-vs-absent-vs-null
  semantics this issue defines

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Newly discovered site — now scoped OUT of conversion by the design review; see Proposed
  Solution §1d. It gets a mirror-drift-gate exemption, not a rewrite.**
  `scripts/little_loops/loops/oracles/code-run-gate.yaml:143-154` implements a *fifth*, distinct resolution convention — a `get_value()` bash function that treats an absent key and an explicit `null` identically (both print nothing, no `pytest` guess), feeding a `resolve_commands` state whose per-command consumers (`run_build`, etc.) self-skip and can emit `GATE_SKIP` (`:108-122`, comment `:114-115`, `:192-193`). This file should be added to the mirror-drift gate's coverage (Proposed Solution §4) and considered for conversion in the same pass, since the gate as specified ("every `scripts/little_loops/loops/**/*.yaml`") already covers it.
- ~~**No existing shared Python helper to delegate to**~~ — **RETRACTED 2026-08-20 by design
  review; this finding was wrong and drove the rejected fragment design.** The research pass
  examined `ProjectConfig` (`scripts/little_loops/config/core.py:184-230`, `test_cmd` field
  `:191`, populated via `data.get("test_cmd", "pytest")` at `:215`) and its consumer
  `verify_epic_branch_before_merge` (`scripts/little_loops/worktree_utils.py:480-609`), but
  never checked for a **CLI wrapper**. `ll-config get` (`scripts/little_loops/cli/config.py`,
  entry point `scripts/pyproject.toml:100`) exposes exactly this resolution to shell and
  implements the required three-way semantics correctly today — verified empirically for both
  `test_cmd` and `lint_cmd`. See Proposed Solution §1. The still-valid part of the original
  finding: `ProjectConfig.test_cmd` is annotated `str` while holding `None` on the opt-out
  path, which is load-bearing and must be pinned by a test (Implementation Step 5).

## Program Design

### Signatures

- `main_config(key: str) -> int` — **existing** CLI entry point (`cli/config.py:54`),
  invoked from shell as `ll-config get project.test_cmd`; the single resolution path
  replacing 13 hand-rolled inline snippets. No new code; prints the value, the
  absent-default, or nothing (opt-out) on stdout, and always returns 0.
- `resolve_variable(var_path: str) -> str` — **existing** (`config/core.py:1044`); returns
  `None` for a present-and-null key, which is the load-bearing opt-out signal.
- `check_baseline_tests(test_cmd: str) -> str` — writes the returned value to
  `baseline-exit.txt`; return type widens from a numeric exit-code string to that plus the
  new no-runnable-baseline sentinel `SKIP`.
- `run_final_tests(baseline_exit: str, final_exit: int) -> bool` — gates on `final_exit`
  alone when `baseline_exit` is `SKIP`, on the ENH-2244 equality comparison otherwise.

No fragment, no `parameters:` block, no executor change. The `config_key` /
`absent_default` / `null_value` parameters from the original design are all subsumed: the
key is the dot-path argument, and the absent-default comes from `ProjectConfig`'s field
defaults (`config/core.py:188-195`), which is where a project-command default *should*
live — one authority instead of a per-call-site literal.

### Call Path

- `check_baseline_tests` → `ll-config get project.test_cmd` — first resolution; writes
  `baseline-exit.txt`. Currently the buggy site at `general-task.yaml:37`.
- `check_baseline_tests` → `define_done` → `plan` → … → `final_verify` → `run_final_tests`
  — the poisoned `baseline-exit.txt` travels this far before anything reads it.
- `run_final_tests` → `ll-config get project.test_cmd` — second resolution of the same key;
  reads `baseline-exit.txt` and must branch on `SKIP` before the numeric comparison.
- `run_final_tests` → `count_final` — the opt-out path; taken directly, running nothing,
  when the key is explicitly null.
- `run_final_tests` → `continue_work` — the gate-failed edge; the entry point of the
  infinite cycle when the baseline is garbage.
- `observe` → `ll-config get project.test_cmd` + `ll-config get project.lint_cmd` (in
  `rl-coding-agent.yaml`) — the second and third buggy sites; the result feeds `TEST_SCORE`
  in the composite reward. Two calls in one state, which the rejected fragment design could
  not express.
- Inside `ll-config get`: `main_config` (`cli/config.py:54`) → `BRConfig(Path.cwd())` →
  `_load_config` (deep-merges `.ll/ll.local.md` frontmatter, `:265-280`) →
  `ProjectConfig.from_dict` (`:208`) → `resolve_variable` (`:1044-1060`) → `print` only
  when non-`None` (`:75-76`).

### Resolution contract

**Resolution order at each call site** (shell, two lines):

1. Non-empty `${context.<key>}` shell-level override → use it verbatim.
2. Otherwise `ll-config get project.<key>`, which internally distinguishes:
   - config file missing, or `project` absent, or key absent → the `ProjectConfig` field
     default (`pytest` / `ruff check .`);
   - key present and `null` → empty output (opt-out);
   - key present and truthy → its value.
3. Empty result → skip; the state must not run or gate on anything.

**Precondition — cwd must be the project root.** `main_config` constructs
`BRConfig(Path.cwd())` (`cli/config.py:71`) and `resolve_config_path` (`config/core.py:157`)
is a flat candidate probe with **no upward walk**. From a subdirectory of a project with
`test_cmd: null`, the opt-out silently degrades to the absent-default — verified:

```
$ cd <proj>/sub/deep && ll-config get project.test_cmd
pytest          # ← opt-out lost, no error, exit 0
```

This is **not a regression** — the 13 inline snippets open the relative path
`.ll/ll-config.json` and fall back identically — but converting does not fix it either, and
it must be stated rather than assumed away. FSM shell actions run at
`FSMExecutor.working_dir` (`fsm/executor.py:2482`), which is the project root for ordinary
runs and the worktree root (which carries its own checked-in `.ll/`) for worktree-isolated
runs, so every converted site is safe today. Note this also means §1d's first exemption
bullet for `oracles/code-run-gate.yaml` (`${context.project_root}` vs `Path.cwd()`) argues a
difference that the other 13 sites never relied on; the alias-pair and never-guess bullets
are the load-bearing reasons for that exemption.

`ll-config get` never raises and always exits 0, so no call site needs `|| true` or a
`try/except`. Note that per BUG-3274's family, resolution is **whole-dataclass**: an
unrelated malformed key in `project` does not silently poison this read, but a future
coercion of `ProjectConfig.test_cmd`'s `None` to satisfy its `str` annotation would.

**Not needed:** the `fix-quality-and-tests.yaml:66-72` three-way python body. It stays the
reference for *what the semantics are*, but it is deleted rather than generalized — the
semantics now live in `ProjectConfig` + `resolve_variable`.

**`general-task.yaml` — baseline sentinel contract**

- `check_baseline_tests` writes `baseline-exit.txt` = `SKIP` when the resolved command is
  the opt-out sentinel, **or** the command exits `127`, **or** `baseline-test-output.txt`
  matches `command not found`. Otherwise it writes the numeric exit code as today.
- `run_final_tests` reads `baseline-exit.txt` and branches **before** its numeric
  comparison: `SKIP` → pass when `[ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "127" ]`,
  never on equality with the baseline. This preserves the ENH-2244 comparison for every run
  that has a real baseline, and prevents a present-but-unrunnable `test_cmd` from
  reproducing the BUG-3269 cycle (see Expected Behavior).
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
- **Mirror-drift gate precedent — correction to the Proposed Solution's citation**: the `fb747a60` pattern actually lives in `scripts/tests/test_wiring_skills_and_commands.py:376-424` (`GATED_HOSTS` list + `@pytest.mark.parametrize("host", GATED_HOSTS)` over `resolve_emitter`'s own registry), not in `test_builtin_loops.py`'s generic `builtin_loops` fixture (`:34-40`). A new mirror-drift gate for `test_cmd`/`lint_cmd` resolution should follow the `test_wiring_skills_and_commands.py` registry-parametrize shape — a `GATED_LOOPS` constant plus one assertion per site that it delegates to ~~`fragment: resolve_test_cmd`~~ **`ll-config get project.<key>`** (corrected: no fragment is added, see §1c) rather than an inline snippet — while `builtin_loops` remains the right fixture if a blanket scan-every-loop-file approach is preferred instead.

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Fragment parameter mechanism, confirmed against current code** (verifies the proposed `resolve_test_cmd(config_key, absent_default, null_value)` fragment is directly implementable with no executor changes): `resolve_fragments` (`scripts/little_loops/fsm/fragments.py:66-153`) is a parse-time expansion only — it does not substitute `${param.x}` text. It captures the fragment's `parameters:` block (`:141`), deep-merges the fragment body into the calling state (`:142`), and renames the state's `with:` block to `fragment_bindings` while stashing declared params as `fragment_parameters` (`:144-148`). The actual `${param.x}` substitution happens at runtime in `FSMExecutor._build_context` (`scripts/little_loops/fsm/executor.py:3283-3325`): it interpolates `fragment_bindings` against the run context (`:3307`), fills declared defaults for unbound optional params (`:3308-3315`), raises `ValueError` on an unbound required param (`:3317-3322`), and assigns the result to `ctx.param` (`:3323`). Static validation of `with:` bindings against the fragment's declared contract runs separately in `_validate_fragment_bindings` (`scripts/little_loops/fsm/validation/structural_rules.py:334-403`), invoked from `load_and_validate` (`:1755`).
- **`rn-refine.yaml:988-994` conversion caveat**: this site's `try/except` degrades to an empty string `''` on any resolution failure (missing config, present-null, or exception alike), and the consuming state branches only on `[ -z "$TEST_CMD" ]` (`:995-997`) — it is gated as advisory only (`on_yes`/`on_no` are not set; failure only appends a `RECOVERY_NEEDED` note to `plan-rubric.md`, `:998-1002`). No other state or test reads this state's output. Converting it to the shared fragment's `SKIP`/`true` sentinel values is low-risk but not a drop-in: the site's `-z "$TEST_CMD"` skip check must be preserved rather than assumed to already match a `SKIP`/`true` shape, since `SKIP` and `true` are both non-empty strings.

## Implementation Steps

1. **Pin the contract first — no production code yet.** Add tests for `ll-config get`
   covering, for **both** `project.test_cmd` and `project.lint_cmd`: key present-and-null →
   empty stdout; key absent → the `ProjectConfig` default; key present with a value → that
   value; config file entirely absent → the default; and a `.ll/ll.local.md` frontmatter
   value overriding `.ll/ll-config.json`. These pass today — they exist to stop a future
   BUG-3274-style type cleanup from silently deleting the opt-out. Model the shell-execution
   half on `TestVerifyStateConfigReadShell` (`test_builtin_loops.py:4938-5038`), which
   currently covers only the key-**absent** path.
   Also add the negative case: `test_cmd: null` in `ll.local.md` resolves to the
   absent-default, **not** opt-out (documented asymmetry, see Expected Behavior).
2. **Decide the `rl-coding-agent` precedence question** (§2, options (a)/(b)) before writing
   any shell there. This is the one genuine design choice in the issue; everything else is
   mechanical.
3. **Fix the three blockers.** Convert `general-task.yaml:37` and
   `rl-coding-agent.yaml:60,68` to `ll-config get` — the sites that emit literal `None`
   today. Use the **per-site** precedence from §2's table: context-first for
   `general-task`, config-first for `rl-coding-agent`. Do not paste one shape into both.
   In the same edit, give `check_baseline_tests` the `${context.test_cmd}` override it
   lacks today, so its resolution shell is byte-identical to `run_final_tests`'s; preserve
   the existing `baseline-ref.txt` capture at `:39`.
4. **Add the baseline sentinel.** Implement the `SKIP` contract in `check_baseline_tests` +
   `run_final_tests`, with the opt-out detected as `[ -z "$CMD" ]`. The `SKIP` branch in
   `run_final_tests` passes on `FINAL_EXIT` in `{0, 127}` — the `127` arm is required to
   close the present-but-unrunnable `test_cmd` spin (see Expected Behavior), not optional
   defensiveness. Add a regression test for that case specifically: `test_cmd` set to a
   command that does not exist, asserting `run_final_tests` reaches `count_final`.
5. **Convert the remaining sites.** The nine correct-but-guessing copies plus
   `auto-refine-and-implement.yaml`, one file at a time, running `ll-loop validate` after
   each. `fix-quality-and-tests.yaml:58-78`'s three-way python body is **deleted**, not
   generalized. Skip `oracles/code-run-gate.yaml` (§1d).
6. **Land the mirror-drift gate.** Static scan over every loop YAML asserting no inline
   `.ll/ll-config.json` read for `test_cmd` / `lint_cmd`, with `oracles/code-run-gate.yaml`
   as the sole documented exemption. Confirm it fails before step 3 and passes after step 5.
7. **Verify.** `python -m pytest scripts/tests/` exits 0; `ll-loop validate` clean on every
   converted loop; manual smoke of `general-task` in a scratch project with
   `test_cmd: null` reaching a terminal state instead of cycling, plus a second smoke with
   `test_cmd` set to a nonexistent command (the 127 path from step 4).

**Rollback seam:** steps 3–5 are independent per-file edits behind a contract pinned in
step 1. If a conversion misbehaves in a consuming project, revert that one file — there is
no shared artifact to unwind, which is a further advantage over the fragment design.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Convert `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436,679-680` — the
  13th call site, not in the original ~12-site table; not currently buggy but in scope for
  the "convert all call sites" mandate
- Update `scripts/tests/test_general_task_loop.py` — retarget the `test_cmd` substring
  assertions in `TestENH2225FinalOnlyGate` and `TestRunFinalTestsShellAction` at
  `ll-config get project.test_cmd` (no load-path rewrite needed)
- Update `scripts/tests/test_builtin_loops.py::TestGeneralTaskLoop` — verify the raw-YAML
  fixture's baseline/final-test substring assertions still hold after conversion
- ~~Extend `test_fsm_fragments.py`'s `migration_targets`~~ — not applicable, no fragment
- Add `ll-config get` contract tests per Implementation Step 1, covering
  key-present-with-JSON-`null` for both `test_cmd` and `lint_cmd` (not just key-absent),
  the `ll.local.md` override, and the `ll.local.md`-null asymmetry
- Update `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md`, and
  `docs/reference/CONFIGURATION.md` to reflect the corrected absent/null/value semantics and
  the `SKIP` sentinel. `docs/reference/loops.md:829-833` (`code-run-gate.yaml`) needs **no
  change** — that loop is out of scope (§1d)
- Document in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` that `ll-config get` is the
  required way to read a project command inside a loop, and that inline
  `.ll/ll-config.json` parsing is prohibited (it bypasses `ll.local.md`). Include both
  precedence shapes from §2's table and the cwd precondition — no other loop uses this
  call today, so the guide is the only precedent a future author will find
- Add the `${context.test_cmd}` override to `general-task.yaml`'s `check_baseline_tests`
  (it has none today) so baseline and final gate resolve identically
- Add a `run_final_tests` test for `baseline-exit.txt = SKIP` with `FINAL_EXIT = 127`
  routing to `count_final`, not `continue_work`

## Impact

- **Severity**: P0. Silently burns a full iteration budget and the user's tokens on
  already-completed work; requires manual SIGKILL to stop. Corrupts RL reward signal in a
  second loop.
- **Blast radius**: `general-task` is the most-used built-in loop and is live in every
  local-editable consuming project.
- **Risk of the fix**: low. No new production code — `ll-config get` already exists and
  behaves correctly. The risk is entirely in converting 13 call sites across 11 loop files,
  each mechanically checkable by the new gate and independently revertible.
- **Backward compatibility**: projects with a non-null `test_cmd` see no behavior change.
  Projects with `test_cmd: null` change from "guess pytest" to "no test gate" — that is
  the intended fix, and matches what `fix-quality-and-tests.yaml` already does. Two smaller
  intended changes: (a) `.ll/ll.local.md` overrides of `test_cmd`/`lint_cmd` now take effect
  inside loops (they never did); (b) `rl-coding-agent.yaml` with the key **absent** resolves
  to `pytest` / `ruff check .` instead of the context literal, and its `:17-18` context
  defaults become dead under §2 option (a). Two further intended changes: (c) a
  present-but-unrunnable `test_cmd` (exit 127) no longer gates `general-task`'s
  `run_final_tests`; (d) `general-task`'s `check_baseline_tests` starts honoring
  `${context.test_cmd}`, which it silently ignored before.
- **Not fixed by this issue**: `ll-config get` resolves from `Path.cwd()` with no upward
  walk, so a loop state invoked from a subdirectory still loses the opt-out. Safe for all
  13 converted sites today (FSM shell actions run at the project or worktree root) and no
  worse than the snippets being replaced — see the precondition in the Resolution contract.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` — full forensic audit
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop design rules
- ENH-2244 — the baseline-comparison gate whose null-config failure mode this is
- ENH-2225 — final-only whole-suite gate (`run_final_tests`)

## Status

**Open** | Created: 2026-08-20 | Priority: P0


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-20_

**Readiness Score**: 88/100 → PROCEED (blocked by hard override — see below)
**Outcome Confidence**: 77/100 → Good

### Gaps to Address
- ~~**Program Design gate (hard override)**~~ — **RESOLVED 2026-08-20 by design review.**
  The `### Signatures` bullets were rewritten as strict `name(params: Type) -> Type` lines
  with bare-token types; `ll-issues check-design BUG-3269` now exits 0 and
  `format-check --format json` reports an empty `program_design_nonspecific`. The
  remaining `stale_file_ref` entries (`.ll/ll.local.md`, `postmortems/...`) are expected —
  both paths are gitignored. Original text retained below for context:
- **Program Design gate (hard override, `ll-issues check-design` exits 1)**: none of the
  three `### Signatures` bullets are regex-matchable as signature-shaped by
  `scripts/little_loops/issues/program_design.py` (`_SIG_CALL`/`_SIG_FIELD`), even though a
  human reader can see they are precise. Two distinct causes: (1) `` `ll-config get
  project.<key> -> str` `` has no `(...)` call syntax, so `_SIG_CALL` never matches it; (2)
  `` `check_baseline_tests() -> writes baseline-exit.txt: int | "SKIP"` `` and `` `run_final_tests(baseline_exit: int | "SKIP") -> bool` ``
  both have return/param type text (`writes baseline-exit.txt: int | "SKIP"`,
  `int | "SKIP"` with an embedded quoted string literal) that doesn't fit `_TYPE`'s
  `[\w.]+` token grammar. Remedy: rephrase as strict `name(params: Type) -> Type` lines with
  a bare token type — e.g. replace the `"SKIP"` string-literal type with a plain identifier
  like `SkipSentinel` or `str` in the signature, and give the `ll-config get` line a
  call-shaped form such as `` `get(key: str) -> str | None` `` — then move the CLI-invocation
  prose after the em-dash description. Verify with `ll-issues format-check BUG-3269 --format
  json` and confirm `program_design_nonspecific` is empty, then `ll-issues check-design
  BUG-3269` exits 0, before implementation.

### Outcome Risk Factors
- Broad enumeration across ~13 call sites in 11 loop files — each conversion is mechanical
  and independently revertible (per the issue's own rollback seam), but the sheer count
  raises the odds that one site's precedence shell (`${context.*}` override before
  `ll-config get`) gets pasted wrong. The mirror-drift gate (Implementation Step 5) is the
  intended catch for this, but it lands *after* all conversions in Step 4 rather than
  per-file — consider running `ll-loop validate` (already planned) plus a scoped `grep` for
  the old `.get('test_cmd'` pattern after each file, not just at the end.

## Session Log
- `/ll:confidence-check` - 2026-08-21T00:48:05 - `e0ced191-faba-4adf-9e21-fe9bb9babc29.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:22:27 - `8fa51734-384b-46a2-a10c-bd13c601a684.jsonl`
- `/ll:confidence-check` - 2026-08-20T23:39:55 - `bae4c657-9e53-457d-bcc4-db4ed042c8fb.jsonl`
- `/ll:wire-issue` - 2026-08-20T23:37:01 - `f8d1ceb8-b964-4281-915c-bc7d008244e2.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:29:35 - `8838a661-0444-4cad-a5d2-117e364de078.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
