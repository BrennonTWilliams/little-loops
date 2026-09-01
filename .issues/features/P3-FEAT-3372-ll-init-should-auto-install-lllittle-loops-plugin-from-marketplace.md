---
id: FEAT-3372
type: FEAT
title: ll-init should auto-install ll@little-loops plugin from marketplace
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T03:55:51Z'
---

# FEAT-3372: ll-init should auto-install ll@little-loops plugin from marketplace

## Summary

`ll-init` never installs the `ll@little-loops` Claude Code plugin from the marketplace on behalf of the user. It detects whether the plugin is already present and reports staleness, but when it's absent it leaves the user to run `claude plugin marketplace add` / `claude plugin install` manually — even when the user selected `claude-code` as a host during the wizard.

## Current Behavior

`detect_installation()` (`scripts/little_loops/init/install_check.py:60`) shells out to `claude plugin list --json` to check whether `ll@little-loops` is installed, returning `(None, None, None)` when it isn't found — this is read-only detection, not installation.

`_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:94`) is what actually acts on the selected hosts list during `ll-init`. For every other host (`codex`, `kimi-code`, `qwen`) it writes adapter files. For `claude-code` there is no branch that does anything — the loop falls through to a bare comment: `# claude-code: no adapter file needed; plugin hooks fire when globally enabled` (`scripts/little_loops/init/cli.py:169`). Nothing in that path calls `claude plugin marketplace add` or `claude plugin install`, so a user who selects `claude-code` in the wizard (or gets it via auto-detection in `_detect_hosts()`, `scripts/little_loops/init/cli.py:73`) but hasn't already installed the plugin ends `ll-init` with `/ll:*` commands, skills, agents, and hooks still unavailable.

## Expected Behavior

When `claude-code` is among the selected/detected hosts and `detect_installation()` reports the plugin is not installed (`install_source is None`), `ll-init` should install `ll@little-loops` from the marketplace automatically — unless the user explicitly deselected `claude-code` in the TUI's host checklist (`scripts/little_loops/init/tui.py:519`) or via `--hosts` on the headless path.

## Motivation

Today, running `ll-init` with Claude Code as the target host doesn't actually get you working `/ll:*` commands unless you separately know to run the marketplace/install commands yourself. That's a broken first-run experience for exactly the host `ll-init`'s wizard treats as the default checked option (`tui.py:140`, `tui.py:288`).

## Proposed Solution

Add a `claude-code` branch inside `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:169`) parallel to the existing `codex`/`kimi-code`/`qwen` branches: call `detect_installation(project_root)`; if the returned source is `None`, resolve the `claude` binary the same way `fetch_latest_plugin()` already does (`resolve_host().build_version_check().binary` / the pattern in `install_check.py:83`), then run the marketplace-add + install subprocess sequence, reporting success/failure via `info()`/`warning()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_dispatch_host_adapters()` claude-code branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/tui.py` (calls `_dispatch_host_adapters` at line 902) and `scripts/little_loops/init/cli.py` (headless paths at lines 223, 672, 879)

### Similar Patterns
- `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:172`) already has claude-code-specific, scope-aware subprocess logic to model the install branch after
- `detect_installation()` / `fetch_latest_plugin()` (`scripts/little_loops/init/install_check.py`) for the `resolve_host()` + subprocess pattern

### Tests
- TBD — needs a test covering: host selected + not installed → install invoked; host deselected → not invoked; host selected + already installed → not invoked

### Documentation
- N/A

## Program Design

### Types

No new types — reuses `detect_installation()`'s existing
`tuple[str | None, str | None, str | None]` (`install_source`, `installed_version`,
`install_path`) return shape.

### Signatures

- `_dispatch_host_adapters(hosts: list[str], project_root: Path, plugin_root: Path, force: bool = False, dry_run: bool = False) -> None` — add a `claude-code` branch alongside the existing `codex`/`kimi-code`/`qwen` branches (`scripts/little_loops/init/cli.py:169`)
- `detect_installation(project_root: Path) -> tuple[str | None, str | None, str | None]` — existing, called from the new branch to gate on `install_source is None` (`scripts/little_loops/init/install_check.py:60`)

### Call Path

`_dispatch_host_adapters()` -> `detect_installation(project_root)` -> (if `install_source is None`) `resolve_host().build_version_check().binary` -> `subprocess.run([binary, "plugin", "marketplace", "add", ...])` -> `subprocess.run([binary, "plugin", "install", "ll@little-loops"])`, reporting via `info()`/`warning()` — mirrors the scope-aware subprocess pattern already used in `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:172`).

## Implementation Steps

1. Add a `claude-code` branch to `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:169`) that calls `detect_installation(project_root)` and short-circuits (no-op) when `install_source` is already one of `local-editable`/`pypi`/`global-claude-code`/`project-claude-code`
2. When `install_source is None`, resolve the host binary via `resolve_host().build_version_check().binary` and run the `claude plugin marketplace add` + `claude plugin install ll@little-loops` subprocess sequence, reporting outcome through `info()` on success and `warning()` on subprocess failure or missing binary (headless/non-interactive `claude` CLI limitation)
3. Add tests covering: host selected + not installed → install invoked; host deselected/omitted from `--hosts` → not invoked; host selected + already installed (any `install_source` value) → not invoked; install subprocess failure → surfaced as `warning()`, not silent

## Impact

- **Priority**: P3 - First-run UX gap (default host ends up with no working `/ll:*` commands), not a regression or data-loss risk, so below P0-P2
- **Effort**: Small - One new branch in an existing dispatch function, reusing `detect_installation()` and the `resolve_host()` subprocess pattern already proven in `_dispatch_host_upgrade()`; no new files or public API
- **Risk**: Low - Change is additive and gated behind `install_source is None`; existing hosts' branches and the already-installed path are untouched
- **Breaking Change**: No

## Use Case

A developer runs `ll-init` in a new project, accepts the default host selection (Claude Code checked), and expects `/ll:capture-issue`, `/ll:manage-issue`, etc. to work immediately afterward without a separate manual plugin-install step.

## Acceptance Criteria

- If `claude-code` is selected/detected as a host and `detect_installation()` returns no installed source, `ll-init` runs the marketplace add + plugin install for `ll@little-loops` (or clearly documents/prints the exact commands needed and why it can't run them itself, e.g. headless/non-interactive `claude` CLI limitations).
- If the user unchecks `claude-code` in the TUI host checklist (or omits it from `--hosts`), no install is attempted.
- If the plugin is already installed (any of the `install_source` values `local-editable`, `pypi`, `global-claude-code`, `project-claude-code`), no redundant install is attempted — this path already exists via `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:172`) for the upgrade case and should not be duplicated.
- Failure to install (e.g. `claude` binary present but the install subprocess errors) is surfaced as a warning, not a silent no-op, consistent with the `warning()`/`info()` pattern already used for the other hosts in `_dispatch_host_adapters()`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-01 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-01T04:14:36 - `e78ad427-afac-4f8a-8262-9a68ce395c55.jsonl`
- `/ll:capture-issue` - 2026-09-01T03:55:58 - `54b7abda-af7a-4b45-bfa4-e6f3cd9335a3.jsonl`
