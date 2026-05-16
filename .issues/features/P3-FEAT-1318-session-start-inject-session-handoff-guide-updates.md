---
id: FEAT-1318
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-05-01
discovered_by: issue-size-review
blocked_by: [FEAT-1315]
parent: FEAT-1316

size: Medium
confidence_score: 86
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
relates_to: ['FEAT-1315', 'FEAT-1316', 'FEAT-1317', 'FEAT-1319']
---

# FEAT-1318: SessionStart Inject — Session Handoff Guide Updates

## Summary

Update `docs/guides/SESSION_HANDOFF.md` in five locations after FEAT-1315 ships `session-start-inject.sh`: flow diagram, ToC entry, Auto-Detect section rewrite, Files table, Stop hook bullet, and Configuration Reference row.

## Parent Issue

Decomposed from FEAT-1316: SessionStart Inject — Documentation Updates

## Depends On

FEAT-1315 must be complete before this issue is worked (docs reference the shipped implementation).

## Acceptance Criteria

- `docs/guides/SESSION_HANDOFF.md` `### Interactive Sessions` flow diagram includes new step: "SessionStart hook auto-injects continue prompt as additionalContext" (between lines 101 and 103)
- `### Auto-Detect on Session Start` section paragraph (line 331; heading at line 329) rewritten to distinguish legacy passive detection (`auto_detect_on_session_start`) from new active injection (`session-start-inject.sh`); makes clear both hooks coexist
- `## Files` table includes new row for `.ll/ll-session-injected` (created by `session-start-inject.sh`, cleared by `session-cleanup.sh` Stop hook)
- Stop hook bullet at line 499 extended to include `.ll/ll-session-injected` cleanup
- `### Configuration Reference` row at line 314 has precedence note

## Implementation Steps

1. Wait for FEAT-1315 to merge.
2. Edit `docs/guides/SESSION_HANDOFF.md`:
   - **Flow diagram** (lines 86–104, `### Interactive Sessions`): insert new step between existing line 101 (`/ll:handoff writes .ll/ll-continue-prompt.md`) and line 103 (`Start new session → /ll:resume → Continue working`): describe `SessionStart hook auto-injects continue prompt as additionalContext`.
   - **ToC entry** (line 22): update the `Auto-Detect on Session Start` ToC entry if its text changes.
   - **`### Auto-Detect on Session Start`** (paragraph at line 331; heading at line 329): rewrite single paragraph to reflect that `auto_detect_on_session_start` is currently a no-op flag (see Codebase Research Findings → "Auto-Detect Flag Is Unimplemented"), while `session-start-inject.sh` performs active injection via `additionalContext`. Both flag and hook coexist — do not imply the old flag is removed.
   - **`### Configuration Reference` row** (line 314): add precedence note for `auto_detect_on_session_start` vs active injection.
   - **`## Files` table** (after line 377): add new row for `.ll/ll-session-injected` sentinel (created by `session-start-inject.sh`, cleared by `session-cleanup.sh` Stop hook).
   - **Stop hook bullet** (line 499, `## Integration` section): extend to include `.ll/ll-session-injected` cleanup alongside existing `.ll/ll-context-state.json` and `.ll/ll-session-state.json`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Write `scripts/tests/test_feat1318_doc_wiring.py` — four test classes asserting the five planned edits landed correctly (flow diagram step, Auto-Detect section rewrite, Files table row, Stop hook bullet). Follow the `Path(__file__).parent.parent.parent / "docs" / "guides" / "SESSION_HANDOFF.md"` + `content.read_text()` + `assert "..." in content` pattern from `scripts/tests/test_enh1130_doc_wiring.py`.
4. After edits land, run `mkdocs build` (or confirm CI does it) — `site/guides/SESSION_HANDOFF/index.html` is a pre-built copy that will be stale until rebuilt. Note: the site already has pre-existing path staleness (`.claude/` instead of `.ll/` paths from ENH-896) independent of this issue.
5. Coordinate with FEAT-1317: `config-schema.json:493-496` `description` field is unscoped — see Configuration subsection in Integration Map.

## Files to Modify

- `docs/guides/SESSION_HANDOFF.md` — 5 locations (flow diagram insertion between lines 101 and 103 inside box at lines 89–104, ToC ~line 22, Auto-Detect paragraph at line 331 (heading at 329), Configuration Reference row ~line 314, Files table data rows at lines 375–377 (header at 373–374), Stop hook bullet line 499)

## Codebase Anchors

- `docs/guides/SESSION_HANDOFF.md:13` — ToC anchor `[How It Works](#how-it-works)`
- `docs/guides/SESSION_HANDOFF.md:22` — ToC entry for Auto-Detect section
- `docs/guides/SESSION_HANDOFF.md:86-104` — `### Interactive Sessions` flow diagram
- `docs/guides/SESSION_HANDOFF.md:314` — `### Configuration Reference` table row for `auto_detect_on_session_start`
- `docs/guides/SESSION_HANDOFF.md:329` — `### Auto-Detect on Session Start` heading
- `docs/guides/SESSION_HANDOFF.md:331` — Auto-Detect section paragraph (single line)
- `docs/guides/SESSION_HANDOFF.md:371` — `## Files` heading
- `docs/guides/SESSION_HANDOFF.md:373-374` — `## Files` table header + separator row
- `docs/guides/SESSION_HANDOFF.md:375-377` — `## Files` table data rows (`.ll/ll-continue-prompt.md`, `.ll/ll-context-state.json`, `.ll/ll-session-state.json`)
- `docs/guides/SESSION_HANDOFF.md:499` — Stop hook bullet in `## Integration` section

## Behavioral Note

`docs/guides/SESSION_HANDOFF.md:331` currently describes the Auto-Detect flag as printing a notice prompting `/ll:resume`. After FEAT-1315 ships, `session-start.sh` (existing SessionStart hook) still implements the legacy passive notice, while `session-start-inject.sh` performs active injection. Both coexist — the documentation must explain this without implying the old flag is removed.

> **Correction (see Codebase Research Findings → "Auto-Detect Flag Is Unimplemented" below):** the premise that `session-start.sh` implements a legacy passive notice is **incorrect**. The flag exists only in `config-schema.json` and documentation. The doc rewrite must reflect this reality — see the recommended rewrite shape below.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis on 2026-05-01:_

### Files to Modify
- `docs/guides/SESSION_HANDOFF.md` — 5 distinct edits at the verified anchors listed in `## Codebase Anchors`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1318_doc_wiring.py` — new test file; write 4 test classes asserting the 5 planned edits (see Wiring Phase steps)

### Dependent Files (Cross-Links / Sibling Docs)
- `docs/reference/CONFIGURATION.md` — owned by sibling FEAT-1317; cross-link from the rewritten `### Auto-Detect on Session Start` paragraph back to `CONFIGURATION.md` `### continuation`. Sibling FEAT-1317 already plans the reciprocal cross-link in the other direction (FEAT-1317 step 3 cross-links to `SESSION_HANDOFF.md#auto-detect-on-session-start`).
- `docs/ARCHITECTURE.md` — owned by sibling FEAT-1317; no edits required by this issue, but if the implementer encounters stale "Continuation Flow" wording while cross-referencing, defer to FEAT-1317.
- `docs/reference/COMMANDS.md` — owned by sibling FEAT-1317; no edits.
- `commands/handoff.md` — covered by sibling FEAT-1319; no edits in this issue.

### Producer Anchors (read-only — do not modify here)
- `hooks/scripts/session-start-inject.sh` — implementation lives here (created by FEAT-1315). All `### Auto-Detect on Session Start` rewrite text must accurately describe this script's behavior as specified in FEAT-1315 acceptance criteria.
- `hooks/scripts/session-cleanup.sh` — Stop hook; FEAT-1315 adds `.ll/ll-session-injected` cleanup here. The `## Integration` `Stop hook` bullet at line 499 must list this sentinel only **after** FEAT-1315 has actually wired it.
- `.gitignore` — `.ll/ll-session-injected` is added by FEAT-1315 (~line 84-92).
- `hooks/prompts/continuation-prompt-template.md` — section names referenced by the injected content (`## Intent`, `## Next Steps`, `## File Modifications`) are owned by FEAT-1156/FEAT-1264. The `### Files` row description should not over-specify content shape.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1318_doc_wiring.py` — **new test file to write** (no existing tests cover `SESSION_HANDOFF.md` content); follow pattern from `scripts/tests/test_enh1130_doc_wiring.py`. Four test classes to write:
  - `TestSessionHandoffFlowDiagram` — asserts `"additionalContext"` present in file content (flow diagram step)
  - `TestSessionHandoffAutoDetectSection` — asserts `"session-start-inject.sh"` and `"auto_detect_on_session_start"` both present
  - `TestSessionHandoffFilesTable` — asserts `".ll/ll-session-injected"` present
  - `TestSessionHandoffStopHookBullet` — asserts `".ll/ll-session-injected"` present in stop-hook context

Note: `ll-verify-docs` (`scripts/little_loops/verify_docs.py`) only checks file counts in `commands/`, `agents/`, `skills/` — it does not cover `SESSION_HANDOFF.md` prose or table rows.
Note: `ll-check-links` silently skips internal anchor validation (`is_internal_reference()` returns True without resolving headings) — run `ll-check-links docs/guides/SESSION_HANDOFF.md` as a smoke test but do not rely on it to catch broken anchors.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:493-496` — `auto_detect_on_session_start` `description` field currently reads `"Check for continuation prompt when session starts"`. FEAT-1318 rewrites `SESSION_HANDOFF.md` to mark this flag a no-op; the schema description will contradict the guide unless updated. **This gap is unscoped across all FEAT-1316 siblings** — coordinate with FEAT-1317 maintainer (reference doc updates) since updating a schema description string aligns with that issue's scope. If not handled by FEAT-1317, add a one-line edit to this issue's implementation: change description to `"Reserved for future use; currently a no-op — active injection is performed by session-start-inject.sh"`.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis on 2026-05-01:_

### Verified Anchors

All line references in this issue have been verified against `docs/guides/SESSION_HANDOFF.md` (516 lines total) on 2026-05-01:

- Line 22 — ToC entry `[Auto-Detect on Session Start](#auto-detect-on-session-start)` ✓
- Lines 86-104 — `### Interactive Sessions` flow diagram (ASCII box) ✓
- Line 101 — `/ll:handoff writes .ll/ll-continue-prompt.md` (insertion point: between line 101 and line 103) ✓
- Line 103 — `Start new session → /ll:resume → Continue working` ✓
- Line 314 — `### Configuration Reference` table row for `continuation.auto_detect_on_session_start` ✓
- Line 329 — `### Auto-Detect on Session Start` heading; paragraph is the single line at 331 (lines 329–331 originally claimed as a "range" was inaccurate — corrected on re-verification) ✓
- Lines 375-377 — `## Files` table data rows: `.ll/ll-continue-prompt.md`, `.ll/ll-context-state.json`, `.ll/ll-session-state.json` (header + separator at 373–374; original "373–377" range corrected on re-verification) ✓
- Line 499 — Stop hook bullet in `## Integration` `### With Other Hooks`: lists `.ll/ll-context-state.json` and `.ll/ll-session-state.json` cleanup; preserves `.ll/ll-continue-prompt.md` for `/ll:resume` ✓

### Auto-Detect Flag Is Unimplemented (Critical Correction)

The issue's `## Behavioral Note` and parts of the Acceptance Criteria assume `auto_detect_on_session_start` is a "legacy passive flag" that `session-start.sh` honors. **This is incorrect.** A repo-wide grep for `auto_detect_on_session_start` shows the flag exists **only** in:

- `config-schema.json:493` — schema definition (default `true`)
- `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md` — documentation
- `skills/init/`, `skills/configure/` — surfaced in setup UI
- `site/` — generated docs

It does **not** appear in `hooks/scripts/` (including `session-start.sh`), `commands/`, or `scripts/little_loops/`. `hooks/scripts/session-start.sh` (lines 1-159) only resolves config + merges local overlays; it does not read `.ll/ll-continue-prompt.md` or print a resume notice. No code in the repo reads or branches on this flag.

**Implication for the rewrite:** the rewritten `### Auto-Detect on Session Start` paragraph must not describe `auto_detect_on_session_start` as currently implemented. The accurate framing is:

- `session-start-inject.sh` (new in FEAT-1315) is the only mechanism that surfaces the continuation prompt at session start, via `additionalContext` injection.
- `auto_detect_on_session_start` is a documented config flag that is currently not wired to any code; it is reserved for future use and ignored at runtime. Disabling it has no effect.
- The `### Configuration Reference` row at line 314 should reflect this honestly (e.g., note "Currently a no-op — superseded by `session-start-inject.sh`. Reserved for future use.") rather than claim it controls active behavior.

If the implementer disagrees with this framing, the alternative is to wire the flag (e.g., gate `session-start-inject.sh` execution on it). That would expand FEAT-1315's scope and is **out of scope for FEAT-1318** — this issue is docs-only. Raise a follow-up issue if wiring is preferred.

### Stop Hook Bullet — Wording Pattern

The current line 499 bullet uses "deleting `.ll/ll-context-state.json` and `.ll/ll-session-state.json`; the continuation prompt `.ll/ll-continue-prompt.md` is preserved for use by `/ll:resume`". The cleanest extension preserves that two-clause shape: append `.ll/ll-session-injected` to the deleted list (it is *not* preserved across sessions — see FEAT-1315 `session-cleanup.sh` change, which is the reason the sentinel is in the cleanup block).

### Files Table — Wording Pattern

The existing rows are terse `Purpose` descriptions (3–5 words). Match that style for the new row, e.g.:

| File | Purpose |
|------|---------|
| `.ll/ll-session-injected` | SessionStart injection sentinel (one-shot guard, cleared by Stop hook) |

### Flow Diagram Insertion — Box Width Constraint

The ASCII flow diagram box spans lines 89–104 (opening fence ` ``` ` at line 88, closing fence at line 105) and is 67 characters wide. Top/bottom borders use `┌─…─┐` / `└─…─┘`; vertical bars `│` sit at columns 1 and 67 (1-indexed), giving 65 chars of usable interior width. Any new step text must fit within 65 chars (including a leading space after `│` and a trailing space before `│`) or the box border will misalign. A safe phrasing under the limit:

```
│ SessionStart hook auto-injects prompt as additionalContext      │
│     ↓                                                           │
```

(Verify column alignment after editing — the existing arrows `↓` sit at column 7.)

### ToC Entry — Likely No Change Required

The ToC entry at line 22 reads `[Auto-Detect on Session Start](#auto-detect-on-session-start)`. The acceptance criterion says "update the ToC entry **if its text changes**". The recommended rewrite (above) keeps the heading text `### Auto-Detect on Session Start` unchanged (only the body paragraph is rewritten), so the ToC entry can remain as-is. Mark this acceptance bullet as a no-op in the implementation note unless the implementer chooses a different heading.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 86/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **FEAT-1315 is still unshipped.** All five doc edits reference `session-start-inject.sh`, `.ll/ll-session-injected`, and `session-cleanup.sh` Stop hook changes that don't exist yet. The issue's own step 1 mandates waiting. Preliminary work (test scaffolding, edit-point planning) is safe now, but the full implementation must be held until FEAT-1315 merges.
- **config-schema.json description ownership is unscoped.** `config-schema.json:493-496` `auto_detect_on_session_start` description contradicts the rewritten guide. The issue flags FEAT-1317 as the likely owner but treats this as a fallback for FEAT-1318. Coordinate with FEAT-1317 before closing to avoid the contradiction landing unfixed.

## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:43:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:28:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9065566b-c476-4052-ae1c-d075d76f3b33.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:53:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72289cba-9611-4ef4-9b76-f0d5e2e83663.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/173908f9-660e-433b-b4c1-8c6c6cf614fd.jsonl`
- `/ll:wire-issue` - 2026-05-02T03:48:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91286acc-2865-4339-97ae-a8b386be8836.jsonl`
- `/ll:refine-issue` - 2026-05-02T03:43:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d452ceb7-8597-43d6-8d48-8dd672aecffc.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

## Blocks

- FEAT-1319

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The `config-schema.json:505-509` `auto_detect_on_session_start` description update has been assigned to FEAT-1317 (reference doc updates is the natural owner). Remove the "unscoped across siblings" fallback language from this issue's Configuration section — FEAT-1317 owns that edit. This issue owns only the `docs/guides/SESSION_HANDOFF.md` updates.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `docs/guides/SESSION_HANDOFF.md` in multiple locations. The same file is also modified by FEAT-1158 (precompact handoff docs). No ordering dependency exists between these two issues. If worked concurrently, coordinate to avoid git merge conflicts in `docs/guides/SESSION_HANDOFF.md`.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): This issue **owns** the `skills/configure/areas.md` line 509 edit (continuation area `false` option description — update to note injection fires regardless of this flag). FEAT-1319 previously listed this same edit; it has been removed from FEAT-1319's scope to avoid a duplicate modification. When implementing, apply the line 509 change here (FEAT-1318) and do not re-apply it in FEAT-1319.

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
