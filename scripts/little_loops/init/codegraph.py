"""Code-graph tool detection, install and indexing for ll-init.

little-loops' structural code queries (``ll-code``, and the graph-seeded
discovery phases in ``/ll:refine-issue`` / ``/ll:wire-issue`` /
``/ll:verify-issues``) are served by the ``codegraph`` provider when a
``.codegraph/codegraph.db`` index exists, and by a grep/AST fallback
otherwise. The index is built by the external ``@colbymchenry/codegraph``
npm package (binary ``codegraph``; ``codegraph init <path>`` builds it,
``codegraph sync`` refreshes it).

This module gives ``ll-init`` one place to:

* detect whether the binary / index / npm toolchain are present;
* decide what to do for a given ``--code-graph`` mode (never install
  without an explicit ask);
* run the install / index commands with timeouts, reporting failures as
  warnings plus the exact manual commands — the init exit code is never
  affected by the code-graph step.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CODEGRAPH_PACKAGE = "@colbymchenry/codegraph"
CODEGRAPH_BINARY = "codegraph"
INSTALL_TIMEOUT = 300
INDEX_TIMEOUT = 600
_VERSION_TIMEOUT = 10

CodeGraphMode = Literal["auto", "install", "index", "commands", "skip"]
CODE_GRAPH_MODES: tuple[str, ...] = ("auto", "install", "index", "commands", "skip")

Action = Literal["ready", "index", "install", "commands", "skip"]


@dataclass(frozen=True)
class CodegraphStatus:
    """What the machine and project currently have."""

    binary: str | None
    index_present: bool
    db_path: Path
    node: str | None
    npm: str | None
    npx: str | None
    version: str | None = None

    @property
    def recommended_action(self) -> Literal["ready", "index", "install", "commands"]:
        """What a fresh project should do next (ignoring the requested mode)."""
        if self.index_present:
            return "ready"
        if self.binary:
            return "index"
        if self.npm:
            return "install"
        return "commands"

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary": self.binary,
            "version": self.version,
            "index_present": self.index_present,
            "db_path": str(self.db_path),
            "npm": self.npm,
            "npx": self.npx,
            "recommended_action": self.recommended_action,
            "manual_commands": manual_commands(self),
        }


@dataclass(frozen=True)
class CodegraphActionResult:
    """Outcome of an install/index attempt."""

    ok: bool
    action: str
    detail: str
    commands: list[list[str]]


def _which(name: str) -> str | None:
    return shutil.which(name)


def _probe_version(binary: str) -> str | None:
    try:
        # ll-no-project: detection probe, no task payload (ENH-3184 AC2)
        result = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=_VERSION_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def detect_codegraph(
    project_root: Path, db_path: str | None = None, *, probe_version: bool = False
) -> CodegraphStatus:
    """Probe PATH and the project for the codegraph binary, index, and npm toolchain.

    ``probe_version`` runs ``codegraph --version`` (a Node startup, ~0.5 s);
    only display surfaces that show the version should ask for it.
    """
    if db_path is None:
        from little_loops.init.core import schema_default

        db_path = str(schema_default("code_query.codegraph.db_path"))
    binary = _which(CODEGRAPH_BINARY)
    db = project_root / db_path
    return CodegraphStatus(
        binary=binary,
        index_present=db.is_file(),
        db_path=db,
        node=_which("node"),
        npm=_which("npm"),
        npx=_which("npx"),
        version=_probe_version(binary) if (binary and probe_version) else None,
    )


def manual_commands(status: CodegraphStatus) -> list[str]:
    """The exact shell commands a user runs to get from *status* to a fresh index."""
    commands: list[str] = []
    if status.binary is None:
        commands.append(f"npm install -g {CODEGRAPH_PACKAGE}")
    if not status.index_present:
        commands.append(f"{CODEGRAPH_BINARY} init .")
    commands.append("ll-code status")
    return commands


def resolve_code_graph_action(mode: str, status: CodegraphStatus) -> Action:
    """Map a ``--code-graph`` mode + detected status to the action to take.

    ``auto`` never installs: it indexes when the binary is already on PATH
    and otherwise prints the commands. ``install`` is the only mode that
    runs ``npm install -g``. ``index`` without the binary falls back to an
    ``npx`` one-shot when npx is available.
    """
    if mode == "skip":
        return "skip"
    if status.index_present:
        return "ready"
    if mode == "commands":
        return "commands"
    if status.binary:
        return "index"
    if mode == "index" and status.npx:
        return "index"
    if mode == "install" and status.npm:
        return "install"
    return "commands"


def _run(argv: list[str], *, timeout: int, cwd: Path | None = None) -> tuple[bool, str]:
    try:
        # ll-no-project: tool install/index helper, not a host CLI spawn (ENH-3184 AC2)
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as exc:
        return False, str(exc)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, (tail[-1] if tail else f"exit code {result.returncode}")
    return True, (result.stdout or "").strip()


def install_codegraph(
    *, dry_run: bool = False, timeout: int = INSTALL_TIMEOUT
) -> CodegraphActionResult:
    """``npm install -g @colbymchenry/codegraph``. Never retries with sudo."""
    npm = _which("npm")
    argv = [npm or "npm", "install", "-g", CODEGRAPH_PACKAGE]
    if npm is None:
        return CodegraphActionResult(False, "install", "npm not found on PATH", [argv])
    if dry_run:
        return CodegraphActionResult(False, "install", "dry run — not executed", [argv])
    ok, detail = _run(argv, timeout=timeout)
    if not ok and "EACCES" in detail:
        detail += (
            " — npm's global prefix isn't writable. Fix with "
            "`npm config set prefix ~/.npm-global` (and add ~/.npm-global/bin to PATH), "
            f"or run `npx --yes {CODEGRAPH_PACKAGE} init .` instead."
        )
    return CodegraphActionResult(ok, "install", detail or "installed", [argv])


def index_codegraph(
    project_root: Path,
    status: CodegraphStatus,
    *,
    dry_run: bool = False,
    timeout: int = INDEX_TIMEOUT,
) -> CodegraphActionResult:
    """``codegraph init <root>`` (or the ``npx`` one-shot when only npx is available).

    The npx form leaves ``code_query.codegraph.auto_sync`` a no-op (it needs
    ``codegraph`` on PATH), so the global install remains the recommended
    path; the one-shot is a convenience for an explicit ``--code-graph index``.
    """
    binary = status.binary or _which(CODEGRAPH_BINARY)
    # Run from the project root with "." so the displayed command is the one
    # a user would type; the subprocess gets cwd=project_root.
    if binary:
        argv = [binary, "init", "."]
    elif status.npx:
        argv = [status.npx, "--yes", CODEGRAPH_PACKAGE, "init", "."]
    else:
        return CodegraphActionResult(
            False, "index", "codegraph binary not found on PATH", [[CODEGRAPH_BINARY, "init", "."]]
        )
    if dry_run:
        return CodegraphActionResult(False, "index", "dry run — not executed", [argv])
    ok, detail = _run(argv, timeout=timeout, cwd=project_root)
    if ok and not (project_root / status.db_path.relative_to(project_root)).is_file():
        # The tool exited 0 but produced no database — treat as failure so the
        # config isn't pointed at an index that does not exist.
        ok = False
        detail = detail or "codegraph init exited 0 but wrote no index"
    return CodegraphActionResult(ok, "index", detail or "indexed", [argv])


def code_query_section() -> dict[str, Any]:
    """The ``code_query`` config block written once an index exists."""
    from little_loops.init.core import schema_default

    return {"provider": schema_default("code_query.provider")}


def run_code_graph_step(
    mode: str,
    project_root: Path,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] | None = None,
    warn: Callable[[str], None] | None = None,
    status: CodegraphStatus | None = None,
) -> tuple[CodegraphStatus, CodegraphActionResult | None]:
    """Run the code-graph step for *mode* and report through *log*/*warn*.

    Returns the detected status (re-probed after a successful action so
    ``index_present`` reflects the new index) and the action result, if any
    action ran. Failures are reported as warnings with the manual commands;
    they never raise.
    """
    from little_loops.cli.output import info, warning

    log = log or info
    warn = warn or warning
    status = status or detect_codegraph(project_root)
    action = resolve_code_graph_action(mode, status)
    rel_db = _relative(status.db_path, project_root)

    if action == "skip":
        return status, None
    if action == "ready":
        log(f"Code graph: codegraph index found at {rel_db} — ll-code will use it")
        return status, None
    if action == "commands":
        if status.binary is None and status.npm is None:
            log(
                "Code graph: optional — install Node.js/npm, then codegraph, to give "
                "ll-code an indexed call graph (grep/AST fallback works without it):"
            )
        elif status.binary is None:
            log(
                "Code graph: optional — codegraph gives ll-code an indexed call graph "
                "(re-run with --code-graph install to do this automatically):"
            )
        else:
            log("Code graph: codegraph is installed but this project isn't indexed yet:")
        for cmd in manual_commands(status):
            log(f"  {cmd}")
        return status, None

    result: CodegraphActionResult | None = None
    if action == "install":
        log(f"Code graph: installing {CODEGRAPH_PACKAGE} (npm install -g, may take a minute)...")
        result = install_codegraph(dry_run=dry_run)
        if dry_run:
            log(f"  would run: {' '.join(result.commands[0])}")
        elif not result.ok:
            warn(f"Code graph: install failed: {result.detail}")
            for cmd in manual_commands(status):
                warn(f"  {cmd}")
            return status, result
        else:
            log("Code graph: codegraph installed")
            status = detect_codegraph(project_root, str(_relative(status.db_path, project_root)))

    result = index_codegraph(project_root, status, dry_run=dry_run)
    if dry_run:
        log(f"Code graph: would build the codegraph index: {' '.join(result.commands[0])}")
        return status, result
    log("Code graph: building the codegraph index (codegraph init) — this can take a while...")
    if not result.ok:
        warn(f"Code graph: indexing failed: {result.detail}")
        for cmd in manual_commands(status):
            warn(f"  {cmd}")
        return status, result
    status = detect_codegraph(project_root, str(_relative(status.db_path, project_root)))
    log(f"Code graph: index built at {rel_db} — ll-code will use it")
    return status, result


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path
