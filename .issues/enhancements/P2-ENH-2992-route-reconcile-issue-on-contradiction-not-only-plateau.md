---
id: ENH-2992
status: done
priority: P2
captured_at: '2026-08-02T13:43:01Z'
completed_at: '2026-08-02T22:28:05Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
- ENH-2993
- BUG-3001
confidence_score: 100
outcome_confidence: 55
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 0
missing_artifacts: false
testable: true
decision_needed: false
blocked_by: []
---

# Route reconcile-issue on contradiction, not only on readiness plateau

## Summary

`/ll:reconcile-issue` exists specifically to rewrite an issue's directive
sections when they contradict its own accumulated research findings. It is
almost never invoked: **1,703 issues have been refined, 19 have been
reconciled**. The gate that triggers it — `check_reconcile_needed` in
`autodev.yaml` — fires only on a *readiness-score plateau*, at most once per
issue. A contradiction that does not happen to stall the confidence score never
reaches the remedy. Reconcile is also absent from `/ll:refine-issue`'s own
pipeline diagram and Next Steps block, so no human path leads to it either.

Trigger reconcile on the condition it was built for — detected contradiction —
in addition to the existing plateau predicate.

## Current Behavior

`commands/reconcile-issue.md` states the problem it solves, verbatim:

> Over a long refine/spike/confidence-check cycle, `/ll:refine-issue` and
> `/ll:confidence-check` only **append** new "Codebase Research Findings"
> bullets — they never rewrite the issue's own Implementation Steps /
> Acceptance Criteria / Files to Modify to match.

But the only automated route in is `check_reconcile_needed`
(`scripts/little_loops/loops/autodev.yaml:1406-1458`), whose predicate is a
readiness plateau — the score failing to improve against a pre-refine snapshot
— and which is armed as a **one-shot per issue** via a `reconcile_attempted`
marker (`autodev.yaml:1418`). Secondary entries at `autodev.yaml:1684` and
`autodev.yaml:1964` are fallbacks from other states, not contradiction
detection.

Measured across `.issues/` (2026-08-02):

| Signal | Count |
|---|---|
| Issues with a `/ll:refine-issue` session-log entry | 1,703 |
| Issues with a `/ll:reconcile-issue` session-log entry | 19 |
| Issues whose research-findings blocks contain correction language | 316 |

So ~316 issues carry the exact condition reconcile was written to fix, and 19
have been through it.

Additionally, `/ll:refine-issue` never mentions reconcile:
- Pipeline diagram (`commands/refine-issue.md:791`):
  `capture-issue → format-issue → refine-issue → decide-issue → wire-issue → ready-issue → manage-issue`
- `## NEXT STEPS` output block (`commands/refine-issue.md:753-758`) lists
  decide-issue, wire-issue, ready-issue, manage-issue, and issue-size-review —
  not reconcile-issue.

A user who reads refine's own output has no way to learn reconcile exists.

## Expected Behavior

1. **Contradiction is a trigger.** When a refine (or confidence-check) pass
   deposits findings that refute a directive section, `check_reconcile_needed`
   routes to `reconcile_current` regardless of whether the readiness score
   plateaued.
2. **The one-shot arms per contradiction, not per issue.** A second, distinct
   contradiction discovered on a later pass is eligible for a second reconcile.
   (Retain a bounded cap so this cannot loop.)
3. **The human path exists.** refine-issue's pipeline diagram and Next Steps
   block name `/ll:reconcile-issue` when the pass emitted correction language.

## Motivation

The append-only design is deliberate and correct — it protects human prose.
Reconcile is the designed release valve. A release valve that opens 1% of the
time it is needed is a design that has one half installed. The cost is paid by
headless implementers reading contradictory directive sections (see ENH-2995
for the measured shape of that).

This is cheap to fix relative to its reach: the detection signal is already
being written into the issue in plain text by refine itself.

## Proposed Solution

Two changes, independent:

**A. Widen the automated gate.** In `check_reconcile_needed`
(`autodev.yaml:1406-1458`), add a contradiction predicate OR'd with the
existing plateau predicate.

> ⚠ Superseded — the `--check`/heuristic detection question below was open when
> this issue was captured. **ENH-2995 landed 2026-08-02 (`56893def`)** and
> settles it; see "Detection: decided" immediately after.

Detection candidates, cheapest first:
- A Python check over the issue's directive sections vs its
  `### Codebase Research Findings` blocks. This is plausibly a new
  `ll-issues` subcommand rather than prose in a skill —
  `ll-verify-skill-prose` will flag a prose reimplementation of a
  string-matching algorithm.
- If ENH-2995 lands first, the superseded markers it writes are a direct,
  unambiguous signal: presence of a marker in a directive section ⇒
  reconcile-eligible. Prefer this if available; it removes the heuristic
  entirely.

#### Detection: decided

ENH-2995 shipped both halves of the signal:

- the `> ⚠ Superseded — …` in-place marker convention written by
  `/ll:refine-issue` into `## Implementation Steps` / `### Files to Modify` /
  `## Acceptance Criteria`;
- a deterministic `unmarked_superseded_directive` gap class in
  `ll-issues format-check --format json`
  (`scripts/little_loops/issue_parser.py:543-560`).

The predicate is therefore **inline Python over
`ll-issues format-check ${ID} --format json`**, which matches
`check_reconcile_needed`'s existing inline-Python-over-`ll-issues show --json`
idiom (`autodev.yaml:1436-1458`), satisfies MR-1 with zero LLM judgment, and
leaves `--check`'s zero-caller contract untouched. Neither option in the
wiring note's "(a) wire `--check` / (b) second inline check" framing is taken:
this is a third, smaller option that did not exist when that note was written.

**One gap remains.** `format-check` reports only the *unmarked* case
(correction language present, no marker) — that is a refine-did-not-mark
defect, the inverse of what this gate wants. The reconcile-eligible signal is
marker **presence**, which has no query surface today:
`_SUPERSEDED_MARKER_PREFIX`, `_SUPERSEDED_DIRECTIVE_SECTIONS` and
`_heading_bodies` are all private to `issue_parser.py`. Implementation must add
one — a public helper (e.g. `superseded_marker_count(path) -> int`) or an
additional `format-check` field. **Reuse BUG-3002's verdict-surface cleanup if
it lands first**: that issue proposes collapsing its three duplicated
`DESIGN_FAIL` `python3 -c` heredocs into "a shared fragment or an `ll-issues`
subcommand returning the verdict directly" — the same primitive. Two
independently-invented verdict paths is the failure mode to avoid; BUG-3002
marks that cleanup separable, which is how it gets missed.

#### Open design point: marker lifecycle across reconcile

`commands/reconcile-issue.md` has **zero** awareness of ENH-2995's markers
(`grep -n "Superseded" commands/reconcile-issue.md` → no hits). If
marker-presence is the predicate and reconcile rewrites a directive line
without removing that line's marker, `check_reconcile_needed` fires again on
every subsequent pass — the unbounded loop this issue's own Scope Boundaries
forbid, and the precise mechanism Expected Behavior #2 depends on.

Two candidate resolutions, both unspecified today:

> **Selected:** Option A — reuses reconcile's existing Step 5 Edit-based rewrite with no new state file; BUG-3002's rejected "widen the contract" precedent was a different kind of change (new content authorship) and doesn't re-apply here.

**Option A**: Reconcile clears the marker it acted on. Note this is a change
to reconcile's Contract section, which Scope Boundaries currently says is
untouched — see the amended boundary below. It is also worth arguing rather
than assuming: BUG-3002 scored "widen reconcile's contract" 5/12 and rejected
it. The counter-argument here is that removing a marker on a line reconcile is
already rewriting falls inside its existing rewrite scope and requires no
re-research (the thing `reconcile-issue.md:67-68` disclaims) — but that
argument has to be made explicitly, not inherited.

**Option B**: Marker-fingerprint snapshot diffed pass-over-pass under
`${context.run_dir}`, mirroring the existing `autodev-pre-readiness.txt`
pattern. Leaves reconcile's contract alone; costs a new artifact and a
comparison step.

Resolve this before implementing the predicate — it determines whether the
bounded-cap requirement is satisfied structurally or only by the counter.

### Decision Rationale

**Selected: Option A** — reconcile clears the `⚠ Superseded` marker on every
directive line it evaluates, as part of its existing Step 5 rewrite action
**and** its no-op branch (see "Option A must cover the no-op path" below).

**Reasoning**: `commands/reconcile-issue.md` Step 5 already uses the Edit tool
to replace stale bullet/line text in place; extending the `old_string` span to
include the trailing `> ⚠ Superseded — …` blockquote removes the marker as a
byproduct of a rewrite reconcile is already performing, with no new state
file, no new comparison logic, and no re-research. Marker matching in
`issue_parser.py` (`_SUPERSEDED_MARKER_PREFIX`, `_heading_bodies()`) is a
plain substring check over section text, not structural parsing, so clearing
is a straightforward string removal rather than a re-parse.

**Precedent (not previously cited)**: marker *deletion* is already a sanctioned
operation with written rules — `commands/refine-issue.md`'s **"Bounded
marker-removal right"** (`refine-issue.md:534-540`, ENH-2995) grants refine the
one exception to "Do NOT remove any existing content under any circumstance":
when a pass's findings no longer refute a marked line, refine deletes the
marker line silently, no tombstone. Option A is therefore not a novel
capability — it extends an existing, bounded, precedented right to the second
skill that acts on the same lines. Implementation must keep the two rules
composable rather than divergent: reconcile's clearing rule uses the same
containment test on `⚠ Superseded`, the same "only marker lines are ever
deletable" restriction, and the same silent-deletion behavior. Do not introduce
a second, differently-shaped marker lifecycle.

#### Option A must cover the no-op path

Clearing "the marker on the line it rewrites" is **not sufficient on its own**.
`commands/reconcile-issue.md` has two paths that leave a marked line unedited:

- the explicit no-op branch (`reconcile-issue.md:140-142`) — when directives
  already match findings, reconcile emits verdict `RECONCILED` with an empty
  `## CORRECTIONS_MADE` and *makes no edits at all*;
- Step 5's "Preserve any bullets that are still accurate" rule, which leaves
  individual marked lines untouched inside an otherwise-rewritten section.

On either path a marker survives a completed reconcile pass, the
marker-presence predicate re-fires on the next pass, and Acceptance Criteria 4
("two consecutive passes over the same issue with one marker → exactly one
`reconcile_current` entry") fails.

**Resolution**: reconcile clears the marker on every directive line it
*evaluated*, not only on lines it rewrote — including on the no-op branch,
where clearing markers is then the pass's only edit and `## CORRECTIONS_MADE`
stays `None`. Rationale: a marker means "this pass's findings refute this
line"; once reconcile has adjudicated that line against the findings — whether
by rewriting it or by confirming it still holds — the annotation has been
consumed and is stale by definition. Leaving it standing is the same
append-only defect this issue exists to close, one level up.

The BUG-3002 precedent that rejected "widen reconcile's contract" (5/12) was
a materially different kind of change — authoring an entirely new `## Program
Design` section from fresh research, the exact re-research reconcile's
Contract disclaims. Marker-clearing deletes an annotation on a line already
being rewritten from findings already in hand; it is not the same category of
widening and isn't a re-litigation of that rejection.

Option B (fingerprint snapshot under `${context.run_dir}`) was rejected
because a scalar/count-based fingerprint (mirroring the existing
`autodev-pre-readiness.txt` pattern) cannot distinguish "marker A persists
unresolved" from "marker A was replaced by distinct marker B" — both leave
the count unchanged — so it does not fully satisfy Acceptance Criteria 5's
distinct-second-contradiction requirement without added per-marker-identity
tracking. It also adds a new artifact file and diff logic that the existing
FEAT-2751 `count_repair_cycle_reconcile` cap already substantially covers for
the unbounded-loop risk this option exists to address, lowering its
value-add relative to its cost.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 2 |
| Simplicity | 2 | 1 |
| Testability | 3 | 2 |
| Risk | 1 | 2 |
| **Total** | **9/12** | **7/12** |

**Key evidence**:
- `commands/reconcile-issue.md` Step 5 (lines 144–171) already performs
  targeted in-place Edit-tool rewrites — the exact mechanism a marker-strip
  piggybacks on.
- `_SUPERSEDED_MARKER_PREFIX`/`_heading_bodies()` in `issue_parser.py` treat
  markers as substrings within section bodies, not line-owned structural
  objects — clearing requires no new parsing.
- BUG-3002's rejected "widen the contract" proposal (`.issues/bugs/P2-BUG-3002-*.md:128-211`)
  was scoped to authoring a new `## Program Design` section from fresh
  research — a different category of contract change than deleting an
  existing marker on a line already being rewritten.
- `autodev-pre-readiness.txt` (the Option B precedent) stores a single scalar,
  not a set of marker identities; a count/hash diff cannot fully distinguish
  "unresolved persisting marker" from "new distinct marker" per AC5.
- FEAT-2751's `count_repair_cycle_reconcile` / `CYCLE_COUNT >= 2` cap
  (`autodev.yaml:1749-1759`, `:1799-1910`) already bounds repeated reconcile
  fires regardless of marker state, reducing Option B's added precision to a
  lower-value, higher-cost addition.

**Implication for Implementation Steps / Scope Boundaries**: the "Open design
point" and Step 1 (superseded step) above are resolved as Option A. The
Scope Boundaries item stating reconcile's Contract is unchanged is amended:
reconcile's Contract section gains a narrow addition — clearing the
`⚠ Superseded` marker on every directive line it evaluates — while the
rewrite-eligible vs preserve-untouched section list is otherwise unchanged.

#### Arming: decided

The predicate's relationship to the existing `reconcile_attempted` one-shot was
unstated, and it is what makes Acceptance Criteria 4 and 5 either satisfiable
or mutually exclusive. Resolved as follows.

**The `contradiction` term is NOT gated by `reconcile_attempted`.** That flag
is issue frontmatter (`cli/issues/show.py:225`, written by
`commands/reconcile-issue.md:99`), permanent once set, and never cleared by any
state — `dequeue_next` does not reset it. Gating the contradiction term on it
would make Acceptance Criteria 5 structurally impossible: no issue could ever
receive a second reconcile, which is precisely the failure this issue was
opened to fix. The predicate is therefore:

```python
plateau      = (pre != '' and pre == cur and not attempted)
fresh_below  = (pre == '' and cur != ''
                and int(cur) < ${context.readiness_threshold} and not attempted)
contradiction = marker_count > 0          # deliberately unguarded by `attempted`
sys.exit(0 if (plateau or fresh_below or contradiction) else 1)
```

**Bounding is therefore structural + counted, in that order:**

1. *Structural* — marker-clearing (Option A, extended to the no-op path).
   A consumed marker cannot re-arm the gate. This is what satisfies AC4.
2. *Counted* — a dedicated, reconcile-scoped per-run fire counter capped at 2
   (see the correction to the cap claim below). This is the backstop for a
   reconcile that fails to clear a marker, and what makes AC5's "pass 3+ →
   capped" deterministic.

**Correction — the existing `CYCLE_COUNT >= 2` cap does not bound this.**
Earlier drafts of this issue (and ## Program Design § Call Path) asserted that
FEAT-2751's shared repair-cycle counter "is what ultimately bounds a second
reconcile fire". Verified against the tree, it does not:

- The branch at `autodev.yaml:1910` is
  `CYCLE_COUNT >= 2 AND PRE_READINESS non-empty AND CUR <= PRE`. It only fires
  when readiness **fails to improve**. A contradiction-driven reconcile that
  raises the readiness score is never capped by it.
- It is a **deferral** branch inside `recheck_after_size_review`, not a gate on
  `check_reconcile_needed`. It changes the deferral *reason*
  (`readiness_stagnated` vs `low_readiness`); it does not suppress a reconcile
  fire.
- `autodev-repair-cycle-count.txt` is **shared across all six repair classes**
  (`count_repair_cycle_refine` / `_wire` / `_spike` / `_size_review` /
  `_refine_for_design` / `_reconcile`). A prior refine plus wire exhausts the
  budget before reconcile fires once, so AC5's three-pass sequence is not
  reproducible against it.

Implementation must add a reconcile-scoped counter
(`${context.run_dir}/autodev-contradiction-reconcile-count.txt`, incremented in
`count_repair_cycle_reconcile` alongside the existing shared increment) and
read it as a third guard term in the contradiction predicate. Keep the existing
shared increment untouched — the stagnation backstop still needs it.

#### Side effect: reconcile stamping burns the pre-deferral remedy budget

Not previously recorded anywhere in this issue, and a real behavior regression
if unaddressed. `recheck_after_size_review`'s pre-deferral remedy dispatcher
(`autodev.yaml:1942`) reads:

```python
if d.get('spike_attempted') == 'true' or d.get('reconcile_attempted') == 'true':
    print('')          # → REMEDY empty → no remedy dispatched at all
```

`reconcile_current` invokes `/ll:reconcile-issue`, which unconditionally stamps
`reconcile_attempted: true` (`commands/reconcile-issue.md:99`). Today that
stamp is only ever set on an issue that already plateaued below the readiness
threshold, so suppressing its remedy dispatch is coherent. Once reconcile also
fires on *contradiction* — a condition with no relationship to readiness — a
perfectly healthy issue gets permanently stamped, and thereafter the
pre-deferral dispatcher will refuse to dispatch **either** remedy for it,
including `spike`. An issue that later needs a spike silently cannot get one.

**Resolution**: the contradiction branch must not consume the pre-deferral
remedy budget. Route it through a distinct arming signal rather than
`reconcile_attempted` — a per-issue run-dir touch-file
`autodev-contradiction-reconcile-$ID`, mirroring BUG-3002's
`autodev-design-remedy-attempted-$ID` precedent (`autodev.yaml:1710-1726`,
deliberately excluded from the `dequeue_next` reset) — and leave the `:1942`
predicate reading `reconcile_attempted` unchanged. Reconcile will still stamp
`reconcile_attempted` when it runs; the narrow requirement is that a
contradiction-only fire must not be the *reason* an issue loses its spike
remedy. If separating the stamp proves to require widening reconcile's
contract, the fallback is to amend the `:1942` predicate to distinguish the two
arming sources. Decide which before touching the predicate; do not land the
contradiction branch without one of them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing marker mechanism in `autodev.yaml` supports "arm again on a new
  distinct trigger" (what Option A's clearing behavior and Option B's
  fingerprint diff both have to provide). Two one-shot mechanisms coexist
  today and neither does this: the `reconcile_attempted` frontmatter flag
  (`autodev.yaml:1442`, `:1736`) is a pure boolean, true forever once set; the
  BUG-3002-introduced run-dir touch-file `autodev-design-remedy-attempted-$ID`
  (`autodev.yaml:1710-1726`) is per-run, filename-scoped, and deliberately
  excluded from the `dequeue_next` reset. Neither is a counter/list keyed by
  *which* marker fired. This confirms the "Open design point" framing above —
  it is a genuine gap, not something an existing pattern already resolves.
- Direct precedent exists for OR'ing a new predicate term into
  `check_reconcile_needed` without restructuring the state: its current
  `plateau or fresh_below` expression is itself already a BUG-2803 widening of
  ENH-2689's original single-condition check, using the same
  inline-Python-over-`shell_exit` idiom this issue would extend a third time.

**B. Surface the human path.** In `commands/refine-issue.md`:
- Add reconcile to the pipeline diagram at its real position — after refine,
  conditional. Note there are **three** pipeline diagrams in that file, not
  one; decide explicitly which get the conditional branch.
- Add a Next Steps entry: when this pass deposited findings that refute an
  existing directive section, run `/ll:reconcile-issue [ID]`.
- Regenerate the host mirrors — `.gemini/commands/refine-issue.toml` and
  `.kimi-code/skills/ll-refine-issue/SKILL.md` are committed in-tree and were
  updated alongside `commands/refine-issue.md` in ENH-2995's commit
  (`56893def`). Any edit to the command file must carry them.

> ⚠ Superseded — "Change B is independently shippable and near-zero-risk" was
> true at capture. **BUG-3001 restructured the same region of
> `commands/refine-issue.md`**: its change 2 has refine calling
> `ll-issues format-check --format json` at Step 6.5 and reporting gaps in
> Step 8's output, and its change 3 reorders Step 6.5 against the Session Log
> append. Change B should ride that mechanism — one more key in the JSON refine
> already has in hand — rather than land as standalone prose. It stays
> low-risk; it is no longer independent.

**Sequencing — satisfied.** The intended order was BUG-3001 → BUG-3002 → this
issue. **Both prerequisites are now `status: done`**, verified against the tree
on 2026-08-02: BUG-3001's `format-check` call is live at
`commands/refine-issue.md:744`, and BUG-3002's retarget of
`check_atomic_design_remedy.on_yes` to `refine_for_design` is in
`autodev.yaml`. This issue's `blocked_by` is empty and correct; nothing gates
implementation. See [Related Key Documentation](#related-key-documentation) for
why each edge existed.

> **Status update (2026-08-02, `/ll:refine-issue`):** BUG-3002 has landed
> (`status: done`, `completed_at: '2026-08-02T19:28:04Z'`). Verified against
> the current tree: `check_atomic_design_remedy.on_yes` now targets
> `refine_for_design`, not `reconcile_current`; `check_reconcile_needed` /
> `reconcile_current` / `count_repair_cycle_reconcile` are byte-identical in
> shape to what this issue describes; and both named test consumers this
> issue predicted BUG-3002 would delete are confirmed gone —
> `test_dispatcher_routes_pending_remedy_to_reconcile_current` no longer
> exists, surviving only as `test_dispatcher_routes_pending_remedy_to_refine_for_design`
> (`scripts/tests/test_autodev_loop.py:661`). This issue's `blocked_by:
> BUG-3002` is therefore resolved as of this pass; the implementer does not
> need to re-verify BUG-3002's landing.

## Program Design

### Types

No new data types are introduced. The only shape change is a new boolean/int
signal surfaced through the existing `FormatGaps` dataclass
(`scripts/little_loops/issue_parser.py:237-256`) — either a new field
alongside `unmarked_superseded_directive: list[str]`, or a value returned by a
new standalone function (see Signatures below). Both options reuse
`FormatGaps.to_dict()` (`:277`), which is already always emitted in full by
`ll-issues format-check <ID> --format json`'s single-issue path
(`scripts/little_loops/cli/issues/format_check.py:282-318`) — no new CLI
plumbing is needed for the value to reach the FSM predicate.

### Signatures

Current (unchanged) predicate — `check_reconcile_needed`
(`scripts/little_loops/loops/autodev.yaml:1406-1460`), the exact code the new
predicate term is OR'd into:

```python
plateau = (pre != '' and pre == cur and not attempted)
fresh_below = (pre == '' and cur != ''
               and int(cur) < ${context.readiness_threshold} and not attempted)
sys.exit(0 if (plateau or fresh_below) else 1)
```

Proposed new public helper in `issue_parser.py`, reusing the existing private
constants verbatim (no new parsing logic — matches this codebase's
established private-helper/public-wrapper pairing, e.g.
`count_open_questions_in_sections()` wrapping `_count_unresolved_items_in_text()`
at `issue_parser.py:1085-1120`):

```python
def superseded_marker_count(issue_path: Path) -> int:
    content = issue_path.read_text()
    return sum(
        body.count(_SUPERSEDED_MARKER_PREFIX)
        for name in _SUPERSEDED_DIRECTIVE_SECTIONS
        for body in _heading_bodies(content, name)
    )
```

This reuses `_SUPERSEDED_MARKER_PREFIX`, `_SUPERSEDED_DIRECTIVE_SECTIONS`, and
`_heading_bodies()` exactly as `check_format_gaps()`'s
`unmarked_superseded_directive` computation already does
(`issue_parser.py:546-559`).

### Call Path

`check_reconcile_needed` (shell_exit fragment) → subprocess pipe
`ll-issues show ${captured.input.output} --json | python3 -c "..."` (existing,
unchanged) **plus** a second subprocess call
`ll-issues format-check ${captured.input.output} --format json`, backed by
`check_format_gaps` → the new marker-presence key is read from
`python3 -c "..."` → OR'd into the existing `sys.exit(0 if
(plateau or fresh_below or contradiction) else 1)` → `on_yes: reconcile_current`
(existing, unchanged) → `count_repair_cycle_reconcile` (existing state, already
wired) → `rerun_confidence_after_reconcile` → `recheck_after_size_review`.

> **Interpolation note**: the issue ID in this state is `${captured.input.output}`
> — there is no `${ID}` context variable at `check_reconcile_needed` (the bare
> `ID=` shell assignment exists only in `count_repair_cycle_refine_for_design`
> and `recheck_after_size_review`). Earlier drafts of this section wrote
> `${ID}`; do not copy that.

> **Correction — the cap is not the shared counter.** This section previously
> asserted that `count_repair_cycle_reconcile`'s shared
> `autodev-repair-cycle-count.txt` and the `CYCLE_COUNT >= 2` stagnation
> ceiling bound a second reconcile fire, and that no new counter state is
> needed. Verified against the tree, both claims are false: the ceiling at
> `autodev.yaml:1910` is conditioned on `CUR <= PRE` (a reconcile that improves
> readiness is never capped), it is a deferral-reason branch rather than a gate
> on `check_reconcile_needed`, and the counter is shared across all six
> repair-class states so sibling repairs can exhaust it before reconcile fires
> once. A reconcile-scoped counter **is** new work — see ## Proposed Solution
> § "Arming: decided". The shared increment stays as-is; the new one is
> additive.

### Deviations

_2026-08-02, `/ll:manage-issue` — implementation departed from the directive
sections above in three places. Original content above is unmodified._

1. **Counter increment plumbing (Implementation Step 4).** Step 4 said to
   increment `autodev-contradiction-reconcile-count.txt` in
   `count_repair_cycle_reconcile`. Implemented there as specified, but via a
   consume-once handshake rather than unconditionally: `check_reconcile_needed`
   touches `${context.run_dir}/autodev-contradiction-reconcile-armed` only when
   it fired on a contradiction *alone* (neither `plateau` nor `fresh_below`),
   and `count_repair_cycle_reconcile` checks-and-removes that marker before
   incrementing. Reason: `count_repair_cycle_reconcile` is also the successor
   of plateau-driven reconciles, so an unconditional increment would burn the
   contradiction budget on fires that never used it, and AC5's three-pass
   sequence would not be reproducible. `dequeue_next` additionally resets the
   counter (and the armed marker) — without that the cap of 2 would be shared
   across every issue in the run rather than the per-issue bound AC5 describes.

2. **Step 5 took the stated fallback, not the primary option.** Step 5 offered
   "arm via a per-issue touch-file *rather than* `reconcile_attempted`, **or**
   amend the `:1942` predicate". The first is unreachable without widening
   reconcile's contract — `/ll:reconcile-issue` stamps `reconcile_attempted:
   true` unconditionally (`reconcile-issue.md:99`) and nothing in scope stops
   it. Implemented the fallback: `count_repair_cycle_reconcile` writes the
   per-issue `autodev-contradiction-reconcile-$ID` stamp, and the `:1942`
   selector reads it via `CONTRA_ONLY` to distinguish the two arming sources,
   dispatching `spike` (the remedy AC5a exists to protect) instead of empty.
   Plateau-driven reconciles carry no stamp and behave byte-identically.

3. **Implementation Step 11's target does not exist.** `.claude/CLAUDE.md`
   § Issue File Format has no plateau-gate paragraph — `grep -n reconcile
   .claude/CLAUDE.md` returns only the line-89 command catalog entry. The
   canonical mechanism narrative is `docs/guides/LOOPS_REFERENCE.md`, which
   Step 9 already covers; the contradiction clause landed there. CLAUDE.md was
   left unchanged rather than growing a mechanism paragraph it never had.

4. **Marker count is a standalone helper, not a `FormatGaps` field** (Step 1
   permitted either). `FormatGaps.to_dict()` is typed `dict[str, list[str]]`
   and `has_gaps` ORs every field, so an `int` that is not a gap would have
   broken both the type contract and the exit code. `superseded_marker_count()`
   is a module-level public function; `format-check`'s single-issue JSON path
   merges the value in as a sibling key.

## Integration Map

### Files to Modify

> ⚠ Superseded — every line number in this issue predates `56893def`
> (ENH-2995), which shifted `commands/refine-issue.md` by ~46 lines, and
> BUG-3001/BUG-3002 will move both `refine-issue.md` and `autodev.yaml` again.
> **Line numbers here are deliberately left uncorrected** — resolve every
> anchor by symbol/heading at implementation time, not by line. Known drift as
> of 2026-08-02: pipeline diagram 791 → 837 (plus 847, 852); `## NEXT STEPS`
> 753-758 → 799-805; `test_builtin_loops.py` 5613 → 5621.

- `scripts/little_loops/loops/autodev.yaml` — `check_reconcile_needed` state:
  add the contradiction predicate; revisit the `reconcile_attempted` one-shot
  arming
- `scripts/little_loops/issue_parser.py` — public marker-presence surface (see
  "Detection: decided"); or the shared verdict subcommand if BUG-3002's cleanup
  lands first
- `commands/refine-issue.md` — pipeline diagrams and `## NEXT STEPS` output
  block, plus the `.gemini` / `.kimi-code` mirrors
- `commands/reconcile-issue.md` — **in scope** (Option A selected): Contract
  section plus Step 5 and the no-op branch, to clear the `⚠ Superseded` marker
  on every directive line reconcile evaluates

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/autodev.yaml:1942` — `recheck_after_size_review`'s
  **pre-deferral remedy dispatcher**. Its inline predicate
  `if d.get('spike_attempted') == 'true' or d.get('reconcile_attempted') == 'true':
  print('')` returns an empty remedy — dispatching *neither* `spike` nor
  `reconcile` — for any issue already stamped. Because `/ll:reconcile-issue`
  unconditionally writes `reconcile_attempted: true`
  (`commands/reconcile-issue.md:99`), firing reconcile on contradiction
  permanently burns this budget for issues that never had a readiness problem,
  silently removing their access to the `spike` remedy. Not a test pin — a live
  behavioral consumer, and the one this issue is most likely to regress. See
  Implementation Step 5.
- `scripts/little_loops/cli/issues/show.py:225,419-420` — the only producer of
  the `reconcile_attempted` key the predicates above read.

_Wiring pass added by `/ll:wire-issue`:_
- **Clarifying finding**: `commands/reconcile-issue.md`'s `--check` mode is
  documented as an FSM-evaluator contract (exit 0 = `NEEDED`, exit 1 = `CLEAN`)
  but currently has **zero callers** — `check_reconcile_needed` in
  `autodev.yaml` (~1406-1460) never invokes `/ll:reconcile-issue --check`; it
  runs a self-contained inline-Python predicate over `ll-issues show --json`
  snapshots instead. Proposed Solution's "extend `--check`" framing therefore
  means either (a) newly wiring a slash-command evaluator into
  `check_reconcile_needed` (bigger structural change than "widen the gate"),
  or (b) adding the contradiction predicate as a second inline-Python check
  alongside the existing one, leaving `--check`'s still-consumer-less contract
  untouched. Resolve this explicitly before implementation.

  > ⚠ Superseded — resolved. Neither (a) nor (b): the predicate reads
  > `ll-issues format-check ${ID} --format json` inline, an option that did not
  > exist when this note was written (ENH-2995, `56893def`). `--check` stays
  > consumer-less and untouched. See "Detection: decided" in Proposed Solution.
  > This closes the Architecture Compliance 15/20 and the ambiguity risk factor
  > recorded in Confidence Check Notes.
- `scripts/tests/test_autodev_loop.py` — `_run_reconcile_predicate()` helper
  (subprocess-execs the state's action) backs a `TestCheckReconcileNeeded*`
  suite; also `check_atomic_design_remedy`/selector tests (~439-455) that
  hardcode `reconcile_attempted` as a boolean gate in a **sibling** state, and
  `test_dispatcher_routes_pending_remedy_to_reconcile_current` (~657) — another
  routing edge into `reconcile_current` sharing the same one-shot guard.

  > ⚠ Superseded — **BUG-3002 deletes both of these consumers.** Its selected
  > Option A retargets the `design_gate_failed` remedy from `reconcile_current`
  > to a new `refine_for_design` state, "leaving `reconcile_current` untouched
  > for the plateau case it was built for." Land BUG-3002 first and this
  > issue's blast radius shrinks by two named consumers; land them
  > concurrently and they collide on the same routing edges and test pins.
  > Re-measure the surviving pin list against `main` before implementing —
  > the "11+ existing tests" figure in Confidence Check Notes is a pre-BUG-3002
  > count.
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`, ~4127-6411) —
  structural assertions on `check_reconcile_needed`'s action/routing:
  `test_reconcile_states_exist` (5824), `test_check_reconcile_needed_fires_for_fresh_below_threshold`
  (5613, **will break** — pins the literal `"plateau or fresh_below"` boolean
  expression), `test_check_reconcile_needed_routes_through_guard2_verdict`
  (5152), `test_check_reconcile_needed_predicate_reads_snapshot_and_guard`
  (5846), `test_check_reconcile_needed_routing` (5860), `test_reconcile_current_invokes_reconcile_skill`
  (5870), `test_rerun_confidence_after_reconcile_routing` (5884),
  `test_recheck_after_size_review_arms_remedy_before_low_readiness` (5569),
  `test_recheck_after_size_review_measurement_gate_precedes_ambiguity_fallback`
  (5591), `test_pre_deferral_remedy_gate_routing` / `test_pre_deferral_remedy_dispatch_routing`
  (5544/5554) — all read `reconcile_attempted` as a sibling consumer.
- `scripts/tests/test_reconcile_issue_command.py` — `TestReconcileCheckModeCoverage`
  (159-181, slices between `"### 7. Check Mode Behavior"` and `"## Output Format"`)
  and `TestReconcileGuardAndOutput.test_arms_reconcile_attempted_guard` (64).
- `.ll/decisions.d/995f5144-debd-4e55-a188-b10445796f56.json` — existing
  decision-log entry already tracking this issue; close/annotate via
  `ll-issues decisions outcome` on completion.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed against the current tree (post-BUG-3002): the six named
  `test_builtin_loops.py::TestAutodevLoop` pins are still live and unmodified
  — `test_check_reconcile_needed_fires_for_fresh_below_threshold` is now at
  `:5615-5623` (drifted +2 from the `:5613` cited above),
  `test_reconcile_states_exist` at `:5826`,
  `test_check_reconcile_needed_predicate_reads_snapshot_and_guard` at `:5848`,
  `test_check_reconcile_needed_routing` at `:5862`,
  `test_reconcile_current_invokes_reconcile_skill` at `:5872`,
  `test_rerun_confidence_after_reconcile_routing` at `:5886`. Per the section
  header note above, resolve by symbol at implementation time regardless.
- `_run_reconcile_predicate(run_dir, *, confidence, reconcile_attempted)`
  (`scripts/tests/test_autodev_loop.py:46-80`) — still the correct harness for
  new contradiction-predicate test cases; it subprocess-execs the state's
  action script directly rather than driving the FSM, so it can exercise the
  new `contradiction` term in isolation the same way it already exercises
  `plateau`/`fresh_below`.
- `commands/reconcile-issue.md` and `autodev.yaml` both still have zero
  occurrences of `--check` — confirms the "Detection: decided" note above:
  `/ll:reconcile-issue --check` remains a genuinely uncalled contract, not
  something this issue's predicate should route through.

### Similar Patterns
- `autodev.yaml:1684` and `autodev.yaml:1964` — existing fallback routes into
  `reconcile_current`; the new predicate should compose with these, not
  duplicate them
- FEAT-2751's `autodev-repair-cycle-count.txt` mechanism — the established
  pattern for bounding repeated repair-class attempts within a cycle; reuse it
  rather than inventing a new cap

_Added by `/ll:refine-issue` — based on codebase analysis:_
- `count_repair_cycle_reconcile` (`autodev.yaml:1749-1759`) **already exists**
  as `reconcile_current`'s successor state — it is not new work to introduce,
  only to route the contradiction branch through. The five sibling counter
  states share byte-identical action bodies:
  `count_repair_cycle_refine` (`:452`), `count_repair_cycle_wire` (`:754`),
  `count_repair_cycle_spike` (`:1218`), `count_repair_cycle_size_review`
  (`:1283`), `count_repair_cycle_refine_for_design` (`:1710-1729`, the
  BUG-3002-added variant). The shared cap they all feed —
  `CYCLE_COUNT >= 2` in `recheck_after_size_review`
  (`autodev.yaml:1799-1805`) — is the actual mechanism bounding a second
  reconcile fire, not a marker-specific counter.
- `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_skills_and_commands.py:20-45`
  is `list[tuple[str, str, str]]` of `(doc_path, expected_string, issue_id)`,
  e.g. `("commands/refine-issue.md", "**Status enum**:", "ENH-1550")`. Several
  entries for the same file are the established way to lock multiple strings
  (e.g. `align-issues.md` has three ENH-1362 tuples) — relevant here since
  Change B touches three separate pipeline diagrams plus the Next Steps block
  in the same file.

### Tests
- `scripts/little_loops/loops/autodev.yaml` holds the state; the four test
  modules below are the full current coverage surface.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop` — update
  `test_check_reconcile_needed_fires_for_fresh_below_threshold` (~5613, exact
  break — pins `"plateau or fresh_below"`), `test_check_reconcile_needed_predicate_reads_snapshot_and_guard`
  (~5846, extend to also assert the new contradiction marker), and
  `test_reconcile_states_exist` (~5824, add a name if a cap-tracking state is
  introduced). Routing pins (`test_check_reconcile_needed_routing` ~5860,
  `test_reconcile_current_invokes_reconcile_skill` ~5870,
  `test_rerun_confidence_after_reconcile_routing` ~5884) only break if
  `on_yes`/`on_no`/`next` targets themselves change.
- `scripts/tests/test_autodev_loop.py` — extend the `_run_reconcile_predicate()`-backed
  `TestCheckReconcileNeeded*` suite (~46-292) with cases exercising the new
  contradiction predicate independent of plateau; new test if the one-shot cap
  becomes a distinct counter state (follow the `count_repair_cycle_*` pattern
  used for FEAT-2751).
- `scripts/tests/test_reconcile_issue_command.py::TestReconcileCheckModeCoverage`
  (~159-181) — add assertions for a generalized contradiction verdict if
  `--check` is extended.
- New test needed (no existing coverage): `commands/refine-issue.md`'s
  pipeline diagram / NEXT STEPS block has zero test coverage today. Add a
  `("commands/refine-issue.md", "/ll:reconcile-issue", "ENH-2992")` tuple to
  `scripts/tests/test_wiring_skills_and_commands.py`'s `DOC_STRINGS_PRESENT`
  table (existing convention, e.g. line 26's ENH-1550 entry) to lock in
  Change B once shipped.

_Added by `/ll:refine-issue` — based on codebase analysis:_
- Step 1a's new `superseded_marker_count()`-style public helper (see
  ## Program Design) has no existing coverage — `scripts/tests/test_issue_parser.py`
  is the module holding parser-level tests and is where a unit test for it
  belongs (parallel to whatever test already covers
  `unmarked_superseded_directive`). If the signal is instead surfaced as a new
  `FormatGaps` field, `scripts/tests/test_ll_issues_format_check.py` is the
  CLI-level test module to extend.

### Documentation
- TBD — docs that need updates

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — ASCII routing diagram (~1034-1035:
  `check_reconcile_needed → [pre-spike Readiness == post-spike AND NOT
  reconcile_attempted?] (ENH-2689)`) and the "Post-spike reconcile plateau
  (ENH-2689)" prose paragraph (~1051) both need a contradiction OR-branch
  clause and updated one-shot-arming description.
- `docs/reference/COMMANDS.md` — `### /ll:reconcile-issue` section (~279-292),
  specifically the `--check` flag line (~284) and "When to run" (~288).
- `.claude/CLAUDE.md` § Issue File Format — the FEAT-2751/ENH-2666/BUG-2803
  paragraph narrating `check_reconcile_needed`'s plateau predicate and
  stagnation backstop is the canonical mechanism narrative other issues layer
  onto; needs a companion clause for the contradiction branch.

_Added by `/ll:refine-issue` — based on codebase analysis:_
- A **third** `refine-issue` mirror exists beyond `.gemini` and `.kimi-code`:
  `skills/ll-refine-issue/SKILL.md` (a Codex Skills API bridge). Unlike the
  other two mirrors, it does not duplicate the pipeline diagram or Next Steps
  text — it is a thin stub reading "Bridged from `commands/refine-issue.md`
  ... See the source command file for the full prompt body." Change B does
  **not** need to touch this file; flagging it here so the implementer doesn't
  spend time hunting for reconcile text in it or assume it needs the same
  regeneration step as the other two mirrors.

### Configuration
- N/A

## Implementation Steps

_Assembled from `/ll:wire-issue`'s wiring analysis (previously stranded under a
`### Wiring Phase` subsection while this section read "TBD") and the resolved
decisions in ## Proposed Solution. The former step 1 — "resolve the `--check`
wiring ambiguity" — is dropped, not renumbered: that ambiguity is settled (see
"Detection: decided"), as is the marker-lifecycle question that superseded it
(see "Decision Rationale" and "Arming: decided")._

1. **Add the marker-presence query surface.** Public helper
   `superseded_marker_count(issue_path) -> int` in
   `scripts/little_loops/issue_parser.py` per ## Program Design § Signatures,
   reusing `_SUPERSEDED_MARKER_PREFIX` / `_SUPERSEDED_DIRECTIVE_SECTIONS` /
   `_heading_bodies()` verbatim; or an equivalent `FormatGaps` field.
   `format-check` today reports only the inverse
   (`unmarked_superseded_directive`). Unit-test in
   `scripts/tests/test_issue_parser.py`, or
   `scripts/tests/test_ll_issues_format_check.py` if surfaced as a
   `FormatGaps` field.

2. **Teach `/ll:reconcile-issue` to clear markers.** `commands/reconcile-issue.md`
   — Contract section plus Step 5 *and* the no-op branch
   (`reconcile-issue.md:140-142`): clear the `⚠ Superseded` marker on every
   directive line reconcile evaluated, not only lines it rewrote. Match
   refine's existing "Bounded marker-removal right"
   (`commands/refine-issue.md:534-540`) rule-for-rule — containment test on the
   `⚠ Superseded` prefix, only marker lines deletable, silent deletion, no
   tombstone. This is the structural half of the loop bound and must land in
   the same change as step 3, not after it.

3. **Extend `check_reconcile_needed`'s predicate**
   (`scripts/little_loops/loops/autodev.yaml`) with a `contradiction` term OR'd
   into the existing `plateau or fresh_below` expression, read from a second
   inline call to `ll-issues format-check ${captured.input.output} --format json`.
   Per "Arming: decided", the `contradiction` term is **not** gated by
   `reconcile_attempted`.

4. **Add the reconcile-scoped fire counter.** Increment
   `${context.run_dir}/autodev-contradiction-reconcile-count.txt` in
   `count_repair_cycle_reconcile` alongside the existing shared
   `autodev-repair-cycle-count.txt` increment (leave that one untouched — the
   FEAT-2751 stagnation backstop still needs it), and read it as a third guard
   term in the contradiction predicate with a cap of 2. The existing shared
   `CYCLE_COUNT >= 2` ceiling does **not** bound this branch; see the
   correction in ## Program Design § Call Path.

5. **Preserve the pre-deferral remedy budget.** Ensure a contradiction-only
   reconcile does not cause `recheck_after_size_review`'s dispatcher
   (`autodev.yaml:1942`) to suppress *both* remedies for the issue — arm the
   contradiction branch via a per-issue run-dir touch-file
   `autodev-contradiction-reconcile-$ID` (BUG-3002's
   `autodev-design-remedy-attempted-$ID` precedent) rather than via
   `reconcile_attempted`, or amend the `:1942` predicate to distinguish the two
   arming sources. See "Side effect: reconcile stamping burns the pre-deferral
   remedy budget". Do not land step 3 without one of these.

6. **Change B — surface the human path.** `commands/refine-issue.md`: pipeline
   diagrams (three of them) and the `## NEXT STEPS` block name
   `/ll:reconcile-issue`, folded onto the `ll-issues format-check --format json`
   call BUG-3001 landed at Step 6.5 (`refine-issue.md:744`) rather than added
   as separate prose. Regenerate `.gemini/commands/refine-issue.toml` and
   `.kimi-code/skills/ll-refine-issue/SKILL.md`.
   `skills/ll-refine-issue/SKILL.md` is a thin bridge stub and needs no edit.

7. **Update loop and predicate tests.**
   `scripts/tests/test_builtin_loops.py::TestAutodevLoop` and
   `scripts/tests/test_autodev_loop.py` per the Tests subsection —
   `test_check_reconcile_needed_fires_for_fresh_below_threshold` pins the
   literal `"plateau or fresh_below"` string and needs that string updated, not
   just extended. Extend the `_run_reconcile_predicate()`-backed suite with
   cases exercising `contradiction` independent of `plateau`, the marker-cleared
   no-refire case (AC4), and the second-distinct-marker case (AC5).

8. **Update `commands/reconcile-issue.md` tests.**
   `scripts/tests/test_reconcile_issue_command.py` — cover the new
   marker-clearing Contract clause, including on the no-op branch.

9. **Docs.** `docs/guides/LOOPS_REFERENCE.md` (ASCII routing diagram ~1034-1035
   and the "Post-spike reconcile plateau (ENH-2689)" paragraph ~1051) and
   `docs/reference/COMMANDS.md` (`### /ll:reconcile-issue`, ~279-292), per the
   Documentation subsection.

10. **Lock Change B.** Add a `("commands/refine-issue.md", "/ll:reconcile-issue",
    "ENH-2992")` tuple to `DOC_STRINGS_PRESENT` in
    `scripts/tests/test_wiring_skills_and_commands.py`.

11. **Update `.claude/CLAUDE.md`** § Issue File Format's plateau-gate paragraph
    with the contradiction-branch clause.

## Impact

- Closes the loop between the problem refine creates and the skill built to
  fix it.
- Affects ~316 existing issues and every future refine pass.
- Change B alone makes reconcile discoverable to humans at zero risk.

## Acceptance Criteria

1. `check_reconcile_needed` routes to `reconcile_current` when the issue's
   directive sections carry a `⚠ Superseded` marker **and the readiness score
   has changed from the pre-repair snapshot** (`pre != cur`, so `plateau` is
   false) — proving the contradiction branch fires independently of the plateau
   branch. Note the earlier wording of this criterion ("score unchanged, i.e.
   no plateau") was inverted: an unchanged score *is* the plateau condition
   (`plateau = (pre != '' and pre == cur and not attempted)`,
   `autodev.yaml:1451`), so it could not have demonstrated independence.
2. The predicate is evaluated in Python with no LLM in the routing chain;
   `ll-loop validate autodev` reports MR-1 clean.
3. Marker presence is read through a public, tested surface — not by
   re-implementing `_SUPERSEDED_MARKER_PREFIX` matching inline, and not by
   prose in a skill (`ll-verify-skill-prose` flags the latter).
4. A directive line whose marker reconcile has already acted on does not
   re-trigger the gate on the next pass. Test: two consecutive passes over the
   same issue with one marker → exactly one `reconcile_current` entry.
   **Covers both reconcile outcomes**: the rewrite path *and* the no-op path
   (`RECONCILED` with empty `## CORRECTIONS_MADE`), which today makes no edits
   at all and would otherwise leave the marker standing.
5. A *second, distinct* contradiction discovered on a later pass is eligible
   for a second reconcile, bounded by the new reconcile-scoped counter
   (`autodev-contradiction-reconcile-count.txt`, cap 2 — **not** the shared
   `autodev-repair-cycle-count.txt` / `CYCLE_COUNT >= 2` ceiling, which is
   readiness-conditioned and shared across six repair classes; see ## Program
   Design § Call Path). Test: pass 1 marker A → reconcile; pass 2 marker B →
   reconcile; pass 3+ → capped, no further entries, with no sibling repair-class
   state having run so the result is attributable to the reconcile-scoped cap.
5a. A contradiction-only reconcile does not suppress the issue's later
   pre-deferral remedy dispatch. Test: fire the contradiction branch on an
   issue with passing readiness, then drive it to `recheck_after_size_review`
   below threshold — `autodev.yaml:1942` still dispatches a remedy (`spike` or
   `reconcile`) rather than returning empty.
6. Issues with no marker and no plateau reach `check_size_review_ran_this_pass`
   exactly as they do today — no behavior change off the new branch.
7. `commands/refine-issue.md` names `/ll:reconcile-issue` in its `## NEXT STEPS`
   block and pipeline diagram(s), locked by a `DOC_STRINGS_PRESENT` tuple in
   `scripts/tests/test_wiring_skills_and_commands.py`; the `.gemini` and
   `.kimi-code` mirrors carry the same text.
8. `python -m pytest scripts/tests/` exits 0, with each test named in the
   Dependent Files subsection verified individually rather than only in bulk.

## Success Metrics

- Reconcile invocation rate rises from 1% of refined issues toward the rate at
  which markers are actually written.

  > ⚠ Superseded — the "~24% contradiction rate" figure was measured
  > pre-ENH-2995 using correction-phrase heuristics over
  > `### Codebase Research Findings`. Post-ENH-2995 the denominator is
  > *marker* count, which only accrues on issues refined after `56893def` —
  > the ~316-issue backlog carries the condition but not the marker. State the
  > target against markers written, and measure over issues refined after the
  > ENH-2995 cutover only.

- No rise in autodev cycle count per issue. Measurement mechanism must be
  named before this is a metric — candidate: `count_repair_cycle_reconcile`
  values in run artifacts, compared across a fixed issue set before/after.
- `ll-loop validate autodev` stays clean — in particular MR-1 (the new
  predicate must have a non-LLM evaluator in its routing chain).

## Scope Boundaries

- Does **not** change *which sections* reconcile rewrites — the
  rewrite-eligible vs preserve-untouched lists in its Contract are unchanged.
  Its Contract does gain one narrow addition (Option A, selected): clearing the
  `⚠ Superseded` marker on every directive line reconcile evaluates, on both
  the rewrite and no-op paths. This restates the boundary now that the
  marker-lifecycle question is resolved; the argument that marker-clearing sits
  inside reconcile's existing scope — and is distinct from the "widen the
  contract" proposal BUG-3002 scored 5/12 and rejected — is made explicitly in
  ## Proposed Solution § Decision Rationale.
- Does **not** amend the Preservation Rule; that is ENH-2995 (landed).
- Does **not** make reconcile unbounded — marker-clearing plus a
  reconcile-scoped per-run cap of 2 remain.
- Does **not** change the `:1942` pre-deferral dispatcher's behavior for
  plateau/readiness-driven reconciles. The only requirement is that a
  *contradiction-only* fire must not consume that budget (Implementation
  Step 5). Broader rework of `reconcile_attempted`'s semantics is out of scope.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/reconcile-issue.md` | Defines the remedy and its `--check` mode |
| `scripts/little_loops/loops/autodev.yaml` | Contains the gate being widened |
| `scripts/little_loops/issue_parser.py` | ENH-2995 marker convention + `unmarked_superseded_directive` gap class; where the marker-presence surface goes |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 constrains the new predicate's evaluator |
| ENH-2995 (done, `56893def`) | Supplies the detection signal this issue routes on |
| BUG-3001 (**done**) | Restructured the `refine-issue.md` region Change B edits; its `format-check --format json` call is live at `refine-issue.md:744` — fold Change B onto it |
| BUG-3002 (**done**) | Retargeted `design_gate_failed` off `reconcile_current`, deleting two of this issue's named test consumers; no longer blocking |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW

### Outcome Risk Factors
- Very wide blast radius (Pattern A) on the routing edge being changed:
  existing tests across `test_builtin_loops.py`, `test_autodev_loop.py`, and
  `test_reconcile_issue_command.py` hardcode or pin the current
  `check_reconcile_needed` predicate string, routing targets, and the
  `reconcile_attempted` one-shot guard. Any change to the predicate or the
  one-shot arming risks breaking several of these simultaneously — verify each
  named test individually rather than relying on a single suite run to catch
  regressions.

  > ⚠ Superseded — the "11+ existing tests" figure was a **pre-BUG-3002**
  > count and is no longer accurate: BUG-3002 has landed and deleted two of the
  > named consumers (`test_dispatcher_routes_pending_remedy_to_reconcile_current`
  > survives only as `..._to_refine_for_design`). Re-measure the surviving pin
  > list against `main` before implementing rather than trusting this number.
  > The *qualitative* risk — pins on the literal predicate string and on
  > `reconcile_attempted` as a sibling guard — still holds.

- **New, not reflected in the 53/100 score**: the `autodev.yaml:1942`
  pre-deferral remedy dispatcher is a live behavioral consumer of
  `reconcile_attempted`, not merely a test pin. Widening the gate without
  Implementation Step 5 silently removes the `spike` remedy from any issue that
  ever hits a contradiction-only reconcile. This is a correctness risk with no
  failing test to catch it today, and it is the single most likely way this
  change regresses production loop behavior.
- Broad enumeration across ~10+ change sites spanning distinct
  toolchains — FSM YAML (`autodev.yaml`), Python parser (`issue_parser.py`),
  three command-file mirrors, two docs files, and four test modules. No
  single site is deep, but cross-module coordination (a new predicate term,
  a new public helper, and a marker-clearing edit to `reconcile-issue.md`'s
  Contract, all landing together) raises the chance of a partial or
  inconsistent landing versus a single-file change of similar total size.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- Wide blast radius (Pattern A) on a live behavioral routing edge, not just
  test pins: `check_reconcile_needed`'s predicate string, `reconcile_attempted`
  guard, and routing targets are pinned across `test_builtin_loops.py`,
  `test_autodev_loop.py`, and `test_reconcile_issue_command.py` (all six named
  loop-structure pins re-verified at their current line numbers this pass —
  `test_check_reconcile_needed_fires_for_fresh_below_threshold` at :5615,
  `test_reconcile_states_exist` at :5826, and four others), and
  `autodev.yaml:1942`'s pre-deferral dispatcher is a live consumer of
  `reconcile_attempted`, not merely a test pin — landing Step 3 without Step 5's
  budget fix silently removes the `spike` remedy from contradiction-only
  reconciles with no failing test to catch it.
- Broad enumeration across ~10+ change sites spanning FSM YAML, Python parser,
  three command-file mirrors, two docs files, and four test modules — no single
  site is deep, but cross-module coordination (new predicate term, new public
  helper, new counter state, marker-clearing edit to reconcile's Contract, all
  landing together per Implementation Step 2's "must land in the same change as
  step 3" note) raises the risk of a partial or inconsistent landing.

## Resolution

_Implemented 2026-08-02 via `/ll:manage-issue`._

**Change A — the automated gate.** `check_reconcile_needed`
(`scripts/little_loops/loops/autodev.yaml`) now OR's a third `contradiction`
term into `plateau or fresh_below`. The shell action captures `ll-issues
format-check "$ID" --format json` into a variable and passes it through the
environment (`LL_FORMAT_CHECK_JSON`) so the state keeps exactly one inline
`python3 -c` predicate — deterministic Python, MR-1 clean. The term is
`markers > 0 and fires < 2`, deliberately ungated by `reconcile_attempted`.

**Detection surface.** New public `superseded_marker_count(issue_path) -> int`
in `scripts/little_loops/issue_parser.py`, reusing `_SUPERSEDED_MARKER_PREFIX`
/ `_SUPERSEDED_DIRECTIVE_SECTIONS` / `_heading_bodies()` verbatim, surfaced as
a `superseded_marker_count` key on `format-check`'s single-issue JSON payload.
Not a `FormatGaps` field — marker presence is not a structural gap and must not
feed `has_gaps` or the exit code.

**Bounding, structural then counted.** `/ll:reconcile-issue` now clears the
`⚠ Superseded` marker on every directive line it evaluated — on the rewrite
path (Step 5 extends the Edit span) *and* on the no-op branch, where clearing
becomes the pass's only edit. Rule-for-rule identical to refine's existing
"Bounded marker-removal right" so there is one marker lifecycle, not two. On
top of that, a reconcile-scoped per-issue budget of 2
(`autodev-contradiction-reconcile-count.txt`, consume-once handshake into
`count_repair_cycle_reconcile`, reset at `dequeue_next`). The shared FEAT-2751
`CYCLE_COUNT >= 2` ceiling was verified *not* to bound this branch and was left
untouched.

**Regression guard (AC5a).** `recheck_after_size_review`'s pre-deferral remedy
dispatcher treated `reconcile_attempted` as "readiness remedy spent" and
returned no remedy at all. Since a contradiction fire has no relationship to
readiness, `count_repair_cycle_reconcile` stamps
`autodev-contradiction-reconcile-$ID` on such fires and the dispatcher
dispatches `spike` when it sees one — closing the silent loss of the spike
remedy this issue's Confidence Check Notes flagged as the most likely
production regression.

**Change B — the human path.** `commands/refine-issue.md` gained a Step 6.7
`superseded_marker_count` gate (folded onto BUG-3001's existing `format-check`
call), a `## NEXT STEPS` entry, an output-report row, and a conditional
reconcile branch on its canonical pipeline diagram. `.gemini` and `.kimi-code`
mirrors regenerated via `ll-adapt`; `skills/ll-refine-issue/SKILL.md` is a thin
bridge stub and needed no edit, as predicted.

**Docs**: `docs/guides/LOOPS_REFERENCE.md` (routing diagram + mechanism
paragraph), `docs/reference/COMMANDS.md`, `docs/reference/CLI.md`,
`docs/reference/API.md`.

**Verification**: `python -m pytest scripts/tests/` → 17978 passed, 42 skipped.
`ruff check scripts/` clean. `ll-loop validate autodev` valid (AC2). Every test
named in Dependent Files re-run individually (AC8). `mypy` reports only two
pre-existing errors in `cli/issues/normalize.py`, confirmed present on `main`.

See `### Deviations` under `## Program Design` for the four places
implementation departed from the directive sections.

## Session Log
- `/ll:manage-issue` - 2026-08-02T22:27:52 - `8ee80aea-872f-44f1-860a-ddca61811562.jsonl`
- `/ll:ready-issue` - 2026-08-02T21:35:33 - `c086abeb-757e-43bc-a9ce-55391abe3204.jsonl`
- `/ll:confidence-check` - 2026-08-02T21:31:03 - `a19bb83d-629a-488d-832c-2afbb30f5117.jsonl`
- `/ll:ready-issue` - 2026-08-02T21:16:57 - `45e00442-b901-444b-929d-0f4d78b17ea4.jsonl`
- `/ll:refine-issue` - 2026-08-02T21:08:50 - `49653a5a-d7ff-4b8f-a6b8-2d4013dc7e17.jsonl`
- `/ll:confidence-check` - 2026-08-02T21:06:50 - `fa4f5cf7-5457-4423-9741-a8025cdbaf37.jsonl`
- `/ll:decide-issue` - 2026-08-02T20:58:39 - `bc3cf078-a345-4297-857c-b20009b9e1f3.jsonl`
- `/ll:refine-issue` - 2026-08-02T20:53:53 - `b1ec4ad5-58ed-4d88-9770-95462c7e4cd4.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:26:31 - `0a208318-6b67-47ba-88f1-23b17a2f5884.jsonl`
- `/ll:confidence-check` - 2026-08-02T15:25:07 - `cc770090-bce7-4043-b70f-eaa9a130277c.jsonl`
- `/ll:wire-issue` - 2026-08-02T15:21:04 - `ced002cf-1c4b-4fb0-81ad-841dca8598ba.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:14:35 - `674c1fcd-abda-4e29-9d3f-07a624c63f75.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:56 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
