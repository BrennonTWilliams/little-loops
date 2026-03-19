# Implementation Plan: FEAT-808 — go-no-go skill for adversarial issue assessment

**Date**: 2026-03-19
**Issue**: FEAT-808
**Action**: implement

---

## Summary

Create `skills/go-no-go/SKILL.md` — a new skill that evaluates whether an issue should be implemented using an adversarial debate format. Two background agents argue for/against, a judge agent renders a GO/NO-GO verdict.

---

## Solution Design

**Primary deliverable**: `skills/go-no-go/SKILL.md`
**No Python code required** — skill is a prompt-based instruction file only.

### Architecture

```
/ll:go-no-go FEAT-808
      │
      ├── Phase 1: Parse args (issue IDs, sprint name, --check flag)
      ├── Phase 2: Resolve issue files
      ├── Phase 3: For each issue:
      │     ├── Read issue file
      │     ├── Launch pro-agent + con-agent in parallel (background, worktree)
      │     ├── Wait for both to complete
      │     ├── Launch judge agent (foreground) with both outputs
      │     └── Display formatted verdict
      ├── Phase 4: Batch summary table (if >1 issue)
      └── Phase 5: --check mode exit codes (0=all GO, 1=any NO-GO)
```

### Key Design Decisions

1. **Background agents with worktree isolation** — pro/con agents launched via `Agent` tool with `run_in_background: true, isolation: "worktree"` per issue spec
2. **Inline agent prompts** — no separate agent files in `agents/`; all prompts defined within SKILL.md
3. **Judge is foreground** — receives both outputs sequentially, no need for background
4. **Sprint name detection** — if token doesn't match any active issue ID, treat as sprint name
5. **Session log** — append entry to each evaluated issue file

---

## Implementation Steps

### Phase 0: TDD Red Phase
- [x] Create `skills/go-no-go/SKILL.md` (makes actual skill count = 19)
- [ ] Run `python -m pytest scripts/tests/test_doc_counts.py` — expect FAIL (documents 18, finds 19)

### Phase 1: Implementation
- [ ] SKILL.md created with full content
- [ ] `.claude/CLAUDE.md` line 38: `(18 skills)` → `(19 skills)`
- [ ] `.claude/CLAUDE.md` line 53: add `` `go-no-go`^ `` to Planning & Implementation category

### Phase 2: TDD Green Phase
- [ ] Run `python -m pytest scripts/tests/test_doc_counts.py` — expect PASS (19/19)
- [ ] Run full test suite `python -m pytest scripts/tests/` — all pass

---

## Files Modified

| File | Change |
|------|--------|
| `skills/go-no-go/SKILL.md` | **CREATE** — new skill |
| `.claude/CLAUDE.md` | Update skill count + category |

---

## Acceptance Criteria Mapping

| Criterion | Implementation |
|-----------|----------------|
| Accepts comma-separated IDs, sprint name, no arg | Phase 1 arg parsing |
| Two concurrent background agents | Step 3b: both in single message |
| Real codebase research | Pro/con agent prompts direct file research |
| Judge agent with both arguments | Step 3d: foreground judge |
| GO/NO-GO verdict with structured reasoning | Step 3e: formatted output |
| Clear terminal display | `=` separator lines |
| Multiple issues → summary table | Phase 4 batch table |
| `--check` mode exit codes | Phase 5 |
