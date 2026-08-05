"""Tests for little_loops.issues.symbol_claims (FEAT-3048)."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.issues.symbol_claims import (
    SymbolClaim,
    build_symbol_index,
    extract_symbol_claims,
    symbol_exists_in_file,
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
