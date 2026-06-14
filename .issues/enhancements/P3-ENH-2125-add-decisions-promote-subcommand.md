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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | decisions module API |
| `.ll/decisions.yaml` | live data file |

## Session Log

- `/ll:capture-issue` - 2026-06-14T00:09:45Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
