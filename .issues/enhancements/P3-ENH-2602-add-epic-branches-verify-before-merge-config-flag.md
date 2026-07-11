---
id: ENH-2602
type: enhancement
status: done
priority: P3
parent: ENH-2600
completed_at: '2026-07-11T15:11:53Z'
relates_to:
- ENH-2603
confidence_score: 100
outcome_confidence: 93
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2602: Add `epic_branches.verify_before_merge` config flag

## Summary

Add a new `verify_before_merge` boolean field to `EpicBranchesConfig`, wired
through both dataclass representations, the config bridge, and the JSON
schema. The flag is inert on its own (nothing reads it yet — that lands in
[[ENH-2603]]) but must be fully plumbed and tested so ENH-2603 can build on a
working, validated config surface.

## Parent Issue

Decomposed from ENH-2600: Verify epic-branch tests/lint before merge-to-base
or PR-open

## Motivation

ENH-2600 proposes gating EPIC-branch merge/PR-open on a new
`test_cmd`/`lint_cmd` verify step, controlled by a new config flag. That flag
must exist in both `EpicBranchesConfig` dataclasses, the bridge between them,
and the schema (`additionalProperties: false` makes the schema entry a hard
validation gate, not just documentation) before the verify-gate logic in
ENH-2603 can read it.

## Current Behavior

`EpicBranchesConfig` has four fields (`enabled`, `prefix`,
`merge_to_base_on_complete`, `open_pr`); there is no way to request a
test/lint verify step before an EPIC branch is merged to base or a PR is
opened for it. Setting `parallel.epic_branches.verify_before_merge` in
`.ll/ll-config.json` today is silently rejected — `additionalProperties:
false` on the schema's `epic_branches` block makes any unrecognized key a
hard validation failure, not a no-op.

## Expected Behavior

`verify_before_merge: bool = False` exists on both `EpicBranchesConfig`
dataclasses, round-trips through `to_dict`/`from_dict` on both sides, is
threaded through the `_build_parallel_epic_branches` bridge, and is declared
in the JSON schema so config files can set it without validation errors. The
flag has no behavioral effect yet (nothing reads it) — that lands in
[[ENH-2603]] — but the full plumbing is tested end-to-end so ENH-2603 has a
working config surface to build on.

## Scope Boundaries

Out of scope for this issue: any code that actually *reads*
`verify_before_merge` and gates the merge/PR-open step on a `test_cmd`/
`lint_cmd` run — that gate logic, its failure surfacing, and CLI/TUI
messaging are ENH-2603's responsibility. This issue is config plumbing only.

## Proposed Solution

Add `verify_before_merge: bool = False` (default `False` — matches the
"additive gate" risk posture ENH-2600 settled on, since a `True` default
would break existing `TestEpicCompletionMerge` tests that don't mock a
`test_cmd`/`lint_cmd` subprocess call) to:

1. `scripts/little_loops/parallel/types.py` — `EpicBranchesConfig` (311-334),
   the runtime dataclass.
2. `scripts/little_loops/config/automation.py` — `EpicBranchesConfig`
   duplicate (40-59), the config-file-facing dataclass.
3. `scripts/little_loops/config/core.py` — `_build_parallel_epic_branches`
   (~513-534) explicit field-by-field bridge between the two dataclasses
   above; add `verify_before_merge=src.verify_before_merge` or the flag is
   silently dropped at runtime.
4. `scripts/little_loops/config-schema.json` — `epic_branches` schema block
   (412-438), a new property alongside the existing four.

## Implementation Steps

1. Add the field to both `EpicBranchesConfig` dataclasses (default `False`).
2. Add `verify_before_merge=src.verify_before_merge` to
   `_build_parallel_epic_branches` in `config/core.py`.
3. Add the schema property to `config-schema.json` `epic_branches` block.
4. Update tests to cover the new field end-to-end through the config layers.
5. Update config-surface documentation for the new field.

## Files to Modify

- `scripts/little_loops/parallel/types.py` — `EpicBranchesConfig` (311-334)
- `scripts/little_loops/config/automation.py` — `EpicBranchesConfig` (40-59)
- `scripts/little_loops/config/core.py` — `_build_parallel_epic_branches`
  (~513-534)
- `scripts/little_loops/config-schema.json` — `epic_branches` block (412-438)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The four call sites above are the declaration/bridge/schema layer, but three
additional **serialization** touch points manually enumerate
`EpicBranchesConfig`'s fields and will silently drop `verify_before_merge`
if not also updated:

- `scripts/little_loops/parallel/types.py:510-514` — `ParallelConfig.to_dict()`
  builds the `"epic_branches"` dict key-by-key (not `dataclasses.asdict`);
  add `"verify_before_merge": self.epic_branches.verify_before_merge,`.
  (`from_dict` at line 562 uses `EpicBranchesConfig(**data.get(...))`
  kwargs-spread, so it needs no edit.)
- `scripts/little_loops/config/automation.py:53-61` — the automation-side
  `EpicBranchesConfig.from_dict()` classmethod hand-writes
  `data.get("field", default)` per field (no kwargs-spread here); add
  `verify_before_merge=data.get("verify_before_merge", False),`.
- `scripts/little_loops/config/core.py:604-609` — `BRConfig.to_dict()` has a
  **third** independent field-by-field `"epic_branches"` dict build (distinct
  from `_build_parallel_epic_branches`); add
  `"verify_before_merge": self._parallel.epic_branches.verify_before_merge,`.

Precedent: `open_pr` is the most recently-added field in this exact config
and was threaded through all seven of these sites (2 dataclasses, 1 bridge,
1 schema, 2 manual `to_dict` dict builds, 1 manual `from_dict`), confirming
this is the full site list, not partial.

### Tests

- `scripts/tests/test_config_schema.py` —
  `test_parallel_epic_branches_in_schema` (~744-770): extend with a
  `verify_before_merge` type/default assertion.
- `scripts/tests/test_config.py` — `test_epic_branches_defaults` (~419-425),
  `test_epic_branches_from_dict` (~427-441),
  `test_epic_branches_partial_dict_uses_defaults` (~443-449), the
  dict-roundtrip assertion (~811-815), and the `create_parallel_config`
  override tests (~970-1021): add `verify_before_merge` coverage to each.
- `scripts/tests/test_parallel_types.py` — the defaults test (~767-770) and
  dict-conversion roundtrip test (~1043-1060): add `verify_before_merge`
  coverage.

_Wiring pass added by `/ll:wire-issue`:_
- Three sites hand-enumerate **every** `EpicBranchesConfig` field in a single
  constructor/dict literal; these won't error without the new field (dataclass
  fields default) but will silently stop being "full-field" fixtures unless
  updated:
  - `scripts/tests/test_parallel_types.py:1043-1048` —
    `EpicBranchesConfig(enabled=..., prefix=..., merge_to_base_on_complete=...,
    open_pr=...)` inside the `to_dict()`/`from_dict()` round-trip test; add
    `verify_before_merge=...` and the matching round-trip assertion at line
    ~1060.
  - `scripts/tests/test_config.py:1007-1012` — full `epic_branches={...}`
    dict literal in `test_create_parallel_config_epic_branches_none_falls_back_to_config`.
  - `scripts/tests/test_config.py:429-436` —
    `test_epic_branches_from_dict`'s `data["epic_branches"]` dict; its
    docstring says "parses all 4 sub-keys" and needs updating to "5 sub-keys."
- `test_parallel_epic_branches_in_schema` (~744-770) asserts each schema
  property individually (no exhaustive `set(...)` check), so adding
  `verify_before_merge` to the schema without extending this test won't fail
  CI but will leave the new property unverified — extend it per the
  `open_pr` assertion pair (`["type"] == "boolean"`, `["default"] is False`).

### Documentation

- `docs/reference/API.md` — `EpicBranchesConfig` dataclass code block
  (~3299-3319): add the fifth field with its default-value comment.
- `docs/reference/CONFIGURATION.md` — config-reference table (~364-367): add
  a row for `epic_branches.verify_before_merge`.
- `skills/configure/show-output.md` (~54-57): add a
  `epic_branches.verify_before_merge: {{...}} (default: false)` line.
- `skills/configure/areas.md`: check for a settings-area enumeration that
  needs the new field added alongside the existing four.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/SPRINT_GUIDE.md` (~323-328) — "Per-EPIC Integration Branch"
  section has a literal `| Config key | Default | Effect |` table enumerating
  `enabled`, `prefix`, `merge_to_base_on_complete`, `open_pr` (this is the
  same enumeration `CONFIGURATION.md` has, already in scope above) — add a
  `verify_before_merge` row; since the flag is inert until ENH-2603, note
  "no effect yet — see ENH-2603" in the Effect column.
- `docs/development/MERGE-COORDINATOR.md` (~146-158, "EPIC-Aware Merge
  Path") — step 3 of the routing logic names `merge_to_base_on_complete`
  and `open_pr` as the precedent gating fields for the merge/PR step. No
  edit required by *this* issue (the flag has no routing effect yet), but
  ENH-2603 should add `verify_before_merge` to this same step once it wires
  the actual gate — flagged here so it isn't missed.

## Impact

- **Priority**: P3 — prerequisite plumbing for ENH-2603, not independently
  urgent.
- **Effort**: Small — mechanical field addition across four already-parallel
  representations (two dataclasses, one bridge, one schema block), following
  an existing exhaustive per-field test pattern.
- **Risk**: Low — the flag is inert until ENH-2603 reads it; default `False`
  means no behavior change on its own.

## Resolution

Added `verify_before_merge: bool = False` to both `EpicBranchesConfig`
dataclasses (`parallel/types.py`, `config/automation.py`), threaded it through
`_build_parallel_epic_branches` in `config/core.py`, declared it in
`config-schema.json`'s `epic_branches` block, and updated all three manual
serialization sites (`ParallelConfig.to_dict`, `automation.EpicBranchesConfig.from_dict`,
`BRConfig.to_dict`) plus the exhaustive per-field test fixtures in
`test_config.py`, `test_config_schema.py`, and `test_parallel_types.py`.
Documented in `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`,
`docs/guides/SPRINT_GUIDE.md`, and `skills/configure/show-output.md`. The flag
is inert — no behavior change — until ENH-2603 reads it.

## Session Log
- `/ll:manage-issue` - 2026-07-11T15:11:07 - `2c94229a-c23f-4426-9111-5c8f04e4dcf1.jsonl`
- `/ll:ready-issue` - 2026-07-11T15:04:04 - `e0bf89ca-4b80-4a16-b3ef-934e7b0d1d70.jsonl`
- `/ll:wire-issue` - 2026-07-11T15:00:19 - `fc00f6a1-8185-441f-9ad1-710bb4da19fa.jsonl`
- `/ll:refine-issue` - 2026-07-11T14:53:46 - `bdc27b85-6ed4-4ccb-898e-ff59122f9de5.jsonl`
- `/ll:issue-size-review` - 2026-07-11 - `2385c5ce-bdf9-4918-95d8-8118da444ec1.jsonl`

---

## Status

- [x] Complete
