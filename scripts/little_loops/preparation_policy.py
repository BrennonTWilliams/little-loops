"""Preparation routing policy for autodev's second pass (ENH-3623 Phase A: ENH-3630).

Expresses the 39-state preparation ladder that lives in ``autodev.yaml`` today as a
pure function over an issue snapshot and an append-only per-issue fact log::

    next_preparation_step(config, issue_id, run_dir, *, readiness_threshold,
                          outcome_threshold) == decide(snapshot_issue(...), load_facts(...))

The dispatch loop (``loops/prepare-issue-policy.yaml`` on ``main``, still only a test
fixture at ``scripts/tests/fixtures/loops/prepare-issue-policy.yaml`` until ENH-3623
Phase B) runs one command per step (the inner ``refine-to-ready-issue`` run or one
slash command) and calls three writers, which are the only side-effecting entry
points:

- ``ll-issues prep step`` -- replay the open intent of this pass, else ``decide()``,
  append its observations and the new intent, run the intent's idempotent
  preconditions, and print the :class:`StepKind` token the loop routes on;
- ``ll-issues prep record [--guard2]`` -- append the ``done`` fact for the open intent;
- ``ll-issues prep apply`` -- the sole writer of the terminal effects (ledger row ->
  set-status -> run record -> inflight clear), idempotent through its own done fact.

Fact log: ``<run_dir>/prep-facts/<ID>.jsonl``, one JSON object per line
``{pass, seq, kind: intent|done|obs, step, payload}``. The pass id comes from
``<run_dir>/prep-pass-<ID>`` (written by autodev's ``dequeue_next``, ENH-3623 Phase B;
absent until then, so :func:`current_pass` reads pass ``"0"``). The log replaces the
run_dir handshake files (see the spike report's aggregate table,
``thoughts/spikes/preparation-policy-spike.md``).

Layering (ENH-3630 § Proposed Solution, decided): only this pure layer --
:class:`StepKind`, :class:`Step`, :class:`Facts`, :class:`IssueSnapshot` and
:func:`decide` -- is ``little_loops.cli``-free (enforced by an import-boundary test).
The writers and :func:`snapshot_issue` / :func:`next_preparation_step` import from
``little_loops.cli.*`` lazily, inside the function, because every input they need
lives there. Nothing is relocated or renamed.

Ported from the ENH-3621 spike (tag ``spike/preparation-policy-a51621302``, report
``thoughts/spikes/preparation-policy-spike.md``), applying ENH-3623's production
hardening and four fixes that landed on ``main`` after the spike branched (merge base
``9f7c5dc27``): BUG-3624 (Q1, superseded-marker count is no longer masked by blocking
format-check gaps), ENH-3625 (Q3, the first post-refine gate is design-aware, matching
every later gate), BUG-3620 (the design-gate-failed check reads the *current*
check-design verdict every time -- no sticky marker/observation) and BUG-3622 (the FSM
executor's rate-limit detection now reaches ``next:`` states, so
``prep apply --rate-limited`` is live, not dead code).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.run_record import RunRecord

FACTS_DIR = "prep-facts"
PASS_PREFIX = "prep-pass-"

#: Policy infra stop: more done facts than this in one pass is a runaway ladder.
#:
#: Derived from the ladder's own budgets (ENH-3623 § Production additions item 1),
#: not the spike's empirical ``MAX_DONE_PER_PASS = 15`` (max observed ~10 across the
#: spike's 28 end-to-end scenarios): at most 4 inner epochs per pass (one
#: ``RUN_CHILD`` each, bounded by ``refine_cap``/``spike_runs`` re-entry limits), each
#: epoch worst-casing one done fact per wire/rescore/size-review/reconcile leg (4),
#: plus one atomic and one design remedy leg overall (not per epoch, since both are
#: gated by their own "attempted" flag) -- 4 * (1 + 4) + 2 = 22.
DONE_FACT_CAP = 22
#: A command step visits select_step -> run_* -> record_step (3 states); a
#: SIZE_REVIEW step additionally visits classify_guard2 (4 states); the final
#: select_step -> apply_outcome -> done/failed tail is 3 more. 4 * cap + 3 upper-bounds
#: every legal worst-case ladder (see ENH-3630's "Budget arithmetic" for why
#: 3 * cap + 3 undercounts). Replaces the spike YAML's hardcoded ``max_steps: 80``.
MAX_STEPS = 4 * DONE_FACT_CAP + 3
#: Backward-compatible alias for the spike's constant name.
MAX_DONE_PER_PASS = DONE_FACT_CAP
RESOLVED_STATUSES = ("done", "completed", "cancelled")


class StepKind(str, Enum):
    """What the dispatch loop runs next (the ``select_step`` route token)."""

    RUN_CHILD = "RUN_CHILD"
    WIRE = "WIRE"
    REFINE_GAP = "REFINE_GAP"
    RESCORE = "RESCORE"
    RECONCILE = "RECONCILE"
    SIZE_REVIEW = "SIZE_REVIEW"
    GO_NO_GO = "GO_NO_GO"
    FINISH = "FINISH"
    STOP = "STOP"


TERMINAL_KINDS = (StepKind.FINISH, StepKind.STOP)


@dataclass(frozen=True)
class Step:
    """One policy decision.

    ``payload`` carries the explicit return address (``role`` / ``origin`` /
    ``attempt``), budget flags (``pre_deferral``, ``contradiction_only``), the
    idempotent ``preconditions`` the step writer runs before the command, and for
    FINISH/STOP the ``outcome``. ``observations`` are facts ``decide()`` derived
    on the way (pre-readiness backfill) that the step writer appends before the
    intent.
    """

    kind: StepKind
    seq: int
    payload: Mapping[str, Any]
    reason: str
    evidence: tuple[str, ...] = ()
    observations: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Fact:
    """One fact-log line."""

    pass_id: str
    seq: int
    kind: str  # intent | done | obs
    step: str
    payload: Mapping[str, Any]

    def to_json(self) -> str:
        return json.dumps(
            {
                "pass": self.pass_id,
                "seq": self.seq,
                "kind": self.kind,
                "step": self.step,
                "payload": dict(self.payload),
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class Facts:
    """The fact log of one issue, viewed from the current pass."""

    pass_id: str
    facts: tuple[Fact, ...] = ()

    # -- views -------------------------------------------------------------
    def in_pass(self) -> list[Fact]:
        return [f for f in self.facts if f.pass_id == self.pass_id]

    def intents(self, *, run: bool = False) -> list[Fact]:
        src = self.facts if run else self.in_pass()
        return [f for f in src if f.kind == "intent"]

    def dones(self) -> list[Fact]:
        return [f for f in self.in_pass() if f.kind == "done"]

    def last_done(self) -> Fact | None:
        d = self.dones()
        return d[-1] if d else None

    def open_intent(self) -> Fact | None:
        done_seqs = {f.seq for f in self.dones()}
        for f in reversed(self.intents()):
            if f.seq not in done_seqs:
                return f
        return None

    def next_seq(self) -> int:
        seqs = [f.seq for f in self.in_pass() if f.kind in ("intent", "done")]
        return (max(seqs) + 1) if seqs else 1

    def obs(self, name: str, *, run: bool = False) -> list[Fact]:
        src = self.facts if run else self.in_pass()
        return [f for f in src if f.kind == "obs" and f.step == name]

    # -- aggregates (the handshake files these replace are named inline) ----
    def any_intent(self, kind: StepKind, *, run: bool = False, **match: Any) -> bool:
        return any(
            f.step == kind.value and all(f.payload.get(k) == v for k, v in match.items())
            for f in self.intents(run=run)
        )

    def count_intents(self, kind: StepKind, **match: Any) -> int:
        return sum(
            1
            for f in self.intents()
            if f.step == kind.value and all(f.payload.get(k) == v for k, v in match.items())
        )

    def repair_cycles(self) -> int:
        """``autodev-repair-cycle-count.txt``: counted done facts in this pass."""
        n = 0
        for f in self.dones():
            p = f.payload
            if f.step == StepKind.RUN_CHILD.value and p.get("terminal") == "done":
                n += 1
            elif f.step == StepKind.WIRE.value and p.get("role") == "artifacts":
                n += 1
            elif f.step in (StepKind.SIZE_REVIEW.value, StepKind.RECONCILE.value):
                n += 1
            elif f.step == StepKind.REFINE_GAP.value and p.get("role") == "design":
                n += 1
        return n

    def pre_readiness(self) -> str:
        """``autodev-pre-readiness.txt``: dequeue snapshot, then the latest backfill."""
        vals = self.obs("pre_readiness")
        if vals:
            return str(vals[-1].payload.get("value") or "")
        start = self.obs("pass_start")
        return str(start[-1].payload.get("pre_readiness") or "") if start else ""

    def baseline_ids(self) -> frozenset[str]:
        """``autodev-pre-ids.txt`` as written by ``dequeue_next`` for this pass."""
        start = self.obs("pass_start")
        return frozenset(start[-1].payload.get("pre_ids") or ()) if start else frozenset()

    def last_size_review(self) -> Fact | None:
        srs = [f for f in self.dones() if f.step == StepKind.SIZE_REVIEW.value]
        return srs[-1] if srs else None

    def needs_child_scan(self) -> bool:
        """Whether ``decide()`` might reach DETECT or POST_SIZE_REVIEW this call.

        DETECT is reached only from a last-done ``RUN_CHILD`` or ``RESCORE`` step;
        POST_SIZE_REVIEW only from a last-done ``SIZE_REVIEW`` step (see
        ``_Decider.run()``'s dispatch). Every other last-done kind, and pass start (no
        done fact yet), never reaches either. Used by :func:`snapshot_issue` to skip
        the project-wide child-provenance scan (ENH-3623 § Production additions item
        1: "make the snapshot lazy") on the steps that can't need it. A false
        positive here (scanning when the branch actually taken doesn't end up calling
        ``children()``) only costs the scan; a false negative would silently drop
        real children, so this is a necessary-but-not-sufficient condition by design.
        """
        last = self.last_done()
        return last is not None and last.step in (
            StepKind.RUN_CHILD.value,
            StepKind.RESCORE.value,
            StepKind.SIZE_REVIEW.value,
        )


@dataclass(frozen=True)
class IssueSnapshot:
    """Everything the ladder reads from the issue, config and child-owned files."""

    issue_id: str
    exists: bool = True
    status: str = "open"
    confidence: int | None = None
    outcome: int | None = None
    waived: bool = False
    decision_needed: bool = False
    missing_artifacts: bool = False
    reconcile_attempted: bool = False
    spike_needed: bool = False
    spike_attempted: bool = False
    score_ambiguity: int = 0
    score_complexity: int = 0
    score_test_coverage: int = 0
    score_change_surface: int = 0
    design_failed: bool = False
    gate_verdict: str = "none"
    #: ``next-obligation`` with the six tier-1 skips and ``--honor-waiver``; ``ERROR``
    #: when the selector exits non-zero (the classify ``_error`` route today).
    obligation_post: str = "NONE"
    superseded_markers: int = 0
    refine_count: int = 0
    refine_cap: int = 5
    spike_runs: int = 0
    readiness_threshold: int = 85
    outcome_threshold: int = 65
    #: Active issues whose file carries ``parent: <ID>`` / "Decomposed from <ID>".
    #: Populated only when :meth:`Facts.needs_child_scan` says the ladder might reach
    #: DETECT / POST_SIZE_REVIEW this call (lazy: see :func:`snapshot_issue`).
    child_candidates: frozenset[str] = frozenset()

    @property
    def resolved(self) -> bool:
        return self.status in RESOLVED_STATUSES

    @property
    def scores_absent(self) -> bool:
        return self.confidence is None or self.outcome is None

    def check_readiness_passes(self) -> bool:
        """``check-readiness --honor-waiver`` exit 0 (exit 3 on absent is a fail)."""
        if self.scores_absent:
            return False
        outcome_ok = self.waived or (self.outcome or 0) >= self.outcome_threshold
        return (self.confidence or 0) >= self.readiness_threshold and outcome_ok

    def inline_gate_passes(self) -> bool:
        """The RASR/RAAR inline-Python gate (absent scores read as 0)."""
        conf = self.confidence or 0
        outc = self.outcome or 0
        return conf >= self.readiness_threshold and (self.waived or outc >= self.outcome_threshold)


# ---------------------------------------------------------------------------
# decide()
# ---------------------------------------------------------------------------


class _Decider:
    """One ``decide()`` evaluation: accumulates observations, then returns a Step."""

    def __init__(self, snap: IssueSnapshot, facts: Facts) -> None:
        self.s = snap
        self.f = facts
        self.seq = facts.next_seq()
        self.observations: list[tuple[str, Any]] = []
        self.carry_preconditions: list[str] = []
        self.trail: list[str] = []

    # -- step constructors ----------------------------------------------------
    def step(self, kind: StepKind, reason: str, **payload: Any) -> Step:
        pre = list(payload.pop("preconditions", []))
        if kind is StepKind.RUN_CHILD:
            pre.insert(0, "clear_records")
        pre = [*self.carry_preconditions, *pre]
        if pre:
            payload["preconditions"] = pre
        return Step(
            kind=kind,
            seq=self.seq,
            payload=payload,
            reason=reason,
            evidence=tuple(self.trail),
            observations=tuple(self.observations),
        )

    def finish(self, outcome: str, reason: str, **extra: Any) -> Step:
        return self.step(StepKind.FINISH, reason, outcome=outcome, **extra)

    def stop(self, outcome: str, reason: str, **extra: Any) -> Step:
        return self.step(StepKind.STOP, reason, outcome=outcome, **extra)

    def pre_readiness(self) -> str:
        for n, v in reversed(self.observations):
            if n == "pre_readiness":
                return str(v)
        return self.f.pre_readiness()

    def backfill_pre_readiness(self, value: str) -> None:
        self.observations.append(("pre_readiness", value))

    def children(self) -> list[str]:
        return sorted(self.s.child_candidates - self.f.baseline_ids())

    # -- budgets --------------------------------------------------------------
    def decision_used(self) -> bool:
        return self.f.any_intent(StepKind.RUN_CHILD, role="decision")

    def proof_used(self) -> bool:
        return self.f.any_intent(StepKind.RUN_CHILD, role="proof")

    def pre_deferral_fired(self) -> bool:
        return any(f.payload.get("pre_deferral") for f in self.f.intents())

    def design_remedy_attempted(self) -> bool:
        return self.f.any_intent(StepKind.REFINE_GAP, run=True, role="design")

    def go_no_go_attempted(self) -> bool:
        return self.f.any_intent(StepKind.GO_NO_GO, run=True)

    def under_cap(self) -> bool:
        return self.s.refine_count < self.s.refine_cap

    # -- entry -----------------------------------------------------------------
    def run(self) -> Step:
        if len(self.f.dones()) > DONE_FACT_CAP:
            return self.stop("ladder_error", f"more than {DONE_FACT_CAP} done facts")
        last = self.f.last_done()
        if last is None:
            self.trail.append("pass start")
            return self.step(StepKind.RUN_CHILD, "first inner run", role="first")
        kind, p = last.step, last.payload
        self.trail.append(f"after {kind}{_fmt_payload(p)}")
        if kind == StepKind.RUN_CHILD.value:
            return self.after_child(p)
        if kind == StepKind.WIRE.value and p.get("role") == "artifacts":
            return self.step(StepKind.REFINE_GAP, "post-wire gap refine", role="post_wire")
        if kind == StepKind.REFINE_GAP.value and p.get("role") == "post_wire":
            return self.rescore("wire")
        if kind == StepKind.RESCORE.value:
            return self.after_rescore(str(p.get("origin")), int(p.get("attempt") or 1))
        if kind == StepKind.SIZE_REVIEW.value:
            return self.post_size_review()
        if kind == StepKind.RECONCILE.value:
            return self.rescore("reconcile")
        if kind == StepKind.WIRE.value and p.get("role") == "atomic":
            return self.rescore("atomic")
        if kind == StepKind.REFINE_GAP.value and p.get("role") == "design":
            return self.rescore("reconcile")
        if kind == StepKind.GO_NO_GO.value:
            return self.after_go_no_go()
        if kind in (StepKind.FINISH.value, StepKind.STOP.value):
            return self.step(StepKind(kind), "pass already applied", outcome=p.get("outcome"))
        return self.stop("ladder_error", f"no continuation after {kind}")

    # -- continuations ----------------------------------------------------------
    def after_child(self, p: Mapping[str, Any]) -> Step:
        terminal = p.get("terminal")
        token = str(p.get("token") or "MISSING")
        if terminal == "failed":
            return self.stop("child_stop", f"inner loop failed ({token})")
        if terminal != "done":
            return self.stop("inner_error", f"inner loop ended {terminal}")
        if token == "CANCELLED":
            return self.finish("cancelled", "inner loop recorded CANCELLED")
        if token == "DECOMPOSED":
            self.trail.append("inner DECOMPOSED -> detect")
            return self.detect()
        # ENH-3625 (Q3): the first post-refine gate is design-aware too, matching
        # every later gate in the ladder (recheck_scores/RASR/RAAR) -- option A.
        if self.s.check_readiness_passes() and not self.s.design_failed:
            self.trail.append("check_passed yes")
            return self.pre_implement()
        self.trail.append("check_passed no")
        return self.post_refine_select()

    def rescore(self, origin: str) -> Step:
        return self.step(
            StepKind.RESCORE,
            f"rescore after {origin}",
            origin=origin,
            attempt=1,
            preconditions=["clear_scores"],
        )

    def after_rescore(self, origin: str, attempt: int) -> Step:
        if self.s.scores_absent:
            if attempt < 2:
                return self.step(
                    StepKind.RESCORE, "rescore wrote no scores; retry", origin=origin, attempt=2
                )
            return self.stop("scores_absent", f"scores absent after {origin} rescore retry")
        if origin == "wire":
            return self.post_size_review()
        if origin == "reconcile":
            return self.rasr()
        if origin == "atomic":
            return self.raar()
        return self.stop("scores_absent", f"unknown rescore origin {origin!r}")

    def after_go_no_go(self) -> Step:
        if not self.s.waived:
            return self.stop("oversized_atomic", "go/no-go did not stamp the waiver", row=True)
        # ENH-3606 accepted change 4: the waiver covers only the outcome gate.
        if (self.s.confidence or 0) < self.s.readiness_threshold:
            return self.stop("low_readiness", "waived but readiness below threshold", row=True)
        self.carry_preconditions.append("reopen")
        self.trail.append("GO: reopen")
        return self.pre_implement()

    # -- chains (today's shell/classify states between two commands) ------------
    def post_refine_select(self) -> Step:
        """select_obligation_post_refine."""
        s = self.s
        if s.decision_needed:
            if not self.under_cap() or self.decision_used():
                return self.stop("decision_exhausted", "decision still needed; re-entry spent")
            return self.step(StepKind.RUN_CHILD, "decision_needed re-entry", role="decision")
        tok = s.obligation_post
        if tok == "ERROR":
            self.trail.append("SPR _error -> detect")
            return self.detect()
        if tok.startswith("PROOF") and self.proof_reentry_ok():
            return self.step(StepKind.RUN_CHILD, "proof re-entry (post refine)", role="proof")
        # check_missing_artifacts
        if s.missing_artifacts:
            return self.step(StepKind.WIRE, "missing_artifacts", role="artifacts")
        return self.detect()

    def proof_reentry_ok(self) -> bool:
        s = self.s
        return (
            s.spike_needed
            and not s.spike_attempted
            and s.spike_runs < 2
            and not self.proof_used()
            and self.under_cap()
        )

    def detect(self) -> Step:
        """detect_children -> check_parent_resolved -> recheck_scores."""
        kids = self.children()
        if kids:
            return self.finish("decomposed", "children detected", child_ids=kids)
        if self.s.resolved:
            return self.finish("decomposed", f"parent already {self.s.status}")
        # recheck_scores: check-readiness AND check-design (current verdict, not sticky
        # -- BUG-3620: a design fix must fall through to the score-based branches).
        if self.s.check_readiness_passes() and not self.s.design_failed:
            self.trail.append("recheck_scores yes")
            return self.pre_implement()
        return self.step(StepKind.SIZE_REVIEW, "recheck_scores failed")

    def post_size_review(self) -> Step:
        """enqueue_or_skip -> check_parent_resolved_post_size_review -> SPSR."""
        kids = self.children()
        if kids:
            return self.finish("decomposed", "size-review children", child_ids=kids)
        if self.s.resolved:
            return self.finish("decomposed", f"parent already {self.s.status}")
        tok = self.s.obligation_post
        if tok == "ERROR":
            return self.rasr()
        if tok.startswith("PROOF") and self.proof_reentry_ok():
            return self.step(StepKind.RUN_CHILD, "proof re-entry (post size review)", role="proof")
        return self.reconcile_check()

    def reconcile_check(self) -> Step:
        """check_reconcile_needed."""
        s = self.s
        cur = str(s.confidence) if s.confidence else ""
        pre = self.pre_readiness()
        attempted = s.reconcile_attempted
        plateau = pre != "" and pre == cur and not attempted
        fresh_below = pre == "" and cur != "" and int(cur) < s.readiness_threshold and not attempted
        fires = self.f.count_intents(StepKind.RECONCILE, contradiction_only=True)
        # BUG-3624 (Q1): superseded_marker_count is read regardless of blocking
        # format-check gaps (fixed at the snapshot in snapshot_issue()).
        contradiction = s.superseded_markers > 0 and fires < 2
        if fresh_below:
            self.backfill_pre_readiness(cur)
        if plateau or fresh_below or contradiction:
            only = contradiction and not (plateau or fresh_below)
            why = "plateau" if plateau else ("fresh_below" if fresh_below else "contradiction")
            return self.step(StepKind.RECONCILE, why, contradiction_only=only)
        return self.guard2()

    def guard2(self) -> Step:
        """check_size_review_ran_this_pass -> check_guard2_* -> CRAR."""
        sr = self.f.last_size_review()
        if sr is None or not sr.payload.get("guard2"):
            return self.rasr()
        if (self.s.confidence or 0) >= self.s.readiness_threshold:
            return self.step(StepKind.WIRE, "guard-2 atomic remediation", role="atomic")
        return self.rasr()

    def rasr(self) -> Step:
        """recheck_after_size_review -> check_pre_deferral_remedy -> dispatchers."""
        s = self.s
        # BUG-3620: use this visit's check-design verdict directly -- no sticky
        # marker/observation carried across visits.
        if s.inline_gate_passes() and not s.design_failed:
            self.trail.append("RASR pass")
            return self.pre_implement()
        if s.resolved:
            return self.finish("decomposed", f"parent already {s.status} at recheck")
        if s.scores_absent:
            return self.stop("scores_absent", "scores absent at recheck gate")
        cycles = self.f.repair_cycles()
        pre = self.pre_readiness()
        cur = s.confidence or 0
        fired = self.pre_deferral_fired()
        if s.design_failed:
            if not fired and not self.design_remedy_attempted():
                if pre == "":
                    self.backfill_pre_readiness(str(cur))
                return self.step(
                    StepKind.REFINE_GAP,
                    "design pre-deferral remedy",
                    role="design",
                    pre_deferral=True,
                )
            return self.stop("design_gate_failed", "design gate failed", row=True)
        if s.decision_needed:
            return self.stop("decision_unresolved", "decision_needed at recheck", row=True)
        if cycles >= 2 and pre != "" and _int_or_none(pre) is not None and cur <= int(pre):
            return self.stop(
                "readiness_stagnated", f"cycles={cycles} cur={cur} pre={pre}", row=True
            )
        if not fired:
            remedy = self.pick_remedy()
            if remedy:
                if pre == "":
                    self.backfill_pre_readiness(str(cur))
                if remedy == "spike" and s.spike_runs < 2 and self.under_cap():
                    return self.step(
                        StepKind.RUN_CHILD,
                        "pre-deferral spike remedy",
                        role="spike_remedy",
                        pre_deferral=True,
                    )
                return self.step(
                    StepKind.RECONCILE,
                    f"pre-deferral {remedy} remedy",
                    pre_deferral=True,
                    contradiction_only=False,
                )
        return self.stop("low_readiness", "below readiness after remedies", row=True)

    def pick_remedy(self) -> str:
        s = self.s
        spent = s.spike_runs >= 2
        contra_only = self.f.any_intent(StepKind.RECONCILE, run=True, contradiction_only=True)
        gate_marker = s.gate_verdict in ("structured_proof", "prose")
        if s.spike_attempted:
            return ""
        if s.reconcile_attempted and contra_only:
            return "" if spent else "spike"
        if s.reconcile_attempted:
            return ""
        if spent:
            return "reconcile"
        if gate_marker:
            return "spike"
        amb = s.score_ambiguity
        others = [s.score_complexity, s.score_test_coverage, s.score_change_surface]
        return "spike" if (amb and amb < min(others)) else "reconcile"

    def raar(self) -> Step:
        """regate_after_atomic_remediation -> CADR -> check_go_no_go_eligible."""
        s = self.s
        # BUG-3620: current verdict, not sticky (see rasr()).
        if s.inline_gate_passes() and not s.design_failed:
            return self.pre_implement()
        if s.resolved:
            return self.finish("decomposed", f"parent already {s.status} at regate")
        if s.scores_absent:
            return self.stop("scores_absent", "scores absent at regate")
        if s.design_failed:
            if not self.design_remedy_attempted():
                return self.step(StepKind.REFINE_GAP, "atomic design remedy", role="design")
            return self.stop("design_gate_failed", "design gate failed at regate", row=True)
        if self.go_no_go_attempted():
            return self.stop("oversized_atomic", "go/no-go already attempted", row=True)
        return self.step(
            StepKind.GO_NO_GO,
            "oversized_atomic: adversarial review",
            preconditions=["defer_oversized_atomic"],
        )

    def pre_implement(self) -> Step:
        """select_obligation_pre_implement."""
        s = self.s
        if s.decision_needed:
            if not self.under_cap() or self.decision_used():
                return self.stop("decision_exhausted", "decision still needed; re-entry spent")
            return self.step(StepKind.RUN_CHILD, "decision_needed re-entry", role="decision")
        if (
            s.gate_verdict == "structured_proof"
            and not s.spike_attempted
            and not s.waived
            and s.spike_runs < 2
            and not self.proof_used()
            and self.under_cap()
        ):
            return self.step(StepKind.RUN_CHILD, "proof gate re-entry", role="proof")
        return self.finish("ready", "gates pass")


def _fmt_payload(p: Mapping[str, Any]) -> str:
    keys = [f"{k}={p[k]}" for k in ("role", "origin", "attempt", "terminal", "token") if k in p]
    return "{" + ",".join(keys) + "}" if keys else ""


def _int_or_none(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def decide(snapshot: IssueSnapshot, facts: Facts) -> Step:
    """Pure policy: the next preparation step for *snapshot* given *facts*."""
    return _Decider(snapshot, facts).run()


# ---------------------------------------------------------------------------
# Snapshot + fact log I/O
# ---------------------------------------------------------------------------


def _flag(fm: Mapping[str, Any], key: str) -> bool:
    return str(fm.get(key)).lower() == "true"


def _opt_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def snapshot_issue(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    *,
    readiness_threshold: int,
    outcome_threshold: int,
    facts: Facts | None = None,
) -> IssueSnapshot:
    """Read everything :func:`decide` needs, with today's probe semantics.

    *facts* (when given) drives the lazy child-provenance scan (ENH-3623 §
    Production additions item 1): the project-wide scan for ``parent:`` / "Decomposed
    from" provenance only runs when :meth:`Facts.needs_child_scan` says the ladder
    might reach DETECT or POST_SIZE_REVIEW this call. Omitting *facts* (e.g. for
    ``prep explain``, or a caller that just wants everything) always scans.
    """
    from little_loops.cli.issues.check_gate import resolve_gate_verdict
    from little_loops.cli.issues.next_obligation import Obligation, select_next_obligation
    from little_loops.cli.issues.search import _load_issues_with_status
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_parser import (
        IssueParser,
        check_format_gaps,
        design_gate_failed,
        superseded_marker_count,
    )

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return IssueSnapshot(issue_id=issue_id, exists=False)
    text = path.read_text()
    fm = parse_frontmatter(text, coerce_types=True)

    try:
        gaps = check_format_gaps(path)
        design = design_gate_failed(gaps)
    except Exception:  # noqa: BLE001 - check-design errors do not file the marker
        design = False
    # BUG-3624 (Q1): read regardless of blocking format-check gaps. The spike's
    # `0 if blocking else superseded_marker_count(path)` mirrored a shell quirk
    # (`FMT_JSON=$(ll-issues format-check ID --format json || echo '{}')`
    # discarding the real payload on any blocking gap via the `||`), masking the
    # contradiction trigger exactly when a blocking gap coexists with markers.
    markers = superseded_marker_count(path)
    try:
        spike_proven = _flag(fm, "spike_completed") and not _flag(fm, "spike_refuted")
        gate: str = resolve_gate_verdict(fm, text, spike_proven)[0]
    except Exception:  # noqa: BLE001 - fail-open as the shell `|| true` callers
        gate = ""
    tier1 = (
        Obligation.FORMAT,
        Obligation.VERIFY,
        Obligation.HEDGES,
        Obligation.PLACEHOLDERS,
        Obligation.ACCEPTANCE_CRITERIA,
        Obligation.DESIGN,
    )
    try:
        res = select_next_obligation(
            config,
            issue_id,
            skip=tier1,
            readiness_override=readiness_threshold,
            outcome_override=outcome_threshold,
            honor_waiver=True,
        )
        obligation = res.token() if res is not None else "ERROR"
    except Exception:  # noqa: BLE001 - exit 2 -> classify _error
        obligation = "ERROR"
    try:
        refine_count = (
            IssueParser(config).parse_file(path).session_command_counts.get("/ll:refine-issue", 0)
        )
    except Exception:  # noqa: BLE001 - `|| echo 0`
        refine_count = 0
    try:
        cfg = json.loads((config.project_root / ".ll" / "ll-config.json").read_text())
        cap = int(cfg.get("commands", {}).get("max_refine_count", 5))
    except Exception:  # noqa: BLE001 - `|| echo 5`
        cap = 5
    spike_runs = _opt_int(_read(run_dir / f"spike-runs-{issue_id}")) or 0

    candidates: set[str] = set()
    if facts is None or facts.needs_child_scan():
        parent_re = re.compile(
            rf"^parent:[ \t]*['\"]?{re.escape(issue_id)}['\"]?[ \t]*$", re.MULTILINE
        )
        prose_re = re.compile(
            rf"Decomposed from (\[\[)?{re.escape(issue_id)}([^0-9]|$)", re.MULTILINE
        )
        for info, _status in _load_issues_with_status(config, True, False, False):
            if info.issue_id == issue_id:
                continue
            try:
                body = Path(info.path).read_text()
            except OSError:
                continue
            if parent_re.search(body) or prose_re.search(body):
                candidates.add(info.issue_id)

    return IssueSnapshot(
        issue_id=issue_id,
        status=str(fm.get("status") or "open").lower(),
        confidence=_opt_int(fm.get("confidence_score")),
        outcome=_opt_int(fm.get("outcome_confidence")),
        waived=_flag(fm, "outcome_gate_waived"),
        decision_needed=_flag(fm, "decision_needed"),
        missing_artifacts=_flag(fm, "missing_artifacts"),
        reconcile_attempted=_flag(fm, "reconcile_attempted"),
        spike_needed=_flag(fm, "spike_needed"),
        spike_attempted=_flag(fm, "spike_attempted"),
        score_ambiguity=_opt_int(fm.get("score_ambiguity")) or 0,
        score_complexity=_opt_int(fm.get("score_complexity")) or 0,
        score_test_coverage=_opt_int(fm.get("score_test_coverage")) or 0,
        score_change_surface=_opt_int(fm.get("score_change_surface")) or 0,
        design_failed=design,
        gate_verdict=gate,
        obligation_post=obligation,
        superseded_markers=markers,
        refine_count=int(refine_count),
        refine_cap=cap,
        spike_runs=spike_runs,
        readiness_threshold=readiness_threshold,
        outcome_threshold=outcome_threshold,
        child_candidates=frozenset(candidates),
    )


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def facts_path(run_dir: Path, issue_id: str) -> Path:
    return Path(run_dir) / FACTS_DIR / f"{issue_id}.jsonl"


def current_pass(run_dir: Path, issue_id: str) -> str:
    """The pass id from ``<run_dir>/prep-pass-<ID>``; ``"0"`` when absent (or empty).

    Nothing writes that file until ENH-3623 Phase B's ``dequeue_next``, so every
    ENH-3630-era call reads pass ``"0"`` -- pinned by a test, not just this default.
    """
    return _read(Path(run_dir) / f"{PASS_PREFIX}{issue_id}") or "0"


def load_facts(run_dir: Path, issue_id: str) -> Facts:
    """Parse the fact log (a torn last line is ignored)."""
    out: list[Fact] = []
    path = facts_path(run_dir, issue_id)
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    for ln in lines:
        try:
            d = json.loads(ln)
            out.append(
                Fact(
                    pass_id=str(d["pass"]),
                    seq=int(d["seq"]),
                    kind=str(d["kind"]),
                    step=str(d["step"]),
                    payload=d.get("payload") or {},
                )
            )
        except (ValueError, KeyError, TypeError):
            continue
    return Facts(pass_id=current_pass(run_dir, issue_id), facts=tuple(out))


def append_fact(run_dir: Path, issue_id: str, fact: Fact) -> bool:
    """Append *fact* unless an equal key is already logged; returns True if written.

    Keys: ``(pass, seq, kind)`` for intent/done; ``(pass, seq, step, payload)`` for
    obs (a replayed ``decide()`` at the same seq re-derives identical observations).
    """
    existing = load_facts(run_dir, issue_id).facts
    for f in existing:
        if f.pass_id != fact.pass_id or f.kind != fact.kind or f.seq != fact.seq:
            continue
        if fact.kind != "obs":
            return False
        if f.step == fact.step and dict(f.payload) == dict(fact.payload):
            return False
    path = facts_path(run_dir, issue_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(fact.to_json() + "\n")
        fh.flush()
    return True


def next_preparation_step(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    *,
    readiness_threshold: int,
    outcome_threshold: int,
) -> Step:
    """``decide(snapshot_issue(...), load_facts(...))``."""
    facts = load_facts(run_dir, issue_id)
    snap = snapshot_issue(
        config,
        issue_id,
        run_dir,
        readiness_threshold=readiness_threshold,
        outcome_threshold=outcome_threshold,
        facts=facts,
    )
    return decide(snap, facts)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _ensure_pass_start(run_dir: Path, issue_id: str, pass_id: str) -> None:
    facts = load_facts(run_dir, issue_id)
    if facts.obs("pass_start"):
        return
    pre_ids = sorted(ln for ln in _read(run_dir / "autodev-pre-ids.txt").splitlines() if ln)
    append_fact(
        run_dir,
        issue_id,
        Fact(
            pass_id,
            0,
            "obs",
            "pass_start",
            {"pre_readiness": _read(run_dir / "autodev-pre-readiness.txt"), "pre_ids": pre_ids},
        ),
    )


def _resolve_or_raise(config: BRConfig, issue_id: str) -> Path:
    from little_loops.cli.issues.show import _resolve_issue_id

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise RuntimeError(f"prep precondition: issue {issue_id!r} not found")
    return path


def _set_status_checked(
    config: BRConfig,
    path: Path,
    issue_id: str,
    status: str,
    *,
    reason: str | None = None,
    by: str | None = None,
) -> None:
    """``apply_status_transition``, validated and checked (ENH-3630 in-process writes).

    The spike's ``_ll_issues()`` shelled out to ``ll-issues set-status`` via
    ``subprocess`` and ignored the return code, so a silently failed write broke the
    "each write independently idempotent" guarantee. This runs the same
    ``--reason``-vs-status check ``cmd_set_status`` runs (``apply_status_transition``
    itself assumes an already-valid transition) and lets any write failure
    (``OSError``) propagate, surfacing as a non-zero ``ll-issues prep`` exit instead
    of silently doing nothing.
    """
    from little_loops.cli.issues.set_status import apply_status_transition, reason_error_for_status

    error = reason_error_for_status(status, reason)
    if error:  # pragma: no cover - defensive; every call site below passes a valid pair
        raise RuntimeError(error)
    apply_status_transition(config, path, issue_id, status, reason=reason, by=by)


def _run_preconditions(config: BRConfig, issue_id: str, run_dir: Path, pre: Sequence[str]) -> None:
    """Idempotent writes that must precede the command (replayed on resume)."""
    from little_loops.cli.issues.run_record import canonical_record_id
    from little_loops.run_record import record_path

    for p in pre:
        if p == "clear_records":
            rid = canonical_record_id(config, issue_id)
            for writer in ("prepare-issue", "refine-to-ready-issue"):
                record_path(run_dir, writer, rid).unlink(missing_ok=True)
        elif p == "clear_scores":
            from little_loops.cli.issues.set_scores import clear_scores

            clear_scores(_resolve_or_raise(config, issue_id))
        elif p == "defer_oversized_atomic":
            path = _resolve_or_raise(config, issue_id)
            _set_status_checked(
                config, path, issue_id, "deferred", reason="oversized_atomic", by="automation"
            )
        elif p == "reopen":
            path = _resolve_or_raise(config, issue_id)
            _set_status_checked(config, path, issue_id, "open", by="automation")


def prep_step(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    *,
    readiness_threshold: int,
    outcome_threshold: int,
) -> Step:
    """Replay the open intent, else decide and append (see module docstring)."""
    run_dir = Path(run_dir)
    pass_id = current_pass(run_dir, issue_id)
    _ensure_pass_start(run_dir, issue_id, pass_id)
    facts = load_facts(run_dir, issue_id)
    applied = [f for f in facts.dones() if StepKind(f.step) in TERMINAL_KINDS]
    if applied:  # the pass already ended; a restarted wrapper re-applies idempotently
        a = applied[-1]
        return Step(StepKind(a.step), a.seq, a.payload, "pass already applied")
    open_ = facts.open_intent()
    if open_ is not None:
        pre = list(open_.payload.get("preconditions") or ())
        if StepKind(open_.step) not in TERMINAL_KINDS:
            _run_preconditions(config, issue_id, run_dir, pre)
        return Step(StepKind(open_.step), open_.seq, open_.payload, "replay open intent")
    step = next_preparation_step(
        config,
        issue_id,
        run_dir,
        readiness_threshold=readiness_threshold,
        outcome_threshold=outcome_threshold,
    )
    for name, value in step.observations:
        append_fact(run_dir, issue_id, Fact(pass_id, step.seq, "obs", name, {"value": value}))
    payload = {**dict(step.payload), "reason": step.reason}
    append_fact(run_dir, issue_id, Fact(pass_id, step.seq, "intent", step.kind.value, payload))
    if step.kind not in TERMINAL_KINDS:
        _run_preconditions(config, issue_id, run_dir, list(step.payload.get("preconditions") or ()))
    return step


def prep_record(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    *,
    guard2: bool = False,
) -> Fact | None:
    """Append the done fact for the open (non-terminal) intent; no-op if none.

    Classifies the child outcome from ``run-records/refine-to-ready-issue/<ID>.json``
    alone -- never from the loop's ``captured.run_child`` (ENH-3623 decision: a
    ``failure_terminal`` capture can outlive the run that set it). The ``RUN_CHILD``
    precondition cleared that record, and every inner terminal writes one, so:
    absent -> the inner loop errored; a legacy class -> it ended ``failed`` (the
    failure paths always pass ``--legacy-class``); otherwise it ended ``done``.
    """
    from little_loops.cli.issues.run_record import canonical_record_id
    from little_loops.run_record import read_run_record, record_token

    run_dir = Path(run_dir)
    facts = load_facts(run_dir, issue_id)
    open_ = facts.open_intent()
    if open_ is None or StepKind(open_.step) in TERMINAL_KINDS:
        return None
    payload = {k: v for k, v in open_.payload.items() if k not in ("preconditions", "reason")}
    if open_.step == StepKind.RUN_CHILD.value:
        rec = read_run_record(
            run_dir, "refine-to-ready-issue", canonical_record_id(config, issue_id)
        )
        if rec is None:
            terminal = "error"
        else:
            terminal = "failed" if rec.legacy_class else "done"
        payload["terminal"] = terminal
        payload["token"] = record_token(rec)
        if terminal == "done":
            # route_inner_success (ENH-3606): no ladder path starts with the flag at 1.
            (run_dir / "refine-broke-down").write_text("0")
    elif open_.step == StepKind.SIZE_REVIEW.value:
        payload["guard2"] = guard2
    done = Fact(facts.pass_id, open_.seq, "done", open_.step, payload)
    append_fact(run_dir, issue_id, done)
    # Projection kept for today's readers/pins (dequeue_next still resets it).
    count = load_facts(run_dir, issue_id).repair_cycles()
    (run_dir / "autodev-repair-cycle-count.txt").write_text(str(count))
    return done


#: STOP outcomes that own a ledger row + deferral, with their row reason /
#: deferred_reason and legacy class.
_DEFER_STOPS: dict[str, tuple[str, str]] = {
    "design_gate_failed": ("design_gate_failed", "gate_unmet"),
    "oversized_atomic": ("oversized_atomic", "gate_unmet"),
    "readiness_stagnated": ("readiness_stagnated", "gate_unmet"),
    "low_readiness": ("low_readiness", "gate_unmet"),
    "decision_unresolved": ("decision_unresolved", "decision_unresolved"),
    "decision_exhausted": ("decision_unresolved", "decision_unresolved"),
}
_INFRA_STOPS = ("scores_absent", "ladder_error", "inner_error")


def prep_apply(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    *,
    readiness_threshold: int,
    outcome_threshold: int,
    rate_limited: bool = False,
) -> int:
    """Sole terminal writer. Returns 0 (wrapper ``done``) or 1 (wrapper ``failed``).

    Crash-safe (ENH-3623 § Production additions item 1): the ledger row, ``set-status``,
    run record and inflight-clear writes are each independently idempotent (keyed by
    ``(pass, seq)`` with check-before-append for the ledger row, ``apply_status_transition``
    and ``write_typed_run_record`` for the others), each followed by its own
    ``apply_progress`` mark, so replaying ``apply`` from any crash point converges on
    one terminal without double-appending the ledger row.
    """
    run_dir = Path(run_dir)
    facts = load_facts(run_dir, issue_id)
    pass_id = facts.pass_id
    open_ = facts.open_intent()
    applied = [f for f in facts.dones() if StepKind(f.step) in TERMINAL_KINDS]
    if applied:  # idempotent: already applied this pass
        return int(applied[-1].payload.get("exit", 1))
    if rate_limited:
        outcome, kind, seq = "rate_limited", StepKind.STOP, facts.next_seq()
        payload: dict[str, Any] = {"outcome": outcome}
    elif open_ is not None and StepKind(open_.step) in TERMINAL_KINDS:
        kind, seq, payload = StepKind(open_.step), open_.seq, dict(open_.payload)
        outcome = str(payload.get("outcome"))
    else:  # select_step errored, or the step cap fired mid-step: ladder error
        outcome, kind, seq = "ladder_error", StepKind.STOP, facts.next_seq()
        payload = {"outcome": outcome, "open_step": open_.step if open_ else None}
        append_fact(run_dir, issue_id, Fact(pass_id, seq, "intent", kind.value, payload))
    progress = {
        str(f.payload.get("value")): f.payload for f in facts.obs("apply_progress") if f.seq == seq
    }

    def mark(part: str, **extra: Any) -> None:
        fact = Fact(pass_id, seq, "obs", "apply_progress", {"value": part, **extra})
        append_fact(run_dir, issue_id, fact)

    code = _apply_outcome(
        config,
        issue_id,
        run_dir,
        outcome,
        payload,
        progress,
        mark,
        readiness_threshold=readiness_threshold,
        outcome_threshold=outcome_threshold,
    )
    append_fact(
        run_dir,
        issue_id,
        Fact(pass_id, seq, "done", kind.value, {"outcome": outcome, "exit": code}),
    )
    return code


def _apply_outcome(
    config: BRConfig,
    issue_id: str,
    run_dir: Path,
    outcome: str,
    payload: Mapping[str, Any],
    progress: Mapping[str, Mapping[str, Any]],
    mark: Any,
    *,
    readiness_threshold: int,
    outcome_threshold: int,
) -> int:
    from little_loops.cli.issues.run_record import (
        derive_child_ids,
        forward_run_record,
        write_typed_run_record,
    )
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.run_record import RATE_LIMIT_EXHAUSTED_REF, read_run_record, record_token

    skipped = run_dir / "autodev-skipped.txt"
    path = _resolve_issue_id(config, issue_id)
    status = ""
    if path is not None:
        status = str(parse_frontmatter(path.read_text(), coerce_types=True).get("status") or "")

    def row(reason: str) -> None:
        # Check-before-append across two files (ENH-3623): the ledger has no key of
        # its own, so a `row_pending` mark records how many identical rows existed
        # before the append. A replay after a crash between the append and the `row`
        # mark sees one more than that and skips the append.
        if "row" in progress:
            return
        line = f"{issue_id}  {reason}"
        existing = skipped.read_text().splitlines().count(line) if skipped.exists() else 0
        pending = progress.get("row_pending")
        before = existing if pending is None else int(pending.get("before", 0))
        if pending is None:
            mark("row_pending", before=before)
        if existing <= before:
            with skipped.open("a") as fh:
                fh.write(f"{line}\n")
        mark("row")

    def sentinel(cls: str) -> None:
        (run_dir / "refine-terminal-class").write_text(cls)

    def write(legacy_class: str | None, *, broke_down: bool = False, **kw: Any) -> None:
        # Shared with `ll-issues run-record write` (ENH-3630 Step 2): the same
        # ready/decomposed predicate, including ENH-3625's check-design condition
        # that the spike's inline `_apply_outcome.write()` predicate omitted.
        (run_dir / "refine-broke-down").write_text("1" if broke_down else "0")
        raw_child_ids = kw.get("child_ids")
        write_typed_run_record(
            config,
            issue_id,
            run_dir,
            "prepare-issue",
            legacy_class=legacy_class,
            child_ids=list(raw_child_ids) if raw_child_ids is not None else None,
            evidence_refs=tuple(kw.get("evidence_refs") or ()),
            readiness_threshold=readiness_threshold,
            outcome_threshold=outcome_threshold,
            broke_down=broke_down,
        )

    def forward() -> RunRecord | None:
        # Same read -> re-writer -> write as `ll-issues run-record forward`.
        return forward_run_record(
            config, issue_id, run_dir, source="refine-to-ready-issue", writer="prepare-issue"
        )

    def rm_inflight() -> None:
        (run_dir / "autodev-inflight").unlink(missing_ok=True)

    if outcome == "ready":
        write(None)
        return 0
    if outcome == "cancelled":
        forward()
        return 0
    if outcome == "decomposed":
        kids = list(payload.get("child_ids") or ()) or derive_child_ids(config, issue_id)
        write(None, broke_down=True, child_ids=kids)
        return 0
    if outcome == "child_stop":
        rec = forward()
        # Every failed-bound terminal leaves the sentinel (read by autodev's
        # skip_inflight until ENH-3600 removes it); the child's own class stands.
        if rec is not None and rec.legacy_class:
            sentinel(rec.legacy_class)
        if record_token(rec) in ("BLOCKED:quality", "DEFERRED:gate_unmet"):
            row("refine_failed")
        return 1
    if outcome == "rate_limited":
        sentinel("infra")
        write("infra", evidence_refs=[RATE_LIMIT_EXHAUSTED_REF])
        return 1
    if outcome in _INFRA_STOPS:
        from little_loops.cli.issues.run_record import canonical_record_id

        rid = canonical_record_id(config, issue_id)
        existing = record_token(read_run_record(run_dir, "prepare-issue", rid))
        sentinel("infra")
        if outcome == "ladder_error" and existing.startswith(("BLOCKED:", "DEFERRED:")):
            return 1  # a stop record for this pass stands (ENH-3606 mark_ladder_error)
        write("infra")
        return 1
    if outcome in _DEFER_STOPS:
        reason, legacy = _DEFER_STOPS[outcome]
        if status.lower() in RESOLVED_STATUSES:
            # ENH-3606 route_ladder_stop: a resolved issue never defers; it ends
            # DECOMPOSED so autodev's recover_subloop_children owns the row. (Only
            # decision_exhausted reaches here resolved; decide() routes RASR/RAAR.)
            kids = derive_child_ids(config, issue_id)
            write(None, broke_down=True, child_ids=kids)
            return 0
        row(reason)
        rm_inflight()
        if "status" not in progress and path is not None:
            _set_status_checked(config, path, issue_id, "deferred", reason=reason, by="automation")
            mark("status")
        sentinel(legacy)
        write(legacy)
        return 1
    # Unknown outcome: fail closed as infra.
    sentinel("infra")
    write("infra")
    return 1


# ---------------------------------------------------------------------------
# CLI: ll-issues prep {step,record,apply,explain}
# ---------------------------------------------------------------------------


def add_prep_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register ``ll-issues prep`` (ENH-3630).

    Internal loop plumbing, not for manual use: ``prep step`` and ``prep apply``
    mutate issue status/scores as a side effect of routing the preparation ladder.
    """
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser("prep", help="Preparation policy dispatch (ENH-3623/ENH-3630)")
    p.set_defaults(command="prep")
    ss = p.add_subparsers(dest="prep_command", required=True)
    for name in ("step", "record", "apply", "explain"):
        sp = ss.add_parser(name)
        sp.add_argument("issue_id")
        sp.add_argument("--run-dir", required=True)
        sp.add_argument("--readiness-threshold", type=int, default=85)
        sp.add_argument("--outcome-threshold", type=int, default=65)
        if name == "record":
            sp.add_argument("--guard2", action="store_true")
        if name == "apply":
            sp.add_argument("--rate-limited", action="store_true")
        add_config_arg(sp)
    return p


def cmd_prep(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch ``ll-issues prep``; ``step`` prints the StepKind token on stdout."""
    run_dir = Path(args.run_dir)
    iid = str(args.issue_id).strip()
    cmd = args.prep_command
    if cmd == "step":
        step = prep_step(
            config,
            iid,
            run_dir,
            readiness_threshold=args.readiness_threshold,
            outcome_threshold=args.outcome_threshold,
        )
        print(
            f"[PREP] {iid} #{step.seq} {step.kind.value} {dict(step.payload)} — {step.reason}",
            file=sys.stderr,
        )
        print(step.kind.value)
        return 0
    if cmd == "record":
        done = prep_record(config, iid, run_dir, guard2=args.guard2)
        print(f"[PREP] recorded {done.step if done else 'nothing'}", file=sys.stderr)
        return 0
    if cmd == "apply":
        return prep_apply(
            config,
            iid,
            run_dir,
            readiness_threshold=args.readiness_threshold,
            outcome_threshold=args.outcome_threshold,
            rate_limited=args.rate_limited,
        )
    if cmd == "explain":
        step = next_preparation_step(
            config,
            iid,
            run_dir,
            readiness_threshold=args.readiness_threshold,
            outcome_threshold=args.outcome_threshold,
        )
        print(
            json.dumps(
                {
                    "kind": step.kind.value,
                    "payload": dict(step.payload),
                    "reason": step.reason,
                    "evidence": list(step.evidence),
                }
            )
        )
        return 0
    return 2


__all__ = [
    "DONE_FACT_CAP",
    "MAX_DONE_PER_PASS",
    "MAX_STEPS",
    "Fact",
    "Facts",
    "IssueSnapshot",
    "Step",
    "StepKind",
    "decide",
    "load_facts",
    "next_preparation_step",
    "snapshot_issue",
]
