---
id: ENH-2500
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: '2026-07-06T20:21:41Z'
discovered_by: capture-issue
relates_to:
- BUG-1960
decision_needed: false
labels:
- loops
- prompt-across-issues
- cross-run-isolation
- run-dir
- captured
confidence_score: 98
outcome_confidence: 84
score_complexity: 17
score_test_coverage: 21
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2500: prompt-across-issues: per-run-dir pending file + scope declaration

## Summary

`scripts/little_loops/loops/prompt-across-issues.yaml` writes its pending-issue queue to a fixed shared path (`.loops/tmp/prompt-across-issues-pending.txt`), which makes two concurrent instances race on the same file. Add a `scope:` declaration so the LockManager gives each instance its own scope automatically, and migrate the queue file to `${context.run_dir}/pending.txt` so concurrent runs are isolated without requiring `--no-lock`.

## Current Behavior

The loop's `init` state writes to a hardcoded path:

```yaml
# scripts/little_loops/loops/prompt-across-issues.yaml:64
ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "..." \
  > .loops/tmp/prompt-across-issues-pending.txt
```

`discover` reads from the same path; `advance` does a `tail -n +2 … && mv` mutation against the same path. The YAML acknowledges this at line 36:

```yaml
shared_state_ok: true  # pending-list file intentionally uses a fixed path; not designed for concurrent runs
```

The loop declares **no `scope:`**, so `resolve_scope()` defaults to `["."]` (whole project). Two instances on different parent EPICs SHOULD conflict at `_helpers.py:1288`, but the user can bypass the check with `--no-lock`. When they do (or when a second instance starts before the first acquires its scope lock — race window), both instances read and mutate the same `pending.txt`. A documented collision occurred on 2026-07-06 between the EPIC-2457 sweep (`prompt-across-issues-20260706T140004`) and the EPIC-2451 `--no-lock` sweep (`prompt-across-issues-20260706T140754`):

- Run 1's `init` wrote the 16 EPIC-2457 children to `pending.txt`.
- Run 2's `init` **overwrote** `pending.txt` with the 4 EPIC-2451 children (`FEAT-2447…2450`).
- Run 1's `discover` (after a 14m `execute`) read Run 2's queue head — `FEAT-2448` — and refined an issue from a foreign EPIC.
- Run 1's `advance` removed `FEAT-2448` from the file before Run 2 reached it; Run 2 silently skipped `FEAT-2448` (its file mtime predates both runs).

Concrete data integrity outcome: Run 1 (EPIC-2457) refined 1 of its own children + 1 foreign; Run 2 (EPIC-2451) refined 3 of 4 children and silently lost one.

## Expected Behavior

Two `prompt-across-issues` instances started on different `--context parent=` filters should run concurrently without colliding — no `--no-lock` workaround required, no queue corruption, no cross-scope issue refinement, no silent skips.

After the change:

1. **Per-run queue path**: each instance's pending list lives under its own `${context.run_dir}/pending.txt`. The runner already creates `run_dir` before execution (`run.py:405`), so no extra `mkdir -p` is needed.
2. **LockManager gives each instance its own scope**: declaring `scope: ["${context.run_dir}"]` makes the conflict check at `_helpers.py:1288` always pass for distinct instances (different `run_dir`s), and the check is still meaningful for the (unusual) case where two concurrent runs were started against the same `run_dir`.
3. **`shared_state_ok: true` exemption is removed** from the loop YAML — it's no longer accurate once the path is per-instance.

## Motivation

- **Data integrity**: The 2026-07-06 collision refined an issue under the wrong EPIC and silently skipped another. Both are silent data-loss outcomes — the loop reports `done` without warning.
- **Forces the user to know an internal**: `--no-lock` exists today as the only way to run two sweeps concurrently, but it removes the only signal that would otherwise prevent this collision. Knowledge of the loop's shared-file quirk is load-bearing for safe parallel use.
- **Pattern match**: BUG-1960 (closed 2026-06-05) fixed the identical class of bug for `general-task.yaml` and explicitly listed `prompt-across-issues.yaml` as one of 19 remaining built-in loops still using `.loops/tmp/` paths (in `## Codebase Research Findings → Widespread .loops/tmp/ Usage`). The fix is a direct application of that precedent.
- **Template hazard**: `prompt-across-issues` is a frequently-copied loop template. Its current `shared_state_ok: true` comment normalizes a pattern that causes silent data corruption when applied to user-authored loops.

## Proposed Solution

### Fix 1: Migrate queue path to `${context.run_dir}` (structural)

Capture the per-instance path once and reference it everywhere. Pattern mirrors `autodev.yaml` and `rn-refine.yaml` (`scripts/little_loops/loops/`):

```yaml
# scripts/little_loops/loops/prompt-across-issues.yaml
context:
  type: ""        # existing — Optional: BUG/FEAT/ENH/EPIC
  parent: ""      # existing — Optional: EPIC-NNN
  pending_file: "${context.run_dir}/pending.txt"   # NEW — per-instance

states:
  init:
    action: |
      if [ -z "${context.input}" ]; then
        echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
        exit 1
      fi
      TYPE_ARG=""
      if [ -n "${context.type}" ]; then
        TYPE_ARG="--type ${context.type}"
      fi
      PARENT_ARG=""
      if [ -n "${context.parent}" ]; then
        PARENT_ARG="--parent ${context.parent}"
      fi
      ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "
      import json, sys
      issues = json.load(sys.stdin)
      for i in issues:
          print(i['id'])
      " > "${context.pending_file}"
      COUNT=$(wc -l < "${context.pending_file}" | tr -d ' ')
      echo "Found $${COUNT} issues to process"
    fragment: shell_exit
    on_yes: discover
    on_error: diagnose_error

  discover:
    action: |
      if [ ! -s "${context.pending_file}" ]; then
        exit 1
      fi
      head -1 "${context.pending_file}"
    fragment: shell_exit
    capture: current_item
    on_yes: prepare_prompt
    on_no: done
    on_error: done

  advance:
    action: |
      DIR="$(dirname "${context.pending_file}")"
      tail -n +2 "${context.pending_file}" > "${DIR}/pending.tmp"
      mv "${DIR}/pending.tmp" "${context.pending_file}"
      REMAINING=$(wc -l < "${context.pending_file}" | tr -d ' ')
      echo "Completed ${captured.current_item.output}"
      echo "Progress: $REMAINING items remaining"
    action_type: shell
    next: discover
```

### Fix 2: Declare `scope:` so LockManager handles concurrent instances

Pattern precedent: `scripts/little_loops/loops/autodev.yaml` (line `scope: ["${context.run_dir}"]`) and `scripts/little_loops/loops/rn-refine.yaml` (line `scope: ["${context.plan_file}"]`). Each instance's `run_dir` is timestamped, so the resolved scopes are disjoint by construction:

```yaml
scope:
  - "${context.run_dir}"
```

Optional widening (only if same-parent concurrent runs also need locking): add a parent-scoped path:

```yaml
scope:
  - "${context.run_dir}"
  - "${context.parent}"   # catches two runs on the same EPIC across different run_dirs
```

…but `_scopes_overlap` would need to handle a bare EPIC ID like `EPIC-2457`. Recommend starting with the `run_dir`-only form (simpler, sufficient for the documented use case) and revisiting if same-parent cross-instance locking becomes a requirement.

### Fix 3: Remove the `shared_state_ok: true` exemption

The comment at line 36 documents an accurate constraint at the time it was written but becomes a footgun once the path is per-instance. Delete the line:

```yaml
# REMOVE:
shared_state_ok: true  # pending-list file intentionally uses a fixed path; not designed for concurrent runs
```

After Fix 1, every instance owns its own `pending.txt`, so MR-3 (`.loops/tmp/` usage warning) will pass naturally.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ **Critical correction: the proposed `context.pending_file` indirection will not work.**
>
> The proposed `context: pending_file: "${context.run_dir}/pending.txt"` block followed by `${context.pending_file}` references in shell actions is broken. `fsm.context` values are literal strings loaded from YAML — they are **not** template-expanded at YAML load time. The template engine (`scripts/little_loops/fsm/interpolation.py` / `scripts/little_loops/fsm/concurrency.py:resolve_scope`) interpolates `${context.<var>}` references **at state-action execution time**, not at YAML load. So `${context.pending_file}` would resolve to the literal string `"${context.run_dir}/pending.txt"` and the shell would attempt to write a file with that exact name (containing the `$`, `{`, etc.), not to the resolved path.
>
> **Fix (recommended, matches BUG-1960 / autodev precedent):** Drop the `context.pending_file` block entirely. Reference `${context.run_dir}/pending.txt` directly in each shell action — same pattern as `general-task.yaml` (e.g., `resume_check` at `scripts/little_loops/loops/general-task.yaml:103-150` uses `CHECKPOINT="${context.run_dir}/checkpoint.json"` inline) and `autodev.yaml`. The fix collapses to **2 changes** to the YAML (add `scope:`, remove `shared_state_ok`) plus path replacements; the `context.pending_file` step should be skipped.
>
> **Alternative (rn-implement precedent):** Keep `pending_file: ""` in `context:` and use `capture: pending_file` in `init` so the resolved path gets stored in `${captured.pending_file.output}` for downstream states. This adds capture machinery that `prompt-across-issues` doesn't need (it has only 3 references, all in `init`/`discover`/`advance` which all execute in the same instance lifetime). Recommend the direct-reference path.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — add `context.pending_file`, add `scope:`, replace 4 hardcoded `.loops/tmp/prompt-across-issues-pending.txt` path occurrences (`init`, `discover`, `advance` shell actions plus the `diagnose_error` prompt text), remove `shared_state_ok: true`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Path occurrence count is undercounted.** The "4 occurrences" claim refers to 4 STATES (init, discover, advance, diagnose_error). The actual literal `.loops/tmp/prompt-across-issues-pending.txt` strings in the YAML are 8: lines 64 (`init` write), 65 (`init` read), 75 (`discover` test), 78 (`discover` read), 117 (`advance` write to `.tmp`), 118 (`advance` mv), 119 (`advance` read), 134 (`diagnose_error` prompt text). Plus line 50 `mkdir -p .loops/tmp` (now redundant — see Implementation Steps § Codebase Research Findings). Implementer should grep for `.loops/tmp/prompt-across-issues-pending.txt` to enumerate all replacements, not count by state.
- **`run.py:405` line reference is wrong.** Line 405 is `_git_lock = GitLock(logger)` (worktree setup). The actual `run_dir` injection is at `scripts/little_loops/cli/loop/run.py:175-178` and the `mkdir(parents=True, exist_ok=True)` is at `scripts/little_loops/cli/loop/run.py:483`.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py` — validates all built-in loops parse; no change expected, but a re-run is part of the verification gate
- `scripts/little_loops/loops/lib/common.yaml` — imported by `prompt-across-issues`; check for any shared-path assumptions
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.acquire` / `find_conflict` / `_scopes_overlap` — read-only consumers of the new `scope:` declaration; no changes expected, but verify `${context.run_dir}` resolves to an absolute path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — runtime consumer at line 322 (`scope = resolve_scope(fsm.scope or ["."], fsm.context)`); `run_dir` injection at lines 175-178 (`fsm.context["run_dir"] = str(loops_dir / "runs" / (_pre_instance_id or loop_name)) + "/"`); `Path(fsm.context["run_dir"]).mkdir(parents=True, exist_ok=True)` at line 483 confirms `${context.run_dir}` is created before any state executes (no defensive `mkdir -p` inside the loop once `.loops/tmp` is dropped). Read-only; no edit needed.
- `scripts/little_loops/cli/loop/_helpers.py` — pre-flight scope-conflict check at lines 1282-1291 (`scope = resolve_scope(fsm.scope or ["."], scope_context)` + `lock_manager.find_conflict(scope)`); the new `scope: ["${context.run_dir}"]` declaration will make this check pass cleanly for disjoint instances (the documented EPIC-2457 vs EPIC-2451 collision scenario). Read-only; no edit needed.
- `scripts/little_loops/cli/loop/info.py` — `ll-loop show` display output at lines 1159-1160 (`if fsm.scope: config_parts.append(f"scope: {', '.join(fsm.scope)}")`); the new `scope: ["${context.run_dir}"]` will surface in `ll-loop show prompt-across-issues` post-fix. Read-only; no edit needed.
- `scripts/little_loops/cli/loop/testing.py` — `run_dir` injection for `ll-loop test` simulation at lines 213-216; the new `${context.run_dir}/pending.txt` reference must resolve under the injected `run_dir`. Read-only; no edit needed.
- `scripts/little_loops/cli/loop/lifecycle.py` — `run_dir` re-injection on resume at lines 501-504; ensures `${context.run_dir}` is stable across `--resume` invocations. Read-only; verify post-fix.
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.scope: list[str] = field(default_factory=list)` at line 1038; `shared_state_ok: bool = False` default at lines 1068-1070; round-trip via `to_dict` (1097-1098) and `from_dict` (1235). The schema already supports the new YAML keys with no validator changes. Read-only.
- `scripts/little_loops/fsm/validation.py` — `_SHARED_TMP_PATH_RE` at line 107; `_find_shared_tmp_writes` at lines 1377-1390; `_validate_artifact_isolation` at lines 1418-1448 (early-returns `[]` at line 1430 when `fsm.shared_state_ok` is `True`); `KNOWN_TOP_LEVEL_KEYS` at lines 174-219 includes `"scope"` at line 182. **After `shared_state_ok: true` is removed**, the MR-3 gate (lines 1377-1448) will START firing for `prompt-across-issues` — making any residual `.loops/tmp/` reference a WARNING (this is the regression net ENH-2500 § Codebase Research Findings explicitly relies on). Read-only; verify post-fix that `_validate_artifact_isolation(prompt-across-issues FSM)` returns `[]`.

### Similar Patterns (Precedent for the Fix)
- `scripts/little_loops/loops/autodev.yaml:scope:` — declares `["${context.run_dir}"]`; all per-run artifacts (`queue.txt`, `passed.txt`, `skipped.txt`) live under `run_dir`. Model the migration after this.
- `scripts/little_loops/loops/rn-refine.yaml:scope:` — declares `["${context.plan_file}"]` for a non-run-dir scope; shows the variable-substitution pattern works in `scope:`.
- `scripts/little_loops/loops/rn-implement.yaml` — captures `RUN_DIR="${context.run_dir}"` as a local shell variable, writes `checkpoint.json` at the captured path; shows the per-state capture-and-use pattern.
- **BUG-1960 (closed)** — same root cause for `general-task.yaml`; the `## Codebase Research Findings → Widespread .loops/tmp/ Usage` section explicitly enumerated `prompt-across-issues.yaml` as a remaining instance.

### Tests
- `scripts/tests/test_builtin_loops.py::test_prompt_across_issues_yaml_parses` — existing parse check (no change; verify after edit)
- `scripts/tests/test_prompt_across_issues_loop.py` (new) — concurrent-collision regression test:
  - Start two `prompt-across-issues` instances with different `--context parent=` filters via `subprocess` against `scripts/little_loops/cli/loop/__init__.py run …`
  - Assert neither `run_dir`/pending.txt has been clobbered by the other (read each `pending.txt` after one cycle, compare against expected ordering)
  - Assert no LockManager conflict was raised (i.e., the `scope: ["${context.run_dir}"]` resolves disjoint)
- `scripts/tests/test_lock_manager.py` — add a unit test that `resolve_scope(["${context.run_dir}"], {"run_dir": "/tmp/run-A"})` and `resolve_scope(["${context.run_dir}"], {"run_dir": "/tmp/run-B"})` produce disjoint scopes and don't conflict in `find_conflict`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/tests/test_lock_manager.py` does not exist.** The scope / LockManager tests live in `scripts/tests/test_concurrency.py` (`TestScopeLock` line 18+, `TestLockManager` line 60+, `TestLockManagerRaceConditions` line 333+, `TestResolveScope` line 654+). Use `test_concurrency.py` for the disjoint-scope and `resolve_scope` unit tests; the issue's `test_lock_manager.py` references should be retargeted there.
- **Existing structural test class for prompt-across-issues** lives at `scripts/tests/test_builtin_loops.py::TestPromptAcrossIssuesLoop` (lines 1576-1689) with 17 tests covering required fields, captures, paths, retries, and routing. The MR-3 regression test should be added to this class (mirroring `scripts/tests/test_rn_implement.py:503-511` `test_mr3_no_loops_tmp_writes` + `test_shared_state_ok_is_false` precedent), not as a standalone test. Suggested additions:
  - `test_no_loops_tmp_writes` — iterate `data["states"][*].action` and assert `.loops/tmp/` not in each string (matches `test_rn_implement.py:503-511`)
  - `test_shared_state_ok_is_false` — assert `data["shared_state_ok"] is False` (matches `test_rn_implement.py:577`)
  - `test_scope_declared` — assert `data["scope"] == ["${context.run_dir}"]`
- **Existing BUG-1960 test pattern** to mirror for the new `test_prompt_across_issues_loop.py`: `scripts/tests/test_general_task_loop.py:1305-1401` (`TestResumeCheckBUG1960`, `TestSelectStepBUG1960`, `TestCheckDoneErrorRoutingBUG1960`) — uses `_load_state_script(state_name)`, `_setup_run_dir(tmp_path)`, `_bash(script, cwd=tmp_path)` helpers that substitute `${context.run_dir}` / `${context.input_hash}` placeholders and run the actual shell action via subprocess. Same harness fits `prompt-across-issues`'s `init`/`discover`/`advance` cycle.
- **Concurrent-acquire test pattern** to mirror: `scripts/tests/test_concurrency.py::TestLockManagerRaceConditions::test_concurrent_acquire_same_scope_only_one_wins` (line 333+) — uses `threading.Barrier(2)` to launch two threads that both call `LockManager.acquire(...)` against the same scope. For ENH-2500's disjoint-scope counterpart, launch two threads with distinct `run_dir` values and assert BOTH succeed (no conflict).

_Wiring pass added by `/ll:wire-issue`:_
- **Mirror in `scripts/tests/test_builtin_loops.py::TestPromptAcrossIssuesLoop` (lines 1576-1689)** — add to the existing 17-test class (NOT a new file). Mirror patterns from:
  - `scripts/tests/test_rn_implement.py:503-511` (`test_mr3_no_loops_tmp_writes`) — iterate `data["states"][*].action` and assert `.loops/tmp/` not in each string
  - `scripts/tests/test_rn_implement.py:577-580` (`test_shared_state_ok_is_false`) — assert `data["shared_state_ok"] is False`
  - `scripts/tests/test_builtin_loops.py:3288-3298` (`TestAutodevLoop.test_scope_field_uses_run_dir_template`) — assert `data["scope"] == ["${context.run_dir}"]`
  - `scripts/tests/test_fsm_validation.py:1321-1330` (`test_mr3_runs_via_validate_fsm`) — call `validate_fsm(load_and_validate(LOOP_FILE))` and assert zero MR-3 WARNINGs post-fix (regression net for any residual `.loops/tmp/` references in the rewritten YAML)
- **Mirror in `scripts/tests/test_concurrency.py::TestResolveScope` (lines 653-719)** — append `test_run_dir_template_resolves` mirroring line 662 `test_with_context_var` (`resolve_scope(["${context.run_dir}"], {"run_dir": ".loops/runs/inst-123/"}) == [".loops/runs/inst-123/"]`).
- **Mirror in `scripts/tests/test_concurrency.py::TestLockManagerRaceConditions` (lines 333-650)** — append disjoint-scope counterparts:
  - `test_prompt_across_issues_with_run_dir_scopes_both_acquire_concurrently` — mirror `test_autodev_with_run_dir_scopes_both_acquire_concurrently` at line 582; two `LockManager.acquire("prompt-across-issues", [...])` calls with distinct run_dir strings both succeed
  - `test_prompt_across_issues_with_dot_scope_still_conflicts` — mirror `test_autodev_with_dot_scope_still_conflicts` at line 619; regression guard for default scope
- **New file `scripts/tests/test_prompt_across_issues_loop.py`** — concurrent-collision regression test mirroring `scripts/tests/test_general_task_loop.py:1305-1401` BUG-1960 pattern (`_load_state_script` + `_setup_run_dir` + `_bash` helpers at lines 415-431, 774-775):
  - `TestInitWritesToRunDir` — load `init` state, substitute `${context.run_dir}`, run via `_bash`, assert `pending.txt` exists under `run_dir` (not `.loops/tmp/`)
  - `TestDiscoverReadsRunDirPending` — load `discover` state, assert it reads head of `pending.txt` under `run_dir`
  - `TestAdvanceAdvancesRunDirQueue` — load `advance` state, assert it removes head and preserves rest
  - `TestDiagnoseErrorMentionsRunDir` — load `diagnose_error` state, assert the LLM prompt body no longer contains `.loops/tmp/prompt-across-issues-pending.txt`
- **No end-to-end smoke test exists** for prompt-across-issues; Agent 3 confirmed zero matches for `ll-loop run prompt-across-issues` in `scripts/tests/`. The new `test_prompt_across_issues_loop.py` shell-action harness is the entire integration surface today.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — search for any references to `prompt-across-issues-pending.txt` or `.loops/tmp/` usage patterns in loop examples; update if found
- `scripts/little_loops/loops/README.md` — built-in loop catalog; verify the description for `prompt-across-issues` doesn't claim shared-state semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:724` — built-in loop catalog row for `prompt-across-issues` under the **"Issue Management"** section. Currently no shared-state claim, so no edit required; but if post-fix the description is updated to advertise the new per-instance scope semantics, this row should reflect that.
- `docs/development/TROUBLESHOOTING.md:309` — usage example `ll-loop run prompt-across-issues "/ll:format-issue {issue_id} --auto"` in the **"Skills stall on AskUserQuestion when run via a loop"** section. No path reference; no update required.
- `thoughts/audits/loop-artifact-isolation-audit.md:62, 112` — pre-existing audit lists `prompt-across-issues` as needing migration (line 62 calls it "Per-run is correct" but the path wasn't per-run; line 112 lists it under "Medium" migration candidates). After ENH-2500, the audit is stale in a "still says it needs migration" sense. **Optional follow-up** — mark `prompt-across-issues` as resolved in this audit.
- `.ll/decisions.yaml:4010-4023` — `ARCHITECTURE-106` rule already prescribes the exact post-fix pattern: *"Migrate prompt-across-issues pending.txt from fixed .loops/tmp/ to per-run-dir ${context.run_dir}/pending.txt + declare scope: ["${context.run_dir}"] so concurrent instances are isolated by LockManager."* After implementation, this rule becomes "enforced by code" rather than "advisory". Verify it survives `sync_to_local_md` cleanly.
- `CHANGELOG.md:1003, 1782` — historical entries from BUG-1606 and the loop's original FEAT-934 respectively. Immutable; the new ENH-2500 fix will get a fresh entry at release time.

### Configuration
- N/A — no config-file changes; `loops.run_defaults.clear: true` in `.ll/ll-config.json` already cleans `.loops/runs/`, so per-run pending.txt files don't accumulate

## Implementation Steps

1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block
2. Add `scope: ["${context.run_dir}"]` to the loop's top-level keys (matching `autodev.yaml`'s placement)
3. Replace the 4 occurrences of `.loops/tmp/prompt-across-issues-pending.txt` in shell actions and prompt text with `${context.pending_file}`; in `advance`, use `$(dirname "${context.pending_file}")` for the `.tmp` swap target
4. Delete `shared_state_ok: true` from the loop YAML
5. Add `scripts/tests/test_prompt_across_issues_loop.py` with the concurrent-collision regression test
6. Add the `_scopes_overlap` disjoint-scope unit test to `scripts/tests/test_lock_manager.py`
7. Run the full validation gate: `ll-loop validate prompt-across-issues`, `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_prompt_across_issues_loop.py scripts/tests/test_lock_manager.py -x --tb=short`
8. Manual verification: start two `prompt-across-issues` instances on `--context parent=EPIC-2457` and `--context parent=EPIC-2451` (the pair from the 2026-07-06 collision), confirm no `Scope conflict` error, confirm each instance's `run_dir`/`pending.txt` contains only its own parent EPIC's children, confirm both terminate cleanly
9. Update `docs/guides/LOOPS_GUIDE.md` if any references are found in step 7's documentation sweep

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Steps 1 + 3 are mutually incompatible with how context template resolution works** (see Proposed Solution § Codebase Research Findings). The `context.pending_file` indirection must be dropped; the implementation should use `${context.run_dir}/pending.txt` directly inline in shell actions (matches `general-task.yaml:103-150` and `autodev.yaml`). Revised step 1: **omit entirely**. Revised step 3: replace with `${context.run_dir}/pending.txt` (8 path-occurrence replacements — see Integration Map § Codebase Research Findings for the full line list). In `advance`, use `DIR="$(dirname "${context.run_dir}/pending.txt")"` and `tail -n +2 "${context.run_dir}/pending.txt" > "$DIR/pending.tmp"` then `mv "$DIR/pending.tmp" "${context.run_dir}/pending.txt"`.
- **Add an unmentioned step: delete line 50 `mkdir -p .loops/tmp`.** Once the path moves to `${context.run_dir}/pending.txt`, the `.loops/tmp/` directory is no longer needed by this loop. The runner creates `${context.run_dir}` at `scripts/little_loops/cli/loop/run.py:483` before any state executes, so no defensive `mkdir -p` is required.
- **Step 6 target file is wrong.** Add the `resolve_scope(["${context.run_dir}"], ...)` disjoint-scope unit test to `scripts/tests/test_concurrency.py` (extend `TestResolveScope` or `TestLockManager`), not `test_lock_manager.py` (does not exist).
- **Step 7 test command path correction.** Replace `test_lock_manager.py` with `test_concurrency.py` in the pytest invocation: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_prompt_across_issues_loop.py scripts/tests/test_concurrency.py -x --tb=short`.
- **`diagnose_error` prompt text (line 134) needs special handling.** The path string `${env.PWD}/.loops/tmp/prompt-across-issues-pending.txt` is a literal embedded in the LLM prompt body. Replace with `${context.run_dir}/pending.txt` (the FSM engine will resolve `${context.run_dir}` at prompt-render time, since prompt actions go through the same interpolation pass). The `${env.PWD}` prefix is a non-FSM `${env.*}` pattern the engine does not interpret — leaving it as-is is harmless because shell-side `${env.PWD}` is also not substituted by the engine; the LLM only needs the resolved path.
- **`input_hash` is auto-injected by the runner** (`scripts/little_loops/cli/loop/run.py:182-183`, SHA-256 first 12 chars of input). `prompt-across-issues` does not currently reference `${context.input_hash}` and does not need to — keep that unchanged.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Verify all 8 path-occurrence replacements in `prompt-across-issues.yaml`** (per § Codebase Research Findings): grep for `.loops/tmp/prompt-across-issues-pending.txt` before and after the edit; assert zero matches post-fix. Replacement lines per issue: 64 (`init` write), 65 (`init` read), 75 (`discover` test), 78 (`discover` read), 117 (`advance` write to `.tmp`), 118 (`advance` mv), 119 (`advance` read), 134 (`diagnose_error` prompt text). Plus delete line 50 (`mkdir -p .loops/tmp`) which becomes redundant.
11. **Verify MR-3 gate clears**: run `validate_fsm(load_and_validate("scripts/little_loops/loops/prompt-across-issues.yaml"))` and assert zero WARNING entries from `_validate_artifact_isolation` (`scripts/little_loops/fsm/validation.py:1418-1448`). The MR-3 scanner is gated by `fsm.shared_state_ok` (early-return at line 1430); once `shared_state_ok: true` is removed, this gate starts enforcing — any residual `.loops/tmp/` reference will surface here.
12. **Verify `info.py:1159-1160` surfaces the new `scope:` declaration**: run `ll-loop show prompt-across-issues` after the fix and assert the output includes `scope: ${context.run_dir}`.
13. **Verify `lifecycle.py:501-504` resume path resolves `${context.run_dir}` correctly**: confirm a `prompt-across-issues` instance started today can be `--resume`d tomorrow and reads the same `pending.txt` (i.e., `run_dir` is stable across `instance_id`).
14. **Verify `testing.py:213-216` `ll-loop test` simulation resolves the new path**: confirm `ll-loop test prompt-across-issues` (or any state-level test harness) substitutes `${context.run_dir}` against the test-injected `run_dir` and the new `pending.txt` is created there.
15. **Cross-check `.ll/decisions.yaml:4010-4023` (`ARCHITECTURE-106`) survives `sync_to_local_md`**: after implementation, run `ll-issues decisions sync` and verify the rule is preserved without modification (it should be — the rule already prescribes the post-fix pattern).
16. **Cross-check `.claude/CLAUDE.md:149` MR-3 row** still describes the suppression mechanism accurately post-fix (the description "Suppress with `shared_state_ok`" remains correct; only the implicit per-loop context changes).
17. **Optional follow-up: mark `thoughts/audits/loop-artifact-isolation-audit.md:62, 112` as resolved** — the audit lists `prompt-across-issues` as needing migration; after this fix, update the audit entry to reflect the migration is complete.

## Success Metrics

- **Zero collision across 10 concurrent runs**: spin up 10 `prompt-across-issues` instances on 10 distinct `--context parent=` filters simultaneously; assert no `pending.txt` clobber and all 10 terminate with the expected issue count
- **No `--no-lock` required**: the user can run two concurrent sweeps without bypassing the LockManager — verified by running with the default flags and confirming no `Scope conflict` error at startup
- **`ll-loop validate` clean**: validation passes with no MR-3 violation (the `.loops/tmp/` exemption is removed)
- **No regression in `general-task.yaml` pattern**: BUG-1960's fix remains intact (re-run `python -m pytest scripts/tests/test_general_task_loop.py -x`)

## Scope Boundaries

- **Out of scope**: migrating the other 18 built-in loops still using `.loops/tmp/` paths (BUG-1960 listed them; each is its own issue). This ENH covers `prompt-across-issues.yaml` only.
- **Out of scope**: changes to the LockManager itself — `resolve_scope` and `_scopes_overlap` already handle `${context.run_dir}` interpolation; no runner changes expected.
- **Out of scope**: introducing a "task fingerprint" check (analogous to BUG-1960 Fix 3) — the per-instance path makes cross-run contamination impossible by construction, so fingerprinting adds no value here.
- **Out of scope**: widening scope to include `${context.parent}` — recommend revisit only if user reports a same-parent cross-instance collision in production.

## Impact

- **Priority**: P3 — affects data integrity for a power-user workflow (concurrent sweeps), but the loop is fully functional in the single-instance case. Default users are unaffected.
- **Effort**: Small — ~15 lines changed in one YAML file plus two new tests (~80 lines). Reuses the exact migration pattern from BUG-1960 and the scope pattern from `autodev.yaml`.
- **Risk**: Low — `${context.run_dir}` is already injected by the runner; no behavioral change for single-instance users. The `--no-lock` workaround remains a valid escape hatch for anyone who explicitly needs to bypass scope checks (no deprecation).
- **Breaking Change**: No — public CLI surface (`ll-loop run prompt-across-issues …`) unchanged; pending list location moves from `.loops/tmp/` to `.loops/runs/<instance>/`, which is internal.

## Related Key Documentation

- `scripts/little_loops/loops/general-task.yaml` — BUG-1960's reference implementation for the per-run-dir migration
- `scripts/little_loops/loops/autodev.yaml` — `scope: ["${context.run_dir}"]` precedent
- `scripts/little_loops/loops/rn-refine.yaml` — variable-substitution `scope:` precedent
- `docs/generalized-fsm-loop.md` — documents `${context.run_dir}` context variable
- `docs/guides/LOOPS_GUIDE.md` — built-in loop reference (verify after change)
- `.claude/CLAUDE.md` § Loop Authoring — MR-3 rule (`.loops/tmp/` exemption warning), MR-7/9 shell-escape rules

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/little_loops/fsm/concurrency.py`** (lines 35-53, 130-175, 187-236, 323-356) — `resolve_scope`, `LockManager.acquire`, `find_conflict`, `_scopes_overlap`, `_paths_overlap`. Confirms: (1) `${context.*}` templates are interpolated against the `fsm.context` dict at runtime (not at YAML load); (2) scope paths are normalized via `Path(path).resolve()` (`_normalize_path`, line 358-360) so `run_dir` strings become absolute before comparison; (3) `_paths_overlap` uses filesystem-tree subset semantics — disjoint sibling paths do not overlap, so distinct timestamped `run_dir`s always produce disjoint scopes.
- **`scripts/little_loops/fsm/validation.py`** (lines 104-107, 1377-1448) — `_SHARED_TMP_PATH_RE`, `_find_shared_tmp_writes`, `_validate_artifact_isolation`. The `shared_state_ok: true` early-return at line 1430 short-circuits the entire MR-3 scan for the loop. After removal, the validator will WARN on any residual `.loops/tmp/` references — useful as a regression net.
- **`scripts/little_loops/fsm/schema.py`** (line 1038) — `FSMLoop.scope: list[str] = field(default_factory=list)`. Adding `scope: ["${context.run_dir}"]` is a schema-supported top-level key with no validator changes needed.
- **`scripts/little_loops/cli/loop/run.py`** (lines 175-178, 483) — `run_dir` injection + mkdir. Confirms `${context.run_dir}` is guaranteed to exist before any state runs.
- **`scripts/little_loops/cli/loop/_helpers.py`** (lines 1239-1241, 1266-1292) — `_make_instance_id` (1-second granularity timestamp) and the pre-flight scope-conflict check. Pre-flight runs in the parent shell; child re-exec's `LockManager.acquire` closes the TOCTOU race with fcntl sentinel.
- **`scripts/tests/test_concurrency.py`** (lines 60-720) — all LockManager / resolve_scope tests. `TestResolveScope::test_with_context_var` (line ~665) and `TestLockManagerRaceConditions::test_concurrent_acquire_same_scope_only_one_wins` (line ~340) are the two precedents to mirror.
- **`scripts/tests/test_general_task_loop.py`** (lines 1305-1401) — BUG-1960 regression test pattern: `_load_state_script(state_name)`, `_setup_run_dir(tmp_path)`, `_bash(script, cwd=tmp_path)`. Mirror this for `test_prompt_across_issues_loop.py`.
- **`scripts/tests/test_fsm_validation.py`** (lines 1256-1349) — `TestArtifactIsolation` MR-3 unit tests (8 test methods). The `test_mr3_suppressed_by_shared_state_ok` (line ~1336) and `test_mr3_does_not_fire_when_loop_uses_context_run_dir` (line ~1279) tests directly cover the before/after states.
- **`scripts/tests/test_builtin_loops.py`** (lines 1576-1689) — `TestPromptAcrossIssuesLoop` (17 existing structural tests). Add MR-3 regression tests to this class per `Integration Map → Tests → Codebase Research Findings`.
- **`scripts/tests/test_rn_implement.py`** (lines 503-580) — `test_mr3_no_loops_tmp_writes` + `test_shared_state_ok_is_false` precedent. Direct copy/adapt for prompt-across-issues.

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-07-06T23:18:36 - `b40dc064-82ba-4007-afc5-5edcd3d6e37f.jsonl`
- `/ll:wire-issue` - 2026-07-06T23:15:27 - `92c11ed2-4ada-4b29-8c65-a2bbfde75f29.jsonl`
- `/ll:refine-issue` - 2026-07-06T23:05:27 - `7d53ffac-32c7-4513-8b32-280c71dc29a5.jsonl`
- `/ll:capture-issue` - 2026-07-06T20:21:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53fe5b07-3152-43ab-8a19-a7e0451c11cf.jsonl`