---
id: ENH-1619
type: ENH
priority: P4
status: open
discovered_date: 2026-05-22
discovered_by: confidence-check
blocked_by:
- FEAT-1112
relates_to:
- FEAT-1112
labels:
- enhancement
- wiring
- docs
---

# ENH-1619: Wire ll-session into docs, help, and config references

## Summary

Mechanical follow-up to FEAT-1112 (Unified Session Store): once `ll-session`, `SQLiteTransport`, and the `events.sqlite` config block land, update all documentation, help tables, skill allow-lists, and the doc-wiring test to reference the new CLI and transport. Carved out of FEAT-1112 so the core DB/CLI/transport implementation ships as a focused PR and the ~15 uniform wiring edits land separately without mixed concerns in review.

## Motivation

FEAT-1112's wiring pass enumerated ~28 change sites. Roughly half are functional (new modules, transport registration, config schema, entry-point registration) and half are mechanical reference updates (count increments, list additions, doc sections). Bundling both into one PR inflates the review surface and the breadth-driven implementation risk. Splitting the mechanical reference updates into this issue keeps each PR single-purpose.

## Current Behavior

- `ll-session` does not appear in `commands/help.md`, `.claude/CLAUDE.md` CLI Tools, `README.md` tool count, `CONTRIBUTING.md` package tree, or `docs/reference/CLI.md` / `docs/reference/API.md`
- `SQLiteTransport` / `events.sqlite` are absent from `docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, and `docs/reference/HOST_COMPATIBILITY.md`
- `skills/configure/areas.md` and `skills/init/SKILL.md` do not authorize `ll-session`
- `test_feat1504_doc_wiring.py` asserts `"Authorize all 24"` — will be stale once `areas.md` updates

## Expected Behavior

All documentation, help surfaces, skill allow-lists, and the doc-wiring test reference `ll-session` and `SQLiteTransport` consistently, matching the CLI and transport delivered by FEAT-1112.

## Acceptance Criteria

- `ll-session` row added to `commands/help.md` CLI TOOLS table
- `ll-session` entry added to `.claude/CLAUDE.md` CLI Tools section
- `README.md` tool count incremented `27` → `28` (both occurrences, ~lines 46 and 166)
- `CONTRIBUTING.md` package tree adds `session.py` to the `cli/` listing
- `docs/reference/CLI.md` adds `### ll-session` section documenting `search --fts` and `recent --kind` subcommands
- `docs/reference/API.md` adds `ll-session` CLI reference
- `docs/ARCHITECTURE.md` adds `SQLiteTransport` to EventBus component row, CLI Entry Points table, built-in transports prose, and `cli/session.py` to the module tree
- `docs/reference/CONFIGURATION.md` adds `"sqlite"` row to "Currently shipped transports" and an `events.sqlite` sub-object example
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` `## CLI Deep Dive: ll-workflows` data-source description revised for the DB-backed model
- `docs/reference/HOST_COMPATIBILITY.md` `## State directory` table adds a `.ll/session.db` row
- `skills/configure/areas.md` increments `"Authorize all 24 ll- CLI tools"` → `25` and adds `ll-session` to the inline list
- `skills/init/SKILL.md` adds `"Bash(ll-session:*)"` + narrative to both Bash allow-list JSON blocks
- `skills/update-docs/SKILL.md` inline snippet (~line 93) updated/annotated for the DB-backed `history.py` path
- `commands/analyze-workflows.md` data-availability precondition updated from "JSONL message file present" to "session.db populated"
- `test_feat1504_doc_wiring.py::TestConfigureAreasWiring.test_authorize_all_count_is_24` assertion updated to `"Authorize all 25"` (and renamed accordingly)
- Verification grep (see below) returns a hit for every wired surface

## Verification

```bash
# Every surface below must reference ll-session after this issue lands:
grep -rln "ll-session" \
  commands/help.md \
  .claude/CLAUDE.md \
  README.md \
  CONTRIBUTING.md \
  docs/reference/CLI.md \
  docs/reference/API.md \
  skills/configure/areas.md \
  skills/init/SKILL.md

# SQLiteTransport doc surfaces:
grep -rln "SQLiteTransport\|events.sqlite\|session.db" \
  docs/ARCHITECTURE.md \
  docs/reference/CONFIGURATION.md \
  docs/reference/HOST_COMPATIBILITY.md

# Doc-wiring test must assert the new count:
grep -n "Authorize all 25" scripts/tests/test_feat1504_doc_wiring.py
```

## Integration Map

### Files to Modify
- `commands/help.md` — add `ll-session` row to CLI TOOLS table
- `commands/analyze-workflows.md` — precondition note update
- `.claude/CLAUDE.md` — add `ll-session` to CLI Tools section
- `README.md` — increment tool count `27` → `28` (~lines 46, 166)
- `CONTRIBUTING.md` — add `session.py` to `cli/` package tree (~lines 188–203)
- `docs/reference/CLI.md` — add `### ll-session` section
- `docs/reference/API.md` — add `ll-session` CLI reference
- `docs/ARCHITECTURE.md` — add `SQLiteTransport` rows + `cli/session.py` tree entry
- `docs/reference/CONFIGURATION.md` — add `"sqlite"` transport row + `events.sqlite` example
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — revise `## CLI Deep Dive: ll-workflows` data-source description
- `docs/reference/HOST_COMPATIBILITY.md` — add `.ll/session.db` row to `## State directory` table
- `skills/configure/areas.md` — increment count to `25`, add `ll-session`
- `skills/init/SKILL.md` — add `"Bash(ll-session:*)"` to both Bash allow-list blocks
- `skills/update-docs/SKILL.md` — update/annotate inline `scan_completed_issues` snippet (~line 93)

### Tests
- `scripts/tests/test_feat1504_doc_wiring.py` — update `test_authorize_all_count_is_24` assertion to `"Authorize all 25"` [existing, will break — update required]

## Impact

- **Priority**: P4 — Non-blocking documentation/reference consistency follow-up
- **Effort**: Small — ~15 mechanical, uniform reference edits
- **Risk**: Low — No functional code; all changes are docs/help/allow-list text
- **Breaking Change**: No

## Risks / Notes

- Blocked by FEAT-1112: the `ll-session` CLI, `SQLiteTransport`, and `events.sqlite` config block must exist before these references are accurate.
- `test_feat1504_doc_wiring.py` will fail the moment `areas.md` is updated — bundle the assertion update in the same commit as the `areas.md` edit.

## References

- Carved out of FEAT-1112 (Unified Session Store) during a confidence-check pass to reduce that issue's breadth-driven implementation risk.

## Status

**Open** | Created: 2026-05-22 | Priority: P4
