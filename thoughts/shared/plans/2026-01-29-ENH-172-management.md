# ENH-172: Add Mutation Testing with mutmut - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-172-add-mutation-testing-with-mutmut.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The project has a mature test infrastructure:
- **1,868 tests** with good line coverage
- pytest configuration in `pyproject.toml:86-101`
- Coverage configuration in `pyproject.toml:103-119` with 80% threshold
- Dev dependencies in `pyproject.toml:56-63`
- Hypothesis property-based testing already integrated

### Key Discoveries
- Dependencies pattern: `pyproject.toml:56-63` uses `>=` version constraints
- Test markers pattern: `pyproject.toml:98-101` defines `slow` marker for deselection
- Coverage pattern: `pyproject.toml:103-119` uses `[tool.coverage.*]` sections
- Documentation pattern: `CONTRIBUTING.md:40-73` shows test commands with marker filtering
- No CI workflows exist (local-only testing)

## Desired End State

Mutation testing integrated to verify test assertion quality:
- mutmut installed as dev dependency
- Configuration file created for mutation testing
- Documentation added to CONTRIBUTING.md
- Baseline mutation score established

### How to Verify
- `mutmut run` executes without errors
- `mutmut results` shows mutation score
- Tests, lint, and type checks pass

## What We're NOT Doing

- Not adding CI integration (no CI infrastructure exists)
- Not fixing surviving mutants in this issue (would require separate issues per module)
- Not achieving >80% mutation score initially (baseline only)
- Not adding mutation tests to default test runs (too slow)

## Problem Analysis

Line coverage measures code execution, not assertion quality. The example from the issue:

```python
# Both tests have 100% coverage but only the second is useful
def test_bad_example():  # Passes even if function is broken
    result = calculate_sum(1, 2)
    assert result is not None  # USELESS - always passes

def test_good_example():  # Fails if function is broken
    result = calculate_sum(1, 2)
    assert result == 3  # USEFUL - verifies actual behavior
```

Mutation testing introduces artificial bugs to verify tests actually detect them.

## Solution Approach

Follow established patterns from ENH-169 (hypothesis integration):
1. Add dependency to `[project.optional-dependencies]` dev group
2. Create tool configuration file
3. Document in CONTRIBUTING.md with examples
4. Run baseline to verify setup works

## Implementation Phases

### Phase 1: Add mutmut Dependency

#### Overview
Add mutmut to dev dependencies following established pattern.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: Add `mutmut>=3.0` to dev dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",
    "mutmut>=3.0",  # Add this line
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Install succeeds: `pip install -e "./scripts[dev]"`
- [ ] mutmut available: `mutmut --version`
- [ ] Lint passes: `ruff check scripts/little_loops/`
- [ ] Types pass: `mypy scripts/little_loops/`

---

### Phase 2: Create mutmut Configuration

#### Overview
Create `.mutmut.toml` configuration file in scripts directory.

#### Changes Required

**File**: `scripts/.mutmut.toml` (new file)
**Changes**: Create configuration file

```toml
[mutmut]
paths_to_mutate = "little_loops/"
tests_dir = "tests/"
runner = "python -m pytest -x -q"
dict_synonyms = "Struct, NamedStruct"
```

Configuration notes:
- `paths_to_mutate`: Only mutate source code, not tests
- `tests_dir`: Where tests are located
- `runner`: Use pytest with `-x` (fail fast) and `-q` (quiet) for speed
- No exclusions initially - can be refined based on baseline results

#### Success Criteria

**Automated Verification**:
- [ ] Configuration file exists: `test -f scripts/.mutmut.toml`
- [ ] Lint passes: `ruff check scripts/little_loops/`

---

### Phase 3: Run Initial Baseline

#### Overview
Execute mutation testing to establish baseline score.

#### Changes Required

Run mutation testing from scripts directory:

```bash
cd scripts
mutmut run --paths-to-mutate little_loops/config.py
```

Note: Start with a single small module to verify setup works, then document
the process for running full mutation tests.

#### Success Criteria

**Automated Verification**:
- [ ] mutmut run completes without error on single module
- [ ] mutmut results shows mutation score

**Manual Verification**:
- [ ] Review mutation score output
- [ ] Document any configuration adjustments needed

---

### Phase 4: Document in CONTRIBUTING.md

#### Overview
Add mutation testing documentation to CONTRIBUTING.md.

#### Changes Required

**File**: `CONTRIBUTING.md`
**Changes**: Add mutation testing section after "Running Tests" section (around line 60)

```markdown
### Mutation Testing

Mutation testing verifies test assertion quality by introducing artificial bugs:

```bash
# Run mutation testing on a specific module (faster)
cd scripts
mutmut run --paths-to-mutate little_loops/config.py

# Run mutation testing on all modules (slow - hours)
cd scripts
mutmut run

# View results
mutmut results

# Show specific surviving mutant
mutmut show 42
```

Mutation testing is slow and not included in regular test runs. Use it to:
- Identify tests with weak assertions
- Verify critical code has quality tests
- Find untested code paths

A surviving mutant means the mutation (artificial bug) wasn't detected by tests.
Fix by improving test assertions to catch the specific mutation.
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/`
- [ ] Tests pass: `pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
No new unit tests required - mutmut is a tool for verifying existing tests.

### Integration Tests
- Verify mutmut runs against actual source code
- Verify results can be displayed

## References

- Issue: `.issues/enhancements/P3-ENH-172-add-mutation-testing-with-mutmut.md`
- Similar implementation: `.issues/completed/P3-ENH-169-property-based-tests-for-parsers.md`
- Dev dependencies: `scripts/pyproject.toml:56-66`
- Test documentation: `CONTRIBUTING.md:40-73`
