---
id: ENH-1151
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1146
related: [ENH-1144, ENH-1150]
confidence_score: 93
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-1151: 429 Resilience — Heartbeat Docs (Guide, Skill, Changelog, Tests)

## Summary

Update `LOOPS_GUIDE.md`, `skills/analyze-loop/SKILL.md`, and `CHANGELOG.md` for the `rate_limit_waiting` heartbeat event and ENH-1131 config fields. Write `test_enh1146_doc_wiring.py` to assert all new doc content is present.

## Parent Issue

Decomposed from ENH-1146: 429 Resilience — Heartbeat Documentation (parent is in `.issues/completed/`).

## Can run in parallel with ENH-1150.

## Dependency Note

`test_enh1146_doc_wiring.py` (step 4 below) covers assertions against files edited in both ENH-1150 and ENH-1151. Run the test after both children complete.

## Expected Behavior

### 1. `docs/guides/LOOPS_GUIDE.md`

- Lines 1020-1033: per-state property table. Rows for `rate_limit_max_wait_seconds` (line 1032) and `rate_limit_long_wait_ladder` (line 1033) are **already present** as of 2026-04-17 refine-issue verification. Spot-check content/formatting of those rows; update only if stale.
- Lines 1670-1691: extend prose + YAML example with two-tier ladder + budget mechanics (issue originally said 1668-1680; drifted ~2 lines).
- Line 2051: update `with_rate_limit_handling` fragment row "Supplies" column (issue originally said 2028; 2028 is an unrelated `my_gate` example block — correct row is at 2051).

**Line-drift warning**: All line numbers above verified at refine time (2026-04-17). Lines drift with edits — always spot-check before inserting.

**PRESERVE these existing strings** (tested by `test_enh1138_doc_wiring.py`):
- `circuit_breaker_enabled` at LOOPS_GUIDE.md:76,82

### 2. `skills/analyze-loop/SKILL.md`

- Line 108: event payload table lists `rate_limit_exhausted`; add `rate_limit_waiting` row with payload fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`)

### 3. `CHANGELOG.md`

**Note**: `[Unreleased]` currently has no `### Added` subsection — only `### Changed` at line 10. Create a new `### Added` subsection under `## [Unreleased]` (prior 429 entries at lines 27-30 are under `### Fixed` in released `[1.83.0]`; use them only as a style reference).

```markdown
- **Multi-Hour 429 Resilience with Shared Circuit Breaker** — Two-tier retry ladder (short-burst + long-wait) with wall-clock budget; `rate_limit_waiting` heartbeat events; cross-worktree circuit breaker to pre-sleep peers; new `StateConfig` fields `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder`. (ENH-1131)
```

### 4. `scripts/tests/test_enh1146_doc_wiring.py` (new file)

Follow the pattern in `scripts/tests/test_enh1138_doc_wiring.py` (read real files, assert strings present). Cover:

- `rate_limit_waiting` present in `docs/reference/EVENT-SCHEMA.md`
- `rate_limit_waiting` present in `docs/reference/OUTPUT_STYLING.md`
- `rate_limit_waiting` present in `skills/analyze-loop/SKILL.md`
- `rate_limit_max_wait_seconds` present in `docs/reference/API.md`
- `rate_limit_long_wait_ladder` present in `docs/reference/API.md`
- `22 \`LLEvent\` types` present in `docs/reference/CLI.md` (LLEvent type count — assert full phrase, not bare `22`, to avoid false matches)
- `rate_limit_waiting` present in `docs/reference/COMMANDS.md`

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md` — 3 locations
- `skills/analyze-loop/SKILL.md` — 1 location
- `CHANGELOG.md` — new entry

### New Files to Create

- `scripts/tests/test_enh1146_doc_wiring.py`

### Tests

- `python -m pytest scripts/tests/test_enh1146_doc_wiring.py` — new test (run after both ENH-1150 and ENH-1151 complete)
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` — regression check on LOOPS_GUIDE.md edits
- `ll-verify-docs` — event count check
- `ll-check-links` — catch broken internal links

### Codebase Research Findings (from parent ENH-1146)

- `scripts/little_loops/fsm/executor.py:56` — `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS = 21600`
- `scripts/little_loops/fsm/executor.py:59` — `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER = [300, 900, 1800, 3600]`
- `scripts/little_loops/loops/lib/common.yaml:61-62` — `with_rate_limit_handling` fragment defaults
- Tier values: `"short"` | `"long"` (from executor.py docstrings at lines 891-893, 942-944, 956)

### Codebase Research Findings (refine-issue, 2026-04-17)

_Added by `/ll:refine-issue` — verified against current files:_

**LOOPS_GUIDE.md line drift confirmed**:
- Per-state property table block spans lines 1020-1033. Rows `rate_limit_max_wait_seconds` (line 1032) and `rate_limit_long_wait_ladder` (line 1033) **already exist** — spot-check content before inserting to avoid duplicates.
- Prose section on two-tier retry ladder: lines 1670-1691 (issue said 1668-1680 — drifted by ~2 lines).
- `with_rate_limit_handling` fragment row in fragments table: **line 2051** (issue said 2028 — 2028 is an unrelated `my_gate` example block). Update the row at 2051.

**CHANGELOG.md has no `### Added` section under `[Unreleased]`**:
- Line 8: `## [Unreleased]` header
- Line 10: `### Changed` subsection (existing)
- Implementation must **create** a new `### Added` subsection under `[Unreleased]` — cannot simply append to an existing one. Prior 429-related entries are under `### Fixed` in released `[1.83.0]` at lines 25-30 (style reference only).

**skills/analyze-loop/SKILL.md event payload table**:
- Lines 101-111 contain the event payload table.
- Line 108: existing `rate_limit_exhausted` row with columns `short_retries`, `long_retries`, `total_wait_seconds`.
- Add new `rate_limit_waiting` row directly above/below line 108 with payload fields: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier` (values `"short"` | `"long"`).

**test_enh1138_doc_wiring.py pattern (at `scripts/tests/test_enh1138_doc_wiring.py`)**:
- No pytest imports; only `from pathlib import Path` and `from __future__ import annotations`.
- Module-level constants: `PROJECT_ROOT = Path(__file__).parent.parent.parent`, then per-file `Path` constants.
- One `Test<FileName>Wiring` class per target file; each method reads `.read_text()` fresh and asserts `"literal" in content` with a descriptive message.
- Method naming: `test_<symbol>_present`.

**CLI.md `22` assertion — refinement**:
- `docs/reference/CLI.md:~1081` contains phrase `"all 22 \`LLEvent\` types"`.
- Asserting bare `"22"` is too fragile (would match any `"22"` anywhere). Assert `"22 \`LLEvent\` types"` instead.

**Reference docs already contain `rate_limit_waiting`** (from ENH-1150 work):
- `docs/reference/EVENT-SCHEMA.md` — 4 occurrences (header, prose, JSON example, schema tree, event-source row)
- `docs/reference/OUTPUT_STYLING.md` — 3 occurrences (ANSI color table, summary table, prose note)
- `docs/reference/COMMANDS.md` — 1 occurrence (analyze-loop skill heuristics bullet)

### Test Skeleton (concrete template for step 4)

```python
from __future__ import annotations
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent.parent
EVENT_SCHEMA   = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
OUTPUT_STYLING = PROJECT_ROOT / "docs" / "reference" / "OUTPUT_STYLING.md"
ANALYZE_LOOP   = PROJECT_ROOT / "skills" / "analyze-loop" / "SKILL.md"
API_REFERENCE  = PROJECT_ROOT / "docs" / "reference" / "API.md"
CLI_REFERENCE  = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
COMMANDS       = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"

class TestEventSchemaWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in EVENT_SCHEMA.read_text(), \
            "docs/reference/EVENT-SCHEMA.md must document rate_limit_waiting heartbeat event"

class TestOutputStylingWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in OUTPUT_STYLING.read_text(), \
            "docs/reference/OUTPUT_STYLING.md must document rate_limit_waiting styling"

class TestAnalyzeLoopSkillWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in ANALYZE_LOOP.read_text(), \
            "skills/analyze-loop/SKILL.md event payload table must include rate_limit_waiting row"

class TestApiReferenceWiring:
    def test_rate_limit_max_wait_seconds_present(self) -> None:
        assert "rate_limit_max_wait_seconds" in API_REFERENCE.read_text(), \
            "docs/reference/API.md must reference rate_limit_max_wait_seconds"
    def test_rate_limit_long_wait_ladder_present(self) -> None:
        assert "rate_limit_long_wait_ladder" in API_REFERENCE.read_text(), \
            "docs/reference/API.md must reference rate_limit_long_wait_ladder"

class TestCliReferenceWiring:
    def test_llevent_type_count_present(self) -> None:
        assert "22 `LLEvent` types" in CLI_REFERENCE.read_text(), \
            "docs/reference/CLI.md must state '22 `LLEvent` types' (updated count after rate_limit_waiting)"

class TestCommandsWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in COMMANDS.read_text(), \
            "docs/reference/COMMANDS.md must document rate_limit_waiting in analyze-loop heuristics"
```

## Implementation Steps

1. Update `docs/guides/LOOPS_GUIDE.md` (3 touch points — spot-check lines before editing)
2. Update `skills/analyze-loop/SKILL.md` — add `rate_limit_waiting` event row
3. Add `CHANGELOG.md` entry under `### Added`
4. Write `scripts/tests/test_enh1146_doc_wiring.py` — new doc-wiring test
5. Run: `python -m pytest scripts/tests/test_enh1146_doc_wiring.py scripts/tests/test_enh1138_doc_wiring.py`
6. Run: `ll-verify-docs && ll-check-links`

## Acceptance Criteria

- `docs/guides/LOOPS_GUIDE.md` updated at all 3 touch points
- `skills/analyze-loop/SKILL.md` includes `rate_limit_waiting` event row
- `CHANGELOG.md` entry present under `### Added`
- `scripts/tests/test_enh1146_doc_wiring.py` written and passing
- `ll-verify-docs` passes

## Session Log
- `/ll:wire-issue` - 2026-04-17T09:19:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b68d27c-19f7-492b-9687-60064cd76d22.jsonl`
- `/ll:refine-issue` - 2026-04-17T09:13:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1030243e-f4a8-4833-8379-4788d463a4a2.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdbdbf5d-1514-44d9-a8b7-7ce3308a82dc.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd452bbb-10e6-480a-883e-7e149011a2a6.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee709210-6491-4684-b5fd-fd33f555658f.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1152: 429 Resilience — Heartbeat Docs (LOOPS_GUIDE, SKILL.md, CHANGELOG)
- ENH-1153: 429 Resilience — Heartbeat Doc-Wiring Tests

---

## Status
- [ ] Open
