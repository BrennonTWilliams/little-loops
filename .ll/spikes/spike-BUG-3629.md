# Spike Plan: BUG-3629 — run/state-scoped action_stall state

## Context

No `### Outcome Risk Factors` exist; standalone analysis of `## Proposed Solution` chose the riskiest
mechanism: keying stall snapshot/count files as `<run_dir>/<state_name>-<md5(sorted track)[:12]>` with a
cwd `.loops/tmp` fallback. (a) No precedent: `score_stall`/`open_question_stall` only read a loop-written
history file; `action_stall` writes its own state, so scoping must live in the path/key. (b) No existing test
uses two run_dirs, two states, or parent/child sharing one `run_dir` (sub-loops inherit the parent's `run_dir`,
so state name must be in the key).

## Approach

An isolated pure library replicating the snapshot/count state machine of `evaluate_action_stall` with an
injectable `state_dir` + `state_name`. Real files in `tmp_path`; nothing faked except the hash input.

## Critical files

- `scripts/little_loops/fsm/evaluators.py` — `evaluate_action_stall` (contract to honor; not modified)
- `scripts/tests/spike/action_stall_run_scope/run_scoped_stall.py` (new)
- `scripts/tests/spike/action_stall_run_scope/test_run_scoped_stall.py` (new)

## Implementation

```
scripts/tests/spike/action_stall_run_scope/
├── __init__.py
├── run_scoped_stall.py      # stall_paths(), check_stall()
├── conftest.py              # exception-recording hook
└── test_run_scoped_stall.py
```

- `stall_paths(state_dir: Path | None, state_name: str, track: list[str], cwd: Path) -> tuple[Path, Path]`
- `check_stall(current_hash, *, state_dir, state_name, track, max_repeat, cwd) -> tuple[str, int]`

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_sequential_runs_do_not_share_state` | fresh run's first check is `yes`, count 0 | behavior |
| `test_same_track_states_in_one_run_isolated` | two states, same track, one run | behavior |
| `test_parent_child_sharing_run_dir_isolated` | sub-loop inherits run_dir; state name separates | behavior |
| `test_missing_run_dir_falls_back_to_cwd_loops_tmp` | fallback without raising | behavior |
| `test_stall_semantics_preserved` | yes/yes/no at max_repeat matches existing evaluator | behavior |
| `test_guard_no_cwd_writes_when_state_dir_set` | scoping actually leaves cwd untouched | regression |
| `test_guard_spike_does_not_import_production_evaluators` | isolation | regression |

## Verification

- `spike`: `python -m pytest scripts/tests/spike/action_stall_run_scope/ -v`
- `regression`: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`

## Out of Scope

Modifying `evaluators.py`, `diff_stall`, docs, or the `evaluate()` dispatch wiring.

## Promotion

Fold `stall_paths`/`check_stall` logic into `evaluate_action_stall` (`state_dir`/`state_name` params) and its
tests into `scripts/tests/test_fsm_evaluators.py`, in a separate PR.
