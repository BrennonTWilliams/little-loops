---
id: FEAT-1317
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-05-01
discovered_by: issue-size-review
blocked_by: [FEAT-1315]
parent: FEAT-1316

size: Very Large
confidence_score: 80
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
relates_to: ['FEAT-1315', 'FEAT-1316', 'FEAT-1318', 'FEAT-1319']
---

# FEAT-1317: SessionStart Inject — Reference Documentation Updates

## Summary

Update three reference documentation files after FEAT-1315 ships `session-start-inject.sh`: the directory structure in `docs/ARCHITECTURE.md`, the continuation section in `docs/reference/CONFIGURATION.md`, and the `/ll:resume` entry in `docs/reference/COMMANDS.md`.

## Parent Issue

Decomposed from FEAT-1316: SessionStart Inject — Documentation Updates

## Depends On

FEAT-1315 must be complete before this issue is worked (docs reference the shipped implementation).

## Acceptance Criteria

- `docs/ARCHITECTURE.md` directory structure listing includes `session-start-inject.sh` alphabetically after `session-cleanup.sh` and before `session-start.sh`
- `docs/ARCHITECTURE.md` `### Context Monitor and Session Continuation` `**Continuation Flow**` list includes injection step; `**Files**` list includes `.ll/ll-session-injected`
- `docs/reference/CONFIGURATION.md` `### continuation` section has a follow-up paragraph after the table clarifying that `session-start-inject.sh` supersedes `auto_detect_on_session_start` when registered
- `docs/reference/COMMANDS.md` `/ll:resume` entry has a note that automatic injection via SessionStart hook preempts manual resume in normal operation

## Implementation Steps

1. Wait for FEAT-1315 to merge.
2. Edit `docs/ARCHITECTURE.md`:
   - Line 95: insert `session-start-inject.sh` row to the `hooks/scripts/` listing (alphabetical: after `session-cleanup.sh`, before `session-start.sh`).
   - `### Context Monitor and Session Continuation` section (~line 942–965): extend `**Continuation Flow**:` numbered list to add injection step between "Fresh session spawned" and "Work continues seamlessly"; add `.ll/ll-session-injected` to the `**Files**:` list.
3. Edit `docs/reference/CONFIGURATION.md` — append precedence paragraph after line 399 (before `### context_monitor` at line 401). The paragraph should note that `session-start-inject.sh` (when registered) supersedes `auto_detect_on_session_start` because the hook injects context directly via `additionalContext` rather than printing a passive resume notice. Cross-link to `docs/guides/SESSION_HANDOFF.md#auto-detect-on-session-start`.
4. Edit `docs/reference/COMMANDS.md` after line 441 (`/ll:resume` entry, 6 lines): append one-paragraph note that automatic injection via the SessionStart hook preempts manual resume in normal operation; `/ll:resume` remains available as a manual override or for inspection.

## Files to Modify

- `docs/ARCHITECTURE.md` — directory listing (line 95) and Continuation Flow section (~line 942–965)
- `docs/reference/CONFIGURATION.md` — `### continuation` section, after line 399
- `docs/reference/COMMANDS.md` — `/ll:resume` entry at lines 436–441
- `scripts/tests/test_feat1317_doc_wiring.py` — new test file; follow pattern in `scripts/tests/test_enh1138_doc_wiring.py`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1317_doc_wiring.py` — **new** doc wiring test; three test classes following `scripts/tests/test_enh1138_doc_wiring.py` pattern:
  - `TestArchitectureWiring` — asserts `session-start-inject.sh` appears in the `hooks/scripts/` listing section and `.ll/ll-session-injected` appears in the `**Files**` list of `### Context Monitor and Session Continuation`
  - `TestConfigurationWiring` — asserts precedence/supersedes language referencing `session-start-inject.sh` appears in the `### continuation` section of `docs/reference/CONFIGURATION.md`
  - `TestCommandsWiring` — asserts the `/ll:resume` section of `docs/reference/COMMANDS.md` contains `session-start-inject.sh` (or `ll-session-injected`) sentinel language

## Codebase Anchors

- `docs/ARCHITECTURE.md:92-97` — `hooks/scripts/` directory listing; `session-start.sh` is at line 95
- `docs/ARCHITECTURE.md:~942-965` — `### Context Monitor and Session Continuation` section with `**Continuation Flow**` list and `**Files**` list
- `docs/reference/CONFIGURATION.md:387-399` — `### continuation` section with `auto_detect_on_session_start` row at line 394; append after line 399 before `### context_monitor` at line 401
- `docs/reference/CONFIGURATION.md:401-403` — `### context_monitor` intro paragraph (model new precedence note on this shape)
- `docs/reference/COMMANDS.md:436-441` — `### /ll:resume` entry (header + description + Arguments); append before `---` separator at line 442

## Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the current codebase on 2026-05-01:_

### Verified Anchors

All line references in this issue have been verified against the current codebase:

- `docs/ARCHITECTURE.md:90-98` — `hooks/scripts/` listing currently has 7 scripts plus `lib/` subdirectory; `session-cleanup.sh` is at line 94, `session-start.sh` at line 95, so the new entry inserts as a new line between them (alphabetical order preserved)
- `docs/ARCHITECTURE.md:942-948` — `**Continuation Flow**:` numbered list (5 items, ending at line 948); item 4 is "Fresh session spawned with continuation prompt", item 5 is "Work continues seamlessly from saved state" — inject the new step between them (new item becomes step 5; old step 5 renumbers to 6)
- `docs/ARCHITECTURE.md:961-965` — `**Files**:` list (4 items); existing entries are `hooks/prompts/continuation-prompt-template.md`, `.ll/ll-context-state.json`, `.ll/ll-continue-prompt.md`, `subprocess_utils.py`. Add `.ll/ll-session-injected` after `.ll/ll-continue-prompt.md` (line 963) to keep sentinel adjacent to the prompt it gates
- `docs/reference/CONFIGURATION.md:387-399` — `### continuation` section (table at lines 391–399); `auto_detect_on_session_start` row is at line 394 (confirmed); blank line 400; `### context_monitor` heading at line 401 — append the precedence paragraph between line 399 and the existing blank line 400
- `docs/reference/COMMANDS.md:436-441` — `### /ll:resume` entry: header line 436, body line 437, blank line 438, "**Arguments:**" line 439, blank line 440, argument bullet line 441; `---` separator at line 442 — append the SessionStart preemption note as a new paragraph between line 441 and line 442
- `docs/guides/SESSION_HANDOFF.md` — exists with `#auto-detect-on-session-start` anchor (confirmed at line 22 of the TOC); the cross-link in CONFIGURATION.md will resolve

### Companion Hook Reference

When writing the precedence paragraph in `CONFIGURATION.md`, note that `auto_detect_on_session_start` is the *passive* mechanism (prints a notice into the conversation that Claude can choose to read), while `session-start-inject.sh` is the *active* mechanism (emits `additionalContext` via the SessionStart hook protocol so the directive is delivered authoritatively). This framing matches the motivation in FEAT-1315 (parent issue: see `FEAT-1315 ## Motivation` lines 31–33).

### Wording Anchor for `/ll:resume` Note

The note appended to the `/ll:resume` entry in `COMMANDS.md` should be consistent with the sentinel-aware behavior shipped in FEAT-1315's `commands/resume.md:43-50` change ("context already injected at session start"). Phrasing suggestion: *"In normal operation, the SessionStart hook (`session-start-inject.sh`) injects continuation context automatically. `/ll:resume` remains available as a manual override or for inspection — when invoked after automatic injection, it detects the `.ll/ll-session-injected` sentinel and reports that context was already injected rather than re-displaying the full prompt."*

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Create `scripts/tests/test_feat1317_doc_wiring.py` — doc wiring test with three test classes (`TestArchitectureWiring`, `TestConfigurationWiring`, `TestCommandsWiring`) following the pattern in `scripts/tests/test_enh1138_doc_wiring.py`; assert on the specific strings added by steps 2–4 above (e.g., `"session-start-inject.sh"` in the hooks/scripts listing, `"ll-session-injected"` in the Files list, supersedes language in CONFIGURATION.md, sentinel note in COMMANDS.md)

## Scope Boundary

This issue covers **only** the three reference docs listed in Files to Modify. Sibling documentation issues (do not duplicate work):
- FEAT-1318 — `docs/guides/SESSION_HANDOFF.md` updates (sibling)
- FEAT-1319 — `commands/`/`skills/` updates and CLAUDE.md wiring test (sibling)

This issue does NOT modify the `commands/resume.md` body (FEAT-1315 owns that) or the continuation prompt template (FEAT-1156/FEAT-1264 own that).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1315 is still open**: `session-start-inject.sh` does not yet exist. Step 1 of the implementation plan explicitly says "Wait for FEAT-1315 to merge." The acceptance criteria reference a file that must exist before docs can be verified.

## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:06 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:37:33 - `ea9b8888-aee4-4367-aecd-ef628a7ad191.jsonl`
- `/ll:wire-issue` - 2026-05-01T00:00:00 - `current.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:29:39 - `2d505f23-ba04-4111-b275-b786a56c1538.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `dba14921-b765-4d41-b830-b8e1511f2654.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `4a4f54c6-7e68-4068-b26b-79ed42e70c22.jsonl`

## Blocks

- FEAT-1319

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): FEAT-1317 claims ownership of the `config-schema.json:505-509` `auto_detect_on_session_start` description field update. FEAT-1318 flagged this field as "unscoped across siblings" — add updating that description to FEAT-1317's "Files to Modify" list. The description should note that `session-start-inject.sh` (when registered) supersedes `auto_detect_on_session_start` for active injection, while the old flag governs legacy passive detection in `session-start.sh`.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `docs/ARCHITECTURE.md`. The same file is also modified by FEAT-1158 (precompact handoff docs). No ordering dependency exists between these two issues. If worked concurrently, coordinate to avoid git merge conflicts in `docs/ARCHITECTURE.md`.

## Verification Notes

**Verdict**: DEFERRED (architecture supersession) — Verified 2026-05-14

This issue and its sibling series are **superseded by the hook-intent abstraction (FEAT-1116, completed)** and the follow-on series FEAT-1448–1460 (mostly completed). The implementation contracts in this file target `hooks/scripts/*.sh` shell scripts which are no longer the canonical hook layer.

Canonical pattern going forward:

- Python intent handlers under `scripts/little_loops/hooks/<intent>.py`
- Per-host adapters under `hooks/adapters/<host>/` (e.g., `claude-code/`, `opencode/`) that envelope host events into `LLHookEvent` and dispatch to `main_hooks()`
- Prompt text files under `hooks/prompts/` referenced from `hooks/hooks.json`

Parent epics are deferred: **FEAT-1113** (precompact auto-handoff) and **FEAT-1159** (session-event-capture + sessionstart-injection). The headless-mode rationale for FEAT-1113 explicitly notes the FSM signal path already provides automatic handoff.

**To resurrect**: rewrite implementation steps to author a new intent handler + adapter wiring rather than a `hooks/scripts/*.sh` script. Re-validate line anchors in referenced docs (`docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md`) which have shifted since the recent hook-intent doc commits.

Moving to `.issues/deferred/` mirroring parents FEAT-1113 / FEAT-1159.
