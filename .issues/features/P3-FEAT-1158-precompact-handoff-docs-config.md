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
confidence_score: 100
outcome_confidence: 72
score_complexity: 19
score_test_coverage: 12
score_ambiguity: 23
score_change_surface: 18
implementation_order_risk: true
size: Very Large
---

# FEAT-1158: PreCompact Handoff Hook — Docs & Configuration

## Summary

Update all documentation, configuration schema, templates, and peripheral config files to reflect the new `precompact-handoff.sh` hook introduced by FEAT-1156.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `docs/guides/SESSION_HANDOFF.md` describes automatic PreCompact trigger alongside manual `/ll:handoff`
- `docs/ARCHITECTURE.md:86-90` (`claude-code/` adapter listing) includes `precompact-handoff.sh` alongside `precompact.sh`, `session-end.sh`, `session-start.sh`
- `docs/ARCHITECTURE.md:1105-1132` (`### Context Monitor and Session Continuation` flowchart) shows PreCompact as a second handoff trigger path (not PostToolUse-only; currently shows only PostToolUse → handoff)
- `docs/development/TROUBLESHOOTING.md:849` chmod list (lines 844–854) includes `hooks/adapters/claude-code/precompact-handoff.sh` after the existing `precompact.sh` entry
- `docs/development/TROUBLESHOOTING.md:1058-1074` manual test invocation block has parallel entry for `pre_compact_handoff` (three variants: default, `LL_HOOK_HOST=opencode`, `LL_HOOK_HOST=codex`)
- `docs/development/TROUBLESHOOTING.md:1104` lock timeout list includes `little_loops.hooks.pre_compact_handoff` with its 3s advisory lock
- `skills/configure/areas.md:878` hook audit table has a row for `precompact-handoff.sh` (`[Plugin] PreCompact * adapters/claude-code/precompact-handoff.sh 5s`)
- No `config-schema.json` changes (always-on decision: no feature flag)
- No `templates/*.json` changes (always-on decision: no feature flag)
- No `docs/reference/CONFIGURATION.md` config-key changes needed (always-on decision)

## Implementation

### Decision: Always-On (Resolved)

`precompact_handoff` runs unconditionally — no config gate. See `## Decision Rationale` below for scoring and reasoning. Steps 7–9 (schema and template changes) are not needed.

### Documentation Updates

1. `docs/guides/SESSION_HANDOFF.md` — add section explaining PreCompact auto-trigger; clarify `/ll:handoff` is now a manual override for the richer version; update `## Integration` (lines ~490-506) to mention PreCompact hook alongside PostToolUse; add `.ll/ll-precompact-state.json` to `## Files` table (lines ~365-371)
2. `docs/ARCHITECTURE.md:86-91` — add `precompact-handoff.sh` to `claude-code/` adapter file listing after the `precompact.sh` entry at line 88 (currently missing from the `claude-code/` directory tree)
3. `docs/ARCHITECTURE.md:1105-1132` — update `### Context Monitor and Session Continuation` flowchart to show two handoff trigger paths: PostToolUse (existing) + PreCompact (new); the flowchart currently shows only PostToolUse → handoff with no PreCompact path
4. `docs/development/TROUBLESHOOTING.md:849` — add `chmod +x hooks/adapters/claude-code/precompact-handoff.sh` after the existing `precompact.sh` entry at line 849 (within the chmod block at lines 844-854)
5. `docs/development/TROUBLESHOOTING.md:1074` — add manual invocation block for `pre_compact_handoff` after the existing `pre_compact` block at lines 1058-1073; include three variants (default, `LL_HOOK_HOST=opencode`, `LL_HOOK_HOST=codex`) matching the `pre_compact` pattern
6. `docs/development/TROUBLESHOOTING.md:1104` — add `little_loops.hooks.pre_compact_handoff: 3s lock timeout (Python handler invoked via hooks/adapters/claude-code/precompact-handoff.sh)` to the lock timeout list after the existing `pre_compact` entry at line 1104

### Configuration (if opt-in) — NOT APPLICABLE

~~7. `config-schema.json` — new top-level section `precompact_handoff`~~
~~8. `templates/generic.json` + 8 other templates — add `"precompact_handoff": {"enabled": true}`~~
~~9. `docs/reference/CONFIGURATION.md` — document the new config key~~

_Steps 7–9 are superseded by the always-on decision. `pre_compact_handoff.py` has no `_load_config()` call, no `feature_enabled()` guard, and no `config-schema.json` entry — same pattern as `pre_compact.py`. No schema or template changes needed._

### Skill Config Audit Display

10. `skills/configure/areas.md:878` — add row after the existing `precompact.sh` entry (line 878): `[Plugin]   PreCompact        *              adapters/claude-code/precompact-handoff.sh       5s    [exists/MISSING]` (5s timeout per `hooks/hooks.json` PreCompact block; use same column spacing as adjacent rows)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — (a) "Lifecycle at a Glance" table: add second `PreCompact` row after line 67 (`| **PreCompact** | precompact-handoff | Writes session continuation prompt before compaction | — | on |`); (b) `## PreCompact` section (lines 286-294): add parallel block describing `precompact-handoff.sh` → `little_loops.hooks.pre_compact_handoff.handle`, outputs `.ll/ll-continue-prompt.md`, reads `.ll/ll-precompact-state.json` for idempotency guard, 3s advisory lock; (c) "A Session from Hook's Perspective" narrative (lines 71-94): add second PreCompact step showing two-phase behavior (state snapshot via `precompact.sh` first, continuation prompt via `precompact-handoff.sh` second)
12. Update `docs/claude-code/write-a-hook.md:180` — add `precompact-handoff.sh` to the `Adapter files:` inline list (currently: `precompact.sh`, `post-tool-use.sh`, `session-end.sh`, `session-start.sh`; add `precompact-handoff.sh` after `precompact.sh`)
13. Update `commands/handoff.md:239-244` — extend `## Integration` section; add bullet: `- PreCompact hook writes `.ll/ll-continue-prompt.md` automatically before context compaction (passive path); /ll:handoff is the active/richer manual override`
14. Update `scripts/tests/test_wiring_guides_and_meta.py` — add to `DOC_STRINGS_PRESENT` list: `("docs/ARCHITECTURE.md", "precompact-handoff.sh", "FEAT-1158")`, `("docs/development/TROUBLESHOOTING.md", "precompact-handoff.sh", "FEAT-1158")`, `("docs/guides/SESSION_HANDOFF.md", "precompact-handoff.sh", "FEAT-1158")`; follow the tuple format `(doc_path, expected_string, issue_id)` used by existing entries (see lines 37-41)
15. Update `scripts/tests/test_wiring_init_and_configure.py` — add to `DOC_STRINGS_PRESENT` list: `("skills/configure/areas.md", "precompact-handoff.sh", "FEAT-1158")`; follow existing entries at lines 133-134: `("skills/configure/areas.md", "adapters/claude-code/precompact.sh", "FEAT-1457")`

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

- `docs/guides/SESSION_HANDOFF.md` — add PreCompact trigger section; update Integration (~492-507) and Files table (~366-372)
- `docs/ARCHITECTURE.md` (lines 86-91: add adapter entry; lines 1105-1132: update Context Monitor flowchart)
- `docs/development/TROUBLESHOOTING.md` (line 849: chmod entry; lines 1058-1074: add manual invocation block; line 1104: add lock timeout entry)
- `skills/configure/areas.md` (line 878: add hook audit table row)
- ~~`config-schema.json`~~ — not needed (always-on)
- ~~`templates/*.json`~~ — not needed (always-on)
- ~~`docs/reference/CONFIGURATION.md`~~ — no config keys to document (always-on)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — update "Lifecycle at a Glance" table (line 67), "PreCompact" section (lines 286-295), and session narrative (lines 71-94) to include `precompact-handoff.sh` as a second PreCompact entry alongside `precompact.sh`
- `docs/claude-code/write-a-hook.md` — add `precompact-handoff.sh` to `Adapter files:` inline list (line 180) which lists Claude Code adapter scripts
- `commands/handoff.md` — update `## Integration` section (lines 239-244) to mention PreCompact trigger path alongside the existing PostToolUse context monitor description

## References

- Depends on: FEAT-1156 (hook must exist before docs can be accurate)
- Tests: FEAT-1157

## Integration Map

### Confirmed Pre-Existing Implementation (FEAT-1156 Complete)

_Re-verified by `/ll:refine-issue` on 2026-06-17 — all four artifacts confirmed present:_
- `hooks/adapters/claude-code/precompact-handoff.sh` — **EXISTS**; 3-line bash shim that pipes stdin to `python -m little_loops.hooks pre_compact_handoff`; no `LL_HOOK_HOST` export (defaults to `"claude-code"`)
- `hooks/hooks.json:176-198` — **REGISTERED**; `PreCompact` array contains both `precompact.sh` (entry 1) and `precompact-handoff.sh` (entry 2), timeout 5s, feedback `"Writing session handoff..."`
- `scripts/little_loops/hooks/pre_compact_handoff.py` — **EXISTS**; `handle()` reads `.ll/ll-precompact-state.json` for idempotency guard, writes `.ll/ll-continue-prompt.md` atomically with 3s advisory lock, returns `exit_code=2` on success, `exit_code=0` on idempotency skip
- `scripts/little_loops/hooks/__init__.py:17,52,78,87` — **DISPATCHED**; `pre_compact_handoff` is in `_dispatch_table()` mapping to `pre_compact_handoff.handle`; module docstring and `_USAGE` string enumerate it

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/hooks.json` — registers `precompact-handoff.sh` in the `PreCompact` array; owned by FEAT-1156 but must exist before FEAT-1158 docs can be accurate
- `scripts/little_loops/hooks/__init__.py` — module docstring and `_USAGE` string enumerate dispatched intents; owned by FEAT-1156 (adds `pre_compact_handoff` to intent list)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `context_monitor` description (line ~427) implies context_monitor is the sole automatic handoff path; add a clarifying cross-reference to SESSION_HANDOFF.md for the PreCompact trigger path [Agent 2 finding — low-force coupling]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_STRINGS_PRESENT` entries: `("docs/guides/SESSION_HANDOFF.md", "precompact-handoff.sh", "FEAT-1158")` (currently zero wiring test coverage for this file); add presence guards for `"precompact-handoff.sh"` in `docs/ARCHITECTURE.md` and `docs/development/TROUBLESHOOTING.md` after FEAT-1158 edits are applied; follow tuple format at lines 37-41
- `scripts/tests/test_wiring_init_and_configure.py` — add `DOC_STRINGS_PRESENT` entry `("skills/configure/areas.md", "precompact-handoff.sh", "FEAT-1158")` to gate the new hook audit table row; add after existing lines 133-134 (`precompact.sh` entry for FEAT-1457)

### Codebase Research Findings

_Added by `/ll:refine-issue` (full-rewrite pass, 2026-06-17) — verified against current HEAD:_

**Pre-existing implementation artifacts (FEAT-1156) — all confirmed:**
- `hooks/adapters/claude-code/precompact-handoff.sh` — EXISTS; 3-line bash shim piping stdin to `python -m little_loops.hooks pre_compact_handoff`
- `hooks/hooks.json:176-198` — REGISTERED; PreCompact array contains both `precompact.sh` and `precompact-handoff.sh`; timeout 5s; statusMessage `"Writing session handoff..."`
- `scripts/little_loops/hooks/pre_compact_handoff.py:181` — exit_code=2 on success confirmed; exit_code=0 on idempotency skip (line 61) or any exception (line 179)
- `scripts/little_loops/hooks/__init__.py:17,79,87` — dispatch entry `"pre_compact_handoff": pre_compact_handoff.handle` at line 87; module docstring at line 17; lazy import at line 79

**Current line numbers verified for all target sections (all MISSING precompact-handoff.sh):**
- `docs/ARCHITECTURE.md:87-90` — claude-code/ adapter listing; `precompact.sh` at line 88 (add `precompact-handoff.sh` after)
- `docs/ARCHITECTURE.md:1101` — `### Context Monitor and Session Continuation` heading; Mermaid flowchart body at lines 1105-1132 (PostToolUse-only path shown)
- `docs/ARCHITECTURE.md:1231` — NOTE: forward reference to `precompact-handoff.sh` already present in session-capture consumer note; not a target section, but confirms no search/replace will clobber it
- `docs/development/TROUBLESHOOTING.md:843-855` — chmod block; `precompact.sh` at line 849 (add `precompact-handoff.sh` after line 849)
- `docs/development/TROUBLESHOOTING.md:1058-1073` — `pre_compact` manual invocation block; three variants at lines 1061, 1067, 1073
- `docs/development/TROUBLESHOOTING.md:1104` — lock timeout list; `little_loops.hooks.pre_compact` entry (add `pre_compact_handoff` after)
- `docs/guides/SESSION_HANDOFF.md:365-371` — Files table (`.ll/ll-precompact-state.json` missing)
- `docs/guides/SESSION_HANDOFF.md:490-495` — `## Integration` / `### With Other Hooks` (PreCompact trigger path missing; only PostToolUse and Stop hooks listed)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:51-67` — Lifecycle at a Glance table; PreCompact row at line 67 describes only `precompact.sh`
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:286-294` — `## PreCompact` section body; describes only `precompact.sh → pre_compact.handle`
- `docs/claude-code/write-a-hook.md:180` — Adapter files list; `precompact-handoff.sh` absent
- `commands/handoff.md:239-244` — `## Integration` section; no PreCompact trigger path mentioned (only PostToolUse context monitor)
- `skills/configure/areas.md:878` — hook audit table; only one PreCompact row (`precompact.sh` at line 878)

**Test coverage gap confirmed:**
- `scripts/tests/test_wiring_guides_and_meta.py` — 0 FEAT-1158 entries in 168-entry `DOC_STRINGS_PRESENT` list; multi-line tuple format modelled at lines 37-41 (use for long string entries)
- `scripts/tests/test_wiring_init_and_configure.py` — 0 FEAT-1158 entries; list ends at line 177; single-line tuple format at lines 133-134: `("skills/configure/areas.md", "adapters/claude-code/precompact.sh", "FEAT-1457")`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `docs/guides/SESSION_HANDOFF.md` has no automatic PreCompact trigger section ✓
- `docs/ARCHITECTURE.md:85-98` does not list `precompact-handoff.sh` ✓
- `skills/configure/areas.md:867` has no row for `precompact-handoff.sh` ✓
- Blocked by FEAT-1156 (hook must exist before docs can be accurate) ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-17 (re-check #5; blockers confirmed done, stale-language risk cleared)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Low test-coverage baseline** — 7 of 9 change sites are documentation files with no automated unit tests; wiring test entries (steps 14–15) are the only doc-accuracy guard and are co-deliverables of this issue; implement tests first so each subsequent doc change is immediately gated by an automated presence check

## Session Log
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `e513b41c-6b52-45a2-9337-b97860e849e8.jsonl`
- `/ll:refine-issue` - 2026-06-17T14:10:33 - `0f016880-85bc-4bbe-99f8-02033fade9fb.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `b4e83fa1-ac6c-4881-a0f6-8e9ac33e4b65.jsonl`
- `/ll:refine-issue` - 2026-06-17T14:00:27 - `294a6e40-540e-468e-a590-e2a3425e134e.jsonl`
- `/ll:confidence-check` - 2026-06-17T14:00:00Z - `1e6e4626-ba64-460b-8cd7-3b31a567a30d.jsonl`
- `/ll:refine-issue` - 2026-06-17T13:51:12 - `f0515ea5-8fa5-41f9-b3b7-5de2abfc30fd.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `c5589c32-7fd0-47d2-befa-c0ce7b8d1ef4.jsonl`
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
