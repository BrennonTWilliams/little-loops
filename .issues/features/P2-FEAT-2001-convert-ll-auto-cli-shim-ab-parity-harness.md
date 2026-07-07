---
id: FEAT-2001
title: Convert ll-auto CLI to thin shim over ll-loop and build A/B parity harness
type: FEAT
priority: P2
status: deferred
parent: EPIC-1867
blocked_by:
- FEAT-2000
blocks:
- FEAT-2002
- FEAT-1899
relates_to:
- FEAT-2002
- FEAT-1902
size: Very Large
confidence_score: 83
outcome_confidence: 73
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 15
missing_artifacts: true
---

# FEAT-2001: Convert ll-auto CLI to thin shim over ll-loop and build A/B parity harness

## Summary

Convert `scripts/little_loops/cli/auto.py:main_auto()` to a thin shim that delegates to
`ll-loop run ll-auto`. Add a deprecation warning to `AutoManager.run()`. Build the A/B
parity harness that asserts behavioral equivalence between the legacy and FSM paths.
Update all affected tests.

## Parent Issue

Decomposed from FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Use Case

Developer converts the `ll-auto` CLI so it delegates to the FSM, preserving the existing
CLI interface while routing control flow through `ll-loop run ll-auto`. The A/B parity
harness gates merging by asserting identical `completed/failed` sets and `history.db`
event payloads between the legacy and FSM paths.

## Depends On

FEAT-2000 must be merged first — this child invokes `ll-loop run ll-auto`, which requires
`loops/ll-auto.yaml` to exist.

## Implementation Steps

3. Convert `scripts/little_loops/cli/auto.py:main_auto()` to thin shim over
   `ll-loop run ll-auto`. Forward all existing flags as `--context KEY=VALUE` overrides:
   `--max-issues` → `max_issues`, `--resume` → `resume`, `--only` → `only_ids`,
   `--skip` → `skip_ids`, `--type` → `type_prefixes`, `--priority` → `priority_filter`,
   `--label` → `label_filter`, `--category` → `category`, `--quiet`/`--verbose` → `verbose`,
   `--dry-run` → `dry_run`, `--config` → `config`, `--idle-timeout` → `idle_timeout`,
   `--handoff-threshold` → `handoff_threshold`, `--context-limit` → `context_limit`.
   Preserve `cli_event_context(DEFAULT_DB_PATH, ...)` wrapper around the subprocess call.

   ### Codebase Research Findings (shim invocation)

   _Added by `/ll:refine-issue`:_

   **Subprocess invocation pattern** — use `sys.executable -m little_loops.cli.loop` (not the bare
   `ll-loop` binary) to avoid PATH resolution issues, consistent with how `_helpers.py:launch_background()`
   (`scripts/little_loops/cli/loop/_helpers.py:1018`) invokes the loop runner internally:
   ```python
   cmd = [sys.executable, "-m", "little_loops.cli.loop", "run", "ll-auto"]
   ```

   **Flag forwarding split** — `ll-loop run` accepts `--context KEY=VALUE` (action=`append`,
   registered at `scripts/little_loops/cli/loop/__init__.py:236`) for arbitrary context overrides.
   However, `--handoff-threshold` and `--context-limit` have **dedicated flags** on the `run`
   subparser (`cli/loop/__init__.py:238-239`) — pass these as direct args, not via `--context`:
   ```python
   # Use --context for: resume, dry_run, max_issues, only_ids, skip_ids, type_prefixes,
   #                    priority_filter, label_filter, category, verbose, idle_timeout, config
   if args.resume:       cmd += ["--context", "resume=true"]
   if args.dry_run:      cmd += ["--context", "dry_run=true"]
   if args.max_issues:   cmd += ["--context", f"max_issues={args.max_issues}"]
   # ...etc...
   # Use dedicated flags for: handoff_threshold, context_limit
   if args.handoff_threshold: cmd += ["--handoff-threshold", str(args.handoff_threshold)]
   if args.context_limit:     cmd += ["--context-limit", str(args.context_limit)]
   ```

   **`--quiet` vs `--verbose`** — these are separate flags (`add_common_auto_args()` registers
   `--quiet` → dest=`quiet`; `main_auto()` adds `--verbose` → dest=`verbose`). The FSM context
   should receive them as distinct keys (`quiet` and `verbose`), not collapsed to one.

   **`add_common_auto_args()` remains in place** — the shim still calls `parser.parse_args()` to
   validate and normalize CLI input; it just replaces `AutoManager(...)` construction with a
   `subprocess.run(cmd)` call. The function at `scripts/little_loops/cli_args.py:add_common_auto_args()`
   is only called by `main_auto()`, so removing it after the shim is safe if the FSM validates args.
   Decide: keep arg-parsing in shim for validation (recommended) or pass raw `sys.argv[1:]` through.

7. Build A/B parity harness in `scripts/tests/test_issue_manager.py`:
   - Shared fixture of ≥5 fixed issues in a temp directory
   - Run legacy path: `AutoManager(tmp_path).run()` with `pytest.warns(DeprecationWarning)`
   - Run FSM path: `ll-loop run ll-auto` subprocess
   - Compare `SELECT issue_id, transition FROM issue_events ORDER BY issue_id` from each
     run's `.ll/history.db`; assert sets identical
   - Follow pattern from `scripts/tests/test_generate_schemas.py:test_idempotent_on_second_run()`
   - Insert into existing `TestSequentialProcessing` class (L25+)

   **A/B parity test shape** (from `test_generate_schemas.py:test_idempotent_on_second_run()` at L122):
   ```python
   # Run A — legacy path
   manager = AutoManager(config=config, dry_run=True, ...)
   with pytest.warns(DeprecationWarning, match="AutoManager.run"):
       manager.run()
   snapshot_legacy = query_db(db_a, "SELECT issue_id, transition FROM issue_events ORDER BY issue_id")
   # Run B — FSM path
   subprocess.run([sys.executable, "-m", "little_loops.cli.loop", "run", "ll-auto",
                   "--context", "dry_run=true", ...], check=True)
   snapshot_fsm = query_db(db_b, "SELECT issue_id, transition FROM issue_events ORDER BY issue_id")
   assert snapshot_legacy == snapshot_fsm
   ```

8. Add deprecation warning at the top of `AutoManager.run()` in
   `scripts/little_loops/issue_manager.py` (class at ~L1087, `run()` at ~L1266 — line numbers as of last verification; confirm before use):
   ```python
   warnings.warn(
       "AutoManager.run() is deprecated; use ll-loop run ll-auto instead",
       DeprecationWarning,
       stacklevel=2,
   )
   ```
   Follow pattern from `scripts/little_loops/config/core.py:BRConfig.get_completed_dir()`.

11. Wrap all `manager.run()` call sites in `scripts/tests/test_issue_manager.py` with
    `pytest.warns(DeprecationWarning, match="AutoManager.run")`. Follow pattern from
    `scripts/tests/test_config.py:667` (`TestBRConfig.test_get_completed_dir`).

    ### Codebase Research Findings (exact call sites)

    _Added by `/ll:refine-issue`:_

    There are exactly **6 direct `manager.run()` call sites** in `test_issue_manager.py`
    (the "53+ matches" in confidence check notes was a grep count of all `.run()` on any object):

    | Line | Test class / method |
    |------|---------------------|
    | L2742 | `TestAutoManagerRun.test_run_processes_single_issue (class at ~L2742; method offsets below are approximate)` |
    | L2843 | `TestAutoManagerRun.test_run_stops_at_max_issues` |
    | L2874 | `TestAutoManagerRun.test_run_with_only_ids_filter` |
    | L2906 | `TestAutoManagerRun.test_run_with_numeric_only_id_filter` |
    | L2939 | `TestAutoManagerRun.test_run_returns_one_when_only_ids_all_gate_blocked` |
    | L3025 | `TestTimingSummaryAndStateUpdates.test_timing_summary_logged` |

    Each needs the `pytest.warns(DeprecationWarning, match="AutoManager.run")` context manager
    wrapping the `.run()` call, following the exact pattern at `test_config.py:668`.

12. Rewrite `scripts/tests/test_cli.py:TestMainAutoIntegration` (L276) and
    `TestMainAutoAdditionalCoverage` (L1466) — replace `patch("little_loops.cli.auto.AutoManager")`
    and `mock_manager_cls.assert_called_once()` with subprocess/`ll-loop` invocation
    assertions. `AutoManager` is no longer constructed inside `main_auto()` after shim.

    ### Codebase Research Findings (current test structure)

    _Added by `/ll:refine-issue`:_

    Both classes currently follow this pattern for every test:
    ```python
    with patch("little_loops.cli.auto.AutoManager") as mock_manager_cls:
        mock_manager = MagicMock()
        mock_manager.run.return_value = 0
        mock_manager_cls.return_value = mock_manager
        with patch.object(sys, "argv", ["ll-auto", "--dry-run", ...]):
            result = main_auto()
        # Assertions on mock_manager_cls.call_args.kwargs (constructor kwargs)
        assert mock_manager_cls.call_args.kwargs["dry_run"] is True
    ```

    After shim, replace with `patch("subprocess.run")` / `patch("subprocess.Popen")` and
    assert the subprocess `cmd` list contains the expected `--context KEY=VALUE` pairs. The
    existing `test_project_root_fallback_to_cwd` test shape (which uses `os.chdir`) can be
    preserved as-is since the shim still needs a project root.

13. Update `scripts/tests/test_cli_e2e.py`:
    - `test_ll_auto_dry_run()` (L235): update `mock_popen.call_count == 0` assertion to
      expect `ll-loop run ll-auto` subprocess call
    - `test_ll_auto_max_issues_limit()` (L279) and `test_ll_auto_category_filter()` (L295):
      rewrite to test shim flag-forwarding rather than direct `AutoManager` attribute inspection

    ### Codebase Research Findings (current e2e test shapes)

    _Added by `/ll:refine-issue`:_

    - `test_ll_auto_dry_run()` (L235) — calls `main_auto()` with `subprocess.Popen` patched;
      asserts `call_count == 0`. After shim, `ll-loop run ll-auto` will itself be the Popen call,
      so the assertion changes to `mock_popen.assert_called_once()` with args containing
      `"little_loops.cli.loop"` and `"run"`.

    - `test_ll_auto_max_issues_limit()` (L279) — **does NOT call `main_auto()`**; constructs
      `AutoManager` directly and asserts `manager.max_issues == 1`. After shim, this test
      becomes: call `main_auto()` with `["ll-auto", "--max-issues", "1"]` and assert the
      subprocess cmd contains `"--context", "max_issues=1"`.

    - `test_ll_auto_category_filter()` (L295) — same pattern: directly constructs `AutoManager`
      and asserts `manager.category == "bugs"`. Needs same rewrite as above.

    - `test_ll_auto_wires_sqlite()` (L398) — located inside `TestParallelExecutionWorkflow`
      (not `TestSequentialExecutionWorkflow`). Currently patches `little_loops.issue_manager.SQLiteTransport`
      and asserts `call_count == 1` to verify `AutoManager.__init__()` wires the transport.
      After shim, `SQLiteTransport` will be wired by the FSM runner inside `ll-loop`, not by
      `main_auto()` — this test must be rewritten to assert subprocess invocation, not in-process
      transport construction (see step 20).

16. Audit `scripts/little_loops/loops/autodev.yaml`, `scripts/little_loops/loops/oracles/implement-issue-chain.yaml`,
    `scripts/little_loops/loops/rn-remediate.yaml`, `scripts/little_loops/loops/eval-driven-development.yaml`, `scripts/little_loops/loops/lib/cli.yaml`
    — confirm exit-code routing survives shim. No changes expected if `ll-auto` preserves
    exit codes; document findings in a brief comment in the PR.

17. Wrap `manager.run()` call in
    `scripts/tests/test_issue_workflow_integration.py:TestSequentialWorkflowIntegration.test_dry_run_makes_no_changes`
    (~L82) with `pytest.warns(DeprecationWarning, match="AutoManager.run")`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

18. Audit `scripts/little_loops/cli_args.py:add_common_auto_args()` — determine whether the shim
    still invokes this function for arg-parsing or whether args are passed through raw to `ll-loop`;
    if the shim no longer calls `add_common_auto_args()`, verify no callers outside `auto.py` depend
    on its side-effects.

19. Wrap `test_issue_workflow_integration.py:TestSequentialWorkflowIntegration.test_max_issues_limits_processing()`
    (~L119) with `pytest.warns(DeprecationWarning, match="AutoManager.run")` — this test also
    constructs `AutoManager` and calls `.run()` directly but was omitted from the issue's list.

20. Rewrite `scripts/tests/test_cli_e2e.py:test_ll_auto_wires_sqlite()` (~L398) — currently patches
    `little_loops.issue_manager.SQLiteTransport` and expects `AutoManager` construction inside
    `main_auto()`; will break after shim; rewrite to assert subprocess-level behavior consistent
    with the other shim e2e tests.

21. After shim is in place, update `docs/reference/CONFIGURATION.md` "ll-auto exclusion" note under
    `events.transports` — current text states `cli/auto.py` does not construct an EventBus; the
    shim's delegation to `ll-loop run ll-auto` means this exemption no longer applies. Also update
    the corresponding assertion in `scripts/tests/test_wiring_guides_and_meta.py` if the
    `AutoManager.__init__()` anchor is removed from ARCHITECTURE.md.

## Acceptance Criteria

- [ ] `ll-auto` CLI is a thin shim over `ll-loop run ll-auto` (CLI interface preserved)
- [ ] All existing flags are forwarded as `--context KEY=VALUE` overrides
- [ ] `AutoManager.run()` emits `DeprecationWarning` with text "AutoManager.run() is deprecated"
- [ ] A/B parity harness passes: identical `{issue_id: transition}` sets between legacy and FSM runs
- [ ] `scripts/tests/test_issue_manager.py` — all `manager.run()` call sites wrapped with `pytest.warns`
- [ ] `test_cli.py` — `TestMainAutoIntegration` and `TestMainAutoAdditionalCoverage` test shim behavior
- [ ] `test_cli_e2e.py` — e2e tests updated to reflect `ll-loop` subprocess invocation
- [ ] `test_issue_workflow_integration.py` — `test_dry_run_makes_no_changes` wrapped with `pytest.warns`
- [ ] Dependent loop audit complete; no breaking changes in exit-code routing
- [ ] `.auto-manage-state.json` (repo root) is migrated or retired: resume responsibility moves to `ll-loop` run persistence, and the legacy state file is either converted on first run or documented as obsolete and removed (scope added 2026-06-12 — resolves Open Question 3 of the decomposition plan; without this, two resume mechanisms coexist after the FSM conversion)

## Files to Touch

- `scripts/little_loops/cli/auto.py` — convert `main_auto()` to thin shim
- `scripts/little_loops/issue_manager.py` — add `DeprecationWarning` to `AutoManager.run()` (L1234)
- `scripts/tests/test_issue_manager.py` — A/B parity harness + `pytest.warns` wrappers
- `scripts/tests/test_cli.py` — rewrite `TestMainAutoIntegration`, `TestMainAutoAdditionalCoverage`
- `scripts/tests/test_cli_e2e.py` — update `test_ll_auto_dry_run`, `test_ll_auto_max_issues_limit`, `test_ll_auto_category_filter`
- `scripts/tests/test_issue_workflow_integration.py` — add `pytest.warns` to `test_dry_run_makes_no_changes`

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports and re-exports `main_auto` in `__all__` (L39/81); shim body changes but import contract is stable — verify no wrapper logic in this file [Agent 1]
- `scripts/little_loops/cli/loop/__init__.py` — `--context` flag registered at L236 (`action="append"`, `metavar="KEY=VALUE"`); `--handoff-threshold` and `--context-limit` registered at L238-239 as dedicated flags on `run` subparser — forward these directly, not via `--context` [research]
- `scripts/little_loops/cli/loop/_helpers.py:launch_background()` (L1018) — reference implementation for invoking `little_loops.cli.loop` as a subprocess using `sys.executable -m`; follow this pattern for the shim's subprocess call [research]
- `scripts/little_loops/__init__.py` — imports and re-exports `AutoManager` in `__all__` (line 40/121); public API consumers calling `from little_loops import AutoManager` will start hitting `DeprecationWarning` on `.run()` — verify no doc/test asserts on absence of warning from the public import [Agent 1]
- `scripts/little_loops/cli_args.py` — `add_common_auto_args()` is called only by `main_auto()`; when the shim no longer parses args internally (or passes them through), this call site disappears — audit whether the function still needs to be invoked or if arg-forwarding replaces it [Agent 1/2]
- `scripts/little_loops/issue_lifecycle.py` — `complete_issue_lifecycle()` hard-codes the string `"ll-auto"` as the session log source label; if the label should change to reflect FSM routing, update here (but only if intentional — the string is asserted in `test_issue_lifecycle.py`) [Agent 2]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — contains an explicit "ll-auto exclusion" note under `events.transports` stating `cli/auto.py` does not construct an EventBus; **this claim inverts after the shim** since `ll-loop run ll-auto` does wire transports through the normal path — update this note [Agent 2]
- `docs/ARCHITECTURE.md` — `## Sequential Mode (ll-auto)` sequence diagram names `AutoManager` as participant; EventBus table row states `AutoManager.__init__()` bypasses `wire_transports()` — review and update if the shim changes this behavior [Agent 2]
- `docs/reference/API.md` — `### AutoManager` section documents `SQLiteTransport` wiring on construction and `main_auto()` as the entry point; add deprecation notice to `AutoManager.run()` docs [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_e2e.py:test_ll_auto_wires_sqlite()` (~L398) — patches `little_loops.issue_manager.SQLiteTransport` and expects `AutoManager` to be constructed by `main_auto()`; **will break** after shim — rewrite to assert shim subprocess invocation (not in issue's existing test update list) [Agent 3]
- `scripts/tests/test_issue_workflow_integration.py:test_max_issues_limits_processing()` (~L119) — constructs `AutoManager` directly and calls `.run()`; needs `pytest.warns(DeprecationWarning, match="AutoManager.run")` wrapper (issue lists only `test_dry_run_makes_no_changes` from this file) [Agent 3]
- `scripts/tests/test_wiring_guides_and_meta.py` — asserts `("docs/ARCHITECTURE.md", "AutoManager.__init__()", "ENH-1734")`; **will break** if ARCHITECTURE.md is updated and the exact string is removed — update the wiring assertion after doc update [Agent 2]
- `scripts/tests/test_wiring_reference_docs.py` — asserts `AutoManager` in CONFIGURATION.md; monitor after doc update [Agent 2]
- `scripts/tests/test_wiring_skills_and_commands.py` — asserts `AutoManager` in `config-schema.json`; monitor if schema description is updated [Agent 2]
- `scripts/tests/test_issue_lifecycle.py` (~L997) — `assert call_args.args[1] == "ll-auto"` hard-codes the source label string; safe if `"ll-auto"` is preserved in `issue_lifecycle.py`, breaks if changed [Agent 2]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `events.transports` description (L1293) explicitly names `AutoManager.__init__()` behavior (ll-auto exemption from EventBus wiring); update if shim's delegation to `ll-loop` changes the transport wiring contract [Agent 2]

## Similar Patterns

- `scripts/little_loops/config/core.py:BRConfig.get_completed_dir()` (L351) — deprecation warning pattern:
  `warnings.warn("... is deprecated; use ... instead", DeprecationWarning, stacklevel=2)`
- `scripts/tests/test_generate_schemas.py:test_idempotent_on_second_run()` (L122) — A/B parity test shape:
  run-A snapshot, run-B snapshot, `assert content_first == content_second`
- `scripts/tests/test_config.py:668` — `pytest.warns(DeprecationWarning, match="get_completed_dir")` pattern
- `scripts/little_loops/cli/loop/_helpers.py:launch_background()` (L1018) — subprocess invocation pattern
  using `[sys.executable, "-m", "little_loops.cli.loop", subcommand, loop_name]` with `subprocess.Popen`

## Impact

- **Priority**: P2
- **Effort**: Large — shim conversion, A/B harness, multiple test rewrites
- **Risk**: High — modifies `main_auto()` which has many test surfaces; A/B harness requires both legacy and FSM paths to work
- **Breaking Change**: No (shim preserves CLI interface)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-07_

**Readiness Score**: 83/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 73/100 → LOW

### Concerns
- FEAT-2000 is `open`; `loops/ll-auto.yaml` does not exist — shim cannot delegate to `ll-loop run ll-auto` without it

### Gaps to Address
- Gate implementation start on FEAT-2000 merge and verification that `loops/ll-auto.yaml` exists

### Outcome Risk Factors
- `loops/ll-auto.yaml` does not exist — it is a prerequisite from FEAT-2000, not a co-deliverable of this issue; the A/B parity harness cannot be exercised until FEAT-2000 is merged
- **Call-site count corrected** (codebase research, `/ll:refine-issue`): `test_issue_manager.py` has exactly **6** direct `AutoManager.run()` call sites (L2809, L2843, L2874, L2906, L2939, L3025). The prior "53+ matches" figure was a raw grep count of all `.run()` calls on any object in the file. All 6 are already enumerated in Implementation Step 11.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): Wiring-test anchor updates in `test_wiring_guides_and_meta.py`, `test_wiring_reference_docs.py`, and `test_wiring_skills_and_commands.py` are exclusively owned by **FEAT-2002**. Implementation step 21 in this issue (updating the `AutoManager.__init__()` anchor in ARCHITECTURE.md and its wiring-test assertion) and the corresponding `test_wiring_*.py` parametrized entries belong to FEAT-2002's documentation pass. Do not include those wiring-test anchor changes in this issue's PR — leave them for FEAT-2002.

## Verification Notes (2026-06-13)

- `AutoManager.run()` is at `issue_manager.py:1198` (issue says `:1165` — 33-line drift). `AutoManager` class itself is at `:1021` (matches). All 6 `manager.run()` call-sites in `test_issue_manager.py` are at exact lines listed (L2604, 2638, 2669, 2701, 2734, 2820).
- `loops/ll-auto.yaml` prerequisite still does not exist; remains blocked on FEAT-2000.

2026-06-13: `AutoManager.run()` now at :1198 (issue references :1165, drift of +33 lines). All 6 test call-sites in test_issue_manager.py confirmed accurate. Issue correctly blocked on FEAT-2000 (loops/ll-auto.yaml does not exist yet).

2026-06-17: Further drift — `AutoManager.run()` now at :1234 (was :1198/1165). All 6 `manager.run()` test call-sites have drifted ~149 lines (e.g. L2604→L2753, L2820→L2969). `--context` flag in `cli/loop/__init__.py` now at L234/382 (issue says L211). `loops/ll-auto.yaml` still does not exist; remains blocked on FEAT-2000.

2026-06-19 (NEEDS_UPDATE): All 6 `manager.run()` test call-sites in `test_issue_manager.py` have drifted ~149 lines since 2026-06-17 (now at L2753/L2787/L2818/L2850/L2883/L2969 vs. body's L2604–L2820). `--context` flag now at L234/L382. `loops/ll-auto.yaml` still absent; remains blocked on FEAT-2000.

- **2026-06-26** (/ll:verify-issues): Updated stale line numbers — `AutoManager.run()` body/Files-to-Touch to `issue_manager.py:1234`; the 6 `manager.run()` call-sites in `test_issue_manager.py` to L2809/L2843/L2874/L2906/L2939/L3025; `--context` flag to `cli/loop/__init__.py:236`. Scope/dependency claims (shim unbuilt, blocked on FEAT-2000) unchanged.

## Deferral Note

**Deferred** (2026-07-07, backlog grooming) — see EPIC-1867 for the full rationale and re-activation criteria. Summary: 0 of 4 EPIC-1867 layers delivered five weeks after capture; the decomposition premise is weakening because `ll-auto`/`ll-sprint`/`ll-parallel` are actively gaining Python behavior (ENH-2182, ENH-2210, `--feature-branches` override, push & PR creation). The shim + A/B parity work depends on a stable target; right now the target is still moving.

## Session Log
- `/ll:verify-issues` - 2026-06-27T19:13:21 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:verify-issues` - 2026-06-20T00:34:46 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:13:05 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:57 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `d64bcdbc-33e8-450c-b9ac-7d573dea9bb5.jsonl`
- `/ll:refine-issue` - 2026-06-07T18:08:42 - `e6ecb319-ccca-422a-9cca-3bc28f898fc2.jsonl`
- `/ll:wire-issue` - 2026-06-07T18:02:14 - `55c1ea13-0eec-4642-bbd8-5c4c57ca5308.jsonl`
- `/ll:issue-size-review` - 2026-06-07T00:00:00Z - `5db94c28-db76-4bed-885c-95a49da744cb.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `391b7385-6ae5-489b-b23e-15b1d324105b.jsonl`
