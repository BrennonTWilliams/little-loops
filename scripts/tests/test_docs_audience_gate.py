"""Audience gate for everything that ships to consuming projects.

Two scopes, one rule: the reader (or the model) is in a project that ran
``pip install little-loops`` + ``ll-init``, not in the little-loops source
checkout.

* **User docs** — ``docs/guides/``, ``docs/reference/``, ``README.md``.
  Written for the little-loops END USER; their project is not little-loops
  and they are not contributors.
* **Harness surfaces** — ``skills/**/*.md``, ``commands/*.md``. Executed by
  the model inside the consuming project, where ``scripts/tests/`` and
  ``scripts/little_loops/`` do not exist. Pointers into little-loops
  internals use the installed dotted module (``little_loops.fsm.executor``).

This gate catches the curated phrasings that frame the reader as working
inside the little-loops source checkout.

Suppress a single deliberate hit with ``ll-audience-ok: <reason>`` either on
the same line or on the line immediately preceding it (HTML comment in prose,
``#`` comment inside a code block). Rewriting is preferred over suppression.

See CONTRIBUTING.md § Documentation audience.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIRS = ("docs/guides", "docs/reference")
DOC_FILES = ("README.md",)
HARNESS_DIRS = ("skills", "commands")
# Harness paths exempt until the named issue lands (whole skill is source-repo shaped).
HARNESS_EXEMPT: dict[str, str] = {}
SUPPRESS_TOKEN = "ll-audience-ok:"


@dataclass(frozen=True)
class AudienceMarker:
    """One curated source-repo framing and why it is wrong for end-user docs."""

    name: str
    pattern: re.Pattern[str]
    rationale: str


AUDIENCE_MARKERS: tuple[AudienceMarker, ...] = (
    AudienceMarker(
        "your-little-loops-project",
        re.compile(r"your little-loops project", re.IGNORECASE),
        "the reader's project is not little-loops; say 'your project'",
    ),
    AudienceMarker(
        "this-repo-self-reference",
        re.compile(r"\bthis (repo|repository)\b", re.IGNORECASE),
        "ambiguous self-reference; name 'the little-loops source repository' "
        "or 'the current project' explicitly",
    ),
    AudienceMarker(
        "little-loops-repo-itself",
        re.compile(
            r"\b(the )?little-loops (repo|repository|codebase|checkout) itself\b",
            re.IGNORECASE,
        ),
        "frames the reader as inside the source checkout",
    ),
    AudienceMarker(
        "contributor-framing",
        re.compile(r"\bcontributors?\b", re.IGNORECASE),
        "user docs address consumers, not contributors (pointer to "
        "CONTRIBUTING.md may be suppressed)",
    ),
    AudienceMarker(
        "source-tree-test-path",
        re.compile(r"scripts/tests\b"),
        "path exists only in the little-loops source checkout",
    ),
    AudienceMarker(
        "source-tree-tool-cmd",
        re.compile(r"\b(pytest|ruff (check|format)|mypy) scripts\b"),
        "little-loops' own test/lint command used where a user-project command belongs",
    ),
    AudienceMarker(
        "editable-dev-install",
        re.compile(r"pip install -e\b"),
        "editable install is the contributor path, not the user path",
    ),
)

# Harness-only: a source-tree module path is unreachable from a consuming project.
HARNESS_MARKERS: tuple[AudienceMarker, ...] = AUDIENCE_MARKERS + (
    AudienceMarker(
        "source-tree-module-path",
        re.compile(r"scripts/little_loops/"),
        "cite the installed module as `little_loops.<dotted.path>` instead",
    ),
)


def _doc_files() -> list[Path]:
    files: list[Path] = []
    for rel in DOC_DIRS:
        files.extend(sorted((REPO_ROOT / rel).rglob("*.md")))
    files.extend(REPO_ROOT / rel for rel in DOC_FILES)
    return files


def _harness_files() -> list[Path]:
    files: list[Path] = []
    for rel in HARNESS_DIRS:
        for path in sorted((REPO_ROOT / rel).rglob("*.md")):
            rel_str = path.relative_to(REPO_ROOT).as_posix()
            if any(rel_str.startswith(prefix + "/") for prefix in HARNESS_EXEMPT):
                continue
            files.append(path)
    return files


def scan_audience(
    text: str, markers: tuple[AudienceMarker, ...] = AUDIENCE_MARKERS
) -> list[tuple[int, str, str]]:
    """Return ``(line_no, marker_name, line)`` for each unsuppressed hit."""
    hits: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    fence_suppressed = False
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            if fence_suppressed:
                fence_suppressed = False
            elif idx > 0 and SUPPRESS_TOKEN in lines[idx - 1]:
                fence_suppressed = True
            continue
        if fence_suppressed or SUPPRESS_TOKEN in line:
            continue
        if idx > 0 and SUPPRESS_TOKEN in lines[idx - 1]:
            continue
        for marker in markers:
            if marker.pattern.search(line):
                hits.append((idx + 1, marker.name, line.strip()))
    return hits


class TestScanAudience:
    def test_flags_source_repo_framing(self) -> None:
        text = "Observability for your little-loops project.\nTests live in scripts/tests/.\n"
        names = [name for _, name, _ in scan_audience(text)]
        assert names == ["your-little-loops-project", "source-tree-test-path"]

    def test_user_project_framing_passes(self) -> None:
        text = (
            "Observability for the project little-loops is installed in.\n"
            "Set `test_cmd` to `python -m pytest tests/`.\n"
            "See `scripts/little_loops/config.py` for the loader.\n"
        )
        assert scan_audience(text) == []

    def test_same_line_suppression(self) -> None:
        text = "| `local-editable` | `pip install -e` | <!-- ll-audience-ok: config value -->\n"
        assert scan_audience(text) == []

    def test_preceding_line_suppression(self) -> None:
        text = "<!-- ll-audience-ok: pointer -->\nContributors: see CONTRIBUTING.md.\n"
        assert scan_audience(text) == []

    def test_suppression_covers_only_next_line(self) -> None:
        text = "<!-- ll-audience-ok: pointer -->\nfine\nContributors welcome.\n"
        assert [n for n, _, _ in scan_audience(text)] == [3]

    def test_suppression_before_fence_covers_block(self) -> None:
        text = (
            "<!-- ll-audience-ok: example -->\n```markdown\n- see scripts/tests/x.py\n"
            "- and scripts/tests/y.py\n```\nthen scripts/tests/z.py\n"
        )
        assert [n for n, _, _ in scan_audience(text)] == [6]

    def test_module_path_flagged_only_in_harness_scope(self) -> None:
        text = "See `scripts/little_loops/fsm/executor.py`.\n"
        assert scan_audience(text) == []
        assert [name for _, name, _ in scan_audience(text, HARNESS_MARKERS)] == [
            "source-tree-module-path"
        ]

    def test_dotted_module_pointer_passes_harness_scope(self) -> None:
        assert scan_audience("See `little_loops.fsm.executor`.\n", HARNESS_MARKERS) == []

    def test_no_exemptions_registered(self) -> None:
        """HARNESS_EXEMPT must stay empty — no skill is exempt from the audience scan."""
        assert HARNESS_EXEMPT == {}

    def test_spike_skill_is_not_exempt(self) -> None:
        """Non-regression guard: skills/spike must not silently regain an exemption."""
        rels = {p.relative_to(REPO_ROOT).as_posix() for p in _harness_files()}
        assert "skills/spike/SKILL.md" in rels
        assert "skills/create-loop/SKILL.md" in rels


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_user_docs_are_end_user_facing(doc: Path) -> None:
    hits = scan_audience(doc.read_text(encoding="utf-8"))
    if hits:
        rel = doc.relative_to(REPO_ROOT)
        detail = "\n".join(f"  {rel}:{n} [{name}] {line}" for n, name, line in hits)
        pytest.fail(
            "user-facing doc frames the reader as a little-loops contributor "
            f"(see CONTRIBUTING.md § Documentation audience):\n{detail}"
        )


@pytest.mark.parametrize("doc", _harness_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_harness_surfaces_are_consumer_project_safe(doc: Path) -> None:
    hits = scan_audience(doc.read_text(encoding="utf-8"), HARNESS_MARKERS)
    if hits:
        rel = doc.relative_to(REPO_ROOT)
        detail = "\n".join(f"  {rel}:{n} [{name}] {line}" for n, name, line in hits)
        pytest.fail(
            "skill/command assumes the little-loops source checkout; it runs in "
            f"consuming projects (see CONTRIBUTING.md § Documentation Audience):\n{detail}"
        )
