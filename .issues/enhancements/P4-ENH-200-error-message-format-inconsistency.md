# Error Message Format Inconsistency Across Paradigm Compilers

## Type
ENH

## Priority
P4

## Status
OPEN

## Description

Error messages across different paradigm validators use inconsistent formats, making it harder to parse them programmatically and creating minor inconsistency in user experience.

**Examples from `compilers.py`:**

Goal paradigm (line 164-167):
```python
if "goal" not in spec:
    raise ValueError("Goal paradigm requires 'goal' field")
if "tools" not in spec or not spec["tools"]:
    raise ValueError("Goal paradigm requires 'tools' field with at least one tool")
```

Convergence paradigm (lines 232-236):
```python
required = ["name", "check", "toward", "using"]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"Convergence paradigm requires: {', '.join(missing)}")
```

Invariants paradigm (lines 322-328):
```python
if "name" not in spec:
    raise ValueError("Invariants paradigm requires 'name' field")
if "constraints" not in spec or not spec["constraints"]:
    raise ValueError("Invariants paradigm requires 'constraints' field with at least one constraint")
```

Imperative paradigm (lines 422-429):
```python
if "name" not in spec:
    raise ValueError("Imperative paradigm requires 'name' field")
if "steps" not in spec or not spec["steps"]:
    raise ValueError("Imperative paradigm requires 'steps' field with at least one step")
```

**Inconsistencies:**
1. Convergence lists all missing fields together
2. Others validate one field at a time
3. Convergence uses "requires: {fields}" format
4. Others use "requires 'field' field" format

**Evidence:**
- `scripts/little_loops/fsm/compilers.py:164-429`

**Impact:**
Minor. All error messages are clear and actionable. The inconsistency only affects:
1. Programmatic parsing of error messages (if anyone does this)
2. Slight inconsistency in user-facing text

## Files Affected
- `scripts/little_loops/fsm/compilers.py`

## Recommendation

**Option 1: Standardize to list-all-missing format (Recommended)**
All validators could use the convergence pattern which is more comprehensive:
```python
required = [...]
missing = [...]
if missing:
    raise ValueError(f"{paradigm} paradigm requires: {', '.join(missing)}")
```

**Option 2: Keep as-is**
The current approach is fine - all errors are clear. This is a very minor inconsistency.

## Related Issues
None
