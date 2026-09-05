---
id: FEAT-3385
type: FEAT
title: Add project-type templates for Ruby, PHP, C/C++ (CMake), Swift, Deno, and monorepo
  detection
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T20:06:43Z'
deferred_by: human
deferred_date: '2026-09-04T20:08:16Z'
relates_to:
- FEAT-3388
---

# FEAT-3385: Add project-type templates for Ruby, PHP, C/C++ (CMake), Swift, Deno, and monorepo detection

## Summary

Add six new `ll-init` project-type templates — `ruby.json`, `php.json`,
`cmake.json`, `swift.json`, `deno.json`, and `monorepo.json` — to
`scripts/little_loops/templates/`, so these ecosystems get real
`test_cmd`/`lint_cmd`/`format_cmd`/`scan.focus_dirs` defaults instead of
silently falling back to `generic.json`.

## Current Behavior

`scripts/little_loops/templates/` ships nine project-type templates:
`generic.json`, `python-generic.json`, `javascript.json`, `typescript.json`,
`rust.json`, `go.json`, `java-maven.json`, `java-gradle.json`, `dotnet.json`.
`ll-init`'s detection (`scripts/little_loops/init/detect.py:detect_project_type_all`)
globs each template's `_meta.detect` patterns against the project root and picks
the strongest match, falling back to `generic.json` (priority `-1`) when nothing
hits. A Ruby, PHP, C/C++ (CMake), Swift, or Deno project — or a JS/TS monorepo
using pnpm/lerna/nx/turbo workspaces — always falls through to the generic
template: no `test_cmd`/`lint_cmd`/`format_cmd` defaults, no `scan.focus_dirs`,
no `test_patterns`, and (for a monorepo) no signal that multiple sub-projects
with different toolchains coexist under one root.

## Expected Behavior

`ll-init` detects these project types with the same fidelity as the existing
nine and proposes correct tooling defaults:

- **Ruby** — `Gemfile` → `bundle exec rspec` / `rubocop`
- **PHP** — `composer.json` → `composer test` (or `phpunit`) / `phpcs` or `php-cs-fixer`
- **C/C++ (CMake)** — `CMakeLists.txt` → `ctest --test-dir build` / build via `cmake --build build`
- **Swift** — `Package.swift` → `swift test` / `swift build`
- **Deno** — `deno.json`/`deno.jsonc` → `deno test` / `deno lint` / `deno fmt`
- **Monorepo** — `pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, or
  `rush.json` at root → a composite template that surfaces the workspace tool
  instead of guessing a single language, and wins over `javascript.json`/
  `typescript.json` when both a workspace manifest and a root `package.json`
  are present.

## Motivation

Every unsupported project type silently degrades to `generic.json`, which has
no scan focus dirs and no test/lint/format commands — `/ll:check-code`,
`scan-codebase`'s `focus_dirs`, and `ll-init`'s proposed config all go blank
for these ecosystems even though the detection mechanism (JSON + glob) is
already fully data-driven and requires zero code changes to extend. This is
the single largest population of unsupported ecosystems reachable with the
existing plumbing.

## Proposed Solution

Detection is purely additive and data-driven — no changes to
`detect.py`/`init/core.py` are needed for the five single-language templates.
Model each new file on `scripts/little_loops/templates/rust.json` (or
`go.json`), e.g. for Ruby:

```json
{
  "$schema": "config-schema.json",
  "_meta": {
    "name": "Ruby",
    "description": "Ruby project with Bundler",
    "detect": ["Gemfile"],
    "tags": ["ruby", "bundler"],
    "command_options": {
      "test_cmd": ["bundle exec rspec", "bundle exec rake test"],
      "lint_cmd": ["bundle exec rubocop"],
      "format_cmd": ["bundle exec rubocop -a"]
    }
  },
  "project": {
    "src_dir": "lib/",
    "test_cmd": "bundle exec rspec",
    "lint_cmd": "bundle exec rubocop",
    "type_cmd": null,
    "format_cmd": "bundle exec rubocop -a",
    "build_cmd": null,
    "run_cmd": "bundle exec ruby",
    "test_patterns": ["spec/**/*_spec.rb"]
  },
  "scan": { "focus_dirs": ["lib/", "app/"], "exclude_patterns": ["**/vendor/**"] },
  "issues": { "...": "copy verbatim from rust.json" },
  "parallel": { "use_feature_branches": false, "epic_branches": { "enabled": false } }
}
```

`monorepo.json` is the one template needing a design decision: its
`_meta.detect` list should name only workspace-manifest files
(`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, `rush.json`),
never `package.json`, so it never fires for a plain single-package JS repo;
give it `_meta.priority` above `javascript.json`/`typescript.json` (both
currently unset, i.e. `0`) so the `(-match_count, -priority, filename)` sort
in `detect_project_type_all` picks it when both a workspace manifest and a
root `package.json` are present. Its `project.test_cmd`/`lint_cmd` should
point at the workspace runner (`pnpm -r test`, `turbo run test`, etc. — pick
one generic default and document that per-package overrides belong in each
sub-package, not root `.ll/ll-config.json`).

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/ruby.json` (new)
- `scripts/little_loops/templates/php.json` (new)
- `scripts/little_loops/templates/cmake.json` (new)
- `scripts/little_loops/templates/swift.json` (new)
- `scripts/little_loops/templates/deno.json` (new)
- `scripts/little_loops/templates/monorepo.json` (new)
- `scripts/little_loops/package_data.py` — add six `("templates", "<name>.json")` entries to `_PACKAGE_DATA` near the existing template entries (package_data.py:39-47)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/detect.py` — `_load_templates`/`detect_project_type_all` glob `templates/*.json` automatically; no change needed, but the monorepo-priority behavior lives in this file's sort key
- `scripts/little_loops/init/core.py` and `skills/init/SKILL.md` — consume `detect_project_type_all`'s result to build `proposed_config`; no change needed since they're template-agnostic

### Similar Patterns
- `rust.json`, `go.json`, `java-maven.json`, `dotnet.json` are the templates to mirror structurally

### Tests
- `scripts/tests/test_init_core.py::TestDetectProjectType` — add per-template detection cases
- `scripts/tests/test_init_core.py::test_real_template_detection` (parametrized, lines 504-515) — extend the parametrization table
- `scripts/tests/test_wheel_smoke.py::test_package_data_manifest_all_accessible` — will exercise the new `_PACKAGE_DATA` entries once added

### Documentation
- N/A (templates are self-describing via `_meta.description`; no prose doc currently enumerates the template list)

### Configuration
- N/A

## Program Design

### Types

No new types — templates conform to the existing untyped JSON schema shared by
`rust.json`/`go.json`/etc. (`_meta`, `project`, `scan`, `issues`, `parallel` keys).

### Signatures

- `detect_project_type_all(root: Path, templates_dir: Path | None = None) -> list[TemplateMatch]` — unchanged; the six new JSON files are picked up automatically by its `templates_dir.glob("*.json")` scan.

### Call Path

`ll-init` (`scripts/little_loops/init/cli.py`) -> `detect_project_type_all` (`scripts/little_loops/init/detect.py:144`) -> `_load_templates` glob-loads the six new JSON files alongside the existing nine, no code change required.

## Implementation Steps

1. Write `ruby.json`, `php.json`, `cmake.json`, `swift.json`, `deno.json` — single-manifest detect, mirroring `rust.json`'s shape.
2. Write `monorepo.json` with workspace-manifest detect patterns and a priority high enough to beat `javascript.json`/`typescript.json` on dual-manifest repos; verify it does NOT match plain single-package JS/TS repos.
3. Register all six filenames in `package_data.py`'s `_PACKAGE_DATA`.
4. Add/extend detection unit tests in `test_init_core.py` (per-template + monorepo-precedence cases).
5. Run `python -m pytest scripts/tests/` and confirm `test_wheel_smoke.py::test_package_data_manifest_all_accessible` still passes.

## Impact

- **Priority**: P3 - Pure addition, no bug/regression risk, but not blocking any in-flight work; broadens tooling coverage for ecosystems not currently used in this repo's own dogfooding.
- **Effort**: Medium - Five templates are copy-paste-adapt from existing patterns (Small each); the monorepo template's priority/detect_exclude design and its precedence test are the only non-trivial part.
- **Risk**: Low - Purely additive JSON files plus one `_PACKAGE_DATA` list append; the monorepo priority interaction is the only piece that could regress existing JS/TS detection if under-tested, which is why it's called out explicitly in Acceptance Criteria and Implementation Steps.
- **Breaking Change**: No

## Use Case

A user runs `/ll:init` in a fresh Deno API project (`deno.json` at root, no
`package.json`). Today `ll-init` reports "Detected project type: Generic" and
proposes `test_cmd: null`. With this feature, it reports
`Detected: Deno — 1/1 indicators` and proposes `deno test`, `deno lint`,
`deno fmt --check` — the same experience Python/Go/Rust users already get.
A second user runs `/ll:init` in a pnpm-workspace monorepo with a root
`package.json` and `pnpm-workspace.yaml`; today it matches `javascript.json`
(1/2 indicators) and treats the whole repo as one flat JS project. With this
feature it matches `monorepo.json` instead and the proposed config flags that
per-package tooling should be configured per-subdirectory rather than at root.

## Acceptance Criteria

- [ ] New template files exist: `ruby.json`, `php.json`, `cmake.json`,
      `swift.json`, `deno.json`, `monorepo.json` — each with `_meta.name`,
      `_meta.description`, `_meta.detect`, `_meta.tags`, and populated
      `project.{test_cmd,lint_cmd,format_cmd,build_cmd,run_cmd,test_patterns}`,
      `scan.{focus_dirs,exclude_patterns}`, matching the shape of `rust.json`/`go.json`.
- [ ] Each new template's filename is added to `_PACKAGE_DATA` in
      `scripts/little_loops/package_data.py` (alongside the existing
      `("templates", "rust.json")`-style entries) so it ships in the wheel.
- [ ] `deno.json`'s filename does not collide with a real Deno project's own
      `deno.json` config file at detection time — `detect_project_type_all`
      only reads templates from `templates_dir`, never from the scanned
      project root, so this is a naming/documentation concern only, not a
      functional collision; confirm with a test that detection still works
      when the scanned project root itself contains a `deno.json`.
- [ ] `monorepo.json` uses `_meta.priority` high enough that, when a root
      `pnpm-workspace.yaml`/`lerna.json`/`nx.json`/`turbo.json`/`rush.json`
      coexists with `package.json`, it outranks `javascript.json`/
      `typescript.json` in `detect_project_type_all`'s
      `(-match_count, -priority, filename)` sort — add a `detect_exclude`
      or rely on `_meta.detect` matching only workspace-manifest filenames
      (never `package.json` itself) so plain single-package JS repos are
      unaffected.
  - `scripts/little_loops/init/detect.py:detect_project_type_all` sorts by `(-match_count, -meta.get("priority", 0), filename)`; verify the intended template wins for every dual-manifest case with a unit test in `TestDetectProjectType` (mirrors the `(["go.mod"], "go.json")` parametrization).
- [ ] `scripts/tests/test_init_core.py::TestDetectProjectType` and the
      `test_real_template_detection` parametrization (test_init_core.py:504-515)
      gain one case per new template (bare-manifest detection) plus the
      monorepo-vs-javascript precedence case above.
- [ ] `python -m pytest scripts/tests/` passes, including
      `test_wheel_smoke.py::test_package_data_manifest_all_accessible`.

## Status

**Open** | Created: 2026-09-04 | Priority: P3
