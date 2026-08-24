"""Tests for `ll-artifact templatize` Phase A (FEAT-3314): deterministic templating."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from little_loops.artifact_templates import load_manifest
from little_loops.cli.artifact import main_artifact
from little_loops.cli.artifact.templatize import (
    DiscoveryResult,
    Region,
    RegionGroup,
    RegionMapError,
    SpliceError,
    apply_regions,
    build_manifest,
    derive_schema,
    escape_literal_delimiters,
    extract_data,
    load_regions,
    promote,
)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_regions(path: Path, regions=None, groups=None) -> Path:
    payload = {"regions": regions or [], "groups": groups or []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestLoadRegions:
    def test_minimal_map_loads(self, tmp_path):
        path = _write_regions(tmp_path / "map.json", regions=[{"start": 0, "end": 3, "expr": "title"}])
        result = load_regions(path)
        assert result.regions == [Region(start=0, end=3, expr="title")]
        assert result.data == {}
        assert result.data_schema == {}

    def test_anchors_optional(self, tmp_path):
        path = _write_regions(tmp_path / "map.json", regions=[{"start": 0, "end": 3, "expr": "title"}])
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
            id="cards", binding="card", array_path="cards", start=0, end=20, iterations=[(0, 10), (10, 20)]
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
            b"<ul>\n"
            b"  [[% for li in items %]]\n"
            b"  <li>[[= li.n =]]</li>\n"
            b"  [[% endfor %]]\n"
            b"</ul>"
        )

    def test_mismatched_iteration_literal_text_errors(self):
        artifact = b'<li id="a">1</li><li id="b">2</li>'
        group = RegionGroup(
            id="items", binding="li", array_path="items", start=0, end=34, iterations=[(0, 17), (17, 34)]
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
