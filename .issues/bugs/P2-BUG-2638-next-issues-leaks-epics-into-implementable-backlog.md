---
id: BUG-2638
title: ll-issues next-issues leaks EPIC ids into the implementable backlog, causing
  autodev to refine an EPIC as a leaf
type: BUG
priority: P2
status: done
captured_at: '2026-07-14T16:56:26Z'
completed_at: '2026-07-14T17:27:49Z'
discovered_date: '2026-07-14'
discovered_by: capture-issue
size: Small
confidence_score: 96
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 20
---

# BUG-2638: `ll-issues next-issues` leaks EPIC ids into the implementable backlog

## Summary

`ll-issues next-issues` ranks and returns **EPIC-type issues** as if they were
implementable leaf issues. When `auto-refine-and-implement.yaml` runs with an
empty `scope` (backlog mode), it takes the `next-issues` list verbatim, so an
EPIC id is dispatched into the autodev queue alongside its own children. autodev
then hands the EPIC to `refine-to-ready-issue`, which has no issue-type guard and
runs `/ll:refine-issue EPIC-482 --auto --gap-analysis` — refining an umbrella
container as though it were a leaf.

Observed in project `ai-workspaces/ll-labs/cards`, run
`auto-refine-and-implement-20260714T104607`:

```
$ ll-issues next-issues
EPIC-482      ← the EPIC, ranked as a leaf item
BUG-486
FEAT-477
...

# autodev-input.txt (backlog resolution, empty scope):
ENH-469,BUG-478,EPIC-482,FEAT-477,ENH-480,FEAT-479,ENH-481,ENH-471,FEAT-465,FEAT-466
#                       ^^^^^^^^ EPIC dispatched alongside its own children
# autodev-inflight: EPIC-482  → sent to refine-to-ready-issue
```

EPIC-482 has real children (FEAT-477, ENH-480, FEAT-479, ENH-481, BUG-478), so
the EPIC **and** its children were both queued as work in the same wave — a
double dispatch, plus a nonsensical refine of the container.

## Root Cause

**File:** `scripts/little_loops/cli/issues/next_issues.py` (`cmd_next_issues`)

The ranked backlog is built from `find_issues(config, skip_blocked=True)` (and
`find_issues(config)` in the `--include-blocked` branch) and sorted, but the
result set is **never filtered by issue type**. `find_issues` walks the whole
`.issues` tree including `epics/`, so EPIC ids flow straight into the ranked
output. EPICs are umbrella containers meant to be *decomposed* via
`SprintManager.load_or_resolve` (scope mode), never implemented as leaves.

Note the asymmetry: passing `scope=EPIC-482` explicitly to `resolve_set`
correctly expands the EPIC into its children, but the empty-scope backlog path
(`next-issues`) emits the EPIC atom instead.

Downstream, `loops/refine-to-ready-issue.yaml` has no type guard: its
`check_lifetime_limit` state routes any id to `refine_issue` /
`refine_followup` (`/ll:refine-issue`) based purely on refine-count, with no
check for whether the id is an EPIC.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the predicate in "Fix" below.** `IssueInfo.issue_type`
  (`scripts/little_loops/issue_parser.py`) holds the **category name**
  (`"epics"`, `"bugs"`, `"features"`, …) via
  `IssueParser._parse_type_and_id()` / `_prefix_to_category`, **not** the
  string `"EPIC"`. A literal `issue_type == "EPIC"` check would never match.
  Use the id-prefix instead: `info.issue_id.split("-", 1)[0] == "EPIC"`
  (equivalently `info.issue_id.startswith("EPIC-")`), or filter on the
  category name `info.issue_type == "epics"`.
- **Reuse the existing filter parameter.** `find_issues(...)` already accepts
  `type_prefixes: set[str] | None` (`issue_parser.py`) and filters per-file via
  `prefix = info.issue_id.split("-", 1)[0]; if prefix not in type_prefixes: continue`.
  It is an **allow-list**, so to exclude EPICs either pass an allow-set of every
  non-EPIC prefix (`set(config.get_all_prefixes()) - {"EPIC"}`) or apply a local
  post-`find_issues` filter `[i for i in issues if not i.issue_id.startswith("EPIC-")]`.
  A local post-filter is the lower-risk change — it touches only `next_issues.py`.
- **Filter placement matters.** In `cmd_next_issues` the truncation
  (`ranked = issues[:count]`) happens **immediately after `.sort()`**, so the
  EPIC filter must be applied to the `find_issues(...)` result **before** the
  sort/slice in *both* branches, or EPICs still consume `--count` slots.
- **Existing idiom to model after:** `epic_consistency.py`
  (`_parse_children_body`, `compute_drift`) uses both
  `issue_id.split("-")[0] in _REAL_ISSUE_TYPES` (real-type allow-list) and
  `issue_id.startswith("EPIC-")`; `epic_progress.py:49` uses the
  `.upper().startswith("EPIC-")` guard.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issues.py` — `cmd_next_issues()`:
  filter EPIC ids out of the `find_issues(...)` result in both the default
  branch (`issues = find_issues(config, skip_blocked=True)`) and the
  `--include-blocked` branch (`all_issues = find_issues(config)`), before the
  `.sort(key=sort_key)` / `[:count]` slice. Also feeds `--json` and `--path`
  output modes, which read the same `ranked` list, so one filter covers all
  variants.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — defense-in-depth:
  add a guard state ahead of `check_lifetime_limit` (line ~35, the state
  immediately before `refine_issue`) that detects an EPIC id and routes to
  `breakdown_issue` instead of `refine_issue`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/next_issue.py` — **`cmd_next_issue()` (singular
  `next-issue`) has the identical unfiltered bug.** It calls `find_issues(config)` /
  `find_issues(config, skip_blocked=True)` (lines ~30, ~45, ~51, ~66, ~71) with no
  `type_prefixes`, so EPIC ids leak here too. This is the **actual consumer** inside
  `refine-to-ready-issue.yaml`'s `resolve_issue` state (line ~29), which shells out to
  `ll-issues next-issue` (singular) → `check_lifetime_limit` → `refine_issue`. Fixing only
  the plural command leaves the loop's real entry path unfixed. Apply the same EPIC
  post-filter here in both branches, before sort/slice. [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` — CLI registration/dispatch for both
  `next-issue` (`nx`) and `next-issues` (`nxs`) subparsers (imports `cmd_next_issues`
  line ~58, dispatch line ~846; `--include-blocked` wired lines ~583–609). No change
  needed for the post-filter fix; **only** touch this if an opt-out `--include-epics`
  flag is added (mirror the existing `--include-blocked` wiring). [Agent 1 finding]

### Dependent Files (Callers/Consumers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — backlog-mode
  (empty `scope`) consumer that takes `next-issues` output verbatim into
  `autodev-input.txt`; the primary fix removes the EPIC+children double-dispatch
  here.
- `scripts/little_loops/cli/auto.py` — `ll-auto` orchestration consuming ranked
  backlog output.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `resolve_issue` state
  (line ~29) is the singular-command consumer: `ll-issues next-issue` → feeds
  `check_lifetime_limit`. This is why `next_issue.py` (not just `next_issues.py`)
  must be fixed. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — `goal-cluster` `resolve_set` (lines ~918, ~943)
  falls back to `ll-issues next-issues` on empty scope — another verbatim consumer
  that trusts leaf-implementable output. [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/cli/issues/epic_consistency.py` — `_parse_children_body()`,
  `compute_drift()`: EPIC-prefix / real-type-allow-list filtering idioms.
- `scripts/little_loops/cli/issues/epic_progress.py:49` — `.startswith("EPIC-")`
  validation guard.
- `scripts/little_loops/loops/lib/common.yaml` — `fragments.shell_exit`
  (exit-code yes/no gate); `refine-to-ready-issue.yaml:101` `check_decision_mid_refine`
  is a mid-chain gate of the exact shape the EPIC guard needs (inspect id →
  `on_yes`/`on_no`, always with `on_error`). No loop currently branches on an
  `EPIC-*` id prefix, so the guard would be new — either a small
  `case "$ID" in EPIC-*) … ;;` inline shell + `evaluate: exit_code`, or a
  `check-flag`-style CLI delegation.

### Tests
- `scripts/tests/test_next_issues.py` — extend with a regression test.
  `_setup_dirs()` does **not** create `.issues/epics/`; add an epics dir
  (mirror `TestNextIssuesBlockedFilter._setup_bugs_dir`) and write an EPIC via
  `_make_issue(epics_dir, "P2-EPIC-XXX-....md", ...)` plus its children, then
  assert the EPIC id is absent from `next-issues` output while children remain
  present. JSON idiom: `assert "EPIC-XXX" not in [row["id"] for row in data]`.
- `scripts/tests/test_builtin_loops.py` — for the `refine-to-ready-issue`
  EPIC-guard AC (may be a separate test).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_next_issue.py` — **singular-command regression test.** Since
  `next_issue.py` shares the bug, mirror the `next-issues` EPIC-exclusion test here so
  `ll-issues next-issue` also never returns an EPIC id. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — extend `TestRefineToReadyIssueSubLoop`
  (line ~983) with a `check_*`-prefixed guard-state test pair (`_state_exists` +
  `_on_yes_routes_to_breakdown_issue`), following the existing `check_readiness` /
  `breakdown_issue` templates (lines ~1036, ~1105). No existing test constructs EPIC
  fixtures, so nothing breaks. Also note `TestAutoRefineAndImplementLoop.test_resolve_set_supports_scope_branching`
  (line ~1951) already asserts the scoped vs. backlog paths. [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — has existing `type_prefixes` coverage for
  `find_issues()` (lines ~985–1485) to model the post-filter test idiom after. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-issues next-issues` / `next-issue` sections (flag +
  behavior tables); add an EPIC-exclusion bullet. [Agent 2 finding]
- `docs/reference/API.md` — `#### next-issues` / `next-issue` sections (~lines 3671–3778)
  duplicate the CLI.md behavior description. [Agent 2 finding]

### Configuration (FYI — only if a flag/config key is added)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `next_issue` object (lines ~159–203) is
  `additionalProperties: false`; any new `include_epics` key must be declared here. Not
  needed for the local post-filter fix. [Agent 2 finding]
- `scripts/little_loops/config/features.py` — `NextIssueConfig` dataclass (~line 164,
  `from_dict` ~line 240) is the Python counterpart; only touch if a config key is added. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `issues.next_issue` section (~line 979); only if
  the config surface grows. [Agent 2 finding]

## Fix

**Primary — exclude EPICs from `next-issues`.** In `cmd_next_issues`, filter
`issue_type == "EPIC"` (equivalently the `EPIC-` id prefix) out of the ranked
set before sorting, in both the default and `--include-blocked` branches. This
is the true source and also stops the EPIC+children double-dispatch. Consider a
flag (e.g. `--include-epics`) only if a caller genuinely needs epics ranked.

**Defense-in-depth — EPIC guard in `refine-to-ready-issue`.** Add a state before
`refine_issue` that detects an EPIC id and routes it to `breakdown_issue`
(decompose) instead of `/ll:refine-issue`. Even a stray EPIC id reaching the
loop should never be refined as a leaf.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Apply the EPIC post-filter in **`next_issue.py`** (`cmd_next_issue`, singular) as well
   as `next_issues.py` — same `find_issues(...)` result filter in both branches, before
   sort/slice. This is the loop's real entry path (`resolve_issue` → `ll-issues next-issue`).
2. Update `docs/reference/CLI.md` and `docs/reference/API.md` — add EPIC-exclusion note to
   both `next-issue` and `next-issues` sections.
3. Add a singular-command regression test in `scripts/tests/test_next_issue.py` mirroring
   the plural test.
4. Extend `TestRefineToReadyIssueSubLoop` in `scripts/tests/test_builtin_loops.py` with the
   EPIC-guard state test pair.

## Steps to Reproduce

1. In a project with an open EPIC that has children, run `ll-issues next-issues`.
2. Observe the EPIC id appears in the ranked output.
3. Run `ll-loop run auto-refine-and-implement` with empty `scope` (backlog mode).
4. Observe the EPIC id is dispatched into `autodev-input.txt` and eventually
   refined via `/ll:refine-issue EPIC-NNN`.

## Acceptance Criteria

- [ ] `ll-issues next-issues` **and `ll-issues next-issue`** (with `--json` / `--path` /
      `--include-blocked` variants) never emit EPIC-type ids.
- [ ] A regression test asserts an open EPIC with children is absent from
      `next-issues` output while its children remain present.
- [ ] `refine-to-ready-issue` routes an EPIC id to decomposition, not
      `/ll:refine-issue` (defense-in-depth; may be a separate AC/test).
- [ ] `python -m pytest scripts/tests/` passes.

## Resolution

Fixed 2026-07-14. Excluded EPIC-type ids from the ranked backlog at the source
and added a defense-in-depth guard in the loop.

- **Primary fix** — `next_issues.py` (`cmd_next_issues`) and `next_issue.py`
  (`cmd_next_issue`): applied a `not i.issue_id.startswith("EPIC-")` post-filter
  to every `find_issues(...)` result (default `skip_blocked`, `--include-blocked`,
  and the `all_active` fallback branches), before sort/slice. Covers `--json`,
  `--path`, and singular/plural variants.
- **Defense-in-depth** — `loops/refine-to-ready-issue.yaml`: new `check_epic_id`
  guard state between `resolve_issue` and `check_lifetime_limit`. A stray EPIC id
  (exit 0 / `on_yes`) routes to `breakdown_issue` (decompose) instead of
  `refine_issue`; leaves (exit 1 / `on_no`) proceed normally.
- **Tests** — `TestNextIssuesEpicExclusion` / `TestNextIssueEpicExclusion`
  regression tests (EPIC absent, children present, across output modes); four new
  `check_epic_id` routing tests in `TestRefineToReadyIssueSubLoop`.
- **Docs** — EPIC-exclusion notes added to `docs/reference/CLI.md` and
  `docs/reference/API.md` for both commands.

Full suite: 14923 passed, 36 skipped. `ll-loop validate refine-to-ready-issue`
passes.

## Session Log
- `/ll:manage-issue` - 2026-07-14T17:27:17Z - `000ba01e-76b0-4308-a39e-fdaf76f9715c.jsonl`
- `/ll:confidence-check` - 2026-07-14T17:30:00 - `1dac9138-8f2d-42c5-9a0f-fad9ff61b5fd.jsonl`
- `/ll:wire-issue` - 2026-07-14T17:14:36 - `a42f6c07-c78d-46cf-bd5c-2c26d1c9f184.jsonl`
- `/ll:refine-issue` - 2026-07-14T17:01:32 - `d821aeea-bb88-4025-9e93-40153ba7f852.jsonl`
- `/ll:capture-issue` - 2026-07-14T16:56:26Z - conversation root-cause analysis of cards run auto-refine-and-implement-20260714T104607
