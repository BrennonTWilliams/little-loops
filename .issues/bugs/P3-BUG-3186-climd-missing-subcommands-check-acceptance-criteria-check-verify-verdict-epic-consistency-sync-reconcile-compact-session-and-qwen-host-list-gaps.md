---
id: BUG-3186
type: BUG
title: CLI.md missing subcommands (check-acceptance-criteria, check-verify-verdict,
  epic-consistency, sync reconcile, compact-session) and qwen host list gaps
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:32Z'
---

# BUG-3186: CLI.md missing subcommands (check-acceptance-criteria, check-verify-verdict, epic-consistency, sync reconcile, compact-session) and qwen host list gaps

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/reference/CLI.md` and several other reference docs are missing real, currently-installed CLI surface, and multiple docs undercount the fully-wired host list by omitting `qwen`.

## Current Behavior

- `docs/reference/CLI.md` has no `####` entry for `ll-issues check-acceptance-criteria` (`scripts/little_loops/cli/issues/check_acceptance_criteria.py`, ENH-3031), `ll-issues check-verify-verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py`, ENH-3031), or `ll-issues epic-consistency` / alias `ec` (`scripts/little_loops/cli/issues/epic_consistency.py`).
- The `ll-sync` section lists subcommands but omits `ll-sync reconcile` ("Promote feature-branch issues to done when their PR is merged", `scripts/little_loops/cli/sync.py:96-99`).
- `ll-compact-session` is a real installed entry point (`scripts/pyproject.toml`, `little_loops.cli:main_compact_session`) with no `### ll-compact-session` section anywhere in CLI.md.
- `qwen` is a fully-wired host (`install_qwen_adapter` in `scripts/little_loops/init/cli.py`, identical treatment to `claude-code`/`codex`/`kimi-code`) but is missing from the "fully wired hosts" list in `docs/reference/CLI.md:37,49`, `README.md`, `docs/guides/GETTING_STARTED.md:101`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:364` (`--cross-host` probe order), and `docs/reference/CONFIGURATION.md:1234` (`orchestration.host_cli` enum).

## Expected Behavior

- CLI.md documents `ll-issues check-acceptance-criteria`, `ll-issues check-verify-verdict`, `ll-issues epic-consistency`/`ec`, `ll-sync reconcile`, and `ll-compact-session`.
- All "fully wired host" lists include `qwen` alongside `claude-code`, `codex`, `kimi-code`.

## Motivation

Undocumented subcommands are invisible to users grepping CLI.md for capability, and the missing `qwen` entries make host support look narrower than it is — both erode trust in the reference doc as authoritative (CLAUDE.md states `<cmd> --help` is authoritative over prose, but CLI.md is meant to mirror it).

## Impact

- **Priority**: P3 — documentation-only, no functional bug, but affects discoverability of existing features.
- **Effort**: Small — mechanical additions following the existing `####`/`###` section patterns already used for sibling subcommands.
- **Risk**: None — doc-only change.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
