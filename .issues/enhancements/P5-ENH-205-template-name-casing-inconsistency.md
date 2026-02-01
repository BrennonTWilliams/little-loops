# Template Internal Name vs Display Label Casing Inconsistency

## Type
ENH

## Priority
P5

## Status
OPEN

## Description

Template internal identifiers use kebab-case while display labels use different casing conventions. This is a very minor cosmetic inconsistency.

**Internal identifiers (kebab-case):**
- `python-quality`
- `javascript-quality`
- `tests-until-passing`
- `full-quality-gate`

**Display labels:**
- "Python quality (lint + types + format)"
- "JavaScript quality (lint + types)"
- "Run tests until passing"
- "Full quality gate (tests + types + lint)"

**Evidence:**
- `commands/create_loop.md:72-141`

**Impact:**
Extremely minor. Internal names vs display labels having different casing is standard practice and doesn't cause any confusion.

## Files Affected
- `commands/create_loop.md`

## Recommendation
No action needed. This is normal convention:
- Internal identifiers: kebab-case (machine-readable)
- Display labels: Title case, descriptive (human-readable)

## Related Issues
None
