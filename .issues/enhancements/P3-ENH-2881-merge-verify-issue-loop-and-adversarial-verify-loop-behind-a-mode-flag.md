---
id: ENH-2881
title: Merge verify-issue-loop and adversarial-verify-loop behind a mode flag
type: ENH
priority: P3
status: done
captured_at: '2026-07-28T02:07:33Z'
completed_at: '2026-07-28T05:09:42Z'
discovered_date: 2026-07-28
labels:
- skills
- loops
relates_to:
- ENH-2877
confidence_score: 100
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2881: Merge verify-issue-loop and adversarial-verify-loop behind a mode flag

Follow-up from the ENH-2877 skill-merge audit — Tier 1 candidate C2.

## Summary

`skills/verify-issue-loop/` and `skills/adversarial-verify-loop/` share an
identical input contract, an identical tool allowlist, and an identical seven-step
resolve → synthesize → write → validate spine. They differ only in *which* FSM
states get synthesized. Merge into one skill with a `mode` argument
(`criteria` | `adversarial`).

## Current Behavior

Both skills:

1. take a single required `issue_id` argument, documented identically as
   "accepts open or completed issues";
2. declare the same `allowed-tools`: `Bash(ll-issues:*, ll-loop:*, mkdir:*)`,
   `Read`, `Write`;
3. resolve the issue via `ll-issues show <ID> --json`;
4. read the issue file's `## Acceptance Criteria` section;
5. synthesize `llm_structured` evaluator states;
6. wire linear pass/fail routing;
7. write to `.loops/<prefix>-<ISSUE-ID>-<slug>.yaml`;
8. validate with `ll-loop validate` and report.

Steps 1–4, 7, and 8 are byte-for-byte equivalent in intent and near-equivalent in
prose. `verify-issue-loop`'s body already frames the pair as counterparts
("*Where `verify-issue-loop` asks 'does the criterion hold?', `adversarial-verify-loop`
asks 'can we break it?'*").

Every change to the shared spine — a new `ll-issues show` field, a change to the
`.loops/` path convention, a new `ll-loop validate` flag — must be applied twice
by hand.

## Expected Behavior

One skill stating the resolve/write/validate spine once, with a `mode` argument
selecting the state-synthesis body.

## Motivation

Maintenance cost of a duplicated procedural spine. Explicitly **not** a
menu-footprint argument: ENH-2877 measured `ll-verify-skill-budget` at
**516 / 2000 tokens (74% headroom)** and directs that entry-count-only arguments
be rejected. The argument here is that six of eight documented steps are
duplicated prose that must stay in sync manually, with no mechanism enforcing it.

BUG-2801 ("eval/verify loop templates fail own MR lints") is evidence the shared
spine already needs coordinated maintenance across these generators — worth
checking whether that issue's fix touches both files, which would strengthen the
case.

## Proposed Solution

One skill (retaining the name `verify-issue-loop`) with an **optional** `mode`
argument defaulting to `criteria`:

- `mode: criteria` (**default** — applied when `mode` is omitted) — one
  `verify-criterion-N` state per acceptance criterion,
  `llm_structured` pass/fail, linear `on_yes` chaining, `on_no: failed`. Current
  `verify-issue-loop` behavior.
- `mode: adversarial` (**explicit opt-in only**) — three probe states (`probe-boundary`,
  `probe-malformed-hostile`, `probe-failure-mode`), plus the `count_probes` shell
  state that verifies ≥3 probe-result files were written on the filesystem, plus
  the verdict rule that **attempting fewer than 3 genuine probe classes is itself
  a FAIL**. Current `adversarial-verify-loop` behavior.

Output paths stay mode-distinguished (`.loops/verify-<ID>-<slug>.yaml` vs
`.loops/adversarial-<ID>-<slug>.yaml`) so already-generated loops and any tooling
that globs them are unaffected.

### Why `criteria` is the default

Not a compatibility argument — **nothing breaks either way.** A sweep for
`verify-issue-loop|adversarial-verify-loop` across `*.yaml` returns zero hits: no
FSM loop invokes either generator, and already-generated `.loops/verify-*.yaml` /
`.loops/adversarial-*.yaml` are standalone FSM YAML that never call back into the
skill. The only thing that stops resolving is the human-facing name
`/ll:adversarial-verify-loop`.

The default is chosen on cost and ergonomics:

- **Cheaper mode wins by default.** A bare `/ll:verify-issue-loop <ID>` must not
  silently opt into the `timeout: 2700`, three-open-ended-probe path. Requiring
  `mode: adversarial` explicitly preserves the deliberate-opt-in signal the two
  separate skill names carried (see *Cost-aware mode selection* above).
- **Continuity for the retained name.** `criteria` *is* the current behavior of
  `/ll:verify-issue-loop`. Defaulting to it means the retained name's contract is
  unchanged for every existing caller and doc reference.
- **Ergonomics for future FSM consumers.** A loop state wiring in
  `/ll:verify-issue-loop <ID>` gets the cheap, bounded, fail-fast mode without
  having to know a `mode` argument exists. Opting a loop into the expensive path
  becomes a visible, reviewable edit rather than a default it inherits silently.

The merged skill must not error or prompt when `mode` is absent — it resolves to
`criteria` and proceeds.

### What would be lost

The adversarial mode carries a load-bearing invariant that has nothing to do with
the shared spine: the ≥3-probe-classes FAIL rule and its filesystem-derived
`count_probes` check (which exists precisely so the count is not LLM-self-reported
— the same self-evaluation-bias concern MR-1 encodes). Folding that behind a mode
flag makes it easier to skim past when editing the shared spine. The merged skill
must keep that rule visually prominent, not buried in a mode branch.

**Cost-aware mode selection.** The two generators cost the same to *run* — resolve,
emit one YAML, validate — but the loops they emit do not. Adversarial carries a
`timeout: 2700` against verify's `1800`; it always pays a fixed floor of three
open-ended "attempt at least two distinct probes, run real commands — do not
theorize" states before reaching a verdict, whereas verify's cost scales with the
acceptance-criterion count and fails fast on criterion 1. On a 2-criterion issue
adversarial is several times the cost; on a 12-criterion issue verify may exceed it.

Today that trade-off is encoded in the *names*: invoking
`/ll:adversarial-verify-loop` is a deliberate opt-in to the expensive path. Behind
a `mode` argument, `criteria` becomes the default and `adversarial` becomes a
parameter that can be set casually — by a user or by the model. The merged skill
must therefore state, near the mode dispatch, when each mode is appropriate and
that adversarial costs meaningfully more per generated-loop run. Runtime cost of
already-generated loops is unchanged in both directions; this is purely about not
losing the selection signal the two names carried.

### Explicitly out of scope: `create-eval-from-issues`

It shares the same spine and was considered. **Do not include it.** It differs on
the axis that matters: it takes *many* issue IDs, reads Expected Behavior and Use
Case rather than only Acceptance Criteria, and judges *user-experience quality*
rather than implementation conformance. That distinction is deliberate and
recorded in two places — `verify-issue-loop`'s own body, and the project note that
an eval-harness `execute` state means "exercise the feature as a user would, NOT
implement the issue." Merging it would collapse a distinction the codebase spent
effort establishing.

## Scope Boundaries

**In scope**

- Merging `verify-issue-loop` and `adversarial-verify-loop` into one skill under
  the retained name `verify-issue-loop`, with a `mode` argument.
- Preserving both output-path prefixes and both generated-YAML shapes exactly.
- Updating the skill catalog in `.claude/CLAUDE.md`, `commands/help.md`, and docs.

**Out of scope**

- **`create-eval-from-issues`.** Considered and rejected — see the dedicated
  subsection above. It is not to be folded in as a third mode.
- **Any other merge candidate.** ENH-2877's Tier 2/Tier 3 findings were each
  examined and recommended against; do not opportunistically include them.
- **Any router or change to name-based dispatch**, per ENH-2877's core rejection.
- Changing the generated loops' FSM semantics, evaluator shape, or routing —
  this is a skill-file consolidation, not a generator redesign. Fixing MR-lint
  violations in the generated templates belongs to BUG-2801, not here.
- A deprecation shim for `/ll:adversarial-verify-loop` — removed outright.

**Backwards compatibility**: `/ll:adversarial-verify-loop` stops resolving. No
FSM loop, frozenset entry, or `ll-*` bridge references it. Already-generated
`.loops/adversarial-*.yaml` files are untouched and keep running.

## Integration Map

### Dispatch-site check (ENH-2877 AC #2)

**Clean — no name-based dispatch site is affected.**

| Site | `verify-issue-loop` | `adversarial-verify-loop` |
|------|--------------------|---------------------------|
| Loop corpus `/ll:<name>` refs (`scripts/little_loops/loops/`) | 0 | 0 |
| `_VERIFIER_SKILLS` (`cli/action.py:30`) | no | no |
| `_REVIEWER_SKILLS` (`cli/action.py:49`) | no | no |
| `ll-*` thin bridge in `skills/` | none | none |

Both are `disable-model-invocation: false`, so both are in the model-invocable
listing; neither is referenced by any FSM state. Remaining references are docs
and tests.

### Files

- `skills/verify-issue-loop/SKILL.md` (271 lines) — merge target.
- `skills/adversarial-verify-loop/SKILL.md` (395 lines) — removed. Combined:
  666 lines (not 622 as roughly estimated above) — either figure confirms the
  500-line `ll-verify-skills` cap is exceeded and a companion-file split per
  ENH-494 is likely needed, since link-epics' 363-line merged precedent (below)
  is meaningfully smaller.
- `scripts/little_loops/fsm/validation.py` — MR-1 through MR-13; the generated
  YAML must still pass `ll-loop validate`. See BUG-2801.
- Catalog docs: `.claude/CLAUDE.md` § Commands & Skills, `commands/help.md`.
- `scripts/tests/test_builtin_loops.py` and any test asserting either name or
  either generated-file prefix.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact shared-spine boundaries** (byte/near-byte identical between the two
files today):
- `## Arguments` parsing block: `skills/verify-issue-loop/SKILL.md:44-60` vs
  `skills/adversarial-verify-loop/SKILL.md:45-61` — identical shell-loop idiom
  (`for token in $ARGUMENTS; do case "$token" in --*) ;; ...`) that already
  reserves `--*` tokens for future flags, i.e. a `--mode` case arm can be added
  directly without restructuring the parser.
- `## Step 1: Resolve Issue File`: verify-issue-loop lines 62-72 vs
  adversarial-verify-loop lines 63-73 — verbatim-identical prose including the
  "Both open and completed issues are accepted" paragraph.
- `## Step 6: Write and Validate`: verify-issue-loop lines 228-242 vs
  adversarial-verify-loop lines 350-364 — verbatim-identical.
- Slug-generation bash: verify-issue-loop lines 138-148 vs adversarial-verify-loop
  lines 208-217 — identical except for the `verify-`/`adversarial-` prefix
  variable.
- Divergent: Step 2 extraction (verify-issue-loop halts on missing Acceptance
  Criteria; adversarial-verify-loop falls back to title/summary), Step 3
  synthesis body (N criterion states vs 3 fixed probe states + `count_probes`
  shell gate), Step 4 wiring topology (linear chain vs three-way terminal split
  `done`/`failed_with_finding`/`failed_too_few`), Step 5 full YAML templates.
- `adversarial-verify-loop/SKILL.md:394` already carries a `**See also:**
  \`/ll:verify-issue-loop\` (confirmatory counterpart)` cross-reference — the
  two skills already frame themselves as a pair in prose, supporting the merge.

**Direct precedent — `skills/link-epics/SKILL.md` (commit 92e0639e, from
ENH-2880, same merge pattern applied to a different skill pair)**:
- Frontmatter: a single `flags` argument (not a dedicated `mode` argument) whose
  `description` spells out `--mode assign|synthesize (default: assign)` inline;
  `argument-hint: "[--mode assign|synthesize] [--auto] ..."`.
- Body opens with a two-bullet mode summary directly under the H1.
- `## Step 1: Parse Arguments` parses `MODE` first with an explicit default and
  includes a **Rationale** subsection explaining why the two modes' defaults
  were *not* reconciled — directly analogous to this issue's "Why `criteria` is
  the default" subsection.
- Shared logic lives in plain `## Step N` headings; mode-specific logic is
  demarcated `## Mode: \`--mode assign\`` (default)` and `## Mode: \`--mode
  synthesize\`` (`skills/link-epics/SKILL.md:109,213`), each a self-contained
  sub-pipeline with its own lettered sub-steps (`A1`-`A5`/`S1`-`S5`) and its own
  `### Usage Examples`.
- Closes with `## Choosing a Mode` (`SKILL.md:357-362`) giving guidance on which
  mode to run when and cross-referencing the other by name — directly reusable
  for this issue's Step 7 ("mode-selection guidance... adjacent to the `mode`
  dispatch").
- Test precedent: `scripts/tests/test_link_epics_skill.py` — `test_mode_flag_documented`
  (line 76) asserts `--mode` appears in the file; `test_assign_mode_section`/
  `test_synthesize_mode_section` (lines 80-86) assert the exact heading strings
  are present (structural check, not a byte-identical-output diff — no test in
  that file actually renders both invocations and diffs output);
  `test_create_epics_from_unparented_name_removed` (lines 92-94) is the negative-
  assertion template for confirming `adversarial-verify-loop` is fully scrubbed
  from the merged file. `skills/create-epics-from-unparented/` no longer exists
  on disk, confirming the prior merge fully deleted the source skill.
- The merged `link-epics/SKILL.md` needed **no companion-file split** (363
  lines, under the 500-line cap) — but its source skills were more compact than
  this pair's; expect this merge to need the ENH-494 companion-file pattern
  where link-epics didn't.

**Unaddressed wrinkle — mismatched `agents/openai.yaml` companion files**:
`skills/adversarial-verify-loop/agents/openai.yaml` exists (a Codex adapter),
but `skills/verify-issue-loop/` has no `agents/` directory. Neither of
link-epics' source skills had an `agents/` dir, so that prior merge never had
to reconcile this. This merge must either generate `skills/verify-issue-loop/agents/openai.yaml`
(regenerate via `ll-adapt --host codex --apply` after the merge) or explicitly
decide the merged skill drops Codex-adapter parity — not currently addressed
by the Implementation Steps below.

**Additional files not yet listed above** (beyond `.claude/CLAUDE.md` and
`commands/help.md`):
- `scripts/tests/test_verify_issue_loop.py` and
  `scripts/tests/test_adversarial_verify_loop.py` — each holds a
  `TestXLoopStructure`/`TestXLoopValidation` pair with inline YAML fixtures
  (`VERIFY_YAML_3_CRITERIA`, `ADVERSARIAL_YAML`,
  `ADVERSARIAL_YAML_BREAK_FOUND`/`ADVERSARIAL_YAML_TOO_FEW`) and CLI round-trip
  validation via `little_loops.cli.main_loop` — these need merging/porting, not
  just Step 6's new cross-mode assertion test. Note a pre-existing doc/test
  discrepancy: SKILL.md prose says `max_steps: 20` while the test fixtures'
  literal YAML key is `max_iterations: 20` — worth resolving during the merge,
  not introducing into the merged file.
- `scripts/tests/test_wiring_skills_and_commands.py:292-294` —
  `DOC_FILES_MUST_EXIST` parametrized list asserts both `skills/verify-issue-loop/SKILL.md`
  and `skills/adversarial-verify-loop/SKILL.md` exist, tagged `FEAT-1447`/`ENH-2047`.
- `scripts/tests/test_wiring_cli_registry.py:103-107` — asserts both skills
  appear in `commands/help.md` and `.claude/CLAUDE.md`.
- `docs/reference/COMMANDS.md:643-675` (detailed per-skill entries) and
  `:1068-1069` (skill table rows) — not previously listed; needs consolidation
  to one entry/row.
- `CONTRIBUTING.md:175-215` — project-tree diagram lists `adversarial-verify-loop/`;
  remove, keep `verify-issue-loop/`.
- `CHANGELOG.md` — needs an entry noting `/ll:adversarial-verify-loop` removal
  (per this issue's own "must be called out in the changelog" line in Impact).
- `docs/guides/LOOPS_GUIDE.md:616` — example FSM state calling
  `/ll:verify-issue-loop`; already uses the retained name, no change needed.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py:293-294` — the
  `DOC_FILES_MUST_EXIST` tuple list has a distinct row for
  `skills/adversarial-verify-loop/agents/openai.yaml` (tagged `ENH-2047`), not
  just the `SKILL.md` row already noted above — both rows must be removed.
- `scripts/tests/test_verify_triggers.py:131,135` — `TestTriggerFixtures`
  hardcodes `"adversarial-verify-loop"` as a dict key in an illustrative
  `skill_keywords` fixture (BUG-2879 regression case for
  `_best_match_skills`'s tie-break logic). It never reads the real `skills/`
  tree, so it will keep passing verbatim after the merge — but it asserts
  matcher behavior "for a skill named adversarial-verify-loop" that no longer
  exists. Rename the fixture key to `verify-issue-loop` (or another
  placeholder) so the test doesn't reference a retired name.

### Codex Adapter Resolution (Agent 2 finding)

_Wiring pass added by `/ll:wire-issue`:_ the "Unaddressed wrinkle" section above
asks whether deleting `skills/adversarial-verify-loop/agents/openai.yaml`
needs adapter-side cleanup. Confirmed no: `scripts/little_loops/adapters/core.py:138`
drives `ll-adapt --host codex` via a live `skills_dir.glob("*/SKILL.md")`
traversal — there is no fixed registry or allowlist of "skills with an
openai.yaml" to reconcile. Deleting the directory means the next
`ll-adapt --host codex --apply` simply stops seeing it; separately, run
`ll-adapt --host codex --apply` after the merge to generate
`skills/verify-issue-loop/agents/openai.yaml` if Codex parity is being kept
(per the issue's own two-option framing).

## Implementation Steps

1. Diff the two `SKILL.md` bodies; isolate the shared spine from mode-specific
   synthesis prose.
2. Check whether BUG-2801's fix touches both files; coordinate ordering if so.
3. Write the merged `skills/verify-issue-loop/SKILL.md` with `mode` dispatch,
   keeping the ≥3-probe-class FAIL rule prominent rather than nested. `mode` is
   optional and defaults to `criteria`; an absent `mode` must resolve silently,
   never error or prompt. Document the argument as optional in the skill's
   frontmatter/usage line.
4. **Check the 500-line cap**: 249 + 373 = 622 lines concatenated. The merged
   file must land under 500 (`ll-verify-skills`) or extract to a companion file
   per the ENH-494 pattern.
5. Delete `skills/adversarial-verify-loop/`.
6. Generate three loops — no `mode`, `mode: criteria`, `mode: adversarial` —
   and assert the no-`mode` run is byte-identical in shape to the explicit
   `criteria` run (same `.loops/verify-*` prefix, same state set, `timeout: 1800`).
   Confirm all still pass `ll-loop validate`
   with no new MR violations. **`ll-loop validate` does not check budget fields
   against a baseline**, so additionally assert the per-mode values that a spine
   merge is most likely to silently flatten to a single number: loop `timeout`
   (`1800` for `criteria`, `2700` for `adversarial`), `max_steps: 20` on both,
   and per-state `timeout: 300`. Add this as a test in
   `scripts/tests/test_builtin_loops.py` rather than a one-time manual check.
7. Add the mode-selection guidance from "What would be lost" — when each mode
   applies and the relative cost — adjacent to the `mode` dispatch in the merged
   skill body.
8. **No default-mode test precedent exists to copy** (`/ll:wire-issue` finding):
   `test_link_epics_skill.py` never asserts behavior when `--mode` is omitted —
   only that `--mode` is documented and both section headings exist. Write a
   new `test_default_mode_is_criteria`-style test from scratch asserting the
   skill body documents `mode` as optional, defaulting to `criteria`, since
   there is no prior-merge test to mirror for this.
9. Update `scripts/tests/test_wiring_skills_and_commands.py:293-294` (remove
   both the `SKILL.md` and `agents/openai.yaml` rows for
   `adversarial-verify-loop`) and rename the fixture key in
   `scripts/tests/test_verify_triggers.py:131,135` away from
   `adversarial-verify-loop`.
10. Update catalog docs; run `python -m pytest scripts/tests/`,
    `ll-verify-skills`, `ll-verify-skill-budget`.

## Impact

- **Users**: `/ll:adversarial-verify-loop` stops resolving — a breaking change to
  a user-facing name with no deprecation shim proposed. Acceptable given 0
  automation references; must be called out in the changelog.
- **Generated artifacts**: unaffected. Output paths and generated YAML shape are
  preserved.
- **Maintenance**: one resolve/write/validate spine instead of two.
- **Risk**: Low-to-moderate — low mechanically, moderate in that the adversarial
  invariant is easy to weaken accidentally during the merge. Step 6 is the guard.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Loop Authoring MR-1..MR-13 rules the generated YAML must satisfy; Commands & Skills catalog |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Source of truth for the self-evaluation-bias concern the `count_probes` filesystem check exists to address |

## Session Log
- `/ll:manage-issue` - 2026-07-28T05:09:15Z - `880a03c0-b91d-4abd-b4bf-8437fd86ec52.jsonl`
- `/ll:ready-issue` - 2026-07-28T04:57:17 - `4b77d9f8-ff14-4b33-84de-fc56cfe63094.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:00:00 - `d77fa465-eaf8-408d-a0f6-ceb54cb1d460.jsonl`
- `/ll:wire-issue` - 2026-07-28T04:54:22 - `c0b23cdc-a607-4523-a516-b91c063e467b.jsonl`
- `/ll:refine-issue` - 2026-07-28T04:50:17 - `8aa0ee6f-8126-45c8-b9b5-abf2d59b0f97.jsonl`
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

open
