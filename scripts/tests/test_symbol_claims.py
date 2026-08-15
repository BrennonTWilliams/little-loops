"""Tests for little_loops.issues.symbol_claims (FEAT-3048)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.issues.symbol_claims import (
    SymbolClaim,
    SymbolIndex,
    build_symbol_index,
    extract_symbol_claims,
    symbol_exists_in_file,
    symbol_resolves_elsewhere,
)
from little_loops.text_utils import RefIndex
from tests.helpers import copy_git_template


@pytest.fixture
def ref_index() -> RefIndex:
    return RefIndex(
        by_basename={
            "prose_deps.py": ["scripts/little_loops/issues/prose_deps.py"],
            "link.py": ["scripts/little_loops/cli/issues/link.py"],
        }
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "scripts" / "little_loops" / "issues"
    src.mkdir(parents=True)
    (src / "prose_deps.py").write_text("_ID_RE = 1\n\n\ndef extract_prose_deps(body):\n    pass\n")
    cli = tmp_path / "scripts" / "little_loops" / "cli" / "issues"
    cli.mkdir(parents=True)
    (cli / "link.py").write_text(
        '_FIELD_FLAGS = ("blocked_by", "depends_on", "relates_to")\n\n\ndef cmd_link():\n    pass\n'
    )
    return tmp_path


def test_same_sentence_form_extracts_claim(ref_index: RefIndex) -> None:
    body = "Reuse `extract_prose_deps` in `scripts/little_loops/issues/prose_deps.py` for the shared helper."
    claims = extract_symbol_claims(body, ref_index)
    assert claims == {
        SymbolClaim(
            symbol="extract_prose_deps",
            file="scripts/little_loops/issues/prose_deps.py",
            raw="extract_prose_deps",
        )
    }


def test_dotted_form_extracts_claim(ref_index: RefIndex) -> None:
    body = "Reuse `prose_deps.extract_prose_deps` for writes."
    claims = extract_symbol_claims(body, ref_index)
    assert claims == {
        SymbolClaim(
            symbol="extract_prose_deps",
            file="scripts/little_loops/issues/prose_deps.py",
            raw="prose_deps.extract_prose_deps",
        )
    }


def test_explicit_form_extracts_claim(ref_index: RefIndex) -> None:
    body = "See `scripts/little_loops/issues/prose_deps.py:extract_prose_deps` for reference."
    claims = extract_symbol_claims(body, ref_index)
    assert claims == {
        SymbolClaim(
            symbol="extract_prose_deps",
            file="scripts/little_loops/issues/prose_deps.py",
            raw="scripts/little_loops/issues/prose_deps.py:extract_prose_deps",
        )
    }


def test_bare_backticked_word_with_no_file_attribution_is_not_a_claim(
    ref_index: RefIndex,
) -> None:
    body = "Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes"
    assert extract_symbol_claims(body, ref_index) == set()


def test_feat_2942_regression_fixture_original_text(ref_index: RefIndex) -> None:
    """Pins FEAT-2942's original claim text (commit 2225b414) — no `symbol` claim
    fires here since `frontmatter.update_frontmatter` doesn't dotted-resolve
    (no tracked `frontmatter.py` in this fixture's ref_index) and `ll-issues
    link` is a bare word with no file attribution in the same sentence. The
    CLI-flag half of this regression is covered by test_cli_claims.py.
    """
    body = "Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes"
    assert extract_symbol_claims(body, ref_index) == set()


def test_no_claim_inside_fenced_code_block(ref_index: RefIndex) -> None:
    body = "```\n`extract_prose_deps` in `scripts/little_loops/issues/prose_deps.py`\n```"
    assert extract_symbol_claims(body, ref_index) == set()


def test_suppressed_claim_via_ll_prose_ok_marker(ref_index: RefIndex) -> None:
    body = (
        "<!-- ll-prose-ok: aspirational -->\n"
        "Reuse `extract_prose_deps` in `scripts/little_loops/issues/prose_deps.py` for writes."
    )
    assert extract_symbol_claims(body, ref_index) == set()


def test_extract_symbol_claims_empty_body(ref_index: RefIndex) -> None:
    assert extract_symbol_claims("", ref_index) == set()


def test_symbol_exists_in_file_true_for_function(repo: Path) -> None:
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(
        idx, "scripts/little_loops/issues/prose_deps.py", "extract_prose_deps"
    )


def test_symbol_exists_in_file_true_for_module_constant(repo: Path) -> None:
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "scripts/little_loops/issues/prose_deps.py", "_ID_RE")


def test_symbol_exists_in_file_false_for_missing_symbol(repo: Path) -> None:
    idx = build_symbol_index(repo)
    assert (
        symbol_exists_in_file(idx, "scripts/little_loops/cli/issues/link.py", "cmd_set_parent")
        is False
    )


def test_symbol_exists_in_file_fails_open_for_unsupported_extension(repo: Path) -> None:
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "docs/reference/API.md", "anything") is None


def test_symbol_exists_in_file_fails_open_for_unreadable_file(repo: Path) -> None:
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "scripts/little_loops/does_not_exist.py", "foo") is None


def test_symbol_index_caches_per_file_read(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = build_symbol_index(repo)
    calls = {"n": 0}
    orig_read_text = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "prose_deps.py":
            calls["n"] += 1
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    symbol_exists_in_file(idx, "scripts/little_loops/issues/prose_deps.py", "extract_prose_deps")
    symbol_exists_in_file(idx, "scripts/little_loops/issues/prose_deps.py", "_ID_RE")
    assert calls["n"] == 1


def test_extract_symbols_indented_class_attribute_resolves(repo: Path) -> None:
    """D1: an indented dataclass field must enter the per-file index, not just
    module-level constants (BUG-3063 § Survivor Analysis)."""
    dataclass_file = repo / "scripts" / "little_loops" / "issues" / "gaps.py"
    dataclass_file.write_text(
        "from dataclasses import dataclass, field\n\n\n"
        "@dataclass\n"
        "class FormatGaps:\n"
        "    stale_file_ref: list = field(default_factory=list)\n"
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "scripts/little_loops/issues/gaps.py", "stale_file_ref")


def test_extract_symbols_indented_local_variable_also_resolves(repo: Path) -> None:
    """D1 accepted trade: widening to leading whitespace also admits an indented
    local variable assignment inside a function body -- documented, not a bug."""
    module_file = repo / "scripts" / "little_loops" / "issues" / "helper.py"
    module_file.write_text("def run():\n    local_var = 1\n    return local_var\n")
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "scripts/little_loops/issues/helper.py", "local_var")


def test_symbol_resolves_elsewhere_true_when_reverse_index_has_other_file() -> None:
    idx = SymbolIndex(
        root=Path("."),
        _reverse={"cmd_link": frozenset({"scripts/little_loops/cli/issues/other.py"})},
    )
    assert symbol_resolves_elsewhere(idx, "scripts/little_loops/cli/issues/link.py", "cmd_link")


def test_symbol_resolves_elsewhere_false_when_only_cited_file_has_it() -> None:
    idx = SymbolIndex(
        root=Path("."),
        _reverse={"cmd_link": frozenset({"scripts/little_loops/cli/issues/link.py"})},
    )
    assert not symbol_resolves_elsewhere(idx, "scripts/little_loops/cli/issues/link.py", "cmd_link")


def test_symbol_resolves_elsewhere_false_when_absent_from_reverse_index() -> None:
    idx = SymbolIndex(root=Path("."), _reverse={})
    assert not symbol_resolves_elsewhere(idx, "scripts/little_loops/cli/issues/link.py", "ghost")


def test_build_symbol_index_reverse_index_empty_outside_git_repo(tmp_path: Path) -> None:
    """Fail-open convention (mirrors build_ref_index): no git repo -> empty reverse index."""
    idx = build_symbol_index(tmp_path)
    assert idx.files_with_symbol("anything") == frozenset()


# --------------------------------------------------------------------------
# BUG-3201 A: SQL object names declared in embedded migration strings
# --------------------------------------------------------------------------


def _write(repo: Path, rel: str, text: str) -> str:
    """Seed *rel* under *repo* (creating parents) and return the relative path."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return rel


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A tracked git repo, so _build_reverse_index's `git ls-files` sees files."""
    copy_git_template(tmp_path)
    return tmp_path


def _track(repo: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)


def test_create_table_in_migration_string_resolves(repo: Path) -> None:
    """BUG-3201 A: a table name declared inside a triple-quoted _MIGRATIONS entry
    is a citable symbol of the .py file that carries it."""
    rel = _write(
        repo,
        "scripts/little_loops/session_store/schema.py",
        '_MIGRATIONS = """\n'
        "    CREATE TABLE IF NOT EXISTS tool_events (\n"
        "        id INTEGER PRIMARY KEY\n"
        "    );\n"
        '"""\n',
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "tool_events")


def test_create_index_and_view_and_modifiers_resolve(repo: Path) -> None:
    """INDEX/VIEW and the UNIQUE / VIRTUAL / TEMPORARY modifiers, not just TABLE."""
    rel = _write(
        repo,
        "scripts/little_loops/session_store/schema.py",
        '_MIGRATIONS = """\n'
        "    CREATE UNIQUE INDEX IF NOT EXISTS idx_corrections_dedup ON user_corrections(a);\n"
        "    CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(body);\n"
        "    CREATE VIEW issue_sessions AS SELECT 1;\n"
        "    create temporary table lower_case_ddl (x INTEGER);\n"
        '"""\n',
    )
    idx = build_symbol_index(repo)
    for name in ("idx_corrections_dedup", "search_index", "issue_sessions", "lower_case_ddl"):
        assert symbol_exists_in_file(idx, rel, name), name


def test_sql_object_names_enter_reverse_index(git_repo: Path) -> None:
    """Deliberate asymmetry vs imports: SQL names are repo-unique, so a table
    claimed against the wrong file is a mis-attribution, not a stale claim."""
    _write(
        git_repo,
        "schema.py",
        '_MIGRATIONS = """\n    CREATE TABLE IF NOT EXISTS tool_events (id INTEGER);\n"""\n',
    )
    _write(git_repo, "other.py", "def unrelated():\n    pass\n")
    _track(git_repo)
    idx = build_symbol_index(git_repo)
    assert symbol_exists_in_file(idx, "other.py", "tool_events") is False
    assert symbol_resolves_elsewhere(idx, "other.py", "tool_events")


def test_sql_file_extension_still_fails_open(repo: Path) -> None:
    """.sql is deliberately absent from _SUPPORTED_SYMBOL_EXTENSIONS: it must keep
    returning None, not start answering False for every column name."""
    _write(repo, "db/schema.sql", "CREATE TABLE tool_events (id INTEGER);\n")
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, "db/schema.sql", "tool_events") is None


# --------------------------------------------------------------------------
# BUG-3201 B: names bound by import statements
# --------------------------------------------------------------------------


def test_aliased_import_resolves_in_importing_file(repo: Path) -> None:
    """`from m import x as y` binds y in the importing module, so citing y there
    is a true claim -- previously a hard stale_symbol_ref (the alias is defined
    nowhere in the repo, so symbol_resolves_elsewhere could not soften it)."""
    rel = _write(
        repo,
        "scripts/little_loops/cli/adapt.py",
        "def cmd_adapt():\n"
        "    from little_loops.skill_expander import _find_plugin_root as _fpr\n"
        "    return _fpr()\n",
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "_fpr")


def test_plain_from_import_resolves_in_importing_file(repo: Path) -> None:
    """The softer half: `from m import x` previously degraded to a false
    mislocated_symbol_ref, since the reverse index found x at m."""
    rel = _write(
        repo,
        "scripts/little_loops/fsm/executor.py",
        "from little_loops.host_runner import resolve_host\n",
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "resolve_host")


def test_parenthesized_multiline_import_resolves(repo: Path) -> None:
    rel = _write(
        repo,
        "scripts/little_loops/cli/loop/info.py",
        "from little_loops.cli.output import (\n"
        "    ACRONYMS,\n"
        "    CATEGORY_COLOR,\n"
        "    colorize,\n"
        "    terminal_width,\n"
        ")\n",
    )
    idx = build_symbol_index(repo)
    for name in ("ACRONYMS", "CATEGORY_COLOR", "colorize", "terminal_width"):
        assert symbol_exists_in_file(idx, rel, name), name


def test_trailing_comment_paren_does_not_close_continuation(repo: Path) -> None:
    """Regression test for the 6 measured misses: a ")" inside a trailing comment
    on the opening line closed the continuation early, dropping every binding
    after it (cli/loop/info.py's `ACRONYMS,  # noqa: F401  (re-exported ...)`)."""
    rel = _write(
        repo,
        "scripts/little_loops/cli/loop/info.py",
        "from little_loops.cli.output import (\n"
        "    ACRONYMS,  # noqa: F401  (re-exported for tests/lint)\n"
        "    late_name,\n"
        ")\n",
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "late_name")


def test_plain_import_binds_first_dotted_component(repo: Path) -> None:
    rel = _write(repo, "scripts/little_loops/cli/doctor.py", "import importlib.metadata\n")
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "importlib")
    assert symbol_exists_in_file(idx, rel, "metadata") is False


def test_import_star_binds_nothing(repo: Path) -> None:
    rel = _write(repo, "scripts/little_loops/wildcard.py", "from little_loops.config import *\n")
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "config") is False


def test_def_after_closed_import_block_still_indexed(repo: Path) -> None:
    """The continuation counter must close, or every def below a multi-line
    import would be swallowed as a binding line."""
    rel = _write(
        repo,
        "scripts/little_loops/cli/after.py",
        "from little_loops.cli.output import (\n    colorize,\n)\n\n\ndef cmd_after():\n    pass\n",
    )
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "cmd_after")


def test_imported_name_excluded_from_reverse_index(git_repo: Path) -> None:
    """BUG-3201 § Exclude imports from the reverse index: an imported-only name
    claimed against an unrelated file must stay a stale_symbol_ref, not become a
    mislocated_symbol_ref whose printed rationale ("exists elsewhere in the
    repo") would be false."""
    _write(git_repo, "importer.py", "from little_loops.config import shared_helper\n")
    _write(git_repo, "unrelated.py", "def other():\n    pass\n")
    _track(git_repo)
    idx = build_symbol_index(git_repo)
    assert symbol_exists_in_file(idx, "importer.py", "shared_helper")
    assert symbol_exists_in_file(idx, "unrelated.py", "shared_helper") is False
    assert not symbol_resolves_elsewhere(idx, "unrelated.py", "shared_helper")


def test_defined_name_still_in_reverse_index(git_repo: Path) -> None:
    """Control for the exclusion above: a real def-site still resolves elsewhere."""
    _write(git_repo, "definer.py", "def shared_helper():\n    pass\n")
    _write(git_repo, "unrelated.py", "def other():\n    pass\n")
    _track(git_repo)
    idx = build_symbol_index(git_repo)
    assert symbol_resolves_elsewhere(idx, "unrelated.py", "shared_helper")


# --------------------------------------------------------------------------
# BUG-3201: the import scan is gated to .py
# --------------------------------------------------------------------------


def test_java_import_not_indexed(repo: Path) -> None:
    """Ungated, `import java.util.List;` would index `java` into every Java file."""
    rel = _write(repo, "src/Main.java", "import java.util.List;\n")
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "java") is False
    assert symbol_exists_in_file(idx, rel, "List") is False


def test_go_import_block_does_not_suppress_func_indexing(repo: Path) -> None:
    """Go's `import (` must not open a Python-style continuation and swallow the
    func declarations below it."""
    rel = _write(repo, "cmd/main.go", 'import (\n    "fmt"\n)\n\nfunc Handler(w int) {\n}\n')
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "Handler")


def test_ts_import_not_indexed(repo: Path) -> None:
    rel = _write(repo, "src/app.ts", 'import { foo } from "bar";\n')
    idx = build_symbol_index(repo)
    assert symbol_exists_in_file(idx, rel, "foo") is False
