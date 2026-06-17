---
id: FEAT-1158
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by:
- FEAT-1112
- FEAT-1156
parent: FEAT-1113
decision_needed: false
relates_to:
- FEAT-1156
- FEAT-1157
confidence_score: 65
outcome_confidence: 49
score_complexity: 21
score_test_coverage: 8
score_ambiguity: 8
score_change_surface: 12
---

# FEAT-1158: PreCompact Handoff Hook — Docs & Configuration

## Summary

Update all documentation, configuration schema, templates, and peripheral config files to reflect the new `precompact-handoff.sh` hook introduced by FEAT-1156.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `docs/guides/SESSION_HANDOFF.md` describes automatic PreCompact trigger alongside manual `/ll:handoff`
- `docs/ARCHITECTURE.md:85-98` lists `precompact-handoff.sh` in the scripts directory
- `docs/ARCHITECTURE.md:888-955` flow diagram shows PreCompact as a second handoff trigger path (not PostToolUse-only)
- `docs/development/TROUBLESHOOTING.md:753` chmod list includes `precompact-handoff.sh`
- `docs/development/TROUBLESHOOTING.md:939-942` manual test invocation block has parallel entry for `precompact-handoff.sh`
- `docs/development/TROUBLESHOOTING.md:972` timeout list includes `precompact-handoff.sh`
- `skills/configure/areas.md:867` hook audit table has a row for `precompact-handoff.sh`
- If feature flag introduced: `config-schema.json` has a new top-level `precompact_handoff` section (NOT under `context_monitor` — it has `additionalProperties: false`)
- If feature flag introduced: all 9 `templates/*.json` have `"precompact_handoff": {"enabled": true}` alongside `context_monitor`
- `docs/reference/CONFIGURATION.md` `context_monitor` table updated (or new `precompact_handoff` section added) if config keys are introduced

## Implementation

### Decision Required First

Decide whether `precompact_handoff` is opt-in (feature flag in config) or always-on. This determines whether `config-schema.json` and `templates/*.json` need updating.

- **Always-on** (preferred unless users report noise): no config changes needed; just docs.
> **Selected:** Always-on — direct predecessor `pre_compact.py` is itself always-on with no config gate; 8 of 12 hooks run unconditionally; no schema or template changes needed.
- **Opt-in**: add `"precompact_handoff": {"type": "object", ...}` to `config-schema.json` at top level; add `"precompact_handoff": {"enabled": true}` to all 9 template files.

### Documentation Updates

1. `docs/guides/SESSION_HANDOFF.md` — add section explaining PreCompact auto-trigger; clarify `/ll:handoff` is now a manual override for the richer version
2. `docs/ARCHITECTURE.md:85-98` — add `precompact-handoff.sh` line in hooks/scripts/ directory listing
3. `docs/ARCHITECTURE.md:888-955` — update context-monitor flow diagram to show two handoff trigger paths: PostToolUse (existing) + PreCompact (new)
4. `docs/development/TROUBLESHOOTING.md:753` — add `chmod +x hooks/scripts/precompact-handoff.sh`
5. `docs/development/TROUBLESHOOTING.md:939-942` — add manual invocation example parallel to `precompact-state.sh` block
6. `docs/development/TROUBLESHOOTING.md:972` — add `precompact-handoff.sh` to the timeout reference list

### Configuration (if opt-in)

7. `config-schema.json` — new top-level section `precompact_handoff`
8. `templates/generic.json` + 8 other templates — add `"precompact_handoff": {"enabled": true}`
9. `docs/reference/CONFIGURATION.md` — document the new config key

### Skill Config Audit Display

10. `skills/configure/areas.md:867` — add row: `[Plugin] PreCompact * precompact-handoff.sh 5s` (or whatever timeout is configured)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add `precompact-handoff.sh` row to "Lifecycle at a Glance" table; add parallel description alongside `precompact.sh` in the `PreCompact` section; update "A Session from Hook's Perspective" narrative to show two-phase PreCompact behavior (state snapshot first, continuation prompt second)
12. Update `docs/claude-code/write-a-hook.md` — add `precompact-handoff.sh` to adapter file enumeration near line 180
13. Update `commands/handoff.md` — extend Integration section to mention PreCompact auto-trigger path (not just "Works with PostToolUse context monitor hook")
14. Update `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_STRINGS_PRESENT` entries gating `"precompact-handoff.sh"` presence in `docs/ARCHITECTURE.md` and `docs/development/TROUBLESHOOTING.md`; add a sentinel string guard for `docs/guides/SESSION_HANDOFF.md`
15. Update `scripts/tests/test_wiring_init_and_configure.py` — add `DOC_STRINGS_PRESENT` entry for `"precompact-handoff.sh"` in `skills/configure/areas.md`

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-16.

**Selected**: Always-on

**Reasoning**: The existing `pre_compact.py` handler — the direct predecessor to FEAT-1158's additions — runs unconditionally with no config gate and has no entry in `config-schema.json`. Eight of twelve hooks in this codebase follow the always-on pattern; only hooks with meaningful per-call cost or disruptive side effects (analytics, scratch_pad) use a config gate. Choosing always-on avoids adding config-reading to `pre_compact.py` (which currently has none), skips updating 9 template files, and aligns with the preference stated in the issue.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Always-on | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Opt-in | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Always-on**: `pre_compact.py` has no `_load_config()` call, no `feature_enabled()` guard, and no `config-schema.json` entry; 8 of 12 hooks run unconditionally; issue flags always-on as "preferred".
- **Opt-in**: Requires adding config-reading to `pre_compact.py` (absent today), touching all 9 template files, and a new schema section — convention exists but direct predecessor contradicts it.

## Files to Modify

- `docs/guides/SESSION_HANDOFF.md`
- `docs/ARCHITECTURE.md` (lines 85-98 and 888-955)
- `docs/development/TROUBLESHOOTING.md` (lines 753, 939-942, 972)
- `skills/configure/areas.md` (line 867)
- `config-schema.json` (if opt-in)
- `templates/*.json` — all 9 files (if opt-in)
- `docs/reference/CONFIGURATION.md` (if opt-in)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — update "Lifecycle at a Glance" table, "PreCompact" section, and session narrative to include `precompact-handoff.sh` as a second PreCompact entry alongside `precompact.sh`
- `docs/claude-code/write-a-hook.md` — add `precompact-handoff.sh` to adapter file enumeration (line ~180) which lists Claude Code adapter scripts
- `commands/handoff.md` — update Integration section (line ~243) to mention PreCompact trigger path alongside the existing PostToolUse context monitor description

## References

- Depends on: FEAT-1156 (hook must exist before docs can be accurate)
- Tests: FEAT-1157

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/hooks.json` — registers `precompact-handoff.sh` in the `PreCompact` array; owned by FEAT-1156 but must exist before FEAT-1158 docs can be accurate
- `scripts/little_loops/hooks/__init__.py` — module docstring and `_USAGE` string enumerate dispatched intents; owned by FEAT-1156 (adds `pre_compact_handoff` to intent list)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `context_monitor` description (line ~427) implies context_monitor is the sole automatic handoff path; add a clarifying cross-reference to SESSION_HANDOFF.md for the PreCompact trigger path [Agent 2 finding — low-force coupling]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_STRINGS_PRESENT` entries: `("docs/guides/SESSION_HANDOFF.md", "<sentinel>", "FEAT-1158")` (currently zero wiring test coverage for this file); add presence guards for `"precompact-handoff.sh"` in `docs/ARCHITECTURE.md` and `docs/development/TROUBLESHOOTING.md` after FEAT-1158 edits are applied [Agent 3 finding]
- `scripts/tests/test_wiring_init_and_configure.py` — add `DOC_STRINGS_PRESENT` entry `("skills/configure/areas.md", "precompact-handoff.sh", "FEAT-1158")` to gate the new hook audit table row [Agent 3 finding]

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `docs/guides/SESSION_HANDOFF.md` has no automatic PreCompact trigger section ✓
- `docs/ARCHITECTURE.md:85-98` does not list `precompact-handoff.sh` ✓
- `skills/configure/areas.md:867` has no row for `precompact-handoff.sh` ✓
- Blocked by FEAT-1156 (hook must exist before docs can be accurate) ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 49/100 → VERY LOW

### Gaps to Address
- Resolve always-on vs opt-in before implementation begins — the choice adds config-schema.json + 9 template files + docs/reference/CONFIGURATION.md to scope if opt-in, doubling effort
- FEAT-1156 must be fully delivered before any doc claims can be verified accurate

### Outcome Risk Factors
- **Open decision not resolved** — always-on vs opt-in gates whether config-schema.json and 9 template files are in scope; resolve before starting
- **No automated test coverage** — 6 of the 7 mandatory change sites are documentation files with no automated validation; verification relies on manual review

## Session Log
- `/ll:wire-issue` - 2026-06-17T00:11:38 - `8d5b5e3d-ed9e-4e99-9628-47990c24c94a.jsonl`
- `/ll:decide-issue` - 2026-06-17T00:02:06 - `97cf2d3f-bfd7-4961-913e-a7776646b3aa.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `582fb982-6866-45ba-b90e-d2cfdc139ff2.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `docs/ARCHITECTURE.md`, `docs/guides/SESSION_HANDOFF.md`, and `skills/configure/areas.md` for the precompact handoff feature. These same files are also modified by the session-start inject doc family: FEAT-1317 (`docs/ARCHITECTURE.md`), FEAT-1318 (`docs/guides/SESSION_HANDOFF.md`), FEAT-1319 (`skills/configure/areas.md`). No ordering dependency exists between these two doc families. If worked concurrently, coordinate to avoid git merge conflicts in these three shared files.

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1262 (Session Event Capture Hook) also modifies `docs/ARCHITECTURE.md` (PostToolUse hook flow section) and `config-schema.json` (adds `session_capture` property). This issue touches `docs/ARCHITECTURE.md` at lines 85–98 and 888–955 and may touch `config-schema.json` if opt-in is chosen. No ordering dependency exists between FEAT-1158 and FEAT-1262. If worked concurrently, coordinate edits to these two shared files to avoid merge conflicts.
