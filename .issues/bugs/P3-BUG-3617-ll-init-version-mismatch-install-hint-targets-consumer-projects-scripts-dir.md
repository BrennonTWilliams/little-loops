---
id: BUG-3617
type: BUG
title: ll-init version-mismatch install hint targets consumer project's scripts/ dir
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T22:48:52Z'
---

# BUG-3617: ll-init version-mismatch install hint targets consumer project's scripts/ dir

## Summary

`ll-init`'s little-loops version check suggests a fix command that doesn't work. In a consumer project that happens to have its own `scripts/` directory, the hint tells the user to `pip install -e '<consumer>/scripts'`, which is a non-package directory, so pip errors out. The same heuristic also uses bare `pip`, which may be a different interpreter from the one running `ll-*`.

## Current Behavior

Running `ll-init` in a consumer project with its own `scripts/` directory (holding unrelated eval/training code, not a Python package) printed:

```
Warning: little-loops version mismatch: installed '1.163.0', plugin expects '1.165.0'.
  Install/fix: pip install -e '<consumer-project-path>/scripts'
```

Running the suggested command failed:

```
ERROR: file://<consumer-project-path>/scripts does not appear to be a Python project: neither 'setup.py' nor 'pyproject.toml' found.
```

The pip notice from that run also showed bare `pip` resolving to one interpreter (e.g., pyenv 3.11), while `ll-init`'s shebang pointed to a different one (e.g., miniforge 3.12). So even a correct path would have installed into the wrong interpreter.

## Expected Behavior

The hint should target the real little-loops source and the interpreter that runs `ll-*`. For example:

```
<python-interpreter> -m pip install -e '<little-loops-source>/scripts'
```

For editable installs the message should also say the code is already live and only the recorded version metadata is stale (it goes stale whenever `plugin.json` is bumped without re-running `pip install -e`).

## Motivation

A remediation hint that errors when you run it is worse than no hint. Every local-editable consumer project on this machine hits the version-skew warning after each `plugin.json` bump. Any of them with a `scripts/` folder gets a broken command, and following it wastes time and suggests the install itself is broken.

## Proposed Solution

In `_check_little_loops_version()`:

1. Read `direct_url.json` from the installed distribution. If `dir_info.editable` is true and `url` is a `file://` URL, hint `"{sys.executable}" -m pip install -e '<that path>'`, and word the message to say the code is live and only the metadata is stale.
2. Otherwise (PyPI or unreadable metadata), hint `"{sys.executable}" -m pip install --upgrade little-loops`.
3. For the not-installed branch, drop the `project_root / "scripts"` guess. Only suggest an editable path when the `pyproject.toml` inside `project_root`'s `scripts/` dir exists *and* declares `name = "little-loops"`; otherwise use `"{sys.executable}" -m pip install little-loops`.

Related but separate: `scripts/little_loops/init/tui.py` prints a placeholder `pip install -e <editable-path>[dev]` for outdated local-editable installs. That could reuse the same resolver.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/validate.py` — `_check_little_loops_version()` (both hint branches)
- `scripts/little_loops/init/tui.py` — optional: outdated local-editable placeholder hint

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/validate.py` — the dependency-check aggregator calls `_check_little_loops_version(plugin_version, project_root)`
- `scripts/little_loops/init/cli.py` / `init/tui.py` — render `DepWarning.install_hint` as `Install/fix: ...`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/validate.py:validate_deps` — sole caller of `_check_little_loops_version` (gated on `plugin_version is not None and project_root is not None`)
- `scripts/little_loops/init/cli.py:_report_dependency_warnings` — renders `Install/fix: {w.install_hint}` (~line 984); invoked from both init flows via `validate_deps(config, _plugin_version(), project_root)` (~lines 946, 1181); no change needed, string-only hint
- `scripts/little_loops/init/tui.py:1294-1295` — second `Install/fix:` renderer of `DepWarning.install_hint`; no change needed
- `scripts/little_loops/init/proposal.py:143,366` — serializes `install_hint` into the proposal dict via `validate_deps`; hint text flows through unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/tui.py:777` — hardcoded placeholder `pip install -e <editable-path>[dev]` in the `pkg_outdated` / `local-editable` branch (`install_source` already available there); folds into the optional reuse step
- `scripts/little_loops/init/install_check.py:_editable_install_location()` — **existing resolver** returning the `Editable project location:` from `pip show` (via `sys.executable -m pip`); `detect_installation()` already uses it. Prefer reusing/sharing this over adding a second `direct_url.json` parser, or, if `direct_url.json` is used, keep it spawn-free (see spawn guard below)

### Similar Patterns
- `scripts/little_loops/init/cli.py` `--upgrade` path already uses `sys.executable -m pip` for local-editable installs
- `scripts/little_loops/init/writers.py` renders an editable install command from a resolved `install_path`

### Tests
- `scripts/tests/test_init_core.py` — `test_warns_when_package_not_installed`, `test_warns_on_version_mismatch`, `test_silent_on_version_match`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py:test_warns_on_version_mismatch` / `test_warns_when_package_not_installed` — patch only `importlib.metadata.version` and assert only message text; they will not break, but with an unpatched resolver they would read the real dev-machine editable install — patch the new helper in every version-check test for hermeticity
- `scripts/tests/test_enh3184_spawn_site_guard.py` — `_TASK_PATH_MODULES` budgets `init/install_check.py` at `(5, 5)` spawn sites and does not list `init/validate.py`; adding a `subprocess.run` (e.g. `pip show`) in either module without an `ll-no-project:` marker / budget bump trips this guard. A `direct_url.json` read via `importlib.metadata` avoids it
- `scripts/tests/test_init_install.py` — covers `detect_installation` / `_editable_install_location`; update if the resolver is shared or refactored
- `scripts/tests/test_init_proposal.py` (~lines 191-194) — patches `detect_installation` / `plugin_installed` around `validate_deps`; verify unaffected

### Documentation
- N/A

### Configuration
- N/A

## Program Design

### Types

- `DepWarning.install_hint: str` — existing field, now built from `sys.executable` and the recorded editable source

### Signatures

- `_editable_source_dir() -> Path | None` — parse `direct_url.json` from the `little-loops` distribution; return the `file://` path when `dir_info.editable` is true, else `None`
- `_check_little_loops_version(plugin_version: str, project_root: Path) -> DepWarning | None` — existing; both hint branches rewritten

### Call Path

`validate_deps` -> `_check_little_loops_version` -> `_editable_source_dir`

## Implementation Steps

1. Add a small helper (e.g. `_editable_source_dir() -> Path | None`) in `init/validate.py` that parses `direct_url.json`.
2. Rewrite both hint branches of `_check_little_loops_version()` to use it plus `sys.executable -m pip`.
3. Optionally reuse the helper in `init/tui.py`'s outdated-package hint.
4. Extend the tests in `scripts/tests/test_init_core.py` (next to `test_warns_on_version_mismatch`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide resolver home: reuse `init/install_check.py:_editable_install_location()` (pip-show based, already `sys.executable`-correct) vs. a new spawn-free `direct_url.json` helper; avoid a duplicate parser
- Keep `scripts/tests/test_enh3184_spawn_site_guard.py` green — no new unmarked `subprocess` spawn in `init/validate.py`; if reusing the pip-show resolver, import it rather than re-spawning
- Update `scripts/little_loops/init/tui.py:777` — replace `<editable-path>` placeholder with the resolved path (and `sys.executable -m pip`)
- Patch the resolver in the existing `test_init_core.py` version-check tests so they don't read the host's real install metadata
- No doc changes: no `docs/`, `skills/`, or `commands/` file quotes the version-mismatch hint text

## Impact

- **Priority**: P3 — cosmetic-but-misleading. The warning is correct, the remedy is wrong, and a user following it hits a hard pip error.
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Root Cause

- **File**: `scripts/little_loops/init/validate.py`
- **Anchor**: `_check_little_loops_version()`
- **Cause**: Both branches (package-not-installed, lines ~94-99, and version-mismatch, lines ~105-111) build the hint from `project_root / "scripts"` whenever that directory exists. That assumes the project being initialized *is* the little-loops source repo, which only holds when running `ll-init` inside little-loops itself. It also hardcodes bare `pip` instead of `sys.executable -m pip`.

The installed distribution already records the true source. `importlib.metadata.distribution("little-loops").read_text("direct_url.json")` returns `{"dir_info": {"editable": true}, "url": "file://<little-loops-source>/scripts"}` for editable installs.

## Steps to Reproduce

1. Have little-loops installed editable from its source checkout.
2. Bump `.claude-plugin/plugin.json` version without re-running `pip install -e` (or otherwise create a version skew).
3. Run `ll-init` in a different project that has a `scripts/` directory with no `pyproject.toml`/`setup.py`.
4. Observe: the hint points at `<project>/scripts`; running it fails.

## Acceptance Criteria

- A consumer project with a non-package `scripts/` dir gets a hint pointing at the editable source from `direct_url.json`, not at `<project>/scripts`.
- Hints use `sys.executable -m pip`, not bare `pip`.
- A PyPI (non-editable) install gets a `--upgrade little-loops` hint.
- Running `ll-init` inside the little-loops source repo still yields a correct editable hint.

## Tests

Add to `scripts/tests/test_init_core.py`:
- Mismatch plus editable `direct_url.json` plus unrelated `tmp_path/scripts/` → hint contains the direct_url path and `sys.executable`, not `tmp_path/scripts`.
- Mismatch plus non-editable dist → `--upgrade little-loops` hint.
- Not-installed plus `tmp_path/scripts/` with no pyproject → PyPI install hint.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-init`, `install`

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-26T23:05:55 - `6cddab98-ff74-4434-89de-e1aeb0e2c3bb.jsonl`
- `/ll:refine-issue` - 2026-09-26T22:52:32 - `242c13c2-daff-4514-b4c7-3c6299f5c0af.jsonl`
- `/ll:format-issue` - 2026-09-26T22:51:44 - `2d14fe2c-428f-4be0-80df-471f93ad0e5d.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:48:59 - `58016881-a136-4f55-8da0-640ef93df277.jsonl`
