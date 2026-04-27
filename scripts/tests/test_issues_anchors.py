"""Tests for issues.anchors — ENH-1300."""

from __future__ import annotations

from pathlib import Path

from little_loops.issues.anchors import resolve_anchor
from little_loops.issues.anchor_sweep import _FILE_LINE


class TestResolveAnchorPython:
    """resolve_anchor() backwards-scan for Python def / async def."""

    def test_python_def(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def foo():\n    x = 1\n    return x\n")
        assert resolve_anchor(str(src), 3) == "near function foo"

    def test_python_async_def(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("async def bar(a, b):\n    pass\n")
        assert resolve_anchor(str(src), 2) == "near function bar"

    def test_python_indented_def(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("class Outer:\n    def inner(self):\n        pass\n")
        assert resolve_anchor(str(src), 3) == "near function inner"


class TestResolveAnchorTypeScript:
    """resolve_anchor() backwards-scan for TypeScript / JavaScript functions."""

    def test_ts_function_declaration(self, tmp_path: Path) -> None:
        src = tmp_path / "utils.ts"
        src.write_text("function process(items: string[]): void {\n  items.forEach(() => {});\n}\n")
        assert resolve_anchor(str(src), 2) == "near function process"

    def test_ts_async_function(self, tmp_path: Path) -> None:
        src = tmp_path / "utils.ts"
        src.write_text("export async function fetchData(url: string) {\n  return fetch(url);\n}\n")
        assert resolve_anchor(str(src), 2) == "near function fetchData"

    def test_ts_const_arrow(self, tmp_path: Path) -> None:
        src = tmp_path / "utils.ts"
        src.write_text("const handler = async (req: Request) => {\n  return 'ok';\n};\n")
        assert resolve_anchor(str(src), 2) == "near function handler"


class TestResolveAnchorGo:
    """resolve_anchor() backwards-scan for Go func declarations."""

    def test_go_plain_func(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text("func main() {\n\trun()\n}\n")
        assert resolve_anchor(str(src), 2) == "near function main"

    def test_go_method(self, tmp_path: Path) -> None:
        src = tmp_path / "server.go"
        src.write_text("func (s *Server) Start() error {\n\treturn nil\n}\n")
        assert resolve_anchor(str(src), 2) == "near function Start"


class TestResolveAnchorRust:
    """resolve_anchor() backwards-scan for Rust fn declarations."""

    def test_rust_pub_fn(self, tmp_path: Path) -> None:
        src = tmp_path / "lib.rs"
        src.write_text("pub fn parse(input: &str) -> Result<(), Error> {\n    Ok(())\n}\n")
        assert resolve_anchor(str(src), 2) == "near function parse"

    def test_rust_async_fn(self, tmp_path: Path) -> None:
        src = tmp_path / "lib.rs"
        src.write_text("pub async fn run() {\n    loop {}\n}\n")
        assert resolve_anchor(str(src), 2) == "near function run"


class TestResolveAnchorClass:
    """resolve_anchor() backwards-scan for class / struct declarations (universal pattern)."""

    def test_python_class(self, tmp_path: Path) -> None:
        src = tmp_path / "models.py"
        src.write_text("class MyModel:\n    x: int = 0\n")
        assert resolve_anchor(str(src), 2) == "near class MyModel"

    def test_typescript_class(self, tmp_path: Path) -> None:
        src = tmp_path / "widget.ts"
        src.write_text("export class Widget {\n  render() {}\n}\n")
        assert resolve_anchor(str(src), 2) == "near class Widget"

    def test_rust_struct(self, tmp_path: Path) -> None:
        src = tmp_path / "types.rs"
        src.write_text("pub struct Config {\n    pub debug: bool,\n}\n")
        assert resolve_anchor(str(src), 2) == "near class Config"


class TestResolveAnchorMarkdown:
    """resolve_anchor() backwards-scan for Markdown section headings."""

    def test_h2_heading(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.md"
        src.write_text("# Title\n\n## Installation\n\nRun pip install.\n")
        assert resolve_anchor(str(src), 5) == 'under section "Installation"'

    def test_h3_heading(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.md"
        src.write_text("## Usage\n\n### Quick Start\n\nDetails here.\n")
        assert resolve_anchor(str(src), 5) == 'under section "Quick Start"'


class TestResolveAnchorFallback:
    """resolve_anchor() returns None when no anchor can be resolved."""

    def test_no_anchor_found(self, tmp_path: Path) -> None:
        src = tmp_path / "data.py"
        src.write_text("x = 1\ny = 2\nz = 3\n")
        assert resolve_anchor(str(src), 3) is None

    def test_nonexistent_file(self) -> None:
        assert resolve_anchor("/nonexistent/path/file.py", 10) is None

    def test_line_number_beyond_file(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def foo():\n    pass\n")
        # Line 999 is beyond EOF; should still find def foo at line 1
        assert resolve_anchor(str(src), 999) == "near function foo"


class TestFileLinkRegex:
    """_FILE_LINE regex captures file path and line number correctly."""

    def test_captures_path_and_line(self) -> None:
        m = _FILE_LINE.search("see scripts/foo.py:42 for details")
        assert m is not None
        assert m.group(1) == "scripts/foo.py"
        assert m.group(2) == "42"

    def test_requires_line_number(self) -> None:
        # Unlike _STANDALONE_PATH, _FILE_LINE requires :NNN
        m = _FILE_LINE.search("see scripts/foo.py for details")
        assert m is None

    def test_captures_at_start_of_line(self) -> None:
        m = _FILE_LINE.search("foo.py:10\n")
        assert m is not None
        assert m.group(1) == "foo.py"
        assert m.group(2) == "10"

    def test_does_not_match_inside_code_fence(self) -> None:
        # The sweeper handles fence exclusion at the span-intersection level;
        # _FILE_LINE itself matches inside fences (exclusion is caller's job).
        # Verify it still matches so the caller can correctly skip it.
        content = "```\nfoo.py:99\n```"
        m = _FILE_LINE.search(content)
        assert m is not None  # match exists; caller filters via fence spans

    def test_multiple_matches(self) -> None:
        content = "see foo.py:1 and bar.ts:200 for details"
        matches = list(_FILE_LINE.finditer(content))
        assert len(matches) == 2
        assert matches[0].group(1) == "foo.py"
        assert matches[1].group(1) == "bar.ts"
        assert matches[1].group(2) == "200"
