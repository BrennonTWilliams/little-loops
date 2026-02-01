# ENH-198: Outdated Model Name References - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-198-outdated-model-name-references.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The default LLM model name `"claude-sonnet-4-20250514"` is hardcoded in 14+ locations across the codebase. The research revealed a **critical architectural issue**: there are two independent defaults that are not synchronized:

1. **LLMConfig default** (schema.py:299) - Used by FSM instances and default evaluation path
2. **evaluate_llm_structured default** (evaluators.py:391) - Used by explicit llm_structured evaluators

This means explicit `llm_structured` evaluators bypass the FSM's LLMConfig and cannot be overridden via CLI or configuration.

### Key Discoveries
- `scripts/little_loops/fsm/schema.py:299` - LLMConfig dataclass default (PRIMARY)
- `scripts/little_loops/fsm/schema.py:309` - to_dict() comparison against hardcoded string
- `scripts/little_loops/fsm/schema.py:323` - from_dict() fallback string
- `scripts/little_loops/fsm/evaluators.py:391` - evaluate_llm_structured() parameter default (SECONDARY)
- `scripts/little_loops/fsm/fsm-loop-schema.json:260` - JSON schema default (manually maintained)
- Pattern established: Codebase already uses `DEFAULT_LLM_SCHEMA`, `DEFAULT_LLM_PROMPT`, `REQUIRED_CATEGORIES` as module-level constants

### Files Requiring Changes

**Python Source (4 locations, 2 files):**
1. `scripts/little_loops/fsm/schema.py` - 3 occurrences
2. `scripts/little_loops/fsm/evaluators.py` - 1 occurrence

**JSON Schema (1 location):**
3. `scripts/little_loops/fsm/fsm-loop-schema.json` - 1 occurrence

**Tests (4 locations in 3 files):**
4. `scripts/tests/test_fsm_schema.py` - 1 assertion
5. `scripts/tests/test_ll_loop.py` - 1 YAML fixture
6. `scripts/tests/test_worker_pool.py` - 2 occurrences (data + assertion)

**Documentation (5 occurrences in 2 files):**
7. `docs/generalized-fsm-loop.md` - 3 occurrences
8. `docs/API.md` - 2 occurrences

## Desired End State

A single source-of-truth constant `DEFAULT_LLM_MODEL` defined in `schema.py`, exported via the package `__init__.py`, and referenced everywhere the model default appears. Tests import and use the constant instead of hardcoded strings.

### How to Verify
- All Python code references `DEFAULT_LLM_MODEL` constant
- Tests import and assert against `DEFAULT_LLM_MODEL`
- Documentation reflects the constant pattern
- Running `pytest scripts/tests/ -v` passes
- Running `ruff check scripts/` passes
- Running `ruff format scripts/` passes
- Running `mypy scripts/little_loops/` passes

## What We're NOT Doing

- **NOT creating a schema generation script** - The JSON schema is manually maintained; adding auto-generation is out of scope for this enhancement
- **NOT adding environment variable override** - Option 4 from the issue is not being implemented (would be a separate feature)
- **NOT adding ll-config.json setting** - Option 3 from the issue is not being implemented (would be a separate feature)
- **NOT changing to generic model identifier** - Staying with dated identifier for now (Option 2 would be a separate decision)
- **NOT updating archived/completed issues** - Historical references in completed issues and plans are left as-is

## Problem Analysis

Root cause: The model default is hardcoded as a string literal in multiple locations. When the model needs updating, all 14+ locations must be found and manually updated, which is error-prone. Additionally, the dual-default architecture means explicit evaluators cannot have their model overridden.

## Solution Approach

Following established codebase patterns (DEFAULT_LLM_SCHEMA, DEFAULT_CATEGORIES), define `DEFAULT_LLM_MODEL` as a module-level constant in `schema.py`, export it via `__init__.py`, and update all references to use the constant.

## Implementation Phases

### Phase 1: Define Constant and Export

#### Overview
Create the `DEFAULT_LLM_MODEL` constant and make it available for import across the package.

#### Changes Required

**File**: `scripts/little_loops/fsm/schema.py`
**Changes**: Add constant at module level (after imports, before dataclasses)

```python
# After line ~30 (after imports, before LLMConfig class)
# Default LLM model for structured evaluation
DEFAULT_LLM_MODEL: str = "claude-sonnet-4-20250514"
```

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Import and export the constant

```python
# Add to imports
from little_loops.fsm.schema import (
    FSMLoop,
    LLMConfig,
    DEFAULT_LLM_MODEL,  # Add this
    # ... existing imports
)

# Add to __all__ (around line 40)
__all__ = [
    "DEFAULT_LLM_MODEL",  # Add this
    "FSMLoop",
    "LLMConfig",
    # ... existing exports
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `from little_loops.fsm import DEFAULT_LLM_MODEL` works in Python REPL

---

### Phase 2: Update Python Code to Use Constant

#### Overview
Replace hardcoded strings in Python source files with references to `DEFAULT_LLM_MODEL`.

#### Changes Required

**File**: `scripts/little_loops/fsm/schema.py`

```python
# In LLMConfig dataclass (line ~299)
@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = DEFAULT_LLM_MODEL  # Changed from hardcoded string
    max_tokens: int = 256
    timeout: int = 30

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not self.enabled:
            result["enabled"] = self.enabled
        if self.model != DEFAULT_LLM_MODEL:  # Changed from hardcoded string
            result["model"] = self.model
        # ... rest of method

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMConfig:
        return cls(
            enabled=data.get("enabled", True),
            model=data.get("model", DEFAULT_LLM_MODEL),  # Changed from hardcoded string
            max_tokens=data.get("max_tokens", 256),
            timeout=data.get("timeout", 30),
        )
```

**File**: `scripts/little_loops/fsm/evaluators.py`

```python
# At top of file, add import (around line 20)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL

# In function signature (line ~391)
def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,  # Changed from hardcoded string
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult:
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Verify no hardcoded strings remain: `grep -r "claude-sonnet-4-20250514" scripts/little_loops/` returns no results

**Manual Verification**:
- [ ] Create a minimal FSM loop config and run it to verify evaluator still works

---

### Phase 3: Update Tests to Use Constant

#### Overview
Replace hardcoded strings in test assertions and fixtures with references to `DEFAULT_LLM_MODEL`.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`

```python
# Add import (around line 10)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL

# In TestLLMConfig.test_defaults (line ~369)
def test_defaults(self) -> None:
    """Default LLM configuration."""
    config = LLMConfig()

    assert config.enabled is True
    assert config.model == DEFAULT_LLM_MODEL  # Changed from hardcoded string
    assert config.max_tokens == 256
    assert config.timeout == 30
```

**File**: `scripts/tests/test_ll_loop.py`

```python
# Add import (around line 10)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL

# In YAML test fixture (line ~3039)
# Change from:
# model: "claude-sonnet-4-20250514"
# To:
model: ${DEFAULT_LLM_MODEL}  # Note: Using interpolation for YAML
# OR keep the explicit value if it's testing a specific model override
```

**File**: `scripts/tests/test_worker_pool.py`

```python
# Add import (around line 10)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL

# In test data (line ~1282)
# Change mock data to use constant
modelUsage = {DEFAULT_LLM_MODEL: {"input": 10}}

# In assertion (line ~1290)
assert model == DEFAULT_LLM_MODEL
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Verify grep finds no hardcoded model strings in tests: `grep -r "claude-sonnet-4-20250514" scripts/tests/`

---

### Phase 4: Update JSON Schema

#### Overview
Update the manually maintained JSON schema to reflect the new constant (as a comment since JSON can't reference Python constants).

#### Changes Required

**File**: `scripts/little_loops/fsm/fsm-loop-schema.json`

```json
// Around line 260, update the model property
"model": {
  "type": "string",
  "description": "Model identifier for LLM calls (default: DEFAULT_LLM_MODEL in schema.py, currently claude-sonnet-4-20250514)",
  "default": "claude-sonnet-4-20250514"
}
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON is valid: `python -c "import json; json.load(open('scripts/little_loops/fsm/fsm-loop-schema.json'))"`

**Manual Verification**:
- [ ] Description field mentions the constant source

---

### Phase 5: Update Documentation

#### Overview
Update code examples and API documentation to reference the constant.

#### Changes Required

**File**: `docs/generalized-fsm-loop.md`

```markdown
# Line ~414 - Update comment
# Model for LLM evaluation (default: DEFAULT_LLM_MODEL from schema.py)

# Line ~759 - Update code example
model: str = DEFAULT_LLM_MODEL  # Default model from schema.py

# Line ~1136 - Update YAML example
llm:
  model: ${DEFAULT_LLM_MODEL}  # Uses default from schema.py
```

**File**: `docs/API.md`

```markdown
# Lines ~2526, ~2661 - Update API signatures
model: str = DEFAULT_LLM_MODEL  # Default model from schema.py
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation builds (if applicable)

**Manual Verification**:
- [ ] Read through documentation sections to verify clarity
- [ ] Verify examples show the constant pattern

---

## Testing Strategy

### Unit Tests
- Test that `DEFAULT_LLM_MODEL` constant is accessible via package import
- Test that `LLMConfig()` creates instances with `model == DEFAULT_LLM_MODEL`
- Test that `LLMConfig.from_dict({})` uses `DEFAULT_LLM_MODEL`
- Test that `evaluate_llm_structured()` uses `DEFAULT_LLM_MODEL` when no model specified

### Integration Tests
- Run full FSM loop with default configuration (should use `DEFAULT_LLM_MODEL`)
- Run FSM loop with `--llm-model` CLI override (should override default)
- Test serialization/deserialization roundtrip preserves model when it's the default

## References

- Original issue: `.issues/enhancements/P4-ENH-198-outdated-model-name-references.md`
- Pattern to follow: `scripts/little_loops/fsm/evaluators.py:57-84` (DEFAULT_LLM_SCHEMA pattern)
- Pattern to follow: `scripts/little_loops/config.py:33-42` (REQUIRED_CATEGORIES pattern)
- Similar implementation: `scripts/tests/test_fsm_evaluators.py:706-709` (constant import pattern)
