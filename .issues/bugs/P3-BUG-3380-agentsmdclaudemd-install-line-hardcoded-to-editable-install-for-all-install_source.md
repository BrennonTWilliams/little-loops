---
id: BUG-3380
type: BUG
title: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-02'
captured_at: '2026-09-02T22:19:40Z'
decision_needed: false
---

# BUG-3380: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source

## Summary

`ll-init` generates AGENTS.md (and CLAUDE.md) with a hardcoded `Install:` line
of `pip install -e "./scripts[dev]"` regardless of the consuming project's
`install_source`. This command is only valid for the little-loops source repo
itself (editable dev install with the `scripts/` package dir and `[dev]`
extras present); PyPI-installed and Claude Code plugin-installed consumers
have no `scripts[dev]` to install and the command fails for them.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Thread `install_source: str | None` from `detect_installation()` through to
`_render_commands_block()` so the `Install:` line varies per value. Two
constraints beyond the existing Root Cause/Suggested Fix text must both hold:

1. `_render_commands_block()`'s invocation must move out of
   module-import-time scope (`writers.py:252`/`256`) into a per-call site
   inside `write_claude_md()`/`write_agents_md()` — the current
   `_CLAUDE_MD_COMMANDS_BLOCK`/`_AGENTS_MD_COMMANDS_BLOCK` constants are
   frozen once at import and referenced unconditionally by every caller.
2. `install_source` must actually reach every production call site. It
   already does at `_run_yes()` (`cli.py:706`/`711`, via `cli.py:519`). It
   does **not** yet reach `_run_apply()` (`cli.py:918`/`923`) or
   `_apply_config()` (`tui.py:895`/`900`) — see Root Cause's Codebase
   Research Findings for why.

How `_run_apply()` obtains `install_source` before its writer calls is an
open choice:

**Option A**: Call `detect_installation(project_root)` unconditionally near
the top of `_run_apply()`, before the writer calls at `cli.py:918`/`923`,
rather than only inside the `if plan.get("requested_upgrade") and not
dry_run:` branch at `cli.py:934-935`. In `_apply_config()` (`tui.py:819`),
add an `install_source: str | None = None` parameter and pass the
already-computed local from `run_tui()` (`tui.py:185`) at its call site
(`tui.py:648-661`).

**Option B**: Populate `config["install_source"]` inside `_run_plan()`
(`cli.py:743-829`, which currently never sets this key) so `_run_apply()`
can read it back without a second `detect_installation()` call; thread the
same value into `_apply_config()` as in Option A.

**Recommended**: Option A — it reuses the existing `detect_installation()`
call pattern already used by `_run_yes()` (`cli.py:519`) and `run_tui()`
(`tui.py:185`) rather than introducing a new config-plumbing path through
`_run_plan()`, which today has no `install_source` concept at all.

The exact per-`install_source`-value wording of the `Install:` line is an
implementation choice, not dictated by this research; `tui.py:228-242`
shows existing precedent for a two-way message split (`local-editable` vs.
everything else) that a fix could follow or depart from.

> **Selected:** Option A — reuses the existing `detect_installation()`
> unconditional-near-top call shape already used by `_run_yes()`
> (`cli.py:519`) and `run_tui()` (`tui.py:185`), and the `_apply_config()`
> parameter addition matches that function's existing optional-keyword
> convention. Implementers should dedupe against the existing
> `detect_installation()` call at `cli.py:935` rather than leaving two
> calls in `_run_apply()`.

### Decision Rationale

**Selected**: Option A (11/12) over Option B (5/12).

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 3 | 1 |
| Testability | 3 | 2 |
| Risk | 2 | 1 |
| **Total** | **11** | **5** |

Option A mirrors the unconditional-`detect_installation()`-near-the-top
shape already present verbatim in both `_run_yes()` (`cli.py:519`) and
`run_tui()` (`tui.py:185`), and the `_apply_config()` parameter addition
follows that function's existing optional-keyword-arg convention exactly
(`tui.py:819-832`). Its only real risk is a redundant second
`detect_installation()` call if the pre-existing `cli.py:935` call isn't
removed/deduped — up to a 10s subprocess probe cost in the plugin-install
case — which the implementation should address directly rather than
leaving both calls in place.

Option B's write-side shape (`config["install_source"] = install_source`)
has exact precedent (`cli.py:677-678`, `tui.py:623-624`), but reading that
value back in a later, separately-invoked `_run_apply()` crosses a
JSON-serialization boundary the code's own docstring flags as
"machine-editable" — a shape with zero existing precedent that runs
against two established conventions in this codebase: detection-only
facts are kept outside `proposed_config` (the `plan["detected"]` section),
and potentially-stale plan data is recomputed fresh at apply-time rather
than trusted from the plan (`validate_deps` at `cli.py:927`).

## Integration Map

### Files to Modify
- `scripts/little_loops/init/writers.py` — `_render_commands_block()` (242),
  `write_claude_md()` (564), `write_agents_md()` (615): thread
  `install_source` in; move commands-block rendering off
  module-import-time.
- `scripts/little_loops/init/cli.py` — `_run_apply()` (832-939): resolve
  `install_source` availability before `cli.py:918`/`923` (see Proposed
  Solution Option A/B).
- `scripts/little_loops/init/tui.py` — `_apply_config()` (819) and its call
  site in `run_tui()` (648-661): thread `install_source` through as a new
  parameter.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:706,711` — `_run_yes()` calls
  `write_claude_md`/`write_agents_md`; `install_source` already a live
  local here (`cli.py:519`).
- `scripts/little_loops/init/cli.py:918,923` — `_run_apply()` calls same;
  `install_source` NOT yet in scope (see Root Cause).
- `scripts/little_loops/init/tui.py:895,900` — `_apply_config()` calls
  same; `install_source` NOT yet in scope (see Root Cause).
- `scripts/little_loops/init/__init__.py:20-31` — imports from
  `writers.py` (does not re-export `write_claude_md`/`write_agents_md`).

### Conventions in Force
- `install_source` comparisons in this codebase use direct `== "value"`
  string equality (`cli.py:247`, `cli.py:549`) or `in (tuple-of-values)`
  membership (`tui.py:192`, `tui.py:197-200`) against the raw string — no
  enum type, no dict dispatch. Unmatched/`None` values fall through to an
  implicit default branch rather than raising (contrast:
  `scripts/little_loops/pii.py:apply_pii_action()`'s `action` parameter
  raises `ValueError` on an unrecognized value — this codebase does not use
  one single convention for every enum-like string parameter).
- `_render_commands_block()` (`writers.py:242`) is already precedent for
  "parameterize the render function, call it with different args to freeze
  different text" — it already takes `desc_overrides` and is called twice
  with different arguments. There is no existing case in `writers.py`
  where a `write_*` function computes its text per-call from a parameter;
  every writer's output is currently import-time-frozen.

### Tests
- `scripts/tests/test_init_core.py` — `TestWriteClaudeMd` (1444-1534),
  `TestWriteAgentsMd` (1542-1616): real-filesystem writes into `tmp_path`,
  asserting on `result is True/False` and content substrings; no mocking.
  No `pytest.mark.parametrize` used anywhere in this file for enum-branch
  testing — this codebase's convention is one named test method per branch
  value (e.g. `test_local_editable_installation_detected`,
  `test_pypi_installation_detected` in `TestDetectInstallation`,
  `scripts/tests/test_init_install.py:67-98`).
- `scripts/tests/test_init_install.py` — `TestDetectInstallation`: mocks at
  the `subprocess.run`/`importlib.metadata.version` boundary via
  `unittest.mock.patch`.
- `scripts/tests/test_init_tui.py` — has a `mock_detect_installation`
  fixture (lines 25-32, 778) patching
  `little_loops.init.install_check.detect_installation`.
- `scripts/tests/test_config_schema.py::test_install_source_in_schema`
  (1023) — asserts schema enum contents; no change expected since the
  schema itself isn't changing.

### Documentation
- `docs/reference/CONFIGURATION.md:273-285` — documents the
  `install_source` enum and values; may want a note that the generated
  Install line now varies by source.
- `docs/reference/API.md:11165` — `detect_installation()` signature
  reference.

### Configuration
- N/A — no config schema changes; `install_source` enum already exists.

## Program Design

### Types
N/A — no new data types introduced; the change threads an existing
`str | None` value already returned by `detect_installation()`.

### Signatures
- `_render_commands_block(desc_overrides: dict[str, str] | None = None) -> str`
  (`writers.py:242`) — currently module-import-time only; would need an
  `install_source: str | None` parameter and to move to per-call invocation.
- `write_claude_md(project_root: Path, dry_run: bool = False) -> bool`
  (`writers.py:564`) — would need `install_source: str | None = None`.
- `write_agents_md(project_root: Path, dry_run: bool = False) -> bool`
  (`writers.py:615`) — same.
- `_apply_config(config, project_root, ll_dir, config_path, templates_dir,
  plugin_root, hosts, settings_target, force, console,
  claude_md_opt_in=False, existing_config=None)` (`tui.py:819`) — would need
  an `install_source: str | None = None` parameter threaded from its caller
  `run_tui()` (`tui.py:648-661`).

### Call Path
`detect_installation()` (`install_check.py:59`) -> `install_source` local ->
`write_claude_md()`/`write_agents_md()` (`writers.py:564`/`615`) ->
`_render_commands_block(desc_overrides, install_source)` (`writers.py:242`)
-> rendered `Install:` line text.

Reachable today: `_run_yes()` (`cli.py:519` -> `cli.py:706`/`711`). Not yet
reachable, needs new plumbing: `_run_apply()` (`cli.py:918`/`923`,
`detect_installation()` not called until `cli.py:935`) and the TUI's
`_apply_config()` (`tui.py:895`/`900`, `install_source` is a `run_tui()`
local at `tui.py:185` not passed into `_apply_config()`).

### Decision Rules
- Gap: what text renders per `install_source` value. Exact inputs: the four
  non-null values `detect_installation()` actually returns —
  `"local-editable"`, `"pypi"`, `"global-claude-code"`,
  `"project-claude-code"` — plus `None`. Existing precedent for a two-way
  split appears at `tui.py:239` (`== "local-editable"` vs. else) and
  `cli.py:549`. No exhaustive per-value switch on `install_source` exists
  anywhere in this codebase today; every existing branch checks one value
  vs. an implicit else.
- Gap: how `_run_apply()` obtains `install_source` before its writer calls
  at `cli.py:918`/`923`, given `detect_installation()` isn't invoked until
  `cli.py:935` and `_run_plan()` never populates `config["install_source"]`.
  **Resolved: Option A** — call `detect_installation()` unconditionally
  near the top of `_run_apply()`, deduping against the existing
  `cli.py:935` call (see Proposed Solution's Decision Rationale).

## Implementation Steps

1. `_render_commands_block()` (`writers.py:242`) accepts an
   `install_source: str | None` parameter and is invoked per-call from
   `write_claude_md()`/`write_agents_md()` rather than frozen once at
   module import (`writers.py:252`/`256`) — the `Install:` line it emits
   varies with the value passed in.
2. `write_claude_md()` (`writers.py:564`) and `write_agents_md()`
   (`writers.py:615`) accept `install_source: str | None = None` and pass
   it through to `_render_commands_block()`.
3. `install_source` reaches every production call site of
   `write_claude_md`/`write_agents_md`: it already does at `_run_yes()`
   (`cli.py:706`/`711`, via `cli.py:519`); `_run_apply()`
   (`cli.py:918`/`923`) and `_apply_config()` (`tui.py:895`/`900`, via a
   new parameter threaded from `run_tui()`'s `tui.py:185` local) resolve
   per the Proposed Solution decision.
4. `TestWriteClaudeMd`/`TestWriteAgentsMd`
   (`scripts/tests/test_init_core.py:1444-1616`) gain coverage for at
   least one non-`local-editable` `install_source` value, following this
   file's one-test-method-per-value convention (see `TestDetectInstallation`
   in `test_init_install.py` for the precedent).
5. `python -m pytest scripts/tests/test_init_core.py
   scripts/tests/test_init_install.py scripts/tests/test_init_tui.py -v`
   passes.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`scripts/little_loops/init/writers.py:247`, inside `_render_commands_block()`:

```python
lines.extend(["", 'Install: `pip install -e "./scripts[dev]"`', ""])
```

This runs once at module import time to build module-level constants
`_CLAUDE_MD_COMMANDS_BLOCK` (line 252) and `_AGENTS_MD_COMMANDS_BLOCK` (line
256), which `write_claude_md()` and `write_agents_md()` then append verbatim.
Neither writer function accepts an `install_source` parameter, so the string
never varies per project.

`install_source` is already computed and in scope at every call site that
could pass it through instead:

- `scripts/little_loops/init/cli.py:519-520` (`detect_installation(...)`)
  before the writer calls at `cli.py:706` / `cli.py:711`
- `scripts/little_loops/init/cli.py:918-936` (`_run_yes` path) before the
  writer calls at `cli.py:918` / `cli.py:923`
- `scripts/little_loops/init/tui.py:185-274` before the writer calls at
  `tui.py:895` / `tui.py:900`

Precedent for branching writer/CLI behavior on `install_source` already
exists at `cli.py:247` (`== "project-claude-code"`) and `cli.py:549`
(`== "local-editable"`).

`config-schema.json:2062-2066` defines the `install_source` enum:
`local-editable`, `pypi`, `global-claude-code`, `project-claude-code`,
`global-codex`, `global-pi`, or `null`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- `_render_commands_block()` is invoked exactly twice, both at **module import time**, not per-call: `_CLAUDE_MD_COMMANDS_BLOCK = _render_commands_block(_CLAUDE_MD_DESC_OVERRIDES)` (`writers.py:252`) and `_AGENTS_MD_COMMANDS_BLOCK = _render_commands_block()` (`writers.py:256`), which also freeze `_CLAUDE_MD_NEW_FILE_CONTENT`/`_AGENTS_MD_NEW_FILE_CONTENT` (`writers.py:258-259`). `write_claude_md()` (`writers.py:597,604`) and `write_agents_md()` (`writers.py:650,657`) only reference these pre-frozen constants — neither calls `_render_commands_block()` itself. Adding an `install_source` parameter to the outer `write_*` functions alone is not sufficient; `_render_commands_block()`'s invocation must move out of module scope into a per-call site inside `write_claude_md`/`write_agents_md`.
- `install_source` is **not** in scope at `cli.py:918`/`923` (inside `_run_apply()`, def at `cli.py:832`): `detect_installation()` is imported at `cli.py:851` but not called until `cli.py:935`, gated behind `if plan.get("requested_upgrade") and not dry_run:` (`cli.py:934`) — which runs *after* both writer calls. `_run_plan()` (`cli.py:743-829`) also never populates `config["install_source"]`, so there is no config-based fallback either. This contradicts this issue's own claim above that install_source is "already computed and in scope at every call site" — that claim holds for `_run_yes()` (`cli.py:519` -> `cli.py:706/711`) but not for `_run_apply()`.
- `tui.py:895`/`900` are inside `_apply_config()` (def at `tui.py:819`), a *different* function from `run_tui()` (def at `tui.py:128`) where `install_source` is actually detected (`tui.py:185`). `_apply_config()`'s signature (`tui.py:819-832`) has no `install_source` parameter, and its call site inside `run_tui()` (`tui.py:648-661`) does not pass the local `install_source` through.
- `detect_installation()` (`scripts/little_loops/init/install_check.py:59-92`) only ever returns `"local-editable"`, `"pypi"`, `"global-claude-code"`, `"project-claude-code"`, or `None` — never `"global-codex"`/`"global-pi"`, despite both appearing in the `config-schema.json:2062-2066` enum. A fix only needs to branch on the four non-null values `detect_installation()` actually produces (plus `None`).

## Steps to Reproduce

1. Run `ll-init` in a project where little-loops was installed via
   `pip install little-loops` (install_source: `pypi`) or as a Claude Code
   plugin (`global-claude-code` / `project-claude-code`).
2. Open the generated `AGENTS.md` (or `CLAUDE.md`).
3. The `Install:` line reads `pip install -e "./scripts[dev]"` — a command
   that assumes a `scripts/` dir and dev extras that don't exist in that
   project.

## Expected vs Actual

- **Expected**: the install line reflects how the project actually installed
  little-loops — e.g. `pip install little-loops` for `pypi`, no bare
  `pip install -e "./scripts[dev]"` for plugin-based installs.
- **Actual**: every generated AGENTS.md/CLAUDE.md gets the same
  source-repo-only editable-dev-install command.

## Suggested Fix

Thread `install_source: str | None` into `_render_commands_block()` and into
`write_claude_md()` / `write_agents_md()`; branch the Install line so
`pip install -e "./scripts[dev]"` renders only when
`install_source == "local-editable"`, otherwise `pip install little-loops`
(or omit the line for plugin-based `install_source` values, where there's no
pip install to run at all). Update the three call sites above to pass the
already-detected `install_source` through instead of leaving it unused.

## Related

`P2-BUG-1071` / `P3-ENH-1020` cover a related but distinct instance of the
same install_source-unaware problem class in `skills/init/SKILL.md` /
`skills/configure/SKILL.md`'s bash `INSTALL_CMD` shim. That shim already
branches correctly (`[ -d "./scripts" ] && ... || INSTALL_CMD="pip install
--upgrade little-loops"`) and is not affected by this bug — this issue is
scoped to the Python-side AGENTS.md/CLAUDE.md generator in `writers.py` only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- The `[ -d "./scripts" ]` directory-existence check this section attributes to `skills/init/SKILL.md`/`skills/configure/SKILL.md` no longer exists in either file — it was replaced (BUG-1071/ENH-1020) by a `pip show ... | grep "Editable project location:"` check (`skills/configure/SKILL.md:80-87`, mirrored in `skills/update/SKILL.md:123-131`). `scripts/tests/test_update_skill.py:112-127,200-208` explicitly assert `[ -d "./scripts" ]` is absent from both files. `skills/init/SKILL.md` itself has no `INSTALL_CMD` shim at all — only `skills/configure/SKILL.md` and `skills/update/SKILL.md` do. The overall claim (this shim already correctly branches and is unaffected by this bug) still holds; only the quoted mechanism text is stale.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-02 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-02T22:37:14 - `bea601b2-a6af-4ef3-8359-e10eab8b1a54.jsonl`
- `/ll:refine-issue` - 2026-09-02T22:29:09 - `25d94b5b-402d-469f-a07b-24795969ce49.jsonl`
- `/ll:capture-issue` - 2026-09-02T22:19:45 - `64850b61-eea3-464a-8dc5-33dc204c7fce.jsonl`
