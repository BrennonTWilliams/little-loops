---
id: FEAT-3388
type: FEAT
title: 'll-init: add project-type templates for Ruby, PHP, C/C++ (CMake), Swift, Deno,
  and monorepo/workspace layouts'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T21:03:39Z'
relates_to:
- FEAT-3385
---

# FEAT-3388: ll-init: add project-type templates for Ruby, PHP, C/C++ (CMake), Swift, Deno, and monorepo/workspace layouts

## Summary

The 2026-09 ll-init audit extended manifest introspection (task runners, tool config files, Go/Rust/Java/.NET conventions) but deferred new project-type templates. Add `scripts/little_loops/templates/*.json` entries (with `_meta.detect`, `detect_exclude`, `command_options`, `scan` focus/excludes, `test_patterns`) for Ruby (Gemfile), PHP (composer.json), C/C++ (CMakeLists.txt / meson.build), Swift (Package.swift), Deno (deno.json), and workspace roots (pnpm-workspace.yaml, turbo.json, nx.json, Cargo workspaces, go.work), plus matching `_ecosystem_command` rules in `init/introspect.py` and detection tests in `scripts/tests/test_init_core.py::TestDetectProjectType`.


## Current Behavior

`scripts/little_loops/templates/` only ships `_meta.detect`-driven templates for Go, Rust, the two Java build tools, .NET, JavaScript/TypeScript, Python, and a generic fallback (see `scripts/little_loops/templates/go.json` for the shape). `init/introspect.py`'s `_ecosystem_command` only recognizes `go.mod`, `Cargo.toml`, and the other covered ecosystems. Ruby, PHP, C/C++, Swift, Deno, and monorepo/workspace-root projects all fall through to `generic.json`, so `ll-init` proposes no ecosystem-appropriate `test_cmd`/`lint_cmd`/`format_cmd` or `scan.focus_dirs`/`exclude_patterns` for them.

## Expected Behavior

`ll-init` detects a Ruby (`Gemfile`), PHP (`composer.json`), C/C++ (`CMakeLists.txt` or `meson.build`), Swift (`Package.swift`), Deno (`deno.json`), or workspace-root (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`, a Cargo workspace, or `go.work`) project the same way it already detects Go via `go.mod`, and proposes that ecosystem's conventional commands and scan focus/excludes instead of falling back to `generic.json`.

## Use Case

**Who**: A developer running `ll-init` for the first time on a Ruby, PHP, C/C++, Swift, or Deno project, or on a monorepo root.

**Context**: `ll-init`'s detection wizard walks the project root looking for a matching `_meta.detect` marker file to pick a project-type template.

**Goal**: Get an `.ll/ll-config.json` pre-populated with the right `test_cmd`/`lint_cmd`/`format_cmd` and `scan` focus/exclude directories for their ecosystem, without hand-editing the generated config afterward.

**Outcome**: `ll-init` reports the detected project type (e.g. "Ruby (Gemfile)") and writes config values that match the ecosystem's real tooling, the same experience Go/Rust/Java/.NET projects already get.

## Acceptance Criteria

- [ ] `scripts/little_loops/templates/ruby.json` (new), `php.json` (new), `cpp.json` (new), `swift.json` (new), `deno.json` (new), and `workspace.json` (new) exist, each with `_meta.detect` (and `detect_exclude` where a false-positive marker could collide, e.g. a Ruby `Gemfile` inside a mixed-language monorepo), `_meta.command_options`, `project.test_cmd`/`lint_cmd`/`format_cmd`, `scan.focus_dirs`/`exclude_patterns`, and `project.test_patterns`
- [ ] `init/introspect.py::_ecosystem_command` gains ecosystem-convention branches for Ruby (`bundle exec rspec`/`rubocop`), PHP (`composer test`/`phpcs` or `phpstan`), C/C++ (`ctest`/`clang-format`), Swift (`swift test`), and Deno (`deno test`/`deno lint`/`deno fmt`), mirroring the existing `go.mod`/`Cargo.toml` branches
- [ ] Workspace-root detection (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`, a Cargo `[workspace]` table, `go.work`) resolves to the `workspace.json` template rather than `generic.json` or a single-package ecosystem template
- [ ] `scripts/tests/test_init_core.py::TestDetectProjectType` gains one detection test per new template (positive match) and at least one negative/exclusion test for a marker collision
- [ ] `python -m pytest scripts/tests/` passes

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

Findings below cover the existing template schema, detection/collision mechanisms, package-data registration, test conventions, and a near-duplicate sibling issue relevant to the six new templates.

### Files to Modify

- `scripts/little_loops/templates/{ruby,php,cpp,swift,deno,workspace}.json` (all new) — follow `scripts/little_loops/templates/go.json`'s exact schema: `$schema`, `_meta` (`name`, `description`, `detect`, `tags`, `command_options`), `project` (`src_dir`, `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`, `build_cmd`, `run_cmd`, `test_patterns`), `scan` (`focus_dirs`, `exclude_patterns`), byte-identical `issues`/`parallel` blocks
- `scripts/little_loops/init/introspect.py` — `_ecosystem_command` (line 484) gains one branch per new ecosystem, following the existing `go.mod`/`Cargo.toml` branch shape (guard on marker existence → build an `evidence` string → per-`field_name` lookup via `_choose(default_value, candidates, must_contain, fallback)`, `introspect.py:327-336`, or `_any_glob` for multi-candidate markers like `.sln`/`.csproj`, `introspect.py:339-344`)
- `scripts/little_loops/package_data.py:39-47` — every shipped template filename has a corresponding `("templates", "<name>.json")` tuple in `_PACKAGE_DATA` so it ships in the wheel; the six new template files need entries added here or `test_wheel_smoke.py::test_package_data_manifest_all_accessible` will fail

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_test_file_patterns.py` — module-level `TYPED_TEMPLATES` list (~lines 23-33) AND the `shared_fixture_markers` dict inside `TestTemplateDefaults.test_template_defaults_include_shared_fixture_equivalent()` must **both** gain entries for the six new template stems, or the parametrized test raises `KeyError` at collection time (fails loudly, not silently) [Agent 2 finding]
- `scripts/tests/test_init_core.py::TestTemplateCommandOptions.TYPED_TEMPLATES` (~line 4278, currently 8 filenames) — gains the six new template filenames so `_meta.command_options`/`test_cmd`/`test_patterns` checks cover them [Agent 1 + Agent 2 finding]
- `scripts/tests/test_init_core.py::TestProjectTypeTemplatesEpicBranchesStamp.project_templates` (~line 4392, currently 9 filenames) — gains the six new template filenames so the ARCHITECTURE-096 `parallel.epic_branches.enabled: false` stamp is checked on them too; silently under-covered (not failing) if skipped [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/init/detect.py::_load_templates` — glob-loads every `templates/*.json`, skipping `_SECTION_TEMPLATES` and any file whose `_meta` lacks `detect`; a new template is picked up automatically with no code change to `detect.py` itself
- `scripts/little_loops/init/detect.py::detect_project_type_all` (docstring 147-157, impl 196-234) — the only existing marker-collision resolution mechanism: scores each candidate by `_meta.detect` glob match count, vetoes any candidate whose `_meta.detect_exclude` glob is present, sorts by `(-match_count, -meta.priority, filename)`. This is the mechanism workspace-root detection must win through (higher `_meta.priority` or a `detect_exclude` veto on single-package templates), not a new precedence mechanism of its own
- `scripts/little_loops/init/introspect.py::_ecosystem_command` — has its OWN, different collision-resolution: a fixed sequential if/elif chain (go.mod → Cargo.toml → pom.xml → build.gradle → .sln/.csproj), first match wins, no scoring/priority/exclude of its own — this file only reacts to whichever template `detect.py` already picked upstream via the `TemplateMatch` passed into `introspect()`

### Conventions in Force

- Every real (non-generic, non-section) template shares one schema exactly — confirmed against `go.json`, `rust.json`, `java-gradle.json`, `java-maven.json`, `dotnet.json` — with two allowed variations: `_meta.detect` may list multiple candidate marker filenames (not just one), and `project.format_cmd`/`type_cmd`/`build_cmd`/`run_cmd` are frequently `null` when the ecosystem has no strong convention for that field.
- `_meta.detect_exclude` exists in the schema but only one template (`javascript.json`, excluding `tsconfig.json`) actually uses it today — it is the sole existing precedent for resolving a marker collision via template metadata rather than code.
- `_meta.priority` exists in the schema but only `generic.json` sets it (`-1`, marking it the fallback) — no other template sets it, so a `workspace.json` template needing to outrank single-package templates would be introducing the second-ever use of this field.
- `TestDetectProjectType` positive-match tests follow one shape: touch marker file(s) in a `tmp_project`/`fake_templates` (or real `templates_dir`) fixture, call `detect_project_type`, assert `match.filename`; the real-template parity suite is a single `@pytest.mark.parametrize` function (`test_real_template_detection`, `test_init_core.py:519-549`) with one row per shipped template plus a `[]` fallback row and a "3 matches beat 1, not alphabetical" row — six new parametrize rows plus a negative/exclusion row is the shape to extend, not six new standalone test methods.
- `TestEcosystemDetection` (`test_init_introspect.py:431`) is the model for the new `_ecosystem_command` branch tests: `_template_for(tmp_path, "go.mod", templates_dir)` fixture helper plus an assertion on the derived `lint_cmd`/`test_cmd` string.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| FEAT-3385 (deferred, P3) | Proposes the same six templates under different filenames: `cmake.json`/`monorepo.json` (FEAT-3385) vs. `cpp.json`/`workspace.json` (FEAT-3388) | See note | FEAT-3385 is `status: deferred`, `deferred_by: human` (2026-09-04T20:08:16Z) — a human decision, not automation. This is very likely scope duplication rather than two independent features; flagged via `relates_to` link rather than resolved here (a cancel/supersede call is an operator decision, not refine's). See Acceptance Criteria for the naming discrepancy this creates.

### Tests

- `scripts/tests/test_init_core.py::TestDetectProjectType` (line 367) and the parametrized `test_real_template_detection` (line 519) — extend both: unit-level positive/negative tests in the class, plus one parametrize row per new template in the parity suite
- `scripts/tests/test_init_introspect.py::TestEcosystemDetection` (line 431) — extend with one test per new `_ecosystem_command` branch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py::test_real_template_detection` (parametrize rows, lines 519-549) — add one `(["<indicator>"], "<filename>.json")` row per new template following the existing tuple shape; note `dotnet.json` is missing from this parametrize list today too (pre-existing gap, not introduced by this issue) [Agent 3 finding]
- `scripts/tests/test_init_introspect.py::TestEcosystemDetection` (model: `test_go_conventions`, line 432) — add one `test_<ecosystem>_conventions` method per new `_ecosystem_command` branch using the `_template_for(tmp_path, marker, templates_dir)` helper (line 287) [Agent 3 finding]
- `scripts/tests/test_init_core.py::test_js_excluded_by_tsconfig` (line 381-386, the only existing `detect_exclude` test) and its paired `test_js_matched_without_tsconfig` (line 388-391) — model the new Ruby-Gemfile-in-monorepo exclusion test as this same matched pair (excluded case + matched-without-exclusion case) [Agent 3 finding]
- `scripts/tests/test_init_core.py::test_priority_tiebreak_when_match_count_equal` (line 458-472) — the only existing `_meta.priority` tiebreak test, and it operates on a synthetic `fake_templates` fixture, not real templates; `workspace.json` will be the second-ever real-template user of `_meta.priority` (after `generic.json`'s `-1`), so a real-template tiebreak test (workspace vs. a single-package template) has no existing precedent to extend [Agent 3 finding]

### Documentation

- `docs/guides/GETTING_STARTED.md:367` — "falls back to the generic template" troubleshooting row would need updating once these ecosystems are covered
- `docs/reference/CONFIGURATION.md:309,321` — references "the per-project-type template default" for `test_patterns`, applies unchanged to the six new templates

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` ("Set Up Your Project" section, distinct from the line 367 troubleshooting row) — a second enumeration sentence ("Detected project types: Python, JavaScript/TypeScript, Go, Rust, Java (Maven or Gradle), and .NET...") lists both supported types and ecosystem-convention marker files; needs the six new ecosystems added [Agent 2 finding]
- `docs/ARCHITECTURE.md` (package-layout tree, "Package data: project-type configs and section templates") — enumerates every template filename; needs the six new filenames added [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add entries to `scripts/tests/test_test_file_patterns.py`'s `TYPED_TEMPLATES` list AND its `shared_fixture_markers` dict together — a mismatch between the two raises `KeyError` at collection time
- Add the six new template filenames to `TestTemplateCommandOptions.TYPED_TEMPLATES` and `TestProjectTypeTemplatesEpicBranchesStamp.project_templates` in `scripts/tests/test_init_core.py`
- Add six parametrize rows to `test_real_template_detection` and six `test_<ecosystem>_conventions` methods to `TestEcosystemDetection`
- Add a workspace-vs-single-package `_meta.priority` tiebreak test against real templates (no existing precedent — the only current tiebreak test uses a synthetic fixture)
- Update `docs/guides/GETTING_STARTED.md`'s "Set Up Your Project" enumeration and `docs/ARCHITECTURE.md`'s template-filename tree to include the six new ecosystems

## Program Design

### Types

- `_meta.detect: list[str]` / `_meta.detect_exclude: list[str]` (template JSON fields, existing shape per `scripts/little_loops/templates/go.json`)

### Signatures

- `_ecosystem_command(field_name: str, root: Path, default_value: str, candidates: list[str] | None) -> IntrospectedValue | None` (`scripts/little_loops/init/introspect.py:484`) — gains branches keyed on `Gemfile`, `composer.json`, `CMakeLists.txt`/`meson.build`, `Package.swift`, `deno.json`
- new template files: `scripts/little_loops/templates/{ruby,php,cpp,swift,deno,workspace}.json`, same schema as `scripts/little_loops/templates/go.json`

### Call Path

`init/core.py` project-type detection -> matches a new template's `_meta.detect` -> `_ecosystem_command` -> proposed `test_cmd`/`lint_cmd`/`format_cmd`/`build_cmd`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

`init/detect.py::detect_project_type_all`'s scoring/veto/tiebreak algorithm (glob match count → `_meta.priority` → filename) is the general-purpose collision resolver; `_ecosystem_command` (`introspect.py:484-581`) has its own, separate, hard-coded sequential-first-match resolver with no scoring of its own — a workspace-root template needs to win via the FIRST mechanism (a `_meta.priority` higher than single-package templates' implicit `0`, or a `detect_exclude` veto on those templates), not via anything in `_ecosystem_command`. This is the only existing marker-collision precedent in the codebase (`javascript.json`'s `tsconfig.json` exclude is the sole other real-world use of `detect_exclude`; no template besides `generic.json` sets `_meta.priority` today), so the workspace-vs-single-package precedence design is new ground, not an established pattern to copy.

## Impact

- **Priority**: P4 - broadens `ll-init` ecosystem coverage but every unsupported project type already works via `generic.json`; no broken behavior today
- **Effort**: Medium - six new template JSON files plus matching `_ecosystem_command` branches and a detection test per type; each template is small but there are six of them, and workspace-root detection needs collision handling against single-package templates
- **Risk**: Low - purely additive templates/detection branches; existing ecosystems' detection and templates are untouched
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-04 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-05T04:57:35 - `7ad2c895-8f68-4859-96fb-41e7c667e5b1.jsonl`
- `/ll:refine-issue` - 2026-09-05T04:32:54 - `251307a7-40ea-42f4-beb3-43e6b4de6744.jsonl`
- `/ll:format-issue` - 2026-09-05T04:22:41 - `adb409c3-bb29-46e0-a080-e89ad1cec8e0.jsonl`
