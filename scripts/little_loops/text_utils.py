"""Text extraction utilities for issue content.

Provides shared functions for extracting file paths from markdown issue
content. Used by dependency_mapper, issue_history, and other modules that
need to identify file references in issue text.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

# File path patterns for extraction from issue content
_BACKTICK_PATH = re.compile(r"`([^`\s]+\.[a-z]{2,4})`")
_BOLD_FILE_PATH = re.compile(r"\*\*File\*\*:\s*`?([^`\n]+\.[a-z]{2,4})`?")
_STANDALONE_PATH = re.compile(
    r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",
    re.MULTILINE,
)
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# File extensions that indicate real source file paths
SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".html",
        ".css",
        ".scss",
        ".sh",
        ".bash",
        ".sql",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".php",
    }
)


def extract_file_paths(content: str) -> set[str]:
    """Extract file paths from issue content.

    Searches for file paths in:
    - Backtick-quoted paths: `path/to/file.py`
    - Location section bold paths: **File**: `path/to/file.py`
    - Standalone paths with recognized extensions

    Code fence blocks are stripped before extraction to avoid
    matching paths inside example code. Line number suffixes
    (e.g., ``path.py:123``) are normalized by stripping the
    line number portion.

    Args:
        content: Issue file content

    Returns:
        Set of file paths found in the content
    """
    if not content:
        return set()

    # Strip code fences to avoid matching example paths
    stripped = _CODE_FENCE.sub("", content)

    paths: set[str] = set()
    for pattern in (_BOLD_FILE_PATH, _BACKTICK_PATH, _STANDALONE_PATH):
        for match in pattern.finditer(stripped):
            path = match.group(1).strip()
            # Normalize: remove line numbers (path.py:123 -> path.py)
            if ":" in path and path.split(":")[-1].isdigit():
                path = ":".join(path.split(":")[:-1])
            # Only include paths with directory separators or recognized extensions
            ext = Path(path).suffix.lower()
            if ext in SOURCE_EXTENSIONS and ("/" in path or ext):
                paths.add(path)
    return paths


# =============================================================================
# Word Extraction and Overlap Scoring
# =============================================================================

# Common stop words excluded from word extraction
_COMMON_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "should",
        "would",
        "could",
        "may",
        "might",
        "must",
        "file",
        "code",
        "issue",
    }
)


def extract_words(text: str) -> set[str]:
    """Extract significant words from text.

    Extracts all lowercase alphabetic words of 3+ characters,
    excluding common stop words. Useful for topic-based relevance
    scoring via Jaccard similarity.

    Args:
        text: Input text

    Returns:
        Set of lowercase words (3+ chars, excluding common words)
    """
    words = set(re.findall(r"\b[a-z]{3,}\b", text.lower()))
    return words - _COMMON_WORDS


def calculate_word_overlap(words1: set[str], words2: set[str]) -> float:
    """Calculate Jaccard similarity between word sets.

    Args:
        words1: First word set
        words2: Second word set

    Returns:
        Similarity score from 0.0 to 1.0
    """
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


# =============================================================================
# Duration Parsing
# =============================================================================

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def parse_duration(s: str) -> int:
    """Parse a duration string like '1h', '30m', '2d', '45s' into seconds.

    Args:
        s: Duration string with a numeric value followed by a unit (s/m/h/d)

    Returns:
        Number of seconds represented by the duration

    Raises:
        ValueError: If the string does not match the expected format
    """
    m = _DURATION_RE.match(s)
    if not m:
        raise ValueError(f"Invalid duration: {s!r}. Use e.g. 1h, 30m, 2d, 45s")
    return int(m.group(1)) * _DURATION_UNITS[m.group(2)]


def score_bm25(
    query_words: set[str],
    doc_words: set[str],
    doc_freq: dict[str, int],
    avg_doc_len: float,
    total_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compute BM25 relevance score for a document against a query.

    Uses the Robertson BM25 formula with IDF smoothing. Since doc_words
    is a set (unique terms only), term frequency within the document is
    always 1 for matching terms.

    Args:
        query_words: Set of query terms
        doc_words: Set of document terms (unique words, from extract_words)
        doc_freq: Document frequency per term (number of docs containing each term)
        avg_doc_len: Average document length in unique words across corpus
        total_docs: Total number of documents in corpus
        k1: Term frequency saturation parameter (default: 1.5)
        b: Length normalization parameter (default: 0.75)

    Returns:
        BM25 score (non-negative float, unbounded above)
    """
    if not query_words or not doc_words or total_docs == 0 or avg_doc_len == 0:
        return 0.0

    doc_len = len(doc_words)
    score = 0.0

    for term in query_words & doc_words:
        df = doc_freq.get(term, 0)
        # Robertson IDF with +1 smoothing to keep score non-negative
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)
        # TF = 1 (term present in doc), with length normalization
        tf_norm = (k1 + 1) / (1 + k1 * (1 - b + b * doc_len / avg_doc_len))
        score += idf * tf_norm

    return score
