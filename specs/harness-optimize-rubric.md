# Harness-Optimize Evaluation Rubric

**Evaluand:** `scripts/little_loops/loops/harness-optimize.yaml` — its definition (static plane), its individual runs (run plane), and its accumulated telemetry (fleet plane).
**Checker:** [`specs/harness-optimize-rubric-check.py`](harness-optimize-rubric-check.py) — runs every discriminator below and emits a scorecard.
**Status:** Normative. Every dimension is mechanically checkable: a command or algorithm over external signals (exit codes, floats, JSONL, git objects), never an LLM self-grade.

---

## 1. The Load-Bearing Premise and the Admissibility Rule

The project's premise, operationalized so it can be measured and falsified:

> **P:** For a given task distribution, a harnessed run outperforms an unguided single call
> (`ab.json` `summary.delta > 0`) by more than its marginal cost
> (`median_tokens_harness / median_tokens_baseline`).

The empirical substrate (SHOR, *Towards Direct Evaluation of Harness Optimizers*, arXiv:2605.22505; distilled in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`):

| # | Finding | Consequence for this rubric |
|---|---------|------------------------------|
| P1 | 44.8–48.2% of optimizer update steps are detrimental (Analysis I) | A healthy gate must *reject* roughly half of proposals; acceptance rate is a scored band, not a maximization target |
| P2 | 94.4% of non-prompt intermediate errors persist to the final harness (Analysis II) | Revert integrity and cross-run continuity are scored; errors do not wash out on their own |
| P3 | Optimizer self-assessment accuracy is 0.334–0.549 — a coin flip (Table 1) | No dimension may use an LLM self-grade as its signal (MR-1 generalized to the rubric itself) |
| P4 | Priority-ranking ability predicts optimization ability, ρ = 0.602 | Diagnosis (component prioritization) is scored as a first-class abstraction |
| P5 | Optimization is trial-and-error unless externally measured step-wise | The scorer instrument and gate discrimination are gating dimensions — if they fail, nothing downstream means anything |

**Admissibility rule.** A dimension is scored **iff** all three hold:

1. **Premise-link** — it operationalizes one of P1–P5 (each dimension names its link).
2. **External signal** — its discriminator reads exit codes, numeric output, JSONL artifacts, or git objects. Never a model's opinion of its own work.
3. **Ablation validity** — disabling the mechanism it checks degrades a *named, measured* outcome (each dimension names it).

### Excluded dimensions (fail the admissibility rule)

| Candidate | Why excluded |
|-----------|--------------|
| LLM-judged "edit quality" | Violates rule 2; P3 shows 0.33–0.55 accuracy — worse than a coin on SWE-V |
| Prompt eloquence / style | No external signal; no premise-link |
| YAML aesthetics, state count, naming | No ablation validity — no measured outcome changes |
| Absolute runtime / speed | Cost matters only relative to lift; folded into H3 |
| **Raw harness pass-rate in isolation** | Confounds model capability with scaffold value. Under P, only the *delta vs. baseline* is admissible evidence. A rising pass-rate with a shrinking delta is the premise *breaking*, not improving — see § 7 |

---

## 2. Irreducible Abstractions → Dimension Groups

The optimizer harness decomposes into eight abstractions that cannot be expressed in terms of each other; the ninth is the meta-abstraction over the whole enterprise. (The four SHOR components — `prompt`/`tool`/`memory`/`workflow` — are the abstractions of the *target* harness; they appear inside groups D and E as the vocabulary of diagnosis.)

| Group | Abstraction | One-line definition | Weight |
|-------|-------------|---------------------|--------|
| A | **Scorer** | The external measurement instrument (`harbor_scorer` contract: exit 0 + bare float stdout) | 20 |
| B | **Gate** | The non-LLM accept/revert decision (`convergence` evaluator: target/progress/stall) | 26 |
| C | **Trajectory** | Memory that persists across iterations and runs (`trajectory.jsonl`) | 10 |
| D | **Proposal** | The LLM mutation generator, judged only by its externally observable products (git diffs) | 11 |
| E | **Diagnosis** | Priority ranking over target-harness components before editing (P4's lever) | 8 |
| F | **Budget** | Iteration/token economics (`max_iterations`, `max_steps`, cost telemetry) | 7 |
| G | **Isolation** | Per-run artifact separation and revertability (run_dir, git) | 6 |
| H | **Transfer** | Does improvement generalize — held-out, cross-host, and vs. baseline (premise accounting) | 12 |
| I | **Premise sentinel** | Earliest observable signal that P itself is failing | unweighted (§ 7) |

Weights sum to 100. Group I carries no weight because it does not measure harness *quality*: a perfectly built harness can sit on a dead premise, and a shoddy one on a live premise. It is reported as a state, not a score.

---

## 3. Scoring Model

- Each dimension scores **s ∈ {0, 0.5, 1}** (FAIL / PARTIAL / PASS) against its stated predicate. PARTIAL exists only where the dimension defines it.
- **SKIP** — required data absent (e.g., < min runs) or required flag not supplied. **NA** — structurally inapplicable (e.g., one host installed). Both are excluded from the aggregate denominator and reported as reduced **coverage**.
- **Gating dimensions** (`A1, A2, B1, B5, H1`): any FAIL caps the aggregate at 49 and forces exit code 1. Rationale: these are the instrument, the validator, the revert mechanism, and the premise-accounting data — with any of them broken, the other scores are unfalsifiable.
- **Aggregate** = round(100 × Σ wᵢsᵢ / Σ wᵢ) over evaluated (non-SKIP/NA) dimensions. **Coverage** = Σ evaluated wᵢ.
- **Tiers** (rubric-router compatible): high ≥ 85, medium ≥ 65, else low.

### Output contract (checker)

```
DIMENSION: <id> <name>: PASS|PARTIAL|FAIL|SKIP|NA (w=<n>) — <verbatim evidence>
...
SENTINEL: HEALTHY|WATCH|BREAKING|BROKEN|INSTRUMENT_FAILURE|INSUFFICIENT_DATA — <triggers>
PREMISE: delta=<x> tokens_ratio=<y> n=<n> age_days=<d>   (from latest ab.json, if any)
COVERAGE: <int>%
AGGREGATE: <int 0-100>
```

Exit codes: **0** pass · **1** gating failure · **3** sentinel BREAKING/BROKEN (no gating failure). The final `AGGREGATE:` line makes the checker consumable by `lib/rubric-router.yaml`'s `rubric_parse_scores`; the exit code makes it consumable by an `exit_code` evaluator; code 3 lets automation route to the pivot protocol (§ 7.4).

---

## 4. Dimension Catalog

Legend — **Plane:** S static · R run · F fleet. **G:** gating. All file paths repo-relative. Defaults in § 8; every threshold there is traceable to a system constant or a P-finding.

### A — Scorer (the instrument)

| | A1 · Scorer contract conformance | w=5 · **G** · Plane R |
|---|---|---|
| Premise-link | P5 — external step-wise measurement is what separates optimization from trial-and-error |
| Discriminator | Run `${scorer} ${tasks_dir}` once (checker `--scorer/--tasks-dir`). Contract from `lib/benchmark.yaml` `harbor_scorer`: exit 0 **and** stdout parses as a bare float |
| PASS | exit 0 ∧ float. FAIL otherwise. SKIP if `--scorer` not supplied |
| Ablation | A non-conforming scorer routes every `score` state to `on_error` → `revert_and_log`; the optimizer silently rejects everything |

| | A2 · Scorer noise floor | w=6 · **G** · Plane R |
|---|---|---|
| Premise-link | P1/P5 — the gate promotes any Δscore > tolerance (0.02); if scorer noise ≥ tolerance, hill-climbing degenerates to a random walk that *keeps* noise |
| Discriminator | Run the scorer K=5 times on unchanged targets; sample stddev σ |
| PASS | σ ≤ tolerance/2 = 0.01. PARTIAL: σ ≤ tolerance. FAIL: σ > tolerance. SKIP without `--scorer` |
| Ablation | With σ > tolerance, accepted-edit "improvements" are indistinguishable from resampling noise |

| | A3 · Scorer dynamic range | w=4 · Plane F |
|---|---|---|
| Premise-link | P5 — an instrument that cannot fail cannot discriminate (instrument-level analog of the Bernoulli-variance check) |
| Discriminator | Pool all `trajectory.jsonl` lines across runs; count distinct `score` values |
| PASS | ≥ 2 distinct values. FAIL: 1 distinct value over ≥ 10 lines. SKIP: < 10 lines |
| Ablation | A constant scorer makes B3, B4, B6, F2 and sentinel S1/S2 all vacuous |

| | A4 · Held-out separation | w=5 · Plane R |
|---|---|---|
| Premise-link | P1 — "Hardcoding" and "Task-specific Addition" are named optimizer error types; the gate scores on the tuning set every iteration, so overfitting to it is *rewarded* unless a held-out set exists |
| Discriminator | Held-out set = `--heldout-dir` or sibling `<tasks_dir>.heldout`. With `--scorer`: score tuning and held-out; gap = tuning − heldout |
| PASS | held-out exists ∧ gap ≤ 0.15. PARTIAL (0.5): held-out exists, unmeasured (no `--scorer`). FAIL: no held-out set exists |
| Ablation | Without it, D-group catches only *syntactic* overfit; semantic hardcoding sails through the gate |

### B — Gate (accept/revert)

| | B1 · Validator clean of ERRORs | w=6 · **G** · Plane S |
|---|---|---|
| Premise-link | P3 — MR-1/MR-7/MR-9/static-ref are the codified defenses against self-grading and interpolation corruption |
| Discriminator | `ll-loop validate harness-optimize --json` → zero ERROR-severity findings |
| PASS | 0 ERRORs. FAIL: any. SKIP: `ll-loop` not on PATH |
| Ablation | MR-9 alone: `$$(` expands to the runner PID and silently corrupts every downstream `${captured.*}` |

| | B2 · Warnings clean or justified | w=2 · Plane S |
|---|---|---|
| Premise-link | P1/P2 — MR-2..MR-10 WARNs each encode an observed failure mode (BUG-2383, ENH-1957, …) |
| Discriminator | Same command: zero WARNING findings that lack a suppression flag in the YAML |
| PASS | 0 unsuppressed. PARTIAL: ≤ 2. FAIL: > 2. SKIP: no CLI |

| | B3 · Gate discrimination (variance) | w=6 · Plane F |
|---|---|---|
| Premise-link | P1 — with ~half of edits detrimental, a truthful gate's pass-rate p ≈ 0.5 → variance p(1−p) ≈ 0.25; the guide: "a gate can satisfy MR-1 yet be toothless" |
| Discriminator | `ll-loop diagnose-evaluators harness-optimize --json`, or equivalent internal computation (pair `state_enter`/`evaluate` events in `.loops/.history/*-harness-optimize/events.jsonl`, Bernoulli variance per state). Applies to the `gate` state |
| PASS | variance ≥ 0.05 over ≥ 10 verdicts. FAIL: < 0.05. SKIP: < 10 verdicts |
| Ablation | This is the system's own definition of a toothless evaluator (`analytics/variance.py`, threshold 0.05, min_runs 10) |

| | B4 · Acceptance-rate realism band | w=4 · Plane F |
|---|---|---|
| Premise-link | P1 — SHOR measured 44.8–48.2% detrimental steps. â ≈ 1.0 means the gate filters nothing (or the premise is saturating → feeds sentinel S2); â ≈ 0 means the proposal generator is dead |
| Discriminator | Pooled `accepted` fraction â over trailing-window trajectory lines |
| PASS | 0.15 ≤ â ≤ 0.85. FAIL outside. SKIP: < 10 lines |

| | B5 · Revert/commit integrity | w=5 · **G** · Plane F |
|---|---|---|
| Premise-link | P2 — errors persist unless *actually* reverted; the accept/revert branch is "the operational answer to half of edits are detrimental" |
| Discriminator | Every trajectory line: `accepted:true` → non-empty `commit_sha` that resolves (`git cat-file -e <sha>^{commit}`) with subject matching `harness-optimize: iter`; `accepted:false` → empty `commit_sha` |
| PASS | 100% conform. FAIL: any violation. SKIP: no trajectory lines |
| Ablation | A dangling sha means load_directive's best-commit checkout restores garbage — cross-run continuity (G2) silently breaks |

| | B6 · Accepted-chain monotonicity | w=3 · Plane F |
|---|---|---|
| Premise-link | P5 — hill-climbing's invariant: within a run, accepted scores are non-decreasing (within tolerance 0.02) |
| Discriminator | Per trajectory file: sequence of `score` over `accepted:true` lines; flag any drop > tolerance |
| PASS | no drops. FAIL: any. SKIP: no file with ≥ 2 accepted lines |
| Ablation | A drop means the gate's `previous` wiring (`${captured.prev_score.output}`) is broken — accepting regressions |

### C — Trajectory (memory)

| | C1 · Trajectory schema validity | w=3 · Plane F |
|---|---|---|
| Premise-link | P2 — the trajectory is the substrate for revert, resume, and every fleet dimension; the loop builds JSONL by shell interpolation, which corrupts on multi-line scorer output (MR-10-adjacent) |
| Discriminator | Every line parses as JSON with `iter:int, score:number, accepted:bool, commit_sha:str` |
| PASS | ≥ 99% valid ∧ no file 100% invalid. FAIL otherwise. SKIP: no files |

| | C2 · Cumulative feed-forward ledger | w=4 · Plane S |
|---|---|---|
| Premise-link | P1 "Redundant Duplication" + guide § *Feed the trajectory forward*: without memory of reverted edits, the optimizer re-proposes what it just discarded |
| Discriminator | Static: the `propose` (or a feeding) state's action interpolates a prior-iteration ledger — references `trajectory`, a rejected-summary capture, or a `${context.run_dir}` ledger file — beyond merely `${captured.benchmark_score.output}` |
| PASS | ledger reference present. FAIL: absent. *(Expected today: FAIL — `propose` receives only baseline + last score.)* |

| | C3 · Duplicate re-proposal rate | w=3 · Plane F |
|---|---|---|
| Premise-link | Same as C2, measured at runtime rather than structurally |
| Discriminator | Requires candidate snapshots `${context.run_dir}/candidates/iter-<N>.txt` (convention this spec establishes). dup-rate = duplicated sha256 (whitespace-normalized) / rejected candidates |
| PASS | dup-rate ≤ 0.2. FAIL: > 0.2. SKIP: no snapshots (unlocked by C2 remediation — § 6) |

### D — Proposal (judged by its diffs)

| | D1 · Blast radius | w=3 · Plane F |
|---|---|---|
| Premise-link | P2 + "Safety Violation" — revertability presumes bounded writes (`git restore ${targets}` restores only declared targets) |
| Discriminator | `git show --name-only` per accepted commit. With `--targets`: file set ⊆ declared targets. Without: every commit's file set ⊆ the first accepted commit's file set |
| PASS | 100%. FAIL: any leak. SKIP: no accepted commits |

| | D2 · Diff economy | w=2 · Plane F |
|---|---|---|
| Premise-link | P1 "Overengineering" — "appends without pruning"; guide: watch diff size, favor deletions |
| Discriminator | `git show --numstat` per accepted commit: median added lines ≤ 120 ∧ max ≤ 400 |
| PASS | both. PARTIAL: median ok, max exceeded. FAIL: median exceeded. SKIP: no accepted commits |

| | D3 · Dangling-reference rate | w=3 · Plane F |
|---|---|---|
| Premise-link | P1 "Hallucination" — references tools/paths that don't exist |
| Discriminator | Added lines of accepted commits (last 20): backticked repo-path tokens must exist at HEAD (`git cat-file -e HEAD:<path>`); `ll-*` CLI names must appear in `scripts/pyproject.toml` script entries |
| PASS | 0 dangling. FAIL: any. SKIP: no accepted commits |

| | D4 · Guardrail preservation | w=3 · Plane F |
|---|---|---|
| Premise-link | P1 "Safety Violation" — strips step/cost limits or deletes scaffold |
| Discriminator | For loop-YAML targets: removed lines matching `max_steps|max_iterations|timeout|target_score|tolerance` keys without a same-key added line in the same accepted commit |
| PASS | none. FAIL: any. NA: no loop-YAML targets |

### E — Diagnosis (priority ranking)

| | E1 · Diagnose state on every cycle | w=4 · Plane S |
|---|---|---|
| Premise-link | P4 — ρ = 0.602; the guide's canonical shape makes `diagnose` initial *and* the commit-loopback target ("the biggest lever on fix-rate") |
| Discriminator | Loop graph contains a state named `/diagnos/i` or whose action contains `COMPONENT=`; BFS from each commit-state's loopback reaches it before `propose` |
| PASS | present ∧ on-cycle. PARTIAL: present, not on every cycle. FAIL: absent. *(Expected today: FAIL — harness-optimize.yaml has no diagnose state; `propose` self-selects its file.)* |

| | E2 · Diagnosis commitment contract | w=3 · Plane F |
|---|---|---|
| Premise-link | P4 + guide's "one-line hardening": diagnose must emit one committed component and refuse to advance without it |
| Discriminator | Snapshots `${context.run_dir}/diagnosis/iter-<N>.txt` (convention): last line matches `^COMPONENT=(prompt|tool|memory|workflow)$` in 100% of iterations |
| PASS / FAIL / SKIP | 100% / any miss / no snapshots (unlocked by E1 — § 6) |

| | E3 · Component-coverage entropy | w=1 · Plane F |
|---|---|---|
| Premise-link | P4 — a diagnosis that always answers the same component is a constant, contributing zero information (variance argument applied to diagnosis) |
| Discriminator | ≥ 2 distinct components across trailing 10 diagnoses |
| PASS / FAIL / SKIP | ≥2 / 1 / E2 skipped |

### F — Budget (economics)

| | F1 · Evaluator-wide discrimination | w=3 · Plane F |
|---|---|---|
| Premise-link | P5 — `calibrate-budget`: iterations against a toothless evaluator earn nothing |
| Discriminator | `ll-loop calibrate-budget harness-optimize --json` zero WARNs, or internal: every evaluator state with ≥ 10 verdicts has variance ≥ 0.05 (B3 generalized beyond the gate) |
| PASS / FAIL / SKIP | all ≥ 0.05 / any below / < 10 verdicts everywhere |

| | F2 · Budget calibrated to yield curve | w=2 · Plane F |
|---|---|---|
| Premise-link | P1 — with ~half of edits detrimental, marginal yield decays; budget beyond the last-acceptance quantile is pure token burn |
| Discriminator | p90 of per-run max(`accepted` iter) across ≥ 5 runs; `max_iterations` (context default 30) ≤ ⌈1.5 × p90⌉ |
| PASS / FAIL / SKIP | within / beyond / < 5 runs with acceptances |

| | F3 · Cost telemetry present | w=2 · Plane F |
|---|---|---|
| Premise-link | P — the premise is *cost-adjusted*; without token accounting, H3 and sentinel S4 are blind |
| Discriminator | ≥ 1 `ab.json` ≤ 90 days old with `summary.median_tokens_harness > 0` |
| PASS / FAIL | present / absent-or-zero |

### G — Isolation & reproducibility

| | G1 · No cross-run trajectory append | w=2 · Plane F |
|---|---|---|
| Premise-link | P2 + MR-3/MR-5 — shared paths corrupt state across runs; `init_run` keys the whole-file path on second-resolution epoch |
| Discriminator | Within any single `trajectory.jsonl`: `iter` never decreases (a restart-at-1 mid-file = a second run appended to the same file) |
| PASS / FAIL / SKIP | no decreases / any / no files |

| | G2 · Resume continuity | w=3 · Plane F |
|---|---|---|
| Premise-link | P2 — gains must persist across runs or the optimizer re-pays for the same ground; `load_directive` checks out the best accepted commit |
| Discriminator | Working-tree blobs of the newest accepted commit's files (`git hash-object`) equal that commit's blobs (`git rev-parse <sha>:<path>`); "newest" = topological tip of the accepted set (`git merge-base --independent`), clock-independent, falling back to commit date only for diverged tips |
| PASS / FAIL / SKIP | equal / drifted / no accepted commits |

| | G3 · Clean-tree invariant | w=1 · Plane F |
|---|---|---|
| Premise-link | P2 — `git restore ${targets}` (revert path) only means anything from a clean start |
| Discriminator | `git status --porcelain -- <targets>` empty (targets from `--targets` or accepted-commit union) |
| PASS / FAIL / SKIP | empty / dirty / targets unknown |

### H — Transfer (premise accounting)

| | H1 · Fresh baseline A/B exists | w=3 · **G** · Plane F |
|---|---|---|
| Premise-link | P — the *only* admissible evidence for the premise is harness-vs-baseline delta; stale evidence is no evidence |
| Discriminator | Latest `ab.json` mtime ≤ 30 days |
| PASS / FAIL | fresh / stale-or-absent (data absence **is** the failure — this dimension cannot SKIP) |

| | H2 · Harness lift | w=4 · Plane F |
|---|---|---|
| Premise-link | P directly — `delta = harness_pass_rate − baseline_pass_rate` |
| Discriminator | Latest `ab.json`: `summary.delta ≥ 0.05` ∧ `len(items) ≥ 10` |
| PASS | both. PARTIAL: delta > gate tolerance (0.02) but n < 10 or delta < 0.05. FAIL: delta ≤ tolerance — indistinguishable from noise (aligned with sentinel S3's parity definition). SKIP: no ab.json (already a gating FAIL at H1) |

| | H3 · Cost-adjusted lift | w=3 · Plane F |
|---|---|---|
| Premise-link | P — "by more than its marginal cost" |
| Discriminator | ratio = `median_tokens_harness / median_tokens_baseline`; PASS: ratio ≤ 3 ∨ delta ≥ 0.15. PARTIAL: ratio ≤ 5. FAIL: beyond |

| | H4 · Cross-host stability | w=2 · Plane F |
|---|---|---|
| Premise-link | Guide § cross-host: an improvement whose harness-vs-baseline *ordering reverses* between hosts is host-specific, not premise evidence |
| Discriminator | ≥ 2 `ab.json` with distinct `host` fields in window: sign(delta) agrees. NA: single host installed or `host` field absent |
| PASS / FAIL / NA | agree / reversal / inapplicable |

---

## 5. Dimension Dependency Graph

Some dimensions are unlockable only after loop hardening — the checker reports them SKIP with the blocking remediation, so a low coverage number is itself diagnostic:

```
C2 (add ledger + candidate snapshots) ──► C3 (dup-rate)
E1 (add diagnose state) ──► E2 (commitment contract) ──► E3 (entropy)
A1/A2 (supply --scorer) ──► A4 measured-gap variant
H1 (run --baseline) ──► H2, H3, F3, sentinel S3/S4
```

---

## 6. Data Sources (exact schemas)

| Source | Path | Schema (fields used) |
|--------|------|----------------------|
| Trajectory | `.ll/runs/harness-optimize-<epoch>/states/<state>/trajectory.jsonl`, `.loops/runs/**/states/<state>/trajectory.jsonl` | `{"iter": int, "score": float, "accepted": bool, "commit_sha": str}` per line |
| Run events | `.loops/.history/<ts>-harness-optimize/events.jsonl` | `{"event": "state_enter", "state": str}` · `{"event": "evaluate", "verdict": str}` — verdicts for the `gate` convergence state: `target` / `progress` / `stall` |
| A/B results | `<run_dir>/ab.json` (glob `.loops/**/ab.json`, `.ll/**/ab.json`) | `summary: {harness_pass_rate, baseline_pass_rate, delta, median_tokens_harness, median_tokens_baseline}`, `items: [{harness_pass, baseline_pass, ...}]` |
| Accepted edits | git | subject `harness-optimize: iter <N>, score <S>` |
| Loop definition | `scripts/little_loops/loops/harness-optimize.yaml` | states, routes, context defaults |
| Candidate/diagnosis snapshots | `${context.run_dir}/candidates/iter-<N>.txt`, `${context.run_dir}/diagnosis/iter-<N>.txt` | conventions established by this spec (C3, E2) |

---

## 7. Dimension I — the Premise-Validity Sentinel

**What it detects:** the premise P failing not because the harness is badly built, but because the underlying model stopped needing the scaffolding. The sentinel is orthogonal to the aggregate — it consumes several of the same signals with *inverted* polarity (e.g., a saturating B4 is a quality failure *or* a premise success, disambiguated by instrument health).

### 7.1 Signals, ordered by lead time

Earliest signals are passive (zero marginal cost, accrue on every ordinary optimization run); the confirmatory signal is an active probe. This ordering is the point: saturation appears in routine runs *weeks before* anyone schedules an A/B.

| Signal | Definition (mechanical) | Cost | Lead |
|--------|------------------------|------|------|
| **S1 · First-iteration saturation** | Fraction of trailing W=10 runs whose *first* `gate` verdict is `target` (events.jsonl) — the raw model + current harness hits `target_score` before any optimization happens | passive | earliest |
| **S2 · Gate collapse toward always-accept** | `gate` pass-rate ≥ 0.95 ∧ variance < 0.05 over ≥ 10 verdicts — every edit "improves"; there is no headroom left to discriminate | passive | early |
| **S3 · A/B parity** | Latest k consecutive `ab.json` probes (each n ≥ 10) with `delta ≤ 0.02` (the gate's own tolerance — below it, "lift" is indistinguishable from noise) or `delta < 0` | active probe | confirmatory |
| **S4 · Fleet delta decay** | OLS slope of `delta` over trailing ≤ 5 probes < 0 ∧ latest `delta < 0.10`; corroborated by `tokens_ratio ≥ 1` (the harness trends toward pure overhead) | passive over probe history | strategic |

### 7.2 Instrument-health precondition

S1/S2 are premise signals **only if the instruments are healthy**. Instruments are *unhealthy* iff any of A2/A3/B1 is FAIL — a SKIP is absence of evidence, not evidence of breakage (note that a truly saturated fleet produces few trajectory lines, so A3 legitimately SKIPs precisely when S1 fires). When unhealthy, the identical observations mean the *scorer or gate is broken*, and the sentinel reports `INSTRUMENT_FAILURE` instead. This disambiguation is the sentinel's load-bearing move — without it, every toothless evaluator masquerades as model progress.

### 7.3 State machine (first match wins)

| State | Trigger |
|-------|---------|
| `INSUFFICIENT_DATA` | < 5 runs ∧ no ab.json |
| `INSTRUMENT_FAILURE` | (S1 ≥ 0.5 ∨ S2) ∧ instruments unhealthy |
| `BROKEN` | S3 k ≥ 2 ∧ (S1 ≥ 0.8 ∨ S2) |
| `BREAKING` | S3 k ≥ 2 ∨ (S3 k = 1 ∧ (S1 ≥ 0.5 ∨ S2 ∨ S4)) |
| `WATCH` | S1 ≥ 0.5 ∨ S2 ∨ S3 k = 1 ∨ S4 |
| `HEALTHY` | none of the above |

### 7.4 Response protocol (the pivot, before obsolescence)

| State | Mandated response |
|-------|-------------------|
| `WATCH` | Freeze `max_iterations` raises. Schedule an active probe now: `ll-loop run harness-optimize --baseline` (and `--cross-host` if ≥ 2 hosts). Passive signals are cheap but confounded; buy the direct measurement |
| `BREAKING` | Run the confirmatory probe on the **held-out** task set. Stop optimizing this target/task-class pair. Record via `ll-issues decisions add` so the finding outlives the session |
| `BROKEN` | Emit `PREMISE-BREAK` (exit 3). Then pivot along whichever branch the evidence supports: **(a)** if A3 shows score compression at ceiling → the benchmark is saturated, not the premise: raise `target_score` / harden the task set and re-baseline; **(b)** if delta ≤ 0 at honest difficulty → retire the scaffold *for this task class*, keep a quarterly cheap re-probe cadence; **(c)** re-aim the optimizer at task classes where S1 < 0.5 — the premise is per-task-class, and it breaks frontier-inward, not globally |
| `INSTRUMENT_FAILURE` | Fix A2/A3/B1 first; premise inference is suspended — do **not** treat saturation as model progress |

The per-task-class relativization in (c) is the strategic content: "LLMs need harness scaffolding" never fails everywhere at once. It fails first on the easiest task distribution the project serves; the sentinel's job is to detect *that frontier moving*, and the project's job is to stay ahead of it or stand down deliberately — with a decision record — rather than drift.

---

## 8. Defaults (every threshold traceable)

| Constant | Value | Source |
|----------|-------|--------|
| Gate tolerance | 0.02 | `harness-optimize.yaml` `gate.evaluate.tolerance` |
| Variance floor / min verdicts | 0.05 / 10 | `analytics/variance.py` (`threshold`, `min_runs`) |
| Acceptance band | [0.15, 0.85] | P1: 44.8–48.2% detrimental steps ± sampling slack |
| Noise floor | tolerance/2 = 0.01 | half-interval of the gate's own progress test |
| Held-out gap cap | 0.15 | default; override `--heldout-gap` |
| Diff economy | median ≤ 120, max ≤ 400 added lines | default; override `--diff-median/--diff-max` |
| Dup re-proposal cap | 0.20 | default; override `--dup-rate` |
| Budget factor | 1.5 × p90(last accepted iter) | default; override `--budget-factor` |
| A/B freshness / cost window | 30 / 90 days | default; override `--ab-max-age/--cost-max-age` |
| Lift / strong-lift | 0.05 / 0.15 | ≥ 2.5 × gate tolerance / cost-waiver level |
| Token-ratio cap / hard cap | 3 / 5 | default; override `--token-ratio` |
| Sentinel window W / parity k | 10 runs / 2 probes | matches min_runs; two probes ≈ Wilson-overlap at n=10 |
| Tiers | 85 / 65 | `lib/rubric-router.yaml` defaults |

---

## 9. Running It

```bash
# Full check (structural + fleet planes; live scorer probes enabled):
python3 specs/harness-optimize-rubric-check.py \
  --repo . --scorer ./scripts/score.sh --tasks-dir tasks/ \
  --targets "skills/foo/SKILL.md" --json .loops/diagnostics/rubric-scorecard.json

# Telemetry-only (no scorer runs; A1/A2 SKIP):
python3 specs/harness-optimize-rubric-check.py --repo .
```

Wiring into a loop: call as a `shell` state — the exit code drives an `exit_code` evaluator (route exit 3 via `on_error` to a pivot state), or feed stdout to `lib/rubric-router.yaml`'s `rubric_parse_scores`, which consumes the final `AGGREGATE:` line.

**Why this is not a pytest CI gate:** the fleet-plane dimensions score *live telemetry* (run history, ab.json age), which is machine-local and time-varying — exactly what the repo's test suite must not depend on. The static-plane subset (B1/B2, C2, E1) is already enforced by `ll-loop validate` where it is ERROR-severity.

---

## 10. Calibration and Self-Test

A rubric on which everything passes is itself toothless (the variance argument, applied one level up). Expected results against the repo **today** — these are the rubric's proof of discrimination:

| Dimension | Expected | Why |
|-----------|----------|-----|
| C2 | **FAIL** | `propose` receives baseline + last score only; no rejected-edit ledger |
| E1 | **FAIL** | no diagnose state; `propose` self-selects the file (guide's canonical shape not yet adopted by the reference loop) |
| C3, E2, E3 | SKIP | snapshot conventions not yet emitted by the loop |
| A1, A2, A4-measured | SKIP | no `--scorer` in telemetry-only mode |
| H1 | FAIL until a `--baseline` probe is run | premise accounting starts at zero |
| B1 | PASS expected | no `check_semantic`/`llm_structured` states; `$${...}`/`:default=` forms used correctly — verify, don't assume |

If a future edit makes every dimension PASS while the fleet's sentinel stays `HEALTHY` across model generations — distrust the rubric before you trust the harness, and re-derive thresholds from the then-current SHOR-successor data.
