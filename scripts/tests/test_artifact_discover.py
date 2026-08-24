"""Tests for `ll-artifact templatize` Phase B (FEAT-3315): LLM region discovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from little_loops.cli.artifact.discover import (
    DiscoveryResponse,
    _resolve_offsets,
    discover_regions,
)
from little_loops.cli.artifact.templatize import RegionMapError
from little_loops.host_runner import BlockingJsonError, HostInvocation


def _make_runner(name: str = "claude-code"):
    runner = type(
        "FakeRunner",
        (),
        {
            "name": name,
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()
    return runner


class TestResolveOffsetsBasic:
    def test_non_ascii_byte_offsets(self):
        # "café" -> "caf\xc3\xa9" (é is 2 UTF-8 bytes), followed by the quoted region.
        artifact = "<p>café</p><h1>Hello</h1>\n".encode()
        raw = {"regions": [{"text": "Hello", "expr": "title"}], "groups": []}
        resolved = _resolve_offsets(artifact, raw)
        region = resolved["regions"][0]
        assert artifact[region["start"] : region["end"]].decode("utf-8") == "Hello"
        assert region["expr"] == "title"

    def test_forward_only_cursor_disambiguates_repeated_text(self):
        # Same literal text repeats; anchors pick each occurrence, and the
        # advancing cursor guarantees the second resolution can't walk
        # backward onto the first's already-consumed position.
        artifact = b"<p>A</p><span>A</span>"
        raw = {
            "regions": [
                {"text": "A", "expr": "first", "anchor_after": "</p>"},
                {"text": "A", "expr": "second", "anchor_after": "</span>"},
            ],
            "groups": [],
        }
        resolved = _resolve_offsets(artifact, raw)
        first, second = resolved["regions"]
        assert first["start"] < second["start"]
        assert artifact[first["start"] : first["end"]] == b"A"
        assert artifact[second["start"] : second["end"]] == b"A"

    def test_text_not_found_raises(self):
        artifact = b"<h1>Hello</h1>\n"
        raw = {"regions": [{"text": "Goodbye", "expr": "title"}], "groups": []}
        with pytest.raises(RegionMapError, match="not found"):
            _resolve_offsets(artifact, raw)

    def test_ambiguous_without_anchors_raises(self):
        artifact = b"<p>dup</p><p>dup</p>"
        raw = {"regions": [{"text": "dup", "expr": "title"}], "groups": []}
        with pytest.raises(RegionMapError, match="ambiguous"):
            _resolve_offsets(artifact, raw)

    def test_anchor_disambiguates_repeated_text(self):
        artifact = b"<p>dup</p><span>dup</span>"
        raw = {
            "regions": [
                {"text": "dup", "expr": "title", "anchor_before": "<span>"},
            ],
            "groups": [],
        }
        resolved = _resolve_offsets(artifact, raw)
        start = resolved["regions"][0]["start"]
        assert artifact[:start].endswith(b"<span>")

    def test_anchor_mismatch_raises(self):
        artifact = b"<h1>Hello</h1>\n"
        raw = {
            "regions": [{"text": "Hello", "expr": "title", "anchor_before": "<h2>"}],
            "groups": [],
        }
        with pytest.raises(RegionMapError, match="anchor_before/anchor_after did not match"):
            _resolve_offsets(artifact, raw)

    def test_missing_top_level_key_raises(self):
        with pytest.raises(RegionMapError, match="missing required key"):
            _resolve_offsets(b"x", {"regions": []})

    def test_unknown_top_level_key_raises(self):
        with pytest.raises(RegionMapError, match="unknown top-level key"):
            _resolve_offsets(b"x", {"regions": [], "groups": [], "data": {}})


class TestResolveOffsetsGroups:
    def _artifact(self) -> bytes:
        items = "".join(f"<li>{i}</li>" for i in range(3))
        return f"<ul>{items}</ul>\n".encode()

    def test_group_span_derived_from_first_and_last_iteration(self):
        artifact = self._artifact()
        raw = {
            "regions": [
                {"text": "0", "expr": "n", "group": "items"},
                {"text": "1", "expr": "n", "group": "items"},
                {"text": "2", "expr": "n", "group": "items"},
            ],
            "groups": [
                {
                    "id": "items",
                    "binding": "item",
                    "array_path": "items",
                    "iterations": [
                        {"text": "<li>0</li>"},
                        {"text": "<li>1</li>"},
                        {"text": "<li>2</li>"},
                    ],
                }
            ],
        }
        resolved = _resolve_offsets(artifact, raw)
        group = resolved["groups"][0]
        first_it, last_it = group["iterations"][0], group["iterations"][-1]
        assert group["start"] == first_it[0]
        assert group["end"] == last_it[1]

    def test_group_field_regions_confined_to_own_iteration(self):
        artifact = self._artifact()
        raw = {
            "regions": [
                {"text": "0", "expr": "n", "group": "items"},
                {"text": "1", "expr": "n", "group": "items"},
                {"text": "2", "expr": "n", "group": "items"},
            ],
            "groups": [
                {
                    "id": "items",
                    "binding": "item",
                    "array_path": "items",
                    "iterations": [
                        {"text": "<li>0</li>"},
                        {"text": "<li>1</li>"},
                        {"text": "<li>2</li>"},
                    ],
                }
            ],
        }
        resolved = _resolve_offsets(artifact, raw)
        group = resolved["groups"][0]
        field_regions = [r for r in resolved["regions"] if r["group"] == "items"]
        assert len(field_regions) == 3
        for region, (it_start, it_end) in zip(field_regions, group["iterations"], strict=True):
            assert it_start <= region["start"] and region["end"] <= it_end

    def test_uneven_field_count_raises(self):
        artifact = self._artifact()
        raw = {
            "regions": [
                {"text": "0", "expr": "n", "group": "items"},
                {"text": "1", "expr": "n", "group": "items"},
            ],
            "groups": [
                {
                    "id": "items",
                    "binding": "item",
                    "array_path": "items",
                    "iterations": [
                        {"text": "<li>0</li>"},
                        {"text": "<li>1</li>"},
                        {"text": "<li>2</li>"},
                    ],
                }
            ],
        }
        with pytest.raises(RegionMapError, match="not evenly divisible"):
            _resolve_offsets(artifact, raw)

    def test_region_group_references_undeclared_group_raises(self):
        artifact = b"<li>0</li>"
        raw = {
            "regions": [{"text": "0", "expr": "n", "group": "missing"}],
            "groups": [],
        }
        with pytest.raises(RegionMapError, match="not declared"):
            _resolve_offsets(artifact, raw)


class TestDiscoverRegions:
    def test_happy_path_returns_response(self):
        raw = {
            "regions": [{"text": "Hello", "expr": "title"}],
            "groups": [],
        }
        with (
            patch("little_loops.cli.artifact.discover.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.discover.run_blocking_json", return_value=raw),
        ):
            response = discover_regions(b"<h1>Hello</h1>\n", "# Hello\n", config=None)
        assert isinstance(response, DiscoveryResponse)
        assert response.raw == raw
        assert response.host == "claude-code"
        assert response.result.regions[0].expr == "title"

    def test_missing_required_key_raises(self):
        malformed = {"regions": []}
        with (
            patch("little_loops.cli.artifact.discover.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.discover.run_blocking_json", return_value=malformed),
        ):
            with pytest.raises(RegionMapError, match="missing expected keys"):
                discover_regions(b"<h1>Hello</h1>\n", "# Hello\n", config=None)

    def test_unknown_key_raises(self):
        malformed = {"regions": [], "groups": [], "data": {}}
        with (
            patch("little_loops.cli.artifact.discover.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.discover.run_blocking_json", return_value=malformed),
        ):
            with pytest.raises(RegionMapError, match="unknown top-level key"):
                discover_regions(b"<h1>Hello</h1>\n", "# Hello\n", config=None)

    def test_host_failure_translated_to_region_map_error(self):
        with (
            patch("little_loops.cli.artifact.discover.resolve_host", return_value=_make_runner()),
            patch(
                "little_loops.cli.artifact.discover.run_blocking_json",
                side_effect=BlockingJsonError("boom", {"error": "boom"}),
            ),
        ):
            with pytest.raises(RegionMapError, match="discovery call failed"):
                discover_regions(b"<h1>Hello</h1>\n", "# Hello\n", config=None)

    def test_resolution_failure_carries_raw_response(self):
        raw = {"regions": [{"text": "Goodbye", "expr": "title"}], "groups": []}
        with (
            patch("little_loops.cli.artifact.discover.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.discover.run_blocking_json", return_value=raw),
        ):
            with pytest.raises(RegionMapError) as exc_info:
                discover_regions(b"<h1>Hello</h1>\n", "# Hello\n", config=None)
        assert getattr(exc_info.value, "raw", None) == raw
