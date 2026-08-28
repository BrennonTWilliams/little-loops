"""Static sweep classifying `${context.*}` / `${captured.*}` / `${prev.*}`
interpolation sites found inside embedded Python bodies (heredocs and
`python3 -c` strings) within loop-YAML shell actions.

A quoted heredoc or `-c` string protects a substituted value from *bash*
expansion, but once the interpolated text lands inside a Python source
string, an unescaped quote/backslash in the value is a Python syntax break
or injection, not a bash one. MR-11 (`shell_safety.py`) treats a quoted
heredoc as unconditionally safe, which is the inversion this sweep exists
to catch (ENH-3338).

`classify_site()` is the single source of truth for the A/B/C classification
rule; ENH-3342 imports it to widen MR-11 without duplicating the rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.interpolation import InterpolationError, parse_interpolation_suffixes

# Mirrors interpolation.py's VARIABLE_PATTERN: a single ${...} token, no nested braces.
_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

# Heredoc opener: `<<'EOF'`, `<<-"EOF"`, or the unquoted `<<EOF` form. Recognized
# anywhere on a line (the opener is a mid-line redirection, never a comment or a
# lone statement). The terminator is matched separately, at column 0 only — except
# a `<<-` opener, which relaxes column-0 to allow leading *tabs* only (bash
# semantics; not spaces). Lookbehind/lookahead exclude a `<<<` here-string
# (`done <<< "$VAR"`, fence.py's `<<<BRIEF` prose markers) from matching as a
# heredoc opener.
_HEREDOC_OPEN_RE = re.compile(r"(?<!<)<<(?!<)(-)?\s*(?:['\"](\w+)['\"]|(\w+))")

# A heredoc's body is a Python body only when the command that reads its stdin
# is `python3` — a `cat > file << 'MARKER'` (or `cat <<'EOF' | tail`) heredoc is
# a data sink: its content is written to disk (or piped to a display command),
# never passed to the Python parser, so a captured value inside it is safe
# regardless of shell metacharacters (BUG-2468's fix; see AC 11).
_PYTHON3_WORD_RE = re.compile(r"\bpython3\b")

# Entry into a `python3 -c "..."` / `python3 -c '...'` body. Group 1 is the
# opening quote character, which is also the character that closes the body.
_C_FLAG_RE = re.compile(r"python3\s+-c\s+(['\"])")

# Trusted, runner-constructed `context.*` keys (never operator/LLM-authored prose).
# An underscore-prefixed key is bookkeeping (e.g. `_tamper_guard`) and is also trusted.
TRUSTED_CONTEXT_KEYS = frozenset({"run_dir", "promoted_artifact"})

# prev.* fields that carry the previous state's LLM/command output text, vs. the
# runner-constructed metadata fields (exit_code, state, timeout_kind).
_UNTRUSTED_PREV_KEYS = frozenset({"output", "stderr"})


def classify_site(namespace: str, key: str) -> str:
    """Classify one interpolation token by namespace and first path segment.

    Returns ``"A"`` (untrusted context key), ``"B"`` (always-untrusted capture/
    prev-output, or any namespace without an explicit trust verdict), or
    ``"C"`` (trusted/runner-owned; recorded but not gating). ``namespace ==
    "loop"`` is never asked about here — callers skip it before reaching this
    function, since it's runner-constructed and not reported at all.
    """
    if namespace == "captured":
        return "B"
    if namespace == "prev":
        return "B" if key in _UNTRUSTED_PREV_KEYS else "C"
    if namespace == "context":
        if key in TRUSTED_CONTEXT_KEYS or key.startswith("_"):
            return "C"
        return "A"
    # result / state / env / messages / param / any future namespace: no
    # namespace besides the ones above has an explicit trust verdict, so the
    # safe-direction default applies here too (decided 2026-08-28) — the same
    # inversion this sweep applies to unknown `context` keys. No such site
    # exists inside a Python body in the corpus today; this costs nothing
    # until one is introduced, at which point it fails safe rather than open.
    return "B"


@dataclass(frozen=True)
class InterpSite:
    """One classified interpolation site inside a Python body.

    Equality/hash are restricted to the four anchor fields (`file`, `state`,
    `var`, `cls`) so a baseline can be diffed by set equality without churning
    on line-number drift. `host_shape`, `misapplied_remedy`, `line`, and
    `count` are informational only — printed in failure messages, excluded
    from comparison.
    """

    file: str
    state: str
    var: str
    cls: str
    host_shape: str = field(compare=False)
    misapplied_remedy: bool = field(compare=False)
    line: int = field(compare=False)
    count: int = field(compare=False, default=1)


def _merge_counts(sites: list[InterpSite]) -> list[InterpSite]:
    """Collapse duplicate (file, state, var, cls) sites, summing `count`."""
    merged: dict[tuple[str, str, str, str], InterpSite] = {}
    for site in sites:
        key = (site.file, site.state, site.var, site.cls)
        existing = merged.get(key)
        if existing is None:
            merged[key] = site
        else:
            merged[key] = InterpSite(
                file=existing.file,
                state=existing.state,
                var=existing.var,
                cls=existing.cls,
                host_shape=existing.host_shape,
                misapplied_remedy=existing.misapplied_remedy,
                line=existing.line,
                count=existing.count + site.count,
            )
    return list(merged.values())


def scan_action(action: str, *, state: str, file: str) -> list[InterpSite]:
    """Scan one action string, returning one `InterpSite` per interpolation
    token found inside an embedded Python body (heredoc or `-c` string).

    Tokens outside any Python body (plain bash position, including a `:shell`
    binding on a `python3` invocation line) are not reported here — that
    position is MR-11's territory (ENH-3342), not this baseline's.
    """
    if not action:
        return []

    sites: list[InterpSite] = []
    heredoc_marker: str | None = None
    heredoc_indented = False
    heredoc_is_python = False
    c_quote: str | None = None

    for lineno, line in enumerate(action.splitlines(), start=1):
        in_body_ranges: list[tuple[int, int]] = []
        host_shape = ""

        if heredoc_marker is not None:
            terminator_line = line.lstrip("\t") if heredoc_indented else line
            if terminator_line == heredoc_marker:
                heredoc_marker = None
                continue
            if heredoc_is_python:
                in_body_ranges.append((0, len(line)))
                host_shape = "heredoc"
        else:
            heredoc_match = _HEREDOC_OPEN_RE.search(line)
            if heredoc_match:
                heredoc_indented = heredoc_match.group(1) is not None
                heredoc_marker = heredoc_match.group(2) or heredoc_match.group(3)
                heredoc_is_python = bool(_PYTHON3_WORD_RE.search(line, 0, heredoc_match.start()))
                # The opener line itself is the bash redirection line, not the body.

        if heredoc_marker is None or host_shape != "heredoc":
            # Track `-c "..."` / `-c '...'` independently of heredoc state.
            pos = 0
            if c_quote is not None:
                close = line.find(c_quote)
                if close == -1:
                    in_body_ranges.append((0, len(line)))
                    host_shape = host_shape or "c-string"
                    pos = len(line)
                else:
                    in_body_ranges.append((0, close))
                    host_shape = host_shape or "c-string"
                    c_quote = None
                    pos = close + 1
            if c_quote is None:
                c_match = _C_FLAG_RE.search(line, pos)
                if c_match:
                    c_quote = c_match.group(1)
                    body_start = c_match.end()
                    close = line.find(c_quote, body_start)
                    if close == -1:
                        in_body_ranges.append((body_start, len(line)))
                        host_shape = host_shape or "c-string"
                    else:
                        in_body_ranges.append((body_start, close))
                        host_shape = host_shape or "c-string"
                        c_quote = None

        if not in_body_ranges:
            continue

        for match in _TOKEN_RE.finditer(line):
            start = match.start()
            if not any(lo <= start < hi for lo, hi in in_body_ranges):
                continue

            full_path = match.group(1)
            try:
                var_path, _default, _nullable, shell_quote = parse_interpolation_suffixes(full_path)
            except InterpolationError:
                continue

            if "." not in var_path:
                continue
            namespace, key_path = var_path.split(".", 1)
            if namespace == "loop":
                continue
            key = key_path.split(".", 1)[0]
            cls = classify_site(namespace, key)

            sites.append(
                InterpSite(
                    file=file,
                    state=state,
                    var=f"{namespace}.{key_path}",
                    cls=cls,
                    host_shape=host_shape,
                    misapplied_remedy=shell_quote,
                    line=lineno,
                    count=1,
                )
            )

    return _merge_counts(sites)


def _iter_shell_entries(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Yield (name, entry) for every dict entry under `states:` and `fragments:`."""
    entries: list[tuple[str, dict[str, Any]]] = []
    for scope_key in ("states", "fragments"):
        scope = data.get(scope_key)
        if not isinstance(scope, dict):
            continue
        for name, entry in scope.items():
            if isinstance(entry, dict):
                entries.append((name, entry))
    return entries


def scan_corpus(root: Path) -> list[InterpSite]:
    """Scan every loop YAML under `root` (recursively), walking both `states:`
    and `fragments:` top-level keys, and return all classified sites sorted
    deterministically.
    """
    sites: list[InterpSite] = []
    for path in sorted(root.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            continue

        file_label = f"loops/{path.relative_to(root)}"
        for name, entry in _iter_shell_entries(data):
            action_type = entry.get("action_type")
            if action_type not in ("shell", None):
                continue
            action = entry.get("action")
            if not action or (isinstance(action, str) and action.lstrip().startswith("/")):
                continue
            sites.extend(scan_action(action, state=name, file=file_label))

    return sorted(sites, key=lambda s: (s.file, s.state, s.var, s.cls))
