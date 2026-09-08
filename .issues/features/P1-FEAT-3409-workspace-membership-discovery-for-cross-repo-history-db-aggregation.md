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
verify_verdict: VALID
confidence_score: 85
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
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

## Use Case

**Who**: FEAT-3410's ATTACH-based cross-repo aggregation — the sole intended
consumer of this issue's output.

**Context**: FEAT-3410 needs to know which repos belong to a workspace, what
role each plays, and where each one's `history.db` lives, before it can
`ATTACH` each member database into one aggregation query. That topology has
to come from somewhere declared: the only existing multi-project mechanism,
`discover_all_projects()` (`cli/logs.py:166`), is a runtime filesystem walk
over host session directories, not a registry a caller can enumerate ahead of
time.

**Goal**: `discover_workspace_members()` reads `ll-workspace.yaml` once and
returns the member list FEAT-3410 iterates to build its per-repo `ATTACH
DATABASE` calls.

**Outcome**: A project with no `ll-workspace.yaml` gets an empty/None result,
so FEAT-3410 — and any other future consumer — falls back to single-repo
behavior byte-for-byte, with no separate code path to maintain.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Malformed-manifest handling is unspecified** — Expected Behavior only defines the absent-manifest case; a present-but-malformed `ll-workspace.yaml` (bad YAML syntax, or an entry missing `repo`/`role`) has no stated behavior. This codebase holds three disagreeing conventions for a present-but-bad manifest, not one: fail-closed/raise (`artifact_templates.py::load_manifest`, `:161-163`, re-raises as a domain error), fail-open/degrade (`fsm/loop_paths.py::draft_internal_name`, `:31-33`; `config/core.py::parse_local_override_frontmatter`, `:83-86`; both catch `yaml.YAMLError` and return `None`/`{}`), and no-wrap/propagate (`decisions.py::load_decisions`, `:381`, deliberately lets `yaml.YAMLError` propagate for the flat file "preserving ENH-2589 corruption gating," per its own docstring). `load_decisions()` — this issue's own cited model — is itself the no-wrap case, not the fail-open case; picking it as the pattern means a malformed `ll-workspace.yaml` raises, which is a different posture than the absent-manifest fallback.
- **`db_path` derivation is unspecified relative to a real composition hazard**: `WorkspaceMember.db_path` could be (a) an explicit field authored per-entry in the manifest, or (b) computed at discovery time via `resolve_history_db(root=member.repo_path)` (`session_store/db.py:121-132`). Option (b) does not compose safely across multiple members in one process: `_resolve_db_path()`'s `LL_HISTORY_DB` env-var check (`session_store/db.py:107-109`) fires unconditionally ahead of the `root=`-scoped config lookup, so a single `LL_HISTORY_DB` value in the environment would resolve to the same path for every member's `db_path`, silently collapsing a multi-repo workspace onto one database. No existing call site invokes `resolve_history_db()` more than once per process with different `root=` values.
- **`_resolve_token_root()` is a three-way branch, not binary**: new-layout dir present -> return it; profiles dir present but active profile missing -> warn (unless `quiet=True`) and return `None`; neither present -> fall through to treating `base_path` itself as the root (legacy layout), returned directly, never `None` in that branch. Relevant since `discover_workspace_members()`'s own degradation is currently described as a single absent/present split.
- Doc citations confirmed at exact ranges: `docs/ARCHITECTURE.md:711-713` (not just :712) states `.ll/history.db` "is the per-project event history store"; `docs/reference/API.md:92` (module table) and `:8205-8209` (package docstring, not just :8207) both use per-project/single-repo framing.

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
- **Module placement**: no existing subpackage fits. The two cited precedent
  modules (`decisions.py`, `design_tokens.py`) both sit directly under
  `scripts/little_loops/` as top-level siblings, are never re-exported from
  `scripts/little_loops/__init__.py`'s `__all__`, and are imported by callers
  via the direct submodule path (e.g. `from little_loops.decisions import
  load_decisions`). A new `scripts/little_loops/workspace.py` (name TBD)
  follows this precedent — not a new subpackage, not a `config/__init__.py`
  re-export (that file's re-export list is reserved for `config.*` dataclasses
  per its own docstring). [`/ll:wire-issue` finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `WorkspaceMember` value-object shape: the closest existing "discriminator string + `Path`" precedent is `_ResourceEntry` (`scripts/little_loops/mcp_server/resources.py:59-68`, frozen dataclass, `kind: str` paired with `path: Path`). A looser `role: str` precedent (free-text, not a closed-set discriminator) is `Persona` (`scripts/little_loops/goals_parser.py:15-27`).
- Frozen-vs-mutable is a contested, chronologically-split convention in this codebase, not a settled one: `decisions.py`'s entry dataclasses (this issue's cited dispatch model) and every existing `Path`-field dataclass surveyed (`ArtifactTemplate`, `CompletedIssue`, `WorktreeResult`) are plain mutable `@dataclass`. But `host_runner.py:316-327` explicitly states new value objects that cross a runner/caller-style boundary should be `frozen=True`, and ~20 dataclasses added since follow that convention. `WorkspaceMember` crosses exactly that kind of boundary (produced here, consumed by FEAT-3410), which is the shape `host_runner.py`'s stated convention targets.
- No existing "list of entries with a role" manifest concept exists to mirror structurally — searched `fsm/schema.py`, `fsm/fsm-loop-schema.json`, `sprint.py` repo-wide for a `role`-bearing member/entry list; 0 hits. `WorkspaceMember` would be the first of this shape.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Correction**: the frozen-vs-mutable finding above cites `WorktreeResult` as a third existing mutable `Path`-field dataclass alongside `ArtifactTemplate`/`CompletedIssue`. Independent search confirms no `WorktreeResult` class exists under that name anywhere in `scripts/little_loops` (0 hits) — that citation does not resolve against current source. The contested-convention conclusion still holds on the two confirmed mutable examples (`ArtifactTemplate`, `scripts/little_loops/artifact_templates.py:50-55`; `CompletedIssue`, `scripts/little_loops/issue_history/models.py:16-28`) versus `host_runner.py:316-327`'s stated `frozen=True` convention for `HostInvocation`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:1513-1554` (`HistoryConfig` dataclass + `from_dict()`) — if the nested `history.workspace_manifest_path` field is chosen, add it here alongside the existing `db_path` field/getter pair (`:1523`/`:1541`); no change needed to `config/core.py` or `config/__init__.py` in this case, since `HistoryConfig`'s existing wiring already covers new fields on the dataclass.
- `scripts/little_loops/config/core.py:31-35,370,518-520` — only if the alternative **new top-level `workspace` config section** is chosen instead (sibling to `history`, not nested inside it): add a `WorkspaceConfig` import (mirroring `DecisionsConfig` at `:31` / `HistoryConfig` at `:35`), a `self._workspace = WorkspaceConfig.from_dict(...)` instantiation (mirroring `:370`), and a `workspace` property (mirroring `:518-520`).
- `scripts/little_loops/config/__init__.py:50,58,105,155` — same top-level-section case: add a `WorkspaceConfig` import + `__all__` entry, mirroring the `DecisionsConfig`(`:50`/`:105`)/`HistoryConfig`(`:58`/`:155`) pairs.
- `scripts/tests/test_config_schema.py:1363-1430` (`_DATACLASS_SECTION_MAP`) — only required if a new `WorkspaceConfig` dataclass is added (not required for the nested-scalar-on-`HistoryConfig` path); `TestDataclassSectionMapCompleteness` (class starts `:1433`) fails at collection if a new dataclass is added without a map entry.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` § `history` (table rows around `:616-620`, alongside the existing `history.db_path` row) — the authoritative doc site for any new `history.workspace_manifest_path` config key; not previously listed here.
- `docs/reference/API.md:3532-3563` (`### discover_all_projects` section) — the existing *runtime-discovered* projects concept this issue's declared-manifest approach should cross-reference; distinct from the already-listed lines 92/8207.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No `conftest.py` fixture exists for writing a YAML manifest to `tmp_path` (searched, 0 hits) — the new test module needs its own module-local helper (e.g. `_write_manifest()`), following the `_write_tokens()` pattern in `scripts/tests/test_design_tokens.py:23-39`, not a shared fixture.
- Parsing-class shape precedent beyond the graceful-degradation classes already cited: `TestLoadDecisions` (`scripts/tests/test_decisions.py:109-183`) covers one-member/multi-member/malformed-YAML/missing-required-field/unknown-discriminator cases — mirror this shape for `discover_workspace_members()`'s happy-path and error-path tests, not just the absent-manifest degradation case.

## Program Design

### Types

- `WorkspaceMember`: `repo_path: Path`, `role: str`, `db_path: Path`

### Signatures

- `discover_workspace_members(manifest_path: Path) -> list[WorkspaceMember]` — default `manifest_path` is `Path("ll-workspace.yaml")`

### Call Path

`discover_workspace_members(manifest_path)` -> `Path.exists()` guard -> `yaml.safe_load(manifest_path.read_text())` -> per-entry construction of `WorkspaceMember(repo_path=..., role=..., db_path=...)` -> returned `list[WorkspaceMember]`. No caller exists yet in this codebase — FEAT-3410's ATTACH-based aggregation entry point is the sole intended consumer, feeding each returned member's `db_path` into a per-member `ATTACH DATABASE` call in the shape of `build_snapshot_db` (`scripts/little_loops/session_store/queries.py:246-301`, today's only `ATTACH DATABASE` call site, single-source/single-alias — a multi-member attach loop has no existing precedent to confirm against).

### Decision Rules

- **Malformed-manifest posture** (present but invalid `ll-workspace.yaml`): unresolved. This codebase holds three disagreeing conventions for this exact situation — fail-closed/raise (`artifact_templates.py::load_manifest`), fail-open/degrade to empty (`fsm/loop_paths.py::draft_internal_name`, `config/core.py::parse_local_override_frontmatter`), and no-wrap/propagate (`decisions.py::load_decisions`, this issue's own cited model, which deliberately does not catch `yaml.YAMLError` for its flat file). Expected Behavior currently specifies only the absent-manifest case; the malformed-but-present case needs an explicit choice among these three postures before implementation.
- **`db_path` derivation**: unresolved. Either (a) an explicit per-entry manifest field, or (b) computed at discovery time via `resolve_history_db(root=member.repo_path)`. Option (b) has a known composition hazard: `resolve_history_db`'s `LL_HISTORY_DB` env-var check fires unconditionally ahead of the `root=`-scoped lookup (`session_store/db.py:107-109`), so calling it once per member in the same process would resolve every member's `db_path` to the same env-overridden value whenever `LL_HISTORY_DB` is set — silently collapsing a multi-repo workspace onto one database. No escape hatch is specified for this case; the implementer must pick (a) or (b) knowingly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Frozen-vs-mutable is not resolved by majority precedent**: a repo-wide sweep confirms the split is real at scale, not an artifact of the two cited examples — 158 frozen-dataclass declarations vs. 327 plain `@dataclass` declarations across `scripts/little_loops/`. Frequency alone does not favor either convention for `WorkspaceMember`.
- **Malformed-manifest three-way tie is exhaustive, not under-sampled**: a broader sweep of all ~45 `yaml.safe_load()`/`yaml.load()` call sites in the package found no fourth handling convention and no other manifest-shaped parser beyond the three already cited (fail-closed `artifact_templates.py:161-163`, fail-open `fsm/loop_paths.py:31-33` / `config/core.py:83-86`, no-wrap `decisions.py:381`). Further codebase research will not resolve this — it needs an explicit choice, not more searching.
- **No other multi-instance `db_path`-derivation precedent exists**: confirmed no call site anywhere in the codebase invokes `resolve_history_db()` more than once per process with different `root=` values, and no other function with an equivalent per-instance-derivation shape exists to model the composition hazard's handling against.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Place the new module at `scripts/little_loops/workspace.py` (or a similarly-named top-level module) — a top-level sibling of `decisions.py`/`design_tokens.py`, not a subpackage, not re-exported from `scripts/little_loops/__init__.py` or `config/__init__.py`.
- If choosing the nested `history.workspace_manifest_path` config path: update only `scripts/little_loops/config/features.py`'s `HistoryConfig` dataclass and `from_dict()`.
- If choosing the new top-level `workspace` config section path instead: update `scripts/little_loops/config/features.py` (new `WorkspaceConfig` dataclass), `scripts/little_loops/config/core.py` (import, instantiation, property), `scripts/little_loops/config/__init__.py` (import + `__all__` entry), and `scripts/tests/test_config_schema.py`'s `_DATACLASS_SECTION_MAP`.
- Update `docs/reference/CONFIGURATION.md` § `history` with the new key's doc row, if a config key is added.
- Write a module-local YAML-manifest test helper (e.g. `_write_manifest()`) — no shared `conftest.py` fixture exists to reuse.

## Tests

- New test module/class for `discover_workspace_members()`: manifest parses into
  correct `WorkspaceMember` rows; absent manifest degrades to empty/None,
  following `TestDecisionsGracefulDegradation`/`TestLoadDesignTokensFallbacks`.
- `scripts/tests/test_config_schema.py` — if `history.workspace_manifest_path`
  (or a new `workspace` section) is added to `config-schema.json`, add a
  matching per-property test.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py`'s `_DATACLASS_SECTION_MAP` (`:1363-1430`) — new entry required only if a new `WorkspaceConfig` dataclass is introduced (the new-top-level-section path); `TestDataclassSectionMapCompleteness` (`:1433`) fails at collection otherwise.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Per-property schema test convention confirmed at `scripts/tests/test_config_schema.py:319` (`test_decisions_in_schema`) and its `history`-namespace siblings `:564`/`:615`/`:630` (`test_history_in_schema`, `test_history_db_path_in_schema`, `test_history_compaction_in_schema`) — 39 such tests exist total, each asserting one property's `type`/`default` against `data["properties"][...]`.
- A dataclass-to-schema-key mapping table exists at `scripts/tests/test_config_schema.py:1386,1409-1418` (e.g. `"DecisionsConfig": "decisions"`, `"HistoryConfig": "history"`) — a new `workspace` config class (if added) needs an entry here in addition to the per-property test.
- Graceful-degradation test shape confirmed exactly as cited: `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) and `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`) both use `tmp_path`, one test per short-circuit branch, direct `== []`/`is None` assertions — neither class asserts a raised exception (raise-path tests, where they exist, live in separate sibling classes, e.g. `TestLoadDesignTokensErrors`).

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- An additional malformed-input test-class precedent beyond `TestLoadDecisions`: `TestLoadDecisionsMalformedInput` (`scripts/tests/test_verify_decisions.py:42`) — a second existing example of how this codebase tests a malformed-YAML-manifest case, directly relevant to the still-unresolved malformed-manifest-posture Decision Rule above.

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

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-08 — graph: provider=`codegraph` freshness=`fresh`:_

- Anchor relocation: `scripts/tests/test_config_schema.py:1349-1430` (cited twice, in
  Files to Modify and Tests) was off by 14 lines at the start — `_DATACLASS_SECTION_MAP`
  actually begins at `:1363` (confirmed via `ll-code defines`); the dict body runs
  `:1363-1430` and `TestDataclassSectionMapCompleteness` starts at `:1433`. Both
  citations corrected in place.
- All other file:line citations checked (30+ across `config-schema.json`,
  `decisions.py`, `session_store/db.py`, `fsm/loop_paths.py`, `config/core.py`,
  `mcp_server/resources.py`, `goals_parser.py`, `host_runner.py`,
  `config/features.py`, `config/__init__.py`, `test_decisions.py`,
  `test_design_tokens.py`, `test_config_schema.py`, `docs/ARCHITECTURE.md`,
  `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`,
  `session_store/queries.py`) match current code/docs content exactly.
- `discover_workspace_members()`, `WorkspaceMember`, and `ll-workspace.yaml` confirmed
  absent repo-wide (0 hits) — Current Behavior and Files to Modify claims hold.
- `ll-verify-evidence --json` returned `"ok": true`, 0 findings — no fabricated
  evidence quotes.
- No active required decision rules — decisions check is a clean skip.
- No `## Blocked By`/`## Blocks` sections present — dependency-reference check (§E)
  not applicable.
- `## Proposed Solution` section absent (issue uses Program Design/Decision
  Rules/Implementation Steps instead) — proposal-vs-code consequence check (B6)
  skipped per its precondition.

_Re-verified `/ll:verify-issues` — 2026-09-08 — graph: provider=`codegraph` freshness=`fresh`:_

- Previously-flagged anchor (`test_config_schema.py` `_DATACLASS_SECTION_MAP`/
  `TestDataclassSectionMapCompleteness`) confirmed already corrected in the working
  tree to `:1363-1430`/`:1433` — matches current source exactly.
- Two claims added since the prior verify pass (by `/ll:refine-issue:gap-analysis`)
  checked and confirmed: `WorktreeResult` remains 0 hits repo-wide (correction
  holds); `TestLoadDecisionsMalformedInput` confirmed at
  `scripts/tests/test_verify_decisions.py:42`.
- Spot-checked load-bearing Decision Rule citations: `session_store/db.py:107-132`
  (`LL_HISTORY_DB` env check fires unconditionally before the `root=`-scoped
  config lookup — composition-hazard claim holds) and
  `config-schema.json:2117-2146` (`history.db_path` shape) both match current
  source.
- `ll-verify-evidence --json` re-run: `"ok": true`, 0 findings.
- Parent (`FEAT-3399`) and sibling (`FEAT-3410`) references both resolve; no
  `## Blocked By`/`## Blocks` sections to check.
- No active required decision rules — clean skip.
- Verdict: **VALID** — all claims, including those added after the prior verify
  pass, hold against current code.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- Two Decision Rules remain unresolved: malformed-manifest posture (three
  disagreeing codebase conventions cited: fail-closed/raise, fail-open/degrade,
  no-wrap/propagate) and `db_path` derivation (explicit manifest field vs.
  `resolve_history_db()`, which has a documented `LL_HISTORY_DB` composition
  hazard across multiple members). Resolve via `/ll:decide-issue FEAT-3409`
  before starting Implementation Step 1.
- Config registration path is also left open (nested
  `history.workspace_manifest_path` vs. a new top-level `workspace` section) —
  the choice determines which of two Dependent-Files wiring lists apply.

## Session Log
- `/ll:refine-issue` - 2026-09-08T18:20:33 - `93c855fd-cd38-4404-abc3-eca785ed7ae8.jsonl`
- `/ll:confidence-check` - 2026-09-08T17:48:31 - `da08f1cf-aa72-4044-9c86-40020b649222.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:45:51 - `c85a7f3d-8147-4f84-a4a8-b54c8bbd73dd.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T17:41:47 - `5027b454-4016-483b-bbf8-8af9131c8c75.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:36:08 - `130fcd36-de26-44a3-b91d-ce69b841840c.jsonl`
- `/ll:wire-issue` - 2026-09-08T17:31:32 - `fa35fcdd-03ef-4e02-8495-668286d605de.jsonl`
- `/ll:refine-issue` - 2026-09-08T17:21:28 - `9bcae330-1a21-42d2-bfd3-9b52b57ca4c1.jsonl`
- `/ll:issue-size-review` - 2026-09-08T06:21:27 - `c53583bd-6c7a-49a7-8685-76b64ad999da.jsonl`
