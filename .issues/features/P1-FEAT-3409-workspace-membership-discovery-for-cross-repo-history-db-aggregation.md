---
id: FEAT-3409
title: Workspace membership discovery for cross-repo history.db aggregation
type: FEAT
priority: P1
status: open
discovered_date: '2026-09-08'
labels:
- path-a
- history-db
- multi-repo
learning_tests_required:
- yaml
parent: FEAT-3399
---

## Summary

Introduce `discover_workspace_members()`: a parser for a new `ll-workspace.yaml`
manifest that names member repos by path with a role apiece, producing a
`WorkspaceMember` list for consumers to aggregate over. Absence of the manifest
must fall back cleanly (an empty/None result), never raise.

## Parent Issue

Decomposed from FEAT-3399: Cross-repo history.db aggregation (read-only workspace
rollup). This child covers the workspace-topology discovery half of that issue;
the ATTACH-based aggregation, quality-report integration, and `--workspace` CLI
wiring is FEAT-3410, which consumes this child's `WorkspaceMember` type and
`discover_workspace_members()` function as its input.

## Current Behavior

No checked-in multi-repo membership manifest of any name exists anywhere in the
codebase (searched `config-schema.json`, `cli/parallel.py`, `worktree_utils.py`,
repo-wide for `repos:`/`members:`/`projects:`). The only existing multi-project
mechanism is runtime filesystem discovery (`discover_all_projects()`,
`cli/logs.py:166`), which walks the host's session-directory tree and decodes
paths from JSONL — not a declared registry.

## Expected Behavior

`discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml")) ->
list[WorkspaceMember]` parses the manifest into `WorkspaceMember(repo_path: Path,
role: str, db_path: Path)` rows. With no manifest present at the discovery path,
the function returns an empty/None result rather than raising, so downstream
consumers can fall back to single-repo behavior byte-for-byte.

## Design Notes

**New manifest format convention**: JSON-Schema-shaped files in this codebase
(`config-schema.json`, `fsm/fsm-loop-schema.json`) are documentation/test-fixture
only — neither is loaded through a schema-validator library at runtime
(`jsonschema` is not a base dependency). Every existing YAML manifest is instead
hand-parsed with `yaml.safe_load()` plus manual type-dispatch —
`decisions.py::load_decisions()`'s `dict.get("type")`-keyed dispatch into one of
four dataclasses (`decisions.py:353-385`) is the closest model. `ll-workspace.yaml`
should follow this hand-parsed shape; adding a schema-validation dependency would
be a new pattern, not a followed one.

**No shared YAML-loading helper exists** — 0 hits for `def load_yaml`/`def
_load_yaml`/`def read_yaml` repo-wide. 35 separate `yaml.safe_load()` call sites
exist across production modules, each with its own local read/parse/error-handling.
`discover_workspace_members()` is the 36th independent parser, consistent with
every other YAML consumer in this codebase — not an outlier needing a new shared
utility.

**Manifest-absent graceful degradation** is an established pattern:
`decisions.py::load_decisions()` and `design_tokens.py::_resolve_token_root()`
both do an explicit `Path.exists()`/`is_dir()` check, document the fallback
target in the docstring, and have a dedicated test class
(`TestDecisionsGracefulDegradation`, `TestLoadDesignTokensFallbacks`). Follow this
shape for the no-`ll-workspace.yaml` fallback.

## Constraints

- Repo discovery must not introduce a second registry beyond the manifest itself
  — this is the first and only declared multi-repo membership list in the
  codebase.
- No manifest present must degrade cleanly, never raise.

## Files to Modify

- New module (path not yet chosen) implementing `discover_workspace_members()`
  — no existing file to modify since neither the function nor `WorkspaceMember`
  exists anywhere in the codebase today (confirmed 0 hits repo-wide).
- `config-schema.json:2117-2146` — the `history` object already has a `db_path`
  property (`:2143-2146`) with an `LL_HISTORY_DB`-env-var-precedence shape. If a
  configurable manifest path is wanted, `history.workspace_manifest_path`
  alongside `history.db_path` is the sibling location to register it in — the
  function's own bare-default signature (`Path("ll-workspace.yaml")`) is not yet
  routed through this config/env-var chain. Alternatively,
  `config-schema.json:704-728`'s `decisions` object registration shape (top-level
  object, `enabled`/`log_path`/`auto_generate` properties) is the closest
  precedent for a new top-level `workspace` config section instead of nesting
  under `history`. Pick one deliberately.

## Program Design

### Types

- `WorkspaceMember`: `repo_path: Path`, `role: str`, `db_path: Path`

### Signatures

- `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml")) -> list[WorkspaceMember]`

## Implementation Steps

1. Define `WorkspaceMember` and implement `discover_workspace_members()`,
   hand-parsing `ll-workspace.yaml` with `yaml.safe_load()` per the
   `decisions.py::load_decisions()` dispatch model.
2. Implement the no-manifest graceful-degradation branch: explicit
   `Path.exists()` check, empty/None return, documented fallback target in the
   docstring.
3. Decide and implement config registration for a configurable manifest path
   (`history.workspace_manifest_path` or a new top-level `workspace` section) if
   wanted; if `config-schema.json` gains the property, add a matching
   `test_*_in_schema` test following the existing per-property convention (e.g.
   `test_decisions_in_schema:319`).
4. Add a graceful-degradation test class modeled exactly on
   `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) /
   `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`): one test
   per short-circuit branch, `tmp_path`-based (no manifest created), direct
   `== []`/`is None` return-value assertion.
5. Update `docs/ARCHITECTURE.md:712` and `docs/reference/API.md:92,8207`'s
   "per-project"/single-repo framing to mention the new workspace-topology
   concept this manifest introduces (the aggregation-specific CLI/output docs
   belong to FEAT-3410, not here).

## Tests

- New test module/class for `discover_workspace_members()`: manifest parses into
  correct `WorkspaceMember` rows; absent manifest degrades to empty/None,
  following `TestDecisionsGracefulDegradation`/`TestLoadDesignTokensFallbacks`.
- `scripts/tests/test_config_schema.py` — if `history.workspace_manifest_path`
  (or a new `workspace` section) is added to `config-schema.json`, add a
  matching per-property test.

## Impact

- **Priority**: P1 — prerequisite for FEAT-3410's cross-repo aggregation; no
  standalone user-facing behavior change until FEAT-3410 consumes it.
- **Effort**: Small — a single hand-parsed YAML manifest with a well-precedented
  graceful-degradation shape; no SQLite or ATTACH mechanics.
- **Risk**: Low — read-only manifest parsing, no database access.
- **Breaking Change**: No

## Acceptance Criteria

- `discover_workspace_members()` parses a well-formed `ll-workspace.yaml` into
  the correct `WorkspaceMember` list.
- Absent manifest degrades to an empty/None result without raising, covered by a
  dedicated graceful-degradation test class.
- If a configurable manifest path is registered in `config-schema.json`, a
  matching schema test exists.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Session Log
- `/ll:issue-size-review` - 2026-09-08T06:21:27 - `c53583bd-6c7a-49a7-8685-76b64ad999da.jsonl`
