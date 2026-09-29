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

1. `reframe` — generate N problem framings ("How might we…"), select 2–3 (skippable
   per profile).
2. `diverge` once per lens, with framings assigned round-robin across lenses (L
   calls, not F×L) — prompt includes the running list of idea titles **and the
   current per-cell occupancy**, and instructs the model to favor empty or
   under-filled cells. Each idea is emitted with a grid cell whose two values must
   come from the profile's enumerated axis bins. A script assigns stable IDs, normalizes each
   cell value (strip + casefold, then map to the canonical bin spelling), and rejects
   (flags `off_grid`) any value that still matches no bin. Off-grid ideas stay in
   `ideas.jsonl` with `off_grid: true` but are excluded from
   `shortlist`, `min_ideas`, and `min_cells`.
3. `dedup` — one cheap LLM pass over titles only emits duplicate groups by idea ID;
   a script collapses each group, keeping the **first-generated** idea as
   representative (never "longest body"). The collapse **fails open**: unknown IDs are
   ignored, an ID appearing in more than one group stays in the first group only, groups
   with fewer than 2 valid members are ignored, and unparseable output skips dedup
   entirely (logged to `dedup.log`) — malformed output never drops ideas.
4. `shortlist` — one representative per occupied cell. Single-idea cells are
   taken by the script; all multi-idea cells are resolved in **one batched LLM
   call** (a pick per cell). A malformed or missing pick falls back to the
   first-generated idea in that cell. When more than `max_finalists` cells are
   occupied (a 3×3 grid can have 9), drop the lowest-occupancy cell(s) until the cap is
   met (ties: drop the later cell in grid order); dropped cells are listed in
   `shortlist.json` and the report.
5. `tournament` — Swiss format, script-built and script-tallied, run as a
   **sub-loop** (one parent step); each pair is judged in two independent LLM
   calls (one per position order). See § Tournament Specification.
6. `portfolio` — script writes canonical `portfolio.json` (winner, runner-up, wildcard — see § Data Contract for the slot rules) and `winners.md` (the non-null portfolio members, in
   that order; `top_k` is removed); hybrid only when `synthesize=true`.
7. `validate_portfolio` (script, **before any sink**) — fail when post-dedup idea
   count < `min_ideas`, occupied cells < `min_cells`, eligible finalists < 2, or
   winner/runner-up/wildcard IDs do not resolve in `ideas.jsonl`.
8. `verify_artifacts` — remains after sinks as a report-integrity check.

Sinks (`none|file|issue|decision`) keep their contract and read `winners` from the
portfolio. No sink executes unless `validate_portfolio` passed.

## Use Case

**Who**: A little-loops user running `ll-loop run brainstorm "<brief>"` to explore options for a naming, design, or product question.

**Context**: Today every run is 9 lenses × 5 ideas, dedup never fires, and the output is a single Frankenstein hybrid; a run can even "succeed" with zero ideas.

**Goal**: Get a diverse, de-duplicated set of ideas ranked by structured pairwise judgment.

**Outcome**: `brainstorm.md` presents a portfolio (winner, runner-up from a different grid cell, wildcard) plus the grid map, and the run fails loudly if too few ideas or cells were produced.

## Motivation

The 4 historical `brainstorm-*` runs (see EPIC-3581 § Motivation) show the current core is inert where it matters:

- Dedup/saturation never fire: max pairwise difflib ratio was 0.44 vs the 0.55 threshold across 45 ideas, and `saturation.txt` stayed 0 in all runs.
- `diverge` never sees prior ideas, so there is no cross-lens anti-anchoring.
- `cluster`/`rank`/`converge` are single listwise LLM passes (`converge` read ~319k input tokens in one run) and always force a hybrid.
- A zero-idea run passes `verify_artifacts` because it only checks `brainstorm.md` is non-empty.

This feature is the core (C + B + A) that every other EPIC-3581 child builds on.

## Proposed Solution

Rewrite the state graph in `scripts/little_loops/loops/brainstorm.yaml` (keep `init`, sinks, `finalize_*`, `on_handoff: spawn`):

1. `reframe` — LLM emits N "How might we…" framings; a script selects 2–3.
2. `diverge` — one call per lens (framing assigned round-robin; `lenses.txt` lines pair `framing|lens`); prompt carries the running list of idea titles and per-cell occupancy and asks for empty/under-filled cells; each idea is emitted as a tagged JSON line with `cell` (2 values, each from the profile's axis bins). A script assigns IDs and flags off-grid cells; off-grid ideas do not count toward `min_cells`.
3. `dedup` — an LLM pass over `{id, title}` pairs only emits duplicate groups (`DUP_GROUPS_JSON:`); a Python heredoc collapses each group to its first-generated member. Duplicate detection and per-cell representative selection are separate steps.
4. `shortlist` — script takes single-idea cells; one batched LLM call picks a representative for every multi-idea cell (fallback: first-generated). Cap at `max_finalists` (lowest-occupancy cell dropped first; see Expected Behavior 4); writes `finalists.json` for the tournament child.
5. `tournament` — a sub-loop state (`loop:`; the child runs its own executor and `max_steps`, so the parent spends one step). Swiss bracket per § Tournament Specification; script builds pairings, two independent judge calls per pair (order `ab`, then order `ba`, neither sees the other), script tallies. The child is `brainstorm-tournament.yaml` (see § Tournament Specification → Child loop); verify it against `ll-loop list`, `ll-verify-package-data`, and the built-in loop count in `README.md`.
6. `portfolio` — script writes `portfolio.json` (the one canonical portfolio format) and `winners.md`; hybrid only when `synthesize=true`. A profile's `output_shape` affects only how `brainstorm.md` is rendered, never `portfolio.json`.
7. `resolve_profile` (script, after `init`) — owned here so FEAT-3583 only adds presets and the classifier: reads the profile named by context `mode` (default `artifact` until FEAT-3583 flips it to `auto`), validates it, writes `${context.run_dir}/profile.json`. Ships with the built-in `artifact` profile only. Every later state reads resolved values from `profile.json`; no state hardcodes profile behavior.
8. `validate_portfolio` — gate before `route_sink`; enforces generation and finalist floors (§ Data Contract) and winner-reference integrity. Fails to `finalize_failed` with no sink executed.
9. `verify_artifacts` — report-integrity check after sinks.

Reuse `parse_tagged_json` and `queue_pop` from `lib/common.yaml`. Remove difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, `saturation.txt`.

### Data Contract

Owned by this issue; FEAT-3583..3586 extend it, never redefine it.

- **Idea IDs**: script-assigned (`i001`, `i002`, … in generation order), stable for the run; the LLM never invents IDs.
- **Common fields** (every profile): `id`, `title`, `body`, `framing`, `lens`, `cell`, `off_grid`. Profile-specific fields live under an `extra: {}` object.
- **Legacy mapping** for `winners.md` / sinks: `title`→`text`, `body`→`rationale` (both keys written).
- **Cell vocabulary**: each profile declares `axes: [{name, bins: [str, …]}, {name, bins: [str, …]}]` (FEAT-3583). A cell is valid only if both values are in the bins. The core ships a default 3×3 grid for runs without a profile.
- **Floor defaults** (pinned 2026-09-28; a profile may lower them): `min_ideas: 12`, `min_cells: 4` (default 3×3 grid), framings selected by `reframe`: 3 (ties broken by generation order), `max_finalists: 8`.
- **Floors**: generation floor `min_ideas` counts post-dedup, on-grid ideas; `min_cells` counts distinct on-grid cells; finalist floor = at least 2 finalists in `eligible`. `eligible` is reduced only by *filtering* steps (ground, materialize); it is **never reduced by premortem concession** — a conceded finalist stays in `eligible` and is also listed in `conceded`, so FEAT-3586's all-conceded outcome (`winner: null`, `conceded == eligible`) is valid and not a floor violation. Floors are rechecked in `validate_portfolio`, not only after `diverge`.
- **`portfolio.json`**: `{winner: id | null, runner_up: id | null, wildcard: id | null, ranking: [id], eligible: [id], conceded: [id], flags: {id: [str]}, tie_rate: float, low_confidence: bool}` (`tie_rate`/`low_confidence` copied from `tournament.json` so the report and FEAT-3596 read them from one file). `winner` is non-null for every run that reaches `portfolio`; it becomes null **only** when FEAT-3586 concedes every finalist (`conceded` then equals `eligible`). Runner-up/wildcard are null only when no qualifying candidate exists (recorded in the report). **Slot rules** (used by `portfolio` and by any post-`portfolio` rewrite such as FEAT-3586 demotion): winner = first non-conceded id in `ranking`; runner-up = next non-conceded id in `ranking`. Because `shortlist` keeps one finalist per cell, every finalist already occupies a distinct cell, so a different-cell test alone would make the wildcard merely third place. **Wildcard** = the highest-ranked remaining non-conceded finalist whose cell differs from the winner's on **both** axes; if none exists, fall back to the highest-ranked remaining non-conceded finalist and add `wildcard_fallback` to that id's `flags`. Recompute always applies these same rules.
- **`top_k`**: removed. `winners.md` = the non-null portfolio members (winner, runner-up, wildcard); `sink_decision`/`sink_issue` iterate its lines instead of reading `top_k`.

### Tournament Specification

- **Format**: Swiss, `ceil(log2 N)` rounds (minimum 1) over N ≤ `max_finalists` (8) finalists — at most 3 rounds × 4 pairs × 2 orders = 24 judge calls. Runs as a sub-loop so the parent `max_steps` is unaffected; the child sets its own `max_steps` (worst case ≈ 3 rounds × (8 judge + 2 bookkeeping) + setup ≈ 40; pin 60).
- **Child loop**: `scripts/little_loops/loops/brainstorm-tournament.yaml` (top level, alongside `brainstorm.yaml`; `ll-loop list` uses `rglob`, so it is discoverable and runnable — accepted, and it declares `required_inputs: []` with a `description:` saying it is an internal child of `brainstorm`). The parent state is `loop: brainstorm-tournament` with `with:` bindings for `run_dir` and `brief` (the `with:` branch re-injects the parent `run_dir` via `setdefault`, `executor.py:1186`). Contract: the child reads `${context.run_dir}/finalists.json` (written by `shortlist`), reads the rubric from `profile.json`, appends `tournament.jsonl`, writes `tournament.json`, and **never** re-runs `init` or touches `ideas.jsonl`. Child `timeout: 1800` and matching state-level `timeout: 1800` on the parent `tournament` state (the child inherits the parent's remaining budget; ≈24 sequential judge calls ≈ 12–24 min wall-clock). Parent routing: `on_yes` → `portfolio`; `on_no` and `on_error` → `finalize_failed`. The judge prompts interpolate `${context.brief}` and must use the `<<<BRIEF … BRIEF>>>` fence (register in `FENCE_ROLES` under `brainstorm-tournament.yaml`).
- **Swiss pairing** (`build_bracket`, deterministic): (1) if N is odd, the lowest-seeded player without a prior bye gets the bye (removed before pairing); (2) sort remaining players by points descending, then seed; (3) pair by adjacent position in that order, choosing via backtracking search the first full pairing in sorted order that repeats **no** previous pairing; (4) if no rematch-free pairing exists, take the first pairing with the fewest rematches and record `rematch: true` in `tournament.jsonl`. Round 1 has all-zero points, so it pairs by seed (1v2, 3v4, …).
- **Seeding**: grid order (axis-1 bin index, then axis-2 bin index, then idea ID).
- **Byes**: odd N → the lowest-seeded player without a prior bye gets a bye worth 1 point.
- **Scoring per pair**: both orders agree → winner 1, loser 0; orders disagree → 0.5 each (tie); abstention or malformed vote in either order → 0.5 each, logged in `tournament.jsonl`.
- **Independence**: order `ab` and order `ba` for a round are two separate LLM calls; the second call's prompt contains no verdicts from the first.
- **Tie-break**: total points, then Buchholz (sum of opponents' points), then seed.
- **Judge reliability**: `tournament.json` records `tie_rate` (share of pairs whose two orders disagreed or abstained). When `tie_rate > 0.5` the ranking is `low_confidence` (seed order is then decisive and arbitrary); `portfolio` copies `tie_rate` and `low_confidence` into `portfolio.json` and the report states it. FEAT-3596 reports `tie_rate` in the old-vs-new comparison.
- **Wildcard**: per the § Data Contract slot rules (differs from the winner on both axes; fallback flagged).
- **Verdicts** carry a rubric-based `rationale` so the report can explain the ranking.

## Program Design

### Types

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, cell: [str, str], off_grid: bool, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `PairVerdict`: `{a: str, b: str, winner: str | null, order: "ab" | "ba", rationale: str}` — `winner: null` = abstention
- `Portfolio`: see § Data Contract

### Signatures

- `collapse_duplicates(ideas: list[IdeaRecord], groups: list[list[str]]) -> list[IdeaRecord]` — keeps the first-generated member of each duplicate group
- `build_bracket(finalists: list[IdeaRecord], standings: dict[str, float], round_no: int) -> list[tuple[str, str]]` — deterministic Swiss pairing with byes, no rematches where avoidable (§ Tournament Specification → Swiss pairing)
- `tally(verdicts: list[PairVerdict]) -> list[str]` — idea IDs ranked by points, then Buchholz, then seed
- `validate_portfolio(portfolio: dict, ideas: list[IdeaRecord]) -> bool` — floors + reference integrity, exit 1 on violation

### Call Path

`init` -> `resolve_profile` -> `frame` -> `reframe` -> `pop_lens` -> `diverge` (loop over lenses) -> `dedup` -> `shortlist` -> `tournament` (sub-loop) -> `portfolio` -> `validate_portfolio` -> `route_sink` -> `verify_artifacts` -> `finalize_done`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Anchor-resolvable identifiers today: state names in `scripts/little_loops/loops/brainstorm.yaml` (`frame`, `pop_lens`, `diverge`, `dedup_novelty`, `verify_artifacts`, `route_sink`) and `parse_tagged_json`/`queue_pop` in `scripts/little_loops/loops/lib/common.yaml`. `dedup_cells`, `build_bracket`, `tally` do not exist yet — they are inline Python inside shell states, so their signatures are contracts, not importable symbols.
- `parse_tagged_json` supplies no default action (`lib/common.yaml` design note: interpolation is single-pass, no nested `${captured.${…}}`); each consuming state writes its own extraction, and the tag today is `IDEAS_JSON:` with keys `text`/`rationale`. The `IdeaRecord` shape (`title`/`body`/`cell`/`cluster`) is a schema change from `text`/`rationale` — `winners.md` consumers still read `text`/`rationale`, so the mapping (`title`→`text`, `body`→`rationale`) must be pinned.

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Decision Rules still unpinned (implementer must fix and document): default values of `min_ideas` and `min_cells`; how many framings `reframe` selects and the tie rule for that selection; the escape hatch, if any, for intentionally small runs (e.g. a profile that lowers the minimums — FEAT-3583 consumes this). _Resolved 2026-09-25 (Astra review): floors count post-dedup on-grid ideas (§ Data Contract); bracket is Swiss with disagreeing orders scored as a tie (§ Tournament Specification)._

## Integration Map

### Behavior Parity

Behaviors of `scripts/little_loops/loops/brainstorm.yaml` and their disposition:

| Artifact | Behavior | Disposition |
|----------|----------|-------------|
| `scripts/little_loops/loops/brainstorm.yaml` | `frame` selects lenses; `pop_lens` queues them | preserved (lens queue feeds `diverge`; `reframe` added before it) |
| `scripts/little_loops/loops/brainstorm.yaml` | `diverge` generates `ideas_per_round` ideas per lens | changed — sees running idea titles and tags a two-value `cell` from the profile's axis bins (per-idea `IdeaRecord` in `ideas.jsonl`) |
| `scripts/little_loops/loops/brainstorm.yaml` | `dedup_novelty` difflib dedup at `novelty_threshold` | dropped — replaced by `dedup`: an LLM pass over `{id, title}` pairs emits duplicate groups, a script collapses each group to its first-generated member (per-cell representative selection is the separate `shortlist` step) |
| `scripts/little_loops/loops/brainstorm.yaml` | `saturation_gate` early exit after `max_saturation` zero-novel rounds | dropped — never fired in observed runs |
| `scripts/little_loops/loops/brainstorm.yaml` | `cluster` / `rank` single listwise LLM passes | changed — per-cell `shortlist` + pairwise `tournament` |
| `scripts/little_loops/loops/brainstorm.yaml` | `converge` synthesizes best-of hybrid | changed — `portfolio`; hybrid only when `synthesize=true` |
| `scripts/little_loops/loops/brainstorm.yaml` | `route_sink` + `sink_file`/`sink_issue`/`sink_decision` contract | preserved — sinks read `winners` from the portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` (a failing run can already create issues/decisions) | changed — `validate_portfolio` gates `route_sink`; no sink fires on an invalid run |
| `scripts/little_loops/loops/brainstorm.yaml` | `verify_artifacts` requires non-empty `brainstorm.md` | changed — also requires `min_ideas` and `min_cells` |
| `scripts/little_loops/loops/brainstorm.yaml` | `on_handoff: spawn`, `scope`, artifacts under `${context.run_dir}` | preserved |

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — replace `frame`/`diverge`/`dedup_novelty`/`saturation_gate`/`cluster`/`rank`/`converge` with the new state graph; tighten `verify_artifacts`; update `description:` and `context:` keys
- `scripts/little_loops/loops/brainstorm-tournament.yaml` — **new** child loop (Swiss tournament; see § Tournament Specification → Child loop); add to `test_builtin_loops.py` built-in set, `scripts/little_loops/loops/README.md`, and the `README.md` loop count (mirror `scripts/README.md`)
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entries for `reframe` and the child's judge states

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `parse_tagged_json` / `queue_pop` — fragments to reuse for tagged-JSON extraction and lens/framing queues

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: duplicate-group collapse (3 fixtures in § Acceptance Criteria) plus malformed-group fail-open, off-grid flagging and case/whitespace normalization, cap-selection at 9 occupied cells, wildcard slot rule and fallback, Swiss no-rematch pairing and rematch fallback, generation/finalist floors in `validate_portfolio`, Swiss bracket determinism + byes, position-swap tally with tie/abstention scoring

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions
- `README.md` — brainstorm mention (verify wording only)

### Configuration
- Context keys: add `mode` (default `artifact`), `min_ideas` (`12`), `min_cells` (`4`), `max_finalists` (`8`), `synthesize`; remove `novelty_threshold`, `max_saturation`, `novelty_backend`, `top_k`

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
- New tests should follow Pattern A (`_bash(script, cwd)` + `$${`→`${` unescape helper, `test_builtin_loops.py:~56`) against `dedup`/`shortlist`/`tournament` actions extracted from the YAML, not inline script copies [Agent 3]

**Configuration / validator constraints**
- `scripts/tests/data/loop_interpolation_baseline.json` — regenerate for removed `dedup_novelty` and new heredoc states [Agent 2]
- Validator rules the new states must satisfy: MR-10 parse-swallow (`json.loads`+`except`+`sys.exit(0)` without `on_error` warns — keep exit-2 crash contract), abstention route (an `llm_structured` pair judge needs `on_error`/`cannot_judge`), classify `default:` route, capture reachability/dominance for new `${captured.*}` [Agent 2]
- **Step budget** (pinned 2026-09-28): fixed parent states ≈ 13 (incl. `resolve_profile`) + (L+1) `pop_lens` (the final pop returns the empty-queue exit) + L `diverge` (L ≤ 9 → 19) + 1 for the `tournament` sub-loop ≈ 33, under `max_steps: 60`, so `test_max_steps_is_60` stays valid for the core. Framing×lens is **not** a cross product (round-robin), and the tournament's ~24 judge calls live in the child loop's own budget. The combined all-features budget (ground + materialize + premortem) is owned by FEAT-3596.

## Implementation Steps

1. Define the idea record schema and grid-cell tagging contract.
2. Rewrite states per Expected Behavior; reuse `lib/common.yaml` fragments
   (`parse_tagged_json`, `queue_pop`).
3. Write the tournament bracket/tally script inline (or as a small helper under the
   loop) with position-swap handling.
4. Tighten `verify_artifacts`.
5. Update tests and the loop's description/docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Budget pinned (see Review Decisions); keep `test_max_steps_is_60` valid, add a test asserting the child tournament loop's `max_steps` and that the parent reaches it via a `loop:` state
- Verify the child tournament loop's placement against loop discovery scanners and `ll-verify-package-data`
- Drop `top_k` from context and from `sink_decision`/`sink_issue` prompts; update `test_context_*` tests
- Update `scripts/tests/test_builtin_loops.py` fence/MR-11/heredoc-site/warning-budget assertions and `scripts/tests/data/loop_interpolation_baseline.json`
- Add `reframe`/tournament-judge states to `fence.py` `FENCE_ROLES`; drop `converge` from `KNOWN_UNFENCED_PROMPT_SITES`
- Update `README.md:131` and mirror to `scripts/README.md`; add `CHANGELOG.md` entry under a concrete version
- Extract new-state tests via the `_bash` helper rather than inline script copies

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
  insufficient cells, and fewer than 2 eligible finalists each route to
  `failed` with no sink executed; an all-conceded portfolio (`winner: null`,
  `conceded == eligible`) passes `validate_portfolio`.
- Tournament bracket construction and scoring are deterministic shell/Python; only
  individual pair verdicts are LLM calls; each pair is judged in both orders via
  two independent calls; every verdict carries a `rationale`.
- Swiss pairing, byes, tie scoring, and Buchholz tie-break are covered by
  deterministic tests.
- Off-grid cell values are flagged (after case/whitespace normalization) and excluded from `min_ideas`, `min_cells`, and `shortlist`.
- Malformed dedup output (unknown IDs, overlapping groups, unparseable text) never drops ideas.
- `portfolio.json` carries `tie_rate` and `low_confidence`; the wildcard differs from the winner on both axes or is flagged `wildcard_fallback`.
- The tournament child `brainstorm-tournament.yaml` has `max_steps: 60` and `timeout: 1800`, is reached via a `loop:` state, and a child failure routes to `finalize_failed`.
- Output `brainstorm.md` presents a portfolio + the grid map; `portfolio.json` is
  written for every run; `ideas.jsonl` records `id`, `cell`, `framing`, `lens` per
  idea.
- `ll-loop validate brainstorm` passes; artifacts only under `${context.run_dir}/`.
- Existing brainstorm tests updated; new dedup fixtures cover: distinct ideas that
  share a cell (both kept), paraphrases in different cells (collapsed), and a
  concise representative kept over a longer duplicate (first-generated wins).

## Review Decisions

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

1. **Tournament as a sub-loop** — per-pair independent judging needs ~24 calls (8 finalists); as parent states it would blow `max_steps: 60`. `loop:` states run a child executor and cost the parent one step (`executor.py:_execute_sub_loop`). Finalists capped at 8; rounds `ceil(log2 N)`.
2. **Round-robin framings** — one `diverge` per lens with a rotating framing, not F×L calls; keeps old-loop cost and pins the core budget at ≈ 32 parent steps.
3. **`top_k` removed** — `winners.md` = portfolio members; sinks iterate lines.
4. **`shortlist` resolved** — script for single-idea cells, one batched LLM pick for multi-idea cells, first-generated fallback.
5. **`portfolio.json` nullability + recompute rule** — `winner: null` only via FEAT-3586 all-conceded; slots recomputed by the stated rules.
6. **Occupancy-aware `diverge`** — per-cell counts fed into the prompt so the grid steers generation rather than only tagging it.
7. **Defaults pinned** — `min_ideas: 12`, `min_cells: 4`, 3 framings, `max_finalists: 8`.
8. **`resolve_profile` + `profile.json` schema move here** (with the `artifact` profile) so FEAT-3583 does not rewrite `diverge`/`reframe`/`tournament` prompts a second time.
9. **Judge reliability** — `tie_rate` recorded; `low_confidence` flag above 0.5.

10. **Wildcard redefined** — finalists occupy distinct cells, so the different-cell rule was vacuous; wildcard now differs from the winner on both axes (fallback flagged). FEAT-3586 recompute reuses these slot rules.
11. **Swiss pairing pinned** — adjacent pairing in points/seed order, backtracking no-rematch search, fewest-rematch fallback; byes to the lowest-seeded player without one.
12. **Cap rule** — over-cap cells: drop lowest-occupancy first, ties by later grid order.
13. **Eligible floor vs concession** — `eligible` is never reduced by premortem concession; all-conceded is valid.
14. **Child loop named** — `brainstorm-tournament.yaml`, `with:` bindings, `timeout: 1800`, failure → `finalize_failed`; off-grid normalization and dedup fail-open added.

The two Confidence Check concerns below (unpinned defaults, `max_steps`) are resolved by items 2 and 7; re-run `/ll:confidence-check`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28 (re-run after review-fold)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Prior concerns resolved: child loop named (`brainstorm-tournament.yaml`, § Tournament Specification → Child loop) and `eligible` vs premortem concession pinned (§ Data Contract).
- Program Design, dependency, claim, and learning-test gates are all clean.

### Outcome Risk Factors
- **Complexity (5/25)**: rewrites most of a 459-line loop, adds a new child loop, and touches fence registry, interpolation baseline, README counts, and ~10 existing tests — expect iteration on validator warnings (MR-10/MR-11, warning budget).
- **Change surface (18/25)**: the `context:` key removals and `winners.md` schema mapping ripple into sinks, docs, and FEAT-3583..3586.
- **Ambiguity (22/25)**: judge rubric wording and the `reframe`/`diverge` prompt text are still left to the implementer.


## Session Log
- `/ll:confidence-check` - 2026-09-29T02:07:51 - `a043a653-a6de-455c-af91-864f254d2405.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:46 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:38 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:30 - `fa11583b-aa00-4da8-b0f0-fc89c6cf8f64.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:44 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:47:12 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:36 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
