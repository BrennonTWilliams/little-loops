---
id: ENH-1153
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1151
related: [ENH-1144, ENH-1150, ENH-1152]
size: Small
---

# ENH-1153: 429 Resilience — Heartbeat Doc-Wiring Tests

## Summary

Write `scripts/tests/test_enh1146_doc_wiring.py` to assert all `rate_limit_waiting` heartbeat doc content is present across reference files, then run all verification commands.

## Parent Issue

Decomposed from ENH-1151: 429 Resilience — Heartbeat Docs (Guide, Skill, Changelog, Tests).

## Dependency Note

Run this issue **after** ENH-1152 completes (doc edits). The test file asserts strings written by ENH-1150 and ENH-1152.

## Expected Behavior

### `scripts/tests/test_enh1146_doc_wiring.py` (new file)

Follow the pattern in `scripts/tests/test_enh1138_doc_wiring.py` (read real files, assert strings present). Cover:

- `rate_limit_waiting` present in `docs/reference/EVENT-SCHEMA.md`
- `rate_limit_waiting` present in `docs/reference/OUTPUT_STYLING.md`
- `rate_limit_waiting` present in `skills/analyze-loop/SKILL.md`
- `rate_limit_max_wait_seconds` present in `docs/reference/API.md`
- `rate_limit_long_wait_ladder` present in `docs/reference/API.md`
- `22 \`LLEvent\` types` present in `docs/reference/CLI.md`
- `rate_limit_waiting` present in `docs/reference/COMMANDS.md`

### Test Skeleton (fully specified — copy and run)

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

## Integration Map

### New Files to Create

- `scripts/tests/test_enh1146_doc_wiring.py`

### Tests to Run

- `python -m pytest scripts/tests/test_enh1146_doc_wiring.py` — new test (after ENH-1152 completes)
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` — regression check
- `ll-verify-docs` — event count check
- `ll-check-links` — catch broken internal links

## Implementation Steps

1. Write `scripts/tests/test_enh1146_doc_wiring.py` using the skeleton above
2. Run `python -m pytest scripts/tests/test_enh1146_doc_wiring.py scripts/tests/test_enh1138_doc_wiring.py`
3. Run `ll-verify-docs && ll-check-links`

## Acceptance Criteria

- `scripts/tests/test_enh1146_doc_wiring.py` written and all 7 assertions pass
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` passes (regression)
- `ll-verify-docs` passes

## Session Log
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee709210-6491-4684-b5fd-fd33f555658f.jsonl`

---

## Status
- [ ] Open
