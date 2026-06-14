---
id: ENH-2126
title: "Surface rule-candidate suggestions when listing or reviewing decisions"
status: open
priority: P4
type: ENH
captured_at: "2026-06-14T00:09:45Z"
discovered_date: "2026-06-14"
discovered_by: capture-issue
relates_to: [ENH-2125]
---

# ENH-2126: Surface rule-candidate suggestions when listing or reviewing decisions

## Summary

Add a `--suggest-rules` flag (or dedicated `suggest-rules` subcommand) to `ll-issues decisions` that analyzes existing `type: decision` entries and identifies candidates suitable for promotion to `type: rule`. Without this, users must notice cross-issue patterns manually, so rules are rarely created.

## Motivation

Rules are durable cross-issue constraints that prevent `/ll:verify-issues` DECISIONS_VIOLATION checks from being inert. But identifying which decisions are worth promoting requires noticing repeated patterns across many entries. Currently there is no tooling for this:

- `ll-issues decisions list` shows all entries but gives no guidance on promotion candidates.
- The `generate_from_completed()` function creates decisions but never suggests rules.
- Users are expected to "notice a pattern" — but with 31+ decisions, that is impractical.

## Implementation Steps

1. Add `suggest-rules` subcommand (or `--suggest-rules` flag on `list`) in `scripts/little_loops/cli/issues/decisions.py`.
2. Load all `type: decision` entries from decisions.yaml.
3. Group by `category` field; flag categories with 3+ decisions as high-signal.
4. Within each group, extract `if_changed` globs (for coupling entries) or recurring file/module mentions in `rationale` text; flag entries that share the same module as a cluster.
5. For each candidate cluster, emit a suggestion block:
   ```
   [SUGGEST] ARCHITECTURE-018, ARCHITECTURE-030 share category=architecture and reference host_runner — consider promoting to a rule:
     "Always use resolve_host() for host CLI invocations; never hardcode 'claude'"
   ```
6. Optionally, pipe suggestions through a simple heuristic: entries whose `rule` field starts with "Option A/B/C" are less likely promotion candidates (one-off choices), while entries whose `rule` field reads as a general constraint are higher priority.
7. Exit 0 if any candidates found; exit 1 if none (useful for FSM evaluator routing).

## Acceptance Criteria

- `ll-issues decisions suggest-rules` prints at least one candidate cluster given the current 31 decisions.
- Entries with `type: rule` or `type: exception` are excluded from suggestions (already handled).
- Output is parseable by a human; each candidate includes entry IDs, inferred theme, and a suggested rule text.
- Gracefully exits with message when decisions.yaml has fewer than 3 entries.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | decisions module API |

## Session Log

- `/ll:capture-issue` - 2026-06-14T00:09:45Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
