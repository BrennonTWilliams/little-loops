---
id: ENH-1430
type: ENH
priority: P2
parent: ENH-1391
status: done
completed_at: 2026-05-10T23:02:46Z
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1430: Standardize Relationship Fields — Schema & Parser Foundation

## Summary

Define the canonical 6-field relationship vocabulary in `config-schema.json` and update `IssueInfo` / `IssueParser` to parse all new fields and handle deprecated aliases. This is the foundational child of ENH-1391 and must complete before ENH-1431 and ENH-1432 begin.

## Current Behavior

`IssueInfo` has `blocked_by` and `blocks` fields but lacks `parent`, `depends_on`, `relates_to`, and `duplicate_of`. `config-schema.json` does not define these relationship fields. The parser silently ignores `parent_issue:` and `related:` frontmatter keys rather than mapping them to canonical fields.

## Expected Behavior

`IssueInfo` exposes `parent`, `depends_on`, `relates_to`, and `duplicate_of` with correct types and defaults. `config-schema.json` validates all five new fields. The parser populates them from frontmatter and emits deprecation warnings when the legacy `parent_issue:` or `related:` aliases are encountered.

## Impact

- **Priority**: P2 — Blocks ENH-1431, ENH-1432, and ENH-1433; foundational for all relationship-aware tooling
- **Effort**: Medium — Two files modified (`config-schema.json`, `issue_parser.py`), tests across three test modules
- **Risk**: Low — Purely additive; existing `blocked_by`/`blocks` logic is unchanged

## Labels

`enhancement`, `schema`, `parser`, `issue-management`

## Parent Issue

Decomposed from ENH-1391: Standardize Issue Relationship Fields

## Scope

Covers implementation steps 1 and 2 from the parent.

## Proposed Solution

### Step 1 — `config-schema.json` schema additions

Add 5 fields to the `issues.properties` block (skip `epic` — deferred to FEAT-1389):

| Field | JSON Schema type | Constraint |
|---|---|---|
| `parent` | `string` | single value |
| `blocked_by` | `array`, items: `string` | list |
| `depends_on` | `array`, items: `string` | list |
| `relates_to` | `array`, items: `string` | list |
| `duplicate_of` | `string` | single value |

Follow existing patterns:
- `worktree_copy_files` (lines ~839–913) — array-of-strings pattern
- `status` field (lines ~100–106) — enum-constrained single-value pattern

### Step 2 — `issue_parser.py`: `IssueInfo` dataclass + `IssueParser.parse_file()`

**`IssueInfo` additions:**
```python
parent: str | None = None
depends_on: list[str] = field(default_factory=list)
relates_to: list[str] = field(default_factory=list)
duplicate_of: str | None = None
```

**`parse_file()` changes:**
- Read `parent_issue` frontmatter key as deprecated alias → populate `parent` field (emit `logger.warning()` on use)
- Read `related` frontmatter key as deprecated alias → populate `relates_to` field (emit `logger.warning()` on use)
- Extend the existing frontmatter reconciliation loop (`for fm_key, body_ids in (("blocked_by", blocked_by), ("blocks", blocks)):`) to also handle `depends_on` and `relates_to` as list fields using the identical pattern
- Update `to_dict()` and `from_dict()` symmetrically for all new fields

## Files to Modify

- `config-schema.json` — relationship field definitions
- `scripts/little_loops/issue_parser.py` — `IssueInfo` + `IssueParser.parse_file()` + `to_dict()`/`from_dict()`

## Tests

- `scripts/tests/test_config_schema.py` — add structural assertions for new relationship fields (follow `test_commands_rate_limits_block` pattern)
- `scripts/tests/test_issue_parser.py` — add tests for `depends_on`, `relates_to`, `duplicate_of`, `parent` parsing; test deprecated alias handling (`parent_issue` → `parent`, `related` → `relates_to`); follow `caplog` warning pattern already used there
- `scripts/tests/test_issue_parser_properties.py` — extend Hypothesis `make_issue()` strategies to cover new fields (`depends_on`, `relates_to`, `duplicate_of`, `parent`)

## Acceptance Criteria

- `IssueInfo` has `parent`, `depends_on`, `relates_to`, `duplicate_of` fields with correct defaults
- `IssueParser.parse_file()` populates all new fields from frontmatter
- `parent_issue:` frontmatter key is read as alias for `parent` with a deprecation warning
- `related:` frontmatter key is read as alias for `relates_to` with a deprecation warning
- `config-schema.json` validates all 5 new fields with correct types and constraints
- All new tests pass

## Scope Boundaries

- **In scope**: `config-schema.json` changes, `issue_parser.py` `IssueInfo` + parser updates, alias handling
- **Out of scope**: Migration script (ENH-1431), dependency graph logic (ENH-1432), docs/skills (ENH-1433)
- **Deferred**: `epic:` field implementation (FEAT-1389)

## Integration Map

### Files to Modify
- `config-schema.json` — add 5 fields inside `issues.properties` block (lines 63–201, before `additionalProperties: false` at line 201)
- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass (~line 210), `IssueParser.parse_file()` reconciliation loop (lines 464–485), `to_dict()` (lines 275–304), `from_dict()` (lines 306–336)

### Dependent Files (Callers — informational, out of scope)
These consume `IssueInfo` fields and will benefit from new fields being populated once this lands:
- `scripts/little_loops/dependency_graph.py` — uses `blocked_by`/`blocks`; will pick up `depends_on`/`relates_to` in ENH-1432
- `scripts/little_loops/dependency_mapper/analysis.py`, `models.py`, `operations.py`, `formatting.py`
- `scripts/little_loops/cli/deps.py` — `ll-deps` cross-issue dependency analysis
- `scripts/little_loops/cli/issues/sequence.py`, `clusters.py`, `next_issue.py` — use relationship fields for ordering
- `scripts/little_loops/issue_lifecycle.py` — note: uses `"parent_issue_id"` as an event *payload* key (line 499), not a frontmatter key; distinct from the `parent_issue:` alias being deprecated

### Similar Patterns to Follow
- `issue_parser.py:464–485` — frontmatter reconciliation loop for `blocked_by`/`blocks` (extend tuple for `depends_on`/`relates_to`)
- `config-schema.json:314–321` — `worktree_copy_files` array-of-strings pattern (use for `blocked_by`, `depends_on`, `relates_to`)
- `config-schema.json:100–105` — `status` single-value string pattern (use for `parent`, `duplicate_of`)
- `test_issue_parser.py:1452–1489` — `to_dict/from_dict` roundtrip test pattern for `blocked_by`/`blocks`
- `test_issue_parser.py:811` — `caplog.at_level(logging.WARNING, logger="little_loops.issue_parser")` deprecation-warning assertion pattern
- `test_config_schema.py:79` — `test_commands_rate_limits_block` structural schema assertion pattern (drill `data["properties"]["issues"]["properties"]`)
- `test_issue_parser_properties.py:73` — `@given` with `st.lists(st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5)` for list fields; `st.one_of(st.none(), st.from_regex(...))` for optional scalars

### Tests
- `scripts/tests/test_config_schema.py` — `TestConfigSchema` (add schema field assertions)
- `scripts/tests/test_issue_parser.py` — `TestDependencyParsing` (line 1249) — add field parsing + alias + roundtrip tests
- `scripts/tests/test_issue_parser_properties.py` — `TestIssueInfoProperties.test_roundtrip_serialization` (line 73) — extend `@given` strategies

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_fuzz.py` — `TestIssueParserFuzz.test_dependency_parsing_handles_lists` — extend fuzz coverage to `depends_on` and `relates_to` body-section parsing (follow existing pattern for `blocked_by`/`blocks`) [Agent 3 finding]
- `scripts/tests/test_loops_recursive_refine.py` — **awareness only, no code change required**: `build_parent_map()` greps for literal `parent_issue:` string (safe — existing fixture files use `parent_issue:` intentionally to test the deprecated alias path); those fixtures will emit the new deprecation warning on every parse run — confirm the warning does not interfere with assertions in that test module [Agent 2 finding]

### Documentation (update in ENH-1433, not here)
- `docs/reference/API.md` — documents `IssueInfo` dataclass fields
- `docs/reference/ISSUE_TEMPLATE.md` — documents frontmatter structure; the `parent_issue` row and Epic checklist at line 522 use the old field name; needs update to show `parent` as canonical and `parent_issue` as deprecated alias

_Wiring pass added by `/ll:wire-issue`:_
- `skills/issue-size-review/SKILL.md` — Phase 4 and Phase 6 frontmatter templates instruct writing `parent_issue:` (will generate deprecated alias after this lands; update in ENH-1433) [Agent 2 finding]
- `skills/confidence-check/SKILL.md` — line 235 references `parent_issue: EPIC-NNN` (same; ENH-1433 scope) [Agent 2 finding]

## Implementation Steps

1. **`config-schema.json`** — Open `issues.properties` (lines 66–200). Add `parent` and `duplicate_of` as `{"type": "string"}` following the `status` field pattern (lines 100–105). Add `blocked_by`, `depends_on`, `relates_to` as `{"type": "array", "items": {"type": "string"}}` following `worktree_copy_files` (lines 314–321). All 5 must appear before `"additionalProperties": false` at line 201.

2. **`IssueInfo` dataclass** (`issue_parser.py:210`) — Add after `blocks` / `epic`:
   ```python
   parent: str | None = None
   depends_on: list[str] = field(default_factory=list)
   relates_to: list[str] = field(default_factory=list)
   duplicate_of: str | None = None
   ```

3. **`parse_file()` — scalar reads** (`issue_parser.py:380–454`) — Add alongside existing scalar frontmatter reads:
   ```python
   parent = frontmatter.get("parent")
   duplicate_of = frontmatter.get("duplicate_of")
   # deprecated aliases
   if parent is None and (v := frontmatter.get("parent_issue")):
       logger.warning("%s: deprecated frontmatter key 'parent_issue' — rename to 'parent'", issue_path.name)
       parent = v
   ```
   Apply the same alias pattern for `related` → `relates_to` (initialize `relates_to: list[str] = []` before the alias read, then populate if alias found).

4. **`parse_file()` — reconciliation loop** (`issue_parser.py:464`) — Initialize `depends_on: list[str] = []` before the loop. Extend the loop tuple:
   ```python
   for fm_key, body_ids in (
       ("blocked_by", blocked_by),
       ("blocks", blocks),
       ("depends_on", depends_on),
       ("relates_to", relates_to),
   ):
   ```
   The `relates_to` list initialized in step 3 (populated from the `related` alias if present) will be further reconciled here against any frontmatter `relates_to:` key.

5. **`to_dict()`** (`issue_parser.py:275`) — Add after `"blocks": self.blocks`:
   ```python
   "parent": self.parent,
   "depends_on": self.depends_on,
   "relates_to": self.relates_to,
   "duplicate_of": self.duplicate_of,
   ```

6. **`from_dict()`** (`issue_parser.py:306`) — Add after `blocks=data.get("blocks", [])`:
   ```python
   parent=data.get("parent"),
   depends_on=data.get("depends_on", []),
   relates_to=data.get("relates_to", []),
   duplicate_of=data.get("duplicate_of"),
   ```

7. **`test_config_schema.py`** — Add test drilling `data["properties"]["issues"]["properties"]` to assert presence and type of all 5 new fields (follow `test_commands_rate_limits_block` at line 79).

8. **`test_issue_parser.py`** — Add to `TestDependencyParsing` (line 1249): inline frontmatter string tests for each new field; `caplog` warning tests for `parent_issue` and `related` aliases; `to_dict/from_dict` roundtrip tests (follow lines 1452–1489).

9. **`test_issue_parser_properties.py`** — Extend `@given` in `test_roundtrip_serialization` (line 73): add `depends_on` and `relates_to` as `st.lists(st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5)`; add `parent` and `duplicate_of` as `st.one_of(st.none(), st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True))`.

10. **`test_issue_parser_fuzz.py`** (`TestIssueParserFuzz.test_dependency_parsing_handles_lists`) — extend fuzz coverage to include `depends_on` and `relates_to` body-section parsing following the `blocked_by`/`blocks` pattern already in the test.

11. **Verify** — `python -m pytest scripts/tests/test_config_schema.py scripts/tests/test_issue_parser.py scripts/tests/test_issue_parser_properties.py scripts/tests/test_issue_parser_fuzz.py -v` — also run `test_loops_recursive_refine.py` and confirm the new deprecation warning logs do not break any assertion in that module.

## Session Log
- `/ll:manage-issue` - 2026-05-10T23:02:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-10T22:56:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c66f0de9-0780-444d-9aac-80015c099696.jsonl`
- `/ll:wire-issue` - 2026-05-10T22:50:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e55238b5-aeb7-4357-85aa-85b11d5af80f.jsonl`
- `/ll:refine-issue` - 2026-05-10T22:43:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd4e407a-1507-4958-a2b9-82f714371500.jsonl`
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
- `/ll:confidence-check` - 2026-05-10T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68cccc04-0d5f-414d-bb6a-13e6957466b6.jsonl`
