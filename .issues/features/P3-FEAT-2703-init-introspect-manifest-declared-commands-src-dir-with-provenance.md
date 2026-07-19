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
