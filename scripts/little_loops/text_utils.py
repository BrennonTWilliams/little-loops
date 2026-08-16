"""Text extraction utilities for issue content.

Provides shared functions for extracting file paths from markdown issue
content. Used by dependency_mapper, issue_history, and other modules that
need to identify file references in issue text.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

# File path patterns for extraction from issue content
_BACKTICK_PATH = re.compile(r"`([^`\s]+\.[a-z]{2,4})`")
_BOLD_FILE_PATH = re.compile(r"\*\*File\*\*:\s*`?([^`\n]+\.[a-z]{2,4})`?")
_STANDALONE_PATH = re.compile(
    r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",
    re.MULTILINE,
)
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Line-anchored fence delimiter (BUG-3202). Unlike ``_CODE_FENCE``, which has
# no ``^`` anchor and so lets an inline triple-backtick mention in prose pair
# with the next real fence opener, this only matches a delimiter that starts
# its own line — the markdown-correct shape.
_LINE_FENCE_DELIMITER_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)

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


def fence_spans(content: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` character-offset spans of fenced code blocks.

    Shared fence-span helper (BUG-3202), exported so every heading-resolution
    call site excludes fenced ``##``-shaped lines the same way instead of
    reimplementing its own fence idiom. Offset-preserving by construction: it
    never rewrites *content*, only locates spans within it, so callers can
    slice the original string at offsets computed against these spans (unlike
    :func:`strip_code_fences`, which removes text and shifts every later
    offset).

    Delimiters are matched via :data:`_LINE_FENCE_DELIMITER_RE`
    (line-start-anchored), not :data:`_CODE_FENCE`, so an inline triple-
    backtick mention in prose cannot pair with the next real fence opener and
    invert fenced/unfenced classification for the rest of the document.

    Markers are paired consecutively (1st+2nd, 3rd+4th, ...). An odd number of
    markers leaves the trailing, unpaired marker's opener treated as *not*
    fenced (fail-open) rather than swallowing the remainder of the document —
    the deliberate choice for hand-authored issue bodies, which routinely have
    unbalanced fences.

    Args:
        content: Text to scan for fenced code blocks.

    Returns:
        A list of ``(start, end)`` spans, each covering from a fence opener's
        line start through its paired closer's line end.
    """
    markers = list(_LINE_FENCE_DELIMITER_RE.finditer(content))
    return [(markers[i].start(), markers[i + 1].end()) for i in range(0, len(markers) - 1, 2)]


def in_fence(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """True when the ``[start, end)`` span is fully contained in a fence span.

    Companion to :func:`fence_spans`. Mirrors the ``_in_fence`` idiom already
    used by ``issues/symbol_claims.py`` and ``issues/prose_deps.py`` — this is
    the shared, exported form those (and BUG-3202's other call sites) are
    meant to converge on.
    """
    return any(fs <= start and end <= fe for fs, fe in spans)


def strip_code_fences(content: str) -> str:
    """Remove fenced code blocks from *content*.

    The public form of the fence handling :func:`extract_file_paths` applies,
    so callers that scan the same text for something else (e.g. ENH-2971's
    symbol check) use identical fence semantics rather than a second regex.
    """
    return _CODE_FENCE.sub("", content)


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
    stripped = strip_code_fences(content)

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
# File Reference Classification (ENH-2983)
# =============================================================================

RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]

# Characters that mark a reference as a glob pattern rather than a literal
# path (e.g. `skills/*/SKILL.md`) — always unresolvable_form. `{`/`}` added
# (BUG-3194 Finding 2) for brace expansion (`.gemini/skills/{a,b}/SKILL.md`),
# a shape /ll:wire-issue itself emits — no character-class check can leave it
# unresolvable_form-classified without this addition.
_GLOB_CHARS = frozenset("*?[]{}")

# BUG-3194 Finding 2: a non-final path component that itself looks like a
# filename (has a short alpha extension) means the span is two filenames
# joined by prose punctuation ("ARCHITECTURE.md/CONTRIBUTING.md" from a title
# like "ARCHITECTURE.md/CONTRIBUTING.md directory trees list …"), not one
# path -- the slash is a conjunction. Hidden dot-directories (`.ll/`,
# `.gemini/`) are excluded by requiring the component not start with `.`, so
# a genuine ref like `.ll/ll-continue-prompt.md` keeps resolving.
_EXTENSION_LIKE_COMPONENT_RE = re.compile(r"^[^.].*\.[A-Za-z0-9]{1,6}$")


def _has_extension_like_directory_component(ref: str) -> bool:
    parts = ref.split("/")
    return any(_EXTENSION_LIKE_COMPONENT_RE.match(part) for part in parts[:-1])


# A line-context marker for a not-yet-created file, e.g.
# "- `scripts/new_thing.py` (new)". Case-insensitive.
#
# Corpus survey of `.issues/` when this was widened: `(new)` 323, `**new**` 67,
# `(new file)` 34, `(to be created)` 2 — the original `(new)`-only pattern
# missed 28% of planned-new declarations and reported them as drift.
#
# `(does not exist)` (24 uses) is deliberately NOT matched: that phrase marks a
# file the author *confirmed absent*, which is a true `stale` finding, not a
# planned one. Adding it here would suppress real drift.
_PLANNED_NEW_RE = re.compile(r"\((?:new|new file|to be created)\)|\*\*new\*\*", re.IGNORECASE)


@cache
def _mirror_prefixes() -> tuple[str, ...]:
    """Path prefixes of generated host-adapter mirrors of tracked source.

    ``.codex/``, ``.gemini/``, and ``.kimi-code/`` hold ``ll-adapt``-generated
    copies of ``skills/`` and ``agents/``. They are tracked, so they inflate the
    basename index and make an unrooted ref like ``confidence-check/SKILL.md``
    match three paths instead of one — see :func:`resolve_ref_path`.

    Derived from the host-capability registry rather than hardcoded so a newly
    registered adapter host is covered without a second edit here. Imported
    lazily and cached: ``text_utils`` is a leaf utility and importing
    ``little_loops.adapters`` eagerly would pull the emitter chain in with it.
    """
    from little_loops.adapters.capabilities import HOST_CAPABILITIES

    return tuple(entry.config_dir + "/" for entry in HOST_CAPABILITIES.values() if entry.config_dir)


@dataclass(frozen=True)
class RefIndex:
    """Tracked-file index for file-reference resolution (ENH-2983).

    Built once per invocation via :func:`build_ref_index` and threaded
    through every :func:`classify_file_ref` call rather than shelling out
    to ``git ls-files`` per reference.
    """

    by_basename: dict[str, list[str]]  # basename -> tracked repo-relative paths


def build_ref_index(root: Path) -> RefIndex:
    """Index tracked files by basename via a single ``git ls-files`` call.

    Follows the fail-*empty*-never-raise convention shared by the other
    ``git ls-files`` call sites in this codebase (e.g.
    ``cli/verify_private_refs.py``'s ``_tracked_files()``,
    ``codequery/fallback.py``'s ``_tracked_py_files()``): an unavailable git
    binary or a non-zero exit yields an empty index rather than raising, so
    a caller like ``check_format_gaps()`` can keep its own fail-open
    contract intact.

    Args:
        root: Repository root to run ``git ls-files`` from.

    Returns:
        A :class:`RefIndex` mapping each tracked file's basename to the
        list of repo-relative paths sharing that basename.
    """
    by_basename: dict[str, list[str]] = {}
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return RefIndex(by_basename=by_basename)
    if result.returncode != 0:
        return RefIndex(by_basename=by_basename)

    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    for name in names:
        if not name:
            continue
        basename = name.rsplit("/", 1)[-1]
        by_basename.setdefault(basename, []).append(name)
    return RefIndex(by_basename=by_basename)


def classify_file_ref(ref: str, index: RefIndex, *, line: str = "") -> RefStatus:
    """Classify one path reference extracted from issue prose.

    Resolution order (not commutative — see ENH-2983 Program Design):

    1. Form checks first — a glob (``skills/*/SKILL.md``, or brace expansion
       ``{a,b}/SKILL.md``), a ``<placeholder>``-bearing path, an outside-repo
       path (``~/…`` or a leading ``/``), a bare basename with no ``/``, or a
       non-final path component that is itself extension-shaped
       (``ARCHITECTURE.md/CONTRIBUTING.md`` — two filenames joined by prose,
       not one path; BUG-3194) all return ``unresolvable_form`` immediately.
       This must run before any
       suffix matching, or a bare basename like ``SKILL.md`` would
       spuriously suffix-match dozens of unrelated tracked files. The
       outside-repo check matters for the *verdict*, not just efficiency: a
       ``~/.claude/CLAUDE.md`` is not repo-relative and can never resolve
       against a ``git ls-files`` index, so calling it ``stale`` would assert
       drift that cannot be true.
    2. ``planned_new`` from line context (``(new)`` marker) — a planned file
       legitimately fails both existence and suffix match, so it must be
       distinguished before either lookup.
    3. An exact tracked-path match (``ref`` itself is a tracked repo-relative
       path) resolves.
    4. A *unique* suffix match against the basename-keyed index resolves —
       an unrooted partial path like ``fsm/executor.py`` cited without its
       ``scripts/little_loops/`` prefix. Zero matches is ``stale``;
       more-than-one is ``ambiguous`` (ambiguous matches must not silently
       resolve), except that generated host-adapter mirrors are tie-broken
       away first — see :func:`suffix_match_candidates`.
    5. Otherwise ``stale`` — a ``/``-qualified path with no match, the
       genuine-drift signal this classifier exists to surface.

    Args:
        ref: The path reference as extracted from issue prose.
        index: A :class:`RefIndex` built once per invocation.
        line: The source line the reference was found on, used only for
            ``planned_new`` detection.

    Returns:
        One of ``"resolved"``, ``"stale"``, ``"unresolvable_form"``,
        ``"planned_new"``, or ``"ambiguous"``.
    """
    if any(ch in ref for ch in _GLOB_CHARS):
        return "unresolvable_form"
    if "<" in ref or ">" in ref:
        return "unresolvable_form"
    if ref.startswith(("~", "/")):
        return "unresolvable_form"
    if "/" not in ref:
        return "unresolvable_form"
    if _has_extension_like_directory_component(ref):
        return "unresolvable_form"

    if line and _PLANNED_NEW_RE.search(line):
        return "planned_new"

    candidates = suffix_match_candidates(ref, index)
    if len(candidates) == 1:
        return "resolved"
    if len(candidates) > 1:
        return "ambiguous"
    return "stale"


def suffix_match_candidates(ref: str, index: RefIndex) -> list[str]:
    """Candidates for *ref* after the existing tie-break order.

    0 = absent, 1 = resolves, >1 = ambiguous. Holds the shared body of the
    resolution steps used by both :func:`resolve_ref_path` (which needs only
    the resolved target) and :func:`classify_file_ref` (which needs to tell
    "no match" apart from "many matches").

    Ambiguity is resolved against generated host-adapter mirrors before it is
    given up on: ``confidence-check/SKILL.md`` suffix-matches ``skills/…`` plus
    one copy per adapter host, and reporting a plainly-present file as drift is
    worse than picking the source of truth the mirrors were generated from. The
    tie-break runs *after* the exact-match step below, so a deliberate ref to a
    mirror (``.codex/agents/loop-specialist.toml``) still resolves to itself,
    and *before* it is applied when there is already a unique suffix match —
    a ref whose only match is a mirror (``agents/codebase-analyzer.toml`` ->
    ``.codex/agents/codebase-analyzer.toml``) still resolves to that mirror.
    Genuine same-name ambiguity between two non-mirror paths still declines;
    if every match is a mirror, the mirror filter yields an empty list, which
    is reported the same as zero matches (``stale``), not ``ambiguous``.
    """
    basename = ref.rsplit("/", 1)[-1]
    candidates = index.by_basename.get(basename, [])
    if ref in candidates:
        return [ref]

    suffix = "/" + ref
    matches = [p for p in candidates if p.endswith(suffix)]
    if len(matches) == 1:
        return matches

    return [p for p in matches if not p.startswith(_mirror_prefixes())]


def resolve_ref_path(ref: str, index: RefIndex) -> str | None:
    """Return the tracked repo-relative path *ref* resolves to, else ``None``.

    Steps 3-4 of :func:`classify_file_ref`'s resolution order, factored out so
    callers that need the *target* rather than the verdict (ENH-2971's
    staleness check has to stat the file) cannot drift from the classifier.
    Assumes the form checks have already passed; call it via
    :func:`classify_file_ref` unless you have run them yourself.

    Signature and behavior are unchanged by ENH-2999: this still returns the
    single element when there is exactly one, else ``None`` — a caller cannot
    tell "no match" from "ambiguous" through this function; use
    :func:`classify_file_ref` (or :func:`suffix_match_candidates` directly) for
    that distinction.
    """
    candidates = suffix_match_candidates(ref, index)
    return candidates[0] if len(candidates) == 1 else None


def classify_issue_refs(content: str, index: RefIndex) -> dict[str, RefStatus]:
    """Classify every file path reference extracted from one issue body.

    Pairs each reference returned by :func:`extract_file_paths` with a source
    line it appears on (needed for ``planned_new`` detection) before
    classifying it with :func:`classify_file_ref`.

    Line selection prefers a *marked* mention over the first one. A planned
    file is routinely discussed in prose ("→ ``docs/reference/FOO.md``, because
    …") well before its marked ``### Files to Modify`` entry, and keying on the
    first mention alone classified it as drift while the declaration sat a
    hundred lines below. The declaration is a property of the issue, not of
    whichever paragraph happens to mention the path first.

    Args:
        content: Full issue file content (frontmatter + body).
        index: A :class:`RefIndex` built once per invocation.

    Returns:
        A mapping of reference string to its :data:`RefStatus`.
    """
    refs = extract_file_paths(content)
    if not refs:
        return {}
    lines = content.splitlines()
    result: dict[str, RefStatus] = {}
    for ref in refs:
        mentions = [ln for ln in lines if ref in ln]
        line_text = next(
            (ln for ln in mentions if _PLANNED_NEW_RE.search(ln)),
            mentions[0] if mentions else "",
        )
        result[ref] = classify_file_ref(ref, index, line=line_text)
    return result


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
