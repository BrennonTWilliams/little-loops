"""ll-verify-evidence: certify that quoted evidence exists in its cited artifact (BUG-3282).

`/ll:verify-issues` validates an issue's *code* claims but never checked that
quoted **evidence** — a snippet attributed to another artifact, usually
another `.issues/` file — actually appears there. An issue whose code
references are all accurate but whose motivating evidence is fabricated
passed verification and received `verify_verdict: VALID`. This module is the
deterministic gate that closes that gap.

**Scope.** Only evidence-bearing sections are in scope — ``## Current
Behavior``, ``## Steps to Reproduce``, ``## Root Cause``, ``## Motivation``,
``### Codebase Research Findings``. Forward-looking sections (``## Proposed
Solution``, ``## Expected Behavior``, ``## Implementation Steps``, ``##
Integration Map``, ``## Program Design``) quote code that intentionally does
not exist yet, so a presence check there is meaningless. This is an
allowlist, not a denylist: a section named in neither list is out of scope,
so a template addition can never silently widen the checker.

**Pipeline** (see BUG-3282 Program Design § Decision Rules for the full
rationale of each stage): section filter -> span extraction (fenced blocks
and inline-backtick runs) -> attribution (following-parenthetical, else
nearest-preceding mention, section-bounded, with a command-output exclusion)
-> span-kind filter (drop bare identifiers, command/skill invocations, and
inline output following an invocation) -> char floor -> baseline suppression
-> artifact resolution -> tiered match (working tree -> HEAD -> `git log
--all -p` -> `git log --all --follow -p`), each side normalized identically
(whitespace collapse + markdown-emphasis strip).

**Modes**, mirroring ``verify_private_refs``'s three enforcement points:

* **changed-files** (``ll-verify-evidence FILE...``) — whole-file scan, no
  baseline. The skill / host-hook invocation.
* **``--added-only FILE...``** — only spans on lines the staged diff adds.
  The pre-commit hook.
* **``--all``** — full scan of ``issues.base_dir``, compared against the
  tracked ID-keyed span-hash baseline at ``.ll/evidence-baseline.json``. This
  is the pytest CI gate.

A ``<!-- ll-evidence-ok: reason -->`` marker on the span's own or preceding
line suppresses that one finding — required for the *counter-example* class,
where an issue reports a fabricated quote and must therefore reproduce it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context
from little_loops.text_utils import SOURCE_EXTENSIONS, fence_spans, in_fence

if TYPE_CHECKING:
    pass

BASELINE_PATH = Path(".ll") / "evidence-baseline.json"

_SUPPRESS_RE = re.compile(r"ll-evidence-ok:\s*(.+?)\s*(?:-->|$)")

# Section scope is an allowlist (Decision Rules -> Section scope). A section
# heading text matching neither this set nor a "### " subsection variant is
# out of scope by default.
IN_SCOPE_SECTIONS = frozenset(
    {
        "Current Behavior",
        "Steps to Reproduce",
        "Root Cause",
        "Motivation",
        "Codebase Research Findings",
    }
)

# Raw-character floor. Bounded in (13, 24] by the flagship fixture: the
# shortest genuine fabrication is 24 raw chars ("- **(b) Drop the knob.**");
# the designated true-negative ("**Option A**") is 12. Measured on the raw
# span text, before normalization (Decision Rules -> Threshold).
MIN_SPAN_LEN = 20

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
_INLINE_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_ISSUE_ID_RE = re.compile(r"\b(?:P[0-5]-)?(?:BUG|FEAT|ENH|EPIC)-(\d+)\b")
_FILE_PATH_CANDIDATE_RE = re.compile(
    r"(?<![\w./])([A-Za-z0-9_.][\w/.-]*\.[A-Za-z0-9_]{1,6})(?::\d+(?:[-,]\d+)*)?(?!\w)"
)
_FOLLOWING_PAREN_RE = re.compile(r"^\s*\(([^)]*)\)")


def _looks_like_file_path(candidate: str) -> bool:
    """A path candidate is a real file-path mention, not a dotted symbol reference.

    Requires either a ``/`` (structural marker of a path) or a recognized
    source-file extension — a bare ``module.method`` code symbol (e.g.
    ``issue_parser.locate``) has neither and must not be misattributed as a
    file-path mention.
    """
    if "/" in candidate:
        return True
    ext = "." + candidate.rsplit(".", 1)[-1].lower()
    return ext in SOURCE_EXTENSIONS


# Command-output exclusion: a line whose backtick run is a shell invocation
# and that ends in a presentation verb attributes the next fenced block to
# *the command's output*, not to the artifact the command names.
_COMMAND_BINARIES = ("ll-", "git", "python3", "python", "ruff", "pytest")
_PRESENTATION_VERB_RE = re.compile(r"(returns|outputs|prints|emits|shows):\s*$")

# Span-kind filter (Decision Rules -> Span kind, load-bearing): a span is only
# checked if it is plausibly a *quote*, not a mention.
_SKILL_INVOCATION_RE = re.compile(r"^/ll:[a-z-]+")


@dataclass(frozen=True)
class Section:
    """One in-scope (or out-of-scope) heading-delimited chunk of an issue body."""

    name: str
    start: int
    end: int


@dataclass(frozen=True)
class CandidateSpan:
    """One quoted span extracted from an in-scope section, pre-filtering."""

    text: str  # raw span content, without backticks/fence delimiters
    start: int  # char offset in the full document
    end: int
    line: int  # 1-indexed line the span starts on
    section: str
    is_fence: bool


@dataclass(frozen=True)
class EvidenceFinding:
    """One evidence span verified absent from its cited artifact."""

    issue_path: Path
    section: str
    line: int
    span: str
    artifact: str


# ---------------------------------------------------------------------------
# Section scoping
# ---------------------------------------------------------------------------


def iter_sections(content: str) -> list[Section]:
    """Split *content* into heading-delimited chunks (## or ### level).

    Each :class:`Section` runs from just after its heading line to the start
    of the next ``##``/``###`` heading (or end of document). Section-bounded
    attribution (Decision Rules -> Attribution rule) relies on these
    boundaries: a mention never attributes a span across a heading.
    """
    matches = list(_HEADING_RE.finditer(content))
    sections: list[Section] = []
    for i, m in enumerate(matches):
        name = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append(Section(name=name, start=start, end=end))
    return sections


def in_scope_sections(content: str) -> list[Section]:
    """Sections whose heading text is in :data:`IN_SCOPE_SECTIONS` (allowlist)."""
    return [s for s in iter_sections(content) if s.name in IN_SCOPE_SECTIONS]


# ---------------------------------------------------------------------------
# Mention extraction (for attribution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mention:
    pos: int
    ref: str


def _extract_mentions(text: str, base_offset: int) -> list[Mention]:
    """Find issue-ID and file-path mentions in *text*, offset to the document."""
    mentions: list[Mention] = []
    for m in _ISSUE_ID_RE.finditer(text):
        mentions.append(Mention(pos=base_offset + m.start(), ref=m.group(0)))
    for m in _FILE_PATH_CANDIDATE_RE.finditer(text):
        if _looks_like_file_path(m.group(1)):
            mentions.append(Mention(pos=base_offset + m.start(), ref=m.group(1)))
    mentions.sort(key=lambda mm: mm.pos)
    return mentions


# ---------------------------------------------------------------------------
# Span extraction
# ---------------------------------------------------------------------------


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def extract_candidate_spans(content: str, section: Section) -> list[CandidateSpan]:
    """Extract fenced-block and inline-backtick spans within *section*.

    Fenced blocks reuse :func:`fence_spans`/:func:`in_fence`; inline runs are
    a new regex (``text_utils.py`` has no inline-backtick primitive — see
    BUG-3282 Codebase Research Findings). Both span forms matter: the
    flagship regression fixture's must-flag spans are all inline runs.
    """
    section_text = content[section.start : section.end]
    all_fences = fence_spans(content)
    spans: list[CandidateSpan] = []

    # Fenced blocks whose span lies inside this section.
    for fs, fe in all_fences:
        if fs >= section.start and fe <= section.end:
            raw = content[fs:fe]
            # Strip the delimiter lines themselves, keep the body.
            body_lines = raw.splitlines()
            body = "\n".join(body_lines[1:-1]) if len(body_lines) > 2 else ""
            spans.append(
                CandidateSpan(
                    text=body,
                    start=fs,
                    end=fe,
                    line=_line_number(content, fs),
                    section=section.name,
                    is_fence=True,
                )
            )

    # Inline backtick runs, excluding anything inside a fence.
    for m in _INLINE_BACKTICK_RE.finditer(section_text):
        start = section.start + m.start()
        end = section.start + m.end()
        if in_fence(start, end, all_fences):
            continue
        spans.append(
            CandidateSpan(
                text=m.group(1),
                start=start,
                end=end,
                line=_line_number(content, start),
                section=section.name,
                is_fence=False,
            )
        )

    spans.sort(key=lambda s: s.start)
    return spans


# ---------------------------------------------------------------------------
# Command-output exclusion
# ---------------------------------------------------------------------------


def _preceding_nonblank_line(content: str, offset: int) -> str | None:
    """Return the nearest non-blank line before *offset*, crossing blank lines."""
    line_start = content.rfind("\n", 0, offset)
    while True:
        prev_end = line_start
        if prev_end <= 0:
            return None
        prev_start = content.rfind("\n", 0, prev_end)
        line = content[prev_start + 1 : prev_end]
        if line.strip():
            return line
        line_start = prev_start


def _is_command_invocation_line(line: str) -> bool:
    stripped = line.strip().lstrip("`").lstrip("- ").strip()
    return stripped.startswith(_COMMAND_BINARIES) or bool(_SKILL_INVOCATION_RE.match(stripped))


def is_command_output(content: str, span: CandidateSpan) -> bool:
    """True when *span* (a fence) is the output of a command, not a quote.

    Must reach the next fenced block across intervening blank lines — an
    adjacency-only check is dead code on the flagship fixture, where the
    invocation line and the fence it introduces are separated by one blank
    line (Decision Rules -> Attribution rule).
    """
    if not span.is_fence:
        return False
    preceding = _preceding_nonblank_line(content, span.start)
    if preceding is None:
        return False
    return _is_command_invocation_line(preceding) and bool(_PRESENTATION_VERB_RE.search(preceding))


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def attribute_span(content: str, span: CandidateSpan, mentions: list[Mention]) -> str | None:
    """Return the artifact reference *span* is attributed to, or ``None``.

    Following parenthetical wins; otherwise nearest preceding mention within
    the same section (Decision Rules -> Attribution rule, load-bearing).
    """
    following = content[span.end : span.end + 200]
    m = _FOLLOWING_PAREN_RE.match(following)
    if m:
        inner = m.group(1)
        id_match = _ISSUE_ID_RE.search(inner)
        if id_match:
            return id_match.group(0)
        path_match = _FILE_PATH_CANDIDATE_RE.search(inner)
        if path_match and _looks_like_file_path(path_match.group(1)):
            return path_match.group(1)

    preceding = [mm for mm in mentions if mm.pos < span.start]
    if not preceding:
        return None
    return preceding[-1].ref


# ---------------------------------------------------------------------------
# Span-kind filter (quote vs. mention)
# ---------------------------------------------------------------------------


def is_mention_class(span_text: str, line_text: str, span_start_col: int) -> bool:
    """True when *span_text* is a reference/mention rather than a claimed quote.

    Excluded shapes (Decision Rules -> Span kind):
    1. Bare identifiers/paths — no internal whitespace.
    2. Command/skill invocations — first token is a known binary or ``/ll:``.
    3. Inline output following an invocation span on the same line.
    4. A markdown heading marker (``## Some Section``) — a reference to a
       section *name* (template shape, e.g. "checks that a `## Steps to
       Reproduce` naming a live artifact..."), not a quote of literal file
       content.
    """
    stripped = span_text.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if " " not in stripped:
        return True
    if stripped.startswith(_COMMAND_BINARIES) or _SKILL_INVOCATION_RE.match(stripped):
        return True
    # Inline output following an invocation earlier on the same line: check
    # whether an excluded invocation backtick run precedes this span's column
    # on its own line.
    prefix = line_text[:span_start_col]
    for m in _INLINE_BACKTICK_RE.finditer(prefix):
        candidate = m.group(1).strip()
        if candidate and (
            " " not in candidate
            or candidate.startswith(_COMMAND_BINARIES)
            or _SKILL_INVOCATION_RE.match(candidate)
        ):
            if candidate.startswith(_COMMAND_BINARIES) or _SKILL_INVOCATION_RE.match(candidate):
                return True
    return False


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def is_suppressed(content: str, span_start: int) -> bool:
    """``<!-- ll-evidence-ok: reason -->`` on the span's own or preceding line."""
    line_start = content.rfind("\n", 0, span_start) + 1
    line_end = content.find("\n", span_start)
    if line_end == -1:
        line_end = len(content)
    own_line = content[line_start:line_end]
    if _SUPPRESS_RE.search(own_line):
        return True
    if line_start == 0:
        return False
    prev_end = line_start - 1
    prev_start = content.rfind("\n", 0, prev_end) + 1
    prev_line = content[prev_start:prev_end]
    return bool(_SUPPRESS_RE.search(prev_line))


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_EMPHASIS_CHARS_RE = re.compile(r"[*_`]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace and strip markdown emphasis/decoration.

    Identical treatment on both span and artifact text (Decision Rules ->
    Normalization, load-bearing): whitespace-only normalization is not
    enough — the fixture's own designated true-negative (``**Option A**``)
    only holds once emphasis is stripped too.
    """
    stripped = _EMPHASIS_CHARS_RE.sub("", text)
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip()
    return collapsed


def normalize_query(text: str) -> str:
    """:func:`normalize`, plus trailing sentence punctuation stripped."""
    return normalize(text).rstrip(" .,;:!?")


# ---------------------------------------------------------------------------
# Patch-text preparation
# ---------------------------------------------------------------------------

_DIFF_METADATA_PREFIXES = ("diff --git", "index ", "--- ", "+++ ", "@@")


def strip_patch_prefixes(patch_text: str) -> str:
    """Strip diff line-prefixes and metadata from ``git log -p`` output.

    Required before normalizing (Decision Rules -> Patch-text preparation,
    load-bearing): with the ``+``/``-``/space prefix left on, whitespace
    collapse lands those characters *between* joined lines, so a multi-line
    span never matches raw patch text (measured False on a known-present
    span). Removed (``-``) lines are kept deliberately — content that
    existed and was later deleted is exactly what the history tier is for.
    """
    out_lines: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith(_DIFF_METADATA_PREFIXES) or line.startswith("commit "):
            continue
        if line and line[0] in "+- ":
            out_lines.append(line[1:])
        elif not line.startswith(("Author:", "Date:")):
            out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Artifact resolution
# ---------------------------------------------------------------------------


def build_tracked_index(base_dir: Path) -> frozenset[str]:
    """Single ``git ls-files -z`` call, reused across every span's resolution.

    Resolution is per-candidate-span, and a corpus-wide scan can carry
    thousands of candidates; a subprocess per candidate does not scale
    (measured: ~0.4s/file at 100 files with a per-candidate ``git
    ls-files --error-unmatch`` call). One index built up front makes
    tracked-ness a set lookup instead.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return frozenset(n for n in names if n)


def _is_tracked(base_dir: Path, rel_path: str, tracked: frozenset[str] | None) -> bool:
    if tracked is not None:
        return rel_path in tracked
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_artifact(
    base_dir: Path,
    ref: str,
    config: object | None,
    tracked: frozenset[str] | None = None,
    cache: dict[str, str | None] | None = None,
) -> str | None:
    """Resolve *ref* (issue ID or file path) to a git-tracked repo-relative path.

    Fail-open (Decision Rules -> Fail-open): an artifact that does not
    resolve, or resolves to an untracked path, is skipped with no finding.
    *tracked*, when given, is a prebuilt index (:func:`build_tracked_index`)
    used instead of a per-call subprocess. *cache*, when given, memoizes by
    *ref* across calls — a corpus-wide scan repeats the same handful of
    heavily-cited issue IDs across hundreds of files, and
    ``resolve_issue_path`` globs the issue tree on every call.
    """
    if cache is not None and ref in cache:
        return cache[ref]

    id_match = _ISSUE_ID_RE.fullmatch(ref)
    if id_match and config is not None:
        from little_loops.issue_parser import resolve_issue_path

        path = resolve_issue_path(config, ref)  # type: ignore[arg-type]
        if path is None:
            result = None
        else:
            try:
                rel = str(path.resolve().relative_to(base_dir.resolve())).replace("\\", "/")
            except ValueError:
                rel = str(path)
            result = rel if _is_tracked(base_dir, rel, tracked) else None
    else:
        rel = ref.replace("\\", "/")
        result = rel if _is_tracked(base_dir, rel, tracked) else None

    if cache is not None:
        cache[ref] = result
    return result


# ---------------------------------------------------------------------------
# Tiered matching
# ---------------------------------------------------------------------------


def _read_working_tree(base_dir: Path, rel_path: str) -> str | None:
    try:
        return (base_dir / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _git_show(base_dir: Path, ref: str, rel_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def _git_log_patch(base_dir: Path, rel_path: str, *, follow: bool, n: int = 20) -> str | None:
    args = ["git", "log", "--all"]
    if follow:
        args.append("--follow")
    args += ["-p", f"-n{n}", "--", rel_path]
    try:
        result = subprocess.run(args, cwd=base_dir, capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


class ArtifactMatcher:
    """Tiered, artifact-major matcher: fetches each tier at most once per artifact.

    Working tree -> HEAD -> ``git log --all -p`` -> ``git log --all --follow
    -p``, short-circuiting as soon as every pending span for this artifact
    has matched. History tiers are single-process (Decision Rules -> History
    enumeration) rather than a per-revision ``git show`` loop.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._normalized_cache: dict[tuple[str, str], str | None] = {}

    def _tier_text(self, rel_path: str, tier: str) -> str | None:
        key = (rel_path, tier)
        if key in self._normalized_cache:
            return self._normalized_cache[key]
        if tier == "working_tree":
            raw = _read_working_tree(self.base_dir, rel_path)
            text = normalize(raw) if raw is not None else None
        elif tier == "head":
            raw = _git_show(self.base_dir, "HEAD", rel_path)
            text = normalize(raw) if raw is not None else None
        elif tier == "history":
            raw = _git_log_patch(self.base_dir, rel_path, follow=False)
            text = normalize(strip_patch_prefixes(raw)) if raw is not None else None
        else:  # history_follow
            raw = _git_log_patch(self.base_dir, rel_path, follow=True)
            text = normalize(strip_patch_prefixes(raw)) if raw is not None else None
        self._normalized_cache[key] = text
        return text

    def matches(self, rel_path: str, normalized_spans: list[str]) -> dict[str, bool]:
        """Return ``{normalized_span: found}`` for every span, artifact-major."""
        pending = set(normalized_spans)
        found: dict[str, bool] = {}
        for tier in ("working_tree", "head", "history", "history_follow"):
            if not pending:
                break
            text = self._tier_text(rel_path, tier)
            if text is None:
                continue
            hit_this_tier = {span for span in pending if span in text}
            for span in hit_this_tier:
                found[span] = True
            pending -= hit_this_tier
        for span in pending:
            found[span] = False
        return found


# ---------------------------------------------------------------------------
# Baseline (--all mode)
# ---------------------------------------------------------------------------


def _span_hash(normalized_span: str) -> str:
    return hashlib.sha256(normalized_span.encode("utf-8")).hexdigest()[:16]


def load_baseline(base_dir: Path) -> dict[str, set[str]]:
    """Read the tracked baseline: issue ID -> set of baselined span hashes.

    An empty/missing/malformed baseline is the strict reading — every finding
    is a regression — the safe failure direction (mirrors
    ``verify_private_refs.load_baseline``).
    """
    path = base_dir / BASELINE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    spans = data.get("spans") if isinstance(data, dict) else None
    if not isinstance(spans, dict):
        return {}
    result: dict[str, set[str]] = {}
    for issue_id, hashes in spans.items():
        if isinstance(hashes, list):
            result[str(issue_id)] = {str(h) for h in hashes}
    return result


def write_baseline(base_dir: Path, keyed_hashes: dict[str, set[str]]) -> Path:
    path = base_dir / BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Grandfathered evidence-unverifiable spans per issue ID (ll-verify-evidence "
            "--all). Keyed on the anchored numeric issue ID (not path — issue files are "
            "renamed constantly) and holding normalized span hashes (never the matched "
            "text). Regenerate with ll-verify-evidence --all --update-baseline. New spans "
            "fail the gate."
        ),
        "spans": {k: sorted(v) for k, v in sorted(keyed_hashes.items())},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _issue_id_from_frontmatter(content: str) -> str | None:
    m = re.search(r"^id:\s*(?:BUG|FEAT|ENH|EPIC)-(\d+)\s*$", content, re.MULTILINE)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Staged-added-lines filter (pre-commit --added-only mode)
# ---------------------------------------------------------------------------

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def staged_added_lines(base_dir: Path, paths: list[Path]) -> dict[str, set[int]] | None:
    """Map each path to the set of line numbers *added* in the staged diff.

    Ported from ``verify_private_refs.staged_added_lines`` (identical
    contract): ``None`` means the diff could not be computed and callers must
    fail open by scanning everything.
    """
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", *[str(p) for p in paths]],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    added: dict[str, set[int]] = {}
    current: str | None = None
    lineno = 0
    for raw in result.stdout.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current = target[2:] if target.startswith(("b/", "a/")) else None
            if target == "/dev/null":
                current = None
            continue
        if raw.startswith("@@"):
            match = _HUNK_RE.match(raw)
            lineno = int(match.group(1)) if match else 0
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            added.setdefault(current, set()).add(lineno)
            lineno += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            lineno += 1
    return added


def _tracked_issue_files(base_dir: Path, issues_base_dir: str) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", f"{issues_base_dir}/**/*.md"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [Path(n) for n in names if n]


# ---------------------------------------------------------------------------
# Top-level scan
# ---------------------------------------------------------------------------


def scan_file(
    base_dir: Path,
    path: Path,
    config: object | None,
    *,
    rel_path: Path | None = None,
    allowed_lines: set[int] | None = None,
    baseline: dict[str, set[str]] | None = None,
    matcher: ArtifactMatcher | None = None,
    tracked: frozenset[str] | None = None,
    resolution_cache: dict[str, str | None] | None = None,
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Scan one issue file for unverifiable evidence spans.

    Returns ``(findings, {artifact_ref: {normalized_span, ...}})`` — the
    second element groups this file's candidate spans by resolved artifact so
    callers can batch matching artifact-major.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], {}

    display_path = rel_path or path
    issue_id = _issue_id_from_frontmatter(content)
    baselined = baseline.get(issue_id, set()) if (baseline and issue_id) else set()

    candidates: list[tuple[CandidateSpan, str]] = []
    for section in in_scope_sections(content):
        section_mentions = _extract_mentions(content[section.start : section.end], section.start)
        for span in extract_candidate_spans(content, section):
            if span.is_fence and is_command_output(content, span):
                continue
            if len(span.text) < MIN_SPAN_LEN:
                continue
            if is_suppressed(content, span.start):
                continue
            if allowed_lines is not None and span.line not in allowed_lines:
                continue
            if not span.is_fence:
                line_start = content.rfind("\n", 0, span.start) + 1
                line_end = content.find("\n", span.start)
                line_end = len(content) if line_end == -1 else line_end
                line_text = content[line_start:line_end]
                if is_mention_class(span.text, line_text, span.start - line_start):
                    continue
            artifact = attribute_span(content, span, section_mentions)
            if artifact is None:
                continue
            candidates.append((span, artifact))

    if not candidates:
        return [], {}

    if matcher is None:
        matcher = ArtifactMatcher(base_dir)

    by_artifact: dict[str, list[CandidateSpan]] = {}
    resolved_ref: dict[str, str] = {}
    unresolved_spans: set[str] = set()
    for span, artifact in candidates:
        resolved = resolve_artifact(base_dir, artifact, config, tracked, resolution_cache)
        if resolved is None:
            unresolved_spans.add(id(span).__repr__())
            continue
        by_artifact.setdefault(resolved, []).append(span)
        resolved_ref[resolved] = artifact

    findings: list[EvidenceFinding] = []
    keyed_hashes: dict[str, set[str]] = {}
    for resolved_path, spans in by_artifact.items():
        to_check: dict[str, list[CandidateSpan]] = {}
        for span in spans:
            normalized = normalize_query(span.text)
            if not normalized:
                continue
            span_hash = _span_hash(normalized)
            if span_hash in baselined:
                continue
            to_check.setdefault(normalized, []).append(span)
        if not to_check:
            continue
        results = matcher.matches(resolved_path, list(to_check.keys()))
        for normalized, spans_for_norm in to_check.items():
            if results.get(normalized, False):
                continue
            if issue_id:
                keyed_hashes.setdefault(issue_id, set()).add(_span_hash(normalized))
            for span in spans_for_norm:
                findings.append(
                    EvidenceFinding(
                        issue_path=display_path,
                        section=span.section,
                        line=span.line,
                        span=span.text,
                        artifact=resolved_ref[resolved_path],
                    )
                )

    findings.sort(key=lambda f: f.line)
    return findings, keyed_hashes


def scan_paths(
    base_dir: Path,
    paths: list[Path],
    config: object | None,
    *,
    added_only: bool = False,
) -> list[EvidenceFinding]:
    """Scan an explicit file list (skill / host-hook / pre-commit mode)."""
    added = staged_added_lines(base_dir, paths) if added_only else None
    matcher = ArtifactMatcher(base_dir)
    tracked = build_tracked_index(base_dir)
    resolution_cache: dict[str, str | None] = {}
    findings: list[EvidenceFinding] = []
    for path in paths:
        abs_path = path if path.is_absolute() else base_dir / path
        if not abs_path.is_file():
            continue
        try:
            rel = abs_path.resolve().relative_to(base_dir.resolve())
        except ValueError:
            rel = path
        allowed_lines: set[int] | None = None
        if added_only:
            if added is None:
                allowed_lines = None  # fail closed -> scan everything
            else:
                allowed_lines = added.get(str(rel).replace("\\", "/"), set())
        file_findings, _ = scan_file(
            base_dir,
            abs_path,
            config,
            rel_path=rel,
            allowed_lines=allowed_lines,
            matcher=matcher,
            tracked=tracked,
            resolution_cache=resolution_cache,
        )
        findings.extend(file_findings)
    return findings


def scan_all(
    base_dir: Path, config: object, issues_base_dir: str
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Scan every tracked issue file under *issues_base_dir* (Proposed Solution step 8).

    Scoped to the issue corpus, not the whole repo: evidence attribution is
    an issue-file concern, and an unscoped ``--all`` would walk history for
    every source file.
    """
    baseline = load_baseline(base_dir)
    matcher = ArtifactMatcher(base_dir)
    tracked = build_tracked_index(base_dir)
    resolution_cache: dict[str, str | None] = {}
    all_findings: list[EvidenceFinding] = []
    all_hashes: dict[str, set[str]] = {}
    for rel in _tracked_issue_files(base_dir, issues_base_dir):
        findings, hashes = scan_file(
            base_dir,
            base_dir / rel,
            config,
            rel_path=rel,
            baseline=baseline,
            matcher=matcher,
            tracked=tracked,
            resolution_cache=resolution_cache,
        )
        all_findings.extend(findings)
        for k, v in hashes.items():
            all_hashes.setdefault(k, set()).update(v)
    return all_findings, all_hashes


def _scan_one_file_worker(
    base_dir: Path,
    rel: Path,
    baseline: dict[str, set[str]],
    tracked: frozenset[str],
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Process-pool worker: one file, its own config/matcher (not shareable)."""
    from little_loops.config import BRConfig

    config = BRConfig(base_dir)
    matcher = ArtifactMatcher(base_dir)
    return scan_file(
        base_dir,
        base_dir / rel,
        config,
        rel_path=rel,
        baseline=baseline,
        matcher=matcher,
        tracked=tracked,
    )


def scan_all_parallel(
    base_dir: Path,
    issues_base_dir: str,
    *,
    workers: int = 8,
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Parallel form of :func:`scan_all`, for one-time baseline seeding only.

    Implementation Steps step 4: the git calls are read-only and safe under a
    process pool, but the pool must stay out of the pytest path (a nested
    pool multiplies against pytest-xdist workers) — this is called only from
    ``--all --update-baseline``, never from the plain ``--all`` gate check.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    baseline = load_baseline(base_dir)
    tracked = build_tracked_index(base_dir)
    rels = _tracked_issue_files(base_dir, issues_base_dir)
    all_findings: list[EvidenceFinding] = []
    all_hashes: dict[str, set[str]] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_scan_one_file_worker, base_dir, rel, baseline, tracked) for rel in rels
        ]
        for fut in as_completed(futures):
            findings, hashes = fut.result()
            all_findings.extend(findings)
            for k, v in hashes.items():
                all_hashes.setdefault(k, set()).update(v)
    return all_findings, all_hashes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(findings: list[EvidenceFinding]) -> str:
    if not findings:
        return "ll-verify-evidence: PASS — no unverifiable evidence spans"
    lines = [f"ll-verify-evidence: {len(findings)} finding(s)", ""]
    for f in findings:
        lines.append(f"  {f.issue_path}:{f.line}: [{f.section}] quoted, attributed to {f.artifact}")
        lines.append(f"      “{f.span.strip()}” — not found in any revision of {f.artifact}")
    lines.append("")
    lines.append(
        "An evidence quote must exist in the artifact it is attributed to. Fix the "
        "quote, correct the attribution, or suppress a reviewed counter-example with "
        "'<!-- ll-evidence-ok: reason -->' on the line or the one above."
    )
    return "\n".join(lines)


def _findings_to_json(findings: list[EvidenceFinding], mode: str) -> dict:
    return {
        "ok": not findings,
        "mode": mode,
        "count": len(findings),
        "findings": [
            {
                "file": str(f.issue_path),
                "line": f.line,
                "section": f.section,
                "span": f.span,
                "artifact": f.artifact,
            }
            for f in findings
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_evidence(argv: list[str] | None = None) -> int:
    """Entry point for ``ll-verify-evidence``.

    Returns 0 when clean, 1 on any unsuppressed finding (changed-files /
    added-only mode) or any finding beyond baseline (``--all``).
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-evidence", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-evidence",
            description=(
                "Certify that quoted evidence attributed to a named artifact (file path "
                "or issue ID) actually exists there, at HEAD, in the working tree, or in "
                "any git revision (BUG-3282)."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s FILE...                     # Gate specific issue files (skill / hook)
  %(prog)s --added-only FILE...        # Only lines the staged diff adds (pre-commit)
  %(prog)s --all                       # Full scan of issues.base_dir vs. baseline
  %(prog)s --all --update-baseline     # Re-record the grandfathered corpus
  %(prog)s --all --json                # Machine-readable output

Suppress a reviewed counter-example (a quote reported *because* it is
fabricated) on the matching line or the one above:
  <!-- ll-evidence-ok: reason -->

Exit codes:
  0 - Clean (or no findings beyond baseline under --all)
  1 - One or more unsuppressed findings
""",
        )
        parser.add_argument(
            "paths",
            nargs="*",
            type=Path,
            help="Issue files to scan (changed-files mode). Omit with --all.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Scan every tracked issue file, comparing against the baseline.",
        )
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Rewrite the baseline from the current full scan (requires --all).",
        )
        parser.add_argument(
            "--added-only",
            action="store_true",
            help=(
                "Report only spans on lines added in the staged diff. Used by the "
                "pre-commit gate. Incompatible with --all."
            ),
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root to scan (default: cwd)",
        )
        add_json_arg(parser)

        args = parser.parse_args(argv)

        if args.update_baseline and not args.all:
            parser.error("--update-baseline requires --all")
        if args.added_only and args.all:
            parser.error("--added-only applies to changed-files mode, not --all")
        if not args.all and not args.paths:
            parser.error("provide one or more paths, or use --all")

        configure_output()
        logger = Logger(use_color=use_color_enabled())
        base_dir = args.directory or Path.cwd()

        from little_loops.config import BRConfig

        config = BRConfig(base_dir)

        if args.all:
            mode = "all"
            issues_base_dir = config.issues.base_dir
            if args.update_baseline:
                # Seeding is one-time and safe to parallelize (read-only git);
                # the steady-state gate path below stays serial and out of
                # the pool (Implementation Steps step 4).
                findings, hashes = scan_all_parallel(base_dir, issues_base_dir)
            else:
                findings, hashes = scan_all(base_dir, config, issues_base_dir)
            if args.update_baseline:
                write_baseline(base_dir, hashes)
                logger.success(f"Baseline updated: {BASELINE_PATH} ({len(findings)} occurrence(s))")
                return 0
            reported = findings
        else:
            mode = "paths"
            reported = scan_paths(base_dir, args.paths, config, added_only=args.added_only)

        if args.json:
            print_json(_findings_to_json(reported, mode))
            return 1 if reported else 0

        print(_format_text_report(reported))
        if reported:
            logger.error(f"{len(reported)} unverifiable evidence finding(s)")
            return 1
        logger.success("No unverifiable evidence spans")
        return 0
