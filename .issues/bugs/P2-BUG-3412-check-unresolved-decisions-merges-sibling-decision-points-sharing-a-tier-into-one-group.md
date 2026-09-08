---
id: BUG-3412
type: BUG
title: check-unresolved-decisions merges sibling decision points sharing a tier into
  one group
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T19:44:58Z'
---

# BUG-3412: check-unresolved-decisions merges sibling decision points sharing a tier into one group

## Summary

`_decision_groups_in_body()` in `scripts/little_loops/issue_parser.py` splits an issue
section's decision-point option blocks into `DecisionGroup`s only on a tier change or a
Pattern E directive boundary — never on a `**Decision point:**` prose boundary. When a
section has 2+ decision points that happen to share the same option tier, they merge into
one `DecisionGroup`, and `is_group_resolved()` marks the whole merged group resolved as soon
as any single member has a `> **Selected:**` callout. `ll-issues check-unresolved-decisions`
then reports 0 unresolved groups even though a real, undecided decision point remains.

## Current Behavior

`ll-issues check-unresolved-decisions <ID>` (backed by `locate_unresolved_decisions()` /
`is_group_resolved()` in `scripts/little_loops/issue_parser.py`) can report "no unresolved
decision group remains" (exit 0) even when a real, un-decided decision point remains in the
issue's `## Proposed Solution` section — as long as it shares its option-block tier with an
already-decided sibling decision point in the same section.

Root cause: `_decision_groups_in_body()` splits a section's tagged option-block matches into
`DecisionGroup`s only on a *tier change* (e.g. `bold_label` -> `numbered`) or when a Pattern E
directive window falls between two matches — never on a `**Decision point:**` prose boundary.
When a `## Proposed Solution` section contains several distinct "Decision point:" blocks that
all happen to use the same tier (e.g. all `**Option A**/**Option B**` bold-label blocks in a
row, with no intervening tier change), they get merged into a single `DecisionGroup` spanning
the whole run.

`is_group_resolved()` then returns `True` for that merged group as soon as **any** member
option's span carries a `> **Selected:**` callout — it has no way to know the merged group
actually represents 3-4 independent decision points, only one of which was decided.

## Expected Behavior

`_decision_groups_in_body()` splits a same-tier run into separate `DecisionGroup`s whenever
a `**Decision point:**` marker (or equivalent decision-point boundary text) falls between two
consecutive matches, the same way it already splits on `directive_between`. Given a section
with 2+ same-tier decision points, only the first decided, `ll-issues
check-unresolved-decisions <ID>` exits 1 and names the still-undecided decision point as an
unresolved group, instead of exiting 0 for the merged group.

## Motivation

`/ll:decide-issue`'s Phase 7b and Phase 3b step 4 gate clearing `decision_needed` directly on
this check's exit code. As demonstrated live on FEAT-3409 (4 same-tier decision points, 3
resolved, 1 not), the merge bug lets `decision_needed` clear while a real decision point is
still open in the issue body — downstream automation (`/ll:wire-issue`, `/ll:manage-issue`)
then proceeds against an issue that looks fully decided but isn't. The bug was caught only by
manual inspection, not by the tool it exists to gate.

## Proposed Solution

In `_decision_groups_in_body()` (scripts/little_loops/issue_parser.py:2777), add a
decision-point boundary check alongside the existing `directive_between` check in the
run-splitting loop (issue_parser.py:2806-2817). Detect a `**Decision point:**` (or equivalent)
marker between `tagged[i-1]` and `tagged[i]` the same way `directive_between` detects a
Pattern E directive line between them — via a line-range comparison against
`body_offset`/`content` — and start a new run when either condition holds, even when
`tier_name == prev_tier`:

```python
decision_point_between = _decision_point_marker_between(content, body_offset, prev_pos, pos)
if tier_name == prev_tier and not directive_between and not decision_point_between:
    runs[-1].append(i)
else:
    runs.append([i])
```

`is_group_resolved()` itself is correct per-group and needs no change — the fix belongs
entirely in group construction.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_decision_groups_in_body()` run-splitting loop
  (issue_parser.py:2806-2817); add a decision-point-marker helper alongside it.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` — `DecisionGroup` class docstring
  (issue_parser.py:2710-2719) states only two run-breaking conditions ("A run breaks when
  the tier changes, when a Pattern E directive window intervenes, or at a section
  boundary") — needs a third clause for the new decision-point-marker boundary.

### Dependent Files (Callers/Importers)
- `_decision_groups_in_body()` is called from `locate_unresolved_decisions()`
  (issue_parser.py:2925, 2934), which backs `ll-issues check-unresolved-decisions`.
- `/ll:decide-issue`'s Phase 7b and Phase 3b step 4 gate `decision_needed` clearing on this
  check's exit code — no code change needed there, but behavior changes once the fix lands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_unresolved_decisions.py:63,71` — the actual CLI
  entry point backing `ll-issues check-unresolved-decisions`; calls
  `locate_unresolved_decisions()` directly and was not previously named in this issue. No
  code change needed — its output changes once the fix lands, since more same-tier
  multi-decision-point issues will correctly surface an unresolved group.
- `scripts/little_loops/cli/issues/__init__.py:36-39,747,1046-1047` — imports, registers,
  and dispatches the `check-unresolved-decisions` subcommand. No code change needed.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:216,242` — `check_residual_decision`
  FSM state shells out to `ll-issues check-unresolved-decisions ${context.issue_id:shell}`
  and branches on its exit code. No code change needed — behavior changes once the fix lands.
- `skills/decide-issue/SKILL.md:181,190,285,401` and `skills/decide-issue/reference.md:134,245`
  — gate `decision_needed` clearing on this CLI's exit code at Phase 3b step 4 and Phase 7b;
  prose is generic (no tier-merge claim) and needs no correction, but confirmed dependent.

### Similar Patterns
- `_directive_decision_group()` (issue_parser.py:2842) already demonstrates the pattern of
  treating a prose marker as a group boundary distinct from tier — worth checking for
  consistency once the decision-point-marker check is added.

### Tests
- `scripts/tests/test_issue_parser_unresolved.py` — add the regression test named in
  Acceptance Criteria (2+ same-tier decision points, only the first decided).
- `scripts/tests/test_decide_issue_skill.py` — verify `/ll:decide-issue`'s gate still behaves
  correctly against the corrected grouping.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_unresolved_decisions.py` — subprocess-level CLI tests
  for `check-unresolved-decisions`; no existing fixture covers 2+ same-tier decision points
  (closest, `test_second_lower_precedence_group_exits_one_even_when_first_is_decided`, splits
  via a tier change, not a marker). Add a CLI-level fixture mirroring the new unit test to
  confirm the fix is visible through the actual CLI exit code and `--json` payload, not just
  the parser internals.

### Documentation
- N/A — `_decision_groups_in_body()` behavior isn't documented outside its own docstring and
  the BUG-3278 issue that introduced it.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1098` — `locate_unresolved_decisions` doc entry mirrors the same
  stale two-condition prose ("a maximal contiguous run of same-tier option blocks, or one
  Pattern E directive window") as the `DecisionGroup` docstring above; needs the same
  third-condition addition.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `directive_between` (issue_parser.py:2806-2817) is an inline local variable computed within the run-splitting loop, not an extracted helper function — no existing `_..._between()` line-range-check helper exists anywhere in the codebase (repo-wide search; only unrelated hits: `extract_between_tags()` in `output/parse.py:30`, `_seconds_between()` in `session_store/writers.py:135`). The new `_decision_point_marker_between()` will be the first extracted function of this shape; `directive_between`'s inline computation is a structural precedent, not an existing function to literally mirror.
- The Similar Patterns claim that `_directive_decision_group()` (issue_parser.py:2842) "demonstrates the pattern of treating a prose marker as a group boundary" is only partly accurate: `_directive_decision_group()` locates the Pattern E directive and returns a standalone `DecisionGroup`, but the actual line-range boundary comparison lives in `_decision_groups_in_body()`'s inline `directive_between` (issue_parser.py:2810-2813), fed by `directive_split_line = directive_group.end_line` computed once in `_iter_decision_groups()` (issue_parser.py:2908-2916). The new helper differs further in shape: `directive_between` compares against one precomputed line number per document, while a `**Decision point:**` marker check must detect any marker line falling within the (prev, pos) range per pair.
- No existing regex/constant matches the literal `**Decision point:**` marker text anywhere in the codebase; the only related hit is a case-insensitive, unbolded `\bdecision point\b` alternative inside `_OPEN_QUESTION_SIGNAL_RE` (issue_parser.py:3092), used for open-question hedge detection — a different function and purpose, not directly reusable. Marker regexes in this module follow a module-level `_SOMETHING_RE = re.compile(...)` constant convention (e.g. `_SELECTED_CALLOUT_RE` line 1381, `_PREFERENCE_MARKER_RE` lines 2269-2277), declared above their consuming functions rather than inlined.
- The char-offset-to-1-based-line-number idiom `content.count("\n", 0, offset) + 1` recurs inline at issue_parser.py:2213-2214, 2359-2360, 2448-2449, 2767-2768, 2810/2812 — never factored into a shared helper; the new marker-detection helper should follow this same inline idiom rather than introducing a new utility.
- `scripts/tests/test_issue_parser_unresolved.py`'s `TestDecisionGroups` class (line 1187) is the convention for the regression test: import the target function inline inside the test body (not module top), build the fixture as a triple-quoted string literal in the test (not a fixture file), and assert on `len(groups)`/`groups[i].tier`/`len(groups[i].options)`/`is_group_resolved(...)`. The closest structural analog is `test_directive_splits_a_same_tier_run_into_two_groups` (lines 1304-1321, splits a same-tier run via a Pattern E directive rather than a decision-point marker). `test_two_decision_points_one_decided_leaves_one_unresolved` (lines 1380-1400) and `test_both_groups_marked_resolved_converges_to_zero` (lines 1402-1422) already cover "one decided, one not" but across a tier change, not a same-tier `**Decision point:**` marker split — no existing test reproduces BUG-3412's own shape (same tier, split only by the marker).

## Program Design

### Types

- No new types; `DecisionGroup` (issue_parser.py:2711) is unchanged.

### Signatures

- `_decision_point_marker_between(content: str, body_offset: int, prev_pos: int, pos: int) -> bool`
  — mirrors the existing inline `directive_between` computation (issue_parser.py:2809-2813)
  but checks for a `**Decision point:**`-style marker between the two positions instead of
  the Pattern E directive line.

### Call Path

`ll-issues check-unresolved-decisions` -> `locate_unresolved_decisions()` ->
`_decision_groups_in_body()` -> `_decision_point_marker_between()` (new) -> `is_group_resolved()`

## Implementation Steps

1. Add `_decision_point_marker_between()` in `scripts/little_loops/issue_parser.py`, mirroring
   the line-range comparison `directive_between` already does for the Pattern E directive.
2. Wire it into the run-splitting condition at issue_parser.py:2814 so a run breaks when either
   `directive_between` or the new decision-point check is true.
3. Add the regression test to `scripts/tests/test_issue_parser_unresolved.py` reproducing the
   FEAT-3409 shape (2+ same-tier decision points, only the first decided).
4. Run `python -m pytest scripts/tests/` and confirm `check-unresolved-decisions` against
   FEAT-3409 now reports the unresolved decision point.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `DecisionGroup` class docstring (issue_parser.py:2710-2719) to add the new
  decision-point-marker run-breaking condition alongside tier change and Pattern E directive.
- Update `docs/reference/API.md:1098` (`locate_unresolved_decisions` entry) to match the
  corrected docstring.
- Add a CLI-level regression fixture to
  `scripts/tests/test_ll_issues_check_unresolved_decisions.py` reproducing the same-tier
  multi-decision-point shape, to confirm the fix through the actual CLI exit code and
  `--json` payload, not just the parser internals.

## Impact

`/ll:decide-issue`'s Phase 7b and Phase 3b step 4 gate clearing `decision_needed` directly on
this check's exit code. In `--auto` mode, an issue whose Proposed Solution section holds
multiple same-tier decision points can have `decision_needed` silently cleared after only one
of them is actually decided — the remaining decision point(s) stay unresolved in the issue body
but the frontmatter flag no longer signals it, so downstream automation (`/ll:wire-issue`,
`/ll:manage-issue`) proceeds as if the issue were fully decided.

## Steps to Reproduce

1. Create (or find) an issue whose `## Proposed Solution` section has 2+ separate
   `**Decision point:** ...` blocks, each followed by `**Option A**`/`**Option B**` bold-label
   option pairs, with no section-header-tier options and no Pattern E directive between them.
2. Resolve only the *first* decision point by inserting a `> **Selected:** Option A — ...`
   callout on its winning option. Leave the second (or later) decision point's options with no
   Selected callout (e.g. only a `**Recommended**: Option B` line, or nothing at all).
3. Run `ll-issues check-unresolved-decisions <ID>`.

**Expected**: exit 1, naming the still-undecided decision point as an unresolved group.

**Actual**: exit 0 — "No unresolved decision group remains" — because the two decision points
were merged into one `DecisionGroup` by `_decision_groups_in_body()`, and the first decision
point's Selected callout satisfies `is_group_resolved()` for the whole merged group.

## Discovered Via

Live `/ll:decide-issue FEAT-3409 --auto` run (2026-09-08). FEAT-3409's `## Proposed Solution`
section has 4 `**Decision point:**` blocks, all using the `bold_label` tier
(`**Option A**/**Option B**/**Option C**`), with 3 already resolved via `> **Selected:**`
callouts and a 4th ("Default `manifest_path` resolution") left only with a declarative
`**Recommended**: Option B` line (no Selected callout). `ll-issues check-unresolved-decisions
FEAT-3409` reported 0 unresolved groups despite the 4th decision point being genuinely
undecided. Caught by manual inspection, not by the tool.

## Files to Modify

- `scripts/little_loops/issue_parser.py` — `_decision_groups_in_body()` (the run-splitting
  loop, currently keyed only on `tier_name == prev_tier` and `directive_between`) needs to also
  split a run when a `**Decision point:**` marker (or equivalent decision-point boundary text)
  falls between two consecutive same-tier matches, mirroring the existing `directive_between`
  boundary check.
- `scripts/little_loops/issue_parser.py` — `is_group_resolved()`'s single-Selected-callout check
  is otherwise correct per-group; the fix belongs in group construction, not resolution.

## Acceptance Criteria

- A `## Proposed Solution` section with 2+ `**Decision point:**` blocks sharing the same option
  tier is split into separate `DecisionGroup`s by `_decision_groups_in_body()`.
- `ll-issues check-unresolved-decisions` correctly reports an unresolved group when only some
  same-tier decision points in a section have been decided.
- Regression test reproducing the FEAT-3409 shape: 2+ same-tier decision points in one section,
  only the first decided, asserting `check-unresolved-decisions` still reports the second as
  unresolved.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-08T20:21:07 - `829655b3-be33-4d4b-a196-5c697fc23a0c.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:57:45 - `b6b6e9ca-1e9e-4589-b966-7e973d10f797.jsonl`
- `/ll:format-issue` - 2026-09-08T19:51:50 - `cb4b9ca3-dab7-4f31-8422-5d785ebaffef.jsonl`
- `/ll:capture-issue` - 2026-09-08T19:45:05 - `ce7357ff-ca14-4ec7-8141-84e7fba71ec5.jsonl`
