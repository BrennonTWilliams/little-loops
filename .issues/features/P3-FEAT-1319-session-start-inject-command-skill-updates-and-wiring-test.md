---
id: FEAT-1319
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-01
discovered_by: issue-size-review
blocked_by: [FEAT-1315, FEAT-1317, FEAT-1318]
parent: FEAT-1316
related: [FEAT-1315, FEAT-1316, FEAT-1317, FEAT-1318]
size: Very Large
confidence_score: 80
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
---

# FEAT-1319: SessionStart Inject — Command/Skill Updates and Wiring Test

## Summary

Update `commands/handoff.md`, `skills/configure/areas.md`, and `skills/init/interactive.md` after FEAT-1315 ships `session-start-inject.sh`; create the doc-wiring test `scripts/tests/test_feat1316_doc_wiring.py`; run link verification.

## Parent Issue

Decomposed from FEAT-1316: SessionStart Inject — Documentation Updates

## Depends On

FEAT-1315 must be complete before this issue is worked (docs reference the shipped implementation).

## Acceptance Criteria

- `commands/handoff.md` `### 4. Output Handoff Signal` step 2 marks "Run /ll:resume" as optional, with wording that context will be automatically injected when `session-start-inject.sh` is registered
- `skills/configure/areas.md` hook table (~line 861) lists `session-start-inject.sh` as a second SessionStart entry alongside `session-start.sh`
- `skills/configure/areas.md` line 509 (`## Area: continuation` → `false` option description) updated to note active injection fires regardless of this flag
- `skills/init/interactive.md` `## Round 9` `false` option label (~line 530) updated to note `session-start-inject.sh` injects context regardless of this flag
- `scripts/tests/test_feat1316_doc_wiring.py` exists and passes, asserting presence of `session-start-inject.sh` in `docs/ARCHITECTURE.md`, `.ll/ll-session-injected` in `docs/guides/SESSION_HANDOFF.md`, and `session-start-inject.sh` in `skills/configure/areas.md`
- `ll-check-links docs/` passes with no broken links in modified files

## Implementation Steps

1. Wait for FEAT-1315, FEAT-1317, and FEAT-1318 to merge. Two of the three test assertions in `test_feat1316_doc_wiring.py` depend on FEAT-1317 (adds `session-start-inject.sh` to `docs/ARCHITECTURE.md`) and FEAT-1318 (adds `.ll/ll-session-injected` to `docs/guides/SESSION_HANDOFF.md`). Only the third assertion (`session-start-inject.sh` in `skills/configure/areas.md`) is supplied by FEAT-1319 itself.
2. Edit `commands/handoff.md` lines 200–201 (`### 4. Output Handoff Signal`): change step 2 from "Run /ll:resume" (required) to optional — e.g. "Run `/ll:resume` (optional — context is automatically injected on next session start when `session-start-inject.sh` is registered; manual run remains available as a fallback or for inspection)".
3. Edit `skills/configure/areas.md`:
   - After line 861: insert sibling SessionStart row for `session-start-inject.sh`, matching neighboring column alignment (`[Plugin]`, `SessionStart`, `*`, `session-start-inject.sh`, `5s`, `[exists/MISSING]`).
   - Line 509 (`## Area: continuation` → `### Round 1` → `false` option description, currently "No, require manual /ll:resume"): update to note active injection fires regardless of this flag.
4. Edit `skills/init/interactive.md` — `## Round 9` continuation round (line 514), `false` option `description` field at line 530 (currently "Manual /ll:resume required"; the `label: "No"` is at line 529): update the description to note that `session-start-inject.sh` injects context regardless of this flag value.
5. Create `scripts/tests/test_feat1316_doc_wiring.py`:
   - Follow pattern from `scripts/tests/test_circuit_breaker_doc_wiring.py` and `scripts/tests/test_enh1268_doc_wiring.py`
   - Use `PROJECT_ROOT = Path(__file__).parent.parent.parent` and file-level path constants per convention
   - Assert: `session-start-inject.sh` present in `docs/ARCHITECTURE.md`
   - Assert: `.ll/ll-session-injected` present in `docs/guides/SESSION_HANDOFF.md`
   - Assert: `session-start-inject.sh` present in `skills/configure/areas.md`
6. Run `ll-check-links docs/` to verify no broken links introduced.

## Files to Modify

- `commands/handoff.md` — `### 4. Output Handoff Signal` at lines 189–204 (step 2 at line 200–201)
- `skills/configure/areas.md` — hook table (~line 861) and continuation `false` option (~line 509)
- `skills/init/interactive.md` — `## Round 9` false option label (~line 530)

## Files to Create

- `scripts/tests/test_feat1316_doc_wiring.py`

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — must contain `session-start-inject.sh` (added by FEAT-1317) before `TestArchitectureWiring.test_session_start_inject_script_present` can pass [Agent 2 finding]
- `docs/guides/SESSION_HANDOFF.md` — must contain `.ll/ll-session-injected` (added by FEAT-1318) before `TestSessionHandoffWiring.test_ll_session_injected_marker_present` can pass [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs_wiring.py::TestConfigureAreasWiring` — asserts `"Authorize all 16"` and `"ll-logs"` on `areas.md`; unaffected by hook table or continuation text changes [Agent 3 finding]
- `scripts/tests/test_cli_docs.py` — exercises `ll-check-links`; implementation step 6 invokes this tool [Agent 1 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Before creating `test_feat1316_doc_wiring.py`, confirm `docs/ARCHITECTURE.md` references `session-start-inject.sh` (FEAT-1317 must have merged) and `docs/guides/SESSION_HANDOFF.md` references `.ll/ll-session-injected` (FEAT-1318 must have merged) — two of the three test assertions depend on these.
8. After creating `test_feat1316_doc_wiring.py`, run the full test suite including `test_ll_logs_wiring.py` and `test_cli_docs.py` to confirm no regressions.

## Codebase Anchors

- `commands/handoff.md:189-204` — `### 4. Output Handoff Signal` block; step 2 at lines 200–201
- `skills/configure/areas.md:858-873` — hardcoded `Current Hook Configuration` table (header at line 858, not 855 as previously noted); SessionStart row at line 861 currently shows `session-start.sh` and a sibling row for `session-start-inject.sh` must be inserted
- `skills/configure/areas.md:509` — `## Area: continuation` → `### Round 1` → `false` option description
- `skills/init/interactive.md:514` — `## Round 9` continuation round
- `skills/init/interactive.md:530` — `false` option label
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — doc wiring test pattern to follow
- `scripts/tests/test_enh1268_doc_wiring.py` — doc wiring test pattern to follow

## Notes

- The `skills/configure/areas.md` hook table is a hardcoded display sample rendered by `/ll:configure`; the live status table is generated by `skills/configure/SKILL.md` reading `hooks/hooks.json` directly. Only the hardcoded display sample needs updating here.
- No `config-schema.json` changes needed — no new config keys are introduced.
- Existing tests that will NOT break: `test_create_extension_wiring.py::TestConfigureAreasWiring::test_count_updated_to_16` (asserts on "Authorize all 16", not the hook table); `test_hooks_integration.py::TestSessionStartValidation` (tests `session-start.sh` behavior, not docs); `test_doc_counts.py` (counts commands/agents/skills, unchanged here); `test_ll_logs_wiring.py::TestConfigureAreasWiring` (asserts `"Authorize all 16"` and `"ll-logs"` on `areas.md` — not in the hook table or continuation text).
- `scripts/tests/test_cli_docs.py` exercises `ll-check-links` — this is the automated test for the CLI tool run in step 6; no new test is needed for the link-check step itself, but it should be run to confirm no regressions.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-05-01):_

### Anchor Verification
- `commands/handoff.md:189-204` `### 4. Output Handoff Signal` — VERIFIED. Step 2 at lines 200-201 is exactly `Run /ll:resume`. The file contains zero current references to `session-start-inject.sh`.
- `skills/configure/areas.md:858` (table header) — table starts at line 858, not 855. SessionStart row at line 861 confirmed; it currently references `session-start.sh`. The new row for `session-start-inject.sh` is a *sibling* (additional row), not a replacement.
- `skills/configure/areas.md:509` `false` option description — VERIFIED exact text `"No, require manual /ll:resume"`.
- `skills/init/interactive.md:514` `## Round 9: Continuation Behavior (Optional)` — VERIFIED. Line 530 is the `description:` field of the `false` option (the `label: "No"` lives at line 529); text `"Manual /ll:resume required"` confirmed.

### Test Pattern Convention (from `test_circuit_breaker_doc_wiring.py`, `test_enh1268_doc_wiring.py`)
- Pytest plain-class style (no `unittest.TestCase`)
- Imports limited to: `from __future__ import annotations` and `from pathlib import Path`
- `PROJECT_ROOT = Path(__file__).parent.parent.parent`
- Module-level `ALL_CAPS` Path constants for each target file
- One class per target file with docstring describing the invariant
- Each test method calls `<CONST>.read_text()` inline and asserts `assert "string" in content, "<file path> must reference <string> because ..."`

### Recommended Skeleton for `scripts/tests/test_feat1316_doc_wiring.py`

```python
"""Tests for FEAT-1316: session-start-inject documentation wiring.

Asserts that session-start-inject.sh and related artefacts are surfaced in
authoritative user-facing documentation and skill files so users and future
contributors can discover them.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
SESSION_HANDOFF = PROJECT_ROOT / "docs" / "guides" / "SESSION_HANDOFF.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"


class TestArchitectureWiring:
    """docs/ARCHITECTURE.md must reference session-start-inject.sh."""

    def test_session_start_inject_script_present(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "session-start-inject.sh" in content, (
            "docs/ARCHITECTURE.md must reference session-start-inject.sh "
            "so users can discover the session-context injection script"
        )


class TestSessionHandoffWiring:
    """docs/guides/SESSION_HANDOFF.md must reference .ll/ll-session-injected."""

    def test_ll_session_injected_marker_present(self) -> None:
        content = SESSION_HANDOFF.read_text()
        assert ".ll/ll-session-injected" in content, (
            "docs/guides/SESSION_HANDOFF.md must reference .ll/ll-session-injected "
            "so users know the marker file that tracks injection state"
        )


class TestConfigureAreasWiring:
    """skills/configure/areas.md must reference session-start-inject.sh."""

    def test_session_start_inject_script_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "session-start-inject.sh" in content, (
            "skills/configure/areas.md must reference session-start-inject.sh "
            "so the configure skill exposes the injection script to users"
        )
```

### Tooling References
- `ll-check-links` entry point: `scripts/little_loops/cli/docs.py:main_check_links` (registered in `scripts/pyproject.toml:59`)
- All sibling doc-wiring tests in repo (for additional pattern reference): `test_circuit_breaker_doc_wiring.py`, `test_enh1130_doc_wiring.py`, `test_enh1138_doc_wiring.py`, `test_enh1146_doc_wiring.py`, `test_enh1268_doc_wiring.py`, `test_enh1299_doc_wiring.py`, `test_feat1172_doc_wiring.py`

### Second Refinement Pass (2026-05-01)

_Additional findings from a second `/ll:refine-issue` pass — gaps the first pass missed:_

**Hook table format is plain-text fixed-width, NOT markdown.** `skills/configure/areas.md:858-873` is a fenced code block with positional columns (`Source`, `Event`, `Matcher`, `Script`, `Timeout`, `Status`). The new `session-start-inject.sh` row must match column widths exactly — do not introduce markdown table pipes. Verbatim existing rows (lines 861–869) for alignment reference:

```
  [Plugin]   SessionStart      *              session-start.sh                5s       [exists/MISSING]
  [Plugin]   UserPromptSubmit  (no matcher)   user-prompt-check.sh            3s       [exists/MISSING]
  [Plugin]   PreToolUse        Write|Edit     check-duplicate-issue-id.sh     5s       [exists/MISSING]
  [Plugin]   PostToolUse       *              context-monitor.sh              5s       [exists/MISSING]
  [Plugin]   PostToolUse       Bash           issue-completion-log.sh         5s       [exists/MISSING]
  [Plugin]   Stop              (no matcher)   session-cleanup.sh              15s      [exists/MISSING]
  [Plugin]   PreCompact        *              precompact-state.sh             5s       [exists/MISSING]
```

The new sibling row to insert after the existing `SessionStart` row (line 861):
```
  [Plugin]   SessionStart      *              session-start-inject.sh         5s       [exists/MISSING]
```

**Label format inconsistency between the two skill files** — preserve each file's local convention; do NOT normalize:
- `skills/configure/areas.md:508-509` uses `label: "false"` (boolean-string style)
- `skills/init/interactive.md:529-530` uses `label: "No"` (human-readable style)

Only the `description:` value should change in each; the `label:` value is invariant.

**Wording precedent for "regardless of this flag".** No prior occurrences in `.md` files; the closest production-text idiom is `docs/reference/CONFIGURATION.md:692`: `"Set NO_COLOR=1 to disable all colorization regardless of config."` — short parenthetical clause appended after the primary description. Suggested wording (compact, fits the YAML option-description constraint):
- `areas.md:509` description → `"No — but session-start-inject.sh injects context regardless of this flag"`
- `interactive.md:530` description → `"Manual /ll:resume required (session-start-inject.sh injects context regardless of this flag)"`

**Pre-condition status (re-verified 2026-05-01).** `hooks/session-start-inject.sh` does NOT exist; `session-start-inject` and `ll-session-injected` strings appear ONLY in `.issues/` files. FEAT-1315/1317/1318 have not landed. Implementation Step 1 (wait-for-blockers) remains a hard gate.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 76/100 → MODERATE

### Concerns
- All three blocking dependencies (FEAT-1315, FEAT-1317, FEAT-1318) remain open. Two of three test assertions in `test_feat1316_doc_wiring.py` cannot pass until FEAT-1317 and FEAT-1318 ship their doc updates. FEAT-1315's `session-start-inject.sh` must exist before the `commands/handoff.md` change is meaningful. Step 1 of the implementation plan explicitly says to wait — treat unresolved blockers as a hard gate before starting.
- `readiness_threshold` in config is 85 — the manage-issue Phase 2.5 gate will flag this score (80); must unblock deps to raise score to 100 before automated pipelines will proceed without a warning.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-10T14:28:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/062ec8c6-6424-4417-9cb0-d25f3f41a8bc.jsonl`
- `/ll:refine-issue` - 2026-05-02T04:12:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e3297cf-0323-4e90-9d85-590243f90677.jsonl`
- `/ll:wire-issue` - 2026-05-02T04:07:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19d3bdf4-5f60-472b-9dbc-a3be86bef0ca.jsonl`
- `/ll:refine-issue` - 2026-05-02T04:00:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/555306d2-cad7-44c8-a701-8d11f2961594.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085730b-f073-48ce-bcdd-8508092f06ce.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `test_feat1316_doc_wiring.py` MUST NOT include `TestArchitectureWiring` (asserting `session-start-inject.sh` in `docs/ARCHITECTURE.md`) or `TestSessionHandoffWiring` (asserting `.ll/ll-session-injected` in `docs/guides/SESSION_HANDOFF.md`). Those assertions are owned by FEAT-1317 (`test_feat1317_doc_wiring.py`) and FEAT-1318 (`test_feat1318_doc_wiring.py`) respectively. FEAT-1319's test file should assert only what this issue uniquely produces: `session-start-inject.sh` present in `skills/configure/areas.md`.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `skills/configure/areas.md` (hook table ~line 861, area:continuation ~line 509). The same file is also modified by FEAT-1158 (precompact handoff docs, hook audit table row ~line 867). No ordering dependency exists between these two issues. If worked concurrently, coordinate to avoid git merge conflicts in `skills/configure/areas.md`.
