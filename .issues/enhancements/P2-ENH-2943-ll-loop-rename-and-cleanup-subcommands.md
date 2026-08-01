---
id: ENH-2943
title: 'll-loop rename and ll-loop cleanup: loop lifecycle mechanics out of markdown'
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- loops
- lifecycle
confidence_score: 96
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 23
completed_at: '2026-08-01T08:45:22Z'
---

# ENH-2943: `ll-loop rename` + `ll-loop cleanup` — lifecycle mechanics out of markdown

## Summary

Three lifecycle files are near-100% mechanical: `skills/rename-loop/SKILL.md` (261 lines), `skills/cleanup-loops/SKILL.md` (398 lines), `commands/cleanup-worktrees.md` (64 lines). Move the mechanics into `ll-loop` subcommands.

## Current Behavior

- **rename-loop**: 9 steps, zero judgment — strip `.yaml`/kebab-case validation (L41–46), 2-path file location (L52–62), destination-exists + running-loop guards via `ls .loops/.running/<old>-*.pid` (L68–88), Grep for `loop:\s+<old>` refs across loops/tests/docs (L108–149), fixed-format dry-run and results tables (L155–180, L221–243), `replace_all` Edits (L206–218).
- **cleanup-loops**: deterministic 6-way classification (stuck-running / stale-interrupted / stale-interrupted-aged / abandoned-handoff / terminal / healthy) driven purely by `status` × `kill -0` pid-liveness × age thresholds (L108–195), including an inline `python3 -c` age computation the LLM is told to run (L99–106) and archive moves with string-sliced `run_id` (L281–295). Only Step 7 (L327–344) — root-cause narration from `tail -20 events.jsonl` — needs an LLM.
- **cleanup-worktrees**: 64 lines wrapping a single boolean: `ll-parallel --cleanup-orphans [--dry-run]`.

## Expected Behavior

- `ll-loop rename <old> <new> [--dry-run] [--yes]` — validates, guards (destination exists, loop running), renames the YAML, rewrites `loop:` references across loops/tests/docs, reports a summary. Skill → ~30 lines.
- `ll-loop cleanup [--dry-run] [--threshold <days>] [--interrupted-age <hours>] --json` — performs the 6-way classification, stops/archives per class, emits JSON per run. Skill keeps only the LLM hook: narrate root causes for interrupted/anomalous runs from the JSON + event tails.
- `commands/cleanup-worktrees.md` → a direct `ll-parallel --cleanup-orphans` invocation (a few lines).

## Proposed Solution

Reuse `ll-loop list/status --json` internals (state files, pid checks in `cli/loop/`), the psutil identity-checked liveness pattern from `ll-loop queue` (FEAT-2684), and `ll-parallel`'s existing cleanup flag. rename's reference rewrite can reuse the static `loop:` ref resolution logic in `fsm/validation.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/validation/reachability.py:_validate_loop_references()` (not `fsm/validation.py` — validation now lives under `fsm/validation/` as a package) only *validates* resolvability of `state.loop` — it skips dynamic `${...}` names and calls `resolve_loop_path()` (`scripts/little_loops/fsm/loop_paths.py`), raising on `FileNotFoundError`. It does not enumerate or rewrite matches, so rename's ref-rewrite needs new code that walks the same `state.loop == old_name` space (or keeps the current grep-based `loop:\s+<old_name>` match) and reuses `resolve_loop_path`'s project→builtin search order for scope/location resolution.
- The pid-liveness check actually used in `cli/loop/lifecycle.py` (`cmd_status`, `cmd_stop`) and `_reconcile_stale_running()`/`_reconcile_stale_runs()` (`fsm/persistence.py`) is the lightweight `_process_alive(pid)` in `scripts/little_loops/fsm/concurrency.py` (plain `os.kill(pid, 0)`), not the psutil identity check. The fuller psutil identity check (`_verify_queue_pid_identity()` in `scripts/little_loops/cli/loop/queue.py`, FEAT-2684) exists only for `ll-loop queue remove`, where a *recycled* PID must not be signaled. `cleanup`'s classification (read-only except via `ll-loop stop`) matches `_process_alive`'s existing usage pattern more closely than the psutil identity check.
- `StatePersistence.archive_run()`/`clear_all()` (`scripts/little_loops/fsm/persistence.py`) already implements the exact run_id-derivation-plus-archive-move mechanism the skill's Step 3/6 (`stale-interrupted-aged`) hand-rolls in bash/inline python3 — `archive_run()` derives `run_id` from `state.started_at` and copies `state.json`/`events.jsonl` into `.loops/.history/<run_id>-<loop_name>/`. `cleanup()`'s archive action should call this directly instead of re-deriving `run_id` by string-slicing.
- `_reconcile_stale_runs()` (`fsm/persistence.py`) already covers 2 of the skill's 6 classes (stuck-running → archived, terminal → archived) via `status × pid-liveness` — `classify_run()` needs to be a strict superset pure function (adds the two age thresholds and the `stale-interrupted`/`abandoned-handoff` branches `_reconcile_stale_runs()` doesn't handle).
- No kebab-case validator exists anywhere in `scripts/little_loops/` (only free-text help strings) — `rename`'s naming guard is new code, not a reuse.
- Closest existing shape match for `cleanup()`'s pure-function/dataclass split: `scripts/little_loops/analytics/variance.py` (`EvaluatorVariance`/`VarianceReport` dataclasses with `to_dict()`) consumed by `cmd_diagnose_evaluators()`/`cmd_calibrate_budget()` in `cli/loop/info.py` — pure computation lives in a separate module, the CLI command function only handles `--json`/human-render branching and exit code.
- Dry-run-gated mutation with an always-populated report object precedent: `scripts/little_loops/issues/anchor_sweep.py` (`SweepResult` dataclass, `_sweep_file()`) — the mutation function always records what it did/would-do; `dry_run` only gates the actual `atomic_write()`. `RenameReport.refs_rewritten` should follow this same "always collect, conditionally apply" shape.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()`'s dispatch table: add `rename`/`cleanup` to the `known_subcommands` set (~L54–86, needed so `ll-loop rename foo bar` isn't swallowed by the "bare loop name → insert run" shorthand at L88–94), add `subparsers.add_parser(...)` blocks, add `elif args.command == "rename": ...` / `"cleanup"` arms (~L992). Follow the flat `edit-routes`/`promote-baseline` shape (not the nested `queue` subcommand shape, since `rename`/`cleanup` aren't verb groups).
- New module `scripts/little_loops/cli/loop/rename.py` — `rename_loop()`, `cmd_rename()`; lazy-imported inside `main_loop()`'s `with cli_event_context(...)` block, matching `edit_routes.py`/`next_loop.py`/`queue.py`.
- New module `scripts/little_loops/cli/loop/cleanup.py` (or `scripts/little_loops/loops_cleanup.py` for the pure-function half, mirroring `analytics/variance.py`'s split) — `classify_run()`, `cleanup()`, `cmd_cleanup()`.
- `commands/cleanup-worktrees.md` — already a thin wrapper (`mode` arg → `ll-parallel --cleanup-orphans [--dry-run]`); only the `mode` string parsing needs collapsing to a direct flag passthrough.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/persistence.py` — `_find_instances()`, `_read_pid_file()`, `_reconcile_stale_running()` (singular, per-instance), `_reconcile_stale_runs()` (plural, startup sweep), `StatePersistence.archive_run()`/`clear_all()` — direct dependencies for `cleanup`'s classification/action phases.
- `scripts/little_loops/fsm/concurrency.py` — `_process_alive(pid)`, the liveness check `cleanup`'s classification should reuse.
- `scripts/little_loops/fsm/validation/reachability.py` — `_validate_loop_references()`; `scripts/little_loops/fsm/loop_paths.py` — `resolve_loop_path()` (project→builtin search order rename's Step 2 location logic duplicates today).
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status()`/`_status_single()`, `cmd_stop()` (SIGTERM→10s→SIGKILL via `_kill_with_timeout`/`_signal_process_group`/`os.killpg`) — `cleanup`'s stuck-running action calls this.
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` → `list_running_loops()` (`fsm/persistence.py`), the `list --running --json` source the skill's Step 1 currently shells out to.
- `scripts/little_loops/cli/parallel.py` (~L211–226) → `little_loops.parallel.orchestrator.ParallelOrchestrator._cleanup_orphaned_worktrees()` — already-implemented target for `cleanup-worktrees.md`.

### Similar Patterns

- `scripts/little_loops/issues/anchor_sweep.py` (`SweepResult`, `_sweep_file()`) — dry-run-gated mutation with always-populated report dataclass.
- `scripts/little_loops/analytics/variance.py` + `cli/loop/info.py:cmd_diagnose_evaluators()` — pure-function-in-separate-module + thin CLI-command-does-only-io/json-branching split.
- `scripts/little_loops/cli/loop/queue.py` — nested-subcommand precedent (`queue list`/`queue remove`) and the psutil identity-check pattern (`_verify_queue_pid_identity()`), for reference even though `cleanup`'s liveness check should use the lighter `_process_alive()` instead.

### Tests

- `scripts/tests/test_cli_loop_queue.py` — closest existing test-convention precedent: `tmp_path`-based `.queue`/`.running` fixture directories (not mocks), `capsys` for stdout capture, `patch()` targeted at the *consuming* module path (e.g. `little_loops.cli.loop.queue.os.kill`). `classify_run()`'s status×pid×age test matrix (Implementation Step 2) should follow this fixture-file convention. No existing `pytest.mark.parametrize` classification-table test was found in the codebase for status×condition matrices in loop code — `scripts/little_loops/issue_lifecycle.py:classify_failure()` + `scripts/tests/test_issue_lifecycle.py::TestClassifyFailure` (parametrized rows of `(inputs..., expected_classification, expected_reason_fragment)`, plus separate non-parametrized boundary tests) is the closest cross-codebase precedent to model `classify_run()`'s tests after.
- `scripts/tests/test_cli_loop_lifecycle.py`, `scripts/tests/test_fsm_persistence.py` — existing coverage of `_reconcile_stale_running()`/`_reconcile_stale_runs()`/`cmd_stop()` that `cleanup()` reuses; new tests should extend these files' fixtures rather than duplicate them.
- `scripts/tests/test_parallel_cli.py` — existing `--cleanup-orphans` coverage; `cleanup-worktrees.md`'s slimming needs no new test since the underlying flag is already tested.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — `_mock_handlers()` (module-path→function-name dict) mocks every existing subcommand handler and asserts routing/flag-forwarding; must gain entries for `cmd_rename`/`cmd_cleanup`. `TestMainLoopQueueDispatch` (~L1055) is the closest structural twin for a new top-level verb group (flag forwarding, bare-subcommand-prints-help-and-returns-1 case). Also needs a new test analogous to `TestMainLoopShorthand::test_unknown_first_arg_inserts_run` proving `"rename"`/`"cleanup"` are excluded from the bare-loop-name shorthand once added to `known_subcommands` — that exclusion isn't automatically covered by adding subparsers alone.
- `scripts/tests/test_fsm_validation_reachability.py::TestLoopReferenceValidation` — `_validate_loop_references()` is a per-loaded-FSM, single-state validator, not a cross-file reference finder, so it can't be reused directly for rename's ref-discovery — but it's the existing gate a missed rewrite would trip (`test_missing_loop_reference_emits_error`'s ERROR path fires on a stale `loop: <old_name>` after the old file is renamed away). Add a rename regression test asserting `ll-loop validate`/`load_and_validate` produces zero `nonexistent-loop`-style errors across any loop that referenced the renamed name, post-rename.
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases::test_current_tree_baseline_does_not_grow` — asserts `len(scan_prose(repo_root)) <= BASELINE_COUNT` (currently 23, comment notes this is EPIC-2938's frozen baseline). The `<=` means removing prose hits from `rename-loop`/`cleanup-loops` SKILL.md won't fail this test, but `BASELINE_COUNT` should be manually decremented afterward to ratchet the ceiling down (no test enforces this — a manual follow-up noted in the test's own comment).
- No dedicated unit-test file exists for the closest "always collect, conditionally apply" precedent (`scripts/little_loops/issues/anchor_sweep.py`'s `SweepResult`/`_sweep_file()`) — its only coverage is CLI-level (`scripts/tests/test_issues_cli.py::TestIssuesCLIAnchorSweep`, asserting on stdout/file-mutation through `main_issues()`, not on dataclass fields directly). `RenameReport`/`CleanupEntry` tests should decide explicitly whether to follow this CLI-only convention or add a module-level layer the codebase doesn't otherwise have.

### Documentation

- `docs/reference/CLI.md`, `docs/reference/COMMANDS.md` — need `rename`/`cleanup` subcommand entries.
- `docs/guides/LOOPS_REFERENCE.md` — loop-command reference; may need a mention of the new lifecycle subcommands.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — two mentions: `/ll:cleanup-worktrees [mode]` in the detailed "Available Commands" entry (~L177, the `[mode]` argument-hint goes stale once the mode arg collapses to a direct flag passthrough) and the condensed "Git & Release" category line (~L333, name stays valid, no edit needed there).
- Host-adapter generated mirrors of the above and of `agents/loop-specialist.md` — `.gemini/commands/cleanup-worktrees.toml`, `.gemini/commands/help.toml`, `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md`, `.codex/agents/loop-specialist.toml`, `.gemini/agents/loop-specialist.md`. These are `ll-adapt` outputs — regenerate via `ll-adapt --host <host> --apply` per host after editing the canonical `commands/`/`skills/`/`agents/` files; do not hand-edit.
- `skills/ll-cleanup-worktrees/SKILL.md` — thin Codex-bridge pointer ("Bridged from `commands/cleanup-worktrees.md`..."); verify it stays accurate, likely no content change needed.
- `CONTRIBUTING.md` (~L657) — cites `cleanup-worktrees` by name as a worked example of a `disable-model-invocation: true` skill; verify the example still holds once the command is slimmed.
- `docs/ARCHITECTURE.md` (~L132, ~L208) — directory-tree annotations for `cleanup-loops/` and `rename-loop/`; verify the `rename-loop/` annotation text ("Rename a loop and update all references") still holds post-change.
- `agents/loop-specialist.md` (~L8, ~L138) — behavioral pointers delegating to `/ll:rename-loop`/`/ll:cleanup-loops` and framing `cleanup-loops` as owning "retention"; verify against the slimmed skill's actual capability boundary.
- `.ll/decisions.yaml` (~L2287–2290) — existing decision entry `'Preferred path: delegate cleanup-worktrees to ll-parallel --cleanup-orphans'` (scope: issue); check whether it needs an outcome/promotion update via `ll-issues decisions outcome` once implemented — do not hand-edit (append-only, managed by the decisions CLI).
- `ll-verify-skill-prose` gate — may newly flag or need a `<!-- ll-prose-ok: reason -->` suppression removed once the mechanical prose (kebab-case validation, age-computation snippet, 6-way classification table, archive-move string-slicing) is deleted from the three skill/command files.

## Implementation Steps

1. `ll-loop rename` + tests (guards, dry-run parity with apply, ref rewriting).
2. `ll-loop cleanup` + tests (classification table as fixtures: status × pid × age).
3. Slim the three markdown files.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Extend `scripts/tests/test_cli_loop_dispatch.py` — add `cmd_rename`/`cmd_cleanup` to `_mock_handlers()`, add dispatch/flag-forwarding tests (model on `TestMainLoopQueueDispatch`), and add a shorthand-exclusion test proving `"rename"`/`"cleanup"` don't fall into the bare-loop-name-inserts-`run` path.
5. Add a rename regression test in `scripts/tests/test_fsm_validation_reachability.py` — post-rename, `ll-loop validate` produces zero stale `loop: <old_name>` reference errors.
6. Update `commands/help.md`'s `/ll:cleanup-worktrees [mode]` entry (~L177) to drop the stale `[mode]` argument-hint once collapsed to a direct flag passthrough.
7. Regenerate host-adapter mirrors via `ll-adapt --host <host> --apply` for each affected host (`.gemini/commands/cleanup-worktrees.toml`, `.gemini/commands/help.toml`, `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md`, `.codex/agents/loop-specialist.toml`, `.gemini/agents/loop-specialist.md`) after the canonical files change.
8. Manually decrement `BASELINE_COUNT` in `scripts/tests/test_verify_skill_prose.py` if the prose migration removes hits from `rename-loop`/`cleanup-loops` SKILL.md (ratchet the ceiling down; not enforced by the test itself).

## Program Design

### Types

- `RenameReport: dataclass` — `old: str`, `new: str`, `yaml_moved: bool`, `refs_rewritten: list[tuple[Path, int]]`, `dry_run: bool`
- `RunClass: Enum` — `STUCK_RUNNING | STALE_INTERRUPTED | STALE_INTERRUPTED_AGED | ABANDONED_HANDOFF | TERMINAL | HEALTHY`
- `CleanupEntry: dataclass` — `run_id: str`, `loop: str`, `cls: RunClass`, `pid_alive: bool`, `age_minutes: float`, `action_taken: str`

### Signatures

- `rename_loop(old: str, new: str, dry_run: bool) -> RenameReport` — guards: destination exists, `.loops/.running/<old>-*.pid`
- `classify_run(status: str, pid_alive: bool, age_minutes: float, thresholds: CleanupThresholds) -> RunClass` — the skill's 6-way table as pure function
- `cleanup(dry_run: bool, thresholds: CleanupThresholds) -> list[CleanupEntry]`

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `rename_loop()`
- `main_loop()` -> `cleanup()` -> `read_queue_entries()` (existing pid-marker pattern, `cli/loop/_helpers.py`)

## Scope Boundaries

- In scope: the two `ll-loop` subcommands, slimming the three markdown files, pid-liveness reuse from the FEAT-2684 pattern.
- Out of scope: changing classification semantics, `ll-parallel` internals (cleanup-worktrees just calls the existing flag), loop archival format changes.

## Impact

- **Priority**: P2 - ~660 lines of lifecycle prose removed; cleanup becomes safely re-runnable by automation
- **Effort**: Medium - Two subcommands, well-specified behavior
- **Risk**: Low - `--dry-run` parity tested; rename guards prevent destructive mistakes

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-loop rename --dry-run` output matches what `--yes` then performs
- [ ] `ll-loop cleanup --json` classification reproduces the skill's 6-way decision table
- [ ] `skills/rename-loop/SKILL.md` ≤ ~40 lines; `skills/cleanup-loops/SKILL.md` retains only invocation + root-cause narration
- [ ] `commands/cleanup-worktrees.md` is a direct `ll-parallel` invocation
- [ ] pytest coverage in `scripts/tests/`

## Notes

If oversized, `rename` is the natural standalone split.


## Session Log
- `ll-auto` - 2026-08-01T08:45:22 - `c8ef15b9-94d6-4d30-8319-de69dac016ce.jsonl`
- `/ll:ready-issue` - 2026-08-01T08:37:59 - `42303ac4-b51e-44ee-8ebb-986f788ea2ca.jsonl`
- `/ll:confidence-check` - 2026-08-01T08:36:50 - `3ceb3084-12a8-460b-aee1-e6c69bae4f97.jsonl`
- `/ll:wire-issue` - 2026-08-01T08:35:58 - `11996918-b058-44c8-a694-d7c9f378a4de.jsonl`
- `/ll:refine-issue` - 2026-08-01T08:30:40 - `7b75a4c6-fc3c-498e-b17f-c02db74dce82.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-01
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
