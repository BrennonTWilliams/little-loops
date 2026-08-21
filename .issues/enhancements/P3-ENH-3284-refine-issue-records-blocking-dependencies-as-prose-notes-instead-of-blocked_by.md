---
id: ENH-3284
type: ENH
title: refine-issue records blocking dependencies as prose notes instead of blocked_by
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:30:43Z'
completed_at: '2026-08-21T20:49:45Z'
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
confidence_score: 100
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

When a refine pass deposits a finding that names another open issue as affecting *whether or how*
this issue's proposed mechanism works, it classifies that finding as a hard dependency and writes
`blocked_by:` to frontmatter at deposit time via `ll-issues link [ID] blocked_by [BLOCKER-ID]` —
not as a hedged prose note left for a downstream gate to maybe catch.

Concretely, for the BUG-3278 case: the pass would have written `blocked_by: [BUG-3279]` and phrased
the finding as an ordering constraint ("Blocked by BUG-3279 — the span-excluding re-scan proposed
here cannot work while `options[-1].end_line` over-consumes to the end of section") rather than
"worth checking whether a fix here should share a code path with that fix". Readiness-ranked dequeue
(`ll-issues next-issue`/`next-issues`) and sprint scheduling would then correctly withhold BUG-3278
until BUG-3279 reached `done`/`cancelled`.

The prose is written in canonical phrasing alongside the write, so the three reactive consumers of
the same signal (`format-check`'s `prose_dep_drift`, `ll-issues sequence`'s unverified-prose-dep
display, and `wire-issue`'s prose-dependency gate) read the body and the frontmatter as agreeing
rather than contradicting.

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
2. Set `blocked_by:` in frontmatter (append if present) by calling `ll-issues link [ID] blocked_by
   [BLOCKER-ID]`, and state the ordering constraint plainly in the prose finding: what breaks if
   the order is violated, not "worth checking".
3. Keep `relates_to` for genuine see-also links.

The classification cue is whether the other issue changes the *correctness* of a proposed
mechanism here. "Touches the same function" is `relates_to`; "the mechanism this issue proposes
does not work until that issue lands" is `blocked_by`.

### Why the write happens at deposit time, not via canonical prose alone

Step 6 item 6 (`commands/refine-issue.md:885-892`) already instructs the pass to phrase dependency
prose canonically so `extract_prose_deps()` detects it, and Step 6.7's `prose_dep_drift` handling
(`:922-928`) then writes the edge. An obvious cheaper design is therefore "just classify, phrase
canonically, and let 6.7 do the write." **That design was considered and rejected**, because
`extract_prose_deps()` (`scripts/little_loops/issues/prose_deps.py:87`) carries three independent
suppression rules that a correctly-classified finding must clear simultaneously:

1. **Backtick suppression** (`_BACKTICK_SPAN_RE`, `:42`, ENH-3061) — `` `Blocked by BUG-3279` ``
   inside an inline code span is ignored. Findings blocks backtick identifiers routinely.
2. **Scope attribution** (`_scope_subject`, `:62-80`, BUG-3057) — if another issue ID appears
   earlier *in the same sentence or list item*, the phrase is attributed to that issue and
   excluded from the host's deps. This is fatal for exactly the BUG-3278 shape, where the finding
   names BUG-3279 in prose before any dependency clause, inside one list item.
3. **Deliberately conservative phrase list** (`_PHRASE_RE`, `:28-31`) — temporal/narrative
   phrasings ("after X", "once X", "pending X", "needs X") are excluded by design.

Missing any of the three fails **silently**: `prose_dep_drift` returns empty, 6.7's confirm loop
has nothing to confirm, and the pass reports success — reproducing the very bug this issue fixes,
one step downstream. A direct `ll-issues link` call does not depend on regex recall at all.

**Canonical phrasing is still required, as a companion to the write rather than a replacement for
it.** The write is load-bearing; the phrasing keeps the body and the frontmatter in agreement for
the three reactive consumers of the same signal (`format_check._fix_prose_deps`,
`sequence._unverified_prose_deps`, and `skills/wire-issue/prose-dependency-gate.md`). Because
`apply_link` reports `unchanged` on a duplicate edge, a later reactive sweep over an already-written
edge is a harmless no-op — the two mechanisms layer rather than conflict.

### Ambiguous middle ground: default to `relates_to`

When the classification is genuinely uncertain, **do not promote** — record `relates_to` and append
a one-line `Ordering check: <what would break if the other issue lands after this one>` note to the
finding.

Rationale, and note this is the *opposite* default from Step 6.7's `soft_dep_hard_edge` gate
(which resolves conflicts toward the soft reading because it is looking at an edge that already
exists): a spurious `blocked_by` written in confident prose has **no** detector — `soft_dep_hard_edge`
only fires when soft-dependency language shares the paragraph — and it silently withholds the issue
from readiness-ranked dequeue (`ll-issues next-issue`/`next-issues`) and sprint scheduling. A
*missed* edge stays recoverable through
`ll-issues format-check --fix --apply` and is surfaced by `ll-issues sequence`'s `⚠ prose dep …,
not in blocked_by` warning. The explicit `Ordering check:` note is what keeps a non-promoted finding
promotable by a later pass instead of losing the judgment entirely.

### Promotion moves the edge; it does not duplicate it

`apply_link` appends and never removes (`link.py:219`), so promoting an ID already listed under
`relates_to` leaves it in **both** fields — which contradicts "keep `relates_to` for genuine
see-also links" above, and is precisely the state BUG-3278 was in (BUG-3279 sat in `relates_to`).
When the blocker ID is already present in `relates_to`, promote with the move idiom rather than a
bare add — the mirror image of the demotion idiom Step 6.7's `soft_dep_hard_edge` remedy already
documents:

```bash
ll-issues link [ISSUE-ID] blocked_by [BLOCKER-ID] --unlink [ISSUE-ID] relates_to [BLOCKER-ID]
```

### Cycle refusal is a reportable outcome, not a retry

`apply_link` runs `_check_cycle()` (`link.py:212-214`, `:299-329`) and raises — exiting `1` — if the
edge would close a dependency cycle. The promotion step must not retry, force (`--force`), or
silently swallow this. On refusal: leave frontmatter untouched, keep the finding as `relates_to`
plus the `Ordering check:` note, and report the refused edge in Step 8's output so the operator can
resolve the cycle by hand. A refused cycle is a real modeling conflict between two issues, not a
transient failure.

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

- Confirmed: refine-issue has no `skills/` counterpart — a Glob over the skills tree for a
  refine-issue SKILL returns no matches. It is implemented only as `commands/refine-issue.md`, and
  the "Files to Modify" entry above already reflects that.
- Exact insertion points in `commands/refine-issue.md`: Step 6 item 6 ("Canonical dependency phrasing", ~lines 885–892) already instructs writing prose canonically so `extract_prose_deps()` can detect it, but only Step 6.7's `prose_dep_drift` handling (~lines 922–928) actually calls `ll-issues link [ID] blocked_by [ID]` — and only reactively, after the drift gate fires. There is no step in Step 3–5a's research-to-enrichment path that classifies a fresh finding as a hard dependency and promotes it at write time; a new promotion step belongs in Step 5a, alongside the other Enrichment Rules.
- `ll-issues link` (`scripts/little_loops/cli/issues/link.py`) is the only CLI that writes `blocked_by`: `apply_link()` (`:119-225`) reads existing `blocked_by`/`relates_to` (`:192-194`) and appends (`new_list = [*existing, target_id]`, `:219`) — it does not overwrite. Idempotent: re-adding an existing edge reports `unchanged` (`:208-209`). A cycle guard (`_check_cycle()`, `:299-329`) refuses an edge that would create a dependency cycle, raising and returning exit `1`. `ll-issues fold-findings` never touches frontmatter — the classification/promotion logic would be new skill-prose, with `ll-issues link` supplying only the mechanical write.
- Confirmed dependency-resolution rule: `find_issues_for_graph()` (`issue_parser.py:3483-3497`) loads the non-terminal superset, so a `blocked_by` edge to a `deferred` issue stays unresolved — matches `.claude/CLAUDE.md`'s "only `done`/`cancelled` resolve `blocked_by`/`depends_on`" rule.
- Closest existing precedent for "classify freshly-deposited content, then write a frontmatter field" is Step 5a's "Option-Count Detection" (~lines 538-557): count a structural signal, verify with a deterministic CLI probe (`ll-issues check-decidable`) before setting `decision_needed`, skip the write if the value is already correct (idempotency), and skip it entirely under `--dry-run`. A `blocked_by`-promotion step has a direct write-side analogue (`ll-issues link [ID] blocked_by [BLOCKER-ID]`, already used in Step 6.7) but no existing precedent for the *classification* judgment itself — that judgment is closer in kind to Step 6.7's `soft_dep_hard_edge` handling (~lines 965-974), which states its discriminator as a closed phrase list with an explicit default direction when signals conflict.

## Program Design

### Types
N/A — no new data shape; the promotion step operates on the `blocked_by`/`relates_to` frontmatter lists that already exist on `IssueInfo`.

### Signatures
- `apply_link(config: BRConfig, *, issue_id: str, field: str, target: str, unlink: bool = False, reciprocal: bool = False, force: bool = False, dry_run: bool = False) -> LinkResult` — the mechanical write this step must call, invoked through the `ll-issues link` CLI rather than imported; appends to the existing list rather than overwriting (`scripts/little_loops/cli/issues/link.py:119`)
- `extract_prose_deps(body: str, host_id: str | None = None) -> set[str]` — the canonical-phrasing detector Step 6.7's `prose_dep_drift` gate already runs; its three suppression rules (backtick spans, sentence-scope attribution, conservative phrase list) are why this issue writes the edge directly instead of relying on the detector to catch it (`scripts/little_loops/issues/prose_deps.py:87`)

### Call Path
`commands/refine-issue.md Step 5a` (Enrichment Rules — deposit a finding under `## Codebase Research Findings`) -> new classification step (this issue: hard-dependency vs relates_to) -> `apply_link` (`link.py:119`, invoked as `ll-issues link [ID] blocked_by [BLOCKER-ID]`) -> `find_issues_for_graph` (`issue_parser.py:3483`) -> `DependencyGraph.get_ready_issues` (`dependency_graph.py:154`)

### Decision Rules
- **Gap kind**: dependency-hardness classification — decides whether a freshly-deposited finding is promoted from prose-only to a `blocked_by:` frontmatter edge.
- **Trigger**: a finding names another open issue as affecting *how or whether* this issue's proposed mechanism works — not merely that it touches the same file or function.
- **Discriminator** (from Proposed Solution): "touches the same function" -> `relates_to`; "the mechanism this issue proposes does not work until that issue lands" -> `blocked_by`. Structurally the same shape as the existing `soft_dep_hard_edge` gate (`commands/refine-issue.md` § 6.7), which states an explicit default when signals conflict ("the soft prose is usually the accurate statement and the hard edge is the mistake").
- **Default when signals conflict**: `relates_to` (do not promote), plus a one-line `Ordering check:` note on the finding — see Proposed Solution § "Ambiguous middle ground: default to `relates_to`". This is the *opposite* direction from `soft_dep_hard_edge` because that gate inspects an edge that already exists while this rule decides whether to create one; the shared principle is that the reversible, detectable error is preferred. A spurious hard edge has no detector and stalls sprint dequeue (this issue's own Impact § Risk); a missed edge is recoverable via `format-check --fix --apply` and surfaced by `ll-issues sequence`.
- **Companion write**: the prose finding is phrased canonically (bare un-backticked ID, dependency clause in its own sentence) *in addition to* the frontmatter write, so the three reactive consumers of this signal agree with frontmatter rather than contradicting it. The phrasing is not the promotion mechanism — see Proposed Solution § "Why the write happens at deposit time, not via canonical prose alone".
- **Escape hatch / idempotency**: `apply_link` is already idempotent (`unchanged` on a duplicate edge, `link.py:208-209`) and refuses a cycle-forming edge (`_check_cycle`, `link.py:299-329`) — the new step does not reimplement either check. It decides whether to call `ll-issues link` at all, uses `--unlink` to *move* an ID already sitting in `relates_to` rather than duplicating it across both fields, and on a cycle refusal (exit `1`) falls back to `relates_to` and reports rather than retrying or forcing.
- **Mode scope**: Step 5a is Auto Mode only (`### 5a` opens with `Skip this section if AUTO_MODE is false`), so a rule placed solely there never runs for interactive refinement via Step 5b. The classification rule must be reachable from both paths — see Implementation Steps.
- **Dry-run guard**: skip the `ll-issues link` call entirely when `--dry-run` is set, reporting the edge that would have been written in the DRY RUN PREVIEW block — matching the Option-Count Detection precedent's dry-run handling in the same Enrichment Rules block.

## Implementation Steps

1. Add a dependency-classification rule to `commands/refine-issue.md` Step 5a's Enrichment Rules
   (alongside "Option-Count Detection", ~lines 538-557): when a fresh finding names another open
   issue as affecting whether or how the proposed mechanism works (not merely touching the same
   function/file), classify it as a hard dependency using the Program Design § Decision Rules
   discriminator. State the ambiguous-middle default explicitly (`relates_to` + an `Ordering check:`
   note) and say why it runs opposite to Step 6.7's `soft_dep_hard_edge` default.
2. Make the rule reachable from interactive mode too. Step 5a is Auto Mode only, so a rule written
   only there silently never runs under Step 5b. Either place the classification rule in a
   mode-independent location and have Step 5a reference it, or add a matching instruction to Step 5b
   — and state which choice was made in the rule text, so the next reader does not have to infer the
   scope from the enclosing heading.
3. On hard-dependency classification, call `ll-issues link [ID] blocked_by [BLOCKER-ID]`
   (`apply_link`, `link.py:119`) to promote the finding into frontmatter at deposit time. Use the
   move form `--unlink [ID] relates_to [BLOCKER-ID]` when the blocker is already listed under
   `relates_to`, so the ID does not end up in both fields. Skip the call under `--dry-run` and report
   the would-be edge in the DRY RUN PREVIEW block.
4. Handle cycle refusal explicitly: `_check_cycle` (`link.py:212-214`, `:299-329`) exits `1` when the
   edge would close a dependency cycle. Do not retry and do not pass `--force` — leave frontmatter
   untouched, keep the finding as `relates_to` plus the `Ordering check:` note, and report the
   refused edge in Step 8's output.
5. Write the prose finding in canonical ordering-constraint language alongside the frontmatter write
   — bare un-backticked blocker ID, dependency clause in its own sentence with no other issue ID
   preceding it in that sentence or list item (both constraints are load-bearing: see Proposed
   Solution § "Why the write happens at deposit time"). This keeps `format-check`'s `prose_dep_drift`,
   `ll-issues sequence`, and `wire-issue`'s gate agreeing with frontmatter; it is not the promotion
   mechanism.
6. Note in the rule text that `ll-issues format-check --fix --apply` (`format_check.py:118-143`,
   ENH-3247) already backfills `blocked_by` from `prose_dep_drift` reactively, and that this step
   complements it rather than replacing it — `apply_link`'s `unchanged`-on-duplicate idempotency
   makes the later reactive sweep a harmless no-op.
7. Verify: a finding matching the BUG-3278/BUG-3279 shape now sets `blocked_by` when the rule runs,
   rather than only being caught reactively by Step 6.7's `prose_dep_drift` gate; confirm
   `find_issues_for_graph` (`issue_parser.py:3483`) still treats the edge as unresolved until the
   blocker reaches `done`/`cancelled`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a sentence to the Proposed Solution or Step 5a prose noting that `ll-issues format-check
  --fix --apply` (`format_check.py:118-143`, ENH-3247) already backfills `blocked_by` from
  `prose_dep_drift` reactively — this new step complements it (proactive, deposit-time) rather
  than duplicating or superseding it; `apply_link`'s idempotency makes a later reactive sweep a
  harmless no-op. **Done** — see Proposed Solution § "Why the write happens at deposit time" and
  Implementation Steps item 6.
- Update `docs/reference/CLI.md` (`format-check` `--fix` description) and `docs/reference/API.md`
  (`prose_dep_drift` gap-class description) with a short note that `/ll:refine-issue` Step 5a can
  also write the `blocked_by` edge proactively, so the two write paths read as layered rather than
  mutually exclusive.
- Add a new test class to `scripts/tests/test_refine_issue_command.py` (e.g.
  `TestDependencyClassificationInStep5a`) asserting the promotion rule and discriminator text are
  present in the Step 5a slice, mirroring `TestOptionCountDetectionInCommand`'s slicing idiom.
- **Incidental stale reference, found while drafting this issue**: `commands/refine-issue.md:892`
  (Step 6 item 6 — the canonical-phrasing rule this issue extends) and `docs/reference/API.md:949`
  (the `prose_dep_drift` gap-class description this issue also updates) both cite an "ll-issues
  ready" subcommand that does not exist on the CLI surface — `ll-issues format-check` flags it as
  `stale_cli_flag`. The readiness-ranked surfaces are `ll-issues next-issue`/`next-issues`. Both
  citations sit in text this issue already edits, so correct them in the same pass rather than
  filing separately. (Quoted unbackticked here deliberately: the backticked form would trip the
  same `stale_cli_flag` check on this issue file.)

## Scope Boundaries

Explicitly **not** in scope:

- **No new CLI, flag, or Python mechanism.** `ll-issues link` supplies the entire write path; this
  issue adds command prose and a structural test, nothing more. In particular, do not add a
  `--promote`-style flag to `ll-issues link` or a new gap kind to `check_format_gaps`.
- **No corpus sweep.** Existing issues whose dependencies are already filed as prose notes are not
  retro-promoted. `ll-issues format-check --all --fix --apply` already covers that case reactively
  for canonically-phrased prose, and non-canonical historical prose stays out of reach by design.
- **No change to `extract_prose_deps()`'s three suppression rules.** Their conservatism is
  deliberate (FEAT-2849: "recall matters less than not crying wolf"; BUG-3057 scope attribution;
  ENH-3061 backtick spans). This issue routes around them with a direct write rather than loosening
  them — widening the regex would re-open the false-positive class those rules exist to close.
- **No consolidation of the four `ll-issues link` call sites.** Step 6.7, `format_check._fix_prose_deps`,
  `skills/wire-issue/prose-dependency-gate.md`, and this new step remain independent; idempotency is
  what makes that safe. Deduplicating them is a separate refactor with its own risk.
- **No `depends_on` handling.** Only `blocked_by` is written. `depends_on` is left to whatever
  already sets it.
- **Not a decision-drift or option-location change.** This issue is unrelated to EPIC-3290's
  `locate_enumerable_options`/`_unapplied_decision` work despite sharing BUG-3278/BUG-3279 as
  motivating examples.

## Acceptance Criteria

1. `commands/refine-issue.md` contains a dependency-classification rule stating the
   `blocked_by`-vs-`relates_to` discriminator and naming `relates_to` as the explicit default when
   signals conflict.
2. The rule instructs calling `ll-issues link [ID] blocked_by [BLOCKER-ID]`, with the
   `--unlink … relates_to …` move form specified for the case where the blocker already sits in
   `relates_to`.
3. The rule specifies the cycle-refusal branch (no retry, no `--force`, fall back to `relates_to`,
   report in Step 8) and the `--dry-run` skip.
4. The rule requires canonical prose phrasing as a companion to the write, and states that it is a
   companion rather than the mechanism.
5. The rule is reachable from both auto and interactive refinement paths, with its mode scope stated
   in the text rather than left implicit in the enclosing heading.
6. `scripts/tests/test_refine_issue_command.py` gains a test class asserting 1–5 are present in the
   relevant command slice, mirroring `TestOptionCountDetectionInCommand`'s slicing idiom.
7. `docs/reference/CLI.md` (`format-check --fix`) and `docs/reference/API.md` (`prose_dep_drift`)
   each note that `/ll:refine-issue` can also write the edge proactively, so the two write paths read
   as layered rather than mutually exclusive.
8. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — the information survives either way; this makes it actionable
- **Effort**: Small–Medium — command prose plus a structural test and two doc notes. Larger than the
  original "prose change, no new mechanism" estimate because the rule must also specify the
  cycle-refusal branch, the dry-run guard, the move-vs-duplicate semantics, and its own mode scope.
- **Risk**: Low-Medium — over-eager promotion produces spurious `blocked_by` edges that stall
  sprint dequeue, and no gate detects a confidently-worded spurious edge (`soft_dep_hard_edge` only
  fires when soft-dependency language shares the paragraph). The correctness-based discriminator plus
  the `relates_to` default for the ambiguous middle is what keeps it bounded.
- **Breaking Change**: No

## Related Key Documentation

- BUG-3278 / BUG-3279 — the pair where the hard dependency was filed as a soft note
- `.claude/CLAUDE.md` § Issue File Format — deferral discriminator and which statuses resolve a
  `blocked_by` edge

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-21T20:49:24 - `d06c9128-4ee6-4f06-925c-39933c980b0a.jsonl`
- `/ll:ready-issue` - 2026-08-21T20:32:44 - `a458e22b-0d75-42ff-afce-7b1dde09ba9a.jsonl`
- `/ll:confidence-check` - 2026-08-21T20:28:41 - `f43edb41-c89c-4b7e-9e53-d33ec1f5029d.jsonl`
- `/ll:confidence-check` - 2026-08-21T20:13:37 - `e2e1442c-6810-4106-ac77-209e0a6a894d.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:16:11 - `3f6ddaa1-8943-4e02-80c6-991ae42bf623.jsonl`
- `/ll:reconcile-issue` - 2026-08-21T18:07:51 - `73da6192-349c-4cd0-b9a2-b714f2801296.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:46:16 - `60a158f1-d190-4921-8534-c9c523505485.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
