---
id: ENH-2896
type: ENH
priority: P2
status: open
captured_at: "2026-07-28T22:13:33Z"
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to: [BUG-2893, BUG-2894, ENH-2895]
---

# ENH-2896: Reject or warn on unknown keys in EvaluateConfig.from_dict

## Summary

`EvaluateConfig.from_dict` builds the dataclass by enumerating known fields with
`data.get(...)`. Any key present in the YAML but absent from that enumeration is
discarded silently — no exception, no log line, no `ll-loop validate` diagnostic. A
typo'd, aspirational, or version-drifted evaluator key is indistinguishable from a
working one until someone traces a runtime verdict back to its source.

This is the root cause that let BUG-2893 and BUG-2894 ship: two loops declaring
`key: <field>` on `output_numeric`, both inert, both undetected.

## Motivation

The failure mode is uniquely bad because it is *quiet and plausible*. The author writes
a field, the loop loads, `ll-loop validate` passes, the loop runs. The only symptom is a
verdict that is subtly wrong — and in BUG-2894's case the wrong verdict was masked by
shared `on_no`/`on_error` routing, so it went unnoticed indefinitely.

`.claude/CLAUDE.md` documents an extensive `ll-loop validate` gate table (MR-1 … MR-13,
policy-table, capture-reachability, …) built precisely to shift this class of error
left. "Evaluator field silently does nothing" belongs in that family and is currently
the only member with no detection at all.

The same pattern likely exists in sibling `from_dict` methods across `fsm/schema.py`
(`StateConfig`, `LoopConfig`, and others) — worth auditing in the same pass.

## Current Pain Point / Current Behavior

`scripts/little_loops/fsm/schema.py`:

```python
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluateConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            type=data["type"],
            operator=data.get("operator"),
            target=data.get("target"),
            ...
        )
```

`{"type": "output_numeric", "key": "pass_rate", "operator": "ge", "target": 0.95}`
constructs successfully; `key` is gone. `EvaluateConfig` has ~28 optional fields, most
of them evaluator-type-specific, so authors reasonably guess at names.

## Expected Behavior

An unknown key under `evaluate:` produces a diagnostic naming the state, the key, and
the evaluator type — at validation time, not at runtime.

Two candidate strictness levels:

- **WARN at `ll-loop validate`** (recommended default): a new lint rule reporting
  unknown evaluate keys. Non-breaking; surfaces existing drift across user loops without
  hard-failing anyone's working automation.
- **ERROR at load**: `from_dict` raises on unknown keys. Strongest guarantee, but
  breaks any third-party or user loop currently carrying a stray key — including,
  today, two of our own built-ins.

Recommended sequencing: land the WARN lint first, fix BUG-2893/BUG-2894 and any other
hits it surfaces, then consider promoting to ERROR in a subsequent release. Record this
as a decision.

A useful refinement either way: suggest the nearest known field name
(`difflib.get_close_matches`) so `key` → *did you mean `line`? `path`?* guides the author
to an existing primitive.

### Type-aware validation (stretch)

Beyond unknown keys, most fields are only meaningful for specific evaluator types —
`pattern` for `output_contains`, `pairs` for `contract`, `line` for `classify`. A field
that is *known but irrelevant to the declared type* is equally inert. Consider a
per-type allowed-field map as a follow-on; note it here so the option isn't lost, but
keep it out of this issue's minimum scope.

## Proposed Solution

1. Derive the known-field set from the dataclass itself
   (`{f.name for f in dataclasses.fields(EvaluateConfig)}`) rather than hand-maintaining
   a second list that can drift from `from_dict` the same way `from_dict` drifted from
   authors' expectations.
2. Add an `ll-loop validate` rule walking every state's raw `evaluate:` mapping and
   reporting keys outside that set, with a close-match suggestion.
3. Follow the existing gate conventions in `.claude/CLAUDE.md`: assign a rule id,
   severity, and a top-level suppression flag consistent with the MR-* table.
4. Audit sibling `from_dict` implementations in `fsm/schema.py` for the same silent-drop
   pattern and decide whether to generalize the check.

## Integration Map

- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.from_dict` and siblings
- `scripts/little_loops/fsm/validation/` — new lint rule
- `.claude/CLAUDE.md` — Loop Authoring gate table entry (rule id, severity, suppress flag)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — source of truth the table summarizes
- `scripts/tests/` — lint unit tests + a built-in-loops sweep asserting zero unknown keys

## Implementation Steps

1. Write a test asserting the current silent drop, to pin the behaviour being changed.
2. Implement known-field derivation from `dataclasses.fields`.
3. Add the validation rule with close-match suggestions; assign the rule id and
   suppression flag.
4. Run it across all built-in loops; expect hits in `docs-sync.yaml` and
   `oracles/code-run-gate.yaml` (and possibly others — that sweep is a deliverable).
5. Document the rule in `.claude/CLAUDE.md` and the harness guide.
6. Record the WARN-now / ERROR-later decision via `ll-issues decisions add`.
7. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Value**: Prevents recurrence of an entire defect class. This is the higher-leverage
  half of the ENH-2895 / ENH-2896 pair — ENH-2895 fixes the field authors wanted;
  this one ensures the *next* wrong field is loud.
- **Backward compatibility**: WARN level is non-breaking. ERROR level is breaking and
  should not ship until the built-in sweep is clean.
- **Effort**: Moderate — the validation framework and gate-table conventions already
  exist; this is a new rule within them.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` | Loop Authoring gate table; where the new rule is registered |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Source of truth for validation rules and rationale |
| `docs/reference/API.md` | `little_loops.fsm.schema` / `validation` reference |

## Session Log
- `/ll:verify-issues` - 2026-07-28T22:25:21 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open
