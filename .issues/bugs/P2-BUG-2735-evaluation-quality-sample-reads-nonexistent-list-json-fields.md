---
id: BUG-2735
title: evaluation-quality.yaml's sample state reads confidence_score/outcome_confidence/formatted
  fields that ll-issues list --json never returns
type: BUG
captured_at: '2026-07-22T04:51:32Z'
discovered_date: '2026-07-22'
discovered_by: capture-issue
labels:
- fsm-loop
- issue-management
relates_to:
- BUG-2734
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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/evaluation-quality.yaml` (`sample` state) — either approach requires updating this state's action
- `scripts/little_loops/cli/issues/list_cmd.py` (`cmd_list`) — only if Option A is chosen
- `scripts/little_loops/cli/issues/__init__.py` (list subparser flags, ~lines 172-265) — only if Option A adds a new flag

### Dependent Files (Callers/Importers)
- None outside the loop itself call `sample`'s output structure directly; it's consumed in-process by the `score` state's prompt interpolation (`${captured.metrics.output}`)

### Similar Patterns
- `scripts/little_loops/cli/issues/show.py` lines 180-181, 352-353 — the existing `confidence_score`/`outcome_confidence` -> `confidence`/`outcome` frontmatter-to-JSON-key mapping to mirror if Option A is chosen

### Tests
- `scripts/tests/` — add/extend a test asserting `evaluation-quality`'s `sample` state (or the underlying CLI change) produces non-worst-case metrics against a fixture backlog with real scores

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Decide between Option A (bulk CLI flag) and Option B (per-issue subprocess loop) during refinement — weigh perf cost of Option B against the CLI surface-area cost of Option A.
2. Implement the chosen data-sourcing change.
3. Update `evaluation-quality.yaml`'s `sample` state to consume the corrected field names/source.
4. Add a test verifying `scored`/`avg_confidence_score`/`below_threshold`/`unformatted` reflect real per-issue data rather than defaulting to worst-case.
5. Manually run `ll-loop run evaluation-quality` (or `ll-loop simulate`) against a small fixture backlog to confirm the reported metrics change with real score variation.

## Impact

- **Priority**: P2 — not a crash and not blocking, but it silently and permanently corrupts one dimension of a periodic health-check loop's primary output; anyone relying on `evaluation-quality`'s issue_quality score to gauge backlog health has been getting a meaningless constant.
- **Effort**: Medium — Option A touches CLI + loop; Option B is loop-only but needs a perf gate.
- **Risk**: Low — read-only reporting path; no risk of corrupting issue data either way.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | `ll-issues` CLI tool descriptions (`list`, `show`) |

## Session Log
- `/ll:capture-issue` - 2026-07-22T04:51:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b578d6b3-a1ba-4ae1-8566-2846991a5642.jsonl`

## Status

- **Status**: open
