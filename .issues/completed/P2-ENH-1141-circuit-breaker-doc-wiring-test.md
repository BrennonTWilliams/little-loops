---
id: ENH-1141
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
completed_date: 2026-04-17
parent: ENH-1138
related: [ENH-1138, ENH-1139, ENH-1140, ENH-1134]
size: Small
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1141: 429 Resilience — Doc Wiring Test and Link Verification

## Summary

Write `scripts/tests/test_enh1138_doc_wiring.py` to assert that ENH-1139 and ENH-1140 doc changes landed correctly, then run `ll-check-links` and `ll-verify-docs` to confirm no regressions.

## Parent Issue

Decomposed from ENH-1138: 429 Resilience — Documentation Updates for Circuit Breaker

## Dependencies

Implement after ENH-1139 (API.md updates) and ENH-1140 (prose doc updates) are complete.

## Expected Behavior

### Test file: `scripts/tests/test_enh1138_doc_wiring.py`

Follow the pattern from `scripts/tests/test_create_extension_wiring.py`.

Assert the following:

**`docs/reference/API.md` assertions (verified present in current doc state):**
- Contains `signal_detector` (currently at API.md:3673)
- Contains `handoff_handler` (currently at API.md:3670)
- Contains `loops_dir` (currently at API.md:431)
- Contains `circuit: RateLimitCircuit | None = None` (currently at API.md:4015)
- Contains `### little_loops.fsm.rate_limit_circuit` — the H3 class section header (currently at API.md:4446). Note: header is H3 (`###`), not H2.
- Contains `RateLimitCircuit,` — listed in the Quick Import block's multi-line `from little_loops.fsm import (…)` grouping (currently at API.md:3695, between `### Quick Import` at line 3675 and `### little_loops.fsm.schema` at line 3701). **Correction**: the literal string `from little_loops.fsm import RateLimitCircuit` does NOT appear in API.md — the Quick Import block uses a parenthesized multi-line import that lists `RateLimitCircuit,` on its own line with a `# Rate Limiting` comment above it. Assert on the presence of `RateLimitCircuit,` (trailing comma) and optionally on `# Rate Limiting` to anchor it to the Quick Import block.

**`docs/guides/LOOPS_GUIDE.md` assertions (verified present):**
- Contains `circuit_breaker_enabled` (currently at LOOPS_GUIDE.md:1702)
- Contains `circuit_breaker_path` (currently at LOOPS_GUIDE.md:1703)

**`docs/reference/CONFIGURATION.md` assertions (verified present):**
- Contains `circuit_breaker_enabled` (currently at CONFIGURATION.md:83, also 336)

### Verification steps

After the test file is written and passing:

1. Run `ll-check-links` — confirm no broken cross-references introduced by ENH-1139 or ENH-1140
2. Run `ll-verify-docs` — confirm no count regressions (no count changes expected)

## Integration Map

### Files to Create

- `scripts/tests/test_enh1138_doc_wiring.py`

### Reference Patterns

- `scripts/tests/test_create_extension_wiring.py` — canonical doc-wiring test (adds `not in` + `.count()` variations)
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — **closer model** (same subject area; already ships ENH-1143 assertions for `rate_limits: RateLimitsConfig` in API.md plus `circuit_breaker_enabled`/`circuit_breaker_path` in four `skills/**` files). New file should match its style exactly: per-file `TestXxxWiring` class, class docstring, one `.read_text()` per method, no helpers/fixtures, parenthesized failure messages.

**Non-duplication check**: `test_circuit_breaker_doc_wiring.py` covers different assertion targets (it does NOT check LOOPS_GUIDE.md, CONFIGURATION.md, or any of the new API.md strings ENH-1141 adds). Creating `test_enh1138_doc_wiring.py` as a separate file is correct — do not merge into the existing file; keeping them separate preserves the issue-ID-to-test mapping used across other wiring tests.

### Shared Pattern Details (from reference files)

- Imports: only `from __future__ import annotations` and `from pathlib import Path`
- Path anchor: `PROJECT_ROOT = Path(__file__).parent.parent.parent`
- Path constants at module top as `PROJECT_ROOT / "docs" / "reference" / "API.md"` etc.
- Read pattern inside each test method: `content = <CONST>.read_text()` (no caching)
- Assertion style: `assert "literal" in content, ("<path> must include `<literal>`")` — always include a parenthesized failure message
- One class per target file; method name describes the specific substring

### Files Verified By Tests

- `docs/reference/API.md`
- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/CONFIGURATION.md`

### Dependent CLI Tools (invoked after test passes)

- `ll-check-links` → `little_loops.cli:main_check_links` (console_script in `scripts/pyproject.toml:57-58`, impl in `scripts/little_loops/cli/docs.py`)
- `ll-verify-docs` → `little_loops.cli:main_verify_docs` (same location)

### Source Module (subject of the assertions)

- `scripts/little_loops/fsm/rate_limit_circuit.py` — `RateLimitCircuit` class (documented by the API.md section header assertion)

### Sibling Issues (context)

- `.issues/completed/P2-ENH-1134-429-resilience-circuit-breaker-module.md` — module source
- `.issues/completed/P2-ENH-1138-circuit-breaker-docs.md` — parent
- `.issues/completed/P2-ENH-1139-circuit-breaker-api-md-updates.md` — produced the API.md strings
- `.issues/completed/P2-ENH-1140-circuit-breaker-prose-doc-updates.md` — produced the LOOPS_GUIDE.md / CONFIGURATION.md strings

## Implementation Steps

1. **Read `scripts/tests/test_circuit_breaker_doc_wiring.py`** (closer model than `test_create_extension_wiring.py` — same subject domain, same style, no negative assertions).
2. **Write `scripts/tests/test_enh1138_doc_wiring.py`** with:
   - Module docstring referencing ENH-1138/ENH-1139/ENH-1140
   - Three path constants: `API_REFERENCE`, `LOOPS_GUIDE`, `CONFIGURATION`
   - Three classes: `TestApiReferenceWiring`, `TestLoopsGuideWiring`, `TestConfigurationWiring`
   - Individual test methods for each literal string listed under *Expected Behavior*
   - Parenthesized failure messages on every assertion
3. **Run the specific test**: `python -m pytest scripts/tests/test_enh1138_doc_wiring.py -v` (ENH-1139 and ENH-1140 already completed per commits `442311cc` and `69334f14`, so all assertions should already pass against the current doc state).
4. **Run the full test suite**: `python -m pytest scripts/tests/` to confirm no regressions.
5. **Run `ll-check-links`** to confirm no broken links.
6. **Run `ll-verify-docs`** to confirm no count regressions.

## Acceptance Criteria

- `test_enh1138_doc_wiring.py` exists and all assertions pass
- `ll-check-links` reports no new broken links
- `ll-verify-docs` reports no count regressions

## Resolution

Added `scripts/tests/test_enh1138_doc_wiring.py` modeled on
`test_circuit_breaker_doc_wiring.py`: three classes
(`TestApiReferenceWiring`, `TestLoopsGuideWiring`,
`TestConfigurationWiring`) with 10 substring assertions covering the
API.md `RateLimitCircuit` surface, Quick Import grouping, and the
`circuit_breaker_enabled` / `circuit_breaker_path` prose doc fields.

All 10 new tests pass; full suite 4922 passed / 5 skipped. `ll-check-links`
and `ll-verify-docs` report no regressions introduced by ENH-1139/1140
(the 3 broken links flagged are pre-existing and unrelated to this issue).

## Session Log
- `/ll:manage-issue` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c75d3b3-4717-4739-babf-180962235e0b.jsonl`
- `/ll:wire-issue` - 2026-04-17T06:53:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39d35ae7-2c23-475d-912b-3429c70ba400.jsonl`
- `/ll:refine-issue` - 2026-04-17T06:50:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2338b6f7-547d-411e-845b-2dd0d7fed16b.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6682d5-cb79-4c33-9ce6-ede83cb84a43.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe6c8c43-d29f-4dc0-99d5-1b7f311480cd.jsonl`

---

## Status
- [x] Completed
