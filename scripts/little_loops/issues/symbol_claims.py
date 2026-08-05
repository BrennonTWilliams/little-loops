"""Symbol-claim extractor and forward-existence resolver (FEAT-3048).

Peer of :mod:`little_loops.issues.prose_deps`: same fence-aware, regex-based
shape, extended to a second claim class — a backticked symbol attributed to a
cited file ("`extract_prose_deps` in `little_loops/issues/prose_deps.py`",
"`prose_deps.extract_prose_deps`", "`prose_deps.py:extract_prose_deps`")
rather than an issue-ID dependency phrase.

Only the three forms pinned in FEAT-3048's § Claim Grammar count as claims. A
bare backticked identifier with no file attribution is never a claim — the
false-positive-control measure that keeps this extractor from choking on the
~30,500 `foo()`-shaped backticked tokens already in the backlog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.issues.anchors import _ANCHOR_PATTERNS
from little_loops.text_utils import _CODE_FENCE, RefIndex, resolve_ref_path

# Reuse the function/class def-site regexes _ANCHOR_PATTERNS already carries
# for its inverse "what encloses line N" query — "section" (markdown
# headings) is not a code symbol and is excluded. Module-level constants
# (`_FIELD_FLAGS = (...)`) are the one symbol shape those regexes don't
# cover (see § Types), so a dedicated pattern is added alongside them.
_SYMBOL_DEF_PATTERNS: list[re.Pattern[str]] = [
    pattern for pattern, kind in _ANCHOR_PATTERNS if kind in ("function", "class")
]
_MODULE_CONSTANT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)")

# Languages the def-site patterns above meaningfully cover — a cited file
# outside this set produces no claim (fail-open), never a gap, per § Claim
# Grammar's "Language scope" bullet.
_SUPPORTED_SYMBOL_EXTENSIONS = frozenset(
    {".py", ".rb", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs"}
)

_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
_EXPLICIT_RE = re.compile(r"^([\w./-]+\.[A-Za-z0-9]{1,6}):([A-Za-z_]\w*)(?:\(\))?$")
_DOTTED_RE = re.compile(r"^([A-Za-z_]\w*)\.([A-Za-z_]\w*)(\(\))?$")
_BARE_SYMBOL_RE = re.compile(r"^([A-Za-z_]\w*)(\(\))?$")
# Line-number shorthand ("L519", "L242") is a common citation form in this
# codebase's own review prose, not a code symbol -- excluded from the bare
# form to avoid a systematic false-positive class.
_LINE_NUMBER_REF_RE = re.compile(r"^L\d+$")
_FILE_PATH_BACKTICK_RE = re.compile(r"^[\w./-]+\.[A-Za-z0-9]{1,6}$")

# A short, lowercase-only "attr" after the dot is overwhelmingly a file
# extension ("`prose_deps.py`" parsing as module=prose_deps, attr=py), not a
# real symbol -- Python/JS symbol names are snake_case, camelCase, or
# PascalCase in this codebase and essentially never a bare 1-4 char lowercase
# token. Excluding this shape is what keeps a bare backticked filename from
# misparsing as a dotted symbol claim against itself.
_EXTENSION_LIKE_RE = re.compile(r"^[a-z0-9]{1,4}$")

# Boundaries that start a new attribution scope for the "bare symbol + file
# path in the same sentence" grammar form: a sentence terminator, a blank
# line, or a markdown list-item marker (BUG-3057 precedent in prose_deps.py's
# _SCOPE_BOUNDARY_RE) -- without the list-item boundary, an unrelated symbol
# in one bullet pairs with an unrelated file path in a neighboring bullet
# whenever a "### Files to Modify" block has no blank lines between items.
# Nearest-mention cap for the "bare symbol + file path in the same sentence"
# form (characters). A long sentence naming several files ("existing call
# sites in `a.py`, `b.py`, and `c.py`") should not attribute a symbol to
# whichever file happens to appear anywhere in it -- only a close-by mention
# plausibly means "defined in".
_MAX_ATTRIBUTION_DISTANCE = 80

_SENTENCE_BOUNDARY_RE = re.compile(
    r"[.!?][\s)\"']"
    r"|\n\s*\n"
    r"|^[ \t]*(?:[-*+]|\d+\.)\s",
    re.MULTILINE,
)

# <!-- ll-prose-ok: ... --> suppression convention (cli/verify_skill_prose.py
# _SUPPRESS_RE) — a match on the line immediately preceding a claim
# suppresses it.
_SUPPRESS_RE = re.compile(r"<!--\s*ll-prose-ok:\s*(.+?)\s*-->")


@dataclass(frozen=True)
class SymbolClaim:
    """One attributed symbol claim extracted from an issue body."""

    symbol: str
    file: str  # resolved, tracked repo-relative path
    raw: str  # original backticked text, for gap-message reporting


def _in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool:
    return any(fs <= start and end <= fe for fs, fe in fence_spans)


def _is_suppressed(body: str, match_start: int) -> bool:
    line_start = body.rfind("\n", 0, match_start) + 1
    if line_start == 0:
        return False
    prev_newline_pos = line_start - 1
    prev_line_start = body.rfind("\n", 0, prev_newline_pos) + 1
    preceding = body[prev_line_start:prev_newline_pos]
    return bool(_SUPPRESS_RE.search(preceding))


def _sentence_span(body: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(body, 0, pos):
        start = m.end()
    end_match = _SENTENCE_BOUNDARY_RE.search(body, pos)
    end = end_match.end() if end_match else len(body)
    return start, end


def _resolve_module_prefix(module: str, ref_index: RefIndex) -> str | None:
    """Resolve a bare dotted-prefix module token (no ``/``) to a tracked file."""
    candidates = ref_index.by_basename.get(f"{module}.py", [])
    return candidates[0] if len(candidates) == 1 else None


def extract_symbol_claims(body: str, ref_index: RefIndex) -> set[SymbolClaim]:
    """Extract attributed symbol claims from an issue body (§ Claim Grammar).

    Args:
        body: Issue markdown body (frontmatter stripped or not — frontmatter
            carries no backticked symbol claims in practice).
        ref_index: A :class:`~little_loops.text_utils.RefIndex` built once
            per invocation, used to resolve a cited file path/module prefix
            to a tracked repo-relative path.

    Returns:
        A set of :class:`SymbolClaim`. Empty when *body* or *ref_index* is
        falsy/empty, or when no backticked span matches one of the three
        pinned grammar forms.
    """
    if not body or ref_index is None:
        return set()

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]
    claims: set[SymbolClaim] = set()

    for m in _BACKTICK_SPAN_RE.finditer(body):
        if _in_fence(m.start(), m.end(), fence_spans):
            continue
        if _is_suppressed(body, m.start()):
            continue
        text = m.group(1)

        explicit = _EXPLICIT_RE.match(text)
        if explicit:
            file_ref, symbol = explicit.group(1), explicit.group(2)
            resolved = resolve_ref_path(file_ref, ref_index)
            if resolved:
                claims.add(SymbolClaim(symbol=symbol, file=resolved, raw=text))
            continue

        dotted = _DOTTED_RE.match(text)
        if dotted:
            module_prefix, symbol = dotted.group(1), dotted.group(2)
            if _EXTENSION_LIKE_RE.match(symbol):
                continue
            resolved = _resolve_module_prefix(module_prefix, ref_index)
            if resolved:
                claims.add(SymbolClaim(symbol=symbol, file=resolved, raw=text))
            continue

        bare = _BARE_SYMBOL_RE.match(text)
        if bare and not _LINE_NUMBER_REF_RE.match(text):
            symbol = bare.group(1)
            sent_start, sent_end = _sentence_span(body, m.start())
            sentence = body[sent_start:sent_end]
            rel_pos = m.start() - sent_start
            best: tuple[int, str] | None = None
            for path_m in _BACKTICK_SPAN_RE.finditer(sentence):
                candidate = path_m.group(1)
                if candidate == text or "/" not in candidate:
                    continue
                if not _FILE_PATH_BACKTICK_RE.match(candidate):
                    continue
                distance = min(abs(path_m.start() - rel_pos), abs(path_m.end() - rel_pos))
                if distance > _MAX_ATTRIBUTION_DISTANCE:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, candidate)
            if best is not None:
                resolved = resolve_ref_path(best[1], ref_index)
                if resolved:
                    claims.add(SymbolClaim(symbol=symbol, file=resolved, raw=text))

    return claims


def _extract_symbols(path: Path) -> set[str] | None:
    """Return every def-site symbol name found in *path*, or None if unreadable."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    found: set[str] = set()
    for line in lines:
        matched = False
        for pattern in _SYMBOL_DEF_PATTERNS:
            dm = pattern.match(line)
            if dm:
                found.add(dm.group(1))
                matched = True
                break
        if matched:
            continue
        cm = _MODULE_CONSTANT_RE.match(line)
        if cm:
            found.add(cm.group(1))
    return found


@dataclass
class SymbolIndex:
    """Lazily-populated per-file symbol cache, threaded through ``check_format_gaps``.

    Built once per ``format-check`` invocation via :func:`build_symbol_index`
    (cheap — just records *root*); each cited file's symbol set is parsed at
    most once across the whole invocation, mirroring
    :class:`~little_loops.text_utils.RefIndex`'s build-once-thread-everywhere
    shape without re-reading a file already resolved for an earlier issue.
    """

    root: Path
    _cache: dict[str, set[str] | None] = field(default_factory=dict)

    def symbols_in(self, rel_path: str) -> set[str] | None:
        if rel_path not in self._cache:
            self._cache[rel_path] = _extract_symbols(self.root / rel_path)
        return self._cache[rel_path]


def build_symbol_index(root: Path) -> SymbolIndex:
    """Build (empty, lazily-populated) per-file symbol cache rooted at *root*."""
    return SymbolIndex(root=root)


def symbol_exists_in_file(index: SymbolIndex, file: str, symbol: str) -> bool | None:
    """Does *symbol* resolve as a def-site or module-level constant in *file*?

    Args:
        index: A :class:`SymbolIndex` built once per invocation.
        file: Tracked repo-relative path (as resolved by
            :func:`extract_symbol_claims`).
        symbol: The claimed symbol name.

    Returns:
        True/False, or ``None`` when *file*'s extension is outside
        :data:`_SUPPORTED_SYMBOL_EXTENSIONS` or the file cannot be read —
        both fail open (no claim, no gap), never a false positive.
    """
    if Path(file).suffix not in _SUPPORTED_SYMBOL_EXTENSIONS:
        return None
    symbols = index.symbols_in(file)
    if symbols is None:
        return None
    return symbol in symbols
