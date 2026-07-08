---
id: BUG-2547
title: "ll-init --yes crashes with FileNotFoundError on config-schema.json in non-editable (wheel) installs"
type: BUG
status: done
priority: P1
captured_at: '2026-07-08T20:58:29Z'
completed_at: '2026-07-08T20:58:29Z'
discovered_date: '2026-07-08'
discovered_by: user-report
labels:
  - ll-init
  - packaging
  - wheel
  - importlib-resources
  - regression-guard
confidence_score: 99
outcome_confidence: 99
---

# BUG-2547: `ll-init --yes` crashes with FileNotFoundError on config-schema.json in non-editable (wheel) installs

## Summary

A fresh `pip install little-loops && ll-init --yes` on a user machine crashed
with:

```
FileNotFoundError: [Errno 2] No such file or directory:
  '/Users/<u>/.pyenv/versions/<v>/lib/python3.12/config-schema.json'
  File ".../site-packages/little_loops/init/core.py", line 23, in _load_schema
    with schema_path.open(encoding="utf-8") as f:
```

`ll-init --yes` is the entry point the project steers *every* new user toward,
so this broke the canonical install path for the public.

## Current Behavior

A fresh non-editable install of the package (`pip install little-loops` from
PyPI) followed by `ll-init --yes` in an empty directory crashes with:

```
FileNotFoundError: [Errno 2] No such file or directory:
  '/Users/<u>/.pyenv/versions/<v>/lib/python3.12/config-schema.json'
  File ".../site-packages/little_loops/init/core.py", line 23, in _load_schema
    with schema_path.open(encoding="utf-8") as f:
```

`ll-init --yes` exits non-zero before writing `.ll/ll-config.json` or creating
the `.issues/` tree. The same traceback fires in `--dry-run` mode because
`_run_yes` → `build_config` → `schema_default("learning_tests.enabled")` is
reached very early in the config-building pipeline (line 125 of
`scripts/little_loops/init/core.py`).

The failure is silent in the editable-install development workflow
(`pip install -e ./scripts[dev]`): `_load_schema()`'s
`Path(__file__).resolve().parents[3]` resolves to the repo root, where the
file lives, so no one in the dev loop ever sees the crash.

## Expected Behavior

`pip install little-loops && ll-init --yes` in an empty directory should:

1. Detect the project type and write `.ll/ll-config.json` with a valid
   `$schema` URL.
2. Create the canonical issue sub-directories
   (`.issues/{bugs,features,enhancements,epics}/`).
3. Exit 0 and print the success banner.

The schema must be discoverable in *every* install layout — editable, wheel
install into a system Python, wheel install into a `python -m venv`,
wheel install under `pipx`, etc.

## Steps to Reproduce

1. `python -m venv /tmp/repro && /tmp/repro/bin/pip install --quiet little-loops`
2. `cd /tmp && mkdir empty && cd empty`
3. `unset CLAUDE_PLUGIN_ROOT`
4. `/tmp/repro/bin/ll-init --yes`
5. Observe `FileNotFoundError: .../config-schema.json` and non-zero exit.

(The `pip install little-loops` step installs a wheel — *not* editable —
which is the canonical public path; the editable dev install does not
exhibit the bug.)

## Impact

- **Severity**: P1 — every public user of the package hits this on first run.
- **Affected users**: 100% of fresh `pip install little-loops` installs.
- **Recovery**: nothing automatic; the user must file a bug, downgrade, or
  install editable.
- **CI gap**: `ll-verify-package-data` was already flagging the
  `Path(__file__).resolve().parents[3]` escape as a lint violation, but it
  was a lint, not a build-time gate. `tests/test_wheel_smoke.py` exercises
  the exact failure mode but is gated on `PYTEST_INTEGRATION=1`, which the
  project's standard test runner does not set — so the bug shipped.
- **Workaround before fix**: `pip install -e ./scripts[dev]` from a clone,
  or set `CLAUDE_PLUGIN_ROOT` to a checkout (the latter doesn't actually
  help — `_load_schema` doesn't read `CLAUDE_PLUGIN_ROOT`).

## Root Cause

Two compounding defects, both in `scripts/little_loops/`:

1. **`config-schema.json` lived outside the package.** The file sat at the
   repo root. `pyproject.toml`'s `[tool.hatch.build.targets.wheel]` only
   includes `little_loops/**` + `LICENSE`, so the file was never packaged
   into the wheel. The published artifact did not contain the schema at all.

2. **`init/core.py:_load_schema()` walked out of the package** via
   `Path(__file__).resolve().parents[3] / "config-schema.json"`. In an
   *editable* install that resolves to the repo root (where the file lived),
   so it worked for the dev workflow. In a *wheel* install `parents[3]`
   resolves to `…/lib/python3.X/`, where the file doesn't exist — hence
   `FileNotFoundError` at the first `schema_default()` call inside
   `build_config()`.

The static lint `ll-verify-package-data` was already flagging the
`Path(__file__).resolve().parents[3]` escape — but it produced a lint
violation, not a build failure, and the violation was not gating the
publish path. The wheel-install smoke test (`tests/test_wheel_smoke.py`)
exercises the exact failure mode and would have caught it on day one, but
it is gated behind `PYTEST_INTEGRATION=1`, which the project's "CI" gate
(`python -m pytest scripts/tests/`) does not set.

## Blast Radius

- Every public user of the package hits this on first run.
- `ll-init` is the recommended install path in every Getting Started /
  README / docs page.
- `--dry-run` (the only wheel-smoke-tested path) happened to NOT call
  `schema_default()` early enough to surface this, so the bug was
  invisible to the existing smoke harness.

## Fix

Move the canonical schema into the Python package and load it via
`importlib.resources`, matching the pattern every other bundled asset uses
(via `little_loops.package_data`).

```
$ git mv config-schema.json scripts/little_loops/config-schema.json
```

- `scripts/little_loops/init/core.py:_load_schema()` now reads via
  `importlib.resources.files("little_loops").joinpath("config-schema.json")`.
- `SCHEMA_URL` updated to point at the new in-repo GitHub raw path
  (`.../main/scripts/little_loops/config-schema.json`).
- `("config-schema.json",)` registered in `PACKAGE_DATA_ASSETS`, so the
  manifest check (`ll-verify-package-data`) enforces its inclusion in the
  wheel.
- 9 project-type templates (`scripts/little_loops/templates/*.json`)
  updated from `"$schema": "../config-schema.json"` → `"config-schema.json"`
  (co-located in the package).
- `tests/test_config_schema.py` and `tests/test_enh1768_profile_system.py`
  now resolve the schema via `importlib.resources` instead of
  `PROJECT_ROOT / "config-schema.json"` (the file no longer exists at the
  repo root).
- `tests/test_wiring_skills_and_commands.py` updated: the two `ENH-1734`
  wiring entries now point at `scripts/little_loops/config-schema.json`.
- `docs/ARCHITECTURE.md` and `docs/reference/CONFIGURATION.md` updated to
  reflect the new in-package location and the new GitHub raw URL.

## Defense-in-Depth (regression guards)

Three layers of backstop so this cannot recur silently:

1. **`ll-verify-package-data`** — already flagged the `parents[3]` escape.
   The rewrite removes the only violation in `init/core.py`, and the
   manifest check now requires the schema asset.

2. **`tests/test_init_core.py::TestSchemaLoaderInWheelInstall`** (NEW,
   fast, ungated) — two tests that exercise `_load_schema()` and
   `schema_default()` directly. Fails with `FileNotFoundError` if anyone
   reintroduces a parent-walk or breaks the loader. Runs in <1s on every
   `pytest scripts/tests/` invocation.

3. **`tests/test_wheel_smoke.py::test_schema_loads_in_wheel_install`**
   (NEW, gated behind `PYTEST_INTEGRATION=1` like the rest of that file)
   — full end-to-end reproduction: builds the wheel, installs into a fresh
   venv, calls `schema_default("learning_tests.enabled")`, asserts the
   default value. This is the exact code path that crashed in the user's
   traceback.

## Files Changed

- `config-schema.json` → `scripts/little_loops/config-schema.json` (moved via
  `git mv`; history preserved)
- `scripts/little_loops/init/core.py` (loader rewrite + `SCHEMA_URL` update)
- `scripts/little_loops/package_data.py` (`PACKAGE_DATA_ASSETS` entry)
- `scripts/little_loops/templates/{generic,python-generic,javascript,typescript,rust,go,java-maven,java-gradle,dotnet}.json`
  (`$schema` reference)
- `scripts/tests/test_config_schema.py` (importlib.resources lookup)
- `scripts/tests/test_enh1768_profile_system.py` (importlib.resources lookup)
- `scripts/tests/test_init_core.py` (NEW `TestSchemaLoaderInWheelInstall`)
- `scripts/tests/test_wheel_smoke.py` (NEW `test_schema_loads_in_wheel_install`)
- `scripts/tests/test_wiring_skills_and_commands.py` (path correction for
  the two `ENH-1734` wiring entries)
- `docs/ARCHITECTURE.md` (in-package location)
- `docs/reference/CONFIGURATION.md` (new GitHub raw URL)
- `CHANGELOG.md` (1.139.0 Fixed section entry)

## Verification

- `ll-verify-package-data`: PASS (lint clean + manifest check includes the
  new asset entry).
- `pytest scripts/tests/test_config_schema.py scripts/tests/test_enh1768_profile_system.py scripts/tests/test_init_core.py scripts/tests/test_package_data_manifest.py scripts/tests/test_verify_package_data.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_wheel_smoke.py`: 460 passed, 7 skipped.
- `pytest scripts/tests/` (full suite): 14,342 passed, 28 skipped. The 4
  failures observed are pre-existing on `main` (`README.md` line-count +
  3 unrelated wiring-guides content drifts); confirmed via `git stash`
  baseline before this fix.
- **End-to-end reproduction of the user's failure mode**: built the wheel
  with `python -m build --wheel`, installed non-editable into a fresh
  venv with `CLAUDE_PLUGIN_ROOT` unset, ran `ll-init --yes`. Exit code 0;
  the user's exact `FileNotFoundError` traceback is gone; the generated
  `.ll/ll-config.json` carries the new `$schema` URL; `.issues/{bugs,features,enhancements,epics}/`
  are created.
- URL audit: `grep -r "raw.githubusercontent.*config-schema" scripts/`
  returns only the single updated `SCHEMA_URL` definition; no stragglers
  point at the old path.

## Notes / Follow-ups

- **Backwards compat (URL drift)**: existing users with `.ll/ll-config.json`
  containing the old GitHub raw URL (`.../main/config-schema.json`) will
  see a 404 in IDE schema validation. Functionality is unaffected (the
  `$schema` URL is metadata for editor autocomplete, not a runtime
  dependency). Re-running `ll-init --yes` refreshes the URL. Documented
  in the CHANGELOG entry.
- **`PYTEST_INTEGRATION=1` gate**: the `test_wheel_smoke.py` family
  remains gated. The new `TestSchemaLoaderInWheelInstall` runs in the
  ungated default suite, so the most likely regression surface is covered
  without paying the wheel-build cost on every run. Ungateing the full
  wheel smoke suite is a separate decision (slow-path; out of scope here).

## Acceptance Criteria

- [x] `pip install little-loops && ll-init --yes` exits 0 in a fresh venv.
- [x] `config-schema.json` ships inside the wheel at
      `site-packages/little_loops/config-schema.json`.
- [x] `ll-verify-package-data` is clean (no `__file__`-escape violations).
- [x] `TestSchemaLoaderInWheelInstall` catches the regression in <1s.
- [x] `test_schema_loads_in_wheel_install` reproduces the original
      failure mode under `PYTEST_INTEGRATION=1`.
- [x] The `parents[3]` `__file__`-walk in `init/core.py` is gone.
- [x] Existing test wiring entries pointing at `config-schema.json` are
      redirected to the new in-package location.


## Status

`done` — fix shipped and verified end-to-end on 2026-07-08. Captured at the
same timestamp because the user-reported traceback led directly to the
fix in the same session. Files Changed, Verification, and Acceptance
Criteria sections document the shipped state.

## Session Log
- `/ll:format-issue` - 2026-07-08T21:00:46 - `57bffb63-87a0-45cc-9a20-6991344f05da.jsonl`
- `hook:posttooluse-status-done` - 2026-07-08T20:59:05 - `57bffb63-87a0-45cc-9a20-6991344f05da.jsonl`
- `hook:sessionstart` - 2026-07-08T20:30:00Z - SessionStart:startup hook success (local-editable install)