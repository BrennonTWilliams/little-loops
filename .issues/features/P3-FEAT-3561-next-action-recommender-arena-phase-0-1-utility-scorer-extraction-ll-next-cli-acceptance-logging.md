---
id: 3561
title: 'Next-action recommender arena — Phase 0+1: utility scorer extraction, ll-next CLI, acceptance logging'
type: FEAT
priority: P3
status: open
discovered_date: '2026-09-24'
labels: []
---

# Next-action recommender ("the arena") — Phase 0+1: utility scorer extraction, `ll-next` CLI, acceptance logging

## Problem

The existing narrow recommenders each answer one slice of "what should I do next":

- `ll-issues next-issue` / `next-issues` — lexicographic sort of open issues (`-outcome_confidence, -confidence_score, priority`); can only ever recommend *implementing* an issue.
- `ll-issues next-action` — recommends the next *refinement* step (verify → refine → ready) for one issue.
- `ll-loop next-loop` — a true weighted-additive utility score (`0.50·freq + 0.30·recency + 0.20·success_rate`, weights hardcoded), but scoped to a single verb: "run a loop".

None of them can reason across the whole project state. The capability this issue delivers is the deterministic core of a **Product Owner / Tech Lead reasoner**: a fixed menu of action *types*, each candidate scored by weighted *considerations*, with a legible, auditable score — pick the top N actions for right now.

**Non-goals:** not a scheduler or work queue (it recommends; it doesn't sequence or enforce); advisory-first (`--execute` is opt-in); the four narrow `next-*` CLIs keep working unchanged through Phase 1 — subsumption is gradual, not a rewrite. In docs and code comments, call the feature **"the arena"** to avoid colliding with `ll-issues next-action`'s existing meaning.

## Scope

Two phases, explicitly bounded. Phases 2–4 (LLM reviewer over the shortlist, goal-alignment critical-path depth, learned weights) are **out of scope** and deferred until this issue has shipped and is emitting a real accept/outcome stream.

### Phase 0 — extract the scorer *and fix the config surface*

1. Pull `next-loop`'s scoring into a reusable `utility/` module: considerations, response curves, aggregation. Pure functions, pure pytest.
2. The module must expose **both aggregators**, parameterized: `next-loop` aggregates by weighted *sum* today; the arena wants geometric-mean-with-gates (Appendix A semantics below). Phase 0 must be behavior-preserving for `next-loop` — its first caller. **Enforce, don't assert:** a golden test pins `next-loop`'s output on a fixture history as byte-identical pre/post extraction.
3. Weights, curves, gate assignments, and bucket pressures live in `ll-config.json` under a `next` key, mirroring the `NextIssueConfig`/`sort_keys` extensibility pattern. **Config shape: keyed objects, not arrays** — local config merge semantics replace arrays wholesale, so `weights: [0.5, 0.3, …]` would make a local tweak to one weight silently drop the rest; `weights: {freq: 0.5, recency: 0.3, …}` deep-merges correctly.
4. Register the `next` key in `config-schema.json` so curves/weights/gates are validated like every other config surface; invalid config maps to exit code 2 (below).

### Phase 1 — the deterministic arena

#### Action taxonomy — the verbs

Nine active action types, each needing a candidate generator (a taxonomy entry with no generator can never surface — all nine ship in Phase 1):

1. **implement-issue** — take an issue to done
2. **run-sprint** — curated issue set (enumerate existing sprint definitions only; auto-clustered proposals deferred)
3. **run-loop** — fire an FSM loop (what `next-loop` recommends today)
4. **refine-issue** — an issue is high-value but not ready
5. **capture-issues** — run a discovery pass because information is stale
6. **resolve-blocker** — untangle a dependency gating many issues
7. **pay-tech-debt** — dead code, audit findings
8. **update-docs** — docs drift detected
9. **meta** — improve the harness itself (yield nothing when no audit-findings artifact exists)

**`generic` is deliberately NOT a verb.** Its blockers are structural, not cosmetic: no candidate generator (nothing enumerable produces "decide X, review PR Y"), no signal source (every consideration axis reads frontmatter/deps/history, so a generic candidate has coverage 0/9 and any fallback score is false precision), and escape-hatch decay (a type that fits everything erodes the taxonomy). Generic work is supported via **capture-as-issue**: write "review PR #42" down as an issue and it flows through `implement-issue`/`refine-issue` with real signals.

**One target, many candidates.** The same issue legitimately appears under multiple action types — `implement-issue` (readiness *gates* it to 0 if unready) and `refine-issue` (unreadiness *raises* its score). This coupling is intentional: it's the mechanism by which the arena routes work to the right verb. Candidate generation is per-(action-type, target) pair, no dedup across types; gates ensure at most one of a coupled pair scores well. If both survive gating, keep both — the tie itself is signal.

#### Considerations — the scoring signals

Each consideration maps a raw signal onto `[0,1]` via a **response curve**. Sources that exist today:

| Consideration | Meaning | Signal source |
|---|---|---|
| priority | urgency | frontmatter `priority` |
| unblocked-ness | are deps satisfied? | dependency graph |
| leverage | does it unblock many others? | **needs building** — the graph exists but exposes no fan-out/unblock-count metric; build it in Phase 1 |
| goal-alignment | serves a top strategic priority? | deterministic **EPIC-membership matcher**: issue → parent EPIC → a goal↔EPIC mapping in `ll-goals.md`; issue frontmatter `goal_alignment`/`persona_impact`/`business_value` overrides when present. **Goal-blind-tolerant:** while no goals doc exists the axis resolves `None` and is excluded (missing-axis semantics below) — Phase 1 is *not* gated on `ll-goals.md` |
| effort | cost to complete | frontmatter `effort` / `impact-effort` / history cycle-time |
| confidence / risk | how sure are we? | frontmatter `outcome_confidence`, `confidence_score` |
| staleness | age since captured/touched | `captured_at` / mtime |
| momentum | continues current theme | current sprint, recent commits, session command counts |
| info-freshness | when did we last scan/measure? | loop/scan history |
| historical-signal | recurring failures, prior corrections | history DB, active decision rules |
| readiness | is the issue actually actionable? | session refinement tally |

**Gate vs. curve is per (consideration, action-type), enumerated in config, not code:**

| Consideration | Gate for | Curve for |
|---|---|---|
| unblocked-ness | implement-issue, run-sprint | resolve-blocker (inverted: blockage *raises* it) |
| readiness | implement-issue | refine-issue (inverted) |
| decision-rule compliance | **all** action types | — |
| info-freshness | — | capture-issues (rising), all others (mild) |
| everything else | — | all |

#### The Candidate contract

Pinned before implementation because it is simultaneously the scorer's input, the CLI's JSON output, and (later, out of scope) the LLM reviewer's payload:

```python
@dataclass
class AxisScore:
    raw: str | float | None     # signal as read from the source (None = missing)
    curve: str                  # curve applied ("step", "linear-cap-5", "logistic-21d", …)
    score: float | None         # [0,1] after curve; None = missing → excluded
    gate: bool                  # is this axis a gate for this action type?
    source: str                 # provenance: "deps", "frontmatter", "history", …

@dataclass
class Candidate:
    action_type: str            # one of the nine verbs
    target: str                 # issue ID, loop name, sprint name, scan scope…
    command: str                # executable, e.g. "ll-loop run oracles/foo" — REQUIRED
    axes: dict[str, AxisScore]  # per-axis decomposition (raw → curve → score)
    utility: float              # within-type aggregate — NOT globally comparable
    bucket_rank: int            # rank within this action type's bucket (1 = best)
    pressure: float             # bucket pressure at selection time
    selection_reason: str       # "bucket rank 1, pressure 0.9, 40d since scan"
    coverage: str               # "scored on 7/9 signals"
```

Three invariants: **(1) every recommendation emits a runnable command** (generalize `next-loop`'s param-resolver registry per action type); **(2) every score is decomposable** into per-axis raw→curve→score rows; **(3) selection is expressible in the contract** — `bucket_rank`, `pressure`, and `selection_reason` ride on the record so the anti-starvation mechanism is auditable from the JSON alone.

#### Scoring semantics (IAUS-style)

- **Response curves** per consideration: linear, quadratic, inverse-quadratic, logistic, step. Sketches: priority `P0→1.0, P1→0.85, P2→0.6, P3→0.4, P4→0.2, P5→0.1`; leverage `min(1, unblocked_count / 5)`; staleness logistic rising after ~21 days; effort as cost `1 - (effort-1)/2`.
- **Hard gates (veto):** a zero-gate consideration scores the candidate 0 regardless of the rest (e.g. blocked → unblocked-ness 0 → utility 0; decision-rule violation likewise).
- **Aggregation — geometric mean with make-up compensation:**

  ```
  base   = (∏ cᵢ) ^ (1/n)                      # geometric mean of n considerations
  makeup = (1 - base) * (base) * (1/n)
  U      = clamp(base + makeup * (1 - base), 0, 1)
  ```

- **Why geometric, not `next-loop`'s weighted sum?** A sum lets a high priority mask a fatal flaw (e.g. blocked). Geometric + explicit gates makes any single near-zero axis dominate — correct for "should I do this *now*": vetoes, not averages. `next-loop`'s additive form is preserved for its own narrower case (Phase 0 golden test).
- **Missing axes are excluded from the product** — `n` counts only axes with data; never impute 0.5 into a product (a "neutral" 0.5 under multiplication is a penalty proportional to missingness). Exclusion applies to **curve axes only**: a missing *gate* axis fails closed — the candidate is vetoed and annotated `gate-missing`, distinguishable from a genuine 0. A coverage discount belongs at the **selection layer**, not inside utility: a candidate scored on `k/n` axes must clear the slot threshold on `pressure × (k/n)` (`next.selection.coverage_penalty`, default linear — a config knob, not code). Full fallback to priority sort only when *no* signals resolve.
- **Cold start:** with no history and no signals the arena must still emit the priority-sort fallback with a warning — it must not exit empty the way `next-loop` does.

#### Cross-type comparability — bucketed selection with pressure curves

A 0.78 for *implement P1-FEAT* and a 0.45 for *run a scan* are not on the same scale. Scalar type weights would cause **starvation** (hygiene actions never surface, so the info every score depends on goes stale) and **false precision** (tuning wars over type weights). Instead:

- **Score within type, select across buckets.** Each verb ranks its own candidates on its own scale; a thin policy layer fills the top-N across buckets (e.g. slots 1–3 from highest-pressure buckets, at most 2 slots to any one type).
- **Bucket pressure, not bucket weight.** Each type carries a pressure that **rises over time when never selected** and resets when it is: `capture-issues` pressure is a logistic over days-since-last-scan; `update-docs` pressure rises with docs-drift findings; implementation types have flat pressure ≈ their static weight.
- **Pressure is persisted state.** Per-bucket `last_accepted_at` (plus drift inputs) lives in the history DB alongside `recommendation_events`. Reset keys off **acceptance**, not display — showing a scan rec you then ignore must not reset the pressure. `--type`-filtered runs neither accrue nor reset pressure for excluded buckets; an accepted rec from a filtered run still resets its own bucket.
- Every output annotates which slot came from which bucket and why.

#### CLI contract (`ll-next`)

- `ll-next [--json] [--top N] [--type <verb> …] [--explain <target>] [--execute]` — `--top` defaults to 3; `--type` filters to given verbs; `--explain` prints the full axis table for one candidate; `--execute` runs the top-1 command (opt-in).
- Exit codes: `0` = recommendations emitted; `1` = no candidate survived gating (priority-sort fallback emitted with a warning); `2` = config error.
- `--json` emits a list of `Candidate` records; generate a JSON Schema into `docs/reference/schemas/` (same pattern as the existing `ll-generate-schemas` flow) so downstream consumers get a pinned contract.
- **Perf gate in the suite:** a pytest test asserts a full scoring pass on this repo's live backlog stays **< 1 s** (pure Python, no LLM, no network), asserted with a generous margin (fail at 3×) to catch order-of-magnitude regressions without machine-dependent flakes. This budget is also what keeps a session-start-hook placement viable later.

#### Acceptance logging from day one

Phase 4 learning is out of scope, but its decision stream only exists if collection starts at the first release — deferring it means starting Phase 4 with zero data.

- Add a `recommendation_events` table to the history DB (rec ID, timestamp, ranked candidate list, chosen/ignored, match source, plus a `viewed` marker — was `ll-next` output actually emitted in the session).
- "Accepted" is detected by **matching on `(action_type, target)`** against existing event tables — *not* exact command-string match, which breaks on arg reordering and wrappers. "Ignored" = no matching event by the end of the next session or 72 h, whichever comes first.
- "Outcome" is per-verb: issues join completed-issue stats (cycle time, corrections, reverts); loops join loop-event success; capture-issues = issues created within 7 days of the scan; docs/debt = delta in the underlying audit metric.
- Known limitation, recorded on purpose: acceptance matching can't distinguish "followed the rec" from "was going to do it anyway." Fine for the health metric; the `viewed` marker is the weak treatment indicator for any later learning work.

### Evaluation — what "a good recommendation" means

Phase 1 must beat plain `next-issue` before anything LLM-flavored ships on top. Three checks, cheapest first:

1. **Golden-set regression (pytest).** Snapshot project states as fixtures (issue dirs + fake history + optional goals file) with hand-agreed expected top-3. These fixtures are also the tuning harness for Phase 0 curves — and must include one candidate with missing curve axes and one with a missing gate axis, pinning the exclusion / fail-closed semantics.
2. **Backtest against git history.** Reconstruct past project states by checking out `.issues/` at historical commits (frontmatter dates alone are unreliable — issue files keep being edited after capture). Score: did the arena rank the issue that was *actually completed next, successfully* in its top-3? Metrics: **top-3 hit rate** and **MRR**, reported against `next-issue`'s ordering as the baseline. **Scope: the `implement-issue` bucket only** — the ground truth is what the developer actually did next, and hygiene verbs would be penalized by exactly the anti-starvation behavior the arena exists to add. Hygiene verbs are evaluated by check 3.
3. **Live acceptance rate.** From the acceptance log: fraction of top-1 recommendations acted on, and outcome quality of accepted ones. This is the ongoing health metric — if acceptance decays, the weights have drifted from reality.

## Acceptance criteria

- [ ] Phase 0: `utility/` module extracted; both aggregators exposed; golden test proves `next-loop` output byte-identical pre/post on a fixture history.
- [ ] Phase 0: `next` config key registered in `config-schema.json`; keyed-object weights; invalid config → exit 2.
- [ ] Phase 1: candidate generators exist for all nine verbs; `generic` is absent and the capture-as-issue path is the documented substitute.
- [ ] Phase 1: `ll-next` implements the CLI contract (exit codes 0/1/2, `--json`, `--top`, `--type`, `--explain`, opt-in `--execute`); JSON Schema generated into `docs/reference/schemas/`.
- [ ] Phase 1: missing-curve-axis exclusion and missing-gate-axis fail-closed semantics pinned by golden fixtures; coverage penalty applied at the selection layer.
- [ ] Phase 1: bucketed selection with persisted per-bucket pressure; pressure resets on acceptance only; `--type`-filtered runs excluded from accrual/reset.
- [ ] Phase 1: `recommendation_events` table live from first release, matching on `(action_type, target)` with the 72 h / next-session ignored rule.
- [ ] Perf gate: full scoring pass on the live backlog < 1 s, asserted in the suite.
- [ ] Evaluation: golden-set fixtures pass; backtest over git history reports top-3 hit rate and MRR vs the `next-issue` baseline for the `implement-issue` bucket.
- [ ] All four existing `next-*` CLIs unchanged in behavior.
