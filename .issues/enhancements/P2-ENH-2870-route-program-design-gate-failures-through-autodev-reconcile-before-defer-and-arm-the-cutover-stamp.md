---
id: ENH-2870
title: Route program-design gate failures through autodev reconcile-before-defer and
  arm the cutover stamp
type: ENH
priority: P2
status: done
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
blocked_by:
- ENH-2852
relates_to:
- ENH-2871
- FEAT-2855
- FEAT-2867
labels:
- rework
- verification
- automation
confidence_score: 100
outcome_confidence: 76
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 16
completed_at: '2026-07-28T04:07:12Z'
---

# ENH-2870: Route program-design gate failures through autodev reconcile-before-defer and arm the cutover stamp

Split from ENH-2852 (2026-07-27): the core gate ships fail-open (no cutover stamp
written), so nothing can mass-defer before this routing exists. This issue adds the
autodev deferral routing for the new gate and — as its final AC — arms the gate in this
repo by writing the stamp. The sequencing is self-enforcing: the stamp is only safe to
write once the reconcile-before-defer routing exists, and that routing is this issue.

## Summary

ENH-2852 adds a deterministic `## Program Design` specificity gate inside
`check_format_gaps()` / `ll-issues format-check`, consumed by `/ll:confidence-check` as a
hard override. That override is **prose-only** — it flips the human-readable verdict to
`STOP — ADDRESS GAPS` but leaves the persisted numeric scores untouched, and autodev's
gates read only the numbers. Once the gate is armed, a design-less issue with a passing
readiness score therefore sails straight through autodev to implementation, bypassing the
gate entirely. Make the gate visible to autodev, then give its failure its own routing:
reconcile-before-defer, and a distinct machine reason code when the remedy fails.

## Current Behavior

After ENH-2852 core ships (unstamped), the gate is off everywhere. Once armed, autodev
still does not see it. `skills/confidence-check/SKILL.md:296` (Program Design Hard
Override) changes only the emitted verdict "regardless of aggregate score"; Phase 4
(`SKILL.md:302-322`) persists `confidence`/`outcome` to frontmatter unchanged. Autodev's
gate states read exactly those two numbers and nothing else:

```python
# autodev.yaml — identical block in all THREE gate states (see below)
conf = int(d.get('confidence') or 0); outc = int(d.get('outcome') or 0)
print('PASS' if (readiness_ok and outcome_ok) else 'FAIL')
```

**There are three such states, not one**, and every one of them routes
`on_yes: decide_current`. Patching only the last is insufficient — the issue reaches
implementation through whichever fires first:

| State | Line | FAIL-branch deferral reason | Pre-deferral remedy? |
|---|---|---|---|
| `recheck_scores` | `autodev.yaml:942` | none — `on_no: check_decision_before_size_review` | n/a |
| `regate_after_atomic_remediation` | `autodev.yaml:1410` | `oversized_atomic` (unconditional) | **no** |
| `recheck_after_size_review` | `autodev.yaml:1500` | `readiness_stagnated` / `low_readiness` | yes (BUG-2803) |

So a refined-but-design-less issue scoring 92 readiness reads `PASS` and routes to
`decide_current` → `implement_current`. There is no `FAIL` to discriminate, no deferral,
and no `low_readiness` — the gate is silently bypassed in exactly the automation path
(`ll-auto` / `ll-parallel` / `ll-sprint`) the epic exists to protect.

## Expected Behavior

Autodev's readiness gate hard-ANDs the deterministic Program Design verdict into its
`PASS`/`FAIL` computation, so a design-less issue cannot reach implementation once the
gate is armed. A `FAIL` caused solely by the `## Program Design` gate routes once through
the `/ll:reconcile-issue` remedy (it is exactly the kind of directive-section gap
reconcile exists to fix) before any deferral; a post-remedy deferral uses the distinct
machine reason code `design_gate_failed`, not generic `low_readiness`, so
`ll-issues deferred-triage` can distinguish it. With detection and routing in place, the
cutover stamp is written for this repo, arming the gate.

## Proposed Change

0. **Detection — make the gate visible to autodev** (the prerequisite for everything
   below). In the `GATE=PASS/FAIL` python block of **all three** gate states named in
   Current Behavior — `recheck_scores` (`:942`), `regate_after_atomic_remediation`
   (`:1410`), and `recheck_after_size_review` (`:1500`) — shell out to
   `ll-issues format-check "$ID" --format json` and hard-AND the Program Design verdict
   into `GATE`: FAIL when `program_design_nonspecific` is non-empty **or** `Program
   Design` appears in `missing`/`empty`. Record the discriminator to a run-dir marker
   (e.g. `${context.run_dir}/autodev-design-gate-failed-$ID`) so the reconcile/defer
   branch below can tell a design-caused FAIL from a score-caused one.

   **JSON shape differs by mode** — pin the single-ID form. `ll-issues format-check <ID>
   --format json` prints a **flat** gap dict (`{"missing": [...], ...,
   "program_design_nonspecific": [...]}`), exit 0 when clean; only `--all` prints the
   `{issue_id: gaps}` mapping (`format_check.py:159`). Parse the flat form; do not index
   by issue ID.

   Reading the CLI directly (rather than having `/ll:confidence-check` persist a
   `program_design_gap` flag) keeps the deterministic linter as the single source of
   truth, needs no LLM cooperation, and follows the precedent already documented in
   `recheck_after_size_review`'s own comments — the state reads frontmatter/CLI directly
   because `ll-issues check-readiness` hard-ANDs both halves and can't express the
   waiver. The gate is fail-open, so in an unstamped project `format-check` reports
   nothing for the section and this AND is inert.

1. **`DeferReason` enum** (`scripts/little_loops/issue_lifecycle.py`, lines 58–79 — the
   established single place new deferral reason codes are added):
   `DESIGN_GATE_FAILED = "design_gate_failed"  # ENH-2852/ENH-2870: program-design stage failed verification`,
   following the existing inline-comment convention.
2. **`autodev.yaml` routing** — `recheck_after_size_review` (`:1500`) already implements
   the shape needed: it computes `GATE=PASS/FAIL`, checks a stagnation backstop, and
   (per BUG-2803's pre-deferral remedy guarantee) arms a one-shot `reconcile`/`spike`
   remedy via run-dir handshake files (`autodev-pre-deferral-remedy-fired`, `:1572`)
   before any deferral write. Add a design-gate-caused-FAIL discriminator to this chain,
   routed once through `reconcile_current` (via `check_reconcile_needed`, `:1230`) and
   deferred with `--reason design_gate_failed` only if the post-remedy pass still fails.
   This reuses BUG-2803/FEAT-2751's machinery — but reuse is **not** a drop-in. Three
   things must be stated explicitly, because the existing machinery does the wrong thing
   for a design-caused FAIL:

   **(a) Branch precedence — pin it.** The FAIL branch has four exits in sequence:
   `resolved_by_subloop` (`:1544`) → `readiness_stagnated` (`:1557`) → pre-deferral
   remedy (`:1572`) → `low_readiness` (`:1597`). A design-gate FAIL can arrive with
   *passing* scores — that is the entire premise of this issue — so on a second cycle
   with `CYCLE_COUNT >= 2` it would be swallowed by the `readiness_stagnated` branch and
   never reach the design branch. Required order: **after `resolved_by_subloop`, before
   `readiness_stagnated`.** It is not sufficient to sit merely "ahead of
   `low_readiness`".

   **(b) Force the remedy to `reconcile`.** The BUG-2803 selector (`:1573-1586`) picks
   `spike` when `score_ambiguity` is the strictly weakest subscore. A spike proves an
   external mechanism; it does not write a `## Program Design` section. On the
   design-gate branch the remedy must be hardcoded `reconcile`, bypassing the
   weakest-subscore heuristic entirely.

   **(c) Fix the selector's empty fall-through.** That same selector returns `''` when
   `reconcile_attempted == 'true'`, which currently falls through to `low_readiness`.
   On the design-gate branch that fall-through must land on `design_gate_failed`.

   **`regate_after_atomic_remediation` (`:1410`) needs its own policy.** Unlike
   `recheck_after_size_review` it has *no* pre-deferral remedy at all — its FAIL branch
   writes `oversized_atomic` unconditionally (`:1443`). A design-caused FAIL there must
   not be mislabelled `oversized_atomic`: route it to the same reconcile remedy if
   reachable, and otherwise defer with `design_gate_failed`.

   **`recheck_scores` (`:942`)** has no deferral branch at all (`on_no:
   check_decision_before_size_review`), so it needs only the step-0 detection AND — the
   design-caused FAIL simply continues down the existing not-ready path, which
   eventually funnels into `recheck_after_size_review`. No new reason-code write here.
### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to Current Behavior's "identical block in all THREE gate states" claim**:
  `recheck_scores` (`autodev.yaml:942-955`) does **not** build a `GATE` variable via an
  inline `python3 -c` block the way `regate_after_atomic_remediation` (`:1410-1451`) and
  `recheck_after_size_review` (`:1500-1534`) do. It instead shells directly to
  `ll-issues check-readiness ${captured.input.output} --readiness ... --outcome ...`
  under `fragment: shell_exit`, routing on that CLI's own exit code — no local `GATE`
  string to hard-AND into. `check-readiness` (`scripts/little_loops/cli/issues/check_readiness.py::cmd_check_readiness`)
  also reads a **different frontmatter key pair** (`confidence_score`/`outcome_confidence`
  via `parse_frontmatter`) than the other two states' `confidence`/`outcome` (read from
  `ll-issues show --json`). Consequence for Step 0: patching `recheck_scores` cannot reuse
  the "hard-AND into `GATE`" recipe verbatim — the detection AND has to compose with a
  `shell_exit`-routed CLI call instead of a python `PASS`/`FAIL` print, e.g. by adding a
  second `&&`-chained check or wrapping both checks in one script that exits non-zero if
  either fails.
- Confirmed current line ranges as of 2026-07-27: `recheck_scores` `942-955`;
  `regate_after_atomic_remediation` `1410-1451`; `recheck_after_size_review`'s `GATE`
  block `1500-1534` with its FAIL branch `1537-1601`, plus dispatcher states
  `check_pre_deferral_remedy` `1607-1622` and `dispatch_pre_deferral_remedy` `1624-1648`.
- Confirmed run-dir marker filenames used by the existing BUG-2803/FEAT-2751 machinery
  (all under `${context.run_dir}/`): `autodev-passed.txt`, `autodev-skipped.txt`,
  `autodev-inflight`, `autodev-repair-cycle-count.txt`, `autodev-pre-readiness.txt`,
  `autodev-pre-deferral-remedy-fired`, `autodev-pre-deferral-remedy.txt`,
  `autodev-pre-spike-readiness.txt`.
- Confirmed `DeferReason` (`issue_lifecycle.py:58-79`), `_DEFERRAL_REASON_CODES`
  (`set_status.py:12-22`), and `_REASON_RANK` (`deferred_triage.py:15-30`) currently
  enumerate exactly the same seven reason codes each, with no `design_gate_failed` entry
  yet — the three-file lockstep-update requirement is confirmed, not just asserted.
- Verified empirically as of this refinement pass: no stray gitignored `.ll/` directories
  exist under `.issues/` (glob for `**/.ll` and `*/.ll` returned no matches), and no
  `.ll/program-design-cutover.json` exists yet at the repo root — both match the issue's
  current claims (stray dirs cleared 2026-07-27, stamp not yet written).
- Test scaffolding to model the new test class after: `scripts/tests/test_autodev_loop.py:346-370`
  (`TestRecheckAfterSizeReviewStagnationBackstop`), using module helpers `_load_autodev_yaml()`
  (`:30`), `_extract_python_script()` (`:38`), and `_run_reconcile_predicate()` (`:45`) —
  the latter substitutes `${context.run_dir}` the way the FSM interpolator would and can
  drive a behavioral (not just string-assertion) test of the design-gate branch against a
  synthetic `format-check --format json` payload, if desired beyond the AC's minimum bar.

3. **Consumers of the new reason code** (two, not three):
   - `scripts/little_loops/cli/issues/set_status.py:12` — `_DEFERRAL_REASON_CODES` is a
     **hardcoded `frozenset` literal that duplicates the `DeferReason` enum**, so adding
     an enum member alone leaves `--reason design_gate_failed` rejected as a non-deferral
     code. Prefer deriving the set from the enum
     (`frozenset(r.value for r in DeferReason)`) over adding a seventh literal — it kills
     the drift class permanently and is a smaller diff than the duplicate.
   - `scripts/little_loops/cli/issues/deferred_triage.py:15` — insert `design_gate_failed`
     into `_REASON_RANK` at an explicit rank with a dated `# ENH-2870:` rationale comment
     following the existing `# FEAT-2751:`/`# BUG-2734:` convention (rank it above
     `low_readiness`; it is a more actionable, specific signal).
   - *Not* `issue_manager.py` — grep confirms it never reads `deferred_reason`; its only
     mention is a prose comment at line 905. Previously listed here in error.
3b. **Pre-arming blocker — stray `.ll/` directories shadow the project root.**
   `find_project_root()` (`program_design.py:~300`) returns the *nearest* ancestor
   containing a `.ll` directory. This checkout has 10+ stray `.ll/` dirs — including
   `.issues/.ll`, `.issues/enhancements/.ll`, `.issues/features/.ll`, `.issues/epics/.ll`
   — created as a side effect of running `ll-*` from those working directories, and all
   gitignored (`.gitignore:131 **/.ll/`) so invisible to `git status`.

   Consequence, verified empirically: for any issue under `.issues/enhancements/`,
   `find_project_root()` returns `.issues/enhancements`, `git_grep_resolver` then runs
   `git grep` from there and resolves **nothing**, so every `Call Path` anchor is
   unresolved and the section grades non-specific — even when it is perfectly specific.
   Grading this very issue's `## Program Design` section proves it: with the shadowed
   root, `is_specific=False` with "no call-path anchor resolves against the repo"; with
   the true repo root, `is_specific=True` and all six anchors resolve.

   **Cleared 2026-07-27** (50 stray dirs removed; all 2787 files under `.issues/` now
   resolve to the repo root, and this issue's own section re-grades `is_specific=True`
   through the real code path). The AC below stays regardless — the dirs regenerate
   whenever an `ll-*` command is invoked from a subdirectory, so this must be re-checked
   immediately before the stamp is written, not assumed from this note.

   So **arming the gate before clearing these would mass-fail every issue in this repo**
   for a reason unrelated to design quality — the exact mass-defer outcome ENH-2852's
   fail-open design exists to prevent. Delete the stray dirs before writing the stamp
   (they hold only stray `history.db` files from mis-rooted invocations; confirm each is
   not the live DB first). Consider whether `find_project_root` should prefer a `.git`
   ancestor over the nearest `.ll` — the shadowing is a latent trap for any consuming
   project, not just this one; file a follow-up rather than widening this issue.
4. **Arm the gate in this repo**: write `.ll/program-design-cutover.json`
   (`{"sha": "<full 40-char SHA>", "date": "YYYY-MM-DD"}` — exactly these two keys, the
   schema pinned in ENH-2852). Per the pinned boundary rule, the `date` is the day
   *after* this issue's gate-arming merge, so every pre-gate issue is strictly earlier
   and exempt. FEAT-2855 and FEAT-2867 parse this same file at this same path.
5. **Docs**: `docs/reference/API.md` `#### deferred-triage` enumerates every `DeferReason`
   code by name in ranked prose — slot `design_gate_failed` in to match `_REASON_RANK`.

## Program Design

No new Python type or function is introduced. The routing change is YAML/shell inside
three `autodev.yaml` state `action:` blocks; the Python delta is one enum member and one
literal-to-derived set.

### Types

- `DESIGN_GATE_FAILED: str`
- `_DEFERRAL_REASON_CODES: frozenset[str]`

New member of the existing `DeferReason` enum (`issue_lifecycle.py:58-79`);
`_DEFERRAL_REASON_CODES` changes from a hardcoded literal set to a derived one, type
unchanged. The run-dir marker `${context.run_dir}/autodev-design-gate-failed-<ID>` is a
presence-only sentinel file with no payload.

### Signatures

- `read_cutover_stamp(root: Path) -> date | None`
- `program_design_gate_active(issue_path: Path, content: str) -> bool`
- `check_format_gaps(issue_path: Path) -> FormatGaps`

All three are existing and unchanged — consumed, not modified. At `set_status.py:12` the
literal set is replaced by `frozenset(r.value for r in DeferReason)`.

### Call Path

`ll-issues format-check` → `check_format_gaps` → `program_design_gate_active` →
`read_cutover_stamp`, read by the three autodev gate states, whose deferral branch
calls `cmd_set_status` → `DeferReason`, and whose output is ranked by
`cmd_deferred_triage`.

## Acceptance Criteria

- [ ] **All three** gate states — `recheck_scores` (`:942`),
      `regate_after_atomic_remediation` (`:1410`), `recheck_after_size_review` (`:1500`)
      — hard-AND `ll-issues format-check <ID> --format json`'s Program Design verdict
      into their `PASS`/`FAIL`: an issue with a non-empty `program_design_nonspecific`,
      or `Program Design` in `missing`/`empty`, cannot reach `implement_current` through
      *any* of them, no matter how high its persisted `confidence` score is. A test
      asserts the pre-fix bypass (high score + design gap → implement) is closed on each.
- [ ] The parser reads the **flat** single-ID JSON shape, not the `--all`
      `{issue_id: gaps}` mapping.
- [ ] The design-caused FAIL is distinguishable from a score-caused FAIL via a run-dir
      marker, and in an unstamped project the added AND is inert (gate fails open).
- [ ] The design-gate branch is ordered **after `resolved_by_subloop` and before
      `readiness_stagnated`** — a test asserts a design-gate FAIL with `CYCLE_COUNT >= 2`
      and a non-improving confidence score defers as `design_gate_failed`, not
      `readiness_stagnated`.
- [ ] On the design-gate branch the pre-deferral remedy is hardcoded to `reconcile`,
      bypassing BUG-2803's weakest-subscore `spike`/`reconcile` heuristic; and the
      selector's `reconcile_attempted == 'true'` empty fall-through lands on
      `design_gate_failed`, never `low_readiness`.
- [ ] A design-caused FAIL at `regate_after_atomic_remediation` is never labelled
      `oversized_atomic`.
- [ ] `DeferReason.DESIGN_GATE_FAILED = "design_gate_failed"` exists with the
      convention-following inline comment; `set_status.py`'s deferral-code set and
      `deferred_triage.py`'s `_REASON_RANK` (with dated comment) both recognize it.
      `set_status.py` no longer duplicates the enum as a hardcoded literal set.
- [ ] A gate failure caused solely by the `## Program Design` gate routes to
      the reconcile remedy before any deferral; only a post-remedy failure defers, and
      with `--reason design_gate_failed`, never generic `low_readiness`.
- [ ] The design-gate discriminator in `recheck_after_size_review` short-circuits ahead of
      the generic `low_readiness` write and reuses the existing BUG-2803 one-shot remedy
      handshake (no new remedy infrastructure).
- [ ] **Before** the stamp is written, the stray `.ll/` directories that shadow
      `find_project_root()` are cleared, and a sweep confirms it: for a sample of issues
      across `.issues/{bugs,features,enhancements,epics}/`,
      `find_project_root(<issue path>)` returns the repo root — not the containing issue
      directory. Arming with these present mass-fails every issue on unresolvable
      anchors regardless of design quality.
- [ ] `.ll/program-design-cutover.json` is written for this repo with the pinned
      two-key schema, dated the day after the gate-arming merge (strictly-earlier
      exemption comparison per ENH-2852).
- [ ] `docs/reference/API.md`'s deferred-triage reason-code list includes
      `design_gate_failed` at its `_REASON_RANK` position.
- [ ] Rollback is documented in the Session Log / commit message at two granularities:
      **project-wide**, `rm .ll/program-design-cutover.json` fully disarms the gate (it
      is fail-open by construction — `read_cutover_stamp()` returns `None` on absent,
      unreadable, or unparseable, and `program_design_gate_active()` then returns
      `False`); **per-issue**, `program_design_not_applicable: true` in frontmatter
      exempts a single issue (`program_design.py:390`). No code revert required for
      either. The per-issue escape hatch is the one a human hits first during a live
      `ll-auto` run, so it must be named, not just the file deletion.
- [ ] Tests: `scripts/tests/test_autodev_loop.py` gains a sibling class to
      `TestRecheckAfterSizeReviewStagnationBackstop` following the `readiness_stagnated`
      pattern — string-assertions that the action references `design_gate_failed` and any
      new marker files, plus an ordering test that the branch short-circuits
      `low_readiness`; `test_autodev_decision_gate.py` extended for the routing;
      `test_issue_lifecycle.py` covers enum membership if exhaustive coverage is wanted.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `#### ll-issues deferred-triage` section hardcodes its
  own copy of the rank-order prose list ("Rank order (highest first):
  `remediation_stalled`, `blocked_by_unmet`, `gate_blocked`, `decision_unresolved`,
  `oversized_atomic`, `readiness_stagnated`, `low_readiness`, then any other
  (unranked) code") — independent of `docs/reference/API.md`'s copy already listed in
  Proposed Change item 5. Both must be updated with `design_gate_failed` at its
  `_REASON_RANK` position or `CLI.md` goes stale. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes`
  — `@pytest.mark.parametrize` over the reason-code list (currently
  `blocked_by_unmet`, `remediation_stalled`, `low_readiness`, `gate_blocked`,
  `decision_unresolved`, `oversized_atomic`, `readiness_stagnated`); add
  `design_gate_failed` following the same per-code registration convention used when
  `readiness_stagnated` was added for FEAT-2751. [Agent 3 finding]
- `scripts/tests/test_issues_cli.py` — has an established rank-order regression
  pattern, e.g. `test_oversized_atomic_ranked_between_decision_unresolved_and_low_readiness`
  (~line 6331): fixture issue files with specific `deferred_reason:` values, asserting
  `captured.out.index(...)` ordering. Add a sibling test proving
  `design_gate_failed`'s rank placement in `_REASON_RANK`. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — the primary structural test file for
  `autodev.yaml`; contains exact-value routing assertions for
  `regate_after_atomic_remediation` and `recheck_after_size_review`
  (`on_yes`/`on_no` targets, e.g. `test_check_guard2_verdict_routes_to_remediation_chain`
  ~4847-4875) and action-string assertions
  (`test_regate_after_atomic_remediation_defers_oversized_atomic_via_set_status` ~4810,
  which already asserts `"low_readiness" not in action` — the closest existing
  precedent shape for the new design-gate discriminator). These break if the new
  branch changes `on_yes`/`on_no` routing keys rather than staying inline in the
  shell action; verify and extend during implementation. [Agent 3 finding]
- `scripts/tests/test_program_design_gate.py` and
  `scripts/tests/test_ll_issues_format_check.py` — both hold fixture-level knowledge
  of the `.ll/program-design-cutover.json` stamp's exact on-disk JSON shape
  (`cutover_date` field). Treat these as the informal schema contract when
  constructing the arming payload for AC item on writing the stamp. [Agent 2 finding]

## Scope Boundaries

- **In scope**: the autodev `format-check` detection AND (step 0),
  `DeferReason.DESIGN_GATE_FAILED` + its two real consumers, the
  `recheck_after_size_review` design-gate discriminator, docs for the reason-code list,
  and writing `.ll/program-design-cutover.json` for this repo (arming the gate).
- **Unaffected, verified**: `rn-remediate.yaml:109` references the cutover stamp in a
  prose comment only — arming the gate changes no behavior there. Confirm during
  implementation rather than assuming.
- **Out of scope**: the gate itself, specificity grading, grandfathering/stamp-*reading*
  (ENH-2852, which blocks this); the `manage-issue` Deviations writer (ENH-2871);
  wiring stamp-arming into `ll-init`/`/ll:configure` (optional follow-up, unowned);
  FEAT-2855/FEAT-2867's window computations (they only consume the stamp this issue
  writes).

## Impact

- **Priority**: P2 - the gate ENH-2852 ships stays disarmed everywhere until this lands;
  arming without it would defer design-gap issues under an indistinct reason code with no
  reconcile-first remedy.
- **Effort**: Medium-Large (revised up on review) - the detection AND lands in **three**
  gate states, not one; the reconcile-before-defer branch needs explicit precedence plus
  two overrides of BUG-2803's selector; and the stray-`.ll` cleanup gates the arming AC.
  Previously scoped as: one detection AND in the autodev gate block, one enum member, one
  autodev discriminator reusing existing remedy machinery, two small consumer updates,
  one stamp file, docs.
- **Risk**: Medium - the routing reuses proven BUG-2803/FEAT-2751 machinery, but step 0
  edits the hot `GATE=PASS/FAIL` block that every issue passes through, and the final AC
  arms the gate repo-wide. Mitigated by the fail-open rollback (delete the stamp) and by
  the pinned single-file stamp contract shared with FEAT-2855/FEAT-2867.
- **Breaking Change**: No - additive reason code; the stamp arms the gate only in this
  repo.

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- `ll-auto` - 2026-07-28T04:07:12 - `37e1dd10-f662-41f2-a581-6d5e31bd8852.jsonl`
- `/ll:ready-issue` - 2026-07-28T03:55:39 - `242f6456-6c38-4cfb-b4c2-1feb394ae379.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:00:00 - `f0efab9d-a734-472f-9a08-e777d48ad7a5.jsonl`
- `/ll:wire-issue` - 2026-07-28T03:52:52 - `04db6d17-d8a8-4dea-9f11-74a2e2d40be7.jsonl`
- `/ll:refine-issue` - 2026-07-28T03:47:02 - `3d97f601-b3aa-40ce-921e-9192166996d1.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-27
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
