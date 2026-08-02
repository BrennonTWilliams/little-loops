---
id: BUG-3002
title: autodev routes design_gate_failed to reconcile-issue, whose contract excludes
  the Program Design section
type: BUG
priority: P2
captured_at: '2026-08-02T15:46:46Z'
completed_at: '2026-08-02T19:28:04Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- autodev
- reconcile-issue
- program-design-gate
relates_to:
- BUG-3001
- BUG-3003
status: done
testable: true
depends_on:
- BUG-3001
- BUG-3003
decision_needed: false
confidence_score: 98
outcome_confidence: 82
score_complexity: 16
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 19
---

# BUG-3002: autodev routes design_gate_failed to reconcile-issue, whose contract excludes the Program Design section

## Summary

`autodev.yaml` computes the same deterministic `DESIGN_FAIL` check in three
states and, on failure, applies exactly one automated remedy —
`/ll:reconcile-issue` via `reconcile_current` — before deferring the issue with
reason code `design_gate_failed`.

`commands/reconcile-issue.md:44-47` states, as a binding contract, "Rewrite
ONLY these three directive sections: `## Implementation Steps`,
`## Acceptance Criteria`, `### Files to Modify`." `## Program Design` is not
among them, and the file contains zero occurrences of "Program Design". The
remedy is structurally incapable of touching the section whose failure
triggered it, so the reconcile attempt burns a full skill invocation, the
re-check fails identically, and the issue defers.

## Steps to Reproduce

1. In a stamped project (`.ll/program-design-cutover.json` present — this repo
   is stamped `2026-07-30`), queue an issue whose `## Program Design` is
   missing, empty, or prose-only and whose readiness/outcome scores otherwise
   pass.
2. Run `ll-loop run autodev` (or `ll-auto`) so the issue reaches
   `recheck_after_size_review` or `regate_after_atomic_remediation`.
3. Observe the run: `DESIGN_FAIL=true` → `check_atomic_design_remedy` →
   `reconcile_current` → `/ll:reconcile-issue <ID>` → re-check → still
   `DESIGN_FAIL=true` → `ll-issues set-status <ID> deferred --by automation
   --reason design_gate_failed`.
4. Confirm via `git diff` on the issue file that `## Program Design` is
   byte-identical before and after the reconcile pass.

## Current Behavior

Three states independently compute the identical `DESIGN_FAIL` shell block
(`ll-issues format-check --format json`, then a `python3 -c` reading
`program_design_nonspecific` / `Program Design` in `missing` / `empty`):

| State | Line | On `DESIGN_FAIL` |
|---|---|---|
| `recheck_scores` | ~1090 | no local deferral; routes on toward the size-review recheck |
| `regate_after_atomic_remediation` | 1586 | → `check_atomic_design_remedy` (`:1669`) → `reconcile_current` (`:1688`); defers `design_gate_failed` at `:1654-1656` if reconcile already attempted |
| `recheck_after_size_review` | 1735 | same shape; defers `design_gate_failed` at `:1837-1839` |

Both deferring states force reconcile as the remedy, explicitly bypassing the
general spike-vs-reconcile heuristic used elsewhere for readiness remediation.
The `regate_after_atomic_remediation` comment (`:1598-1603`) documents the
intent plainly: "it routes once through the shared reconcile remedy via
`check_atomic_design_remedy`/`reconcile_current`, and only defers
`design_gate_failed` (never `oversized_atomic`) if reconcile was already
attempted."

`reconcile_current` (`:1688-1703`) is a pure dispatch state — its own comment
notes "the state owns no rewrite logic — only the call and routing" — so the
capability question resolves entirely in `commands/reconcile-issue.md`, which
excludes the section by contract.

Net effect: for the `design_gate_failed` class specifically, autodev has
detection and deferral but no working remedy. It spends one
`/ll:reconcile-issue` invocation per affected issue to reach a foregone
conclusion.

## Expected Behavior

An issue that fails only the Program Design gate should have at least one
automated remedy that can actually write the section, and should defer with
`design_gate_failed` only after that remedy has genuinely been attempted and
failed.

## Root Cause

The ENH-2870 wiring that added the `DESIGN_FAIL` hard-AND to the three gate
states reused the existing `reconcile_current` remedy path (introduced by
ENH-2689 for the plateau case) without checking whether
`/ll:reconcile-issue`'s section scope covers Program Design. It does not — its
frontmatter `description` and its `## Contract (read this first — it is
binding)` block both enumerate three sections, none of which is Program
Design.

The upstream half of the same defect is BUG-3001: `/ll:refine-issue` — the
*other* command the gate prescribes — has the same blind spot. Neither
prescribed remedy writes the section.

## Proposed Solution

Two viable routes; they are not mutually exclusive but option A is the smaller
and more honest change.

**A. Retarget the remedy (preferred, contingent on BUG-3001).** Once
`/ll:refine-issue` populates Program Design (BUG-3001), point the
`design_gate_failed` remedy at refine instead of reconcile. This means a new
remedy state (or a parameterized variant of the existing refine dispatch)
reached from `check_atomic_design_remedy`, leaving `reconcile_current`
untouched for the plateau case it was built for. Keeps each skill's contract
intact and creates a real dependency: BUG-3002 should land after BUG-3001.

**B. Widen reconcile's contract.** Add `## Program Design` as a fourth
rewritable directive section in `commands/reconcile-issue.md`, updating the
frontmatter `description`, the binding contract block (`:42-77`), the
Step 5 rewrite instructions (`:144-171`), and the `SECTIONS_REWRITTEN` output
block (`:205`). Defensible — Program Design is directive in the same sense the
other three are, and reconcile already reads the accumulated research findings
that would source it. But it duplicates BUG-3001's enrichment logic in a
second command.

Either way, the three duplicated `DESIGN_FAIL` shell blocks are a maintenance
liability worth collapsing (they are copy-pasted `python3 -c` heredocs); a
shared fragment or an `ll-issues` subcommand returning the verdict directly
would make the next change to this predicate a one-site edit. That cleanup is
separable and should not block the remedy fix.

### Codebase Research Findings

_Added by `/ll:refine-issue` — formatting the decision point above for
machine visibility:_

**Option A**: Retarget the remedy (contingent on BUG-3001).

> **Selected:** Option A — matches the existing `run_spike`/`reconcile_current` dispatch template exactly (reuse score 3/3 vs. 1/3), while Option B asks `reconcile-issue` to author signature/call-path content its own contract explicitly excludes as refine's job.

Once
`/ll:refine-issue` populates Program Design (BUG-3001), point the
`design_gate_failed` remedy at refine instead of reconcile — a new remedy
state (or a parameterized variant of the existing refine dispatch) reached
from `check_atomic_design_remedy`, leaving `reconcile_current` untouched for
the plateau case it was built for. Keeps each skill's contract intact and
creates a real dependency: BUG-3002 should land after BUG-3001.

**Option B**: Widen reconcile's contract. Add `## Program Design` as a fourth
rewritable directive section in `commands/reconcile-issue.md`, updating the
frontmatter `description`, the binding contract block (`:42-77`), the Step 5
rewrite instructions (`:144-171`), and the `SECTIONS_REWRITTEN` output block
(`:205`). Defensible — Program Design is directive in the same sense the
other three are, and reconcile already reads the accumulated research
findings that would source it. Duplicates BUG-3001's enrichment logic in a
second command.

**Recommended**: Option A — the smaller and more honest change; keeps each
skill's contract intact rather than widening reconcile's scope. Contingent on
BUG-3001 landing first.

### Decision Rationale

**Selected**: Option A — retarget the `design_gate_failed` remedy from
`reconcile_current` to a new `refine_for_design` state, contingent on BUG-3001.

**Reasoning**: The `check_atomic_design_remedy` → `reconcile_current` dispatch
(`autodev.yaml:1669-1704`) is a thin, single-edge router that already mirrors
`run_spike`'s exact rate-limit/counter/confidence-recheck template
(`with_rate_limit_handling` + `count_repair_cycle_*` + confidence-recheck
successor), a shape used five times in the file. Adding a parallel
`refine_for_design` state requires no structural deviation from established
convention and leaves `reconcile_current` untouched for the plateau case it
was built for. Option B, by contrast, asks `reconcile-issue` to author
signature- and resolvable-call-path-level content
(`grade_program_design`/`_SIG_CALL`/`_SIG_FIELD`) that its own contract
explicitly excludes as refine's job ("do not go re-research the codebase —
that is `/ll:refine-issue`'s job", `reconcile-issue.md:67-68`) — a scope
violation in kind, not just size.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 2 | 1 |
| Testability | 3 | 2 |
| Risk | 2 | 1 |
| **Total** | **10/12** | **5/12** |

**Key evidence**:
- `autodev.yaml:1194-1223` (`run_spike`) and `:1688-1716` (`reconcile_current`)
  share an identical rate-limit/counter/recheck template — the house pattern
  a new `refine_for_design` state would follow verbatim.
- `commands/reconcile-issue.md:67-68` explicitly disclaims re-research as
  out of scope, which is precisely what authoring Program Design requires.
- `scripts/little_loops/issues/program_design.py:271-342` shows Program
  Design authoring needs `git_grep_resolver`-verified call-path anchors —
  categorically more research-heavy than reconciling existing prose.
- Risk on Option A is real but bounded: it is a sequencing dependency on
  BUG-3001 landing first, not a scope violation, and BUG-3001's own
  Integration Map already names this issue's states as downstream scope.

## Program Design

### Deviations

_2026-08-02, `/ll:manage-issue`:_ `dispatch_design_remedy` clears
`autodev-pre-deferral-remedy.txt` on the `refine_design` match (exit-0 branch),
rather than reading it non-destructively as originally specified. Tracing the
full loop back through `check_pre_deferral_remedy` showed the non-destructive
read as designed would replay the remedy dispatch indefinitely: once
`recheck_after_size_review` eventually defers as `design_gate_failed`, that
branch also `exit 1`s through the same `on_no: check_pre_deferral_remedy` edge,
which would see the un-cleared token still present and re-fire
`refine_for_design` on every subsequent pass. Clearing the token only on the
match preserves non-destructive behavior for every other token (spike,
reconcile, empty), which still falls through unchanged to
`dispatch_pre_deferral_remedy` for it to consume itself.

Option A requires no Python signature change — the fix is FSM routing plus one
new `autodev.yaml` state. Three constraints drive the shape, each established
by tracing the current graph rather than by the original ENH-2870 comments:

**(a) There are two remedy routes, not one.** Only
`regate_after_atomic_remediation` reaches the remedy via
`check_atomic_design_remedy`. `recheck_after_size_review` writes the literal
token `reconcile` into `autodev-pre-deferral-remedy.txt` (`:1829`) and routes
`on_no → check_pre_deferral_remedy` (`:1924`) → `dispatch_pre_deferral_remedy`
(`:1941`), whose `on_no: reconcile_current` is the catch-all. Retargeting only
`check_atomic_design_remedy.on_yes` leaves the more common path unfixed.

**(b) The one-shot guard is reconcile-specific — but only the regate route
depends on it.** Both branches arm only when frontmatter
`reconcile_attempted != true` (`:1646-1649`, `:1824-1828`) — a flag
`/ll:reconcile-issue` writes and `/ll:refine-issue` does not. The consequence
is asymmetric, and an earlier draft of this issue overstated it:

- **Regate route** — `regate_after_atomic_remediation` has no run-dir fired
  marker of its own, so `reconcile_attempted` is the *only* thing stopping it
  from re-arming. Retargeting without a replacement guard makes the
  `design_gate_failed` deferral at `:1654` unreachable there.
- **Recheck route** — already bounded by the run-dir marker
  `autodev-pre-deferral-remedy-fired` (`:1821`, cleared at `dequeue_next`),
  independent of any frontmatter flag. On a second visit the marker exists, so
  the branch falls straight through to the `design_gate_failed` deferral at
  `:1837` even with no guard swap at all.

A replacement marker is therefore still warranted, but for two narrower
reasons: arming the regate route's one-shot, and deduplicating *across* the two
routes so an issue cannot burn one refine pass per route.

Note also that the design branch (`:1821`) and the general readiness branch
(`:1881`) share the single `autodev-pre-deferral-remedy-fired` file, so a fired
design remedy already suppresses the readiness remedy for that issue. This is
pre-existing behavior and needs no change, but the new marker sits alongside it
and should not be confused with it.

**(c) The remedy must be additive.** `--full-rewrite` escapes the triage that
blocks enrichment (BUG-3003) but consumes `max_refine_count`
(`refine-issue.md:688` — "Gap-analysis runs (`--gap-analysis`) do NOT count
against `max_refine_count` … Only full-rewrite passes … consume the refinement
budget") and rewrites sections wholesale — a rewrite cycle on a
repeatedly-deferred issue. The correct call is `--auto --gap-analysis`,
matching `run_refine`'s existing precedent (`autodev.yaml:767`); Step 5a is
gated on `AUTO_MODE`, not on gap-analysis, so it runs and writes the section
under its Preservation Rule (`refine-issue.md:470`) once BUG-3003 makes the
analyzer axis unmet.

### Signatures

Existing Python surfaces the three `DESIGN_FAIL` blocks consume, unchanged:

- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/format_check.py:158`) — emits the JSON the
  shell blocks parse
- `check_format_gaps(...) -> FormatGaps`
  (`scripts/little_loops/issue_parser.py:316`) — owns
  `FormatGaps.program_design_nonspecific` (`:251`)
- `cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/set_status.py:20`) — writes the
  `design_gate_failed` deferral

New FSM states (YAML, so no Python signature):

- `refine_for_design:` — `action_type: slash_command`,
  `action: "/ll:refine-issue ${captured.input.output} --auto --gap-analysis"`,
  `fragment: with_rate_limit_handling`, `next`/`on_error:
  count_repair_cycle_refine_for_design`, `on_rate_limit_exhausted: done`, and a
  `pruning_profile` (MR-12 WARNs without one) copied verbatim from `run_refine`
  (`:772-775`): `enabled: true`, `name: refine-issue-repair`,
  `suppress_claude_md: true` — same skill, same repair context, so the same
  profile applies. Structurally modeled on `reconcile_current` (`:1688-1703`);
  flag set modeled on `run_refine` (`:761-779`).
- `count_repair_cycle_refine_for_design:` — increments the shared
  `autodev-repair-cycle-count.txt`, `next: rerun_confidence_after_reconcile`
  (that state is remedy-agnostic: it re-runs `/ll:confidence-check` and falls
  into `recheck_after_size_review`; reuse it rather than adding a sixth
  near-identical rerun state, and update its ENH-2689 comment accordingly).
- `dispatch_design_remedy:` — a gate chained **before**
  `dispatch_pre_deferral_remedy`, reached from `check_pre_deferral_remedy.on_yes`
  (`:1937`). It reads `autodev-pre-deferral-remedy.txt` **non-destructively** and
  exits 0 for `refine_design` → `refine_for_design`, 1 otherwise →
  `dispatch_pre_deferral_remedy` (which then consumes the token and dispatches
  spike/reconcile exactly as today).

  ⚠ It must be chained *before*, not after. `dispatch_pre_deferral_remedy`
  `rm -f`s the token file at `:1953` immediately after reading it, so a gate
  placed downstream would always read empty and fall to `reconcile_current` —
  silently reproducing this bug in a new state. Chaining before also leaves
  `dispatch_pre_deferral_remedy` byte-identical, which is what makes the
  plateau-path no-regression criterion trivially true.

New handshake file (issue-scoped, run-dir):
`autodev-design-remedy-attempted-$ID` — the `reconcile_attempted` replacement
from constraint (b). Written by `count_repair_cycle_refine_for_design`, read by
both design branches' arming guards. **Not cleared at `dequeue_next`**: it is
per-issue-scoped by filename, exactly like the existing
`autodev-design-gate-failed-$ID` marker, whose `dequeue_next` comment
(`:127-130`) states the pattern outright — "the design-gate-failed-<ID> marker
is already per-issue-scoped by filename, so it self-isolates without cleanup."
Clearing it per dequeue would also let an issue dequeued twice in one run take
two refine passes, contradicting the once-per-issue-per-run criterion.

A run-dir marker rather than a frontmatter flag: refine has no
`refine_attempted` field, inventing one would need a writer in
`commands/refine-issue.md`, and the design-gate remedy is a per-run routing
concern, not durable issue state.

Optional consolidation (separable, still recommended) — collapse the three
duplicated `python3 -c` blocks behind one Python entry point:

- `cmd_check_design_gate(config: BRConfig, args: argparse.Namespace) -> int` —
  new `ll-issues` subcommand delegating to the existing
  `program_design_gate_active` / `grade_program_design` pair

### Call Path

Verdict resolution (existing, unchanged, invoked by each `DESIGN_FAIL` block):
`cmd_format_check` → `check_format_gaps` → `_gate_program_design` →
`program_design_gate_active` → `grade_program_design`

Remedy routing, path 1 (regate): `regate_after_atomic_remediation` (`:1586`) →
arms `autodev-atomic-design-remedy-pending` unless
`autodev-design-remedy-attempted-$ID` exists → `check_atomic_design_remedy`
(`:1669`) → **`refine_for_design`** (new; today `reconcile_current`) →
**`count_repair_cycle_refine_for_design`** → `rerun_confidence_after_reconcile`
(`:1718`) → `recheck_after_size_review`

Remedy routing, path 2 (recheck): `recheck_after_size_review` (`:1735`) →
emits `refine_design` (not `reconcile`) at `:1829`, guarded on
`autodev-design-remedy-attempted-$ID` instead of `reconcile_attempted` →
`check_pre_deferral_remedy` (`:1924`, `on_yes` now
**`dispatch_design_remedy`**) → **`refine_for_design`** (exit 0) or
`dispatch_pre_deferral_remedy` (exit 1, `:1941`, unchanged) → `run_spike` /
`reconcile_current` as today

Third entry into `reconcile_current` — `check_reconcile_needed.on_yes`
(`:1458`) — is not on either design route and is untouched by this change.

Terminal: on a repeat failure with the attempt marker present, both branches
fall through to `cmd_set_status --reason design_gate_failed` (`:1654`, `:1837`)
exactly as today.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — new states `refine_for_design`,
  `count_repair_cycle_refine_for_design`, `dispatch_design_remedy`;
  `check_atomic_design_remedy.on_yes` (`:1684`);
  `check_pre_deferral_remedy.on_yes` (`:1937`, repointed at the new gate —
  `dispatch_pre_deferral_remedy` itself, `:1941-1965`, is left unchanged);
  both arming guards (`:1646-1649`, `:1824-1828`) and the remedy token at
  `:1829`; the stale comments at `:1598-1603` and `:1946-1951`; optionally the
  three `DESIGN_FAIL` blocks at `:1107`, `:1607`, `:1771`.
  No change to `dequeue_next`'s marker-clearing block (`:121-131`) — see the
  handshake-file note in Program Design for why the new marker is not cleared
  there
- ⚠ Superseded — `commands/reconcile-issue.md` (contract block `:42-77`,
  Step 5 `:144-171`, output `:205`, frontmatter `description`): option B only,
  and option A was selected. Not a file this issue modifies.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — five other `count_repair_cycle_*`
  states carry inline comments cross-referencing "one of the five repair-class
  states" (`:446` `count_repair_cycle_refine`, `:751`
  `count_repair_cycle_wire`, `:1215-1216` `count_repair_cycle_spike`,
  `:1276` `count_repair_cycle_size_review`, `:1707-1709`
  `count_repair_cycle_reconcile`) — if `refine_for_design` is wired into the
  same shared `autodev-repair-cycle-count.txt` counter, these need updating to
  "six" [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `commands/refine-issue.md` — BUG-3001 landed the Step 5a enrichment rule and
  BUG-3003 (commit `12373303`, 2026-08-02) made it reachable for already-refined
  issues: `:189` now documents the Step 3.0 Program Design gate override that
  forces the `analyzer` axis `covered: false`. Both prerequisites are satisfied;
  no change needed here.
- `scripts/little_loops/issues/research_triage.py` — BUG-3003's fix site, landed
  (`_program_design_unmet` at `:320`, wired at `:309`); this is why
  `--auto --gap-analysis` is sufficient here and `--full-rewrite` is not needed.
  ⚠ BUG-3003 was committed via an automated *fallback* commit ("command exited
  before completion") — the override is verifiably present in both files above,
  but spot-check it end-to-end before relying on it
- `scripts/little_loops/cli/issues/deferred_triage.py` — consumes the
  `design_gate_failed` reason code (priority 6/8); no change expected, but its
  advisory text may need to stop implying reconcile is the fix

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.DESIGN_GATE_FAILED`
  (`:88`) is the enum value the new remedy chain ultimately still writes; no
  change expected but confirms the deferral code itself is unaffected by the
  remedy retarget [Agent 1 finding]

### Similar Patterns
- `check_reconcile_needed` / `dispatch_pre_deferral_remedy` (`:1945-1965`) —
  the existing one-shot-remedy-then-defer shape to model the new state on
- `run_spike` — the other rate-limit-handled slash-command remedy state

### Tests
- `scripts/tests/test_builtin_loops.py` — validates `autodev.yaml` structure;
  new states must pass `ll-loop validate` (capture-reachability and
  terminal-action rules in particular)
- `scripts/tests/test_program_design_gate.py` — gate semantics; unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py:657-659` —
  `test_dispatcher_routes_pending_remedy_to_reconcile_current` hard-asserts
  `check_atomic_design_remedy.on_yes == "reconcile_current"`; **will break**
  once the edge retargets to `refine_for_design` — update the assertion and
  rename the test (its name embeds the old target) [Agent 3 finding,
  confirmed by Agent 1]
- `scripts/tests/test_builtin_loops.py:5143-5150` —
  `test_check_guard2_verdict_routes_to_remediation_chain` only asserts
  `check_atomic_design_remedy.on_no`, so it will not break, but its inline
  comment ("falls through to `dequeue_next` when no reconcile remedy was
  armed") should be reviewed since `refine_for_design` becomes the `on_yes`
  target [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py:296-311` —
  `TestRepairCycleCounterStates.test_all_five_counter_states_exist` hardcodes
  exactly five `count_repair_cycle_*` names; adding a sixth
  (`count_repair_cycle_refine_for_design` or similar) won't fail this
  membership check but leaves its "five"-worded test name/docstring stale —
  extend or rename if the new state joins the shared counter [Agent 3
  finding]
- **New test needed**: structural assertions for `refine_for_design` mirroring
  `test_reconcile_current_invokes_skill`
  (`test_autodev_decision_gate.py:567-578` / `test_builtin_loops.py:5870-5883`)
  — action contains `/ll:refine-issue`, `action_type == "slash_command"`,
  `fragment == "with_rate_limit_handling"`, `next`/`on_error` route to the new
  counter state, `on_rate_limit_exhausted == "done"` [Agent 3 finding]
- **New test needed**: end-to-end mini-FSM routing test mirroring
  `TestReconcilePlateauRouting` (`test_autodev_decision_gate.py:587-663`) that
  drives `check_atomic_design_remedy` → `refine_for_design` →
  `count_repair_cycle_refine_for_design` → recheck, and asserts
  `"refine_for_design" in visited` / `"reconcile_current" not in visited` for
  the design-gate-pending case — no existing test exercises this full hop
  chain [Agent 3 finding]

_Second review pass (missed by the wiring pass — `test_autodev_loop.py` was not
inspected):_
- `scripts/tests/test_autodev_loop.py:439-447`
  `test_design_branch_hardcodes_reconcile_remedy` — asserts
  `"else 'reconcile'" in branch`; **will fail** once the token becomes
  `refine_design`. Retarget and rename.
- `scripts/tests/test_autodev_loop.py:449-459`
  `test_design_branch_reconcile_attempted_falls_through_to_design_gate_failed`
  — asserts the exact string
  `"'' if d.get('reconcile_attempted') == 'true' else 'reconcile'"`; **will
  fail** once the guard becomes the marker file. Rewrite around
  `autodev-design-remedy-attempted-$ID`.
- `scripts/tests/test_autodev_loop.py:461-468`
  `test_design_branch_reuses_existing_remedy_handshake_files` — asserts the
  branch reuses `autodev-pre-deferral-remedy-fired` /
  `autodev-pre-deferral-remedy.txt`; still true, but extend it to cover the
  new marker rather than leaving "no new remedy infrastructure" as its stated
  contract.
- Class docstrings at `test_autodev_loop.py:422-427` and `:632-637` describe
  the reconcile-based routing and go stale.
- **New test needed**: `dispatch_design_remedy` structural + routing
  assertions (exit 0 → `refine_for_design`, exit 1 → `reconcile_current`), and
  a negative test that a `spike`/plateau token still reaches
  `reconcile_current` unchanged.
- **New test needed**: one-shot-across-both-routes — with
  `autodev-design-remedy-attempted-$ID` present, neither
  `regate_after_atomic_remediation` nor `recheck_after_size_review` arms a
  second remedy, and both reach the `design_gate_failed` deferral.

### Documentation
- `.claude/CLAUDE.md` § Issue File Format — the deferral-reason-code paragraph
  mentions `design_gate_failed` handling only indirectly; check for wording
  that asserts reconcile is the remedy
- `docs/guides/` autodev/loop documentation referencing the remedy chain

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`#deferred-triage` section, ~`:4038-4043`) — the
  ranking-rationale prose reads "...above `design_gate_failed` (ENH-2870: the
  deterministic `## Program Design` gate failed even after **the one-shot
  reconcile remedy**)..." — becomes factually wrong once the remedy is
  `/ll:refine-issue` via `refine_for_design` [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md` — the
  `readiness_stagnated` row (`:24`) enumerates repair-class attempts as
  "refine/wire/size-review/spike/reconcile" (five); if `refine_for_design`
  joins the shared repair-cycle counter this becomes an incomplete
  enumeration. The file also currently has no row for `design_gate_failed`
  itself — a pre-existing gap worth closing in the same pass [Agent 2
  finding]

_Second review pass:_
- `scripts/little_loops/loops/autodev.yaml` inline comments at `:1598-1603`
  (regate's "routes once through the shared reconcile remedy") and
  `:1946-1951` (dispatcher's "the frontmatter attempted-flags … make a second
  arming impossible") both become factually wrong and are load-bearing for the
  next reader of this graph.

### Configuration
- N/A

## Implementation Steps

_Both prerequisites (BUG-3001, BUG-3003) landed 2026-08-02; this is unblocked._

1. Add the `refine_for_design` state to `autodev.yaml`, modeled on
   `reconcile_current` (`:1688-1703`): `action_type: slash_command`, action
   `"/ll:refine-issue ${captured.input.output} --auto --gap-analysis"`,
   `fragment: with_rate_limit_handling`, `on_rate_limit_exhausted: done`, and
   the `pruning_profile` copied from `run_refine` (`:772-775`:
   `name: refine-issue-repair`, `suppress_claude_md: true`) — MR-12
   (`scripts/little_loops/fsm/validation/evaluator_rules.py:254`) WARNs on any
   `slash_command` state without one.
2. Add `count_repair_cycle_refine_for_design`, incrementing the shared
   `autodev-repair-cycle-count.txt` and additionally writing the
   `autodev-design-remedy-attempted-$ID` marker. Route
   `next`/`on_error: rerun_confidence_after_reconcile` and update that state's
   ENH-2689 comment to say it now serves both design and plateau remedies.
3. Do **not** clear `autodev-design-remedy-attempted-$ID` at `dequeue_next` —
   it is per-issue-scoped by filename and self-isolates, matching the existing
   `autodev-design-gate-failed-$ID` precedent documented at `:127-130`. Clearing
   it per dequeue would let one issue take two refine passes in a single run.
4. Retarget `check_atomic_design_remedy.on_yes` (`:1684`) from
   `reconcile_current` to `refine_for_design`, and swap
   `regate_after_atomic_remediation`'s arming guard (`:1646-1649`) from the
   `reconcile_attempted` frontmatter read to the new marker file — without
   this the `design_gate_failed` deferral at `:1654` becomes unreachable on
   this route (it has no run-dir fired marker of its own).
5. Fix the second route: in `recheck_after_size_review`, change the emitted
   remedy token at `:1829` from `reconcile` to `refine_design` and swap its
   `reconcile_attempted` guard (`:1824-1828`) to the marker file. Note this
   route's deferral stays reachable either way — `autodev-pre-deferral-remedy-fired`
   (`:1821`) already bounds it — so the swap here buys cross-route dedup, not
   reachability.
6. Add `dispatch_design_remedy` and repoint `check_pre_deferral_remedy.on_yes`
   (`:1937`) at it, so the new gate runs **before**
   `dispatch_pre_deferral_remedy` rather than after. It reads
   `autodev-pre-deferral-remedy.txt` without deleting it, exits 0 for
   `refine_design` → `refine_for_design`, and exits 1 otherwise →
   `dispatch_pre_deferral_remedy`, which is left entirely unchanged.
   ⚠ Do not chain it downstream: `dispatch_pre_deferral_remedy` `rm -f`s the
   token at `:1953` before routing, so a gate placed after it would always read
   an empty token and fall through to `reconcile_current`.
7. Update the now-false inline comments: `regate_after_atomic_remediation`
   (`:1598-1603`, "routes once through the shared reconcile remedy") and
   `dispatch_pre_deferral_remedy` (`:1946-1951`, "the frontmatter
   attempted-flags … make a second arming impossible").
8. Update the tests listed under Integration Map → Tests, including the two
   in `test_autodev_loop.py` that hard-assert the reconcile selector string
   and will fail outright.
9. Since `refine_for_design` joins the shared repair-cycle counter, update the
   "one of the five repair-class states" inline comments in `autodev.yaml`
   (`:446`, `:751`, `:1215-1216`, `:1276`, `:1707-1709`) and the
   `readiness_stagnated` enumeration in `docs/reference/DEFERRAL_CODES.md:24`
   to six, and add the missing `design_gate_failed` row to that file.
10. Update the stale "one-shot reconcile remedy" phrasing in
    `docs/reference/API.md` (`#deferred-triage`, ~`:4038-4043`) to describe the
    refine-based remedy.

## Acceptance Criteria

- [ ] A Program-Design-only failure reaching **either** deferring state
      (`regate_after_atomic_remediation` or `recheck_after_size_review`) is
      routed to `refine_for_design`, not `reconcile_current`.
- [ ] The remedy fires **at most once per issue per run** across both routes —
      an issue that takes the regate route does not get a second refine pass
      via the recheck route.
- [ ] `design_gate_failed` deferral remains reachable on both routes once the
      attempt marker is present; `deferred-triage` output stays meaningful.
- [ ] The plateau path is untouched: `dispatch_pre_deferral_remedy` still
      routes a non-design remedy token to `run_spike` / `reconcile_current`,
      and its state definition (`:1941-1965`) is unmodified. The third,
      unrelated entry into `reconcile_current` — `check_reconcile_needed.on_yes`
      (`:1458`) — is likewise unchanged.
- [ ] The remedy consumes no `max_refine_count` budget and removes no existing
      issue content (additive `--auto --gap-analysis` pass).
- [ ] `ll-loop validate autodev` passes with no new MR-* warnings, and
      `python -m pytest scripts/tests/` exits 0.
- [ ] End-to-end on a real gate-failing issue: `git diff` shows
      `## Program Design` non-identical before/after the remedy pass, and the
      post-remedy `format-check` clears `program_design_nonspecific`.

## Impact

Every issue that autodev defers as `design_gate_failed` today is deferred
without a genuine remedy attempt, and each one costs a wasted
`/ll:reconcile-issue` invocation (a full slash-command turn, rate-limit
handling included) to arrive there. In a stamped project the class is
potentially large — the gate applies to every non-grandfathered issue, and
BUG-3001 means running `/ll:refine-issue` actively *enlarges* the class by
un-grandfathering previously-exempt issues.

Ordering: both of option A's prerequisites have landed as of 2026-08-02 —
BUG-3001 (refine writes `## Program Design` at Step 5a) and BUG-3003 (the
triage blind spot that made that enrichment unreachable for already-refined
issues). This issue is unblocked. Option B remains an alternative at the cost
of duplicating enrichment logic across two commands.

Scope note from the same review: the fix is roughly twice the size originally
estimated. The remedy has two routes (`check_atomic_design_remedy` and the
`pre-deferral-remedy.txt` dispatcher), the one-shot guard is reconcile-specific
and needs a replacement marker, and the dispatcher needs a chained gate to hold
a third remedy target.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/autodev.yaml` | The three `DESIGN_FAIL` states and the remedy routing being changed |
| `commands/reconcile-issue.md` | The binding three-section contract that excludes Program Design |
| `skills/confidence-check/SKILL.md` | Defines the gate autodev mirrors |

## Status

**Open** | Created: 2026-08-02 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- `depends_on: BUG-3001` was a hard blocker for the selected Option A path; BUG-3001 has since landed (`status: done`, completed 2026-08-02) — see Codebase Research Findings below. This concern is resolved.
- `depends_on: BUG-3003` (the triage blind spot making refine's Program Design enrichment unreachable for already-refined issues) also landed 2026-08-02, commit `12373303`. Both dependencies now resolve; this issue is unblocked. Caveat: that commit was an automated fallback ("command exited before completion"), so verify the Step 3.0 override end-to-end before relying on `refine_for_design` to actually write the section.

_Review pass 2026-08-02 (pre-implementation) corrected three Program Design defects: the `dispatch_design_remedy` gate must chain **before** `dispatch_pre_deferral_remedy` (which deletes the remedy token at `:1953`); constraint (b)'s unreachability claim holds only for the regate route, not the recheck route; and the new attempt marker must **not** be cleared at `dequeue_next`. Assorted line references were also refreshed against the current `autodev.yaml`._

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase re-check:_

- **BUG-3001 has landed** (`status: Completed`, `Completed at: 2026-08-02` per `ll-issues show BUG-3001`) — the concern above ("do not begin Option A until BUG-3001 lands") is resolved. `commands/refine-issue.md` now populates `## Program Design` at Step 5a (`:372-374`) and gates it at Step 6.7 (`:737` "Prose Dependency & Program Design Gate (FEAT-2849, BUG-3001)", `:753`, `:829`, `:859`). Option A's prerequisite is satisfied; the `refine_for_design` remedy state would call a `/ll:refine-issue` that can actually write the section it targets.
- `docs/reference/DEFERRAL_CODES.md` is now tracked in git (commit `d980fb82`, 2026-08-02) — the earlier "(new, untracked)" note under Integration Map → Documentation is stale. The file still has no row for `design_gate_failed` itself, so that part of the gap stands.
- `.claude/CLAUDE.md` § Issue File Format was trimmed in the same commit (`d980fb82`, "migrate CLI Tools/Loop Authoring/Issue File Format out of CLAUDE.md") — the deferral-reason-code paragraph this issue's Documentation section referenced no longer lives in CLAUDE.md at all; it now points to `docs/reference/DEFERRAL_CODES.md`. The stale-remedy-wording risk flagged there has moved entirely to `DEFERRAL_CODES.md` and `docs/reference/API.md` (`#deferred-triage`), both already tracked in this issue's Integration Map.
- `commands/refine-issue.md` line citations above (`:372-374` for Step 5a) are now stale — the file changed again after this issue's most recent refine pass. The Program Design template in Step 5a currently lives at lines 376-388, not 372-374 (`:372-374` is now the Root Cause template example). The Step 6.7 citations (`:737`, `:753`, `:829`, `:859`) are still substantively accurate (Step 6.7's heading is now at `:741`, a one-line drift). Neither shift changes this issue's scope or conclusions — reference `commands/refine-issue.md`'s current content directly during implementation rather than these line numbers. [locator finding]

## Session Log
- `/ll:manage-issue` - 2026-08-02T19:27:41 - `c2ddc2b8-a949-46f6-8466-7e925f3a2db0.jsonl`
- `/ll:confidence-check` - 2026-08-02T18:51:33 - `b1ebc156-6c0d-4467-8083-0cca9e6e9a52.jsonl`
- `/ll:ready-issue` - 2026-08-02T18:46:27 - `7cac88e2-2b28-447a-81f8-098fcff1cd67.jsonl`
- `/ll:ready-issue` - 2026-08-02T18:29:25 - `a4a2ec47-afaf-4693-a4bc-7ad2a1747435.jsonl`
- `/ll:refine-issue` - 2026-08-02T18:26:12 - `d69ad2ba-fe5b-4482-9f62-1ac8277e1ec0.jsonl`
- `/ll:refine-issue` - 2026-08-02T16:57:00 - `68d927d9-c11c-4d1e-89b3-a56472ca2633.jsonl`
- `/ll:confidence-check` - 2026-08-02T16:24:56 - `79f2cbf6-efe9-4c5a-8ea6-c127c1fa8674.jsonl`
- `/ll:wire-issue` - 2026-08-02T16:13:51 - `7350086a-c582-4853-bc33-c455a6cf8d34.jsonl`
- `/ll:decide-issue` - 2026-08-02T15:59:14 - `7350086a-c582-4853-bc33-c455a6cf8d34.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:53:38 - `6f876dea-3115-4d85-82a1-939918043ab9.jsonl`
- `/ll:capture-issue` - 2026-08-02T15:49:44 - `757e6b7e-c10a-4a24-9492-2b31e8e379e5.jsonl`
