"""Anchor resolver for file:line references — ENH-1300.

Resolves a file:line reference to its enclosing function, class, or section
using a language-agnostic backwards regex scan (no AST). Covers Python,
TypeScript, JavaScript, Go, Rust, Ruby, Java, C#, and Markdown.
"""

from __future__ import annotations

import re
from pathlib import Path

# Each entry: (compiled pattern, kind)
# kind is "function", "class", or "section"
_ANCHOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Python / Ruby — def and async def
    (re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\("), "function"),
    # JS / TS — function declaration or named function expression
    (
        re.compile(r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*\("),
        "function",
    ),
    # JS / TS — const/let/var arrow or assigned function
    (
        re.compile(
            r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function\b)"
        ),
        "function",
    ),
    # Go — top-level func and methods (optional receiver before name)
    (re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*[(\[]"), "function"),
    # Rust — fn (optionally pub, async, unsafe)
    (
        re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*[<(]"),
        "function",
    ),
    # Java / C# heuristic — access-modifier(s) + return-type + name(
    (
        re.compile(
            r"^[ \t]*(?:(?:public|private|protected|static|final|override|virtual|abstract|async|synchronized)\s+)"
            r"{1,4}\w[\w<>\[\]?*]*\s+(\w+)\s*\("
        ),
        "function",
    ),
    # Universal — class / struct / interface / trait / impl / enum
    (
        re.compile(
            r"^[ \t]*"
            r"(?:(?:pub(?:\([^)]*\))?\s+|(?:public|private|protected|abstract|final|sealed|static|export|default)\s+))*"
            r"(?:class|struct|interface|trait|impl|enum)\s+(\w+)"
        ),
        "class",
    ),
    # Markdown heading (any level, strip trailing hashes)
    (re.compile(r"^#{1,6}\s+(.+?)(?:\s+#+)?$"), "section"),
]


def resolve_anchor(file_path: str, line_number: int) -> str | None:
    """Return the enclosing function, class, or section for the given file:line.

    Scans backwards from line_number to find the nearest enclosing definition
    using language-agnostic regexes. Works for .py, .ts, .js, .go, .rs, .rb,
    .java, .cs, .md and any language with recognizable definition syntax.

    Args:
        file_path: Path to the source file (relative or absolute).
        line_number: 1-based line number within the file.

    Returns:
        A human-readable anchor string such as:
          "near function foo"
          "near class Bar"
          'under section "Title"'
        or None if the file cannot be read or no anchor can be resolved.
    """
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    scan_end = min(line_number, len(lines))
    for i in range(scan_end - 1, -1, -1):
        for pattern, kind in _ANCHOR_PATTERNS:
            m = pattern.match(lines[i])
            if m:
                name = m.group(1).strip()
                if kind == "section":
                    return f'under section "{name}"'
                return f"near {kind} {name}"
    return None
