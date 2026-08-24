"""Tests for FEAT-3036 Phase 1: artifact template format + `ll-artifact render`."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    TemplateResolutionError,
    build_environment,
    load_manifest,
    render_template,
    resolve_template,
    validate_top_level_data,
)
from little_loops.logger import Logger

_FIXTURES = Path(__file__).parent / "fixtures" / "artifact_templates"


def _make_config(project_root: Path, artifacts_extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if artifacts_extra:
        cfg["artifacts"] = artifacts_extra
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


def _copy_fixture(name: str, dest: Path) -> Path:
    target = dest / f"{name}.llat"
    shutil.copytree(_FIXTURES / f"{name}.llat", target)
    return target


# ---------------------------------------------------------------------------
# pyproject.toml: jinja2 pin + justification comment
# ---------------------------------------------------------------------------


class TestJinja2Pin:
    def test_jinja2_pinned_with_justifying_comment(self) -> None:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        text = pyproject.read_text()
        assert "jinja2" in text.lower()
        idx = text.lower().index("jinja2")
        preceding = text[max(0, idx - 600) : idx]
        assert "FEAT-3036" in preceding


# ---------------------------------------------------------------------------
# Jinja2 environment: frozen delimiter + whitespace contract
# ---------------------------------------------------------------------------


class TestBuildEnvironment:
    def test_frozen_delimiters_and_whitespace_flags(self) -> None:
        env = build_environment()
        assert env.variable_start_string == "[[="
        assert env.variable_end_string == "=]]"
        assert env.block_start_string == "[[%"
        assert env.block_end_string == "%]]"
        assert env.comment_start_string == "[[#"
        assert env.comment_end_string == "#]]"
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True
        assert env.keep_trailing_newline is True

    def test_no_loader(self) -> None:
        env = build_environment()
        assert env.loader is None

    def test_autoescape_disabled(self) -> None:
        env = build_environment()
        assert env.autoescape is False


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------


class TestResolveTemplate:
    def test_resolves_as_filesystem_path(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        resolved = resolve_template(str(root), tmp_path / "templates")
        assert resolved == root

    def test_resolves_as_name_under_templates_dir(self, tmp_path: Path) -> None:
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        _copy_fixture("simple", templates_dir)
        # rename to a plain name
        (templates_dir / "simple.llat").rename(templates_dir / "myreport.llat")
        resolved = resolve_template("myreport", templates_dir)
        assert resolved == templates_dir / "myreport.llat"

    def test_not_found_names_both_paths_tried(self, tmp_path: Path) -> None:
        templates_dir = tmp_path / "templates"
        with pytest.raises(TemplateResolutionError) as exc_info:
            resolve_template("nope", templates_dir)
        message = str(exc_info.value)
        assert "nope" in message
        assert str(templates_dir / "nope.llat") in message


# ---------------------------------------------------------------------------
# Manifest loading + validation
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_valid_manifest_loads(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest = load_manifest(root)
        assert manifest["name"] == "simple-report"
        assert manifest["renderer"] == "jinja2"

    def test_missing_manifest_file(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path)

    def test_unknown_top_level_key_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            (root / "manifest.yaml").read_text() + "\nbogus_key: 1\n"
        )
        with pytest.raises(ManifestError, match="unknown top-level key"):
            load_manifest(root)

    def test_missing_required_key(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text("name: x\nversion: 1\n")
        with pytest.raises(ManifestError, match="missing required key"):
            load_manifest(root)

    def test_renderer_must_be_jinja2(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        text = (
            (root / "manifest.yaml").read_text().replace("renderer: jinja2", "renderer: mustache")
        )
        (root / "manifest.yaml").write_text(text)
        with pytest.raises(ManifestError, match="renderer"):
            load_manifest(root)

    def test_invalid_theme_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            (root / "manifest.yaml").read_text() + "\ntheme: rainbow\n"
        )
        with pytest.raises(ManifestError, match="theme"):
            load_manifest(root)

    def test_reserved_ll_key_in_schema_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            """
name: x
version: 1
renderer: jinja2
output: out.html
data_schema:
  type: object
  properties:
    ll: {type: string}
"""
        )
        with pytest.raises(ManifestError, match="reserved"):
            load_manifest(root)

    @pytest.mark.parametrize(
        "schema_yaml",
        [
            "type: object\noneOf: []\n",
            "type: object\n$ref: '#/foo'\n",
            "type: object\npatternProperties: {}\n",
            "type: object\nadditionalProperties: false\n",
            "type: string\nformat: date\n",
            "type: number\nminimum: 0\n",
        ],
    )
    def test_unsupported_schema_construct_rejected_at_load(
        self, tmp_path: Path, schema_yaml: str
    ) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\ndata_schema:\n"
            + "\n".join(f"  {line}" for line in schema_yaml.splitlines())
            + "\n"
        )
        with pytest.raises(ManifestError):
            load_manifest(root)

    def test_required_only_under_object(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\n"
            "data_schema:\n  type: string\n  required: [a]\n"
        )
        with pytest.raises(ManifestError, match="only permitted under type: object"):
            load_manifest(root)

    def test_items_only_under_array(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\n"
            "data_schema:\n  type: string\n  items: {type: string}\n"
        )
        with pytest.raises(ManifestError, match="only permitted under type: array"):
            load_manifest(root)

    def test_items_tuple_form_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\n"
            "data_schema:\n  type: array\n  items: [{type: string}, {type: number}]\n"
        )
        with pytest.raises(ManifestError, match="tuple-form"):
            load_manifest(root)

    def test_enum_must_be_non_empty_scalars(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\n"
            "data_schema:\n  type: string\n  enum: []\n"
        )
        with pytest.raises(ManifestError, match="enum"):
            load_manifest(root)


# ---------------------------------------------------------------------------
# data.json validation
# ---------------------------------------------------------------------------


class TestValidateData:
    def test_valid_data_passes(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest = load_manifest(root)
        data = json.loads((root / "data.json").read_text())
        validate_top_level_data(data, manifest["data_schema"])  # no raise

    def test_missing_required_key_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest = load_manifest(root)
        with pytest.raises(DataValidationError, match="missing required key"):
            validate_top_level_data({"title": "x"}, manifest["data_schema"])

    def test_enum_violation_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest = load_manifest(root)
        data = {
            "title": "x",
            "sections": [{"heading": "h", "body": "b", "severity": "critical"}],
        }
        with pytest.raises(DataValidationError, match="not in enum"):
            validate_top_level_data(data, manifest["data_schema"])

    def test_top_level_ll_key_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest = load_manifest(root)
        data = {"title": "x", "sections": [], "ll": {}}
        with pytest.raises(DataValidationError, match="reserved"):
            validate_top_level_data(data, manifest["data_schema"])


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderTemplate:
    def test_renders_loop_and_asset(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        data = json.loads((root / "data.json").read_text())
        template = ArtifactTemplate(root=root, manifest=manifest)
        rendered = render_template(template, data, config)
        assert "Auth outage" in rendered
        assert "Latency creep" in rendered
        assert "Generated by the FEAT-3036 fixture." in rendered

    def test_idempotent_render_is_byte_identical(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        data = json.loads((root / "data.json").read_text())
        template = ArtifactTemplate(root=root, manifest=manifest)
        first = render_template(template, data, config)
        second = render_template(template, data, config)
        assert first == second

    def test_literal_delimiters_preserved_byte_for_byte(self, tmp_path: Path) -> None:
        root = _copy_fixture("delimiters", tmp_path)
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        source = (root / "template.html.j2").read_text()
        template = ArtifactTemplate(root=root, manifest=manifest)
        rendered = render_template(template, {}, config)
        assert rendered == source
        assert '{{name: "x"}}' in rendered
        assert "${cfg.name}-suffix" in rendered
        assert "{% color: red %}" in rendered
        assert "[[not a substitution]]" in rendered

    def test_no_loader_include_fails_with_clear_error(self, tmp_path: Path) -> None:
        root = tmp_path / "include.llat"
        root.mkdir()
        (root / "manifest.yaml").write_text(
            "name: x\nversion: 1\nrenderer: jinja2\noutput: out.html\n"
            "data_schema:\n  type: object\n  properties: {}\n"
        )
        (root / "template.html.j2").write_text('[[% include "other.j2" %]]')
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        template = ArtifactTemplate(root=root, manifest=manifest)
        with pytest.raises(TypeError, match="no loader"):
            render_template(template, {}, config)

    def test_theme_css_stamped_via_design_tokens_path(self, tmp_path: Path) -> None:
        root = _copy_fixture("theme", tmp_path)
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        template = ArtifactTemplate(root=root, manifest=manifest)
        with patch(
            "little_loops.cli.artifact.policy_builder._themed_css_vars",
            return_value=":root{--x:1}",
        ) as themed:
            rendered = render_template(template, {}, config)
        themed.assert_called_once()
        assert ":root{--x:1}" in rendered

    def test_render_makes_no_llm_call(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        config = _make_config(tmp_path)
        manifest = load_manifest(root)
        data = json.loads((root / "data.json").read_text())
        template = ArtifactTemplate(root=root, manifest=manifest)
        with patch("little_loops.host_runner.resolve_host") as resolve_host:
            render_template(template, data, config)
        resolve_host.assert_not_called()

    def test_render_module_imports_nothing_from_host_runner_or_anthropic(self) -> None:
        import ast

        module_path = Path(__file__).parent.parent / "little_loops" / "artifact_templates.py"
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
# CLI: cmd_render
# ---------------------------------------------------------------------------


class TestCmdRender:
    def test_happy_path_writes_output(self, tmp_path: Path, capsys) -> None:
        from little_loops.cli.artifact.render import cmd_render

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(template=str(root), data=None, output=str(out_dir))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 0
        out_file = out_dir / "report.html"
        assert out_file.is_file()
        assert "Auth outage" in out_file.read_text()

    def test_unresolvable_template_exits_1(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.render import cmd_render

        _make_config(tmp_path)
        args = argparse.Namespace(template="nope", data=None, output=None)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_schema_violation_exits_1_and_writes_nothing(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.render import cmd_render

        root = _copy_fixture("simple", tmp_path)
        bad_data = tmp_path / "bad-data.json"
        bad_data.write_text(json.dumps({"title": "x"}))
        _make_config(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(template=str(root), data=str(bad_data), output=str(out_dir))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 1
        assert not out_dir.exists()

    def test_output_dir_naming_existing_file_is_error(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.render import cmd_render

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        existing_file = tmp_path / "out-as-file"
        existing_file.write_text("occupied")
        args = argparse.Namespace(template=str(root), data=None, output=str(existing_file))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_dotted_output_directory_name_is_not_an_error(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.render import cmd_render

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        out_dir = tmp_path / "out.v2"
        args = argparse.Namespace(template=str(root), data=None, output=str(out_dir))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert (out_dir / "report.html").is_file()

    def test_named_template_resolves_via_templates_dir(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.render import cmd_render

        templates_dir = tmp_path / "artifacts" / "templates"
        templates_dir.mkdir(parents=True)
        _copy_fixture("simple", templates_dir)
        (templates_dir / "simple.llat").rename(templates_dir / "myreport.llat")
        _make_config(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(template="myreport", data=None, output=str(out_dir))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert (out_dir / "report.html").is_file()


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestArtifactCLIDispatchRender:
    def test_render_dispatches_to_handler(self) -> None:
        from little_loops.cli.artifact import main_artifact

        with (
            patch("sys.argv", ["ll-artifact", "render", "some-template"]),
            patch("little_loops.cli.artifact.cmd_render", return_value=0) as handler,
        ):
            code = main_artifact()
        assert code == 0
        handler.assert_called_once()
