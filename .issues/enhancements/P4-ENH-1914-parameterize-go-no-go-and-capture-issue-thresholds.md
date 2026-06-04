---
id: ENH-1914
title: Parameterize ENH-1888's hardcoded go-no-go / capture-issue thresholds
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T21:38:03Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, ENH-1913, ENH-1888]
labels:
  - history-db
  - configurability
---

# ENH-1914: Parameterize ENH-1888's hardcoded thresholds

## Summary

ENH-1888 (done) bakes in two magic numbers with no config exposure: a `-0.2`
correction-confidence penalty in `go-no-go` and a `>70%` (0.7) duplicate-overlap
threshold in `capture-issue`. Expose both as `history.*` keys read inside the
respective Python paths, so they become user-tunable like the rest of the
read/consume surface.

## Current Behavior

The go-no-go skill applies a hardcoded `-0.2` correction-confidence penalty and the capture-issue skill uses a hardcoded `0.7` duplicate-overlap threshold. Both constants are baked into the Python source with no config exposure.

## Expected Behavior

Both thresholds are read from `ll-config.json` via `BRConfig`, falling back to their current defaults (`-0.2` and `0.7`) when absent. Users can tune them per-project without code changes.

## Motivation

These thresholds directly affect agent decisions (whether go/no-go flags a recent
correction; whether capture-issue warns about a near-duplicate) but cannot be
tuned per project. They are the last hardcoded read-side consumers from the
EPIC-1707 audit. Parameterizing them completes the "consistent, user-tunable
`history.*`" goal for the consumer surface.

## Scope Boundaries

- **In scope**: Wiring `BRConfig` reads for the two threshold constants in the go-no-go and capture-issue Python paths; fallback to current defaults.
- **Out of scope**: Adding schema keys to `config-schema.json` (owned by ENH-1913); UI or output changes to either skill; changing the default threshold values.

## API/Interface

- `history.go_no_go.correction_penalty` — float, default `-0.2`
- `history.capture_issue.dup_overlap_threshold` — float, default `0.7`

Both are already declared in the `history` schema by ENH-1913; this issue wires
the **runtime reads** only — no `config-schema.json` edit.

## Implementation Steps

1. **`find_existing_issue()` in `scripts/little_loops/issue_discovery/search.py:261`**: Replace `if overlap > 0.7` with `if overlap > config.history.capture_issue.dup_overlap_threshold`. No signature change — `config: BRConfig` is already the first parameter; `config.history.capture_issue.dup_overlap_threshold` resolves via the already-wired `HistoryConfig.capture_issue` sub-object.

2. **`skills/go-no-go/SKILL.md:145`**: Replace `-0.2` with `{{config.history.go_no_go.correction_penalty}}` and append `(default -0.2)` in the same sentence, following the `review-epic` pattern. Full sentence becomes: "Each matched correction is a `{{config.history.go_no_go.correction_penalty}}` (default -0.2) signal on the GO/NO-GO verdict confidence."

3. **`skills/capture-issue/SKILL.md:216`**: Replace the `>70%` prose literal with `>{{config.history.capture_issue.dup_overlap_threshold}}` (default 0.7). Append `(default 0.7)` inline, consistent with the review-epic fallback note pattern.

4. **`scripts/tests/test_issue_discovery.py:362`** (`TestFindExistingIssue`): Add `test_find_existing_issue_configurable_dup_threshold` — create a config with `history.capture_issue.dup_overlap_threshold: 0.9`, confirm a 0.75-overlap title match is rejected; then create a config with threshold 0.6, confirm the same 0.75-overlap match is accepted.

5. **`scripts/tests/test_config.py:2749`** (`TestBRConfigHistoryIntegration`): Add `config.history.go_no_go.correction_penalty == -0.2` and `config.history.capture_issue.dup_overlap_threshold == 0.7` assertions to `test_history_defaults_on_absent`; add matching override assertions to `test_history_loads_from_config`.

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md:145` — LLM prose where `-0.2` penalty is stated; implementation must use a skill-level config read (e.g. embed threshold in `ll-history-context` output, or call `ll-config` in prose) rather than a Python path
- `skills/capture-issue/SKILL.md:216` — LLM prose where `>70%` threshold is stated; update prose to read threshold from config
- `scripts/little_loops/issue_discovery/search.py:261` — Python `if overlap > 0.7` that also implements the dup-overlap check; back this via `BRConfig.history`

### Dependent Files (Callers/Importers)
- N/A — thresholds are internal to each skill's Python path

### Similar Patterns
- ENH-1913 declares the `history.*` config keys; follow the same `BRConfig` read pattern
- `skills/capture-issue/SKILL.md:191` — already uses `{{config.issues.duplicate_detection.exact_threshold}}` and `{{config.issues.duplicate_detection.similar_threshold}}` template variables; same pattern applies for `{{config.history.capture_issue.dup_overlap_threshold}}`
- `skills/review-epic/SKILL.md` — uses `{{config.commands.review_epic.stale_days}}` with explicit `(default 14)` fallback note in prose; follow this pattern for the penalty and threshold replacements

### Tests
- `scripts/tests/test_issue_discovery.py:362` — `TestFindExistingIssue`: add `test_find_existing_issue_configurable_dup_threshold` verifying that `history.capture_issue.dup_overlap_threshold: 0.9` misses a 0.75-overlap match that the 0.7 default catches, and that `history.capture_issue.dup_overlap_threshold: 0.6` catches a 0.65-overlap match that the 0.7 default misses
- `scripts/tests/test_config.py:2749` — `TestBRConfigHistoryIntegration.test_history_defaults_on_absent`: add `assert config.history.go_no_go.correction_penalty == -0.2` and `assert config.history.capture_issue.dup_overlap_threshold == 0.7`
- `scripts/tests/test_config.py:2749` — `TestBRConfigHistoryIntegration.test_history_loads_from_config`: add assertions that setting `history.go_no_go.correction_penalty` and `history.capture_issue.dup_overlap_threshold` in ll-config.json propagates through `BRConfig.history`

### Documentation
- N/A — no user-facing documentation changes

### Configuration
- `.ll/ll-config.json` — users add `history.go_no_go.correction_penalty` or `history.capture_issue.dup_overlap_threshold` to tune

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Config infrastructure already in place (ENH-1913 is done):**
- `scripts/little_loops/config/features.py:688` — `GoNoGoConfig` dataclass, field `correction_penalty: float = -0.2`, `from_dict` with fallback
- `scripts/little_loops/config/features.py:702` — `CaptureIssueConfig` dataclass, field `dup_overlap_threshold: float = 0.7`, `from_dict` with fallback
- `scripts/little_loops/config/features.py:716` — `HistoryConfig` includes `go_no_go: GoNoGoConfig` (line 733) and `capture_issue: CaptureIssueConfig` (line 734) sub-fields
- `scripts/little_loops/config/core.py:227` — `BRConfig._parse_config()` wires `HistoryConfig.from_dict(self._raw_config.get("history", {}))`
- `scripts/little_loops/config/core.py:320` — `BRConfig.history` property exposes the full `HistoryConfig`
- `config-schema.json:1477` — schema declarations for both keys already present

**No `ll-config get` CLI exists** — template variable injection (`{{config.*}}`) is the only established approach for parameterizing skill prose.

**Test classes already covering the config layer (ENH-1913 added these):**
- `scripts/tests/test_config.py:2667` — `TestGoNoGoConfig` (defaults + override)
- `scripts/tests/test_config.py:2683` — `TestCaptureIssueConfig` (defaults + override)
- `scripts/tests/test_config.py:2699` — `TestHistoryConfig` with `test_go_no_go_defaults` / `test_capture_issue_defaults`
- `scripts/tests/test_config.py:2749` — `TestBRConfigHistoryIntegration` exists but lacks assertions for `go_no_go`/`capture_issue` sub-fields — add in step 5 of implementation

## Acceptance Criteria

- Absent config → identical behavior to today (`-0.2`, `0.7`).
- Setting the keys changes the effective threshold; never raises on
  malformed/partial config.
- No `config-schema.json` diff (schema owned by ENH-1913).

## Impact

- **Priority**: P4 — Low-friction quality-of-life improvement; no user-facing blocking issue
- **Effort**: Small — Two one-line config reads with fallbacks; follows established `BRConfig` pattern
- **Risk**: Low — Fallbacks preserve current behavior; no breaking changes
- **Breaking Change**: No

## Dependencies

- **Depends on**: ENH-1913 (declares both keys in the `history` schema).
- Follow-up to ENH-1888 (done).

## Verification Notes

**Verdict: NEEDS_UPDATE** — Verified 2026-06-03. Integration map is inaccurate: both thresholds are in skill Markdown prose, not Python paths.

- **`-0.2` correction penalty**: Lives in `skills/go-no-go/SKILL.md:145` as LLM instruction prose ("Each matched correction is a -0.2 signal on the GO/NO-GO verdict confidence"). There is no Python path applying this value — the LLM interprets it directly from the skill text. "TBD — go-no-go Python path" is incorrect; the implementation approach must change.
- **`0.7` dup overlap threshold**: Lives in both `skills/capture-issue/SKILL.md:216` (LLM prose: ">70% title word overlap") AND `scripts/little_loops/issue_discovery/search.py:261` (Python: `if overlap > 0.7`). The Python path IS configurable via BRConfig, but the prose copy also needs updating.
- **Action**: The go-no-go approach requires either (a) having the skill prose call `ll-config` to read the threshold, or (b) exposing it via `ll-history-context` output, or (c) a different design. Update "Files to Modify" to reflect the actual paths before implementation.

## Session Log
- `/ll:refine-issue` - 2026-06-04T00:45:23 - `3ce6b5fc-b012-4951-b3ab-bb878fcf9d39.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:verify-issues` - 2026-06-03T21:38:03Z - `b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`
- `/ll:format-issue` - 2026-06-03T21:43:44 - `94aee1f9-3b17-4da0-bc07-bb56977ac102.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

**Open** | Created: 2026-06-03 | Priority: P4
