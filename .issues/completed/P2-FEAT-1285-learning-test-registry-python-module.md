---
id: FEAT-1285
type: FEAT
priority: P2
captured_at: "2026-04-25T00:00:00Z"
completed_at: "2026-04-25T19:36:39Z"
discovered_date: "2026-04-25"
discovered_by: issue-size-review
parent_issue: FEAT-1282
size: Medium
decision_needed: false
confidence_score: 85
outcome_confidence: 60
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-1285: Learning Test Registry Python Module

## Summary

Implement the `scripts/little_loops/learning_tests.py` module with `LearnTestRecord` dataclass, CRUD functions (`write_record`, `read_record`, `list_records`, `mark_stale`), config integration (`LearningTestsConfig`, `config-schema.json` wiring), and package registration. This is the foundational layer that all downstream features (CLI, skill, ENH-1283, ENH-1284) depend on.

## Parent Issue

Decomposed from FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Proposed Solution

### Registry record format

`.ll/learning-tests/<slug>.md` with frontmatter:
```yaml
---
target: "Anthropic SDK streaming"
date: "2026-04-25"
status: proven  # proven | refuted | stale
assertions:
  - claim: "streaming events are dicts with a `type` key"
    result: pass
  - claim: "fork_session=true is required for resumed sessions"
    result: pass
raw_output_path: ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"
---
```

### Python API

```python
# scripts/little_loops/learning_tests.py

@dataclass
class Assertion:
    claim: str
    result: Literal["pass", "fail", "untested"]

@dataclass
class LearnTestRecord:
    target: str
    date: str
    status: Literal["proven", "refuted", "stale"]
    assertions: list[Assertion]
    raw_output_path: str | None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "LearnTestRecord": ...

def write_record(record: LearnTestRecord) -> Path: ...
def read_record(target_slug: str) -> LearnTestRecord | None: ...
def list_records() -> list[LearnTestRecord]: ...
def mark_stale(target_slug: str) -> None: ...
def check_learning_test(target: str) -> LearnTestRecord | None: ...
```

### Key implementation notes

- Use `parse_frontmatter` from `scripts/little_loops/frontmatter.py:18` for deserialization
- Use `update_frontmatter` from `scripts/little_loops/frontmatter.py:110` for writes
- Model `LearnTestRecord` after `IssueInfo` dataclass at `scripts/little_loops/issue_parser.py:202`
- Use `Literal["proven", "refuted", "stale"]` pattern from `scripts/little_loops/fsm/schema.py:56`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### CRITICAL: `parse_frontmatter` cannot parse nested `assertions`

`parse_frontmatter` at `frontmatter.py:18` handles only flat top-level keys (strings, ints, inline lists of strings). Block sequences of dicts (the proposed `assertions` format) return `None` silently. Two competing approaches:

**Option A: Extract frontmatter block and call `yaml.safe_load` directly** (recommended)
> **Selected:** Option A — the `yaml.safe_load(fm_match.group(1))` pattern already exists verbatim in `frontmatter.py:130` and `sync.py:179`; reuses proven mechanics with no format change to the on-disk schema.
- Extract the `---\n...\n---\n` block, strip delimiters, call `yaml.safe_load`
- `update_frontmatter` (line 110) already does this internally for round-trips, so writes are safe
- Consistent with how nested data survives `update_frontmatter` calls; no format change needed

**Option B: Flatten `assertions` to an inline-JSON string**
- Store as `assertions: '[{"claim": "...", "result": "pass"}]'`
- `parse_frontmatter` handles plain strings; deserialize with `json.loads` in `from_dict`
- Simpler read path but less human-editable; YAML format diverges from the proposed schema

> `decision_needed: true` — run `/ll:decide-issue FEAT-1285` to select Option A or B before implementing.

#### Slug generation
- Use `slugify(target)` from `scripts/little_loops/issue_parser.py:99-110`
- Import as: `from little_loops.issue_parser import slugify`
- Already used by `issue_lifecycle.py:484` and `parallel/worker_pool.py:243`

#### Missing config wiring steps (not in Implementation Steps)
- `BRConfig.learning_tests` **property** — add `@property` in `config/core.py` following `@property loops` at lines 152-155
- `BRConfig.to_dict()` — add `learning_tests` dict block at `config/core.py:348-476` following `sprints`/`loops` pattern

### Config integration (3 files)

- `config-schema.json` — add `learning_tests` to `"properties"` block alongside `"loops"` (line 756) and `"sprints"` (line 731); must do this since `"additionalProperties": false` is set
- `scripts/little_loops/config/features.py` — add `LearningTestsConfig` dataclass with `stale_after_days: int = 30` and `@classmethod from_dict(cls, data)`
- `scripts/little_loops/config/core.py:95-115` — add `self._learning_tests = LearningTestsConfig.from_dict(self._raw_config.get("learning_tests", {}))`

### Package registration (2 files)

- `scripts/little_loops/config/__init__.py` — add `LearningTestsConfig` to `__all__` (lines 32-46)
- `scripts/little_loops/__init__.py:1-79` — add `check_learning_test` and `LearnTestRecord` to public API exports

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-25.

**Selected**: Option A: Extract frontmatter block and call `yaml.safe_load` directly

**Reasoning**: The `yaml.safe_load(fm_match.group(1))` pattern exists verbatim in two places in the codebase (`frontmatter.py:130` and `sync.py:179`), both as write-path helpers that prove the mechanism handles nested YAML correctly. Option B requires quoting the JSON value in YAML to avoid corruption by `parse_frontmatter`'s `[` branch at `frontmatter.py:67-69`, introduces JSON-in-YAML with zero codebase precedent, and diverges from the native YAML block sequence format proposed in the issue schema itself.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (yaml.safe_load) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B (inline-JSON string) | 0/3 | 1/3 | 2/3 | 1/3 | 4/12 |

**Key evidence**:
- **Option A**: `yaml.safe_load(fm_match.group(1))` used in `frontmatter.py:130` and `sync.py:179`; `update_frontmatter` directly reusable for writes; `temp_project_dir` fixture at `conftest.py:55-62` supports tests
- **Option B**: `parse_frontmatter`'s `[` branch at `frontmatter.py:67-69` would corrupt unquoted JSON arrays; zero JSON-in-YAML precedent; diverges from native YAML block sequence schema proposed in issue

## Files to Create/Modify

- `scripts/little_loops/learning_tests.py` — **create** (new module)
- `scripts/little_loops/config/features.py` — add `LearningTestsConfig`
- `scripts/little_loops/config/core.py` — wire `_learning_tests` in `_parse_config()`
- `scripts/little_loops/config/__init__.py` — re-export `LearningTestsConfig`
- `scripts/little_loops/__init__.py` — export public symbols
- `config-schema.json` — add `learning_tests` property
- `scripts/tests/test_learning_tests.py` — **create** (new test file)
- `scripts/tests/test_config.py` — add `TestLearningTestsConfig` and `TestBRConfigLearningTestsIntegration` classes
- `scripts/tests/test_config_schema.py` — add `test_learning_tests_in_schema` sentinel
- `docs/reference/API.md` — document `learning_tests` module

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py:239` — add `LearningTestsConfig` after `SprintsConfig` (same pattern: `@dataclass`, fields with defaults, `from_dict()`)
- `scripts/little_loops/config/core.py:95-115` — add `self._learning_tests = LearningTestsConfig.from_dict(...)` in `_parse_config()`
- `scripts/little_loops/config/core.py:152-155` — add `@property learning_tests` following `@property loops` pattern
- `scripts/little_loops/config/core.py:348-476` — add `learning_tests` dict block in `to_dict()` following `sprints`/`loops` pattern
- `scripts/little_loops/config/__init__.py:32-46` — import `LearningTestsConfig` from `features`; add to `__all__` (lines 48-79)
- `scripts/little_loops/__init__.py:39-79` — add `check_learning_test`, `LearnTestRecord` to imports and `__all__`
- `config-schema.json` — add `learning_tests` object after `"loops"` block (~line 787); follow `sprints` schema at line 731

### Files to Create
- `scripts/little_loops/learning_tests.py` — new module (no existing callers yet)
- `scripts/tests/test_learning_tests.py` — CRUD tests (create, read, mark-stale, list-all)

### Similar Patterns
- `scripts/little_loops/config/features.py:239-253` — `SprintsConfig` dataclass pattern for `LearningTestsConfig`
- `scripts/little_loops/config/core.py:152-155` — `@property loops` pattern for `@property learning_tests`
- `scripts/tests/test_config.py:511-533` — `TestSprintsConfig` structure to follow for `TestLearningTestsConfig`
- `scripts/tests/test_config.py:1587-1610` — `TestBRConfigLoopsGlyphs` integration pattern for `TestBRConfigLearningTestsIntegration`
- `scripts/tests/test_config_schema.py:82-95` — schema sentinel pattern for `test_learning_tests_in_schema`

### Tests
- `scripts/tests/conftest.py:55-62` — `temp_project_dir` fixture yields `project_root: Path` with `.ll/` pre-created; tests must `mkdir` `.ll/learning-tests/` themselves
- `scripts/tests/test_config.py` — add `TestLearningTestsConfig` and `TestBRConfigLearningTestsIntegration`
- `scripts/tests/test_config_schema.py` — add `test_learning_tests_in_schema`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_extension.py:469-543` — add `test_smoke_import_check_learning_test` and `test_smoke_import_learn_test_record` smoke import tests following the `TestNewProtocols` pattern [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — add `little_loops.learning_tests` to Module Overview table and document public symbols

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:176-289` — `scripts/little_loops/` directory tree; add `learning_tests.py` entry [Agent 2 finding]
- `CONTRIBUTING.md:200-254` — `scripts/little_loops/` directory tree; add `learning_tests.py` entry [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — add `learning_tests` section with `stale_after_days` field documentation and example JSON block; no entry currently exists [Agent 2 finding]

## Implementation Steps

1. Create `.ll/learning-tests/` directory structure
2. Implement `learning_tests.py` module with dataclasses and CRUD functions
3. Add `LearningTestsConfig` to `config/features.py`
4. Wire config in `core.py` and re-export in `config/__init__.py`
5. Update `config-schema.json` to add `learning_tests` property
6. Register public symbols in `__init__.py`
7. Write tests in `test_learning_tests.py` (create/read/mark-stale/list-all, using `temp_project_dir` fixture)
8. Add config tests to `test_config.py` and schema sentinel to `test_config_schema.py`
9. Update `docs/reference/API.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` — add `learning_tests.py` to the `scripts/little_loops/` directory tree listings
11. Update `docs/reference/CONFIGURATION.md` — add `learning_tests` section with `stale_after_days` field documentation and an example JSON block (no entry currently exists for this config area)
12. Add smoke import tests in `scripts/tests/test_extension.py` — `test_smoke_import_check_learning_test` and `test_smoke_import_learn_test_record`, following the `TestNewProtocols` pattern at lines 469–543

_Note: `skills/configure/SKILL.md` area mapping table (lines 99–113) and `skills/configure/areas.md` do not include a `learning_tests` area — running `/ll:configure --list` will not show this config section after it lands. This is a downstream concern; consider capturing as a separate enhancement after FEAT-1286 lands._

## Acceptance Criteria

- `write_record()` creates a valid frontmatter `.md` file in `.ll/learning-tests/`
- `read_record()` deserializes back to identical `LearnTestRecord`
- `mark_stale()` updates `status: stale` without losing other fields
- `list_records()` returns all records in the directory
- `LearningTestsConfig` parses from `ll-config.json` with sensible defaults
- `config-schema.json` validates a config containing `learning_tests.stale_after_days`
- All tests pass: `python -m pytest scripts/tests/test_learning_tests.py scripts/tests/test_config.py scripts/tests/test_config_schema.py -v`

## Dependencies

None — this is the foundational layer.

## Downstream Dependents

- FEAT-1286 (CLI tool) — imports and exposes this module via CLI
- FEAT-1287 (explore-api skill) — calls `write_record` and `read_record` indirectly via CLI
- ENH-1283 (FSM learning state) — calls `check_learning_test()` before advancing FSM
- ENH-1284 (issue lifecycle gate) — queries registry during `ll:ready-issue`

---

**Completed** | Created: 2026-04-25 | Completed: 2026-04-25 | Priority: P2

## Resolution

All acceptance criteria met:

- `write_record()` creates a valid frontmatter `.md` file in `.ll/learning-tests/`
- `read_record()` deserializes nested `assertions` back to identical `LearnTestRecord` using `yaml.safe_load`
- `mark_stale()` updates `status: stale` without losing other fields (delegates to `update_frontmatter`)
- `list_records()` returns all records in the directory
- `LearningTestsConfig` parses from `ll-config.json` with `stale_after_days=30` default
- `config-schema.json` validates a config containing `learning_tests.stale_after_days`
- All 28 tests pass

**Files created**: `scripts/little_loops/learning_tests.py`, `scripts/tests/test_learning_tests.py`

**Files modified**: `config/features.py`, `config/core.py`, `config/__init__.py`, `__init__.py`, `config-schema.json`, `test_config.py`, `test_config_schema.py`, `test_extension.py`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/reference/CONFIGURATION.md`


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-25_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 60/100 → MODERATE

### Concerns
- **Unresolved serialization decision**: The issue has `decision_needed: true` and explicitly directs you to run `/ll:decide-issue FEAT-1285` before implementing. Option A (yaml.safe_load for nested assertions) vs Option B (inline-JSON string) affects the on-disk format, `from_dict`, and any future consumers. Starting without resolving this risks having to rewrite the core read/write path.
- **Wide implementation breadth**: 14 files across 4+ subsystems (new module, config wiring, tests, docs). All changes are additive, but the span means you need to hold more context simultaneously — plan for methodical pass-by-pass execution rather than a single sweep.

## Session Log
- `/ll:manage-issue` - 2026-04-25T19:36:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7f436c4-e846-47c8-8784-9e30750c1037.jsonl`
- `/ll:ready-issue` - 2026-04-25T19:26:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4976a136-d8c0-4a43-bd93-2067c8e0ea33.jsonl`
- `/ll:decide-issue` - 2026-04-25T19:23:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e01f4663-cf90-46a5-9bf2-707bcff9ccec.jsonl`
- `/ll:confidence-check` - 2026-04-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`
- `/ll:wire-issue` - 2026-04-25T19:05:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e58ad7a-a8c3-41cd-9261-6c51bd4412fc.jsonl`
- `/ll:refine-issue` - 2026-04-25T18:59:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8327f553-dd40-49de-9353-6656cb7f6d56.jsonl`
