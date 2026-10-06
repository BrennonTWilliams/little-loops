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

Readiness checks and next-action re-read a fixed `.ll/ll-config.json` path instead of consuming the merged configuration already loaded by `BRConfig`. Local threshold/enabled overrides, local null removal, root-level config and host-selected config are ignored. Honor those sources while preserving the distinct explicit-override and absent-key caller-fallback contracts. This is a separate follow-up from BUG-3757's set-flags/default correction, with no blocking dependency in either direction.

## Current Behavior

- `scripts/little_loops/cli/issues/check_readiness.py`, `resolve_confidence_thresholds()`, reads JSON from its path argument and applies caller defaults per missing key. `readiness_status()` supplies a fixed `.ll/ll-config.json` path and layers explicit overrides afterwards.
- `scripts/little_loops/cli/issues/next_action.py`, `cmd_next_action()`, supplies the same fixed path and uses argparse values as missing-key fallbacks. A present config key beats these arguments.
- `BRConfig` already resolves supported config locations and deep-merges local overrides, but these readers bypass that loaded result. A local enabled override is also missed in `ReadinessStatus.enabled`, which the ll-auto readiness gate consumes.
- Base outcome 65 / enabled false plus local outcome 75 / enabled true yields loaded 75 / true but readiness status 65 / false. A verified, formatted issue at readiness 90 / outcome 70 can consequently produce ALL_DONE from next-action. Removing base outcome 75 with local null leaves readiness using 75 although the loaded key was removed.
- ENH-3604 intentionally preserved absent-key caller defaults. Switching directly to populated `ConfidenceGateConfig` values would erase key absence and break that contract; preserve the decision rather than undoing it.

## Expected Behavior

- Both readers use the selected, merged raw configuration, retaining key presence after null removal.
- `readiness_status`: explicit override > present merged config key > caller default. Enabled comes from the merged key, defaulting to false. Check-readiness continues to ignore enabled; ll-auto continues to honor it.
- `cmd_next_action`: present merged config key > argparse fallback, independently for each threshold. Its arguments remain fallbacks rather than unconditional overrides.
- Local null restores the caller's supplied default for that key, which may differ from 85/65. Partial blocks preserve each caller's other fallback. Root/host precedence remains the config loader's responsibility.
- Existing missing-score, waiver, issue-selection, output-token and exit-code behavior remains intact. Malformed base JSON still fails BRConfig loading; the standalone path helper retains its existing read/parse-error fallback.

## Proposed Solution

Expose a narrow defensive copy of the loaded raw confidence-gate block through BRConfig. Add an optional mapping input to the existing helper and pass it from both BRConfig-backed callers. Keep the public path-based helper behavior for existing callers/tests, including standalone malformed/missing-file fallbacks. Do not add FSM imports to this hot CLI path or re-read configuration from the BRConfig-backed paths.

## Integration Map

### Files to Modify

- `scripts/little_loops/config/core.py` — proposed loaded raw-block accessor.
- `scripts/little_loops/cli/issues/check_readiness.py` — mapping-aware resolution and readiness_status caller.
- `scripts/little_loops/cli/issues/next_action.py` — mapping input, existing fallback precedence.
- `scripts/tests/test_resolve_confidence_thresholds.py`, `scripts/tests/test_check_readiness.py`, `scripts/tests/test_next_action.py`, `scripts/tests/test_config.py`, `scripts/tests/test_issue_manager.py` — presence, locations, precedence and actual gate behavior.
- `docs/reference/API.md` — shared helper signature and precedence.

### Dependent Files

- `scripts/little_loops/issue_manager.py` — consumes readiness_status and its enabled field; verify behavior without changing the readiness-only gate policy.
- `scripts/little_loops/fsm/context_seed.py` — already consumes loaded typed defaults; leave its context precedence intact and avoid importing it into the helper.
- `scripts/little_loops/loops/autodev.yaml` and other explicit CLI-threshold callers — preserve explicit override behavior; no loop rewrite planned.
- BUG-3757 is related and independently implementable. ENH-3604 and BUG-3123 are completed precedents, not blockers.

## Program Design

### Types

- `gate_config: dict[str, Any]` — proposed raw gate view retaining omitted keys; local null has already removed keys during configuration merge.
- Existing result: `tuple[int, int, bool]` for readiness, outcome and enabled.

### Signatures

- `BRConfig.confidence_gate_raw(self) -> dict[str, Any]` — proposed accessor in `scripts/little_loops/config/core.py`; copy the loaded raw commands.confidence_gate block without dataclass defaults.
- `resolve_confidence_thresholds(config_path: Path, defaults: tuple[int, int], *, gate_config: Mapping[str, Any] | None = None) -> tuple[int, int, bool]` — proposed extension; a supplied mapping, including an empty mapping, takes precedence over file reading; None retains the legacy path reader.
- Existing `readiness_status()` and `cmd_next_action()` keep their signatures and pass the new mapping. Explicit overrides remain layered only in readiness_status.

### Call Path

`BRConfig` → proposed `confidence_gate_raw()` → `readiness_status()` / `cmd_next_action()` → `resolve_confidence_thresholds(gate_config=...)` → existing score comparisons / consumers. Legacy path-only calls continue through the current file-reader branch.

## Implementation Steps

1. Add the defensive raw-block accessor and optional mapping input, retaining empty-versus-None distinction. Keep key-by-key fallback and existing error semantics; do not change threshold type validation policy.
2. Wire both callers to the loaded mapping and update source docstrings/API documentation to explain presence-aware precedence. Preserve existing helper positional arguments and no-FSM-import constraints.
3. Add real-config cases for both directions of local threshold override, local enabled override, null removal with noncanonical caller defaults, partial blocks, no configuration, root config and host config precedence. Verify check-readiness explicit overrides still win, next-action fallback arguments still lose to present keys, and a post-load file edit does not affect the loaded mapping.
4. Cover the actual ll-auto gate honoring local enabled/readiness overrides, and preserve check-readiness's enabled-independent behavior, outcome waivers, missing-score handling and selector output/exit codes. Keep existing standalone path-helper malformed/absent-file cases.
5. Run the helper, check-readiness, next-action, config and issue-manager test suites, then `python -m pytest scripts/tests/`.

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

## Root Cause

The shared helper extracted in ENH-3604 preserves correct per-key fallback semantics but still reads the original fixed file path. Typed dataclass defaults cannot represent absent keys, so the remedy is a presence-aware view of the loaded raw block, not another default literal or a replacement with the populated dataclass.

## Acceptance Criteria

- Both BRConfig-backed readers honor merged local values, removed keys and resolved root/host config without independently re-reading the base file.
- Readiness explicit overrides beat config; next-action arguments remain fallbacks. Null/missing keys use each caller's supplied defaults, including values other than 85/65.
- Local enabled/readiness overrides reach the ll-auto gate; check-readiness remains enabled-independent. Existing waiver/missing-score and next-action output/exit contracts pass.
- Existing positional/path helper calls and their malformed/missing-file fallback tests remain compatible. Relevant and full local test suites pass.

## Review Notes

Discovered while reviewing BUG-3757 on 2026-10-06, main at 77faacc66. Temporary-project probes reproduced threshold and enabled drift; a selector probe with format/verify prerequisites isolated next-action's incorrect ALL_DONE result. Opus via /ll:advise recommended a separate linked issue (confidence 0.85) to preserve distinct fallback semantics. No implementation edits made.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | `docs/reference/API.md` | Shared helper and readiness-status public contracts |
| architecture | `docs/ARCHITECTURE.md` | Configuration layer and automation consumers |

## Status

**Open** | Created: 2026-10-06 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-10-06T18:16:35 - `471d3a7a-54d3-4495-af46-a12400a91738.jsonl`
