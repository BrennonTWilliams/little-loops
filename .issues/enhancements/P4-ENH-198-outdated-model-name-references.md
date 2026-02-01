# Outdated Model Name References in Documentation

## Type
ENH

## Priority
P4

## Status
OPEN

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
Documentation drift. As new Claude models are released, the hardcoded model name becomes stale. This is a maintenance burden and may confuse users.

## Files Affected
- `scripts/little_loops/fsm/schema.py`
- `docs/generalized-fsm-loop.md`

## Recommendation

**Option 1: Use generic model identifier (Recommended)**
Change to a more generic default like:
- `"claude-sonnet-4"` (without date)
- `"claude-sonnet-latest"` (if supported)
- Or use a config file setting

**Option 2: Document as "current default"**
Add a note in docs: "Default as of February 2025, subject to change"

**Option 3: Make configurable**
Allow project-level config override for default model.

## Related Issues
None
