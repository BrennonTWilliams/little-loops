---
captured_at: '2026-05-09T20:48:12Z'
completed_at: 2026-05-11T04:44:08Z
status: done
discovered_date: 2026-05-09
discovered_by: capture-issue
confidence_score: 86
outcome_confidence: 41
score_complexity: 13
score_test_coverage: 0
score_ambiguity: 18
score_change_surface: 10
---

# ENH-1394: Add `disable-model-invocation: true` to Operational Skills

## Summary

Tag 16 maintenance/audit skills with `disable-model-invocation: true` in their frontmatter so Claude Code excludes their descriptions from the listing budget. This is the direct fix for the `/doctor` warning that 23 skill descriptions are being dropped (1.4% used vs 1% budget) every session.

## Current Behavior

All 28 skill descriptions are included in the listing budget regardless of whether the LLM needs to discover them. Skills like `update`, `cleanup-worktrees`, `analyze-history`, and `audit-claude-config` are always user-invoked by typing the command — yet their descriptions consume budget that causes other skills to be silently truncated.

## Expected Behavior

Operational/maintenance skills are tagged `disable-model-invocation: true`. Their descriptions are excluded from the listing budget. The total listing footprint drops from ~1.4% to ~0.6% (estimate), eliminating the truncation warning. Affected skills remain fully functional — users can still type them explicitly; they just won't appear in the LLM's skill routing list.

## Motivation

Every session, Claude Code silently drops 23 skill descriptions due to budget overflow. The MRU algorithm keeps recently-used skills and drops the rest, making rarely-used skills unroutable by the LLM unless the user already knows the skill name. As more skills are added, this problem compounds. The fix is principled: skills that are always user-invoked don't need LLM routing and shouldn't occupy listing budget.

## Proposed Solution

Add `disable-model-invocation: true` to the YAML frontmatter of each operational skill's `SKILL.md`.

**Skills to tag (always user-invoked, never need LLM routing):**
- `update` — explicit maintenance command
- `cleanup-loops` — explicit maintenance command
- `rename-loop` — explicit loop management
- `review-loop` — explicit loop audit
- `debug-loop-run` — explicit loop debugging
- `audit-loop-run` — explicit loop audit
- `issue-workflow` — quick reference card
- `analyze-history` — explicit analysis trigger
- `audit-docs` — explicit audit trigger
- `update-docs` — explicit update trigger
- `improve-claude-md` — explicit improvement trigger
- `map-dependencies` — explicit dependency analysis
- `audit-issue-conflicts` — explicit conflict audit
- `audit-claude-config` — explicit config audit
- `issue-size-review` — explicit planning review
- `workflow-automation-proposer` — pipeline step 3, invoked programmatically by `analyze-workflows`; requires step1/step2 output files to exist so blind LLM routing would fail

**Skills that MUST remain LLM-discoverable (natural language routing):**

- `capture-issue` — Primary discovery path. Users say "log this bug", "capture what we just found", "track this issue" without knowing the command name. LLM routing is the intended entry point.
- `manage-issue` — Core implementation entry point. Users say "implement FEAT-123", "fix BUG-042", "let's work on this issue" — the LLM must route natural implementation requests here.
- `configure` — Settings are requested naturally: "change my test command", "update my scan settings", "set the source directory". Users have no reason to know `/ll:configure` by name.
- `init` — One-time onboarding case: new users say "set up little-loops for this project", "initialize ll", "bootstrap the config". They won't know the explicit command; discoverable routing is essential here.
- `go-no-go` — Adversarial review is triggered conversationally: "should we implement this?", "is this worth doing?", "review this issue before we start". The "go/no-go" terminology is jargon users learn after, not before, routing.
- `confidence-check` — Pre-implementation assessment expressed naturally: "is this ready to implement?", "am I ready to start?", "how confident are we?". Conversational trigger, not a typed command.
- `wire-issue` — Wiring gaps are described, not named: "this issue is missing its integration map", "what files does this touch?", "fill in the wiring". Users articulate the gap; LLM routes to the remedy.
- `format-issue` — Template correction is natural language: "fix the format of this issue", "this issue doesn't match the template", "reformat ENH-1394". Users won't know a dedicated format command exists.
- `create-loop` — Automation requests arrive as goals: "automate X", "create a loop to keep Y under Z", "set up a recurring task". LLM routing connects the intent to the FSM-based skill.
- `create-eval-from-issues` — Eval generation is requested concisely: "generate an eval for FEAT-123", "create an eval harness for these issues". While technical, the trigger is natural enough that blind invocation would fail; LLM routing provides the bridge.
- `product-analyzer` — Product analysis is framed as questions: "analyze our product gaps", "check feature coverage against our goals", "evaluate the business value of the backlog". Requires routing from goal language to skill.
- `decide-issue` — Decision resolution is conversational: "decide which option to use for ENH-123", "pick the best implementation", "resolve the open decision". Triggered naturally when an issue has competing options (`decision_needed: true`), which the user may not inspect directly.

**Note — commands are excluded:** `audit-architecture`, `cleanup-worktrees`, and `tradeoff-review-issues` all live in `commands/` and have no `SKILL.md`. The `disable-model-invocation` frontmatter flag is a skill-level field; it is inapplicable to commands. These are excluded from this tracking list entirely.

## Implementation Steps

1. For each skill in the "to tag" list above, open `skills/<name>/SKILL.md`
2. Add `disable-model-invocation: true` to the YAML frontmatter block (or create frontmatter if absent)
3. After all edits, run `/doctor` to verify the truncation warning is gone
4. Run `/skills` to confirm tagged skills still appear in the available list

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add frontmatter flag
- `skills/cleanup-loops/SKILL.md` — add frontmatter flag
- `skills/rename-loop/SKILL.md` — add frontmatter flag
- `skills/review-loop/SKILL.md` — add frontmatter flag
- `skills/debug-loop-run/SKILL.md` — add frontmatter flag
- `skills/audit-loop-run/SKILL.md` — add frontmatter flag
- `skills/issue-workflow/SKILL.md` — add frontmatter flag
- `skills/analyze-history/SKILL.md` — add frontmatter flag
- `skills/audit-docs/SKILL.md` — add frontmatter flag
- `skills/update-docs/SKILL.md` — add frontmatter flag
- `skills/improve-claude-md/SKILL.md` — add frontmatter flag
- `skills/map-dependencies/SKILL.md` — add frontmatter flag
- `skills/audit-issue-conflicts/SKILL.md` — add frontmatter flag
- `skills/audit-claude-config/SKILL.md` — add frontmatter flag
- `skills/issue-size-review/SKILL.md` — add frontmatter flag
- `skills/workflow-automation-proposer/SKILL.md` — add frontmatter flag (pipeline step, not user-facing)

### Dependent Files (Callers/Importers)
- N/A — frontmatter flag is read by Claude Code harness, not by project code

### Similar Patterns
- N/A — this is a novel field in this project; no existing examples to follow

### Tests
- N/A — no automated test for this; verification is `/doctor` output

### Documentation
- `CONTRIBUTING.md` — add note that operational skills use this flag (covered by ENH-1395)
- `.claude/CLAUDE.md` — no change needed

### Configuration
- N/A

## Success Metrics

- `/doctor` no longer reports skill-description truncation (currently 23 dropped per session)
- Total skill listing footprint drops from ~1.4% to ~0.6% of the context budget
- All tagged skills remain invocable by explicit `/ll:<name>` typing (manual smoke check)
- Skills in the "MUST remain LLM-discoverable" list still appear in `/skills` and are routable from natural-language prompts

## Scope Boundaries

Explicitly **out of scope**:
- Changing any skill's behavior, prompt, or logic — frontmatter flag only
- Tagging skills in the "MUST remain LLM-discoverable" list (those require natural-language routing)
- Modifying commands (e.g., `audit-architecture`) — `disable-model-invocation` is a skill-level frontmatter field and does not apply to `commands/*.md`
- Introducing a new mechanism for budget control beyond Claude Code's existing `disable-model-invocation` flag
- Documentation updates to `CONTRIBUTING.md` describing the convention (tracked separately in ENH-1395)
- Automated linting/CI to enforce which skills carry the flag

## Impact

- **Priority**: P3 — active session-quality issue; truncation happens every session
- **Effort**: Low — frontmatter edits only, 16 files
- **Risk**: Very low — flag removes descriptions from LLM listing; skills remain fully functional
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `ux`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 86/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 41/100 → LOW

### Concerns
- `skills/cleanup-worktrees/SKILL.md` does not exist — `cleanup-worktrees` lives at `commands/cleanup-worktrees.md` (a command, not a skill). The issue explicitly excludes `audit-architecture` for the same reason; skip this entry likewise. Effective scope is 16 SKILL.md files, not 18.
- `skills/tradeoff-review-issues/SKILL.md` does not exist — `tradeoff-review-issues` lives at `commands/tradeoff-review-issues.md` (a command). Same exclusion rule applies.

### Outcome Risk Factors
- No test harness: SKILL.md frontmatter changes have no automated validation — wrong field name or format will only surface at runtime via manual `/doctor` run; verify exact field spelling against Claude Code harness docs before committing edits
- Wide change surface without verification grep: 16 files to edit with no specified verification command; add a completeness check after implementation (e.g., `grep -rl "disable-model-invocation" skills/ | wc -l` should return 16)
- `disable-model-invocation` field has no existing usage in this codebase — field name and behavior unconfirmed locally; strongly recommend running `/doctor` before and after to confirm the warning clears

## Resolution

Added `disable-model-invocation: true` to the YAML frontmatter of all 16 operational skills. Each file received the flag immediately after its `description:` line. Completeness check: `grep -rl "disable-model-invocation" skills/ | wc -l` returns 16.

## Status

**Done** | Created: 2026-05-09 | Completed: 2026-05-11 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-11T04:42:41 - `d8d12a0e-5ca4-4480-917f-2297fc8753ca.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `a5252305-eff8-4e07-9ef5-ead70b4aad16.jsonl`
- `/ll:format-issue` - 2026-05-11T04:28:22 - `3ceb5948-bbad-469f-bb99-a8277556d87a.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`
