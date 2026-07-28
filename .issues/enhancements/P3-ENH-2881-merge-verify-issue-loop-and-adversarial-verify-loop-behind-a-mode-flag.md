---
id: ENH-2881
title: Merge verify-issue-loop and adversarial-verify-loop behind a mode flag
type: ENH
priority: P3
status: open
captured_at: "2026-07-28T02:07:33Z"
discovered_date: 2026-07-28
labels:
- skills
- loops
relates_to: [ENH-2877]
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

- `skills/verify-issue-loop/SKILL.md` (249 lines) — merge target.
- `skills/adversarial-verify-loop/SKILL.md` (373 lines) — removed.
- `scripts/little_loops/fsm/validation.py` — MR-1 through MR-13; the generated
  YAML must still pass `ll-loop validate`. See BUG-2801.
- Catalog docs: `.claude/CLAUDE.md` § Commands & Skills, `commands/help.md`.
- `scripts/tests/test_builtin_loops.py` and any test asserting either name or
  either generated-file prefix.

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
8. Update catalog docs; run `python -m pytest scripts/tests/`,
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
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

open
