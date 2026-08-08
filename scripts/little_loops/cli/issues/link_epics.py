"""ll-issues link-epics: cluster orphan issues, propose EPIC assignment/synthesis (FEAT-2942).

An "orphan" is an open BUG/FEAT/ENH issue with both `parent:` and `epic:`
unset. `assign` scores orphans against existing open EPICs; `synthesize`
union-find clusters unmatched orphans against each other. Both modes are
proposal-only unless `--apply` is passed; `--apply` is unsupported for
`synthesize` (EPIC creation is FEAT-2947's responsibility, not this
subcommand's).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

_ORPHAN_TYPE_PREFIXES = frozenset({"BUG", "FEAT", "ENH"})
_CHILDREN_HEADING_RE = re.compile(r"^##\s+Children\s*$", re.MULTILINE)


def _tier_for_score(score: float) -> str:
    """Map a similarity score to a HIGH/MEDIUM/LOW confidence tier.

    Boundaries carried over from the skill prose being replaced:
    score >= 0.7 -> HIGH, 0.4 <= score < 0.7 -> MEDIUM, score < 0.4 -> LOW.
    """
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"


@dataclass
class EpicProposal:
    """A scored orphan-to-EPIC assignment proposal."""

    orphan_id: str
    epic_id: str
    score: float
    tier: str

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict, rounding score to 3 decimals."""
        return {
            "orphan_id": self.orphan_id,
            "epic_id": self.epic_id,
            "score": round(self.score, 3),
            "tier": self.tier,
        }


@dataclass
class ClusterProposal:
    """A union-find cluster of similar orphans, proposed as a new EPIC."""

    member_ids: list[str]
    placeholder_title: str
    modal_priority: str
    pairwise_min_score: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict, rounding scores to 3 decimals."""
        return {
            "member_ids": sorted(self.member_ids),
            "placeholder_title": self.placeholder_title,
            "modal_priority": self.modal_priority,
            "pairwise_min_score": round(self.pairwise_min_score, 3),
        }


def is_orphan(info: IssueInfo) -> bool:
    """True when *info* is an open BUG/FEAT/ENH issue with no EPIC assignment."""
    prefix = info.issue_id.split("-", 1)[0]
    return prefix in _ORPHAN_TYPE_PREFIXES and info.parent is None and info.epic is None


def propose_assignments(
    orphans: list[IssueInfo], epics: list[IssueInfo], threshold: float
) -> list[EpicProposal]:
    """Score every orphan x EPIC pair via title word-overlap, filtered by *threshold*.

    Args:
        orphans: Candidate orphan issues.
        epics: Candidate open EPIC issues.
        threshold: Minimum score for a proposal to be included.

    Returns:
        Proposals sorted by score descending, then orphan_id, then epic_id
        (deterministic tiebreak for equal-score pairs).
    """
    from little_loops.text_utils import calculate_word_overlap, extract_words

    epic_words = [(epic, extract_words(epic.title)) for epic in epics]

    proposals: list[EpicProposal] = []
    for orphan in orphans:
        orphan_words = extract_words(orphan.title)
        for epic, words in epic_words:
            score = calculate_word_overlap(orphan_words, words)
            if score >= threshold:
                proposals.append(
                    EpicProposal(
                        orphan_id=orphan.issue_id,
                        epic_id=epic.issue_id,
                        score=score,
                        tier=_tier_for_score(score),
                    )
                )

    proposals.sort(key=lambda p: (-p.score, p.orphan_id, p.epic_id))
    return proposals


class _UnionFind:
    """Minimal disjoint-set structure keyed by issue ID."""

    def __init__(self, ids: list[str]) -> None:
        self._parent = {issue_id: issue_id for issue_id in ids}

    def find(self, issue_id: str) -> str:
        while self._parent[issue_id] != issue_id:
            self._parent[issue_id] = self._parent[self._parent[issue_id]]
            issue_id = self._parent[issue_id]
        return issue_id

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _placeholder_title(members: list[IssueInfo], top_n: int = 4) -> str:
    """Derive a placeholder cluster title from the members' most frequent words."""
    from little_loops.text_utils import extract_words

    counts: Counter[str] = Counter()
    for member in members:
        counts.update(extract_words(member.title))
    top_words = [word for word, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]]
    return " ".join(word.title() for word in top_words)


def synthesize_clusters(orphans: list[IssueInfo], min_score: float) -> list[ClusterProposal]:
    """Union-find cluster orphans on pairwise title word-overlap >= *min_score*.

    Args:
        orphans: Candidate orphan issues.
        min_score: Minimum pairwise score for an edge to union two orphans.

    Returns:
        ClusterProposal list for clusters with 2+ members (singletons are not
        proposed), sorted by member count descending then first member_id.
    """
    from little_loops.text_utils import calculate_word_overlap, extract_words

    if len(orphans) < 2:
        return []

    word_sets = [(info, extract_words(info.title)) for info in orphans]
    uf = _UnionFind([info.issue_id for info in orphans])
    edge_scores: dict[frozenset[str], float] = {}

    for i, (info_a, words_a) in enumerate(word_sets):
        for info_b, words_b in word_sets[i + 1 :]:
            score = calculate_word_overlap(words_a, words_b)
            if score >= min_score:
                uf.union(info_a.issue_id, info_b.issue_id)
                edge_scores[frozenset((info_a.issue_id, info_b.issue_id))] = score

    by_root: dict[str, list[IssueInfo]] = {}
    for info in orphans:
        by_root.setdefault(uf.find(info.issue_id), []).append(info)

    clusters: list[ClusterProposal] = []
    for members in by_root.values():
        if len(members) < 2:
            continue
        member_ids = {m.issue_id for m in members}
        cluster_edge_scores = [score for pair, score in edge_scores.items() if pair <= member_ids]
        priorities = Counter(m.priority for m in members)
        modal_priority = min(priorities.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        clusters.append(
            ClusterProposal(
                member_ids=sorted(member_ids),
                placeholder_title=_placeholder_title(members),
                modal_priority=modal_priority,
                pairwise_min_score=min(cluster_edge_scores) if cluster_edge_scores else 0.0,
            )
        )

    clusters.sort(key=lambda c: (-len(c.member_ids), c.member_ids[0]))
    return clusters


def _section_bounds(content: str, heading_re: re.Pattern[str]) -> tuple[int, int] | None:
    """Return (body_start, body_end) byte offsets for a ``## Heading`` section."""
    match = heading_re.search(content)
    if not match:
        return None
    start = match.end()
    next_match = re.search(r"^##\s", content[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(content)
    return start, end


def apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path) -> None:
    """Write the orphan-side frontmatter and EPIC-side ``## Children`` append.

    Writes both `parent:` and `epic:` on the orphan (corpus convention is
    both fields, not `parent:` alone). Idempotent: re-running with the same
    proposal is a no-op on the EPIC body if the child is already listed.

    Args:
        proposal: The accepted assignment.
        orphan_path: Path to the orphan issue file.
        epic_path: Path to the target EPIC issue file.
    """
    from little_loops.file_utils import atomic_write
    from little_loops.frontmatter import update_frontmatter

    orphan_content = orphan_path.read_text(encoding="utf-8")
    new_orphan_content = update_frontmatter(
        orphan_content, {"parent": proposal.epic_id, "epic": proposal.epic_id}
    )
    atomic_write(orphan_path, new_orphan_content)

    epic_content = epic_path.read_text(encoding="utf-8")
    if re.search(rf"\b{re.escape(proposal.orphan_id)}\b", epic_content):
        return

    bullet = f"- **{proposal.orphan_id}** — (added by link-epics --apply)"
    bounds = _section_bounds(epic_content, _CHILDREN_HEADING_RE)
    if bounds is None:
        new_content = epic_content.rstrip("\n") + "\n\n## Children\n\n" + bullet + "\n"
    else:
        start, end = bounds
        section_body = epic_content[start:end]
        stripped = section_body.rstrip("\n")
        sep = "\n" if stripped.strip() else ""
        new_section_body = stripped + sep + "\n" + bullet + "\n"
        new_content = epic_content[:start] + new_section_body + epic_content[end:]

    atomic_write(epic_path, new_content)


def add_link_epics_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``link-epics`` subparser on *subs*."""
    from little_loops.cli_args import add_config_arg, add_json_arg

    p = subs.add_parser(
        "link-epics",
        help="Score orphan issues for EPIC assignment, or cluster them into new-EPIC proposals",
        description=(
            "Text-similarity clustering/scoring for orphan (parentless) issues. "
            "Distinct from `ll-issues clusters`, which visualizes existing "
            "dependency-edge relationships, not text similarity."
        ),
    )
    p.set_defaults(command="link-epics")
    p.add_argument(
        "--mode",
        choices=["assign", "synthesize"],
        default="assign",
        help="assign: score orphans against existing EPICs (default). "
        "synthesize: union-find cluster orphans against each other.",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=None,
        metavar="N",
        help="Minimum score to include (default: config.issues.link_epics.min_score)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write accepted assign-mode proposals; unsupported for --mode synthesize",
    )
    add_json_arg(p)
    add_config_arg(p)
    return p


def cmd_link_epics(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch assign/synthesize scoring and (optionally) apply proposals.

    Returns:
        0 on success, 1 on error (e.g. --apply with --mode synthesize).
    """
    from little_loops.issue_parser import find_issues

    mode: str = args.mode
    threshold: float = (
        args.threshold if args.threshold is not None else config.issues.link_epics.min_score
    )
    apply: bool = args.apply
    as_json: bool = getattr(args, "json", False)

    if apply and mode == "synthesize":
        print(
            "Error: --apply is not supported for --mode synthesize "
            "(EPIC creation is not implemented by this subcommand)",
            file=sys.stderr,
        )
        return 1

    all_issues = find_issues(config, type_prefixes=set(_ORPHAN_TYPE_PREFIXES) | {"EPIC"})
    orphans = [i for i in all_issues if is_orphan(i)]

    if mode == "assign":
        epics = [i for i in all_issues if i.issue_id.startswith("EPIC-")]
        proposals = propose_assignments(orphans, epics, threshold=threshold)
        applied: list[dict] = []
        if apply:
            by_id = {i.issue_id: i for i in all_issues}
            for proposal in proposals:
                orphan_info = by_id.get(proposal.orphan_id)
                epic_info = by_id.get(proposal.epic_id)
                if orphan_info is None or epic_info is None:
                    continue
                apply_assignment(proposal, orphan_path=orphan_info.path, epic_path=epic_info.path)
                applied.append(proposal.to_dict())

        if as_json:
            print_json(
                {
                    "proposals": [p.to_dict() for p in proposals],
                    "applied": applied,
                }
            )
        else:
            for p in proposals:
                print(f"{p.orphan_id} -> {p.epic_id}: {p.score:.3f} ({p.tier})")
            if apply:
                print(f"\nApplied {len(applied)} proposal(s).")
        return 0

    # mode == "synthesize"
    clusters = synthesize_clusters(orphans, min_score=threshold)
    if as_json:
        print_json({"clusters": [c.to_dict() for c in clusters], "applied": []})
    else:
        for c in clusters:
            print(
                f"[{c.placeholder_title}] {', '.join(c.member_ids)} "
                f"(min score: {c.pairwise_min_score:.3f}, modal priority: {c.modal_priority})"
            )
    return 0
