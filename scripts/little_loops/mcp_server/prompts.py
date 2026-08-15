"""ll-mcp's prompts-from-skills surface (FEAT-3137).

`ll-mcp` advertises every discovered `SKILL.md` as an MCP prompt, mirroring `resources.py`'s
"build once at discovery, close handlers over an index" shape (see that module's docstring for
why this is a deliberate, scoped departure from `tools.py`'s statelessness invariant).

Discovery walks the plugin's `skills/` directory recursively (`Path.rglob("SKILL.md")`), not
the non-recursive `glob("*/SKILL.md")` used by the 4+ existing skill-catalog sites
(`tool_catalog.py`, `adapters/core.py`, `cli/help.py`, `cli/verify_skill_prose.py`) — a nested
`SKILL.md` must register as its own independent prompt, never be absorbed as a parent skill's
supporting file. `prompts/get` resolves only against skill names recorded in that same
discovery-time index — the enumeration, not path sanitization, is what makes traversal
impossible, matching `resources.py`'s access-control shape exactly.

Frontmatter is parsed at list time only (`parse_skill_frontmatter` — the canonical SKILL.md
parser; see `frontmatter.py`); full skill bodies are read on demand in `prompts/get`, not
cached in the index. A skill with `disable-model-invocation: true` is skipped entirely,
matching `adapters/core.py::process_skills()`'s blanket-skip behavior — the closest existing
precedent in intent to an external, untrusted MCP client (see this issue's Conventions in
Force).

ENH-3172: the once-built index goes stale the moment a `SKILL.md` is added, removed, or
renamed after startup. `PromptIndex` wraps the dict in a cheap on-demand refresh (the
skills root's own mtime, via `_staleness.dir_signature`) so `prompts/list`/`prompts/get`
resolve against a fresh enumeration instead of the discovery-time snapshot. Nested
`SKILL.md` additions two or more levels under the skills root won't retrigger a rebuild
via this signal alone — see `_staleness.py`'s module docstring for why that's the accepted
scope, not a gap to close here.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcp_types as types
from mcp.shared.exceptions import MCPError

from little_loops.mcp_server._staleness import Signature, dir_signature

if TYPE_CHECKING:
    from mcp.server.subscriptions import SubscriptionBus


@dataclasses.dataclass(frozen=True)
class _PromptEntry:
    """One discovery-time-enumerated `SKILL.md` prompt."""

    name: str
    description: str
    args_hint: str | None
    path: Path


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def build_prompt_index(skills_dir: Path) -> dict[str, _PromptEntry]:
    """Build the discovery-time enumeration once: the full `name -> _PromptEntry` map.

    This is the allowlist `prompts/get` resolves against — see the module docstring.
    Skill name is always the containing directory name, never a frontmatter `name` field
    (the established convention at every existing skill-walk site but one).
    """
    from little_loops.adapters.core import _is_model_invocation_disabled
    from little_loops.frontmatter import parse_skill_frontmatter

    if not skills_dir.is_dir():
        return {}

    index: dict[str, _PromptEntry] = {}
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        name = skill_md.parent.name
        if name in index:
            continue
        content = _read_text_or_empty(skill_md)
        fm = parse_skill_frontmatter(content) if content else {}
        if _is_model_invocation_disabled(fm):
            continue
        args_hint = _clean(fm.get("args") or fm.get("argument-hint")) or None
        index[name] = _PromptEntry(
            name=name,
            description=_clean(fm.get("description")),
            args_hint=args_hint,
            path=skill_md,
        )
    return index


@dataclasses.dataclass
class PromptIndex:
    """Mutable holder for the prompts-from-skills enumeration, refreshed on demand (ENH-3172).

    Built once (`__post_init__`), then re-derived only when `refresh()` observes the
    skills root's own mtime has changed — a cheap `stat()` call, not a full `rglob`, on
    every request that doesn't need one.
    """

    skills_dir: Path
    entries: dict[str, _PromptEntry] = dataclasses.field(default_factory=dict, init=False)
    _signature: Signature = dataclasses.field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        self.entries = build_prompt_index(self.skills_dir)
        self._signature = dir_signature([self.skills_dir])

    def refresh(self) -> bool:
        """Rebuild `entries` if the skills-root signature changed.

        Returns whether a rebuild happened, so callers can decide whether to notify
        subscribers and whether this response is safe to let a client cache.
        """
        signature = dir_signature([self.skills_dir])
        if signature == self._signature:
            return False
        self.entries = build_prompt_index(self.skills_dir)
        self._signature = signature
        return True


def make_list_prompts_handler(index: PromptIndex, bus: SubscriptionBus) -> Any:
    """Build the `prompts/list` handler, closing over `index` and refreshing it per call.

    `ttlMs`/`cacheScope` are left unset on the common path, same as `handle_list_resources` —
    the `Server(cache_hints=...)` entry for `"prompts/list"` fills them per SEP-2549. When
    `index.refresh()` rebuilds (ENH-3172), a `PromptsListChanged` event is published on `bus`
    (delivered to any open `subscriptions/listen` stream) and this particular response has
    `ttl_ms=0` forced on it, matching `make_list_resources_handler`'s reconciliation with the
    5-minute public `CacheHint`.
    """
    from mcp.server.subscriptions import PromptsListChanged

    def _prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name=entry.name,
                description=entry.description or None,
                arguments=(
                    [
                        types.PromptArgument(
                            name="args",
                            description=entry.args_hint,
                            required=False,
                        )
                    ]
                    if entry.args_hint
                    else None
                ),
            )
            for entry in index.entries.values()
        ]

    async def handle_list_prompts(
        _ctx: Any,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListPromptsResult:
        changed = index.refresh()
        result = types.ListPromptsResult(prompts=_prompts())
        if changed:
            await bus.publish(PromptsListChanged())
            result = result.model_copy(update={"ttl_ms": 0})
        return result

    return handle_list_prompts


def make_get_prompt_handler(index: PromptIndex) -> Any:
    """Build the `prompts/get` handler, closing over `index` and refreshing it per call.

    A `name` absent from `index.entries` after the refresh is rejected outright — the dict
    lookup below is the entire access-control boundary, matching `handle_read_resource`'s
    shape exactly.
    """
    from little_loops.frontmatter import strip_frontmatter

    async def handle_get_prompt(
        _ctx: Any,
        params: types.GetPromptRequestParams,
    ) -> types.GetPromptResult:
        index.refresh()
        entry = index.entries.get(params.name)
        if entry is None:
            raise MCPError(
                code=types.INVALID_PARAMS,
                message=f"Unknown prompt: {params.name}",
                data={"name": params.name},
            )
        try:
            content = entry.path.read_text()
        except OSError as exc:
            raise MCPError(
                code=types.INVALID_PARAMS,
                message=f"Prompt skill unreadable: {exc}",
                data={"name": params.name},
            ) from exc
        body = strip_frontmatter(content)
        return types.GetPromptResult(
            description=entry.description or None,
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=body),
                )
            ],
        )

    return handle_get_prompt
