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
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp.shared.exceptions import MCPError


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


def make_list_prompts_handler(index: dict[str, _PromptEntry]) -> Any:
    """Build the `prompts/list` handler, closing over the enumeration built once at startup.

    `ttlMs`/`cacheScope` are left unset here, same as `handle_list_resources` — the
    `Server(cache_hints=...)` entry for `"prompts/list"` fills them per SEP-2549.
    """
    prompts = [
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
        for entry in index.values()
    ]

    async def handle_list_prompts(
        _ctx: Any,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListPromptsResult:
        return types.ListPromptsResult(prompts=prompts)

    return handle_list_prompts


def make_get_prompt_handler(index: dict[str, _PromptEntry]) -> Any:
    """Build the `prompts/get` handler, closing over the same enumeration.

    A `name` absent from `index` is rejected outright — the dict lookup below is the entire
    access-control boundary, matching `handle_read_resource`'s shape exactly.
    """
    from little_loops.frontmatter import strip_frontmatter

    async def handle_get_prompt(
        _ctx: Any,
        params: types.GetPromptRequestParams,
    ) -> types.GetPromptResult:
        entry = index.get(params.name)
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
