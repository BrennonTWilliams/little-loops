"""Region-context tagging and context-dispatched escaping (ENH-3554)."""

from __future__ import annotations

import json
import re

import pytest

from little_loops.artifact_templates import (
    ARRAY_ITEM,
    ManifestError,
    _validate_schema_shape,
    escape_data,
    script_string_body,
)
from little_loops.cli.artifact.templatize import (
    DiscoveryResult,
    Region,
    RegionGroup,
    annotate_contexts,
    classify_region,
    derive_schema,
    merge_contexts,
)


def _cls(html: str, needle: str) -> str:
    raw = html.encode()
    i = raw.index(needle.encode())
    return classify_region(raw, i, i + len(needle.encode()))


class TestClassifyRegion:
    @pytest.mark.parametrize(
        ("html", "needle", "expected"),
        [
            ("<p>hello VAL</p>", "VAL", "text"),
            ('<div title="VAL"></div>', "VAL", "attr"),
            ('<a href="VAL">x</a>', "VAL", "url"),
            ('<img src="VAL">', "VAL", "url"),
            ("<script>var a = VAL;</script>", "VAL", "script"),
            ('<script>var a = "VAL";</script>', "VAL", "script_string"),
            ("<script>var a = 'VAL';</script>", "VAL", "script_string"),
            ("<style>p{color:VAL}</style>", "VAL", "style"),
            ('<p style="color:VAL">x</p>', "VAL", "style"),
            ("<p>a<b>VAL</b>c</p>", "a<b>VAL</b>c", "markup"),
            ("<title>VAL</title>", "VAL", "text"),
        ],
    )
    def test_contexts(self, html: str, needle: str, expected: str) -> None:
        assert _cls(html, needle) == expected

    @pytest.mark.parametrize(
        "html",
        [
            "<div title=VAL></div>",
            "<!-- VAL -->",
            "<svg><text>VAL</text></svg>",
            '<svg><a xlink:href="VAL"></a></svg>',
            "<script>var a = `VAL`;</script>",
            "<script>// VAL\n</script>",
            '<a href="VAL">x</a>'.replace("href", "srcset"),
            '<meta http-equiv="refresh" content="VAL">',
            '<iframe srcdoc="VAL"></iframe>',
            '<b onclick="VAL">x</b>',
            "<noscript>VAL</noscript>",
            '<script type="text/html">VAL</script>',
            "<![CDATA[ VAL ]]>",
        ],
    )
    def test_fail_closed(self, html: str) -> None:
        assert _cls(html, "VAL") == "markup"

    @pytest.mark.parametrize(
        "tag",
        [
            '<script src="VAL"></script>',
            '<iframe src="VAL"></iframe>',
            '<object data="VAL"></object>',
            '<embed src="VAL">',
            '<link href="VAL">',
            '<base href="VAL">',
            '<form action="VAL"></form>',
            '<button formaction="VAL">x</button>',
        ],
    )
    def test_resource_attrs_are_markup(self, tag: str) -> None:
        assert _cls(tag, "VAL") == "markup"

    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            ('<a href="https://x/VAL">x</a>', "attr"),
            ('<a href="/docs/VAL">x</a>', "attr"),
            ('<a href="#VAL">x</a>', "attr"),
            ('<a href="java VAL">x</a>'.replace(" ", ""), "markup"),
            ('<a href="VALscript:alert(1)">x</a>', "markup"),
            ('<a href="javascript:VAL">x</a>', "markup"),
        ],
    )
    def test_url_positions(self, html: str, expected: str) -> None:
        assert _cls(html, "VAL") == expected

    def test_non_ascii_offsets(self) -> None:
        html = '<p>héllo wörld ✓</p><a href="VAL">x</a><script>var s = "ünï VAL2";</script>'
        assert _cls(html, "VAL") == "url"
        assert _cls(html, "VAL2") == "script_string"

    def test_mid_multibyte_span_is_markup(self) -> None:
        raw = "<p>é</p>".encode()
        assert classify_region(raw, 4, 6) == "markup"

    def test_invalid_utf8_artifact_is_markup(self) -> None:
        assert classify_region(b"<p>\xff</p>", 3, 4) == "markup"


class TestMerge:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            ("text", "url", "url"),
            ("text", "attr", "attr"),
            ("text", "script", "markup"),
            ("script", "script_string", "markup"),
            ("url", "script_string", "markup"),
            ("style", "text", "style"),
            ("markup", "url", "markup"),
            ("url", "url", "url"),
        ],
    )
    def test_merge(self, a: str, b: str, expected: str) -> None:
        assert merge_contexts(a, b) == expected  # type: ignore[arg-type]


class TestAnnotateContexts:
    def test_regions_groups_and_merge(self) -> None:
        html = b'<p>T</p><a href="U">x</a><i>M</i><a href="M2">y</a><ul><li>G1</li><li>G2</li></ul>'
        regions = [
            Region(html.index(b">T<") + 1, html.index(b">T<") + 2, "title"),
            Region(html.index(b'"U"') + 1, html.index(b'"U"') + 2, "link"),
            Region(html.index(b">M<") + 1, html.index(b">M<") + 2, "both"),
            Region(html.index(b'"M2"') + 1, html.index(b'"M2"') + 3, "both"),
            Region(html.index(b"G1"), html.index(b"G1") + 2, "name", group="g"),
            Region(html.index(b"G2"), html.index(b"G2") + 2, "name", group="g"),
        ]
        groups = [
            RegionGroup(
                "g",
                "it",
                "items",
                html.index(b"<li>"),
                html.index(b"</ul>"),
                [
                    (html.index(b"<li>G1"), html.index(b"G1") + 7),
                    (html.index(b"<li>G2"), html.index(b"G2") + 7),
                ],
            )
        ]
        result = DiscoveryResult({}, {}, regions, groups)
        schema = derive_schema(result)
        annotate_contexts(html, result, schema)
        props = schema["properties"]
        assert props["title"]["x-ll-context"] == "text"
        assert props["link"]["x-ll-context"] == "url"
        assert props["both"]["x-ll-context"] == "url"
        assert props["items"]["items"]["properties"]["name"]["x-ll-context"] == "text"
        assert "x-ll-trusted" not in json.dumps(schema)


class TestValidationMatrix:
    @pytest.mark.parametrize(
        "context", ["text", "attr", "url", "script", "script_string", "style", "markup"]
    )
    def test_all_contexts_on_string(self, context: str) -> None:
        _validate_schema_shape({"type": "string", "x-ll-context": context})

    @pytest.mark.parametrize("context", ["text", "attr", "url", "script", "script_string"])
    def test_trusted_rejected(self, context: str) -> None:
        with pytest.raises(ManifestError):
            _validate_schema_shape(
                {"type": "string", "x-ll-context": context, "x-ll-trusted": True}
            )

    @pytest.mark.parametrize("context", ["style", "markup", None])
    def test_trusted_allowed(self, context: str | None) -> None:
        node: dict = {"type": "string", "x-ll-trusted": True}
        if context:
            node["x-ll-context"] = context
        _validate_schema_shape(node)

    def test_context_on_non_string_rejected(self) -> None:
        with pytest.raises(ManifestError):
            _validate_schema_shape({"type": "array", "x-ll-context": "markup"})


class TestEscapeDispatch:
    def test_legacy_default_is_text(self) -> None:
        assert escape_data({"k": "<b>"}) == {"k": "&lt;b&gt;"}

    def test_attr_keeps_unterminated_refs(self) -> None:
        out = escape_data({"k": "?x=1&copy=2"}, contexts={("k",): "attr"})
        assert out == {"k": "?x=1&amp;copy=2"}

    def test_script_and_script_string(self) -> None:
        payload = "</script><script>alert(1)</script>\"'\\"
        out = escape_data(
            {"a": payload, "b": payload}, contexts={("a",): "script", ("b",): "script_string"}
        )
        assert "</script" not in out["a"] and json.loads(out["a"]) == payload
        assert "</script" not in out["b"]
        # Only escape pairs may carry a quote, so neither literal delimiter can close it.
        assert not {'"', "'"} & set(re.sub(r"\\.", "", out["b"]))
        assert json.loads(f'"{out["b"]}"') == payload

    def test_script_string_line_separators(self) -> None:
        body = script_string_body("a b c&<>")
        assert " " not in body and " " not in body
        assert json.loads(f'"{body}"') == "a b c&<>"

    @pytest.mark.parametrize("context", ["style", "markup"])
    def test_style_markup_raise_unless_trusted(self, context: str) -> None:
        with pytest.raises(ValueError, match="x-ll-trusted"):
            escape_data({"k": "<b>"}, contexts={("k",): context})  # type: ignore[dict-item]
        out = escape_data(
            {"k": "<b>"},
            markup_keys=frozenset({"k"}),
            contexts={("k",): context},  # type: ignore[dict-item]
        )
        assert out == {"k": "<b>"}

    def test_trusted_ignored_for_encoded_contexts(self) -> None:
        out = escape_data({"k": "<b>"}, markup_keys=frozenset({"k"}), contexts={("k",): "attr"})
        assert out == {"k": "&lt;b&gt;"}

    def test_array_item_paths(self) -> None:
        out = escape_data({"xs": [{"u": "https://x"}]}, contexts={("xs", ARRAY_ITEM, "u"): "url"})
        assert out == {"xs": [{"u": "https://x"}]}
        with pytest.raises(ValueError, match="xs"):
            escape_data({"xs": [{"u": "javascript:1"}]}, contexts={("xs", ARRAY_ITEM, "u"): "url"})
