"""Host-parameterized adapter core for skill/command/agent emission.

Defines the :class:`HostEmitter` Protocol and a registry-backed
:func:`resolve_emitter` factory.  Concrete emitters live in sibling modules
(``codex.py``, ``omp.py``); this module owns only the shared interface,
registry, shared helpers, and traversal functions.

See FEAT-2391 for the full design.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

import yaml


class AdapterError(Exception):
    """Raised when a host emitter cannot fulfil the request."""


@runtime_checkable
class HostEmitter(Protocol):
    """Protocol for host-specific output emitters.

    Implementations convert ll skill/command/agent metadata into the target
    host's discovery format.  Structurally matched — any class with ``name``
    and the three ``emit_*`` methods satisfies this Protocol without explicit
    subclassing.  ``@runtime_checkable`` enables ``isinstance`` registry checks.
    """

    name: str

    def emit_skill(self, skill_meta: dict) -> str: ...
    def emit_command(self, cmd_meta: dict) -> str: ...
    def emit_agent(self, agent_meta: dict) -> str: ...


# Lazy-import registry: host name → (module_path, class_name).
# Concrete modules import from this module (AdapterError, helpers), so we must
# not import them at the module level — only resolve on demand via importlib.
_EMITTER_MAP: dict[str, tuple[str, str]] = {
    "codex": ("little_loops.adapters.codex", "CodexEmitter"),
    "gemini": ("little_loops.adapters.gemini", "GeminiEmitter"),
    "omp": ("little_loops.adapters.omp", "OmpEmitter"),
}


def resolve_emitter(host: str) -> HostEmitter:
    """Return a :class:`HostEmitter` instance for *host*.

    Args:
        host: One of ``"codex"``, ``"gemini"``, ``"omp"``.

    Returns:
        A :class:`HostEmitter` ready to emit skills, commands, and agents.

    Raises:
        AdapterError: if *host* is not registered.
    """
    entry = _EMITTER_MAP.get(host)
    if entry is None:
        raise AdapterError(f"Host {host!r} is not registered. Available: {sorted(_EMITTER_MAP)}.")
    module_path, cls_name = entry
    module = importlib.import_module(module_path)
    return cast(HostEmitter, getattr(module, cls_name)())


# ---------------------------------------------------------------------------
# Shared frontmatter helpers
# ---------------------------------------------------------------------------


def _read_frontmatter(text: str) -> dict | None:
    """Parse YAML frontmatter from *text*. Returns None on any failure."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _extract_body(text: str) -> str:
    """Return body text after the closing ``---`` of frontmatter."""
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    after_fm = text[end + 3 :]
    if after_fm.startswith("\n"):
        after_fm = after_fm[1:]
    return after_fm


def _is_model_invocation_disabled(fm: dict) -> bool:
    """Return True if *fm* has ``disable-model-invocation`` set to a truthy value.

    Handles both native YAML booleans and stringified values (``"true"``,
    ``"yes"``, ``"1"``) for compatibility with ``parse_skill_frontmatter``
    which returns a flat ``dict[str, str]``.
    """
    val = fm.get("disable-model-invocation")
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "yes", "1"}


# ---------------------------------------------------------------------------
# Shared traversal functions
# ---------------------------------------------------------------------------


def process_skills(
    emitter: HostEmitter,
    skills_dir: Path,
    apply: bool,
    quiet: bool,
) -> tuple[int, int, int]:
    """Walk *skills_dir*, apply the ``disable-model-invocation`` filter, and
    call ``emitter.emit_skill`` for each eligible skill.

    Returns:
        ``(adapted, skipped, errors)`` counts.
    """
    adapted = skipped = errors = 0

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        try:
            content = skill_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  {skill_name}: cannot read: {exc}", file=sys.stderr)
            errors += 1
            continue

        fm = _read_frontmatter(content) or {}
        if _is_model_invocation_disabled(fm):
            if not quiet:
                print(f"  SKIP   {skill_name}: disable-model-invocation: true")
            skipped += 1
            continue

        result = emitter.emit_skill(
            {
                "skill_name": skill_name,
                "skill_path": skill_md,
                "content": content,
                "fm": fm,
                "apply": apply,
                "quiet": quiet,
            }
        )
        if result == "adapted":
            adapted += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    return adapted, skipped, errors


def process_commands(
    emitter: HostEmitter,
    commands_dir: Path,
    output_dir: Path,
    apply: bool,
    quiet: bool,
) -> tuple[int, int, int]:
    """Walk *commands_dir*, apply the ``disable-model-invocation`` filter, and
    call ``emitter.emit_command`` for each eligible command.

    Args:
        output_dir: Host-specific destination for synthesized skill wrappers
            (e.g. ``skills/`` for Codex).

    Returns:
        ``(adapted, skipped, errors)`` counts.
    """
    adapted = skipped = errors = 0

    if not commands_dir.exists():
        return adapted, skipped, errors

    for cmd_md in sorted(commands_dir.glob("*.md")):
        stem = cmd_md.stem
        label = f"ll-{stem}"
        try:
            content = cmd_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  {label}: cannot read: {exc}", file=sys.stderr)
            errors += 1
            continue

        fm = _read_frontmatter(content)
        if fm is None:
            if not quiet:
                print(f"  SKIP   {label}: no parseable frontmatter")
            skipped += 1
            continue

        if _is_model_invocation_disabled(fm):
            if not quiet:
                print(f"  SKIP   {label}: disable-model-invocation: true")
            skipped += 1
            continue

        result = emitter.emit_command(
            {
                "stem": stem,
                "cmd_path": cmd_md,
                "content": content,
                "fm": fm,
                "output_dir": output_dir,
                "apply": apply,
                "quiet": quiet,
            }
        )
        if result == "adapted":
            adapted += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    return adapted, skipped, errors


def process_agents(
    emitter: HostEmitter,
    agents_dir: Path,
    output_dir: Path,
    apply: bool,
    quiet: bool,
    only: str | None = None,
) -> tuple[int, int, int]:
    """Walk *agents_dir* and call ``emitter.emit_agent`` for each agent file.

    Agents whose stem does not match *only* (when set) are silently skipped
    and NOT counted in any return bucket.

    Args:
        output_dir: Host-specific destination for emitted artefacts
            (e.g. ``.codex/agents/`` for Codex).
        only: If non-None, restrict processing to the single agent with this
            stem name.

    Returns:
        ``(adapted, skipped, errors)`` counts.
    """
    adapted = skipped = errors = 0

    for agent_md in sorted(agents_dir.glob("*.md")):
        agent_name = agent_md.stem

        if only is not None and agent_name != only:
            continue  # silently dropped, not counted

        try:
            content = agent_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  {agent_name}: cannot read: {exc}", file=sys.stderr)
            errors += 1
            continue

        fm = _read_frontmatter(content) or {}

        try:
            result = emitter.emit_agent(
                {
                    "agent_name": agent_name,
                    "agent_path": agent_md,
                    "content": content,
                    "fm": fm,
                    "output_dir": output_dir,
                    "apply": apply,
                    "quiet": quiet,
                }
            )
        except AdapterError as exc:
            if not quiet:
                print(f"  ERROR  {agent_name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        if result == "adapted":
            adapted += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    return adapted, skipped, errors
