---
id: FEAT-1316
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-01
discovered_by: issue-size-review
blocked_by: [FEAT-1315]
parent: FEAT-1263
related: [FEAT-1315]
confidence_score: 80
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
missing_artifacts: true
size: Very Large
---

# FEAT-1316: SessionStart Inject — Documentation Updates

## Summary

Update all documentation touchpoints that become stale after FEAT-1315 ships `session-start-inject.sh`. Covers 6 documentation files, `commands/handoff.md` behavior text, and `skills/configure/areas.md` hook table.

## Parent Issue

Decomposed from FEAT-1263: SessionStart Context Injector (`session-start-inject.sh`)

## Depends On

FEAT-1315 must be complete before this issue is worked (docs reference the shipped implementation).

## Acceptance Criteria

- `docs/ARCHITECTURE.md` directory structure listing includes `session-start-inject.sh`
- `docs/guides/SESSION_HANDOFF.md` updated in three places: flow diagram, `## Files` table, `### Auto-Detect on Session Start` section
- `docs/reference/CONFIGURATION.md` `### continuation` section clarifies `auto_detect_on_session_start` vs active injection
- `commands/handoff.md` `### 4. Output Handoff Signal` marks "Run /ll:resume" as optional/automatic
- `docs/reference/COMMANDS.md` `/ll:resume` entry mentions the automatic injection path
- `skills/configure/areas.md` hook table (~line 861) lists `session-start-inject.sh` as second SessionStart entry

## Implementation

### `docs/ARCHITECTURE.md`

Update `## Directory Structure` to include `session-start-inject.sh` alongside `session-start.sh` in the `hooks/scripts/` listing.

### `docs/guides/SESSION_HANDOFF.md`

Three locations:

1. **`## How It Works` flow diagram** — add a new step showing automatic context injection via the SessionStart hook (currently the diagram omits this step)
2. **`## Files` table (line ~373)** — add row for `.ll/ll-session-injected` sentinel (created by hook, cleared by session-cleanup.sh)
3. **`### Auto-Detect on Session Start` (~line 329)** — rewrite to reflect active injection: Claude now *receives* context via `additionalContext` rather than passively detecting the prompt file

### `docs/reference/CONFIGURATION.md`

**`### continuation` at line 387**: Clarify relationship between `auto_detect_on_session_start` (the old passive flag) and the new active injection behavior introduced by `session-start-inject.sh`. Note that when the hook fires, `auto_detect_on_session_start` is superseded.

### `commands/handoff.md`

**`### 4. Output Handoff Signal` at line 189**: Change "Run /ll:resume" from a required step 2 to "optional — context will be automatically injected on next session start if `session-start-inject.sh` is registered." Keep the manual run as a fallback option.

### `docs/reference/COMMANDS.md`

**`## Session Management / /ll:resume` at line 436**: Add note that automatic injection via SessionStart hook preempts manual resume in normal operation; `/ll:resume` remains available as a manual override or for inspection.

### `skills/configure/areas.md`

**Hardcoded hook table (~line 861)**: Add `session-start-inject.sh` as a second SessionStart entry alongside the existing `session-start.sh` entry.

## Files to Modify

- `docs/ARCHITECTURE.md` — directory structure listing
- `docs/guides/SESSION_HANDOFF.md` — 3 locations (flow diagram, Files table, Auto-Detect section)
- `docs/reference/CONFIGURATION.md` — `### continuation` at ~line 387
- `commands/handoff.md` — `### 4. Output Handoff Signal` at ~line 189
- `docs/reference/COMMANDS.md` — `/ll:resume` entry at ~line 436
- `skills/configure/areas.md` — hook table at ~line 861

## Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the codebase on 2026-05-01:_

### Verified Anchors

All file paths and line references in this issue have been verified against the current codebase:

- `docs/ARCHITECTURE.md:92-97` — `hooks/scripts/` directory listing; `session-start.sh` is at line 95. Insert `session-start-inject.sh` as a sibling immediately above (line 95) so the listing remains alphabetically sorted (`session-cleanup.sh` → `session-start-inject.sh` → `session-start.sh`).
- `docs/guides/SESSION_HANDOFF.md`:
  - Line 86–104: `### Interactive Sessions` flow diagram (the "How It Works" diagram referenced by the issue) — insert the new injection step between the existing line 101 (`/ll:handoff writes .ll/ll-continue-prompt.md`) and line 103 (`Start new session → /ll:resume → Continue working`); the new line should describe `SessionStart hook auto-injects continue prompt as additionalContext`. Note: ToC anchor `[How It Works](#how-it-works)` at line 13 already covers this.
  - Line 329–331: `### Auto-Detect on Session Start` section — single paragraph; rewrite to clarify that `auto_detect_on_session_start` is the legacy passive flag (prints a notice prompting `/ll:resume`), while the new `session-start-inject.sh` hook performs *active* injection via `additionalContext`. Also update the matching ToC entry (line 22) and the `### Configuration Reference` row at line 314.
  - Line 373–377: `## Files` table — currently lists `.ll/ll-continue-prompt.md`, `.ll/ll-context-state.json`, `.ll/ll-session-state.json`. Add a new row for `.ll/ll-session-injected` (sentinel — created by `session-start-inject.sh`, cleared by `session-cleanup.sh` Stop hook).
  - Line 499 (`## Integration` / Stop hook bullet): currently mentions `.ll/ll-context-state.json` and `.ll/ll-session-state.json` cleanup; this bullet should be extended to include `.ll/ll-session-injected` so the cleanup contract documented here matches FEAT-1315's `session-cleanup.sh` change.
- `docs/reference/CONFIGURATION.md`:
  - Line 387–399: `### continuation` section with table; `auto_detect_on_session_start` row is at line 394. Add a follow-up paragraph after the table (after line 399, before `### context_monitor` at line 401) that clarifies precedence: `session-start-inject.sh` (when registered) supersedes `auto_detect_on_session_start` because the hook injects context directly via `additionalContext` rather than printing a passive resume notice.
  - Line 114–120: `"continuation"` JSON example block — no change needed (the boolean key remains valid; semantics are documented in the prose update).
- `commands/handoff.md:189–204`: `### 4. Output Handoff Signal` block. The literal text "Run /ll:resume" is at line 201, inside the numbered list at lines 200–201 (`1. Start a new Claude Code session` / `2. Run /ll:resume`). Edit step 2 to read along the lines of: "Run `/ll:resume` (optional — context is automatically injected on next session start when `session-start-inject.sh` is registered; manual run remains available as a fallback or for inspection)".
- `docs/reference/COMMANDS.md:436–441`: `### /ll:resume` entry; only 6 lines (header + description + Arguments). Append a one-paragraph note after line 441 (before the next `---` separator at line 442) noting that automatic injection via the SessionStart hook preempts manual resume in normal operation.
- `skills/configure/areas.md:861`: hardcoded SessionStart row in the `Current Hook Configuration` reference table. Insert a sibling row immediately after line 861 with values: `[Plugin]`, `SessionStart`, `*`, `session-start-inject.sh`, `5s`, `[exists/MISSING]`. Match existing column alignment (verify with `cat -A` or by visual compare against neighboring rows).

### Pattern Sources

- **Sentinel-file documentation pattern**: `docs/guides/SESSION_HANDOFF.md:373-377` (Files table) and `docs/guides/SESSION_HANDOFF.md:499` (Stop hook integration bullet) are the canonical places where runtime artifact files (e.g., `.ll/ll-context-state.json`) are documented. New sentinel `.ll/ll-session-injected` should be documented in both places for symmetry.
- **Hook table row format** (`skills/configure/areas.md:860-867`): each row is `[Source] Event Matcher Script Timeout Status` — copy the column widths of neighboring rows when adding `session-start-inject.sh`.
- **Configuration precedence note**: `docs/reference/CONFIGURATION.md:401-403` (`### context_monitor` intro paragraph) shows the established style for short prose notes that follow a config table — model the `auto_detect_on_session_start` precedence note on that shape.

### Behavioral Note

`docs/guides/SESSION_HANDOFF.md:331` currently describes the Auto-Detect flag as printing a notice prompting `/ll:resume`. After FEAT-1315 ships, the `session-start.sh` script (the existing SessionStart hook, untouched by FEAT-1315) still implements the legacy passive notice, while the new `session-start-inject.sh` performs active injection. **Both hooks coexist** — the documentation must explain this without implying the old flag is removed.

## Integration Map

### Files to Modify

- `docs/ARCHITECTURE.md` — directory listing (line 95); **also** `### Context Monitor and Session Continuation` → `**Continuation Flow**:` numbered list (~line 942–965): add injection step between "Fresh session spawned" and "Work continues seamlessly"; add `.ll/ll-session-injected` to the `**Files**:` list in that section
- `docs/guides/SESSION_HANDOFF.md` — 4 locations (flow diagram ~line 102, ToC entry line 22, Auto-Detect section line 329–331, Files table line 373–377, Stop hook bullet line 499); the `### Configuration Reference` row at line 314 also benefits from a precedence note
- `docs/reference/CONFIGURATION.md` — append precedence paragraph after line 399 (in `### continuation` section)
- `commands/handoff.md` — line 200–201 (step 2 of "To continue in a new session" list)
- `docs/reference/COMMANDS.md` — line 436–441 (`/ll:resume` entry)
- `skills/configure/areas.md` — line 861 (hardcoded SessionStart row in `Current Hook Configuration` table); **also** line 509 (`## Area: continuation` → `### Round 1` → `false` option description currently reads "No, require manual /ll:resume" — update to note active injection fires regardless of this flag)
- `skills/init/interactive.md` — `## Round 9` (continuation auto-detect round) at line 514, `false` option label at line 530: currently "Manual /ll:resume required" — update to note that `session-start-inject.sh` injects context regardless of this flag setting [Wiring pass]

### Dependent Files (Callers/Importers)

None — this is a pure documentation issue. No code imports or invokes these markdown files. The `skills/configure/areas.md` table at line 855–873 is rendered by `/ll:configure` but the hardcoded sample is for display only (the live status table is generated by `skills/configure/SKILL.md` reading `hooks/hooks.json` directly).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1316_doc_wiring.py` — **new test file needed**, following the pattern in `scripts/tests/test_circuit_breaker_doc_wiring.py` and `scripts/tests/test_enh1268_doc_wiring.py`; assert presence of `session-start-inject.sh` in `docs/ARCHITECTURE.md`, `.ll/ll-session-injected` in `docs/guides/SESSION_HANDOFF.md`, and `session-start-inject.sh` in `skills/configure/areas.md`; use `PROJECT_ROOT = Path(__file__).parent.parent.parent` and file-level path constants per convention

No existing tests will break from these documentation changes (confirmed: `test_create_extension_wiring.py::TestConfigureAreasWiring::test_count_updated_to_16` asserts on "Authorize all 16" not the hook table; `test_hooks_integration.py::TestSessionStartValidation` tests `session-start.sh` behavior, not docs; `test_doc_counts.py` counts commands/agents/skills, unchanged here).

Two indirect verifications also apply:
- After FEAT-1315 ships and `session-start-inject.sh` is registered in `hooks/hooks.json`, `ll-verify-docs` (if run) should not flag any count discrepancies introduced by these doc changes.
- `ll-check-links` (markdown link checker) should pass on all modified files — the new content adds prose only, no new cross-doc links.

### Documentation Cross-References

- `docs/reference/CONFIGURATION.md:403` already cross-links to `docs/guides/SESSION_HANDOFF.md` from the `### context_monitor` section. The new precedence paragraph in `### continuation` should similarly cross-link to `docs/guides/SESSION_HANDOFF.md#auto-detect-on-session-start` for the expanded explanation.
- `commands/handoff.md` and `commands/resume.md` are siblings; FEAT-1315 already updates `commands/resume.md` for sentinel awareness. The `commands/handoff.md` step-2 update in this issue closes the cross-reference loop (handoff → optional resume).

### Configuration

No `config-schema.json` changes — `continuation.enabled` (line 488) and `continuation.prompt_expiry_hours` (line 520) are already defined; no new keys are introduced by this documentation update.

## Implementation Steps

1. Wait for FEAT-1315 to merge (ships `session-start-inject.sh`, registers it in `hooks/hooks.json`, adds sentinel cleanup, updates `.gitignore`, updates `commands/resume.md`).
2. Edit `docs/ARCHITECTURE.md`:
   - Line 95: add `session-start-inject.sh` row to the `hooks/scripts/` listing (alphabetical: after `session-cleanup.sh`, before `session-start.sh`).
   - `### Context Monitor and Session Continuation` section (~line 942–965): extend the `**Continuation Flow**:` numbered list to add injection step between "Fresh session spawned" and "Work continues seamlessly"; add `.ll/ll-session-injected` to the `**Files**:` list.
3. Edit `docs/guides/SESSION_HANDOFF.md`:
   - Insert new step in `### Interactive Sessions` flow diagram (between lines 101 and 103) describing automatic SessionStart injection.
   - Rewrite `### Auto-Detect on Session Start` (lines 329–331) to distinguish legacy passive detection from new active injection.
   - Add new row to `## Files` table (after line 377) for `.ll/ll-session-injected` sentinel.
   - Extend Stop hook bullet at line 499 to include sentinel cleanup.
   - Update `### Configuration Reference` row at line 314 with precedence note.
4. Edit `docs/reference/CONFIGURATION.md` — append precedence paragraph after line 399 (before `### context_monitor`).
5. Edit `commands/handoff.md` line 200–201 — soften step 2 to "optional" with hook-registered fallback wording.
6. Edit `docs/reference/COMMANDS.md` after line 441 — append one-line note about automatic injection preempting manual resume.
7. Edit `skills/configure/areas.md`:
   - After line 861: insert sibling SessionStart row for `session-start-inject.sh`, matching neighboring column alignment.
   - Line 509 (`## Area: continuation` → `false` option description): update "No, require manual /ll:resume" to note active injection fires regardless of this flag.
8. Edit `skills/init/interactive.md` — `## Round 9` continuation round (line 514), `false` option label at line 530: update "Manual /ll:resume required" to note that `session-start-inject.sh` injects context regardless of this flag value. [Wiring Phase]
9. Create `scripts/tests/test_feat1316_doc_wiring.py` — doc wiring test following the pattern in `test_circuit_breaker_doc_wiring.py`; assert `session-start-inject.sh` present in `docs/ARCHITECTURE.md`, `.ll/ll-session-injected` present in `docs/guides/SESSION_HANDOFF.md`, `session-start-inject.sh` present in `skills/configure/areas.md`. [Wiring Phase]
10. Verify with `ll-check-links docs/` (no broken links introduced) and visual diff review of each file.

## Scope Boundary

This issue covers only documentation updates. No functional code changes. The hook implementation, hook registration, sentinel cleanup, `.gitignore`, and test coverage are all in FEAT-1315.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- **2-hop blocking dependency**: FEAT-1315 (`status: open`) is itself blocked by FEAT-1156 and FEAT-1116 (both open). Implementation Step 1 explicitly states "Wait for FEAT-1315 to merge." This issue cannot begin until the full chain resolves.

### Outcome Risk Factors
- **Wiring test does not yet exist**: `scripts/tests/test_feat1316_doc_wiring.py` is planned (Step 9) but not yet created. Pattern is well-established (`test_circuit_breaker_doc_wiring.py`, `test_enh1268_doc_wiring.py`), so low risk to author — but omitting it leaves 5 of 8 modified files without automated validation.
- **Breadth of edit surface**: 13+ discrete edit locations across 8 files. `SESSION_HANDOFF.md` alone has 5 locations and `ARCHITECTURE.md` has 2. Risk is missing one location during implementation.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-02T03:27:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2937f5c9-2552-45c5-b256-0d66c34e6599.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1d63728-833b-4fbb-adfc-a9a0091b6043.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:21:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc7ce5f5-10a3-4c98-9d28-4e599e257206.jsonl`
- `/ll:wire-issue` - 2026-05-02T03:15:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f03a8600-2bea-4a23-a20e-ea3e3ba15965.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:09:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05165ff1-ef3d-44ad-86a8-76bfadec512b.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29f10429-7b81-4ece-9545-cd5da490acdd.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f03a8600-2bea-4a23-a20e-ea3e3ba15965.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-01
- **Reason**: Issue too large for single session (score 11/11 — 8 files, 10 implementation steps, 13+ discrete edit locations)

### Decomposed Into
- FEAT-1317: SessionStart Inject — Reference Documentation Updates
- FEAT-1318: SessionStart Inject — Session Handoff Guide Updates
- FEAT-1319: SessionStart Inject — Command/Skill Updates and Wiring Test
