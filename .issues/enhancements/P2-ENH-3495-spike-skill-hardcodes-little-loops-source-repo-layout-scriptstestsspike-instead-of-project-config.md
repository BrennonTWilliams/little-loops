---
id: ENH-3495
type: ENH
title: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike)
  instead of project config
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T00:15:03Z'
decision_needed: false
---

# ENH-3495: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike) instead of project config

## Summary

`/ll:spike` hardcodes the little-loops source-repo layout. Its `allowed-tools` frontmatter grants `Write(scripts/tests/spike/**)` / `Edit(scripts/tests/spike/**)`, its plan template and SKILL.md body place every spike package under `scripts/tests/spike/<slug>/`, and the promotion step targets `scripts/little_loops/spike/<slug>/`. Neither path exists in a consuming project, so in any project other than little-loops itself the skill either writes into a directory the user never asked for or is blocked by its own permission glob.

## Context

Found 2026-09-16 during the docs-audience sweep (CONTRIBUTING.md § Documentation Audience). `docs/reference/COMMANDS.md` carries an `ll-audience-ok` suppression on the `/ll:spike` entry that should be removed when this lands. The skills-audience gate in `scripts/tests/test_docs_audience_gate.py` exempts `skills/spike/` by this issue ID; remove that exemption too.

## Current Behavior

- `skills/spike/SKILL.md` frontmatter: `Write(scripts/tests/spike/**)`, `Edit(scripts/tests/spike/**)`.
- SKILL.md body (Implementation, Spike location, Promotion, `--check` mode) and `skills/spike/plan-template.md` all name `scripts/tests/spike/<slug>/` and `scripts/little_loops/spike/<slug>/` literally.
- The regression-suite command `python -m pytest scripts/tests/<named-regression-suite>.py` assumes the source-repo test dir.

## Expected Behavior

Spike location derives from the consuming project's config: `project.test_dir` (or `tests/` when unset) joined with `spike/<slug>/`, and the promotion target derives from `project.src_dir`. `allowed-tools` must still fence writes to the spike directory only; since the frontmatter glob is static, either widen it to a config-independent shape (e.g. `Write(**/spike/**)`) or document that consuming projects override it via `.claude/settings` — decide during refinement. The skill must run unchanged in a project whose layout is `src/` + `tests/`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

Expected Behavior leaves the `allowed-tools` static-glob resolution as an open decision ("decide during refinement"). Codebase research found no existing precedent for either branch in this repo — `skills/spike/SKILL.md` is the only skill whose `allowed-tools` targets a `scripts/tests/...`-shaped subpath at all, and no skill or command anywhere uses a widened prefix-free glob (`Write(**/foo/**)`); a project-local Claude Code settings override is not a checked-in file in this repo today. Both alternatives are genuinely novel here, not applications of an existing pattern.

**Option A**: Widen `allowed-tools` to a config-independent glob shape — `Write(**/spike/**)` / `Edit(**/spike/**)` — so the grant matches a `spike/<slug>/` directory regardless of where `project.test_dir` resolves in a given consuming project, with no per-project setup required.

> **Selected:** Option A — scores 10/12 vs. Option B's 4/12; satisfies AC3 out-of-the-box for any consuming-project layout with no new mechanism, and the `**/x/**` glob token is already idiomatic in this codebase (scan/exclude patterns) even though this is its first use in an `allowed-tools` grant.

**Option B**: Keep a project-specific static glob and document that consuming projects whose resolved `project.test_dir` differs from what ships by default must override the grant themselves via a project-local Claude Code settings override (not currently a checked-in file in this repo), since Claude Code's `allowed-tools` frontmatter cannot itself be dynamically parameterized by a config value resolved at skill-run time.

**Recommended**: Option A — it satisfies Acceptance Criterion 3 ("`allowed-tools` still restricts writes to the spike directory in a `src/` + `tests/` project") for any consuming-project layout without requiring the user to configure anything first, whereas Option B pushes a manual setup burden onto every consuming project and has no existing mechanism in this repo to model it on.

### Decision Rationale

**Selected:** Option A — widen `allowed-tools` to `Write(**/spike/**)` / `Edit(**/spike/**)`.

**Reasoning:** Option A satisfies AC3 for any consuming-project layout with zero per-project setup, reusing a glob token (`**/x/**`) already idiomatic in this codebase's scan/exclude configs even though this is its first appearance in a permission grant. Option B does not actually resolve the issue's core defect — it keeps a hardcoded, project-specific literal and requires every consuming project with a non-default `test_dir` to manually edit an uncommitted `.claude/settings.json` before the skill works, which contradicts this codebase's documented zero-config design goal (`terminal_adapter.py`, ENH-2317, FEAT-1931) and has no existing precedent to model — no skill or command doc in this repo instructs users to hand-edit permissions for a skill to function.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 0/3 |
| Simplicity | 3/3 | 2/3 |
| Testability | 3/3 | 1/3 |
| Risk | 2/3 | 1/3 |
| **Total** | **10/12** | **4/12** |

**Key evidence:**
- No skill or command in this repo uses a prefix-free `Write(**/foo/**)`/`Edit(**/foo/**)` grant today, but the `**/x/**` shape itself is an established convention for scan/exclude patterns (`scripts/little_loops/config/features.py:346`, `config-schema.json:69,826`, every `templates/*.json` project type, `.ll/ll-config.json:20-24`) and is documented in-repo as matching any depth including the root (`docs/claude-code/memory.md:201-206`).
- The collision risk noted for Option A — `**/spike/**` could in principle match an unrelated top-level `spike/` directory a consuming-project user creates, or a `node_modules/spike/**` path — is real but narrow (bounded to directories literally named `spike`) and has no existing precedent either confirming or ruling it out, since no prior `allowed-tools` grant has used this shape.
- No committed `.claude/settings.json`/`settings.local.json` exists anywhere in this repo (`.gitignore:59` keeps it out of version control), and the only "hand-edit settings.json" precedent in little-loops' own docs (`README.md:90`) is a narrowly-scoped plugin-install fallback, not a skill-functionality permission-scoping mechanism — undermining Option B's premise that consuming projects have an established, documented path to do this.
- Every other instance of permission entries entering `.claude/settings*.json` in this codebase is automation-written by `ll-init`/`ll-adapt` (`docs/guides/GETTING_STARTED.md:84,103`, `docs/reference/CLI.md:52`, FEAT-749, ENH-1846, BUG-2042), never doc-instructed manual user action — Option B would be the first case of the latter.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

Confirmed literal-path and convention findings from `codebase-locator`, `codebase-analyzer`, and `codebase-pattern-finder`, grouped below.

### Files to Modify
- `skills/spike/SKILL.md` — `allowed-tools` `Write(scripts/tests/spike/**)`/`Edit(scripts/tests/spike/**)` (lines 10, 12) plus 12 body references to `scripts/tests/spike/`/`scripts/little_loops/spike/` (lines 141, 146, 149, 156, 161, 172, 174, 185, 213, 215, 253, 254) need to resolve from `project.test_dir`/`project.src_dir`.
- `skills/spike/plan-template.md` — 5 references to the same literals (lines 44, 46, 49, 76, 89).
- `scripts/tests/test_docs_audience_gate.py` — remove the `HARNESS_EXEMPT` entry at line 38 and update `test_exempt_prefix_excluded` (lines 189-192), which currently hard-asserts `skills/spike/` files are excluded from the audience scan; that assertion inverts once the exemption is removed.
- `docs/reference/COMMANDS.md` — remove the `ll-audience-ok` suppression comment at line 378.

### Dependent Files (Callers/Importers)
- `.gemini/skills/spike/SKILL.md`, `.gemini/skills/spike/plan-template.md`, `.kimi-code/skills/spike/SKILL.md`, `.kimi-code/skills/spike/plan-template.md`, `.qwen/skills/spike/SKILL.md`, `.qwen/skills/spike/plan-template.md` — host-adapter mirrors of `skills/spike/`, synced via `ll-adapt --host <name> --apply`; carry the identical hardcoded literals today and will drift out of sync with the fixed source unless re-synced after this lands.
- `scripts/tests/test_spike_skill.py::test_spike_code_confined_to_tests_dir` — asserts `"scripts/tests/spike/" in _plan_text()` via raw substring match; this is the test currently pinning the hardcoded literal this issue changes and needs updating alongside the fix.

### Conventions in Force
- This codebase resolves config values inside a markdown skill's bash body via the `ll-config get <key>` CLI (wrapping `BRConfig.resolve_variable()`), not by hand-parsing `.ll/ll-config.json` — established by ENH-2678, whose stated rationale is "config is read only in Python, never in markdown skills." The only existing call site is `skills/go-no-go/SKILL.md:154` (`PENALTY=$(ll-config get history.go_no_go.correction_penalty)`).
- The `{{config.project.src_dir}}`/`{{config.project.test_dir}}` template-token syntax used elsewhere in `commands/*.md` and some `skills/*/SKILL.md` prose is not usable here: it only expands under `ll-auto`'s `skill_expander.py` pre-expansion pass (frontmatter is stripped before expansion runs, and interactive/slash-command invocation never triggers it at all) — `scripts/little_loops/skill_expander.py:126-165`, `docs/reference/CLI.md:598`, `docs/reference/API.md:5170`.
- No skill or command in this codebase uses a widened, config-independent `allowed-tools` glob shape (e.g. `Write(**/spike/**)`) — confirmed absent by a repo-wide search. `skills/spike/SKILL.md` is the only skill whose `allowed-tools` targets a `scripts/tests/...`-shaped subpath at all; there is no existing precedent for either resolution named in Expected Behavior.
- No hardcode-detection gate covers `skills/` or `commands/` for `scripts/tests`/`scripts/little_loops` literals — `test_builtin_loop_hardcode_gate.py` is scoped only to `scripts/little_loops/loops/**/*.yaml` (its `BUILTIN_LOOPS_DIR` constant). A regression here would not be caught by any existing automated check.

## Program Design

### Types

- `SPIKE_DIR: str` (bash var, `<test_dir>/spike/<slug>`)
- `PROMOTE_DIR: str` (bash var, `<src_dir>/spike/<slug>`)

### Signatures

- `BRConfig.resolve_variable(self, var_path: str) -> str | None` — existing,
  `scripts/little_loops/config/core.py:1108`; backs the `ll-config get
  project.test_dir` / `ll-config get project.src_dir` CLI already exercised
  from bash elsewhere (`scripts/little_loops/cli/config.py`)
- `BRConfig.get_src_path(self) -> Path` — existing,
  `scripts/little_loops/config/core.py:606`

### Call Path

`skills/spike/SKILL.md` Phase 3 (Plan) / Phase 4 (Implement) -> `ll-config get
project.test_dir` -> `BRConfig.resolve_variable("project.test_dir")` ->
`SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"` (replaces the literal
`scripts/tests/spike/<slug>/`); Phase 6 (Promotion) -> `ll-config get
project.src_dir` -> `BRConfig.get_src_path` -> `PROMOTE_DIR="${SRC_DIR%/}/spike/<slug>"`
(replaces the literal `scripts/little_loops/spike/<slug>/`).
`skills/spike/plan-template.md` follows the same substitution for its
`Critical files`, `Implementation`, and `Promotion` sections. Note: this
repo's own `.ll/ll-config.json` does not set `project.test_dir`, so it
currently resolves to the schema default `"tests"`, not the actual
`scripts/tests/` root — implementation should confirm whether that also
needs setting here, or whether the skill falls back to a
`pytest.ini`/`pyproject.toml` probe when `project.test_dir` is absent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

`BRConfig.resolve_variable("project.test_dir")` never returns `None` for this key: `ProjectConfig.from_dict()` (`scripts/little_loops/config/core.py:239-240`) defaults `test_dir` to `"tests"` and `src_dir` to `"src/"` when absent from `.ll/ll-config.json`, and `to_dict()` (`core.py:763-766`) always materializes both keys before `resolve_variable`'s dict-walk runs. This resolves the open question in the Call Path note above: no `pytest.ini`/`pyproject.toml` probe fallback is needed — the method's contract guarantees a non-empty string.

This repo's own `.ll/ll-config.json` sets `project.src_dir: "scripts/"` but does not set `project.test_dir`, so `ll-config get project.test_dir` resolves to the schema default `"tests"` here today — not `scripts/tests/`, where spike packages actually live and where this repo's own `project.test_cmd` (`python -m pytest scripts/tests/`) points. Implementing the fix as a literal `project.test_dir` + `spike/<slug>` join, without also adding `"test_dir": "scripts/tests/"` to this repo's own `.ll/ll-config.json` (mirroring the existing explicit `src_dir` entry), would silently relocate this repo's own future spikes to `tests/spike/<slug>/`, diverging from every prior spike under `scripts/tests/spike/` and from `test_spike_code_confined_to_tests_dir`'s current assumption.

## Scope Boundaries

- **In scope**: deriving the spike directory and promotion target from
  `project.test_dir`/`project.src_dir` in `skills/spike/SKILL.md` and
  `skills/spike/plan-template.md`; resolving the `allowed-tools` static-glob
  tension (widen to a config-independent shape or document a settings
  override); removing the `skills/spike/` exemption in
  `test_docs_audience_gate.py` and the `ll-audience-ok` suppression in
  `docs/reference/COMMANDS.md`.
- **Out of scope**: changing the spike plan's required section shape
  (`plan-template.md`'s Context/Approach/Acceptance Criteria structure);
  changes to `/ll:explore-api` (the external-API analogue); migrating any
  spike artifacts already committed under `scripts/tests/spike/` in this
  repo.

## Impact

- **Priority**: P2 - functional-correctness/portability bug (not a crash):
  `/ll:spike` is unusable as shipped in any consuming project whose layout
  isn't `scripts/`, so it blocks a whole skill outside the source repo.
- **Effort**: Small - text/template substitution in two files
  (`SKILL.md`, `plan-template.md`) plus removing two doc-audience
  exemptions; reuses the existing `ll-config get project.src_dir` /
  `project.test_dir` CLI pattern already used elsewhere in the codebase
  (`scripts/little_loops/cli/issues/decisions.py:650`), no new mechanism
  needed.
- **Risk**: Low - the spike directory stays isolated under
  `<test_dir>/spike/<slug>/` either way; the only behavior change is which
  literal path is written to, verified by re-running the skill in both the
  `scripts/`-layout source repo and a `src/`+`tests/` fixture project.
- **Breaking Change**: No - existing spike artifacts already committed under
  `scripts/tests/spike/` are untouched; only future `/ll:spike` invocations
  resolve their path dynamically.

## Acceptance Criteria

- [ ] `skills/spike/SKILL.md` and `plan-template.md` contain no `scripts/tests` or `scripts/little_loops` literals.
- [ ] Spike dir and promotion target resolve from `project.test_dir` / `project.src_dir` with sensible defaults.
- [ ] `allowed-tools` still restricts writes to the spike directory in a `src/` + `tests/` project.
- [ ] The `skills/spike/` exemption in `test_docs_audience_gate.py` and the `ll-audience-ok` line in `docs/reference/COMMANDS.md` are removed.

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:decide-issue` - 2026-09-17T00:55:55 - `8e7ed6a7-45f1-4830-9b8d-ec6405748b84.jsonl`
- `/ll:refine-issue` - 2026-09-17T00:46:42 - `a247e656-a04b-48d2-b369-8647c50460db.jsonl`
- `/ll:format-issue` - 2026-09-17T00:37:18 - `2b860fe0-3e33-4473-a957-2f06e4ff45f0.jsonl`
