# Outdated Model Name References in Documentation

## Type
ENH

## Priority
P4

## Status
COMPLETED

## Description

The default LLM model is documented as `claude-sonnet-4-20250514` in multiple locations. This is a specific dated model identifier that may become outdated as newer models are released.

**Locations with this model name:**
- `scripts/little_loops/fsm/schema.py:299` - Default model in LLMConfig
- `docs/generalized-fsm-loop.md:414` - LLM evaluation settings
- `docs/generalized-fsm-loop.md:759` - Example implementation

**Evidence:**
- `schema.py:299`: `model: str = "claude-sonnet-4-20250514"`
- `generalized-fsm-loop.md:414`: `model: string` (default: claude-sonnet-4-20250514)

**Impact:**
Documentation and code maintenance burden. The hardcoded dated model identifier appears in **14+ files** across source code, documentation, tests, and schema definitions. As new Claude models are released, keeping these synchronized becomes error-prone.

**Scope Note:** While the original issue listed 3 locations, a comprehensive grep reveals the model name is hardcoded in many more places, making this a larger refactoring task than initially documented.

## Files Affected

### Primary Code Locations
- `scripts/little_loops/fsm/schema.py` - LLMConfig default value (line 299, 309, 323)
- `scripts/little_loops/fsm/evaluators.py` - llm_structured_evaluator default (line 391)
- `scripts/little_loops/fsm/fsm-loop-schema.json` - JSON schema default (line 260)

### Documentation
- `docs/generalized-fsm-loop.md` - Three locations (lines 414, 759, 1136)
- `docs/API.md` - Two locations (lines 2526, 2661)

### Tests (expected values, may need updates)
- `scripts/tests/test_fsm_schema.py:369`
- `scripts/tests/test_worker_pool.py:1282, 1290`
- `scripts/tests/test_ll_loop.py:3039`

### Other References
- `scripts/little_loops/parallel/worker_pool.py:523` - Comment only

### Completed Issues (archived references)
- `.issues/completed/P2-FEAT-044-tier2-llm-evaluator.md:87`
- `.issues/completed/P1-FEAT-040-fsm-schema-definition-and-validation.md:88`
- `thoughts/shared/plans/2026-01-13-FEAT-044-management.md:147`

## Recommendation

**Option 1: Define as module constant (Recommended)**
Create a single source of truth:
```python
# In scripts/little_loops/fsm/schema.py
DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"  # Update here to propagate everywhere
```
Then reference `DEFAULT_LLM_MODEL` everywhere instead of hardcoded strings. Tests can import this constant.

**Option 2: Use generic model identifier**
Change to a more stable default like:
- `"claude-sonnet-4"` (without specific date)
- Document that this maps to the latest Sonnet 4.x version

**Option 3: Make configurable via ll-config.json**
Add a `default_llm_model` setting to project config, falling back to a module constant.

**Option 4: Environment variable**
Support `LL_DEFAULT_MODEL` env var override for flexibility.

## Implementation Notes
- Test files (test_*.py) reference the model in assertions - these should be updated to use the constant
- The JSON schema (`fsm-loop-schema.json`) also contains the hardcoded default
- Consider whether updating the default requires a minor version bump

## Related Issues
None

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made

**Python Source Files:**
- `scripts/little_loops/fsm/schema.py` - Added `DEFAULT_LLM_MODEL` constant, updated LLMConfig to use it (lines 20, 299, 309, 323)
- `scripts/little_loops/fsm/evaluators.py` - Imported and used `DEFAULT_LLM_MODEL` in evaluate_llm_structured (lines 23, 391)
- `scripts/little_loops/fsm/__init__.py` - Exported `DEFAULT_LLM_MODEL` in `__all__` (lines 113, 136)

**Test Files:**
- `scripts/tests/test_fsm_schema.py` - Imported and used `DEFAULT_LLM_MODEL` in test assertion (lines 17, 369)
- `scripts/tests/test_worker_pool.py` - Imported and used `DEFAULT_LLM_MODEL` in test data and assertion (lines 30, 1282, 1290)

**JSON Schema:**
- `scripts/little_loops/fsm/fsm-loop-schema.json` - Updated description to reference constant (line 259)

**Documentation:**
- `docs/generalized-fsm-loop.md` - Updated comments and code examples to reference constant (lines 414, 759, 1136)
- `docs/API.md` - Updated API signatures to reference constant (lines 2526, 2661)

### Verification Results
- Tests: PASS (78/78 in test_fsm_schema.py, 5/5 in test_worker_pool.py model tests)
- Lint: Pre-existing issues only (none related to this change)
- Types: PASS (no mypy issues)
