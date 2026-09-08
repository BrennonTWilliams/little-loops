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
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
decision_needed: false
reconcile_attempted: true
---

## Summary

Introduce `discover_workspace_members()`: a parser for a new `ll-workspace.yaml`
manifest that names member repos by path with a role apiece, producing a
`WorkspaceMember` list for consumers to aggregate over. Absence of the manifest
must fall back cleanly (an empty list), never raise.

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

`discover_workspace_members(manifest_path: Path | None = None, *, start: Path |
None = None) -> list[WorkspaceMember]` parses the manifest into
`WorkspaceMember(repo_path: Path, role: str, db_path: Path)` rows. When the
implicit ancestor walk (Manifest Path Resolution step 3) finds no manifest, the
function returns `[]` (never `None`) rather than raising, so downstream consumers
can fall back to single-repo behavior byte-for-byte. When the path came from the
explicit argument or the config key (steps 1–2) and does not exist, the function
raises `FileNotFoundError` — see "Absent-by-discovery vs absent-by-declaration"
under Manifest Path Resolution. `start` seeds steps 2 and 3 (defaults to
`Path.cwd()`); see the `start` note there.

### Manifest Format

```yaml
# ll-workspace.yaml — workspace membership manifest
members:
  - repo: .                       # required; relative paths resolve against the manifest's parent dir
    role: primary                 # required; free-text string, no closed set enforced
  - repo: ../sibling-service
    role: service
    db_path: .ll/history.db       # optional; relative to THIS member's repo; default: <repo>/.ll/history.db
```

Rules:

- Top-level is a mapping with a `members:` list. Any other top-level shape
  (bare list, scalar, `members` not a list) raises `ValueError`. An **empty
  file** (`yaml.safe_load` → `None`) is malformed, not absent, and raises
  `ValueError` via the same shape check. `members: []` is well-formed and
  returns `[]` — indistinguishable from the absent-manifest case by design.
- `repo` and `role` are required per entry; a missing key raises `KeyError`
  (bare `entry["repo"]`, mirroring `decisions.py`'s `from_dict` style).
  Both must be non-empty strings — a non-string value (e.g. `role: 1`, which
  YAML yields as `int`) or an empty string raises `ValueError` under the
  shape-check rule; no `str()` coercion. `role` is free-text; FEAT-3410 must
  surface it in the per-repo breakdown (see Decision Rules → Cross-issue
  consistency) — a required field no consumer reads would be decorative.
- `db_path` is optional. When absent it is composed statically as
  `(repo_path / ".ll" / "history.db").resolve()` — a plain `Path` join, **not**
  `resolve_history_db()`, so the `LL_HISTORY_DB` collapse hazard (Decision
  Rules) is never reintroduced by the default. The default is `.resolve()`d
  exactly like an explicit `db_path` (`Path.resolve()` is non-strict and works
  on nonexistent paths), so the duplicate check below compares like with like:
  without it, an explicit entry aliasing `<repo>/.ll/history.db` through a
  symlinked `.ll/` would compare unequal to the unresolved default and slip
  past the check. "Absent" means the key is
  missing **or** its value is `None`/empty string (`db_path:` with no value,
  `db_path: ""`) — the presence check is `entry.get("db_path")`, not
  `"db_path" in entry`, so a bare `db_path:` line never reaches
  `repo_path / None` (`TypeError`) and `""` never silently yields `repo_path`
  itself. A present non-string `db_path` raises `ValueError`.
- Relative `repo` values resolve against the manifest file's parent directory,
  not cwd. Relative `db_path` values resolve against **that entry's resolved
  `repo_path`**, mirroring how the `history.db_path` config key resolves
  against its own project root (`session_store/db.py::_config_db_path`). This
  is deliberate: manifest-relative `db_path` would make `db_path:
  .ll/history.db` on a sibling entry silently point at the primary repo's
  database. Both are stored resolved (absolute) on the returned
  `WorkspaceMember`. `Path.resolve()` follows symlinks, so a symlinked member
  repo is stored by its real path — document this in the docstring; it is
  also what makes the duplicate check below catch two entries that alias one
  database through different symlinks.
- **Duplicate members** — two entries whose resolved `db_path` values collide
  — raise `ValueError` naming the path. FEAT-3410 would otherwise `ATTACH`
  one database twice and double-count it.
- **No existence checks.** Discovery does not verify that `repo_path` or
  `db_path` exists on disk; FEAT-3410 owns skip-and-report for a missing or
  schema-skewed member database. An implementer must not add a filter here.
- A member repo's own `history.db_path` config key is **not** consulted (the
  static default is the only fallback). A member with a custom `history.db_path`
  must repeat it in the manifest. Document this limitation in the function
  docstring and the `docs/reference/CONFIGURATION.md` row.
- **`~` expansion**: `repo` and `db_path` values are passed through
  `Path.expanduser()` before resolution, so `repo: ~/src/sibling` works in a
  gitignored machine-local manifest (the use case the relative-path rule
  below anticipates). Without this, `Path("~/x").resolve()` silently yields
  `<manifest_dir>/~/x`. The config-key path (`history.workspace_manifest_path`)
  gets the same treatment. The `history.db_path` precedent does not expand
  `~`; this is a deliberate, documented divergence, not an oversight.
- Prefer relative paths in a committed manifest: absolute member paths in a
  checked-in `ll-workspace.yaml` leak machine-local paths (and would trip
  `ll-verify-private-refs` in this repo — it excludes by directory, not file
  type, so a root-level YAML is in scope). Gitignoring the file is left to the
  consuming project; this issue does not change `ll-init`.

### Manifest Path Resolution

Precedence, highest first:

1. Explicit `manifest_path` argument — wins outright, but is normalized with
   `.resolve()` before use (not returned verbatim): `manifest_dir` is derived
   from it, and a relative arg would otherwise leak into the `exists()` guard,
   the duplicate-`db_path` error text, and every path stored on the returned
   members. The resolved path is what `discover_workspace_members()` operates
   on for every subsequent step. Precedence is unchanged — only normalization
   is added.
2. `history.workspace_manifest_path` from the project config (relative
   values resolve against the project root; `~` is expanded), read inside
   `discover_workspace_members()` itself via a small `_config_manifest_path()`
   helper — so the config key is reachable without every caller re-loading
   config. **Read through `BRConfig(root).history.workspace_manifest_path`,
   not a raw-JSON mirror of `session_store/db.py::_config_db_path`** (revised
   2026-09-08 review). `_config_db_path` reads raw JSON because
   `session_store/db.py` is a low layer that cannot import `little_loops.config`;
   the new top-level `workspace.py` has no such constraint (`design_tokens.py`,
   a top-level sibling, already imports `BRConfig` at
   `design_tokens.py:25`), and `BRConfig._load_config()` (`config/core.py:292-`)
   already deep-merges `.ll/ll.local.md` frontmatter on top of the base config
   (BUG-3123). Since a machine-local manifest path is exactly what a user
   would put in `ll.local.md`, the raw-JSON precedent's documented
   "does not merge local overrides" limitation is dropped rather than
   inherited. `BRConfig` tolerates a missing config file (returns defaults,
   `config/core.py:304-308`), so a project with no `.ll/ll-config.json`
   yields `None` here and falls through. Two consequences to document in the
   `_config_manifest_path()` docstring: (a) `BRConfig.__init__` calls
   `load_env_fallback(project_root)` (`config/core.py:287`), so this step has
   the same `.env`-into-`os.environ` side effect every `ll-*` CLI already has;
   (b) the import is done lazily inside the helper (as `design_tokens.py`
   does) to keep module import cost low for callers that pass an explicit
   `manifest_path`.

   **Root location for this step still uses `find_project_root(start)`**
   (`paths.py:14-41`) and therefore deliberately inherits the stray-`.ll`
   behavior that step 3 avoids: from a workspace parent dir with a stray
   `.ll`-only ancestor (e.g. `~/AIProjects/.ll` on the dev machine) this step
   reads `~/AIProjects/.ll/ll-config.json` if one exists and honors its
   `history.workspace_manifest_path`. Accepted as-is: the key is opt-in, a
   config file placed at a workspace parent is a plausible way to declare a
   workspace-level manifest, and when no root resolves or the key is unset the
   step returns `None` and falls through. Document this in the
   `_config_manifest_path()` docstring and cover it with one test (stray
   ancestor `.ll/ll-config.json` carrying the key → that manifest is used;
   stray `.ll/` with no config → falls through to step 3), plus one test that
   an `ll.local.md` override of the key is honored.
3. **Nearest-ancestor walk**: starting at `start.resolve()` (`Path.cwd()`
   when `start` is `None`), the first directory (`start` itself, then each
   parent) containing `ll-workspace.yaml` wins. When no ancestor holds one,
   the resolved path is `start / "ll-workspace.yaml"` (which does not exist
   → `[]`).

**Absent-by-discovery vs absent-by-declaration** (2026-09-08 review): the
"never raise on absent" contract applies **only to step 3**. When the manifest
path came from step 1 (explicit argument) or step 2 (config key) and the
resolved path does not exist, `discover_workspace_members()` raises
`FileNotFoundError` naming the path and its provenance (`"explicit
manifest_path"` / `"history.workspace_manifest_path"`). Rationale: a typo in
either would otherwise silently produce single-repo output, and FEAT-3410
cannot distinguish "no workspace declared" from "workspace misconfigured"
from a bare `[]`. The resolver knows the provenance; the consumer does not.
`_resolve_manifest_path()` therefore returns `(path, declared: bool)` (or an
equivalent small frozen result type) rather than a bare `Path`, so the
`exists()` guard can branch on provenance. This narrows the Constraints
entry "no manifest present must degrade cleanly" to the discovery case.

**The `start` seed** (2026-09-08 review): `discover_workspace_members(...,
*, start: Path | None = None)` seeds both step 2's `find_project_root(start)`
and step 3's ancestor walk; `None` means `Path.cwd()`. This mirrors
`resolve_history_db(root=)` (`session_store/db.py:121-132`), whose docstring
records why a cwd-only anchor failed once already: `ll-mcp` receives
`--project-root` far from cwd (BUG-3181). FEAT-3410 is a CLI and may leave
`start` unset today; the parameter exists so a non-CLI caller never has to
`os.chdir()` to steer discovery. Step 1 ignores `start` entirely.

   This single rule replaces an earlier two-step design
   (`find_project_root(cwd) / "ll-workspace.yaml"`, else cwd). That design was
   broken by stray ancestor `.ll/` dirs: `find_project_root()` returns the
   nearest `.ll`-only ancestor whenever no `.git` boundary is crossed, so from
   a workspace parent dir (no `.ll/`, no `.git`) it resolves to e.g.
   `~/AIProjects` (reproduced on the dev machine, where `~/AIProjects/.ll`
   exists) and the cwd fallback never fires — defeating FEAT-3399's "run one
   command from a workspace root" case. The ancestor walk covers both
   manifest layouts (checked into the primary repo with `repo: .`, or placed
   at a workspace parent above sibling repos) and works from a subdirectory or
   worktree of the primary repo. It does not consult `find_project_root()` at
   all for this step.

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

**Outcome**: A project with no `ll-workspace.yaml` gets an empty list,
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
- No manifest **discovered** (ancestor walk, step 3) must degrade cleanly,
  never raise. A manifest **declared** (explicit arg or config key) but
  missing raises `FileNotFoundError` — see Manifest Path Resolution →
  Absent-by-discovery vs absent-by-declaration.

## Files to Modify

- New module (path not yet chosen) implementing `discover_workspace_members()`
  — no existing file to modify since neither the function nor `WorkspaceMember`
  exists anywhere in the codebase today (confirmed 0 hits repo-wide).
- `config-schema.json:2117-2256` — the `history` object (real bounds:
  `additionalProperties: false` at `:2255`, object-close at `:2256`; four
  other nested blocks — `session_digest`, `evolution`, `go_no_go`,
  `capture_issue`, `compaction` — sit between the existing `db_path` property
  at `:2143-2146` and the true close) already has a `db_path` property with an
  `LL_HISTORY_DB`-env-var-precedence shape. Decided (see Proposed Solution →
  Decision Rationale): add `workspace_manifest_path` inside
  `properties.history.properties`, ahead of the `additionalProperties: false`
  gate at `:2255` — confirmed live by
  `test_config_schema.py::test_history_in_schema` (`:578`) and
  `test_history_db_path_in_schema` (`:615-628`), which exist specifically
  because the gate rejects undeclared keys.
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
- `scripts/little_loops/config/features.py:1513-1554` (`HistoryConfig` dataclass + `from_dict()`) — Decided (Proposed Solution → Decision Rationale): add the nested `history.workspace_manifest_path` field here alongside the existing `db_path` field/getter pair (`:1523`/`:1541`); no change needed to `config/core.py` or `config/__init__.py`, since `HistoryConfig`'s existing wiring already covers new fields on the dataclass.
- ~~`scripts/little_loops/config/core.py:31-35,370,518-520`~~ — not needed: the new-top-level-`workspace`-section path was not selected.
- ~~`scripts/little_loops/config/__init__.py:50,58,105,155`~~ — not needed: the new-top-level-`workspace`-section path was not selected.
- `scripts/tests/test_config_schema.py:1363-1430` (`_DATACLASS_SECTION_MAP`) — not required: a `_DATACLASS_SECTION_MAP` entry is only needed for a new dataclass, and the nested-scalar-on-`HistoryConfig` path adds no new dataclass.

_Wiring pass added by `/ll:wire-issue` (second pass):_
- **Confirmed NOT needed** (established exclusion precedent): `config/core.py::BRConfig.to_dict()`'s hand-written `"history"` dict (`:997-1026`) and the `/ll:configure` skill's field listings (`skills/configure/areas.md:1441-1452`, `skills/configure/show-output.md:250-261`) all already omit the sibling `db_path` field — the established convention for escape-hatch/manifest-path settings. `workspace_manifest_path` should follow the same exclusion: do not add it to `ll-config get`'s `to_dict()` output or `/ll:configure`'s interactive field lists.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` § `history` (table rows around `:616-620`, alongside the existing `history.db_path` row) — the authoritative doc site for any new `history.workspace_manifest_path` config key; not previously listed here.
- `docs/reference/API.md:3532-3563` (`### discover_all_projects` section) — the existing *runtime-discovered* projects concept this issue's declared-manifest approach should cross-reference; distinct from the already-listed lines 92/8207.
- **`docs/reference/API.md` — new module section and table row** (2026-09-08 review): every top-level module has its own `## little_loops.<name>` section (e.g. `## little_loops.decisions` at `:12174`) plus a row in the module table at `:46` (`| \`little_loops.decisions\` | Decisions and rules log data layer (FEAT-1891) |`). The new `workspace.py` needs both — a `## little_loops.workspace` section documenting `WorkspaceMember`, `discover_workspace_members()`, the resolution chain, and the raise-vs-degrade provenance rule, and a table row tagged `(FEAT-3409)`. This is distinct from the *framing* edits at `:92`/`:8208-8210`. No test enforces module coverage in API.md (checked `test_wiring_reference_docs.py`, `test_wiring_guides_and_meta.py`, `test_symbol_claims.py` — none enumerates modules), so a miss here would not fail the suite; add a `("docs/reference/API.md", "## little_loops.workspace", "FEAT-3409")` row to `DOC_STRINGS_PRESENT` to pin it.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No `conftest.py` fixture exists for writing a YAML manifest to `tmp_path` (searched, 0 hits) — the new test module needs its own module-local helper (e.g. `_write_manifest()`), following the `_write_tokens()` pattern in `scripts/tests/test_design_tokens.py:23-39`, not a shared fixture.
- Parsing-class shape precedent beyond the graceful-degradation classes already cited: `TestLoadDecisions` (`scripts/tests/test_decisions.py:109-183`) covers one-member/multi-member/malformed-YAML/missing-required-field/unknown-discriminator cases — mirror this shape for `discover_workspace_members()`'s happy-path and error-path tests, not just the absent-manifest degradation case.

_Wiring pass added by `/ll:wire-issue` (second pass):_
- `scripts/tests/test_config.py::TestHistoryConfig` (`:4245-4326`) — add `test_workspace_manifest_path_default_none`/`test_workspace_manifest_path_override`, modeled directly on `test_db_path_default_none`/`test_db_path_override` (`:4320-4326`) [Agent 3 finding].
- `scripts/tests/test_wiring_reference_docs.py`'s `DOC_STRINGS_PRESENT` list (`:150-156` area) — optional: add a `("docs/reference/CONFIGURATION.md", "workspace_manifest_path", "FEAT-3409")` row following the `db_path`/ENH-1916 precedent, to prove the new doc mention landed per the ENH-1963 convention [Agent 1/2 finding].

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Decision point:** Malformed-manifest posture (present but invalid `ll-workspace.yaml`)

**Option A**: Fail-closed/raise — mirror `artifact_templates.py::load_manifest()` (`:145-177`), catching `yaml.YAMLError`/schema violations and re-raising as a domain-specific error.

**Option B**: Fail-open/degrade — mirror `fsm/loop_paths.py::draft_internal_name()` (`:28-37`) / `config/core.py::parse_local_override_frontmatter()` (`:63-87`), catching `yaml.YAMLError` and returning the same empty/None result as the absent-manifest case.

**Option C**: No-wrap/propagate — mirror `decisions.py::load_decisions()` (`:369-385`), letting `yaml.YAMLError` (and missing-field errors) propagate unmodified to the caller.

> **Selected:** Option C — matches this issue's own cited dispatch model (`decisions.py::load_decisions()`) and scores highest (11/12); see Decision Rationale below.

**Decision point:** `db_path` derivation

**Option A**: Explicit per-entry manifest field — `db_path` authored directly in `ll-workspace.yaml` per member.

> **Selected:** Option A — avoids the `resolve_history_db()` composition hazard entirely; see Decision Rationale below.

**Option B**: Computed via `resolve_history_db(root=member.repo_path)` (`session_store/db.py:121-132`) — has a documented composition hazard: the `LL_HISTORY_DB` env-var check fires unconditionally ahead of the `root=`-scoped lookup, so calling it once per member in one process collapses every member's `db_path` onto the same value whenever `LL_HISTORY_DB` is set.

**Decision point:** Config registration path for a configurable manifest path

**Option A**: Nest under `history.workspace_manifest_path`, sibling to the existing `history.db_path` property (`config-schema.json:2143-2146`) — only touches `HistoryConfig` (`config/features.py:1513-1554`).

> **Selected:** Option A — smallest wiring footprint (only `HistoryConfig`), no new dataclass to register; see Decision Rationale below.

**Option B**: New top-level `workspace` config section, mirroring the `decisions` object's registration shape (`config-schema.json:704-728`) — requires a new `WorkspaceConfig` dataclass plus wiring in `config/core.py`, `config/__init__.py`, and `test_config_schema.py`'s `_DATACLASS_SECTION_MAP`.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Decision point:** Default `manifest_path` resolution (cwd-relative vs. project-root-anchored)

**Option A**: Keep the bare cwd-relative default as currently specified in Expected Behavior — `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml"))`, resolved against whatever the process's current working directory happens to be at call time.

**Option B**: Anchor the default via `find_project_root(Path.cwd())` (`scripts/little_loops/paths.py:14-41`) — e.g. `find_project_root(Path.cwd()) / "ll-workspace.yaml"` — mirroring `decisions.py::_resolve_path()` (`decisions.py:26-41`), the function backing this issue's own cited dispatch model (`load_decisions()`), which explicitly anchors its default "at the resolved project root (ENH-2927) instead of a bare cwd-relative path."

> **Selected:** Option B, **subsequently revised** (2026-09-08 review) to a nearest-ancestor walk that does not call `find_project_root()` — see Decision Rules → Default `manifest_path` resolution for the stray-`.ll` failure that forced the revision. Original rationale retained below. This issue's own chosen precedent (`decisions.py::load_decisions()`) deliberately rejects a bare cwd-relative default for exactly the reason `resolve_ll_dir()`'s docstring states: it "let stray `.ll/` directories accumulate outside the project root" (`paths.py:52-54`). A bare-cwd `ll-workspace.yaml` default reproduces the same failure mode one level up (repo root instead of `.ll/`) — a caller invoking `discover_workspace_members()` from a subdirectory or worktree would silently miss the manifest. `resolve_ll_dir()` itself isn't directly reusable (the manifest lives at the repo root, not under `.ll/`), but `find_project_root()` is the same primitive one level up, with no other call site resolving a repo-root-relative manifest default this way to confirm the composition against.

### Decision Rationale

**Decision point: Malformed-manifest posture**

Selected: **Option C** (No-wrap/propagate). This codebase holds three disagreeing conventions for a present-but-malformed manifest; Option C matches the issue's own cited dispatch model (`decisions.py::load_decisions()`), which deliberately does not catch `yaml.YAMLError` for its flat file, "preserving ENH-2589 corruption gating" per its own docstring. `ll-workspace.yaml` is a structural analog to `decisions.yaml` — a small, hand-authored registry where a silently-swallowed error (Option B) risks a cross-repo aggregation silently dropping a workspace member, and a swallowed-then-rewrapped error (Option A) adds a new exception class this codebase has no existing convention for surfacing to `discover_workspace_members()`'s callers.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — fail-closed/raise | 2 | 2 | 3 | 3 | 10/12 |
| B — fail-open/degrade | 2 | 3 | 3 | 1 | 9/12 |
| **C — no-wrap/propagate** | **3** | **3** | **3** | **2** | **11/12** |

Key evidence: `decisions.py::load_decisions()` (`:369-385`) is this issue's own cited hand-parsed-dispatch model and does not wrap `yaml.YAMLError`; `test_decisions.py::test_raises_yaml_error_on_othe_203_corruption` (`:153-164`) and the independent `test_verify_decisions.py::TestLoadDecisionsMalformedInput` (`:42`) confirm this is a deliberately tested posture, not an oversight.

**Decision point: `db_path` derivation**

Selected: **Option A** (explicit per-entry manifest field). Option B's mechanism, `resolve_history_db(root=member.repo_path)`, has a documented composition hazard: `_resolve_db_path()`'s `LL_HISTORY_DB` env-var check (`session_store/db.py:107-109`) fires unconditionally ahead of the `root=`-scoped config lookup, so calling it once per member in the same process collapses every member's `db_path` onto the same value whenever `LL_HISTORY_DB` is set in the environment — silently defeating the entire point of a multi-repo workspace. No existing call site invokes `resolve_history_db()` more than once per process with different `root=` values, so there is no precedent this hazard has already been solved elsewhere.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| **A — explicit manifest field** | **2** | **3** | **3** | **3** | **11/12** |
| B — `resolve_history_db(root=...)` | 1 | 2 | 1 | 0 | 4/12 |

Key evidence: `session_store/db.py:105-132` (`_resolve_db_path`/`resolve_history_db`) — the env-var check precedes the `root=`-scoped branch unconditionally.

**Decision point: Config registration path**

Selected: **Option A** (nest under `history.workspace_manifest_path`). Per this issue's own Dependent Files findings, Option A touches only `HistoryConfig`'s dataclass and `from_dict()` (`config/features.py:1513-1554`) with no change needed to `config/core.py` or `config/__init__.py`. Option B requires a new `WorkspaceConfig` dataclass plus wiring across three additional files, including a `_DATACLASS_SECTION_MAP` entry that a missing update fails at test collection (`TestDataclassSectionMapCompleteness`, `test_config_schema.py:1433`).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| **A — nest under `history`** | **3** | **3** | **3** | **3** | **12/12** |
| B — new top-level `workspace` section | 2 | 1 | 2 | 1 | 6/12 |

Key evidence: `config-schema.json:2117-2146` (`history` object, existing `db_path` sibling); `config-schema.json:704-728` (`decisions` object, the top-level-section precedent Option B would mirror); `test_config_schema.py:1363-1430,1433` (`_DATACLASS_SECTION_MAP` + completeness gate).

## Program Design

### Types

- `WorkspaceMember` (`@dataclass(frozen=True)` — it crosses the producer/consumer boundary to FEAT-3410, the shape `host_runner.py:316-327`'s stated `frozen=True` convention targets; the mutable precedents `ArtifactTemplate`/`CompletedIssue` predate that convention): `repo_path: Path` (resolved absolute), `role: str`, `db_path: Path` (resolved absolute)
- `HistoryConfig.workspace_manifest_path: str | None = None` — `str`, not `Path`, matching the sibling `db_path: str | None` field and the schema's `["string", "null"]` type

### Signatures

- `discover_workspace_members(manifest_path: Path | None = None, *, start: Path | None = None) -> list[WorkspaceMember]` — `None` `manifest_path` triggers the three-step resolution chain in Expected Behavior → Manifest Path Resolution; `start` (default `Path.cwd()`) seeds steps 2 and 3. Returns `[]` (never `None`) when step 3 finds nothing; raises `FileNotFoundError` when a step-1/step-2 path does not exist.
- `_ResolvedManifest(path: Path, declared: bool)` — private `frozen=True` result of the resolver; `declared` is `True` for steps 1–2 (explicit arg / config key) and `False` for step 3, so the caller can branch raise-vs-`[]` on provenance.
- `_resolve_manifest_path(manifest_path: Path | None, start: Path) -> _ResolvedManifest` — private resolver: explicit arg (`.expanduser().resolve()`d, not verbatim — see Manifest Path Resolution step 1) → config key (`_config_manifest_path(find_project_root(start))`) → nearest-ancestor walk from `start` (see `_find_manifest_upward`); mirrors the explicit-arg-wins contract of `decisions.py::_resolve_path()` (`decisions.py:26-41`) but does **not** delegate to `find_project_root()` for the ancestor-walk default (see Manifest Path Resolution step 3). `.path` is always absolute.
- `_find_manifest_upward(start: Path) -> Path | None` — private walk over `start.resolve()` and its parents returning the first `<dir>/ll-workspace.yaml` that exists, else `None`
- `_config_manifest_path(root: Path | None) -> Path | None` — private config reader: lazily imports `BRConfig` (as `design_tokens.py:25` does), returns `BRConfig(root).history.workspace_manifest_path` with `~` expanded and relative values resolved against `root`; `None` when `root` is `None` or the key is unset. Inherits `BRConfig`'s `ll.local.md` deep-merge (BUG-3123). `root` is `find_project_root(start)` and therefore carries the stray-`.ll` ancestor behavior documented in Manifest Path Resolution step 2.

### Call Path

`discover_workspace_members(manifest_path, start=None)` -> `start = (start or Path.cwd()).resolve()` -> `_resolve_manifest_path(manifest_path, start)` (explicit arg `.expanduser().resolve()`d, `declared=True` → config key via `_config_manifest_path(find_project_root(start))`, `declared=True` → `_find_manifest_upward(start)` → `start / "ll-workspace.yaml"`, `declared=False`; `.path` always absolute) -> `Path.exists()` guard (`declared` → raise `FileNotFoundError` naming path and provenance; not `declared` → return `[]`) -> `yaml.safe_load(manifest_path.read_text())` -> top-level shape check (`dict` with `members` list, else `ValueError`; `None` from an empty file fails this check) -> per-entry shape check (`entry` is a mapping; `entry["repo"]`/`entry["role"]` present — `KeyError` — and non-empty `str` — `ValueError`; `entry.get("db_path")`, when truthy, is a `str` — `ValueError`) -> per-entry construction of `WorkspaceMember(repo_path=(manifest_dir / Path(entry["repo"]).expanduser()).resolve(), role=entry["role"], db_path=((repo_path / Path(db_path_raw).expanduser()) if (db_path_raw := entry.get("db_path")) else repo_path / ".ll" / "history.db").resolve())` — note the single trailing `.resolve()` applies to **both** the explicit and default `db_path` branches -> duplicate-`db_path` check (`ValueError`) -> returned `list[WorkspaceMember]`. No existence check on `repo_path`/`db_path`. No caller exists yet in this codebase — FEAT-3410's ATTACH-based aggregation entry point is the sole intended consumer, feeding each returned member's `db_path` into a per-member `ATTACH DATABASE` call in the shape of `build_snapshot_db` (`scripts/little_loops/session_store/queries.py:246-301`, today's only `ATTACH DATABASE` call site, single-source/single-alias — a multi-member attach loop has no existing precedent to confirm against).

### Decision Rules

- **Malformed-manifest posture** (present but invalid `ll-workspace.yaml`): **Resolved** — no-wrap/propagate, mirroring `decisions.py::load_decisions()`; `yaml.YAMLError` and missing-field errors propagate unmodified to the caller. See Proposed Solution → Decision Rationale for the full scoring against the fail-closed/raise and fail-open/degrade alternatives.
- **`db_path` derivation**: **Resolved** — explicit per-entry manifest field, authored directly in `ll-workspace.yaml`. `resolve_history_db(root=member.repo_path)` was rejected: its `LL_HISTORY_DB` env-var check fires unconditionally ahead of the `root=`-scoped lookup (`session_store/db.py:107-109`), which would collapse every member's `db_path` onto the same value whenever `LL_HISTORY_DB` is set. See Proposed Solution → Decision Rationale.
- **Default `manifest_path` resolution**: **Resolved (revised 2026-09-08)** —
  explicit arg → config key → nearest-ancestor walk from cwd, per Expected
  Behavior → Manifest Path Resolution. Proposed Solution Option B
  (`find_project_root(cwd) / "ll-workspace.yaml"` with cwd fallback) was
  selected first and then found broken: `find_project_root()` returns a stray
  `.ll`-only ancestor (e.g. `~/AIProjects/.ll`) from a workspace parent dir,
  so the cwd fallback never fires. The ancestor walk keeps Option B's
  motivation (no bare cwd literal; works from subdirs/worktrees) without
  depending on `.ll/` placement. The signature is
  `manifest_path: Path | None = None`, not a bare `Path("ll-workspace.yaml")`
  literal.
- **Relative `db_path` base**: **Resolved** — relative to the entry's resolved
  `repo_path`, not the manifest dir (see Manifest Format rules for the
  footgun this avoids).
- **Duplicate members**: **Resolved** — colliding resolved `db_path` values
  raise `ValueError` (no-wrap/fail-loud posture; prevents FEAT-3410
  double-attaching one database).
- **Empty file vs. empty `members`**: **Resolved** — empty file is malformed
  (`ValueError`); `members: []` returns `[]`.
- **Existence checks**: **Resolved** — none. FEAT-3410 owns missing/skewed
  member DB handling.
- **Member repo's own `history.db_path` config**: **Resolved** — ignored;
  documented limitation. `session_store/db.py::_config_db_path(root=)` could
  honor it without the `LL_HISTORY_DB` hazard, but it is private and the
  manifest field already covers the case; revisit only if a consumer needs it.
- **Return type on absent manifest**: **Resolved** — `[]`, never `None`. A
  `None` branch would force every consumer (FEAT-3410 first) to null-check
  before iterating.
- **Absent-by-discovery vs absent-by-declaration** (2026-09-08 review, third
  pass): **Resolved** — `[]` applies only when the ancestor walk (step 3)
  finds nothing. A path that came from the explicit arg or the config key
  and does not exist raises `FileNotFoundError` naming the path and its
  provenance. Rationale: a typo in `--workspace <path>` or
  `history.workspace_manifest_path` would otherwise silently degrade to
  single-repo output, and the consumer cannot tell "no workspace" from
  "misconfigured workspace" from a bare `[]`. `_resolve_manifest_path()`
  returns `_ResolvedManifest(path, declared)` so the guard can branch.
- **Default `db_path` resolution** (2026-09-08 review, third pass):
  **Resolved** — the static default is `.resolve()`d exactly like an explicit
  `db_path`, so the duplicate check compares resolved against resolved. Without
  it, an explicit entry aliasing `<repo>/.ll/history.db` through a symlinked
  `.ll/` would slip past the check. `Path.resolve()` is non-strict, so this
  does not violate the no-existence-check rule.
- **`~` expansion** (2026-09-08 review, third pass): **Resolved** — `repo`,
  `db_path`, and the config-key value are passed through `Path.expanduser()`
  before resolution. `history.db_path`'s reader does not expand `~`; the
  divergence is deliberate (a gitignored machine-local manifest is the
  expected home for `~`-paths) and documented in the docstring and
  `CONFIGURATION.md` row.
- **`start` seed** (2026-09-08 review, third pass): **Resolved** — keyword-only
  `start: Path | None = None` seeds steps 2 and 3 (`None` → `Path.cwd()`),
  mirroring `resolve_history_db(root=)` (BUG-3181's fix for `ll-mcp`'s
  `--project-root` being far from cwd). Step 1 ignores it.
- **Missing-field / bad-shape exceptions**: **Resolved** — missing `repo`/`role`
  raises `KeyError`; non-mapping top level, missing/non-list `members`, a
  non-mapping entry, a non-string or empty `repo`/`role`, or a present
  non-string `db_path` raises `ValueError`; malformed YAML propagates
  `yaml.YAMLError` unmodified. All three are the no-wrap posture. No other
  exception type may escape for a shape problem — in particular `db_path:`
  with a `None` value must not reach `repo_path / None` (`TypeError`).
- **`db_path` absent-vs-present** (2026-09-08 review): **Resolved** — `None`
  and `""` count as absent (static default applies); presence is tested with
  `entry.get("db_path")`, not `"db_path" in entry`.
- **Explicit `manifest_path` normalization** (2026-09-08 review):
  **Resolved** — the explicit arg is `.resolve()`d before use, not returned
  verbatim; precedence is unchanged. `_resolve_manifest_path()` always
  returns an absolute path.
- **Config-key step and `find_project_root()`** (2026-09-08 review):
  **Resolved** — step 2 locates the project root via `find_project_root(start)`
  and therefore inherits the stray-`.ll` ancestor behavior step 3 avoids.
  Accepted and documented (Manifest Path Resolution step 2) rather than
  special-cased; one test pins each branch.
- **Config-key reader: `BRConfig` vs raw JSON** (2026-09-08 review, third
  pass): **Resolved** — read via `BRConfig(root).history.workspace_manifest_path`,
  not a raw-JSON mirror of `_config_db_path`. The precedent reads raw JSON
  only because `session_store/db.py` cannot import `little_loops.config`
  (layering); `workspace.py` is top-level and `design_tokens.py:25` already
  imports `BRConfig` from that tier. `BRConfig` deep-merges `ll.local.md`
  (BUG-3123), which removes the "local overrides not merged" limitation the
  raw-JSON design had to document. Cost: `BRConfig.__init__` runs
  `load_env_fallback()` (`config/core.py:287`); acceptable, every CLI already
  does. Import is lazy inside `_config_manifest_path()`.
- **Symlinked members**: **Resolved** — `.resolve()` follows symlinks;
  `repo_path`/`db_path` are stored as real paths. Docstring note only.
- **Frozen vs mutable**: **Resolved** — `frozen=True` (see Types).
- **Cross-issue consistency**: FEAT-3410's Design Notes previously recommended
  `resolve_history_db(root=member.repo_path)` per member — contradicting this
  issue's `db_path` decision. FEAT-3410 has been corrected to consume
  `member.db_path` directly. Second consistency point (2026-09-08 review):
  FEAT-3410 previously had zero mentions of `role`, making this issue's
  required field dead data. FEAT-3410 now carries a rule that its per-repo
  breakdown labels each member with `member.role` alongside the repo path.
  Third consistency point (2026-09-08 review, third pass): FEAT-3410's
  "no-manifest fallback" rule assumes `[]` is the only absent outcome. It now
  also notes that a declared-but-missing manifest (explicit `--workspace`
  path or config key) surfaces as `FileNotFoundError` from
  `discover_workspace_members()`, which the CLI must report as a user error
  rather than swallow into the single-repo fallback.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Frozen-vs-mutable is not resolved by majority precedent**: a repo-wide sweep confirms the split is real at scale, not an artifact of the two cited examples — 158 frozen-dataclass declarations vs. 327 plain `@dataclass` declarations across `scripts/little_loops/`. Frequency alone does not favor either convention for `WorkspaceMember`.
- **Malformed-manifest three-way tie is exhaustive, not under-sampled**: a broader sweep of all ~45 `yaml.safe_load()`/`yaml.load()` call sites in the package found no fourth handling convention and no other manifest-shaped parser beyond the three already cited (fail-closed `artifact_templates.py:161-163`, fail-open `fsm/loop_paths.py:31-33` / `config/core.py:83-86`, no-wrap `decisions.py:381`). Further codebase research will not resolve this — it needs an explicit choice, not more searching.
- **No other multi-instance `db_path`-derivation precedent exists**: confirmed no call site anywhere in the codebase invokes `resolve_history_db()` more than once per process with different `root=` values, and no other function with an equivalent per-instance-derivation shape exists to model the composition hazard's handling against.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Default `manifest_path` resolution is unspecified relative to project root, and the issue's own cited dispatch model does not use a bare cwd-relative default**: Expected Behavior's signature is `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml"))` — a bare relative `Path` literal. But `decisions.py::_resolve_path()` (`decisions.py:26-41`), the function backing this issue's own cited dispatch model (`load_decisions()`), explicitly rejects that shape: its docstring states it anchors the default "at the resolved project root (ENH-2927) instead of a bare cwd-relative path," delegating to `little_loops.paths.resolve_ll_dir()` -> `find_project_root()` (`paths.py:14-41,45`). `resolve_ll_dir()`'s own docstring calls building `Path(".ll/...")` against a bare cwd the exact pattern that "let stray `.ll/` directories accumulate outside the project root" (`paths.py:52-54`) — the same class of bug a bare-cwd `ll-workspace.yaml` default would reproduce for a manifest one level higher (repo root, not `.ll/`). `resolve_ll_dir()` itself is not directly reusable (`ll-workspace.yaml` is proposed to live at the repo root, not under `.ll/`), but `find_project_root(Path.cwd())` is the same primitive one level up. No other call site in the codebase resolves a repo-root-relative (non-`.ll/`) manifest default this way, so there is no existing precedent to confirm the exact composition against — this is a gap in the issue's own specified default, not a resolved question.

## Implementation Steps

1. Define `WorkspaceMember` (`frozen=True`) and implement
   `discover_workspace_members()`, hand-parsing `ll-workspace.yaml` with
   `yaml.safe_load()` per the `decisions.py::load_decisions()` dispatch model
   and the Manifest Format rules (`members:` list; `repo`/`role` required;
   `db_path` optional, defaulting to `repo/.ll/history.db` by static `Path`
   join; relative paths resolved against the manifest's parent dir; `~`
   expanded via `Path.expanduser()` on `repo` and `db_path`; the default
   `db_path` is `.resolve()`d the same as an explicit one).
   Also: `db_path` relative to the entry's `repo_path`; duplicate resolved
   `db_path` → `ValueError`; empty file → `ValueError`; `members: []` → `[]`;
   no existence checks; docstring notes that a member's own `history.db_path`
   config is not consulted.
2. Implement `_find_manifest_upward()`, `_ResolvedManifest`, and
   `_resolve_manifest_path(manifest_path, start)` (explicit arg → config key
   → nearest-ancestor walk from `start` → `start / "ll-workspace.yaml"`),
   threading the keyword-only `start: Path | None = None` seed from
   `discover_workspace_members()`. The `Path.exists()` guard branches on
   `declared`: `True` → `FileNotFoundError` naming the path and provenance;
   `False` → `[]` with the documented fallback target in the docstring. Do
   not route the default through `find_project_root()` (see Manifest Path
   Resolution step 3 for why).
3. Implement config registration for the configurable manifest path as
   `history.workspace_manifest_path` (decided — see Proposed Solution →
   Decision Rationale); add a matching `test_*_in_schema` test following the
   existing per-property convention (e.g. `test_decisions_in_schema:319`).
   Implement `_config_manifest_path(root)` on top of
   `BRConfig(root).history.workspace_manifest_path` (lazy import, `~`
   expanded, relative resolved against `root`) — not a raw-JSON reader.
4. Add a graceful-degradation test class modeled exactly on
   `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) /
   `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`): one test
   per short-circuit branch, `tmp_path`-based (no manifest created), direct
   `== []`/`is None` return-value assertion.
5. Update `docs/ARCHITECTURE.md:714`, `docs/reference/API.md:92,8208-8210`,
   and `docs/reference/CLI.md:3775`'s "per-project"/single-repo framing to
   mention the new workspace-topology concept this manifest introduces (the
   aggregation-specific CLI/output docs belong to FEAT-3410, not here).
   Anchors corrected per the Documentation section's drift finding; re-check
   before editing since these files move often.
6. Add the new module's own `## little_loops.workspace` section to
   `docs/reference/API.md` (pattern: `## little_loops.decisions` at `:12174`)
   covering `WorkspaceMember`, `discover_workspace_members()` (including
   `start`), the three-step resolution chain, the raise-vs-`[]` provenance
   rule, and the `~`/symlink/`history.db_path`-not-consulted notes; plus a
   row in the module table at `:46` tagged `(FEAT-3409)`. Add a
   `("docs/reference/API.md", "## little_loops.workspace", "FEAT-3409")`
   row to `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` so the
   section's presence is test-pinned (no module-coverage gate exists
   otherwise — see Documentation). Also add the `~`-expansion and
   `FileNotFoundError`-on-declared-missing notes to the
   `docs/reference/CONFIGURATION.md` `history.workspace_manifest_path` row.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Place the new module at `scripts/little_loops/workspace.py` (or a similarly-named top-level module) — a top-level sibling of `decisions.py`/`design_tokens.py`, not a subpackage, not re-exported from `scripts/little_loops/__init__.py` or `config/__init__.py`.
- Decided (Proposed Solution → Decision Rationale): the nested `history.workspace_manifest_path` config path — update only `scripts/little_loops/config/features.py`'s `HistoryConfig` dataclass and `from_dict()`. ~~The new top-level `workspace` config section~~ was not selected.
- Update `docs/reference/CONFIGURATION.md` § `history` with the new `history.workspace_manifest_path` doc row.
- Write a module-local YAML-manifest test helper (e.g. `_write_manifest()`) — no shared `conftest.py` fixture exists to reuse.
- Add `workspace_manifest_path` inside `config-schema.json`'s `properties.history.properties` block, ahead of the object's real `additionalProperties: false` close at `:2255-2256` (not `:2146` as originally cited — see Files to Modify anchor correction).
- Add `test_workspace_manifest_path_default_none`/`test_workspace_manifest_path_override` to `scripts/tests/test_config.py::TestHistoryConfig`, modeled on `test_db_path_default_none`/`test_db_path_override` (`:4320-4326`).
- Optional: add a `scripts/tests/test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` row for `workspace_manifest_path` documentation, following the `db_path`/ENH-1916 precedent.

## Tests

- New test module/class for `discover_workspace_members()`: manifest parses into
  correct `WorkspaceMember` rows; absent manifest degrades to empty/None,
  following `TestDecisionsGracefulDegradation`/`TestLoadDesignTokensFallbacks`;
  a malformed manifest raises, following `TestLoadDecisions`'s malformed-input
  cases (decided posture: no-wrap/propagate).
- Edge-case class (2026-09-08 review): duplicate `db_path` → `ValueError`;
  empty file → `ValueError`; `members: []` → `[]`; repo-relative `db_path`;
  nonexistent `repo_path`/`db_path` still returned; stray-ancestor-`.ll`
  regression for the nearest-ancestor walk (see Acceptance Criteria).
- Value-type class (2026-09-08 review, second pass): `db_path:` with no value
  and `db_path: ""` both yield the static default (no `TypeError`, no
  `repo_path`-as-db); `role: 1`, `repo: 1`, `role: ""`, and `db_path: 1`
  each raise `ValueError`; a relative explicit `manifest_path` arg still
  yields absolute `repo_path`/`db_path` on the returned members; a
  symlinked member repo is stored by its real path.
- Config-step class (2026-09-08 review, second pass): stray ancestor
  `.ll/ll-config.json` carrying `history.workspace_manifest_path` → that
  manifest is used; stray ancestor `.ll/` with no config → falls through to
  the ancestor walk; (third pass) an `.ll/ll.local.md` frontmatter override
  of `history.workspace_manifest_path` is honored over the base config value
  (proves the `BRConfig` reader, not a raw-JSON one, is in use).
- Provenance class (2026-09-08 review, third pass): explicit `manifest_path`
  pointing at a nonexistent file → `FileNotFoundError` whose message names
  the path; `history.workspace_manifest_path` pointing at a nonexistent file
  → `FileNotFoundError`; no config key and no ancestor manifest → `[]` (the
  only degrade branch). Also: `start=` pointing at a directory holding a
  manifest, while cwd is an unrelated `tmp_path` dir with none, finds the
  manifest without `monkeypatch.chdir`; `start=` is ignored when
  `manifest_path` is explicit.
- Path-normalization class (2026-09-08 review, third pass): `repo: ~/x`
  and `db_path: ~/x.db` expand `~` (`monkeypatch.setenv("HOME", tmp_path)`);
  an explicit `db_path` that aliases the default through a symlinked `.ll/`
  collides with a second entry's default and raises `ValueError` (proves the
  default is resolved too).
- `scripts/tests/test_config_schema.py` — add a `test_history_workspace_manifest_path_in_schema`
  matching per-property test for the new `history.workspace_manifest_path` property.

_Wiring pass added by `/ll:wire-issue`:_
- ~~`scripts/tests/test_config_schema.py`'s `_DATACLASS_SECTION_MAP` (`:1363-1430`)~~ — not needed: no new dataclass is introduced under the decided nested-scalar-on-`HistoryConfig` path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Per-property schema test convention confirmed at `scripts/tests/test_config_schema.py:319` (`test_decisions_in_schema`) and its `history`-namespace siblings `:564`/`:615`/`:630` (`test_history_in_schema`, `test_history_db_path_in_schema`, `test_history_compaction_in_schema`) — 39 such tests exist total, each asserting one property's `type`/`default` against `data["properties"][...]`.
- A dataclass-to-schema-key mapping table exists at `scripts/tests/test_config_schema.py:1386,1409-1418` (e.g. `"DecisionsConfig": "decisions"`, `"HistoryConfig": "history"`) — a new `workspace` config class (if added) needs an entry here in addition to the per-property test.
- Graceful-degradation test shape confirmed exactly as cited: `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) and `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`) both use `tmp_path`, one test per short-circuit branch, direct `== []`/`is None` assertions — neither class asserts a raised exception (raise-path tests, where they exist, live in separate sibling classes, e.g. `TestLoadDesignTokensErrors`).

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- An additional malformed-input test-class precedent beyond `TestLoadDecisions`: `TestLoadDecisionsMalformedInput` (`scripts/tests/test_verify_decisions.py:42`) — a second existing example of how this codebase tests a malformed-YAML-manifest case, directly relevant to the now-resolved malformed-manifest-posture Decision Rule above (no-wrap/propagate).

## Impact

- **Priority**: P1 — prerequisite for FEAT-3410's cross-repo aggregation; no
  standalone user-facing behavior change until FEAT-3410 consumes it.
- **Effort**: Small — a single hand-parsed YAML manifest with a well-precedented
  graceful-degradation shape; no SQLite or ATTACH mechanics.
- **Risk**: Low — read-only manifest parsing, no database access.
- **Breaking Change**: No

## Acceptance Criteria

- `discover_workspace_members()` parses a well-formed `ll-workspace.yaml` into
  the correct `WorkspaceMember` list: `repo_path`/`db_path` are absolute,
  resolved against the manifest's parent directory; an entry without
  `db_path` gets `(repo_path / ".ll" / "history.db").resolve()` without calling
  `resolve_history_db()` (test: set `LL_HISTORY_DB` in the environment and
  assert two members still get two distinct `db_path` values). The default
  is resolved like an explicit `db_path`: an explicit entry aliasing another
  entry's default through a symlinked `.ll/` raises the duplicate
  `ValueError`.
- `WorkspaceMember` is `frozen=True` (attribute assignment raises
  `FrozenInstanceError`).
- Absent-by-discovery manifest (ancestor walk finds nothing, no explicit arg,
  no config key) degrades to `[]` (not `None`) without raising, covered by a
  dedicated graceful-degradation test class.
- Absent-by-declaration manifest raises: an explicit `manifest_path` that
  does not exist, or a `history.workspace_manifest_path` that does not exist,
  raises `FileNotFoundError` whose message names the path — one test per
  provenance. `[]` is never returned for a declared-but-missing manifest.
- `~` is expanded in `repo`, `db_path`, and `history.workspace_manifest_path`
  values (`Path.expanduser()` before `.resolve()`), covered by a test that
  sets `HOME` to `tmp_path`.
- `discover_workspace_members()` accepts keyword-only `start: Path | None =
  None` seeding the config-root lookup and the ancestor walk; a test passes
  `start=` pointing at a manifest-holding directory while cwd holds none and
  asserts the manifest is found without `monkeypatch.chdir`; a second test
  asserts `start=` is ignored when `manifest_path` is explicit.
- The config-key step reads through `BRConfig` (not raw JSON): a test writes
  `.ll/ll-config.json` with one `history.workspace_manifest_path` and
  `.ll/ll.local.md` frontmatter overriding it, and asserts the override wins.
- Default-path resolution follows the documented chain: explicit arg wins
  (and is `.resolve()`d — a relative arg still yields absolute
  `repo_path`/`db_path` on every returned member);
  `history.workspace_manifest_path` is honored when the arg is `None`; with no
  config key, the nearest ancestor of `start` (default cwd) holding
  `ll-workspace.yaml` wins —
  one test per branch, using `tmp_path` + `monkeypatch.chdir`, plus one
  regression test for the stray-`.ll` case: cwd is a `ws/` subdir of
  `tmp_path` (manifest present in `ws/`, no `.ll/`, no `.git`) while
  `tmp_path` itself holds a `.ll/` dir and a second manifest — the one in
  `ws/` must be found, not the one beside the stray `.ll/`. A second walk
  test: cwd is a
  subdirectory of the primary repo and the manifest sits at the repo root.
- Config-key step inherits `find_project_root()` semantics, pinned by two
  tests: a stray ancestor `.ll/ll-config.json` (no `.git`) carrying
  `history.workspace_manifest_path` is honored; the same stray `.ll/` with no
  config file falls through to the ancestor walk.
- Value-type edge cases raise the documented types and nothing else:
  `db_path:` with a `None` value and `db_path: ""` both resolve to the static
  default (no `TypeError`); a non-string or empty `repo`/`role`, or a present
  non-string `db_path`, raises `ValueError`.
- Relative `db_path` resolves against the entry's `repo_path`: a sibling entry
  with `db_path: .ll/history.db` yields `<sibling>/.ll/history.db`, not the
  manifest dir's.
- Two entries resolving to the same `db_path` raise `ValueError`; an empty
  manifest file raises `ValueError`; `members: []` returns `[]`; a member whose
  `repo_path`/`db_path` does not exist on disk is still returned (no filtering).
- `history.workspace_manifest_path` is registered in `config-schema.json`
  (nested under the existing `history` object — decided per Proposed Solution
  → Decision Rationale), with a matching
  `test_history_workspace_manifest_path_in_schema` schema test.
- A present-but-malformed `ll-workspace.yaml` propagates unmodified to the
  caller — no-wrap/propagate, per Decision Rules: bad YAML syntax raises
  `yaml.YAMLError`; an entry missing `repo`/`role` raises `KeyError`; a
  non-mapping top level, missing/non-list `members`, or non-mapping entry
  raises `ValueError` — covered by
  malformed-input tests mirroring `TestLoadDecisions`
  (`test_decisions.py:109-183`) / `TestLoadDecisionsMalformedInput`
  (`test_verify_decisions.py:42`).
- `history.workspace_manifest_path` is threaded through `HistoryConfig`'s
  dataclass field and `from_dict()` (`config/features.py:1513-1554`), covered
  by `test_workspace_manifest_path_default_none`/
  `test_workspace_manifest_path_override` in
  `test_config.py::TestHistoryConfig` (`:4245-4326`).
- `docs/reference/API.md` carries a `## little_loops.workspace` section and a
  module-table row for the new module, pinned by a
  `("docs/reference/API.md", "## little_loops.workspace", "FEAT-3409")` row
  in `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT`.

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

_Re-verified `/ll:verify-issues` — 2026-09-08 — graph: provider=`codegraph` freshness=`fresh`:_

- All prior file:line citations re-checked and still hold: `config-schema.json`
  `history` object at `:2117`, `db_path` property at `:2143-2146`, object close
  (`additionalProperties: false`) at `:2255-2256`; `HistoryConfig` class at
  `config/features.py:1513-1554`. `discover_workspace_members()`, `WorkspaceMember`,
  and `ll-workspace.yaml` still confirmed absent repo-wide. Parent (`FEAT-3399`)
  and sibling (`FEAT-3410`) references resolve. `ll-verify-evidence --json`:
  `"ok": true`, 0 findings. No active required decision rules.
- **New since the last verify pass**: a `## Proposed Solution` section was added
  (by `/ll:decide-issue` at 18:39:07, after both prior verify-issues runs at
  17:36/17:45) — check B6 (proposal-vs-code consequence check) had not yet run
  against it. Running it now surfaces a real gap:
  - **AC coverage gap #1**: the Decision Rules section resolves the
    malformed-manifest posture as Option C (no-wrap/propagate — a present-but-invalid
    `ll-workspace.yaml` must raise `yaml.YAMLError`/a missing-field error to the
    caller). This is a decided, load-bearing behavior, but no Acceptance Criterion
    states it — the AC list only covers the well-formed-parse and absent-manifest
    cases. It appears only as prose under `## Tests`. An implementation could pass
    all three listed ACs while accidentally swallowing malformed-manifest errors
    (e.g. adding a stray `try/except`) and nothing in the AC list would catch it.
  - **AC coverage gap #2**: the Wiring Phase and Dependent Files sections decide
    (Config registration path, Option A) that `history.workspace_manifest_path`
    must be wired into `HistoryConfig`'s dataclass fields and `from_dict()`
    (`config/features.py:1513-1554`), with dedicated tests named
    (`test_workspace_manifest_path_default_none`/`_override`,
    `test_config.py::TestHistoryConfig`). No Acceptance Criterion covers this.
    AC3 only requires the schema-registration test
    (`test_history_workspace_manifest_path_in_schema`); an implementation could
    add the schema property without ever threading it through `HistoryConfig`,
    leaving the config value schema-valid but inert, and still satisfy every
    listed AC.
  - Exception-handler compatibility and test-fixture invalidation (the other two
    B6 criteria): no findings — this is greenfield code with no existing caller
    or test fixture to conflict with.
- **Stale cross-reference noted (not itself a verdict driver)**: the
  `## Confidence Check Notes → Concerns` section (added 17:48:31) still reads
  "Two Decision Rules remain unresolved" and "Config registration path is also
  left open" — both were resolved by `/ll:decide-issue` at 18:39:07, after that
  note was written. Frontmatter (`decision_needed: false`) and the Decision
  Rules/Proposed Solution sections already reflect the resolved state; only the
  Concerns prose under Confidence Check Notes is now stale and should be updated
  or struck through on next touch.
- Verdict: **PROPOSAL_UNSOUND** (check B6) — all claims about current code state
  still hold (checks 1-4, evidence check, decisions check, dependency refs all
  clean), so this does not collapse to `OUTDATED`/`INVALID`; the defect is purely
  that the Acceptance Criteria under-cover the issue's own decided proposal. Add
  ACs for (a) malformed-manifest raise behavior and (b) `HistoryConfig` wiring of
  `workspace_manifest_path`, or fold them explicitly into the existing three ACs.

_Re-verified `/ll:verify-issues` — 2026-09-08 — graph: provider=`codegraph` freshness=`fresh`:_

- **AC gaps from the prior `PROPOSAL_UNSOUND` pass are closed**: that verdict (19:21:57)
  flagged two missing ACs — malformed-manifest-raise behavior, and `HistoryConfig`
  wiring of `workspace_manifest_path`. Both are now present as explicit ACs (the
  malformed-manifest AC and the `HistoryConfig`/`from_dict()` wiring AC), added by
  the `/ll:refine-issue` pass at 19:34:12. Re-running check B6 against the current
  Proposed Solution/Decision Rules/AC set finds no residual coverage gap.
- All codebase claims re-checked and hold: `config-schema.json` `history` object
  bounds (`:2117`, `:2143-2146`, `:2255-2256`), `HistoryConfig`
  (`config/features.py:1513-1554`), `session_store/db.py` env-precedence hazard
  (`:107-109`, `:121-132`), `decisions.py` dispatch model (`:353`, `:369`, `:381`,
  `:385`). `discover_workspace_members`/`WorkspaceMember`/`ll-workspace.yaml`
  still 0 hits repo-wide.
- The most-recently-added Documentation finding's three doc anchors (added since
  the last verify pass, not previously checked) confirmed exact:
  `docs/ARCHITECTURE.md:714`, `docs/reference/API.md:8208`/`:8210`/`:92`,
  `docs/reference/CLI.md:3775`.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- No active required decision rules — clean skip.
- Parent (`FEAT-3399`) and sibling (`FEAT-3410`) references both resolve; no
  `## Blocked By`/`## Blocks` sections to check.
- Verdict: **VALID** — supersedes the prior `PROPOSAL_UNSOUND` persisted verdict,
  which predated the AC-gap fix.

_Re-verified `/ll:verify-issues` — 2026-09-08 — graph: provider=`codegraph` freshness=`fresh`:_

- `discover_workspace_members`/`WorkspaceMember`/`ll-workspace.yaml` still 0 real
  hits repo-wide (only unrelated `node_modules` noise from an embedded npm
  package matched the grep).
- Spot-checked load-bearing citations against current source — all match
  exactly: `config-schema.json` `history` object/`db_path` property/object
  close; `HistoryConfig` dataclass + `from_dict()`
  (`config/features.py:1513-1554`); the `LL_HISTORY_DB` env-check-before-`root=`-
  scoped-lookup hazard (`session_store/db.py:105-132`); `decisions.py::load_decisions()`'s
  no-wrap `yaml.YAMLError` propagation.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- No active required decision rules — clean skip.
- Parent (`FEAT-3399`) and sibling (`FEAT-3410`) references both resolve.
- Re-ran check B6 against the current Proposed Solution/AC set: the prior
  `PROPOSAL_UNSOUND` AC-coverage gaps (malformed-manifest raise behavior,
  `HistoryConfig` wiring) remain closed; no residual gap.
- Verdict: **VALID** — unchanged from the prior pass.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 100/100 → PROCEED (frontmatter is authoritative; the
original 85/78 pass predated the decide-issue resolutions below)
**Outcome Confidence**: 74/100 → MODERATE

### Concerns
- ~~Two Decision Rules remain unresolved: malformed-manifest posture and
  `db_path` derivation.~~ Resolved by `/ll:decide-issue` (18:39) — see Decision
  Rules.
- ~~Config registration path is also left open.~~ Resolved (nested
  `history.workspace_manifest_path`).

_Manual review — 2026-09-08 — folded in: manifest format specification
(previously absent), `manifest_path: Path | None = None` signature aligned to
the project-root decision, four-step path-resolution precedence including who
reads the config key, `[]` return type pinned, concrete exception types,
`frozen=True`, `str | None` config field type, relative-path convention for
committed manifests, and the FEAT-3410 `resolve_history_db(root=)`
cross-issue conflict._

_Manual review (second pass) — 2026-09-08 — folded in: default-path
resolution revised to a nearest-ancestor walk after reproducing the
stray-`.ll` failure of `find_project_root()` from a workspace parent dir;
`db_path` now repo-relative; duplicate-member, empty-file, `members: []`, and
no-existence-check rules; member-config `history.db_path` limitation noted;
`role` consumer added to FEAT-3410; Step 5 doc anchors corrected; local
override non-merge noted for the config reader._

_Manual review (third pass) — 2026-09-08 — folded in: (1) declared-but-missing
manifest (explicit arg / config key) now raises `FileNotFoundError`; only the
ancestor-walk miss degrades to `[]` (`_ResolvedManifest.declared` carries
provenance); (2) default `db_path` is `.resolve()`d like an explicit one so
the duplicate check compares like with like; (3) config-key step reads via
`BRConfig(root).history.workspace_manifest_path` (lazy import), inheriting the
`ll.local.md` deep-merge, replacing the raw-JSON mirror of `_config_db_path`
and its documented non-merge limitation; (4) keyword-only `start: Path | None`
seed for steps 2–3, mirroring `resolve_history_db(root=)` / BUG-3181;
(5) `docs/reference/API.md` needs a `## little_loops.workspace` section and
module-table row, test-pinned via `DOC_STRINGS_PRESENT`; plus `~` expansion
on `repo`/`db_path`/config-key values pinned as a Decision Rule. Constraints,
Signatures, Call Path, Implementation Steps 1–3 and new Step 6, Tests, and
Acceptance Criteria updated to match. The prior `VALID` verify verdict
predates these edits._

## Session Log
- `/ll:confidence-check` - 2026-09-08T23:19:00 - `ee9b6e9d-61e7-4275-89c2-f498d623ae45.jsonl`
- `/ll:verify-issues` - 2026-09-08T23:15:34 - `3dd7ffea-f30a-4c9b-8a7c-b75eee0560e1.jsonl`
- `/ll:confidence-check` - 2026-09-08T22:55:29 - `6dd2bd32-5c1a-431a-9f43-0c09572d9b18.jsonl`
- `/ll:confidence-check` - 2026-09-08T22:13:14 - `c8d9f83d-83c6-4ca6-948a-bd5e1259be35.jsonl`
- `/ll:verify-issues` - 2026-09-08T22:10:26 - `5efb5fe2-2f1a-445a-a9f9-35c0b9974bdf.jsonl`
- `/ll:refine-issue` - 2026-09-08T22:02:01 - `b8cb2fff-d50b-4bf2-babb-458135fa8e22.jsonl`
- `/ll:decide-issue` - 2026-09-08T19:42:39 - `ec62a17d-6d92-4eb9-8c86-638b441ac713.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:34:12 - `98fcfd72-df15-46ed-a5e8-3df189a0e0ba.jsonl`
- `/ll:verify-issues` - 2026-09-08T19:21:57 - `9151ddc6-ab2d-4793-bd0e-e517d6829851.jsonl`
- `/ll:reconcile-issue` - 2026-09-08T19:17:31 - `8253aa54-816e-4b30-a515-5729bc18e0a3.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:11:30 - `2ff580d6-652f-49e4-b298-e76bb54b7ee2.jsonl`
- `/ll:wire-issue` - 2026-09-08T18:49:49 - `96ffa0f9-be3e-4674-b135-6a82c1057b6c.jsonl`
- `/ll:decide-issue` - 2026-09-08T18:39:07 - `1da9e372-c79e-4132-94c9-48b9fab73fe1.jsonl`
- `/ll:refine-issue` - 2026-09-08T18:33:22 - `d235f946-7b83-4228-9eed-a9bd5517b547.jsonl`
- `/ll:refine-issue` - 2026-09-08T18:20:33 - `93c855fd-cd38-4404-abc3-eca785ed7ae8.jsonl`
- `/ll:confidence-check` - 2026-09-08T17:48:31 - `da08f1cf-aa72-4044-9c86-40020b649222.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:45:51 - `c85a7f3d-8147-4f84-a4a8-b54c8bbd73dd.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T17:41:47 - `5027b454-4016-483b-bbf8-8af9131c8c75.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:36:08 - `130fcd36-de26-44a3-b91d-ce69b841840c.jsonl`
- `/ll:wire-issue` - 2026-09-08T17:31:32 - `fa35fcdd-03ef-4e02-8495-668286d605de.jsonl`
- `/ll:refine-issue` - 2026-09-08T17:21:28 - `9bcae330-1a21-42d2-bfd3-9b52b57ca4c1.jsonl`
- `/ll:issue-size-review` - 2026-09-08T06:21:27 - `c53583bd-6c7a-49a7-8685-76b64ad999da.jsonl`
