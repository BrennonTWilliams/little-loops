# FEAT-503 Implementation Plan

## Summary
Add `generate-docs` subcommand to `ll-history` that synthesizes architecture documentation from completed issue history.

## Steps

### Step 1: Promote text helpers to `text_utils.py`
- Add `extract_words()` and `calculate_word_overlap()` as public functions
- Exact same implementations as `matching.py` private versions, without leading underscores

### Step 2: Update `matching.py`
- Replace function definitions with imports from `text_utils` aliased to preserve private names
- Keeps backward compatibility for all callers (search.py, __init__.py, tests)

### Step 3: Create `doc_synthesis.py` module
- New file: `scripts/little_loops/issue_history/doc_synthesis.py`
- Functions: `score_relevance`, `synthesize_docs`, `build_narrative_doc`, `build_structured_doc`
- Uses `extract_words`/`calculate_word_overlap` from `text_utils`
- Uses `lines: list[str]` accumulation pattern from `formatting.py`
- Uses `contents: dict[Path, str]` pre-loading pattern from `analysis.py`

### Step 4: Add `generate-docs` subparser to `history.py`
- Add deferred imports for new functions
- Register subparser with args: topic (positional), --output, --format, --since, --min-relevance, --type, -d
- Add dispatch block following existing pattern

### Step 5: Update `issue_history/__init__.py`
- Import and export `synthesize_docs`, `score_relevance`, `build_narrative_doc`, `build_structured_doc`

### Step 6: Write tests
- `test_doc_synthesis.py` - at least 5 unit tests for scoring, ordering, formatting
- `test_text_utils.py` - tests for promoted functions

### Step 7: Update CLI epilog
- Add generate-docs examples to help text

## Success Criteria
- [x] `extract_words` and `calculate_word_overlap` promoted to `text_utils.py`
- [ ] `matching.py` updated to import from `text_utils`
- [ ] `doc_synthesis.py` created with scoring and synthesis logic
- [ ] `generate-docs` subparser registered in CLI
- [ ] `__init__.py` exports updated
- [ ] At least 5 unit tests for `doc_synthesis.py`
- [ ] Tests for `text_utils.py` promoted functions
- [ ] All existing tests pass
- [ ] Linting and type checking pass
