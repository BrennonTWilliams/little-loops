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

The ll-mcp registry has no enumeration tool. `queue_add` can classify a name
(`cli.queue._classify_action` → `runner: skill` vs the `cmd` fallback), but nothing in the
registry's tool surface lists which names exist, so a consumer building a picker must
re-implement the engine's plugin-root resolution and scan to reconstruct the catalog
(ll-console does so three times over — see Motivation). The "listed in picker implies
classifies as skill" guarantee holds only because consumers mirror
`skill_expander._resolve_content_path`'s rules by hand and pin `CLAUDE_PLUGIN_ROOT` to keep
the two roots from disagreeing.

## Expected Behavior

`skills_list` is exposed as a read-only Tier 1 tool in the ll-mcp registry (no `apply`
argument, absent from `policy.MUTATING_TOOLS`), returning a plain JSON list of
`{name, kind, description, args?}` for every skill and command in the install, anchored at
the plugin root the server itself resolves (`skill_expander._find_plugin_root()`), wrapping
the existing `tool_catalog.assemble_tool_catalog` enumeration. Every returned name
classifies identically under `queue_add` (same process, same lookup domain as
`_classify_action`); the result is identical for any `--project-root`; an unresolvable
plugin root returns `[]`, never an error.

## Motivation

ll-console (the deployment dashboard) currently duplicates the engine's resolution three
times over:

1. ll-console's install script (`install.sh` under its `deploy/` tree) probes the plugin
   root at install time and renders it into `/etc/ll-console.env` as `LL_LOOPS_ROOT`
2. Its `skills_client.py` scans that root directly (`skills/<name>/SKILL.md` +
   `commands/*.md`) with a hand-rolled frontmatter parser and name-derivation rules that
   mirror `skill_expander._resolve_content_path` (path stem is truth; frontmatter `name:`
   is decorative)
3. Its `queue_client.py` pins `CLAUDE_PLUGIN_ROOT=$LL_LOOPS_ROOT` into every ll-mcp
   spawn so the catalog (console-resolved root) and the classification (engine-resolved
   root, which prefers that same env var) cannot disagree — without the pin, a picker row
   for `ll-commit` could silently classify as `cmd` and queue a broken shell line

The "listed in picker implies classifies as skill" guarantee holds today only via that
mirroring. Moving enumeration into the engine makes it a construction guarantee: same
process, same `_find_plugin_root()` call path, same lookup domain as `_classify_action`.

## Proposed Solution

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

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` — new `_tool_skills_list` handler;
  register in `_TOOL_HANDLERS` and `_TOOLS` (read-only Tier 1 slot beside `loop_list`)
- `scripts/little_loops/tool_catalog.py` — add `kind` to `ToolDefinition`; set it in
  `_skill_entries` / `_command_entries` / `_agent_entries`

### Dependent Files (Callers/Importers)
- `tool_catalog.to_anthropic_tools` consumers — `host_runner.build_anthropic_request`
  (FEAT-2673) and FEAT-2672 deferred loading. `kind` is an additive optional field the
  serializer ignores, so the assembled Anthropic `tools` array is byte-unchanged.
- `mcp_server/policy.py` — `MUTATING_TOOLS` deliberately NOT extended; the split is
  defined solely by that registry, so absence is the read-only marker.

### Similar Patterns
- `_tool_loop_list` (mcp_server/tools.py) — wraps an existing non-printing enumeration
  anchored at a root; the structural template for this handler (plugin-root instead of
  project-root anchoring)
- `_tool_queue_list` / `_tool_capabilities` — plain-JSON read-only returns, no `apply`
- `mcp_server/prompts.py` — also enumerates `skills/` for the prompts surface, but
  recursively (`rglob("SKILL.md")`, FEAT-3137). `skills_list` must NOT follow it:
  parity is with `_resolve_content_path`'s non-recursive `glob("*/SKILL.md")` domain.

### Tests
- `scripts/tests/test_enh_3444_mcp_skills_list.py` (new) — patterns:
  `test_feat_3352_mcp_loop_list.py`, `test_feat_queue_mcp_tools.py`

### Documentation
- `docs/reference/API.md` — the `little_loops.mcp_server` module row enumerates the
  read-only tool roster; add `skills_list`

### Configuration
- N/A — no config knob; tool presence is registry-level

## Implementation Steps

1. Add `kind` to `ToolDefinition` and set it in the three entry builders
   (`tool_catalog.py`); confirm `to_anthropic_tools` output is unchanged.
2. Add `_tool_skills_list` in `mcp_server/tools.py` — anchor at
   `skill_expander._find_plugin_root()`, exclude `kind: "agent"`, dedupe skill-wins,
   `{name, kind, description, args?}` rows — and register it in `_TOOL_HANDLERS` +
   `_TOOLS` as read-only Tier 1.
3. New test module: classification parity (`_classify_action` on every returned name),
   `[]` on unresolvable root, identical output across `--project-root` values, `kind`
   present, agents absent.
4. Update the `docs/reference/API.md` tool roster; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 - closes the only gap in the registry's queue workflow (`queue_add`
  can classify but nothing enumerates); unblocks retiring ll-console's three-way
  plugin-root mirroring.
- **Effort**: Small - thin exposure of the existing `assemble_tool_catalog`; only new
  logic is the `kind` field and skill-wins dedupe.
- **Risk**: Low - additive read-only tool; `ToolDefinition.kind` is optional and ignored
  by serialization, so Anthropic-request assembly and the prompts surface are untouched.
- **Breaking Change**: No

## Scope Boundaries

- ll-console's migration (swap `skills_client` read side to `skills_list`, retire the
  `LL_LOOPS_ROOT` probe) — consumer-side follow-up work, not this issue
- Listing `agents/*.md` — outside `_resolve_content_path`'s lookup domain; including
  them would break the classification-parity invariant
- Any project-root scoping, filtering, or config knob for the catalog — one install,
  one answer
- Changes to `_classify_action` or queue classification semantics — this issue exposes
  the existing domain, it does not alter it
- Returning skill/command bodies or frontmatter beyond `description`/`args` — catalog
  metadata only (bodies already exist via the `ll://` resource and prompts surfaces)

## Program Design

### Types

- `ToolDefinition.kind: str` — `"skill" | "command" | "agent"`, default `""` so existing
  frozen-dataclass constructions are unchanged

### Signatures

- `_tool_skills_list(_arguments: dict[str, Any], *, project_root: Path) -> list[dict[str, Any]]` — read-only Tier 1 handler; `project_root` accepted but deliberately unused (install-scoped)
- `assemble_tool_catalog(project_root: Path) -> list[ToolDefinition]` — signature unchanged; entries now carry `kind`
- `_find_plugin_root() -> Path` — reused as-is (`skill_expander`), the same resolver `_classify_action`-side lookups go through

### Call Path

`handle_call_tool` (mcp_server/tools.py) -> `_TOOL_HANDLERS["skills_list"]` -> `_tool_skills_list` -> `skill_expander._find_plugin_root()` + `tool_catalog.assemble_tool_catalog` -> `_skill_entries` / `_command_entries`

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
- `/ll:format-issue` - 2026-09-10T23:42:00 - `d0293195-1c81-4d81-ac17-fa584ee4566b.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:35:10 - `e38fd574-1060-4376-8bc3-e25c31d15dce.jsonl`
