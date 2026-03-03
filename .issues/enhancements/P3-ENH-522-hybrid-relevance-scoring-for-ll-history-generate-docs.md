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

Currently the tool uses simple intersection scoring which works but produces binary-ish scores (0.0, 0.5, 1.0) with no way to rank among matching documents. All documents with the same intersection score are effectively tied.

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
- `scripts/little_loops/issue_history/doc_synthesis.py` - Add BM25 scoring logic
- `scripts/little_loops/cli/history.py` - Add `--scoring` flag (intersection|bm25|hybrid)
- `scripts/little_loops/text_utils.py` - Add BM25 calculation function

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/__init__.py` - Exports `synthesize_docs`

### Tests
- `scripts/tests/test_issue_history.py` - Add tests for BM25 scoring
- `scripts/tests/test_text_utils.py` - Add tests for BM25 function

### Documentation
- `docs/reference/API.md` - Document new scoring parameter

### Configuration
- N/A

## Implementation Steps

1. Add `score_bm25()` function to `text_utils.py` with TF-IDF and length normalization
2. Add corpus statistics computation to `doc_synthesis.py` (doc frequencies, avg length)
3. Update `score_relevance()` to optionally use hybrid scoring
4. Add `--scoring` CLI flag to choose scoring method
5. Update tests to cover new scoring methods
6. Update documentation

## Impact

- **Priority**: P3 - Enhancement to recently implemented feature, improves ranking quality
- **Effort**: Medium - BM25 implementation is straightforward, but requires corpus pre-scan and score normalization
- **Risk**: Low - Intersection scoring remains default, BM25 is opt-in enhancement
- **Breaking Change**: No - Default behavior unchanged, BM25 is additive

## Labels

`enhancement`, `ll-history`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/54ea04b1-9748-4277-ba23-8560b42c40a0.jsonl`

---
**Open** | Created: 2026-03-02 | Priority: P3
