---
discovered_date: 2026-03-03
discovered_by: capture-issue
---

# ENH-523: Rename `ll-history generate-docs` subcommand to `export`

## Summary

The `ll-history generate-docs` subcommand name implies AI synthesis or prose generation, but it only compiles and formats excerpts from completed issue files — no actual documentation generation occurs. Rename it to `ll-history export` (or `topic-report`) to set accurate user expectations.

## Current Behavior

The user invokes the subcommand as:

```
ll-history generate-docs <topic>
```

The CLI help output shows `generate-docs` as the subcommand name, misleading users into expecting AI-generated or synthesized documentation.

## Expected Behavior

The user invokes the subcommand as:

```
ll-history export <topic>
```

The CLI help output shows `export` as the subcommand name, accurately conveying that the command compiles and exports topic-filtered issue excerpts.

## Motivation

"generate-docs" misleads users into expecting polished, synthesized documentation output. The command is actually a **topic-filtered issue excerpt compiler**: it scores relevance, extracts markdown sections (Summary, Motivation, Implementation Notes), and assembles them chronologically. A name like `export` or `topic-report` accurately conveys this scope and prevents confusion about what the tool produces.

## Proposed Solution

Rename the subcommand from `generate-docs` to `export` across all affected files:

- `scripts/little_loops/cli/history.py` — subparser name, argparse epilog examples
- `scripts/little_loops/issue_history/doc_synthesis.py` — rename `synthesize_docs` → `export_topic` (or keep as-is if only the CLI name changes)
- `.claude/CLAUDE.md` — update `ll-history` description in the CLI Tools section
- `scripts/tests/test_doc_synthesis.py` — update any references to the subcommand name

## Implementation Steps

1. In `history.py`, change `subparsers.add_parser("generate-docs", ...)` → `"export"`
2. Update the `epilog` examples (`generate-docs` → `export`)
3. Update the `dest` / `args.command` check (`"generate-docs"` → `"export"`)
4. Decide whether to rename `synthesize_docs()` in `doc_synthesis.py` — internal rename is optional but improves consistency
5. Update `CLAUDE.md` CLI Tools entry
6. Run tests to confirm no regressions: `python -m pytest scripts/tests/test_doc_synthesis.py`

## Scope Boundaries

- **In scope**: Renaming the CLI-facing subcommand from `generate-docs` to `export` across all affected files
- **Out of scope**: Backward-compatibility alias — old `ll-history generate-docs` invocations will break; that's acceptable
- **Out of scope**: Renaming internal Python functions (`synthesize_docs()` stays as-is)
- **Out of scope**: Changes to output format, behavior, or output content

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — subparser registration (`add_parser`), epilog examples, `args.command` check
- `.claude/CLAUDE.md` — CLI Tools section `ll-history` description
- `scripts/tests/test_doc_synthesis.py` — test references to the subcommand name

### Dependent Files (Callers/Importers)
- Any shell scripts or external docs that invoke `ll-history generate-docs` directly — use `grep -r "generate-docs" .` to find

### Similar Patterns
- Other subcommand registrations in `scripts/little_loops/cli/` for naming consistency

### Tests
- `scripts/tests/test_doc_synthesis.py` — update `generate-docs` string references to `export`

### Documentation
- `.claude/CLAUDE.md` — CLI Tools section entry for `ll-history`

### Configuration
- N/A

## Impact

- **Priority**: P4 — low-priority cosmetic rename; no behavior change
- **Effort**: Small — pure string replacement across ~4 files, no logic changes
- **Risk**: Low — no functional changes; test suite confirms no regressions
- **Breaking Change**: Yes (minor) — `ll-history generate-docs` invocations will fail; no backward-compat alias

## Labels

`enhancement`, `cli`, `ux`

---

**Open** | Created: 2026-03-03 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62ebf762-eee5-484f-a05f-cd1fd66f159e.jsonl`
- `/ll:format-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3f89019-8d96-425f-80aa-cd975bd7521c.jsonl`
