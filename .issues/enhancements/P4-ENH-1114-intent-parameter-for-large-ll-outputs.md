---
id: ENH-1114
type: ENH
priority: P4
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue

blocked_by: [FEAT-1112]
relates_to: ['FEAT-1112', 'ENH-1111']
---

# ENH-1114: Intent Parameter for Large ll-* CLI Outputs

## Summary

Add an optional `--intent <query>` parameter to `ll-history`, `ll-deps`, `ll-scan-*`, `ll-workflows`, and similar CLIs so the full result is indexed but only the slice matching the intent is returned to the caller.

## Motivation

These CLIs today dump their entire result to stdout. A single `ll-deps` run on a mature issue set can be thousands of lines; `ll-history` analysis excerpts push the same. In loop contexts, the agent reads the full dump, even when it only needs "which issues touch FSM state machine rate limits."

Context-mode (github.com/mksglu/context-mode) calls this "intent-driven filtering": when tool output exceeds a threshold and an intent is supplied, the full result is indexed and only the relevant sections return. They report this as one of their highest-impact context reductions.

## Current Behavior

- `ll-history`, `ll-deps`, `ll-scan-*` all print full results
- No way to ask "dependency chain for FEAT-960 only" without piping through grep (which loses context)
- Output sizes routinely exceed 500 lines on real projects

## Expected Behavior

- Affected CLIs accept `--intent "<query>"` and `--intent-limit <N>` (default 50 lines)
- When `--intent` is supplied and full output >200 lines:
  - Full result written to `.ll/scratch/<cmd>-<timestamp>.txt` (or indexed into session DB once FEAT-1112 lands)
  - Ranked subset returned to stdout with a footer: `# Full output: <path> (N lines)`
- Step 1: Wire `--intent` flag into affected CLIs as a no-op pass-through (full output returned, `--intent` value captured but not used)
- Step 2: After FEAT-1112 ships, implement ranking directly against FTS5 — no interim BM25 layer
- `--intent` without a threshold hit is a no-op

## Acceptance Criteria

- `--intent` flag wired into at least 3 CLIs (`ll-history`, `ll-deps`, `ll-scan-codebase`)
- No `ranking.py` / BM25 module — ranking is implemented exclusively against FEAT-1112's FTS5 store
- Integration test: `ll-history --intent "rate limit" | wc -l` returns < `ll-history | wc -l` (only valid after FEAT-1112 lands)
- CLAUDE.md / API reference updated

## References

- Inspiration: context-mode intent-driven filtering
- Blocked by FEAT-1112: implement ranking only after FTS5 store ships (no interim BM25)
- Pairs with ENH-1111 scratch-pad enforcement

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `--intent` flag in `ll-history`, `ll-deps`, or `ll-scan-codebase` ✓
- No `scripts/little_loops/ranking.py` module ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-14T20:57:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-04-27T02:55:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d048a1c-d492-434e-87b2-d34bc1ea2f6c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `ranking.py` BM25 module introduced by this issue is an interim implementation. Once FEAT-1112 (unified SQLite + FTS5 store) lands, the ranking backend should be replaced with FTS5 rather than maintaining two parallel ranking approaches. Implement `ranking.py` as a thin, swappable backend so the transition is a drop-in replacement, not a rewrite.

**Implementation constraint** (added by `/ll:audit-issue-conflicts` 2026-05-04): `ranking.py` MUST NOT be authored before FEAT-1112 ships. The correct sequence is: (1) wire the `--intent` flag UI into the affected CLIs with full unranked output as a no-op placeholder, (2) wait for FEAT-1112's FTS5 store to land, (3) implement ranking directly against FTS5. Building the BM25 interim layer creates throwaway code with HIGH technical debt (confirmed by tradeoff review 2026-04-26).

---

## Tradeoff Review Note

**Reviewed**: 2026-04-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | MEDIUM |
| Technical debt risk | HIGH |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — This issue is explicitly blocked by FEAT-1112 (SQLite + FTS5 store), which does not yet exist. The proposed `ranking.py` BM25 module is designed to be thrown away once FEAT-1112 lands, creating throwaway tech debt. Defer implementation until FEAT-1112 is complete and replace BM25 backend directly with FTS5 rather than building the interim layer. If you do implement the interim, ensure `ranking.py` is a thin swappable backend with no callers hard-coupling to BM25 specifics.
