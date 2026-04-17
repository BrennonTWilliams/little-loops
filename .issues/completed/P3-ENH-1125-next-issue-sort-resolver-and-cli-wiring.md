---
parent: ENH-1123
depends_on: ENH-1124
discovered_date: 2026-04-16
discovered_by: issue-size-review
size: Medium
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1125: Sort-Key Resolver and CLI Wiring for next-issue

## Summary

Implement the sort-key resolver function that converts a `NextIssueConfig` into a sort-key callable, and replace the hardcoded sort tuples in `next_issue.py` and `next_issues.py` with resolver calls.

## Parent Issue

Decomposed from ENH-1123: Configurable ll-issues next-issue Selection Behavior

## Current Behavior

`next_issue.py:33-39` and `next_issues.py:31-37` both contain a hardcoded sort-key lambda — `(-(outcome_confidence or -1), -(confidence_score or -1), priority_int)` — duplicated byte-for-byte across the two CLI handlers. Users cannot change selection behavior without editing source.

## Expected Behavior

Both CLI handlers call a single resolver (`build_sort_key(config.issues.next_issue)`) that returns a sort-key callable. Named strategies (`confidence_first`, `priority_first`) and explicit `sort_keys` lists in config change selection order; absent config, the default `confidence_first` strategy is byte-identical to today's lambda.

## Impact

- **Priority**: P3 — unlocks configurability unlocked by ENH-1124 schema; no user-visible regression required.
- **Effort**: Medium — one new helper, two ~6-line call-site swaps, per-field sentinel logic documented by predecessor refinement passes.
- **Risk**: Low — default preset is byte-identical to current tuple; existing `TestNextIssueSorting` / `TestNextIssuesRankedOrder` act as regression guards.
- **Breaking Change**: No.

## Scope Boundaries

- Out of scope: test additions for `build_sort_key` itself and doc updates (both owned by ENH-1126).
- Out of scope: config schema additions (owned by ENH-1124, now completed).
- Out of scope: changing error-handling convention in other `cli/` subpackages; only `cli/issues/` local convention applies.

## Labels

`enhancement`, `cli`, `refactor`

## Proposed Solution

1. Implement a sort-key resolver — a function `build_sort_key(config: NextIssueConfig) -> Callable[[IssueInfo], tuple]`:
   - Either reuse/extend `_sort_issues(items, sort_field, descending)` at `scripts/little_loops/cli/issues/search.py:135-178` or implement a sibling helper following the same string-dispatch shape
   - Support all sortable `IssueInfo` fields: `outcome_confidence`, `confidence_score`, `priority_int`, `effort`, `impact`, `size`, and the four `score_*` sub-scores
   - Pin a single None-handling convention (current `next_issue.py` treats `None` as `-1` after negation; choose this or `search.py`'s `9999` — document the choice)
   - Implement named presets: `"confidence_first"` (current behavior: `(-(oc or -1), -(cs or -1), priority_int)`), `"priority_first"` (priority first, then confidence)
   - When `sort_keys` is set, it overrides `strategy`

2. Replace hardcoded sort blocks with resolver call:
   - `scripts/little_loops/cli/issues/next_issue.py:33-39` → `issues.sort(key=build_sort_key(config.issues.next_issue))`
   - `scripts/little_loops/cli/issues/next_issues.py:31-37` → same resolver call
   - Ensure `config` is loaded (these CLIs already receive a config object; verify the path)
   - Surface `ValueError` from resolver cleanly. **Note**: the original ENH-1123 pointer to `cli/loop/run.py:46-48` (`logger.error` + `return 1`) is wrong for this subpackage — `cli/issues/` uses `print(f"Error: {e}", file=sys.stderr); return 1` (see `path_cmd.py:29-30`, `skip.py:34-35`, `list_cmd.py:84-85`). Follow the local convention.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issue.py:33-39` — replace hardcoded sort with `issues.sort(key=build_sort_key(config.issues.next_issue))`
- `scripts/little_loops/cli/issues/next_issues.py:31-37` — replace byte-identical block with same resolver call

### New Code
- **Resolver placement decision**: add `build_sort_key(config: NextIssueConfig) -> Callable[[IssueInfo], tuple]` as a **sibling helper alongside `_sort_issues` in `scripts/little_loops/cli/issues/search.py`** (not inside `_sort_issues`). Rationale: `_sort_issues` operates on 4-tuples `(IssueInfo, status, discovered_date, completed_date)` (search.py:135-139), so reuse is impractical; co-locating a bare-`IssueInfo` sibling keeps all sort infrastructure in one module.

### Dependent Files (verify no assumptions break)
- `scripts/little_loops/cli/issues/__init__.py:441-444` — dispatcher already invokes `cmd_next_issue(config, args)` and `cmd_next_issues(config, args)`; **no handler signature changes needed** — `config.issues.next_issue` is reachable once ENH-1124 lands
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:26` — shells out to `ll-issues next-issue`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:31,33` — shells out to `ll-issues next-issue --skip`
- `scripts/little_loops/loops/lib/cli.yaml:55` — reusable `ll_issues_next_issue` fragment

### Similar Patterns
- `scripts/little_loops/cli/issues/search.py:135-178` — `_sort_issues` is the closest structural template (string-dispatch on field name → tuple key, with None sentinel); **does NOT operate on bare `IssueInfo`**, so model after, don't call
- `scripts/little_loops/cli/issues/search.py:143-177` — inner `key()` closure style: named inner `def` capturing outer config via closure — the idiomatic "factory returning callable" shape in this codebase
- `scripts/little_loops/cli/issues/refine_status.py:310-313` — `_sort_key` named-function style (preferred over lambda for nontrivial extraction)
- `scripts/little_loops/fsm/evaluators.py:699-820` — `evaluate(config, ...)` dispatches on `config.type` (string preset); mirror this shape for `strategy` dispatch
- `scripts/little_loops/fsm/evaluators.py:83-90` — `_NUMERIC_OPERATORS: dict[str, Callable[...]]` is the dict-of-lambdas alternative if strategy table grows
- `scripts/little_loops/issue_parser.py:202-310` — all sortable `IssueInfo` fields (enum source for `sort_keys[].key`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Error-handling convention correction**: the Proposed Solution step 2 suggests mirroring `cli/loop/run.py:46-48` (`except ValueError as e: logger.error(...); return 1`). However, the `cli/issues/` subpackage uses a **different convention**: `print(f"Error: ...", file=sys.stderr); return 1` (no logger instance). Examples: `path_cmd.py:29-30`, `skip.py:34-35`, `list_cmd.py:84-85`, `append_log.py:28-32`. **Recommendation**: follow the local convention for `cli/issues/` — wrap `build_sort_key(config.issues.next_issue)` in a try/except at the top of `cmd_next_issue`/`cmd_next_issues` with `except ValueError as e: print(f"Error: {e}", file=sys.stderr); return 1`.

**Handler signatures** (already correct — no changes needed):
- `cmd_next_issue(config: BRConfig, args: argparse.Namespace) -> int` (`next_issue.py:12`)
- `cmd_next_issues(config: BRConfig, args: argparse.Namespace) -> int` (`next_issues.py:12`)

Both handlers already receive `config: BRConfig`; `config.issues.next_issue` becomes reachable once ENH-1124 lands.

**`_sort_issues` coverage gap** (`search.py:145-176`): existing helper supports `priority`, `id`, `date`/`created`, `completed`, `type`, `title`, `confidence`, `outcome`, `refinement`. It does **NOT** cover `effort`, `impact`, or the four `score_*` fields that ENH-1123 requires. The new resolver must implement all sortable fields listed on `IssueInfo`; extending `_sort_issues` in place would change its contract (4-tuple input) for no benefit. Sibling helper is the right call.

**None-handling convention decision** (resolve here): `next_issue.py:33-39` uses `-1` (sorts `None` last after negation for `desc`); `search.py:159-164` uses `9999` (sorts `None` last in `asc`).

**Important caveat on "adopt `search.py`'s convention + `reverse=True`"**: `search.py:_sort_issues` is single-field, so `reverse=True` on the whole tuple works. `build_sort_key` must produce **multi-field tuples with mixed directions** — e.g., `confidence_first` is `(desc oc, desc cs, asc priority_int)` — and `sorted(..., reverse=True)` inverts **every** field uniformly, which would break priority ordering (lower `priority_int` must come first).

**Recommendation (revised)**: stay with **per-field key transformation, no `reverse=True`**, matching the current lambda. Choose the sentinel per-field based on the field's `direction`:
- `direction: "desc"` (confidence-like, high = best): key component = `-value if value is not None else 1` (mirrors current lambda) — or equivalently `-(value or -1)`
- `direction: "asc"` (priority-like, low = best): key component = `value if value is not None else 9999` (None sorts last)

Document this in the resolver docstring. Do **not** rely on `sorted(..., reverse=True)` — the resolver should return a key function that works under the default ascending `sorted()`.

**Strategy preset tuples** (from ENH-1124 research, re-stated for implementer — see "Strategy tuple semantics restated" below for the final sentinel-aware form):
- `"confidence_first"` (default): `(-(outcome_confidence or -1), -(confidence_score or -1), priority_int)` — byte-identical to today's lambda
- `"priority_first"`: `(priority_int, -(outcome_confidence or -1), -(confidence_score or -1))`

**No existing `build_sort_key` / `make_sort_key` / `sort_resolver` helpers** exist — confirmed safe to introduce without naming conflict.

**Import path for CLI handlers** (both `next_issue.py` and `next_issues.py` use lazy imports inside the handler — see `next_issue.py:24-26`, `next_issues.py:24-25`): add `from little_loops.cli.issues.search import build_sort_key` to the inline import block. Do **not** promote to module-level — the existing style defers CLI imports to keep `ll-issues --help` fast.

**Strategy tuple semantics restated with the chosen sentinel** (per-field, no `reverse=True`):
- `"confidence_first"`: `(-(oc) if oc is not None else 1, -(cs) if cs is not None else 1, priority_int)` — byte-identical to the current lambda
- `"priority_first"`: `(priority_int, -(oc) if oc is not None else 1, -(cs) if cs is not None else 1)`

When `sort_keys` list is provided, build the tuple by iterating `sort_keys` in order, applying the per-field sentinel rule above based on each entry's `direction`.

**Tests do not import the sort lambda directly** (`test_next_issue.py`, `test_next_issues.py` use black-box `main_issues()` via `sys.argv` patch). The resolver refactor cannot silently break imports; order-assertion tests at `test_next_issue.py:58-197` and `test_next_issues.py:58-143` will still need to see the `confidence_first` default produce the same order (covered by ENH-1126 scope, not this issue).

### Tests
- `scripts/tests/test_next_issue.py` — integration coverage via `main_issues()`; `TestNextIssueSorting` (line 58) asserts today's order and must continue to pass unchanged under `confidence_first` default (regression guard). Test updates belong to ENH-1126.
- `scripts/tests/test_next_issues.py` — same pattern; `TestNextIssuesRankedOrder` (line 58) is the mirror regression guard.
- **Test pattern for the resolver itself** (belongs to ENH-1126, referenced here for context): `scripts/tests/test_fsm_evaluators.py:404-478` (`TestEvaluateDispatcher`) is the canonical template — construct config, call dispatcher, assert on result. For `build_sort_key`: construct `NextIssueConfig`, call `build_sort_key(config)`, call the returned key on a synthetic `IssueInfo`, assert on the resulting tuple.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_search.py` — existing `TestSearchSorting` (lines 639-723) tests `_sort_issues` via `cmd_search` and is unaffected by `build_sort_key` addition; new `TestBuildSortKey` class belongs here (ENH-1126 scope) — this is the natural home per `test_issues_*.py` naming convention [Agent 3 finding]
- `scripts/tests/test_next_issues.py:101-106, 141-143` — these are **full-list index assertions** (`assert lines[0] == "FEAT-002"` etc.), structurally more fragile than the winner-only checks in `test_next_issue.py`. If the None-sentinel convention changes (adopting `9999` over `-1`), verify the tuple ordering remains byte-compatible with these assertions before merging [Agent 3 finding]
- `scripts/tests/test_config.py:154-169` — `TestIssuesConfig.test_from_dict_with_defaults` currently asserts on `duplicate_detection` defaults; after ENH-1124 lands, needs `assert config.next_issue.strategy == "confidence_first"` added (ENH-1126 scope) [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2975, 3005` — two locations that describe the hardcoded sort-key tuple verbatim (`-(outcome_confidence or -1), -(confidence_score or -1), priority_int`); become stale after this implementation — update to describe configurable behavior (ENH-1126 scope) [Agent 2 finding]
- `docs/reference/CLI.md:526, 541` — hardcoded sort-order descriptions for `next-issue` and `next-issues` commands; same stale-doc risk (ENH-1126 scope) [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:37-40, 247-248` — config example block and `IssuesConfig` table both lack `next_issue.*` entries; update alongside ENH-1124 schema work (ENH-1126 scope) [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:126-148` — `"additionalProperties": false` on the `issues` object will reject any config containing `issues.next_issue` until this schema is updated; this is a hard dependency: ENH-1124 must add the `next_issue` object definition here before ENH-1125 can be tested against a real config [Agent 2 finding]

## Acceptance Criteria

- `ll-issues next-issue` with no config produces identical output to today's hardcoded behavior
- `ll-issues next-issue` with `strategy: "priority_first"` in config returns the highest-priority issue first
- `ll-issues next-issue` with custom `sort_keys` respects the specified field order
- A config with unknown strategy causes `ll-issues next-issue` to exit 1 with an error message
- Both `next_issue.py` and `next_issues.py` use the same resolver

## Resolution

- **Implementation**: Added `build_sort_key(config: NextIssueConfig) -> Callable[[IssueInfo], tuple]` as sibling helper to `_sort_issues` in `scripts/little_loops/cli/issues/search.py`. Strategy preset table (`_STRATEGY_SORT_KEYS`) maps `"confidence_first"`/`"priority_first"` to `(field, direction)` entry sequences; `sort_keys` takes precedence when set. Per-field sentinel: `desc` → `-value else 1`, `asc` → `value else 9999`. Schema key `"priority"` maps to `IssueInfo.priority_int`.
- **Wiring**: Replaced hardcoded lambda in `next_issue.py:33-39` and `next_issues.py:31-37` with `build_sort_key(config.issues.next_issue)`. Both handlers wrap the resolver call in `try/except ValueError` following the local `cli/issues/` convention (`print(f"Error: {e}", file=sys.stderr); return 1`).
- **Default parity**: `confidence_first` preset produces `(-(oc) or 1, -(cs) or 1, priority_int)` — byte-identical to the previous lambda. All regression tests pass unchanged.
- **Verification**: 4934 tests pass (`python -m pytest scripts/tests/`), ruff clean, mypy clean.

## Session Log
- `/ll:manage-issue` - 2026-04-17T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-04-17T18:42:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9167bb39-d550-4147-9ba4-1c4c18f4332e.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5dd383c-269e-4293-be55-d331c7b17127.jsonl`
- `/ll:refine-issue` - 2026-04-16T20:03:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23d47188-3676-49de-b1f7-a5cbc4800ff9.jsonl`
- `/ll:wire-issue` - 2026-04-16T19:59:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c4a1c636-06bb-43fb-a1e0-0981651dd6e7.jsonl`
- `/ll:refine-issue` - 2026-04-16T19:55:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45c11175-fab0-451f-b9eb-c8d6dfff4d21.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed68bd1a-5a6f-4d92-94fd-8ff3a80f7d09.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d999d664-e1fc-4ade-87dc-7332cf0ca773.jsonl`

---

**Open** | Created: 2026-04-16 | Priority: P3
