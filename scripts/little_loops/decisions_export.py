"""Export active required rules to review-tool-specific rule files (FEAT-3485).

Target-keyed exporter seam: ``export_rules()`` dispatches to a private
``_export_<target>`` function via ``_EXPORTERS``. The only target today is
"ocr" (open-code-review, https://github.com/alibaba/open-code-review). This
module never imports ``little_loops.config`` — scope resolution is a CLI
concern (``cli/issues/decisions.py::_cmd_export``); every function here is
pure with respect to config, cwd, and stderr.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from little_loops.decisions import RuleEntry
from little_loops.file_utils import atomic_write_json

_WILDCARD_CHARS = set("*?[{")


def _literal_prefix(glob: str) -> str:
    """Return the portion of *glob* before its first wildcard character."""
    for i, ch in enumerate(glob):
        if ch in _WILDCARD_CHARS:
            return glob[:i]
    return glob


def _glob_sort_key(glob: str) -> tuple[int, int, str]:
    """Specificity sort key: longest literal prefix first, fewest bare-wildcard
    segments next, lexical order breaks remaining ties.

    A "bare-wildcard segment" is a ``/``-separated segment that is *exactly*
    ``*`` or ``**`` — not any segment containing a wildcard character. This is
    what makes ``scripts/**/*.py`` (one such segment) sort before
    ``scripts/**/*`` (two).
    """
    prefix = _literal_prefix(glob)
    wildcard_segments = sum(1 for seg in glob.split("/") if seg in ("*", "**"))
    return (-len(prefix), wildcard_segments, glob)


def _dir_prefix(glob: str) -> str | None:
    """Return the covered directory prefix for a directory glob, else None.

    A directory glob has the shape ``<prefix>/**/*`` (prefix may be empty, the
    bare ``**/*`` case). Returns ``<prefix>/`` (or ``""`` for the bare case);
    returns ``None`` for any other glob shape (e.g. ``scripts/**/*.py``).
    """
    if glob == "**/*":
        return ""
    if glob.endswith("/**/*"):
        return glob[: -len("**/*")]
    return None


def _render_body(rules: list[RuleEntry], prefix_note: str = "") -> str:
    bullets = "\n".join(f"- {r.rule} (decision {r.id})" for r in rules)
    return f"{prefix_note}{bullets}" if prefix_note else bullets


_SYSTEM_RULES_NOTE = (
    "Note: this replaces OCR's embedded system rules for matched files; "
    "language conventions still apply and are not restated here.\n"
)


def _export_ocr(
    rules: list[RuleEntry],
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,
) -> Path:
    """Write ``.opencodereview/rule.json``. The only OCR-specific function. Pure."""
    scope_globs = scope_globs if scope_globs is not None else ["**/*"]

    repo_wide = [r for r in rules if not r.paths]

    scoped_globs: dict[str, list[RuleEntry]] = {}
    for r in rules:
        for glob in r.paths:
            scoped_globs.setdefault(glob, []).append(r)

    catch_all_rules: dict[str, list[RuleEntry]] = {g: list(repo_wide) for g in scope_globs}

    scoped_entries: list[tuple[str, list[RuleEntry]]] = []
    for glob, own_rules in scoped_globs.items():
        if glob in catch_all_rules:
            # Merges into the matching catch-all rather than a separate entry.
            for r in own_rules:
                if r not in catch_all_rules[glob]:
                    catch_all_rules[glob].append(r)
            continue

        prefix = _literal_prefix(glob)
        body_rules = list(own_rules)
        for other_glob, other_rules in scoped_globs.items():
            if other_glob == glob:
                continue
            dir_prefix = _dir_prefix(other_glob)
            if dir_prefix is not None and prefix.startswith(dir_prefix):
                for r in other_rules:
                    if r not in body_rules:
                        body_rules.append(r)
        for r in repo_wide:
            if r not in body_rules:
                body_rules.append(r)

        scoped_entries.append((glob, body_rules))

    scoped_entries.sort(key=lambda t: _glob_sort_key(t[0]))

    entries = [{"path": glob, "rule": _render_body(body)} for glob, body in scoped_entries]
    for glob in scope_globs:
        if not catch_all_rules[glob]:
            continue
        entries.append(
            {"path": glob, "rule": _render_body(catch_all_rules[glob], _SYSTEM_RULES_NOTE)}
        )

    payload = {"rules": entries}
    output_path = output_dir / ".opencodereview" / "rule.json"
    atomic_write_json(output_path, payload)
    return output_path


_EXPORTERS: dict[str, Callable[..., Path]] = {"ocr": _export_ocr}


def export_rules(
    rules: list[RuleEntry],
    target: str,
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,
) -> Path:
    """Dispatch to the exporter registered for *target*.

    Raises ``ValueError`` naming the valid targets if *target* is unknown.
    """
    exporter = _EXPORTERS.get(target)
    if exporter is None:
        raise ValueError(f"Unknown export target {target!r}; choose from {sorted(_EXPORTERS)}")
    return exporter(rules, output_dir, scope_globs=scope_globs)
