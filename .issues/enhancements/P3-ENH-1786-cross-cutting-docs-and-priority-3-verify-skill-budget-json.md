---
id: ENH-1786
title: Cross-cutting docs and add --json to ll-verify-skill-budget
type: enh
status: open
priority: P3
parent: ENH-1780
labels:
- cli
- agent-composability
- documentation
---

# ENH-1786: Cross-cutting docs and add --json to ll-verify-skill-budget

## Summary

Update documentation to reflect the universal `--json` contract across all `ll-*` CLIs. Also add `--json` to `ll-verify-skill-budget` (Priority 3, nice-to-have data-emitting CLI).

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Proposed Solution

### Documentation Updates

Document the universal `--json` contract in the reference docs and skill files. Update flag tables across 6 CLI sections. Address the pattern inconsistency between `ll-deps validate --json` and `ll-deps analyze --format json` in the map-dependencies skill docs.

### ll-verify-skill-budget --json

Add `--json` flag to `ll-verify-skill-budget` (`main_verify_skill_budget()` in `scripts/little_loops/cli/docs.py`, lines 107-201). This is Priority 3 (nice-to-have) — the command emits numerical output with no `--json` currently.

## Files to Modify

- `docs/reference/API.md` — Document the universal `--json` contract.
- `docs/reference/CLI.md` — Add `--json | -j` rows to flag tables in 6 sections: `ll-sync` (status/diff), `ll-logs` (discover/tail), `ll-session` (search), `ll-deps` (validate), `ll-gitignore`, `ll-verify-skill-budget`.
- `skills/map-dependencies/SKILL.md` — Note `--json` on `validate` vs `--format json` on `analyze` pattern. Consider normalizing `analyze` to also accept `--json` (or document the inconsistency).
- `scripts/little_loops/cli/docs.py` — Add `--json` for `ll-verify-skill-budget` numerical output.

## Pre-requisite

- ENH-1783: `add_json_arg()` shared helper must exist before starting this work.

## Tests

Per CLI verification checklist for `ll-verify-skill-budget`:
- `--json` flag appears in `--help` output
- Valid JSON output (parse with `json.loads()`)
- Exit code is 0

Reference existing pattern: `test_json_output_flag` in `scripts/tests/test_cli_docs.py` (line 38) for `ll-verify-docs` and `ll-check-links`.

## Implementation Steps

1. Update `docs/reference/API.md` — document the universal `--json` contract.
2. Update `docs/reference/CLI.md` — add `--json | -j` rows to flag tables in 6 sections: `ll-sync`, `ll-logs`, `ll-session`, `ll-deps`, `ll-gitignore`, `ll-verify-skill-budget`.
3. Update `skills/map-dependencies/SKILL.md` — note `--json` on `validate` vs `--format json` on `analyze` pattern inconsistency.
4. Add `--json` to `ll-verify-skill-budget` in `docs.py`.
5. Add JSON output test for `ll-verify-skill-budget` to `test_cli_docs.py` (if not already covered).

## Impact

- **Priority**: P3
- **Effort**: Small — documentation updates + one minor CLI change
- **Risk**: Low — documentation and additive CLI flag
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
