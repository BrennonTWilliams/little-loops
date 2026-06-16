---
id: ENH-2199
type: ENH
priority: P3
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels: [hermes, cli, json, contract]
---

# Document and guarantee `--json` output contract stability

## Summary

Hermes consumes the `--json` output of `ll-loop list`, `ll-loop status`, and
`ll-issues list` for portfolio sync and the `ll_status`/`ll_portfolio` tools.
These `--json` outputs exist but have no documented schema or stability
guarantee, so a future field rename or shape change would silently break the
integration. Document the JSON shape for each of these three surfaces and add
snapshot tests that fail on unannounced breaking changes. Source:
`PRD-Hermes-Integration-v4.md` (EG-3).

## Acceptance Criteria

- The JSON output shape for `ll-loop list --json`, `ll-loop status --json`, and
  `ll-issues list --json` is documented (fields, types, semantics) in a reference doc.
- Snapshot tests assert the JSON shape for each command and fail when a field is
  removed, renamed, or retyped.
- A short stability note states what callers (e.g. Hermes) may rely on and how
  additive vs. breaking changes are signaled.

## Notes

- Additive fields should remain non-breaking; the guarantee covers removals/renames/retypes.
- Wiring points: list/status handlers under `scripts/little_loops/cli/loop/`,
  `scripts/little_loops/cli/issues/__init__.py`, and a reference doc under `docs/reference/`.
