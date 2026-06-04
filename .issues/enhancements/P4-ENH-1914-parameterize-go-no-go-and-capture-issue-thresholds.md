---
id: ENH-1914
title: Parameterize ENH-1888's hardcoded go-no-go / capture-issue thresholds
type: ENH
priority: P4
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T21:38:03Z'
completed_at: '2026-06-04T02:27:25Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1913
- ENH-1888
decision_needed: false
labels:
- history-db
- configurability
confidence_score: 100
outcome_confidence: 94
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1914: Parameterize ENH-1888's hardcoded thresholds

## Summary

ENH-1888 (done) bakes in two magic numbers with no config exposure: a `-0.2`
correction-confidence penalty in `go-no-go` and a `>70%` (0.7) duplicate-overlap
threshold in `capture-issue`. Expose both as `history.*` keys read inside the
respective Python paths and skill prose, so they become user-tunable like the rest of the
read/consume surface.

## Current Behavior

The go-no-go skill applies a hardcoded `-0.2` correction-confidence penalty in LLM prose
(`skills/go-no-go/SKILL.md:145`) and the capture-issue skill uses a hardcoded `0.7`
duplicate-overlap threshold in both LLM prose (`skills/capture-issue/SKILL.md:216`) and
Python (`scripts/little_loops/issue_discovery/search.py:261`). Neither constant is config-exposed.

## Expected Behavior

Both thresholds are read from `ll-config.json` via `BRConfig`, falling back to their current
defaults (`-0.2` and `0.7`) when absent. Skill prose uses `{{config.*}}` template variables
(resolved at expansion time by `skill_expander.py`). The Python path reads
`config.history.capture_issue.dup_overlap_threshold` directly. Users can tune them
per-project without code changes.

## Motivation

These thresholds directly affect agent decisions (whether go/no-go flags a recent
correction; whether capture-issue warns about a near-duplicate) but cannot be
tuned per project. They are the last hardcoded read-side consumers from the
EPIC-1707 audit. Parameterizing them completes the "consistent, user-tunable
`history.*`" goal for the consumer surface.

## Scope Boundaries

- **In scope**: Wiring `{{config.*}}` template variables into skill prose for go-no-go
  and capture-issue; replacing `0.7` literal in `search.py:261` with the BRConfig read;
  adding test assertions to cover both config paths.
- **Out of scope**: Adding schema keys to `config-schema.json` (owned by ENH-1913 — already
  done); UI or output changes to either skill; changing the default threshold values.

## API/Interface

- `history.go_no_go.correction_penalty` — float, default `-0.2`
- `history.capture_issue.dup_overlap_threshold` — float, default `0.7`

Both are already declared in the `history` schema by ENH-1913 and serialized by
`BRConfig.to_dict()` (confirmed at `core.py:2800-2801`), so `resolve_variable()` resolves
both template variable paths correctly. No `config-schema.json` edit needed.

## Implementation Steps

1. **`scripts/little_loops/issue_discovery/search.py:261`** — in `find_existing_issue()`,
   replace:
   ```python
   if overlap > 0.7 and overlap > best_pass2_score:
   ```
   with:
   ```python
   if overlap > config.history.capture_issue.dup_overlap_threshold and overlap > best_pass2_score:
   ```
   No signature change — `config: BRConfig` is already the first parameter;
   `config.history.capture_issue.dup_overlap_threshold` resolves to `0.7` by default.

2. **`skills/go-no-go/SKILL.md:145`** — replace the literal `-0.2` in the sentence:
   > "Each matched correction is a -0.2 signal on the GO/NO-GO verdict confidence."

   with the template variable:
   > "Each matched correction is a `{{config.history.go_no_go.correction_penalty}}` (default -0.2) signal on the GO/NO-GO verdict confidence."

   The `{{config.*}}` syntax is resolved by `scripts/little_loops/skill_expander.py:_substitute_config()`
   at expansion time. Follows the `review-epic` pattern at `skills/review-epic/SKILL.md` (Step 1 + Step 9).

3. **`skills/capture-issue/SKILL.md:216`** — replace the `>70%` prose literal in the
   history-DB near-duplicate search section with:
   > "`>{{config.history.capture_issue.dup_overlap_threshold}}` (default 0.7) title word overlap"

   Append `(default 0.7)` inline, consistent with the `review-epic` fallback note pattern
   and the existing `{{config.issues.duplicate_detection.*}}` usage at lines 191–193.

4. **`scripts/tests/test_issue_discovery.py:361`** (`TestFindExistingIssue`): Add
   `test_find_existing_issue_configurable_dup_threshold` — write a config fixture with
   `history.capture_issue.dup_overlap_threshold: 0.9`, confirm a 0.75-overlap title match
   is rejected; then use threshold 0.6, confirm the same 0.75-overlap match is accepted.
   Construct `BRConfig` from the fixture `temp_project_dir` with the relevant
   `ll-config.json` content written before constructing the config object.

5. **`scripts/tests/test_config.py:2760`** (`TestBRConfigHistoryIntegration.test_history_defaults_on_absent`):
   Add the two missing assertions at the end of the existing method:
   ```python
   assert config.history.go_no_go.correction_penalty == -0.2
   assert config.history.capture_issue.dup_overlap_threshold == 0.7
   ```

6. **`scripts/tests/test_config.py:2767`** (`TestBRConfigHistoryIntegration.test_history_loads_from_config`):
   Extend the `sample_config["history"]` dict to include the sub-fields, then assert
   they propagate:
   ```python
   sample_config["history"]["go_no_go"] = {"correction_penalty": -0.5}
   sample_config["history"]["capture_issue"] = {"dup_overlap_threshold": 0.9}
   ```
   Then after constructing `BRConfig`:
   ```python
   assert config.history.go_no_go.correction_penalty == -0.5
   assert config.history.capture_issue.dup_overlap_threshold == 0.9
   ```
   Note: `test_history_to_dict_round_trip` (line 2783) already asserts the defaults via
   `to_dict()` — these new assertions test the override path.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Do not drop `(default -0.2)` from Step 2's prose.** The literal string `-0.2` must remain
   somewhere in `skills/go-no-go/SKILL.md:145` (inside the `(default -0.2)` suffix) or
   `TestGoNoGoHistoryContextInjection.test_correction_signal_documented` (`test_go_no_go_skill.py:28`)
   will fail. The inline suffix is load-bearing, not stylistic.
8. (Optional) **`scripts/little_loops/issue_discovery/search.py:185`** — Update the `find_existing_issue`
   docstring from `>70% = likely duplicate` to reference the configurable threshold, e.g.
   `> dup_overlap_threshold (default 0.7) = likely duplicate`. No runtime effect — stale prose only.

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md:145` — LLM prose where `-0.2` penalty is stated; replace with
  `{{config.history.go_no_go.correction_penalty}}` template variable
- `skills/capture-issue/SKILL.md:216` — LLM prose where `>70%` threshold is stated; replace
  with `{{config.history.capture_issue.dup_overlap_threshold}}` template variable
- `scripts/little_loops/issue_discovery/search.py:261` — Python `if overlap > 0.7` in
  `find_existing_issue()` Pass 2 title-similarity guard; replace with
  `config.history.capture_issue.dup_overlap_threshold`

### Template Variable Resolution
- `scripts/little_loops/skill_expander.py:_substitute_config()` — resolves `{{config.*}}`
  placeholders via `BRConfig.resolve_variable()`; walks `BRConfig.to_dict()` which already
  includes `history.go_no_go.correction_penalty` and `history.capture_issue.dup_overlap_threshold`
  at `core.py:2800-2801`

### Config Infrastructure (ENH-1913 — already complete, no changes needed)
- `scripts/little_loops/config/features.py:688` — `GoNoGoConfig` dataclass, field
  `correction_penalty: float = -0.2`, `from_dict` with fallback
- `scripts/little_loops/config/features.py:702` — `CaptureIssueConfig` dataclass, field
  `dup_overlap_threshold: float = 0.7`, `from_dict` with fallback
- `scripts/little_loops/config/features.py:716` — `HistoryConfig` includes both via
  `field(default_factory=...)` at lines 733-734
- `scripts/little_loops/config/core.py:227` — `BRConfig._parse_config()` wires
  `HistoryConfig.from_dict(self._raw_config.get("history", {}))`
- `scripts/little_loops/config/core.py:320` — `BRConfig.history` property

### Tests to Modify/Add
- `scripts/tests/test_issue_discovery.py:361` — `TestFindExistingIssue`: add
  `test_find_existing_issue_configurable_dup_threshold`
- `scripts/tests/test_config.py:2760` — `TestBRConfigHistoryIntegration.test_history_defaults_on_absent`:
  add two assertions for `go_no_go.correction_penalty` and `capture_issue.dup_overlap_threshold`
- `scripts/tests/test_config.py:2767` — `TestBRConfigHistoryIntegration.test_history_loads_from_config`:
  add `go_no_go` and `capture_issue` override assertions

### Dependent Tests (coupling guard — no edits needed if Step 2 is followed exactly)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_go_no_go_skill.py:26` — `TestGoNoGoHistoryContextInjection.test_correction_signal_documented`
  asserts `"-0.2"` as a **literal string** in the SKILL.md source via `_phase_text()`. This test passes if and only if
  Step 2's `(default -0.2)` suffix is preserved verbatim in the replacement prose. Omitting the suffix
  (e.g., leaving only `{{config.history.go_no_go.correction_penalty}}`) will cause this test to fail.
  No edit to this test file is required as long as the implementation follows Step 2 exactly.

### Existing Tests (no changes needed)
- `scripts/tests/test_config.py:2667` — `TestGoNoGoConfig` — already tests defaults + override
- `scripts/tests/test_config.py:2683` — `TestCaptureIssueConfig` — already tests defaults + override
- `scripts/tests/test_config.py:2783` — `test_history_to_dict_round_trip` — already asserts
  `h["go_no_go"]["correction_penalty"] == -0.2` and `h["capture_issue"]["dup_overlap_threshold"] == 0.7`

### Configuration
- `.ll/ll-config.json` — users add `history.go_no_go.correction_penalty` or
  `history.capture_issue.dup_overlap_threshold` to tune; `config-schema.json` already
  declares both keys (ENH-1913)

### Similar Patterns
- `skills/capture-issue/SKILL.md:191` — uses `{{config.issues.duplicate_detection.exact_threshold}}`
  and `{{config.issues.duplicate_detection.similar_threshold}}` template variables; same pattern
- `skills/review-epic/SKILL.md` — uses `{{config.commands.review_epic.stale_days}}` with explicit
  `(default 14)` fallback in Step 1 and Guard Rails; follow this two-mention pattern

### Documentation
- N/A — no user-facing documentation changes (config-schema and docs/reference/CONFIGURATION.md
  already updated by ENH-1913)

## Acceptance Criteria

- Absent config → identical behavior to today (`-0.2`, `0.7`).
- Setting the keys changes the effective threshold; never raises on malformed/partial config.
- No `config-schema.json` diff (schema owned by ENH-1913).

## Impact

- **Priority**: P4 — Low-friction quality-of-life improvement; no user-facing blocking issue
- **Effort**: Small — Two one-line prose replacements + one Python literal; tests add ~15 lines
- **Risk**: Low — Fallbacks preserve current behavior; no breaking changes
- **Breaking Change**: No

## Dependencies

- **Depends on**: ENH-1913 (declares both keys in the `history` schema — done).
- Follow-up to ENH-1888 (done).

## Verification Notes

**Verdict: CURRENT** — Verified 2026-06-04. Implementation plan is accurate:

- **`-0.2` correction penalty**: Lives in `skills/go-no-go/SKILL.md:145` as LLM instruction
  prose. Template variable `{{config.history.go_no_go.correction_penalty}}` resolves correctly
  via `skill_expander.py:_substitute_config()` → `BRConfig.resolve_variable()` →
  `BRConfig.to_dict()` (confirmed at lines 2800-2801 in the test file).
- **`0.7` dup overlap threshold**: Lives in both `skills/capture-issue/SKILL.md:216` (LLM prose)
  AND `scripts/little_loops/issue_discovery/search.py:261` (Python: `if overlap > 0.7`).
  The Python guard is distinct from the `config.issues.duplicate_detection` thresholds used
  in Passes 1 and 3 — this is a standalone Pass 2 title-similarity guard that must use
  `config.history.capture_issue.dup_overlap_threshold`.
- **to_dict coverage**: `test_history_to_dict_round_trip` (test_config.py:2800-2801) already
  tests both defaults through `to_dict()`. The implementation steps add override-path assertions
  to `test_history_defaults_on_absent` and `test_history_loads_from_config`.

## Session Log
- `/ll:ready-issue` - 2026-06-04T02:20:43 - `38ca444e-8874-4458-84a2-de691c1a661a.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `2666939e-93b1-4789-9b59-9fb330b0cf63.jsonl`
- `/ll:wire-issue` - 2026-06-04T02:15:58 - `883e90c7-6180-4dd9-a495-a83dab066a44.jsonl`
- `/ll:refine-issue` - 2026-06-04T02:10:59 - `290988ce-bf6b-40a9-85ac-256fb4bd6b5e.jsonl`
- `/ll:refine-issue` - 2026-06-04T00:45:23 - `3ce6b5fc-b012-4951-b3ab-bb878fcf9d39.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:verify-issues` - 2026-06-03T21:38:03Z - `b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`
- `/ll:format-issue` - 2026-06-03T21:43:44 - `94aee1f9-3b17-4da0-bc07-bb56977ac102.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

**Open** | Created: 2026-06-03 | Priority: P4
