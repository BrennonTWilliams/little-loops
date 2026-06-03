---
id: FEAT-1896
title: "Decisions Log \u2014 Skill Bridges"
type: FEAT
priority: P3
parent: FEAT-1892
discovered_date: 2026-06-03
completed_at: 2026-06-03 06:58:37+00:00
depends_on:
- FEAT-1891
- FEAT-1894
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 20
status: done
---

# FEAT-1896: Decisions Log — Skill Bridges

## Summary

Wire three skills (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to append `decision` entries as a side effect, and optionally wire `/ll:capture-issue` for architectural choices at capture time. All integrations gracefully degrade when `decisions.yaml` is absent. Can run in parallel with FEAT-1895 once FEAT-1894 is merged.

## Current Behavior

The three skills (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) make structured decisions but do not record them to `.ll/decisions.yaml`. The `ll-issues decisions add` CLI (FEAT-1894) exists but is never called by these skills, leaving the decisions log unpopulated during normal ll usage.

## Expected Behavior

After each decision event — option selection in `/ll:decide-issue`, tradeoff outcome in `/ll:tradeoff-review-issues`, or go/no-go verdict in `/ll:go-no-go` — an entry is silently appended to `.ll/decisions.yaml` via `ll-issues decisions add`. If `decisions.yaml` is absent, the call is silently skipped (`2>/dev/null || true`).

## Use Case

A developer runs `/ll:decide-issue FEAT-1896` and selects option A. After the decision is applied to the issue file, the skill automatically calls `ll-issues decisions add --type=decision --category=architecture --issue=FEAT-1896 --rule="Option A" --rationale="..."`. Later they run `ll-issues decisions list` to review all architectural decisions made during the sprint.

## Parent Issue

Decomposed from FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — add `ll-issues decisions add` bash call after Phase 7 (Apply Changes) and before Phase 8 (Append Session Log); `Bash(ll-issues:*)` already present in frontmatter (line 14) — no frontmatter change needed
- `commands/tradeoff-review-issues.md` — add `ll-issues decisions add` bash call in Phase 5 per-issue processing, once after each `ll-issues append-log` call (lines 284 and 321); `Bash(ll-issues:*)` already present in frontmatter (line 13)
- `skills/go-no-go/SKILL.md` — add `ll-issues decisions add` bash call at end of Step 3f, after `git add "[issue-file-path]"` (line 399), before the `---` separator (line 402); **must also add `Bash(ll-issues:*)` to `allowed-tools` frontmatter** (currently absent — frontmatter ends at `Bash(ll-history-context:*)` on line 16)
- `skills/capture-issue/SKILL.md` — optional: add `ll-issues decisions add` for notable architectural choices at Phase 4 step 5, after session log append and before `git add`; `Bash(ll-issues:*, git:*)` already present in frontmatter (line 11)
- `skills/ll-go-no-go/SKILL.md` — Codex stub: add `- Bash(ll-issues:*)` to `allowed-tools` list (mirrors the `skills/go-no-go/SKILL.md` frontmatter change; stub currently has `Bash(ll-history-context:*)` but not `Bash(ll-issues:*)`) [Wiring pass]

### Dependent Files (Callers / Consumers)
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_add()` (lines 273–339): the CLI handler that all bridge calls invoke; `--category` is a **required** argument (line 89 in `add_decisions_parser()`)
- `scripts/little_loops/decisions.py` — `add_entry()`: atomic append to `.ll/decisions.yaml`
- `scripts/tests/test_cli_decisions.py` — `TestDecisionsCLIAdd`: existing CLI test fixture to model bridge smoke tests after
- `scripts/tests/test_feat1894_doc_wiring.py` — doc-wiring test pattern to follow for any new doc-wiring test for this feature

### Similar Patterns
- `skills/decide-issue/SKILL.md:330–332` — `ll-issues append-log` side-effect call in Phase 8; mirrors placement of `decisions add` call
- `skills/go-no-go/SKILL.md:141` — `HIST=$(ll-history-context ... 2>/dev/null || true)` — existing graceful degradation idiom in this file
- `skills/capture-issue/SKILL.md:213` — `ll-session search ... 2>/dev/null || true` — fire-and-forget silent fallthrough pattern

### Tests
- `scripts/tests/test_cli_decisions.py` — existing coverage for `ll-issues decisions add` CLI
- `scripts/tests/test_decisions.py` — data layer unit tests; shared fixtures: `decisions_path`, `sample_decision`
- New doc-wiring test (if required by FEAT-1893): follow pattern from `scripts/tests/test_feat1894_doc_wiring.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1896_skill_bridges.py` — new file needed; 4–5 test classes: `TestGoNoGoFrontmatter` (frontmatter check for `Bash(ll-issues:*)`), `TestDecideIssueDecisionsBridge` (phase-boundary slice Phase 7→Phase 8), `TestTradeoffReviewDecisionsBridge` (Phase 5 body), `TestGoNoGoDecisionsBridge` (Step 3f body); follow `_frontmatter()` helper from `test_enh1847_doc_wiring.py` and phase-boundary pattern from `test_decide_issue_skill.py` [Agent 3 finding]
- `scripts/tests/test_enh1888_doc_wiring.py` — add `test_ll_go_no_go_stub_has_ll_issues_tool` in `TestHistoryContextAllowedTools` asserting `Bash(ll-issues:*)` in `skills/ll-go-no-go/SKILL.md` frontmatter (ENH-1847 pattern) [Agent 2 finding]
- `scripts/tests/test_go_no_go_skill.py` — existing structural tests, verified safe: inspects Step 3a only, Step 3f insertion will not break [Agent 2 finding]
- `scripts/tests/test_decide_issue_skill.py` — existing structural tests, verified safe: Phase 7→Phase 8 boundary extraction unaffected by insertion [Agent 2 finding]

### Configuration
- `.ll/decisions.yaml` — written by `add_entry()`; bridge calls degrade silently when absent

## Proposed Solution

### Full `ll-issues decisions add` CLI Signature

```bash
ll-issues decisions add \
  --type {rule,decision,exception}   # required
  --category CATEGORY                # required (e.g. "architecture", "tradeoff", "implementation")
  --rule TEXT                        # required for type=decision (the decision text / chosen option)
  --rationale TEXT                   # required
  [--issue ISSUE_ID]                 # related issue ID, e.g. FEAT-1896
  [--enforcement {required,advisory}]# default: advisory
  [--alternatives-rejected TEXT]     # losing options and scores
  [--scope {issue,project}]          # default: issue
```

`--category` is required; it is validated in `_cmd_add()` at `scripts/little_loops/cli/issues/decisions.py:273`. The auto-generated entry ID uses `CATEGORY.upper()` as a prefix (e.g., `ARCHITECTURE-001`).

---

### decide-issue Bridge

Insert in `skills/decide-issue/SKILL.md` between Phase 7 (`---` separator at line 326) and `## Phase 8` (line 328). By Phase 7's end, `SELECTED_OPTION_TITLE`, `RATIONALE`, and the scoring table are all written to the issue file — all data is available.

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add \
      --type=decision \
      --category="architecture" \
      --issue="{{issue_id}}" \
      --rule="$SELECTED_OPTION_TITLE" \
      --rationale="$RATIONALE" \
      --alternatives-rejected="$ALTERNATIVES_REJECTED" \
      2>/dev/null || true
fi
```

`SELECTED_OPTION_TITLE` = winning option title from Phase 5 scoring. `ALTERNATIVES_REJECTED` = comma-separated losing option titles with scores.

---

### tradeoff-review-issues Bridge

Add in `commands/tradeoff-review-issues.md` Phase 5 "Execution", once per processed issue, right after each `ll-issues append-log` call:

- **For Approved Closures** (after line 284): `RECOMMENDATION` = "Close" or "Defer", `KEY_TRADEOFF` = rationale from subagent output, `LOSING_OPTIONS` = the kept/updated alternative.
- **For Approved Updates** (after line 321): `RECOMMENDATION` = "Update", `KEY_TRADEOFF` = tradeoff narrative, `LOSING_OPTIONS` = the close/defer alternative.

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add \
      --type=decision \
      --category="tradeoff" \
      --issue="$ISSUE_ID" \
      --rule="$RECOMMENDATION" \
      --rationale="$KEY_TRADEOFF" \
      --alternatives-rejected="$LOSING_OPTIONS" \
      2>/dev/null || true
fi
```

---

### go-no-go Bridge

**Step 1 — Add `Bash(ll-issues:*)` to frontmatter** (`skills/go-no-go/SKILL.md` lines 5–17). Insert after `Bash(ll-history-context:*)` (line 16):

```yaml
  - Bash(ll-issues:*)
```

**Step 2 — Add decisions call** at end of Step 3f, after `git add "[issue-file-path]"` (line 399), before the `---` separator (line 402):

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add \
      --type=decision \
      --category="implementation" \
      --issue="{{issue_id}}" \
      --rule="$VERDICT" \
      --rationale="$RATIONALE" \
      --enforcement=advisory \
      2>/dev/null || true
fi
```

`VERDICT` = "Go" or "No-Go" (parsed from judge output in Step 3e). `RATIONALE` = RATIONALE field from judge. `DECIDING_FACTOR` can be appended to `--rationale` for richer context.

**Skip guard**: the entire `decisions add` block must be inside the existing `CHECK_MODE` guard — skip when `CHECK_MODE` is true (same as the write-back guard at Step 3f line 360).

---

### capture-issue Bridge (Optional)

Add in `skills/capture-issue/SKILL.md` Phase 4, Action: Create New Issue, at step 5 (after session log append, before `git add` at step 6):

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add \
      --type=decision \
      --category="architecture" \
      --issue="$ISSUE_ID" \
      --rule="Captured: $ISSUE_TITLE" \
      --rationale="$ISSUE_SUMMARY" \
      --scope=issue \
      2>/dev/null || true
fi
```

Gate condition: only emit when the issue type is FEAT or EPIC (architectural choices), not for BUGs.

---

### Graceful Degradation Pattern

All bridges use `2>/dev/null || true` (silent fallthrough). Optional explicit guard:

```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add ... 2>/dev/null || true
fi
```

## Acceptance Criteria

- [ ] `/ll:decide-issue` appends `decision` entry after option selection (Phase 7→Phase 8 boundary); silently skipped if `decisions.yaml` absent
- [ ] `/ll:tradeoff-review-issues` appends `decision` entry per processed issue in Phase 5; silently skipped if absent
- [ ] `/ll:go-no-go` appends `decision` entry after verdict write-back (Step 3f); silently skipped if absent or `CHECK_MODE=true`
- [ ] `skills/go-no-go/SKILL.md` frontmatter adds `Bash(ll-issues:*)` to `allowed-tools` after `Bash(ll-history-context:*)`
- [ ] All `ll-issues decisions add` calls include `--category` (required argument)
- [ ] Optional: `/ll:capture-issue` appends `decision` entry for FEAT/EPIC captures
- [ ] All bridges use `2>/dev/null || true` graceful degradation

## Implementation Steps

1. **go-no-go frontmatter** — Edit `skills/go-no-go/SKILL.md` lines 5–17: insert `- Bash(ll-issues:*)` after `- Bash(ll-history-context:*)` (line 16)
2. **go-no-go decisions call** — In `skills/go-no-go/SKILL.md`, insert the `decisions add` block after `git add "[issue-file-path]"` (line 399), before `---` (line 402); wrap in `$CHECK_MODE` guard
3. **decide-issue decisions call** — In `skills/decide-issue/SKILL.md`, insert the `decisions add` block between `---` (line 326) and `## Phase 8` (line 328); no frontmatter change needed
4. **tradeoff-review-issues decisions call** — In `commands/tradeoff-review-issues.md`, insert the `decisions add` block once per issue after each `ll-issues append-log` call (lines 284 and 321)
5. **capture-issue decisions call (optional)** — In `skills/capture-issue/SKILL.md` Phase 4 step 5, add the FEAT/EPIC-gated `decisions add` block
6. **Run tests** — `python -m pytest scripts/tests/test_cli_decisions.py scripts/tests/test_decisions.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `skills/ll-go-no-go/SKILL.md` — add `- Bash(ll-issues:*)` to `allowed-tools` frontmatter (Codex stub must mirror primary skill frontmatter change)
8. Update `scripts/tests/test_enh1888_doc_wiring.py` — add `test_ll_go_no_go_stub_has_ll_issues_tool` in `TestHistoryContextAllowedTools` to gate the stub frontmatter update
9. Write `scripts/tests/test_feat1896_skill_bridges.py` — comprehensive bridge wiring tests (5 classes: frontmatter + 3 skill-body phase-boundary + optional capture-issue); run with: `python -m pytest scripts/tests/test_feat1896_skill_bridges.py -v --tb=short`

## Impact

- **Priority**: P3 — Required for the decisions log to be populated automatically; without this bridges, the log relies entirely on manual `ll-issues decisions add` calls
- **Effort**: Low — Inserting ~10-line bash snippets at existing phase boundaries in three skill files; no new source files except tests
- **Risk**: Low — All calls use `2>/dev/null || true` graceful degradation; existing skill behavior is unchanged when `decisions.yaml` is absent
- **Breaking Change**: No

## Labels

`decisions`, `skills`, `wiring`, `feat`

## Status

**Open** | Created: 2026-06-03 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T06:52:48 - `2f0aa301-0831-4dce-9077-2f2aa5142287.jsonl`
- `/ll:wire-issue` - 2026-06-03T06:46:37 - `cabeea1c-5e97-4e42-b311-705e56d0a765.jsonl`
- `/ll:refine-issue` - 2026-06-03T06:42:13 - `117370f8-7446-4b35-b1b3-dbd68cf3d270.jsonl`
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
