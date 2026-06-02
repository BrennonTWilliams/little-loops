---
id: ENH-1861
title: "Wave 2a Part 1 \u2014 Add `parse_tagged_json` Fragment and Convert 3 Integration\
  \ Loops"
type: ENH
priority: P3
captured_at: '2026-06-01T00:00:00Z'
completed_at: '2026-06-01T18:36:32Z'
discovered_date: 2026-06-01
parent: ENH-1854
relates_to:
- ENH-1854
- ENH-1775
- EPIC-1773
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1861: Wave 2a Part 1 — Add `parse_tagged_json` Fragment and Convert 3 Integration Loops

## Summary

Add a `parse_tagged_json` fragment to `scripts/little_loops/loops/lib/common.yaml`, then convert the 3 integration loops that duplicate this parsing logic to use the fragment. Includes fragment tests and loop validation.

## Parent Issue

Decomposed from ENH-1854: Wave 2a — Add `parse_tagged_json` and `ll_commit` Fragments

## Current Behavior

3 integration loops each contain a near-identical python3 heredoc that parses a tagged JSON line from LLM output:

- `adopt-third-party-api.yaml` — parses `ENUMERATE_JSON:` tag (lines 58–95)
- `integrate-sdk.yaml` — parses `ENUMERATE_JSON:` tag (lines 117–161)
- `assumption-firewall.yaml` — parses `ASSUMPTIONS_JSON:` tag (lines 53–83)

Each duplicates the python3 invocation, line-splitting, tag-matching, and JSON extraction.

## Expected Behavior

**`parse_tagged_json` fragment** in `scripts/little_loops/loops/lib/common.yaml`:

```yaml
parse_tagged_json:
  description: |
    Shell state that extracts a tagged JSON line from LLM output.
    State must supply: action (full extraction + normalization logic),
    capture, evaluate (output_json recommended), on_yes, on_no.
    Context: set context.json_tag (e.g. ENUMERATE_JSON) and
    context.capture_var (e.g. raw_enumeration) to document intent;
    the action must reference captured output directly
    (e.g. ${captured.raw_enumeration.output}) as nested interpolation
    is not supported by the current engine.
  action_type: shell
```

Insert after `with_throttle` (after line 83) and before `numeric_gate` (line 85).

> **Design note — no default `action:`**: The fragment provides only `action_type: shell`. All 3 callers override `action:` via deep-merge anyway (they carry per-loop normalization logic). A parameterized default `action:` using `${captured.${context.capture_var}.output}` is NOT viable because the FSM interpolation engine (`scripts/little_loops/fsm/interpolation.py:VARIABLE_PATTERN`) is single-pass and stops at the first `}` — nested `${...}` inside a variable path is treated as a malformed token and raises `InterpolationError`. Future callers wanting generic extraction should provide their own `action:` referencing the captured variable by its literal name.

Callers set `context.json_tag` (e.g., `ENUMERATE_JSON`, `ASSUMPTIONS_JSON`) and `context.capture_var` (e.g., `raw_enumeration`, `raw_extraction`) for documentation/readability, but the `action:` must use the literal captured variable name directly (e.g., `${captured.raw_enumeration.output}`). Fragment provides `action_type` only. All `evaluate:` and routing fields come from the caller.

## Codebase Research Findings

### Fragment Resolution Pipeline

`scripts/little_loops/fsm/fragments.py:resolve_fragments()`:
- `_deep_merge(frag_copy, state_dict)` — fragment is base, state fields override
- `action_type` and `action` at state level fully replace fragment's values
- `description:` is stripped from the fragment dict before merge (line 137) — never reaches the FSM engine

### Single-Pass Interpolation Constraint

`scripts/little_loops/fsm/interpolation.py:VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")` is applied once via `re.sub()` (line 201). Pattern uses `[^}]+` which stops at the first `}` — nested expressions like `${captured.${context.capture_var}.output}` are split into an invalid token `captured.${context.capture_var` and the remainder `.output}`, raising `InterpolationError`. **This means fragment actions cannot use nested variable interpolation.**

### Fragment Placement

`scripts/little_loops/loops/lib/common.yaml` currently defines 6 fragments in order: `shell_exit`, `retry_counter`, `llm_gate`, `with_rate_limit_handling`, `with_throttle`, `numeric_gate`. Insert `parse_tagged_json` after `with_throttle` (after line 83, before `numeric_gate` at line 85). `description:` field required by `test_all_common_yaml_fragments_have_description`.

### ⚠ Design Constraint: Integration Loop Normalization Logic

The 3 integration loop parse states contain per-loop business logic beyond tag extraction:

- `adopt-third-party-api.yaml:58-95` (`parse_enumeration`): computes `fallback_domain` via `urlparse(${context.input})`, caps `targets` to 7, emits `{targets, domain, count, rationale}`.
- `integrate-sdk.yaml:117-161` (`parse_enumeration`): caps `targets` to 7, extracts `branch` and `requires_credentials`, emits `{targets, count, branch, requires_credentials, rationale}`.
- `assumption-firewall.yaml:53-83` (`parse_assumptions`): uses `${captured.raw_extraction.output}` (not `raw_enumeration`), caps `targets` to 7, emits `{targets, rationale, count}`.

The fragment handles `action_type` injection only. Callers keep their existing `action:` fields wholesale (they override the fragment's absent action via deep-merge). The `evaluate:` / routing fields on each state remain unchanged.

### Confirmed: Test File Structure

- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — add 4 tests here following the `TestThrottleFragment` pattern (lines 670–733): presence, `action_type`, `description`, and a `resolve_from_real_common_yaml` integration test
- `scripts/tests/test_fsm_fragments.py:1068` (`test_all_common_yaml_fragments_have_description`) — asserts `description:` field present and non-empty on ALL common.yaml fragments
- `scripts/tests/test_builtin_loops.py:TestAssumptionFirewallLoop:4605` — does NOT assert on `parse_assumptions` action content; safe to change
- `scripts/tests/test_builtin_loops.py:TestAdoptThirdPartyApiLoop:4842` — does NOT assert on `parse_enumeration` action content; safe to change
- `scripts/tests/test_builtin_loops.py:TestIntegrateSdkLoop:4887` — does NOT assert on `parse_enumeration` action content; safe to change

### Test Pattern (from TestThrottleFragment at line 670)

Follow the 4-test shape:
```python
def test_parse_tagged_json_defined_in_common_yaml(self) -> None:
    data = self._load_common_yaml()
    assert "parse_tagged_json" in data["fragments"], "parse_tagged_json fragment missing from lib/common.yaml"

def test_parse_tagged_json_has_correct_action_type(self) -> None:
    data = self._load_common_yaml()
    assert data["fragments"]["parse_tagged_json"]["action_type"] == "shell"

def test_parse_tagged_json_has_description(self) -> None:
    data = self._load_common_yaml()
    frag = data["fragments"]["parse_tagged_json"]
    assert frag.get("description", "").strip(), "parse_tagged_json fragment must have a non-empty description"

def test_parse_tagged_json_resolves_from_real_common_yaml(self) -> None:
    """Full resolve_fragments integration against the real lib/common.yaml."""
    loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
    raw = {
        "name": "test",
        "initial": "parse",
        "import": ["lib/common.yaml"],
        "states": {
            "parse": {
                "fragment": "parse_tagged_json",
                "action": "echo '{\"count\": 1}'",
                "capture": "parsed",
                "evaluate": {"type": "output_json", "path": ".count", "operator": "gt", "target": 0},
                "on_yes": "done",
                "on_no": "done",
            },
            "done": {"terminal": True},
        },
    }
    result = resolve_fragments(raw, loops_dir)
    state = result["states"]["parse"]
    assert state["action_type"] == "shell"
    assert "fragment" not in state
```

### `skills/create-loop/reference.md` — No Existing Fragment Catalog

The file contains only state-structure reference tables (Fix Until Clean, Drive a Metric, Maintain Constraints, Run a Sequence, Harness variants). There is no `fragment:`, `shell_exit`, `llm_gate`, or fragment section anywhere. Step 6 must CREATE a new `## Fragment Catalog` section, not add a row to an existing table.

### `docs/guides/LOOPS_GUIDE.md` — Fragment Table Position

The existing fragment table is at lines 3156–3162 under `#### lib/common.yaml — type-pattern fragments`. The `with_throttle` fragment is in common.yaml but also missing from this table (a parallel gap). Add `parse_tagged_json` as a new row with columns: Fragment, Description, Provides, Caller must supply.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/lib/common.yaml` — add `parse_tagged_json` fragment after `with_throttle` (after line 83)
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — add `fragment: parse_tagged_json` to `parse_enumeration` state (lines 58–95); keep existing `action:`, `capture:`, `evaluate:`, routing
- `scripts/little_loops/loops/integrate-sdk.yaml` — add `fragment: parse_tagged_json` to `parse_enumeration` state (lines 117–161); keep existing `action:`, `capture:`, `evaluate:`, routing
- `scripts/little_loops/loops/assumption-firewall.yaml` — add `fragment: parse_tagged_json` to `parse_assumptions` state (lines 53–83); keep existing `action:`, `capture:`, `evaluate:`, routing

### Tests

- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — add 4 tests (presence, action_type, description, resolve integration)
- `scripts/tests/test_fsm_fragments.py:1068` — `test_all_common_yaml_fragments_have_description` will enforce `description:` field
- `scripts/tests/test_builtin_loops.py:TestAssumptionFirewallLoop:4605` — safe to change (no action assertions)
- `scripts/tests/test_builtin_loops.py:TestAdoptThirdPartyApiLoop:4842` — safe to change (no action assertions)
- `scripts/tests/test_builtin_loops.py:TestIntegrateSdkLoop:4887` — safe to change (no action assertions)

### Documentation

- `docs/guides/LOOPS_GUIDE.md:3156` — add `parse_tagged_json` row to existing fragment table
- `skills/create-loop/reference.md` — CREATE new `## Fragment Catalog` section (no existing section)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md:162` — `### Fragment Libraries` section lists `lib/common.yaml` fragments by name in a parenthetical; add `parse_tagged_json` to this list [Agent 2 finding]
- `CHANGELOG.md` — add entry for new fragment and 3-loop conversion under the current concrete `## [X.Y.Z] - DATE` section (do NOT use `[Unreleased]`) [Agent 2 finding]

### Configuration

No configuration changes required.

## Implementation Steps

1. **Add `parse_tagged_json` fragment** to `scripts/little_loops/loops/lib/common.yaml` — insert after `with_throttle` (after line 83). Provide `action_type: shell` and a `description:` that documents the nested-interpolation constraint. Do NOT include a default `action:` (see design note above).

2. **Convert 3 integration loops** — For each parse state, add `fragment: parse_tagged_json` as a peer key alongside the existing `action:`, `capture:`, `evaluate:`, and routing fields. Keep all existing fields unchanged. The existing `action:` overrides the fragment's absent action via deep-merge; `action_type: shell` is injected by the fragment.
   - `adopt-third-party-api.yaml`: add `fragment: parse_tagged_json` to `parse_enumeration` (line 58)
   - `integrate-sdk.yaml`: add `fragment: parse_tagged_json` to `parse_enumeration` (line 117)
   - `assumption-firewall.yaml`: add `fragment: parse_tagged_json` to `parse_assumptions` (line 53)

3. **Add fragment tests** — In `TestCommonYamlNewFragments` (line 523 of `test_fsm_fragments.py`), add 4 methods following the `TestThrottleFragment` pattern (lines 670–733): `test_parse_tagged_json_defined_in_common_yaml`, `test_parse_tagged_json_has_correct_action_type`, `test_parse_tagged_json_has_description`, `test_parse_tagged_json_resolves_from_real_common_yaml`.

4. **Validate 3 modified loops** — `ll-loop validate` on `adopt-third-party-api.yaml`, `integrate-sdk.yaml`, `assumption-firewall.yaml`. Fix any ERROR-severity issues.

5. **Run regression** — `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`. Verify `test_all_common_yaml_fragments_have_description` passes and all 3 integration loop test classes are unaffected.

6. **Update documentation**:
   - `docs/guides/LOOPS_GUIDE.md:3156` — add `parse_tagged_json` row to the existing `lib/common.yaml` fragment table
   - `skills/create-loop/reference.md` — CREATE a new `## Fragment Catalog` section (no existing section exists) listing the common.yaml fragments with name, description, and caller-required fields

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Add `import: ["lib/common.yaml"]` to each of the 3 integration loops** — All 3 loops (`adopt-third-party-api.yaml`, `integrate-sdk.yaml`, `assumption-firewall.yaml`) currently do NOT import `lib/common.yaml`. Without this import, `resolve_fragments()` raises `ValueError: Unknown fragment 'parse_tagged_json'` and `TestBuiltinLoopFiles:test_all_validate_as_valid_fsm` fails. Add this import declaration to each loop's header as part of Step 2 — it was omitted from the implementation steps.

8. **Update `scripts/little_loops/loops/README.md:162`** — add `parse_tagged_json` to the parenthetical fragment name list in the `### Fragment Libraries` section for `lib/common.yaml`.

9. **Update `CHANGELOG.md`** — add entry for the new fragment and 3-loop conversion under the current concrete `## [X.Y.Z] - DATE` section (not `[Unreleased]`).

## Success Metrics

- `parse_tagged_json` fragment eliminates duplicate `action_type: shell` declarations across 3 parse states
- All 3 modified loops pass `ll-loop validate`
- `test_all_common_yaml_fragments_have_description` passes (`description:` field present)
- 4 new fragment tests pass; test suite passes with no regressions in integration loop test classes

## Impact

- **Priority**: P3
- **Effort**: Small — mechanical substitution across 3 enumerated files, 4 new tests
- **Risk**: Low — fragment resolution is well-tested; integration loop test classes don't assert on action content; nested interpolation constraint is pre-empted by omitting the default `action:`

## Scope Boundaries

- **In scope**: Adding the `parse_tagged_json` fragment to `lib/common.yaml` and converting exactly the 3 enumerated integration loops (`adopt-third-party-api.yaml`, `integrate-sdk.yaml`, `assumption-firewall.yaml`)
- **Out of scope**: The `ll_commit` fragment — that is ENH-1862 (Wave 2a Part 2)
- **Out of scope**: Modifying the FSM interpolation engine or removing the single-pass constraint
- **Out of scope**: Adding a default `action:` to the fragment (the nested interpolation limitation prevents a generic default)
- **Out of scope**: Converting loops beyond the 3 enumerated integration loops
- **Out of scope**: Changes to any existing fragment behavior or interface

## Labels

`loops`, `fragments`, `refactoring`, `enhancement`

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-01T18:32:55 - `ea6d0bf0-9645-4b35-9737-42cfcda25d44.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `08b37632-8612-4103-9d09-928ebcf3d023.jsonl`
- `/ll:wire-issue` - 2026-06-01T18:27:50 - `f047901e-179f-434b-9f07-6133fafddcb9.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:20:19 - `308a7bec-74a4-4a3c-bed1-559a8fc73ada.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `2cacc3f7-f908-4e86-8ef8-b96c1b43a157.jsonl`
- `/ll:refine-issue` - 2026-06-01T00:00:00Z - `pending`
