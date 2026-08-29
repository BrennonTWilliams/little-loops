---
id: ENH-3355
type: ENH
title: Generate workflow-generator's evaluator vocabulary from validator tables instead
  of hand-listing it in the attach_evaluators prompt
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T22:35:07Z'
completed_at: '2026-08-29T22:48:03Z'
verify_verdict: VALID
labels:
- workflow-generator
- drift
- feat-3328-followup
relates_to:
- FEAT-3328
confidence_score: 100
outcome_confidence: 93
decision_needed: false
reconcile_attempted: true
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3355: Generate workflow-generator's evaluator vocabulary from validator tables instead of hand-listing it in the attach_evaluators prompt

## Summary

`workflow-generator.yaml`'s `attach_evaluators` state (`action_type: prompt`,
`scripts/little_loops/loops/workflow-generator.yaml:409-465`) hand-lists the
entire allowed evaluator vocabulary plus an English copy of the
`EVALUATOR_REQUIRED_FIELDS` companion-field table:

```
- exit_code — no companion fields
- output_contains — requires `pattern`
- output_numeric — requires `operator` and `target`
- output_json — requires `path`, `operator`, AND `target`
...
```

That prose table drifts silently the moment `EVALUATOR_REQUIRED_FIELDS`
(`scripts/little_loops/fsm/validation/_base.py:45`) changes. FEAT-3328's
gate-completeness lint deliberately does not inspect `prompt` actions (its
settled coverage-gap decision, option (a)), and its option (c) — fix this one
live restatement generatively and file it as its own issue — is this issue.

## Current Behavior

`attach_evaluators`'s prompt carries a hand-maintained copy of the evaluator
type/required-field vocabulary. Nothing checks it against
`EVALUATOR_REQUIRED_FIELDS` / `NON_LLM_EVALUATOR_TYPES`; when the tables
change, the prompt keeps instructing the model with the stale vocabulary, and
defects surface downstream at `validate_artifact` — the exact laundering
pattern FEAT-3328's Summary describes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

The fallback pattern this issue mandates for the generator command's redirect (`> "$DIR/evaluator-vocab.md"`, with a fallback write mirroring `baseline-ref.txt`'s `|| : > "$DIR/evaluator-vocab.md"`, per this section's redirect finding above) makes any generation-time failure (e.g. an import error inside the `python3 -c` body) produce a silently EMPTY `evaluator-vocab.md` unless its stderr is captured somewhere diagnosable.

**Correction (adversarial-review pass):** an earlier draft of this finding proposed routing that failure through this loop's existing `.emit_errors.txt` sink, attributing its write to `emit_artifact`. That attribution was wrong, and the reuse is unsafe. `init` does reset `.emit_errors.txt` at the top of its action (`scripts/little_loops/loops/workflow-generator.yaml:63`), but the file is written by the *next* state, `validate_artifact` — an `action_type: shell` state that tees `ll-loop validate`'s output into it and clears it only on success (`scripts/little_loops/loops/workflow-generator.yaml:598-601`). `emit_artifact` itself is `action_type: prompt` and has no shell action; it only *reads* `.emit_errors.txt` (`:559-561`, "If ... exists and is non-empty, read it first — treat it as the errors from your previous attempt [at emit_artifact] and fix every listed error"). `.emit_errors.txt` is therefore a single-purpose retry-communication channel between `validate_artifact` and `emit_artifact`, and the terminal `diagnose` state reads it under that same attribution (`:880-881`, "emit_artifact could not produce a workflow.yaml that passes ll-loop validate"). Reusing it for a generator-vocabulary failure — which happens in `init`, several states upstream of `emit_artifact` — would leave it non-empty from `init` through every intermediate state until `emit_artifact`'s first invocation, where the prompt would misread an unrelated vocab-generation traceback as its own prior-attempt error on an attempt that never happened, and `diagnose` would misdiagnose the run as an `emit_artifact` failure.

The generator block's failure path must use a dedicated, collision-free signal instead: a new `.evaluator_vocab_errors.txt`, reset by `init` alongside its existing `.emit_errors.txt`/`.intent_errors.txt`/`.scope_violations.txt` resets (`:63-67`) and written only by the generator command's own stderr redirect — never touched by `emit_artifact` or `validate_artifact`. `attach_evaluators` and `diagnose` can then read it without any risk of cross-attribution with the emit/validate retry loop.

## Expected Behavior

The vocabulary the prompt presents is generated from the validator's own
exported tables at run time, so it cannot drift. Per FEAT-3328's option (c)
sketch:

- `init` gains a `python3 -c` block that emits the vocabulary from the tables.
  This sketch reflects the resolved Decision Needed below (Option 2: curated
  exclusion set) and emits BOTH the allowed-type table and the derived
  "Do not use" exclusion list — not the allowed-type table alone:

  ```yaml
  # in init, alongside the existing mkdir/echo block
  python3 -c "
  from little_loops.fsm.validation import EVALUATOR_REQUIRED_FIELDS, NON_LLM_EVALUATOR_TYPES
  EXCLUDED = {'open_question_stall', 'harbor_scorer'}
  for t in sorted(NON_LLM_EVALUATOR_TYPES - EXCLUDED):
      req = EVALUATOR_REQUIRED_FIELDS[t]
      print(f'- {t} — ' + ('no companion fields' if not req else 'requires ' + ', '.join(req)))
  print()
  print('Do not use:')
  for t in sorted(set(EVALUATOR_REQUIRED_FIELDS) - NON_LLM_EVALUATOR_TYPES):
      print(f'- {t}')
  " > "$DIR/evaluator-vocab.md" 2> "$DIR/.evaluator_vocab_errors.txt" \
    || : > "$DIR/evaluator-vocab.md"
  ```

- `attach_evaluators`'s prompt reads `evaluator-vocab.md` (via the run-dir
  path) instead of hand-listing the vocabulary.

This is the import-don't-restate principle applied where an import genuinely
isn't available (a prompt has no import to offer). It must respect the
existing `init` stdout-contract constraint: write to a file, keep the
`case`/`echo` block last.

Note on the sketch's shell variables: FSM shell actions are interpolated
before bash sees them, so any bash `${...}` reference in the real `init`
block must be escaped `$${...}` (e.g. `$${DIR}`) per the loop-authoring
rule — a bare `${DIR}` raises "expected namespace.path" at interpolation
time.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

The sketch's `python3 -c "..." > "$DIR/evaluator-vocab.md"` redirect above only redirects stdout. `init`'s own header comment (`scripts/little_loops/loops/workflow-generator.yaml:54-55`) states the actual convention every other command in that block follows: "Every new command below redirects stdout to a file (or $(...)) and stderr to /dev/null so init's stdout stays exactly one line." That convention's load-bearing requirement is only that stderr never leaks onto init's own stdout (constraint (b): "init's stdout stays exactly one line") — it does not require discarding stderr to `/dev/null` specifically. Per the diagnosability finding in Current Behavior's Codebase Research Findings above, discarding it to `/dev/null` would make a generation-time failure silently invisible, so the real implementation instead redirects stderr to a dedicated file, `$DIR/.evaluator_vocab_errors.txt` (reset by `init` alongside its existing `.emit_errors.txt`/`.intent_errors.txt`/`.scope_violations.txt` resets), with a fallback write mirroring how every existing command in this block degrades — e.g. `git -C "$ROOT" rev-parse HEAD > "$DIR/baseline-ref.txt" 2>/dev/null || : > "$DIR/baseline-ref.txt"`, same file, line 70. This still satisfies the per-command convention (stdout stays exactly one line; stderr never reaches it) while keeping the failure diagnosable instead of discarding it.

The vocabulary that must stop drifting is not only the allowed-type table — it is also the "Do not use" exclusion line, whose current omission of `advisor_consult` the Decision Needed section identifies as a live inaccuracy. That line is generatable from the same import with no new judgment call: `sorted(EVALUATOR_REQUIRED_FIELDS.keys() - NON_LLM_EVALUATOR_TYPES)` evaluates to exactly `advisor_consult`, `comparator`, `contract`, `llm_structured` today (verified against `scripts/little_loops/fsm/validation/_base.py:45-71`), because `NON_LLM_EVALUATOR_TYPES` is itself defined as that same set difference in reverse. The generator block's output must include this derived exclusion list alongside the allowed-type table, so the `advisor_consult` omission is closed by construction rather than needing a hand-fix that could drift again the same way the original list did.

## Decision Needed

**The hand-listed vocabulary is a curated proper subset, not a stale copy.**
The `attach_evaluators` prompt lists **10** types, while
`NON_LLM_EVALUATOR_TYPES` (`_base.py`) has **12** members — the prompt omits
`open_question_stall` and `harbor_scorer`, and its "Do not use" line names
`llm_structured`, `comparator`, and `contract` but omits the fourth excluded
type, `advisor_consult`. Naively generating the list from the table therefore
**widens the offered vocabulary by 2 types**. Options:

1. **Accept the widening** — generate all 12. Defensible: the
   `validate_evaluators` gate (and the terminal validator) already passes all
   12, so the prompt would merely offer what the gates accept.
2. **Keep a curated exclusion set in the generator block** — e.g.
   `sorted(NON_LLM_EVALUATOR_TYPES - {"open_question_stall", "harbor_scorer"})`,
   preserving today's narrower offered vocabulary while still deriving
   required-field text from the table.

Either way, the prompt's prose guidance lines (prefer `output_contains` for
free-text prompt states; the `output_json` all-three-fields warning) must stay
coherent with the generated list, and the proposed generator-block execution
test ("covers every member of `NON_LLM_EVALUATOR_TYPES`") must match the
chosen option — under option 2 it asserts coverage of every *non-excluded*
member instead.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **The two excluded types are excluded for more than staleness — each needs infrastructure the generator's pipeline does not produce.** `EVALUATOR_REQUIRED_FIELDS` lists no required companion fields for either (`"open_question_stall": []`, `"harbor_scorer": []`, `scripts/little_loops/fsm/validation/_base.py:53,57`), so this gap is invisible to a generation pass driven only by that table:
  - `open_question_stall` (`evaluate_open_question_stall`, `scripts/little_loops/fsm/evaluators.py:736-770`) reads a maintained per-round open-question-count history file — nothing in `graph-sketch.yaml`'s generic `name`/`purpose`/`kind` state shape produces or updates that file.
  - `harbor_scorer` (`evaluate_harbor_scorer`, `scripts/little_loops/fsm/evaluators.py:1008`) expects the state's own shell action to run an actual Harbor-format benchmark scorer and emit a float on stdout — a specific external-tool contract, not something a generically-sketched state satisfies.
  - This bears on the option 1 vs. option 2 trade-off above: widening to all 12 (option 1) would offer two types whose *structural* validation passes (no required fields, so `validate_evaluators` and `ll-loop validate` both accept them) but whose evaluators would misbehave against generically-generated state output, unlike the other 10 offered types, which are all general-purpose and require no extra generated infrastructure.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

For machine-visibility: `ll-issues check-decidable ENH-3355`'s enumerable-option probe (`locate_enumerable_options()`, `scripts/little_loops/issue_parser.py:2456`) only recognizes an `### Option A` heading, a `**Option A**` bold-label line, a `1. **Option ...` numbered line, or a `- Option A` bullet — the numbered prose above (`1. **Accept the widening**...`, `2. **Keep a curated exclusion set...`) matches none of the four tiers, and confirmed via a direct run: `ll-issues check-decidable ENH-3355` exits 1 (`OPTIONS_MISSING`) against the issue as it stood before this pass. The same two alternatives restated in canonical bold-label form, so `/ll:decide-issue ENH-3355` and `ll-issues check-decidable` can locate them (this restates, not replaces, the numbered prose above — that prose stays the fuller explanation):

**Option 1**: Accept the widening — generate all 12 members of `NON_LLM_EVALUATOR_TYPES`.

**Option 2**: Keep a curated exclusion set in the generator block — `sorted(NON_LLM_EVALUATOR_TYPES - {"open_question_stall", "harbor_scorer"})`.

> **Selected:** Option 2 — the curated exclusion set. `open_question_stall` and
> `harbor_scorer` need pipeline infrastructure (a maintained open-question-count
> history file; an actual Harbor-format benchmark scorer) that a generically
> sketched state never produces, so they would pass `validate_evaluators`
> structurally while misbehaving at runtime if the LLM selected them — a risk
> Option 1's straight widening would introduce. Option 2 preserves today's
> working 10-type vocabulary, adds only the derived "Do not use" fix
> (`advisor_consult`), and costs one extra set-difference literal over Option 1.

This decision is recorded by `/ll:decide-issue ENH-3355`, which appends a `> **Selected:**` callout beneath the chosen Option block above — that callout, plus `decision_needed: false` in frontmatter (set by `/ll:decide-issue` once it records the callout, per `skills/decide-issue/SKILL.md:275,289,297` — `true` is only the pre-resolution flag `/ll:refine-issue --auto` sets when it deposits an unresolved decision), is the concrete mechanism the Acceptance Criteria's "resolved and recorded" bullet resolves through. **Status as of this pass**: the callout is present above and frontmatter already reads `decision_needed: false` — this bullet is satisfied.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-29.

**Selected**: Option 2 — Keep a curated exclusion set in the generator block

**Reasoning**: `validate_evaluators` (`workflow-generator.yaml:466-500`) imports
`NON_LLM_EVALUATOR_TYPES` directly and would structurally accept all 12 members
including `open_question_stall` and `harbor_scorer`, but codebase research
(`fsm/evaluators.py:736-770`, `:1008`) shows both require infrastructure — a
maintained per-round question-count history file, and an actual Harbor
benchmark scorer emitting a float on stdout — that a generically-sketched
`graph-sketch.yaml` state never produces. Widening to all 12 (Option 1) would
therefore offer two types that pass structural validation but misbehave at
runtime, a landmine the current hand-listed 10-type vocabulary already avoids
by omission. Option 2 keeps that same working boundary while still deriving
the required-field prose from the shared table, closing the `advisor_consult`
"Do not use" omission by construction.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (accept widening) | 2/3 | 3/3 | 3/3 | 1/3 | 9/12 |
| Option 2 (curated exclusion) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Accept-the-widening (Option 1): matches `NON_LLM_EVALUATOR_TYPES` and
  `validate_evaluators` exactly with the simplest possible generator body
  (`sorted(NON_LLM_EVALUATOR_TYPES)`, no exclusion literal), but reintroduces
  two types (`open_question_stall`, `harbor_scorer`) whose evaluators expect
  pipeline output the generator does not produce
  (`fsm/evaluators.py:736-770,1008`) — structurally valid, functionally
  broken if selected.
- Curated-exclusion (Option 2): one extra set-difference literal over the
  widening approach, but preserves the vocabulary boundary the current
  hand-list already enforces (10 types) and avoids the same functional
  landmine, while still closing the `advisor_consult` exclusion-line gap via
  the shared table.

## Program Design

### Types

- `NON_LLM_EVALUATOR_TYPES: frozenset[str]` — existing,
  `scripts/little_loops/fsm/validation/_base.py:66-71`
  (`frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured",
  "comparator", "contract", "advisor_consult"}` — the four excluded types are
  a *derived* set difference, not a separately hand-maintained literal)
- `EVALUATOR_REQUIRED_FIELDS: dict[str, list[str]]` — existing,
  `scripts/little_loops/fsm/validation/_base.py:45-62`

### Signatures

No new Python functions. The design is a shell `python3 -c` block embedded in
`init`'s action string: it iterates `sorted(NON_LLM_EVALUATOR_TYPES)` (or the
curated subset, per the Decision Needed above) and formats each entry against
`EVALUATOR_REQUIRED_FIELDS[t]`.

The Decision Needed above is now resolved to Option 2: the allowed-type loop
iterates `sorted(NON_LLM_EVALUATOR_TYPES - {"open_question_stall",
"harbor_scorer"})`, not the full `NON_LLM_EVALUATOR_TYPES`. The block's
output is not this one loop alone — it must also emit a second, derived line
for the "Do not use" exclusion list: `sorted(EVALUATOR_REQUIRED_FIELDS.keys()
- NON_LLM_EVALUATOR_TYPES)`, which evaluates to `advisor_consult`,
`comparator`, `contract`, `llm_structured` today. Expected Behavior's `python3
-c` sketch above shows only the allowed-type loop; it does not show this
second emit. Both emits belong to the same generator block — the
exclusion-list line is part of this design, not an optional extra, since it
is what closes the `advisor_consult` omission Current Behavior's Codebase
Research Findings and Acceptance Criteria both require closed "by
construction."

### Call Path

`init` -> writes `evaluator-vocab.md` (via a `python3 -c` block reading
`EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` and redirected using
bash's own already-set `$DIR` var — the same variable the existing
mkdir/echo block in `init` uses — never a raw `${context.run_dir}`
interpolation inside the new Python body), also resetting and redirecting
the generator command's stderr to a new dedicated `.evaluator_vocab_errors.txt`
(never `.emit_errors.txt` — see Current Behavior's Codebase Research
Findings for why that file is reserved for the `validate_artifact`<->
`emit_artifact` retry loop) -> `attach_evaluators` reads
`evaluator-vocab.md` via `${captured.run_dir.output}/evaluator-vocab.md`.
The terminal `diagnose` state's file-inspection list (`workflow-generator.yaml:874-878`)
must also be extended to name `evaluator-vocab.md` and
`.evaluator_vocab_errors.txt`, so a run that fails specifically because
vocabulary generation failed leaves `diagnose` able to explain it.

Constraint this corrects: every existing `action_type: prompt` state in this
loop (`capture_intent`, `sketch_state_graph`, `attach_evaluators` itself,
`resolve_routing`, `emit_artifact`, `finalize_await_confirmation`, `diagnose`
— all 7 of the loop's `action_type: prompt` states; `await_confirmation` is
`terminal: true` with no `action_type` key and reads no files, so it is not
a member of this list) reads run-dir files exclusively via
`${captured.run_dir.output}` — never
`${context.run_dir}`, which appears only inside `init` and inside
`action_type: shell` `validate_*` states, always wrapped in
`os.path.abspath(...)` (guarding the double-prefixing hazard `init`'s own
header comment attributes to BUG-2435). `attach_evaluators`'s own current
action already opens with `Read ${captured.run_dir.output}/graph-sketch.yaml.`
— the new `evaluator-vocab.md` read must follow that identical, already-
established variable, not `${context.run_dir}`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Correction — diagnose is not reachable from attach_evaluators/validate_evaluators failures.** Verified via grep of every `diagnose:`/`on_no:` reference in `workflow-generator.yaml`: `diagnose` has exactly three inbound edges — `check_intent_scope`'s `on_no` (line 344), `count_intent_retry`'s `on_no` (line 361), and `count_emit_retry`'s `on_no` (line 624). `validate_evaluators`'s `on_no` goes straight back to `attach_evaluators` (line 500) with no bounded counter — the same unbounded one-shot-window retry shape HARNESS_OPTIMIZATION_GUIDE.md already documents for attach_evaluators/sketch_state_graph/resolve_routing. `workflow-generator.yaml` sets no `on_max_steps` (grepped, absent), so an attach_evaluators<->validate_evaluators cycle that never resolves exhausts `max_steps` (45) and the run terminates via `_finish("max_steps")` without ever visiting `diagnose`. Consequence for this issue's Call Path/Acceptance-Criteria claim that extending diagnose's file-inspection list makes a generator-vocabulary failure "visible to the loop's own terminal failure-triage state": that is only true when the failure additionally trips one of the three existing bounded-retry edges above. On its own, an attach_evaluators/validate_evaluators cycle caused by an empty evaluator-vocab.md never reaches diagnose regardless of what diagnose's file list names. Fully closing this (making diagnose actually reachable from this failure) would require adding a new bounded-retry counter mirroring `count_intent_retry`/`count_emit_retry` and routing its `on_no` to `diagnose` — this would widen the current Scope Boundaries (single loop-YAML edit to init/attach_evaluators/diagnose). Absent that addition, the diagnose-extension AC bullet should be read as "diagnose can explain this failure on the runs where it is also reachable via an existing bounded-retry edge," not as a guarantee that every generator-vocabulary failure reaches diagnose.

**Correction — applied.** An earlier draft of Call Path's prompt-state list named the wrong terminal state (`await_confirmation` instead of `finalize_await_confirmation`) and undercounted by one (6 instead of 7, omitting `diagnose`). Both are now fixed directly in the Call Path text above; this paragraph records the verification trail. `await_confirmation` (`workflow-generator.yaml:860-864`) is `terminal: true` with no `action_type` key at all — it is not an `action_type: prompt` state and reads no files. The state that is actually `action_type: prompt` and reads `${captured.run_dir.output}/workflow.yaml` (line 851) immediately before `await_confirmation` in the chain is `finalize_await_confirmation` (`workflow-generator.yaml:847-859`), reached via `promotion_gate`'s `on_no` on the normal success path — once `validate_artifact` has already passed, `check_shrink_enabled` has run, and `auto_promote != "true"` (line 812: `on_no: finalize_await_confirmation`, inside `promotion_gate`, not `validate_artifact` — `validate_artifact`'s own `on_no`, line 606, goes to `count_emit_retry`, whose `on_no`, line 624, goes to `diagnose`; `validate_artifact`'s retry-exhaustion path never reaches `finalize_await_confirmation`) — and itself transitioning `next: await_confirmation` (line 858). `diagnose` (`workflow-generator.yaml:866-889`) is also `action_type: prompt` and also reads run-dir files exclusively via `${captured.run_dir.output}` ("Diagnose by reading whichever of these exist under `${captured.run_dir.output}/`: ...", lines 874-878) — confirmed by grep, there are 7 `action_type: prompt` states in the file (lines 173, 367, 414, 506, 554, 848, 867), not 6. The corrected 7-member list is `capture_intent, sketch_state_graph, attach_evaluators, resolve_routing, emit_artifact, finalize_await_confirmation, diagnose`.

**Residual manual-curation surface, not eliminated by this issue.** The Option-2 generator block's `EXCLUDED = {'open_question_stall', 'harbor_scorer'}` literal (Expected Behavior sketch; also this section's Signatures) is itself a hand-curated vocabulary exclusion set, not derived from any table — narrower than the 10-item hand-list this issue replaces, but the same class of manually-maintained knowledge one level down. If a future evaluator type requiring pipeline infrastructure the generator doesn't produce is added to `EVALUATOR_REQUIRED_FIELDS`, nothing this issue adds detects that the new type needs to join `EXCLUDED` — the same silent-drift failure mode this issue exists to close can recur. This 2-item literal is also silently exempt from `_validate_gate_completeness`'s own restatement lint (`scripts/little_loops/fsm/validation/meta_rules.py:509`: "A literal is flagged only when it has >=3 members") — a coincidence of size, verified in `meta_rules.py`, not a deliberate design choice recorded anywhere else in this issue. This is an accepted trade-off of the `Decision Needed` section's Option 2 selection (a 2-item manual list traded for the 10-item one being replaced), not a defect for this pass to fix; recorded here so a future reader does not read this issue's title ("...instead of hand-listing it") as a claim that all hand-curation of the vocabulary was eliminated.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Placement constraint for the new generator block, not previously stated.** `init`'s existing action has three regions: (1) the mkdir/reset block (lines 61-67, unconditional), (2) `ROOT=$(git rev-parse --show-toplevel ...)` followed by `if [ -n "$ROOT" ]; then ... else ... fi` (lines 68-162, git-specific — writes `baseline-ref.txt`/`baseline-changed-set.json` with empty-placeholder fallbacks in the `else` branch for non-repo runs), and (3) the `case`/`echo` stdout block (lines 163-166, must stay last per the stdout-contract comment at lines 54-55). The new vocab-generator block has no dependency on `$ROOT` or git at all, and must NOT be nested inside the `if [ -n "$ROOT" ]`/`else` branches — doing so would make `evaluator-vocab.md` never generate on a non-repo run. It must sit in region (1) or between regions (1) and (2), unconditionally, before the `case`/`echo` block. `workflow-generator` explicitly supports and tests a non-repo run mode (`TestCheckIntentScopeShellAction::test_xiii_init_stdout_exactly_one_line_in_non_repo`, `scripts/tests/test_builtin_loops.py:18748`), but that test only asserts `init`'s stdout is exactly one line — it does not check that `evaluator-vocab.md` exists or is non-empty, so an incorrect placement inside the `if` branch would pass every test currently named in this issue's plan. Closing this requires either a new assertion in that non-repo test (or a sibling test) that `evaluator-vocab.md` exists and is non-empty after a non-repo `init` run, not merely relying on the repo-fixture tests (`_setup`/`_run_init`), which never exercise the non-repo path.

## Scope Boundaries

- **In scope**: replacing `attach_evaluators`'s hand-listed vocabulary and
  required-field prose with a generated file sourced from
  `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES`; the `init` generator
  block and its stdout-contract compliance; the workflow-generator test
  coverage for both.
- **Out of scope**: extending FEAT-3328's gate-completeness lint to inspect
  `prompt` actions (FEAT-3328's own settled coverage-gap decision, tracked
  there — not reopened here); changing `EVALUATOR_REQUIRED_FIELDS`/
  `NON_LLM_EVALUATOR_TYPES` themselves; auditing other loop YAMLs for similar
  hand-listed vocabulary drift (single-loop fix only).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Clarification — two changes mandated elsewhere in this issue are not visible in the "In scope" enumeration above, though they are in scope.** Program Design > Call Path, Integration Map > Files to Modify, and an Acceptance Criteria bullet all require extending `diagnose`'s file-inspection list (`workflow-generator.yaml:874-878`) to name `evaluator-vocab.md` and `.evaluator_vocab_errors.txt`; Program Design > Call Path and an Acceptance Criteria bullet also require `init` to reset the new `.evaluator_vocab_errors.txt` alongside its existing `.emit_errors.txt`/`.intent_errors.txt`/`.scope_violations.txt` resets (`workflow-generator.yaml:63-67`). Both are part of the single-loop-YAML fix this issue scopes in ("the `init` generator block and its stdout-contract compliance") and must not be read as excluded because this bullet's enumeration does not name them by file/state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `init` (generator
  block writing `evaluator-vocab.md` and, on failure, `.evaluator_vocab_errors.txt`
  into the run dir via bash's own already-set `$DIR` var, per Program Design
  > Call Path), `attach_evaluators` (prompt reads the file via
  `${captured.run_dir.output}/evaluator-vocab.md` instead of hand-listing),
  and `diagnose` (add `evaluator-vocab.md` and `.evaluator_vocab_errors.txt`
  to its existing file-inspection list, `:874-878`, so a generator-vocabulary
  failure is diagnosable at the terminal state, not just an unattributed
  silent gap)

### Tests
- Repoint `test_attach_evaluators_documents_every_required_field`
  (`TestWorkflowGeneratorLoop`, `scripts/tests/test_builtin_loops.py:18147`)
  at the generated `evaluator-vocab.md` content instead of the removed
  hand-listed prompt table — the retained prompt template still contains
  enough of the old substrings (`output_json`, `path`, `operator`, `target`)
  that this test would otherwise keep passing for the wrong reason — and
  assert `init` emits the vocab file under `${context.run_dir}/` (per-run
  artifact isolation, not bare `.loops/tmp/`)
- A generator-block execution test (reusing the `_run_init` helper on
  `TestCheckIntentScopeShellAction`): run the `python3 -c` body and assert
  its output covers every member of `NON_LLM_EVALUATOR_TYPES -
  {open_question_stall, harbor_scorer}` (the curated Option 2 allowed set)
  plus the derived "Do not use" exclusion list (`advisor_consult`,
  `comparator`, `contract`, `llm_structured`)
- A test asserting `diagnose`'s file-inspection list names
  `evaluator-vocab.md` and `.evaluator_vocab_errors.txt`, mirroring the
  existing one-line substring assertions `test_diagnose_reads_emit_errors_file`
  (`:18214`), `test_diagnose_mentions_intent_retry_files` (`:18313`), and
  `test_diagnose_mentions_both_retry_exhaustion_paths` (`:18318`) — no such
  assertion currently exists
- A test exercising the generator's failure path that asserts
  `.evaluator_vocab_errors.txt` is left non-empty on a generation-time failure
- A negative-assertion test that the removed restatement sites are actually
  gone from `attach_evaluators`'s `action` string: assert `classify`,
  `mcp_result`, `action_stall`, `diff_stall`, and `score_stall` do not appear
  in it (these five appear only in the removed enumerations — the inline
  allowed-vocabulary sentence at `workflow-generator.yaml:420-421`, the
  bullet table at `:433-438`, and the YAML template's "required if" comments
  at `:457-460` — never in the retained `output_contains`/`output_json`
  prose-guidance sentences, so their absence is a safe proxy for all three
  sites being replaced rather than only the bullet table)
- A new assertion in (or sibling to)
  `test_xiii_init_stdout_exactly_one_line_in_non_repo`
  (`TestCheckIntentScopeShellAction`, line 18748) that `evaluator-vocab.md`
  exists and is non-empty after a non-repo `init` run — the existing test
  only checks stdout is one line

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::test_xiii_init_stdout_exactly_one_line_in_repo`
  (line 18710) — existing behavioral test that runs `init`'s full action
  end-to-end via `_run_init` and asserts stdout is exactly one line equal to
  the resolved run_dir path; the new generator block must write only to
  `evaluator-vocab.md` (redirected, per the `init` stdout contract), never to
  stdout, or this test starts failing [Agent finding]
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::test_xiii_init_stdout_exactly_one_line_in_non_repo`
  (line 18719) — same stdout-contract assertion, non-repo case [Agent finding]
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::test_init_resets_emit_errors_and_retry_count`
  (line 18225) — another existing behavioral test that runs `init`'s full
  action and asserts `result.stdout.strip() == str(tmp_path)`; also at risk if
  the generator block leaks any output to stdout [Agent finding]
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::_run_init`
  (line 18446) — the existing helper for invoking `init`'s action via
  `subprocess.run(["bash", "-c", action], ...)` with `${context.run_dir}`
  substituted; the proposed "generator-block execution test" (Acceptance
  Criteria) should reuse this helper rather than reinventing action-invocation
  plumbing [Agent finding]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the gate-completeness rule
  entry (added by FEAT-3328) cites this issue as the tracked remedy for its
  known `prompt`-action coverage gap; update the cross-reference once landed
- `docs/guides/LOOPS_REFERENCE.md:2659` — describes `attach_evaluators` as
  attaching an evaluator "restricted to the same vocabulary `ll-loop
  validate`'s MR-1 accepts," which is already inaccurate (10 offered types vs.
  12 accepted) and stays inaccurate by design under the recorded Option 2
  decision, which deliberately keeps that narrower boundary; update to state
  the vocabulary is generated but intentionally narrower than the full
  validator-accepted set

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Existing shell-side precedent for the same import-don't-restate rule**: `validate_evaluators` (`scripts/little_loops/loops/workflow-generator.yaml:466-500`), the very next state after `attach_evaluators`, already imports `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` directly (`from little_loops.fsm.validation import (...)`, lines 479-483) inside its `action_type: shell` python3 heredoc, with its own comment stating the drift-proofing rationale nearly identical to this issue's Summary. `attach_evaluators` cannot take the same direct-import route because it is `action_type: prompt` — a prompt action has no Python import available to it, which is exactly why this issue's file-based route (generate in `init`, read via `${captured.run_dir.output}` in the prompt) is the right shape rather than a shortcut around the simpler import.
- **The file-written-in-a-shell-state / read-by-a-later-prompt convention is already in use in this same loop**: `attach_evaluators`'s own action already opens with `Read ${captured.run_dir.output}/graph-sketch.yaml.` — a shell/init-written artifact consumed by a later prompt state through the `captured.run_dir.output` interpolation (`init`'s `capture: run_dir`, `workflow-generator.yaml:167`). The proposed `evaluator-vocab.md` read follows this identical, already-established shape; no new mechanism needs to be introduced.
- **An existing test inspects `attach_evaluators`'s prompt text directly and will need explicit rework, not just extension**: `test_attach_evaluators_documents_every_required_field` (`scripts/tests/test_builtin_loops.py:18118-18141`) currently computes `offered = [t for t in NON_LLM_EVALUATOR_TYPES if t in action]` against the prompt's raw `action` string, then asserts every required field name of every offered type is a substring of that same `action` string. Once the vocabulary/required-field text moves out of the prompt into a generated file, none of those substrings will be present in `action` any more and this test's assertions go stale — it needs to be pointed at the `init` generator's output (or its python3 body) rather than silently broken or deleted.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

scripts/tests/data/loop_interpolation_baseline.json + `TestInterpSweepBaseline::test_completeness_guard` (`scripts/tests/test_builtin_loops.py:19236`, backed by `scan_corpus` in `scripts/little_loops/fsm/interp_sweep.py`) is an exact-match corpus gate over every `${context.*}`/`${captured.*}`/`${prev.*}` reference embedded inside `python3 -c`/heredoc bodies in shell actions across all built-in loops (EPIC-3336). `init` currently has zero entries for it in the baseline — its existing action contains no such embedded interpolation site. As sketched (reusing the bash `$DIR` var already set earlier in `init`, not a `${context.run_dir}` interpolation inside the new Python body — see Program Design > Call Path), the new generator block introduces no new site and needs no baseline update. If the real implementation instead interpolates `${context.run_dir}` (or any `${captured.*}`/`${prev.*}` var) directly into the new Python body, that is a new, un-baselined `(file, state, var, class)` tuple and `test_completeness_guard` fails until `loop_interpolation_baseline.json` is updated in the same change.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

Correction to the wire-issue findings above: `_run_init` (line 18446), `test_xiii_init_stdout_exactly_one_line_in_repo` (line 18710), and `test_xiii_init_stdout_exactly_one_line_in_non_repo` (line 18719) are methods of `TestCheckIntentScopeShellAction` (`scripts/tests/test_builtin_loops.py:18423-18785`; FEAT-3332's `check_intent_scope`-gate test class, which sets `LOOP_FILE = BUILTIN_LOOPS_DIR / "workflow-generator.yaml"` and drives `init`'s full action through that same `_run_init` helper) — not `TestWorkflowGeneratorLoop` (`scripts/tests/test_builtin_loops.py:17899-18422`). Only `test_init_resets_emit_errors_and_retry_count` (line 18225) is correctly attributed to `TestWorkflowGeneratorLoop`; verified directly: `grep -n "^class Test" scripts/tests/test_builtin_loops.py` shows `TestWorkflowGeneratorLoop` ending at line 18422, immediately followed by `class TestCheckIntentScopeShellAction:` at 18423. An implementer following the wiring bullets literally would look for `_run_init` inside `TestWorkflowGeneratorLoop` and not find it; `TestCheckIntentScopeShellAction` also carries the `_init_repo`/`_setup` git-fixture helpers (lines 18437, 18465) the proposed generator-block execution test would need alongside `_run_init`.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Line numbers cited in this section's Tests/wiring bullets have drifted since the prior refine pass, due to FEAT-3328 landing (commit `1445fd3e4`) and inserting its own gate-completeness lint tests earlier in the same file. Current, re-verified locations in `scripts/tests/test_builtin_loops.py`:
  - `class TestWorkflowGeneratorLoop:` now starts at line 17928 (was 17899) and still ends immediately before `class TestCheckIntentScopeShellAction:`, now at line 18452 (was 18423) — the class-attribution correction from the earlier wiring pass (`_run_init`, the two `test_xiii_init_stdout_exactly_one_line_in_*` tests belong to `TestCheckIntentScopeShellAction`, not `TestWorkflowGeneratorLoop`) still holds.
  - `test_attach_evaluators_documents_every_required_field` — now at line 18147 (was 18118); content unchanged, still asserts every offered type's required fields are named as substrings of `attach_evaluators`'s `action` string.
  - `test_init_resets_emit_errors_and_retry_count` — now at line 18254 (was 18225).
  - `_run_init` — now at line 18475 (was 18446), still inside `TestCheckIntentScopeShellAction`.
  - `test_xiii_init_stdout_exactly_one_line_in_repo` — now at line 18739 (was 18710).
  - `test_xiii_init_stdout_exactly_one_line_in_non_repo` — now at line 18748 (was 18719).
  - `TestInterpSweepBaseline::test_completeness_guard` — now at line 19267 (was 19236).
  None of these tests' bodies changed in a way that affects this issue's plan — only their line offsets moved. Re-verify line numbers again before implementing if further commits land on `scripts/tests/test_builtin_loops.py` in the meantime.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Correction — the prior correction paragraph's line numbers are themselves stale.** Re-verified against the current tree (this pass): `_init_repo` (inside `TestCheckIntentScopeShellAction`) is at line 18466 and `_setup` is at line 18494 — not 18437/18465 as the earlier correction paragraph in this section states. `TestCheckIntentScopeShellAction` runs from line 18452 through line 18814 (immediately before `class TestEnh3347RouterInjection:` at line 18815) — not `18423-18785`. `TestWorkflowGeneratorLoop` starts at line 17928 and ends immediately before `TestCheckIntentScopeShellAction` at 18452, consistent with this section's most recent "re-verified locations" paragraph, which already corrected every other citation in this section but did not revisit this one. Re-verify again before implementing if further commits land on `scripts/tests/test_builtin_loops.py` in the meantime — this is the second time in this section's history that a "re-verify before implementing" note has itself gone stale before being acted on.

**Coupling risk: `test_check_intent_scope_matched_pair_byte_identical` is at risk from this issue's edit to `init`'s action and is not currently listed here.** `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::test_check_intent_scope_matched_pair_byte_identical` (line 18075 — this test is a method of `TestWorkflowGeneratorLoop`, which spans 17928-18452; the earlier draft of this finding misattributed it to `TestCheckIntentScopeShellAction`, which starts at 18452, immediately after) extracts `init`'s python3 body with `re.compile(r"python3 -c '\n(.*?)\n *' ", re.S)` via `pattern.search(init_action)` — a leftmost match — and asserts it is byte-identical to `check_intent_scope`'s own single-quoted `python3 -c '...'` body (FEAT-3332 requirement (c)). `init` currently contains exactly one `python3 -c '...'` block (the single-quoted baseline changed-set script). Two constraints on the new vocab-generator block follow directly, neither stated elsewhere in this issue: (1) it must use double quotes (`python3 -c "..."`), not single quotes — required regardless of this test, since the generator body itself contains single-quoted Python string literals (`'open_question_stall'`, `'harbor_scorer'`, `'no companion fields'`) that would prematurely terminate a bash single-quoted wrapper; a double-quoted block does not match this test's single-quote-anchored pattern, so the test is unaffected as long as double quotes are used. (2) If the new block were instead single-quoted, `pattern.search`'s leftmost-match semantics mean inserting it before the existing baseline block in `init`'s action string would make the test extract the new block's body instead of the baseline's, silently miscomparing it against `check_intent_scope` and failing this test — so quoting choice and insertion position both matter, not quoting alone.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**A second documentation file also needs updating, not only `HARNESS_OPTIMIZATION_GUIDE.md`.** `docs/guides/LOOPS_REFERENCE.md:2659` describes `attach_evaluators` as attaching "a non-LLM evaluator per state, restricted to the same vocabulary `ll-loop validate`'s MR-1 accepts." That claim is already inaccurate today — the hand-listed prompt offers 10 types while `NON_LLM_EVALUATOR_TYPES`/`validate_evaluators`/`ll-loop validate` accept 12 — and this issue's `Decision Needed` section resolves to Option 2 specifically to *keep* that narrower 10-type boundary permanently (excluding `open_question_stall`, `harbor_scorer`), deliberately preserving the mismatch this doc's prose denies. This line should be updated alongside the `HARNESS_OPTIMIZATION_GUIDE.md` cross-reference to state the vocabulary is generated but intentionally narrower than the full validator-accepted set, not merely "restricted to the same vocabulary" the validator accepts.

**No test currently enforces the `diagnose` file-inspection-list extension mandated elsewhere in this issue.** The exact assertion shape already exists in the suite as precedent — `test_diagnose_reads_emit_errors_file` (`scripts/tests/test_builtin_loops.py:18214`), `test_diagnose_mentions_intent_retry_files` (`:18313`), and `test_diagnose_mentions_both_retry_exhaustion_paths` (`:18318`) are each a one-line substring assertion on `diagnose`'s action text for a specific filename — but no sibling assertion for `evaluator-vocab.md`/`.evaluator_vocab_errors.txt` is listed under this issue's Tests. Without one, an implementer can skip editing `diagnose` entirely and no test in this issue's own plan will fail.

## Acceptance Criteria

- [x] The Decision Needed above is resolved and recorded in this issue
      (widen to all 12 vs. curated exclusion set) before the prompt/generator
      edits land.
- [x] `init` gains a generator block, placed in the unconditional
      pre-`$ROOT` region of its action (or between it and the git-conditional
      `if [ -n "$ROOT" ]` block) and never nested inside that block, so it
      also runs on non-repo runs, that writes `evaluator-vocab.md` into the
      run dir via bash's own already-set `$DIR` var — never a raw
      `${context.run_dir}` interpolation inside the new Python body, per
      Program Design > Call Path — derived from `NON_LLM_EVALUATOR_TYPES` /
      `EVALUATOR_REQUIRED_FIELDS`, minus the curated exclusion set
      `{open_question_stall, harbor_scorer}` per the recorded Option 2
      decision, respecting the `init` stdout contract (write to a file;
      `case`/`echo` block stays last).
- [x] `attach_evaluators`'s prompt reads the generated vocab file instead of
      hand-listing the type/required-field table, and its remaining prose
      guidance (prefer `output_contains`; `output_json` field warnings) stays
      coherent with the generated list. "Hand-listing" covers ALL THREE
      restatement sites in the current action, not only the bullet table:
      (1) the inline allowed-vocabulary sentence
      (`workflow-generator.yaml:420-421`) and the "Do not use:
      llm_structured, comparator, or contract" sentence (`:425-427`) — the
      very line whose `advisor_consult` omission Decision Needed identifies;
      (2) the bullet table (`:433-438`); (3) the YAML example template's
      per-field "required if" comments (`:457-460`), which restate the
      required-fields mapping a fourth time and drift identically. Sites (1)
      and (3) are replaced by references to the generated file (the template
      comments genericized to "include exactly the companion fields
      evaluator-vocab.md lists for the chosen type"), not left standing as
      residual drift channels.
- [x] A negative-assertion test proves the removed enumerations are gone:
      type names that appear ONLY in the removed restatement sites and not in
      the retained prose-guidance sentences — `classify`, `mcp_result`,
      `action_stall`, `diff_stall`, `score_stall` — are asserted absent from
      `attach_evaluators`'s `action` string after the edit. Without this, an
      implementer can replace only the bullet table, leave sites (1) and (3)
      as live drift channels, and every test in this plan still passes.
- [x] `test_attach_evaluators_documents_every_required_field`
      (`TestWorkflowGeneratorLoop`, `scripts/tests/test_builtin_loops.py:18147`)
      is repointed at the generated `evaluator-vocab.md` content instead of
      the removed hand-listed prompt table — the retained prompt template
      otherwise still contains enough of the old substrings (`output_json`,
      `path`, `operator`, `target`) to keep passing for the wrong reason —
      and asserts `init` emits the vocab file under `${context.run_dir}/`
      (per-run artifact isolation, not bare `.loops/tmp/`).
- [x] A generator-block execution test runs the generator body and asserts
      its output covers every member of `NON_LLM_EVALUATOR_TYPES -
      {open_question_stall, harbor_scorer}` (the curated allowed set per the
      recorded Option 2 decision) and also covers the derived "Do not use"
      exclusion list (`advisor_consult`, `comparator`, `contract`,
      `llm_structured`).
- [x] `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml`
      passes with no new violations.
- [x] FEAT-3328's gate-completeness guide entry's ENH-3355 cross-reference in
      `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:117` is updated from
      "tracked separately as ENH-3355" to reflect this issue as resolved.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- [x] The concrete mechanism for the first bullet's "resolved and recorded": `ll-issues check-decidable ENH-3355` exits 0 against the machine-visible `**Option 1**`/`**Option 2**` blocks under Decision Needed, `/ll:decide-issue ENH-3355` has appended a `> **Selected:**` callout beneath the chosen option, and `decision_needed` is `false` in frontmatter (set by `/ll:decide-issue` on resolution — `true` is only the pre-resolution flag a refine pass sets while the decision is still open, per `skills/decide-issue/SKILL.md:275,289,297`). **Status as of this pass**: all three hold — frontmatter reads `decision_needed: false` and the `> **Selected:**` callout is present under Decision Needed — this bullet is satisfied.
- [x] The generator's output includes the derived "Do not use" exclusion list — `sorted(EVALUATOR_REQUIRED_FIELDS.keys() - NON_LLM_EVALUATOR_TYPES)` — alongside the allowed-type table, so the current hand-listed line's `advisor_consult` omission (identified in Decision Needed) is closed by construction; this is the concrete check for the third bullet's "stays coherent with the generated list."
- [x] If the real generator block interpolates any `${context.*}`/`${captured.*}`/`${prev.*}` var directly into the new `python3 -c` Python body (rather than reusing bash's own already-set `$DIR`), `scripts/tests/data/loop_interpolation_baseline.json` is updated in the same change and `TestInterpSweepBaseline::test_completeness_guard` (`scripts/tests/test_builtin_loops.py:19267` — re-verified this pass; was 19236) passes.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- [x] The generator block's failure path is diagnosable, not silent: on a
      generation-time failure (e.g. an import error in the `python3 -c`
      body), the run surfaces that failure in a dedicated
      `.evaluator_vocab_errors.txt` file, reset by `init` alongside its
      existing `.emit_errors.txt`/`.intent_errors.txt`/`.scope_violations.txt`
      resets and written only by the generator command's own stderr
      redirect — never `.emit_errors.txt` itself, which is reserved for the
      `validate_artifact`<->`emit_artifact` retry loop (see Current
      Behavior's Codebase Research Findings for why reusing it would be
      unsafe) — rather than only falling back to a silently empty
      `evaluator-vocab.md`; a test exercises the failure path and asserts
      `.evaluator_vocab_errors.txt` is left non-empty.
- [x] `diagnose`'s file-inspection list
      (`scripts/little_loops/loops/workflow-generator.yaml:874-878`) is
      extended to name `evaluator-vocab.md` and
      `.evaluator_vocab_errors.txt`, so a generation-time failure is visible
      to the loop's own terminal failure-triage state, not just written to a
      file nothing reads.
      > ⚠ Superseded — visibility holds only on runs that also trip one of
      > `diagnose`'s 3 existing bounded-retry edges (`check_intent_scope`,
      > `count_intent_retry`, `count_emit_retry`); an attach_evaluators /
      > validate_evaluators cycle alone never reaches `diagnose` regardless
      > of its file list — see the "Scope correction" finding below.
- [x] The concrete check for the third bullet's "stays coherent with the
      generated list" prose-guidance half: `attach_evaluators`'s action
      string still contains the `output_contains` preference sentence
      ("Prefer `output_contains` for a \"kind: prompt\" state that emits
      free text") and the `output_json` three-field warning ("you MUST
      supply all three fields") after the hand-listed vocabulary/
      required-field table is replaced by the generated-file read — a test
      asserts both substrings remain present in `action`, the same
      assertion shape `test_attach_evaluators_documents_every_required_field`
      (`scripts/tests/test_builtin_loops.py:18147` — re-verified this pass;
      was 18118) already uses for the table this issue removes.
- [x] Concrete redefinition for the seventh bullet (superseded below): as of
      this pass, FEAT-3328 is `status: open` and
      `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` contains no
      gate-completeness rule entry and no cross-reference to ENH-3355
      (grepped `FEAT-3328`/`gate-completeness`/`ENH-3355` in that file: one
      unrelated `FEAT-3328` mention at line 675, nothing else). Treat the
      seventh bullet as not-yet-checkable until FEAT-3328 lands a
      gate-completeness guide entry that names ENH-3355; at that point
      "resolved" means that entry's ENH-3355 cross-reference line no longer
      carries open/pending/tracked language — the concrete marker to check
      for, once the entry exists.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- The seventh bullet's premise has changed since the last pass: FEAT-3328 is now `status: done` (commit `1445fd3e4`, "feat(fsm): gate-completeness lint for restated validator rule tables" — `_validate_gate_completeness` landed in `scripts/little_loops/fsm/validation/meta_rules.py`), and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` now carries a **gate-completeness** guide-rule row (currently an uncommitted working-tree change) whose Symptom cell states: "a rule table restated in *prose* inside a `prompt` action is invisible to this rule (tracked separately as ENH-3355)". The bullet's "not-yet-checkable until FEAT-3328 lands a guide entry" precondition from the prior pass no longer holds — it is now checkable, and the check result is that the bullet is still **unresolved**: "tracked separately as ENH-3355" is exactly the pending/tracked language the bullet is watching for, not "resolved". The annotation that previously stood beneath this bullet (noting FEAT-3328 was still open and no guide entry existed) has been removed as no longer accurate (this pass's bounded marker-removal right) rather than left standing on a now-false premise.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Scope correction — the failure-path test only proves the write, not diagnose's reachability.** The AC bullet's test ("a test exercises the failure path and asserts `.evaluator_vocab_errors.txt` is left non-empty") verifies only that the stderr redirect lands in the right file; it says nothing about whether any run ever reaches a state that reads that file. Per the reachability finding recorded under Program Design's Codebase Research Findings, `diagnose` is unreachable from an attach_evaluators/validate_evaluators failure alone (`validate_evaluators`'s `on_no` cycles back to `attach_evaluators` with no bounded counter and no `on_max_steps` fallback to `diagnose`) — so the sibling AC bullet's language ("visible to the loop's own terminal failure-triage state") is a strictly stronger claim than this test checks. A fixer implementing only the literal text of these two bullets can pass both while leaving the reachability gap open. Treat "visible to the loop's own terminal failure-triage state" as scoped to runs that also trip one of `diagnose`'s three existing bounded-retry edges (`check_intent_scope`, `count_intent_retry`, `count_emit_retry` — `workflow-generator.yaml:344,361,624`), not as holding for every generator-vocabulary failure, unless a bounded-retry counter routing attach_evaluators/validate_evaluators failures to `diagnose` is separately added.

## Impact

- **Priority**: P4 — no current mismatch between prompt and tables; this
  removes a silent-drift channel rather than fixing a live defect
- **Effort**: Small — one loop YAML edit (two states) plus tests
- **Risk**: Low — generated text replaces equivalent hand-written text;
  `ll-loop validate` and the existing workflow-generator tests gate regressions
- **Breaking Change**: No

## Notes

Split out of FEAT-3328 per its settled coverage-gap decision ("(c) Fix the
live drift generatively, then re-price this rule — split into its own issue").
Independent of FEAT-3328: neither needs to land first, and FEAT-3328's AC #3
(zero violations) is unaffected either way since the restatement lives in a
`prompt` action its rule does not inspect.

Source: `postmortems/workflow-generator-output-json-gate-gap.md`;
FEAT-3328 § Known coverage gap.

## Resolution

Implemented per the recorded Option 2 decision. `init` gained an
unconditional generator block (before the `$ROOT` git-conditional region)
that imports `NON_LLM_EVALUATOR_TYPES`/`EVALUATOR_REQUIRED_FIELDS` and
writes `evaluator-vocab.md` (allowed types + required fields) and the
derived "Do not use" exclusion list into the run dir, with stderr captured
to a dedicated `.evaluator_vocab_errors.txt` (reset by `init`, never
`.emit_errors.txt`) and a truncating fallback on failure so `init`'s
one-line stdout contract holds either way. `attach_evaluators` now reads
`evaluator-vocab.md` instead of hand-listing the vocabulary/required-field
table across all three prior restatement sites (inline sentence, bullet
table, YAML template comments); its retained prose guidance
(`output_contains` preference, `output_json` three-field warning) is
unchanged. `diagnose`'s file-inspection list now names both new artifacts.

Verified: `ll-loop validate` passes with no new violations; the generator
block was executed directly and its output matches the curated 10-type
allowed vocabulary plus the 4-type exclusion list exactly;
`python -m pytest scripts/tests/` passes except 4 pre-existing failures
unrelated to this change (README/BUG-3179 drift, decision-rules corpus,
subprocess_utils guillotine-prompt test, verify_evidence repo gate — none
touch `workflow-generator.yaml` or `test_builtin_loops.py`). Both
documentation cross-references (`HARNESS_OPTIMIZATION_GUIDE.md`,
`LOOPS_REFERENCE.md`) were updated to reflect the generated, intentionally
narrower vocabulary.

## Status

**Open** | Created: 2026-08-28 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-08-29T22:48:03 - `f7c14658-bb40-440b-81af-f3a16fcf645e.jsonl`
- `/ll:confidence-check` - 2026-08-29T22:28:28 - `6ccd6e6e-388b-438a-9b4d-590811851d9d.jsonl`
- `/ll:confidence-check` - 2026-08-29T21:51:31 - `50c46bf0-423e-4388-a12d-c46c8485daa9.jsonl`
- `/ll:reconcile-issue` - 2026-08-29T21:47:59 - `c9c1c0a3-4ed0-4475-ae26-5a077ef3a172.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:43:51 - `56a8dea0-aa3e-460a-b690-91edf1aee623.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:34:10 - `095cbd0a-db00-46a3-adc4-bd813f5370ea.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:21:26 - `2c13c55a-19b4-426e-82a9-8daecd5791a5.jsonl`
- `/ll:verify-issues` - 2026-08-29T19:13:35 - `fedec3ab-76ac-4b03-acac-d98d32d4349a.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:08:20 - `0ffc86a7-1497-4d98-b701-beefa90422f4.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:04:18 - `1af8753e-4f9c-4ef2-97a5-4e6f8d5943ea.jsonl`
- `/ll:refine-issue` - 2026-08-29T18:45:12 - `237f015b-641f-4613-8e7e-3269af82a4c8.jsonl`
- `/ll:confidence-check` - 2026-08-29T17:12:27 - `ae75495c-b3b3-484c-ab1b-67f636f84f94.jsonl`
- `/ll:verify-issues` - 2026-08-29T17:08:23 - `ae75495c-b3b3-484c-ab1b-67f636f84f94.jsonl`
- `/ll:refine-issue` - 2026-08-29T17:03:11 - `349c7330-13ab-43c2-bdc2-9bd5e349f81e.jsonl`
- `/ll:decide-issue` - 2026-08-29T16:53:52 - `349c7330-13ab-43c2-bdc2-9bd5e349f81e.jsonl`
- `/ll:confidence-check` - 2026-08-29T16:48:50 - `1a3ef653-fb3c-418b-9f59-cf436fe3c24c.jsonl`
- `/ll:verify-issues` - 2026-08-29T16:44:28 - `8cef6ec1-5cb0-4cb4-8f7b-ed8c1bc53873.jsonl`
- `/ll:refine-issue` - 2026-08-29T16:39:19 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:confidence-check` - 2026-08-29T16:32:21 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:verify-issues` - 2026-08-29T16:27:38 - `2b9cf0aa-17fa-4c56-a0c2-6a6f4f822dae.jsonl`
- `/ll:wire-issue` - 2026-08-29T16:21:14 - `7e3e461d-c448-4f5e-b605-da4742b390e0.jsonl`
- `/ll:refine-issue` - 2026-08-29T16:14:49 - `b7bcafc8-2a6b-479f-8e57-018d577b3945.jsonl`
- `/ll:format-issue` - 2026-08-29T16:07:26 - `980cbc7a-2998-4ff5-83ab-7e00435d03b9.jsonl`
