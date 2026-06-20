---
id: ENH-2191
title: HOST_COMPATIBILITY.md Gemini column — populate cells as children land
type: enhancement
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179, ENH-2184, ENH-2185, FEAT-2186, ENH-2187, FEAT-2188, FEAT-2189, FEAT-2190]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, docs]
---

# ENH-2191: HOST_COMPATIBILITY.md Gemini column — populate cells as children land

## Summary

Update `docs/reference/HOST_COMPATIBILITY.md` to populate the Gemini column from
its current stub values (`(unknown)` / `(deferred)`) to accurate ✓, ✗ (with
tracking issue), or N/A as each EPIC-2178 child issue lands.

The Gemini column stub was added as part of FEAT-2179. This issue is the
tracking/completion step — flip each cell once the corresponding implementation
is verified.

## Use Case

A developer evaluating Gemini CLI support opens `HOST_COMPATIBILITY.md` and sees
accurate parity status for each feature. The end-state acceptance for EPIC-2178
requires no `(unknown)` cells in the Gemini column.

## Cell Update Map (from FEAT-2179)

| Capability | Expected value | Depends on |
|-----------|---------------|-----------|
| `session_start` hook | ✓ | FEAT-2186 |
| `pre_compact` hook | ✓ | FEAT-2186 |
| `pre_tool_use` hook | ✓ | FEAT-2186 |
| `post_tool_use` hook | ✓ | FEAT-2186 |
| `user_prompt_submit` hook | ✓ | FEAT-2186 |
| `session_end` hook | ✓ (best-effort) | FEAT-2186 |
| Headless / `-p` flag | ✓ | ENH-2185 |
| Streaming JSON | ✓ (`-o stream-json`) | ENH-2185 |
| Blocking JSON | ✓ (`-o json`) | ENH-2185 |
| `--version` flag | ✓ | ENH-2185 |
| Config probe | ✓ (`.gemini/ll-config.json`) | ENH-2187 |
| Skills discovery | ✓ (`.gemini/skills/`) | FEAT-2188 |
| Commands discovery | ✓ (`.gemini/commands/*.toml`) | FEAT-2189 |
| Project instructions | ✓ (`GEMINI.md`) | FEAT-2190 |
| `ll-auto` conformance | ✓ | FEAT-2192 |
| `ll-loop` conformance | ✓ | FEAT-2192 |

## Implementation Steps

This issue should be updated incrementally as children land. Final pass:
1. Read current Gemini column in `HOST_COMPATIBILITY.md`.
2. For each landed child, flip the corresponding cell(s) to ✓.
3. For any remaining ✗ cells, link the tracking issue.
4. Remove all `(unknown)` / `(deferred)` values.
5. Verify no Gemini cells are blank.

## Acceptance Criteria

- Every Gemini column cell in `HOST_COMPATIBILITY.md` is ✓, ✗ (linked), or N/A.
- No `(unknown)` or `(deferred)` cells remain.
- EPIC-2178 end-state acceptance is satisfied.

## API/Interface

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — Gemini column cells

## Impact

- **Effort**: XS per cell update; aggregate XS–S
- **Risk**: None — documentation only
- **Breaking Change**: No

---

**Open** | Created: 2026-06-15 | Priority: P4

## Verification Notes (2026-06-17)

- The Gemini column in `HOST_COMPATIBILITY.md` already contains `(deferred)[^gemini]` values populated by FEAT-2179 research — the issue description's claim that cells are `(unknown)` stubs is outdated.
- The actual remaining work (flipping deferred/✗ cells to ✓ as child issues land) is still valid; update the issue body to reflect the current state of the column.

2026-06-19 (NEEDS_UPDATE): Confirmed — HOST_COMPATIBILITY.md Gemini column already has `(deferred)[^gemini]` values, not the `(unknown)` stubs the issue body describes. Remaining work (flip deferred→✓ as children land) is still valid; update Summary and Use Case sections to reflect the current column state.

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
