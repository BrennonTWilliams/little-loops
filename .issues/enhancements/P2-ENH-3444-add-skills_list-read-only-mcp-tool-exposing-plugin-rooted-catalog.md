---
id: ENH-3444
type: ENH
title: Add skills_list read-only MCP tool exposing plugin-rooted catalog
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:35:03Z'
---

# ENH-3444: Add skills_list read-only MCP tool exposing plugin-rooted catalog

## Summary

Add a `skills_list` tool to the ll-mcp registry: a read-only enumeration of the install's
skills and commands, anchored at the plugin root the server itself resolves
(`skill_expander._find_plugin_root()`), wrapping the existing single-source enumeration
`tool_catalog.assemble_tool_catalog` rather than building a new one.

This closes the one gap in the registry's queue workflow: `queue_add` can classify a name
(`runner: skill` vs `cmd` fallback) but nothing can list what names exist, forcing consumers
to duplicate the engine's plugin-root resolution to build a picker catalog.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

ll-console (the deployment dashboard) currently duplicates the engine's resolution three
times over:

1. `deploy/install.sh` probes the plugin root at install time and renders it into
   `/etc/ll-console.env` as `LL_LOOPS_ROOT`
2. `ll_console/skills_client.py` scans that root directly (`skills/<name>/SKILL.md` +
   `commands/*.md`) with a hand-rolled frontmatter parser and name-derivation rules that
   mirror `skill_expander._resolve_content_path` (path stem is truth; frontmatter `name:`
   is decorative)
3. `ll_console/queue_client.py` pins `CLAUDE_PLUGIN_ROOT=$LL_LOOPS_ROOT` into every ll-mcp
   spawn so the catalog (console-resolved root) and the classification (engine-resolved
   root, which prefers that same env var) cannot disagree — without the pin, a picker row
   for `ll-commit` could silently classify as `cmd` and queue a broken shell line

The "listed in picker implies classifies as skill" guarantee holds today only via that
mirroring. Moving enumeration into the engine makes it a construction guarantee: same
process, same `_find_plugin_root()` call path, same lookup domain as `_classify_action`.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Proposed Approach

The enumeration already exists — `scripts/little_loops/tool_catalog.py` (FEAT-2672/2673's
"single, stable data source") walks `skills/*/SKILL.md` and `commands/*.md` with
resolution-truth names (directory name / file stem), tolerant reads (OSError caught, missing
dirs contribute no entries, never raises), sorted determinism, and frontmatter description
extraction. The tool is therefore a thin exposure, not a new design:

1. Handler: enumerate via `tool_catalog` anchored at `_find_plugin_root()` — NOT
   `project_root`. This is the key asymmetry: every existing registry tool anchors at
   `project_root` (e.g. `loop_list` wraps `enumerate_loop_catalog(_loops_dir(project_root))`),
   but `_classify_action` ignores `project_root` entirely for skill resolution, so a
   project-scoped catalog would reintroduce exactly the divergence this tool exists to kill.
   One install answers identically for any `--project-root` (correct for multi-project hosts).
2. Add a `kind` field (`skill` | `command`) to entries — `assemble_tool_catalog` currently
   drops it; consumers need it to render skill vs command sections.
3. Exclude `agents/*.md` — agents are outside `_resolve_content_path`'s lookup domain;
   listing them would break the parity invariant.
4. Read-only Tier 1: no `apply` parameter, absent from `policy.MUTATING_TOOLS`, following
   `queue_list`/`loop_list` conventions (plain JSON list of `{name, kind, description, args?}`).
5. Tolerance: missing/unresolvable root returns an empty list, never an error; broken or
   absent frontmatter still lists (presence is membership); output sorted for determinism.
6. Dedupe name collisions across `skills/<name>/` and `commands/<name>.md` with skill-wins,
   matching `_resolve_content_path`'s skill-first preference.

## Acceptance Criteria

- [ ] `skills_list` appears in `tools/call` over a one-shot initialize handshake and returns
      a plain JSON list with no `apply` argument
- [ ] Every returned entry's `name` classifies `runner: skill` via `queue_add` dry-run
      (classification parity) — encoded as a unit test asserting
      `_classify_action(entry name)` returns `RunnerType.SKILL` in the same process
- [ ] Entries carry `kind` (`skill` | `command`); agents are not listed
- [ ] Names are the lookup names (skills = directory name, commands = file stem)
- [ ] Unresolvable plugin root (e.g. pip-install layout without `skills/`) returns `[]`,
      not an error
- [ ] Result is identical across different `--project-root` values (install-scoped)
- [ ] `python -m pytest scripts/tests/` exits 0 with new coverage

## Notes

- On pip-install deployments the three-parents-up fallback resolves into site-packages,
  which has no `skills/` — the tool returns empty by design. Engine and consumer then agree
  on when skills exist instead of the consumer papering over disagreement with an env pin.
- Consumer migration (ll-console): swap `skills_client`'s read side to
  `mcp_client.call_tool("skills_list")` behind the unchanged `GET /api/skills` shape;
  retire the install.sh probe and `LL_LOOPS_ROOT` first; keep the `CLAUDE_PLUGIN_ROOT` pin
  as belt-and-braces until parity is proven in the wild; add a contract-check round-trip
  (catalog non-empty, every name classifies skill, garbage falls back cmd, dry-run writes
  nothing).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-10T23:35:10 - `e38fd574-1060-4376-8bc3-e25c31d15dce.jsonl`
