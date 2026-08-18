---
id: ENH-3248
type: ENH
title: Triage the refine-to-ready-issue retry path by failure kind instead of always
  refining
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:10Z'
completed_at: '2026-08-18T19:29:27Z'
blocked_by: []
relates_to:
- BUG-3245
- ENH-3238
- ENH-3244
depends_on: []
confidence_score: 98
outcome_confidence: 84
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 21
---

# ENH-3248: Triage the refine-to-ready-issue retry path by failure kind instead of always refining

## Summary

`check_refine_limit` routes every gate failure to a single remedy, `refine_followup`
(`/ll:refine-issue --auto --gap-analysis`), which is additive-only. Failures that need content
*removed*, *rewritten*, or *deterministically filled* get a remedy structurally incapable of
clearing them. Route by failure kind: deterministic normalize, then self-referential reconcile,
then re-research refine.

## Current Behavior

Four gates in `scripts/little_loops/loops/refine-to-ready-issue.yaml` route to `check_refine_limit`
(`:482-502`), which routes uniformly to `refine_followup` (`:177-191`):

| Gate | Line | Failure means | Needs | `--gap-analysis` can do it |
|---|---|---|---|---|
| `check_verify_verdict` | `:289-299` | claims don't match the codebase | re-research | ✅ |
| `check_readiness` | `:360-390` | confidence below threshold | re-research | ✅ |
| `check_hedges` | `:301-310` | unresolved prose hedges | answer by research | ✅ (post-ENH-3244) |
| `check_ac_automatable` | `:335-344` | manual-verification ACs | **rewrite ACs** | ❌ |

Pre-ENH-3244, `check_hedges` conflated two failure kinds: it counted
`count_open_questions_in_sections` + `locate_unresolved_options`
(`scripts/little_loops/cli/issues/check_open_questions.py:59-62`) with `\bTBD\b` still a term in
`_OPEN_QUESTION_SIGNAL_RE`, so a literal template placeholder and a genuine prose hedge were
indistinguishable at the gate. ENH-3244 (done, 2026-08-18) performed that split: `\bTBD\b` moved to
the `template_placeholders` structural gap class (`issue_parser.py:2054`), so `check_hedges` now
measures prose hedges only — a research-shaped failure for which `--gap-analysis` **is** the right
remedy. The placeholder half now has no gate at all in this loop; adding one is this issue's work
(Proposed Solution step 3).

`refine_followup` is additive-only by contract (`:177-181`): *"Gap-analysis is additive-only (never
removes content) and does not consume max_refine_count."*

Observed on the ENH-3238 run
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`, 27 routes):

```
refine_issue → wire_issue → verify_issue → VALID → check_hedges NO → hedge_attempts=1 → refine_followup
             → check_wire_done(=1) → verify_issue → VALID → check_hedges NO → hedge_attempts=2 → PROCEED
             → check_ac_automatable → confidence_check → done
```

`check_hedges` failed on template placeholders. Its remedy could not delete them. The retry produced
no improvement, `check_hedges` failed again, `check_hedge_attempts` hit its cap, and the loop
proceeded to `done` with the debris intact — plus new debris the additive retry itself created
(BUG-3245).

## Expected Behavior

A gate failure routes to a remedy capable of fixing that kind of failure, escalating cheapest-first:

```
normalize (deterministic, no LLM)  →  reconcile (self-referential)  →  refine (re-research)
```

- **Repairable structural debris** → `ll-issues format-check --fix --apply` (ENH-3247). No model.
  "Repairable" is not a judgment call: it is exactly the key set of `_REPAIR_DISPATCH`
  (`scripts/little_loops/cli/issues/format_check.py:281-286`) — `prose_dep_drift`,
  `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`, plus the
  `template_placeholders` entry this issue adds. A gap class with no entry in that table is **not**
  routable to this rung.
- **Stale directive sections / non-automatable ACs** → `/ll:reconcile-issue` (ENH-3246). Reads the
  issue's own findings; no codebase research. Bounded by reconcile's own contract — see Decision
  Rules › Reconcile's mandate is the routing boundary.
- **Claim/codebase mismatch, low readiness** → `refine_followup`. Unchanged.
- **Unresolved prose hedges (`check_hedges`, post-ENH-3244)** → `refine_followup` via
  `check_hedge_attempts`. Unchanged.
- **Missing/failing Program Design (BUG-3249's new `check_design` gate)** → `refine_followup`
  **directly**, skipping both cheaper rungs. See Decision Rules › Design-gap exception.
- **Template placeholders (ENH-3244's signal)** → split by whether the placeholder's correct value
  is *computable from the issue's own frontmatter*. See Decision Rules › The placeholder class is
  three kinds:
  - **Frontmatter-derivable** — `Impact: [P0-P5]`, `Status: [P0-P5]`, `Status: [YYYY-MM-DD]`,
    `Labels: [type-label]` → `normalize_structure`, via a new `template_placeholders` fixer in
    `_REPAIR_DISPATCH`. Deterministic, no model.
  - **Judgment** — `Impact: [Small/Medium/Large]` (Effort), `Impact: [Low/Medium/High]` (Risk),
    `Impact: [Yes/No]` (Breaking Change), `Impact: [Justification]`, and the prose-section stubs
    (`Summary: [Description extracted from input]`, …) → `refine_followup`. These sections sit
    **outside** reconcile's rewrite scope, so the reconcile rung is skipped as incapable, not tried.
  - **Research-shaped** — `Integration Map: TBD - requires codebase analysis` (and the four sibling
    `TBD -` tokens), `Implementation Steps: [Major phase 1]` / `[Verification approach]`,
    `Proposed Solution: TBD - requires investigation` → `refine_followup` **directly**. These are
    *absent research*, structurally identical to the design gap; no deterministic or
    self-referential rung can produce their content.

A retry escalates to `refine_followup` only when the cheaper remedies cannot clear the gate — except
for the design-gap, judgment-placeholder, and research-shaped-placeholder kinds, where the cheaper
rungs are known-incapable rather than merely untried.

## Motivation

The uniform remedy is the defect — not the BUG-3170 cap, and not `--gap-analysis`, which is correct
for the three research-shaped failures (verify verdict, readiness, prose hedges). Post-ENH-3244 the
scope is precise rather than "half": **one existing gate is mis-routed** —
`check_ac_automatable`, whose failure needs an AC rewrite that an additive pass cannot perform — and
**one failure kind has no gate at all**, the `template_placeholders` class ENH-3244 split out, whose
frontmatter-derivable members are deterministically fixable and today go unfixed entirely. Both
mis-routes are guaranteed waste or guaranteed silence: a mis-routed retry spends the shared refine
budget, produces no progress toward the gate it was invoked for, and (per BUG-3245) actively
degrades the file; an ungated failure kind ships debris to `done`, which is exactly what the
ENH-3238 run did.

Cost matters here. On the observed run `refine_issue` billed ~$0.65 and `refine_followup` ~$0.43,
against a total run cost of ~$2.53 for 22 minutes. A deterministic normalize is effectively free and
a reconcile pass is a bounded rewrite with no codebase research. Ordering cheapest-first converts the
most common failure kinds into the cheapest remedies.

## Proposed Solution

0. **Make `normalize_structure` capable before routing to it (option (b)).** Add a
   `template_placeholders` entry to `_REPAIR_DISPATCH` (`format_check.py:281-286`) whose fixer fills
   **only** the frontmatter-derivable tokens, leaving every other placeholder in place:

   | Gap entry | Filled from | Written as |
   |---|---|---|
   | `Impact: [P0-P5]` | frontmatter `priority` | `P2` |
   | `Status: [P0-P5]` | frontmatter `priority` | `P2` |
   | `Status: [YYYY-MM-DD]` | frontmatter `discovered_date` | `2026-08-17` |
   | `Labels: [type-label]` | frontmatter `type` | `enhancement` / `bug` / `feature` / `epic` |

   Fixer signature follows the shared shape
   `(config, source_id, path, targets, *, apply) -> None` (`_fix_empty_provenance_stubs` is the
   closest model: pure transform + `atomic_write`, dry-run prints a count). It is **body-rewriting,
   so it must NOT be added to `_SWEEP_SAFE_REPAIRS`** — single-issue mode only, matching the other
   three body fixers (`format_check.py:288-293`). It must be idempotent and fence/inline-code
   masked, reusing `_template_placeholders`' own masking so a section's prose that *names* its
   placeholder is not rewritten. `--fix` still exits 1 afterward whenever judgment or research-shaped
   placeholders remain — that is expected and is why step 1's pass-through shape is required.
1. **Add a `normalize_structure` state** running `ll-issues format-check ${issue_id} --fix --apply`
   (ENH-3247). Deterministic, no LLM, unconditional after `refine_issue` / `refine_followup` /
   `wire_issue`, placed **before** `verify_issue` so every downstream gate reads a post-normalize
   file. **It is a pass-through, not a gate**: `cmd_format_check` returns 1 whenever *any*
   gap remains — including the many classes `--fix` cannot repair (`format_check.py:398`,
   `:576-579`) — so its exit code carries no routing signal here. The action must therefore end in
   `|| true`, or `on_error` must point at the same successor as `next`; otherwise
   `executor.py:1834-1835` (a shell state with both `next:` and `on_error:` routes to `on_error` on
   non-zero exit) sends nearly every run down the error path. No `evaluate:`, no `on_yes`/`on_no`.
   Per the `mark_wire_done` / `write_broke_down` load-bearing test (Codebase Research Findings), this
   write is **not** load-bearing for any downstream reader, so `on_error` falls through to `next`
   rather than to `failed`.
2. **Add a `reconcile_issue` state** invoking `/ll:reconcile-issue ${issue_id}`, with a
   `pruning_profile` matching the other slash-command states in this loop, and **without**
   `fragment: with_rate_limit_handling` / `on_rate_limit_exhausted` — see Decision Rules › Rate-limit
   fragment follows the host file.
3. **Add the missing `check_placeholders` gate.** ENH-3244 shipped detection only: it added
   `FormatGaps.template_placeholders` (`issue_parser.py:514`), the `placeholder_count()` accessor
   (`:1503-1520`), and the `format-check` report line (`format_check.py:382-384`) — **no gate state**
   in this loop. This issue adds it:
   - Position: immediately after `check_hedges`' `on_yes` / `check_hedge_attempts`' `on_no`, before
     `check_ac_automatable`, so it sits in the same score-independent deterministic gate band.
   - Signal: `ll-issues format-check ${issue_id} --format json` (note: the flag is
     `--format json`, **not** `--json`) piped to a count of `.template_placeholders`, evaluated
     `output_numeric` / `eq` / `0`. `placeholder_count()` exists as a Python accessor but has no CLI
     entry point, so the JSON path is the only shell-reachable signal today.
   - Routing: `on_yes` → `check_ac_automatable`; `on_no` → `check_refine_limit`.
   - **No attempt counter, and no `normalize_structure` loopback.** Because
     `normalize_structure` runs unconditionally *before* this gate (step 1), every placeholder this
     gate still sees is by construction one `--fix` could not repair — judgment or research-shaped,
     both of which are refine's. A loopback to `normalize_structure` would be an idempotent re-run
     and would risk phantom convergence against `circuit.repeated_failure` (`:72-75`) for no gain.
4. **Retarget the one mis-routed gate**: `check_ac_automatable.on_no` → `reconcile_issue` (ACs are in
   reconcile's unconditional rewrite list) instead of `check_refine_limit`.
5. **Leave `check_verify_verdict`, `check_readiness`, and `check_hedges` routing unchanged** —
   `refine_followup` is the correct remedy for all three. (`check_hedges` post-ENH-3244 measures
   genuine prose hedges only; an earlier revision of this issue sent it to `normalize_structure`,
   which cannot clear it.)
6. **Bound `reconcile_issue`** with a per-run attempt counter in `${context.run_dir}`, mirroring
   `check_refine_limit` (`:482-502`) and `check_hedge_attempts` (`:312-333`), so a gate a reconcile
   cannot clear escalates rather than spinning. Use the **independent scoped counter** shape, not
   autodev's shared+marker layering — see Decision Rules › Counter shape. **`normalize_structure` and
   `check_placeholders` get no counter**: neither has a loopback into itself.
7. **Raise `max_steps` 40 → 55**, with the arithmetic recorded in a comment as the file already does
   for ENH-3031 (`:38-43`) and BUG-3065 (`:44-51`). Budget over the BUG-3065 worst case:
   `normalize_structure` adds 1 step per refine/wire pass (≤3 passes = 3); `check_placeholders` adds
   1 per gate-band pass (≤3 = 3); a `reconcile_issue` cycle costs ~6 (counter → `reconcile_issue` →
   `normalize_structure` → `verify_issue` → the gate band), bounded at one cycle by its counter — ~12
   more, and 55 preserves roughly the same worst-case-to-budget headroom the ENH-3031 and BUG-3065
   blocks left.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/format_check.py` — the new `template_placeholders` fixer and its
  `_REPAIR_DISPATCH` entry (`:281-286`), the token → frontmatter-field allowlist constant, and the
  `--fix` argparse help, which enumerates the four repairable classes by name and must gain the
  fifth. **Not** `_SWEEP_SAFE_REPAIRS` (`:288-293`) — body-rewriting repairs stay
  single-issue-mode-only.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the three new states
  (`normalize_structure`, `reconcile_issue`, `check_placeholders`), the retargeted
  `check_ac_automatable.on_no`, the `reconcile_issue` attempt counter, `max_steps`, and the
  routing-summary comment block (`:4-33`), which is maintained as documentation and must be updated
  to match.
- `docs/reference/CLI.md` — the `ll-issues format-check` entry's list of `--fix`-repairable gap
  classes.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:78-90` — `resolve_issue` initializes the
  per-run counter files; new counters must be initialized there too.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:606-766` — the `diagnose` /
  `write_failure_evidence` / `classify_terminal` chain enumerates captured states by name. New
  states with `capture:` must be added to those blocks or their failures will be invisible in the
  evidence file.
- `scripts/little_loops/loops/autodev.yaml` — nests this loop; a changed step budget and terminal
  behavior affect it. The `refine-broke-down` / `refine-terminal-class` artifacts it reads must keep
  their current meaning.
- `scripts/little_loops/fsm/validation/` — `ll-loop validate` must pass on the modified YAML.

### Similar Patterns
- `autodev.yaml:1557-1608` (`check_reconcile_needed`) and `:1913-1929` (`reconcile_current`) — the
  existing reconcile call state, including its `pruning_profile` shape and one-shot guard. Model the
  new `reconcile_issue` state's *invocation* on it, but **not** its `fragment` /
  `on_rate_limit_exhausted` keys (Decision Rules › Rate-limit fragment follows the host file).
- `check_hedges` (`:301-310`) — the deterministic-CLI-gate idiom (`action_type: shell`,
  `evaluate: output_numeric`) to mirror for the new `check_placeholders` gate.
- `check_hedge_attempts` (`:312-333`) — the per-run attempt-counter idiom to mirror for the
  `reconcile_issue` bound.
- `mark_wire_done` (`:241-245`) and `write_broke_down` (`:568-574`) — the two in-file pass-through
  (non-gate) shell-state shapes; `normalize_structure` follows `mark_wire_done`'s fall-through
  `on_error`.
- `_fix_empty_provenance_stubs` (`format_check.py`) — the pure-transform + `atomic_write` + dry-run
  count fixer shape for the new `template_placeholders` fixer.

### Tests
- `scripts/tests/` — `ll-loop validate refine-to-ready-issue` exits 0 (MR-1..MR-14 plus routing
  reachability); every state named in the `diagnose` / `write_failure_evidence` blocks exists; the
  routing-summary comment matches the actual `on_yes`/`on_no` targets.
- A routing test asserting `check_ac_automatable.on_no` reaches `reconcile_issue` and that
  `check_verify_verdict.on_no`, `check_readiness.on_no`, and `check_hedges.on_no` all still reach
  `check_refine_limit` / `check_hedge_attempts` unchanged. Update
  `test_check_ac_automatable_state_routing` (`scripts/tests/test_builtin_loops.py:1630-1639`,
  currently asserting `on_no == "check_refine_limit"` at `:1637`) **in place**, matching how
  ENH-3031/BUG-3170 handled prior retargets.
- A test asserting `normalize_structure` carries no `evaluate:`/`on_yes`/`on_no` and cannot strand
  the run on a non-zero `format-check` exit — either its action ends in `|| true` or its `on_error`
  equals its `next` (Proposed Solution step 1).
- A test asserting `check_placeholders` reads the JSON signal (`--format json`, not `--json`),
  evaluates against 0, routes `on_yes` → `check_ac_automatable` and `on_no` →
  `check_refine_limit`, and has **no** route back to `normalize_structure` (the phantom-convergence
  guard from step 3).
- **Capability invariant, at token granularity** (`scripts/tests/test_ll_issues_format_check.py`):
  assert the fixer's token allowlist ⊆ the tokens `_template_placeholder_patterns` actually emits for
  each issue type, and that every allowlisted token maps to a frontmatter field that exists on a real
  issue. A *class*-level `routed-set ⊆ _REPAIR_DISPATCH.keys()` assertion is necessary but no longer
  sufficient once `template_placeholders` is registered: the class has a fixer, but the fixer covers
  only 4 of its ~20 tokens, so a class-only test would wrongly certify the judgment and
  research-shaped tokens as normalize-clearable. Do **not** write a `FormatGaps`-completeness test
  (every gap class has a `_REPAIR_DISPATCH` entry) — most classes are intentionally unfixable, so
  that invariant is false by design.
- Fixer unit tests: idempotence (second `--fix --apply` is a no-op), fence/inline-code masking (a
  section documenting its own placeholder string is untouched), non-derivable tokens survive, and
  `--all --fix --apply` does not invoke it (`_SWEEP_SAFE_REPAIRS` exclusion).

### Documentation
- The in-file routing summary (`:4-33`) is the authoritative description and must be updated.

### Configuration
- N/A — new counters are run-scoped files under `${context.run_dir}`, not config.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Slash-command state shape in this file**: every existing slash-command state in `refine-to-ready-issue.yaml` (`refine_issue` `:157-175`, `wire_issue` `:231-239`, `verify_issue` `:279-287`, `breakdown_issue` `:550-566`) uses a plain shape — `action`, `action_type: slash_command`, `pruning_profile` (`name:` = skill-slug + mode suffix, e.g. `-repair`/`-auto`), `capture`, `next`, `on_error` — with no `on_yes`/`on_no`. Completion is read back afterward by a separate write-verdict/read-verdict gate state (`check_decision_mid_refine` `:193-204`, `check_verify_verdict` `:289-299`, explicitly named as "the write-verdict/read-verdict shape used throughout this file" in `check_verify_verdict`'s own comment `:290-294`).
- **Contested precedent for `reconcile_issue`**: `autodev.yaml`'s `reconcile_current` (`:1913-1929`, the state this issue's Similar Patterns cites as the model) additionally carries `fragment: with_rate_limit_handling` and `on_rate_limit_exhausted: done` — neither key appears on any existing state in `refine-to-ready-issue.yaml` itself. The two examples disagree on whether the new `reconcile_issue` state needs the rate-limit fragment/route or should follow the plainer file-native shape above.
- **Attempt-counter idiom**: a counter is a plain integer file under `${context.run_dir}`, initialized to `'0'` in `resolve_issue`'s single chained `mkdir -p ... && printf '0' > ... && ...` action (`:78-89`), then read-increment-write-echo'd by its own `action_type: shell` state with `capture:` and `evaluate: {type: output_numeric, operator: lt, target: N}` — see `check_hedge_attempts` (`:312-333`) and `check_refine_limit` (`:482-502`), which are structurally identical scripts.
- **Contested counter convention**: `autodev.yaml`'s `count_repair_cycle_reconcile` (`:1931-1966`, cited by this issue as the reconcile-bound model) layers a *shared* cross-repair-class counter on top of a scoped counter, guarded by a consume-once marker file. `refine-to-ready-issue.yaml`'s existing counters (`check_hedge_attempts`, `check_refine_limit`) are each single, independent, scoped counters with no shared backstop. This issue's Decision Rules (`:190-192`) commits only to "a per-run counter" per new state — it does not say whether the new counters need the shared-ceiling layering `autodev.yaml` uses.
- **Four-block registration order**: a capturing state gets one line appended (not inserted alphabetically) to each of `resolve_issue`'s init chain, `diagnose`'s prompt bullets (`:630-637`), `write_failure_evidence`'s three per-state sub-blocks — exit codes, `classify_failure` verdicts, and (only for the highest-signal states, currently `refine_issue`/`refine_followup`/`breakdown_issue`) a stderr-tail block (`:676-712`) — and `classify_terminal`'s two `for` loops (`:750-763`). No test enforces the four blocks' relative order, but every existing entry follows roughly the order states are first reached on the happy path.
- **`max_steps` comment convention**: each budget change gets its own comment block directly above `max_steps:`, shaped `# <ISSUE-ID>: <old> -> <new>.` followed by prose naming the added states/routes, their per-cycle step cost, the worst-case new total, and why the added cycle cannot spin — appended below prior entries, never replacing them. Evidence: the ENH-3031 and BUG-3065 blocks at `:38-51`.
- **Routing-test convention**: one test class per loop file in `scripts/tests/test_builtin_loops.py` (`TestRefineToReadyIssueSubLoop`, `:1366-1374`), with a `data` fixture that `yaml.safe_load`s the file directly (no FSM executor) and asserts `state.get("on_yes")`/`state.get("on_no")` via plain dict comparison. `test_check_ac_automatable_state_routing` (`:1630-1639`) currently asserts `check_ac_automatable.on_no == "check_refine_limit"` — retargeting that route means updating this existing assertion in place, matching how prior retargets (ENH-3031/BUG-3170) updated rather than duplicated it. `check_hedge_attempts` has its own counter-test pattern (`_run_check_hedge_attempts` helper `:1590-1597`, executes the state's bash `action` via `subprocess.run` against a `tmp_path` run_dir; see `test_check_hedge_attempts_counts_up_and_gates_at_two` `:1599-1615` and `test_check_hedge_attempts_counter_is_per_run` `:1617-1628`) — the model for testing the new attempt counters this issue adds.
- **MR rule scope**: MR-1..MR-6 (`scripts/little_loops/fsm/validation/meta_rules.py:1-5`) fire only on loops whose state `action` strings match meta-loop patterns (editing `loops/*.yaml`, `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`, `.claude/CLAUDE.md`). `refine-to-ready-issue.yaml`'s states act on `.issues/` files only (per its own `scope:` block `:35-37`), so MR-1..MR-6 do not fire on this file regardless of the new states added. The broadly-applicable checks relevant to this change live in `scripts/little_loops/fsm/validation/reachability.py` (capture-reachability — relevant to wiring the new states' `capture:` into `diagnose`/`write_failure_evidence`) and `shell_safety.py` (MR-9 shell over-escaping — relevant to the new bash counter states).

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Pass-through-state precedent** (confirms Proposed Solution step 1's shape): `mark_wire_done` (`refine-to-ready-issue.yaml:241-245`) and `write_broke_down` (`:568-574`) are the existing in-file examples of a non-gate `action_type: shell` state with no `evaluate`/`on_yes`/`on_no` — just `action`, `next`, `on_error`. They diverge on `on_error` target by whether the write is load-bearing downstream: `mark_wire_done.on_error` falls through to `verify_issue` (safely skippable), `write_broke_down.on_error` routes to `failed` with an inline comment ("failing to record the decomposition marker loses the signal the parent loop reads — surface it instead of exiting 0"). `normalize_structure`'s `on_error` choice should follow this same load-bearing test.
- **Rate-limit-fragment contest, confirmed at scale**: sampled across both files — 0/5 slash-command states in `refine-to-ready-issue.yaml` (`refine_issue`, `refine_followup`, `wire_issue`, `verify_issue`, `breakdown_issue`) carry `fragment: with_rate_limit_handling` or `on_rate_limit_exhausted`; 5/5 sampled slash-command states in `autodev.yaml` (`reconcile_current` `:1913-1929`, `refine_for_design` `:1871-1890`, `run_spike` `:1345-1363`, `rerun_confidence_after_reconcile` `:1968-1988`, `run_size_review` `:1403-1424`) carry both. Each file is internally consistent but the files disagree with each other — this sharpens the "Contested precedent for `reconcile_issue`" finding already on file from a single-example comparison to a 0/5-vs-5/5 pattern; still undecided which convention the new `reconcile_issue` state should follow.
- **Routing-test docstring convention**: existing routing tests in `test_builtin_loops.py` (e.g. `test_check_hedges_state_routing` `:1521-1534`) pair each `on_yes`/`on_no`/`on_error` assertion with a docstring naming the originating issue ID and the rationale (e.g. "routes on_no through the attempt-bounded gate, not check_refine_limit directly (BUG-3170)") — the new routing tests for `check_ac_automatable`/`reconcile_issue`/`normalize_structure` should follow this same self-documenting shape, not bare asserts.
- **No existing `_REPAIR_DISPATCH`-completeness test**: searched `scripts/tests/` for a test asserting every `FormatGaps` gap class has a corresponding `_REPAIR_DISPATCH` entry (the "capability invariant" test called for in this issue's Tests section). None exists — `TestFormatCheckDuplicateFindingsFix` (`test_ll_issues_format_check.py:2013-2054`) exercises one registered fixer end-to-end, not dispatch-table completeness. This test has no existing analog to model structurally beyond iterating the gap-class enum against `_REPAIR_DISPATCH.keys()`.

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Rate-limit fragment contest, extended to a third file**: `rn-remediate.yaml` carries
  `fragment: with_rate_limit_handling` on every one of its slash-command states — `refine` (`:636`),
  `refine_light` (`:650`), `refine_first` (`:664`), `refine_followup` (`:676`), `wire` (`:615`),
  `assess`/`re_assess` (`:149`, `:721`) — including the same `/ll:refine-issue`/`/ll:wire-issue`
  commands that appear bare in `refine-to-ready-issue.yaml`. No doc (checked
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`) states a rule for
  when the fragment is required vs optional on a slash-command state — the disagreement spans at
  least three loop files with no arbitrating rule. The closest on-point precedent,
  `.issues/enhancements/P4-ENH-3079-document-inert-on-rate-limit-exhausted-on-sub-loop-call-states.md`
  (done), scopes its ruling to `loop:` sub-loop-call states specifically (where
  `on_rate_limit_exhausted` is provably inert per `_execute_sub_loop`'s `str | None` return type,
  `fsm/executor.py:820`) — it does not resolve the question for `action_type: slash_command` states
  like `reconcile_issue` would be.
- **Shared-counter-with-marker pattern confirmed autodev-only**: `count_repair_cycle_*` +
  consume-once-marker (`autodev.yaml:554,805,1365,1426,1892,1931`) exists nowhere else in the
  codebase. `rn-refine.yaml` explicitly cites this same precedent in comments (`:411`, `:492`,
  "mirrors autodev.yaml's `count_repair_cycle_refine` convention") but implements an **independent**
  scoped counter instead — the same shape `check_hedge_attempts`/`check_refine_limit` already use in
  `refine-to-ready-issue.yaml`. No doc or comment states a rule for when the shared+marker shape
  applies; autodev's own inline comments (`:1934`, `:2008`, `:2138`) justify it only for that file's
  six-repair-class shared stagnation backstop, a condition this issue's single new counter does not
  share.
- **Four-block registration has no structural completeness test**: no test asserts that
  `resolve_issue`'s init chain, `diagnose`'s prompt bullets, `write_failure_evidence`'s
  exit_code/failure_type/stderr-tail sub-blocks, and `classify_terminal`'s two `for` loops all
  reference the same state-name set. The file's current content already diverges:
  `check_hedge_attempts` appears in `diagnose` (`:636`) and in `write_failure_evidence`'s
  exit_code/failure_type sub-blocks (`:682`, `:692`) but is absent from `classify_terminal`'s two
  `for` loops (`:752`, `:758`) and from the stderr-tail heredoc block (only `refine_issue`,
  `refine_followup`, `breakdown_issue`, and `prev.output` get full stderr dumps there). The nearest
  enforcement is `test_diagnose_sources_all_carry_capture` (`test_builtin_loops.py:1913`, asserts a
  minimum diagnose-source set all carry `capture:`) and
  `test_classify_terminal_reads_failure_type_for_every_source_state`
  (`test_builtin_loops.py:1888`, internal self-consistency of block 4 only) — neither checks
  cross-block membership. Inclusion in each of the four blocks is decided per-state in this file
  today, not mechanically mirrored.
- **`max_steps` comment shape confirmed** (`refine-to-ready-issue.yaml:38-51`): `# <ISSUE-ID>: <old>
  -> <new>.` opening line, then prose that (a) names the concrete new/changed states driving the
  delta, (b) walks the worst-case cycle by state name with `->` arrows, (c) states the resulting
  worst-case iteration count, and (d) for a cycle-introducing change, an explicit non-spin argument.
  Not test-enforced — observable only from the ENH-3031/BUG-3065 blocks' own precedent.

## Program Design

### Call Path

Two paths, both new. The gate band, post-change:

`refine_issue` -> `normalize_structure` -> `verify_issue` -> `check_verify_verdict` ->
`check_hedges` -> `check_placeholders` -> `check_ac_automatable` -> `reconcile_issue` ->
`normalize_structure`

And inside `normalize_structure`, the Python call path the new fixer adds:

`cmd_format_check` -> `_apply_fix_dispatch` -> `_fix_template_placeholders` ->
`_template_placeholder_patterns`

- `check_ac_automatable` (`refine-to-ready-issue.yaml:335-344`) currently routes `on_no` to
  `check_refine_limit`; retargeted to the new `reconcile_issue` state. This is the only existing
  route this issue changes.
- `check_placeholders` is new; it has no current analog in this file because ENH-3244 shipped
  detection without a gate.
- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:383`) backs the new
  `normalize_structure` state via `--fix --apply` (ENH-3247), dispatching through
  `_apply_fix_dispatch` over `_REPAIR_DISPATCH` (`:281-286`) — which this issue extends with the
  `template_placeholders` fixer.
- `_template_placeholder_patterns` (`issue_parser.py`, ENH-3244) is the runtime-derived section →
  token map the fixer's allowlist is validated against; it reads
  `scripts/little_loops/templates/*-sections.json`, so a new template placeholder appears in the gap
  report with zero Python changes — and is therefore **unfixed** until someone adds it to the
  allowlist deliberately. That asymmetry is intended: detection fails open, repair fails closed.

Note on citations: `reconcile_current` (`autodev.yaml:1913-1929`) is a *shape to copy*, not a
callee on this path — it lives in a different loop file and is never reached from here.

### Decision Rules

- **Escalation order**: deterministic → self-referential → re-research. Never invoke a more expensive
  remedy before a cheaper one that can address the same failure kind.
- **Remedy-capability match**: a gate routes to a remedy only if that remedy can perform the
  operation the failure requires (delete / rewrite / research). This is the invariant the current
  design violates.
- **Design-gap exception: cheapest-first is subordinate to remedy-capability.** BUG-3249 adds a
  `check_design` gate to this loop. Its failure kind routes **straight to `refine_followup`**, not
  through `normalize_structure` or `reconcile_issue`. This is not a violation of the escalation order
  — it is the capability rule taking precedence, and two completed issues make it a fact rather than
  a judgment call:
  - **BUG-3002** (done) — *"autodev routes `design_gate_failed` to reconcile-issue, whose contract
    excludes the Program Design section"*. Reconcile **cannot** write `## Program Design`. Sending a
    design-gap failure down the reconcile rung re-creates a bug that was already fixed once.
  - **BUG-3001** (done) — *"refine-issue never populates `## Program Design` despite being the
    prescribed remedy for the gate"*. Now fixed, so refine is the capable remedy.

  A missing design section is *absent research*, not *stale or malformed text*, so no deterministic
  normalize and no self-referential rewrite can produce it. Generalized: **the ladder is ordered by
  cost only among remedies that are capable; an incapable rung is skipped, not tried.**
- **The placeholder class is three kinds**, and the discriminator is *whether the correct value is
  computable from the issue's own frontmatter* — not whether it "looks fillable". ENH-3244 emits one
  signal (`FormatGaps.template_placeholders` / `placeholder_count`) as a list of
  `"{section}: {token}"` strings derived at runtime from the type's `creation_template` values
  (`_template_placeholder_patterns`), so the section name travels with every entry and routing can key
  on it. The actual token map, enumerated from the ENH/BUG/FEAT templates:
  - *Frontmatter-derivable* — `Impact: [P0-P5]`, `Status: [P0-P5]` ← `priority`;
    `Status: [YYYY-MM-DD]` ← `discovered_date`; `Labels: [type-label]` ← `type`. A pure function of
    data already in the file → `normalize_structure`, via the new fixer (Proposed Solution step 0).
  - *Judgment* — `Impact: [Small/Medium/Large]`, `Impact: [Low/Medium/High]`, `Impact: [Yes/No]`,
    `Impact: [Justification]`, and the prose stubs (`Summary: [Description extracted from input]`,
    `Context: …`, `Current Behavior: …`, `Expected Behavior: …`, `Motivation: …`). Effort, Risk, and
    Breaking Change are *assessments*, not derivations — nothing in the file determines them → the
    deterministic rung is incapable, and (per the mandate boundary below) so is reconcile →
    `refine_followup`.
  - *Research-shaped* — `Integration Map: TBD - requires codebase analysis` and its four siblings,
    `Implementation Steps: [Major phase 1]` / `[Major phase 2]` / `[Verification approach]`,
    `Proposed Solution: TBD - requires investigation`. **Absent research**, exactly the shape the
    design-gap exception covers → straight to `check_refine_limit`.
- **There is no placeholder rung for `reconcile_issue`, and that is a derived fact, not an
  omission.** Cross the two constraints and the intersection is empty:
  reconcile's rewrite scope is `## Implementation Steps`, `## Acceptance Criteria`, `## Integration
  Map`, and a conditional `## Scope Boundaries` carve-out. Every placeholder token *inside* that scope
  (Integration Map's five `TBD -` tokens; Implementation Steps' `[Major phase N]` /
  `[Verification approach]`) is research-shaped, so it escalates on capability grounds. Every token
  whose value is cheaply obtainable sits in `## Impact`, `## Status`, or `## Labels` — all **out of
  contract**, so routing it to `reconcile_issue` would produce a no-op pass. An earlier revision of
  this issue routed "derivable/deletable placeholders inside reconcile's rewrite scope" to
  `reconcile_issue`; that set is provably empty and the branch was dead code. Reconcile's live
  trigger in this loop is `check_ac_automatable` only.
- **`normalize_structure`'s eligible set is `_REPAIR_DISPATCH`'s keys — and, within
  `template_placeholders`, its token allowlist.** Routing a gate to this rung without a matching
  repair re-commits the exact defect this issue exists to fix. The class-level rule is necessary but
  not sufficient once `template_placeholders` is registered with a *partial* fixer: the routed
  granularity is the token, so the invariant is enforced at token granularity (see Tests). The
  alternative capable owner considered and rejected for the frontmatter-derivable tokens was
  `/ll:format-issue --auto` — rejected because it is a model invocation for a pure function of
  frontmatter, which loses the whole cost argument this issue rests on.
- **Reconcile's mandate is the routing boundary.** `commands/reconcile-issue.md:31-49,91-92` binds the
  rewrite to `## Implementation Steps`, `## Acceptance Criteria`, the whole `## Integration Map`, plus
  a conditional `## Scope Boundaries` carve-out and `⚠ Superseded` marker clearing, and explicitly
  excludes "every other section not in the rewrite list". Debris outside those sections — a
  placeholder in `## Summary`, `## Current Behavior`, or `## Impact` — is **out of contract**, so
  routing it to `reconcile_issue` produces a no-op pass. Only failures located inside the rewrite
  scope take this rung; everything else escalates.
- **Rate-limit fragment follows the host file, not the cited model.** `reconcile_issue` gets
  **no** `fragment: with_rate_limit_handling` and no `on_rate_limit_exhausted`. The precedent is
  genuinely split — 0/5 slash-command states in `refine-to-ready-issue.yaml` carry them, 5/5 sampled
  in `autodev.yaml` do, 7/7 in `rn-remediate.yaml` do — with no arbitrating rule in any doc
  (Codebase Research Findings). Deciding it here rather than leaving it contested: **each loop file is
  internally consistent, and a new state joins its host file's convention.** A mixed file is strictly
  worse than either convention, and this issue is not the place to migrate
  `refine-to-ready-issue.yaml`'s five existing bare states. If the fragment should be universal on
  slash-command states, that is a separate whole-file change with its own issue.
- **Counter shape: independent and scoped.** The `reconcile_issue` counter is a single plain-integer
  file under `${context.run_dir}`, read-increment-write-echo'd by its own gate state — the
  `check_hedge_attempts` / `check_refine_limit` shape this file already uses twice. **Not**
  `autodev.yaml`'s shared-counter-plus-consume-once-marker layering: autodev's own comments justify
  that only as a shared stagnation backstop across its six repair classes, a condition a single new
  counter does not share, and `rn-refine.yaml` already set the precedent of citing autodev's
  convention while implementing the independent scoped counter instead.
- **Escalation is mandatory, never discretionary**: `reconcile_issue` is bounded by a per-run counter and
  falls through to `check_refine_limit`, so a failure the cheap remedies cannot fix still reaches
  refine and ultimately `breakdown_issue`. `normalize_structure` is a counter-free pass-through
  (Proposed Solution step 5) — it never loops back into itself, so it needs no bound.
- **Unchanged routing**: `check_verify_verdict` and `check_readiness` keep `refine_followup`.

### Signatures
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` — backs the new
  `normalize_structure` state; defined at `scripts/little_loops/cli/issues/format_check.py:383`.
  Returns 1 when **any** gap remains, fixable or not (`:398`, `:576-579`), so its exit code is
  **not** a usable gate signal for this state — see Proposed Solution step 1 for the
  pass-through shape that requires.
- `_REPAIR_DISPATCH: dict[str, Callable]` — the gap-class → repair-function table at
  `scripts/little_loops/cli/issues/format_check.py:281-286`. Its key set is the authoritative
  definition of what `normalize_structure` can clear at class granularity; this issue adds the
  `template_placeholders` key.
- `_apply_fix_dispatch(config, source_id, path, gaps, *, apply, sweep) -> bool` — the dispatch loop
  (`format_check.py`, just below `_REPAIR_DISPATCH`). It passes **every** target of a fired class to
  that class's fixer and skips any class absent from `_SWEEP_SAFE_REPAIRS` when `sweep` is set, so
  the new fixer must filter its own `targets` down to the allowlist rather than assume pre-filtering.
- `_fix_template_placeholders(config: BRConfig, source_id: str, path: Path, targets: list[str], *,
  apply: bool) -> None` — **new**. Shared fixer signature; model on `_fix_empty_provenance_stubs`
  (pure transform + `atomic_write`, dry-run prints a count).
- `_template_placeholder_patterns(issue_type: str, templates_dir: Path | None = None) ->
  dict[str, list[str]]` — `scripts/little_loops/issue_parser.py`, ENH-3244. Section → token map,
  derived at runtime from `templates/*-sections.json`. The fixer's allowlist is validated against it.
- `placeholder_count(issue_path: Path, templates_dir: Path | None = None) -> int` —
  `issue_parser.py:1503`. The scalar accessor ENH-3244 added for non-LLM gates, but it has **no CLI
  entry point**, so `check_placeholders` reads `format-check --format json` instead. Worth noting for
  a future simplification: a thin CLI wrapper would let the gate drop the JSON parse.

## Implementation Steps

All three prerequisites are `done`: ENH-3247 (`format-check --fix` structural repairs), ENH-3246
(widened reconcile mandate), and ENH-3244 (placeholder detection split out of the hedge scan).
Nothing blocks this issue.

**Phase 1 — make the deterministic rung capable (Python, `format_check.py`):**

1. Add the token → frontmatter-field allowlist constant and `_fix_template_placeholders`, filtering
   its own `targets` to the allowlist (`_apply_fix_dispatch` does not pre-filter). Reuse
   `_template_placeholders`' fence/inline-code masking.
2. Register it in `_REPAIR_DISPATCH`; deliberately **omit** it from `_SWEEP_SAFE_REPAIRS`. Update the
   `--fix` argparse help and `docs/reference/CLI.md`.
3. Fixer unit tests (idempotence, masking, non-derivable survival, sweep exclusion) plus the
   token-granularity capability invariant.

**Phase 2 — route to it (`refine-to-ready-issue.yaml`):**

4. Add `normalize_structure` (pass-through shape, Proposed Solution step 1) with `capture:`, placed
   after `refine_issue` / `refine_followup` / `wire_issue` and before `verify_issue`.
5. Add `check_placeholders` (deterministic gate reading `--format json`), positioned in the
   score-independent gate band before `check_ac_automatable`. No counter, no `normalize_structure`
   loopback.
6. Add `reconcile_issue` (bare slash-command shape — no rate-limit fragment) plus its independent
   scoped attempt counter, initialized in `resolve_issue`'s init chain.
7. Retarget `check_ac_automatable.on_no` → `reconcile_issue`. Leave `check_verify_verdict`,
   `check_readiness`, and `check_hedges` untouched.
8. Register the three new capturing states across the four enumeration blocks — `resolve_issue`'s init
   chain, `diagnose`'s prompt bullets, `write_failure_evidence`'s exit-code and `classify_failure`
   sub-blocks, and `classify_terminal`'s two `for` loops. Note there is **no** test enforcing
   cross-block membership and the file's existing content already diverges (`check_hedge_attempts` is
   in two blocks, not four), so this is a manual checklist, not something validation will catch.
9. Recompute `max_steps` (40 → 55) with the arithmetic comment, and update the routing-summary comment
   block to match the new gate band.

**Phase 3 — verify:**

10. `ll-loop validate refine-to-ready-issue` exits 0; add the routing tests (docstrings naming the
    originating issue ID and rationale, per the in-file convention).
11. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Eliminates the one guaranteed-waste retry route (`check_ac_automatable` →
  additive refine) and closes the ungated placeholder class ENH-3244 split out, giving it a free
  deterministic remedy. Not P1: the loop still terminates correctly today, just with unfixed debris
  and a wasted pass.
- **Effort**: Medium - now spans two components rather than one: a Python fixer with its own unit
  tests, plus three FSM states, counter plumbing, four enumeration blocks to keep in sync, `max_steps`
  arithmetic, and validation. The FSM's diagnose/evidence blocks make every state addition wider than
  it first appears, and the two phases are separable if the change needs splitting.
- **Risk**: Medium - routing changes in a 40-step FSM with a stall-detection circuit
  (`circuit.repeated_failure`, `:72-75`). New cycles risk phantom convergence if the attempt
  counters are wrong. Mitigated by mirroring the existing counter idiom, by giving
  `check_placeholders` no loopback at all, and by `ll-loop validate`. The Python fixer carries the
  usual body-rewriting risk (it edits issue files in place) — bounded by fence masking, idempotence
  tests, and the `_SWEEP_SAFE_REPAIRS` exclusion that keeps it out of `--all` sweeps.
- **Breaking Change**: No - external artifacts (`refine-broke-down`, `refine-terminal-class`) keep
  their meaning.

## Scope Boundaries

**This does not fix the substantive-error class.** ENH-3238's two real defects — a wrong edit site
and a wrong generated-file claim — required *probing the codebase*, which only `verify_issue` does.
No amount of retry triage catches them; that is ENH-3238's subject. This issue is about not wasting
a pass on failures the retry cannot fix.

**Not touching BUG-3170's cap.** The cap on genuine prose hedges is correct and stays. This issue
changes what a retry *does*, not how many are allowed.

**Not making `--gap-analysis` destructive.** Its additive-only contract is deliberate and is what
makes it safe to run repeatedly. Removal capability comes from the other two remedies.

**Not deterministically filling the judgment placeholders.** Effort, Risk, Breaking Change, and the
`[Justification]` slots are assessments; the new fixer covers exactly the four frontmatter-derivable
tokens and leaves the rest for refine. Widening the allowlist means inventing values, which is worse
than leaving the gap visible.

**Not making the fixer available to `--all` sweeps.** It is body-rewriting, so it stays out of
`_SWEEP_SAFE_REPAIRS` alongside the other three body fixers.

## Blocked By

Nothing. All three prerequisites are `done`:

- `ENH-3244` (done 2026-08-18) — supplied the `FormatGaps.template_placeholders` signal this issue's
  placeholder gate consumes, and moved `\bTBD\b` out of `_OPEN_QUESTION_SIGNAL_RE`
  (`issue_parser.py:2054`) so `check_hedges` now measures prose hedges only. Was briefly a hard
  `blocked_by`; cleared.
- `ENH-3246` (done) — reconcile permitted to rewrite the Integration Map subsections.
- `ENH-3247` (done) — `format-check --fix` able to repair structural debris, and the
  `_REPAIR_DISPATCH` table this issue extends.

## Related Issues

- ENH-3244 (done) — **supplied the placeholder signal this triage routes, and nothing more.**
  ENH-3244 was detection-only by decision: it added the gap class, the `placeholder_count()`
  accessor, and the report line, but **no repair function and no gate**. This issue supplies both,
  and owns every `refine-to-ready-issue.yaml` edit. Both previously proposed adding a gate to that
  file, which would have been a merge collision in the same sprint wave.
- BUG-3249 — adds the `check_design` gate to this loop. Sequenced **after** this issue, and its
  failure kind takes the design-gap exception in Decision Rules (straight to `refine_followup`).
- BUG-3245 — removes the debris the current additive retry creates.
- BUG-3001, BUG-3002 (both done) — the evidence behind the design-gap exception.
- ENH-3238 — the run that surfaced this.
- ENH-3246, ENH-3247 (both done) — the former blockers; see Blocked By. ENH-3247 established both
  `_REPAIR_DISPATCH` and the fixer signature this issue's new entry conforms to.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- BUG-3249
- ENH-3250

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-18T19:28:55 - `f0159f45-11d8-4867-9748-ca1d591ef8ee.jsonl`
- `/ll:ready-issue` - 2026-08-18T19:02:38 - `0bda2f92-786e-4202-a05d-e6630e60e1aa.jsonl`
- `/ll:confidence-check` - 2026-08-18T18:00:48 - `f6334ce4-fd4a-470a-a0cc-dbd1d14f42eb.jsonl`
- `/ll:refine-issue` - 2026-08-18T15:25:10 - `b98d0491-3f8d-44db-ac19-187eca069c7f.jsonl`
- `/ll:refine-issue` - 2026-08-18T14:58:03 - `81050041-a768-4bbc-b672-f371308c0627.jsonl`
- `/ll:confidence-check` - 2026-08-17T23:16:18 - `650587c4-5e3f-4515-a253-8c3aba6c3210.jsonl`
- `/ll:refine-issue` - 2026-08-17T22:57:39 - `383f19f2-e8c0-43aa-9cdd-d1c166fe7608.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:35:01 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:13:03 - `ffec4b47-4ed9-4eda-baf1-3dc49ac82fa1.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
