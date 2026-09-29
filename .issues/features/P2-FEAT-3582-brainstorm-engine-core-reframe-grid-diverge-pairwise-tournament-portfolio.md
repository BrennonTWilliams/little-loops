---
id: FEAT-3582
type: FEAT
title: 'Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:13Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
relates_to:
- FEAT-2248
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 70
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
---

# FEAT-3582: Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio

## Summary

Replace the body of `scripts/little_loops/loops/brainstorm.yaml` with the new core
engine (C + B + A from EPIC-3581): **reframe → grid-tagged diverge → script dedup →
per-cell shortlist → script-driven pairwise tournament → portfolio output**, with a
hard minimum-idea invariant. Removes difflib novelty, the saturation counter, and the
forced best-of hybrid.

## Current Behavior

- `dedup_novelty` uses difflib `SequenceMatcher` against `novelty_threshold: "0.55"`;
  observed max pairwise ratio across 45 ideas was 0.44, so nothing is ever deduped and
  `saturation_gate` never early-exits (evidence: transient run dirs under
  `.loops/runs/brainstorm-*`).
- Each `diverge` call sees only the brief, never prior ideas.
- `cluster` / `rank` / `converge` are single listwise LLM passes; `converge` always
  synthesizes a hybrid.
- `verify_artifacts` only checks `brainstorm.md` is non-empty, so a zero-idea run
  (07-01) whose report says "No synthesis produced" passes.

## Expected Behavior

1. `reframe` — generate N problem framings ("How might we…"), each with an LLM-emitted
   1–5 `score` (specificity/usefulness as a lens on the brief); a script selects the top
   3 by score (ties: generation order). Skippable per profile — a skipped `reframe`
   writes one empty framing so `lenses.txt` lines stay `framing|lens`.
2. `diverge` once per lens, with framings assigned round-robin across lenses (L
   calls, not F×L) — the prompt reads `diverge_state.md` (the running list of idea
   titles **and the current per-cell occupancy**) and instructs the model to favor
   empty or under-filled cells. Each idea is emitted with a grid cell whose two values
   must come from the profile's enumerated axis bins. A per-lens `ingest` script state
   (runs after every `diverge`) assigns stable IDs, normalizes each cell value (strip +
   casefold, then map to the canonical bin spelling), rejects (flags `off_grid`) any
   value that still matches no bin, and regenerates `diverge_state.md` for the next
   lens. Off-grid ideas stay in `ideas.jsonl` with `off_grid: true` but are excluded
   from `shortlist`, `min_ideas`, and `min_cells`; the report states the off-grid
   share (a high share means the bins were poorly communicated in the prompt).
3. `dedup` — one cheap LLM pass over `{id, title, body excerpt}` (first ~200 chars of
   `body`) emits duplicate groups by idea ID. Titles alone are not enough: with
   occupancy steering the model can relabel a paraphrase into an empty cell, which
   would inflate `min_cells` and the finalist count. A script collapses each group,
   keeping the **first-generated** idea as representative (never "longest body"). The
   collapse **fails open**: unknown IDs are
   ignored, an ID appearing in more than one group stays in the first group only, groups
   with fewer than 2 valid members are ignored, and unparseable output skips dedup
   entirely (logged to `dedup.log`) — malformed output never drops ideas.
4. `shortlist` — one representative per occupied cell, drawn only from ideas with
   `grounded != false` (FEAT-3584 may have marked some `false` before this step).
   Single-idea cells are taken by the script; all multi-idea cells are resolved in
   **one batched LLM call** (a pick per cell). A malformed or missing pick falls back to
   the first-generated idea in that cell. **Cap first, then reserve**: when more than
   `max_finalists` cells are occupied (a 3×3 grid can have 9), drop the lowest-occupancy
   cell(s) until the cap is met (ties: drop the later cell in grid order); dropped cells
   are listed in `shortlist.json` and the report. Then, when the resolved profile asks
   for a reserve (`reserve: 2`, set by FEAT-3584 for `ground=web`), the next-best
   candidates per surviving cell go to `reserve`, not `finalists`. `shortlist` writes
   `finalists.json` (§ Data Contract → Finalists file); the tournament child reads
   only its `finalists` list.
5. `check_floors` (script) — runs at **two stages**, both before `tournament`:
   `check_floors --stage generation` right after `shortlist` (post-dedup, on-grid,
   `grounded != false` ideas ≥ `min_ideas`, occupied cells ≥ `min_cells`, finalists ≥ 2),
   so a doomed run fails before paying for web-grounding or render calls; and
   `check_floors --stage pre_tournament` after every filtering state (`ground_web`,
   `materialize` — both skipped when their profile knob is off, in which case this stage
   re-verifies the unchanged `finalists.json`), so the tournament never sees a 0- or
   1-player field. Both route to `finalize_failed`. Both stages and
   `validate_portfolio` call **one function** (`brainstorm_engine.check_floors(stage)`), so
   the checks cannot drift.
6. `tournament` — full **round-robin** over the finalists, script-built and
   script-ranked, run as a **sub-loop** (one parent step); one LLM judge call per pair
   with the presentation order counterbalanced across finalists, plus a reversed-order
   probe of the top-3 head-to-heads. See § Tournament Specification.
7. `portfolio` — script writes canonical `portfolio.json` (winner, runner-up, wildcard — see § Data Contract for the slot rules; `winner` is always non-null) and `winners.md` (the non-null portfolio members, in
   that order, each line carrying a `role` key of `winner`/`runner_up`/`wildcard`;
   `top_k` is removed); hybrid only when `synthesize=true`.
8. `validate_portfolio` (script, **before any sink**) — calls
   `brainstorm_engine.check_floors(stage="final")` (same thresholds; post-dedup idea
   count < `min_ideas`, occupied cells < `min_cells`, eligible finalists < 2 all fail) and
   adds reference integrity: winner/runner-up/wildcard IDs must resolve in `ideas.jsonl`
   and the winner must be non-null.
9. `verify_artifacts` — remains after sinks as a report-integrity check.

Sinks (`none|file|issue|decision`) keep their contract and read `winners` from the
portfolio. No sink executes unless `validate_portfolio` passed.

## Use Case

**Who**: A little-loops user running `ll-loop run brainstorm "<brief>"` to explore options for a naming, design, or product question.

**Context**: Today every run is 9 lenses × 5 ideas, dedup never fires, and the output is a single Frankenstein hybrid; a run can even "succeed" with zero ideas.

**Goal**: Get a diverse, de-duplicated set of ideas ranked by structured pairwise judgment.

**Outcome**: `brainstorm.md` presents a portfolio (winner, runner-up, and a wildcard that differs from the winner on both grid axes) plus the grid map, and the run fails loudly if too few ideas or cells were produced.

## Motivation

The 4 historical `brainstorm-*` runs (see EPIC-3581 § Motivation) show the current core is inert where it matters:

- Dedup/saturation never fire: max pairwise difflib ratio was 0.44 vs the 0.55 threshold across 45 ideas, and `saturation.txt` stayed 0 in all runs.
- `diverge` never sees prior ideas, so there is no cross-lens anti-anchoring.
- `cluster`/`rank`/`converge` are single listwise LLM passes (`converge` read ~319k input tokens in one run) and always force a hybrid.
- A zero-idea run passes `verify_artifacts` because it only checks `brainstorm.md` is non-empty.

This feature is the core (C + B + A) that every other EPIC-3581 child builds on.

## Proposed Solution

Rewrite the state graph in `scripts/little_loops/loops/brainstorm.yaml` (keep `init`, sinks, `finalize_*`, `on_handoff: spawn`).

**Engine module (2026-09-29 decision).** All deterministic logic lives in a new tested module,
`scripts/little_loops/brainstorm_engine.py`, invoked from thin shell states as
`$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <command> --run-dir "${context.run_dir}"`
(the idiom `autodev.yaml` uses for `little_loops.autodev_summary`, and `assumption-firewall.yaml` for `$${LL_PYTHON:-python3}`). LLM output reaches the module only as a file the state wrote (heredoc-to-file or the `<state>_output.txt` capture), never interpolated into source — this keeps MR-11 satisfied without per-state escaping gymnastics. Commands: `ingest`, `collapse`, `shortlist-apply`, `check-floors --stage generation|pre_tournament|final`, `build-schedule`, `record-verdict`, `rank`, `salvage`, `portfolio`, `validate`; FEAT-3583/3584/3585/3586 add `resolve-profile`, `probe-*`, `materialize-check`, `annotate`. The YAML keeps only orchestration: prompts, routing, `evaluate:` clauses, and one-line module calls. Non-goal: moving prompts out of the YAML — they stay visible to `ll-loop show`.

1. `reframe` — LLM emits N "How might we…" framings with a 1–5 `score` each; a script selects the top 3 (ties: generation order) and seeds `diverge_state.md` (empty titles, zero occupancy).
2. `diverge` — one call per lens (framing assigned round-robin; `lenses.txt` lines pair `framing|lens`); the prompt reads `diverge_state.md` (running idea titles + per-cell occupancy) and asks for empty/under-filled cells; each idea is emitted as a tagged JSON line with `cell` (2 values, each from the profile's axis bins). **`ingest`** (script, after every `diverge`, routes back to `pop_lens`) assigns IDs, flags off-grid cells, appends `ideas.jsonl`, and rewrites `diverge_state.md`; off-grid ideas do not count toward `min_cells`.
3. `dedup` — an LLM pass over `{id, title, body excerpt}` emits duplicate groups (`DUP_GROUPS_JSON:`); a Python heredoc collapses each group to its first-generated member. Duplicate detection and per-cell representative selection are separate steps.
4. `shortlist` — script takes single-idea cells (excluding `grounded: false` ideas); one batched LLM call picks a representative for every multi-idea cell (fallback: first-generated). Cap at `max_finalists` first (lowest-occupancy cell dropped first; see Expected Behavior 4), then fill `reserve` when the profile asks for it; writes `finalists.json` (§ Data Contract → Finalists file).
5. `check_floors` — script gate at two stages (Expected Behavior 5): `generation` right after `shortlist`, `pre_tournament` after the optional `ground_web`/`materialize` states and immediately before `tournament`; failure → `finalize_failed`.
6. `tournament` — a sub-loop state (`loop:`; the child runs its own executor and `max_steps`, so the parent spends one step). Round-robin per § Tournament Specification; script builds the pair schedule, one judge call per pair, script ranks. The child is `brainstorm-tournament.yaml` (see § Tournament Specification → Child loop); verify it against `ll-loop list`, `ll-verify-package-data`, and the built-in loop count in `README.md`.
7. `portfolio` — script writes `portfolio.json` (the one canonical portfolio format) and `winners.md`; hybrid only when `synthesize=true`. A profile's `output_shape` affects only how `brainstorm.md` is rendered, never `portfolio.json`.
8. `resolve_profile` (script, after `init`) — owned here so FEAT-3583 only adds presets and the classifier: reads the profile named by context `mode` (default `artifact` until FEAT-3583 flips it to `auto`), validates it, writes `${context.run_dir}/profile.json`. Ships with the built-in `artifact` profile only. Every later state reads resolved values from `profile.json`; no state hardcodes profile behavior.
9. `validate_portfolio` — gate before `route_sink`; reruns the `check_floors` body (§ Data Contract floors) and adds winner-reference integrity. Fails to `finalize_failed` with no sink executed.
10. `verify_artifacts` — report-integrity check after sinks.
11. `finalize_done` / `finalize_failed` — rewrite the prompts that name `ranked.md`/`clusters.md`/saturation artifacts (they no longer exist) to name `portfolio.json`, `ideas.jsonl`, `tournament.json`, and the grid map.

Reuse `parse_tagged_json` and `queue_pop` from `lib/common.yaml`. Remove difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, `saturation.txt`.

### Data Contract

Owned by this issue; FEAT-3583..3586 extend it, never redefine it.

- **Idea IDs**: script-assigned (`i001`, `i002`, … in generation order), stable for the run; the LLM never invents IDs.
- **Common fields** (every profile): `id`, `title`, `body`, `framing`, `lens`, `cell`, `off_grid`. Profile-specific fields live under an `extra: {}` object.
- **Legacy mapping** for `winners.md` / sinks: `title`→`text`, `body`→`rationale` (both keys written).
- **Cell vocabulary**: each profile declares `axes: [{name, bins: [str, …]}, {name, bins: [str, …]}]` (FEAT-3583). A cell is valid only if both values are in the bins. The core ships a default 3×3 grid for runs without a profile.
- **Floor defaults** (pinned 2026-09-28; a profile may lower them): `min_ideas: 12`, `min_cells: 4` (default 3×3 grid), framings selected by `reframe`: 3 (ties broken by generation order), `max_finalists: 8`. **These numbers live in the profile (`artifact` ships them), not in loop context.** The context keys `min_ideas`, `min_cells`, `max_finalists` default to `""` (inherit) per FEAT-3583's precedence rule (explicit non-empty context wins over the profile); with non-empty context defaults a profile could never lower a floor. `max_finalists` is clamped to ≤ 8 after resolution, whichever layer set it.
- **Floors**: generation floor `min_ideas` counts post-dedup, on-grid ideas with `grounded != false`; `min_cells` counts distinct on-grid cells among those ideas; finalist floor = at least 2 ids in `finalists`. `finalists` is reduced only by *filtering* steps (`ground_web`, `materialize`). Floors are enforced by `check_floors` at `generation` (after `shortlist`) and `pre_tournament` (after every filter, before `tournament`), and again at `final` in `validate_portfolio` — the same function at every stage.
- **Finalists file** (`${context.run_dir}/finalists.json`, owned here; written by `shortlist`, **rewritten in place by every filtering state**): `{finalists: [id], reserve: {cell_key: [id]}, dropped: {id: reason}, judge_mode: "text" | "image" | "html", assets: {id: {html: path, png: path}}}`. `judge_mode` defaults to `text` and `assets` to `{}` until FEAT-3585 fills them. `eligible` in `portfolio.json` is `finalists` at tournament entry. Filtering states move ids out of `finalists` into `dropped` (reason string) and promote a same-cell id from `reserve`; they never invent ids and never touch `ideas.jsonl` except to set `grounded`/`extra`. The tournament child judges `finalists` only and reads `judge_mode`/`assets` (§ Tournament Specification → Child loop).
- **`portfolio.json`**: `{winner: id, runner_up: id | null, wildcard: id | null, ranking: [id], eligible: [id], flags: {id: [str]}, tie_rate: float, low_confidence: bool, partial: bool}` (`tie_rate`/`low_confidence`/`partial` copied from `tournament.json` so the report and FEAT-3596 read them from one file). `winner` is **always non-null** for a run that reaches `portfolio` (the floors guarantee ≥ 2 finalists); `validate_portfolio` fails a null winner. Runner-up/wildcard are null only when no qualifying candidate exists (recorded in the report). **Slot rules**: winner = first id in `ranking`; runner-up = the next id in `ranking`. Because `shortlist` keeps one finalist per cell, every finalist already occupies a distinct cell, so a different-cell test alone would make the wildcard merely third place. **Wildcard** = the highest-ranked remaining finalist whose cell differs from the winner's on **both** axes; if none exists, fall back to the highest-ranked remaining finalist and add `wildcard_fallback` to that id's `flags`. Later annotate-only features (FEAT-3586) add entries to `flags` and never touch slots. _(2026-09-29: `conceded`, nullable `winner`, and slot recompute after demotion were removed with FEAT-3586's demotion; see Review Decisions 23–24.)_
- **`top_k`**: removed. `winners.md` = the non-null portfolio members (winner, runner-up, wildcard); `sink_decision`/`sink_issue` iterate its lines instead of reading `top_k`.

### Tournament Specification

- **Format**: full **round-robin** over N ≤ `max_finalists` (8) finalists — every pair exactly once, C(N,2) ≤ 28 judge calls (one per pair), plus ≤ 3 probe calls (§ Probe) ≈ 31 calls. Runs as a sub-loop so the parent `max_steps` is unaffected. *Why not Swiss* (the earlier draft): 3 Swiss rounds give each finalist only ~3 comparisons and do not reliably order ranks 2–3, which the runner-up and wildcard slots depend on; and with tie-on-disagree scoring, LLM position bias on close finalists turns into ties, leaving seed order to decide the ranking. Round-robin gives every finalist N−1 comparisons at about the same call count as a two-order Swiss (24), and deletes the pairing algorithm, byes, rematch fallback, and Buchholz. **Cost is quadratic, so `max_finalists` must not be raised above 8** (a profile may lower it, never raise it).
- **Child loop**: `scripts/little_loops/loops/brainstorm-tournament.yaml` (top level, alongside `brainstorm.yaml`; `ll-loop list` uses `rglob`, so it is discoverable and runnable — accepted, and it declares `required_inputs: []` with a `description:` saying it is an internal child of `brainstorm`). The parent state is `loop: brainstorm-tournament` with `with:` bindings for `run_dir` and `brief` (the `with:` branch re-injects the parent `run_dir` via `setdefault`, `executor.py:1186`). Contract: the child reads `${context.run_dir}/finalists.json` (§ Data Contract → Finalists file; it judges the `finalists` list only, never `reserve` or `dropped`, and reads `judge_mode`/`assets` — `text` here; FEAT-3585 adds the `image`/`html` judge states behind that switch without changing the child's inputs or outputs), reads the rubric from `profile.json`, calls the engine module for `build-schedule`, `record-verdict`, and `rank`, **appends every verdict to `tournament.jsonl` as it is judged**, writes `tournament.json`, and **never** re-runs `init` or touches `ideas.jsonl`. The judge prompts interpolate `${context.brief}` and must use the `<<<BRIEF … BRIEF>>>` fence (register in `FENCE_ROLES` under `brainstorm-tournament.yaml`).
- **Budgets** (pinned 2026-09-28): child `max_steps: 100` (a pop + judge state per pair ≈ 2 × 28, plus 3 probe pairs × 2 and ≈ 10 setup/finalize ≈ 72; the verdict-recording step is folded into the next pop). Child `timeout: 2700` with matching state-level `timeout: 2700` on the parent `tournament` state (≈ 31 sequential judge calls ≈ 15–31 min); the child is clamped to the parent's remaining budget (`executor.py:1353-1358`), so the parent `timeout` rises from 3600 to **5400** to keep headroom after up to 9 sequential `diverge` calls.
- **Routing**: `on_yes` → `portfolio`; `on_no` and `on_error` → `finalize_failed`; **`on_timeout`** (`extra_routes["timeout"]`, `executor.py:1434`) → `salvage_tournament`. `salvage_tournament` (script) rebuilds `tournament.json` from the verdicts already in `tournament.jsonl`, counting only **complete rounds** (§ Schedule), with `partial: true` and `low_confidence: true`; fewer than 3 complete rounds → `finalize_failed`. `portfolio` copies `partial` into `portfolio.json`, and the report says the ranking is partial (distinct from `low_confidence` alone).
- **Schedule** (`build_schedule`, deterministic): circle-method round-robin over finalists indexed in **generation order** (idea ID) — never grid order. N even → N−1 rounds of N/2 pairs; N odd → a phantom player is added and its pair skipped (N rounds). Pairs are emitted **in round order**, so every finalist plays once per round and a timeout leaves every finalist with equal games. The schedule fixes the presentation order (`a` = shown first) using standard home/away alternation, so each finalist is shown first in ⌊(N−1)/2⌋ or ⌈(N−1)/2⌉ of its games — position bias is counterbalanced across the field rather than measured per pair.
- **Scoring per pair**: judge picks `a` or `b` → winner 1, loser 0; abstention or malformed vote → 0.5 each, logged in `tournament.jsonl`. Each verdict carries a rubric-based `rationale` so the report can explain the ranking.
- **Probe** (position-sensitivity check): after the round-robin, take the top 3 by the ranking below and re-judge the ≤ 3 head-to-heads among them in the **reversed** presentation order as independent calls (the prompt contains no verdict from the first call). For a probed pair: both orders agree → 1/0; orders disagree or either abstains → 0.5 each (replacing that pair's single-order score). Re-rank once; the probe set is not re-run.
- **Ranking** (`rank`): Copeland score (sum of pair scores) descending; ties → head-to-head result among the tied set (a mini-league over the pairs between tied players; a 2-way tie is decided by their direct result); still tied (a cycle, or all 0.5) → generation order, first-generated first. **Seed/grid order is never a tie-break.**
- **Judge reliability**: `tournament.json` records `tie_rate` = share of *probed* pairs whose two orders disagreed or abstained — a measure of position sensitivity where the podium is decided, not over all pairs. `low_confidence` is true when `tie_rate > 0.5` **or** the winner or runner-up slot was decided by the generation-order fallback; `partial: true` implies `low_confidence`. `portfolio` copies `tie_rate`, `low_confidence`, and `partial` into `portfolio.json` and the report states them. FEAT-3596 reports `tie_rate` (with this definition) in the old-vs-new comparison; measure it there before revisiting the tournament format.
- **`tournament.json`**: `{ranking: [id], scores: {id: float}, tie_rate: float, low_confidence: bool, partial: bool, fallback_decided: bool}`.
- **Wildcard**: per the § Data Contract slot rules (differs from the winner on both axes; fallback flagged).

## Program Design

### Types

All symbols below live in `scripts/little_loops/brainstorm_engine.py` (importable, unit-tested directly) and are exposed through `python3 -m little_loops.brainstorm_engine <command>`.

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, cell: [str, str], off_grid: bool, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `FinalistsFile`: `{finalists: [str], reserve: {str: [str]}, dropped: {str: str}, judge_mode: str, assets: dict}` — § Data Contract → Finalists file
- `PairVerdict`: `{a: str, b: str, winner: str | null, probe: bool, rationale: str}` — `a` is the idea shown first; `winner: null` = abstention; `probe: true` = reversed-order re-judgment of a top-3 head-to-head
- `Portfolio`: see § Data Contract

### Signatures

- `collapse_duplicates(ideas: list[IdeaRecord], groups: list[list[str]]) -> list[IdeaRecord]` — keeps the first-generated member of each duplicate group
- `ingest_ideas(raw: str, ideas: list[IdeaRecord], profile: dict) -> list[IdeaRecord]` — assigns stable IDs, normalizes and validates cells, flags `off_grid`, appends to the run's ideas
- `build_schedule(finalists: list[IdeaRecord]) -> list[tuple[str, str]]` — deterministic circle-method round-robin in round order; each `(a, b)` fixes the presentation order (§ Tournament Specification → Schedule)
- `rank(verdicts: list[PairVerdict], finalists: list[IdeaRecord]) -> list[str]` — idea IDs by Copeland score, then head-to-head, then generation order
- `check_floors(ideas: list[IdeaRecord], finalists: FinalistsFile, profile: dict, stage: str) -> list[str]` — returns the list of violations (empty = pass); `stage` is `generation` | `pre_tournament` | `final`; the CLI exits 1 on any violation. The one function behind both `check_floors` states and `validate_portfolio`
- `validate_portfolio(portfolio: dict, ideas: list[IdeaRecord], finalists: FinalistsFile, profile: dict) -> list[str]` — `check_floors(stage="final")` + reference integrity + non-null winner; exit 1 on violation
- `apply_shortlist(ideas: list[IdeaRecord], picks: dict[str, str], profile: dict) -> FinalistsFile` — script side of `shortlist`: single-idea cells, batched-pick fallback, cap-then-reserve, `grounded == false` exclusion

### Call Path

`init` -> `resolve_profile` -> `frame` -> `reframe` -> `pop_lens` -> `diverge` -> `ingest` (loop over lenses) -> `dedup` -> [`ground_codebase`, FEAT-3584] -> `shortlist` -> `check_floors` (generation) -> [`ground_web`, FEAT-3584] -> [`materialize`, FEAT-3585] -> `check_floors_final` (pre_tournament) -> `tournament` (sub-loop; `on_timeout` -> `salvage_tournament`) -> `portfolio` -> [`premortem`, FEAT-3586] -> `validate_portfolio` -> `route_sink` -> `verify_artifacts` -> `finalize_done`

Bracketed states are added by later children; this issue ships the two `check_floors` states with nothing between them but a no-op pass-through of `finalists.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Anchor-resolvable identifiers today: state names in `scripts/little_loops/loops/brainstorm.yaml` (`frame`, `pop_lens`, `diverge`, `dedup_novelty`, `verify_artifacts`, `route_sink`) and `parse_tagged_json`/`queue_pop` in `scripts/little_loops/loops/lib/common.yaml`. `ingest_ideas`, `build_schedule`, `rank`, `check_floors` do not exist yet. _Superseded 2026-09-29: they are implemented as importable functions in `little_loops/brainstorm_engine.py`, not inline Python in YAML (Review Decision 23)._
- `parse_tagged_json` supplies no default action (`lib/common.yaml` design note: interpolation is single-pass, no nested `${captured.${…}}`); each consuming state writes its own extraction, and the tag today is `IDEAS_JSON:` with keys `text`/`rationale`. The `IdeaRecord` shape (`title`/`body`/`cell`/`cluster`) is a schema change from `text`/`rationale` — `winners.md` consumers still read `text`/`rationale`, so the mapping (`title`→`text`, `body`→`rationale`) must be pinned.

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Decision Rules still unpinned (implementer must fix and document): default values of `min_ideas` and `min_cells`; how many framings `reframe` selects and the tie rule for that selection; the escape hatch, if any, for intentionally small runs (e.g. a profile that lowers the minimums — FEAT-3583 consumes this). _Resolved 2026-09-25 (Astra review): floors count post-dedup on-grid ideas (§ Data Contract); bracket is Swiss with disagreeing orders scored as a tie (§ Tournament Specification)._ _Superseded 2026-09-28 (second-opinion review): the format is now a round-robin (Review Decisions 15–16); `reframe` selects the top 3 by an LLM-emitted score, ties by generation order (Expected Behavior 1)._

## Integration Map

### Behavior Parity

Behaviors of `scripts/little_loops/loops/brainstorm.yaml` and their disposition:

| Artifact | Behavior | Disposition |
|----------|----------|-------------|
| `scripts/little_loops/loops/brainstorm.yaml` | `frame` selects lenses; `pop_lens` queues them | preserved (lens queue feeds `diverge`; `reframe` added before it) |
| `scripts/little_loops/loops/brainstorm.yaml` | `diverge` generates `ideas_per_round` ideas per lens | changed — sees running idea titles and per-cell occupancy (`diverge_state.md`) and tags a two-value `cell` from the profile's axis bins; a new per-lens `ingest` state assigns IDs and flags off-grid (per-idea `IdeaRecord` in `ideas.jsonl`) |
| `scripts/little_loops/loops/brainstorm.yaml` | `dedup_novelty` difflib dedup at `novelty_threshold` | dropped — replaced by `dedup`: an LLM pass over `{id, title, body excerpt}` emits duplicate groups, a script collapses each group to its first-generated member (per-cell representative selection is the separate `shortlist` step) |
| `scripts/little_loops/loops/brainstorm.yaml` | `saturation_gate` early exit after `max_saturation` zero-novel rounds | dropped — never fired in observed runs |
| `scripts/little_loops/loops/brainstorm.yaml` | `cluster` / `rank` single listwise LLM passes | changed — per-cell `shortlist`, a `check_floors` gate, then a round-robin pairwise `tournament` |
| `scripts/little_loops/loops/brainstorm.yaml` | `converge` synthesizes best-of hybrid | changed — `portfolio`; hybrid only when `synthesize=true` |
| `scripts/little_loops/loops/brainstorm.yaml` | `route_sink` + `sink_file`/`sink_issue`/`sink_decision` contract | preserved — sinks read `winners` from the portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` (a failing run can already create issues/decisions) | changed — `validate_portfolio` gates `route_sink`; no sink fires on an invalid run |
| `scripts/little_loops/loops/brainstorm.yaml` | `verify_artifacts` requires non-empty `brainstorm.md` | changed — also requires `min_ideas` and `min_cells` |
| `scripts/little_loops/loops/brainstorm.yaml` | `on_handoff: spawn`, `scope`, artifacts under `${context.run_dir}` | preserved |

### Files to Modify
- `scripts/little_loops/brainstorm_engine.py` — **new** module holding all deterministic engine logic (§ Program Design); `docs/reference/API.md` gains a `little_loops.brainstorm_engine` section (docs audience: cite the module, not `scripts/` paths)
- `scripts/little_loops/loops/brainstorm.yaml` — replace `frame`/`diverge`/`dedup_novelty`/`saturation_gate`/`cluster`/`rank`/`converge` with the new state graph (adds `ingest`, `check_floors` ×2, `salvage_tournament`), each script state a one-line engine-module call; tighten `verify_artifacts`; rewrite the `finalize_*` prompts; raise `timeout` to 5400; update `description:` and `context:` keys
- `scripts/little_loops/loops/brainstorm-tournament.yaml` — **new** child loop (round-robin tournament; see § Tournament Specification → Child loop); add to `test_builtin_loops.py` built-in set, `scripts/little_loops/loops/README.md`, and the `README.md` loop count (mirror `scripts/README.md`)
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entries for `reframe` and the child's judge states

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `parse_tagged_json` / `queue_pop` — fragments to reuse for tagged-JSON extraction and lens/framing queues

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests (state graph, routing, wiring: each script state invokes `little_loops.brainstorm_engine`, and both `check_floors` states plus `validate_portfolio` pass a `--stage`)
- `scripts/tests/test_brainstorm_engine.py` — **new**; direct unit tests of the engine functions (no YAML extraction, no `_bash`)
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New engine unit tests: duplicate-group collapse (3 fixtures in § Acceptance Criteria) plus malformed-group fail-open, off-grid flagging and case/whitespace normalization, cap-selection at 9 occupied cells, wildcard slot rule and fallback, `reframe` top-3 selection with tie-break, `ingest` ID assignment and `diverge_state.md` regeneration, `build_schedule` (every pair exactly once, every finalist once per round, first-position counts differ by ≤ 1, N odd/even, deterministic), `rank` (Copeland, head-to-head tie-break, 3-cycle → generation-order fallback, never grid order), probe rescoring (agree → 1/0, disagree → 0.5) and `tie_rate`/`low_confidence`, abstention scoring, `salvage_tournament` (≥ 3 complete rounds → partial ranking; fewer → failed), `check_floors` at all three stages (`generation`, `pre_tournament`, `final`) including a fixture where `finalists.json` shrinks below 2 between stages, `grounded: false` ideas excluded from `min_ideas`/`min_cells`/`shortlist`, cap-then-reserve ordering, `finalists.json` rewrite invariants (ids only move `finalists`→`dropped`, reserve promotion stays in-cell), null-winner rejected by `validate_portfolio`, dedup paraphrase-relabeled-into-empty-cell fixture

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions
- `README.md` — brainstorm mention (verify wording only)

### Configuration
- Context keys: add `mode` (default `artifact`), `min_ideas`, `min_cells`, `max_finalists` (all default `""` = inherit from the profile; the pinned numbers `12`/`4`/`8` live in the `artifact` profile — see § Data Contract), `synthesize`; change the existing `ideas_per_round` default from `"5"` to `""` (inherit; the profile carries `5`) so it does not silently beat profile values; remove `novelty_threshold`, `max_saturation`, `novelty_backend`, `top_k`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Fence registry: `scripts/little_loops/fsm/fence.py` `FENCE_ROLES` keys `("brainstorm.yaml", "frame")` and `("brainstorm.yaml", "diverge")` require the `<<<BRIEF … BRIEF>>>` fence in those prompt states; `KNOWN_UNFENCED_PROMPT_SITES` exempts `converge` and `finalize_done`. Any new state whose prompt interpolates `${context.brief}` (e.g. `reframe`, tournament judge) must be added to `FENCE_ROLES`, and a removed exempt state (`converge`) must leave `KNOWN_UNFENCED_PROMPT_SITES` — the fence completeness guard fails otherwise.
- Interpolation baseline: `scripts/tests/data/loop_interpolation_baseline.json` carries a `loops/brainstorm.yaml` / `dedup_novelty` / `context.run_dir` heredoc entry; deleting `dedup_novelty` and adding new heredoc scripts changes that baseline and it must be regenerated or updated in the same change.
- MR-11 (`ll-loop validate`): LLM output (`${captured.*}`) reaching a Python body must use the heredoc-to-file or `LL_ARG_` env-hoist idioms (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` MR-11); the current `dedup_novelty` writes `round_ideas.txt` via quoted heredoc and passes thresholds via `LL_ARG_NOVELTY_THRESHOLD=${context.novelty_threshold:shell}`. New dedup/bracket/tally scripts must not embed captured text in Python literals.
- Existing tests that assert removed behavior and must be rewritten, not merely kept green: `scripts/tests/test_brainstorm.py` `test_saturation_gate_uses_output_numeric`, `test_saturation_gate_routes_correctly`, `test_dedup_novelty_uses_exit_code_evaluator`, `test_dedup_novelty_action_contains_difflib`, `test_cluster_and_rank_route_to_failed_on_error`, `test_required_states_exist`, `test_context_has_required_knobs`, `test_context_defaults`, `test_init_seeds_required_files` (asserts `saturation.txt`), and `TestPopLensEmptyQueue` (must keep passing — `pop_lens` is preserved). `scripts/tests/test_bug_2816_cli_invocations.py` asserts `sink_decision` has no `set-flag` and must keep passing; `test_builtin_loops.py` lists `brainstorm` in a built-in set (line ~293).
- Contract that must hold: `lenses.txt` is written by `frame` and consumed by `pop_lens` (exit 1 = queue empty, exit 2 = file missing); `pop_lens` `on_no` currently routes to `cluster` — the re-routed target (dedup/shortlist/tournament chain) must keep the empty-queue path reachable and the missing-file path failing. `sink_*` states read `winners.md` (JSON lines with `text`/`rationale`); the portfolio must keep emitting that file with those keys (plus new fields is fine) so `sink_issue`/`sink_decision` need no change. `finalize_done`/`finalize_failed` prompts name `ranked.md`/`clusters.md`/`saturation` artifacts that will no longer exist and must be updated.
- Sibling coupling: `interactive-component-generator.yaml:92` only mentions `brainstorm` in a comment (no runtime dependency).

### Wiring Additions

_Wiring pass added by `/ll:wire-issue`:_

**Files to Modify**
- `CHANGELOG.md` — breaking-change entry (dropped `novelty_threshold`/`max_saturation`/`novelty_backend`, portfolio output shape) under a concrete `## [X.Y.Z]` heading, not `[Unreleased]` [Agent 1]
- `README.md:131` + `scripts/README.md:131` — `ll-loop run brainstorm ... # multi-lens ideation → ranked brainstorm.md` wording now stale (portfolio + grid map); mirror with `command cp -f README.md scripts/README.md` [Agent 1, Agent 2]

**Dependent Files (Callers/Importers)**
- `docs/development/TROUBLESHOOTING.md:~418` (`--host-guard-budget-mb` example) and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:~761,778` — mention `brainstorm` only; verify wording, no change expected [Agent 1]
- No loop, skill, command, or Python module consumes `winners.md`/`ideas.jsonl`/`brainstorm.md`; readers are `sink_*`, `finalize_*`, `verify_artifacts` inside the loop only [Agent 2]

**Tests**
- `scripts/tests/test_builtin_loops.py` — `_FENCE_LOOP_INPUT_VARS["brainstorm.yaml"]`/`TestBriefFencing`, `test_brainstorm_data_sink_heredoc_is_not_a_site` (asserts `captured.round_ideas.output` is not a site; goes vacuous if the capture is renamed), exact-set `MR11_MARKER_ALLOWLIST` (two brainstorm rows, ENH-3358), and `TestValidatorWarningBudget` (brainstorm has no allowlist entry, so any new partial-route/capture-ordering/unsafe-context-interp/shared-tmp warning fails) [Agent 3, Agent 2]
- `scripts/tests/test_brainstorm.py` — beyond the tests already listed: `TestBrainstormDedup._run_dedup` (inline difflib script copy, delete), `TestBug2468ErrorRouting` (`_dedup_action`/`_verify_action`, `test_all_success_paths_route_through_verify_artifacts`), `TestBrainstormDryRun` (`test_all_states_reachable`, `test_no_ratcheted_category_warnings`, `test_required_inputs_declared`), `test_route_sink_has_all_branches`; `TestBug2468ErrorRouting.test_all_success_paths_route_through_verify_artifacts` conflicts with `validate_portfolio` gating the sinks and must be rewritten [Agent 3]
- ~~New tests should follow Pattern A (`_bash` against actions extracted from the YAML)~~ — superseded 2026-09-29: logic tests are direct imports of `little_loops.brainstorm_engine` (`test_brainstorm_engine.py`); YAML tests assert only wiring (the module call, `--stage` argument, routing). Existing `_bash`-style tests for preserved states (`pop_lens`, sinks) are unchanged [Agent 3]

**Configuration / validator constraints**
- `scripts/tests/data/loop_interpolation_baseline.json` — regenerate for removed `dedup_novelty` and new heredoc states [Agent 2]
- Validator rules the new states must satisfy: MR-10 parse-swallow (`json.loads`+`except`+`sys.exit(0)` without `on_error` warns — keep exit-2 crash contract), abstention route (an `llm_structured` pair judge needs `on_error`/`cannot_judge`), classify `default:` route, capture reachability/dominance for new `${captured.*}` [Agent 2]
- **Step budget** (re-pinned 2026-09-28): fixed parent states ≈ 13 (incl. `resolve_profile`) + 2 `check_floors` (generation + pre_tournament) + (L+1) `pop_lens` (the final pop returns the empty-queue exit) + L `diverge` + L `ingest` (L ≤ 9 → 28) + 1 for the `tournament` sub-loop ≈ **44**, under `max_steps: 60`, so `test_max_steps_is_60` stays valid for the core (`salvage_tournament` adds 1 only on the timeout path). The occupancy/title render is folded into `ingest` (it rewrites `diverge_state.md`); a separate per-lens render state would cost 9 more (≈ 52) — do not add one. Framing×lens is **not** a cross product (round-robin), and the tournament's ~31 judge calls live in the child loop's own budget (`max_steps: 100`). The combined all-features budget (ground + materialize + premortem) is owned by FEAT-3596.

## Implementation Steps

1. Define the idea record schema and grid-cell tagging contract.
2. Rewrite states per Expected Behavior; reuse `lib/common.yaml` fragments
   (`parse_tagged_json`, `queue_pop`).
3. Write `scripts/little_loops/brainstorm_engine.py` first (ingest, collapse, shortlist-apply, `check_floors(stage)`, schedule/rank/salvage, portfolio, validate) with `test_brainstorm_engine.py`, TDD; the YAML states are then one-line `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine …` calls. `check_floors` and `validate_portfolio` call the same function. Confirm the `-m` invocation resolves in a consuming project the way `autodev.yaml` `python3 -m little_loops.autodev_summary` does (`LL_PYTHON` override honored).
4. Tighten `verify_artifacts`; rewrite the `finalize_*` prompts (drop `ranked.md`/`clusters.md`/saturation references).
5. Update tests and the loop's description/docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Budget pinned (see Review Decisions); keep `test_max_steps_is_60` valid, add a test asserting the child tournament loop's `max_steps: 100`/`timeout: 2700`, the parent `timeout: 5400`, that the parent reaches the child via a `loop:` state, and that its `on_timeout` route reaches `salvage_tournament`
- Verify the child tournament loop's placement against loop discovery scanners and `ll-verify-package-data`
- Drop `top_k` from context and from `sink_decision`/`sink_issue` prompts; update `test_context_*` tests (floor/`max_finalists` knobs assert `""`, not the numbers)
- Wire `check_floors` twice (`generation` after `shortlist`, `pre_tournament` immediately before `tournament`); `shortlist` writes `finalists.json` per § Data Contract
- Add `little_loops.brainstorm_engine` to `docs/reference/API.md`; verify `ll-verify-package-data` (module ships with the package, no manifest edit expected)
- Update `scripts/tests/test_builtin_loops.py` fence/MR-11/heredoc-site/warning-budget assertions and `scripts/tests/data/loop_interpolation_baseline.json`
- Add `reframe`/tournament-judge states to `fence.py` `FENCE_ROLES`; drop `converge` from `KNOWN_UNFENCED_PROMPT_SITES`
- Update `README.md:131` and mirror to `scripts/README.md`; add `CHANGELOG.md` entry under a concrete version
- Test engine logic by direct import (`test_brainstorm_engine.py`); YAML tests assert wiring only

## Impact

- **Priority**: P2 - core engine that FEAT-3583..3586 all depend on
- **Effort**: Medium - rewrites most states of one 459-line loop YAML, but reuses `lib/common.yaml` fragments and existing sinks
- **Risk**: Medium - replaces the loop's core behavior; mitigated by `ll-loop validate brainstorm` and updated tests
- **Breaking Change**: Yes - drops the `novelty_threshold`, `max_saturation`, and `novelty_backend` context keys and changes `brainstorm.md` shape from best-of hybrid to portfolio

## Acceptance Criteria

- difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, and
  `saturation.txt` are removed.
- A run with 0 ideas (e.g. forced empty diverge) routes to `failed`.
- `validate_portfolio` runs before `route_sink`; fixtures for zero survivors,
  insufficient cells, fewer than 2 eligible finalists, and a null winner each route to
  `failed` with no sink executed.
- `check_floors` runs at `generation` (after `shortlist`) and `pre_tournament`
  (after every filtering state, immediately before `tournament`): fixtures for zero
  ideas, insufficient cells, and fewer than 2 finalists route to `finalize_failed`
  before any judge call, including a fixture where `finalists.json` drops below 2
  *between* the two stages; the tournament child never runs with fewer than 2 finalists.
- `finalists.json` matches § Data Contract → Finalists file; only `finalists` is judged;
  ids move `finalists` → `dropped` and never appear in both.
- Floor and `max_finalists` context keys default to `""`; a profile value lower than the
  `artifact` default takes effect, and an explicit context value beats the profile
  (`max_finalists` clamped ≤ 8).
- All deterministic logic is importable from `little_loops.brainstorm_engine` and unit-tested
  without extracting YAML actions; `brainstorm.yaml` script states are thin module calls.
- Tournament schedule construction and ranking are deterministic shell/Python; only
  individual pair verdicts are LLM calls; the round-robin covers every finalist pair
  exactly once, with presentation order counterbalanced (first-position counts differ
  by ≤ 1); the top-3 head-to-heads are re-judged in reversed order by independent
  calls; every verdict carries a `rationale`.
- Round-robin schedule, Copeland ranking, head-to-head tie-break, generation-order
  fallback (never grid order), probe rescoring, and abstention scoring are covered by
  deterministic tests.
- A tournament timeout routes to `salvage_tournament`: ≥ 3 complete rounds yield a
  `partial: true`, `low_confidence: true` portfolio; fewer route to `finalize_failed`.
- Off-grid cell values are flagged (after case/whitespace normalization) and excluded from `min_ideas`, `min_cells`, and `shortlist`.
- Malformed dedup output (unknown IDs, overlapping groups, unparseable text) never drops ideas.
- `portfolio.json` has a non-null `winner` and no `conceded` field; it carries `tie_rate`, `low_confidence`, and `partial`; `winners.md` lines carry a `role`; the report states the off-grid share; the wildcard differs from the winner on both axes or is flagged `wildcard_fallback`.
- The tournament child `brainstorm-tournament.yaml` has `max_steps: 100` and `timeout: 2700`, is reached via a `loop:` state, and a child failure routes to `finalize_failed`; the parent `timeout` is 5400.
- Output `brainstorm.md` presents a portfolio + the grid map; `portfolio.json` is
  written for every run; `ideas.jsonl` records `id`, `cell`, `framing`, `lens` per
  idea.
- `ll-loop validate brainstorm` passes; artifacts only under `${context.run_dir}/`.
- Existing brainstorm tests updated; new dedup fixtures cover: distinct ideas that
  share a cell (both kept), paraphrases in different cells (collapsed), and a
  concise representative kept over a longer duplicate (first-generated wins), a
  paraphrase relabeled into an empty cell (collapsed via the body excerpt), and two ideas
  that share a framing but differ in mechanism (both kept).

## Review Decisions

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

1. **Tournament as a sub-loop** — pairwise judging needs ~31 calls (8 finalists, round-robin + probe); as parent states it would blow `max_steps: 60`. `loop:` states run a child executor and cost the parent one step (`executor.py:_execute_sub_loop`). Finalists capped at 8 (quadratic cost — never raised).
2. **Round-robin framings** — one `diverge` per lens with a rotating framing, not F×L calls; keeps old-loop cost and keeps the core budget at ≈ 44 parent steps (re-pinned, items 19 and 25).
3. **`top_k` removed** — `winners.md` = portfolio members; sinks iterate lines.
4. **`shortlist` resolved** — script for single-idea cells, one batched LLM pick for multi-idea cells, first-generated fallback.
5. **`portfolio.json` nullability + recompute rule** — _superseded 2026-09-29 (item 24): `winner` is never null; no post-`portfolio` recompute._
6. **Occupancy-aware `diverge`** — per-cell counts fed into the prompt so the grid steers generation rather than only tagging it.
7. **Defaults pinned** — `min_ideas: 12`, `min_cells: 4`, 3 framings, `max_finalists: 8`.
8. **`resolve_profile` + `profile.json` schema move here** (with the `artifact` profile) so FEAT-3583 does not rewrite `diverge`/`reframe`/`tournament` prompts a second time.
9. **Judge reliability** — `tie_rate` recorded (over probe pairs since item 16); `low_confidence` above 0.5.

10. **Wildcard redefined** — finalists occupy distinct cells, so the different-cell rule was vacuous; wildcard now differs from the winner on both axes (fallback flagged). FEAT-3586 recompute reuses these slot rules.
11. **Swiss pairing pinned** — _superseded by item 15._
12. **Cap rule** — over-cap cells: drop lowest-occupancy first, ties by later grid order.
13. **Eligible floor vs concession** — _superseded 2026-09-29 (item 24): no concession exists._
14. **Child loop named** — `brainstorm-tournament.yaml`, `with:` bindings, `timeout: 1800` (raised to 2700, item 18), failure → `finalize_failed`; off-grid normalization and dedup fail-open added.

_Added 2026-09-28 (second-opinion review, `/ll:advise` with Opus; nothing here has been measured):_

15. **Round-robin replaces Swiss** — 3 Swiss rounds over ≤ 8 finalists give ~3 comparisons each, do not order ranks 2–3 reliably (runner-up and wildcard depend on them), and tie-on-disagree turns position bias into ties so seed order decides. Round-robin: every finalist gets N−1 comparisons at ≈ Swiss's call count, with no pairing algorithm, byes, rematch handling, or Buchholz. Ranking = Copeland → head-to-head → generation order, **never grid/seed order** (grid order systematically favored low-index bins). Dissent recorded: if the judge proves order-consistent, Swiss + two orders would have been defensible; a cheaper middle path was Swiss with head-to-head + a decider call. Round-robin was preferred for simplicity and for ranking quality where slots are decided.
16. **Position bias: counterbalance, then probe** — one call per pair with presentation order counterbalanced across the field; only the top-3 head-to-heads are re-judged reversed. `tie_rate` therefore measures position sensitivity on the podium, and FEAT-3596 should measure it before any further format change.
17. **`check_floors` before `tournament`** — a doomed run (0 ideas, 1 finalist) must not spend judge calls or reach a 0/1-player tournament; one floor body is shared with `validate_portfolio`.
18. **Timeout headroom + salvage** — child `2700`, parent `5400`; a tournament `on_timeout` rebuilds a `partial` ranking from complete rounds (schedule is round-ordered so every finalist has equal games) instead of discarding them.
19. **Step budget re-pinned** — the per-lens `ingest` state (IDs, cell normalization, `diverge_state.md`) was uncounted; core ≈ 43 (was ≈ 32/33, an inconsistent pair); 2026-09-29 the second `check_floors` stage makes it ≈ 44. Render is folded into `ingest`.
20. **`reframe` scoring pinned** — LLM emits a 1–5 score per framing; script takes the top 3, ties by generation order.
21. **Dedup sees a body excerpt** — title-only dedup plus occupancy steering lets paraphrases be relabeled into empty cells, inflating `min_cells` and the finalist count.
22. **Minor** — off-grid share reported; `winners.md` lines carry `role`; runner-up "from a different cell" dropped from the Use Case (true by construction); `finalize_*` prompt rewrites are an explicit step.

_Added 2026-09-29 (EPIC-3581 second review, `/ll:advise` with Opus; nothing here has been measured):_

23. **Engine as a module, not inline YAML** — `scripts/little_loops/brainstorm_engine.py` holds ingest, collapse, shortlist, schedule, rank, salvage, portfolio, floors, validation (and, later, profile resolution, probes, annotation). YAML states are thin `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <cmd>` calls (precedent: `autodev.yaml` → `little_loops.autodev_summary`). Removes the "shared script body" problem, most MR-11/`$${}` escaping and interpolation-baseline churn, and makes the Program Design signatures real, directly unit-testable symbols. Dissent recorded: logic no longer reads inline in `ll-loop show`; prompts stay in YAML.
24. **FEAT-3586 becomes annotate-only for v1** — nullable `winner`, `conceded`, the all-conceded validate path, the sink-skip branch, and post-`portfolio` slot recompute are removed from this contract. A P4 optional finisher should not add nullable-winner complexity to the P2 core before it is proven; a same-model defender supplies a mitigation almost every time, so script-determined concession rarely fired anyway. If demotion returns, it re-adds these fields in a follow-up with a concession signal that does not come from the defender.
25. **Floor gate re-run after filtering states** — `check_floors` runs at `generation` (after `shortlist`) and `pre_tournament` (after `ground_web`/`materialize`, before `tournament`); `validate_portfolio` runs `final`. FEAT-3584's "floor rechecked in `validate_portfolio`" would have allowed a 0/1-player tournament, contradicting item 17.
26. **`finalists.json` is a filter-pipeline contract** — `{finalists, reserve, dropped, judge_mode, assets}`, rewritten in place by every filtering state; the tournament judges only `finalists`. Order pinned: `dedup → ground_codebase → shortlist → check_floors(generation) → ground_web → materialize → check_floors(pre_tournament) → tournament`. `shortlist` excludes `grounded: false`, caps first, then fills `reserve`; floors count `grounded != false` ideas.
27. **Floor and knob defaults live in the profile** — context keys `min_ideas`/`min_cells`/`max_finalists` default to `""`; with non-empty context defaults FEAT-3583's "non-empty context overrides the profile" rule made every profile floor unlowerable.

The two Confidence Check concerns below (unpinned defaults, `max_steps`) are resolved by items 2, 7, and 19; re-run `/ll:confidence-check` — the scores below predate the round-robin rewrite (items 15–22) and the 2026-09-29 contract changes (items 23–27).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29 (re-scored against the round-robin rewrite, Review Decisions 15–22)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Scores re-verified against the round-robin rewrite; unchanged from the prior pass.
- Prior concerns resolved: child loop named (`brainstorm-tournament.yaml`, § Tournament Specification → Child loop) and `eligible` vs premortem concession pinned (§ Data Contract).
- Program Design, dependency, claim, and learning-test gates are all clean.

### Outcome Risk Factors
- **Complexity (5/25)**: rewrites most of a 459-line loop, adds a new child loop, and touches fence registry, interpolation baseline, README counts, and ~10 existing tests — expect iteration on validator warnings (MR-10/MR-11, warning budget).
- **Change surface (18/25)**: the `context:` key removals and `winners.md` schema mapping ripple into sinks, docs, and FEAT-3583..3586.
- **Ambiguity (22/25)**: judge rubric wording and the `reframe`/`diverge` prompt text are still left to the implementer.


## Session Log
- `/ll:confidence-check` - 2026-09-29T06:02:09 - `1e4b6b11-acbb-4e78-b169-131d9cd93116.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:38:55 - `6ac2993c-0f5a-489a-b5b9-4d778beaf475.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:07:51 - `a043a653-a6de-455c-af91-864f254d2405.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:46 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:38 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:30 - `fa11583b-aa00-4da8-b0f0-fc89c6cf8f64.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:44 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:47:12 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:36 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
