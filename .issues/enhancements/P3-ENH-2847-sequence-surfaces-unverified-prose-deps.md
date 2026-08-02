---
id: ENH-2847
type: ENH
priority: P3
status: done
discovered_date: 2026-07-26
discovered_by: manual-review
completed_at: '2026-07-27T04:45:17Z'
labels:
- issues-cli
- dependency-graph
- dx
blocked_by:
- FEAT-2846
relates_to:
- BUG-2848
confidence_score: 100
outcome_confidence: 87
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2847: `ll-issues sequence` should surface unverified prose dependencies

## Summary

`ll-issues sequence` prints `no blockers` for any issue with no structured
`blocked_by` edge, including issues whose bodies state a dependency in prose.
Annotate those rows with the suspected edge instead of asserting the issue is
unblocked — at the point of failure, where the misleading output is actually
read.

## Current Behavior

`cli/issues/sequence.py:74-78`:

```python
blockers = graph.blocked_by.get(issue.issue_id, set())
if blockers:
    rationale = f"blocked by: {', '.join(sorted(blockers))}"
else:
    rationale = "no blockers"
```

`no blockers` is an unqualified positive claim derived from the absence of a
frontmatter key. It reads identically whether the issue genuinely has no
prerequisites or whether an edge was simply never recorded. In a downstream
project's case that produced:

```
[P2, no blockers] FEAT-110: Smoke tests, .gitignore, plan tree sync, ...
```

for an issue whose body names ENH-109 as a blocker, with ENH-109 still open.

`--json` (`sequence.py:56-69`) has the same gap — consumers get
`"blocked_by": []` with no signal that a prose claim exists.

## Expected Behavior

Using FEAT-2846's `extract_prose_deps()`, annotate rather than reorder:

```
[P2, no blockers ⚠ prose dep FEAT-109 (open), not in blocked_by] FEAT-110: ...
```

and add to `--json`:

```json
{"id": "FEAT-110", "blocked_by": [], "unverified_prose_deps": ["FEAT-109"]}
```

**Prose must never change topological order.** Extraction has false positives;
letting it constrain the sort trades a silent false negative for a silent false
positive, which is not an improvement. The annotation prompts a human check;
the structured field remains the only ordering input. Automation that wants to
gate hard can read `unverified_prose_deps` and decide for itself.

Prose references to `done`/`cancelled` issues are not annotated here — those are
`stale_prose_dep` and belong to `format-check` (FEAT-2846), not to sequence
output.

A `--strict` flag that exits non-zero when any shown issue has an unverified
prose dep would make this usable as an automation gate; worth considering but
not required for the core fix.

## Root Cause

`sequence` was written to report the graph faithfully and does so. The gap is
that "the graph has no edge" was rendered as "the issue has no blockers" — a
stronger claim than the data supports.

## Implementation Steps

1. Built on FEAT-2846's `extract_prose_deps()` — this issue should not ship a
   second extractor. (Recorded as `blocked_by: [FEAT-2846]`, which is exactly the
   invariant FEAT-2846 exists to enforce.)
2. In `sequence.py`, for each shown issue with an empty `blocked_by` set,
   extract prose deps, drop those already in `blocked_by`/`depends_on` and those
   whose referenced issue is terminal, and annotate the remainder.
3. Extend the `--json` record with `unverified_prose_deps`.
4. Keep the extraction lazy/bounded — only for the issues actually shown
   (`ordered[:limit]`), not the whole backlog, so `sequence` stays fast.
5. Consider `--strict`.
6. Tests: annotated row for a drifting issue, no annotation when the edge is
   structured, no annotation when the referenced issue is `done`, ordering
   unchanged in all cases.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`. JSON branch
  (lines 54-71) builds one dict per issue via `sorted(graph.blocked_by.get(...))`
  etc.; text branch (lines 73-90) builds `blockers`/`prerequisites` then falls
  back to the literal string `"no blockers"` at line 82 when both are empty.
  Neither branch currently opens the issue body — `extract_prose_deps()` is not
  called anywhere in this file today.

### Dependent Files (Reused Logic — model, don't duplicate)
- `scripts/little_loops/issue_parser.py:308-333` (`check_format_gaps()`) — the
  exact drift/stale classification to mirror:
  ```python
  status = issue_statuses.get(prose_id)
  if status in ("done", "cancelled"):
      gaps.stale_prose_dep.append(prose_id)
  elif prose_id not in structured_deps:
      gaps.prose_dep_drift.append(prose_id)
  ```
  Terminal-status test is the literal tuple `status in ("done", "cancelled")`
  (note: `deferred` is NOT terminal — a prose dep on a `deferred` issue still
  counts as unverified). This function fails open: if `issue_statuses is None`,
  no gaps are reported at all (see docstring lines 234-238) — `sequence` must
  build and pass its own `issue_statuses` map rather than relying on a default.
- `scripts/little_loops/cli/issues/format_check.py:126-127` (`cmd_format_check`)
  — caller-side setup pattern for the `issue_statuses` map:
  ```python
  all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
  issue_statuses = {info.issue_id: info.status for info in all_issues}
  ```
  This must draw from **all** issues, not the status-filtered active set
  `cmd_sequence` already queries via `find_issues()` — otherwise prose refs to
  `done`/`cancelled` issues can't be classified as `stale_prose_dep` (they'd
  already be excluded from the active result set).
- `scripts/little_loops/issues/prose_deps.py:42` — `extract_prose_deps(body: str) -> set[str]`.
  Contract: caller must pass the body with frontmatter already stripped
  (`little_loops.frontmatter.strip_frontmatter()`). Returns normalized
  `TYPE-NNN` ids; excludes matches inside fenced code blocks. Carries no status
  info itself — status classification is the caller's job.
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`,
  `topological_sort()` (lines 301-371), `get_pending_prerequisites()`. Confirms
  `ordered = graph.topological_sort()` / `shown = ordered[:limit]` (sequence.py
  lines 46-52) already scope both output branches to the shown page — the new
  prose-dep extraction can reuse that same `shown` iteration without extra
  bounding logic (Implementation Step 4 is satisfied by existing structure, not
  new code).

### Similar Patterns
- `scripts/little_loops/cli/issues/sequence.py:54-71` — the `--json` dict
  construction to extend with `"unverified_prose_deps": sorted(...)`, following
  the existing `**({"key": val} if val else {})` conditional-key idiom already
  used for `type_filter`.
- `scripts/little_loops/cli/issues/sequence.py:73-90` — the text-mode
  `parts.append(...)` idiom (`parts.append(f"blocked by: ...")`, `parts.append(f"after: ...")`)
  to extend with a third `parts.append(f"⚠ prose dep {...}, not in blocked_by")`
  entry, joined via `"; ".join(parts)`.
- `scripts/little_loops/issue_parser.py:136-175` — `FormatGaps` dataclass shape
  (one `list[str]` field per gap category + `has_gaps` + `to_dict()`) as the
  template if a dedicated dataclass is preferred over inline dict construction.
- No existing `--strict`-style flag exists anywhere in the `ll-issues` CLI
  (confirmed via full-repo grep) — the closest analogs are `format-check`'s
  bare `return 1 if gaps.has_gaps else 0` (format_check.py:200-208, no flag
  needed because gating is the command's whole purpose) and
  `epic_consistency.py:260`'s `p.add_argument("--all", "-a", action="store_true", ...)`
  as the registration pattern if `--strict` is added.

### Tests
- `scripts/tests/test_ll_issues_format_check.py` `TestFormatCheckProseDeps`
  (lines 377-461) — existing three-case coverage pattern (active-target →
  drift, done-target → stale, already-in-`blocked_by` → clean) to mirror for
  `sequence`'s own annotation logic. Uses module-level `_write_issue`/`_invoke`
  helpers and a `format_check_dir` fixture building a temp `.ll/ll-config.json`
  project.
- No dedicated test file for `cmd_sequence` exists yet in `scripts/tests/`
  (only referenced indirectly in `test_issue_parser.py:1498-1502` for
  `find_issues()` callsite-shape parity) — a new `TestSequenceProseDeps` class
  (in `test_issues_cli.py`, which already covers `sequence` at lines
  ~1408-1663, or a new file) is needed rather than an existing one to extend.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py::TestIssuesCLISequence::test_sequence_basic`
  (line ~1431, asserts `"no blockers" in captured.out`) — regression-check, not
  expected to break since none of `conftest.py`'s `issues_dir` fixture bodies
  (BUG-001/002, FEAT-001/002) contain a prose reference `extract_prose_deps()`
  would match, but re-run explicitly since the annotation likely appends onto
  the same rationale string this substring is checked against.
- `scripts/tests/test_issues_cli.py::test_sequence_json_output` (line
  ~1480-1512) — asserts required-keys-present only (not a closed key set), so
  adding `unverified_prose_deps` won't break it; extend with a new assertion
  for the key once added, following the `assert isinstance(item["blocked_by"],
  list)` idiom.
- New test: topological-order-pinning — no existing test does an order-diff
  check for `sequence` annotations; author one that builds a fixture with a
  prose-only dependency and asserts the ordered `id` sequence in `--json`
  output is unchanged whether or not the annotation fires (Acceptance
  Criterion 2).

### Documentation
- `docs/reference/API.md` — documents `DependencyGraph`, `extract_prose_deps()`,
  `check_format_gaps()`; may need a short addition once `sequence`'s
  `unverified_prose_deps` field ships.
- `docs/reference/CLI.md` — documents `ll-issues sequence`; update its
  `--json` schema description alongside the code change.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/SPRINT_GUIDE.md:149` and `commands/create-sprint.md:179,258` —
  both frame "no blockers" as pure `blocked_by`-absence for the
  parallel-ready-issues grouping strategy. Not broken by this change (the
  underlying semantics don't move), but become incomplete once `sequence`
  annotates prose deps — optional accuracy follow-up, not required for this
  issue's scope.
- `commands/ready-issue.md:213-232` already gates on `format-check`'s
  `prose_dep_drift` (a separate signal, FEAT-2849) rather than `sequence`'s
  new `unverified_prose_deps` — the two fields describe related but distinct
  checks; no code coupling, flagging only so a future doc pass can reconcile
  the two names if that reads as confusing.

## Scope Boundaries

**In scope**: `ll-issues sequence` output only — text rationale and the `--json`
record.

**Out of scope**: the extractor itself (FEAT-2846), the `stale_prose_dep`
classification and `--fix` backfill (FEAT-2846), the `depends_on`/
`topological_sort` asymmetry (BUG-2848), and any change to ordering. Other
consumers of the graph — `next-issue`, `clusters`, wave planning — are not
touched; if the annotation proves useful there, that is a follow-up.

## Acceptance Criteria

- [x] An issue with a prose dep and no structured edge is annotated in both text
      and `--json` output.
- [x] Topological order is byte-identical to today's for every input — a test
      pins that prose never affects ordering.
- [x] Prose references to terminal issues produce no annotation.
- [x] Extraction cost scales with `--limit`, not with backlog size.

## Impact

- **Users**: the misleading `no blockers` claim becomes a visible prompt to
  check. This alone would have caught the FEAT-110 case at the moment it misled
  a reader.
- **Risk**: Low. Presentation-only; ordering is untouched.
- **Effort**: Small, once FEAT-2846 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/sequence.py:54-82` | Output paths to extend |
| `FEAT-2846` | Provides the extractor and the drift/stale distinction |
| `BUG-2848` | The other source of `no blockers` false negatives (`depends_on`) |

## Context

Traced from a downstream project's `ll-issues sequence` run that reported a
blocked issue as `[P2, no blockers]`.

## Session Log
- `/ll:manage-issue` - 2026-07-27T04:44:35 - `d2c9705f-c2d7-411b-a63a-bbc11fe8eed7.jsonl`
- `/ll:wire-issue` - 2026-07-27T04:35:01 - `59c0b9c4-4a09-43e1-8935-cd8cde8ed118.jsonl`
- `/ll:refine-issue` - 2026-07-27T04:29:11 - `158b8099-8081-46c2-ab65-4ca145e10262.jsonl`

---

## Status

open
