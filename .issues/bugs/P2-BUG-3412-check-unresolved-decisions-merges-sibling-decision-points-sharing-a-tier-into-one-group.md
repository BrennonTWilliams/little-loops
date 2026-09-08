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
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
a decision-point marker falls between two consecutive matches, the same way it already splits
on `directive_between`. Given a section with 2+ same-tier decision points, only the first
decided, `ll-issues check-unresolved-decisions <ID>` exits 1 and reports the still-undecided
decision point as a separate unresolved group (`<section heading> (lines N-M)` — the group's
own line range, not the merged run's), instead of exiting 0 for the merged group.

A decision-point marker is any of the shapes found in the corpus, case-insensitive and
fence-excluded like the tier matches themselves:

- bold, colon outside the span: `**Decision point:** Malformed-manifest posture`
- bold, colon inside the span: `**Decision point: Malformed-manifest posture**`
- heading form: `### Decision point (2+ viable resolutions)`, `### Decision Point — ENH-2495 ...`,
  `##### Decision point: what to do with ...`, bare `### Decision Point`

A heading-form marker between two same-tier blocks already ends the preceding option *span*
(via `_option_span_boundary`) but does not split the *run* today, so it merges exactly the same
way the bold form does.

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
run-splitting loop (issue_parser.py:2806-2817), and start a new run when either condition
holds, even when `tier_name == prev_tier`.

Unlike `directive_between`, **no line-number conversion is needed**: the marker matches come
from the same `body` string as `prev_pos`/`pos`, so a plain offset comparison suffices.
`directive_between` only does the `content.count("\n", ...)` dance because its split point is
precomputed document-wide as a line number. Collect marker offsets once per section body
(fence-excluded, exactly like `tagged`), then compare offsets:

```python
marker_positions = _decision_point_marker_positions(body, fences)  # sorted body offsets
...
marker_between = any(prev_pos < mp < pos for mp in marker_positions)
if tier_name == prev_tier and not directive_between and not marker_between:
    runs[-1].append(i)
else:
    runs.append([i])
```

with a module-level `_DECISION_POINT_MARKER_RE` (house convention: `_SOMETHING_RE` constant
with a provenance comment, declared above its consumer) of roughly
`^\s*(?:#{1,6}\s+)?(?:[-*]\s+)?\*{0,2}Decision point\b` under `re.MULTILINE | re.IGNORECASE`,
so all three corpus shapes listed under Expected Behavior match.

**Also trim option spans at the marker.** Today the last option of decision point 1 has its
span end at decision point 2's first `**Option A**` (`next_match_start`), so it swallows
DP2's `**Decision point:**` line. Two consequences: the reported line ranges for both groups
are off by the marker line, and a `> **Selected:**` callout placed directly under a
decision-point line (before its options) lands in the *previous* group's span and resolves
the wrong group. Fix by feeding marker offsets into the `next_start` computation passed to
`_decision_option_span()` — the span's end becomes `min(next tier match, next marker)` — so a
group's line range ends before the next decision point's marker line.

`is_group_resolved()` itself is correct per-group and needs no change — the fix belongs
entirely in group construction. Note the `### Decision Rationale` fallback clause in
`is_group_resolved()` ("section holds exactly one group under the widest tier scan") becomes
*stricter* as a side effect, since sections that used to collapse to one merged group now
count their real number of groups — that is the correct direction and needs no code change.

**Out of scope (follow-up ENH):** carrying the marker text as a `DecisionGroup.label` so the
CLI and `/ll:decide-issue`'s Phase 7b log line can name the decision point rather than only
its section heading and line range. `DecisionGroup.heading` is the *section* heading, so this
fix's output stays `Proposed Solution (lines N-M)`.

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
- `scripts/tests/test_issue_parser_unresolved.py` (`TestDecisionGroups`) — add:
  - bold-form marker splits a same-tier run (2 groups, first decided → 1 unresolved);
  - heading-form marker (`### Decision point ...`) splits a same-tier run the same way;
  - a `**Decision point:**` line inside a fenced code block does *not* split;
  - span trimming: the first group's `end_line` is before the second marker's line, and a
    `> **Selected:**` callout placed directly under the second marker resolves the *second*
    group, not the first.
- `scripts/tests/test_decide_issue_skill.py` — static prose assertions on SKILL.md only
  (e.g. `test_phase7b_gates_on_check_unresolved_decisions`); nothing to add here, listed for
  coupling awareness.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_unresolved_decisions.py` — subprocess-level CLI tests
  for `check-unresolved-decisions`; no existing fixture covers 2+ same-tier decision points
  (closest, `test_second_lower_precedence_group_exits_one_even_when_first_is_decided`, splits
  via a tier change, not a marker). Add a CLI-level fixture mirroring the new unit test to
  confirm the fix is visible through the actual CLI exit code and `--json` payload, not just
  the parser internals.

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `scripts/tests/test_builtin_loops.py` — `TestResolveDecisionOracle` (line 3420), esp.
  `test_check_residual_decision_routes_a_real_residual_to_done` (line 3576) — asserts
  `resolve-decision.yaml`'s `check_residual_decision` state's exact `action` string
  (`ll-issues check-unresolved-decisions ${context.issue_id:shell}`) and its `shell_exit`
  routing polarity. Static YAML-config assertions only (no execution) — confirmed unaffected
  by this fix, no code change needed, but genuinely coupled to the CLI's name/exit-code
  contract.

### Documentation
- N/A — `_decision_groups_in_body()` behavior isn't documented outside its own docstring and
  the BUG-3278 issue that introduced it.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1098` — `locate_unresolved_decisions` doc entry mirrors the same
  stale two-condition prose ("a maximal contiguous run of same-tier option blocks, or one
  Pattern E directive window") as the `DecisionGroup` docstring above; needs the same
  third-condition addition.

_Wiring pass added by `/ll:wire-issue` (2nd pass):_
- `docs/reference/CLI.md:2206-2228` — `#### ll-issues check-unresolved-decisions` section:
  full flag/exit-code reference (resolution-rule prose, exit codes `0`/`1`
  `UNRESOLVED_DECISIONS_REMAIN`/`2`, and a worked `--json` example). Describes tier-scan
  breadth rather than the run-splitting boundary rule, so it doesn't carry the stale
  two-condition claim — no textual correction is forced, but it's the authoritative
  flag/exit-code doc for the command and wasn't previously listed.
- `docs/reference/COMMANDS.md:266,268` — `/ll:decide-issue` entry's "Frontmatter write-back
  (conditional, BUG-3278)" paragraph describes the multi-decision-point scenario via a
  tier-change example rather than a same-tier one; no fix-driven edit forced, but a new doc
  surface describing the gate's multi-decision-point behavior.
- `docs/guides/DECISIONS_LOG_GUIDE.md:189` — ASCII workflow diagram node
  (`check-unresolved-decisions: any other decision group left?`) restating the exit-code
  gate contract; generic yes/no framing needs no correction, but is a new doc file
  referencing the contract.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `directive_between` (issue_parser.py:2806-2817) is an inline local variable computed within the run-splitting loop, not an extracted helper function — no existing `_..._between()` line-range-check helper exists anywhere in the codebase (repo-wide search; only unrelated hits: `extract_between_tags()` in `output/parse.py:30`, `_seconds_between()` in `session_store/writers.py:135`). The new `_decision_point_marker_between()` will be the first extracted function of this shape; `directive_between`'s inline computation is a structural precedent, not an existing function to literally mirror.
- The Similar Patterns claim that `_directive_decision_group()` (issue_parser.py:2842) "demonstrates the pattern of treating a prose marker as a group boundary" is only partly accurate: `_directive_decision_group()` locates the Pattern E directive and returns a standalone `DecisionGroup`, but the actual line-range boundary comparison lives in `_decision_groups_in_body()`'s inline `directive_between` (issue_parser.py:2810-2813), fed by `directive_split_line = directive_group.end_line` computed once in `_iter_decision_groups()` (issue_parser.py:2908-2916). The new helper differs further in shape: `directive_between` compares against one precomputed line number per document, while a `**Decision point:**` marker check must detect any marker line falling within the (prev, pos) range per pair.
- No existing regex/constant matches the literal `**Decision point:**` marker text anywhere in the codebase; the only related hit is a case-insensitive, unbolded `\bdecision point\b` alternative inside `_OPEN_QUESTION_SIGNAL_RE` (issue_parser.py:3092), used for open-question hedge detection — a different function and purpose, not directly reusable. Marker regexes in this module follow a module-level `_SOMETHING_RE = re.compile(...)` constant convention (e.g. `_SELECTED_CALLOUT_RE` line 1381, `_PREFERENCE_MARKER_RE` lines 2269-2277), declared above their consuming functions rather than inlined.
- The char-offset-to-1-based-line-number idiom `content.count("\n", 0, offset) + 1` recurs inline at issue_parser.py:2213-2214, 2359-2360, 2448-2449, 2767-2768, 2810/2812 — never factored into a shared helper; the new marker-detection helper should follow this same inline idiom rather than introducing a new utility.
- `scripts/tests/test_issue_parser_unresolved.py`'s `TestDecisionGroups` class (line 1187) is the convention for the regression test: import the target function inline inside the test body (not module top), build the fixture as a triple-quoted string literal in the test (not a fixture file), and assert on `len(groups)`/`groups[i].tier`/`len(groups[i].options)`/`is_group_resolved(...)`. The closest structural analog is `test_directive_splits_a_same_tier_run_into_two_groups` (lines 1304-1321, splits a same-tier run via a Pattern E directive rather than a decision-point marker). `test_two_decision_points_one_decided_leaves_one_unresolved` (lines 1380-1400) and `test_both_groups_marked_resolved_converges_to_zero` (lines 1402-1422) already cover "one decided, one not" but across a tier change, not a same-tier `**Decision point:**` marker split — no existing test reproduces BUG-3412's own shape (same tier, split only by the marker).

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Marker text varies in shape** — real-world usage of `**Decision point:**` in this codebase is not uniform: FEAT-3409's issue file (`.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`)'s `## Proposed Solution` uses colon *outside* the bold span (`**Decision point:** Malformed-manifest posture`, lines 193/203/211/221), while its own `### Decision Rationale` subsections use colon *inside* the bold span (`**Decision point: Malformed-manifest posture**`, lines 231/243/254) — the latter shape is the one `skills/decide-issue/SKILL.md:390` documents as `/ll:decide-issue`'s own disambiguator for an *already-resolved* group, a different purpose than this issue's target (splitting *unresolved* runs). A marker-detection regex needs to match both bold-span shapes to catch real corpus content.
- **No extracted `_..._between()` helper precedent** — repo-wide search for `def \w*_between\(` finds only `_seconds_between()` (`scripts/little_loops/session_store/writers.py:135`, an unrelated timestamp-diff helper). `directive_between` (issue_parser.py:2809-2813) is the only prior art for this shape, and it differs structurally from what BUG-3412 needs: it compares every pair against one `directive_split_line` computed once per document, while a `**Decision point:**` check must scan each `(prev_pos, pos)` pair's own range for a marker line.
- **Module-level `_SOMETHING_RE` convention confirmed** — every marker regex in issue_parser.py (`_SELECTED_CALLOUT_RE`, `_PREFERENCE_MARKER_RE`, `_DECISION_RATIONALE_HEADING_RE`) is declared as a module-level constant with a leading provenance comment, not compiled inline in the consuming function.
- **Char-offset-to-line-number idiom confirmed** — `content.count("\n", 0, offset) + 1` recurs inline at 5 sites (issue_parser.py:2213-2214, 2359-2360, 2448-2449, 2767-2768, 2810/2812); no shared line-number utility exists to call instead.
- **Documentation-mirroring, not a shared source** — `DecisionGroup`'s docstring (issue_parser.py:2711-2719) and `docs/reference/API.md:1086-1119`'s `locate_unresolved_decisions` entry state the same two-condition boundary rule as independent prose paraphrases of each other, not derived from one shared text — both must be edited in lockstep (already flagged under Wiring Phase).
- **Test-file conventions differ by level** — `test_issue_parser_unresolved.py`'s `TestDecisionGroups` class imports targets inline per-test and asserts on `len(groups)`/`.tier`/`.options`/`is_group_resolved(...)` directly; `test_ll_issues_check_unresolved_decisions.py` uses top-level imports and a `_cli()`/`_invoke()`/`_write_issue()`/`_issue_body()` helper set, asserting on subprocess `returncode`, the `UNRESOLVED_DECISIONS_REMAIN` stderr substring, and (for `--json`) parsed payload shape — the two levels are not interchangeable conventions.

## Program Design

### Types

- No new types; `DecisionGroup` (issue_parser.py:2711) is unchanged.

### Signatures

- `_DECISION_POINT_MARKER_RE: re.Pattern[str]` — module-level constant matching the bold and
  heading-form decision-point markers listed under Expected Behavior (`re.MULTILINE |
  re.IGNORECASE`).
- `_decision_point_marker_positions(body: str, fences: list[tuple[int, int]]) -> list[int]`
  — sorted body offsets of every fence-excluded marker match in one section body; computed
  once per `_decision_groups_in_body()` call. No `content`/`body_offset` parameters: offsets
  are compared directly against the tier matches' `prev_pos`/`pos`, which live in the same
  `body` coordinate space.

### Call Path

`ll-issues check-unresolved-decisions` -> `locate_unresolved_decisions()` ->
`_iter_decision_groups()` -> `_decision_groups_in_body()` ->
`_decision_point_marker_positions()` (new; feeds both the run split and the `next_start` span
cap passed to `_decision_option_span()`) -> `is_group_resolved()`

## Implementation Steps

1. Add `_DECISION_POINT_MARKER_RE` and `_decision_point_marker_positions()` in
   `scripts/little_loops/issue_parser.py` (offset-based, fence-excluded; see Proposed Solution).
2. Wire the marker positions into the run-splitting condition at issue_parser.py:2814 so a run
   breaks when either `directive_between` or a marker between the two matches is true.
3. Feed the marker positions into the `next_start` cap passed to `_decision_option_span()` so
   the preceding group's last option span ends before the next decision point's marker line.
4. Add the regression tests to `scripts/tests/test_issue_parser_unresolved.py` (see Tests):
   bold-form split, heading-form split, marker-inside-fence ignored, span trimmed at marker.
5. Add the CLI-level fixture to `scripts/tests/test_ll_issues_check_unresolved_decisions.py`.
6. Run `python -m pytest scripts/tests/`. Do **not** rely on FEAT-3409 as a live check: as of
   2026-09-08 its 4th decision point also carries a `> **Selected:**` callout, so the CLI
   correctly exits 0 for it regardless of this fix. The regression fixtures must carry the
   shape themselves. (Optional sanity check: after the fix, `_iter_decision_groups()` over
   FEAT-3409 with `include_approximate_tiers=True` should yield 4 `bold_label` groups, all
   resolved, instead of today's single 9-option group spanning lines 195-228.)

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

1. Create an issue whose `## Proposed Solution` section has 2+ separate
   `**Decision point:** ...` blocks, each followed by `**Option A**`/`**Option B**` bold-label
   option pairs, with no section-header-tier options and no Pattern E directive between them.
   (FEAT-3409 was the original live example but is now fully decided — see Implementation
   Steps — so a fresh fixture is required.)
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
undecided. Caught by manual inspection, not by the tool. FEAT-3409 has since been fully
decided (all 4 carry `> **Selected:**` callouts), so it no longer reproduces the bug.

## Files to Modify

- `scripts/little_loops/issue_parser.py` — `_decision_groups_in_body()` (the run-splitting
  loop, currently keyed only on `tier_name == prev_tier` and `directive_between`) needs to also
  split a run when a decision-point marker (bold or heading form) falls between two
  consecutive same-tier matches, and cap the preceding option span at that marker.
- `scripts/little_loops/issue_parser.py` — `is_group_resolved()`'s single-Selected-callout check
  is otherwise correct per-group; the fix belongs in group construction, not resolution.

## Acceptance Criteria

- A `## Proposed Solution` section with 2+ decision-point markers (bold form with the colon
  inside or outside the span, or heading form `#{1,6} Decision point ...`, case-insensitive)
  sharing the same option tier is split into separate `DecisionGroup`s by
  `_decision_groups_in_body()`.
- A marker inside a fenced code block does not split a run.
- The group preceding a marker has its last option span, and therefore its `end_line`, capped
  before the marker line; a `> **Selected:**` callout placed directly under a marker resolves
  the group that follows the marker, not the one before it.
- `ll-issues check-unresolved-decisions` exits 1 and reports the still-undecided group as
  `<section heading> (lines N-M)` with that group's own line range when only some same-tier
  decision points in a section have been decided; `--json` lists exactly the undecided groups.
- Regression tests at both levels (parser unit test in `test_issue_parser_unresolved.py`, CLI
  subprocess test in `test_ll_issues_check_unresolved_decisions.py`) reproduce the original
  FEAT-3409 shape as a self-contained fixture: 2+ same-tier decision points in one section,
  only the first decided.
- `DecisionGroup` docstring and `docs/reference/API.md`'s `locate_unresolved_decisions` entry
  both state the third run-breaking condition.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-08T21:43:40 - `c2403af4-baa0-4020-b7c5-f308571f1935.jsonl`
- `/ll:wire-issue` - 2026-09-08T21:30:55 - `a6cc555e-02ae-4e6f-81c7-e73410f8ac54.jsonl`
- `/ll:refine-issue` - 2026-09-08T21:21:21 - `a6890409-0ea2-4587-b566-5505315a74c7.jsonl`
- `/ll:wire-issue` - 2026-09-08T20:21:07 - `829655b3-be33-4d4b-a196-5c697fc23a0c.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:57:45 - `b6b6e9ca-1e9e-4589-b966-7e973d10f797.jsonl`
- `/ll:format-issue` - 2026-09-08T19:51:50 - `cb4b9ca3-dab7-4f31-8422-5d785ebaffef.jsonl`
- `/ll:capture-issue` - 2026-09-08T19:45:05 - `ce7357ff-ca14-4ec7-8141-84e7fba71ec5.jsonl`
