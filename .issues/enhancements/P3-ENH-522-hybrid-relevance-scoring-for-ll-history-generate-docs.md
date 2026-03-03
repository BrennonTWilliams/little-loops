# ENH-522: Add Hybrid Relevance Scoring to ll-history generate-docs

---
issue_id: ENH-522
issue_type: ENH
priority: P3
status: open
discovered_date: 2026-03-02
discovered_by: capture-issue
---

## Summary

Enhance `ll-history generate-docs` with hybrid relevance scoring that combines intersection-based filtering (for recall) with BM25 ranking (for precision).

## Current Behavior

Currently `score_relevance()` at `doc_synthesis.py:18-42` uses intersection scoring: `len(topic_words & issue_words) / len(topic_words)`. This measures what fraction of topic words appear anywhere in the issue text, producing binary-ish scores (0.0, 0.5, 1.0) with no way to rank among matching documents. All documents with the same intersection score are effectively tied.

The `extract_words()` function at `text_utils.py:130-144` tokenizes via `re.findall(r"\b[a-z]{3,}\b", text.lower())` and removes 26 stop words — no stemming, no term frequency, no IDF weighting.

## Expected Behavior

The hybrid approach should:
1. Use intersection scoring as primary filter (what fraction of topic words appear)
2. Use BM25 to differentiate and rank among documents that pass the threshold
3. Combine scores for final ranking

## Motivation

**Better ranking quality**: BM25 considers term frequency (repeated terms = more relevant) and IDF (rare terms weighted higher than common ones), producing meaningful ranking scores instead of binary ties.

**Length normalization**: Shorter docs rank proportionally higher for same term count, which is desirable for topic matching.

**Industry standard**: BM25 is well-understood and tunable with parameters (k1, b).

## Proposed Solution

### Scoring Changes

```python
def score_relevance(topic: str, issue: CompletedIssue, content: str,
                    corpus_stats: dict | None = None) -> float:
    topic_words = extract_words(topic)
    issue_words = extract_words(f"{issue.issue_id} {issue.path.stem} {content}")

    # Primary: intersection (0.0 - 1.0) for recall
    intersection_score = len(topic_words & issue_words) / len(topic_words) if topic_words else 0.0

    if intersection_score == 0:
        return 0.0

    # Optional: BM25 for precision/ranking
    if corpus_stats:
        bm25 = score_bm25(topic_words, issue_words, **corpus_stats)
        return intersection_score * 0.5 + normalize(bm25) * 0.5

    return intersection_score
```

### Corpus Statistics

BM25 requires:
- Document frequencies (how many docs contain each term)
- Average document length
- Total document count

These would be computed via a pre-scan step in `synthesize_docs()` or cached.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/doc_synthesis.py` — Modify `score_relevance()` (line 18) to accept optional `corpus_stats` parameter; update `synthesize_docs()` (line 84) to compute corpus statistics in a pre-scan before scoring loop
- `scripts/little_loops/cli/history.py` — Add `--scoring` flag with `choices=["intersection", "bm25", "hybrid"]` to `generate-docs` subparser (lines 100-153); wire through to `synthesize_docs()` dispatch at line 209
- `scripts/little_loops/text_utils.py` — Add `score_bm25()` function alongside existing `extract_words()` (line 130) and `calculate_word_overlap()` (line 147)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/__init__.py` — Re-exports `score_relevance` (line 75) and `synthesize_docs` (line 76); if `score_relevance` signature changes, the re-export still works but callers using the new parameter need to pass it explicitly

### Similar Patterns
- `scripts/little_loops/dependency_mapper.py:268-320` — `compute_conflict_score()` uses weighted multi-signal combination with configurable weights; similar hybrid scoring approach
- `scripts/little_loops/workflow_sequence_analyzer.py:294-338` — `semantic_similarity()` combines 4 signals with hard-coded weights
- `scripts/little_loops/issue_discovery/search.py:76-110` — `search_issues_by_content()` uses score→filter→sort pipeline identical to `synthesize_docs`

### Tests
- `scripts/tests/test_doc_synthesis.py` — Existing `TestScoreRelevance` class (line 121) tests boundary conditions; add tests for BM25 and hybrid scoring modes
- `scripts/tests/test_text_utils.py` — Existing `TestCalculateWordOverlap` class (line 43) tests Jaccard; add parallel tests for `score_bm25()`
- `scripts/tests/test_issue_history_cli.py` — Existing CLI integration tests (line 53); add tests for `--scoring` flag parsing

### Documentation
- `docs/reference/API.md` — Document new `--scoring` parameter and `score_bm25()` function

### Configuration
- N/A — scoring method controlled via CLI flag, not config file

## Implementation Steps

1. **Add `score_bm25()` to `text_utils.py`** — Place after `calculate_word_overlap()` (line 161). Implement BM25 with parameters `k1=1.5`, `b=0.75`. Function signature: `score_bm25(query_words: set[str], doc_words: set[str], doc_freq: dict[str, int], avg_doc_len: float, total_docs: int) -> float`
2. **Add corpus pre-scan to `synthesize_docs()`** — In `doc_synthesis.py`, before the scoring loop (line 112), add a pre-pass computing: document frequencies per term, average document length, total document count. Store in a `dict` passed to `score_relevance()`
3. **Update `score_relevance()` signature** — Add optional `corpus_stats: dict | None = None` parameter. When `None`, use current intersection-only scoring. When provided, compute hybrid score: `intersection * 0.5 + normalize(bm25) * 0.5`
4. **Add `--scoring` CLI flag** — In `cli/history.py`, add to `generate-docs` subparser (after `--min-relevance` at line 144): `choices=["intersection", "bm25", "hybrid"]`, default `"intersection"`. Wire through `synthesize_docs()` to control whether corpus stats are computed
5. **Add tests** — In `test_text_utils.py`: test `score_bm25()` with known inputs. In `test_doc_synthesis.py`: test `score_relevance()` with and without corpus_stats, verify hybrid scoring produces differentiated rankings. In `test_issue_history_cli.py`: test `--scoring` flag parsing
6. **Update API docs** — Add `score_bm25()` and `--scoring` flag to `docs/reference/API.md`

## Impact

- **Priority**: P3 - Enhancement to recently implemented feature, improves ranking quality
- **Effort**: Medium - BM25 implementation is straightforward, but requires corpus pre-scan and score normalization
- **Risk**: Low - Intersection scoring remains default, BM25 is opt-in enhancement
- **Breaking Change**: No - Default behavior unchanged, BM25 is additive

## Labels

`enhancement`, `ll-history`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/54ea04b1-9748-4277-ba23-8560b42c40a0.jsonl`
- `/ll:refine-issue` - 2026-03-03 - Corrected test file refs (test_issue_history.py→test_doc_synthesis.py); added exact line numbers for score_relevance, synthesize_docs, extract_words; identified similar patterns (compute_conflict_score, semantic_similarity); enriched integration map and implementation steps

---
**Open** | Created: 2026-03-02 | Priority: P3
