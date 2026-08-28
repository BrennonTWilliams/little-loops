---
id: FEAT-3352
type: FEAT
title: Add loop_list catalog tool to ll-mcp
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T18:42:31Z'
learning_tests_required:
- mcp
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# FEAT-3352: Add loop_list catalog tool to ll-mcp

## Summary

Add a tier-1 read tool `loop_list` to `ll-mcp` that returns the project's loop
catalog (built-ins plus `.loops/`, with the same override and visibility semantics
`ll-loop list` applies), so an external director agent can discover loops as an MCP
primitive instead of shelling out to the CLI.

Implementing it requires first extracting a non-printing catalog-enumeration helper
out of `cmd_list` — that extraction is step 1 of this issue, not a separate one.

## Current Behavior

`ll-mcp` exposes 15 tools across three tiers (`mcp_server/tools.py`, `_TOOLS` at
line 709, `_TOOL_HANDLERS` at line 684):

- tier-1 read: `issues_query`, `issue_get`, `history_search`, `deps_check`,
  `capabilities`, `queue_list`, `queue_get`
- tier-2 guarded mutation: `issue_capture`, `issue_set_status`, `issue_link`,
  `issue_append_log`, `queue_add`, `queue_remove`, `queue_requeue`
- tier-3 run control: `loop_start` (plus the `tasks/*` methods)

`loop_start` accepts a loop *name* but there is no way to discover valid names over
MCP. A caller must either already know the name or shell out to `ll-loop list`.

There is no reusable loop-catalog function to wrap. `cmd_list`
(`scripts/little_loops/cli/loop/info.py:104`) is argparse-shaped and prints as it
goes: it interleaves `print` and `print_json` calls with the enumeration, the
built-in/project override resolution, and the `--category` / `--label` /
`--visibility` filtering. The only reusable primitives underneath it are
`get_builtin_loops_dir()`, `is_runnable_loop()`, `_load_loop_meta()`, and the
private `_rel_key()`.

## Expected Behavior

A `tools/list` call reports 16 tools, including `loop_list`. Calling `loop_list`
returns the project's loop catalog — project loops from `.loops/` first, then
built-ins not shadowed by a same-named project loop — each entry carrying its name,
path, description, category, labels, and visibility, with the asymmetric `built_in`
key (present-and-`True` only for built-ins) exactly as `ll-loop list --json` emits
it. Optional
`category` / `label` / `visibility` arguments filter the result the same way the
equivalent `ll-loop list` flags do, and the loops dir is resolved from the server's
`project_root` rather than cwd.

An external director agent can therefore discover a valid loop name and feed it
straight to `loop_start` without shelling out.

## Motivation

`ll-mcp` is becoming the canonical primitive surface for an external director agent.
Loop discovery is the one gap that forces that agent back to the CLI for a read-only
operation the server should answer directly.

The extraction also removes a latent duplication hazard: without it, `loop_list`
would re-implement override resolution and visibility filtering, and the MCP copy
would drift from the CLI's.

## Use Case

**Who**: An external director agent driving `ll-mcp` as its primitive surface.

**Context**: The agent has decided to start a loop via the `loop_start` tool but
does not already know a valid loop name, and today the only way to find one is to
shell out to `ll-loop list` — breaking the MCP-only workflow.

**Goal**: Discover the project's loop catalog (name, description, category,
labels, visibility) entirely over MCP, then pick a name to pass to `loop_start`.

**Outcome**: The agent calls `loop_list`, optionally filtered by `category`,
`label`, or `visibility`, gets back the same catalog `ll-loop list` would show,
and feeds the chosen name straight into `loop_start` without leaving the MCP
transport.

## Proposed Solution

Extract the catalog enumeration out of `cmd_list` into a non-printing function that
returns structured data, have `cmd_list` render that data, and add a thin tier-1 MCP
handler over the same function. One implementation, two presentation layers — the
FEAT-3149 shape applied to a read instead of a write.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — extract the enumeration from `cmd_list`
  (line 104); leave the `--running` / `--status` / `--all-runs` branch alone
- `scripts/little_loops/mcp_server/tools.py` — add `_tool_loop_list`, register in
  `_TOOL_HANDLERS` (line 684) and `_TOOLS` (line 709)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — dispatches to `cmd_list`
- `scripts/little_loops/mcp_server/tasks.py` — `_loops_dir(project_root)`, the
  project-root-aware loops-dir resolver to reuse
- Anything else importing `cmd_list` (grep before editing; expected to be dispatch
  only)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state runs
  `ll-loop list --json --visibility public` and reads each item's `name`,
  `category`, and `loop.get('built_in', False)`. The JSON serializer
  (`LoopCatalogEntry.to_json_item()`) must preserve the current asymmetric-key
  convention (`built_in` present-and-`True` only for built-ins, absent for
  project loops) or this state breaks silently. (The convention lives in the
  serializer, not in `enumerate_loop_catalog()` itself, whose internal entries
  keep the symmetric `builtin: bool` the human rendering needs.)
- `scripts/little_loops/loops/lib/composer.yaml` — same `ll-loop list --json
  --visibility public` pattern and the same three keys, in its `discover_loops`
  fragment.
- `scripts/little_loops/loops/workflow-generator.yaml` — `promote` state runs
  `ll-loop list --json` (no `--visibility` filter) and extracts `name` for
  collision detection.
- `scripts/tests/test_loop_router.py`, `scripts/tests/test_loop_composer.py` —
  assert the `--visibility public` flag is present in the above YAML actions.
- `scripts/tests/test_builtin_loops.py::test_promote_never_overwrites_on_collision`,
  `scripts/tests/test_rn_build.py` — exercise the `ll-loop list --json`
  contract end-to-end.

### Similar Patterns
- `apply_status_transition` / `apply_link` (FEAT-3149) — the extract-a-non-printing-
  function precedent for MCP tool handlers
- `_tool_loop_start` in `mcp_server/tools.py` — the `redirect_stdout` fallback for
  when extraction is impractical; not needed here
- `_tool_queue_list` / `_tool_queue_get` — the tier-1 read handler shape to copy

### Tests
- `scripts/tests/` — existing `ll-loop list` CLI tests must stay green unchanged
  (that is the regression signal for the extraction)
- The ll-mcp tool tests (the issue-tool and queue-tool tests are the pattern) — add
  `loop_list` coverage including the project-root and override cases

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_server.py::test_no_unguarded_mutating_tool_is_advertised`
  (lines 277-319) — hardcodes a `read_only = {...}` set of the 7 current tier-1
  names; `loop_list` must be added to this set or the test fails once it's
  registered without being in `MUTATING_TOOLS`/`TASK_STARTING_TOOLS` — **will
  break, must update**. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_feat_3149_mcp_mutation_tools.py` (lines 107-125, 152-175)
  — `TIER1_NAMES` is a 7-entry list asserted via `names[:7] == TIER1_NAMES`;
  needs the 8th entry (`loop_list`) plus both slice indices updated
  (`[:7]`→`[:8]`, `[7:]`→`[8:]`) — **will break, must update**. [Agent 2 + Agent 3
  finding]
- `scripts/tests/test_issue_parser.py::_ALLOWLIST["mcp_server/tools.py"]`
  (lines 4885-4888) — a line-number-keyed allowlist for JSON-schema
  `pattern: "^P[0-5]$"` hits; line 849 (inside `issue_capture`'s schema) shifts
  down once the new `Tool()` entry is inserted after `queue_get` (~line 818),
  which `test_allowlist_entries_still_exist` (line 4929) will flag as stale —
  **will break, must update to the new line number**. [Agent 3 finding]
- New test file needed (no existing `loop_list`/`enumerate_loop_catalog`
  coverage exists anywhere) — follow the combined pattern of
  `scripts/tests/test_feat_queue_mcp_tools.py` (tier-1 tool test shape,
  `_payload()`/`_make_project()` helpers), the project-root regression in
  `scripts/tests/test_enh_3171_mcp_project_root.py:107`
  (`test_loop_start_resolves_loops_dir_from_explicit_root` — assert on
  *content*, not just `is_error`), and
  `scripts/tests/test_json_output_contracts.py::TestLoopListJsonContract`
  (`_cmd_list_json` helper, lines 47-74) as the reference payload to diff the
  MCP tool's output against. [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py` — full existing `cmd_list` coverage
  that must stay green as the extraction's regression signal:
  `TestCmdList` (:690), `TestLoopListCategoryFilter` (:1023),
  `TestLoopListVisibilityFilter` (:1192, incl. `test_all_shows_everything` at
  :1235 — the closest existing "visibility=all" pattern), `TestLoopListFormatting`
  (:1556), `TestCmdListENH2539Polished` (:2344), `TestCmdListENH2572ScanningFirst`
  (:3018, incl. `test_project_loops_pinned_first_and_exclusive` at :3060 — the
  override-shadowing pattern), `TestCmdListRunningJson` (:3904),
  `TestCmdListRunningAllowlistBUG3232` (:3988). [Agent 3 finding]
- `scripts/tests/test_ll_loop_parsing.py:586`, `scripts/tests/test_cli_loop_dispatch.py`
  (lines 202, 893-929), `scripts/tests/test_cli_loop_lifecycle.py::TestCmdListMultiInstance`
  (:2688) — patch/dispatch-level coverage of `cmd_list` via argv; must stay
  green. [Agent 1 + Agent 3 finding]

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — add `loop_list` to the read-tools inventory
  table (lines 32-33)
- `docs/reference/API.md` — `little_loops.mcp_server` module reference
- `docs/reference/CLI.md` — only if the extraction changes any `ll-loop list` flag
  behavior, which it should not

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4855-4857` — states "fifteen coarse tools ... Seven
  read: `issues_query`, `issue_get`, `history_search`, `deps_check`,
  `capabilities`, `queue_list`, `queue_get`" — becomes "sixteen"/"eight read"
  with `loop_list` added. [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:1-2` — module docstring says "seven
  coarse read-only tools ... plus seven guarded mutation tools"; update to
  eight. [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:1139` — `handle_list_tools`
  docstring says "the fixed fifteen-tool catalog"; update to sixteen.
  [Agent 3 finding]
- `docs/reference/json-output-contracts.md` — has an `ll-loop list --json`
  section documenting the required-field contract
  (`scripts/tests/test_json_output_contracts.py:45`,
  `REQUIRED_FIELDS = {"name", "path", "category", "labels", "visibility",
  "description"}`) that `enumerate_loop_catalog()` and the `loop_list` tool
  payload must both satisfy. [Agent 2 + Agent 3 finding]

_Review pass — 2026-08-28 — two additional stale-count sites:_
- `docs/reference/CLI.md:4883` — "the seven read-only tools carry no
  annotation" → eight.
- `docs/guides/MCP_SERVER_GUIDE.md:486` — "…the seven [read-only tools]" →
  eight (the mutating-seven count on that same line stays correct).

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- The extract-a-non-printing-function precedent (FEAT-3149) keeps the extracted
  function in the *same module* as the `cmd_*` it came from, as a module-level
  function returning a `@dataclass` — never printing itself; validation specific
  to argparse/CLI stays in `cmd_*`. Evidence: `apply_status_transition()`
  (`scripts/little_loops/cli/issues/set_status.py:93`, returns `StatusTransition`)
  and `apply_link()` (`scripts/little_loops/cli/issues/link.py:119`, returns
  `LinkResult`).
- Existing tier-1 read handlers (`_tool_queue_list`/`_tool_queue_get`,
  `scripts/little_loops/mcp_server/tools.py:478`/`:492`) share this shape:
  signature `(arguments: dict[str, Any], *, project_root: Path) -> Any` with
  local (in-function) imports, `raise ValueError(...)` for missing/invalid args
  or not-found results (never a hand-built `is_error` dict — `handle_call_tool`'s
  except-branch converts the raise), and `project_root` threaded straight into
  the underlying call's own root-kwarg rather than re-resolved from `Path.cwd()`.
- Registration order in `_TOOLS`/`_TOOL_HANDLERS` (`mcp_server/tools.py:684`/
  `:709`) is a documented source-order literal; the file-level comment states
  tier-1 entries deliberately keep `annotations=None` (only tier-2's 4 entries
  set `annotations=types.ToolAnnotations(...)`, starting line 824).
- Two existing test files already establish the exact "project-root vs. separate
  cwd" test shape this issue's AC calls for: `scripts/tests/test_feat_queue_mcp_tools.py:155`
  (`test_queue_tools_anchor_at_project_root_not_cwd`) and
  `scripts/tests/test_enh_3171_mcp_project_root.py:107`
  (`test_loop_start_resolves_loops_dir_from_explicit_root` — the closer analog,
  since it already resolves `.loops/` specifically; its comment records a
  BUG-3180 false-positive where an `is_error` assertion alone was insufficient
  and the test also had to assert a path/identity signal). No such
  project-root-override test exists yet for a tier-1 (non-mutating) tool
  specifically — `test_feat_3149_mcp_mutation_tools.py` only tests tier-2 tools
  against a single chdir'd root.

## Program Design

### Types

- `LoopCatalogEntry: @dataclass` — `name: str`, `path: Path`, `builtin: bool`
  (symmetric, always present — this is the *internal* shape the human-rendering
  branch needs for section splits and badges), `description: str`,
  `category: str`, `labels: list[str]`, `visibility: str`; plus a
  `to_json_item() -> dict[str, Any]` method producing the *wire* shape — `path`
  stringified, `builtin` dropped, asymmetric `built_in: True` added only for
  built-ins — matching what `ll-loop list --json` emits today
  (`cli/loop/info.py:289-302`). Both presentation layers (`cmd_list --json` and
  `_tool_loop_list`) call this one serializer so the two surfaces cannot drift.
  (Dataclass, not TypedDict, per the FEAT-3149 precedent recorded in Codebase
  Research Findings below.)
- `LoopCatalog: @dataclass` — `entries: list[LoopCatalogEntry]`,
  `hidden_counts: dict[str, int]` — the enumeration result. `hidden_counts`
  feeds `cmd_list`'s human footer and `_category_rollup`
  (`cli/loop/info.py:373,389-393`) and cannot be reconstructed from a filtered
  entry list. **Tally semantics** (review pass 2026-08-28): today
  `hidden_counts` is tallied only on the two public-only branches
  (`info.py:262-267, 275-280`); the `--internal`/`--examples` subset branch
  hides public loops but tallies nothing. Preserving rule for the set-based
  signature: tally hidden counts only when `visibilities == {"public"}`, leave
  zeros otherwise. Filter order (category → label → visibility) must also be
  preserved — `hidden_counts` reflects only loops that survived the
  category/label filters, which is what keeps the human footer byte-identical.

### Signatures

- `enumerate_loop_catalog(*, loops_dir: Path, category: str | None = None, label: list[str] | None = None, visibilities: set[str] | None = None, builtin_only: bool = False) -> LoopCatalog`
  (new, `cli/loop/info.py`) — the non-printing extraction from `cmd_list`.
  `visibilities` is a *set* of tiers (`None` = show all): a single string cannot
  express the legacy `--internal --examples` combination, which selects
  `{internal, example}` (`info.py:268-274`). `cmd_list` maps its flags to a set;
  the MCP handler maps its `visibility` enum (`public`/`internal`/`example` →
  one-element set, `all` → `None`). `builtin_only` is required because
  `--builtin` both skips project loops *and* un-shadows same-named built-ins
  (empty `project_names` — `info.py:190,202-204`); it is not reproducible by
  post-filtering the combined list. Label matching is case-insensitive
  any-match (`info.py:243-249`) — preserve deliberately.
  **Legacy-flag precedence stays in `cmd_list`** (review pass 2026-08-28):
  `--all` beats `--visibility public` when both are set (`show_all` is checked
  first — `info.py:255-261`), while `--visibility public` beats
  `--internal`/`--examples`. The flag→set mapping in `cmd_list` must preserve
  this checking order; the extraction must not reorder it.
- `_tool_loop_list(arguments: dict, *, project_root: Path) -> list[dict[str, Any]]`
  (new, `mcp_server/tools.py`) — tier-1 handler wrapping the same function,
  returning `[e.to_json_item() for e in catalog.entries]`

### Call Path

`cmd_list` (`cli/loop/info.py:104`) -> `enumerate_loop_catalog()` ->
`get_builtin_loops_dir()` / `is_runnable_loop()` / `_load_loop_meta()` / `_rel_key()`

`_tool_loop_list` (`mcp_server/tools.py`) -> `_loops_dir(project_root)`
(`mcp_server/tasks.py`) -> `enumerate_loop_catalog()`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- No `TypedDict` return-shape precedent exists anywhere in `little_loops` at the
  CLI/MCP boundary (repo-wide grep for `TypedDict` under `scripts/little_loops`
  returns only two unrelated classes in `cli/artifact/templatize.py`). The
  established pattern for an extracted CLI-layer function's return type is
  `@dataclass` (`StatusTransition`, `LinkResult`, `SearchResult`); MCP tool
  handlers return plain `dict[str, Any]` (or a list of them) built either by
  hand or via a dataclass's own `to_dict()` — `LinkResult` has a `to_dict()`
  method but even `_tool_issue_link` does not call it, reading fields directly
  and hand-building its response dict instead.
- The project-root resolution helper for `.loops/` already exists and is the
  one used by `_tool_loop_start`: `_loops_dir(project_root)`
  (`scripts/little_loops/mcp_server/tasks.py:73`), which goes through
  `BRConfig(project_root).get_loops_dir()` rather than reading the raw
  `config.loops.loops_dir` string (BUG-3180 — the raw field is relative and
  silently re-anchors on process cwd).

## Implementation Steps

1. Extract a non-printing enumeration function from `cmd_list`
   (`cli/loop/info.py`) that returns the catalog as structured data (`LoopCatalog`
   per Program Design): for each loop, its relative-path name, absolute path,
   `builtin` flag, and the `_load_loop_meta` fields (description, category,
   labels, visibility), plus the `hidden_counts` the human footer needs. It should
   accept the filter parameters (category, label, visibility-tier *set*,
   `builtin_only`) as ordinary arguments rather than reading an
   `argparse.Namespace`; `cmd_list` keeps the legacy-flag → tier-set mapping.
2. Rewrite `cmd_list`'s catalog branch to call that function and handle only
   presentation (colorized table vs `print_json`). The `--running` / `--status` /
   `--all-runs` branch is a different code path and stays as is.
3. Add `_tool_loop_list` to `mcp_server/tools.py` with the tier-1 signature
   `(arguments: dict, *, project_root: Path) -> Any`, calling the new helper.
4. Register it in `_TOOL_HANDLERS` and add its `types.Tool` entry to `_TOOLS` in
   source order (after `queue_get`, the last tier-1 entry), with `annotations=None`.
5. Do **not** add it to `policy.MUTATING_TOOLS` or `TASK_STARTING_TOOLS` — it is a
   pure read.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Preserve the `built_in` key's asymmetric convention in
  `LoopCatalogEntry.to_json_item()` (present-and-`True` only for built-ins,
  absent for project loops) — `loop-router.yaml`, `lib/composer.yaml`, and
  `workflow-generator.yaml` all branch on `loop.get('built_in', False)` when
  parsing `ll-loop list --json`; the internal entries keep symmetric
  `builtin: bool`
- Update `scripts/tests/test_mcp_server.py` — add `"loop_list"` to the
  `read_only` set in `test_no_unguarded_mutating_tool_is_advertised`
- Update `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — add `loop_list`
  to `TIER1_NAMES` and fix the `names[:7]`/`names[7:]` slice indices to `:8`/`8:`
- Update `scripts/tests/test_issue_parser.py::_ALLOWLIST["mcp_server/tools.py"]`
  — re-point the line-849 entry to wherever `issue_capture`'s schema pattern
  lands after the new `loop_list` `Tool()` entry shifts it down
- Update the stale tool-count docstrings: `mcp_server/tools.py` module
  docstring (seven→eight read tools) and `handle_list_tools` docstring
  (fifteen→sixteen), plus `docs/reference/CLI.md:4855-4857`
- Write `scripts/tests/test_feat_3352_mcp_loop_list.py` (or similar) covering
  the tier-1 tool shape, project-root anchoring, visibility/category/label
  filtering, and JSON-contract parity with `cmd_list --json`

## Impact

- **Priority**: P3 - Closes the last CLI-shellout gap in the MCP primitive surface for
  an external director agent, but nothing is broken today; the agent can still shell
  out to `ll-loop list`.
- **Effort**: Medium - The MCP handler is small; the `cmd_list` extraction is the real
  work (~230 lines of interleaved enumeration, filtering, and printing to separate).
- **Risk**: Medium - The extraction touches a user-facing CLI command. The override
  and visibility semantics are subtle enough to regress silently, which is why
  unchanged `ll-loop list` output is an explicit acceptance criterion.
- **Breaking Change**: No - purely additive on the MCP side; `ll-loop list` behavior
  must be preserved exactly.

## Root Cause / Constraint

Two constraints shape the implementation:

1. **No wrapping `cmd_*` directly.** On the stdio transport stdout *is* the JSON-RPC
   frame, so any handler that lets a `cmd_*` function print corrupts the protocol.
   This is why FEAT-3149 extracted `apply_status_transition` / `apply_link` rather
   than calling `cmd_set_status` / `cmd_link`, and why `_tool_loop_start` wraps
   `run_background()` in `contextlib.redirect_stdout` / `redirect_stderr`. Follow the
   FEAT-3149 pattern: extract, do not redirect, for a pure read.
2. **Project-root threading.** Resolve the loops dir from the handler's
   `project_root`, not cwd — see `mcp_server/tasks.py::_loops_dir` (ENH-3171,
   BUG-3180).

## API / Interface

New tool `loop_list`, tier-1 read, no `apply` parameter.

Input schema (all optional): `category` (string), `label` (array of strings),
`visibility` (enum: `public` | `internal` | `example` | `all`, default `public`).

Output: a list of loop objects, project loops before built-ins, matching what
`ll-loop list --json` emits so the two surfaces stay comparable.

## Explicit Non-Goals

- **No `loop_create` / `loop_install` tool.** `cmd_install`
  (`cli/loop/config_cmds.py:95`) is a `shutil.copy2` with two existence checks that
  returns an int and prints; there is no function to wrap, and an agent that can
  write files can write the loop YAML directly. Loop *creation* proper is the
  LLM-driven `/ll:create-loop` skill plus `_scaffold_core.py`, which is not
  expressible as one MCP call.
- No new auth, no new HTTP server, no events tool.

## Acceptance Criteria

- [ ] A non-printing catalog function exists in `cli/loop/info.py` (or a sibling
      module) and `cmd_list`'s catalog branch calls it rather than duplicating the
      enumeration.
- [ ] `ll-loop list` output is unchanged for the default, `--json`, `--category`,
      `--label`, `--visibility`, `--builtin`, and legacy-flag (`--all` /
      `--internal` / `--examples`, including `--internal --examples` combined)
      cases (regression-tested).
- [ ] `tools/list` reports 16 tools, with `loop_list` present and
      `readOnlyHint` unset (tier-1 convention).
- [ ] `loop_list` resolves the loops dir from `project_root`, verified by a test that
      runs the server with `--project-root` pointed at a scratch tree while cwd is
      elsewhere.
- [ ] Project loops shadow same-named built-ins in the result, matching `cmd_list`.
- [ ] Default visibility filtering hides `internal` and `example` loops.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/MCP_SERVER_GUIDE.md` | Tool inventory table (lines 32-33) needs the new read tool added |
| `docs/reference/API.md` | `little_loops.mcp_server` module reference |

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-28T19:44:53 - `c056a832-2f27-43a8-b622-031bae76a3d0.jsonl`
- `/ll:confidence-check` - 2026-08-28T19:30:17 - `d3964614-0e7e-4d89-bc34-5bd7bd83f914.jsonl`
- `/ll:wire-issue` - 2026-08-28T19:18:02 - `22846f50-44ca-47bb-8d4a-c3a415e9ca6e.jsonl`
- `/ll:refine-issue` - 2026-08-28T19:00:19 - `1d9de51b-4056-4c32-8b39-b0f74389491b.jsonl`
- `/ll:format-issue` - 2026-08-28T18:53:11 - `cd78290f-ddde-4f99-979f-b4b86c3a3f3f.jsonl`
- `/ll:capture-issue` - 2026-08-28T18:43:16 - `51a7dd65-db46-4ad2-be82-40e74f2445d1.jsonl`
