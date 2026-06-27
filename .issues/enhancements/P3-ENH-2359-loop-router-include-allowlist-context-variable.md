---
id: ENH-2359
title: "Add include allowlist context variable to loop-router, loop-composer, and loop-composer-adaptive"
type: ENH
priority: P3
status: open
captured_at: "2026-06-27T23:08:42Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
labels: [loops, loop-router, loop-composer, routing, catalog-filtering]
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

- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state (inline)
- `scripts/little_loops/loops/loop-composer.yaml` — `discover_loops` state (delegates to fragment)
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — `discover_loops` state (delegates to fragment)
- `scripts/little_loops/loops/lib/composer.yaml` — shared `discover_loops` fragment (if used by composer loops)

## Implementation Steps

1. Check whether `loop-composer` and `loop-composer-adaptive` share the `discover_loops` fragment from `lib/composer.yaml` or each have their own inline state.
2. Add `include: ""` to the `context:` block of all three top-level loop files.
3. Add the `_matches_include` filter to `discover_loops` — in the shared fragment if shared, or in each loop file if inline.
4. Place the include-filter step *before* the exclude step so both can be composed.
5. Validate with `ll-loop validate` on all three loops.
6. Test with `ll-loop run loop-router --input "..." --context include=deep-research` and confirm catalog is restricted.

## Impact

- **Scope**: Three loop YAML files (plus possibly `lib/composer.yaml` fragment)
- **Backwards compatibility**: Empty default preserves all existing behavior; no callers need to change
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
- `/ll:capture-issue` - 2026-06-27T23:08:42Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f29bbf4-30b2-48c9-b5bb-d88fd36c8633.jsonl`

---

## Status

**Current status**: open
