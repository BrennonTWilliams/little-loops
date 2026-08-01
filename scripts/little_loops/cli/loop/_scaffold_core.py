"""Shared plumbing for `ll-loop scaffold-eval`/`scaffold-verify` (FEAT-2948).

Only the genuinely-shared bits live here: issue resolution (both scaffolds
resolve an issue ID the same way `ll-issues show` does), the `ScaffoldResult`
report shape, and clean-YAML serialization via `ruamel.yaml` +
`LiteralScalarString` (mirrors `loops/yaml_state_editor.py`'s precedent for
`action: |` block scalars). The two scaffolds' state-chaining shapes diverge
enough (proof-state splicing vs. criteria/probe linear chains) that a shared
chaining helper would need more branching than duplication, so each module
builds its own state dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from little_loops.fsm.schema import FSMLoop
from little_loops.issue_parser import IssueInfo, IssueParser


@dataclass
class ScaffoldResult:
    """Output of a scaffold-eval/scaffold-verify generation (FEAT-2948 Program Design)."""

    yaml_path: Path | None
    yaml_text: str
    placeholders: list[str]
    validated: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "yaml_path": str(self.yaml_path) if self.yaml_path else None,
            "yaml_text": self.yaml_text,
            "placeholders": self.placeholders,
            "validated": self.validated,
            "errors": self.errors,
        }


def resolve_issue(issue_id: str) -> tuple[Path | None, IssueInfo | None, str | None]:
    """Resolve *issue_id* to (path, parsed IssueInfo, error) using the `ll-issues show` lookup."""
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.config import BRConfig

    config = BRConfig(Path.cwd())
    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return None, None, f"Issue '{issue_id}' not found."
    parser = IssueParser(config)
    info = parser.parse_file(path)
    return path, info, None


def dump_fsm_yaml(fsm: FSMLoop) -> str:
    """Serialize *fsm* to clean YAML with block-scalar `action:`/`evaluate.prompt:` fields."""
    data = fsm.to_dict()
    for state in data.get("states", {}).values():
        if isinstance(state.get("action"), str) and "\n" in state["action"]:
            state["action"] = LiteralScalarString(state["action"])
        evaluate = state.get("evaluate")
        if isinstance(evaluate, dict) and isinstance(evaluate.get("prompt"), str):
            evaluate["prompt"] = LiteralScalarString(evaluate["prompt"])
    if isinstance(data.get("description"), str) and "\n" in data["description"]:
        data["description"] = LiteralScalarString(data["description"])

    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.width = 4096
    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()
