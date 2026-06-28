---
id: ENH-2359
title: Add include allowlist context variable to loop-router, loop-composer, and loop-composer-adaptive
type: ENH
priority: P3
status: done
captured_at: '2026-06-27T23:08:42Z'
completed_at: '2026-06-28T03:31:29Z'
discovered_date: '2026-06-27'
discovered_by: capture-issue
labels:
- loops
- loop-router
- loop-composer
- routing
- catalog-filtering
confidence_score: 100
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 18
---

# ENH-2359: Add include allowlist context variable to loop-router, loop-composer, and loop-composer-adaptive

## Summary

Add an optional `include` context variable to the three routing/orchestration loops (`loop-router`, `loop-composer`, `loop-composer-adaptive`) that, when set, restricts the catalog fed to the LLM scorer to only the specified loops or categories. The variable defaults to empty (preserving current full-catalog behavior). Filtering supports three selector forms: built-in loop names, project loop names, and category labels.

## Current Behavior

All three loops call `ll-loop list --json --visibility public` and feed the complete catalog to the LLM scorer. The only filtering mechanism is the `exclude` context variable — a denylist that removes specific loop names. As the catalog grows the scorer prompt bloats, routing quality degrades due to noise, and there is no lightweight way to pin a router/composer to a curated subset without enumerating every loop to exclude.

## Expected Behavior

When `include` is non-empty, the `discover_loops` phase (or the equivalent catalog-building step) filters the catalog down to only the entries that match at least one selector in the `include` value before passing it to the LLM. When `include` is empty (default), behavior is identical to today.

## Motivation

Routing decision quality scales inversely with catalog size — more loops = noisier scoring. Projects that know their loop surface area benefit from a tight allowlist. The existing `exclude` denylist scales poorly (must enumerate everything to exclude as the catalog grows); an `include` allowlist inverts this: opt-in to the known-good set, ignore the rest. Category-level selectors avoid per-loop maintenance by grouping loops that share a purpose (e.g., `category:harness` to include only harness-optimizing loops).

## Proposed Solution

### Context variable

Add `include: ""` alongside `exclude: ""` in the `context:` block of all three loops:

```yaml
context:
  include: ""   # new: allowlist; empty = all public loops (current behavior)
  exclude: ""   # existing: denylist
```

### Selector syntax (comma-separated, mixed types allowed)

| Form | Example | Matches |
|------|---------|---------|
| bare loop name | `deep-research` | loops whose `name` field equals `deep-research` |
| `builtin:*` | `builtin:*` | all loops with `built_in: true` |
| `project:*` | `project:*` | all loops with `built_in: false` |
| `category:<label>` | `category:harness` | all loops whose `category` field equals `harness` |

### Filter logic in `discover_loops`

After parsing the catalog JSON, apply the allowlist before the existing `exclude` step:

```python
include_raw = '${context.include}'
includes = [s.strip() for s in include_raw.split(',') if s.strip()]

def _matches_include(loop):
    if not includes:
        return True  # empty = pass all
    name = loop.get('name', '')
    cat  = loop.get('category', '')
    is_builtin = loop.get('built_in', False)
    for sel in includes:
        if sel == 'builtin:*' and is_builtin:
            return True
        if sel == 'project:*' and not is_builtin:
            return True
        if sel.startswith('category:') and cat == sel[len('category:'):]:
            return True
        if sel == name:
            return True
    return False

loops = [l for l in loops if _matches_include(l)]
# existing exclude step follows unchanged
```

Apply this to the three `discover_loops` implementations:
- `scripts/little_loops/loops/loop-router.yaml` — inline `discover_loops` state
- `scripts/little_loops/loops/loop-composer.yaml` — delegates to `lib/composer.yaml` fragment `discover_loops`
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — same fragment

The fragment in `lib/composer.yaml` should receive the filter too, so the change need only be made once if the `discover_loops` fragment is shared; otherwise apply to all three independently.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state (inline); add `include:` to context block and filter logic
- `scripts/little_loops/loops/loop-composer.yaml` — `discover_loops` state (delegates to fragment); add `include:` to context block
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — `discover_loops` state (delegates to fragment); add `include:` to context block
- `scripts/little_loops/loops/lib/composer.yaml` — shared `discover_loops` fragment; add filter logic here if shared (one change covers both composer loops)
- `scripts/little_loops/loops/goal-cluster.yaml` — also uses `lib/composer.yaml:fragments.discover_loops`; adding `${context.include}` to the fragment without a default will crash interpolation for goal-cluster (`Path 'context.include' not found in context`); either add `include: ""` to goal-cluster's context block OR use `${context.include:default=}` (engine-native default) in the fragment's filter line so missing callers degrade to empty-include (pass-all) behavior [Second wiring pass]

### Dependent Files (Callers/Importers)
- Any loop or script that invokes `ll-loop run loop-router`, `loop-composer`, or `loop-composer-adaptive` with `--context` — callers gain the new optional `include` key

### Similar Patterns
- Existing `exclude` context variable in the same three loops — `include` should follow the same comma-split + `s.strip()` parse pattern for consistency

### Tests
- `scripts/tests/fixtures/` — add FSM fixture(s) for include-filter behavior (e.g., `loop-router-include-allowlist.yaml`)
- `ll-loop validate` on all three loops post-change (enforced in Implementation Steps)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No FSM fixtures are needed for context-variable assertions — all three test files load the loop YAML files directly via `yaml.safe_load()`.
- These existing test methods **must be updated** to add `include` alongside `exclude` (they enumerate exact keys; adding `include` to context without updating them will cause test failures):
  - `scripts/tests/test_loop_router.py:TestLoopRouterFile.test_context_variables` — add `assert "include" in ctx`
  - `scripts/tests/test_loop_router.py:TestLoopRouterFile.test_context_defaults` — add `assert ctx.get("include") == ""`
  - `scripts/tests/test_loop_composer.py:TestLoopComposerFile.test_context_variables` — add `"include"` to the checked-keys tuple
  - `scripts/tests/test_loop_composer.py:TestLoopComposerFile.test_context_defaults` — add `assert ctx.get("include") == ""`
  - `scripts/tests/test_loop_composer_adaptive.py:TestLoopComposerAdaptiveFile.test_context_variables` — add `"include"` to checked-keys
  - `scripts/tests/test_loop_composer_adaptive.py:TestLoopComposerAdaptiveFile.test_context_defaults` — add `assert ctx.get("include") == ""`
- New test method to add: `test_loop_router.py:TestLoopRouterStates.test_discover_loops_handles_include_allowlist` — assert include filter logic is present in `loop_data["states"]["discover_loops"]["action"]`
- New test method to add: `test_loop_composer.py:TestComposerLibFragment.test_discover_loops_fragment_handles_include_allowlist` — assert include filter logic is present in `lib_data["fragments"]["discover_loops"]["action"]`
- **Correction** (wiring pass): `TestLoopComposerAdaptiveFile.test_context_variables` and `test_context_defaults` listed above as "must be updated" do **not exist** yet in `test_loop_composer_adaptive.py` — both must be created as new test methods following the `TestLoopComposerFile` pattern (`for key in (...): assert key in ctx` and bare `assert ctx.get("include") == ""`). See `TestLoopComposerAdaptiveFile.test_context_has_max_replans` (line 93) for the fixture/access style.
- **Adaptive context key set** (second refine pass): `loop-composer-adaptive.yaml` has **five** context keys — `goal`, `auto`, `exclude`, `max_plan_nodes`, `max_replans` — vs. loop-composer's four (no `max_replans`). The new `test_context_variables` for adaptive must check all five plus `include`; `test_context_defaults` should assert `include == ""`, `auto == "false"`, `max_plan_nodes == "8"`, `max_replans == "2"`.
- **Hardcoded exclusion set confirmed** (second refine pass): both `loop-router.yaml:discover_loops` (lines 33-37) and `lib/composer.yaml:fragments.discover_loops` (lines 34-38) hard-exclude **five** loops: `loop-router`, `loop-composer`, `loop-composer-adaptive`, `goal-cluster`, `rn-build`. The `include` filter runs on `loops` before this exclusion step, so including e.g. `loop-router` by name in `include` will still be blocked by the hardcoded set — correct behavior, no special handling needed.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — documents `exclude` in three separate context-variable tables (loop-router ~line 60, loop-composer ~line 2412, loop-composer-adaptive ~line 2457); each needs a parallel `include` row explaining allowlist semantics and the four selector forms
- `docs/reference/loops.md` — documents `exclude` in two context-variable tables (loop-composer line 713, loop-composer-adaptive line 756); each needs a parallel `include` row. Note: `loop-router` has no dedicated section in this file.
- `skills/create-loop/loop-types.md` — two locations documenting `exclude` for routing/orchestration loops: (1) "Orch Router" section YAML context block (~line 1978) shows the customizable context block after `ll-loop install loop-router`; add `include: ""` entry with selector-syntax comment; (2) "Orch Composer" section key context knobs list (~line 2007) enumerates `exclude: "loop-a,loop-b"` as a bullet; add parallel `include` bullet. "Orch Supervisor" (adaptive) has only a paragraph description — no context knob enumeration, no update needed there. [Second wiring pass]

### Configuration
- N/A — no config file changes; callers pass `--context include=...` at invocation time

## Implementation Steps

1. Check whether `loop-composer` and `loop-composer-adaptive` share the `discover_loops` fragment from `lib/composer.yaml` or each have their own inline state.
2. Add `include: ""` to the `context:` block of all three top-level loop files.
3. Add the `_matches_include` filter to `discover_loops` — in the shared fragment if shared, or in each loop file if inline.
4. Place the include-filter step *before* the exclude step so both can be composed.
5. Validate with `ll-loop validate` on all three loops.
6. Test with `ll-loop run loop-router --input "..." --context include=deep-research` and confirm catalog is restricted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 is resolved**: Both `loop-composer.yaml` and `loop-composer-adaptive.yaml` delegate `discover_loops` via `fragment: discover_loops` stub (no inline Python). The canonical implementation lives in `scripts/little_loops/loops/lib/composer.yaml:fragments.discover_loops`. Exactly **two** action strings need the include-filter logic: (1) `loop-router.yaml` inline `discover_loops` action; (2) `lib/composer.yaml:fragments.discover_loops` action.
- **`built_in` key subtlety**: `ll-loop list --json` output includes `"built_in": true` only for built-in loops; project loops omit the key entirely. `loop.get('built_in', False)` in the pseudocode handles this correctly.
- **`category` field confirmed**: Each loop entry in `ll-loop list --json` includes `"category": "..."`. Category filtering uses exact string equality, matching the proposed `category:<label>` selector form.
- **Step 6 must include test updates**: `test_context_variables` and `test_context_defaults` in all three test files explicitly enumerate expected context keys. Adding `include:` to the context block without updating these tests will cause test failures (see Tests research findings above).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Create `test_loop_composer_adaptive.py:TestLoopComposerAdaptiveFile.test_context_variables` and `test_context_defaults` as **new** test methods (they do not yet exist) — follow `TestLoopComposerFile` pattern; use `ctx = loop_data.get("context", {})` preamble
8. Update `docs/guides/LOOPS_REFERENCE.md` — add `include` row to the three `exclude`-containing context tables (~line 60 for loop-router, ~line 2412 for loop-composer, ~line 2457 for loop-composer-adaptive) with selector forms documented
9. Update `docs/reference/loops.md` — add `include` row to the two `exclude`-containing context tables (line 713 for loop-composer, line 756 for loop-composer-adaptive)
10. Resolve `goal-cluster.yaml` interpolation hazard — choose one: (a) add `include: ""` to `goal-cluster.yaml` context block so the fragment's `${context.include}` resolves correctly, or (b) write the fragment filter line as `include_raw = '${context.include:default=}'` (engine-native default) so all loops using the fragment are safe even without declaring `include`. Option (b) is preferred — no callers need updating. [Second wiring pass]
11. Update `skills/create-loop/loop-types.md` — (a) "Orch Router" section YAML context block (~line 1978): add `include: ""  # allowlist; comma-separated loop names / builtin:* / project:* / category:<label>`; (b) "Orch Composer" section knobs list (~line 2007): add `\`include: "category:harness"\` — allowlist; only loops matching selector(s) are offered as candidates`. [Second wiring pass]

## Impact

- **Priority**: P3 — useful quality-of-life improvement; `exclude` denylist is a functional workaround for small catalogs
- **Effort**: Small — YAML context block additions + one filter function in shell actions across 3–4 files; no Python package changes
- **Risk**: Low — empty default preserves current behavior; no callers need to change
- **Breaking Change**: No
- **Scope**: Three loop YAML files (plus possibly `lib/composer.yaml` fragment)
- **Token savings**: Projects using allowlists will see measurably smaller scorer prompts and potentially better routing precision

## Current Pain Point

The `exclude` denylist is the only filtering mechanism, but it requires enumerating every unwanted loop. A catalog with 30 loops and 5 relevant ones requires 25 `exclude` entries vs. 5 `include` entries — the allowlist is always at least as efficient, often far more so.

## Success Metrics

- `ll-loop validate` passes on all three loops with no new violations
- Running with `include=category:harness` produces a catalog containing only harness-category loops
- Running with `include=` (empty) produces the same catalog as today

## Scope Boundaries

- Does not change the LLM scoring prompts beyond the catalog size reduction
- Does not add UI for allowlist configuration (caller sets `--context include=...`)
- Does not affect `ll-loop list` output — only the in-flight catalog fed to the scorer

## Backwards Compatibility

Fully backwards compatible. `include` defaults to empty string, which passes all loops through (identical to current behavior). No existing invocations or callers need to change.

## API/Interface

```yaml
# loop-router context block (same shape for loop-composer / loop-composer-adaptive)
context:
  include: ""        # allowlist: loop names, builtin:*, project:*, category:<label>; empty = all
  exclude: ""        # denylist: comma-separated loop names to exclude (existing)
  auto: "true"
  confidence_threshold: "0.7"
```

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/loop-router.yaml` | Primary implementation target |
| `scripts/little_loops/loops/loop-composer.yaml` | Secondary implementation target |
| `scripts/little_loops/loops/loop-composer-adaptive.yaml` | Secondary implementation target |

## Labels

loops, loop-router, loop-composer, routing, catalog-filtering

## Session Log
- `/ll:ready-issue` - 2026-06-28T03:23:57 - `42c3d343-6292-4ebc-b9a2-8c4572c3562c.jsonl`
- `/ll:confidence-check` - 2026-06-28T05:00:00Z - `30e32b40-781b-41e9-aeb1-ff1283baedee.jsonl`
- `/ll:wire-issue` - 2026-06-28T01:34:37 - `fce0028a-6c8d-4538-aab4-731aad444c57.jsonl`
- `/ll:refine-issue` - 2026-06-28T01:21:19 - `07679074-e054-43f8-91f8-1793865abf75.jsonl`
- `/ll:ready-issue` - 2026-06-28T00:05:20 - `d1ce8ed7-3dd3-4d48-8407-ee501fc4d874.jsonl`
- `/ll:confidence-check` - 2026-06-27T23:59:00Z - `fa16026d-9fe1-4642-94f7-2714dd98d646.jsonl`
- `/ll:confidence-check` - 2026-06-27T23:45:00Z - `92927046-28e2-424e-a38e-73a6afefae1d.jsonl`
- `/ll:wire-issue` - 2026-06-27T23:29:19 - `5fab2d4e-d48f-455c-91b2-e98e0d2f5823.jsonl`
- `/ll:refine-issue` - 2026-06-27T23:21:09 - `3f3810d5-793e-415c-b668-e374d9339c63.jsonl`
- `/ll:format-issue` - 2026-06-27T23:12:54 - `9dd0d52d-9b17-430d-aa90-b29c1718d134.jsonl`
- `/ll:capture-issue` - 2026-06-27T23:08:42Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f29bbf4-30b2-48c9-b5bb-d88fd36c8633.jsonl`

---

## Resolution

- Added `include: ""` context variable to `loop-router.yaml`, `loop-composer.yaml`, and `loop-composer-adaptive.yaml`
- Added `_matches_include` filter (supporting `builtin:*`, `project:*`, `category:<label>`, and bare loop name selectors) to `loop-router.yaml`'s inline `discover_loops` and `lib/composer.yaml`'s shared `discover_loops` fragment
- Fragment uses `${context.include:default=}` engine-native default so `goal-cluster.yaml` callers work without declaring `include`
- Updated 6 test assertions and added 5 new test methods across the three test files
- Updated documentation in `LOOPS_REFERENCE.md`, `loops.md`, and `loop-types.md`
- All 128 tests pass; `ll-loop validate` clean on all three loops

## Status

**Current status**: done
