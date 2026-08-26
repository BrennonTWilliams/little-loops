"""Tests for `ll-artifact templatize` Phase A (FEAT-3314): deterministic templating."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.artifact_templates import load_manifest
from little_loops.cli.artifact import main_artifact
from little_loops.cli.artifact.templatize import (
    DiscoveryResult,
    Region,
    RegionGroup,
    RegionMapError,
    SpliceError,
    _alias_preferred_candidate_map,
    _check_lift_preconditions,
    _is_css_value_position,
    _parse_region_map,
    apply_regions,
    build_manifest,
    derive_schema,
    escape_literal_delimiters,
    extract_data,
    lift_token_literals,
    load_regions,
    promote,
    report_token_literals,
    verify_lift_renders,
    verify_lift_reversible,
)
from little_loops.host_runner import HostInvocation


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def load_regions_from_dict(resolved: dict) -> DiscoveryResult:
    return _parse_region_map(resolved, where="test")


def _fake_host_runner(name: str = "claude-code"):
    return type(
        "FakeRunner",
        (),
        {
            "name": name,
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()


def _write_regions(path: Path, regions=None, groups=None) -> Path:
    payload = {"regions": regions or [], "groups": groups or []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestLoadRegions:
    def test_minimal_map_loads(self, tmp_path):
        path = _write_regions(
            tmp_path / "map.json", regions=[{"start": 0, "end": 3, "expr": "title"}]
        )
        result = load_regions(path)
        assert result.regions == [Region(start=0, end=3, expr="title")]
        assert result.data == {}
        assert result.data_schema == {}

    def test_anchors_optional(self, tmp_path):
        path = _write_regions(
            tmp_path / "map.json", regions=[{"start": 0, "end": 3, "expr": "title"}]
        )
        result = load_regions(path)
        assert result.regions[0].anchor_before is None
        assert result.regions[0].anchor_after is None

    def test_rejects_unknown_top_level_key(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(json.dumps({"regions": [], "data": {}}), encoding="utf-8")
        with pytest.raises(RegionMapError, match="unknown top-level key"):
            load_regions(path)

    def test_rejects_data_schema_key(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(json.dumps({"regions": [], "data_schema": {}}), encoding="utf-8")
        with pytest.raises(RegionMapError, match="unknown top-level key"):
            load_regions(path)

    def test_rejects_missing_required_field(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(json.dumps({"regions": [{"start": 0, "end": 3}]}), encoding="utf-8")
        with pytest.raises(RegionMapError, match="missing required field"):
            load_regions(path)

    def test_rejects_non_integer_offset(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(
            json.dumps({"regions": [{"start": "0", "end": 3, "expr": "title"}]}), encoding="utf-8"
        )
        with pytest.raises(RegionMapError, match="integer"):
            load_regions(path)

    def test_rejects_unknown_key_on_region(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(
            json.dumps({"regions": [{"start": 0, "end": 3, "expr": "t", "bogus": 1}]}),
            encoding="utf-8",
        )
        with pytest.raises(RegionMapError, match="unknown key"):
            load_regions(path)


class TestExtractData:
    def test_simple_region(self):
        artifact = b"<h1>Hello</h1>"
        result = DiscoveryResult(
            data_schema={}, data={}, regions=[Region(start=4, end=9, expr="title")], groups=[]
        )
        assert extract_data(artifact, result) == {"title": "Hello"}

    def test_dotted_expr_nests(self):
        artifact = b"Alice"
        result = DiscoveryResult(
            data_schema={}, data={}, regions=[Region(start=0, end=5, expr="user.name")], groups=[]
        )
        assert extract_data(artifact, result) == {"user": {"name": "Alice"}}

    def test_duplicate_expr_identical_bytes_collapses(self):
        artifact = b"XX"
        result = DiscoveryResult(
            data_schema={},
            data={},
            regions=[
                Region(start=0, end=1, expr="letter"),
                Region(start=1, end=2, expr="letter"),
            ],
            groups=[],
        )
        assert extract_data(artifact, result) == {"letter": "X"}

    def test_duplicate_expr_differing_bytes_errors(self):
        artifact = b"XY"
        result = DiscoveryResult(
            data_schema={},
            data={},
            regions=[
                Region(start=0, end=1, expr="letter"),
                Region(start=1, end=2, expr="letter"),
            ],
            groups=[],
        )
        with pytest.raises(SpliceError, match="duplicate expr"):
            extract_data(artifact, result)

    def test_group_extracts_array(self):
        artifact = b"<li>A</li><li>B</li>"
        group = RegionGroup(
            id="cards",
            binding="card",
            array_path="cards",
            start=0,
            end=20,
            iterations=[(0, 10), (10, 20)],
        )
        regions = [
            Region(start=4, end=5, expr="text", group="cards"),
            Region(start=14, end=15, expr="text", group="cards"),
        ]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        assert extract_data(artifact, result) == {"cards": [{"text": "A"}, {"text": "B"}]}


class TestDeriveSchema:
    def test_simple_string_property(self):
        result = DiscoveryResult(
            data_schema={}, data={}, regions=[Region(start=0, end=1, expr="title")], groups=[]
        )
        schema = derive_schema(result)
        assert schema == {"type": "object", "properties": {"title": {"type": "string"}}}

    def test_group_becomes_array_of_object(self):
        group = RegionGroup(
            id="cards", binding="card", array_path="cards", start=0, end=1, iterations=[(0, 1)]
        )
        regions = [Region(start=0, end=1, expr="text", group="cards")]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        schema = derive_schema(result)
        assert schema["properties"]["cards"]["type"] == "array"
        assert schema["properties"]["cards"]["items"]["properties"]["text"] == {"type": "string"}


class TestEscapeLiteralDelimiters:
    def test_no_delimiters_passthrough(self):
        assert escape_literal_delimiters(b"plain text") == b"plain text"

    def test_wraps_literal_variable_delimiter(self):
        out = escape_literal_delimiters(b'var a = "[[= x =]]";')
        assert out == b'var a = "[[% raw %]][[= x =]][[% endraw %]]";'

    def test_endraw_is_unescapable(self):
        with pytest.raises(SpliceError, match="endraw"):
            escape_literal_delimiters(b"lit [[% endraw %]] more")


class TestApplyRegions:
    def test_simple_substitution(self):
        artifact = b"<h1>Hello</h1>"
        result = DiscoveryResult(
            data_schema={}, data={}, regions=[Region(start=4, end=9, expr="title")], groups=[]
        )
        out = apply_regions(artifact, result)
        assert out == b"<h1>[[= title =]]</h1>"

    def test_overlapping_spans_error(self):
        artifact = b"abcdef"
        result = DiscoveryResult(
            data_schema={},
            data={},
            regions=[
                Region(start=0, end=3, expr="a"),
                Region(start=2, end=5, expr="b"),
            ],
            groups=[],
        )
        with pytest.raises(SpliceError, match="overlaps"):
            apply_regions(artifact, result)

    def test_out_of_bounds_span_errors(self):
        artifact = b"abc"
        result = DiscoveryResult(
            data_schema={}, data={}, regions=[Region(start=0, end=10, expr="a")], groups=[]
        )
        with pytest.raises(SpliceError, match="out of bounds"):
            apply_regions(artifact, result)

    def test_mid_line_repeat_group_round_trips(self):
        artifact = b"<p><span>1</span><span>2</span></p>"
        group = RegionGroup(
            id="spans",
            binding="item",
            array_path="items",
            start=3,
            end=31,
            iterations=[(3, 17), (17, 31)],
        )
        regions = [
            Region(start=9, end=10, expr="text", group="spans"),
            Region(start=23, end=24, expr="text", group="spans"),
        ]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        out = apply_regions(artifact, result)
        assert out == (
            b"<p>[[% for item in items %]]<span>[[= item.text =]]</span>[[% endfor %]]</p>"
        )

    def test_own_line_repeat_group_round_trips(self):
        artifact = b"<ul>\n  <li>1</li>\n  <li>2</li>\n</ul>"
        # iteration spans cover "  <li>1</li>" and "  <li>2</li>" (indent included)
        iter1_start = artifact.index(b"  <li>1")
        iter1_end = iter1_start + len(b"  <li>1</li>")
        iter2_start = artifact.index(b"  <li>2")
        iter2_end = iter2_start + len(b"  <li>2</li>")
        group = RegionGroup(
            id="items",
            binding="li",
            array_path="items",
            start=iter1_start,
            end=iter2_end,
            iterations=[(iter1_start, iter1_end), (iter2_start, iter2_end)],
        )
        text1_start = artifact.index(b"1", iter1_start)
        text2_start = artifact.index(b"2", iter2_start)
        regions = [
            Region(start=text1_start, end=text1_start + 1, expr="n", group="items"),
            Region(start=text2_start, end=text2_start + 1, expr="n", group="items"),
        ]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        out = apply_regions(artifact, result)
        assert out == (
            b"<ul>\n  [[% for li in items %]]\n  <li>[[= li.n =]]</li>\n  [[% endfor %]]\n</ul>"
        )

    def test_mismatched_iteration_literal_text_errors(self):
        artifact = b'<li id="a">1</li><li id="b">2</li>'
        group = RegionGroup(
            id="items",
            binding="li",
            array_path="items",
            start=0,
            end=34,
            iterations=[(0, 17), (17, 34)],
        )
        regions = [
            Region(start=11, end=12, expr="n", group="items"),
            Region(start=28, end=29, expr="n", group="items"),
        ]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        with pytest.raises(SpliceError, match="literal text"):
            apply_regions(artifact, result)

    def test_mixed_boundary_errors(self):
        # whitespace-only prefix but no following newline after group.end
        artifact = b"A\n  <li>1</li><li>2</li>X"
        iter1_start = artifact.index(b"<li>1")
        iter1_end = iter1_start + len(b"<li>1</li>")
        iter2_start = iter1_end
        iter2_end = iter2_start + len(b"<li>2</li>")
        group = RegionGroup(
            id="items",
            binding="li",
            array_path="items",
            start=iter1_start,
            end=iter2_end,
            iterations=[(iter1_start, iter1_end), (iter2_start, iter2_end)],
        )
        regions = [
            Region(start=iter1_start + 4, end=iter1_start + 5, expr="n", group="items"),
            Region(start=iter2_start + 4, end=iter2_start + 5, expr="n", group="items"),
        ]
        result = DiscoveryResult(data_schema={}, data={}, regions=regions, groups=[group])
        with pytest.raises(SpliceError, match="mixed block-tag boundary"):
            apply_regions(artifact, result)


class TestPromote:
    def test_promotes_new_output(self, tmp_path):
        tmp_dir = tmp_path / "out.llat.tmp-1"
        tmp_dir.mkdir()
        (tmp_dir / "marker.txt").write_text("x")
        out_dir = tmp_path / "out.llat"
        promote(tmp_dir, out_dir, force=False)
        assert (out_dir / "marker.txt").is_file()
        assert not tmp_dir.exists()

    def test_errors_on_existing_without_force(self, tmp_path):
        tmp_dir = tmp_path / "out.llat.tmp-1"
        tmp_dir.mkdir()
        out_dir = tmp_path / "out.llat"
        out_dir.mkdir()
        (out_dir / "existing.txt").write_text("x")
        with pytest.raises(SpliceError, match="already exists"):
            promote(tmp_dir, out_dir, force=False)
        assert (out_dir / "existing.txt").is_file()

    def test_force_overwrites_nonempty_existing(self, tmp_path):
        tmp_dir = tmp_path / "out.llat.tmp-1"
        tmp_dir.mkdir()
        (tmp_dir / "new.txt").write_text("new")
        out_dir = tmp_path / "out.llat"
        out_dir.mkdir()
        (out_dir / "old.txt").write_text("old")
        promote(tmp_dir, out_dir, force=True)
        assert (out_dir / "new.txt").is_file()
        assert not (out_dir / "old.txt").exists()
        assert not tmp_dir.exists()
        leftover = list(tmp_path.glob("out.llat.bak-*"))
        assert leftover == []


class TestBuildManifest:
    def test_builds_expected_shape(self):
        schema = {"type": "object", "properties": {"title": {"type": "string"}}}
        manifest = build_manifest(
            name="arch-review",
            output="index.html",
            schema=schema,
            source=Path("docs/ARCHITECTURE.md"),
            extraction={"method": "regions"},
        )
        assert manifest["name"] == "arch-review"
        assert manifest["version"] == 1
        assert manifest["renderer"] == "jinja2"
        assert manifest["output"] == "index.html"
        assert manifest["data_schema"] == schema
        assert "theme" not in manifest

    def test_rejects_reserved_ll_key(self):
        schema = {"type": "object", "properties": {"ll": {"type": "string"}}}
        with pytest.raises(SpliceError, match="reserved"):
            build_manifest(
                name="x", output="index.html", schema=schema, source=Path("s.md"), extraction={}
            )


def _make_config(project_root: Path):
    from little_loops.config.core import BRConfig

    return BRConfig(project_root)


class TestCmdTemplatizeEndToEnd:
    def _run(self, tmp_path, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def test_end_to_end_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 0
        assert out_dir.is_dir()
        manifest = load_manifest(out_dir)
        assert manifest["output"] == "index.html"
        data = json.loads((out_dir / "data.json").read_text())
        assert data == {"title": "Hello"}
        body = (out_dir / "template.html.j2").read_text()
        assert "[[= title =]]" in body

        # resolvable by name via `render`
        render_out = tmp_path / "rendered"
        code2 = self._run(
            tmp_path,
            ["render", "greet", "-o", str(render_out)],
        )
        assert code2 == 0
        assert (render_out / "index.html").read_bytes() == artifact.read_bytes()

    def test_crlf_artifact_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"A\r\n[[= x =]]\r\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(tmp_path / "map.json", regions=[])
        out_dir = tmp_path / "artifacts" / "templates" / "bad.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 1
        assert not out_dir.exists()
        assert not list(out_dir.parent.glob("bad.llat.tmp-*"))
        assert not list(out_dir.parent.glob("bad.llat.rejected"))

    def test_extensionless_artifact_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "README", b"hello\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(tmp_path / "map.json", regions=[])
        out_dir = tmp_path / "artifacts" / "templates" / "bad.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 1

    def test_roundtrip_rejection_writes_rejected_dir_and_preserves_existing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        # A region whose bytes will not round-trip: expr contains a space, harmless,
        # but we force a mismatch by pointing at the wrong span (extracts "Hell" but
        # leaves stray "o" outside the region — round trip is exact by construction,
        # so instead force rejection by corrupting the manifest schema indirectly via
        # a region that maps to reserved key None; simplest: monkeypatch verify to fail).
        import little_loops.cli.artifact.templatize as templatize_mod

        monkeypatch.setattr(
            templatize_mod, "verify_round_trip", lambda *a, **k: "--- fake diff ---"
        )

        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"
        out_dir.mkdir(parents=True)
        (out_dir / "sentinel.txt").write_text("keep me")

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
                "--force",
            ],
        )
        assert code == 2
        assert (out_dir / "sentinel.txt").is_file()
        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        assert (rejected_dir / "roundtrip.diff").read_text() == "--- fake diff ---"
        assert not list(out_dir.parent.glob("greet.llat.tmp-*"))

    def test_existing_output_without_force_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"
        out_dir.mkdir(parents=True)

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 1

    def test_force_reruns_over_populated_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"
        out_dir.mkdir(parents=True)
        (out_dir / "stale.txt").write_text("old")

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
                "--force",
            ],
        )
        assert code == 0
        assert not (out_dir / "stale.txt").exists()
        assert not list(out_dir.parent.glob("greet.llat.tmp-*"))
        assert not list(out_dir.parent.glob("greet.llat.bak-*"))

    def test_stale_tmp_and_bak_siblings_swept(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"
        out_dir.parent.mkdir(parents=True)
        stale_tmp = out_dir.parent / "greet.llat.tmp-999"
        stale_bak = out_dir.parent / "greet.llat.bak-999"
        stale_tmp.mkdir()
        stale_bak.mkdir()

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 0
        assert not stale_tmp.exists()
        assert not stale_bak.exists()

    def test_non_ascii_round_trips(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        content = "<p>Em—dash “quote” Title</p>\n".encode()
        artifact = _write(tmp_path / "out" / "index.html", content)
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        start = content.index(b"Title")
        end = start + len(b"Title")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": start, "end": end, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "nonascii.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 0

    def test_html_entities_preserved_in_data(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        content = b"<p>Terms &amp; Conditions</p>\n"
        artifact = _write(tmp_path / "out" / "index.html", content)
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        start = content.index(b"Terms")
        end = content.index(b"</p>")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": start, "end": end, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "entities.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 0
        data = json.loads((out_dir / "data.json").read_text())
        assert data["title"] == "Terms &amp; Conditions"

    def test_multi_dot_extension_derives_from_suffix(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "report.min.html", b"<h1>Hi</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(tmp_path / "map.json", regions=[])
        out_dir = tmp_path / "artifacts" / "templates" / "report.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ],
        )
        assert code == 0
        assert (out_dir / "template.html.j2").is_file()

    def test_repeat_group_n5_round_trips(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        items = "".join(f"<li>{i}</li>" for i in range(5))
        content = f"<ul>{items}</ul>\n".encode()
        artifact = _write(tmp_path / "out" / "index.html", content)
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")

        regions = []
        cursor = content.index(b"<li>")
        for i in range(5):
            start = content.index(b"<li>", cursor) + len(b"<li>")
            end = start + len(str(i))
            regions.append({"start": start, "end": end, "expr": "n", "group": "items"})
            cursor = end

        group_start = content.index(b"<li>")
        group_end = content.index(b"</ul>")
        iterations = []
        cursor = group_start
        for i in range(5):
            it_start = content.index(b"<li>", cursor)
            it_end = it_start + len(f"<li>{i}</li>")
            iterations.append([it_start, it_end])
            cursor = it_end

        regions_path = _write_regions(
            tmp_path / "map.json",
            regions=regions,
            groups=[
                {
                    "id": "items",
                    "binding": "item",
                    "array_path": "items",
                    "start": group_start,
                    "end": group_end,
                    "iterations": iterations,
                }
            ],
        )
        out_dir = tmp_path / "artifacts" / "templates" / "n5.llat"

        code = self._run(
            tmp_path,
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions_path),
            ],
        )
        assert code == 0
        data = json.loads((out_dir / "data.json").read_text())
        assert data["items"] == [{"n": str(i)} for i in range(5)]
        body = (out_dir / "template.html.j2").read_text()
        assert "[[% for item in items %]]" in body
        assert body.count("<li>") == 1


class TestCmdTemplatizeDiscoveryBranch:
    """FEAT-3315: the default (no `--regions`) LLM-discovery branch."""

    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def _make_response(self, artifact: bytes):
        from little_loops.cli.artifact.discover import DiscoveryResponse

        raw = {"regions": [{"text": "Hello", "expr": "title"}], "groups": []}
        resolved = {
            "regions": [{"start": 4, "end": 9, "expr": "title", "group": None}],
            "groups": [],
        }
        result = load_regions_from_dict(resolved)
        return DiscoveryResponse(
            result=result, raw=raw, resolved=resolved, host="claude-code", model="sonnet"
        )

    def test_happy_path_promotes_and_round_trips(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with patch(
            "little_loops.cli.artifact.discover.discover_regions",
            return_value=self._make_response(artifact.read_bytes()),
        ):
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        assert code == 0
        assert out_dir.is_dir()
        manifest = load_manifest(out_dir)
        assert manifest["extraction"]["method"] == "llm_discovery"
        assert manifest["extraction"]["host"] == "claude-code"
        assert manifest["extraction"]["model"] == "sonnet"
        assert "theme" not in manifest
        data = json.loads((out_dir / "data.json").read_text())
        assert data == {"title": "Hello"}

    def test_malformed_response_raises_not_silent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with (
            patch(
                "little_loops.cli.artifact.discover.resolve_host",
                return_value=_fake_host_runner(),
            ),
            patch(
                "little_loops.cli.artifact.discover.run_blocking_json",
                return_value={"regions": []},  # missing required 'groups' key
            ),
        ):
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        assert code == 1
        assert not out_dir.exists()

    def test_input_size_ceiling_no_host_call(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"artifacts": {"templatize_max_input_bytes": 10}}), encoding="utf-8"
        )
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with patch("little_loops.cli.artifact.discover.resolve_host") as resolve_host:
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        resolve_host.assert_not_called()
        assert code == 1
        assert not out_dir.exists()

    def test_missing_source_no_host_call(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = tmp_path / "docs" / "MISSING.md"
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with patch("little_loops.cli.artifact.discover.resolve_host") as resolve_host:
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        resolve_host.assert_not_called()
        assert code == 1
        assert not out_dir.exists()

    def test_rejected_dir_preserved_on_exit1_splice_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        from little_loops.cli.artifact.discover import DiscoveryResponse

        # Overlapping spans -> apply_regions raises SpliceError downstream of the call.
        raw = {
            "regions": [
                {"text": "Hello", "expr": "a"},
                {"text": "Hello", "expr": "b"},
            ],
            "groups": [],
        }
        resolved = {
            "regions": [
                {"start": 4, "end": 9, "expr": "a", "group": None},
                {"start": 4, "end": 9, "expr": "b", "group": None},
            ],
            "groups": [],
        }
        result = load_regions_from_dict(resolved)
        response = DiscoveryResponse(
            result=result, raw=raw, resolved=resolved, host="claude-code", model="sonnet"
        )

        with patch("little_loops.cli.artifact.discover.discover_regions", return_value=response):
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        assert code == 1
        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        assert (rejected_dir / "discovery.json").is_file()
        assert (rejected_dir / "regions.json").is_file()
        assert json.loads((rejected_dir / "discovery.json").read_text()) == raw

    def test_rejected_dir_preserved_on_exit2_roundtrip_rejection(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        import little_loops.cli.artifact.templatize as templatize_mod

        # Splicing is byte-exact by construction (FEAT-3315 § Decision Rationale ->
        # Offset resolution) — force rejection the same way Phase A's own test does.
        monkeypatch.setattr(
            templatize_mod, "verify_round_trip", lambda *a, **k: "--- fake diff ---"
        )

        from little_loops.cli.artifact.discover import DiscoveryResponse

        raw = {"regions": [{"text": "Hello", "expr": "title"}], "groups": []}
        resolved = {
            "regions": [{"start": 4, "end": 9, "expr": "title", "group": None}],
            "groups": [],
        }
        result = load_regions_from_dict(resolved)
        response = DiscoveryResponse(
            result=result, raw=raw, resolved=resolved, host="claude-code", model="sonnet"
        )

        with patch("little_loops.cli.artifact.discover.discover_regions", return_value=response):
            code = self._run(["templatize", str(artifact), str(source), "-o", str(out_dir)])
        assert code == 2
        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        assert (rejected_dir / "roundtrip.diff").is_file()
        assert (rejected_dir / "discovery.json").is_file()
        assert (rejected_dir / "regions.json").is_file()

    def test_regions_flag_takes_precedence_no_host_call(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with patch("little_loops.cli.artifact.discover.resolve_host") as resolve_host:
            code = self._run(
                [
                    "templatize",
                    str(artifact),
                    str(source),
                    "-o",
                    str(out_dir),
                    "--regions",
                    str(regions),
                ]
            )
        resolve_host.assert_not_called()
        assert code == 0

    def test_templatize_module_imports_nothing_from_host_runner_or_anthropic(self) -> None:
        import ast

        module_path = (
            Path(__file__).parent.parent / "little_loops" / "cli" / "artifact" / "templatize.py"
        )
        tree = ast.parse(module_path.read_text())
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        assert not any("host_runner" in name for name in imported_modules)
        assert not any("anthropic" in name for name in imported_modules)


# ---------------------------------------------------------------------------
# report_token_literals / unlifted-tokens.json (FEAT-3316)
# ---------------------------------------------------------------------------


def _write_design_tokens(
    project_root: Path,
    *,
    primitives: dict | None = None,
    semantic: dict | None = None,
    theme: dict | None = None,
    theme_name: str = "dark",
) -> Path:
    """Materialize a flat-layout design-token profile under *project_root*.

    `design_tokens.enabled` defaults to True with no `.ll/ll-config.json`
    present (`DesignTokensConfig.enabled: bool = True`), so no config file
    is written here — only the token files `load_design_tokens` resolves.
    """
    token_dir = project_root / ".ll" / "design-tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "primitives.json").write_text(json.dumps(primitives or {}))
    (token_dir / "semantic.json").write_text(json.dumps(semantic or {}))
    themes_dir = token_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    (themes_dir / f"{theme_name}.json").write_text(json.dumps(theme or {}))
    return token_dir


def _make_design_tokens(resolved: dict[str, str]):
    from little_loops.design_tokens import DesignTokens

    return DesignTokens(
        primitives={},
        semantic={},
        theme={},
        resolved=resolved,
        source_path=Path("."),
    )


class TestReportTokenLiterals:
    """Unit tests for the matching rule (§ Matching rule) directly."""

    def test_reports_baked_hex_literal(self):
        tokens = _make_design_tokens({"color.brand.500": "#4F46E5"})
        result = report_token_literals("body { color: #4F46E5; }", tokens)
        assert result == [
            {"literal": "#4f46e5", "candidate_names": ["color.brand.500"], "occurrences": 1}
        ]

    def test_non_injective_reports_all_candidate_names(self):
        tokens = _make_design_tokens(
            {"color.brand.500": "#4F46E5", "color.alias.primary": "#4f46e5"}
        )
        result = report_token_literals("color: #4F46E5;", tokens)
        assert len(result) == 1
        assert result[0]["candidate_names"] == ["color.alias.primary", "color.brand.500"]

    def test_shorthand_hex_normalized_to_match(self):
        tokens = _make_design_tokens({"color.short": "#aabbcc"})
        result = report_token_literals("color: #abc;", tokens)
        assert result == [
            {"literal": "#aabbcc", "candidate_names": ["color.short"], "occurrences": 1}
        ]

    def test_substring_not_matched_as_whole_value(self):
        tokens = _make_design_tokens({"color.short": "#fff"})
        result = report_token_literals("color: #fff000;", tokens)
        assert result == []

    def test_non_color_token_values_not_reported(self):
        tokens = _make_design_tokens({"space.sm": "4px", "radius.none": "0"})
        result = report_token_literals("margin: 4px; border-radius: 0;", tokens)
        assert result == []

    def test_occurrences_counted_non_overlapping(self):
        tokens = _make_design_tokens({"color.brand.500": "#4F46E5"})
        result = report_token_literals("a { color: #4f46e5 } b { color: #4F46E5 }", tokens)
        assert result[0]["occurrences"] == 2

    def test_functional_rgb_form_matched_case_insensitive_whitespace_collapsed(self):
        tokens = _make_design_tokens({"color.brand.500": "rgb(10, 20, 30)"})
        result = report_token_literals("color: RGB(10, 20, 30);", tokens)
        assert result == [
            {
                "literal": "rgb(10, 20, 30)",
                "candidate_names": ["color.brand.500"],
                "occurrences": 1,
            }
        ]

    def test_no_matching_tokens_returns_empty(self):
        tokens = _make_design_tokens({"color.brand.500": "#4F46E5"})
        result = report_token_literals("no colors here", tokens)
        assert result == []

    def test_empty_resolved_map_returns_empty(self):
        tokens = _make_design_tokens({})
        result = report_token_literals("color: #4F46E5;", tokens)
        assert result == []


class TestCmdTemplatizeTokenReport:
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def test_report_non_empty_with_ambiguous_candidates(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_design_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}, "alias": {"500": "#4F46E5"}}},
        )
        artifact = _write(
            tmp_path / "out" / "index.html",
            b'<div style="color:#4F46E5">Hello</div>\n',
        )
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 26, "end": 31, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ]
        )
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["unlifted"]
        entry = report["unlifted"][0]
        assert entry["literal"] == "#4f46e5"
        assert sorted(entry["candidate_names"]) == ["color.alias.500", "color.brand.500"]

    def test_scan_excludes_extracted_data_region(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_design_tokens(tmp_path, primitives={"color": {"brand": {"500": "#4F46E5"}}})
        # The hex literal lives entirely inside the extracted "title" region,
        # so it is absent from the spliced template body (§ Scan input).
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>#4F46E5</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 11, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ]
        )
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["unlifted"] == []

    def test_degradation_tokens_disabled_writes_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": False}})
        )
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ]
        )
        assert code == 0
        assert not (out_dir / "unlifted-tokens.json").exists()

    def test_degradation_zero_matches_writes_empty_list_no_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        _write_design_tokens(tmp_path, primitives={"color": {"brand": {"500": "#4F46E5"}}})
        artifact = _write(tmp_path / "out" / "index.html", b"<h1>Hello</h1>\n")
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 4, "end": 9, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions),
            ]
        )
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["unlifted"] == []
        assert "unlifted" not in capsys.readouterr().err

    def test_containment_forced_failure_still_promotes_exit_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_design_tokens(tmp_path, primitives={"color": {"brand": {"500": "#4F46E5"}}})
        artifact = _write(
            tmp_path / "out" / "index.html", b'<div style="color:#4F46E5">Hello</div>\n'
        )
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(
            tmp_path / "map.json", regions=[{"start": 26, "end": 31, "expr": "title"}]
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        with patch(
            "little_loops.cli.artifact.templatize.report_token_literals",
            side_effect=RuntimeError("boom"),
        ):
            code = self._run(
                [
                    "templatize",
                    str(artifact),
                    str(source),
                    "-o",
                    str(out_dir),
                    "--regions",
                    str(regions),
                ]
            )
        assert code == 0
        assert out_dir.is_dir()
        assert (out_dir / "manifest.yaml").is_file()
        assert not (out_dir / "unlifted-tokens.json").exists()


# ---------------------------------------------------------------------------
# Fan-out verification (FEAT-3316 § Fan-out verification)
# ---------------------------------------------------------------------------

_FANOUT_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "artifact_templates" / "fanout"

# Document 1's region values (leak check) — must match
# fixtures/artifact_templates/fanout/doc1.html.
_DOC1_TITLE = "Doc1 Title"
_DOC1_DESC = "Doc1 description"
_DOC1_ITEMS = ["Item1", "Item2"]


class TestFanOutFixture:
    """Structural sanity check for the checked-in fan-out fixture set."""

    def test_fixture_files_present(self):
        assert _FANOUT_FIXTURE_DIR.is_dir()
        for name in ("doc1.html", "map.json", "doc2_data.json", "doc2_expected.html"):
            assert (_FANOUT_FIXTURE_DIR / name).is_file(), name


class TestCmdTemplatizeFanOut:
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def test_produced_template_generalizes_to_second_document(self, tmp_path, monkeypatch):
        if not _FANOUT_FIXTURE_DIR.is_dir():
            pytest.skip("fan-out fixture directory missing")
        monkeypatch.chdir(tmp_path)
        artifact_path = _write(
            tmp_path / "out" / "index.html", (_FANOUT_FIXTURE_DIR / "doc1.html").read_bytes()
        )
        source = _write(tmp_path / "docs" / "SRC.md", b"# Doc1\n")
        out_dir = tmp_path / "artifacts" / "templates" / "fanout.llat"

        # Step 1: templatize document 1 (the checked-in fixture) to produce
        # the template — a checked-in `.llat` would test the fixture, not
        # the subcommand.
        code = self._run(
            [
                "templatize",
                str(artifact_path),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(_FANOUT_FIXTURE_DIR / "map.json"),
            ]
        )
        assert code == 0

        # Step 2: render the *produced* template against document 2's
        # hand-authored data.json — structural divergence (§ Fan-out
        # verification): a different list length (3 vs. 2), an empty-string
        # region, and a region requiring JSON-escaping (quote, backslash,
        # newline).
        render_out = tmp_path / "rendered_doc2"
        with patch("little_loops.cli.artifact.discover.resolve_host") as resolve_host:
            code2 = self._run(
                [
                    "render",
                    "fanout",
                    "--data",
                    str(_FANOUT_FIXTURE_DIR / "doc2_data.json"),
                    "-o",
                    str(render_out),
                ]
            )
        resolve_host.assert_not_called()
        assert code2 == 0

        rendered = (render_out / "index.html").read_bytes().decode("utf-8")
        expected = (_FANOUT_FIXTURE_DIR / "doc2_expected.html").read_text(encoding="utf-8")
        assert rendered == expected

        # Leak assertion: none of document 1's region values survive.
        for leaked in (_DOC1_TITLE, _DOC1_DESC, *_DOC1_ITEMS):
            assert leaked not in rendered


# ---------------------------------------------------------------------------
# --lift-tokens (ENH-3319)
# ---------------------------------------------------------------------------


def _write_simple_lift_tokens(project_root: Path) -> None:
    """A single, unambiguous alias -> primitive pair: #4F46E5 -> color.brand.500.

    Deliberately theme-invariant (no theme-layer override) so it can drive
    the hard-precondition tests without also depending on light/dark value
    differences.
    """
    token_dir = project_root / ".ll" / "design-tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "primitives.json").write_text(json.dumps({"color": {"raw": {"500": "#4F46E5"}}}))
    (token_dir / "semantic.json").write_text(
        json.dumps({"color": {"brand": {"500": "{color.raw.500}"}}})
    )
    themes_dir = token_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    (themes_dir / "dark.json").write_text("{}")
    (themes_dir / "light.json").write_text("{}")


def _write_themed_lift_tokens(project_root: Path) -> None:
    """Light/dark-divergent tokens mirroring the profile measured in the issue.

    color.surface.primary: #fdfbf6 (light) / #0d0b08 (dark, via theme
    override) — an unambiguous alias whose light and dark values differ.
    color.text.inverse also aliases the light primitive, so #fdfbf6 has TWO
    alias candidates (ambiguous) while #0d0b08 has exactly one.
    color.border.subtle: #e8dcc4 — a single unambiguous alias to a
    primitive, theme-invariant.
    """
    token_dir = project_root / ".ll" / "design-tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "primitives.json").write_text(
        json.dumps(
            {
                "color": {
                    "paper": {"0": "#fdfbf6", "200": "#e8dcc4"},
                    "ink": {"900": "#0d0b08"},
                }
            }
        )
    )
    (token_dir / "semantic.json").write_text(
        json.dumps(
            {
                "color": {
                    "surface": {"primary": "{color.paper.0}"},
                    "border": {"subtle": "{color.paper.200}"},
                    "text": {"inverse": "{color.paper.0}"},
                }
            }
        )
    )
    themes_dir = token_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    (themes_dir / "light.json").write_text("{}")
    (themes_dir / "dark.json").write_text(
        json.dumps({"color": {"surface": {"primary": "{color.ink.900}"}}})
    )


def _write_ll_config(project_root: Path, **design_tokens: object) -> Path:
    ll_dir = project_root / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    path = ll_dir / "ll-config.json"
    path.write_text(json.dumps({"design_tokens": dict(design_tokens)}))
    return path


class TestCssValuePositionGuard:
    """Direct unit tests for the scope-then-nearest-delimiter rule."""

    def test_id_selector_after_a_colon_bearing_rule_rejected(self):
        text = "<style> a:hover { color: red } #face { color: blue } </style>"
        start = text.index("#face")
        end = start + len("#face")
        assert _is_css_value_position(text, start, end) is False

    def test_href_attribute_rejected(self):
        text = '<a href="#dedede">link</a>'
        start = text.index("#dedede")
        end = start + len("#dedede")
        assert _is_css_value_position(text, start, end) is False

    def test_script_string_rejected(self):
        text = "<script>var x = '#c0ffee';</script>"
        start = text.index("#c0ffee")
        end = start + len("#c0ffee")
        assert _is_css_value_position(text, start, end) is False

    def test_presentation_attribute_rejected(self):
        text = '<svg><rect fill="#fdfbf6" /></svg>'
        start = text.index("#fdfbf6")
        end = start + len("#fdfbf6")
        assert _is_css_value_position(text, start, end) is False

    def test_box_shadow_multi_value_accepted(self):
        text = "<style>a{box-shadow: 0 0 2px #e8dcc4, 0 0 4px #000;}</style>"
        start = text.index("#e8dcc4")
        end = start + len("#e8dcc4")
        assert _is_css_value_position(text, start, end) is True

    def test_background_with_url_accepted(self):
        text = "<style>a{background: #fdfbf6 url(foo.png);}</style>"
        start = text.index("#fdfbf6")
        end = start + len("#fdfbf6")
        assert _is_css_value_position(text, start, end) is True

    def test_important_suffix_accepted(self):
        text = "<style>a{color: #fdfbf6 !important;}</style>"
        start = text.index("#fdfbf6")
        end = start + len("#fdfbf6")
        assert _is_css_value_position(text, start, end) is True

    def test_style_attribute_accepted(self):
        text = '<div style="color:#4f46e5">x</div>'
        start = text.index("#4f46e5")
        end = start + len("#4f46e5")
        assert _is_css_value_position(text, start, end) is True


class TestAliasPreferredCandidateMap:
    def _tokens(self, resolved, semantic=None, theme=None):
        from little_loops.design_tokens import DesignTokens

        return DesignTokens(
            primitives={},
            semantic=semantic or {},
            theme=theme or {},
            resolved=resolved,
            source_path=Path("."),
        )

    def test_single_alias_survives(self):
        tokens = self._tokens(
            resolved={"color.border.subtle": "#e8dcc4", "color.paper.200": "#e8dcc4"},
            semantic={"color": {"border": {"subtle": "{color.paper.200}"}}},
        )
        candidates = _alias_preferred_candidate_map(tokens)
        assert candidates["#e8dcc4"] == "color.border.subtle"

    def test_two_aliases_stays_ambiguous(self):
        tokens = self._tokens(
            resolved={
                "color.surface.primary": "#fdfbf6",
                "color.text.inverse": "#fdfbf6",
                "color.paper.0": "#fdfbf6",
            },
            semantic={
                "color": {
                    "surface": {"primary": "{color.paper.0}"},
                    "text": {"inverse": "{color.paper.0}"},
                }
            },
        )
        candidates = _alias_preferred_candidate_map(tokens)
        assert "#fdfbf6" not in candidates

    def test_bare_primitive_only_candidate_is_not_an_alias(self):
        tokens = self._tokens(resolved={"color.paper.0": "#fdfbf6"})
        candidates = _alias_preferred_candidate_map(tokens)
        assert "#fdfbf6" not in candidates

    def test_theme_layer_override_flips_winning_candidate(self):
        # Semantic declares surface.primary as an alias; the theme layer
        # overrides it with a concrete literal. Reading semantic alone would
        # pick surface.primary; layering the theme override on top must not.
        tokens = self._tokens(
            resolved={"color.surface.primary": "#0d0b08", "color.text.inverse": "#0d0b08"},
            semantic={
                "color": {
                    "surface": {"primary": "{color.paper.0}"},
                    "text": {"inverse": "{color.ink.900}"},
                }
            },
            theme={"color": {"surface": {"primary": "#0d0b08"}}},
        )
        candidates = _alias_preferred_candidate_map(tokens)
        # surface.primary is now a concrete literal (theme override), so
        # text.inverse is the sole surviving alias candidate.
        assert candidates["#0d0b08"] == "color.text.inverse"

    def test_underscore_prefixed_names_excluded(self):
        tokens = self._tokens(
            resolved={"_wcag_spot_check.foo": "#fdfbf6", "color.paper.0": "#fdfbf6"},
            semantic={"_wcag_spot_check": {"foo": "{color.paper.0}"}},
        )
        candidates = _alias_preferred_candidate_map(tokens)
        assert "#fdfbf6" not in candidates


class TestLiftTokenLiterals:
    def _tokens(self, resolved, semantic=None, theme=None):
        from little_loops.design_tokens import DesignTokens

        return DesignTokens(
            primitives={},
            semantic=semantic or {},
            theme=theme or {},
            resolved=resolved,
            source_path=Path("."),
        )

    def test_lifts_eligible_literal_in_css_value_position(self):
        tokens = self._tokens(
            resolved={"color.brand.500": "#4F46E5"},
            semantic={"color": {"brand": {"500": "{color.raw.500}"}}},
        )
        body = b"<style>a{color:#4F46E5;}</style>"
        lifted_bytes, lifted, unlifted, spans = lift_token_literals(body, tokens)
        assert unlifted == []
        assert len(lifted) == 1
        assert lifted[0]["candidate_names"] == ["color.brand.500"]
        text = lifted_bytes.decode("utf-8")
        assert "var(--color-brand-500)" in text
        assert "#4F46E5" not in text
        # lift_spans locates the replacement in the returned text.
        (start, end) = spans[0]
        assert text[start:end] == "var(--color-brand-500)"

    def test_does_not_lift_outside_css_value_position(self):
        tokens = self._tokens(
            resolved={"color.brand.500": "#4F46E5"},
            semantic={"color": {"brand": {"500": "{color.raw.500}"}}},
        )
        body = b'<a href="#4F46E5">x</a>'
        lifted_bytes, lifted, unlifted, spans = lift_token_literals(body, tokens)
        assert lifted == []
        assert len(unlifted) == 1
        assert lifted_bytes == body
        assert spans == []

    def test_pre_existing_var_reference_left_alone(self):
        """A source artifact already emitting var(--color-surface-primary) must
        survive unchanged — the lift is span-tracked, not a textual inverse."""
        tokens = self._tokens(
            resolved={"color.brand.500": "#4F46E5"},
            semantic={"color": {"brand": {"500": "{color.raw.500}"}}},
        )
        body = b"<style>a{color:#4F46E5;} b{color:var(--color-surface-primary);}</style>"
        lifted_bytes, lifted, unlifted, spans = lift_token_literals(body, tokens)
        assert len(lifted) == 1
        text = lifted_bytes.decode("utf-8")
        assert "var(--color-surface-primary)" in text
        assert "var(--color-brand-500)" in text

    def test_var_name_matches_render_as_css_vars_themed_mangling(self):
        from little_loops.design_tokens import render_as_css_vars_themed

        light = self._tokens(resolved={"color.brand.500": "#4F46E5"})
        dark = self._tokens(resolved={"color.brand.500": "#4F46E5"})
        css_text = render_as_css_vars_themed(light, dark)

        tokens = self._tokens(
            resolved={"color.brand.500": "#4F46E5"},
            semantic={"color": {"brand": {"500": "{color.raw.500}"}}},
        )
        body = b"<style>a{color:#4F46E5;}</style>"
        _lifted_bytes, lifted, _unlifted, _spans = lift_token_literals(body, tokens)
        var_name = f"var(--{lifted[0]['candidate_names'][0].replace('.', '-')})"
        assert var_name == "var(--color-brand-500)"
        assert "--color-brand-500:" in css_text


class TestVerifyLiftReversible:
    def test_reproduces_pre_lift_body_byte_for_byte(self):
        pre_lift = b"<html><head><style>a{color:#4F46E5;}</style></head><body>x</body></html>"
        lit_start = pre_lift.index(b"#4F46E5")
        lit_end = lit_start + len(b"#4F46E5")
        tokens_match = {
            "start": lit_start,
            "end": lit_end,
            "literal": "#4f46e5",
            "candidate_names": ["x"],
        }
        lifted_text = (
            pre_lift[:lit_start].decode() + "var(--color-brand-500)" + pre_lift[lit_end:].decode()
        )
        stamp = "<style>[[= ll.theme_css =]]</style>"
        head_end = lifted_text.index("<head>") + len("<head>")
        stamped_text = lifted_text[:head_end] + stamp + lifted_text[head_end:]
        stamp_span = (head_end, head_end + len(stamp))
        var_start = stamped_text.index("var(--color-brand-500)")
        var_end = var_start + len("var(--color-brand-500)")

        result = verify_lift_reversible(
            stamped_text.encode("utf-8"),
            pre_lift,
            [tokens_match],
            [(var_start, var_end)],
            [stamp_span],
        )
        assert result is None

    def test_mismatch_reports_diff(self):
        pre_lift = b"<style>a{color:#4F46E5;}</style>"
        lifted = b"<style>a{color:var(--color-brand-500);}</style>"
        match = {"start": 15, "end": 22, "literal": "#4f46e5", "candidate_names": ["x"]}
        var_start = lifted.decode().index("var(--color-brand-500)")
        var_end = var_start + len("var(--color-brand-500)")
        # Corrupt: pretend the span is one byte short, so undo does not
        # reproduce the original body.
        result = verify_lift_reversible(lifted, pre_lift, [match], [(var_start, var_end - 1)], [])
        assert result is not None


class TestVerifyLiftRenders:
    def test_missing_declaration_is_reported(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        (tmp_dir / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: index.html\n"
            "data_schema: {type: object, properties: {}}\n"
        )
        (tmp_dir / "template.html.j2").write_text(
            "<html><head></head><body>var(--color-brand-500)</body></html>"
        )
        result = verify_lift_renders(tmp_dir, {}, {"color-brand-500"}, config)
        assert result is not None
        assert "color-brand-500" in result

    def test_present_declaration_passes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        config = _make_config(tmp_path)
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        (tmp_dir / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: index.html\ntheme: design-tokens\n"
            "data_schema: {type: object, properties: {}}\n"
        )
        (tmp_dir / "template.html.j2").write_text(
            "<html><head><style>[[= ll.theme_css =]]</style></head>"
            "<body>var(--color-brand-500)</body></html>"
        )
        result = verify_lift_renders(tmp_dir, {}, {"color-brand-500"}, config)
        assert result is None


class TestCheckLiftPreconditions:
    def _tokens(self, source="profile"):
        from little_loops.design_tokens import DesignTokens

        return DesignTokens(
            primitives={}, semantic={}, theme={}, resolved={}, source_path=Path("."), source=source
        )

    def test_no_head_or_style(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        reason = _check_lift_preconditions(
            "<html><body>hi</body></html>", config.design_tokens, self._tokens(), set(), config
        )
        assert reason is not None and "precondition 1" in reason

    def test_no_root_html(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        reason = _check_lift_preconditions(
            "<head><style>a{}</style></head><body>hi</body>",
            config.design_tokens,
            self._tokens(),
            set(),
            config,
        )
        assert reason is not None and "precondition 2" in reason

    def test_disagreeing_data_theme(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        reason = _check_lift_preconditions(
            '<html data-theme="light"><head><style>a{}</style></head></html>',
            config.design_tokens,
            self._tokens(),
            set(),
            config,
        )
        assert reason is not None and "precondition 3" in reason

    def test_active_theme_outside_light_dark(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_ll_config(tmp_path, active_theme="sepia")
        config = _make_config(tmp_path)
        reason = _check_lift_preconditions(
            "<html><head><style>a{}</style></head></html>",
            config.design_tokens,
            self._tokens(),
            set(),
            config,
        )
        assert reason is not None and "precondition 4" in reason

    def test_design_md_source_bypasses_theme_restriction(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_ll_config(tmp_path, active_theme="sepia")
        config = _make_config(tmp_path)
        with patch(
            "little_loops.cli.artifact.templatize._themed_css_vars",
            return_value=":root {\n}\n[data-theme=dark] {\n}",
        ):
            reason = _check_lift_preconditions(
                "<html><head><style>a{}</style></head></html>",
                config.design_tokens,
                self._tokens(source="design_md"),
                set(),
                config,
            )
        assert reason is None

    def test_missing_var_declaration(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        with patch(
            "little_loops.cli.artifact.templatize._themed_css_vars",
            return_value=":root {\n  --something-else: #000;\n}\n[data-theme=dark] {\n}",
        ):
            reason = _check_lift_preconditions(
                "<html><head><style>a{}</style></head></html>",
                config.design_tokens,
                self._tokens(),
                {"color-brand-500"},
                config,
            )
        assert reason is not None and "precondition 5" in reason

    def test_themed_css_vars_raise_is_a_failed_precondition(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path)
        with patch(
            "little_loops.cli.artifact.templatize._themed_css_vars",
            side_effect=json.JSONDecodeError("boom", "doc", 0),
        ):
            reason = _check_lift_preconditions(
                "<html><head><style>a{}</style></head></html>",
                config.design_tokens,
                self._tokens(),
                {"color-brand-500"},
                config,
            )
        assert reason is not None and "precondition 5" in reason

    def test_all_preconditions_hold(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        config = _make_config(tmp_path)
        reason = _check_lift_preconditions(
            "<html><head><style>a{}</style></head></html>",
            config.design_tokens,
            self._tokens(),
            {"color-brand-500"},
            config,
        )
        assert reason is None


class TestCmdTemplatizeLiftTokens:
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def _templatize(self, tmp_path, body: bytes, *, lift=True, out_name="lifted"):
        artifact = _write(tmp_path / "out" / "index.html", body)
        source = _write(tmp_path / "docs" / "SRC.md", b"# Hello\n")
        regions = _write_regions(tmp_path / "map.json", regions=[])
        out_dir = tmp_path / "artifacts" / "templates" / f"{out_name}.llat"
        argv = [
            "templatize",
            str(artifact),
            str(source),
            "-o",
            str(out_dir),
            "--regions",
            str(regions),
        ]
        if lift:
            argv.append("--lift-tokens")
        code = self._run(argv)
        return code, out_dir, artifact

    def test_flag_off_is_byte_identical_regression(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>x</body></html>"

        code_off, out_dir_off, artifact = self._templatize(
            tmp_path, body, lift=False, out_name="off"
        )
        assert code_off == 0
        manifest_off = load_manifest(out_dir_off)
        assert "theme" not in manifest_off
        body_off = (out_dir_off / "template.html.j2").read_bytes()
        assert body_off == body
        report_off = json.loads((out_dir_off / "unlifted-tokens.json").read_text())
        assert report_off["lifted"] == []
        assert report_off["unlifted"]

    def test_lift_on_rewrites_and_renders_with_declarations(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>x</body></html>"

        code, out_dir, artifact = self._templatize(tmp_path, body)
        assert code == 0

        manifest = load_manifest(out_dir)
        assert manifest["theme"] == "design-tokens"
        promoted_body = (out_dir / "template.html.j2").read_text()
        assert "var(--color-brand-500)" in promoted_body
        assert "#4F46E5" not in promoted_body
        assert 'data-theme="dark"' in promoted_body

        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["lift_skipped_reason"] is None
        assert report["lifted"]
        assert report["lifted"][0]["name"] == "color.brand.500"

        render_out = tmp_path / "rendered"
        code2 = self._run(["render", "lifted", "-o", str(render_out)])
        assert code2 == 0
        rendered = (render_out / "index.html").read_text(encoding="utf-8")
        assert "--color-brand-500: #4F46E5;" in rendered
        assert "[[= ll.theme_css =]]" not in rendered
        assert "/*__THEMED_CSS_VARS__*/" not in rendered

    def test_author_style_precedes_injected_stamp_in_head(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = (
            b"<html><head><style>:root { --color-brand-500: #000000; }"
            b"a{color:#4F46E5;}</style></head><body>x</body></html>"
        )
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="pos")
        assert code == 0
        promoted_body = (out_dir / "template.html.j2").read_text()
        author_idx = promoted_body.index("--color-brand-500: #000000")
        stamp_idx = promoted_body.index("[[= ll.theme_css =]]")
        # The injected stamp <style> sits immediately after <head>, ahead of
        # the author's own <style> — later source order wins at equal
        # specificity, so the author's declaration overrides the stamp's.
        assert stamp_idx < author_idx

    def test_dark_theme_fidelity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_themed_lift_tokens(tmp_path)
        # active_theme defaults to "dark"; the artifact is authored with the
        # dark value of color.surface.primary.
        body = b"<html><head><style>a{color:#0d0b08;}</style></head><body>x</body></html>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="dark")
        assert code == 0
        promoted_body = (out_dir / "template.html.j2").read_text()
        assert "var(--color-surface-primary)" in promoted_body
        assert 'data-theme="dark"' in promoted_body

        render_out = tmp_path / "rendered_dark"
        code2 = self._run(["render", "dark", "-o", str(render_out)])
        assert code2 == 0
        rendered = (render_out / "index.html").read_text(encoding="utf-8")
        dark_scope = rendered.index("[data-theme=dark] {")
        assert "--color-surface-primary: #0d0b08;" in rendered[dark_scope:]

    def test_ambiguous_light_literal_stays_unlifted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_themed_lift_tokens(tmp_path)
        _write_ll_config(tmp_path, active_theme="light")
        body = b"<html><head><style>a{color:#fdfbf6;}</style></head><body>x</body></html>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="ambiguous")
        assert code == 0
        manifest = load_manifest(out_dir)
        assert "theme" not in manifest
        promoted_body = (out_dir / "template.html.j2").read_text()
        assert promoted_body == body.decode()
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["lifted"] == []
        entry = report["unlifted"][0]
        assert sorted(entry["candidate_names"]) == [
            "color.paper.0",
            "color.surface.primary",
            "color.text.inverse",
        ]

    def test_unambiguous_border_subtle_lifts(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_themed_lift_tokens(tmp_path)
        body = b"<html><head><style>a{border-color:#e8dcc4;}</style></head><body>x</body></html>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="subtle")
        assert code == 0
        promoted_body = (out_dir / "template.html.j2").read_text()
        assert "var(--color-border-subtle)" in promoted_body

    def test_css_context_guard_end_to_end(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = (
            b"<html><head><style> a:hover { color: red } #4f46e5-select { color: blue }"
            b" .ok { box-shadow: 0 0 2px #4F46E5, 0 0 4px #000; } </style></head>"
            b'<body><a href="#4F46E5">x</a><script>var y="#4F46E5";</script></body></html>'
        )
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="guard")
        assert code == 0
        promoted_body = (out_dir / "template.html.j2").read_text()
        # The box-shadow occurrence lifts...
        assert "box-shadow: 0 0 2px var(--color-brand-500)" in promoted_body
        # ...but href and script occurrences never do.
        assert 'href="#4F46E5"' in promoted_body
        assert 'var y="#4F46E5"' in promoted_body

    def test_escaped_literal_delimiter_does_not_false_reject(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = (
            b"<html><head><style>a{color:#4F46E5;}</style></head>"
            b"<body>Docs say: [[= something =]]</body></html>"
        )
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="escaped")
        assert code == 0
        assert out_dir.is_dir()

    def test_preexisting_var_reference_does_not_false_reject(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = (
            b"<html><head><style>a{color:#4F46E5;} "
            b"b{color:var(--some-other-existing-token);}</style></head>"
            b"<body>x</body></html>"
        )
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="preexisting")
        assert code == 0
        promoted_body = (out_dir / "template.html.j2").read_text()
        assert "var(--some-other-existing-token)" in promoted_body
        assert "var(--color-brand-500)" in promoted_body

    def test_no_head_or_style_precondition_blocks_lift(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b'<div style="color:#4F46E5">hi</div>'
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="nohead")
        assert code == 0
        manifest = load_manifest(out_dir)
        assert "theme" not in manifest
        assert (out_dir / "template.html.j2").read_bytes() == body
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert report["lift_skipped_reason"] is not None
        assert "precondition 1" in report["lift_skipped_reason"]

    def test_no_root_html_precondition_blocks_lift(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<head><style>a{color:#4F46E5;}</style></head><body>hi</body>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="nohtml")
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert "precondition 2" in report["lift_skipped_reason"]

    def test_disagreeing_data_theme_precondition_blocks_lift(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = (
            b'<html data-theme="light"><head><style>a{color:#4F46E5;}</style></head>'
            b"<body>hi</body></html>"
        )
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="disagree")
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert "precondition 3" in report["lift_skipped_reason"]

    def test_active_theme_outside_light_dark_blocks_lift(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        (tmp_path / ".ll" / "design-tokens" / "themes" / "sepia.json").write_text("{}")
        _write_ll_config(tmp_path, active_theme="sepia")
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="sepia")
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert "precondition 4" in report["lift_skipped_reason"]

    def test_no_tokens_configured_writes_no_report(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_ll_config(tmp_path, enabled=False)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"
        code, out_dir, artifact = self._templatize(tmp_path, body, out_name="notokens")
        assert code == 0
        assert not (out_dir / "unlifted-tokens.json").exists()

    def test_precondition_5_missing_declaration_blocks_lift(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"
        with patch(
            "little_loops.cli.artifact.templatize._themed_css_vars",
            return_value=":root {\n  --something-else: #000;\n}\n[data-theme=dark] {\n}",
        ):
            code, out_dir, artifact = self._templatize(tmp_path, body, out_name="missingdecl")
        assert code == 0
        manifest = load_manifest(out_dir)
        assert "theme" not in manifest
        assert (out_dir / "template.html.j2").read_bytes() == body
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert "precondition 5" in report["lift_skipped_reason"]

    def test_precondition_5_raising_themed_css_vars_still_exits_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"
        with patch(
            "little_loops.cli.artifact.templatize._themed_css_vars",
            side_effect=json.JSONDecodeError("boom", "doc", 0),
        ):
            code, out_dir, artifact = self._templatize(tmp_path, body, out_name="raising")
        assert code == 0
        report = json.loads((out_dir / "unlifted-tokens.json").read_text())
        assert "precondition 5" in report["lift_skipped_reason"]

    def test_unreversible_lift_rejects_with_exit_2(self, tmp_path, monkeypatch):
        from little_loops.cli.artifact import templatize as templatize_mod

        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"

        real_inject = templatize_mod._inject_theme_stamp

        def _corrupting_inject(body_text, active_theme, lift_spans=None):
            text, _spans, rebased = real_inject(body_text, active_theme, lift_spans)
            return text, [], rebased  # drop the stamp span -> undo can't remove it

        with patch.object(templatize_mod, "_inject_theme_stamp", side_effect=_corrupting_inject):
            code, out_dir, artifact = self._templatize(tmp_path, body, out_name="unreversible")
        assert code == 2
        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        assert rejected_dir.is_dir()
        assert (rejected_dir / "lift-reversibility.diff").is_file()

    def test_lost_stamp_point_caught_by_render_check(self, tmp_path, monkeypatch):
        from little_loops.cli.artifact import templatize as templatize_mod

        monkeypatch.chdir(tmp_path)
        _write_simple_lift_tokens(tmp_path)
        body = b"<html><head><style>a{color:#4F46E5;}</style></head><body>hi</body></html>"

        def _no_op_inject(body_text, active_theme, lift_spans=None):
            return body_text, [], (lift_spans or [])  # stamp point never actually inserted

        with patch.object(templatize_mod, "_inject_theme_stamp", side_effect=_no_op_inject):
            code, out_dir, artifact = self._templatize(tmp_path, body, out_name="loststamp")
        assert code == 2
        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        assert rejected_dir.is_dir()
        assert (rejected_dir / "lift-render-check.txt").is_file()
