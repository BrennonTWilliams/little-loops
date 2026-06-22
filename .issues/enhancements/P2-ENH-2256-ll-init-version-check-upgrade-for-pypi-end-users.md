---
id: ENH-2256
type: ENH
priority: P2
status: done
captured_at: '2026-06-22T18:22:22Z'
completed_at: '2026-06-22T19:58:52Z'
discovered_date: 2026-06-22
discovered_by: capture-issue
relates_to:
- FEAT-892
- BUG-1071
- BUG-364
labels:
- init
- version-check
- pypi
- upgrade
confidence_score: 96
outcome_confidence: 79
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2256: ll-init version-check and upgrade for PyPI end users

## Summary

`ll-init`'s install detection and version-drift logic only works inside the
little-loops **source repo**. For real end users — who install the
`little-loops` package from PyPI via `pip install little-loops` and the
`ll@little-loops` plugin from the Claude Code marketplace — drift is
**undetectable by construction**, and the upgrade command it tries to run
**crashes**. Fix `ll-init` to (a) check the installed pip package against the
latest PyPI release, (b) check the installed `ll@little-loops` plugin against
the latest marketplace version (only when the `claude-code` host is selected),
and (c) notify-and-prompt the user to upgrade rather than silently mutating
their environment or running an invalid command.

## Motivation

This is the primary onboarding path for every external user. Today an end user
running `ll-init` in their own project either gets a hard error during the
auto-install/upgrade step or is silently told their stale install is fine. The
version-drift feature advertised in `.claude/CLAUDE.md` ("detects existing
install and version drift") does not function outside this repo.

## Current Behavior

Two distinct defects in `scripts/little_loops/init/`:

1. **Drift is undetectable for PyPI users — by construction.**
   `check_version(installed, current)` compares:
   - `installed_version` = `importlib.metadata.version("little-loops")` (pip metadata)
   - `current` = `_plugin_version()` = `little_loops.__version__` (the running code's own constant)

   In the source repo these can differ (you bump `__init__.py` before re-running
   `pip install -e`). But for a PyPI install **the installed package *is* the
   running code**, so `installed_version == __version__` *always*. There is no
   external source of truth for "latest," so `InstallStatus.OutOfDate` is never
   reached.

2. **The upgrade command crashes outside the repo.**
   `init/cli.py:159` and `:176` build
   `_install_target = f"{_scripts_dir}[dev]" if _scripts_dir.exists() else "little-loops"`
   but then call `pip install -e _install_target`. When `scripts/` doesn't exist
   (every end-user project), this runs `pip install -e little-loops`, which fails
   because `-e` requires a path or VCS URL, not a bare package name.

   Additionally, `detect_installation` returns `(global-claude-code, None)` for
   plugin-only installs, so `check_version` is never even reached for the plugin
   surface — a stale global plugin is silently treated as current.

## Root Cause

- **File**: `scripts/little_loops/init/install_check.py`
  - `check_version()` compares installed-vs-own-code instead of
    installed-vs-external-latest.
  - `detect_installation()` returns `version=None` for the
    `global-claude-code` source, defeating any plugin drift check.
- **File**: `scripts/little_loops/init/cli.py` (≈ lines 154–183)
  - `pip install -e <bare-package-name>` path for the non-source-repo case.
- **File**: `scripts/little_loops/init/tui.py` (≈ lines 163–204)
  - Same dev-repo assumption in the interactive "Plugin Install" screen.

## Expected Behavior

`ll-init` performs **two independent version checks**, both **notify-and-prompt**
(never silent mutation), both via **subprocess** (respecting the user's
configured index/mirror and existing `claude` auth):

1. **Python package (`little-loops` from PyPI)**
   - Installed: `importlib.metadata.version("little-loops")`.
   - Latest: parse the `LATEST:` line from `pip index versions little-loops`,
     with a timeout and offline fallback (on failure, skip the check silently —
     do not block init).
   - On drift: report `installed X → latest Y`, prompt; on confirm run
     `pip install --upgrade little-loops`.

2. **Claude Code plugin (`ll@little-loops`)** — *only when the `claude-code`
   host is selected*
   - Installed: read `.version` for `ll@little-loops` from
     `claude plugin list --json` (closes today's `None` gap).
   - Latest: `claude plugin list --available --json` after
     `claude plugin marketplace update little-loops`.
   - On drift: report, prompt; on confirm run
     `claude plugin marketplace update little-loops && claude plugin update ll@little-loops`.

The **source-repo editable case** becomes one explicit branch: only use
`pip install -e ./scripts[dev]` when `scripts/` exists; the `-e <bare-name>`
crash path is removed. Headless mode notifies-and-acts **only behind an explicit
`--upgrade` flag**, otherwise warns; the TUI keeps its existing prompt.

## Implementation Steps

1. Add `fetch_latest_pypi()` to `install_check.py` — subprocess
   `pip index versions little-loops`, parse `LATEST:`, timeout + offline-safe
   (return `None` on any failure).
2. Add `fetch_latest_plugin()` — `claude plugin marketplace update little-loops`
   then `claude plugin list --available --json`, extract the `ll@little-loops`
   available version; offline-safe.
3. Extend `detect_installation()` to populate the plugin version from
   `claude plugin list --json` for the `global-claude-code` source.
4. Rework `check_version()` — **decided (ARCHITECTURE-044):** change signature
   to `check_version(installed: str, latest: str) -> InstallStatus`, comparing
   installed vs external latest (not `__version__`). No sibling/zombie function;
   the 3 existing `TestCheckVersion` tests must be rewritten to pass a realistic
   `latest` string.
5. In `cli.py`: split the editable (`scripts/` exists → `pip install -e
   ./scripts[dev]`) branch from the consumer branch (`pip install --upgrade
   little-loops`); gate any auto-action behind `--upgrade`; otherwise print a
   warning with the exact command.
6. In `tui.py`: drive the "Plugin Install" screen from the new per-surface
   checks; prompt per surface; only show the plugin check when `claude-code`
   is among the selected hosts.
7. Tests in `scripts/tests/test_init_install.py`: mock subprocess for both
   surfaces (up-to-date, behind, offline/timeout) and assert no `-e <bare-name>`
   invocation is ever constructed for the consumer path.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/init/__init__.py` — add `fetch_latest_pypi` and `fetch_latest_plugin` to the import line from `install_check` and to `__all__`; keeping the public API surface consistent with the new functions
9. Update `scripts/tests/test_init_install.py` (`TestCheckVersion`) — adapt all 3 existing tests for the new `check_version()` semantics; add `TestFetchLatestPypi` and `TestFetchLatestPlugin` test classes
10. Update `scripts/tests/test_init_install.py` (`TestDetectInstallation.test_global_claude_code_installation_detected`) — change assertion from `version is None` to assert populated version string from `claude plugin list --json`
11. Update `scripts/tests/test_init_core.py` (`TestMainInit`) — add tests for `--upgrade` flag (auto-acts), warn-only default headless mode, and consumer-path negative assertion (`pip install -e <bare-name>` never constructed)
12. Review `scripts/tests/test_init_tui.py` (`mock_detect_installation` fixture) — determine if the TUI plugin-check screen needs richer mock for new per-surface behavior tests
13. Update `docs/guides/GETTING_STARTED.md` — add `--upgrade` row to flag table (lines 88–96); revise "Existing Installation Detection" section (lines 112–125) to describe new notify-and-prompt / warn-only semantics
14. Update `skills/init/SKILL.md` (line 46) — add `$UPGRADE_FLAG` variable to the `ll-init` invocation template

## Integration Map

### Files to Modify
- `scripts/little_loops/init/install_check.py` — add `fetch_latest_pypi()`, `fetch_latest_plugin()`, extend `detect_installation()` to populate plugin version from `claude plugin list --json`
- `scripts/little_loops/init/cli.py` (≈ lines 154–183) — split editable (`scripts/` exists) vs consumer (`pip install --upgrade little-loops`) install paths; add `--upgrade` headless flag
- `scripts/little_loops/init/tui.py` (≈ lines 163–204) — drive "Plugin Install" screen from per-surface checks; show plugin check only when `claude-code` is a selected host
- `config-schema.json` — add `"pypi"` to the `install_source` enum (ARCHITECTURE-043: `detect_installation()` now returns `"pypi"` for non-editable pip installs)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/init/validate.py` — **review only (likely no changes needed)**: `_check_little_loops_version()` line 88 stores `install_hint = "pip install --upgrade little-loops"` as display text; verify this function's version-presence check does not conflict with the reworked `detect_installation()` + `check_version()` call chain after this issue is implemented
- **`_scripts_dir` root cause detail**: `project_root / "scripts"` in `cli.py:_run_yes()` lines 158–159 and 175–176 uses `project_root` = the user's target project directory (from `--root` or `cwd()`), **not** the little-loops source location. The correct editable-vs-consumer discriminator mirrors BUG-1071's fix (`skills/update/SKILL.md:124–128`): parse `Editable project location:` from `pip show little-loops` stdout. Python equivalent: `subprocess.run([sys.executable, "-m", "pip", "show", "little-loops"], capture_output=True, text=True, timeout=10)` then scan for `"^Editable project location:"`.
- **`resolve_host()` is required for all `claude` subprocess calls**: Per `.claude/CLAUDE.md`, "All host CLI invocations must go through `resolve_host()` in `host_runner.py`." `fetch_latest_plugin()` must use `runner = resolve_host(); invocation = runner.build_...` and `[invocation.binary, *invocation.args]`, not hardcoded `["claude", "plugin", ...]`. Reference: `scripts/little_loops/cli/action.py:cmd_capabilities()` lines 149–165.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py` — imports `install_check`; calls `check_version()` and `detect_installation()`
- `scripts/little_loops/cli/__init__.py` — imports `main_init` from `little_loops.init.cli`; top-level CLI entry point; indirectly depends on install_check through cli.py

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/__init__.py` — re-exports `InstallStatus`, `check_version`, `detect_installation` from `install_check`; **must also export** `fetch_latest_pypi` and `fetch_latest_plugin` to make them part of the public API surface; update `__all__` accordingly

### Similar Patterns
- FEAT-892 (`/ll:update` skill) — pip + plugin + marketplace upgrade mechanics to reuse; do not duplicate
- BUG-1071 — same `-e <bare-name>` crash class already fixed in `/ll:update`; mirror that fix here

### Tests
- `scripts/tests/test_init_install.py` — **expand existing file** (not new); contains `TestDetectInstallation` and `TestCheckVersion` classes; mock subprocess for both surfaces (up-to-date, behind, offline/timeout); assert no `-e <bare-name>` invocation is constructed for the consumer path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_install.py` (update) — `TestCheckVersion` (3 tests calling `check_version(installed, current)`) will break if signature gains a third param or semantics shift; update to pass `latest` arg and assert notify-and-prompt behavior — **[LIKELY BREAK]**
- `scripts/tests/test_init_install.py` (update) — `TestDetectInstallation.test_global_claude_code_installation_detected` asserts `version is None`; this is exactly the gap being closed by step 3 — update to assert version is populated from `claude plugin list --json` — **[WILL BREAK by design]**
- `scripts/tests/test_init_install.py` (update) — `TestDetectInstallation.test_local_installation_detected` asserts `source == "local-editable"`; if a new `"pypi"` source label is introduced for non-editable installs, update accordingly
- `scripts/tests/test_init_install.py` (new) — add `TestFetchLatestPypi`: mock `pip index versions little-loops` stdout for success (`"LATEST: 1.130.0"`), offline (`TimeoutExpired`), and bad output; assert `None` on failure
- `scripts/tests/test_init_install.py` (new) — add `TestFetchLatestPlugin`: mock `claude plugin marketplace update` and `claude plugin list --available --json`; assert `None` on offline; assert `resolve_host()` is used (not hardcoded `"claude"`)
- `scripts/tests/test_init_core.py` (update) — `TestMainInit` patches `detect_installation` to `(None, None)` in ~10 tests; need new test methods for: `--upgrade` flag causes auto-upgrade, no `--upgrade` only warns, and the assert-no-`pip install -e <bare-name>` pattern (follow `TestUpdateSkillConsumerPath` style in `test_update_skill.py:TestUpdateSkillConsumerPath.test_package_step_does_not_use_relative_scripts_path`)
- `scripts/tests/test_init_tui.py` (review) — `mock_detect_installation` autouse fixture returns `(None, None)` globally; review whether TUI plugin-check screen (new per-surface checks) needs the fixture to return a richer mock for new tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Established mock pattern (stacked context managers, patch target `"little_loops.init.install_check.subprocess.run"`):
  ```python
  with (
      patch("little_loops.init.install_check.importlib.metadata.version", ...),
      patch("little_loops.init.install_check.shutil.which", return_value="/usr/bin/claude"),
      patch("little_loops.init.install_check.subprocess.run") as mock_run,
  ):
  ```
- Offline/timeout test: `side_effect=subprocess.TimeoutExpired("cmd", 10)` — see `TestDetectInstallation.test_global_cmd_timeout_returns_none_none`
- New `fetch_latest_pypi()` tests: mock `stdout="Available versions: ...\nLATEST: 1.130.0\n"` for success, `TimeoutExpired` for offline
- Consumer-path assertion style: `scripts/tests/test_update_skill.py:TestUpdateSkillConsumerPath.test_package_step_does_not_use_relative_scripts_path` (line 129) — asserts `"pip install -e './scripts'" not in content`

### Documentation
- `.claude/CLAUDE.md` § CLI Tools (`ll-init`) — update description once feature is real for end users
- `docs/reference/API.md` — add `fetch_latest_pypi()` and `fetch_latest_plugin()` to `install_check` module reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` (lines 88–96) — flag table lists `--yes`, `--force`, `--dry-run`, `--plan`, `--enable`, `--disable`, `--root`, `--hosts`; add `--upgrade` row describing "act on drift; default headless mode is warn-only"
- `docs/guides/GETTING_STARTED.md` (lines 112–125) — "Existing Installation Detection" table currently says headless mode "upgrades automatically" on version mismatch — this is the behavior being changed to notify-and-prompt; update table to describe new warn-only/`--upgrade` semantics
- `skills/init/SKILL.md` (line 46) — invocation `ll-init --yes $FORCE_FLAG $DRY_RUN_FLAG $HOSTS_FLAG` does not pass `--upgrade`; add `$UPGRADE_FLAG` to the invocation template and document when to set it

### Configuration
- N/A — no new config keys; `--upgrade` is a CLI flag only

## API / Interface

New module-level functions in `install_check.py` (offline-safe, `None` on
failure):

```python
def fetch_latest_pypi(timeout: float = 10.0) -> str | None: ...
def fetch_latest_plugin(timeout: float = 10.0) -> str | None: ...
```

`detect_installation()` return contract unchanged in shape, but the
`global-claude-code` source now carries a non-`None` version when
`claude plugin list --json` resolves it.

New headless flag: `ll-init --upgrade` (act on drift; default is warn-only).

## Acceptance Criteria

- [ ] Running `ll-init` in a non-repo project with a stale PyPI package reports
      `installed → latest` and offers `pip install --upgrade little-loops`.
- [ ] Running `ll-init` with a stale `ll@little-loops` plugin (and `claude-code`
      selected) reports drift and offers the marketplace+plugin update commands.
- [ ] No code path constructs `pip install -e little-loops` (bare name).
- [ ] PyPI / plugin latest-checks fail silently (skip, do not crash) when
      offline or when `claude`/network is unavailable.
- [ ] Plugin check is skipped entirely when `claude-code` is not a selected host.
- [ ] Headless mode only mutates the environment when `--upgrade` is passed.
- [ ] `check_version` no longer compares installed-vs-`__version__`.

## Scope Boundaries

**In scope:**
- PyPI package version check (`little-loops`) via `pip index versions`
- Claude Code plugin version check (`ll@little-loops`) via `claude plugin list --json` / marketplace update
- Fix `pip install -e <bare-name>` crash for consumer (non-source-repo) installs
- New `--upgrade` headless flag; without it, headless mode warns only
- Offline-safe fallbacks: any network failure silently skips the check

**Out of scope:**
- `marketplace.json` staleness on publish (BUG-364 — a `publish`-skill sync gap)
- `/ll:update` skill upgrade mechanics (FEAT-892 — reuse those, do not re-implement)
- Other host CLI plugin surfaces (opencode, codex) — plugin check is `claude-code`-only
- Automating upgrades without explicit user confirmation
- Changing the existing TUI prompt UX beyond adding per-surface drift detection

## Impact

- **Priority**: P2 — Primary onboarding path for all external users; silent failures and crashes on first run erode trust
- **Effort**: Medium — Three files in `init/` to update (`install_check.py`, `cli.py`, `tui.py`), subprocess handling, offline-safe wrappers; no new modules required
- **Risk**: Medium — Touches the install/upgrade flow; incorrect subprocess handling could leave users with broken installs; offline-safe fallbacks mitigate the worst cases
- **Breaking Change**: No — `--upgrade` is an additive headless flag; existing TUI warn-and-prompt behavior is preserved

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § CLI Tools (`ll-init`) | Advertises install + version-drift detection this issue makes real for end users |
| FEAT-892 (`/ll:update` slash command) | Reuse its pip+plugin+marketplace upgrade mechanics; do not duplicate |
| BUG-1071 (update skill `-e ./scripts` path bug) | Same class of bug fixed in the `/ll:update` skill; this is the parallel fix in `ll-init` |
| BUG-364 (marketplace.json version mismatch) | Recurring `marketplace.json` staleness (currently 1.117 vs 1.129); a `publish`-skill sync gap, out of scope here |

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Editable-install detection: Python equivalent of BUG-1071 fix
BUG-1071's fix (`skills/update/SKILL.md:124–128`) detects editable installs via `pip show little-loops | grep "^Editable project location:"`. Python equivalent for `cli.py:_run_yes()` to replace the broken `_scripts_dir = project_root / "scripts"` guard:

```python
_pip_show = subprocess.run(
    [sys.executable, "-m", "pip", "show", "little-loops"],
    capture_output=True, text=True, timeout=10,
)
_editable_line = next(
    (l for l in _pip_show.stdout.splitlines() if l.startswith("Editable project location:")),
    None,
)
if _editable_line:
    _editable_path = _editable_line.split(": ", 1)[1].strip()
    _install_target = f"{_editable_path}[dev]"  # true source-repo path
else:
    # Consumer path: plain PyPI install
    _install_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "little-loops"]
```

### `detect_installation()` source label mismatch
`detect_installation()` currently returns `"local-editable"` for **both** editable source installs and plain PyPI installs — `importlib.metadata` cannot distinguish between the two. **Decided (ARCHITECTURE-043):** return `"pypi"` for non-editable installs. The fix already requires calling `pip show little-loops` to discriminate; returning `"local-editable"` for a PyPI install at that point would be actively incorrect. Required follow-on: add `"pypi"` to `install_source.enum` in `config-schema.json` and update `test_local_installation_detected`'s source assertion.

### `resolve_host()` requirement — canonical invocation pattern
```python
from little_loops.host_runner import resolve_host

runner = resolve_host()
# For version-check style calls:
invocation = runner.build_version_check()
result = subprocess.run(
    [invocation.binary, *invocation.args],
    capture_output=True, text=True, timeout=10,
)
```
`fetch_latest_plugin()` should follow this pattern rather than hardcoding the `claude` binary name.

### Confirmed: `InstallStatus` enum — `NotInstalled` and `Unknown` are dead code today
`InstallStatus` (lines 12–16 of `install_check.py`) has four members: `UpToDate`, `OutOfDate`, `NotInstalled`, `Unknown`. `NotInstalled` and `Unknown` are **never returned** by any current function — dead code. ENH-2256 can put them to use: `Unknown` when the PyPI or plugin latest-version fetch fails (offline/timeout), `NotInstalled` if the install source probe returns `None`.

### Exact `TestCheckVersion` method names (all three will break on signature change)
`scripts/tests/test_init_install.py` `TestCheckVersion` (lines 13–22) has exactly:
- `test_matching_versions_returns_up_to_date()`
- `test_different_versions_returns_out_of_date()`
- `test_installed_ahead_returns_out_of_date()`
All call `check_version(installed, current)` — all three fail when the signature becomes `check_version(installed, latest)` per step 4. Must be rewritten to pass a realistic `latest` string.

### Corrected `GETTING_STARTED.md` line references
The issue text references lines 88–96 and 112–125; verified current line numbers are **86–96** (flag table) and **110–122** ("Existing Installation Detection" section). Minor drift — verify before editing.

### Two consumer-path assertion patterns to mirror (not one)
`test_update_skill.py:TestUpdateSkillConsumerPath` has **two** complementary tests to model in `test_init_core.py`:
- `test_package_step_does_not_use_scripts_dir_check` (line 120) — asserts `[ -d './scripts' ]` is absent (wrong dir-check pattern)
- `test_package_step_does_not_use_relative_scripts_path` (line 129) — asserts `pip install -e './scripts'` is absent (relative path pattern)
Mirror both as `TestMainInit` assertions that `["-e", "little-loops"]` never appears in the `subprocess.run` args constructed by `cli.py:_run_yes()` for the consumer path.

## Session Log
- `/ll:ready-issue` - 2026-06-22T19:38:48 - `7e10f4e6-27be-4069-8252-a20571bfa502.jsonl`
- `/ll:confidence-check` - 2026-06-22T20:00:00Z - `86ea8608-0275-4ab6-9270-49dc109f6497.jsonl`
- `/ll:refine-issue` - 2026-06-22T19:27:29 - `f89a7b96-0442-4d81-ad9c-9f9ab0dd8c72.jsonl`
- `/ll:confidence-check` - 2026-06-22T19:15:00Z - `43ef88af-b7a7-4f0a-8ce6-427eff2bb0d2.jsonl`
- `/ll:confidence-check` - 2026-06-22T19:00:00Z - `b1b9c595-53e9-4823-8303-2bf232a8ff4c.jsonl`
- `/ll:wire-issue` - 2026-06-22T18:47:02 - `e7fadde9-f5fa-45e4-b069-a2f8d1f94cea.jsonl`
- `/ll:refine-issue` - 2026-06-22T18:41:12 - `d8fe3b06-4852-4916-a301-81991cb7e805.jsonl`
- `/ll:format-issue` - 2026-06-22T18:26:38 - `9b5b146b-8e29-4477-b3aa-28d7305acc88.jsonl`
- `/ll:capture-issue` - 2026-06-22T18:22:22Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/900ce319-4e1b-4374-89bd-f7fbb0652cd4.jsonl`

---

## Resolution

All 7 acceptance criteria met:
- PyPI version check via `fetch_latest_pypi()` compares installed vs external latest
- Plugin version check via `fetch_latest_plugin()` using `resolve_host()`
- No code path constructs `pip install -e little-loops` (bare name)
- Both checks fail silently on timeout/offline
- Plugin check gated on `claude-code` in selected hosts
- Headless mode warns only; `--upgrade` flag required to act
- `check_version` compares installed vs external latest (not `__version__`)

**Files changed:** `install_check.py`, `cli.py`, `tui.py`, `__init__.py`, `config-schema.json`, `test_init_install.py`, `test_init_core.py`, `GETTING_STARTED.md`, `skills/init/SKILL.md`

## Status

**Current Status**: done
