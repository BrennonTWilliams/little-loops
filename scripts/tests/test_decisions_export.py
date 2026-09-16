"""Tests for little_loops.decisions_export (FEAT-3485)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.decisions import RuleEntry, active_required_rules, save_decisions


@pytest.fixture
def decisions_path(tmp_path: Path) -> Path:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return ll_dir / "decisions.yaml"


REPO1 = RuleEntry(id="REPO-1", rule="Repo rule one", enforcement="required")
REPO2 = RuleEntry(id="REPO-2", rule="Repo rule two", enforcement="required")
PY_SCRIPTS = RuleEntry(
    id="PY-SCRIPTS",
    rule="Python files in scripts",
    enforcement="required",
    paths=["scripts/**/*.py"],
)
PY_ANY = RuleEntry(id="PY-ANY", rule="Any python file", enforcement="required", paths=["**/*.py"])
SCRIPTS_DIR = RuleEntry(
    id="SCRIPTS-DIR", rule="Scripts dir rule", enforcement="required", paths=["scripts/**/*"]
)
FSM_DIR = RuleEntry(
    id="FSM-DIR", rule="FSM dir rule", enforcement="required", paths=["scripts/fsm/**/*"]
)
SUP_OLD = RuleEntry(
    id="SUP-OLD", rule="Old superseded rule", enforcement="required", paths=["docs/**/*"]
)
SUP_NEW = RuleEntry(
    id="SUP-NEW",
    rule="New docs rule",
    enforcement="required",
    supersedes="SUP-OLD",
    paths=["docs/**/*"],
)
ADVISORY = RuleEntry(id="ADV-1", rule="Advisory only", enforcement="advisory", paths=["tests/**/*"])

ALL_FIXTURE_RULES = [
    REPO1,
    REPO2,
    PY_SCRIPTS,
    PY_ANY,
    SCRIPTS_DIR,
    FSM_DIR,
    SUP_OLD,
    SUP_NEW,
    ADVISORY,
]


@pytest.fixture
def active_rules(decisions_path: Path) -> list[RuleEntry]:
    save_decisions(list(ALL_FIXTURE_RULES), decisions_path)
    return active_required_rules(decisions_path)


class TestGlobSortKey:
    def test_orders_by_specificity(self) -> None:
        from little_loops.decisions_export import _glob_sort_key

        globs = ["**/*.py", "scripts/**/*", "scripts/fsm/**/*", "scripts/**/*.py"]
        ordered = sorted(globs, key=_glob_sort_key)
        assert ordered == [
            "scripts/fsm/**/*",
            "scripts/**/*.py",
            "scripts/**/*",
            "**/*.py",
        ]


class TestDirPrefix:
    def test_directory_glob_prefix(self) -> None:
        from little_loops.decisions_export import _dir_prefix

        assert _dir_prefix("scripts/**/*") == "scripts/"

    def test_bare_wildcard_prefix(self) -> None:
        from little_loops.decisions_export import _dir_prefix

        assert _dir_prefix("**/*") == ""

    def test_non_directory_glob_returns_none(self) -> None:
        from little_loops.decisions_export import _dir_prefix

        assert _dir_prefix("scripts/**/*.py") is None


class TestExportRulesDispatch:
    def test_unknown_target_raises_value_error(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        from little_loops.decisions_export import export_rules

        with pytest.raises(ValueError, match="ocr"):
            export_rules(active_rules, "nope", tmp_path)


class TestExportOcr:
    def _write(self, active_rules: list[RuleEntry], tmp_path: Path, **kwargs) -> dict:
        from little_loops.decisions_export import export_rules

        path = export_rules(active_rules, "ocr", tmp_path, **kwargs)
        assert path == tmp_path / ".opencodereview" / "rule.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_excludes_superseded_and_advisory(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        bodies = " ".join(e["rule"] for e in data["rules"])
        assert "Old superseded rule" not in bodies
        assert "Advisory only" not in bodies
        assert "New docs rule" in bodies

    def test_one_entry_per_distinct_glob_default_scope(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        paths = [e["path"] for e in data["rules"]]
        assert len(paths) == len(set(paths))
        assert set(paths) == {
            "scripts/fsm/**/*",
            "scripts/**/*.py",
            "scripts/**/*",
            "docs/**/*",
            "**/*.py",
            "**/*",
        }

    def test_scoped_entries_precede_catch_all(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        paths = [e["path"] for e in data["rules"]]
        assert paths[-1] == "**/*"
        assert "**/*" not in paths[:-1]

    def test_scoped_sort_order(self, active_rules: list[RuleEntry], tmp_path: Path) -> None:
        data = self._write(active_rules, tmp_path)
        paths = [e["path"] for e in data["rules"]]
        scoped = paths[:-1]
        assert scoped.index("scripts/fsm/**/*") < scoped.index("scripts/**/*.py")
        assert scoped.index("scripts/**/*.py") < scoped.index("scripts/**/*")
        assert scoped.index("scripts/**/*") < scoped.index("**/*.py")

    def test_fsm_body_folds_directory_rules_not_non_directory_overlap(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        fsm_body = by_path["scripts/fsm/**/*"]
        assert "FSM dir rule" in fsm_body
        assert "Scripts dir rule" in fsm_body
        assert "Repo rule one" in fsm_body
        assert "Repo rule two" in fsm_body
        assert "Python files in scripts" not in fsm_body

    def test_py_scripts_body_folds_directory_and_repo_wide(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        body = by_path["scripts/**/*.py"]
        assert "Python files in scripts" in body
        assert "Scripts dir rule" in body
        assert "Repo rule one" in body
        assert "Repo rule two" in body

    def test_catch_all_body_contains_only_repo_wide(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path)
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        catch_all = by_path["**/*"]
        assert "Repo rule one" in catch_all
        assert "Repo rule two" in catch_all
        assert "Scripts dir rule" not in catch_all
        assert "FSM dir rule" not in catch_all

    def test_bullets_carry_decision_id(self, active_rules: list[RuleEntry], tmp_path: Path) -> None:
        data = self._write(active_rules, tmp_path)
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        assert "(decision REPO-1)" in by_path["**/*"]

    def test_none_scope_globs_emits_bare_catch_all(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path, scope_globs=None)
        paths = [e["path"] for e in data["rules"]]
        assert "**/*" in paths

    def test_scoped_glob_equal_to_scope_glob_merges_no_duplicate(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        data = self._write(active_rules, tmp_path, scope_globs=["scripts/**/*"])
        paths = [e["path"] for e in data["rules"]]
        assert paths.count("scripts/**/*") == 1
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        merged = by_path["scripts/**/*"]
        assert "Scripts dir rule" in merged
        assert "Repo rule one" in merged
        assert "Repo rule two" in merged

    def test_idempotent_second_run_byte_identical(
        self, active_rules: list[RuleEntry], tmp_path: Path
    ) -> None:
        from little_loops.decisions_export import export_rules

        path1 = export_rules(active_rules, "ocr", tmp_path)
        first = path1.read_bytes()
        path2 = export_rules(active_rules, "ocr", tmp_path)
        second = path2.read_bytes()
        assert first == second

    def test_no_active_rules_writes_empty_rules_array(self, tmp_path: Path) -> None:
        from little_loops.decisions_export import export_rules

        path = export_rules([], "ocr", tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["rules"] == []

    def test_no_exclude_key_emitted(self, active_rules: list[RuleEntry], tmp_path: Path) -> None:
        data = self._write(active_rules, tmp_path)
        assert "exclude" not in data

    def test_pure_no_config_import(self) -> None:
        import ast

        source = Path("scripts/little_loops/decisions_export.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        assert not any("config" in m for m in imported_modules), imported_modules


class TestActiveRuleWithMultiplePaths:
    def test_appears_in_each_glob_entry(self, tmp_path: Path, decisions_path: Path) -> None:
        from little_loops.decisions_export import export_rules

        multi = RuleEntry(
            id="MULTI-1",
            rule="Applies to two globs",
            enforcement="required",
            paths=["a/**/*", "b/**/*"],
        )
        data = json.loads(export_rules([multi], "ocr", tmp_path).read_text(encoding="utf-8"))
        by_path = {e["path"]: e["rule"] for e in data["rules"]}
        assert "Applies to two globs" in by_path["a/**/*"]
        assert "Applies to two globs" in by_path["b/**/*"]
