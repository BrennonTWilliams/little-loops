---
id: BUG-2735
title: evaluation-quality.yaml's sample state reads confidence_score/outcome_confidence/formatted
  fields that ll-issues list --json never returns
type: BUG
captured_at: '2026-07-22T04:51:32Z'
completed_at: '2026-07-22T13:26:45Z'
discovered_date: '2026-07-22'
discovered_by: capture-issue
labels:
- fsm-loop
- issue-management
relates_to:
- BUG-2734
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-2735: evaluation-quality.yaml's sample state reads confidence_score/outcome_confidence/formatted fields that ll-issues list --json never returns

## Summary

`evaluation-quality.yaml`'s `sample` state (`scripts/little_loops/loops/evaluation-quality.yaml`
lines ~18-36) pipes `ll-issues list --json` into Python that computes
`scored`/`unscored`/`avg_confidence_score`/`below_threshold`/`unformatted` by
reading `i.get('confidence_score')`, `i.get('outcome_confidence')`, and
`i.get('formatted', False)` per issue. None of those keys are ever present in
`ll-issues list --json` output — its per-issue keys are only `id`, `priority`,
`type`, `title`, `path`, `status`, `discovered_date`, `completed_at`, `parent`,
`labels`, `milestone` (+`summary` with `--include-summary`). There is no
`--verbose`/`--full`/`--fields` flag to widen it. `confidence_score` and
`outcome_confidence` are only exposed — as renamed keys `confidence`/`outcome`
— via `ll-issues show <id> --json`, called per-issue. `formatted` isn't a
field anywhere; the closest equivalent is the per-issue `ll-issues
format-check <id>` command, which also has no bulk mode.

Found as a side-effect while diagnosing the (already-fixed) sibling bug in
`autodev.yaml`, where several states read `confidence_score`/`outcome_confidence`
against `ll-issues show --json` output that actually uses `confidence`/`outcome`
— a simple key-rename fix. This one is different in kind: the data isn't
available in bulk at all, so it isn't a one-line fix (see Proposed Solution).

## Current Behavior

Every run of the `sample` state computes the same wrong-in-the-same-direction
metrics regardless of actual backlog state:
- `scored = 0` always (no issue ever has a truthy `confidence_score` key in
  `list --json` output)
- `unscored = total` always
- `avg_confidence_score = 0.0` always (`0 / max(0, 1)`)
- `below_threshold = total` always (missing-key default `0 < 70` is always
  true)
- `unformatted = total` always (missing-key default `False`, `not False` is
  always `True`)

The downstream `score` LLM state (`evaluation-quality.yaml` lines ~58-84)
synthesizes `issue_quality` from these permanently-worst-case inputs, so the
loop's issue-quality dimension has never reflected the real backlog since
this loop was authored (FEAT-790) — it always reports 0 scored, 100% below
threshold, 100% unformatted.

## Steps to Reproduce

1. Ensure at least one active (`open`/`in_progress`/`blocked`) issue has a
   real `confidence_score`/`outcome_confidence` in its frontmatter and has
   been through `/ll:format-issue` (i.e. `is_formatted()` would return
   `True`).
2. Run `ll-issues list --json` directly and inspect one record — note it has
   no `confidence_score`, `outcome_confidence`, or `formatted` key.
3. Run `ll-loop run evaluation-quality` (or `ll-loop simulate evaluation-quality`)
   and inspect the `sample` state's captured output.
4. Observe: `scored: 0`, `avg_confidence_score: 0.0`, `below_threshold: <total>`,
   and `unformatted: <total>` regardless of the real scores/format status set
   up in step 1 — the metrics are pegged to worst-case every run.

## Expected Behavior

The `sample` state's issue-quality metrics reflect the real confidence/outcome
scores and format status of active issues, so `evaluate-quality`'s report and
any threshold-triggered remediation routing are based on real data.

## Motivation

`evaluation-quality` is designed to run periodically (before sprint planning
or weekly, per its own description) as a backlog health check. A metric that
is silently and permanently pegged to the worst possible value defeats the
loop's purpose — it can never distinguish a healthy backlog from an unhealthy
one on this dimension, and any downstream routing gated on
`issue_quality_threshold` (context, threshold 70) would always see the
lowest-possible score.

## Proposed Solution

Two viable approaches, to be weighed during refinement — this issue does not
prescribe one:

**Option A — bulk CLI flag (preferred, avoids N+1 subprocess calls)**: add an
`--include-scores` (or similar) flag to `ll-issues list --json`
(`scripts/little_loops/cli/issues/list_cmd.py::cmd_list`) that reads
`confidence_score`/`outcome_confidence` from each issue's frontmatter (same
source `show.py` lines 180-181 already read) and adds them under the `show`
command's existing key names (`confidence`/`outcome`) for consistency. A
"formatted" bulk signal would need its own decision — either a lightweight
structural check reused from `format-check`'s logic, or drop `unformatted`
from this loop's metrics if it's not worth exposing in bulk.

**Option B — per-issue subprocess loop**: rewrite the `sample` state's Python
to call `ll-issues show <id> --json` (and a formatted-status source) once per
active issue instead of relying on `list --json`. Turns one list call into
N+1 subprocess calls across the whole active backlog — needs a perf gate
(e.g. skip/sample above some issue count) given `evaluation-quality` is meant
to be a quick periodic check, not a long-running scan.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

A third option exists that the original proposal didn't identify, and it
resolves the Option A vs. Option B tradeoff outright:

**Option C — switch `sample` to `ll-issues refine-status --json` (no CLI
changes needed)**:

> **Selected:** Option C — reuses an existing bulk command with zero code
> changes, no new CLI surface, and no subprocess fan-out.

`ll-issues refine-status --json`
(`scripts/little_loops/cli/issues/refine_status.py::cmd_refine_status`,
JSON-array branch lines 321-344) already builds one record per **active**
issue (via the same `find_issues(config, ...)` call `list` uses) containing
exactly the fields `sample`'s Python expects, verbatim key names:
`confidence_score`, `outcome_confidence`, and `formatted` — plus
`score_complexity`/`score_test_coverage`/`score_ambiguity`/
`score_change_surface`/`size`/`normalized`, all sourced from the `Issue`
dataclass (`scripts/little_loops/issue_parser.py`) with no extra subprocess
calls (single bulk command, same cost profile as today's `list --json`).
`formatted` comes from `is_formatted()` (`issue_parser.py:62`), the same
function `show.py` uses for its table `fmt` column — so it is a
structurally-real "formatted" signal, not a placeholder.

This means the `sample` state's fix can be a **one-line substitution**
(`ll-issues list --json` → `ll-issues refine-status --json`) with no changes
to `list_cmd.py` or `__init__.py`'s argparse wiring, and no perf gate needed
— it dominates both Option A (avoids adding new CLI surface area) and
Option B (avoids N+1 subprocess calls). The one caveat: `refine-status`'s
JSON keys are a superset of what `sample` reads today (also includes
`title`, `source`, `commands`, `score_*`, `size`, `normalized`) — harmless
extra keys the inline Python already ignores via `.get(...)`.

**Recommended**: Option C — reuses an existing, already-correct bulk command
instead of building new CLI surface (Option A) or paying N+1 subprocess cost
(Option B).

### Decision Rationale

**Selected**: Option C — switch `sample` to `ll-issues refine-status --json`

**Reasoning**: Three independent codebase-pattern-finder passes confirmed
`refine-status --json`'s default (no-`--type`) invocation walks the identical
active-issue population (`open`/`in_progress`/`blocked`) that `list --json`
walks via the same `find_issues()` call, and already emits `confidence_score`,
`outcome_confidence`, and `formatted` (from `is_formatted()`, the same
function `show.py`'s `fmt` column uses) under the exact key names the
`sample` state's inline Python reads via `.get(...)`. The fix is a one-line
data-source swap with zero Python changes, zero new CLI surface, and no
subprocess fan-out — dominating both alternatives on every scored dimension.

| Dimension | Option A (bulk flag) | Option B (per-issue loop) | Option C (refine-status) |
|---|---|---|---|
| Consistency | 3 | 0 | 3 |
| Simplicity | 2 | 1 | 3 |
| Testability | 2 | 1 | 3 |
| Risk | 3 | 1 | 3 |
| **Total** | **10/12** | **3/12** | **12/12** |

**Key evidence**:
- `refine_status.py:321-344` emits `confidence_score`/`outcome_confidence`/`formatted` verbatim per active issue, sourced from the same `find_issues(config, ...)` selection `list_cmd.py` uses (confirmed matching default status-filter behavior in both `search.py:121-161` and `refine_status.py:277-281`).
- `is_formatted()` (`issue_parser.py:62-106`) is a standalone shared utility already reused by both `show.py:244` and `refine_status.py:338` — not something Option A would duplicate from `format-check`'s CLI logic, and not something Option B's `show --json` exposes at all (confirmed via grep: no `formatted` key anywhere in `show.py`'s JSON payload).
- No existing loop YAML contains an N+1 per-issue `show --json` fan-out over an entire active backlog (`autodev.yaml`'s per-issue `show` calls all operate on a single already-dequeued issue) — Option B would introduce a wholly new idiom with no perf-gate precedent to reuse, and would need ~2N calls (one `show`, one `format-check`-equivalent) per run against a ~50-issue active backlog.
- Option A is well-precedented (`--include-summary`'s gate-and-splice shape in `list_cmd.py:93-94,117,167` is a near-exact template) but adds CLI surface area and duplicated frontmatter-read logic that Option C avoids entirely by reusing an already-shipped command.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/evaluation-quality.yaml` (`sample` state) — either approach requires updating this state's action
- `scripts/little_loops/cli/issues/list_cmd.py` (`cmd_list`) — only if Option A is chosen
- `scripts/little_loops/cli/issues/__init__.py` (list subparser flags, ~lines 172-265) — only if Option A adds a new flag

### Dependent Files (Callers/Importers)
- None outside the loop itself call `sample`'s output structure directly; it's consumed in-process by the `score` state's prompt interpolation (`${captured.metrics.output}`)

### Similar Patterns
- `scripts/little_loops/cli/issues/show.py` lines 180-181, 352-353 — the existing `confidence_score`/`outcome_confidence` -> `confidence`/`outcome` frontmatter-to-JSON-key mapping to mirror if Option A is chosen
- `scripts/little_loops/cli/issues/refine_status.py` lines 321-344 (`cmd_refine_status`, `--json` branch) — already emits `confidence_score`/`outcome_confidence`/`formatted` in bulk for active issues; the direct source for Option C (see Codebase Research Findings above)
- `scripts/little_loops/cli/issues/__init__.py` lines 196-202 — `--include-summary` flag wiring, the pattern to follow for a new `--include-scores`-style flag if Option A is chosen instead
- `scripts/little_loops/loops/autodev.yaml` (fixed by commit `ca4f6d1b`) — the sibling fix that switched inline-Python consumers to `show --json`'s renamed `confidence`/`outcome` keys; confirms the field-renaming idiom but took the per-issue `show` route (closer to Option B) rather than a bulk command

### Tests
- `scripts/tests/` — add/extend a test asserting `evaluation-quality`'s `sample` state (or the underlying CLI change) produces non-worst-case metrics against a fixture backlog with real scores
- `scripts/tests/test_issues_cli.py:790` (`test_list_json_include_summary_flag`) — model for asserting new/existing JSON keys appear per-item, reusable for a `refine-status --json` or `list --include-scores --json` assertion
- `scripts/tests/test_issues_cli.py` `TestListSorting` fixture (`list_sort_issues_dir`, ~line 3468) — pattern for seeding `confidence_score`/`outcome_confidence` frontmatter across multiple fixture issues, reusable for a non-worst-case metrics test

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Decide between Option A (bulk CLI flag), Option B (per-issue subprocess loop), and Option C (switch to `ll-issues refine-status --json`, see Codebase Research Findings under Proposed Solution) — Option C requires no CLI changes and is the recommended default absent a reason to prefer A or B.
2. Implement the chosen data-sourcing change.
3. Update `evaluation-quality.yaml`'s `sample` state to consume the corrected field names/source.
4. Add a test verifying `scored`/`avg_confidence_score`/`below_threshold`/`unformatted` reflect real per-issue data rather than defaulting to worst-case.
5. Manually run `ll-loop run evaluation-quality` (or `ll-loop simulate`) against a small fixture backlog to confirm the reported metrics change with real score variation.

## Impact

- **Priority**: P2 — not a crash and not blocking, but it silently and permanently corrupts one dimension of a periodic health-check loop's primary output; anyone relying on `evaluation-quality`'s issue_quality score to gauge backlog health has been getting a meaningless constant.
- **Effort**: Medium — Option A touches CLI + loop; Option B is loop-only but needs a perf gate. (Option C, added via `/ll:refine-issue` research, is Low effort — a one-line data-source swap in the loop YAML only, see Proposed Solution.)
- **Risk**: Low — read-only reporting path; no risk of corrupting issue data either way.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | `ll-issues` CLI tool descriptions (`list`, `show`) |

## Resolution

Applied the recommended Option C: switched `evaluation-quality.yaml`'s `sample`
state to pipe `ll-issues refine-status --json` instead of `ll-issues list
--json` (one-line data-source swap, no CLI code changes). `refine-status
--json` already emits `confidence_score`, `outcome_confidence`, and
`formatted` verbatim per active issue, so the state's existing inline Python
now computes real metrics instead of a permanent worst-case constant.

Added two tests to `TestEvaluationQualityLoop` in
`scripts/tests/test_builtin_loops.py`:
- `test_sample_state_sources_refine_status_not_list` — structural assertion
  that the action references `refine-status --json`, not `list --json`.
- `test_sample_state_metrics_reflect_real_scores` — executes the embedded
  Python snippet against fixture records shaped like `refine-status --json`
  output and asserts `scored`/`unscored`/`unformatted`/`avg_confidence_score`/
  `below_threshold` reflect the real data rather than defaulting to
  worst-case.

Confirmed via `git stash` that `test_sample_state_sources_refine_status_not_list`
fails against the pre-fix loop file (12 tests passed vs. 14 post-fix). The
metrics test exercises the embedded Python snippet in isolation against a
fixture shaped like `refine-status --json` output — that snippet's logic was
always correct, so this test guards against future regressions in the
snippet itself rather than re-detecting the original wrong-data-source bug.

Full suite: `python -m pytest scripts/tests/` — 15764 passed, 38 skipped, 3
pre-existing unrelated failures (autodev.yaml `confidence_score`/`confidence`
key-naming assertions, confirmed failing identically on `main` before this
change via `git stash`).

## Session Log
- `/ll:manage-issue` - 2026-07-22T13:25:51Z - `c83f0fa0-1024-4d57-b5fa-ddce93f9807a.jsonl`
- `/ll:ready-issue` - 2026-07-22T13:21:59 - `d593a4ac-e1c6-4b48-ad58-c71ac7afed5a.jsonl`
- `/ll:confidence-check` - 2026-07-22T13:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e0e3a48-daf7-4094-9a9a-8e0add2eb66d.jsonl`
- `/ll:decide-issue` - 2026-07-22T13:16:22 - `2cf80bdc-43c8-4852-92cf-aec8ffee1531.jsonl`
- `/ll:refine-issue` - 2026-07-22T13:11:53 - `6a867440-86cc-404f-9d86-f41b915e84c3.jsonl`
- `/ll:capture-issue` - 2026-07-22T04:51:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b578d6b3-a1ba-4ae1-8566-2846991a5642.jsonl`

## Status

- **Status**: open
