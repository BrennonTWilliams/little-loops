---
id: ENH-2895
type: ENH
priority: P2
status: open
captured_at: "2026-07-28T22:13:33Z"
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to: [BUG-2893, BUG-2894, ENH-2896]
---

# ENH-2895: Support an `evaluate.key` field on the output_numeric evaluator

## Summary

Add a `key: str | None` field to `EvaluateConfig` and honour it in
`evaluate_output_numeric`: when set, extract the numeric value from a
`<key>=<number>` field in the action's stdout instead of calling
`float(output.strip())` on the whole output.

Two built-in loops (`docs-sync.yaml`, `oracles/code-run-gate.yaml`) already declare
`key:` on `output_numeric` evaluators, written by independent authors who each assumed
the field did exactly this. It does not exist; it is silently dropped at load. Both
loops are broken as a result (BUG-2893, BUG-2894).

## Motivation

The pattern the field addresses is ubiquitous in shell states: a state runs a command,
computes a metric, and echoes a self-describing `metric=value` line so the run log stays
readable. Today the only ways to feed that value to `output_numeric` are:

- echo a bare, unlabelled number (loses the run-log legibility), or
- restructure the shell to emit JSON and switch to `output_json` + `path:` (more shell
  churn inside `$${}`-escaped blocks — precisely where MR-7/MR-9 escaping bugs breed).

That two authors independently reached for `key:` is direct evidence it is the
discoverable API. Implementing it fixes both existing loops with no shell surgery and
removes the sharp edge for future authors.

## Current Pain Point / Current Behavior

`evaluate_output_numeric` (`scripts/little_loops/fsm/evaluators.py`):

```python
    try:
        value = float(output.strip())
    except ValueError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Cannot parse as number: {output[:100]}"},
        )
```

Any labelled output produces `verdict="error"`. `EvaluateConfig`
(`scripts/little_loops/fsm/schema.py`) has no `key` field, and `from_dict` discards it
silently, so the loop author gets no signal that their YAML is inert — not at load,
not at `ll-loop validate`, and not at runtime beyond a generic parse error.

## Expected Behavior / API

```yaml
    evaluate:
      type: output_numeric
      key: pass_rate
      operator: "ge"
      target: 0.95
```

Against stdout:

```
running tests...
exit_code=0
pass_rate=0.99
```

→ extracts `0.99`, compares `0.99 >= 0.95`, returns `verdict="yes"`.

Semantics to settle during implementation:

- **Match rule**: regex on `^\s*<key>\s*=\s*([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s*$`,
  or a looser in-line match permitting `exit_code=0 pass_rate=0.99` on one line.
  Recommend supporting the in-line form — `code-run-gate` emits exactly that shape.
- **Multiple matches**: take the **last** match. Shell states append progressively;
  the last write is the current value. Document this explicitly.
- **No match**: `verdict="error"` with a `details["error"]` naming the missing key
  (`"key 'pass_rate' not found in output"`) — distinguishable from a parse failure.
- **Key not set**: unchanged `float(output.strip())` behaviour. Fully backward compatible.
- **Escaping**: `re.escape` the key.

## Proposed Solution

1. `EvaluateConfig`: add `key: str | None = None`, wire into `to_dict` (emit when not
   None) and `from_dict` (`data.get("key")`), and document it in the class docstring's
   Attributes block.
2. `evaluate_output_numeric`: add a `key: str | None = None` parameter; when set, run the
   extraction described above before the `float()` call.
3. Dispatch site (`evaluators.py`, the `elif eval_type == "output_numeric":` branch):
   pass `key=config.key`.
4. Consider whether `output_json`-style `source:` interaction needs any change — `source`
   is resolved upstream in `executor.py` and should compose without special handling.

### Scope decision to make

Should `key:` also apply to `convergence` and `score_stall`, which face the same
labelled-output problem? Recommend **no** for this issue — keep the change minimal and
revisit if a concrete need appears. Record the decision either way.

## Integration Map

- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` (field, `to_dict`, `from_dict`, docstring)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric` + dispatch branch
- `scripts/little_loops/loops/docs-sync.yaml` — becomes correct as written (BUG-2893)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — still needs its echo fixed (BUG-2894)
- `docs/reference/API.md` — evaluator reference
- `.claude/CLAUDE.md` / loop-authoring docs — document the new field
- `scripts/tests/` — unit tests for extraction semantics

## Implementation Steps

1. Add the `key` field to `EvaluateConfig` with serialization round-trip coverage.
2. Implement extraction in `evaluate_output_numeric`; unit-test: bare number (no key),
   labelled single line, in-line multi-field, multiple matches (last wins), missing key,
   non-numeric value, key requiring regex escaping.
3. Wire `key=config.key` at the dispatch site.
4. Update `docs/reference/API.md` and the loop-authoring reference.
5. Close out BUG-2893 and BUG-2894 against the new behaviour.
6. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Backward compatibility**: Fully compatible — behaviour is unchanged when `key` is
  absent, which is every loop except the two already broken.
- **Value**: Fixes two live built-in loop defects with no shell rewrite; removes a
  recurring authoring trap.
- **Pairs with**: ENH-2896 (reject unknown evaluate keys). ENH-2896 is the more important
  of the two — it prevents the *next* inert field. This issue only fixes the current one.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/API.md` | `little_loops.fsm.evaluators` / `schema` reference to update |
| `docs/ARCHITECTURE.md` | Evaluator dispatch and verdict routing |
| `.claude/CLAUDE.md` | Loop Authoring rules and evaluator inventory |

## Session Log
- `/ll:verify-issues` - 2026-07-28T22:25:21 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open
