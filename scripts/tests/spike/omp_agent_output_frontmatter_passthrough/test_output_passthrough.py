"""AC tests for the omp agent output-frontmatter passthrough spike (FEAT-2797).

Proves the untested combination the issue's docstring/AC4 assumes: a schema-
shaped, unrecognized ``output:`` frontmatter key survives
``_select_frontmatter_fields`` / ``OmpEmitter.emit_agent`` byte-for-byte,
under the branches the function actually takes for omp (name injection,
short-description strip). See ``.ll/spikes/spike-FEAT-2797.md``.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.core import _read_frontmatter, _select_frontmatter_fields
from little_loops.adapters.omp import OmpEmitter, _fields_read

from .fixtures import SCHEMA_SHAPED_OUTPUT_VALUE, agent_md


class TestOutputFrontmatterPassthrough:
    def test_output_block_survives_name_injection(self):
        content = agent_md(include_name=False, include_metadata_block=False)
        new_content, changed = _select_frontmatter_fields(content, "injected-agent", _fields_read())

        assert changed is True
        fm = _read_frontmatter(new_content)
        assert fm is not None
        assert fm["name"] == "injected-agent"
        assert fm["output"] == SCHEMA_SHAPED_OUTPUT_VALUE

    def test_output_block_survives_short_description_strip(self):
        content = agent_md(include_name=True, include_metadata_block=True)
        new_content, changed = _select_frontmatter_fields(content, "existing-agent-name", _fields_read())

        assert changed is True
        fm = _read_frontmatter(new_content)
        assert fm is not None
        # `short-description:` is stripped, but the `metadata:` header itself
        # is only removed when followed by a blank line or EOF (the regex's
        # `(?=\n|\Z)` lookahead) — here it's immediately followed by
        # `output:`, so a dangling `metadata:` (-> None) survives. This is a
        # pre-existing quirk of `_select_frontmatter_fields`, orthogonal to
        # the output: passthrough claim under test — recorded, not fixed
        # (production code is read-only in this spike).
        assert fm["metadata"] is None
        assert fm["output"] == SCHEMA_SHAPED_OUTPUT_VALUE

    def test_output_block_survives_metadata_block_adjacency(self):
        # Both branches fire together: name missing (injection) AND an
        # adjacent metadata/short-description block (strip), with the
        # output: block directly abutting the metadata: block — the
        # sharpest stress case for the regex-based line removal.
        content = agent_md(include_name=False, include_metadata_block=True)
        new_content, changed = _select_frontmatter_fields(content, "adjacency-agent", _fields_read())

        assert changed is True
        fm = _read_frontmatter(new_content)
        assert fm is not None
        assert fm["name"] == "adjacency-agent"
        # See test_output_block_survives_short_description_strip: dangling
        # `metadata:` (-> None) is expected here too, same root cause.
        assert fm["metadata"] is None
        assert fm["output"] == SCHEMA_SHAPED_OUTPUT_VALUE

    def test_output_block_survives_metadata_without_short_description(self):
        # metadata: block present but with an unrelated key — neither branch
        # touches it; output: should still be untouched and metadata intact.
        content = agent_md(
            include_name=True, include_metadata_block=True, include_short_description=False
        )
        new_content, changed = _select_frontmatter_fields(content, "existing-agent-name", _fields_read())

        assert changed is False
        fm = _read_frontmatter(new_content)
        assert fm is not None
        assert fm["metadata"] == {"owner": "spike-fixture"}
        assert fm["output"] == SCHEMA_SHAPED_OUTPUT_VALUE

    def test_emit_agent_round_trip_preserves_schema_value(self, tmp_path: Path):
        content = agent_md(include_name=False, include_metadata_block=True)
        agent_meta = {
            "agent_name": "roundtrip-agent",
            "content": content,
            "output_dir": tmp_path / ".omp" / "agents",
            "apply": True,
            "quiet": True,
        }

        result = OmpEmitter().emit_agent(agent_meta)

        assert result == "adapted"
        out_path = tmp_path / ".omp" / "agents" / "roundtrip-agent.md"
        assert out_path.exists()
        fm = _read_frontmatter(out_path.read_text())
        assert fm is not None
        assert fm["name"] == "roundtrip-agent"
        assert fm["output"] == SCHEMA_SHAPED_OUTPUT_VALUE

    def test_spike_writes_only_under_tmp_path(self, tmp_path: Path):
        # Regression/isolation guard: re-run the round-trip emission and
        # confirm no real repo `.omp/agents/` dir was created as a side
        # effect — the spike's OmpEmitter().emit_agent() call always takes
        # `output_dir` from a caller-supplied path (never self-derived), so
        # passing tmp_path is sufficient by construction. This test asserts
        # that construction holds: the repo root gains no `.omp/agents/
        # roundtrip-agent.md` file.
        repo_root = Path(__file__).resolve().parents[4]
        real_out_path = repo_root / ".omp" / "agents" / "roundtrip-agent.md"

        content = agent_md(include_name=False, include_metadata_block=True)
        OmpEmitter().emit_agent(
            {
                "agent_name": "roundtrip-agent",
                "content": content,
                "output_dir": tmp_path / ".omp" / "agents",
                "apply": True,
                "quiet": True,
            }
        )

        assert not real_out_path.exists()
