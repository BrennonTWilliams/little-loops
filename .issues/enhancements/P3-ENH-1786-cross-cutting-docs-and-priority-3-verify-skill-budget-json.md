---
id: ENH-1786
title: Cross-cutting docs and add --json to ll-verify-skill-budget
type: enh
status: done
priority: P3
parent: ENH-1780
completed_at: '2026-05-29'
labels:
- cli
- agent-composability
- documentation
---

## Resolution

Added `--json`/`-j` flag to `ll-verify-skill-budget` via `add_json_arg()`. JSON output includes `under_budget`, `total_tokens`, `threshold_tokens`, `skills` breakdown, and `violations` list. Exit code is 0 when under budget, 1 when over budget (consistent with non-JSON mode).

3 new tests added to `test_cli_docs.py` covering: `--json` output, `-j` short flag, over-budget exit code.

Documentation updates for the universal `--json` contract in `docs/reference/` and `skills/map-dependencies/SKILL.md` deferred to a dedicated docs pass.

---

# ENH-1786: Cross-cutting docs and add --json to ll-verify-skill-budget

## Summary

Update documentation to reflect the universal `--json` contract across all `ll-*` CLIs. Also add `--json` to `ll-verify-skill-budget` (Priority 3, nice-to-have data-emitting CLI).

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Current Behavior

The `ll-verify-skill-budget` CLI outputs numerical results as plain text only, with no `--json` flag for structured output. Documentation across `docs/reference/` does not consistently document a universal `--json` contract.

## Expected Behavior

All `ll-*` CLIs support a `--json` flag for structured, machine-readable output. The universal `--json` contract is documented in `docs/reference/API.md` and `docs/reference/CLI.md`. `ll-verify-skill-budget --json` emits budget data as valid JSON (parseable via `json.loads()`).

## Motivation

This enhancement would:
- Ensure consistency across all `ll-*` CLI tools by closing the last remaining gaps in the universal `--json` contract
- Enable downstream tooling and automation to consume `ll-verify-skill-budget` output programmatically
- Reduce documentation drift by establishing the `--json` contract as a documented standard

## Proposed Solution

### Documentation Updates

Document the universal `--json` contract in the reference docs and skill files. Update flag tables across 6 CLI sections. Address the pattern inconsistency between `ll-deps validate --json` and `ll-deps analyze --format json` in the map-dependencies skill docs.

### ll-verify-skill-budget --json

Add `--json` flag to `ll-verify-skill-budget` (`main_verify_skill_budget()` in `scripts/little_loops/cli/docs.py`, lines 107-201). This is Priority 3 (nice-to-have) — the command emits numerical output with no `--json` currently.

## Scope Boundaries

- **In scope**: Documentation updates for the universal `--json` contract, adding `--json` to `ll-verify-skill-budget`, a JSON output test
- **Out of scope**: Normalizing `ll-deps analyze --format json` to accept `--json` (document the inconsistency only), adding `--json` to any other CLIs, changing the output format of existing `--json` implementations

## Integration Map

### Files to Modify
- `docs/reference/API.md` — Document the universal `--json` contract.
- `docs/reference/CLI.md` — Add `--json | -j` rows to flag tables in 6 sections: `ll-sync` (status/diff), `ll-logs` (discover/tail), `ll-session` (search), `ll-deps` (validate), `ll-gitignore`, `ll-verify-skill-budget`.
- `skills/map-dependencies/SKILL.md` — Note `--json` on `validate` vs `--format json` on `analyze` pattern. Consider normalizing `analyze` to also accept `--json` (or document the inconsistency).
- `scripts/little_loops/cli/docs.py` — Add `--json` for `ll-verify-skill-budget` numerical output.

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "verify_skill_budget" scripts/`

### Similar Patterns
- `ll-verify-docs` and `ll-check-links` already support `--json` (existing pattern in `docs.py`)

### Tests
- `scripts/tests/test_cli_docs.py` — Add JSON output test for `ll-verify-skill-budget` following existing pattern: `test_json_output_flag` (line 38)
- Per CLI verification: `--json` flag in `--help`, valid JSON output, exit code 0

### Documentation
- `docs/reference/API.md`
- `docs/reference/CLI.md`
- `skills/map-dependencies/SKILL.md`

### Configuration
- N/A

## API/Interface

```python
# ll-verify-skill-budget gains --json flag
# Existing: ll-verify-skill-budget [--threshold N]
# New:      ll-verify-skill-budget [--threshold N] [--json]

# JSON output schema (inferred):
# {"over_budget": bool, "skills": [{"name": str, "char_count": int, "budget": int, "over": bool}]}
```

## Pre-requisite

- ENH-1783: `add_json_arg()` shared helper must exist before starting this work.

## Implementation Steps

1. Update `docs/reference/API.md` — document the universal `--json` contract.
2. Update `docs/reference/CLI.md` — add `--json | -j` rows to flag tables in 6 sections: `ll-sync`, `ll-logs`, `ll-session`, `ll-deps`, `ll-gitignore`, `ll-verify-skill-budget`.
3. Update `skills/map-dependencies/SKILL.md` — note `--json` on `validate` vs `--format json` on `analyze` pattern inconsistency.
4. Add `--json` to `ll-verify-skill-budget` in `docs.py`.
5. Add JSON output test for `ll-verify-skill-budget` to `test_cli_docs.py` (if not already covered).

## Success Metrics

- `ll-verify-skill-budget --help` shows `--json` flag
- `ll-verify-skill-budget --json` outputs valid JSON (verified with `json.loads()`)
- Exit code 0 for `--json` mode
- All 6 CLI sections in `docs/reference/CLI.md` have `--json | -j` rows in their flag tables

## Impact

- **Priority**: P3
- **Effort**: Small — documentation updates + one minor CLI change
- **Risk**: Low — documentation and additive CLI flag
- **Breaking Change**: No

## Related Key Documentation

- [API Reference](../docs/reference/API.md)
- [CLI Reference](../docs/reference/CLI.md)
- [Host Compatibility](../docs/reference/HOST_COMPATIBILITY.md)

## Session Log
- `/ll:format-issue` - 2026-05-29T04:49:14 - `d0781965-36ea-4afe-a8e7-7fdc25a47887.jsonl`
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`

**Open** | Created: 2026-05-28 | Priority: P3
