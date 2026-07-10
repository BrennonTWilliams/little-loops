---
id: ENH-2590
title: Wire `.pre-commit-config.yaml` repo-local hook for `.ll/decisions.yaml`
type: ENH
status: open
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
decision_needed: false
labels:
  - decisions
  - data-integrity
  - tooling
  - pre-commit
  - git
size: Small
---

# ENH-2590: Wire `.pre-commit-config.yaml` repo-local hook for `.ll/decisions.yaml`

## Summary

Wire the `ll-verify-decisions` CLI (from ENH-2589) into a `.pre-commit-config.yaml`
`repo: local` hook scoped to `.ll/decisions.yaml`. Fires on `git commit`; does
NOT catch `--no-verify` or non-hook edit paths (those are covered by ENH-2591
pytest CI gate and ENH-2592 Claude Code host hook).

This child ships **one** of three transport layers around the parent validator —
the git-side hook. It is **independently testable** as a subprocess that runs
`pre-commit run --files .ll/decisions.yaml` against a known-good and known-bad
fixture pair.

## Parent Issue

Decomposed from ENH-2587: "Guard `.ll/decisions.yaml` with a load-time validation
check on commit/CI"

## Why This Child Exists Standalone

`pre-commit` `repo: local` hooks are their own testable subsystem. This child
verifies the hook *configuration* (path-regex match, language, entry binary
exists) by invoking `pre-commit run` against fixtures in `tmp_path`. The
validator's correctness is independently verified by ENH-2589.

## Acceptance Criteria

- `.pre-commit-config.yaml` contains a `repo: local` hook with:
  - `language: system`
  - `entry: ll-verify-decisions`
  - `files: ^\.ll/decisions\.yaml$`
- `pre-commit run --files .ll/decisions.yaml` exits non-zero when the file is
  corrupted (OTHE-203 fixture).
- `pre-commit run --files .ll/decisions.yaml` exits 0 when the file is valid.
- The hook is registered at the correct position alphabetically between
  sibling `repo: local` hooks.
- A short skip-tolerant pytest test exists for the hook shape
  (skips when `pre-commit` is not on PATH) and is registered under
  `scripts/tests/test_decisions_yaml_gate.py` or a sibling test file.

## Files to Modify

- `.pre-commit-config.yaml` — append a `repo: local` block for
  `.ll/decisions.yaml`. Place alphabetically between existing
  `repo: local` entries (likely just below `check-decisions-yaml`-adjacent
  hooks if present, otherwise at the bottom of the local-hook cluster).
- `docs/guides/DECISIONS_LOG_GUIDE.md` — add a short paragraph explaining the
  pre-commit gate exists, what it does, and how `--no-verify` bypasses it
  (with a pointer to ENH-2591 for the pytest CI belt-and-suspenders).

## Depends On

- **ENH-2589** — `ll-verify-decisions` CLI must exist on `PATH` (installed via
  `pip install -e "./scripts[dev]"`).

## Blocks

Nothing.

## Implementation Steps

1. Read the current `.pre-commit-config.yaml` to identify the cluster of
   `repo: local` hooks and the alphabetical insertion point.
2. Append a `repo: local` block:
   ```yaml
   - repo: local
     hooks:
       - id: ll-verify-decisions
         name: Validate .ll/decisions.yaml
         language: system
         entry: ll-verify-decisions
         files: ^\.ll/decisions\.yaml$
         pass_filenames: false
   ```
3. Verify the validator CLI is installed (`ll-verify-decisions --help`).
4. Smoke-test against a corrupted `tmp_path` fixture: copy the OTHE-203 pattern
   into a temp `.ll/decisions.yaml` and run
   `pre-commit run --files .ll/decisions.yaml` (manual). Expect non-zero exit.
5. Smoke-test against a valid file (use the actual `.ll/decisions.yaml`
   post-recovery). Expect zero exit.
6. Update `docs/guides/DECISIONS_LOG_GUIDE.md` pre-commit paragraph.
7. Run the full pre-commit suite to ensure no regression:
   `pre-commit run --all-files`.
8. Run the test suite: `python -m pytest scripts/tests/`.

## Session Log
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
