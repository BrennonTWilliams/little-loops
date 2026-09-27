---
id: BUG-3617
type: BUG
title: ll-init version-mismatch install hint targets consumer project's scripts/ dir
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T22:48:52Z'
confidence_score: 85
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

1. Read `direct_url.json` from the installed distribution. If `dir_info.editable` is true and `url` is a `file://` URL, decode it with `urllib.request.url2pathname(urllib.parse.urlparse(url).path)` (URLs are percent-encoded: a space is `%20`; never string-strip `file://`). Hint `<python> -m pip install -e <that path>`, and word the message to say the code is live and only the metadata is stale.
2. Otherwise (PyPI, non-editable, or unreadable metadata), hint `<python> -m pip install --upgrade little-loops`.
3. For the not-installed branch, drop the `project_root / "scripts"` guess entirely and always hint `<python> -m pip install little-loops`. This branch is nearly unreachable, because `ll-init` runs from the installed package and so `importlib.metadata.version()` succeeds. It does not justify parsing `pyproject.toml`.
4. Build every hint with `shlex.quote()` on both the interpreter (`sys.executable`) and the path. Do not hand-write mixed `"..."`/`'...'` quoting, which breaks on a path containing `'`.
5. `_check_pyyaml()` has the same wrong-interpreter bug (`install_hint="pip install pyyaml"`, `validate.py:81`). Fold it in: `<python> -m pip install pyyaml`, built with the same `shlex.quote(sys.executable)`.
6. `scripts/little_loops/init/tui.py:777` prints a placeholder `pip install -e <editable-path>[dev]` for outdated local-editable installs. Replace it with the real path and interpreter. The path is already computed: `run_tui` gets `install_path` from `detect_installation()` (`tui.py:879`), so pass it into `_render_install_status()` (call site `tui.py:891`). No second resolver call is needed there.

### Decisions

- **Resolver home**: a new spawn-free `_editable_source_dir()` in `init/validate.py` that reads `direct_url.json` via `importlib.metadata`. Do **not** route through `install_check.py:_editable_install_location()`: it spawns `pip show` (about 1s per `ll-init`) and would need a spawn-guard marker in `validate.py`. The TUI reuses the `install_path` that `detect_installation()` already computed.
- **`[dev]` extra**: the `validate.py` stale-metadata hint omits `[dev]`, since it only needs to refresh version metadata. The `tui.py` "Upgrade:" hint keeps `[dev]` so it matches what `ll-init --upgrade` actually runs (`cli.py:~811`, `-e {install_path}[dev]`).
- **Non-PyPI, non-editable installs** (VCS or local-path, where `direct_url.json` exists without `dir_info.editable`): these get the `--upgrade little-loops` hint, which would move the user to PyPI. This is accepted, because such installs are rare and the hint is advisory.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/validate.py` — `_check_little_loops_version()` (both hint branches), new `_editable_source_dir()`, `_check_pyyaml()` hint
- `scripts/little_loops/init/tui.py` — `_render_install_status()` gains an `install_path` kwarg, the placeholder hint at line 777 is replaced, and the call site at line 891 passes `install_path`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/validate.py` — the dependency-check aggregator calls `_check_little_loops_version(plugin_version, project_root)`
- `scripts/little_loops/init/cli.py` / `init/tui.py` — render `DepWarning.install_hint` as `Install/fix: ...`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/validate.py:validate_deps` — sole caller of `_check_little_loops_version` (gated on `plugin_version is not None and project_root is not None`)
- `scripts/little_loops/init/cli.py:_report_dependency_warnings` — renders `Install/fix: {w.install_hint}` (~line 984); invoked from both init flows via `validate_deps(config, _plugin_version(), project_root)` (~lines 946, 1181); no change needed, string-only hint
- `scripts/little_loops/init/tui.py:1294-1295` — second `Install/fix:` renderer of `DepWarning.install_hint`; no change needed
- `scripts/little_loops/init/proposal.py:143,366` — serializes `install_hint` into the proposal dict via `validate_deps`; hint text flows through unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/tui.py:777` — hardcoded placeholder `pip install -e <editable-path>[dev]` in the `pkg_outdated` / `local-editable` branch. `_render_install_status()` (`tui.py:713`) receives `install_source` but **not** `install_path`. Pass it in from the caller at `tui.py:891`, which already has it from `detect_installation()` at `tui.py:879`
- `scripts/little_loops/init/install_check.py:_editable_install_location()` — existing `pip show`-based resolver, which spawns a subprocess. It is **not** reused by `validate.py` (see Decisions). It still feeds `install_path` to the TUI through `detect_installation()`. Unchanged.

### Similar Patterns
- `scripts/little_loops/init/cli.py` `--upgrade` path already uses `sys.executable -m pip` for local-editable installs
- `scripts/little_loops/init/writers.py` renders an editable install command from a resolved `install_path`

### Tests
- `scripts/tests/test_init_core.py` — `test_warns_when_package_not_installed`, `test_warns_on_version_mismatch`, `test_silent_on_version_match`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py:test_warns_on_version_mismatch` / `test_warns_when_package_not_installed` / `test_silent_on_version_match` — these patch only `importlib.metadata.version` and assert only message text. They will not break, but with an unpatched resolver they would read the real dev-machine editable install. Patch `_editable_source_dir` in **all three** so they are hermetic
- `scripts/tests/test_init_core.py:test_warns_when_pyyaml_missing` — asserts `w.install_hint == "pip install pyyaml"`. Update it to the `sys.executable -m pip` form
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

- `_editable_source_dir() -> Path | None` — parse `direct_url.json` from the `little-loops` distribution. Return the decoded `file://` path (`url2pathname(urlparse(url).path)`) when `dir_info.editable` is true. Return `None` otherwise, including when metadata is missing or malformed (`PackageNotFoundError`, `None` from `read_text`, `json.JSONDecodeError`, non-`file` scheme)
- `_check_little_loops_version(plugin_version: str, project_root: Path) -> DepWarning | None` — existing; both hint branches rewritten. `project_root` is no longer used for hint resolution
- `_render_install_status(console, *, install_source, installed_version, install_path: str | None, selected_hosts, project_root) -> bool | None` — existing (`tui.py:713`); gains the `install_path` kwarg

### Call Path

`validate_deps` -> `_check_little_loops_version` -> `_editable_source_dir`

`run_tui` -> `detect_installation` (existing, provides `install_path`) -> `_render_install_status`

## Implementation Steps

1. Add `_editable_source_dir() -> Path | None` in `init/validate.py`. It is spawn-free and reads `direct_url.json` via `importlib.metadata.distribution("little-loops").read_text(...)`.
2. Rewrite both hint branches of `_check_little_loops_version()`:
   - mismatch plus an editable source: `<python> -m pip install -e <src>`, with a message saying the code is live and only the metadata is stale
   - mismatch without one: `--upgrade little-loops`
   - not installed: `<python> -m pip install little-loops`

   Quote everything with `shlex.quote`.
3. Change the `_check_pyyaml()` hint to `<python> -m pip install pyyaml`.
4. In `init/tui.py`, add an `install_path` kwarg to `_render_install_status()` and pass it from `run_tui` (`tui.py:891`). Replace the `<editable-path>` placeholder with `<python> -m pip install -e <install_path>[dev]`. When `install_path` is `None`, fall back to the current placeholder text.
5. Update and extend `scripts/tests/test_init_core.py`, as described in the Tests section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolver home is decided: a spawn-free `_editable_source_dir()` in `validate.py` (see Decisions)
- Keep `scripts/tests/test_enh3184_spawn_site_guard.py` green. The `direct_url.json` read adds no `subprocess` spawn
- Update `scripts/little_loops/init/tui.py:777` (required): pass `install_path` into `_render_install_status()` and replace the placeholder
- Patch `_editable_source_dir` in all existing `test_init_core.py` version-check tests so they don't read the host's real install metadata
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
- Hints use `sys.executable -m pip`, not bare `pip`. This includes the `_check_pyyaml()` hint.
- A PyPI (non-editable) install gets a `--upgrade little-loops` hint.
- Running `ll-init` inside the little-loops source repo still yields a correct editable hint.
- Percent-encoded `direct_url.json` paths (for example, one containing a space) decode to the real filesystem path, and the path is shell-quoted in the hint.
- The TUI's outdated local-editable "Upgrade:" hint shows the real `install_path` and `sys.executable`, not `<editable-path>`.

## Tests

Update in `scripts/tests/test_init_core.py`:
- Patch `_editable_source_dir` in `test_warns_when_package_not_installed`, `test_warns_on_version_mismatch`, and `test_silent_on_version_match`.
- `test_warns_when_pyyaml_missing`: expect `f"{shlex.quote(sys.executable)} -m pip install pyyaml"`.

Add to `scripts/tests/test_init_core.py`:
- Mismatch plus editable `direct_url.json` plus unrelated `tmp_path/scripts/` → hint contains the direct_url path and `sys.executable`, not `tmp_path/scripts`.
- Mismatch plus editable `direct_url.json` pointing at `tmp_path/scripts` (running inside the source repo) → hint targets `tmp_path/scripts`.
- Mismatch plus a `direct_url.json` URL with `%20` → hint contains the decoded path containing a space, shell-quoted.
- Mismatch plus non-editable dist (or no `direct_url.json`) → `--upgrade little-loops` hint.
- Not-installed plus `tmp_path/scripts/` with no pyproject → `<python> -m pip install little-loops` hint.
- `_editable_source_dir()` unit cases: editable `file://` URL → Path; `editable: false` → None; missing file / malformed JSON → None.

Add to the TUI tests (`scripts/tests/test_init_tui.py`):
- `local-editable` plus `pkg_outdated` plus `install_path="/x/scripts"` → the output contains `/x/scripts[dev]` and `sys.executable`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-init`, `install`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- Resolver home is left open: the Wiring Phase says "decide" between reusing `install_check.py:_editable_install_location()` (pip-show, spawns) and a new spawn-free `direct_url.json` helper, while Program Design/Implementation Steps already commit to `_editable_source_dir()` in `validate.py`. Pick one (spawn-free `direct_url.json` avoids the `test_enh3184_spawn_site_guard.py` budget) and drop the other.
- The `tui.py:777` hint change is "optional" in Implementation Steps but listed under "must be included" in the Wiring Phase — clarify scope.
- Existing `test_init_core.py` version-check tests (lines ~2134-2159) must patch the new helper, or they read the host's real editable install.

_All three concerns were resolved in the 2026-09-26 review pass: resolver home is decided (spawn-free `direct_url.json`), `tui.py` is in scope (with the `install_path` threading), and every version-check test patches the helper._


## Session Log
- `/ll:confidence-check` - 2026-09-27T00:18:55 - `68e35fb0-28ac-4604-989f-2d31cfc587a7.jsonl`
- `/ll:wire-issue` - 2026-09-26T23:05:55 - `6cddab98-ff74-4434-89de-e1aeb0e2c3bb.jsonl`
- `/ll:refine-issue` - 2026-09-26T22:52:32 - `242c13c2-daff-4514-b4c7-3c6299f5c0af.jsonl`
- `/ll:format-issue` - 2026-09-26T22:51:44 - `2d14fe2c-428f-4be0-80df-471f93ad0e5d.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:48:59 - `58016881-a136-4f55-8da0-640ef93df277.jsonl`
