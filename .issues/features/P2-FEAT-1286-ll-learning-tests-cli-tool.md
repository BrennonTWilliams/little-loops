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

## Files to Create/Modify

- `scripts/little_loops/cli/learning_tests.py` — **create** (new CLI handler)
- `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- `scripts/pyproject.toml` — add `ll-learning-tests` entry point
- `commands/help.md` — add CLI tool entry
- `docs/reference/CLI.md` — add reference section

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

## Dependencies

- FEAT-1285 (learning_tests module) must be complete first

---

**Open** | Created: 2026-04-25 | Priority: P2
