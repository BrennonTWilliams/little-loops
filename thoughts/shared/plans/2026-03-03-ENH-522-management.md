# ENH-522 Implementation Plan: Hybrid Relevance Scoring for ll-history generate-docs

**Date**: 2026-03-03
**Issue**: ENH-522
**Approach**: Add BM25 scoring alongside intersection scoring; expose via --scoring CLI flag

## Summary of Changes

1. **`text_utils.py`**: Add `score_bm25()` after `calculate_word_overlap()` (line 161+)
2. **`doc_synthesis.py`**: Update `score_relevance()` + `synthesize_docs()` to support corpus stats and scoring modes
3. **`cli/history.py`**: Add `--scoring` flag to `generate-docs` subparser
4. **Tests**: Add BM25 tests to `test_text_utils.py` and `test_doc_synthesis.py`
5. **Docs**: Update `docs/reference/API.md`

## Design Decisions

- `score_bm25()` parameters: `query_words, doc_words, doc_freq, avg_doc_len, total_docs, k1=1.5, b=0.75`
- BM25 normalization: `bm25 / (bm25 + 1)` maps [0,∞) → [0,1) smoothly
- `score_relevance()` gets `corpus_stats: dict | None = None` and `scoring: str = "intersection"` params
- `synthesize_docs()` gets `scoring: str = "intersection"` param; pre-scans corpus when scoring != "intersection"
- Corpus stats computed over pre-filtered candidates (type + date filtered, before relevance filter)
- Default behavior unchanged (intersection mode, backward compatible)

## Phase 0: Write Tests (Red)
- `TestScoreBM25`: basic score, zero query, zero doc, IDF weighting, length normalization
- `TestScoreRelevance` additions: with corpus_stats (hybrid), scoring="bm25" mode
- `TestSynthesizeDocs` additions: hybrid produces differentiated rankings
- `TestGenerateDocsCLI` additions: --scoring flag parsing

## Implementation Checklist

- [ ] Add `score_bm25()` to `text_utils.py`
- [ ] Update `score_relevance()` signature and logic in `doc_synthesis.py`
- [ ] Add `_compute_corpus_stats()` helper in `doc_synthesis.py`
- [ ] Update `synthesize_docs()` in `doc_synthesis.py`
- [ ] Add `--scoring` to `history.py` generate-docs subparser
- [ ] Wire `scoring` param through CLI to `synthesize_docs()`
- [ ] Add `TestScoreBM25` in `test_text_utils.py`
- [ ] Add hybrid/BM25 tests to `test_doc_synthesis.py`
- [ ] Update `docs/reference/API.md`
