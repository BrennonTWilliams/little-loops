---
id: BUG-3239
type: BUG
title: ll-loop validate warns declares no scope on loops that declare one, and the
  warning never reaches --json violations
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:23:20Z'
---

# BUG-3239: ll-loop validate warns declares no scope on loops that declare one, and the warning never reaches --json violations

## Summary

`ll-loop validate` prints the BUG-3107 "declares no `scope:`" warning for loops that *do* declare
a scope. The warning is emitted during loading against an FSM whose `scope` is not yet populated,
and it bypasses the returned errors list entirely — so it reaches stderr while
`load_and_validate()` reports zero warnings.

## Current Behavior

`scripts/little_loops/loops/refine-to-ready-issue.yaml` declares a scope at lines 35-37:

```yaml
scope:
  - ".issues/"
  - "${context.run_dir}"
```

Yet:

```
$ ll-loop validate refine-to-ready-issue
[WARNING] scope: Loop declares no 'scope:'. Without it, ll-loop run falls back to a repo-root
lock that false-conflicts with every other concurrently running loop. ...
[13:11:15] refine-to-ready-issue is valid
```

The contradiction is sharper in-process — the warning prints, the parsed scope is correct, and
the returned error list is empty:

```python
from pathlib import Path
from little_loops.fsm import load_and_validate
fsm, errs = load_and_validate(Path('scripts/little_loops/loops/refine-to-ready-issue.yaml'),
                              raise_on_error=False)
# stderr: [WARNING] scope: Loop declares no 'scope:'. ...
print(repr(fsm.scope))   # → ['.issues/', '${context.run_dir}']
print(errs)              # → []
```

`--json` output also reports clean, confirming the warning never enters the structured channel:

```
$ ll-loop validate refine-to-ready-issue --json
{"loop": "refine-to-ready-issue", "valid": true, "violations": []}
```

For contrast, `ll-loop validate autodev` emits no such warning, so this is not universal.

## Steps to Reproduce

1. Confirm the loop declares a scope — `scripts/little_loops/loops/refine-to-ready-issue.yaml`
   lines 35-37 contain:

   ```yaml
   scope:
     - ".issues/"
     - "${context.run_dir}"
   ```

2. Validate it:

   ```bash
   ll-loop validate refine-to-ready-issue
   ```

   Observed: `[WARNING] scope: Loop declares no 'scope:'. ...` followed by
   `refine-to-ready-issue is valid`.

3. Confirm the structured channel disagrees:

   ```bash
   ll-loop validate refine-to-ready-issue --json
   # → {"loop": "refine-to-ready-issue", "valid": true, "violations": []}
   ```

4. Confirm in-process that the parsed scope is correct while the warning still prints:

   ```bash
   python3 -c "
   from pathlib import Path
   from little_loops.fsm import load_and_validate
   fsm, errs = load_and_validate(
       Path('scripts/little_loops/loops/refine-to-ready-issue.yaml'), raise_on_error=False)
   print(repr(fsm.scope))   # → ['.issues/', '\${context.run_dir}']
   print(errs)              # → []
   "
   ```

5. Contrast with a loop that does not reproduce it:

   ```bash
   ll-loop validate autodev   # no scope warning
   ```

## Expected Behavior

`ll-loop validate` emits the missing-scope warning only for loops that actually declare no
`scope:`. For every loop, the warnings written to stderr and the entries in `--json`
`violations` describe the same set of findings.

## Motivation

BUG-3107 added this warning to shift the unscoped-repo-root-lock hazard from run time to
validate time, and BUG-3106 then applied `scope:` to 78 built-in loops to clear the resulting
warnings. A false positive undoes that investment: it re-dirties the signal on loops that were
explicitly fixed, and teaches operators that the warning is safe to ignore — which is precisely
how the original hazard returns unnoticed.

The stderr/`--json` disagreement is the more serious half: an automated consumer and a human
reading the same invocation reach opposite conclusions about whether the loop is clean.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

Two distinct harms:

- **The warning is noise on correctly-scoped loops**, which trains operators to ignore it —
  defeating BUG-3107's purpose of shifting the unscoped-lock hazard to validate time. BUG-3106
  applied scope to 78 built-in loops specifically to clear these; a false positive re-dirties
  that signal.
- **stderr and the structured channel disagree.** Any consumer trusting `--json` sees
  `violations: []` while a human sees a warning. A CI-style gate and an operator reading the same
  command reach different conclusions.

## Root Cause

Undetermined at the exact call site, but bounded by two confirmed facts:

1. The rule itself is correct. `_validate_missing_scope`
   (`scripts/little_loops/fsm/validation/structural_rules.py:1226-1248`) is a plain
   `if fsm.scope: return []` guard. Given the final FSM it returns `[]` — consistent with the
   empty `errs`.
2. Therefore the printed warning comes from an *earlier* evaluation, against an FSM whose
   `scope` is still falsy — most likely a pre-import-merge or partially-constructed loop object
   during loading — and is written straight to stderr instead of being collected.

The defect is in how/when the rule is invoked and how its output is routed, not in the predicate.
Introduced with BUG-3107, which added the warning.

## Proposed Solution

1. Locate the pre-final invocation of the scope check during load (the site emitting to stderr
   while `errs` stays empty) and either defer it until after import merging / full construction,
   or route its output through the same `ValidationError` collection every other rule uses.
2. Ensure every warning that reaches stderr also appears in the returned list and in `--json`
   `violations`, so the two channels cannot disagree.

## Acceptance Criteria

- [ ] `ll-loop validate refine-to-ready-issue` emits no scope warning.
- [ ] A loop that genuinely declares no `scope:` still warns (BUG-3107's behavior preserved).
- [ ] For any loop, the warnings on stderr and the entries in `--json` `violations` agree.
- [ ] A regression test covers a scope-declaring loop asserting zero scope warnings, and a
      scope-less loop asserting exactly one.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found incidentally while auditing `refine-to-ready-issue` for an unrelated investigation
(see ENH-3238); not related to that issue's subject matter.

Related completed work: BUG-3107 (added the warning), BUG-3088 (audit of unscoped loops),
BUG-3106 (applied scope to 78 built-in loops).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-17T18:23:56 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
