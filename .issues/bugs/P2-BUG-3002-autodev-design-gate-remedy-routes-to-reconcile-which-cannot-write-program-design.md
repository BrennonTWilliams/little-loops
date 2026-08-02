---
id: BUG-3002
title: autodev routes design_gate_failed to reconcile-issue, whose contract excludes
  the Program Design section
type: BUG
priority: P2
captured_at: '2026-08-02T15:46:46Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- autodev
- reconcile-issue
- program-design-gate
relates_to:
- BUG-3001
status: open
depends_on:
- BUG-3001
decision_needed: false
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
| `recheck_after_size_review` | 1758 | same shape; defers `design_gate_failed` at `:1837-1839` |

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

### Signatures

Option A requires no Python signature change — the fix is FSM routing plus a
new `autodev.yaml` state. Existing surfaces the three `DESIGN_FAIL` blocks
consume, unchanged:

- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/format_check.py:158`) — emits the JSON the
  shell blocks parse
- `check_format_gaps(...) -> FormatGaps`
  (`scripts/little_loops/issue_parser.py:316`) — owns
  `FormatGaps.program_design_nonspecific` (`:251`)
- `cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/set_status.py:20`) — writes the
  `design_gate_failed` deferral

New FSM state (option A), named per `autodev.yaml` convention — YAML, not
Python, so it has no signature:

- `refine_for_design:` — `action_type: slash_command`,
  `action: "/ll:refine-issue ${captured.input.output}"`, modeled structurally
  on `reconcile_current` (`:1688-1703`) including `fragment:
  with_rate_limit_handling` and a `count_repair_cycle_*` successor

Optional consolidation (separable) — collapse the three duplicated `python3 -c`
blocks behind one Python entry point:

- `cmd_check_design_gate(config: BRConfig, args: argparse.Namespace) -> int` —
  new `ll-issues` subcommand delegating to the existing
  `program_design_gate_active` / `grade_program_design` pair

### Call Path

Verdict resolution (existing, unchanged, invoked by each `DESIGN_FAIL` block):
`cmd_format_check` → `check_format_gaps` → `_gate_program_design` →
`program_design_gate_active` → `grade_program_design`

Remedy routing (the change): `recheck_after_size_review` (`autodev.yaml:1758`)
/ `regate_after_atomic_remediation` (`:1586`) → `check_atomic_design_remedy`
(`:1669`) → **`refine_for_design`** (new; today `reconcile_current` `:1688`) →
`count_repair_cycle_reconcile`-style counter → back into the recheck loop → on
repeat failure `cmd_set_status` with `--reason design_gate_failed` (`:1654`,
`:1837`)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_atomic_design_remedy`
  (`:1669-1687`) routing target; new remedy state; optionally the three
  `DESIGN_FAIL` blocks at `:1090`, `:1616`, `:1780`
- `commands/reconcile-issue.md` — only under option B (contract block `:42-77`,
  Step 5 `:144-171`, output `:205`, frontmatter `description`)

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
- `commands/refine-issue.md` — option A depends on BUG-3001 landing first
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
- `docs/reference/DEFERRAL_CODES.md` (new, untracked) — the
  `readiness_stagnated` row (`:24`) enumerates repair-class attempts as
  "refine/wire/size-review/spike/reconcile" (five); if `refine_for_design`
  joins the shared repair-cycle counter this becomes an incomplete
  enumeration. The file also currently has no row for `design_gate_failed`
  itself — a pre-existing gap worth closing in the same pass [Agent 2
  finding]

### Configuration
- N/A

## Implementation Steps

1. A Program-Design-only failure reaches a remedy that can write the section —
   whichever of options A/B is chosen — so the post-remedy re-check has a real
   chance of passing rather than a guaranteed repeat failure.
2. `design_gate_failed` deferrals still occur, but only after a
   section-capable remedy has been attempted; `deferred-triage` output stays
   meaningful.
3. `ll-loop validate autodev` passes and `python -m pytest
   scripts/tests/test_builtin_loops.py` is green, with an end-to-end check on
   a real gate-failing issue confirming `## Program Design` is non-identical
   before/after the remedy pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Add `pruning_profile` to the new `refine_for_design` state — MR-12
   (`scripts/little_loops/fsm/validation/evaluator_rules.py:254`) WARNs on any
   `action_type: slash_command` state without one; `reconcile_current` and
   `run_spike` both carry one as precedent.
5. Update `scripts/tests/test_autodev_decision_gate.py:657-659` — retarget the
   `check_atomic_design_remedy.on_yes` assertion from `"reconcile_current"` to
   `"refine_for_design"` and rename the test.
6. Add a structural test for `refine_for_design` (action string, `fragment`,
   `next`/`on_error`/`on_rate_limit_exhausted`) mirroring
   `test_reconcile_current_invokes_skill`.
7. Add an end-to-end mini-FSM routing test mirroring
   `TestReconcilePlateauRouting` (`test_autodev_decision_gate.py:587-663`)
   that drives `check_atomic_design_remedy` → `refine_for_design` and asserts
   `reconcile_current` is not visited for the design-gate-pending case.
8. If `refine_for_design` joins the shared `autodev-repair-cycle-count.txt`
   counter, update the five "five repair-class states" inline comments in
   `autodev.yaml` (`:446`, `:751`, `:1215-1216`, `:1276`, `:1707-1709`) and the
   `readiness_stagnated` enumeration in `docs/reference/DEFERRAL_CODES.md:24`
   to reflect six states.
9. Update the stale "one-shot reconcile remedy" phrasing in
   `docs/reference/API.md` (`#deferred-triage`, ~`:4038-4043`) to describe the
   refine-based remedy.

## Impact

Every issue that autodev defers as `design_gate_failed` today is deferred
without a genuine remedy attempt, and each one costs a wasted
`/ll:reconcile-issue` invocation (a full slash-command turn, rate-limit
handling included) to arrive there. In a stamped project the class is
potentially large — the gate applies to every non-grandfathered issue, and
BUG-3001 means running `/ll:refine-issue` actively *enlarges* the class by
un-grandfathering previously-exempt issues.

Ordering matters: option A is the cleaner fix but depends on BUG-3001 landing
first. Option B unblocks independently at the cost of duplicating enrichment
logic across two commands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/autodev.yaml` | The three `DESIGN_FAIL` states and the remedy routing being changed |
| `commands/reconcile-issue.md` | The binding three-section contract that excludes Program Design |
| `skills/confidence-check/SKILL.md` | Defines the gate autodev mirrors |

## Status

**Open** | Created: 2026-08-02 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-08-02T16:13:51 - `7350086a-c582-4853-bc33-c455a6cf8d34.jsonl`
- `/ll:decide-issue` - 2026-08-02T15:59:14 - `7350086a-c582-4853-bc33-c455a6cf8d34.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:53:38 - `6f876dea-3115-4d85-82a1-939918043ab9.jsonl`
- `/ll:capture-issue` - 2026-08-02T15:49:44 - `757e6b7e-c10a-4a24-9492-2b31e8e379e5.jsonl`
