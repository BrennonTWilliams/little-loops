---
discovered_commit: 8f24d743
discovered_branch: main
discovered_date: 2026-04-26T15:23:43Z
completed_at: 2026-04-26T15:46:44Z
discovered_by: audit-docs
doc_file: README.md
testable: false
status: done
---

# ENH-1292: Document ll-generate-schemas in README

## Summary

Documentation issue found by `/ll:audit-docs`.

## Location

- **File**: `README.md`
- **Line(s)**: 90
- **Section**: What's Included / CLI Tools

## Current Behavior

```markdown
- **16 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`, etc.) for autonomous and parallel issue processing
```

`ll-generate-schemas` has no entry in the README CLI Tools section.

## Problem

`ll-generate-schemas` is registered in `scripts/pyproject.toml` as a package entry point and is installed with `pip install little-loops`. However, it is absent from README entirely. CLAUDE.md notes it as a "maintainer tool" but README says "16 CLI tools" when 17 are actually installed. Users discovering the binary via their PATH have no documentation to reference.

## Expected Behavior

Either:

**Option A** — Document it briefly with a maintainer note and update the count:

```markdown
- **17 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`, etc.) for autonomous and parallel issue processing
```

And add a `### ll-generate-schemas` section in the CLI Tools area:

```markdown
### ll-generate-schemas

Regenerate JSON Schema files for all `LLEvent` types into `docs/reference/schemas/`. This is a maintainer tool used when adding new event types.

```bash
ll-generate-schemas       # Regenerate all schema files
ll-generate-schemas --help
```
```

**Option B** — Keep count at 16 and explicitly note it excludes the maintainer tool with an inline comment.

## Impact

- **Severity**: Low (maintainer tool, not user-facing workflow)
- **Effort**: Small (add one paragraph + update count)
- **Risk**: Low

## Scope Boundaries

- Update README.md only (no code changes)
- Add brief description + usage example for `ll-generate-schemas`; do not write full API docs
- Update the "16 CLI tools" count; do not audit or change other counts in the README

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-04-26T15:43:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e00e6b64-a720-442d-aa7b-7ccecb6bbad2.jsonl`

---

## Resolution

- Updated CLI tools count from 16 → 17 in README.md line 90
- Added `### ll-generate-schemas` section with description and usage example, placed before `ll-verify-docs / ll-check-links`
- Chose Option A (document with maintainer note and update count)

## Status

**Completed** | Created: 2026-04-26 | Completed: 2026-04-26 | Priority: P4
