---
id: FEAT-2703
title: 'init/introspect.py: manifest-declared commands + src_dir detection with provenance'
type: FEAT
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
labels:
- init
- cli
- detection
- provenance
---

# FEAT-2703: `init/introspect.py` — manifest-declared commands + `src_dir` detection with provenance

## Summary

Add a deterministic introspection module that derives `project.src_dir`,
`project.{test,lint,format,type}_cmd`, and `scan.focus_dirs` from what the
repo *declares* — manifest tool tables, script entries, and package-layout
markers — instead of taking template literals on faith. Every derived value
carries a provenance tag (`declared` / `inferred` / `default`) so downstream
consumers (ENH-2704's plan output, the `--yes` summary, FEAT-2705's skill)
can distinguish verified facts from guesses.

Design principle: **read declarations, don't guess.** Introspection asserts a
value only when the repo unambiguously declares it; anything else stays a
template default, explicitly tagged as unverified.

## Current Behavior

`build_config()` (init/core.py:77-200) copies `project` and `scan` straight
from the template. `_run_yes` (init/cli.py:362-394) overrides only from an
existing `ll-config.json`. Fresh init on this very repo would write
`src_dir: src/`, `test_cmd: pytest` — both wrong (actual: `scripts/`,
`python -m pytest scripts/tests/`). Nothing ever opens `pyproject.toml`,
`package.json`, `Makefile`, or `tox.ini`.

## Expected Behavior

Fresh `ll-init --yes` on a repo with declared tooling writes correct values
and reports how it knows:

```
Detected project type: Python (Generic)
  src_dir: scripts/          (inferred: sole package marker scripts/little_loops/__init__.py)
  test_cmd: pytest           (declared: [tool.pytest.ini_options] present)
  lint_cmd: ruff check .     (declared: [tool.ruff] present)
  type_cmd: mypy             (default: template — no [tool.mypy] found)
```

Existing-config values still win on re-init (pre-population at
cli.py:362-394 unchanged); introspection fills only fresh-init gaps.

## Proposed Solution

New `scripts/little_loops/init/introspect.py`:

- `IntrospectedValue = (value, provenance, evidence_str)` dataclass;
  `introspect(root, template) -> dict[dotted_key, IntrospectedValue]`.
- **Commands, Python**: parse `pyproject.toml` (stdlib `tomllib`) —
  `[tool.pytest.ini_options]` / `[tool.ruff]` / `[tool.mypy]` /
  `[tool.black]` / `[tool.flake8]` presence confirms or overrides the
  template command; also check `tox.ini`, `Makefile` targets
  (`test:`/`lint:`/`format:`/`typecheck:`), `justfile`. Candidate pool seeded
  from the template's existing `_meta.command_options` lists
  (templates/python-generic.json) — introspection picks among candidates with
  evidence instead of taking `[0]`.
- **Commands, TS/JS**: `package.json` `scripts.test/lint/format/typecheck`
  are direct declarations → `npm run <name>` (or detected package manager via
  lockfile: pnpm-lock.yaml / yarn.lock / bun.lockb).
- **src_dir**: candidates from (a) `src/*/__init__.py` → `src/`,
  (b) exactly one top-level `*/__init__.py` package dir, (c) pyproject
  `[tool.setuptools.packages.find]` / `[tool.hatch.build]`,
  (d) `tsconfig.json` `rootDir`/`include`, (e) `Cargo.toml` (rust: `src/`
  is conventional). Adopt only on **exactly one candidate**; multiple
  candidates → keep template default, return the candidate list as an
  ambiguity (consumed by ENH-2704).
- **scan.focus_dirs**: union of adopted src_dir + detected test dirs
  (`tests/`, `test/`, pytest `testpaths`).
- Wire into `_run_yes`/`_run_plan` as `choices` overrides ahead of
  `build_config`, after existing-config pre-population (existing config
  always wins). Print the provenance summary in `--yes` output.
- Python + TS/JS parsers first; other ecosystems (go/rust/java/dotnet) can
  land as follow-ups using the same `IntrospectedValue` contract.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `build_config()` (`scripts/little_loops/init/core.py:77-200`) uses one
  per-field override idiom throughout: `if choices.get("src_dir"):
  project["src_dir"] = choices["src_dir"]`. New introspected values for
  `test_cmd`/`lint_cmd`/`format_cmd`/`type_cmd`/`scan.focus_dirs` should
  follow this exact per-field pattern rather than introducing a new
  mechanism.
- `_run_yes()` only pre-populates `choices["project_name"]` /
  `choices["src_dir"]` from an existing `.ll/ll-config.json`
  (`cli.py:362-395`); no other project/scan field currently flows through
  `choices` at all. `_run_plan()` (`cli.py:455-488`) has no existing-config
  pre-population step. Both call `build_config(template, choices)` as their
  single wiring point — introspection must run between
  `detect_project_type()` and this call in both functions.
- A second override point exists after `build_config()`:
  `merge_with_existing()` (`writers.py:123-146`) uses
  `deep_merge(existing_config, strip_none_leaves(new_config))` — the *new*
  config wins over the old for any key present in both. Introspected values,
  once in `config`, would beat old on-disk config at this step, so the
  "existing-config values still win" requirement must be satisfied at the
  earlier `choices` pre-population step (as `src_dir` already is today), not
  assumed from this merge.
- `_run_apply()` (`cli.py:491-571`) never calls `build_config`/introspection
  — it replays a previously emitted `--plan` JSON's `proposed_config`. Any
  provenance surfaced by introspection must be baked into `_run_plan`'s JSON
  output for `apply` to see it later.
- `templates/python-generic.json` already declares `_meta.command_options`
  exactly as specified (`test_cmd: ["pytest", "pytest -v", "python -m
  pytest"]`, similarly for `lint_cmd`/`format_cmd`) — confirmed this is
  currently inert data, unread by any code in `core.py`/`cli.py`/`tui.py`.
- No `IntrospectedValue`-style dataclass exists yet. Closest precedents to
  model after: `host_runner.py` `CapabilityEntry`/`HookEntry`
  (`frozen=True`, `Literal[...]` status tag, trailing `note: str = ""`) and
  `init/validate.py` `DepWarning` (flat `message` + optional `install_hint`,
  already the shape `_run_plan` serializes into the `warnings` JSON list at
  `cli.py:485`).
- The only existing `tomllib` usage in the codebase is
  `host_runner.py:_inject_agent_persona` (lines 473-488):
  `tomllib.loads(path.read_text())` wrapped in `except (OSError,
  tomllib.TOMLDecodeError)` — no `pyproject.toml`-specific reader exists yet
  to extend.
- Existing filesystem-probing precedent (`detect.py:_glob_match()`,
  `detect_documents()`) is existence-only glob matching, never manifest-content
  parsing — `[tool.pytest.ini_options]` table-presence detection and
  `__init__.py`-based `src_dir` candidate scanning are both net-new logic for
  this issue.
- `test_init_core.py:test_real_template_detection` (lines 380-406) currently
  builds fixtures with `.touch()`-only indicator files, which is insufficient
  for FEAT-2703's content-sensitive detection (e.g. `[tool.pytest.ini_options]`
  presence) — new tests should follow the `fake_templates` fixture's
  `json.dumps({...})` real-content pattern (lines 68-90) instead.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/core.py` — `build_config()` (lines 77-200)
  needs new override hooks for `test_cmd`/`lint_cmd`/`format_cmd`/
  `type_cmd`/`scan.focus_dirs`, following the existing `src_dir` per-field
  pattern.
- `scripts/little_loops/init/cli.py` — `_run_yes()` (choices assembly at
  lines 362-395) and `_run_plan()` (choices assembly at lines 465-469), both
  of which call `build_config(template, choices)` as the single wiring
  point.
- New file `scripts/little_loops/init/introspect.py` — net-new; no
  `introspect.py`-like module exists today (package currently has `core.py`,
  `cli.py`, `detect.py`, `writers.py`, `validate.py`, `install_check.py`,
  `tui.py`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/writers.py:merge_with_existing()` (lines
  123-146) — second override point after `build_config()`; introspection
  output must respect its existing-config-vs-fresh-build precedence, not
  fight it.
- `scripts/little_loops/init/cli.py:_run_apply()` (lines 491-571) — doesn't
  call `build_config`/introspection; replays a prior `--plan` JSON's
  `proposed_config`, so provenance must already be baked into `_run_plan`'s
  output.

### Similar Patterns
- `scripts/little_loops/host_runner.py` `CapabilityEntry` (lines 123-133) /
  `HookEntry` (lines 136-145) — `@dataclass(frozen=True)` + `Literal[...]`
  status tag + trailing `note: str = ""`; the closest existing shape to model
  `IntrospectedValue` after.
- `scripts/little_loops/codequery/core.py` `ProviderStatus` (lines 59-66) —
  same tagged-value shape (`available: bool`, `freshness: Literal[...]`,
  `detail: str`).
- `scripts/little_loops/init/validate.py` `DepWarning` (lines 14-19) —
  flat `message` + optional `install_hint`; the exact dataclass-to-JSON-list
  convention `_run_plan` already uses for `warnings` (`cli.py:485`) — follow
  for a new `ambiguities` list.
- `scripts/little_loops/host_runner.py:_inject_agent_persona` (lines
  473-488) — only existing `tomllib` usage; shape to imitate for
  `pyproject.toml` parsing.
- `scripts/little_loops/init/detect.py:_glob_match()` (lines 48-50) /
  `detect_documents()` (lines 71-121) — glob-based probing with `seen: set`
  dedup + `_EXCLUDE_DIRS` skip-list, existence-only today.

### Tests
- `scripts/tests/test_init_core.py` `TestBuildConfig`, `TestDetectProjectType`,
  `TestDetectAllRealTemplates` (lines 310-406) — existing test classes to
  extend; `fake_templates` fixture (lines 68-90).
- `scripts/tests/test_init_core.py:test_plan_emits_json` (lines 1537-1548) —
  asserts `plan` JSON keys (`detected`/`proposed_config`/`host_options`/
  `warnings`); extend if a `provenance`/`ambiguities` key is added.
- `scripts/tests/integration/test_init_e2e.py` —
  `test_plan_apply_produces_same_artifacts_as_yes` (lines 97-142) and
  `test_plan_output_has_no_logo_and_stays_valid_json` (lines 179-193) —
  round-trip and stdout-purity tests that must keep passing.

## Acceptance Criteria

- Fresh init fixture with `pyproject.toml` declaring pytest/ruff and source
  under `scripts/<pkg>/__init__.py` yields `src_dir: scripts/` and confirmed
  commands, each tagged with provenance in the printed summary.
- Fixture with two top-level package dirs keeps the template `src_dir` and
  records both candidates as an ambiguity.
- `package.json` with a `scripts.test` entry yields `test_cmd: npm run test`
  (or pnpm/yarn per lockfile).
- Re-init on a repo with an existing `ll-config.json` produces byte-identical
  `project`/`scan` sections to today (existing values win).
- No new hard dependency (tomllib is stdlib on 3.11+; guard or vendored
  fallback for older floors if the package supports them).
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: Python + TS/JS manifest parsing, src_dir/focus_dirs layout probing,
  provenance model, wiring into `_run_yes`/`_run_plan`.
- **Out**: exhaustive build-system coverage (Bazel, Nix, gradle task
  parsing…) — the FEAT-2705 skill handles the long tail; probabilistic
  scoring/heuristics beyond the exactly-one-candidate rule; running the
  commands to verify them (validate_deps stays the checker);
  `exclude_patterns` enrichment from .gitignore (possible follow-up ENH).

## Impact

- **Priority**: P3 — core of the epic; fixes the "structurally correct but
  functionally mis-pointed" fresh-init failure.
- **Effort**: Medium — new module + parsers + tests; wiring is small.
- **Risk**: Low-Medium — additive with existing-config precedence; main risk
  is over-eager inference, bounded by the declarations-only rule.

## Status

**Open** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-07-19T22:53:43 - `4598d4c4-6d97-4b71-a7aa-d801448f1c41.jsonl`
