"""Host-parameterized adapter core for skill/command/agent emission.

Defines the :class:`HostEmitter` Protocol and a registry-backed
:func:`resolve_emitter` factory.  Concrete emitters live in sibling modules
(``codex.py``, ``omp.py``); this module owns only the shared interface,
registry, shared helpers, and traversal functions.

See FEAT-2391 for the full design.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

import yaml

from little_loops.adapters.capabilities import HOST_CAPABILITIES


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
    def emit_mcp_config(self, meta: dict) -> str: ...


# Lazy-import registry: host name → (module_path, class_name).
# Concrete modules import from this module (AdapterError, helpers), so we must
# not import them at the module level — only resolve on demand via importlib.
# NOTE: keys must match their host_runner registry key where both exist —
# ll-verify-host-map check 2 only cross-validates the intersection, which is
# why kimi-code is registered with its suffixed runner key (EPIC-2910).
_EMITTER_MAP: dict[str, tuple[str, str]] = {
    "codex": ("little_loops.adapters.codex", "CodexEmitter"),
    "gemini": ("little_loops.adapters.gemini", "GeminiEmitter"),
    "omp": ("little_loops.adapters.omp", "OmpEmitter"),
    "kimi-code": ("little_loops.adapters.kimi", "KimiEmitter"),
    "claude-code": ("little_loops.adapters.claude_code", "ClaudeCodeEmitter"),
}


def resolve_emitter(host: str) -> HostEmitter:
    """Return a :class:`HostEmitter` instance for *host*.

    Args:
        host: One of ``"codex"``, ``"gemini"``, ``"omp"``, ``"kimi-code"``,
            ``"claude-code"``.

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


_FM_CLOSE_RE = re.compile(r"\n---\s*\n")


def _select_frontmatter_fields(
    content: str,
    name: str,
    fields_read: tuple[str, ...],
    short_desc: str = "",
) -> tuple[str, bool]:
    """Add/strip SKILL.md frontmatter fields per a host's ``frontmatter_fields_read``.

    Generalizes what was previously host-private policy
    (``codex._insert_skill_fields``, ``gemini._inject_name`` +
    ``gemini._strip_metadata_short_description``) into a single map-driven
    helper (ENH-2883): the *decision* of which fields a host reads now comes
    from :data:`little_loops.adapters.capabilities.HOST_CAPABILITIES`, not
    from per-emitter code.

    - Injects ``name: <name>`` at the top of frontmatter when ``"name"`` is
      in *fields_read* and no ``name:`` key is already present.
    - When ``"metadata.short-description"`` is in *fields_read*, inserts
      ``metadata.short-description: <short_desc>`` if absent (nesting under
      an existing ``metadata:`` block when present).
    - When it is *not* in *fields_read*, strips an existing
      ``metadata.short-description:`` line (and the ``metadata:`` header if
      left empty) — a host that doesn't read the field shouldn't emit it.

    Uses targeted string manipulation — no yaml roundtrip — to preserve
    existing frontmatter formatting. Returns ``(new_content, changed)``.
    """
    if not content.startswith("---\n"):
        return content, False

    m = _FM_CLOSE_RE.search(content[3:])
    if not m:
        return content, False

    fm_text = content[4 : 3 + m.start()]
    after = content[3 + m.start() :]

    changed = False

    if "name" in fields_read and not re.search(r"^name\s*:", fm_text, re.MULTILINE):
        fm_text = f"name: {name}\n" + fm_text
        changed = True

    if "metadata.short-description" in fields_read:
        if "short-description:" not in fm_text:
            if re.search(r"^metadata\s*:", fm_text, re.MULTILINE):
                fm_text = re.sub(
                    r"^(metadata\s*:.*)$",
                    lambda mtch: mtch.group(0) + f"\n  short-description: {short_desc}",
                    fm_text,
                    flags=re.MULTILINE,
                    count=1,
                )
            else:
                fm_text += f"\nmetadata:\n  short-description: {short_desc}"
            changed = True
    elif "short-description:" in fm_text:
        cleaned = re.sub(r"^[ \t]*short-description:.*$\n?", "", fm_text, flags=re.MULTILINE)
        cleaned = re.sub(r"^metadata:[ \t]*\n(?=\n|\Z)", "", cleaned, flags=re.MULTILINE)
        if cleaned != fm_text:
            changed = True
        fm_text = cleaned

    return f"---\n{fm_text}{after}", changed


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
# Degraded-mode agent emission (ENH-2874)
# ---------------------------------------------------------------------------

# Fixed marker prefix (mirrors codex.py's `_MARKER`/`_format_agent_toml`
# shape) so degraded files are recognisably ll-generated for idempotency and
# so a hand-authored file at the same path is never silently overwritten.
_DEGRADED_AGENT_MARKER = "<!-- generated by ll-adapt (degraded mode, ENH-2874) -->"

_DEGRADED_AGENT_PREAMBLE = f"""{_DEGRADED_AGENT_MARKER}

> **Degraded-mode role — no subagent support on this host.** This host
> cannot spawn a delegated subagent for this role. Perform the role
> described below **inline**, in the current session, instead of attempting
> to delegate or spawn a subagent for it — no subagent tool is available
> here. When you report results for this role, disclose in one line that
> inline substitution was used in place of a delegated subagent (for
> example: "Note: performed this inline — no subagent support on this
> host.").

---

"""


def _emit_degraded_agent(agent_meta: dict) -> str:
    """Write a degraded-mode inline-role file for one ``agents/*.md`` source.

    Selected by :func:`process_agents` for any host whose capability entry
    declares ``subagents == "none"`` with a non-``None`` ``agent_output_format``
    (a working degraded emitter), instead of calling ``emitter.emit_agent``.
    Host emitters that route their own ``emit_agent`` here (e.g.
    ``GeminiEmitter``) get the same output when called directly.

    The output is the fixed preamble (:data:`_DEGRADED_AGENT_PREAMBLE`)
    followed by the authored body extracted verbatim via
    :func:`_extract_body` — never a hand-maintained parallel copy.

    Returns:
        ``"adapted"``, ``"skipped"``, or ``"error"``.
    """
    agent_name: str = agent_meta["agent_name"]
    content: str = agent_meta["content"]
    output_dir: Path = agent_meta["output_dir"]
    apply: bool = agent_meta["apply"]
    quiet: bool = agent_meta["quiet"]

    body = _extract_body(content)
    if not body.strip():
        if not quiet:
            print(f"  SKIP   {agent_name}: no body content")
        return "skipped"

    new_content = _DEGRADED_AGENT_PREAMBLE + body
    out_path = output_dir / f"{agent_name}.md"

    if out_path.exists():
        existing = out_path.read_text()
        if not existing.startswith(_DEGRADED_AGENT_MARKER):
            if not quiet:
                print(f"  SKIP   {agent_name}: user-authored file (no marker)")
            return "skipped"
        if existing == new_content:
            if not quiet:
                print(f"  SKIP   {agent_name}: already up to date")
            return "skipped"

    if apply:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(new_content)
        if not quiet:
            print(f"  APPLY  {agent_name}: degraded-mode inline role")
    else:
        if not quiet:
            print(f"  DRY    {agent_name}: degraded-mode inline role")

    return "adapted"


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

        try:
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
        except AdapterError as exc:
            if not quiet:
                print(f"  ERROR  {skill_name}: {exc}", file=sys.stderr)
            errors += 1
            continue
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

        try:
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
        except AdapterError as exc:
            if not quiet:
                print(f"  ERROR  {label}: {exc}", file=sys.stderr)
            errors += 1
            continue
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

    # ENH-2874: select native vs. degraded emission from the capability flag
    # alone — no host-name branch. A host qualifies for degraded emission
    # when it declares subagents == "none" *and* has a working agent
    # emitter (agent_output_format is not None); omp declares neither, so it
    # stays excluded and continues to hit emitter.emit_agent's raise below.
    entry = HOST_CAPABILITIES.get(getattr(emitter, "name", ""))
    degraded = (
        entry is not None and entry.subagents == "none" and entry.agent_output_format is not None
    )

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
        agent_meta = {
            "agent_name": agent_name,
            "agent_path": agent_md,
            "content": content,
            "fm": fm,
            "output_dir": output_dir,
            "apply": apply,
            "quiet": quiet,
        }

        try:
            result = (
                _emit_degraded_agent(agent_meta) if degraded else emitter.emit_agent(agent_meta)
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


def process_mcp_config(
    emitter: HostEmitter,
    output_dir: Path,
    apply: bool,
    quiet: bool,
) -> tuple[int, int, int]:
    """Call ``emitter.emit_mcp_config`` once to register the ``ll-mcp`` server.

    Unlike ``process_skills``/``process_commands``/``process_agents``, there is
    no per-source-file glob to traverse — MCP config emission produces a
    single artifact per host.

    Args:
        output_dir: Host-specific destination for the emitted MCP config
            artefact (e.g. ``.codex/`` for Codex).

    Returns:
        ``(adapted, skipped, errors)`` counts (each 0 or 1).
    """
    meta = {
        "output_dir": output_dir,
        "apply": apply,
        "quiet": quiet,
    }

    try:
        result = emitter.emit_mcp_config(meta)
    except AdapterError as exc:
        if not quiet:
            print(f"  ERROR  mcp-config: {exc}", file=sys.stderr)
        return 0, 0, 1

    if result == "adapted":
        return 1, 0, 0
    elif result == "skipped":
        return 0, 1, 0
    else:
        return 0, 0, 1
