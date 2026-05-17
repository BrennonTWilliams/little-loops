"""Round-trip YAML editor for loop state action blocks.

Uses ruamel.yaml (round-trip mode) to preserve `action: |` block scalar
formatting when extracting or replacing a named state's action field.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from little_loops.file_utils import atomic_write


def extract_action(loop_yaml_path: Path, state_name: str) -> str:
    """Return the action string for *state_name* in the loop YAML at *loop_yaml_path*.

    Raises KeyError if *state_name* is not found in ``states``.
    """
    yaml = YAML(typ="rt")
    data = yaml.load(loop_yaml_path)
    return str(data["states"][state_name]["action"])


def replace_action(loop_yaml_path: Path, state_name: str, new_action: str) -> None:
    """Replace the action for *state_name* in the loop YAML at *loop_yaml_path*.

    Writes back in-place using atomic_write, preserving block scalar style
    (``action: |``) for the modified state and leaving all other states and
    keys unchanged.

    Raises KeyError if *state_name* is not found in ``states``.
    """
    yaml = YAML(typ="rt")
    data = yaml.load(loop_yaml_path)
    # LiteralScalarString forces ruamel to emit `action: |` rather than
    # choosing a quoted or flow scalar style for the new value.
    data["states"][state_name]["action"] = LiteralScalarString(new_action)
    buf = StringIO()
    yaml.dump(data, buf)
    atomic_write(loop_yaml_path, buf.getvalue())
