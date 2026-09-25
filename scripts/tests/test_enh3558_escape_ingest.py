"""Tests for ENH-3558: escape-by-default ingest for template data and extract output."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from little_loops.artifact_templates import (
    ARRAY_ITEM,
    ArtifactTemplate,
    ManifestError,
    _validate_schema_shape,
    escape_data,
    schema_annotation_paths,
    schema_context_paths,
    strip_schema_annotations,
)
from little_loops.cli.artifact.extract import ExtractError, extract_data
from little_loops.host_runner import HostInvocation


class TestEscapeData:
    def test_idempotent_and_decodes_terminated_refs(self) -> None:
        for raw in ("Tom &amp; Jerry", "Tom & Jerry"):
            assert escape_data({"k": raw}) == {"k": "Tom &amp; Jerry"}
        once = escape_data({"k": "a<b>\"'"})
        assert escape_data(once) == once

    def test_unterminated_refs_not_decoded(self) -> None:
        out = escape_data({"a": "a=1&not=2", "b": "a&copy=1", "c": "&notes"})
        assert out == {"a": "a=1&amp;not=2", "b": "a&amp;copy=1", "c": "&amp;notes"}

    def test_non_strings_pass_through_and_input_not_mutated(self) -> None:
        data = {"n": 1, "f": 1.5, "b": True, "z": None, "s": "<x>"}
        out = escape_data(data)
        assert out == {"n": 1, "f": 1.5, "b": True, "z": None, "s": "&lt;x&gt;"}
        assert data["s"] == "<x>"

    def test_markup_keys_verbatim(self) -> None:
        out = escape_data({"js": "<b>", "t": "<b>"}, markup_keys=frozenset({"js"}))
        assert out == {"js": "<b>", "t": "&lt;b&gt;"}

    def test_nested_tuple_paths(self) -> None:
        data = {"items": [{"body": "<i>", "title": "<i>"}]}
        out = escape_data(data, markup_keys=frozenset({("items", ARRAY_ITEM, "body")}))
        assert out == {"items": [{"body": "<i>", "title": "&lt;i&gt;"}]}

    def test_string_spelled_path_does_not_inherit_trust(self) -> None:
        trusted = frozenset({("items", ARRAY_ITEM, "body")})
        out = escape_data({"items[].body": "<i>", "items.body": "<i>"}, markup_keys=trusted)
        assert out == {"items[].body": "&lt;i&gt;", "items.body": "&lt;i&gt;"}

    def test_mapping_keys_escaped(self) -> None:
        assert escape_data({"g": {"<b>k</b>": "v"}}) == {"g": {"&lt;b&gt;k&lt;/b&gt;": "v"}}

    @pytest.mark.parametrize(
        "value",
        [
            "javascript:alert(1)",
            " JavaScript:alert(1)",
            "java\tscript:alert(1)",
            "java&#9;script:alert(1)",
            "javascript&#58;alert(1)",
            "javascript&colon;alert(1)",
            "data:text/html,x",
            "vbscript:x",
        ],
    )
    def test_url_rule_rejects(self, value: str) -> None:
        with pytest.raises(ValueError, match="link"):
            escape_data({"link": value}, contexts={("link",): "url"})

    @pytest.mark.parametrize(
        ("value", "stored"),
        [
            ("https://x", "https://x"),
            ("https://x/?a=1&not=2", "https://x/?a=1&amp;not=2"),
            ("mailto:a@b", "mailto:a@b"),
            ("/rel/path", "/rel/path"),
            ("#frag", "#frag"),
        ],
    )
    def test_url_rule_accepts(self, value: str, stored: str) -> None:
        out = escape_data({"link": value}, contexts={("link",): "url"})
        assert out == {"link": stored}


class TestAnnotations:
    def _node(self, **kw: object) -> dict:
        return {"type": "string", **kw}

    def test_accepts_valid(self) -> None:
        _validate_schema_shape(self._node(**{"x-ll-context": "url"}))
        _validate_schema_shape(self._node(**{"x-ll-context": "text"}))
        _validate_schema_shape(self._node(**{"x-ll-trusted": True}))
        _validate_schema_shape(self._node(**{"x-ll-trusted": False}))

    @pytest.mark.parametrize(
        "schema",
        [
            {"type": "string", "x-ll-context": "bogus"},
            {"type": "number", "x-ll-context": "url"},
            {"type": "number", "x-ll-trusted": True},
            {"type": "string", "x-ll-trusted": "true"},
            {"type": "string", "x-ll-trusted": True, "x-ll-context": "url"},
        ],
    )
    def test_rejects_invalid(self, schema: dict) -> None:
        with pytest.raises(ManifestError):
            _validate_schema_shape(schema)

    def test_paths_and_strip(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "u": {"type": "string", "x-ll-context": "url"},
                "list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"body": {"type": "string", "x-ll-trusted": True}},
                    },
                },
            },
        }
        assert schema_annotation_paths(schema) == {("list", ARRAY_ITEM, "body")}
        assert schema_context_paths(schema) == {("u",): "url"}
        assert "x-ll-" not in json.dumps(strip_schema_annotations(schema))
        assert "x-ll-trusted" in json.dumps(schema)


_SCHEMA = {
    "type": "object",
    "required": ["title"],
    "properties": {
        "title": {"type": "string", "enum": ["A & B", "C"]},
        "note": {"type": "string"},
        "link": {"type": "string", "x-ll-context": "url"},
        "raw": {"type": "string", "x-ll-trusted": True},
    },
}


def _run(tmp_path: Path, response: dict) -> tuple[dict, dict]:
    template = ArtifactTemplate(
        root=tmp_path,
        manifest={
            "name": "t",
            "version": 1,
            "renderer": "jinja2",
            "output": "o.html",
            "data_schema": _SCHEMA,
            "extraction": {"prompt": "Extract"},
        },
    )
    source = tmp_path / "s.md"
    source.write_text("src")
    config = SimpleNamespace(artifacts=SimpleNamespace(templatize_max_input_bytes=10000))
    captured: dict = {}

    def _build(self, *, prompt, model=None, json_schema=None):
        captured["prompt"] = prompt
        captured["schema"] = json_schema
        return HostInvocation(binary="claude", args=["-p", prompt])

    runner = type("R", (), {"name": "claude-code", "build_blocking_json": _build})()
    with (
        patch("little_loops.cli.artifact.extract.resolve_host", return_value=runner),
        patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=response),
    ):
        data, _ = extract_data(template, source, config, model=None, timeout=1)
    return data, captured


class TestExtractEscaping:
    def test_hostile_output_escaped_and_annotations_hidden(self, tmp_path: Path) -> None:
        data, captured = _run(
            tmp_path,
            {
                "title": "A & B",  # enum match must survive (validate before escape)
                "note": "<script>alert(1)</script>",
                "raw": "<b>ok</b>",
                "extra": {"<i>": "<u>"},
            },
        )
        assert data["title"] == "A &amp; B"
        assert data["note"] == "&lt;script&gt;alert(1)&lt;/script&gt;"
        assert data["raw"] == "<b>ok</b>"
        assert data["extra"] == {"&lt;i&gt;": "&lt;u&gt;"}
        assert "x-ll-" not in captured["prompt"]
        assert "x-ll-" not in json.dumps(captured["schema"])
        assert "decoded" in captured["prompt"]

    def test_disallowed_url_raises_extract_error(self, tmp_path: Path) -> None:
        with pytest.raises(ExtractError, match="link"):
            _run(tmp_path, {"title": "C", "link": "javascript:alert(1)"})


class TestDashboardBoundary:
    def test_dashboard_marker_keys_and_html_escape_gone(self) -> None:
        from little_loops.cli.artifact import dashboard

        assert "serve_events_url" not in dashboard.DASHBOARD_MARKUP_KEYS
        assert "sql_wasm_js" in dashboard.DASHBOARD_MARKUP_KEYS
        src = Path(dashboard.__file__).read_text()
        assert "html.escape(" not in src

    def _build(self, tmp_path: Path, **kw):
        from little_loops.cli.artifact.dashboard import build_dashboard_html
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        return build_dashboard_html(
            db_path=tmp_path / ".ll" / "history.db",
            config=BRConfig(tmp_path),
            mode="shareable",
            **kw,
        )

    def test_hostile_filter_values_escaped(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.dashboard import ServeContext

        payload = "<img src=x onerror=alert(1)>"
        result = self._build(
            tmp_path,
            tables=[payload],
            since_iso=payload,
            serve_context=ServeContext(events_url="http://127.0.0.1:9/t/events"),
        )
        assert payload not in result.html
        assert "&lt;img src=x onerror=alert(1)&gt;" in result.html

    def test_javascript_events_url_rejected(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.dashboard import ServeContext

        with pytest.raises(ValueError, match="serve_events_url"):
            self._build(
                tmp_path,
                tables=["sessions"],
                since_iso=None,
                serve_context=ServeContext(events_url="javascript:alert(1)"),
            )

    def test_live_fragment_still_autoescapes(self) -> None:
        from little_loops.cli.artifact.dashboard import render_live_fragment

        out = render_live_fragment({"event": "state_enter", "state": "<script>x</script>"})
        assert out is None or "<script>x</script>" not in out
