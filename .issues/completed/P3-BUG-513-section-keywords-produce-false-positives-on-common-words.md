---
discovered_commit: 325fd14
discovered_branch: main
discovered_date: 2026-02-26
discovered_by: manual-audit
focus_area: dependency-mapping
---

# BUG-513: Section keyword matching produces false positives on common programming words

## Summary

`_extract_section_mentions()` in `dependency_mapper.py:220-250` maps generic programming words to UI region names, inflating conflict scores and causing `/ll:map-dependencies` to propose spurious dependencies between unrelated issues.

## Current Behavior

The `_SECTION_KEYWORDS` dict at `dependency_mapper.py:39-47` includes common programming words as UI region triggers:

| Keyword | Maps to | Problem |
|---|---|---|
| `list` | `body` | Every issue mentioning a Python list, TODO list, or "list of files" |
| `table` | `body` | Database tables, markdown tables |
| `grid` | `body` | CSS grid references |
| `content` | `body` | Generic word in any description |
| `main` | `body` | Python `__main__`, `main` branch, main module |
| `entry` | `card` | Entry points, log entries, dictionary entries |
| `item` | `card` | List items, menu items, config items |
| `row` | `card` | Table rows, grid rows |
| `input` | `form` | CLI input, user input, function input |
| `field` | `form` | Data fields, struct fields, form fields |
| `editor` | `form` | Code editor references |
| `menu` | `sidebar` | Any menu reference |

These are matched with word-boundary regex (`\b`) at line 246, but that doesn't help — the words are genuinely present in backend/infrastructure issue descriptions.

### Impact on conflict scores

`compute_conflict_score()` at `dependency_mapper.py:279-322` weights section overlap at 0.3:

```python
return round(target_score * 0.5 + section_score * 0.3 + type_score * 0.2, 2)
```

Two backend issues both mentioning "list" and "input" get `section_score = 1.0` (both match `body` and `form`). Combined with `type_score = 1.0` if both are "enhancement" type (triggered by "format", "show", "display" at lines 83-101), the minimum conflict score is `0.0 * 0.5 + 1.0 * 0.3 + 1.0 * 0.2 = 0.50` — above the 0.4 threshold, triggering a dependency proposal.

Similarly, `_classify_modification_type()` at line 253-276 maps common words to types:
- "format" → enhancement (line 96)
- "show" → enhancement (line 93)
- "render" → enhancement (line 94)
- "display" → enhancement (line 92)
- "handler" → infrastructure (line 67)
- "event" → infrastructure (line 68)
- "extract" → structural (line 53)
- "split" → structural (line 54)

## Expected Behavior

Section keyword matching should only activate for issues that are clearly about UI components. Options:

1. **Remove generic programming words** from `_SECTION_KEYWORDS` entirely — keep only unambiguous UI terms like "header", "footer", "sidebar", "modal", "dialog"
2. **Require co-occurrence**: Only match a section if the word appears near a UI-related context word (e.g., "sidebar menu" counts, standalone "menu" does not)
3. **Reduce section weight**: Lower from 0.3 to 0.1, making it less impactful when false positives occur
4. **Context-aware filtering**: Skip section matching for issues tagged with `architecture`, `refactoring`, `infrastructure`, or `cli`

## Location

- **File**: `scripts/little_loops/dependency_mapper.py`
- **Line(s)**: 39-47 (`_SECTION_KEYWORDS`), 220-250 (`_extract_section_mentions`), 50-102 (`_MODIFICATION_TYPES`), 253-276 (`_classify_modification_type`)

## Proposed Solution

Remove or narrow the over-broad keywords. Suggested pruned `_SECTION_KEYWORDS`:

```python
_SECTION_KEYWORDS = {
    "header": frozenset({"header", "navbar", "toolbar", "top bar"}),
    "body": frozenset({"droppable"}),
    "footer": frozenset({"footer", "status bar", "action bar"}),
    "sidebar": frozenset({"sidebar", "side panel", "drawer"}),
    "card": frozenset({"card", "tile"}),
    "modal": frozenset({"modal", "dialog", "popup", "overlay"}),
    "form": frozenset({"form"}),
}
```

Removed: `heading`, `title bar`, `nav`, `content`, `main`, `list`, `table`, `grid`, `bottom`, `menu`, `item`, `row`, `entry`, `input`, `field`, `editor`, `picker`, `sheet`.

Similarly prune `_MODIFICATION_TYPES` to remove `"show"`, `"format"`, `"display"`, `"render"`, `"handler"`, `"event"` which are too generic.

## Scope Boundaries

- **In scope**: Pruning keyword sets, adjusting weights
- **Out of scope**: Rewriting the scoring algorithm, adding NLP-based detection

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` — prune `_SECTION_KEYWORDS` and `_MODIFICATION_TYPES`

### Tests
- `scripts/tests/test_dependency_mapper.py` — update tests for narrowed keyword sets

## Steps to Reproduce

1. Create two unrelated backend/infrastructure issues (e.g., one about CLI input parsing, one about list formatting)
2. Run `/ll:map-dependencies` on the issue set
3. Observe that both issues match `body` (via "list") and `form` (via "input") in `_SECTION_KEYWORDS`
4. Observe `section_score = 1.0` and `type_score = 1.0` (both classified as "enhancement" via "format"/"show"), yielding a minimum conflict score of 0.50 — above the 0.4 threshold
5. A spurious dependency proposal is generated between the two unrelated issues

## Actual Behavior

`_extract_section_mentions()` maps common programming words (list, input, table, field, etc.) to UI regions, and `_classify_modification_type()` maps generic verbs (show, format, display) to modification types. This inflates conflict scores between unrelated issues, causing `/ll:map-dependencies` to propose spurious dependencies.

## Impact

- **Severity**: Medium — inflates conflict scores, causing spurious dependency proposals
- **Effort**: Small
- **Risk**: Low (narrowing keyword sets is strictly more conservative)
- **Breaking Change**: No

## Labels

`bug`, `dependency-mapping`

---

## Resolution

**Fixed** — Pruned `_SECTION_KEYWORDS` and `_MODIFICATION_TYPES` to remove generic programming words that caused false positive section/type matches.

### Changes Made
- **`_SECTION_KEYWORDS`**: Removed `heading`, `title bar`, `nav`, `content`, `main`, `list`, `table`, `grid`, `body`, `bottom`, `menu`, `item`, `row`, `entry`, `sheet`, `input`, `field`, `editor`, `picker` — kept only unambiguous UI terms
- **`_MODIFICATION_TYPES` infrastructure**: Removed `enable`, `hook`, `handler`, `event`, `context`, `store` — kept drag/drop, routing, middleware terms
- **`_MODIFICATION_TYPES` enhancement**: Removed `display`, `show`, `render`, `style`, `format` — kept specific "add X" patterns, tooltip, badge, etc.
- Added regression test `test_generic_words_no_false_section_matches` confirming fix

## Status

**Resolved** | Created: 2026-02-26 | Resolved: 2026-02-26 | Priority: P3

## Session Log
- manual audit - 2026-02-26 - Identified during exhaustive dependency mapping system audit
- manage-issue - 2026-02-26 - Fixed by pruning keyword sets in dependency_mapper.py
