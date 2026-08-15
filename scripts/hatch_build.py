"""Custom hatchling build hook (BUG-3177): conditionally force-include skills/.

`force-include` is otherwise the right tool for shipping `skills/` (host-plugin
glue kept physically at the repo root, FEAT-2274/BUG-938) into the wheel without
relocating it — but a static `[tool.hatch.build.targets.wheel.force-include]`
mapping is unconditional, and hatchling treats a missing source as a hard build
error (``FileNotFoundError: Forced include not found: ...``), not a silent skip.

That matters because this project builds in two different working directories:

- From a full checkout (`scripts/` with `../skills` present) — both the sdist
  and wheel builds need the force-include to reach outside the packaging root.
- From an *unpacked sdist* (`python -m build --wheel` run inside the extracted
  sdist directory, the `pip install little-loops` from-source path) — the sdist
  build already copied `skills/` in place at `little_loops/skills/` (via this
  same hook), so `../skills` no longer exists relative to that root, and a
  static force-include mapping would fail the build outright even though the
  wheel's plain `include = ["little_loops/**"]` glob already covers the
  in-place copy.

This hook adds the force-include mapping only when the source directory
actually exists, so the from-sdist wheel build falls through to the plain
glob instead of hard-failing on the always-static form.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SkillsForceIncludeHook(BuildHookInterface):  # type: ignore[type-arg]
    PLUGIN_NAME = "skills-force-include"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        skills_src = Path(self.root) / ".." / "skills"
        if skills_src.is_dir():
            build_data.setdefault("force_include", {})[str(skills_src)] = "little_loops/skills"
