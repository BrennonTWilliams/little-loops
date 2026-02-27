# BUG-513: Section keyword matching produces false positives on common words

**Created**: 2026-02-26
**Issue**: `.issues/bugs/P3-BUG-513-section-keywords-produce-false-positives-on-common-words.md`
**Action**: fix

## Research Summary

- `_SECTION_KEYWORDS` (line 39-47) maps 7 section names to frozensets containing many generic programming words
- `_MODIFICATION_TYPES` (line 50-102) maps 3 types with generic verbs like "show", "format", "display", "handler", "event"
- `_extract_section_mentions()` (line 220-250) uses word-boundary regex for single words, substring for multi-word
- `_classify_modification_type()` (line 253-276) uses substring matching, no word boundaries
- `compute_conflict_score()` (line 279-322) weights: target 0.5, section 0.3, type 0.2
- Threshold at 0.4 separates parallel-safe from dependency proposals
- Tests use range assertions (`score > 0.6`, `score < 0.4`) through public API, not direct calls to private functions

## Implementation Plan

### Phase 1: Prune `_SECTION_KEYWORDS` (line 39-47)

Remove generic programming words, keeping only unambiguous UI terms:

```python
_SECTION_KEYWORDS: dict[str, frozenset[str]] = {
    "header": frozenset({"header", "navbar", "toolbar", "top bar"}),
    "body": frozenset({"droppable"}),
    "footer": frozenset({"footer", "status bar", "action bar"}),
    "sidebar": frozenset({"sidebar", "side panel", "drawer"}),
    "card": frozenset({"card", "tile"}),
    "modal": frozenset({"modal", "dialog", "popup", "overlay"}),
    "form": frozenset({"form"}),
}
```

**Removed from each section**:
- header: `heading`, `title bar`, `nav` (too generic)
- body: `body`, `content`, `main`, `list`, `table`, `grid` (all common programming words)
- footer: `bottom` (too generic)
- sidebar: `menu` (too generic)
- card: `item`, `row`, `entry` (too generic)
- modal: `sheet` (ambiguous — CSS sheets, spreadsheets)
- form: `input`, `field`, `editor`, `picker` (all common programming words)

### Phase 2: Prune `_MODIFICATION_TYPES` (line 50-102)

Remove generic words from infrastructure and enhancement types:

**infrastructure** — remove: `handler`, `event`, `enable`, `hook`, `context`, `store`
Keep: `listener`, `provider`, `state management`, `routing`, `middleware`, `dragging`, `drag`, `drop`, `dnd`

**enhancement** — remove: `display`, `show`, `render`, `format`, `style`
Keep: `add button`, `add field`, `add column`, `add stats`, `add icon`, `add toggle`, `empty state`, `placeholder`, `tooltip`, `badge`

### Phase 3: Update Tests

Existing tests use carefully crafted content strings with specific UI keywords. After pruning:
- Tests using removed keywords need updated content strings
- Tests using retained keywords should still pass
- Add a new test verifying that generic programming words DON'T inflate section scores

## Files to Modify

1. `scripts/little_loops/dependency_mapper.py` — prune keyword sets
2. `scripts/tests/test_dependency_mapper.py` — update tests for narrowed keywords

## Success Criteria

- [ ] `_SECTION_KEYWORDS` contains only unambiguous UI terms
- [ ] `_MODIFICATION_TYPES` contains only unambiguous modification indicators
- [ ] All existing tests pass (with updated assertions where needed)
- [ ] New test confirms generic words don't produce false section matches
- [ ] `python -m pytest scripts/tests/test_dependency_mapper.py -v` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/dependency_mapper.py` passes
