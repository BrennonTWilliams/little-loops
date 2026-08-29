---
id: ENH-3355
type: ENH
title: Generate workflow-generator's evaluator vocabulary from validator tables instead
  of hand-listing it in the attach_evaluators prompt
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T22:35:07Z'
labels:
- workflow-generator
- drift
- feat-3328-followup
relates_to:
- FEAT-3328
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

## Expected Behavior

The vocabulary the prompt presents is generated from the validator's own
exported tables at run time, so it cannot drift. Per FEAT-3328's option (c)
sketch:

- `init` gains a `python3 -c` block that emits the vocabulary from the tables:

  ```yaml
  # in init, alongside the existing mkdir/echo block
  python3 -c "
  from little_loops.fsm.validation import EVALUATOR_REQUIRED_FIELDS, NON_LLM_EVALUATOR_TYPES
  for t in sorted(NON_LLM_EVALUATOR_TYPES):
      req = EVALUATOR_REQUIRED_FIELDS[t]
      print(f'- {t} — ' + ('no companion fields' if not req else 'requires ' + ', '.join(req)))
  " > "$DIR/evaluator-vocab.md"
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

## Program Design

### Types

- `NON_LLM_EVALUATOR_TYPES: set[str]` — existing, `scripts/little_loops/fsm/validation/_base.py`
- `EVALUATOR_REQUIRED_FIELDS: dict[str, list[str]]` — existing, same module

### Signatures

No new Python functions. The design is a shell `python3 -c` block embedded in
`init`'s action string: it iterates `sorted(NON_LLM_EVALUATOR_TYPES)` (or the
curated subset, per the Decision Needed above) and formats each entry against
`EVALUATOR_REQUIRED_FIELDS[t]`.

### Call Path

`init` -> writes `evaluator-vocab.md` (via a `python3 -c` block reading
`EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES`) -> `attach_evaluators`
reads that file from `${context.run_dir}/evaluator-vocab.md`

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `init` (generator
  block writing `${context.run_dir}/evaluator-vocab.md`) and
  `attach_evaluators` (prompt reads the file instead of hand-listing)

### Tests
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop` — extend to
  assert the prompt no longer hand-lists the required-field table and that
  `init` emits the vocab file under `${context.run_dir}/` (per-run artifact
  isolation, not bare `.loops/tmp/`)
- A generator-block execution test: run the `python3 -c` body and assert its
  output covers every member of `NON_LLM_EVALUATOR_TYPES`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the gate-completeness rule
  entry (added by FEAT-3328) cites this issue as the tracked remedy for its
  known `prompt`-action coverage gap; update the cross-reference once landed

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Existing shell-side precedent for the same import-don't-restate rule**: `validate_evaluators` (`scripts/little_loops/loops/workflow-generator.yaml:466-500`), the very next state after `attach_evaluators`, already imports `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` directly (`from little_loops.fsm.validation import (...)`, lines 479-483) inside its `action_type: shell` python3 heredoc, with its own comment stating the drift-proofing rationale nearly identical to this issue's Summary. `attach_evaluators` cannot take the same direct-import route because it is `action_type: prompt` — a prompt action has no Python import available to it, which is exactly why this issue's file-based route (generate in `init`, read via `${captured.run_dir.output}` in the prompt) is the right shape rather than a shortcut around the simpler import.
- **The file-written-in-a-shell-state / read-by-a-later-prompt convention is already in use in this same loop**: `attach_evaluators`'s own action already opens with `Read ${captured.run_dir.output}/graph-sketch.yaml.` — a shell/init-written artifact consumed by a later prompt state through the `captured.run_dir.output` interpolation (`init`'s `capture: run_dir`, `workflow-generator.yaml:167`). The proposed `evaluator-vocab.md` read follows this identical, already-established shape; no new mechanism needs to be introduced.
- **An existing test inspects `attach_evaluators`'s prompt text directly and will need explicit rework, not just extension**: `test_attach_evaluators_documents_every_required_field` (`scripts/tests/test_builtin_loops.py:18118-18141`) currently computes `offered = [t for t in NON_LLM_EVALUATOR_TYPES if t in action]` against the prompt's raw `action` string, then asserts every required field name of every offered type is a substring of that same `action` string. Once the vocabulary/required-field text moves out of the prompt into a generated file, none of those substrings will be present in `action` any more and this test's assertions go stale — it needs to be pointed at the `init` generator's output (or its python3 body) rather than silently broken or deleted.

## Acceptance Criteria

- [ ] The Decision Needed above is resolved and recorded in this issue
      (widen to all 12 vs. curated exclusion set) before the prompt/generator
      edits land.
- [ ] `init` gains a generator block that writes
      `${context.run_dir}/evaluator-vocab.md` derived from
      `NON_LLM_EVALUATOR_TYPES` / `EVALUATOR_REQUIRED_FIELDS` (minus the
      curated exclusions, if option 2 is chosen), respecting the `init`
      stdout contract (write to a file; `case`/`echo` block stays last) and
      escaping bash interpolation as `$${...}`.
- [ ] `attach_evaluators`'s prompt reads the generated vocab file instead of
      hand-listing the type/required-field table, and its remaining prose
      guidance (prefer `output_contains`; `output_json` field warnings) stays
      coherent with the generated list.
- [ ] `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop` is
      extended: the prompt no longer hand-lists the required-field table, and
      `init` emits the vocab file under `${context.run_dir}/` (per-run
      artifact isolation, not bare `.loops/tmp/`).
- [ ] A generator-block execution test runs the generator body and asserts
      its output covers every member of `NON_LLM_EVALUATOR_TYPES` (option 1)
      or every non-excluded member (option 2), per the recorded decision.
- [ ] `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml`
      passes with no new violations.
- [ ] If FEAT-3328's gate-completeness guide entry has landed, its
      cross-reference to this issue in
      `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` is updated to "resolved".

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

## Status

**Open** | Created: 2026-08-28 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-08-29T16:14:49 - `b7bcafc8-2a6b-479f-8e57-018d577b3945.jsonl`
- `/ll:format-issue` - 2026-08-29T16:07:26 - `980cbc7a-2998-4ff5-83ab-7e00435d03b9.jsonl`
