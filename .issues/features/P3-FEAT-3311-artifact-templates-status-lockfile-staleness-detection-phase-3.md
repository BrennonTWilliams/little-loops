---
id: FEAT-3311
type: FEAT
title: 'Artifact templates: status + lockfile staleness detection (Phase 3)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T03:57:16Z'
parent: EPIC-3299
depends_on:
- FEAT-3036
- FEAT-3310
labels:
- planning-hub
learning_tests_required:
- yaml
- jinja2
---

# FEAT-3311: Artifact templates: status + lockfile staleness detection (Phase 3)

## Summary

Phase 3 of FEAT-3036's artifact-template design: add `ll-artifact status`
(staleness detection) and its backing lockfile, so a refreshed artifact can
be checked against its source(s) without re-rendering.

## Current Behavior

`ll-artifact render` (Phase 1, FEAT-3036) and `refresh` (Phase 2, FEAT-3310)
have no way to report whether a rendered artifact is stale relative to its
source(s).

## Expected Behavior

`ll-artifact status [<template> ...]` compares recorded source hashes
(sha256, stored in a machine-written `<template>.llat.lock` sibling file
next to the template — never written into `manifest.yaml`, per FEAT-3036 §
Second-pass decisions -> *Lockfile is keyed by source path, not a scalar*)
against current source content hashes, reporting `FRESH` / `STALE` /
`SOURCE-MISSING` per `(template, source)` pair. Exits non-zero if anything is
stale (CI-friendly; per CLAUDE.md this is exercised by a pytest test that
invokes it, not a hosted CI workflow).

The lockfile is a mapping keyed by rendered source path (not a scalar), so it
can express EPIC-3299's primary use case (one template, many source
documents), not only "one template, one source over time":

```yaml
version: 1
renders:
  docs/risk-register.md: {sha256: ..., rendered_at: ..., output: ...}
```

## Use Case

A user maintains `quarterly-risk-report.llat/`, refreshed periodically
against `docs/risk-register.md` (FEAT-3036 / FEAT-3310). Before trusting the
last-rendered `quarterly-risk-report.html`, they run `ll-artifact status` in
CI to confirm nothing has drifted since the last refresh; a non-zero exit
fails the build if the register changed without a re-render.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/artifact/status.py` (new) — `cmd_status`, `add_status_parser`, per this issue's own Program Design → Call Path.
- `scripts/little_loops/cli/artifact/render.py` (`cmd_render`, render.py:27-88) — gains a lockfile-write step after `out_path.write_text(...)` and before `logger.success`/`return 0`; currently no lockfile write occurs anywhere in this function (confirmed by direct read — the function logs success and returns immediately after the file write).
- `scripts/little_loops/cli/artifact/__init__.py` (`main_artifact`, :40-136) — needs `add_status_parser(subparsers)` wired alongside `add_render_parser`/`add_templatize_parser` (:119-120) and a new `args.command == "status"` arm in the dispatch chain (:127-135); the module docstring (:1-15) enumerates every subcommand by originating FEAT ID and needs a `status`/FEAT-3311 entry.
- `docs/reference/CLI.md:4566` — the existing not-yet-implemented note names `status` directly and must be updated/removed once this lands. Unrelated to this issue but visible on the same line: that note also misattributes `extract` to FEAT-3309 (a different, already-completed issue) rather than FEAT-3310.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/extract.py` (FEAT-3310, not yet created) — `cmd_refresh` is the other half of "render/refresh gain a lockfile-write step" per this issue's own Program Design. FEAT-3310 is entirely unimplemented today: no `extract.py`, no `cmd_extract`/`cmd_refresh`, no `refresh`/`extract` dispatch branch, and no consumption of the manifest's `source` key anywhere in `cli/artifact/` or `artifact_templates.py` (confirmed by direct grep and read). The render-side lockfile-write step can be added independently, since `render.py`/`cmd_render` already exists and is fully implemented; the refresh-side step has no target to attach to until FEAT-3310 lands.
- `scripts/little_loops/config/core.py` (`BRConfig.artifacts`, :476-478) and `scripts/little_loops/config/features.py` (`ArtifactsConfig`, :391-402) — `templates_dir` (default `artifacts/templates`) is how `status`'s "no `<template>` args" discovery mode must enumerate templates, the same source `cmd_render`/`cmd_templatize` already read.

### Conventions in Force
- Subcommand registration: an `add_<name>_parser(subparsers)` function inside the subcommand's own module, called from `main_artifact()` — evidence: `render.py:91`, `templatize.py:965`, wired at `__init__.py:119-120`.
- Handler signature: `cmd_<name>(args, logger) -> int` with narrow `except <DomainError>` arms above a trailing `except Exception as exc: return 1` backstop — evidence: `render.py:27-88`.
- Multi-item classification + exit-code decision: two coexisting, contested shapes elsewhere in the codebase — (a) `verify_private_refs.py`'s flat `list[Finding]` where `bool(findings)` alone decides the exit code (`:200-208`, `:625-634`), and (b) `doctor.py`'s per-item `CheckResult` dataclass with a `Literal[...]` status field plus a dedicated `_exit_code_for(results)` function (`:55-74`, `:125-128`). This issue's FRESH/STALE/SOURCE-MISSING vocabulary is structurally closer to shape (b) — a `Literal[...]` tri-state per item — but neither shape is mandated by the codebase.
- sha256 content-hash pattern: `_sha256_file(path) -> str | None` (`codequery/codegraph.py:124-130`) reads bytes, hashes, and returns `None` on `OSError` rather than raising — the nearest in-repo precedent for the source-hash comparison this issue needs, but it is module-private (not exported from `codequery`) and nothing outside that module imports it, so `status.py` cannot reuse it directly and would define its own copy of the same shape.
- YAML sidecar load pattern: `load_manifest` (`artifact_templates.py:142-189`) reads via `yaml.safe_load`, validates required/optional/allowed key sets (module-level frozensets at `:25-27`), and raises a module-specific `*Error(ValueError)` on any violation — the nearest read-shape precedent for a `.llat.lock` reader. `artifact_templates.py` has no YAML *writer* anywhere to mirror for the write side; this issue's `{version, renders: {<path>: {sha256, rendered_at, output}}}` shape is the first machine-written YAML sidecar in this subsystem — no shared writer utility exists to reuse.
- "No args = act on everything discoverable": no precedent scoped to `cli/artifact/` — both `render` and `templatize` require a positional template argument. The closest codebase-wide shape is `verify_private_refs.py`'s explicit `--all` flag (`scan_all`, `:365-372`), not an implicit empty-positional-list branch — this issue's AC calls for the latter (no `<template>` args → discover all).

### Tests
- `scripts/tests/test_codequery_codegraph.py` (~lines 375-435) — the issue's own cited precedent: temp git repo fixture + inline `hashlib.sha256(...)` computed independently of the module under test + a `.status()` call + assertion on a `freshness` classification field (`"fresh"`/`"stale"`). This precedent's vocabulary is only 2-way; it has no "source missing" analog to mirror for the 3rd state.
- `scripts/tests/test_artifact_templatize.py:394-401` (`TestCmdTemplatizeEndToEnd._run`) — the established in-process end-to-end CLI pattern (save/restore `sys.argv`, call `main_artifact()` directly, no subprocess) an AC-required end-to-end `status` test would follow.
- `scripts/tests/test_feat3036_artifact_templates.py:375` (`TestCmdRender`), `:458` (`TestArtifactCLIDispatchRender`) — alternative handler-level + dispatch-mock test style, also available as precedent (contested against the templatize style above).
- No `scripts/tests/test_feat3311_artifact_status.py` (or similarly named) test file exists yet.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decisions.py:185-208` (`TestSaveDecisions`: `test_writes_valid_yaml`, `test_round_trip_preserves_fields`) — closest existing "write YAML, read back, assert shape" round-trip pattern in the suite; use as the template for the lockfile write/read test, since `artifact_templates.py` has no prior YAML-writer precedent to mirror.
- `scripts/tests/test_artifact_templatize.py:750-813` (`TestCmdTemplatizeDiscoveryBranch._run` + `main_artifact()`) — precedent for asserting a non-zero exit code through the full CLI dispatch path; the model for `status`'s required non-zero-exit-on-stale end-to-end test.

### Configuration
- `scripts/little_loops/config-schema.json:1875-1895` — `artifacts.templates_dir` (default `artifacts/templates`), read via `BRConfig(Path.cwd())`; no lockfile-related config knob currently exists (e.g., no override for the lockfile's naming/location).

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore:47-49` — the only existing lock-file patterns (`**/.*.lock`, `**/.*.lock.lock`) are dotfile-prefixed globs scoped to "the hook system" (per the file's own comment) and do **not** match `<template-name>.llat.lock` (no leading dot). No `.gitignore` entry currently covers `artifacts/templates/**/*.llat.lock` — confirm intentionally whether the lockfile should be tracked (committed alongside the template) or ignored, and add an entry if the latter.

### Documentation
- `docs/reference/CLI.md:4509-4530` (`#### ll-artifact render`) — the prose → `**Flags:**` table → `**Examples:**` → `**Exit codes:**` shape a new `#### ll-artifact status` section must follow, per this issue's own AC.
- `docs/reference/CLI.md:4566` — the not-yet-implemented note naming `status` directly; must be updated/removed once this lands.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4459-4466` — the `### ll-artifact` `**Subcommands:**` table lists only `policy-builder`/`design-md export`/`render`/`templatize`; needs a new `status` row, distinct from the new `#### ll-artifact status` prose section already noted above.
- `docs/reference/CLI.md:4468` — the top-level Exit codes summary line frames `2` as a `templatize`-only carve-out ("see `templatize` below"); if `status`'s non-zero-on-stale exit reuses `1` this line is unaffected, but if any revision gives `status` a distinct non-1 exit code, this line's phrasing needs to cover both subcommands.
- `scripts/little_loops/cli/artifact/__init__.py:65-69` — `main_artifact()`'s own argparse epilog hard-codes an `Exit codes:` block (`0`/`1`/`2` bullets) as live `--help` text, separate from CLI.md prose and from the module docstring already noted above. Needs a new bullet for `status`'s exit behavior regardless of which exit code it uses.
- `scripts/little_loops/cli/artifact/render.py:27-32` — `cmd_render`'s own docstring states "Returns 0 on success, 1 on error" and enumerates specific error causes; needs a bullet added for a lockfile-write failure once that step is inserted (see Decision Rules below), since the trailing `except Exception` (`render.py:86-88`) will now catch lockfile-write errors too.

## Program Design

### Call Path

`cmd_status` (new `cli/artifact/status.py`) reads the `<template>.llat.lock`
sibling file(s) beside each resolved template (via
`little_loops.artifact_templates.resolve_template`, unchanged from
FEAT-3036), computes current sha256 of each recorded source path, and
compares. `render`/`refresh` (FEAT-3036/FEAT-3310) gain a lockfile-write step
after a successful render — the sha256/rendered_at/output triple keyed by
source path, per § Second-pass decisions -> *Lockfile is keyed by source
path, not a scalar*.

### Tests

New coverage follows `test_codequery_codegraph.py`'s structural template for
sha256 content-hash staleness detection (temp dir + a rendered lockfile
fixture, assert on `.status()`'s FRESH/STALE/SOURCE-MISSING classification
and exit code) — the closest in-repo precedent (FEAT-3036 § Tests).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Types

- The lockfile has no existing type in the codebase — this issue's own `version: 1 / renders: {<source-path>: {sha256, rendered_at, output}}` shape (issue body, § Expected Behavior) is the first place this shape appears; there is no dataclass or schema to reuse.
- `ArtifactTemplate` (`artifact_templates.py:48-64`) — existing dataclass (`root: Path`, `manifest: dict`), unchanged; `resolve_template`'s return value is used to derive the sibling lock path.
- Manifest optional key `source: str` (`artifact_templates.py:26`, `_MANIFEST_OPTIONAL_KEYS`) exists in the schema-allowed key set but is unread by `artifact_templates.py` — `status` does not need it, since the lockfile itself records source paths directly as `renders` mapping keys, independent of the manifest.

### Signatures

- `resolve_template(template_arg: str, templates_dir: Path) -> Path` (`artifact_templates.py:67`) — raises `TemplateResolutionError`; reused unchanged by `cmd_status` to resolve each `<template>` argument to its root directory, per this issue's own Call Path.
- `load_manifest(root: Path) -> dict[str, Any]` (`artifact_templates.py:142`) — raises `ManifestError`; the nearest read-shape precedent for a lockfile reader, but there is no equivalent writer in the module (see Integration Map → Conventions in Force).
- No sha256 helper is importable across modules: `_sha256_file(path: Path) -> str | None` (`codequery/codegraph.py:124-130`) is module-private and unexported — `status.py`'s current-hash computation is new code, not a reuse of an existing function.
- `render.py::cmd_render` (`render.py:27-88`) — the write point for the render-side lockfile-write step is immediately after `out_path.write_text(rendered, encoding="utf-8")` and before the trailing `logger.success(...)`/`return 0`.
- Lock path derivation: `resolve_template` returns a directory ending in `.llat` (e.g. `templates_dir / "foo.llat"`); "sibling file next to the template" (issue body, § Expected Behavior) resolves to `<that directory>.parent / f"{<that directory>.name}.lock"`, i.e. `foo.llat.lock` alongside `foo.llat/`, matching the issue's own example lockfile name.

### Decision Rules

- FRESH/STALE classification per `(template, source)` pair: FRESH iff the source path exists on disk and its current sha256 equals the `renders[source_path].sha256` recorded in the lockfile; STALE iff the source path exists but the current sha256 differs from the recorded one.
- SOURCE-MISSING: the issue's own Expected Behavior names this as a distinct third state (not folded into STALE) for a recorded source path that no longer exists on disk — this differs from `_sha256_file`'s precedent (`codequery/codegraph.py:124-130`), which returns `None` on a missing/unreadable file and lets the caller collapse that into "changed" (2-way). This issue's own tri-state vocabulary is not fully pinned by the codebase precedent it cites.
- Exit-code scope not fully specified by the issue text: § Expected Behavior states "Exits non-zero if anything is stale" and the Acceptance Criteria restate "exits non-zero iff anything is stale," but neither states whether a SOURCE-MISSING pair also triggers the non-zero exit, or whether only STALE does. This is a genuine gap in the issue's own text, not resolvable from the codebase — left open for the implementer/operator to pin down, per `doctor.py`'s precedent (`:125-128`) of a dedicated `_exit_code_for(results)` function making this decision explicit and testable in one place.

_Wiring pass added by `/ll:wire-issue`:_
- No existing test asserts exhaustive output-directory contents on `cmd_render` (`test_feat3036_artifact_templates.py`'s `TestCmdRender` checks only targeted `(out_dir / "report.html")` existence/content, never directory-listing counts) — the planned lockfile-write step will not break any existing assertion there. However, no existing `TestCmdRender` case exercises a read-only/unwritable `templates_dir`, so a lockfile-write failure turning a previously-0 render into a 1 is currently untested — add this case.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

1. `render.py::cmd_render` writes/updates a `<template>.llat.lock` sibling YAML file recording `{sha256, rendered_at, output}` for the rendered source path(s), added after its existing output-file write and before its success log/return — `test_feat3036_artifact_templates.py`'s existing `TestCmdRender`/`TestArtifactCLIDispatchRender` suites continue to pass unmodified alongside new lockfile-specific assertions.
2. `ll-artifact status` is wired into `main_artifact()` via a new `add_status_parser`/`cmd_status` in `cli/artifact/status.py`, following the `add_<name>_parser` + `cmd_<name>(args, logger) -> int` convention every other artifact subcommand uses (`render.py:91`, `render.py:27`, `templatize.py:965`).
3. `cmd_status` reads each resolved template's `<template>.llat.lock`, computes a current sha256 per recorded source path, and classifies each `(template, source)` pair as FRESH/STALE/SOURCE-MISSING per `## Program Design` → Decision Rules — including deciding the still-open question there of whether SOURCE-MISSING triggers the non-zero exit.
4. With no `<template>` positional args, `status` enumerates every template under `config.artifacts.templates_dir` that has a `.llat.lock` sibling — no in-repo precedent for this discovery shape exists (`render`/`templatize` both require a positional template), so this is new surface rather than an extension of an existing pattern.
5. `docs/reference/CLI.md` gains a `#### ll-artifact status` section (flags/examples/exit codes, following the `render`/`templatize` section shape) and its existing not-yet-implemented note at line 4566 no longer names `status`.
6. `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:4459-4466` — add a `status` row to the `**Subcommands:**` table.
- Update `scripts/little_loops/cli/artifact/__init__.py:65-69` — add a `status` bullet to the `main_artifact()` argparse epilog `Exit codes:` block.
- Update `scripts/little_loops/cli/artifact/render.py:27-32` — add a lockfile-write-failure bullet to `cmd_render`'s docstring.
- Add a `TestCmdRender` case exercising a read-only/unwritable `templates_dir` to confirm the lockfile-write failure path exits 1.
- Decide and record whether `<template>.llat.lock` should be gitignored or committed; update `.gitignore` if the former (see Configuration above).
- Coordinate `docs/reference/CLI.md:4566` edit with FEAT-3310, which independently edits the same line.

## Impact

- **Priority**: P3 — serves EPIC-3299's secondary use case (one template,
  one bound source refreshed over time); this is where the stated
  content-drift problem is actually killed.
- **Effort**: Medium
- **Risk**: Low — additive; no changes to Phase 1's render path or Phase 2's
  extract path.

## Acceptance Criteria

- [ ] `render` (and Phase 2's `refresh`) write/update a
      `<template-name>.llat.lock` sibling file recording sha256 + rendered_at
      + output per rendered source path.
- [ ] `ll-artifact status [<template> ...]` reports FRESH/STALE/SOURCE-MISSING
      per `(template, source)` pair and exits non-zero iff anything is stale.
- [ ] With no `<template>` args, `status` reports on every template
      discovered under `config.artifacts.templates_dir` that has a lockfile.
- [ ] A pytest test invokes `ll-artifact status` end-to-end (subprocess or
      direct `cmd_status` call) and asserts the non-zero exit on a stale
      source — this is the "CI gate" per CLAUDE.md's local-suite policy, not
      a hosted workflow.
- [ ] `docs/reference/CLI.md` documents `status` and the lockfile format.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-25T03:17:17 - `5da7f41e-bb5f-4d4a-b24d-114a6e916228.jsonl`
- `/ll:refine-issue` - 2026-08-25T03:09:16 - `f224d8be-3c42-4b3a-8a3e-ebc438693eb8.jsonl`
