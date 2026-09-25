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
2. `diverge` per framing × lens — prompt includes the running list of idea titles;
   each idea is emitted with a grid cell whose two values must come from the
   profile's enumerated axis bins. A script assigns stable IDs and rejects
   (flags `off_grid`) any cell value outside the bins.
3. `dedup` — one cheap LLM pass over titles only emits duplicate groups by idea ID;
   a script collapses each group, keeping the **first-generated** idea as
   representative (never "longest body").
4. `shortlist` (script + LLM) — best idea per occupied cell.
5. `tournament` — Swiss format, script-built and script-tallied; each round is
   judged in two independent LLM calls (one per position order). See § Tournament
   Specification.
6. `portfolio` — script writes canonical `portfolio.json` (winner, runner-up from a
   different cell, wildcard); hybrid only when `synthesize=true`.
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
2. `diverge` — one call per framing × lens; prompt carries the running list of idea titles; each idea is emitted as a tagged JSON line with `cell` (2 values, each from the profile's axis bins). A script assigns IDs and flags off-grid cells; off-grid ideas do not count toward `min_cells`.
3. `dedup` — an LLM pass over `{id, title}` pairs only emits duplicate groups (`DUP_GROUPS_JSON:`); a Python heredoc collapses each group to its first-generated member. Duplicate detection and per-cell representative selection are separate steps.
4. `shortlist` — script picks the best idea per occupied cell.
5. `tournament` — Swiss bracket per § Tournament Specification; script builds pairings, two independent judge calls per round (order `ab`, then order `ba`, neither sees the other), script tallies.
6. `portfolio` — script writes `portfolio.json` (the one canonical portfolio format) and `winners.md`; hybrid only when `synthesize=true`. A profile's `output_shape` affects only how `brainstorm.md` is rendered, never `portfolio.json`.
7. `validate_portfolio` — gate before `route_sink`; enforces generation and finalist floors (§ Data Contract) and winner-reference integrity. Fails to `finalize_failed` with no sink executed.
8. `verify_artifacts` — report-integrity check after sinks.

Reuse `parse_tagged_json` and `queue_pop` from `lib/common.yaml`. Remove difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, `saturation.txt`.

### Data Contract

Owned by this issue; FEAT-3583..3586 extend it, never redefine it.

- **Idea IDs**: script-assigned (`i001`, `i002`, … in generation order), stable for the run; the LLM never invents IDs.
- **Common fields** (every profile): `id`, `title`, `body`, `framing`, `lens`, `cell`, `off_grid`. Profile-specific fields live under an `extra: {}` object.
- **Legacy mapping** for `winners.md` / sinks: `title`→`text`, `body`→`rationale` (both keys written).
- **Cell vocabulary**: each profile declares `axes: [{name, bins: [str, …]}, {name, bins: [str, …]}]` (FEAT-3583). A cell is valid only if both values are in the bins. The core ships a default 3×3 grid for runs without a profile.
- **Floors**: generation floor `min_ideas` counts post-dedup, on-grid ideas; `min_cells` counts distinct on-grid cells; finalist floor = at least 2 eligible finalists after every filtering step (ground, materialize, premortem). Floors are rechecked in `validate_portfolio`, not only after `diverge`.
- **`portfolio.json`**: `{winner: id, runner_up: id | null, wildcard: id | null, ranking: [id], eligible: [id], flags: {id: [str]}}`. Winner is mandatory; runner-up/wildcard are null only when no qualifying candidate exists (recorded in the report).

### Tournament Specification

- **Format**: Swiss, `ceil(log2 N) + 1` rounds over N finalists.
- **Seeding**: grid order (axis-1 bin index, then axis-2 bin index, then idea ID).
- **Byes**: odd N → the lowest-seeded player without a prior bye gets a bye worth 1 point.
- **Scoring per pair**: both orders agree → winner 1, loser 0; orders disagree → 0.5 each (tie); abstention or malformed vote in either order → 0.5 each, logged in `tournament.jsonl`.
- **Independence**: order `ab` and order `ba` for a round are two separate LLM calls; the second call's prompt contains no verdicts from the first.
- **Tie-break**: total points, then Buchholz (sum of opponents' points), then seed.
- **Wildcard**: highest-ranked finalist whose cell is used by neither the winner nor the runner-up.
- **Verdicts** carry a rubric-based `rationale` so the report can explain the ranking.

## Program Design

### Types

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, cell: [str, str], off_grid: bool, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `PairVerdict`: `{a: str, b: str, winner: str | null, order: "ab" | "ba", rationale: str}` — `winner: null` = abstention
- `Portfolio`: see § Data Contract

### Signatures

- `collapse_duplicates(ideas: list[IdeaRecord], groups: list[list[str]]) -> list[IdeaRecord]` — keeps the first-generated member of each duplicate group
- `build_bracket(finalists: list[IdeaRecord], standings: dict[str, float], round_no: int) -> list[tuple[str, str]]` — deterministic Swiss pairing with byes
- `tally(verdicts: list[PairVerdict]) -> list[str]` — idea IDs ranked by points, then Buchholz, then seed
- `validate_portfolio(portfolio: dict, ideas: list[IdeaRecord]) -> bool` — floors + reference integrity, exit 1 on violation

### Call Path

`init` -> `frame` -> `reframe` -> `diverge` -> `dedup` -> `shortlist` -> `tournament` -> `portfolio` -> `validate_portfolio` -> `route_sink` -> `verify_artifacts` -> `finalize_done`

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
| `scripts/little_loops/loops/brainstorm.yaml` | `diverge` generates `ideas_per_round` ideas per lens | changed — sees running idea titles and tags `cell`/`cluster` |
| `scripts/little_loops/loops/brainstorm.yaml` | `dedup_novelty` difflib dedup at `novelty_threshold` | dropped — replaced by script dedup on cell + cluster |
| `scripts/little_loops/loops/brainstorm.yaml` | `saturation_gate` early exit after `max_saturation` zero-novel rounds | dropped — never fired in observed runs |
| `scripts/little_loops/loops/brainstorm.yaml` | `cluster` / `rank` single listwise LLM passes | changed — per-cell `shortlist` + pairwise `tournament` |
| `scripts/little_loops/loops/brainstorm.yaml` | `converge` synthesizes best-of hybrid | changed — `portfolio`; hybrid only when `synthesize=true` |
| `scripts/little_loops/loops/brainstorm.yaml` | `route_sink` + `sink_file`/`sink_issue`/`sink_decision` contract | preserved — sinks read `winners` from the portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` (a failing run can already create issues/decisions) | changed — `validate_portfolio` gates `route_sink`; no sink fires on an invalid run |
| `scripts/little_loops/loops/brainstorm.yaml` | `verify_artifacts` requires non-empty `brainstorm.md` | changed — also requires `min_ideas` and `min_cells` |
| `scripts/little_loops/loops/brainstorm.yaml` | `on_handoff: spawn`, `scope`, artifacts under `${context.run_dir}` | preserved |

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — replace `frame`/`diverge`/`dedup_novelty`/`saturation_gate`/`cluster`/`rank`/`converge` with the new state graph; tighten `verify_artifacts`; update `description:` and `context:` keys

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `parse_tagged_json` / `queue_pop` — fragments to reuse for tagged-JSON extraction and lens/framing queues

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: duplicate-group collapse (3 fixtures in § Acceptance Criteria), off-grid flagging, generation/finalist floors in `validate_portfolio`, Swiss bracket determinism + byes, position-swap tally with tie/abstention scoring

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions
- `README.md` — brainstorm mention (verify wording only)

### Configuration
- Context keys: add `min_ideas`, `min_cells`, `synthesize`; remove `novelty_threshold`, `max_saturation`, `novelty_backend`

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
- `scripts/tests/test_brainstorm.py` — beyond the tests already listed: `TestBrainstormDedup._run_dedup` (inline difflib script copy, delete), `TestBug2468ErrorRouting` (`_dedup_action`/`_verify_action`, `test_all_success_paths_route_through_verify_artifacts`), `TestBrainstormDryRun` (`test_all_states_reachable`, `test_no_ratcheted_category_warnings`, `test_required_inputs_declared`), `test_route_sink_has_all_branches` [Agent 3]
- New tests should follow Pattern A (`_bash(script, cwd)` + `$${`→`${` unescape helper, `test_builtin_loops.py:~56`) against `dedup`/`shortlist`/`tournament` actions extracted from the YAML, not inline script copies [Agent 3]

**Configuration / validator constraints**
- `scripts/tests/data/loop_interpolation_baseline.json` — regenerate for removed `dedup_novelty` and new heredoc states [Agent 2]
- Validator rules the new states must satisfy: MR-10 parse-swallow (`json.loads`+`except`+`sys.exit(0)` without `on_error` warns — keep exit-2 crash contract), abstention route (an `llm_structured` pair judge needs `on_error`/`cannot_judge`), classify `default:` route, capture reachability/dominance for new `${captured.*}` [Agent 2]
- **Step budget**: executor counts every state execution incl. terminals; `on_max_steps` is unset so hitting the cap skips `verify_artifacts`. New graph ≈ 13 fixed states + 2·F·L for the framing×lens loop (F=2,L=8 → ~48; F=3,L=9 → ~54) + ~3/tournament round — exceeds `max_steps: 60` for F=3. This issue pins a core-only budget (raise `max_steps` and update `test_max_steps_is_60`, cap F·L, or batch lenses per framing); the **combined** all-features budget (ground + materialize + premortem) is owned by FEAT-3596 [Agent 2]

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

- Decide and pin the `max_steps` budget for framings × lenses + tournament; update `test_max_steps_is_60` deliberately
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
  insufficient cells, and fewer than 2 distinct portfolio members each route to
  `failed` with no sink executed.
- Tournament bracket construction and scoring are deterministic shell/Python; only
  individual pair verdicts are LLM calls; each pair is judged in both orders via
  two independent calls; every verdict carries a `rationale`.
- Swiss pairing, byes, tie scoring, and Buchholz tie-break are covered by
  deterministic tests.
- Off-grid cell values are flagged and excluded from `min_cells`.
- Output `brainstorm.md` presents a portfolio + the grid map; `portfolio.json` is
  written for every run; `ideas.jsonl` records `id`, `cell`, `framing`, `lens` per
  idea.
- `ll-loop validate brainstorm` passes; artifacts only under `${context.run_dir}/`.
- Existing brainstorm tests updated; new dedup fixtures cover: distinct ideas that
  share a cell (both kept), paraphrases in different cells (collapsed), and a
  concise representative kept over a longer duplicate (first-generated wins).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T02:07:44 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:47:12 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:36 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
