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
import subprocess
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
# BUG-3063 D1: leading whitespace is allowed so indented class attributes and
# dataclass fields ("    stale_file_ref: list[str] = field(...)") enter the
# index too, not just module-level constants. This also admits indented
# local-variable assignments inside function bodies -- an accepted precision
# trade (§ Survivor Analysis D1), not a regression, since a local variable
# claimed as a symbol was never distinguishable from a real attribute by name
# alone.
_MODULE_CONSTANT_RE = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)")

# BUG-3201 A: SQL object names declared inside triple-quoted migration strings
# (session_store/schema.py's _MIGRATIONS, queue_store.py) are real, citable
# symbols of the .py file that carries them -- 40 table and 64 index names
# repo-wide -- but no def-site pattern above can see them, so "`tool_events` in
# `session_store/schema.py`" read as a false stale_symbol_ref. Same shape as
# the precedent regex in cli/verify_kinds.py, widened past TABLE to INDEX/VIEW
# and to the UNIQUE / VIRTUAL / TEMPORARY modifiers.
#
# Deliberately *not* paired with adding ".sql" to _SUPPORTED_SYMBOL_EXTENSIONS:
# a .sql file must keep failing open (None), not start answering False for
# every column, trigger and constraint name these patterns cannot see.
# Ungated by language -- CREATE TABLE means the same thing in a Go heredoc, and
# no _ANCHOR_PATTERNS entry can match a line beginning with CREATE.
_SQL_CREATE_PREFIX_RE = re.compile(r"^[ \t]*CREATE\b", re.IGNORECASE)
_SQL_OBJECT_DEF_RE = re.compile(
    r"^[ \t]*CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:(?:UNIQUE|VIRTUAL|TEMP(?:ORARY)?)\s+)*"
    r"(?:TABLE|INDEX|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# BUG-3201 B: a name bound by an import statement resolves in the importing
# module exactly as a def-site does -- after "from little_loops.skill_expander
# import _find_plugin_root as _fpr" (cli/adapt.py), `adapt._fpr` is a real
# attribute -- so an issue citing `_fpr` in `cli/adapt.py` makes a true claim.
# 10,684 such bindings across 782 tracked .py files (129 `as`-aliased) were
# invisible to the index, turning every one into a false stale_symbol_ref
# (aliased, since the alias is defined nowhere) or mislocated_symbol_ref
# (plain `from m import x`, which the reverse index then found at m).
#
# Line-based, not ast.parse: ast.parse over every tracked .py file measured
# 2.25s, roughly an order of magnitude more than this regex plus a
# paren-continuation counter at 0.22s, against a whole-index build under a
# second. Recall is 10,678/10,684 -- the 6 misses were import lines whose
# *trailing comment* carried a ")" that closed the continuation early, hence
# _TRAILING_COMMENT_RE is applied before every paren count, never after.
#
# Python-only by design (see _extract_symbols' suffix gate): "import
# java.util.List;" would index `java` into every Java file, Go's "import ("
# block would open a continuation with nothing findable inside, and TS/JS place
# the names before `from`, inverted from Python.
_IMPORT_LINE_RE = re.compile(r"^[ \t]*(?:from\s+[.\w]+\s+)?import\s+(.*)$")
# One comma-separated clause: "x", "a.b.c", "x as y". The dotted form only
# occurs in plain `import a.b.c`, where the *first* component is what gets
# bound, so splitting on "." is correct for both forms.
_IMPORT_BINDING_RE = re.compile(r"^\(?\s*([A-Za-z_][\w.]*)(?:\s+as\s+([A-Za-z_]\w*))?")
_TRAILING_COMMENT_RE = re.compile(r"#.*$")

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


def _import_bindings(clause: str) -> set[str]:
    """Names bound by one comment-stripped import clause or continuation line."""
    names: set[str] = set()
    for piece in clause.split(","):
        bm = _IMPORT_BINDING_RE.match(piece.strip())
        if not bm:
            continue
        names.add(bm.group(2) or bm.group(1).split(".", 1)[0])
    return names


def _extract_symbols(path: Path, *, include_imports: bool = True) -> set[str] | None:
    """Return every symbol name that resolves in *path*, or None if unreadable.

    Def-sites, module-level constants, SQL objects declared in embedded
    migration strings (BUG-3201 A), and — for ``.py`` files when
    *include_imports* — every name bound by an import statement (BUG-3201 B).

    *include_imports* is False for :func:`_build_reverse_index` only. An
    imported name answers "does this resolve here" (the per-file index) but
    must never answer "is it defined somewhere else" (the reverse index), or
    ``json`` / ``Path`` / ``re`` would each map to hundreds of files and
    downgrade every genuinely stale claim naming a common token into a
    ``mislocated_symbol_ref`` whose printed rationale ("symbol exists elsewhere
    in the repo") would be false.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    scan_imports = include_imports and path.suffix == ".py"
    found: set[str] = set()
    # Depth is consulted before _SYMBOL_DEF_PATTERNS so a continuation line
    # inside "from x import (\n    field,\n)" is read as the binding it is,
    # never mistaken for a def-site. max(0, ...) clamps the recovery path: a
    # stray ")" must not drive the counter negative and permanently disable
    # continuation handling for the rest of the file.
    import_paren_depth = 0
    for line in lines:
        if import_paren_depth > 0:
            code = _TRAILING_COMMENT_RE.sub("", line)
            found |= _import_bindings(code)
            import_paren_depth = max(0, import_paren_depth + code.count("(") - code.count(")"))
            continue
        matched = False
        for pattern in _SYMBOL_DEF_PATTERNS:
            dm = pattern.match(line)
            if dm:
                found.add(dm.group(1))
                matched = True
                break
        if matched:
            continue
        # Cheap prefix guard before the case-insensitive, alternation-heavy SQL
        # regex: the latter is anchored at ^[ \t]*CREATE, so a line whose first
        # non-blank token is not "CREATE" can never match it. This runs on
        # every line of every tracked file in the reverse-index build, and
        # essentially all of them fail the guard.
        if _SQL_CREATE_PREFIX_RE.match(line):
            sm = _SQL_OBJECT_DEF_RE.match(line)
            if sm:
                found.add(sm.group(1))
                continue
        if scan_imports:
            im = _IMPORT_LINE_RE.match(line)
            if im:
                code = _TRAILING_COMMENT_RE.sub("", im.group(1))
                found |= _import_bindings(code)
                import_paren_depth = max(0, code.count("(") - code.count(")"))
                continue
        cm = _MODULE_CONSTANT_RE.match(line)
        if cm:
            found.add(cm.group(1))
    return found


def _build_reverse_index(root: Path) -> dict[str, frozenset[str]]:
    """Map every def-site symbol name to the tracked files that define it (BUG-3063 C).

    One ``git ls-files`` call plus one read per file in
    :data:`_SUPPORTED_SYMBOL_EXTENSIONS` — the same language set the
    per-file resolver uses, not just ``*.py`` (§ Proposed Solution: "Index
    the same language set the resolver does"). Follows the fail-*empty*
    convention shared with :func:`~little_loops.text_utils.build_ref_index`:
    an unavailable git binary or non-zero exit yields an empty index rather
    than raising.

    Import-bound names are excluded here (``include_imports=False``) while the
    per-file cache keeps them — see :func:`_extract_symbols` and
    :func:`symbol_resolves_elsewhere`. Including them would map ``json`` /
    ``Path`` / ``re`` to hundreds of files apiece and misreport every stale
    claim naming a common token as a mis-attribution. SQL object names *are*
    indexed here: they are repo-unique, so a table name claimed against the
    wrong file correctly resolves to the schema that declares it.
    """
    reverse: dict[str, set[str]] = {}
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}

    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    for name in names:
        if not name or Path(name).suffix not in _SUPPORTED_SYMBOL_EXTENSIONS:
            continue
        symbols = _extract_symbols(root / name, include_imports=False)
        if not symbols:
            continue
        for symbol in symbols:
            reverse.setdefault(symbol, set()).add(name)
    return {symbol: frozenset(files) for symbol, files in reverse.items()}


@dataclass
class SymbolIndex:
    """Lazily-populated per-file symbol cache, threaded through ``check_format_gaps``.

    Built once per ``format-check`` invocation via :func:`build_symbol_index`.
    Each cited file's symbol set is parsed at most once across the whole
    invocation, mirroring :class:`~little_loops.text_utils.RefIndex`'s
    build-once-thread-everywhere shape without re-reading a file already
    resolved for an earlier issue.

    :attr:`_reverse` (BUG-3063 C) is the one eager, non-lazy piece: the
    repo-wide symbol -> files map is built once in :func:`build_symbol_index`
    itself, not on first query, so ``check_format_gaps`` (which only ever
    looks up an already-built index) never shells out — see
    ``test_check_format_gaps_spawns_no_subprocess``.
    """

    root: Path
    _cache: dict[str, set[str] | None] = field(default_factory=dict)
    _reverse: dict[str, frozenset[str]] = field(default_factory=dict)

    def symbols_in(self, rel_path: str) -> set[str] | None:
        if rel_path not in self._cache:
            self._cache[rel_path] = _extract_symbols(self.root / rel_path)
        return self._cache[rel_path]

    def files_with_symbol(self, symbol: str) -> frozenset[str]:
        return self._reverse.get(symbol, frozenset())


def build_symbol_index(root: Path) -> SymbolIndex:
    """Build a per-file symbol cache rooted at *root*, plus the C reverse index.

    The per-file cache stays lazy; the symbol -> files reverse index (C) is
    built eagerly here, once per invocation — measured at 739 tracked Python
    files / 25,388 def-sites / 0.89s on this repo (BUG-3063 § Decision
    Rationale; the file and symbol counts have grown with the repo since).

    BUG-3201 added SQL object names to what that build indexes and kept
    import bindings out of it — see :func:`_build_reverse_index`.
    """
    return SymbolIndex(root=root, _reverse=_build_reverse_index(root))


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


def symbol_resolves_elsewhere(index: SymbolIndex, file: str, symbol: str) -> bool:
    """Does *symbol* resolve as a def-site in some tracked file other than *file* (BUG-3063 C)?

    Only meaningful once :func:`symbol_exists_in_file` has already returned
    ``False`` for the same (*file*, *symbol*) pair — this does not re-check
    *file* itself, only whether the claim is a mis-attribution rather than
    a genuinely stale one.
    """
    return bool(index.files_with_symbol(symbol) - {file})
