---
discovered_date: 2026-03-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
status: done
completed_at: 2026-03-03T00:00:00Z
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

1. **`scripts/little_loops/cli/history.py`** — 4 string replacements:
   - Line 41–42: change two epilog example lines from `generate-docs` → `export`
   - Line 102: `add_parser("generate-docs", ...)` → `add_parser("export", ...)`
   - Line 204: `if args.command == "generate-docs":` → `if args.command == "export":`
2. **`scripts/tests/test_doc_synthesis.py`** — update 4 `sys.argv` mocks in `TestGenerateDocsCLI`:
   - Lines 371, 400, 432, 463: `"generate-docs"` → `"export"` in each `sys.argv` patch list
3. **`docs/reference/API.md`** — replace 6 occurrences at lines 2298, 2300, 2303, 2328, 2331, 2334
4. **`docs/reference/COMMANDS.md`** — replace 1 occurrence at line 248
5. **`README.md`** — replace 2 occurrences at lines 316–317
6. **`skills/analyze-history/SKILL.md`** — replace 5 occurrences at lines 61, 66, 71, 101, 102
7. **`.claude/CLAUDE.md`** — update `ll-history` CLI Tools description
8. **Skip `doc_synthesis.py`** — confirmed zero occurrences of `"generate-docs"`; no changes needed
9. Run tests: `python -m pytest scripts/tests/test_doc_synthesis.py scripts/tests/test_issue_history_cli.py -v`

## Scope Boundaries

- **In scope**: Renaming the CLI-facing subcommand from `generate-docs` to `export` across all affected files
- **Out of scope**: Backward-compatibility alias — old `ll-history generate-docs` invocations will break; that's acceptable
- **Out of scope**: Renaming internal Python functions (`synthesize_docs()` stays as-is)
- **Out of scope**: Changes to output format, behavior, or output content

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — 4 occurrences:
  - Line 41–42: two epilog examples (`generate-docs` → `export`)
  - Line 102: `add_parser("generate-docs", ...)` → `add_parser("export", ...)`
  - Line 204: `if args.command == "generate-docs":` → `if args.command == "export":`
- `scripts/tests/test_doc_synthesis.py` — 4 occurrences (all in `TestGenerateDocsCLI.sys.argv` mocks):
  - Lines 371, 400, 432, 463: `"generate-docs"` → `"export"` in `sys.argv` list patches
- `.claude/CLAUDE.md` — CLI Tools section `ll-history` description
- `docs/reference/API.md` — 6 occurrences at lines 2298, 2300, 2303, 2328, 2331, 2334 (usage examples and API docs)
- `docs/reference/COMMANDS.md` — 1 occurrence at line 248 (prose description)
- `README.md` — 2 occurrences at lines 316–317 (usage examples)
- `skills/analyze-history/SKILL.md` — 5 occurrences at lines 61, 66, 71, 101, 102 (example invocations)

### Dependent Files (Callers/Importers)
- `doc_synthesis.py` contains **zero** occurrences of the string `"generate-docs"` — no changes needed there

### Similar Patterns
- Hyphenated subcommand names are standard: `"next-id"` and `"impact-effort"` in `scripts/little_loops/cli/issues/__init__.py`
- `if`-chain dispatch (not `elif`) is the `history.py` convention — follow the same pattern for the renamed command

### Tests
- `scripts/tests/test_doc_synthesis.py` — `TestGenerateDocsCLI` class (line 358), 4 `sys.argv` mocks to update (lines 371, 400, 432, 463)
- `scripts/tests/test_issue_history_cli.py` — general `ll-history` tests (no `generate-docs` string, no changes needed)

### Documentation
- `docs/reference/API.md`, `docs/reference/COMMANDS.md`, `README.md`, `.claude/CLAUDE.md`, `skills/analyze-history/SKILL.md`

### Configuration
- N/A — no entry points, config files, or pyproject.toml changes needed

## Impact

- **Priority**: P4 — low-priority cosmetic rename; no behavior change
- **Effort**: Small — pure string replacement across ~4 files, no logic changes
- **Risk**: Low — no functional changes; test suite confirms no regressions
- **Breaking Change**: Yes (minor) — `ll-history generate-docs` invocations will fail; no backward-compat alias

## Labels

`enhancement`, `cli`, `ux`

---

**Completed** | Created: 2026-03-03 | Completed: 2026-03-03 | Priority: P4

## Resolution

Renamed CLI subcommand `generate-docs` → `export` across all affected files:
- `scripts/little_loops/cli/history.py` — epilog examples, `add_parser`, and command dispatch
- `scripts/tests/test_doc_synthesis.py` — 4 `sys.argv` mocks in `TestGenerateDocsCLI`
- `docs/reference/API.md` — 6 occurrences (table entry, section heading, usage examples)
- `docs/reference/COMMANDS.md` — prose description
- `README.md` — 2 usage examples + comment
- `skills/analyze-history/SKILL.md` — 5 example invocations and table entries
- `.claude/CLAUDE.md` — CLI Tools description

All 39 tests pass. No backward-compatibility alias added (intentional per scope boundaries).

## Session Log
- `/ll:capture-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62ebf762-eee5-484f-a05f-cd1fd66f159e.jsonl`
- `/ll:format-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3f89019-8d96-425f-80aa-cd975bd7521c.jsonl`
- `/ll:refine-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b5cd253-19da-4e4f-813e-cf37aab9832b.jsonl`
- `/ll:manage-issue` - 2026-03-03T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
