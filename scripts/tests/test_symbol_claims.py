"""Tests for little_loops.issues.symbol_claims (FEAT-3048)."""

from __future__ import annotations

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
    assert symbol_exists_in_file(
        idx, "scripts/little_loops/issues/gaps.py", "stale_file_ref"
    )


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
    assert not symbol_resolves_elsewhere(
        idx, "scripts/little_loops/cli/issues/link.py", "cmd_link"
    )


def test_symbol_resolves_elsewhere_false_when_absent_from_reverse_index() -> None:
    idx = SymbolIndex(root=Path("."), _reverse={})
    assert not symbol_resolves_elsewhere(idx, "scripts/little_loops/cli/issues/link.py", "ghost")


def test_build_symbol_index_reverse_index_empty_outside_git_repo(tmp_path: Path) -> None:
    """Fail-open convention (mirrors build_ref_index): no git repo -> empty reverse index."""
    idx = build_symbol_index(tmp_path)
    assert idx.files_with_symbol("anything") == frozenset()
