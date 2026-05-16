---
id: BUG-1416
type: BUG
priority: P2
status: done
captured_at: '2026-05-10T15:06:51Z'
completed_at: '2026-05-10T17:56:21Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1416: decide-issue --auto asks interactive questions instead of resolving provisional decisions

## Summary

`/ll:decide-issue ENH-1390 --auto` left `decision_needed: true` unchanged and asked an interactive question ("Want me to edit Step 11?") instead of acting. The issue had a provisional `(e.g., completed_at:)` marker in Step 11 — a single named approach in parenthetical form — which `--auto` mode should lock in and clear without user interaction.

## Current Behavior

When `/ll:decide-issue ISSUE_ID --auto` is run on an issue with inline provisional decision language (`(e.g., ...)` style) and no formal `Option A / Option B` blocks are present, the skill:
- Leaves `decision_needed: true` unchanged
- Asks an interactive question (e.g., "Want me to edit Step N?")
- Does not resolve or lock in the provisional approach

## Root Cause

Phase 3 of `skills/decide-issue/SKILL.md` exits when `OPTIONS = 0` (no formal `Option A / Option B` blocks found). It has no fallback for provisional-language patterns (`(e.g., ...)`, `TBD`, `"fundamental rethink"`) that name a clear approach inline. In `--auto` mode this causes the skill to fall through to interactive output.

**Anchor:** Phase 3 in `skills/decide-issue/SKILL.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Phase 3 scope is limited to `## Proposed Solution`**: the option scan only reads the Proposed Solution section; ENH-1390's provisional decision was in Implementation Steps (Step 11), so Phase 3 never saw it — Phase 3b must scan ALL sections
- **Interactive question is emergent, not explicit**: `skills/decide-issue/SKILL.md` contains no `AskUserQuestion` call anywhere; the conversational "Want me to edit Step N?" emerges because the LLM hits the `OPTIONS = 0` clean exit while `decision_needed: true` is still set and no further instructions exist — Phase 3b must supply explicit `--auto` instructions for this path to eliminate the gap
- **`ll-issues set-flag` does not exist**: the `ll-issues` CLI (`scripts/little_loops/cli/issues/__init__.py`) registers `check-flag` (read-only) but has no `set-flag` subcommand; Phase 3b must write `decision_needed: false` via the Edit tool inline `---` block replacement, following the same pattern as Phase 7b of `skills/decide-issue/SKILL.md`

## Expected Behavior

In `--auto` mode, when no formal option blocks are found, the skill should scan all sections for provisional decision language and, if a single clear approach is named, lock it in (edit the issue text to make it declarative, run `ll-issues set-flag ISSUE_ID decision_needed false`) and report what was resolved. If no clear winner can be inferred, record it as unresolvable and exit — no interactive questions in `--auto` mode.

## Steps to Reproduce

1. Create/find an issue where a step uses `(e.g., field_name:)` instead of a formal `Option A / B` block, and `decision_needed: true` is set.
2. Run `/ll:decide-issue ISSUE_ID --auto`.
3. Observe: skill asks "Want me to edit Step N?" instead of acting.

## Impact

`--auto` mode is broken for issues with inline provisional decisions. In `ll-loop run autodev`, this causes `rerun_confidence_after_decide` to see an unchanged score, which (before ENH-1415) dead-ends the loop. Even with ENH-1415 applied, it wastes a decide invocation and routes unnecessarily to size review.

- **Priority**: P2 — breaks `--auto` mode for a common provisional-decision pattern; impacts autodev loop reliability
- **Effort**: Small — targeted addition of one sub-phase to an existing skill file, no new infrastructure
- **Risk**: Low — new Phase 3b only activates in `--auto` mode when `OPTIONS = 0`; interactive behavior untouched
- **Breaking Change**: No

## Implementation Steps

Extend **Phase 3** of `skills/decide-issue/SKILL.md` with a new sub-phase that activates only in `--auto` mode when `OPTIONS = 0`:

> **Phase 3b — Inline decision scan (AUTO_MODE only, triggers when OPTIONS = 0)**
>
> Search ALL sections of the issue for provisional decision language:
> - `(e.g., ...)` where the parenthetical names a concrete approach
> - `"fundamental rethink"` / `"must be replaced with"` followed by a concrete proposal
> - Inline `TBD` in a design context (not a research gap)
>
> For each candidate:
> 1. Read surrounding context to determine if one approach is clearly superior (stated, not merely listed).
> 2. If a clear winner is identifiable:
>    - Edit the issue text to make the approach definitive (remove `e.g.`/parenthetical qualifier; convert provisional wording to declarative).
>    - Run `ll-issues set-flag ISSUE_ID decision_needed false`.
>    - Report what was resolved and why.
> 3. If no clear winner (genuinely ambiguous): record unresolvable in summary, leave `decision_needed: true`, and exit — **no interactive questions**.

The ENH-1390 case is the canonical example: Step 11 had `(e.g., completed_at: frontmatter field)` — one named approach in a provisional wrapper. Phase 3b should lock in `completed_at:` as the definitive field name.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correct frontmatter write mechanism**: replace `ll-issues set-flag ISSUE_ID decision_needed false` (non-existent) with Edit tool inline `---` block replacement; see Phase 7b of `skills/decide-issue/SKILL.md` for the exact model and `skills/confidence-check/SKILL.md` Phase 4.6 for the canonical declarative flag-write pattern without AskUserQuestion
- **Scan all sections, not just Proposed Solution**: Phase 3 already restricts to `## Proposed Solution`; Phase 3b must search ALL sections (Implementation Steps, Summary, etc.) since ENH-1390's provisional language was in Step 11
- **New test class needed**: add `TestPhase3bInlineProvisionalScan` to `scripts/tests/test_decide_issue_skill.py` covering: (a) Phase 3b section documented in SKILL.md, (b) provisional patterns `(e.g., ...)` / `TBD` / `"fundamental rethink"` enumerated, (c) single-winner path (edit + clear `decision_needed`) documented, (d) ambiguous path (unresolvable log, no AskUserQuestion) documented, (e) `AUTO_MODE=true` + `OPTIONS=0` guard explicitly conditioned
- **Broader autodev impact**: `scripts/little_loops/issue_manager.py:718` and `scripts/little_loops/parallel/worker_pool.py:376` both invoke decide-issue as a Python decision gate and continue to implementation even on failure (no hard stop) — Phase 3b failure mode should match: log unresolvable, leave `decision_needed: true`, exit cleanly without blocking

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/reference/COMMANDS.md` — in the `### /ll:decide-issue` section, update the **Frontmatter write-back** sentence to cover the Phase 3b provisional-scan resolution path (not only the formal-option path)
2. Add `TestPhase3bInlineProvisionalScan` to `scripts/tests/test_decide_issue_skill.py` — follow `TestDecisionNeededFlagWriteBack` pattern from `test_confidence_check_skill.py`; assert: Phase 3b heading exists, `AUTO_MODE` guard documented, provisional patterns enumerated, single-winner write-back documented, `AskUserQuestion` absent inside Phase 3b

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — Phase 3 (add Phase 3b sub-phase for inline provisional scan)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — `run_decide` and `rerun_confidence_after_decide` states depend on correct `--auto` behavior

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_decision_needed` gate reads `decision_needed` via `ll-issues check-flag`; Phase 3b's flag write flows correctly through this gate [Agent 1]
- `scripts/little_loops/loops/recursive-refine.yaml` — `check_decision_needed` gate uses `grep -q "decision_needed: true"`; Phase 3b's Edit-tool write to `decision_needed: false` causes grep to not match as intended [Agent 1]
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` (~line 718) invokes `decide-issue --auto` when `info.decision_needed is True`; no code change needed, behavior improves automatically [Agent 1]
- `scripts/little_loops/parallel/worker_pool.py` — `_process_issue_impl()` (~line 376) invokes via `get_decide_command(issue_id)`; no code change needed [Agent 1]

### Similar Patterns
- `skills/decide-issue/SKILL.md` Phase 7b — existing Edit-tool inline `---` block replacement (model for Phase 3b's `decision_needed: false` write)
- `skills/confidence-check/SKILL.md` Phase 4.6 — declarative `decision_needed: true` set without AskUserQuestion (same approach Phase 3b should use for the `false` case)
- `skills/issue-size-review/SKILL.md` Auto Mode Behavior — pattern for silent exit with status log when result is ambiguous (no AskUserQuestion)

### Tests
- `scripts/tests/test_decide_issue_skill.py` — existing structural tests; no test class covers Phase 3b auto-mode + provisional language; add `TestPhase3bInlineProvisionalScan`
- `scripts/tests/test_issue_manager.py` — `TestDecisionNeededGate`: mocked tests for the Python decision gate that calls decide-issue (not the skill itself)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — `TestWorkerPoolDecisionNeededGate`: verifies `_process_issue_impl()` invokes decide-issue when `decision_needed=True`; not broken by Phase 3b but confirms the call chain [Agent 3]
- `scripts/tests/test_orchestrator.py` — `TestDecisionNeededRouting`: dispatch-layer tests; unaffected by Phase 3b [Agent 3]
- `scripts/tests/test_confidence_check_skill.py` — `TestDecisionNeededFlagWriteBack`: reference template for `TestPhase3bInlineProvisionalScan` — use its `_phase_text()` helper pattern and `AskUserQuestion` prohibition assertion style [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:decide-issue` section: **Frontmatter write-back** sentence currently implies `decision_needed: false` is only written after formal-option annotation; add coverage of the Phase 3b provisional-scan resolution path [Agent 2]

### Configuration
- N/A

## Related

- `skills/decide-issue/SKILL.md` — Phase 3 (OPTIONS check)
- `scripts/little_loops/loops/autodev.yaml` — `run_decide`, `rerun_confidence_after_decide`
- `.issues/enhancements/ENH-1390` — original issue where this manifested
- ENH-1415 — companion fix: autodev loop routing after decide fails outcome

## Labels

`bug`, `decide-issue`, `auto-mode`, `captured`

---

## Resolution

Fixed in `skills/decide-issue/SKILL.md` by adding Phase 3b — an inline provisional decision scan that activates only in `--auto` mode when `OPTIONS = 0`. Phase 3b scans all issue sections (not just `## Proposed Solution`) for provisional language patterns (`(e.g., ...)`, `TBD`, `"must be replaced with"`), resolves a single clear winner without user interaction, and writes `decision_needed: false` via the Edit tool inline `---` block replacement. When no clear winner is found, it exits cleanly with a log message instead of falling through to interactive output.

**Changes made:**
- `skills/decide-issue/SKILL.md` — Option Count Check updated to branch on `AUTO_MODE` when `OPTIONS = 0`; new Phase 3b section added with provisional patterns, resolution logic, idempotency guard, and explicit no-interactive-question rule
- `scripts/tests/test_decide_issue_skill.py` — `TestPhase3bInlineProvisionalScan` class added (8 assertions covering heading, guard, patterns, write-back, ambiguous exit, and AskUserQuestion absence)
- `docs/reference/COMMANDS.md` — "Frontmatter write-back" sentence updated to document Phase 3b path

## Status

Completed

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T17:56:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fb749c7-2b66-49d3-9aa3-b2f60fb27509.jsonl`
- `/ll:manage-issue` - 2026-05-10T17:56:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fb749c7-2b66-49d3-9aa3-b2f60fb27509.jsonl`
- `/ll:ready-issue` - 2026-05-10T17:48:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c94e8a9-aa8e-4703-b2bd-c9c8fded7b56.jsonl`
- `/ll:confidence-check` - 2026-05-10T17:44:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5934faa-d742-411a-abba-c8d29afc864b.jsonl`
- `/ll:wire-issue` - 2026-05-10T17:31:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff4254f7-df99-4fc7-838e-192f8779492e.jsonl`
- `/ll:refine-issue` - 2026-05-10T15:16:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`
- `/ll:format-issue` - 2026-05-10T15:11:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7801123-27a3-4b5b-aa78-0beb3e563702.jsonl`
- `/ll:capture-issue` - 2026-05-10T15:06:51Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
