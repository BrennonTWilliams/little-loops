---
id: ENH-2125
title: "Add `ll-issues decisions promote` subcommand to convert decisions to rules"
status: open
priority: P3
type: ENH
captured_at: "2026-06-14T00:09:45Z"
discovered_date: "2026-06-14"
discovered_by: capture-issue
---

# ENH-2125: Add `ll-issues decisions promote` subcommand to convert decisions to rules

## Summary

Add a `promote` subcommand to `ll-issues decisions` that converts an existing `type: decision` entry in `.ll/decisions.yaml` into a `type: rule` with configurable enforcement level. Currently there is no tooling to do this; it requires hand-editing the YAML file, which is friction-laden and error-prone.

## Motivation

`.ll/decisions.yaml` stores two conceptually distinct entry types:

- **decisions** (`type: decision`) — one-time architectural choices tied to a specific issue, auto-captured from completed issues.
- **rules** (`type: rule`) — durable cross-issue constraints that prevent future issues from proposing conflicting approaches; consumed by `sync_to_local_md` and checked by `/ll:verify-issues` DECISIONS_VIOLATION logic.

There is currently no automated pathway between the two. Promoting a decision to a rule requires hand-editing the YAML: changing `type:` from `decision` to `rule` and adding `enforcement: required`. This means rules are rarely created, and the DECISIONS_VIOLATION check in verify-issues is effectively inert.

## Success Metrics

- `ll-issues decisions promote <id>` exits 0 and the entry in `.ll/decisions.yaml` changes `type: decision` → `type: rule`
- `ll-issues decisions list --type rule` includes the promoted entry immediately after promotion
- `--enforcement required` triggers `sync_to_local_md()` and the rule appears in `## Active Rules` in `ll.local.md`
- `--enforcement advisory` produces a rule that does NOT appear in `## Active Rules`
- Promoting a non-decision entry exits 1 with a descriptive error message

## Scope Boundaries

- **In scope**: CLI `promote` subcommand for converting `type: decision` → `type: rule`; optional immediate sync to `ll.local.md` for required enforcement
- **Out of scope**: Reversing a promotion (rule → decision), batch/bulk promotion, any UI changes, modifying the capture flow or how decisions are auto-generated

## API/Interface

```bash
ll-issues decisions promote <entry_id> [--enforcement {required,advisory}]
```

- `entry_id` (positional, required): ID of the decision entry to promote (e.g., `ARCHITECTURE-030`)
- `--enforcement` (optional, default `required`): Enforcement level for the resulting rule; `required` entries are written to `## Active Rules` in `ll.local.md` via `sync_to_local_md()`

## Implementation Steps

1. Add `promote` as a new subparser under `ll-issues decisions` in `scripts/little_loops/cli/issues/decisions.py`.
2. Accept positional `entry_id` and optional `--enforcement {required,advisory}` (default `required`).
3. Load the entry; validate it is `type: decision` (abort with clear error if already a rule or wrong type).
4. Rewrite the entry in place:
   - Change `type` → `rule`
   - Copy `rule` field (or prompt user if blank)
   - Add `enforcement` field
   - Preserve `id`, `timestamp`, `category`, `labels`, `rationale`, `issue`, `supersedes`
   - Drop decision-only fields: `alternatives_rejected`, `scope`, `outcome`
5. Persist via `save_decisions()`.
6. Optionally call `sync_to_local_md()` if `enforcement == "required"` to immediately write the rule into `## Active Rules` in `ll.local.md`.
7. Print confirmation: `Promoted [ID] → rule (enforcement: required)`.

## Acceptance Criteria

- `ll-issues decisions promote ARCHITECTURE-030` succeeds and the entry in decisions.yaml changes `type: decision` → `type: rule`.
- `--enforcement advisory` produces a rule that does NOT appear in `## Active Rules` (only `required` entries are synced).
- Running `promote` on a non-decision entry (already a rule, exception, coupling) prints a clear error and exits 1.
- Running `promote` on a nonexistent ID exits 1.
- `ll-issues decisions list --type rule` includes the promoted entry.
- If `--enforcement required`, `ll.local.md` `## Active Rules` section is updated immediately.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/decisions.py` — add `promote` subparser with `entry_id` and `--enforcement` args
- `scripts/little_loops/decisions.py` (or equivalent module) — `save_decisions()` and `sync_to_local_md()` callers

### Dependent Files (Callers/Importers)
- TBD — `grep -r "decisions" scripts/little_loops/cli/issues/` to find related subcommand handlers

### Similar Patterns
- Existing `ll-issues decisions add` / `ll-issues decisions outcome` subcommands for consistent argument and output patterns

### Tests
- TBD — likely `scripts/tests/test_decisions*.py` or `scripts/tests/test_cli_decisions.py`

### Documentation
- `docs/reference/API.md` — decisions module API docs
- `.ll/decisions.yaml` — live data file (exercised by tests, not modified in code)

### Configuration
- N/A

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | decisions module API |
| `.ll/decisions.yaml` | live data file |

## Session Log
- `/ll:format-issue` - 2026-06-14T00:13:26 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`

- `/ll:capture-issue` - 2026-06-14T00:09:45Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
