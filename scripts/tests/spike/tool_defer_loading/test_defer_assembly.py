"""AC suite for the FEAT-2672 `defer_loading` spike.

See `.ll/spikes/spike-FEAT-2672.md` § Acceptance Criteria -> Test Table.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.spike.tool_defer_loading.defer_assembly import (
    SEARCH_TOOL_NAME,
    SEARCH_TOOL_TYPE,
    SpikeToolEntry,
    assemble_deferred_tools,
    validates_as_search_tool_param,
    validates_as_tool_param,
)

ENTRIES = [
    SpikeToolEntry(name="a", description="tool a", input_schema={"type": "object"}),
    SpikeToolEntry(name="b", description="tool b", input_schema={"type": "object"}),
    SpikeToolEntry(name="c", description="tool c", input_schema={"type": "object"}),
]


class TestDeferLoadingAssembly:
    def test_defer_loading_flag_set_above_threshold(self):
        tools = assemble_deferred_tools(ENTRIES, defer_threshold=2)
        by_name = {t["name"]: t for t in tools if t["name"] != SEARCH_TOOL_NAME}
        assert "defer_loading" not in by_name["a"]
        assert "defer_loading" not in by_name["b"]
        assert by_name["c"]["defer_loading"] is True

    def test_tool_param_with_defer_loading_validates_against_sdk(self):
        tools = assemble_deferred_tools(ENTRIES, defer_threshold=2)
        deferred = next(t for t in tools if t.get("defer_loading"))
        assert validates_as_tool_param(deferred)

    def test_search_tool_injected_when_any_tool_deferred(self):
        tools = assemble_deferred_tools(ENTRIES, defer_threshold=2)
        search_tools = [t for t in tools if t["name"] == SEARCH_TOOL_NAME]
        assert len(search_tools) == 1
        assert search_tools[0]["type"] == SEARCH_TOOL_TYPE

    def test_no_search_tool_and_no_defer_when_below_threshold(self):
        tools = assemble_deferred_tools(ENTRIES, defer_threshold=len(ENTRIES))
        assert all(t["name"] != SEARCH_TOOL_NAME for t in tools)
        assert all("defer_loading" not in t for t in tools)
        assert [t["name"] for t in tools] == ["a", "b", "c"]

    def test_search_tool_param_validates_against_sdk(self):
        tools = assemble_deferred_tools(ENTRIES, defer_threshold=2)
        search_tool = next(t for t in tools if t["name"] == SEARCH_TOOL_NAME)
        assert validates_as_search_tool_param(search_tool)


class TestSpikeIsolation:
    def test_spike_does_not_import_tool_catalog_or_host_runner(self):
        source = Path(__file__).parent.joinpath("defer_assembly.py").read_text()
        tree = ast.parse(source)
        forbidden = {"little_loops.tool_catalog", "little_loops.host_runner"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (imported & forbidden), f"spike imports forbidden module(s): {imported & forbidden}"
