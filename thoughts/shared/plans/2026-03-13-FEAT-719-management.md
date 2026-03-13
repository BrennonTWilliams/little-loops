# Implementation Plan: FEAT-719 — ll-loop analyze synthesizes issues from loop history

**Date**: 2026-03-13
**Issue**: P3-FEAT-719-ll-loop-analyze-synthesizes-issues-from-loop-history.md
**Action**: implement

---

## Summary

Create `skills/analyze-loop/SKILL.md` — a new skill that reads `ll-loop list --running --json` and `ll-loop history <name> --json`, classifies events into BUG/ENH signals, deduplicates against active issues, prompts for confirmation, and writes issue files.

## Research Findings

### Key facts confirmed
- `ll-loop list --running --json` → JSON array of `LoopState.to_dict()` with fields: `loop_name`, `current_state`, `status`, `updated_at`, `accumulated_ms`, `iteration`
- `ll-loop history <name> --json [--tail N]` → JSON array of event dicts; each event: `{"event": "<type>", "ts": "<ISO8601>", ...type-specific fields}`
- `ll-issues next-id` → prints 3-digit zero-padded next available issue number
- `plugin.json` uses `"skills": ["./skills"]` glob — no changes needed there; new directory is auto-discovered
- No Python module needed — skill is pure SKILL.md instructions

### Complete event schema (relevant fields)
| Event type | Key fields |
|---|---|
| `state_enter` | `state`, `iteration` |
| `action_complete` | `exit_code`, `duration_ms`, `is_prompt` |
| `evaluate` | `verdict`, `confidence`, `reason` |
| `loop_complete` | `final_state`, `iterations`, `terminated_by` |
| `route` | `from`, `to` |

`terminated_by` values: `terminal`, `max_iterations`, `timeout`, `signal`, `error`, `handoff`

### Signal classification rules
1. `action_complete.exit_code != 0` repeated 3+ times on same state → **BUG P2**
2. `loop_complete.terminated_by == "signal"` → **BUG P2** (SIGKILL)
3. `loop_complete.terminated_by == "error"` → **BUG P2** (FATAL_ERROR)
4. Same state entered 5+ times across events (retry flood) → **ENH P3**
5. Avg `action_complete.duration_ms` > 30000ms on a state (3+ samples) → **ENH P4**
6. `evaluate.verdict == "fail"` 3+ times on same state → **BUG P3**

### Deduplication key
Loop name + state name: search `.issues/{bugs,enhancements,features}/` for files mentioning both strings.

## Files to Create
- `skills/analyze-loop/SKILL.md`

## Files to Modify
- `docs/reference/COMMANDS.md` — add `/ll:analyze-loop` entry after `/ll:review-loop` and add to quick reference table

## Phase Checklist

- [ ] Phase 3: Create `skills/analyze-loop/SKILL.md`
- [ ] Phase 3: Update `docs/reference/COMMANDS.md`
- [ ] Phase 4: Verify — ruff lint, mypy type check (no new Python, should pass trivially)
- [ ] Phase 5: Complete issue lifecycle

## Design Decisions
- **No Python module**: Issue spec confirmed "no companion `.py` needed; all logic in SKILL.md"
- **Default tail**: Use 200 events for analysis (CLI default is 50, too small for pattern detection)
- **`--tail` as skill arg**: Passed through to `ll-loop history --tail N`
- **Multiple loops**: Use `AskUserQuestion` when 2+ candidate loops found
- **Deduplication threshold**: Grep-based (loop_name + state name present in same file) — sufficient for this use case
