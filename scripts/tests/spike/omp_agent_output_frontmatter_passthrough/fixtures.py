"""Synthetic schema-shaped ``output:`` frontmatter fixtures.

No real ll agent definition carries an ``output:`` schema field today (see
FEAT-2797's own Codebase Research Findings) — this stands in for one, to
exercise ``_select_frontmatter_fields``/``OmpEmitter.emit_agent`` against the
untested combination.
"""

from __future__ import annotations

# A JSON-Schema-shaped block, indented as a nested YAML mapping under a
# top-level `output:` key — the shape a future ll agent output schema would
# plausibly take.
SCHEMA_SHAPED_OUTPUT_BLOCK = (
    "output:\n"
    "  type: object\n"
    "  properties:\n"
    "    verdict:\n"
    "      type: string\n"
    "    confidence:\n"
    "      type: number\n"
    "  required: [verdict]\n"
)

SCHEMA_SHAPED_OUTPUT_VALUE = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["verdict"],
}


def agent_md(
    *,
    include_name: bool,
    include_metadata_block: bool,
    include_short_description: bool = True,
    body: str = "Spike fixture agent body.\n",
) -> str:
    """Build a synthetic agent ``.md`` with ``SCHEMA_SHAPED_OUTPUT_BLOCK``.

    ``include_metadata_block`` controls whether a ``metadata:`` block with a
    ``short-description:`` key sits directly adjacent (no blank line) to the
    ``output:`` block — omp's ``frontmatter_fields_read`` excludes
    ``metadata.short-description``, so this fires the strip branch right next
    to the field under test.
    """
    lines = ["description: Spike fixture agent for FEAT-2797."]
    if include_name:
        lines.append("name: existing-agent-name")
    if include_metadata_block:
        if include_short_description:
            lines.append("metadata:\n  short-description: A fixture agent.")
        else:
            lines.append("metadata:\n  owner: spike-fixture")
    fm_lines = "\n".join(lines) + "\n" + SCHEMA_SHAPED_OUTPUT_BLOCK
    return f"---\n{fm_lines}---\n{body}"
