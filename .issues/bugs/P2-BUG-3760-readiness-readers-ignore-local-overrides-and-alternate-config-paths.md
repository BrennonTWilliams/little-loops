---
id: BUG-3760
type: BUG
title: Readiness readers ignore local overrides and alternate config paths
priority: P2
status: open
discovered_by: capture-issue
discovered_date: '2026-10-06'
captured_at: '2026-10-06T18:15:32Z'
testable: true
relates_to:
- BUG-3757
- ENH-3604
- BUG-3123
---

# BUG-3760: Readiness readers ignore local overrides and alternate config paths

## Summary

Readiness checks and next-action re-read a fixed `.ll/ll-config.json` path instead of consuming the merged configuration already loaded by `BRConfig`. Local threshold/enabled overrides, local null removal, root-level config and host-selected config are ignored. The same drift reaches next-obligation, run-record and the ll-auto readiness gate through `readiness_status()`. Honor the loaded configuration while preserving the distinct explicit-override and absent-key caller-fallback contracts. This is a separate follow-up from BUG-3757's set-flags/default correction, with no blocking dependency in either direction.

## Current Behavior

- `scripts/little_loops/cli/issues/check_readiness.py`, `resolve_confidence_thresholds()`, reads JSON from its path argument and applies caller defaults per missing key. `readiness_status()` supplies a fixed `.ll/ll-config.json` path and layers explicit overrides afterwards.
- `scripts/little_loops/cli/issues/next_action.py`, `cmd_next_action()`, supplies the same fixed path and uses argparse values as missing-key fallbacks. A present config key beats these arguments.
- `BRConfig._load_config()` already delegates to `load_raw_config()`, which resolves one base config and deep-merges `<root>/.ll/ll.local.md`, including when no base file exists. These readers bypass the loaded result. Local overrides still come from `.ll` when a host-specific base is selected; alternate base files are selected by precedence, not merged together.
- A local enabled override is missed in `ReadinessStatus.enabled`, which `process_issue_inplace()` actually consumes for the ll-auto pre-Phase-1 gate. `select_next_obligation()` and `write_typed_run_record()` also consume `readiness_status()`; the latter supplies both run-record and prep apply.
- Base outcome 65 / enabled false plus local outcome 75 / enabled true yields loaded 75 / true but readiness status 65 / false. A verified, formatted issue at readiness 90 / outcome 70 can consequently produce ALL_DONE from next-action. Removing base outcome 75 with local null leaves readiness using 75 although the loaded key was removed.
- ENH-3604 intentionally preserved absent-key caller defaults. Switching directly to populated `ConfidenceGateConfig` values would erase key absence and break that contract; preserve the decision rather than undoing it.
- `docs/reference/CLI.md`, **ll-issues next-action / ll-issues na**, describes a fixed `.ll` reader and incorrectly says an explicit `--ready-threshold` overrides config. The current command treats both threshold arguments as per-key fallbacks.

## Expected Behavior

- Both readers use the selected, merged raw configuration, retaining key presence after local null removal. A project with only `.ll/ll.local.md` works. Removing `enabled`, the whole `confidence_gate` block, or the `commands` ancestor restores the appropriate missing-key defaults rather than recovering values from the stale base file.
- `readiness_status`: explicit override > present merged config key > caller default. Enabled comes from the merged key, defaulting to false. Check-readiness continues to ignore enabled; ll-auto continues to honor it.
- `cmd_next_action`: present merged config key > argparse fallback, independently for each threshold. Its arguments remain fallbacks rather than unconditional overrides.
- Local null restores the caller's supplied default for that key, which may differ from 85/65. Partial blocks preserve each caller's other fallback. Root/host precedence remains the config loader's responsibility.
- The supplied `BRConfig` is authoritative for the duration of the call: later base/local file edits, deletions or host-environment changes do not change its thresholds. The raw accessor returns a detached copy; mutating its result cannot change subsequent reads. Never reconstruct `BRConfig`, call `load_raw_config()` again or use `to_dict()` on these paths.
- Existing missing-score, waiver, issue-selection, output-token and exit-code behavior remains intact. Malformed base JSON still fails BRConfig loading; the standalone path helper retains its existing read/parse-error fallback.

## Proposed Solution

Expose a narrow defensive copy of the loaded raw confidence-gate block through BRConfig. Extract the current per-key calculation into a pure mapping helper and call it from both BRConfig-backed readers. Keep `resolve_confidence_thresholds()` as the compatible path-reading wrapper that delegates to that calculation under its existing error fallback. This removes the fixed path from the loaded-config readers without introducing a mapping-versus-path precedence rule or a dummy path argument. Do not add FSM imports or reload configuration on these paths.

### Scope and Behavior Parity

- **Accepted change:** readiness consumers begin honoring the selected base, merged local values, local removals and the loaded snapshot. Their verdicts can change for projects whose configuration was previously ignored.
- **Preserved:** ENH-3604's per-key caller fallbacks; check-readiness's explicit overrides and enabled-independent comparison; ll-auto's enabled/readiness-only policy and existing dry-run/verify/plan/force bypasses; next-action's priority/ID order, format/verify/score stages, refinement cap and enabled-independent policy; next-obligation's explicit overrides/waiver; run-record's score/waiver/Program Design conjunction.
- **Non-goals:** legacy `threshold` alias harmonization, threshold coercion/range validation, new exit codes, changes to the FSM seeder or loop logic. The raw readers currently recognize only `readiness_threshold` and `outcome_threshold`; retain that behavior even though the typed loader also supports `threshold`. Preserve `.get()` values and existing `bool(enabled)` conversion; do not introduce `int()` coercion, truthiness-based threshold defaults or string-boolean normalization here.
- **Configuration errors:** `main_issues()` constructs `BRConfig` before dispatching either CLI command, and `process_issue_inplace()` already receives it. Malformed base JSON therefore already fails before these readers; no new construction, fallback or error policy is needed. A local YAML null is a merge-time removal sentinel; a literal null in base JSON is not automatically equivalent.

## Integration Map

### Files to Modify

- `scripts/little_loops/config/core.py` — proposed detached loaded raw-block accessor; reuse existing loading/merge behavior unchanged.
- `scripts/little_loops/cli/issues/check_readiness.py` — proposed pure calculation helper, existing path wrapper and readiness_status caller.
- `scripts/little_loops/cli/issues/next_action.py` — pure-helper input, existing fallback precedence.
- `scripts/tests/test_resolve_confidence_thresholds.py`, `scripts/tests/test_check_readiness.py`, `scripts/tests/test_next_action.py`, `scripts/tests/test_config.py`, `scripts/tests/test_issue_manager.py` — presence, snapshot, locations, precedence and actual gate behavior.
- `scripts/tests/test_ll_issues_next_obligation.py`, `scripts/tests/test_run_record.py` — downstream score token and typed readiness outcome against real merged configuration.
- `docs/reference/API.md` — accessor, pure helper and compatible path-wrapper contracts.
- `docs/reference/CLI.md` — next-action config-versus-flag precedence and selected/merged config notes for readiness commands. BUG-3757 owns the separate stale next-action default 70 → 65 in the same section; coordinate edits without adding a dependency.

### Dependent Files

- `scripts/little_loops/issue_manager.py` — consumes readiness_status and its enabled field; verify behavior without changing the readiness-only gate policy.
- `scripts/little_loops/cli/issues/next_obligation.py` — `select_next_obligation()` inherits the fix at its SCORES tier; preserve explicit override, waiver and probe-error routing.
- `scripts/little_loops/cli/issues/run_record.py` — `write_typed_run_record()` inherits the fix for run-record/prep apply; preserve Program Design, waiver, missing-score and legacy-class behavior. No source edits to these downstream consumers are planned.
- `scripts/little_loops/cli/issues/__init__.py` — `main_issues()` already constructs one BRConfig before dispatch; no new loader or error fallback.
- `scripts/little_loops/fsm/context_seed.py` — already consumes loaded typed defaults; leave its context precedence intact and avoid importing it into the helper.
- `scripts/little_loops/loops/autodev.yaml` and other explicit CLI-threshold callers — preserve explicit override behavior; no loop rewrite planned.
- BUG-3757 is related and independently implementable. ENH-3604 and BUG-3123 are completed precedents, not blockers.

## Program Design

### Types

- `gate_config: Mapping[str, Any]` — proposed pure helper input retaining omitted keys; local null has already removed keys during configuration merge.
- Accessor result: `dict[str, Any]`, detached from the loaded raw configuration and without dataclass defaults.
- Existing result: `tuple[int, int, bool]` for readiness, outcome and enabled.

### Signatures

- `BRConfig.confidence_gate_raw(self) -> dict[str, Any]` — proposed accessor in `scripts/little_loops/config/core.py`; return a `copy.deepcopy()` of loaded raw `commands.confidence_gate`, or `{}` when absent/non-mapping. Do not add defaults or normalize values. This does not make malformed blocks acceptable to BRConfig initialization.
- `confidence_thresholds_from_gate(gate_config: Mapping[str, Any], defaults: tuple[int, int]) -> tuple[int, int, bool]` — proposed pure helper in `scripts/little_loops/cli/issues/check_readiness.py`; return `gate_config.get("readiness_threshold", defaults[0])`, `gate_config.get("outcome_threshold", defaults[1])`, `bool(gate_config.get("enabled", False))`. Empty input uses the caller defaults without file access.
- `resolve_confidence_thresholds(config_path: Path, defaults: tuple[int, int]) -> tuple[int, int, bool]` — existing signature unchanged; read/parse the supplied path, extract the raw block, delegate to the proposed pure helper inside the existing broad exception fallback. No optional mapping or optional path parameter.
- Existing `readiness_status()` and `cmd_next_action()` keep their signatures and call the proposed pure helper with `config.confidence_gate_raw()`. Explicit overrides remain layered only in readiness_status, using `is not None` so zero remains an explicit value.

### Call Path

- Loaded-config path: `BRConfig` → proposed `confidence_gate_raw()` → proposed `confidence_thresholds_from_gate()` → `readiness_status()` / `cmd_next_action()` comparisons. Readiness-status consumers are check-readiness, ll-auto, next-obligation and the typed run-record writer.
- Compatibility path: `resolve_confidence_thresholds(path, defaults)` → read/parse raw gate → proposed `confidence_thresholds_from_gate()`; read/parse/extraction failures retain the wrapper's `(defaults[0], defaults[1], False)` fallback.

## Implementation Steps

1. Add the detached raw-block accessor over `_raw_config`. Extract the pure mapping calculation and make the existing path helper delegate under its unchanged exception fallback. Preserve raw value semantics and positional path calls; avoid `ConfidenceGateConfig`, `to_dict()` and FSM dependencies in the calculation.
2. Wire readiness_status and cmd_next_action to the pure helper using their already-supplied config. Remove their fixed config-path arguments. Leave signatures and all downstream caller wiring intact; never reconstruct/reload BRConfig.
3. Add a pure-helper table with noncanonical defaults `(40, 30)`: empty, each partial block, full, enabled absent/false/true, present zero thresholds and a legacy `threshold`-only block. Keep existing standalone missing/malformed/path tests. Test that modifying an accessor result, including a nested extra value, cannot affect subsequent reads.
4. Add focused real-config regressions from the matrix below. Show each affected-reader regression fails before the fix. Reuse `TestBRConfigLocalOverrides` and `TestResolveConfigPath` for loader mechanics; do not duplicate every host or recursive merge combination. Clear `LL_HOOK_HOST` and `LL_STATE_DIR` in location cases, then set the intended trigger. For next-action use eligible formatted/verified fixtures below the refinement cap, so a score-stage failure cannot be hidden by earlier stages.
5. Add real ll-auto gate cases using BRConfig and unpatched readiness_status, mocking only unrelated host/subprocess/advisor effects: local enable/disable, readiness pass↔fail and low-outcome-only nonblocking. Assert `was_gated`, the gate reason and whether Phase 1 was invoked. Add one next-obligation merged-threshold token case and one typed run-record merged-threshold outcome case; keep tier-1/Program Design prerequisites satisfied and explicit threshold/waiver/missing-score regressions passing. Existing `MagicMock(spec=BRConfig)` fixtures that exercise the real reader must return `{}` or a representative mapping from the new accessor; do not let an unconfigured mock supply truthy gate values. Keep the new configuration-wiring cases fully real.
6. Update source docstrings and API documentation for both helpers/accessor. Correct the CLI's next-action precedence claim for both flags; clarify loaded selected/merged config for check-readiness. Leave BUG-3757's default correction to that issue. No configure skill or generated mirrors need changes for this API-only extraction.
7. Run `python -m pytest scripts/tests/test_resolve_confidence_thresholds.py scripts/tests/test_check_readiness.py scripts/tests/test_next_action.py scripts/tests/test_config.py scripts/tests/test_issue_manager.py scripts/tests/test_ll_issues_next_obligation.py scripts/tests/test_run_record.py -q`, then the full `python -m pytest scripts/tests/` and normal lint/type checks for the implementation.

### Behavioral Regression Matrix

| Case | Required observation |
|------|----------------------|
| Base outcome 65 → local 75, and base 75 → local 65; issue 90/70 | Readiness thresholds follow local values; next-action flips between `NEEDS_REFINE <ID>` / exit 1 and `ALL_DONE` / exit 0. Cover analogous readiness raise/lower around a score of 80. |
| Base enabled false → local true with readiness 85 / score 80 | ll-auto returns `was_gated=True`, reason `below_readiness_threshold (80 < 85)`, and does not invoke Phase 1. |
| Base enabled true → local false or local enabled null, with score below readiness | Readiness status disables the gate; ll-auto reaches Phase 1. Check-readiness still compares both scores. |
| Local null leaf, whole gate, or commands ancestor | Removed threshold keys use `(40, 30)` caller defaults and enabled defaults false when removed. The stale base values are not recovered. One parametrized removal test is sufficient. |
| Local-only configuration; no configuration; partial gate | Local-only values are honored; absence/partial blocks use each caller's supplied default independently. |
| Root-only base; conflicting host/`.ll` bases with a `.ll/ll.local.md` override | Both readers use the loader-selected snapshot, with the local overlay applied. One host (Codex) covers the reader seam; exercise its host or state-dir trigger without rebuilding the loader's host matrix. |
| Explicit readiness/outcome overrides; next-action fallback arguments | Readiness explicit values beat local config, including zero; present config keys beat next-action flags, independently for each key. Compare at-threshold and one-below values. |
| Base/local file and host-env change after BRConfig load | Both readers continue using the supplied snapshot. Accessor-result mutation cannot change it either. |
| Downstream score 80 with base readiness 75 / local 85 | Next-obligation yields `SCORES:readiness_below` rather than `NONE`; the typed run-record outcome is `blocked` rather than `ready`, with its other prerequisites met. |

## Impact

- **Priority**: P2 — configured gates can be bypassed or applied at the wrong threshold, including local enabled overrides in ll-auto.
- **Effort**: Small to Medium.
- **Risk**: Medium — caller fallback and explicit override precedence require separate regression cases.
- **Breaking Change**: No API removal or CLI change; affected projects intentionally begin honoring their selected configuration.

## Steps to Reproduce

1. Create a temporary project with base `commands.confidence_gate` outcome 65 / enabled false. Add local Markdown frontmatter overriding outcome to 75 and enabled to true.
2. Create an issue with readiness 90 and outcome 70. Load BRConfig and call readiness_status: observe loaded 75 / true versus status 65 / false.
3. Ensure the issue is formatted, has a verify-issues Session Log entry and is below the refinement cap. Run next-action: observe ALL_DONE instead of NEEDS_REFINE.
4. Repeat with base 75 overridden to 65, or removed with local null. The status still uses base 75. Repeat with only root-level or host-selected threshold 80: status instead uses fallback 65.
5. Remove the whole gate or commands ancestor locally, or remove only enabled; the stale base values still reappear. With local-only outcome 75 / enabled true, BRConfig loads those values but readiness uses its fallbacks / false.
6. For the real ll-auto gate, use base readiness 75 / enabled false, local readiness 85 / enabled true, and score 80. `process_issue_inplace()` reaches Phase 1 instead of gating. Next-obligation with its earlier gates satisfied returns `NONE` instead of `SCORES:readiness_below`.
7. Load BRConfig with outcome 75, then rewrite its base to 65. Readiness/next-action use 65 despite the supplied config retaining 75. Changing local files or host selection after loading is another form of the same re-read defect.

## Root Cause

The shared helper extracted in ENH-3604 preserves correct per-key fallback semantics but still reads the original fixed file path. Typed dataclass defaults cannot represent absent keys, so the remedy is a presence-aware view of the loaded raw block, not another default literal or a replacement with the populated dataclass.

## Acceptance Criteria

- Both BRConfig-backed readers use the supplied loaded snapshot, honoring local-only values, leaf/block/ancestor removals and selected root/host config without any config re-read. Accessor mutation and post-load source/env changes cannot change that snapshot.
- Readiness explicit overrides beat config, including zero; next-action arguments remain per-key fallbacks. Null/missing keys use each caller's supplied defaults, including values other than 85/65. The legacy `threshold` alias and raw coercion policy remain unchanged.
- Real ll-auto tests prove local enabled/readiness overrides change the pre-Phase-1 gate without mocking readiness_status. Local false/removal bypasses that gate; low outcome alone remains nonblocking. Check-readiness remains enabled-independent.
- Next-obligation score tokens and typed run-record readiness outcomes honor local thresholds; existing waiver/missing-score/Program Design and next-action output/exit contracts pass.
- The legacy path helper keeps its exact signature and malformed/missing-file fallback. CLI/API text documents the separate precedence rules accurately. New affected-reader regressions fail before the implementation; targeted/full local suites and normal quality checks pass afterwards.

## Review Notes

Discovered while reviewing BUG-3757 on 2026-10-06, main at 77faacc66. Temporary-project probes reproduced threshold and enabled drift; a selector probe with format/verify prerequisites isolated next-action's incorrect ALL_DONE result. Opus via /ll:advise recommended a separate linked issue (confidence 0.85) to preserve distinct fallback semantics. No implementation edits made.

Pre-implementation review on 2026-10-06 inspected the reader code at `73d27391a` and confirmed the same call paths at `d74c5a6b2`. Ten temporary-project rows reproduced local raise/lower, null threshold/enabled/gate/commands, local-only, root, host and post-load base-edit drift, with noncanonical `(40, 30)` defaults. A real process_issue_inplace probe loaded local enabled true / readiness 85 / score 80 yet returned `was_gated=False` and invoked Phase 1 twice (its retry); a next-obligation probe returned `NONE` instead of `SCORES:readiness_below`. Only unrelated host effects/earlier selector probes were mocked. A real typed run-record probe with base readiness 75 / local 85 / score 80 and satisfied Program Design wrote `ready` instead of `blocked`. Malformed-base loading and standalone-helper fallback were also confirmed separately.

Opus via `/ll:advise --signal user_requested --host claude-code --model opus` recommended proceeding after these amendments (confidence 0.80). Adopted its pure-helper extraction, detached accessor, minimal behavioral tests and legacy-alias scope boundary. Its dissent favored retaining the optional mapping kwarg as a single entry point; rejected because it leaves a dummy path and an avoidable empty-versus-None source rule. Its concerns about new BRConfig loading and enabled source were checked against actual callers: no new config construction is needed, and ll-auto consumes `ReadinessStatus.enabled`. Those conditional suggestions do not change the existing signatures or error policy.

Review validation: the five original targeted suites passed **723 tests**, next-obligation passed **53 tests**, and run-record passed **108 tests / 1 skipped**: **884 passed / 1 skipped** overall. Issue format/design checks and diff whitespace checks passed. These establish the baseline; missing local-config regressions still need to be added during implementation. No implementation changes were made in this review.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | `docs/reference/API.md` | Shared helper and readiness-status public contracts |
| reference | `docs/reference/CLI.md` | Threshold flag precedence and readiness consumers |
| architecture | `docs/ARCHITECTURE.md` | Configuration layer and automation consumers |

## Status

**Open** | Created: 2026-10-06 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-10-06T18:16:35 - `471d3a7a-54d3-4495-af46-a12400a91738.jsonl`
