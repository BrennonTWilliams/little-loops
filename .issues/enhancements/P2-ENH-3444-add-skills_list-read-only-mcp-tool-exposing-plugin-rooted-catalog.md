---
id: ENH-3444
type: ENH
title: Add skills_list read-only MCP tool exposing plugin-rooted catalog
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:35:03Z'
learning_tests_required:
- mcp
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
   Add `args_hint: str | None` alongside it: the raw frontmatter `args`/`argument-hint`
   string is currently folded into `input_schema.properties.args.description` by
   `_make_input_schema` and discarded, so the handler cannot produce the promised `args`
   field without reverse-engineering the schema shape. Carry the raw hint on the
   dataclass instead. Output rule: the `args` key is **omitted** (not `null`) when the
   hint is absent. 79 of the install's skills/commands carry a hint, so this is most of
   the catalog.
3. Exclude `agents/*.md` — agents are outside `_resolve_content_path`'s lookup domain;
   listing them would break the parity invariant.
4. Read-only Tier 1: no `apply` parameter, absent from `policy.MUTATING_TOOLS`, following
   `queue_list`/`loop_list` conventions (plain JSON list of `{name, kind, description, args?}`).
5. Tolerance: missing/unresolvable root returns an empty list, never an error; broken or
   absent frontmatter still lists (presence is membership). Sort order is **`(kind, name)`**
   — skills first, then commands, each sorted by name. This is exactly the order
   `assemble_tool_catalog` already produces (it extends skills, then commands, each from a
   `sorted()` glob), so no re-sort is needed, but the order is now part of the contract.
   Log the resolved plugin root at `debug` level so an empty result is diagnosable
   ("no skills" vs "wrong root").
6. Dedupe name collisions across `skills/<name>/` and `commands/<name>.md` with skill-wins,
   matching `_resolve_content_path`'s skill-first preference. First-seen-wins equals
   skill-wins **only because** `assemble_tool_catalog` emits skills before commands — pin
   that with a test rather than relying on it silently, or dedupe by explicit kind
   preference. No collision exists in the install today.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` — new `_tool_skills_list` handler;
  register in `_TOOL_HANDLERS` and `_TOOLS` (read-only Tier 1 slot beside `loop_list`)
- `scripts/little_loops/tool_catalog.py` — add `kind` and `args_hint` to `ToolDefinition`;
  set both in `_skill_entries` / `_command_entries` (`args_hint=None` for `_agent_entries`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/__init__.py` — package docstring tool counts
  ("eight coarse read-only tools, seven guarded mutation tools") are a third count
  site beyond tools.py:1-3 and tools.py:1232; must be re-counted when the roster
  grows [Agent 2 finding]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_server.py` — WILL BREAK: `test_no_unguarded_mutating_tool_is_advertised`
  (lines 277-320) hard-codes the 8-name `read_only` tier-1 set (lines 292-301); any advertised tool
  outside it must be in `MUTATING_TOOLS` or `TASK_STARTING_TOOLS` — add `"skills_list"` to the set
  (the identical edit FEAT-3352/FEAT-3234 made for `loop_list`/`queue_*`) [Agent 2+3 finding]
- `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — WILL BREAK:
  `test_ac1_tier1_tools_keep_their_shape_and_ordering` (lines 153-176) asserts
  `names[:8] == TIER1_NAMES` then `names[8:]` (minus TASK_STARTING_TOOLS) equals
  `sorted(MUTATING_NAMES)` — `skills_list` at position 9 lands in the tier-2 slice and fails the
  comparison; extend `TIER1_NAMES` (lines 117-126) and bump both slices to `[:9]`/`[9:]` (the
  `tools[:8]` annotations-None loop at lines 171-174 also implies `skills_list` must be registered
  with `annotations=None`) [Agent 2+3 finding]
- `scripts/tests/test_tool_catalog.py` — extend, not just preserve: add `kind` assertions to the
  three assembly test classes (`TestAssembleToolCatalogSkills`/`...Commands`/`...Agents`) and a
  serializer-ignores-`kind` case extending
  `TestToAnthropicTools::test_serializes_required_keys_only_when_no_cache_control` (lines 179-193);
  no entry is ever constructed *with* `kind` set today, so "populated `kind` stays
  serializer-invisible" is un-pinned [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py:86-107` — convention reference, no edit: patches
  the module attribute `little_loops.tool_catalog.assemble_tool_catalog` because `cli/doctor.py`
  imports it function-locally; if `_tool_skills_list` follows the house function-local-import
  style, its tests must patch the module attribute, not an import site in `mcp_server.tools`
  [Agent 1+3 finding]
- Placement constraint: `test_mcp_server.py:58-86` pins `names[:5]` (five read tools first) — the
  planned Tier-1 slot beside `loop_list` (position 9) satisfies it; keep `skills_list` at index ≥ 5

### Documentation
- `docs/reference/API.md` — the `little_loops.mcp_server` module row enumerates the
  read-only tool roster; add `skills_list`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (second, distinct edit) — `## little_loops.tool_catalog` →
  `### ToolDefinition` constructor signature block (lines 10751-10758) and Fields table
  (lines 10762-10769) must gain a `kind` row (`str`, default `""`, set per entry builder)
  [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-mcp` section roster sentence and counts ("sixteen coarse
  tools … Eight read: …", lines 5357-5360) and the "eight read-only tools carry no annotations"
  sentence (lines 5385-5387); the tool-parameters table (line 5401 onward) needs a row only if
  `skills_list` grows parameters (the planned signature takes `_arguments` ignored — likely no
  row, but the counts change) [Agent 2 finding]
- `docs/guides/MCP_SERVER_GUIDE.md` — three spots: the `| **Tools (read)** |` overview table row
  (line 33), the `### The eight read tools, end to end` heading (line 204; per-tool walkthrough
  section where FEAT-3352 added its `loop_list` walkthrough at line 352), and the "eight read-only
  tools carry no annotations at all" sentence (lines 588-589) [Agent 1+2 finding]
- `CHANGELOG.md` — release-prep coupling only (FEAT-3352 precedent at line 189); add the entry at
  release prep under a concrete `## [X.Y.Z] - DATE` section, never `[Unreleased]` [Agent 2 finding]

### Configuration
- N/A — no config knob; tool presence is registry-level

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed N/A: no schema or config validates the MCP tool roster or `ToolDefinition` shape —
  `config-schema.json`'s `mcp` block (lines 612-660) covers `transport_policy`/`http` only;
  `deferred_tools.threshold` is index-based over the same catalog and `kind` adds no entries and
  reorders nothing, so thresholds are unaffected [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Anti-anchor constraint: `mcp_server/server.py:_resolve_skills_root()` (server.py:40-79) is NOT a valid anchor for this tool. It resolves a 4-candidate chain (`LL_MCP_SKILLS_ROOT` env → `CLAUDE_PLUGIN_ROOT/skills` → in-package wheel copy via `importlib.resources` → `_find_plugin_root()/skills`, each `.is_dir()`-validated) and serves the prompts surface (server.py:195). `_classify_action` consults none of the first three candidates, so a `_resolve_skills_root`-anchored catalog would list names that cannot classify `runner: skill`. Bare `skill_expander._find_plugin_root()` is the only parity-preserving anchor.
- `cli/doctor.py:258` (`_skills_commands_data`, doctor.py:253-261) is the only production caller of `assemble_tool_catalog` today — passes `Path.cwd()` and consumes only `len(entries)`; an additive optional `kind` field cannot affect it.
- Tier-1 roster conventions: `_TOOLS` list order is the entirety of the ordering guarantee (tools.py:771-772); tier-1 entries keep `annotations=None` so `tools/list` shape is unchanged — pinned by `test_feat_3352_mcp_loop_list.py:303-312`. The `handle_list_tools` docstring says "the fixed sixteen-tool catalog" (tools.py:1232) and the module docstring carries the same count (tools.py:1-3) — both count references must be updated when the roster grows.
- Return-shape fact: a list payload travels in `content[0].text` only; `structured_content` is attached only when the payload is a dict (tools.py:1325-1334). `skills_list` returns a list, so consumers parse `content[0].text`.
- `_find_plugin_root()` (skill_expander.py:25-35) honors exactly one env var (`CLAUDE_PLUGIN_ROOT`), returns it unconditionally with no `.is_dir()` validation, else falls back to three-parents-up from `skill_expander.py` — never consults `project_root`, `LL_MCP_PROJECT_ROOT`, config, or cwd. "Unresolvable root" therefore includes an env var pointing at a nonexistent dir.
- Classification nuance behind the parity AC: `_resolve_content_path` (skill_expander.py:38-52) resolves `commands/<name>.md` too, so command names also classify `RunnerType.SKILL` (not CMD) — the AC's `_classify_action(...) is RunnerType.SKILL` assertion holds for both kinds. Precedence caveat: the LOOP branch runs first via `BRConfig(Path.cwd())` (queue.py:183-195), so a skill/command name colliding with a loop in the *consumer's* cwd project classifies LOOP before the skill branch is reached.
- Grounded capability claim (searched by name and by capability repo-wide): no existing MCP tool enumerates skills or commands — `_tool_skills_list`/`skills_list` have zero occurrences in the tool surface; the only `skills_list` string hits are an unrelated local variable in `cli/verify_triggers.py:582-606`, this issue file, and a decision fragment.

## Implementation Steps

1. Add `kind` to `ToolDefinition` and set it in the three entry builders
   (`tool_catalog.py`); confirm `to_anthropic_tools` output is unchanged.
2. Add `_tool_skills_list` in `mcp_server/tools.py` — anchor at
   `skill_expander._find_plugin_root()`, exclude `kind: "agent"`, dedupe skill-wins,
   `{name, kind, description, args?}` rows — and register it in `_TOOL_HANDLERS` +
   `_TOOLS` as read-only Tier 1.
3. New test module: classification parity (`_classify_action` on every returned name),
   `[]` on unresolvable root, identical output across `--project-root` values, `kind`
   present, `args` present iff a hint exists, `(kind, name)` ordering, skill-wins dedupe
   on a tmp root with a deliberate collision, agents absent.
   **The parity test must `monkeypatch.chdir(tmp_path)`**: `_classify_action` checks
   `BRConfig(Path.cwd()).loops.loops_dir` for a loop of the same name *before* the skill
   branch, so a `.loops/<name>.yaml` in whatever directory pytest runs from would flip a
   listed name to `RunnerType.LOOP` and fail the test. No collision exists today; the
   chdir keeps it from regressing.
4. Update the `docs/reference/API.md` tool roster; run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_mcp_server.py` — add `"skills_list"` to the `read_only` tier-1 set in
  `test_no_unguarded_mutating_tool_is_advertised` (lines 292-301) or the guard fails on registration
- Update `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — extend `TIER1_NAMES` (lines 117-126)
  and bump the slice arithmetic `names[:8]`/`names[8:]`/`tools[:8]` to 9 in
  `test_ac1_tier1_tools_keep_their_shape_and_ordering` (lines 153-176)
- Extend `scripts/tests/test_tool_catalog.py` — `kind` assertions in the three assembly classes;
  serializer-ignores-`kind` case in `TestToAnthropicTools`
- Update `scripts/little_loops/mcp_server/__init__.py` — re-count the package-docstring tool
  counts alongside tools.py:1-3 and tools.py:1232
- Update `docs/reference/CLI.md` — `### ll-mcp` roster sentence/counts (lines 5357-5360) and
  read-only annotations sentence (lines 5385-5387)
- Update `docs/guides/MCP_SERVER_GUIDE.md` — read-tools table row (line 33), "eight read tools"
  heading + per-tool walkthrough (lines 204, 352), annotations sentence (lines 588-589)
- Update `docs/reference/API.md` — `ToolDefinition` Fields table gains the `kind` row
  (lines 10751-10769), distinct from the roster-row edit in Step 4
- `CHANGELOG.md` — entry at release prep, under a concrete version section (not `[Unreleased]`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Fixture-isolation seam already exists: `test_mcp_server.py:826-888` patches `"little_loops.skill_expander._find_plugin_root"` with a lambda (plus `importlib.resources.files`) to isolate the server from the real install. Because `queue.py:165` imports `_find_plugin_root` function-locally at call time, patching the `little_loops.skill_expander` module attribute also redirects `_classify_action` — a same-process classification-parity test against a tmp plugin root works through that single patch.
- MCP tool tests use a full in-process handshake, not direct handler calls: `pytest.importorskip("mcp")` at module top, `anyio.run` wrapping `async with Client(build_server(transport="stdio", project_root=...))` + `client.call_tool(...)`; payload helper asserts `not result.is_error` then `json.loads(result.content[0].text)` (test_feat_3352_mcp_loop_list.py:25-33).
- `ToolDefinition` is `@dataclass(frozen=True)` (tool_catalog.py:28-41); existing tests construct it with 3 positional args (test_tool_catalog.py:180-212) — the new `kind` field must carry a default for those constructions to keep working.

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
- `ToolDefinition.args_hint: str | None` — raw frontmatter `args`/`argument-hint` string,
  default `None`; the source of the handler's `args` output field. `to_anthropic_tools`
  ignores it (the hint is already baked into `input_schema` by `_make_input_schema`)
- Handler row: `{"name": str, "kind": "skill" | "command", "description": str, "args": str}`
  with `args` omitted when `args_hint` is `None`; rows ordered by `(kind, name)`

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
- [ ] Entries carry `args` (the raw frontmatter hint) when one exists and omit the key
      otherwise; `to_anthropic_tools` output is byte-unchanged
- [ ] Rows are ordered by `(kind, name)`; a `skills/<n>/` + `commands/<n>.md` collision on a
      tmp root yields one `kind: skill` row
- [ ] Names are the lookup names (skills = directory name, commands = file stem)
- [ ] Unresolvable plugin root (e.g. pip-install layout without `skills/`) returns `[]`,
      not an error
- [ ] Result is identical across different `--project-root` values (install-scoped)
- [ ] `python -m pytest scripts/tests/` exits 0 with new coverage

## Notes

- On pip-install deployments the three-parents-up fallback resolves into site-packages,
  which has no `skills/` — the tool returns empty by design. Engine and consumer then agree
  on when skills exist instead of the consumer papering over disagreement with an env pin.
  **Caveat**: the wheel *does* ship a skills copy inside the package (`hatch_build.py`,
  BUG-3177) for the prompts surface, so on a pypi install `prompts/list` shows skills while
  `skills_list` returns `[]` and `queue_add` classifies every skill name as `cmd`. Parity
  holds, but the picker is empty. The `CLAUDE_PLUGIN_ROOT` pin is therefore
  **load-bearing** for pypi installs, not belt-and-braces — it stays unless
  `_find_plugin_root()` grows a wheel-copy fallback (out of scope here; would need to keep
  `_classify_action` in lockstep).
- Optional design alternative, not adopted: a dict payload `{plugin_root, entries}` would
  make `[]` diagnosable and would also gain `structured_content` (lists never do, see
  tools.py:1325-1334). Rejected to keep the `loop_list`/`queue_list` plain-list convention;
  the debug-level log of the resolved root (Proposed Solution step 5) covers diagnosis.
- Consumer migration (ll-console): swap `skills_client`'s read side to
  `mcp_client.call_tool("skills_list")` behind the unchanged `GET /api/skills` shape;
  retire the install.sh probe and `LL_LOOPS_ROOT` first; keep the `CLAUDE_PLUGIN_ROOT` pin
  (required on pypi installs per the caveat above); add a contract-check round-trip
  (catalog non-empty, every name classifies skill, garbage falls back cmd, dry-run writes
  nothing).

## Verification Notes

_Verified by `/ll:verify-issues` — 2026-09-11 — graph: provider=`codegraph` freshness=`fresh`:_

- **Verdict: VALID** — all current-state claims checked against HEAD; none refuted.
- `tool_catalog.py` claims exact: `ToolDefinition` frozen dataclass at lines 28-41 with no
  `kind` field; `_skill_entries`/`_command_entries` use directory-name/file-stem naming;
  `to_anthropic_tools` (lines 158-186) serializes only name/description/input_schema/
  cache_control/defer_loading, so an additive `kind` is serializer-invisible as claimed.
- `skill_expander.py` claims exact: `_find_plugin_root()` (lines 25-35) honors only
  `CLAUDE_PLUGIN_ROOT`, returns it unvalidated, else three-parents-up;
  `_resolve_content_path` (lines 38-52) tries `skills/<name>/SKILL.md` before
  `commands/<name>.md` (skill-first, and command names classify `RunnerType.SKILL`).
- `queue.py` claims exact: function-local `_find_plugin_root` import at line 165; LOOP
  branch via `BRConfig(Path.cwd())` at line 183 runs before the skill branch (precedence
  caveat as stated).
- `mcp_server/server.py` `_resolve_skills_root()` (4-candidate `.is_dir()`-validated chain)
  and `policy.py` `MUTATING_TOOLS` (line 55) verified; anti-anchor argument holds.
- `tools.py` anchors exact: module docstring counts (lines 1-3), `_TOOLS` ordering comment
  (771-772), `handle_list_tools` "fixed sixteen-tool catalog" (line 1232),
  `structured_content` dict-only attachment (line 1333).
- Test-will-break claims confirmed at cited lines: `test_mcp_server.py:292-301` read-only
  set, `names[:5]` pin at ~75, `_find_plugin_root` patch seam at 826-888;
  `test_feat_3149_mcp_mutation_tools.py:117-126` TIER1_NAMES and `[:8]`/`[8:]` slices in
  153-176. Doc anchors (CLI.md 5357-5360/5385-5387/5401, MCP_SERVER_GUIDE.md 33/204/352/
  588-589, API.md 10751-10758/10762-10769, config-schema.json 612+, CHANGELOG.md:189) all
  verified.
- Negative claims confirmed by repo-wide grep (corroborated via codegraph `callers-of`):
  zero `skills_list`/`_tool_skills_list` occurrences in the tool surface;
  `assemble_tool_catalog`'s only production caller is `cli/doctor.py:258`.
- Proposal consequence check (ENH-3250) passed: anchoring `assemble_tool_catalog` at
  `_find_plugin_root()` composes correctly (plugin_root/skills etc.), no exception-path
  or fixture-invalidation consequence beyond the tests already listed, ACs cover the
  named integration points.
- One cosmetic nit, conclusion unaffected: existing test constructions at
  `test_tool_catalog.py:210-211` pass the three fields as **keyword** args, not
  "3 positional args" as the research finding says — either way `kind` needs a default.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-11T00:41:10 - `ec1ed584-4b1f-463d-8cf0-4b21573e9eeb.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:37:59 - `20b69acd-df8f-4639-a911-4c4d70df244e.jsonl`
- `/ll:confidence-check` - 2026-09-11T00:11:14 - `bcda08f4-0e66-4e79-bbb6-35f872f2d3be.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:03:17 - `c2ff98c2-d636-4b9e-88bd-7e3ac0c1f8a7.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:00:07 - `7ab0ae92-3343-45f8-9d51-058b5423b861.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:49:39 - `7ee27d53-14b5-4247-8a45-3ace1bb3ba2a.jsonl`
- `/ll:format-issue` - 2026-09-10T23:42:00 - `d0293195-1c81-4d81-ac17-fa584ee4566b.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:35:10 - `e38fd574-1060-4376-8bc3-e25c31d15dce.jsonl`
