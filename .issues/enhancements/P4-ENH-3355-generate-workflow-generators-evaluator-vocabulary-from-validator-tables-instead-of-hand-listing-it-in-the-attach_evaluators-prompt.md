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
---

# ENH-3355: Generate workflow-generator's evaluator vocabulary from validator tables instead of hand-listing it in the attach_evaluators prompt

## Summary

`workflow-generator.yaml`'s `attach_evaluators` state (`action_type: prompt`,
`scripts/little_loops/loops/workflow-generator.yaml:165-181`) hand-lists the
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
