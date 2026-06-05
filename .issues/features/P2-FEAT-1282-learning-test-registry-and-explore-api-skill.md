---
id: FEAT-1282
type: FEAT
priority: P2
status: open
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
size: Very Large
completed_at: 2026-04-25T00:00:00Z
---

# FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Summary

Add a `.ll/learning-tests/` registry directory that stores executed proof records of external system behaviors, paired with a new `ll:explore-api` skill that implements the full Feathers Learning Test lifecycle (Ingest → Hypothesize → Execute → Refine). Together they give agents institutional knowledge of proven assumptions before committing to architecture.

## Current Behavior

When an agent encounters an unfamiliar external system (API, SDK, binary), it either hallucinates behavior from stale docs or requires a human to manually investigate. There is no structured way to capture, execute, and store proof-of-behavior for external systems. Assumption leakage causes faulty premises at discovery time to invalidate entire implementations.

## Expected Behavior

Running `/ll:explore-api "Anthropic SDK streaming"` triggers a structured discovery session:
1. **Ingest** — reads relevant docs and existing code samples for the target
2. **Hypothesize** — generates specific testable claims (e.g., "streaming events are dicts with `type` key")
3. **Execute** — scaffolds and runs a proof script against the live system, capturing stdout/stderr
4. **Refine** — diffs expected vs actual, updates claims, and saves a proof record to `.ll/learning-tests/<target>.md`

The registry then serves as institutional knowledge: any skill or loop can query it to check whether an assumption about a system has been deterministically proven before implementation begins.

## Motivation

The "slop code crisis" described in our architecture notes is directly caused by agents building on unproven assumptions. A learning test registry transforms one-off exploration into reusable, time-stamped proof. This prevents the same faulty assumption from being re-made across sessions and provides the deterministic foundation that the FSM learning state (ENH-1283) and issue lifecycle gate (ENH-1284) will build on. Without this, both dependent features have nothing to query.

## Proposed Solution

**Registry format** — `.ll/learning-tests/<slug>.md` with frontmatter:
```yaml
---
target: "Anthropic SDK streaming"
date: "2026-04-25"
status: done
assertions:
  - claim: "streaming events are dicts with a `type` key"
    result: pass
  - claim: "fork_session=true is required for resumed sessions"
    result: pass
raw_output_path: ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"
---
```

**`ll:explore-api` skill** (new file: `skills/explore-api/SKILL.md`):
- Accepts a target string and optional assumption list
- Scaffolds a minimal runnable proof script (Python or TypeScript based on target)
- Executes via `Bash` and captures output
- Parses pass/fail per claim, writes registry record
- Reports proven facts back to conversation context

**Query interface** — `ll-issues` or a helper function that other skills can call: `check_learning_test(target: str) -> LearnTestRecord | None`

## Integration Map

### Files to Modify
- `scripts/little_loops/` — add `learning_tests.py` module for registry read/write
- `scripts/pyproject.toml` — no new deps expected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — re-export `LearningTestsConfig` in `__all__` (lines 32-46)
- `scripts/little_loops/cli/__init__.py` — add `main_learning_tests` import (lines 23-41), docstring entry, and `__all__` entry (lines 44-65)
- `scripts/little_loops/cli/learning_tests.py` — new CLI handler implementing `main_learning_tests` for the `ll-learning-tests` entry point
- `README.md` — increment skill count (27→28) and CLI tool count (16→17); add `explore-api^` skill table row and `### ll-learning-tests` CLI subsection
- `CONTRIBUTING.md` — increment skill count (line 125); add `├── explore-api/` to skills tree and `├── learning_tests.py` to module tree
- `commands/help.md` — add `ll-learning-tests` entry to hardcoded CLI tools list (lines 216-234)
- `.claude/CLAUDE.md` — increment skill count (line 38), add `ll-learning-tests` to CLI tools list (not covered by `ll-verify-docs`)

### Dependent Files (Callers/Importers)
- ENH-1283 (`learning` FSM state) will call the registry to verify tests ran before advancing
- ENH-1284 (issue lifecycle gate) will query the registry during `ll:ready-issue`

### Similar Patterns
- `.ll/ll-config.json` — same directory pattern for project-local state
- `scripts/little_loops/issue_parser.py` — frontmatter parsing pattern to reuse

### Tests
- `scripts/tests/test_learning_tests.py` — new test file for registry CRUD
- Test: create record, read back, mark stale

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add `TestLearningTestsConfig` class (following `TestSprintsConfig` at line 511) and `TestBRConfigLearningTestsIntegration` class (following `TestBRConfigSyncIntegration` at line 1116) — covers config wiring [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_learning_tests_in_schema` sentinel (following `test_loops_glyphs_parallel_in_schema` at line 82) to guard against omitting `learning_tests` from schema `properties` block when `"additionalProperties": false` is set [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — add learning test registry section
- `docs/reference/API.md` — document `learning_tests` module

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `### ll-learning-tests` reference section for the new CLI tool [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — optional `learning_tests.stale_after_days` setting

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Frontmatter Engine (actual reuse target)
- `scripts/little_loops/frontmatter.py:18` — `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` — the actual frontmatter engine; `issue_parser.py` calls this, it does not define it
- `scripts/little_loops/frontmatter.py:110` — `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` — merges keys into existing frontmatter or creates new block
- `scripts/little_loops/frontmatter.py:87` — `strip_frontmatter(content: str) -> str` — returns body after closing `---`
- Import: `from little_loops.frontmatter import parse_frontmatter, update_frontmatter`

#### Dataclass Reference Implementations
- `scripts/little_loops/issue_parser.py:202` — `IssueInfo` dataclass: full `to_dict()` / `from_dict()` round-trip pattern with `list`, `dict`, `bool | None`, `int | None` fields
- `scripts/little_loops/fsm/schema.py:24` — `EvaluateConfig` shows `Literal["proven", "refuted", "stale"]` type constraint pattern in dataclass fields
- `scripts/little_loops/issue_parser.py:156` — `ProductImpact` shows minimal Optional-field dataclass with `from_dict(cls, data: dict | None)` classmethod

#### Module Registration
- `scripts/little_loops/__init__.py:1-79` — public API registration: import symbols and add to `__all__`
- Alternative: internal-only import pattern (skip `__init__.py`) if `learning_tests` is only used by CLI and tests — same pattern as `frontmatter.py`
- Decision: given `check_learning_test()` is intended to be called by other skills/loops, the public API path is recommended

#### Config Integration Chain (3 files)
- `config-schema.json` — uses `"additionalProperties": false` at top level; `learning_tests` key **must** be added to `"properties"` block alongside `"loops"` (line 756), `"sprints"` (line 731)
- `scripts/little_loops/config/features.py` — add `LearningTestsConfig` dataclass with `@classmethod from_dict(cls, data)` following existing config dataclass pattern
- `scripts/little_loops/config/core.py:95-115` — `BRConfig._parse_config()` — add: `self._learning_tests = LearningTestsConfig.from_dict(self._raw_config.get("learning_tests", {}))`

#### CLI Query Surface Gap
The issue proposes `check_learning_test(target: str) -> LearnTestRecord | None` callable by "other skills or loops." Skills invoke Python only via Bash CLI tools — a raw Python function is not callable from a skill. This requires one of:
- A subcommand on an existing CLI (e.g., `ll-issues learning-test check <target>`)
- A new `ll-learning-tests` CLI tool registered in `scripts/pyproject.toml:48-67`
This decision must be made before authoring `skills/explore-api/SKILL.md`. Without a CLI surface, the skill cannot query the registry.

#### Skill Structure References
- `skills/manage-issue/SKILL.md` — canonical multi-phase skill: frontmatter with `description`, `argument-hint`, `allowed-tools`, `arguments`; numbered `## Phase N:` sections; `{{config.*}}` interpolation
- `skills/capture-issue/SKILL.md` — shows `Bash(ll-issues:*)` session log appending and `AskUserQuestion` inline
- `skills/wire-issue/SKILL.md` — shows flag-parsing pseudocode in skill body

#### Test Fixtures
- `scripts/tests/conftest.py` — `temp_project_dir` fixture yields a `Path` with `.ll/` already created — use for registry file I/O tests
- `scripts/tests/test_frontmatter.py:180` — `TestUpdateFrontmatter` shows pattern for testing frontmatter round-trips with content strings
- `scripts/tests/test_events.py:15` — `TestLLEvent.test_roundtrip` shows `to_dict()` / `from_dict()` verification pattern

#### FSM Alternative (optional)
The 4-phase lifecycle could be authored as an FSM loop using existing infrastructure:
- `scripts/little_loops/fsm/persistence.py:64` — `LoopState.current_state` tracks current phase across iterations
- `scripts/little_loops/loops/` — existing YAML loop templates to model after
- This is optional for MVP; a linear skill is sufficient if FSM resumability is not needed

## Implementation Steps

1. Create `.ll/learning-tests/` directory structure and define registry record schema
2. Implement `scripts/little_loops/learning_tests.py` with read/write/query functions
3. Scaffold `skills/explore-api/SKILL.md` with Ingest → Hypothesize → Execute → Refine flow
4. Wire skill to write registry records on completion
5. Add `scripts/tests/test_learning_tests.py` with unit tests
6. Update `docs/ARCHITECTURE.md` and `docs/reference/API.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Decide CLI surface first**: Before writing the skill or module, resolve how `check_learning_test()` is exposed to Bash (see Integration Map gap). Recommend adding `ll-learning-tests` subcommand to `pyproject.toml:48-67` or extending `ll-issues` with a `learning-test` subgroup. This gates step 3.
2. **Registry module** (`scripts/little_loops/learning_tests.py`): Call `parse_frontmatter` from `frontmatter.py:18` for record deserialization; use `update_frontmatter` from `frontmatter.py:110` for writes; model `LearnTestRecord` after `IssueInfo` dataclass pattern (`issue_parser.py:202`) with `to_dict()`/`from_dict()`; use `Literal["proven", "refuted", "stale"]` pattern from `fsm/schema.py:24`
3. **Config schema** (if `stale_after_days` setting is included): Add `learning_tests` to `config-schema.json` properties; add `LearningTestsConfig` in `scripts/little_loops/config/features.py`; wire into `BRConfig._parse_config()` at `config/core.py:95-115`
4. **Package registration**: Add to `scripts/little_loops/__init__.py:1-79` if public API; otherwise consumers import directly via `from little_loops.learning_tests import ...`
5. **Skill file** (`skills/explore-api/SKILL.md`): Follow frontmatter structure from `skills/manage-issue/SKILL.md`; use `Bash(ll-issues:*)` for session log appending; use `Write` for creating registry records; use `Read`/`Glob`/`Grep` for codebase research in Ingest phase
6. **Tests** (`scripts/tests/test_learning_tests.py`): Use `temp_project_dir` from `conftest.py` for file I/O; follow `test_frontmatter.py:180` for read/write coverage; follow `test_events.py:15` for `to_dict()`/`from_dict()` round-trip; cover: create record, read back, mark stale, list all
7. **Verification**: `python -m pytest scripts/tests/test_learning_tests.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Create `scripts/little_loops/cli/learning_tests.py` — implement `main_learning_tests` as entry point for `ll-learning-tests` CLI tool, following conventions in existing CLI modules (e.g., `cli/sync.py`)
9. Update `scripts/little_loops/config/__init__.py` — add `LearningTestsConfig` to re-exports in `__all__` (lines 32-46), after adding to `config/features.py`
10. Update `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.learning_tests import main_learning_tests` import and `__all__` entry (lines 23-65)
11. Update `scripts/tests/test_config.py` — add `TestLearningTestsConfig` and `TestBRConfigLearningTestsIntegration` (6 tests each), following patterns at lines 511 and 1116
12. Update `scripts/tests/test_config_schema.py` — add `test_learning_tests_in_schema` sentinel following `test_loops_glyphs_parallel_in_schema` at line 82
13. Update `README.md` — increment skill count (27→28) and CLI tool count (16→17); add `explore-api^` skill table row and `### ll-learning-tests` CLI section
14. Update `CONTRIBUTING.md` — increment skill count (line 125); add `├── explore-api/` and `├── learning_tests.py` to directory trees
15. Update `commands/help.md` — add `ll-learning-tests` entry to hardcoded CLI tools list (lines 216-234)
16. Update `.claude/CLAUDE.md` — increment skill count (line 38), add `ll-learning-tests` to CLI tools list
17. Update `docs/reference/CLI.md` — add `### ll-learning-tests` reference section

## Success Metrics

- Running `/ll:explore-api` produces a `.ll/learning-tests/` record with at least one proven/refuted claim
- Registry records are queryable by other skills/loops without re-executing proofs
- Stale records (configurable age) are flagged during queries

## Scope Boundaries

- Out of scope: automatic staleness enforcement (records are flagged, not auto-deleted)
- Out of scope: sharing registry records across projects
- Out of scope: UI for browsing the registry (plain markdown files serve as the interface)

## API/Interface

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

def write_record(record: LearnTestRecord) -> Path: ...
def read_record(target_slug: str) -> LearnTestRecord | None: ...
def list_records() -> list[LearnTestRecord]: ...
def mark_stale(target_slug: str) -> None: ...
```

## Impact

- **Priority**: P2 — This is the foundation for two downstream features (ENH-1283, ENH-1284) and directly addresses assumption leakage in autonomous runs
- **Effort**: Medium — New skill + new Python module + registry schema design; reuses existing frontmatter parsing patterns
- **Risk**: Low — Additive only; no existing behavior changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for where registry fits |
| `docs/deterministic-backpressure-learning-tests.md` | Source philosophy and Learning Test lifecycle definition |

## Labels

`enhancement`, `autonomy`, `learning-tests`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T22:14:34 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T20:39:40 - `878c5913-3278-47e9-865c-2f4ceb07948f.jsonl`
- `/ll:refine-issue` - 2026-05-16T21:36:45 - `e1da9d61-83f1-4718-91ec-4ed0e57454c9.jsonl`
- `/ll:wire-issue` - 2026-04-25T18:49:33 - `6cab145e-64ca-41f6-9cfa-67c06772edcb.jsonl`
- `/ll:refine-issue` - 2026-04-25T18:42:55 - `3448382b-328e-4cb4-aaea-f22958449e93.jsonl`
- `/ll:confidence-check` - 2026-04-25T00:00:00Z - `408be939-366d-4ada-a014-a49f41e9c0e9.jsonl`
- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`
- `/ll:issue-size-review` - 2026-04-25T00:00:00Z - `4dc8248e-f52c-48ec-8099-31b22aeb934f.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-25
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1285: Learning Test Registry Python Module
- FEAT-1286: ll-learning-tests CLI Tool
- FEAT-1287: ll:explore-api Skill

---

**Decomposed** | Created: 2026-04-25 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-31): This issue's "registry" is the `.ll/learning-tests/` directory of markdown proof records for **external API and system behavior** — proof-of-behavior documents created by the `ll:explore-api` skill, queried via `ll-learning-tests`. This is entirely distinct from FEAT-917's "Extension Registry," which covers third-party installable PyPI packages (`little-loops-ext-*`) discoverable via `ll extensions`. Do not conflate the two: learning-tests records live in `.ll/learning-tests/<slug>.md` (local, project-scoped, markdown); extension manifests live in `pyproject.toml` metadata (published, PyPI-scoped, TOML). Neither registry's CLI commands, storage paths, nor data models should be shared with the other. Related: FEAT-917.

## Verification Notes (2026-06-05)

- **Decomposed children appear IMPLEMENTED**: `learning_tests.py`, `cli/learning_tests.py`,
  `skills/explore-api/SKILL.md`, `LearningTestsConfig` all exist in the codebase. The parent
  issue was decomposed into FEAT-1285/1286/1287 which were implemented.
- **Stale line references**: `frontmatter.py` refs drifted (L18→L29, L110→L190,
  `strip_frontmatter` renamed to inline logic at L180-187). `issue_parser.py` refs drifted
  (IssueInfo L202→L211, ProductImpact L156→L165).
- **Recommendation**: Consider closing parent as done, or updating to reflect post-decomposition state.
