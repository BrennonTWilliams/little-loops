"""ll-verify-decisions: load+schema validator for ``.ll/decisions.yaml`` (ENH-2589).

Wraps :func:`little_loops.decisions.load_decisions` and fails non-zero on any
``yaml.YAMLError``, ``KeyError``, or ``ValueError`` raised during load. Three
corruption classes are gated:

1. **YAML syntax corruption** (OTHE-203 pattern, e.g.
   ``rationale: "abc "" def"`` → unterminated quote) — ``yaml.YAMLError``.
2. **Schema drift** — entries missing required fields (``id``,
   ``result``/``measured_at`` for outcomes, etc.) — ``KeyError``.
3. **Unknown ``type`` discriminator** — ``ValueError("Unknown entry type")``
   from :func:`_entry_from_dict`.

Exit codes match the ``ll-verify-*`` family:

* ``0`` — loadable and schema-clean
* ``1`` — any caught exception, with a single-line ``ERROR:`` message on stderr
  pointing at the file path

The three transport-layer integrations (pre-commit ENH-2590, pytest CI gate
ENH-2591, Claude Code PreToolUse ENH-2592) each wire this binary into their
own subsystem and rely on its exit-code contract.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_DEFAULT_LOG_PATH = Path(".ll") / "decisions.yaml"


def _resolve_log_path(config_root: Path | None) -> Path:
    """Resolve the ``decisions.yaml`` path under *config_root*.

    Mirrors :func:`little_loops.decisions._resolve_path`: when *config_root* is
    ``None`` the default falls back to ``Path.cwd() / .ll/decisions.yaml``.
    """
    if config_root is None:
        return Path.cwd() / _DEFAULT_LOG_PATH
    return config_root / _DEFAULT_LOG_PATH


def _run(log_path: Path) -> tuple[int, str | None]:
    """Validate *log_path*. Returns ``(exit_code, error_message)``.

    Exit code ``0`` is paired with ``None`` (no error). Exit code ``1`` is paired
    with a single-line error message pointing at the file path (caller emits it
    to stderr).
    """
    from little_loops.decisions import load_decisions

    try:
        load_decisions(log_path)
    except (yaml.YAMLError, KeyError, ValueError) as exc:
        return 1, f"ERROR: {log_path}: {type(exc).__name__}: {exc}"
    return 0, None


def main_verify_decisions() -> int:
    """Entry point for ``ll-verify-decisions``.

    Returns 0 when ``.ll/decisions.yaml`` is loadable via
    :func:`load_decisions` and contains no schema drift; returns 1 on any
    caught ``yaml.YAMLError``, ``KeyError``, or ``ValueError``.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-decisions", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-decisions",
            description=(
                "Validate .ll/decisions.yaml by loading it through "
                "load_decisions() and asserting no YAML syntax errors, missing "
                "required fields, or unknown entry-type discriminators. "
                "Exits 0 on a clean file, 1 on any caught corruption (ENH-2589)."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                                # Validate .ll/decisions.yaml from cwd
  %(prog)s --config-root /path/to/repo    # Validate under a specific repo root

Exit codes:
  0 - File loadable via load_decisions(), no schema drift
  1 - YAML parse error, missing required field, or unknown entry type
""",
        )
        parser.add_argument(
            "--config-root",
            type=Path,
            default=None,
            help=(
                "Project root whose .ll/decisions.yaml to validate "
                "(default: cwd). Equivalent to the BRConfig.project_root "
                "field used by sync_to_local_md and related consumers."
            ),
        )

        args = parser.parse_args()
        log_path = _resolve_log_path(args.config_root)
        exit_code, error_message = _run(log_path)
        if error_message is not None:
            print(error_message, file=sys.stderr)
        return exit_code
