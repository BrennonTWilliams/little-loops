---
id: BUG-3380
type: BUG
title: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-02'
captured_at: '2026-09-02T22:19:40Z'
decision_needed: true
confidence_score: 100
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
---

# BUG-3380: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source

## Summary

`ll-init` generates AGENTS.md (and CLAUDE.md, and GEMINI.md since
FEAT-2190) with a hardcoded `Install:` line
of `pip install -e "./scripts[dev]"` regardless of the consuming project's
`install_source`. This command is only valid for the little-loops source repo
itself (editable dev install with the `scripts/` package dir and `[dev]`
extras present); PyPI-installed and Claude Code plugin-installed consumers
have no `scripts[dev]` to install and the command fails for them.

## Current Behavior

Every `ll-init` write path (`--yes`, `apply --config`, and the TUI wizard)
appends the same import-time-frozen `## little-loops CLI Commands` block to
CLAUDE.md/AGENTS.md/GEMINI.md, ending in
`Install: \`pip install -e "./scripts[dev]"\``.
The value of `install_source` is detected (`cli.py:536`, `tui.py:185`) but
never reaches the writers, so a PyPI consumer, a plugin consumer, and a
`local-editable` consumer whose editable checkout lives elsewhere all get a
command that references a `./scripts` directory they do not have.

## Expected Behavior

The `Install:` line reflects how little-loops is actually installed for this
project:

| `install_source` | Rendered `Install:` line |
|---|---|
| `local-editable`, editable path resolved and **inside** `project_root` | `pip install -e "./scripts[dev]"` — i.e. `./<relpath>[dev]`; byte-identical to today's output for the source repo |
| `local-editable`, editable path resolved and **outside** `project_root` | `pip install -e "<relpath>[dev]"` where `<relpath>` is `os.path.relpath(Path(install_path).resolve(), project_root.resolve())` (e.g. `../brenentech/little-loops/scripts[dev]`); absolute path only if `relpath` raises (cross-drive on Windows) |
| `local-editable`, path unresolvable | `pip install -e "./scripts[dev]"` (source-repo fallback) |
| `pypi` | `pip install little-loops` |
| `global-claude-code` / `project-claude-code` | `pip install little-loops` |
| `None` | `pip install little-loops` |

The line is never omitted: a Claude Code plugin install provides `/ll:*`
commands but not the `ll-*` CLIs the block documents, and the TUI already
states this (`tui.py:229-233`). `local-editable` is therefore the only
special case.

**Both paths are `.resolve()`d before `relpath`.** `pip show` reports the
editable location as pip recorded it, while `project_root` may arrive
unresolved (`--root`, or a symlinked temp dir such as macOS `/tmp` ->
`/private/tmp`, which is exactly where pytest's `tmp_path` lives). A
string-only `relpath` on mismatched forms turns an in-tree install into a
bogus `../../..` chain.

**The out-of-tree relative path is still machine-specific, and that is
accepted.** `../brenentech/little-loops/scripts[dev]` is only valid where
the consumer and the checkout share that layout; a contributor cloning the
consumer gets a broken line. This is deliberate: per `.claude/CLAUDE.md`,
every `local-editable` consumer on the maintainer's machine exists to
exercise little-loops development, and the relative form is what keeps the
committed file clear of `ll-verify-private-refs`. Do not "fix" this later by
emitting the bare `pip install little-loops` for out-of-tree editable
installs.

**Why relative, not absolute.** CLAUDE.md/AGENTS.md is a committed file.
`pip show` reports the editable location as an absolute home path (on the
maintainer's machine, `/Users/<name>/.../little-loops/scripts`), which is
exactly the `abs_user_path` pattern `ll-verify-private-refs`
(`scripts/little_loops/cli/verify_private_refs.py:135-141`) rejects and
which runs as a pre-commit hook in this repo (`.pre-commit-config.yaml:14`).
Rendering the absolute path would also change the source repo's own output
from `./scripts[dev]` (the editable path *is* resolved there), contradicting
the "preserves today's output for the source repo" claim under Impact. The
in-tree/relpath rule keeps both properties.

**`[dev]` extras are kept for every `local-editable` row.** They are
arguably unnecessary for a consumer that is not developing little-loops, but
the existing `--upgrade` path already installs `{editable_path}[dev]`
(`cli.py:592`); the generated line matches that convention rather than
introducing a second form. Do not relitigate this during implementation.

**The bare form `pip install little-loops` is used for every
non-`local-editable` row, not `pip install --upgrade little-loops`.** `pypi`
is the primary consumer install path, and these rows also cover plugin
installs and `None`. The `--upgrade` form exists in this codebase only in
update contexts — the version-mismatch branch of `_run_yes()`
(`cli.py:605-613`), `skills/configure/SKILL.md:86`, and
`skills/update/SKILL.md:130` — and is not a precedent for an install
instruction. The generated line is read by people who do not yet have the
package: a contributor cloning the consuming repo (CLAUDE.md/AGENTS.md is
committed), or a plugin-install consumer who has `/ll:*` but not the `ll-*`
CLIs the block documents. `--upgrade` on a first install reads as a
mistake. The bare form matches the not-yet-installed branch of `_run_yes()`
(`cli.py:543`, `cli.py:551`). Do not relitigate this during implementation;
the test for the `pypi` row asserts the exact bare string.

## Motivation

The generated instructions file is the first thing a consuming project's
agent reads. A broken install command there is a visible defect on first
run, and per `.claude/CLAUDE.md` every little-loops consumer on the
maintainer's machine is `local-editable` against a checkout outside the
consumer, so the current text is wrong for *all* local consumers, not just
PyPI/plugin ones.

## Proposed Solution

Thread `install_source: str | None` from `detect_installation()` through to
`_render_commands_block()` so the `Install:` line varies per value. Two
constraints beyond the existing Root Cause/Suggested Fix text must both hold:

1. `_render_commands_block()`'s invocation must move out of
   module-import-time scope (`writers.py:252`/`256`) into a per-call site
   inside `write_claude_md()`/`write_agents_md()`/`write_gemini_md()` — the
   current `_CLAUDE_MD_COMMANDS_BLOCK`/`_AGENTS_MD_COMMANDS_BLOCK` constants
   are frozen once at import and referenced unconditionally by every caller.
   `write_gemini_md()` (`writers.py:665`, FEAT-2190, landed after this issue
   was refined) is the third writer: it reuses `_AGENTS_MD_COMMANDS_BLOCK`
   directly (`writers.py:690`) and via `_GEMINI_MD_NEW_FILE_CONTENT`
   (`writers.py:262`), and is called from all three production sites
   (`cli.py:732`, `cli.py:949`, `tui.py:905`). It is in scope.
2. `install_source` must actually reach every production call site. It
   already does at `_run_yes()` (`cli.py:723`/`728`/`732`, via `cli.py:536`). It
   does **not** yet reach `_run_apply()` (`cli.py:940`/`945`/`949`) or
   `_apply_config()` (`tui.py:896`/`901`/`905`) — see Root Cause's Codebase
   Research Findings for why.

How `_run_apply()` obtains `install_source` before its writer calls is an
open choice:

**Option A**: Call `detect_installation(project_root)` unconditionally near
the top of `_run_apply()`, before the writer calls at `cli.py:940`/`945`/`949`,
rather than only inside the `if plan.get("requested_upgrade") and not
dry_run:` branch at `cli.py:960-961`. In `_apply_config()` (`tui.py:819`),
add an `install_source: str | None = None` parameter and pass the
already-computed local from `run_tui()` (`tui.py:185`) at its call site
(`tui.py:648-661`).

**Option B**: Populate `config["install_source"]` inside `_run_plan()`
(`cli.py:764-850`, which currently never sets this key) so `_run_apply()`
can read it back without a second `detect_installation()` call; thread the
same value into `_apply_config()` as in Option A.

**Recommended**: Option A — it reuses the existing `detect_installation()`
call pattern already used by `_run_yes()` (`cli.py:536`) and `run_tui()`
(`tui.py:185`) rather than introducing a new config-plumbing path through
`_run_plan()`, which today has no `install_source` concept at all.

The per-value wording of the `Install:` line is fixed by the table in
Expected Behavior. Note that a plain two-way split (`local-editable` ->
`./scripts[dev]`, else `pip install little-loops`) is **not sufficient**:
`./scripts[dev]` is only correct when the editable checkout *is* the
consuming project (i.e. the little-loops source repo). For every other
`local-editable` consumer the editable location is elsewhere and must be
resolved.

**Editable-path resolution.** `_is_editable_install()`
(`install_check.py:42-56`) already parses the `Editable project location:`
line from `pip show little-loops` and discards the value; `cli.py:568-583`
re-parses the same line for the `--upgrade` path. Extend
`detect_installation()` to return that location as the third tuple element
(`install_path`) for `local-editable` installs — its docstring
(`install_check.py:64-69`) currently says `install_path` is plugin-only and
must be updated. Thread `install_path` alongside `install_source` into the
writers so the `local-editable` branch can render the path per the Expected
Behavior table (relative to `project_root`; never the raw absolute path),
falling back to `./scripts[dev]` when `install_path` is `None`. Do **not**
write the `<editable-path>` placeholder that `tui.py:240` prints — that is
acceptable in a console hint, not in a generated instructions file.

Overloading the third tuple element is safe: all three current callers
discard `_install_path` (`cli.py:536`, `cli.py:961`, `tui.py:185`), so no
code today treats a non-`None` `install_path` as "plugin install".

**Dedupe the second `Editable project location:` parser.** Once
`detect_installation()` returns the editable path, the `--upgrade` branch in
`_run_yes()` (`cli.py:566-602`) must use the `_install_path` already in
scope from `cli.py:536` instead of re-running `pip show` and re-parsing the
line (`cli.py:568-583`). Replace that block with the returned value; keep
the existing "could not determine editable install path" warning for the
`None` case.

> **Selected:** Option A — reuses the existing `detect_installation()`
> unconditional-near-top call shape already used by `_run_yes()`
> (`cli.py:536`) and `run_tui()` (`tui.py:185`), and the `_apply_config()`
> parameter addition matches that function's existing optional-keyword
> convention. Implementers should dedupe against the existing
> `detect_installation()` call at `cli.py:961` rather than leaving two
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
shape already present verbatim in both `_run_yes()` (`cli.py:536`) and
`run_tui()` (`tui.py:185`), and the `_apply_config()` parameter addition
follows that function's existing optional-keyword-arg convention exactly
(`tui.py:819-832`). Its only real risk is a redundant second
`detect_installation()` call if the pre-existing `cli.py:961` call isn't
removed/deduped — up to a 10s subprocess probe cost in the plugin-install
case — which the implementation should address directly rather than
leaving both calls in place.

Option B's write-side shape (`config["install_source"] = install_source`)
has exact precedent (`cli.py:694-695`, `tui.py:624`), but reading that
value back in a later, separately-invoked `_run_apply()` crosses a
JSON-serialization boundary the code's own docstring flags as
"machine-editable" — a shape with zero existing precedent that runs
against two established conventions in this codebase: detection-only
facts are kept outside `proposed_config` (the `plan["detected"]` section),
and potentially-stale plan data is recomputed fresh at apply-time rather
than trusted from the plan (`validate_deps` at `cli.py:953`).

## Integration Map

### Files to Modify
- `scripts/little_loops/init/writers.py` — `_render_commands_block()` (242),
  `write_claude_md()` (567), `write_agents_md()` (618), `write_gemini_md()`
  (665): thread `install_source`/`install_path` in; move commands-block
  rendering off module-import-time (constants at 252, 256, 258-259, 262).
- `scripts/little_loops/init/cli.py` — `_run_apply()` (853-970): resolve
  `install_source` availability before `cli.py:940`/`945`/`949` (see Proposed
  Solution Option A/B). `_run_yes()` (566-602): replace the inline
  `pip show` re-parse with the `_install_path` returned at 536.
- `scripts/little_loops/init/tui.py` — `_apply_config()` (819) and its call
  site in `run_tui()` (648-661): thread `install_source` (and `install_path`)
  through as new parameters.
- `scripts/little_loops/init/install_check.py` — `detect_installation()`
  (59-92) and `_is_editable_install()` (42-56): return the parsed
  `Editable project location:` value as `install_path` for `local-editable`
  installs; update the docstring at 64-69 which says `install_path` is
  plugin-only.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:723,728,732` — `_run_yes()` calls
  `write_claude_md`/`write_agents_md`/`write_gemini_md`; `install_source`
  already a live local here (`cli.py:536`).
- `scripts/little_loops/init/cli.py:940,945,949` — `_run_apply()` calls same;
  `install_source` NOT yet in scope (see Root Cause).
- `scripts/little_loops/init/tui.py:896,901,905` — `_apply_config()` calls
  same; `install_source` NOT yet in scope (see Root Cause).
- `scripts/little_loops/init/__init__.py:20-31` — imports from
  `writers.py` (does not re-export `write_claude_md`/`write_agents_md`).

### Conventions in Force
- `install_source` comparisons in this codebase use direct `== "value"`
  string equality (`cli.py:263`, `cli.py:566`) or `in (tuple-of-values)`
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
- `scripts/tests/test_init_core.py` — `TestWriteClaudeMd` (1445-1541),
  `TestWriteAgentsMd` (1543-1622): real-filesystem writes into `tmp_path`,
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

_Wiring pass added by `/ll:wire-issue`:_
- No existing test calls `_run_apply()` (`cli.py:853`) or `_apply_config()`
  (`tui.py:819`) directly. `_run_apply()` is exercised indirectly via
  `main_init(["--root", ..., "apply", "--config", <plan>])` in
  `test_init_core.py` (roughly a dozen `test_apply_*` methods at 1985-2300,
  e.g. `test_apply_writes_claude_md` at 2177); `_run_yes()` via
  `main_init(["--yes", ...])`/`main_init(["--upgrade", ...])` (e.g.
  `test_bare_upgrade_implies_yes_never_launches_wizard` at 2565,
  `test_yes_consumer_path_never_uses_editable_bare_name` at 2583). None of
  these assert on `install_source` propagating into the generated
  CLAUDE.md/AGENTS.md Install line. A new test is needed to prove
  `install_source` actually reaches the writer calls through the apply and
  TUI paths, not just through `_run_yes()` [Agent 3 finding].
- **Test isolation for the new unconditional `detect_installation()` call
  in `_run_apply()`.** None of the existing `test_apply_*` tests mock
  `detect_installation` (the file patches it in ~30 places, all in
  `--yes`/`--upgrade`/auto-install tests; none of the `test_apply_*` methods
  at 1985, 2016, 2150, 2177, 2200, 2227, 2255, 2284 do). Option A adds a
  `pip show` subprocess to each of them, and a `claude plugin list` probe
  with a 10s timeout wherever the package is not importable. Lowest-churn
  fix: extend the file's autouse `_default_plugin_installed` fixture
  (`test_init_core.py:75`) with a second `monkeypatch.setattr` stubbing
  `little_loops.init.install_check.detect_installation` to return
  `("pypi", "1.0.0", None)`. Explicit `with patch(...)` blocks in other tests
  still win for their duration, so no existing test changes behavior.

### Documentation
- `docs/reference/CONFIGURATION.md:273-285` — documents the
  `install_source` enum and values; may want a note that the generated
  Install line now varies by source.
- `docs/reference/API.md:11168` — `detect_installation()` signature
  reference.

### Configuration
- N/A — no config schema changes; `install_source` enum already exists.

### Out of Scope: already-generated files
All three writers return `False` without touching the file when
`_CLAUDE_MD_SECTION_MARKER` (`"## little-loops"`, `writers.py:156`) is
already present, and nothing in `--upgrade`, `apply`, or `skills/update`
refreshes the block. Every consumer that ran `ll-init` before this fix
therefore keeps the wrong `Install:` line; re-running `ll-init` will not
correct it. This issue does **not** add an in-place rewrite of the line.
That is filed as ENH-3382 (refresh the `Install:` line of an existing
`## little-loops CLI Commands` block on `--upgrade`), which depends on this
issue.

## Program Design

### Types
N/A — no new data types introduced; the change threads an existing
`str | None` value already returned by `detect_installation()`.

### Signatures
- `_editable_install_location() -> str | None` (`install_check.py:42`) —
  renamed from `_is_editable_install() -> bool`; returns the parsed
  `Editable project location:` value or `None`. One `pip show` probe, one
  parser; no sibling helper.
- `detect_installation(project_root: Path) -> tuple[str | None, str | None, str | None]`
  (`install_check.py:59`) — signature unchanged; the third element
  (`install_path`) becomes the parsed `Editable project location:` for
  `local-editable` installs instead of always `None` for pip installs.
- `_render_commands_block(desc_overrides: dict[str, str] | None = None,
  install_source: str | None = None, install_path: str | None = None,
  project_root: Path | None = None) -> str`
  (`writers.py:242`) — currently module-import-time only; moves to per-call
  invocation and emits the `Install:` line per the Expected Behavior table.
  `project_root` is needed to relativize `install_path`; alternatively the
  writers pre-compute the relative string and pass it as `install_path`.
- `write_claude_md(project_root: Path, dry_run: bool = False,
  install_source: str | None = None, install_path: str | None = None) -> bool`
  (`writers.py:567`).
- `write_agents_md(project_root: Path, dry_run: bool = False,
  install_source: str | None = None, install_path: str | None = None) -> bool`
  (`writers.py:618`) — same.
- `write_gemini_md(project_root: Path, dry_run: bool = False,
  install_source: str | None = None, install_path: str | None = None) -> bool`
  (`writers.py:665`) — same; keeps rendering the host-generic block (no
  Claude description overrides), as today.
- `_apply_config(config, project_root, ll_dir, config_path, templates_dir,
  plugin_root, hosts, settings_target, force, console,
  claude_md_opt_in=False, existing_config=None, install_source=None,
  install_path=None)` (`tui.py:819`) — threaded from its caller `run_tui()`
  (`tui.py:648-661`), which already holds both as locals (`tui.py:185`,
  currently `_install_path` is discarded).

### Call Path
`detect_installation()` (`install_check.py:59`) -> `install_source` +
`install_path` locals -> `write_claude_md()`/`write_agents_md()`/
`write_gemini_md()` (`writers.py:567`/`618`/`665`) ->
`_render_commands_block(desc_overrides,
install_source, install_path)` (`writers.py:242`) -> rendered `Install:`
line text.

Reachable today: `_run_yes()` (`cli.py:536` -> `cli.py:723`/`728`/`732`). Not yet
reachable, needs new plumbing: `_run_apply()` (`cli.py:940`/`945`/`949`,
`detect_installation()` not called until `cli.py:961`) and the TUI's
`_apply_config()` (`tui.py:896`/`901`/`905`, `install_source` is a `run_tui()`
local at `tui.py:185` not passed into `_apply_config()`).

### Decision Rules
- What text renders per `install_source` value: **resolved** — see the
  table in Expected Behavior. Inputs are the four non-null values
  `detect_installation()` actually returns — `"local-editable"`, `"pypi"`,
  `"global-claude-code"`, `"project-claude-code"` — plus `None`. The only
  branch is `install_source == "local-editable"` (matching the existing
  one-value-vs-else convention at `tui.py:239` and `cli.py:566`); inside it,
  `install_path is not None` selects the path form over the `./scripts[dev]`
  fallback, and the path form is always rendered relative to `project_root`
  via `os.path.relpath` (in-tree yields `./scripts[dev]`; out-of-tree yields
  `../.../scripts[dev]`; absolute only when `relpath` raises `ValueError`).
  Never emit the raw absolute path — it trips `ll-verify-private-refs`. All
  other values, including `None`, render the bare `pip install
  little-loops` (never the `--upgrade` form — see Expected Behavior). The
  line is never omitted.
- Dry-run: no preview requirement. All three writers under `dry_run=True`
  print a one-line `info(...)` and return before rendering anything
  (`writers.py:597-605`), so the `Install:` line never appears in preview
  output. Call `detect_installation()` unconditionally in `_run_apply()` for
  simplicity (one call, deduped against `cli.py:961`), but do **not** write
  a test asserting it runs under `--dry-run` — that would pin an
  unobservable property.
- Path form: resolve both sides before `relpath` —
  `os.path.relpath(Path(install_path).resolve(), project_root.resolve())` —
  see Expected Behavior for why. The in-tree unit test must build the fake
  editable path and `project_root` from the same `tmp_path` so this rule is
  exercised, not bypassed.
- Gap: how `_run_apply()` obtains `install_source` before its writer calls
  at `cli.py:940`/`945`/`949`, given `detect_installation()` isn't invoked until
  `cli.py:961` and `_run_plan()` never populates `config["install_source"]`.
  **Resolved: Option A** — call `detect_installation()` unconditionally
  near the top of `_run_apply()`, deduping against the existing
  `cli.py:961` call (see Proposed Solution's Decision Rationale).

## Implementation Steps

1. `detect_installation()` (`install_check.py:59-92`) returns the parsed
   `Editable project location:` as `install_path` for `local-editable`
   installs (rename `_is_editable_install()` at 42-56 to
   `_editable_install_location() -> str | None`; `detect_installation()`
   tests `is not None`. Do not add a sibling helper). Update the docstring
   at 64-69. `TestDetectInstallation` (`test_init_install.py:50-98`) gains
   an assertion that the editable path is returned; the existing
   `subprocess.run` mocks at `test_init_install.py:70,142` already feed an
   `Editable project location:` line, so they exercise the new return value
   directly.
2. `_render_commands_block()` (`writers.py:242`) accepts
   `install_source: str | None` and `install_path: str | None` and is
   invoked per-call from `write_claude_md()`/`write_agents_md()`/
   `write_gemini_md()` rather than frozen once at module import
   (`writers.py:252`/`256`; the `_NEW_FILE_CONTENT` constants at 258-259
   and 262 move per-call too). The `Install:` line it emits follows the
   Expected Behavior table: the `local-editable` path form is
   `os.path.relpath(Path(install_path).resolve(), project_root.resolve())`
   (so `_render_commands_block()` also needs `project_root`, or the writers
   pre-compute the relative string before calling it), with a `./` prefix
   when the result has no leading `..`.
3. `write_claude_md()` (`writers.py:567`), `write_agents_md()`
   (`writers.py:618`), and `write_gemini_md()` (`writers.py:665`) accept
   `install_source: str | None = None, install_path: str | None = None` and
   pass both through to `_render_commands_block()`.
3a. `_run_yes()` (`cli.py:566-602`): delete the inline `pip show` re-parse
   at 551-566 and use the `_install_path` returned at 536 (rename from
   `_install_path` to `install_path` since it is no longer discarded).
4. Both values reach every production call site of
   `write_claude_md`/`write_agents_md`/`write_gemini_md` (three writer calls
   per site): `_run_yes()` (`cli.py:723`/`728`/`732`, via `cli.py:536` — stop
   discarding `_install_path`); `_run_apply()` (`cli.py:940`/`945`/`949`, via
   an unconditional `detect_installation()` call near the top, deduped
   against `cli.py:961`); `_apply_config()` (`tui.py:896`/`901`/`905`, via
   new parameters threaded from `run_tui()`'s `tui.py:185` locals).
5. Extend the autouse `_default_plugin_installed` fixture
   (`test_init_core.py:75`) to also stub `detect_installation` (see
   Integration Map -> Tests) so the new unconditional call in `_run_apply()`
   does not spawn live `pip show`/`claude plugin list` subprocesses in the
   `test_apply_*` tests (`test_init_core.py:1985-2300`).
6. `TestWriteClaudeMd`/`TestWriteAgentsMd`
   (`scripts/tests/test_init_core.py:1445-1622`) gain one test method per
   row of the Expected Behavior table (`local-editable` with in-tree path
   -> exactly `./scripts[dev]`, `local-editable` with out-of-tree path ->
   `..`-relative and containing no `/Users/`/`/home/` segment,
   `local-editable` without path, `pypi` -> exactly
   `pip install little-loops`, a `*-claude-code` value, `None`),
   following this file's one-test-method-per-value convention (see
   `TestDetectInstallation` in `test_init_install.py` for the precedent),
   plus a negative assertion that no non-source-repo row emits
   `./scripts[dev]` and that no row emits `--upgrade`. `TestWriteGeminiMd`
   (`test_init_core.py:1625`) needs only the `pypi` row and the in-tree
   `local-editable` row, since it shares `write_agents_md`'s block. Note:
   no existing test asserts on the `Install:` line at all, so nothing pins
   today's output until these land.
7. `python -m pytest scripts/tests/test_init_core.py
   scripts/tests/test_init_install.py scripts/tests/test_init_tui.py -v`
   passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a test exercising `_run_apply()` (`cli.py:940`/`945`/`949`) that asserts a
  non-`local-editable` `install_source` reaches the generated CLAUDE.md/
  AGENTS.md Install line — no existing test calls `_run_apply()` directly.
- Add a test exercising `_apply_config()` (`tui.py:896`/`901`/`905`) that asserts
  the same for the TUI apply path — no existing test calls `_apply_config()`
  directly.
- ~~Add a test exercising `_run_apply()` with `--dry-run` proving detection
  still runs~~ — dropped at pre-implementation review (2026-09-03): dry-run
  writers emit only an `info(...)` line, so there is no observable
  preview text to match (see Decision Rules).

## Impact

- **Priority**: P3 - Visible defect in every generated CLAUDE.md/AGENTS.md
  outside the source repo, but the wrong line is documentation, not
  executed code; no runtime behavior breaks.
- **Effort**: Small - Four files, additive keyword parameters, one helper
  refactor in `install_check.py`, and test fixtures; no schema or config
  changes.
- **Risk**: Low - New parameters default to `None`, and the in-tree relpath
  rule keeps the source repo's rendered line byte-identical to today; the
  only behavioral risk is the added subprocess in `_run_apply()`, mitigated
  by test patching (step 5).
- **Breaking Change**: No - Existing files are untouched (idempotency
  marker); only newly generated blocks change.

## Root Cause

`scripts/little_loops/init/writers.py:247`, inside `_render_commands_block()`:

```python
lines.extend(["", 'Install: `pip install -e "./scripts[dev]"`', ""])
```

This runs once at module import time to build module-level constants
`_CLAUDE_MD_COMMANDS_BLOCK` (line 252) and `_AGENTS_MD_COMMANDS_BLOCK` (line
256; `_GEMINI_MD_NEW_FILE_CONTENT` at line 262 reuses the latter for
`write_gemini_md()`), which `write_claude_md()`, `write_agents_md()`, and
`write_gemini_md()` then append verbatim. None of the three writer functions
accepts an `install_source` parameter, so the string never varies per
project.

`install_source` is already computed at one of the three call sites and
merely not passed through; at the other two it is not in scope at all (see
Codebase Research Findings below for the correction to the original claim):

- `scripts/little_loops/init/cli.py:536` (`_run_yes()`,
  `detect_installation(...)`) — in scope before the writer calls at
  `cli.py:723` / `cli.py:728` / `cli.py:732`; `_install_path` is discarded.
- `scripts/little_loops/init/cli.py:853-970` (`_run_apply()`) — **not** in
  scope at the writer calls `cli.py:940` / `cli.py:945` / `cli.py:949`;
  `detect_installation()` runs only at `cli.py:961`, after them, gated on
  `requested_upgrade`.
- `scripts/little_loops/init/tui.py:185` (`run_tui()`) — detected here but
  **not** passed into `_apply_config()` (`tui.py:819`), where the writer
  calls at `tui.py:896` / `tui.py:901` / `tui.py:905` live.

Precedent for branching writer/CLI behavior on `install_source` already
exists at `cli.py:263` (`== "project-claude-code"`) and `cli.py:566`
(`== "local-editable"`).

`config-schema.json:2062-2066` defines the `install_source` enum:
`local-editable`, `pypi`, `global-claude-code`, `project-claude-code`,
`global-codex`, `global-pi`, or `null`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- `_render_commands_block()` is invoked exactly twice, both at **module import time**, not per-call: `_CLAUDE_MD_COMMANDS_BLOCK = _render_commands_block(_CLAUDE_MD_DESC_OVERRIDES)` (`writers.py:252`) and `_AGENTS_MD_COMMANDS_BLOCK = _render_commands_block()` (`writers.py:256`), which also freeze `_CLAUDE_MD_NEW_FILE_CONTENT`/`_AGENTS_MD_NEW_FILE_CONTENT` (`writers.py:258-259`). `write_claude_md()` (`writers.py:600,607`) and `write_agents_md()` (`writers.py:653,660`) — and, since FEAT-2190, `write_gemini_md()` (`writers.py:690,696`) — only reference these pre-frozen constants — neither calls `_render_commands_block()` itself. Adding an `install_source` parameter to the outer `write_*` functions alone is not sufficient; `_render_commands_block()`'s invocation must move out of module scope into a per-call site inside `write_claude_md`/`write_agents_md`.
- `install_source` is **not** in scope at `cli.py:940`/`945`/`949` (inside `_run_apply()`, def at `cli.py:853`): `detect_installation()` is imported at `cli.py:872` but not called until `cli.py:961`, gated behind `if plan.get("requested_upgrade") and not dry_run:` (`cli.py:960`) — which runs *after* both writer calls. `_run_plan()` (`cli.py:764-850`) also never populates `config["install_source"]`, so there is no config-based fallback either. This contradicts this issue's own claim above that install_source is "already computed and in scope at every call site" — that claim holds for `_run_yes()` (`cli.py:536` -> `cli.py:723/728/732`) but not for `_run_apply()`.
- `tui.py:896`/`901`/`905` are inside `_apply_config()` (def at `tui.py:819`), a *different* function from `run_tui()` (def at `tui.py:128`) where `install_source` is actually detected (`tui.py:185`). `_apply_config()`'s signature (`tui.py:819-832`) has no `install_source` parameter, and its call site inside `run_tui()` (`tui.py:648-661`) does not pass the local `install_source` through.
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
  little-loops — `pip install little-loops` for `pypi`/plugin/`None`, and
  `pip install -e "<relative-editable-path>[dev]"` for `local-editable`
  consumers whose checkout lives outside the project (see the table in
  Expected Behavior).
- **Actual**: every generated AGENTS.md/CLAUDE.md gets the same
  source-repo-only editable-dev-install command.

## Suggested Fix

Thread `install_source: str | None` and `install_path: str | None` into
`_render_commands_block()` and into `write_claude_md()` /
`write_agents_md()`; render the `Install:` line per the Expected Behavior
table (`local-editable` is the only branch; the editable path rendered
relative to `project_root` when known, `./scripts[dev]` as fallback;
`pip install little-loops` for everything else, never omitted). Update the
three call sites above to pass the detected values through instead of
leaving them unused, and drop the duplicate `pip show` re-parse in
`_run_yes()`. See Proposed Solution for the editable-path resolution and
`_run_apply()` plumbing.

## Related

- ENH-3382 — refresh the `Install:` line inside an existing
  `## little-loops CLI Commands` block on `--upgrade` (see Integration Map ->
  Out of Scope). Depends on this issue.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-02, reconfirmed 2026-09-02, 2026-09-03_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- Change touches 4 files across 3 modules (`writers.py`, `cli.py`, `tui.py`, `install_check.py`) with a control-flow edit in `_run_apply()` (moving/deduping the `detect_installation()` call) rather than a purely mechanical substitution — expect some iteration reconciling the dedup against the existing `cli.py:961` call.
- `unapplied_decision` gap flagged in Program Design / Proposed Solution / Implementation Steps / Files to Modify: rejected-option (Option B) identifiers (`config["install_source"]`, `_run_plan()`, and several shared terms like `detect_installation()`, `local-editable`) still appear unmarked in directive sections alongside the selected Option A text. Likely a false positive of the phrase-based checker picking up vocabulary shared between the contrasted options rather than a true unresolved decision, but caps Criterion C at 10 per rubric — worth a quick scan to confirm no stray Option-B-only guidance survived in a directive section before implementing.
- No existing test calls `_run_apply()` or `_apply_config()` directly (writers.py and install_check.py are well-covered; the two new call sites are not) — the issue's own Wiring Phase already schedules the tests needed to close this gap.
- **Reconfirm note**: this run's `ll-issues set-flags` matched the same `unapplied_decision` phrase-hits and flipped `decision_needed` back to `true`, even though the issue already records an explicit `> **Selected:** Option A` decision. Treat this as the same checker false positive above, not a real open decision — clear it via `/ll:decide-issue` rather than hand-editing frontmatter.

_(no Concerns or Gaps to Address — readiness scored 100/100)_

## Pre-Implementation Review

_2026-09-03, manual review against `main` at 2072fd19b:_

- Added `write_gemini_md()` (FEAT-2190, landed after refinement) to scope:
  Files to Modify, Signatures, Call Path, Steps 2-4, Step 6.
- Dropped the dry-run preview rule and its wiring test — dry-run writers
  render nothing observable.
- Added `.resolve()` on both sides before `relpath` (symlinked tmp dirs,
  unresolved `--root`).
- Pinned the `_is_editable_install()` refactor shape to a rename returning
  `str | None`.
- Made the out-of-tree relative path's machine-specificity an explicit,
  accepted property.
- Switched the test-isolation plan to extending the autouse fixture.
- Re-anchored every `cli.py`/`writers.py`/test line citation to current
  `main` (all had drifted 3-21 lines after FEAT-2190).
- Filed ENH-3382 for the existing-block refresh follow-up.

## Status

**Open** | Created: 2026-09-02 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-09-03T01:57:52 - `56e97453-f956-4b60-af83-bfa4c915222f.jsonl`
- `/ll:confidence-check` - 2026-09-03T01:56:02 - `9c75187e-0701-4291-a5b8-2150f3aee90d.jsonl`
- `/ll:decide-issue` - 2026-09-03T01:38:39 - `7596ad35-9667-4e93-a03c-f4eae524bb56.jsonl`
- `/ll:confidence-check` - 2026-09-03T01:35:55 - `3a18fe40-927e-4b43-a24c-0a175dcd41ed.jsonl`
- `/ll:confidence-check` - 2026-09-03T00:24:19 - `f2d59b82-c760-49ab-831c-620b7014291e.jsonl`
- `/ll:confidence-check` - 2026-09-03T00:05:53 - `4bf97e41-6b03-4e8d-9104-4e84d288cd4b.jsonl`
- `/ll:wire-issue` - 2026-09-02T23:07:19 - `5cfbabad-da25-40ab-bfb7-6d0233f02bb3.jsonl`
- `/ll:decide-issue` - 2026-09-02T22:37:14 - `bea601b2-a6af-4ef3-8359-e10eab8b1a54.jsonl`
- `/ll:refine-issue` - 2026-09-02T22:29:09 - `25d94b5b-402d-469f-a07b-24795969ce49.jsonl`
- `/ll:capture-issue` - 2026-09-02T22:19:45 - `64850b61-eea3-464a-8dc5-33dc204c7fce.jsonl`
