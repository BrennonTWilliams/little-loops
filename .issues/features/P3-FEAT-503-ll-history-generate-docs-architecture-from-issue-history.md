---
id: FEAT-503
type: FEAT
priority: P3
status: open
title: "ll-history generate-docs: architecture documentation synthesis from issue history"
discovered_date: 2026-02-24
discovered_by: capture-issue
---

# FEAT-503: ll-history generate-docs: architecture documentation synthesis from issue history

## Summary

Add a `generate-docs` subcommand to `ll-history` that synthesizes architecture documentation from completed issue history. Given a topic, area, or system, the command finds related completed issues and constructs a documentation file progressively—from oldest to newest by completion time—so the generated documentation is up-to-date and informed by actual development history.

## Current Behavior

`ll-history` provides `summary` and `analyze` subcommands but no documentation synthesis capability. There is no way to generate architecture documentation from completed issue history. Users must manually review completed issues and write documentation by hand, which frequently goes stale.

## Expected Behavior

`ll-history generate-docs <topic>` finds completed issues matching the topic, orders them chronologically by completion date, and synthesizes a structured markdown document. The output can be written to a file via `--output` or printed to stdout. The resulting document reads as a narrative of how the system was built, from earliest decisions to latest changes.

## Motivation

Architecture documentation is frequently stale or absent because it's maintained separately from implementation. Completed issues are a rich, timestamped record of what was built, why, and how. By synthesizing them in chronological order, `generate-docs` can reconstruct accurate documentation that reflects the real implementation state rather than an idealized view. This turns the issue history into a living architecture knowledge base.

## Use Case

A developer wants to understand how the `ll-history` CLI module was built and how it works internally:

```bash
ll-history generate-docs "ll-history module" --output docs/arch/ll-history.md
```

The command:
1. Finds all completed issues related to `ll-history` (e.g., FEAT-110, FEAT-111, ENH-390, ENH-468)
2. Orders them by `completed_date` ascending
3. Constructs a markdown document by synthesizing each issue's intent, implementation scope, and outcome
4. Writes a documentation file that reads like a design narrative—earliest decisions first, latest changes last

Another example:

```bash
ll-history generate-docs "session log" --format narrative
ll-history generate-docs "sprint CLI" --output docs/arch/sprint.md --since 2025-01-01
```

## Scope Boundaries

- **In scope**: Adding `generate-docs` subcommand to `ll-history`; topic-based relevance scoring; chronological synthesis; `--output`, `--format`, `--since`, `--type`, `--min-relevance` flags; new `doc_synthesis.py` module
- **Out of scope**: Modifying completed issue files during synthesis; AI-generated summaries (uses existing issue content only); real-time issue processing (synthesis is read-only)

## Proposed Solution

Add a `generate-docs` subcommand that scores completed issues for relevance using keyword overlap (similar to `capture-issue` duplicate detection), sorts matches chronologically by `completed_date`, and constructs a markdown document section-by-section from each matched issue's Summary, Motivation, and Implementation Notes. A new `doc_synthesis.py` module keeps the CLI thin.

## Implementation Steps

1. **Add `generate-docs` subparser** to `scripts/little_loops/cli/history.py` (alongside existing `summary` and `analyze`)
2. **Topic-based issue filtering**: accept a topic string and score completed issues by relevance (title + description keyword overlap, similar to duplicate detection in `capture-issue`)
3. **Chronological synthesis**: sort matched issues by `completed_date` ascending; iterate to build document sections
4. **Document construction**: for each issue, emit a section with:
   - Issue ID + title as heading
   - Completion date
   - Summary/description content
   - Implementation notes (if present in the issue file)
5. **Output options**: `--output <path>` to write file, default stdout; `--format` flag for `narrative` vs `structured` styles
6. **Optional filters**: `--since <date>`, `--min-relevance <float>`, `--type BUG|FEAT|ENH`
7. **Add a new module** `scripts/little_loops/issue_history/doc_synthesis.py` for the synthesis logic (keeping CLI thin)

## API/Interface

```bash
# New subcommand
ll-history generate-docs <topic> [options]

Options:
  --output PATH         Write to file instead of stdout
  --format {narrative,structured}
                        Output format (default: narrative)
  --since DATE          Only include issues completed after DATE (YYYY-MM-DD)
  --min-relevance FLOAT Minimum relevance score threshold (default: 0.3)
  --type {BUG,FEAT,ENH} Filter by issue type
```

New module: `scripts/little_loops/issue_history/doc_synthesis.py`
- `synthesize_docs(topic: str, issues: list[CompletedIssue], format: str) -> str`
- `score_relevance(topic: str, issue: CompletedIssue) -> float`
- `build_narrative_doc(issues: list[CompletedIssue]) -> str`
- `build_structured_doc(issues: list[CompletedIssue]) -> str`

## Acceptance Criteria

- `ll-history generate-docs "session log"` produces a coherent markdown document from matched completed issues
- Issues appear in chronological order by `completed_date`
- Relevance filtering excludes clearly unrelated issues
- `--output` flag writes the file and prints a confirmation
- At least 5 unit tests for `doc_synthesis.py` covering scoring, ordering, and formatting
- Works with 0 matches (graceful empty output with message)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — add `generate-docs` subparser and `cmd_generate_docs` handler

### New Files
- `scripts/little_loops/issue_history/doc_synthesis.py` — synthesis logic (`synthesize_docs`, `score_relevance`, `build_narrative_doc`, `build_structured_doc`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/parsing.py` — `CompletedIssue` type used for input
- `scripts/little_loops/issue_history/analysis.py` — existing issue scoring patterns to reuse

### Similar Patterns
- `capture-issue` duplicate detection — same keyword overlap scoring approach
- Existing `ll-history summary` subcommand — same pattern for adding new subcommands

### Tests
- `scripts/tests/test_doc_synthesis.py` — at least 5 unit tests for scoring, ordering, and formatting

### Documentation
- N/A — `--help` auto-generated

### Configuration
- N/A

## Impact

- **Priority**: P3 — Valuable developer tool; turns issue history into living documentation
- **Effort**: Medium — New module + subcommand + topic scoring + tests
- **Risk**: Low — Read-only synthesis; no changes to existing commands or issue files
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-history`, `documentation`, `synthesis`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI tool architecture and module patterns |
| `.claude/CLAUDE.md` | CLI tools list, `ll-history` entry |

## Session Log
- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81df3c59-9dd6-4928-bbf8-ba4b14bd0d12.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is comprehensive; cli/history.py integration point confirmed; issue_history/analysis.py confirmed as similar pattern source; no knowledge gaps identified

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocks

- FEAT-441

- ENH-459
- ENH-484

## Blocked By

- ENH-481

- ENH-498
- ENH-491