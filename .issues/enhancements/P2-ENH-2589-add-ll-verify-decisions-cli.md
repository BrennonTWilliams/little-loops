---
id: ENH-2589
title: Add `ll-verify-decisions` validator CLI + malformed-input unit tests
type: ENH
status: done
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
decision_needed: false
learning_tests_required:
- pyyaml
labels:
- decisions
- data-integrity
- tooling
- validator
- cli
size: Medium
confidence_score: 97
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 25
completed_at: '2026-07-10T22:45:37Z'
---

# ENH-2589: Add `ll-verify-decisions` validator CLI + malformed-input unit tests

## Summary

Add the core validator CLI that ENH-2587's three transport layers (pre-commit,
pytest CI gate, Claude Code host PreToolUse) will consume. The validator wraps
`load_decisions()` and fails non-zero on any `yaml.YAMLError`, `KeyError`, or
`ValueError`, catching both syntax corruption (OTHE-203) and schema drift
(unknown `type`, missing required fields).

This child ships the **implementation half** of the parent gate. The three
transport-layer integrations are deferred to ENH-2590, ENH-2591, ENH-2592.

## Parent Issue

Decomposed from ENH-2587: "Guard `.ll/decisions.yaml` with a load-time validation
check on commit/CI"

The parent selected **Option A** — new `ll-verify-decisions` entry in the
`ll-verify-*` family — because it slots natively into a `.pre-commit-config.yaml`
`repo: local` `entry:` line and matches the canonical home for repo-boundary
file validation gates.

## Current Behavior

`.ll/decisions.yaml` is currently only validated at first call site by
`load_decisions()` (`scripts/little_loops/decisions.py:272`). A YAML parse
error (e.g., the OTHE-203 corruption pattern `rationale: "abc "" def"`) or a
schema-drift entry (unknown `type`, missing required field) surfaces only when
a downstream consumer (`sync_to_local_md`, `decisions list`, etc.) calls the
loader. There is no dedicated validator CLI to gate the file at commit time,
CI, or Claude Code PreToolUse. The parent ENH-2587 identified three corruption
modes (syntax corruption OTHE-203, schema drift via unknown discriminators,
missing required fields) with no automated guard.

## Expected Behavior

After this child ships, the new `ll-verify-decisions` CLI is the canonical
load+schema gate for `.ll/decisions.yaml`:

- Exit code `0` when the file is loadable via `load_decisions()` and contains
  no schema drift.
- Exit code `1` on any caught `yaml.YAMLError`, `KeyError`, or `ValueError`,
  with a single-line `ERROR:` message on stderr pointing at the file path.
- `--config-root <path>` flag overrides the default location for non-standard
  repo layouts.
- Companion tests at `scripts/tests/test_decisions.py` cover the three
  corruption modes plus CLI exit-code behavior at
  `scripts/tests/test_verify_decisions.py`.

## Scope Boundaries

**In scope** (this child):

- The `ll-verify-decisions` CLI itself (new module + console script + tests +
  permissions allowlist entry + doc references).
- Three malformed-input unit tests for `TestLoadDecisions` (YAMLError, KeyError,
  ValueError-on-unknown-type).

**Explicitly out of scope** (deferred siblings):

- **ENH-2590**: pre-commit hook wiring `.pre-commit-config.yaml` to invoke
  `ll-verify-decisions`.
- **ENH-2591**: pytest CI gate that subprocesses `ll-verify-decisions` from
  `scripts/tests/`.
- **ENH-2592**: Claude Code `PreToolUse` hook that gates `.ll/decisions.yaml`
  edits via the host hook subsystem.
- Any change to `load_decisions()` itself, `sync_to_local_md`, or existing
  consumers — this child only adds a new gate, it does not retrofit existing
  callers.

## Why This Child Exists Standalone

In TDD-mode the validator's behavior is **independently testable** via
in-process CLI tests that `patch("sys.argv", ...)` and assert exit codes
(`scripts/tests/test_verify_package_data.py:264-334`). Once these tests are
green, the validator ships without any hook needing to exist. The transport
hooks (ENH-2590, ENH-2591, ENH-2592) then each wire the same binary into their
own subsystem and verify their own integration surface.

## Acceptance Criteria

- `ll-verify-decisions` exits 0 when `.ll/decisions.yaml` is loadable via
  `load_decisions()` and contains no schema drift.
- `ll-verify-decisions` exits 1 when the file has YAML syntax errors
  (`yaml.YAMLError`), unknown `type` discriminators (`ValueError`), or missing
  required fields (`KeyError`); error message points at the file path.
- CLI accepts `--config-root <path>` for non-default locations; defaults to
  `config.project_root / config.decisions.log_path`.
- `TestLoadDecisions` (at `scripts/tests/test_decisions.py:~75`) is extended
  with malformed-input cases for the OTHE-203 fixture
  (`rationale: "abc \"\" def"`), missing-id entry, and unknown-type entry.
- CLI-level tests in `scripts/tests/test_cli_decisions.py` mirror
  `test_verify_package_data.py:264-334` and cover clean/dirty exit codes plus
  `--config-root` path override.

## Files to Modify

- `scripts/little_loops/cli/verify_decisions.py` (new) — mirror
  `scripts/little_loops/cli/verify_package_data.py:235-316`
  (`main_verify_package_data`). Catch `yaml.YAMLError`, `KeyError`,
  `ValueError` from `load_decisions()`; print a single-line error pointing at
  the path; return 1 on any caught exception, 0 on success.
- `scripts/little_loops/cli/__init__.py` — re-export
  `main_verify_decisions` (mirror existing `main_verify_*` re-exports at
  `cli/__init__.py:82-85`).
- `scripts/pyproject.toml` — add
  `ll-verify-decisions = "little_loops.cli:main_verify_decisions"` next to
  `ll-verify-package-data`, `ll-verify-design-tokens`, `ll-verify-des-audit`,
  `ll-verify-triggers` (cluster at `pyproject.toml:63-89`).
- `scripts/little_loops/init/writers.py:38-40` — add
  `"Bash(ll-verify-decisions:*)"` to the existing sibling allowlist
  (`ll-verify-package-data:*`, etc.).
- `scripts/tests/test_decisions.py:~75-118` — extend `TestLoadDecisions` with
  malformed-input cases using `pytest.raises(yaml.YAMLError)` /
  `pytest.raises(KeyError)` / `pytest.raises(ValueError, match="Unknown entry
  type")`. Mirrors `scripts/tests/test_decisions.py:251-280`.
- `scripts/tests/test_cli_decisions.py` — add CLI-level tests for the new CLI
  (clean returns 0, dirty returns 1, `--config-root` override) mirroring
  `scripts/tests/test_verify_package_data.py:264-334`.
- `docs/reference/API.md` — new `main_verify_decisions` entry point reference.
- `docs/reference/COMMANDS.md` — new `ll-verify-decisions` command reference.
- `CHANGELOG.md` — single-line release entry on promote (NOT under
  `[Unreleased]` per project convention).

### Documentation listings (wiring pass — must keep CLI registry consistent)

_Wiring pass added by `/ll:wire-issue`:_

- `.claude/CLAUDE.md:205-211` — append `- ll-verify-decisions` bullet to the
  existing `ll-verify-*` cluster in the "CLI Tools" section (siblings already
  listed: `ll-verify-docs`, `ll-verify-package-data`, `ll-verify-design-tokens`,
  `ll-verify-des-audit`, `ll-verify-skill-budget`, `ll-verify-skills`,
  `ll-verify-triggers`).
- `commands/help.md:280-285` — append `ll-verify-decisions <description>` line
  to the existing `ll-verify-*` cluster (siblings already listed).
- `docs/reference/CLI.md:2521-2699` — add a new `### ll-verify-decisions`
  subsection following the established per-CLI template (flags table with
  `--config-root`, exit codes, examples); slot between `### ll-verify-des-audit`
  (`:2680`) and `### ll-verify-design-tokens` (`:2652`) or simply after
  `### ll-verify-des-audit` to keep cluster contiguous (file is grouped by
  verify-* block at the bottom).
- `skills/configure/areas.md:832` — append `ll-verify-decisions` to the
  `/ll:configure permissions` wizard's enumeration string AND bump the leading
  count from "31" to "32" (e.g.,
  `"Authorize all 32 ll- CLI tools and handoff write: ll-action, …,
  ll-verify-decisions, …"`).

### Test wiring (consolidated doc-wiring test — per ENH-1963)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_wiring_cli_registry.py:13+` — add three rows to the
  `DOC_STRINGS_PRESENT` parametrized list asserting `ll-verify-decisions`
  appears in `commands/help.md`, `docs/reference/CLI.md`, and
  `.claude/CLAUDE.md` (mirror the ENH-2308 rows at `:70-72` and the ENH-2475
  rows at `:73-75`). This is the consolidated doc-wiring test that catches
  missing CLI registrations.

## Depends On

Nothing — this is the leaf child. ENH-2590, ENH-2591, ENH-2592 each depend on
this CLI existing.

## Blocks

- ENH-2590 (pre-commit hook — calls `ll-verify-decisions`)
- ENH-2591 (pytest CI gate — calls `ll-verify-decisions`)
- ENH-2592 (Claude Code PreToolUse hook — calls `ll-verify-decisions`)

## Implementation Steps

1. Create `scripts/little_loops/cli/verify_decisions.py` mirroring
   `main_verify_package_data` shape: argparse with `--config-root`,
   `_run(config, log_path)` private helper, public `main_verify_decisions()`
   entry point, structured error message on failure, exit codes 0/1.
2. Re-export `main_verify_decisions` from `scripts/little_loops/cli/__init__.py`.
3. Register console script in `scripts/pyproject.toml` next to sibling
   `ll-verify-*` entries.
4. Add `"Bash(ll-verify-decisions:*)"` to
   `scripts/little_loops/init/writers.py:38-40`.
5. Extend `TestLoadDecisions` with the three malformed-input cases:
   - `rationale: "abc \"\" def"` → `yaml.parser.ParserError`
   - entry missing `id` → `KeyError`
   - entry with `type: foo` → `ValueError("Unknown entry type")`
6. Add CLI-level tests for clean/dirty/`--config-root` using
   `patch("sys.argv", [...])`.
7. Update `docs/reference/API.md` with the new entry point.
8. Update `docs/reference/COMMANDS.md` with the new command.
9. Add single-line CHANGELOG entry on promote.
10. Run `python -m pytest scripts/tests/test_decisions.py scripts/tests/test_cli_decisions.py -v`
    then the full suite: `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. **`.claude/CLAUDE.md:205-211`** — append `- ll-verify-decisions` bullet to
    the existing `ll-verify-*` cluster in the "CLI Tools" section (keep
    alphabetical: between `ll-verify-des-audit` and `ll-verify-design-tokens`).
    Sibling precedent: lines 207-208.
12. **`commands/help.md:280-285`** — append `ll-verify-decisions <description>`
    line to the existing `ll-verify-*` cluster (use the same description tone
    as siblings: short verb phrase).
13. **`docs/reference/CLI.md:2521-2699`** — add a new `### ll-verify-decisions`
    subsection following the established per-CLI template (flags table with
    `--config-root`, exit codes, examples). Slot between
    `### ll-verify-des-audit` (`:2680`) and `### ll-verify-design-tokens`
    (`:2652`).
14. **`skills/configure/areas.md:832`** — append `ll-verify-decisions` to the
    `/ll:configure permissions` wizard's enumeration string AND bump the
    leading count from "31" to "32". Sibling precedent: ENH-1396 step 9.
15. **`scripts/tests/test_wiring_cli_registry.py:13+`** — add three rows to
    the `DOC_STRINGS_PRESENT` parametrized list:
    - `("commands/help.md", "ll-verify-decisions", "ENH-2589")`
    - `("docs/reference/CLI.md", "ll-verify-decisions", "ENH-2589")`
    - `(".claude/CLAUDE.md", "ll-verify-decisions", "ENH-2589")`
    This is the consolidated doc-wiring test (per ENH-1963) that catches
    missing CLI registrations. Sibling precedent: lines 70-72 (ENH-2308) and
    lines 73-75 (ENH-2475).
16. Re-run `python -m pytest scripts/tests/` and confirm
    `scripts/tests/test_wiring_cli_registry.py` is green (the new
    parametrized rows will fail until step 11-13 are complete).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Integration Map (cross-references for implementers)

**Files to Modify** (all anchor references verified against current source):

- `scripts/little_loops/cli/verify_decisions.py` — **new file** mirroring
  `scripts/little_loops/cli/verify_package_data.py:235-316`
  (`main_verify_package_data`). Structural reference: `cli_event_context`
  wrapper at `:241`, `argparse.ArgumentParser(prog=..., ...)` at `:242`,
  exit-code return at `:315` (`return 1 if (...) else 0`).
- `scripts/little_loops/cli/__init__.py` — add import at line 86 (after
  `main_verify_triggers` re-export at `:85`) and add `"main_verify_decisions"`
  to `__all__` alphabetically between `main_verify_des_audit` (`:122`) and
  `main_verify_package_data` (`:123`). Also add docstring bullet at line 25
  (after the `ll-verify-des-audit` line).
- `scripts/pyproject.toml` — add
  `ll-verify-decisions = "little_loops.cli:main_verify_decisions"` between
  `ll-verify-des-audit` (`:89`) and `ll-adapt-agents-for-codex` (`:90`) to
  keep the verify-cluster contiguous.
- `scripts/little_loops/init/writers.py:38-40` — add
  `"Bash(ll-verify-decisions:*)"` between `ll-verify-docs:*` (`:38`) and
  `ll-verify-package-data:*` (`:39`) for alphabetical consistency.
  **Auto-coverage**: `scripts/tests/test_init_core.py:806-812`
  (`test_all_canonical_permissions_present`) iterates
  `_LL_PERMISSIONS` and asserts every entry is written into
  `.claude/settings.local.json` — no new test method needed.
- `scripts/little_loops/decisions.py:272-282` (`load_decisions`) — the
  validator's exception surface. Three sources:
  - `yaml.safe_load(raw)` at `:278` → `yaml.YAMLError`
    (incl. `yaml.parser.ParserError`)
  - `data["id"]` / `data["result"]` / `data["measured_at"]` at the
    `from_dict` classmethods (`RuleEntry:67`, `DecisionEntry:117`,
    `ExceptionEntry:167`, `CouplingEntry:216`) → `KeyError`
  - `_entry_from_dict` at `:268` →
    `ValueError(f"Unknown entry type: {entry_type!r}")`
  - `_resolve_path` at `:23-24` and `_DEFAULT_LOG_PATH` at `:20` resolve
    the default to `Path.cwd() / .ll/decisions.yaml`.
- `scripts/tests/test_decisions.py:75-117` (`TestLoadDecisions`) — extend
  with three `pytest.raises` cases (mirrors `test_decisions.py:270-273`
  for `KeyError` and `test_decisions.py:251-257` for `ValueError, match=`).
  Use inline `decisions_path.write_text(...)` (precedent:
  `TestSyncToLocalMd._write_rules` at `:310-318`) — no committed fixture
  file required.
- `scripts/tests/test_verify_decisions.py` — **new file** (see Open
  Question below for naming-conflict resolution). Mirror the class shape
  of `scripts/tests/test_verify_package_data.py:264-365`
  (`TestMainVerifyPackageData`) and the inline-fixture style of
  `scripts/tests/test_verify_design_tokens.py:1-6` (per-ENH-2308).
- `docs/reference/API.md`, `docs/reference/COMMANDS.md`, `CHANGELOG.md` —
  doc updates as specified in the **Files to Modify** section.

### Reusable Patterns to Follow

- **CLI structure**: wrap the entire entry point body in
  `with cli_event_context(DEFAULT_DB_PATH, "ll-verify-decisions", sys.argv[1:]):`
  (see `session_store.py:868-880`, used by `verify_package_data.py:241`).
  This populates `cli_events` in `.ll/history.db` — no extra wiring needed.
- **Error message format**: `"ERROR: <message>"` to `sys.stderr` (matches
  `verify_package_data.py:294-299`).
- **Test idiom for CLI**: `with (patch("sys.argv", [...]), patch("builtins.print")):` —
  see `test_verify_package_data.py:276-280` and the `patch.object(sys, "argv", ...)`
  variant in `test_des_audit.py` line 94+.

### Open Question for Implementer

> ⚠ **File-name conflict**: the **Files to Modify** section names
> `scripts/tests/test_cli_decisions.py`, but this file already exists
> (`/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_cli_decisions.py`)
> and is dedicated to the `ll-issues decisions <subcommand>` wrapper
> (`from little_loops.cli.issues.decisions import ...`). Mixing
> `ll-verify-decisions` tests there conflates two CLIs.
> The canonical pattern (mirroring `test_verify_package_data.py`,
> `test_verify_design_tokens.py`, `test_verify_des_audit.py`) is to
> create a separate **`scripts/tests/test_verify_decisions.py`**.
> Recommend: change step 6 + step 10 path accordingly before
> implementation.

### Synthetic-Fixture Pattern (no committed fixture file required)

The OTHE-203 corruption fixture is constructed inline via
`decisions_path.write_text(...)` per `TestSyncToLocalMd._write_rules`
(`test_decisions.py:310-318`). The exact OTHE-203 string (per parent
issue ENH-2587 research, lines 174-180) is:

```yaml
entries:
  - id: OTHE-203
    type: decision
    rationale: "abc "" def"
```

In Python, write this raw (no escaping) via:

```python
decisions_path.write_text(
    'entries:\n  - id: OTHE-203\n    type: decision\n'
    '    rationale: "abc "" def"\n',
    encoding="utf-8",
)
```

Then `with pytest.raises(yaml.YAMLError): load_decisions(decisions_path)`.
The `match=` argument can use `"parsing"` (per
`test_fsm_schema.py:1668-1672`) to assert `ParserError` specifically.

### Sibling CLI Reference Files (read, do not modify)

- `scripts/little_loops/cli/verify_package_data.py` — closest analog
- `scripts/little_loops/cli/verify_design_tokens.py:main_verify_design_tokens`
  (lines 197-266) — text/JSON dual-output pattern
- `scripts/little_loops/cli/verify_des_audit.py:main_verify_des_audit`
  (lines 97-164) — minimal-surface analog
- `scripts/little_loops/cli/verify_triggers.py:main_verify_triggers`
  (lines 577-661) — full-featured analog

All four use the same `cli_event_context` + argparse + dataclass-result
+ dual `--json`/text pattern; no shared base class exists.

## Impact

- **Priority**: P2 — defensive validator for a single config file; no immediate
  user-facing breakage, but addresses a known class of corruption (OTHE-203) that
  silently breaks `sync_to_local_md` and downstream consumers.
- **Effort**: Medium — new CLI module (~80-100 LOC mirroring
  `verify_package_data.py`), 3 new malformed-input test cases, 1 new test
  file, 6 wiring touchpoints (pyproject, init/writers, cli/__init__.py,
  API/COMMANDS/CLI.md, help.md, CLAUDE.md, test_wiring_cli_registry, configure/areas.md).
- **Risk**: Low — additive CLI; existing CLIs unchanged. The validator's
  exit-code contract (0 clean, 1 dirty) matches the existing `ll-verify-*`
  family, so transport-layer callers (ENH-2590/2591/2592) can rely on it without
  surprise.
- **Breaking Change**: No — new console script entry, no modifications to
  `load_decisions()`, no schema changes to `.ll/decisions.yaml`.

## Status

**Open** | Created: 2026-07-10 | Priority: P2 | Parent: ENH-2587 (done)

## Session Log
- `ll-auto` - 2026-07-10T22:45:37 - `3f07dfd8-539f-41f1-a8d2-b2e0e59b7a87.jsonl`
- `/ll:ready-issue` - 2026-07-10T22:26:42 - `e4c317c2-7b0b-4bc5-9d33-fda49c26df85.jsonl`
- `/ll:wire-issue` - 2026-07-10T22:18:56 - `f33ab106-89dc-4953-84eb-c7ab426de19f.jsonl`
- `/ll:refine-issue` - 2026-07-10T22:13:23 - `1f8c23e5-8233-46b2-bad8-7121b6844da8.jsonl`
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
- `/ll:confidence-check` - 2026-07-10T22:30:00 - `b11e4a82-2341-4c24-a37b-270932a92971.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-10
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
