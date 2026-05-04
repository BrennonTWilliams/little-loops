---
id: FEAT-1286
type: FEAT
priority: P2
captured_at: "2026-04-25T00:00:00Z"
discovered_date: "2026-04-25"
discovered_by: issue-size-review
parent_issue: FEAT-1282
size: Small
---

# FEAT-1286: ll-learning-tests CLI Tool

## Summary

Implement `ll-learning-tests` as a new CLI entry point that exposes the learning test registry to Bash-based callers (skills, loops, agents). Skills cannot call Python functions directly — they invoke CLI tools via `Bash`. Without this CLI surface, the `ll:explore-api` skill (FEAT-1287) and the FSM/lifecycle dependents (ENH-1283, ENH-1284) cannot query the registry.

## Parent Issue

Decomposed from FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Current Behavior

There is no `ll-learning-tests` CLI entry point. The `LearnTestRecord` registry is accessible only as a Python module (`little_loops.learning_tests`). Skills, loops, and agents invoke tooling via `Bash` and cannot import Python modules directly, leaving the registry unreachable from non-Python callers.

## Expected Behavior

The `ll-learning-tests` CLI is installed as an entry point and provides:

- `ll-learning-tests check <target>` — prints record JSON to stdout; exits 1 with an error message if the target is not found
- `ll-learning-tests list` — prints all records as a JSON array
- `ll-learning-tests mark-stale <target>` — marks a record stale; exits 1 if not found
- `ll-learning-tests --help` — shows all subcommands

Skills, loops, and FSM evaluators can call `ll-learning-tests check <target>` via `Bash` to gate behavior on learning test coverage.

## Use Case

**Who**: Skill or loop developer implementing `ll:explore-api` (FEAT-1287) or a lifecycle hook (ENH-1283/ENH-1284) that must verify learning test coverage before proceeding.

**Context**: A skill or FSM evaluator needs to query the learning test registry at runtime via a `Bash` tool call — it cannot import Python directly.

**Goal**: Call `ll-learning-tests check "Anthropic SDK streaming"` in `Bash` to confirm a test record exists, then branch on exit code or parse the JSON output.

**Outcome**: All non-Python callers (skills, loops, agents) can query the `LearnTestRecord` registry without knowing Python module internals.

## Proposed Solution

### CLI surface

```
ll-learning-tests check <target>      # print record JSON; exit 1 if not found
ll-learning-tests list                # list all records as JSON array
ll-learning-tests mark-stale <target> # mark a record stale
```

The `check` subcommand is the key one — it is the callable surface for other skills and loops.

### Implementation

- `scripts/little_loops/cli/learning_tests.py` — implement `main_learning_tests` following conventions in existing CLI modules (e.g., `cli/sync.py`)
- Import `check_learning_test`, `list_records`, `mark_stale` from `little_loops.learning_tests`
- Register in `scripts/pyproject.toml:48-67` as `ll-learning-tests = "little_loops.cli.learning_tests:main_learning_tests"`
- Update `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry (lines 23-65)

### Documentation touchpoints

- `commands/help.md` — add `ll-learning-tests` entry to hardcoded CLI tools list (lines 216-234)
- `docs/reference/CLI.md` — add `### ll-learning-tests` reference section documenting all subcommands

## API/Interface

```bash
# CLI entry point (installed via pyproject.toml)
ll-learning-tests check <target>      # Exit 0 + JSON record; exit 1 + error message if not found
ll-learning-tests list                # Exit 0 + JSON array of all records
ll-learning-tests mark-stale <target> # Exit 0 on success; exit 1 if not found
ll-learning-tests --help              # Show subcommand help
```

```python
# Python entry point in scripts/little_loops/cli/learning_tests.py
def main_learning_tests() -> None:
    """CLI handler for ll-learning-tests subcommands."""
```

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/learning_tests.py` — **create** (new CLI handler)
- `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- `scripts/pyproject.toml` — add `ll-learning-tests` entry point
- `commands/help.md` — add CLI tool entry
- `docs/reference/CLI.md` — add reference section

### Dependent Files (Callers/Importers)

- `skills/explore-api/SKILL.md` (FEAT-1287) — will call `ll-learning-tests check` via Bash
- FSM loop evaluators (ENH-1283, ENH-1284) — will gate on `ll-learning-tests check` exit code

### Similar Patterns

- `scripts/little_loops/cli/sync.py` — follow module structure and argparse conventions
- Other `scripts/little_loops/cli/*.py` modules for consistent patterns

### Tests

- `scripts/tests/test_cli_learning_tests.py` — new test file for all CLI subcommands
- Install verification: `pip install -e "./scripts[dev]" && ll-learning-tests --help`

### Documentation

- `commands/help.md` — hardcoded CLI tools list (add entry)
- `docs/reference/CLI.md` — add `### ll-learning-tests` reference section

### Configuration

- `scripts/pyproject.toml` — `[project.scripts]` entry point registration

## Implementation Steps

1. Implement `cli/learning_tests.py` with `check`, `list`, `mark-stale` subcommands
2. Register entry point in `pyproject.toml`
3. Update `cli/__init__.py` imports and `__all__`
4. Update `commands/help.md`
5. Update `docs/reference/CLI.md`
6. Verify: `pip install -e "./scripts[dev]" && ll-learning-tests --help`

## Acceptance Criteria

- `ll-learning-tests check "Anthropic SDK streaming"` prints record JSON or exits 1 with message if not found
- `ll-learning-tests list` prints all records as a JSON array
- `ll-learning-tests --help` shows all subcommands
- Entry point is registered and importable after `pip install -e`

## Impact

- **Priority**: P2 — Unblocks FEAT-1287 (`ll:explore-api` skill) and ENH-1283/ENH-1284 (FSM lifecycle hooks); the registry has no non-Python caller surface without this
- **Effort**: Small — New file (`cli/learning_tests.py`) following established patterns in `cli/sync.py`; thin wrapper only, no new logic required
- **Risk**: Low — Additive change; no modifications to existing code paths
- **Breaking Change**: No

## Dependencies

- FEAT-1285 (learning_tests module) must be complete first


## Blocks

- FEAT-1283

## Labels

`cli`, `new-feature`, `learning-tests`

---

**Open** | Created: 2026-04-25 | Priority: P2


## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `scripts/little_loops/cli/learning_tests.py` module ✓
- No `ll-learning-tests` entry point in `scripts/pyproject.toml` ✓
- No `check_learning_test`, `list_records`, `mark_stale` functions exist ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:format-issue` - 2026-04-25T20:15:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2dda3ac-5cb0-428a-8411-98d575600c2c.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): **CLI doc ownership split with FEAT-1287.** FEAT-1286 owns CLI-surface documentation: `commands/help.md` and `docs/reference/CLI.md`. FEAT-1287 owns narrative/architecture documentation: README skill table row, CONTRIBUTING skills tree, `.claude/CLAUDE.md`, and `docs/ARCHITECTURE.md`. Do not duplicate doc touchpoints across both issues — implement CLI docs here and leave narrative docs to FEAT-1287.
