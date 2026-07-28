"""Tests for test_file_patterns.py - shared test-file identification (ENH-2865).

Tests cover:
- is_test_file against each template's default pattern set
- conftest.py classification
- a non-test file that superficially resembles one
- path normalization (backslash -> forward slash)
- filter_test_files list filtering
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from little_loops.test_file_patterns import filter_test_files, is_test_file

TEMPLATES_DIR = Path(__file__).parent.parent / "little_loops" / "templates"

TYPED_TEMPLATES = [
    "dotnet",
    "generic",
    "go",
    "java-gradle",
    "java-maven",
    "javascript",
    "python-generic",
    "rust",
    "typescript",
]


def _config_with_patterns(patterns: list[str]) -> SimpleNamespace:
    return SimpleNamespace(project=SimpleNamespace(test_patterns=patterns))


class TestIsTestFile:
    """Tests for is_test_file against the python-generic default pattern set."""

    def setup_method(self) -> None:
        self.config = _config_with_patterns(
            ["**/test_*.py", "**/*_test.py", "**/tests/**", "conftest.py", "**/conftest.py"]
        )

    def test_matches_test_prefixed_file(self) -> None:
        assert is_test_file("scripts/tests/test_foo.py", config=self.config) is True

    def test_matches_test_suffixed_file(self) -> None:
        assert is_test_file("scripts/foo_test.py", config=self.config) is True

    def test_matches_conftest_at_root(self) -> None:
        assert is_test_file("conftest.py", config=self.config) is True

    def test_matches_nested_conftest(self) -> None:
        assert is_test_file("scripts/tests/conftest.py", config=self.config) is True

    def test_similar_but_not_test_file(self) -> None:
        """pytest_history_plugin.py looks test-related but isn't a test file."""
        assert (
            is_test_file("scripts/little_loops/pytest_history_plugin.py", config=self.config)
            is False
        )

    def test_non_test_source_file(self) -> None:
        assert is_test_file("scripts/little_loops/config/core.py", config=self.config) is False

    def test_normalizes_windows_path_separators(self) -> None:
        assert is_test_file("scripts\\tests\\test_foo.py", config=self.config) is True


class TestFilterTestFiles:
    """Tests for filter_test_files list filtering."""

    def test_filters_to_only_test_files(self) -> None:
        config = _config_with_patterns(["**/test_*.py", "conftest.py"])
        paths = ["scripts/tests/test_foo.py", "scripts/little_loops/core.py", "conftest.py"]
        result = filter_test_files(paths, config=config)
        assert result == ["scripts/tests/test_foo.py", "conftest.py"]

    def test_empty_patterns_matches_nothing(self) -> None:
        config = _config_with_patterns([])
        paths = ["scripts/tests/test_foo.py"]
        assert filter_test_files(paths, config=config) == []


@pytest.mark.parametrize("template_name", TYPED_TEMPLATES)
class TestTemplateDefaults:
    """Every project-type template's default test_patterns set is usable."""

    def _load_patterns(self, template_name: str) -> list[str]:
        data = json.loads((TEMPLATES_DIR / f"{template_name}.json").read_text())
        return data["project"]["test_patterns"]

    def test_template_declares_test_patterns(self, template_name: str) -> None:
        patterns = self._load_patterns(template_name)
        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_template_defaults_include_shared_fixture_equivalent(
        self, template_name: str
    ) -> None:
        """Every default set includes conftest.py or the ecosystem's equivalent."""
        patterns = self._load_patterns(template_name)
        shared_fixture_markers = {
            "dotnet": "TestFixture.cs",
            "generic": "conftest.py",
            "go": "_test.go",
            "java-gradle": "BaseTest.java",
            "java-maven": "BaseTest.java",
            "javascript": "jest.setup.js",
            "python-generic": "conftest.py",
            "rust": "common/mod.rs",
            "typescript": "jest.setup.ts",
        }
        marker = shared_fixture_markers[template_name]
        assert any(marker in pattern for pattern in patterns), (
            f"{template_name} test_patterns missing shared-fixture equivalent {marker!r}"
        )
