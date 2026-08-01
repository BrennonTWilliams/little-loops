"""`ll-doctor --trim`: context-residency verdicts for the installed setup.

Answers a question the rest of `ll-doctor` does not: not "is this component
broken?" but "is it earning the context it costs?".  Every skill description,
command description, and `CLAUDE.md` line is injected at session start and
stays resident for the whole session, whether or not it is ever used.  A setup
accumulates monotonically; nothing in little-loops ever expired an instruction,
so the resident cost only ever grows.

Two signal sources, both already present in the tree:

- **Cost** — `len(text) // 4`, the repo-wide token approximation (see
  `doc_counts.check_skill_budget`, `cache_marking_oracle._estimate_tokens`).
- **Use** — `skill_events` invocation counts out of `.ll/history.db`, the same
  aggregation `ll-logs dead-skills` reports (`cli/logs.py:_aggregate_skill_stats`).

Verdicts are deliberately split by whether the evidence is decidable from those
two signals alone:

- ``trim`` — resident cost > 0 and *zero* recorded invocations in the window.
  Decidable: the component demonstrably returned nothing for what it charged.
- ``review`` — cost is non-trivial but usage is low, or (for memory sections)
  there is no per-line usage signal at all.  **Not** a recommendation to cut;
  a pointer at the sections worth applying judgment to.
- ``keep`` — used often enough in the window to have earned its residency.

The judgment rule this tool is built to serve — *"would the model have worked
this out on its own?"* — is not computable here, and the CLI does not pretend
to answer it.  For memory files it reports section-level cost and defers; the
verdict on a `CLAUDE.md` section belongs to whoever can read it against the
current model's behavior.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

# Memory files are injected verbatim at session start on every host.  Ordered
# most- to least-local; each is reported separately so a project-level bloat
# problem is not hidden behind a lean user-level file (or vice versa).
_MEMORY_CANDIDATES: tuple[tuple[str, str], ...] = (
    (".claude/CLAUDE.md", "project"),
    ("CLAUDE.md", "project"),
    (".ll/ll.local.md", "project"),
)

# An H2 section costing more than this is worth a deliberate keep/cut decision.
# ~250 tokens is roughly a screenful of prose — below it, the residency cost is
# not what is hurting you and flagging it is noise.
_SECTION_REVIEW_TOKENS = 250

# A skill/command whose description costs at least this much has to justify
# itself on usage; cheaper entries are left alone even when rarely invoked,
# since reclaiming ~10 tokens is not worth a review cycle.
_DESCRIPTION_REVIEW_TOKENS = 15

_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_RARELY_THRESHOLD = 2

Verdict = Literal["keep", "trim", "review"]


def _estimate_tokens(text: str) -> int:
    """Token estimate via the repo-wide ``len(text) // 4`` convention."""
    return len(text) // 4


@dataclass(frozen=True)
class TrimComponent:
    """One context-resident component and its residency verdict.

    `resident_tokens` is what the component costs *every session* — for a skill
    or command that is the description only, since the body loads on demand;
    for a memory section it is the whole section.  `invocations` is None when
    no usage signal applies to the component kind (memory files have no
    per-section telemetry), which is distinct from a recorded zero.
    """

    name: str
    kind: Literal["memory", "skill", "command"]
    scope: str
    resident_tokens: int
    invocations: int | None
    verdict: Verdict
    rationale: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "scope": self.scope,
            "resident_tokens": self.resident_tokens,
            "invocations": self.invocations,
            "verdict": self.verdict,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TrimReport:
    """Full `--trim` result: components plus the window they were scored over."""

    components: tuple[TrimComponent, ...]
    window_days: int
    usage_available: bool
    sessions_observed: int

    @property
    def reclaimable_tokens(self) -> int:
        """Per-session tokens held by components verdicted ``trim``."""
        return sum(c.resident_tokens for c in self.components if c.verdict == "trim")

    @property
    def total_resident_tokens(self) -> int:
        return sum(c.resident_tokens for c in self.components)

    def as_dict(self) -> dict:
        return {
            "window_days": self.window_days,
            "usage_available": self.usage_available,
            "sessions_observed": self.sessions_observed,
            "total_resident_tokens": self.total_resident_tokens,
            "reclaimable_tokens": self.reclaimable_tokens,
            "components": [c.as_dict() for c in self.components],
        }


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal `key: value` frontmatter parse, mirroring `doc_counts`.

    Deliberately not a YAML load: descriptions routinely contain unquoted `:`
    and other YAML-hostile punctuation, and a strict parse would drop exactly
    the long descriptions this report exists to surface.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#", "-")):
            continue
        key, sep, val = line.partition(":")
        if sep:
            fm[key.strip()] = val.strip()
    return fm


def _is_model_invocable(fm: dict[str, str]) -> bool:
    """False when frontmatter opts the entry out of the model-visible catalog.

    An opted-out entry costs no listing tokens, so it is out of scope for a
    residency report even though it still exists on disk.
    """
    return fm.get("disable-model-invocation", "").strip().lower() not in ("true", "yes", "1")


def _split_h2_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) pairs at H2 boundaries.

    Content before the first H2 is returned under the ``(preamble)`` heading so
    the section token counts sum to the whole file rather than silently
    dropping the header block.
    """
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4 :]

    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE))
    if not matches:
        stripped = body.strip()
        return [("(whole file)", body)] if stripped else []

    sections: list[tuple[str, str]] = []
    preamble = body[: matches[0].start()]
    if preamble.strip():
        sections.append(("(preamble)", preamble))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append((match.group(1).strip(), body[match.start() : end]))
    return sections


def _memory_components(root: Path) -> list[TrimComponent]:
    """One component per H2 section of each always-loaded memory file."""
    components: list[TrimComponent] = []
    for rel, scope in _MEMORY_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        for heading, section in _split_h2_sections(text):
            tokens = _estimate_tokens(section)
            if tokens >= _SECTION_REVIEW_TOKENS:
                verdict: Verdict = "review"
                rationale = (
                    f"{tokens} tokens resident every session; no per-section usage signal "
                    "exists — decide by hand whether the model would work this out unaided"
                )
            else:
                verdict = "keep"
                rationale = f"{tokens} tokens — below the {_SECTION_REVIEW_TOKENS}-token review bar"
            components.append(
                TrimComponent(
                    name=f"{rel} § {heading}",
                    kind="memory",
                    scope=scope,
                    resident_tokens=tokens,
                    invocations=None,
                    verdict=verdict,
                    rationale=rationale,
                )
            )
    return components


def _catalog_entries(root: Path) -> list[tuple[str, str, str]]:
    """Return (normalized_name, kind, description) for model-visible entries.

    Names are normalized the way `skill_events.skill_name` records them (the
    `ll-` prefix stripped), so they join directly against usage counts.
    """
    entries: list[tuple[str, str, str]] = []

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = _parse_frontmatter(text)
            if not _is_model_invocable(fm):
                continue
            name = skill_md.parent.name.removeprefix("ll-")
            entries.append((name, "skill", fm.get("description", "")))

    commands_dir = root / "commands"
    if commands_dir.is_dir():
        for command_md in sorted(commands_dir.glob("*.md")):
            try:
                text = command_md.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = _parse_frontmatter(text)
            if not _is_model_invocable(fm):
                continue
            name = command_md.stem.removeprefix("ll-")
            entries.append((name, "command", fm.get("description", "")))

    return entries


def _usage_counts(db_path: Path, *, cutoff: datetime | None) -> tuple[dict[str, int] | None, int]:
    """Per-skill invocation counts and observed session count from history.db.

    Returns ``(None, 0)`` when the DB or its `skill_events` table is absent —
    distinct from an empty dict (DB present, no rows in window).  Without this
    distinction a fresh install with no telemetry would score every component
    ``trim``, which is the opposite of true.
    """
    if not db_path.exists():
        return None, 0

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        try:
            rows = conn.execute("SELECT ts, session_id, skill_name FROM skill_events").fetchall()
        except sqlite3.OperationalError:
            return None, 0
    finally:
        conn.close()

    counts: dict[str, int] = defaultdict(int)
    sessions: set[str] = set()
    cutoff_iso = cutoff.isoformat() if cutoff is not None else None
    for ts, session_id, skill_name in rows:
        # Lexicographic compare on ISO-8601 is ordering-correct and avoids
        # parsing every row; malformed/empty timestamps fall outside any window.
        if cutoff_iso is not None and (ts or "") < cutoff_iso:
            continue
        counts[(skill_name or "unknown").removeprefix("ll-")] += 1
        if session_id:
            sessions.add(session_id)
    return dict(counts), len(sessions)


def _catalog_components(
    root: Path,
    counts: dict[str, int] | None,
    *,
    window_days: int,
    rarely_threshold: int,
) -> list[TrimComponent]:
    """Score each catalog entry's description residency against its usage."""
    components: list[TrimComponent] = []
    for name, kind, description in _catalog_entries(root):
        tokens = _estimate_tokens(description)

        if counts is None:
            verdict: Verdict = "keep"
            rationale = "no usage telemetry available — not scored"
            invocations: int | None = None
        else:
            invocations = counts.get(name, 0)
            if invocations == 0 and tokens > 0:
                verdict = "trim"
                rationale = (
                    f"{tokens} listing tokens every session, 0 invocations in "
                    f"{window_days}d — pays residency, returns nothing"
                )
            elif invocations <= rarely_threshold and tokens >= _DESCRIPTION_REVIEW_TOKENS:
                verdict = "review"
                rationale = (
                    f"{tokens} listing tokens for {invocations} invocation(s) in {window_days}d"
                )
            else:
                verdict = "keep"
                rationale = f"{invocations} invocation(s) in {window_days}d"

        components.append(
            TrimComponent(
                name=name,
                kind=kind,  # type: ignore[arg-type]
                scope="project",
                resident_tokens=tokens,
                invocations=invocations,
                verdict=verdict,
                rationale=rationale,
            )
        )
    return components


_VERDICT_ORDER = {"trim": 0, "review": 1, "keep": 2}


def collect_trim_report(
    root: Path | None = None,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    rarely_threshold: int = _DEFAULT_RARELY_THRESHOLD,
    db_path: Path | None = None,
) -> TrimReport:
    """Build the residency report for the setup installed under `root`.

    Args:
        root: Project root (defaults to cwd).
        window_days: Usage lookback. Shorter windows make more components look
            dead; the default is deliberately generous.
        rarely_threshold: Invocation count at or below which a costly entry is
            flagged ``review``.
        db_path: History DB override (defaults to ``<root>/.ll/history.db``).
    """
    if root is None:
        root = Path.cwd()
    if db_path is None:
        db_path = root / ".ll" / "history.db"

    cutoff = datetime.now().astimezone() - timedelta(days=window_days)
    counts, sessions = _usage_counts(db_path, cutoff=cutoff)

    components = _memory_components(root) + _catalog_components(
        root, counts, window_days=window_days, rarely_threshold=rarely_threshold
    )
    components.sort(
        key=lambda c: (_VERDICT_ORDER[c.verdict], -c.resident_tokens, c.name),
    )

    return TrimReport(
        components=tuple(components),
        window_days=window_days,
        usage_available=counts is not None,
        sessions_observed=sessions,
    )


_VERDICT_SYMBOLS = {"trim": "✂", "review": "?", "keep": "✓"}


def render_trim_report(report: TrimReport) -> None:
    """Print the `--trim` section in the doctor text format."""
    from little_loops.cli.output import table

    print()
    print("Context Residency (--trim)")
    print("─" * 40)

    if not report.usage_available:
        print("  No usage telemetry (.ll/history.db skill_events) — usage verdicts skipped.")
        print("  Memory-file section costs are still reported below.")
    else:
        print(f"  Window: {report.window_days}d  ·  {report.sessions_observed} session(s) observed")

    scored = [c for c in report.components if c.verdict != "keep"]
    if not scored:
        print("  ✓  Nothing flagged — every component is either used or cheap.")
        return

    rows = [
        [
            _VERDICT_SYMBOLS[c.verdict],
            c.name,
            c.kind,
            str(c.resident_tokens),
            "—" if c.invocations is None else str(c.invocations),
            c.rationale,
        ]
        for c in scored
    ]
    print(table(["", "Component", "Kind", "Tokens", "Uses", "Verdict"], rows))
    print()
    print(
        f"  Resident: {report.total_resident_tokens:,} tokens  ·  "
        f"Reclaimable (trim): {report.reclaimable_tokens:,} tokens/session"
    )
    print("  ✂ = 0 uses in window.  ? = review by hand: would the model work it out unaided?")
