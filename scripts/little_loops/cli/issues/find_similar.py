"""ll-issues find-similar: title-based word-overlap similarity over the issue corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


@dataclass
class SimilarityMatch:
    """A single issue's title-similarity score against a query text."""

    id: str
    title: str
    path: str
    score: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict, rounding score to 3 decimals."""
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "score": round(self.score, 3),
        }


@dataclass
class SimilarityPair:
    """A pair of issues whose titles overlap above threshold (batch mode)."""

    a: str
    b: str
    score: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict, rounding score to 3 decimals."""
        return {"a": self.a, "b": self.b, "score": round(self.score, 3)}


def _status_filter_for(against: str) -> set[str] | None:
    """Map the --against axis to a find_issues() status_filter.

    "open" -> None (find_issues' default: excludes done/cancelled/deferred).
    "all" -> the full status enum, including done/cancelled/deferred.
    """
    from little_loops.issue_progress import _ALL_STATUSES

    if against == "all":
        return set(_ALL_STATUSES)
    return None


def find_similar(
    config: BRConfig,
    text: str,
    *,
    against: str = "open",
    threshold: float | None = None,
    limit: int | None = None,
) -> list[SimilarityMatch]:
    """Score `text` against every issue's title via Jaccard word overlap.

    Args:
        config: Project configuration.
        text: Query text (typically a candidate issue title).
        against: "open" (default) or "all" issues.
        threshold: Minimum score to include; defaults to
            config.issues.duplicate_detection.similar_threshold.
        limit: Cap on the number of returned matches (post-sort truncation).

    Returns:
        SimilarityMatch list sorted by score descending.
    """
    from little_loops.issue_parser import find_issues
    from little_loops.text_utils import calculate_word_overlap, extract_words

    if threshold is None:
        threshold = config.issues.duplicate_detection.similar_threshold

    query_words = extract_words(text)
    issues = find_issues(config, status_filter=_status_filter_for(against))

    matches: list[SimilarityMatch] = []
    for info in issues:
        score = calculate_word_overlap(query_words, extract_words(info.title))
        if score >= threshold:
            matches.append(
                SimilarityMatch(
                    id=info.issue_id, title=info.title, path=str(info.path), score=score
                )
            )

    matches.sort(key=lambda m: -m.score)
    return matches[:limit] if limit is not None else matches


def batch_similarity(
    config: BRConfig,
    *,
    against: str = "open",
    threshold: float | None = None,
    limit: int | None = None,
) -> list[SimilarityPair]:
    """Pairwise title-similarity scan over the issue corpus.

    Word sets are extracted once per issue before the O(n^2) pairwise loop.

    Args:
        config: Project configuration.
        against: "open" (default) or "all" issues.
        threshold: Minimum score to include; defaults to
            config.issues.duplicate_detection.similar_threshold.
        limit: Cap on the number of returned pairs (post-sort truncation; does
            not bound the comparison work).

    Returns:
        SimilarityPair list sorted by score descending.
    """
    from little_loops.issue_parser import find_issues
    from little_loops.text_utils import calculate_word_overlap, extract_words

    if threshold is None:
        threshold = config.issues.duplicate_detection.similar_threshold

    issues = find_issues(config, status_filter=_status_filter_for(against))
    word_sets = [(info, extract_words(info.title)) for info in issues]

    pairs: list[SimilarityPair] = []
    for i, (info_a, words_a) in enumerate(word_sets):
        for info_b, words_b in word_sets[i + 1 :]:
            score = calculate_word_overlap(words_a, words_b)
            if score >= threshold:
                pairs.append(SimilarityPair(a=info_a.issue_id, b=info_b.issue_id, score=score))

    pairs.sort(key=lambda p: -p.score)
    return pairs[:limit] if limit is not None else pairs


def cmd_find_similar(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch single-text or --batch similarity scoring and print JSON.

    Args:
        config: Project configuration.
        args: Parsed arguments (.text, .batch, .against, .threshold, .limit).

    Returns:
        0 on success, 1 on error (missing text in single-text mode).
    """
    if args.batch:
        pairs = batch_similarity(
            config, against=args.against, threshold=args.threshold, limit=args.limit
        )
        print(json.dumps([p.to_dict() for p in pairs], indent=2))
        return 0

    if not args.text:
        print("Error: TEXT argument is required unless --batch is set", file=sys.stderr)
        return 1

    matches = find_similar(
        config, args.text, against=args.against, threshold=args.threshold, limit=args.limit
    )
    print(json.dumps([m.to_dict() for m in matches], indent=2))
    return 0
