---
id: ENH-1769
type: ENH
priority: P2
status: done
captured_at: "2026-05-28T21:10:40Z"
completed_at: "2026-05-30T06:50:00Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
labels: [enhancement, design-tokens, captured]
---

# ENH-1769: design-tokens: support W3C DTCG `$value` format in token resolver

## Summary

Teach the design-token loader to understand the W3C Design Tokens Community
Group (DTCG) format, where leaf values are wrapped in a `$value` key
(optionally alongside `$type`, `$description`, etc.). Today, projects using
DTCG-formatted `typography.json` / `semantic.json` etc. crash `ll-loop run`
with `ValueError: Unknown token reference '...'` because references like
`{typography.fontFamily.heading}` can't resolve to a flat key that ends in
`.$value`.

## Current Behavior

In `scripts/little_loops/design_tokens.py`:

- `_flatten` (line 44) blindly walks into every dict key, so a DTCG token
  `{ "fontFamily": { "heading": { "$value": "Inter" } } }` flattens to the key
  `fontFamily.heading.$value` rather than `fontFamily.heading`.
- `_resolve_value` (line 76) looks up references verbatim in `flat` /
  `primitives_flat`. A reference like `{typography.fontFamily.heading}` finds
  no key by that exact name (only `…heading.$value` exists) and raises at
  line 102.

Reproducer (real, from a sibling project today):

```
$ ll-loop run general-task "Update v2-index.html ..."
...
File "scripts/little_loops/design_tokens.py", line 102, in _resolve_value
ValueError: Unknown token reference 'typography.fontFamily.heading'
  in 'typography.heading.fontFamily.$value'
```

This makes `ll-loop run` totally unusable in any project that uses DTCG-format
tokens — including tokens exported from Figma Tokens / Tokens Studio, Style
Dictionary's preferred input, and most token libraries published since 2023.

## Expected Behavior

`load_design_tokens` accepts both layouts transparently:

1. **Legacy flat layout** (already supported):
   `{ "fontFamily": { "heading": "Inter" } }` → flat key `fontFamily.heading = "Inter"`.
2. **DTCG layout**: `{ "fontFamily": { "heading": { "$value": "Inter" } } }` →
   flat key `fontFamily.heading = "Inter"` (the `.$value` segment is collapsed
   away). `$type`, `$description`, and other DTCG metadata keys are ignored.
3. References resolve the same way in either layout — `{fontFamily.heading}`
   finds the leaf regardless of whether the source JSON used `$value`.

No change to existing projects' behavior; the DTCG handling is additive.

## Motivation

- **Blocks real usage today.** Any user pointing `design_tokens.path` at a
  DTCG-format token set (a very common export shape) hits a hard crash on
  every `ll-loop run`, with no obvious workaround besides hand-rewriting their
  tokens to the legacy flat shape.
- **DTCG is the emerging standard.** Figma Tokens / Tokens Studio, Style
  Dictionary v4+, and the W3C Design Tokens spec all use `$value`. Supporting
  it is table stakes for "drop your tokens in `.ll/design-tokens/` and go."
- **Tiny surface area.** The fix is ~10 lines in one module, with no
  migration, no config changes, and no breaking impact on legacy projects.

## Proposed Solution

Two narrow edits in `scripts/little_loops/design_tokens.py`:

1. **Flattener collapses `$value`.** In `_flatten`, when a dict has a `$value`
   key, treat the dict as a leaf and emit `{prefix: <$value>}` instead of
   recursing. Ignore sibling `$type` / `$description` / other `$`-prefixed
   metadata at the same level.

   ```python
   def _flatten(obj, prefix=""):
       result = {}
       if isinstance(obj, dict):
           if "$value" in obj:                       # DTCG leaf
               result[prefix] = obj["$value"]
               return result
           for key, value in obj.items():
               if key.startswith("$"):              # skip $type/$description/etc.
                   continue
               full_key = f"{prefix}.{key}" if prefix else key
               result.update(_flatten(value, full_key))
       else:
           result[prefix] = obj
       return result
   ```

2. **Resolver fallback for legacy DTCG inputs.** As a safety net (in case a
   user feeds tokens already containing dotted `.$value` keys, e.g. from a
   pre-flattened export), in `_resolve_value` if `ref_name` misses both
   `primitives_flat` and `flat`, retry the lookup with `ref_name + ".$value"`
   before raising `Unknown token reference`.

The flattener change alone fixes the reported crash. The resolver fallback is
belt-and-suspenders for resilience against partially-flattened inputs.

## Integration Map

### Files to Modify

- `scripts/little_loops/design_tokens.py` — `_flatten` (line 44) and
  `_resolve_value` (line 76).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/run.py` — calls `load_design_tokens` at
  line 182 (where the crash occurs).
- `scripts/little_loops/prompts/*` and any renderer using
  `render_as_prompt_context` / `render_as_css_vars` — unaffected, since they
  consume the already-resolved flat dict.

### Similar Patterns

- None — this is the only token reference resolver in the codebase.

### Tests

- `scripts/tests/test_design_tokens.py` (create or extend): add fixtures for
  both DTCG-format tokens (with `$value`) and mixed-format tokens, asserting
  that references resolve identically to the legacy format.
- Add a regression test for the exact failing reference pattern from the bug
  report: `typography.heading.fontFamily.$value = "{typography.fontFamily.heading}"`.

### Documentation

- `docs/reference/API.md` — note DTCG support in the `design_tokens` module
  section if it's documented there.
- Mention DTCG support in the ENH-1768 design-tokens docs (wherever
  multi-profile layout is described).

### Configuration

- N/A — no new config keys; behavior is auto-detected from JSON shape.

## Implementation Steps

1. Update `_flatten` to detect `$value` leaves and skip `$`-prefixed metadata
   siblings.
2. Update `_resolve_value` with a `.$value` fallback lookup.
3. Add tests covering: pure-legacy tokens (regression), pure-DTCG tokens,
   mixed tokens, DTCG with sibling `$type` / `$description`, and the exact
   crash reproducer.
4. Verify `ll-loop run general-task` works against a DTCG token set
   end-to-end.

## Impact

- **Priority**: P2 — Hard crash on `ll-loop run` for any project using
  industry-standard DTCG tokens; no workaround besides rewriting all tokens.
- **Effort**: Small — ~10 LOC change in one module, plus targeted tests.
- **Risk**: Low — purely additive; legacy flat layout continues to work
  unchanged because the `$value` branch only activates when a dict contains a
  `$value` key.
- **Breaking Change**: No.

## Scope Boundaries

- **Out of scope**: Full DTCG `$type` validation (color spaces, dimension
  units), aliasing via `{group.token}` syntax beyond what's already supported,
  multi-file `$schema` resolution, exporting tokens *back* to DTCG.
- **In scope**: Reading `$value`, ignoring `$`-prefixed metadata, resolving
  references through `$value` indirection.

## Success Metrics

- The reported reproducer (`ll-loop run general-task` against a DTCG
  `typography.json`) no longer crashes.
- Existing little-loops template profiles (`templates/design-tokens/profiles/*/`)
  continue to load identically — same `resolved` dict before and after.
- New test cases cover all four input shapes (pure legacy, pure DTCG, mixed,
  DTCG with metadata siblings).

## Related Key Documentation

| Document | Why it's relevant |
|----------|-------------------|
| `docs/reference/API.md` | Documents `little_loops.design_tokens` module API |
| `.claude/CLAUDE.md` | Project conventions for adding tests and type hints |

## Session Log

- `/ll:capture-issue` - 2026-05-28T21:10:40Z - `16b4effa-6777-470c-8a75-4136cb7cdc03.jsonl`

---

**Open** | Created: 2026-05-28 | Priority: P2
