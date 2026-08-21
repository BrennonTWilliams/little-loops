---
id: ENH-3284
type: ENH
title: refine-issue records blocking dependencies as prose notes instead of blocked_by
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:30:43Z'
reconcile_attempted: true
labels:
- refine-issue
- skills
- dependencies
- frontmatter
relates_to:
- BUG-3282
- BUG-3278
- BUG-3279
confidence_score: 85
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3284: refine-issue records blocking dependencies as prose notes instead of blocked_by

## Summary

When `/ll:refine-issue` discovers that another open issue blocks the one it is refining, it writes
the finding as a hedged prose bullet in `## Codebase Research Findings` rather than setting
`blocked_by:` in frontmatter. The dependency is recorded but not machine-readable, so no gate,
loop, or sprint scheduler can act on it.

## Current Behavior

`refine-issue` appends findings as prose under `## Codebase Research Findings`, using
recommendation language ("worth checking whether…", "may share a code path with…"). Nothing in the
pass promotes a discovered hard dependency into the `blocked_by:` frontmatter field, even though
the field exists and is consumed by dependency resolution (only `done`/`cancelled` resolve a
`blocked_by` edge — see `.claude/CLAUDE.md` § Issue File Format).

Observed on BUG-3278 (2026-08-21). Refinement recorded:

> `locate_enumerable_options`/`_unapplied_decision` (same two functions this bug touches) carry a
> separately-tracked sibling span-boundary defect: BUG-3279 … — worth checking whether a fix here
> should share a code path with that fix [pattern-finder finding].

That undersells it. BUG-3278's proposed fix at the time was a span-excluding re-scan over
`options[0].start_line`–`options[-1].end_line`. BUG-3279 is precisely that the final option's
`end_line` over-consumes to the end of its section — measured on ENH-3277, `options[-1].end_line`
is 435 while the section runs to ~546, so the excluded span swallows the very region the surviving
decision lives in. The proposed fix was unimplementable until BUG-3279 landed. The issue's
frontmatter listed BUG-3279 under `relates_to:` only.

## Expected Behavior

[What should happen instead]

## Motivation

`relates_to` and `blocked_by` are not interchangeable: the first is a reading hint, the second is
a scheduling constraint. An ordering requirement filed as prose is invisible to
`ll-issues`-driven dependency resolution and to the FSM loops that dequeue by readiness, so an
issue can be picked up, implemented against a broken primitive, and fail late — or worse, ship a
fix that silently doesn't work.

The information was already in the file. Only its encoding was wrong.

## Proposed Solution

Extend the refine pass with a promotion step:

1. When a finding names another issue as affecting *how or whether* this issue can be implemented
   — not merely as related context — classify it as a hard dependency.
2. Set `blocked_by:` in frontmatter (append if present) and state the ordering constraint plainly
   in the prose finding: what breaks if the order is violated, not "worth checking".
3. Keep `relates_to` for genuine see-also links.

The classification cue is whether the other issue changes the *correctness* of a proposed
mechanism here. "Touches the same function" is `relates_to`; "the mechanism this issue proposes
does not work until that issue lands" is `blocked_by`.

## Integration Map

### Files to Modify

- `commands/refine-issue.md` Step 5a (Enrichment Rules, alongside the existing "Option-Count
  Detection" rule at ~lines 538-557) — new dependency-classification and `blocked_by`-promotion
  step, calling `ll-issues link [ID] blocked_by [BLOCKER-ID]` (the mechanical write Step 6.7's
  `prose_dep_drift` handling at ~lines 922-928 already uses reactively)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py:118-143` (`_fix_prose_deps`, ENH-3247) —
  **an existing reactive repair already does this mechanical write**: `ll-issues format-check
  --fix --apply` backfills `blocked_by` from `prose_dep_drift` by calling `cmd_link` in-process,
  today. It is not mentioned anywhere in this issue's current text (confirmed via grep — zero
  matches for ENH-3247). This issue's Step 5a step is a *proactive, deposit-time* classification;
  `_fix_prose_deps` is a *reactive, post-write, sweep-capable* repair — genuinely different points
  in the pipeline, but the Proposed Solution/Implementation Steps should say explicitly that Step
  5a complements (not replaces) this existing mechanism, since `apply_link`'s idempotency
  (`link.py:208-209`, "unchanged" on a duplicate edge) makes the reactive sweep a harmless no-op
  once Step 5a has already written the edge [Agent 1, Agent 2 finding].
- `scripts/little_loops/cli/issues/sequence.py:15-44` (`_unverified_prose_deps`) — a read-only
  consumer that re-derives the same drift classification (terminal/structured exclusions) for
  `ll-issues sequence`'s display (`⚠ prose dep ..., not in blocked_by`). Once Step 5a promotes a
  finding at deposit time, this warning naturally stops firing for that edge — no code change
  needed here, but it's a third site with an opinion on the same signal [Agent 1 finding].
- `skills/wire-issue/prose-dependency-gate.md` (FEAT-2849, Phase 3.7) — a third existing site with
  the same reactive pattern this issue proposes to make proactive: it also instructs adding a
  `blocked_by` edge via `ll-issues link` when `prose_dep_drift` fires, downstream in the wire-issue
  pass. Worth a cross-reference so the two passes aren't read as independently reinventing the same
  rule [Agent 1 finding].
- `commands/reconcile-issue.md:214-219` — already documents the "canonical dependency phrasing"
  contract (paraphrases are invisible to `extract_prose_deps()`) but does not itself call
  `ll-issues link`; no code change required, listed for cross-reference only [Agent 1 finding].

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`format-check` section, `--fix`/`--all --fix --apply` description) and
  `docs/reference/API.md` (`check_format_gaps`'s `prose_dep_drift` gap-class description) — neither
  is factually broken by this change, but both currently read as though `format-check --fix` is the
  *only* route by which a `blocked_by` edge gets written from a prose claim. Add a short clarifying
  note that `/ll:refine-issue` Step 5a can also write the edge proactively at deposit time, so the
  two mechanisms read as layered (reactive safety net + proactive write) rather than mutually
  exclusive [Agent 2 finding].

### Tests

- Skill-prose assertions for the promotion step and the `blocked_by` vs `relates_to` discriminator,
  following the structural convention used for LLM-executed skills

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — the existing structural-test file for
  `commands/refine-issue.md`. Add a new test class here (e.g. `TestDependencyClassificationInStep5a`)
  mirroring `TestOptionCountDetectionInCommand`'s slicing idiom (`content.index("### 5a. Fill Gaps
  with Research Findings")` to `"### 5b. Interactive Refinement"`) — this is the file to update,
  not a new file [Agent 3 finding].
- Confirmed clean (no action needed): `apply_link`/`cmd_link` idempotency and cycle-guard are
  already covered by `test_link_cli.py` (`test_link_is_idempotent_no_duplicate_entry`,
  `test_link_cycle_refused_nonzero_exit`) and `test_ll_issues_format_check.py::TestFormatCheckFix::
  test_fix_apply_is_idempotent` — calling `ll-issues link` twice (once from `format-check --fix`,
  once from this new Step 5a step) is safe by construction; no new idempotency test is required
  [Agent 2, Agent 3 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Confirmed: `skills/refine-issue/SKILL.md` does not exist (`Glob skills/refine-issue/**` returns no matches). Refine-issue is implemented only as `commands/refine-issue.md` — the "Files to Modify" line above has been annotated accordingly.
- Exact insertion points in `commands/refine-issue.md`: Step 6 item 6 ("Canonical dependency phrasing", ~lines 885–892) already instructs writing prose canonically so `extract_prose_deps()` can detect it, but only Step 6.7's `prose_dep_drift` handling (~lines 922–928) actually calls `ll-issues link [ID] blocked_by [ID]` — and only reactively, after the drift gate fires. There is no step in Step 3–5a's research-to-enrichment path that classifies a fresh finding as a hard dependency and promotes it at write time; a new promotion step belongs in Step 5a, alongside the other Enrichment Rules.
- `ll-issues link` (`scripts/little_loops/cli/issues/link.py`) is the only CLI that writes `blocked_by`: `apply_link()` (`:119-225`) reads existing `blocked_by`/`relates_to` (`:192-194`) and appends (`new_list = [*existing, target_id]`, `:219`) — it does not overwrite. Idempotent: re-adding an existing edge reports `unchanged` (`:208-209`). A cycle guard (`_check_cycle()`, `:299-329`) refuses an edge that would create a dependency cycle, raising and returning exit `1`. `ll-issues fold-findings` never touches frontmatter — the classification/promotion logic would be new skill-prose, with `ll-issues link` supplying only the mechanical write.
- Confirmed dependency-resolution rule: `find_issues_for_graph()` (`issue_parser.py:3367-3386`) loads the non-terminal superset, so a `blocked_by` edge to a `deferred` issue stays unresolved — matches `.claude/CLAUDE.md`'s "only `done`/`cancelled` resolve `blocked_by`/`depends_on`" rule.
- Closest existing precedent for "classify freshly-deposited content, then write a frontmatter field" is Step 5a's "Option-Count Detection" (~lines 538-557): count a structural signal, verify with a deterministic CLI probe (`ll-issues check-decidable`) before setting `decision_needed`, skip the write if the value is already correct (idempotency), and skip it entirely under `--dry-run`. A `blocked_by`-promotion step has a direct write-side analogue (`ll-issues link [ID] blocked_by [BLOCKER-ID]`, already used in Step 6.7) but no existing precedent for the *classification* judgment itself — that judgment is closer in kind to Step 6.7's `soft_dep_hard_edge` handling (~lines 965-974), which states its discriminator as a closed phrase list with an explicit default direction when signals conflict.

## Program Design

### Types
N/A — no new data shape; the promotion step operates on the `blocked_by`/`relates_to` frontmatter lists that already exist on `IssueInfo`.

### Signatures
- `apply_link(source_id, field, target_id) -> LinkResult` — the mechanical write this step must call; appends to the existing list rather than overwriting (`link.py:119`)
- `extract_prose_deps(body) -> list[ProseDep]` — the canonical-phrasing detector Step 6.7's `prose_dep_drift` gate already runs; a promotion step written at deposit time makes this detector's reactive catch redundant for findings this pass writes (`prose_deps.py:87`)

### Call Path
`commands/refine-issue.md Step 5a` (Enrichment Rules — deposit a finding under `## Codebase Research Findings`) -> new classification step (this issue: hard-dependency vs relates_to) -> `apply_link` (`link.py:119`, invoked as `ll-issues link [ID] blocked_by [BLOCKER-ID]`) -> `find_issues_for_graph` (`issue_parser.py:3367`) -> `DependencyGraph.get_ready_issues` (`dependency_graph.py:154`)

### Decision Rules
- **Gap kind**: dependency-hardness classification — decides whether a freshly-deposited finding is promoted from prose-only to a `blocked_by:` frontmatter edge.
- **Trigger**: a finding names another open issue as affecting *how or whether* this issue's proposed mechanism works — not merely that it touches the same file or function.
- **Discriminator** (from Proposed Solution): "touches the same function" -> `relates_to`; "the mechanism this issue proposes does not work until that issue lands" -> `blocked_by`. Structurally the same shape as the existing `soft_dep_hard_edge` gate (`commands/refine-issue.md` § 6.7), which states an explicit default when signals conflict ("the soft prose is usually the accurate statement and the hard edge is the mistake") — a `blocked_by`-promotion rule needs the same kind of explicit default for the ambiguous middle ground, or it inherits `soft_dep_hard_edge`'s stated risk in reverse (spurious hard edges that stall sprint dequeue, named in this issue's own Impact § Risk).
- **Escape hatch / idempotency**: `apply_link` is already idempotent (`unchanged` on a duplicate edge) and refuses a cycle-forming edge (`_check_cycle`, `link.py:299`) — the new step does not need to reimplement either check, only decide whether to call `ll-issues link` at all.

## Implementation Steps

1. Add a dependency-classification rule to `commands/refine-issue.md` Step 5a's Enrichment Rules
   (alongside "Option-Count Detection", ~lines 538-557): when a fresh finding names another open
   issue as affecting whether or how the proposed mechanism works (not merely touching the same
   function/file), classify it as a hard dependency using the Program Design § Decision Rules
   discriminator, with an explicit default for the ambiguous middle ground — mirroring Step 6.7's
   `soft_dep_hard_edge` gate, which states its own default when signals conflict.
2. On hard-dependency classification, call `ll-issues link [ID] blocked_by [BLOCKER-ID]`
   (`apply_link`, `link.py:119` — already idempotent and cycle-guarded, `_check_cycle`,
   `link.py:299`) to promote the finding into frontmatter at deposit time, and write the prose
   finding in plain ordering-constraint language (what breaks if the order is violated) instead of
   hedged "worth checking" phrasing.
3. Verify: a finding matching the BUG-3278/BUG-3279 shape now sets `blocked_by` when Step 5a runs,
   rather than only being caught reactively by Step 6.7's `prose_dep_drift` gate; confirm
   `find_issues_for_graph` (`issue_parser.py:3367`) still treats the edge as unresolved until the
   blocker reaches `done`/`cancelled`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a sentence to the Proposed Solution or Step 5a prose noting that `ll-issues format-check
  --fix --apply` (`format_check.py:118-143`, ENH-3247) already backfills `blocked_by` from
  `prose_dep_drift` reactively — this new step complements it (proactive, deposit-time) rather
  than duplicating or superseding it; `apply_link`'s idempotency makes a later reactive sweep a
  harmless no-op.
- Update `docs/reference/CLI.md` (`format-check` `--fix` description) and `docs/reference/API.md`
  (`prose_dep_drift` gap-class description) with a short note that `/ll:refine-issue` Step 5a can
  also write the `blocked_by` edge proactively, so the two write paths read as layered rather than
  mutually exclusive.
- Add a new test class to `scripts/tests/test_refine_issue_command.py` (e.g.
  `TestDependencyClassificationInStep5a`) asserting the promotion rule and discriminator text are
  present in the Step 5a slice, mirroring `TestOptionCountDetectionInCommand`'s slicing idiom.

## Impact

- **Priority**: P3 — the information survives either way; this makes it actionable
- **Effort**: Small — prose change to the skill, no new mechanism
- **Risk**: Low-Medium — over-eager promotion produces spurious `blocked_by` edges that stall
  sprint dequeue. The correctness-based discriminator is what keeps it bounded.
- **Breaking Change**: No

## Related Key Documentation

- BUG-3278 / BUG-3279 — the pair where the hard dependency was filed as a soft note
- `.claude/CLAUDE.md` § Issue File Format — deferral discriminator and which statuses resolve a
  `blocked_by` edge

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by the Parity/Claim/Structure gate: the
  `## Expected Behavior` section is still the literal unfilled template placeholder
  (`[What should happen instead]`), flagged by `format-check` as both `template_placeholders` and
  `boilerplate`.
- `## Scope Boundaries` is entirely missing — no "what we're NOT doing" section, though the
  Program Design § Decision Rules discriminator partially substitutes for it.
- Two Program Design § Signatures citations have inaccurate return types/parameters:
  `apply_link` is stated as `(source_id, field, target_id) -> LinkResult` but the actual signature
  is `apply_link(config, *, issue_id, field, target, unlink=False, reciprocal=False, force=False,
  dry_run=False) -> LinkResult` (`link.py:119`); `extract_prose_deps` is stated as
  `(body) -> list[ProseDep]` but the actual signature is
  `extract_prose_deps(body: str, host_id: str | None = None) -> set[str]` (`prose_deps.py:87`).
  Neither trips the Program Design gate (which checks for a signature-shaped line and a
  resolvable Call Path, not parameter accuracy), but an implementer following these signatures
  literally would write against the wrong contract.
- Criterion C notes that "an explicit default for the ambiguous middle ground" is *needed* for
  the new classification rule but does not itself specify what that default is (only that it
  should mirror `soft_dep_hard_edge`'s stated bias) — left as a judgment call for implementation.
- `format-check` flags this issue file itself with `unmarked_superseded_directive`: the Codebase
  Research Findings body contains a correction phrase ("does not exist") with no `⚠ Superseded`
  marker in a directive section. Appears to be a gate false-positive here — the Files to Modify
  section was already updated to reflect the finding — but worth a marker or it will keep
  resurfacing in format-check sweeps.

## Session Log
- `/ll:confidence-check` - 2026-08-21T20:13:37 - `e2e1442c-6810-4106-ac77-209e0a6a894d.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:16:11 - `3f6ddaa1-8943-4e02-80c6-991ae42bf623.jsonl`
- `/ll:reconcile-issue` - 2026-08-21T18:07:51 - `73da6192-349c-4cd0-b9a2-b714f2801296.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:46:16 - `60a158f1-d190-4921-8534-c9c523505485.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
