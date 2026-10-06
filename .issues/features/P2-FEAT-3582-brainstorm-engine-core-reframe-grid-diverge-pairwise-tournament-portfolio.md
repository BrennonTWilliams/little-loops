---
id: FEAT-3582
type: FEAT
title: 'Brainstorm engine core: grid diverge, pairwise tournament, portfolio'
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
blocked_by:
- FEAT-3667
- FEAT-3686
---

# FEAT-3582: Brainstorm engine core: grid diverge, pairwise tournament, portfolio

## Scope Note (split, 2026-09-29)

_EPIC-3581 pre-implementation review (`/ll:advise` with Opus) split the engine module out of this issue._ **FEAT-3667** implements `brainstorm_engine.py`, its tests, `resolve-profile`, all four preset JSONs and the **CLI contract table** (it is `blocked_by` FEAT-3667). This issue is the **loop side**: the `brainstorm.yaml` rewrite, the `brainstorm-tournament.yaml` child loop, fence/baseline/README/CHANGELOG/docs wiring, and YAML wiring tests — landed as **one commit** (a half-landed rewrite on `main` breaks brainstorm in every `local-editable` project). The § Data Contract, § Tournament Specification and § Program Design below remain the **spec of record** for both issues. Where the body below says "the engine module implements X", read it as FEAT-3667; where it says "the state calls X", that is this issue.

## Summary

Replace the body of `scripts/little_loops/loops/brainstorm.yaml` with the new core
engine (C + B + A from EPIC-3581): **frame → grid-tagged diverge → duplicate-group dedup →
per-cell shortlist → script-driven pairwise tournament → portfolio output**, with a
hard minimum-idea invariant. Removes difflib novelty, the saturation counter, and the
forced best-of hybrid.

## Current Behavior

- `dedup_novelty` uses difflib SequenceMatcher against novelty_threshold=0.55. Historical runs found weak semantic duplicate removal; the preserved fresh baseline retained 42/45 artifact ideas and 45/45 functional ideas. Do not generalize the earlier zero-removal observation to every run. The duplicate/coverage comparison uses FEAT-3596's preserved matched baseline.
- Each `diverge` call sees only the brief, never prior ideas.
- `cluster` / `rank` / `converge` are single listwise LLM passes; `converge` always
  synthesizes a hybrid.
- `verify_artifacts` only checks `brainstorm.md` is non-empty, so a zero-idea run
  (07-01) whose report says "No synthesis produced" passes.

## Expected Behavior

1. `frame` selects 1–9 unique lenses in one call (`LENSES_JSON: {"lenses": [str, ...]}`). `frame-apply` validates the list and writes the immutable `lenses.json` ledger plus `lenses.txt` queue (`lens_index|framing|lens`, empty framing in v1), then emits only `pop_lens`. **Reframe and reframe-select are deferred to v2 and are not states, CLI calls, tests or fence registrations in this issue.** FEAT-3667 owns ledger/queue/ingest semantics.
2. `diverge` once per lens, with empty framing in v1 (L calls, never a framing×lens cross product) — the prompt reads `diverge_state.md` (the running list of idea
   titles **and the current per-cell occupancy**) and instructs the model to favor
   empty or under-filled cells. Each idea is emitted with a grid cell whose two values
   must come from the profile's enumerated axis bins. A per-lens `ingest` script state
   (runs after every `diverge`) assigns stable IDs, replaces any prior ideas of the same lens index (idempotent — a re-run never double-appends; lens identity is the persisted `lens_index` resolved through immutable `lenses.json`), normalizes each cell value (strip +
   casefold, then map to the canonical bin spelling), rejects (flags `off_grid`) any
   value that still matches no bin, and regenerates `diverge_state.md` for the next
   lens. Off-grid ideas stay in `ideas.jsonl` with `off_grid: true` but are excluded
   from `shortlist`, `min_ideas`, and `min_cells`; the report states the off-grid
   share (a high share means the bins were poorly communicated in the prompt).
3. `dedup` — one cheap LLM pass over `{id, title, body excerpt}` (first ~200 chars of
   `body`) emits duplicate groups by idea ID. Titles alone are not enough: with
   occupancy steering the model can relabel a paraphrase into an empty cell, which
   would inflate `min_cells` and the finalist count. The same call also **re-tags every
   idea's cell blind to the generator's own tag** (it sees no `cell`; emits `RETAG_JSON` with
   one bin per axis) — the generator's tag is a self-claim under occupancy steering, so
   `min_cells` and the diversity metric would otherwise be gameable. A valid on-grid re-tag
   replaces cell, recomputes off_grid=false and keeps the original in extra.orig_cell; invalid/missing re-tags preserve both cell and off_grid (FEAT-3667).
   A script collapses each group,
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
   cell(s) until the cap is met (ties: drop the cell whose first idea was generated later — generation order, never grid order); dropped cells
   are listed in `shortlist.json` and the report. Then, when the resolved profile asks
   for a reserve (`reserve: 2` in a deferred web-grounding follow-up; v1 presets use `reserve: 0`), the next-best
   candidates per surviving cell go to `reserve`, not `finalists`. `shortlist` writes
   `finalists.json` (§ Data Contract → Finalists file); the tournament child reads
   only its `finalists` list.
5. `check_floors` (script) — runs at **two stages**, both before `tournament`:
   `check_floors --stage generation` right after `shortlist` (post-dedup, on-grid,
   `grounded != false` ideas ≥ `min_ideas`, occupied cells ≥ `min_cells`, finalists ≥ 2),
   so a doomed run fails before paying for optional render calls; and
   `check_floors --stage pre_tournament` after every filtering state (`materialize` — skipped when its profile knob is off, in which case this stage
   re-verifies the unchanged `finalists.json`; `ground_web` is deferred out of v1), so the tournament never sees a 0- or
   1-player field. Both route to `finalize_failed`. `check_floors` **also emits the next-state routing token**
   (`materialize` | `tournament`, derived from `profile.json`) as its last stdout
   line, or `fail` on any violation/crash, so the profile gates cost **no extra parent step** (no separate `*_gate` states; the
   state itself carries `evaluate: classify` + `route:` with the happy tokens listed explicitly, **`_: finalize_failed`** for unexpected successful output, and an explicit on_error/_error route to finalize_failed. The common evaluator maps nonzero action exits/timeouts to error before classification; trailing fail/default alone is insufficient). At
   `pre_tournament` it additionally fails with the violation `insufficient_time` when
   `PARENT_TIMEOUT_S − elapsed < TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + RETRY_SLEEP_RESERVE_S + TAIL_S` with `elapsed` taken from `--elapsed-ms ${loop.elapsed_ms}` (§ Tournament Specification →
   Budgets), so a doomed tournament never starts. Both stages and
   `validate_portfolio` call **one function** (`brainstorm_engine.check_floors(stage)`), so
   the checks cannot drift.
6. `tournament` — full **round-robin** over the finalists, script-built and
   script-ranked, run as a **sub-loop** (one parent step; `on_yes` → `portfolio`, **`on_no`, `on_error` and `on_timeout` → `salvage_tournament`** — a judge-call error would otherwise send the run to `finalize_failed` and discard every completed round); **one LLM judge call per round**
   (each round is N/2 disjoint pairs, so every non-bye finalist appears once per call), the
   presentation order counterbalanced across the field by the schedule, plus one batched
   reversed-order probe call over the top-3 head-to-heads. ≈ 8 judge calls for 8 finalists.
   See § Tournament Specification.
7. `portfolio` — script writes canonical `portfolio.json` (winner, runner-up, wildcard — see § Data Contract for the slot rules; `winner` is always non-null) and `winners.md` (the non-null portfolio members, in
   that order, each line carrying a `role` key of `winner`/`runner_up`/`wildcard`;
   `top_k` is removed); no unjudged hybrid in v1 (`synthesize=true` is rejected at preflight; synthesis is deferred). Its last stdout line routes
   (`premortem` | `render`; the happy path with no finisher goes straight to `render_report`, not to `validate_portfolio`) so the premortem gate costs no extra step. The report header states the
   resolved mode (`Mode: <x> (auto, confidence 0.72) — rerun with mode=<y> to override`).
8a. `render_report` (script, engine `render-report`) — the **only writer of `brainstorm.md`** (`init` creates it only if absent; `converge` no longer exists). Runs after `portfolio`/`premortem` and before `validate_portfolio`, from the on-disk artifacts (`portfolio.json`, `ideas.jsonl`, `finalists.json`, `shortlist.json`, `tournament.json`, optional `premortem.json`/`materialize.json`), so it is deterministic and unit-tested. A report for a run that then fails validation is harmless because sinks are gated behind `validate_portfolio`.
8. `validate_portfolio` (script, **before any sink**) — calls
   `brainstorm_engine.check_floors(stage="final")` (same thresholds; post-dedup idea
   count < `min_ideas`, occupied cells < `min_cells`, eligible finalists < 2 all fail) and
   adds reference integrity: winner/runner-up/wildcard IDs must resolve in `ideas.jsonl`
   and the winner must be non-null.
9. `verify_artifacts` — remains after sinks as a report-integrity check (sinks never see an empty report: `validate_portfolio` now also requires `brainstorm.md` non-empty).

**Lens handoff**: `pop_lens` retains its state name/evaluator and empty/missing exit semantics, but becomes a non-destructive queue-head read followed by divergence-block construction. `ingest` acknowledges that head only after its publications succeed, per FEAT-3667. Do not use the destructive action from `queue_pop`; leave the shared fragment unchanged. An interrupted block construction or generation keeps the lens pending, including the native-resume window before the pop visit is checkpointed.

Sinks (`none|file|issue|decision`) keep their contract and read `winners` from the
portfolio. No sink executes unless `validate_portfolio` passed.

## Use Case

**Who**: A little-loops user running `ll-loop run brainstorm "<brief>"` to explore options for a naming, design, or product question.

**Context**: The default run attempts 9 lenses × 5 ideas, semantic duplicates can survive, and the output is a single hybrid; a run can even "succeed" with zero ideas.

**Goal**: Get a diverse, de-duplicated set of ideas ranked by structured pairwise judgment.

**Outcome**: `brainstorm.md` presents a portfolio (winner, runner-up, and a wildcard that differs from the winner on both grid axes) plus the grid map, and the run fails loudly if too few ideas or cells were produced.

## Motivation

The 4 historical `brainstorm-*` runs (see EPIC-3581 § Motivation) show the current core is inert where it matters:

- Historical zero-removal/saturation observations motivated the rewrite; the newer preserved artifact baseline removed three ideas with difflib. FEAT-3686 still found retained semantic redundancy, so compare with the actual baseline instead of claiming dedup never fires.
- `diverge` never sees prior ideas, so there is no cross-lens anti-anchoring.
- `cluster`/`rank`/`converge` are single listwise LLM passes (`converge` read ~319k input tokens in one run) and always force a hybrid.
- A zero-idea run passes `verify_artifacts` because it only checks `brainstorm.md` is non-empty.

This feature is the core (C + B + A) that every other EPIC-3581 child builds on.

## Proposed Solution

Rewrite the state graph in `scripts/little_loops/loops/brainstorm.yaml` (keep `init`, sinks, `finalize_*`, `on_handoff: spawn`).

**Engine module (2026-09-29 decision).** All deterministic logic lives in a new tested module,
`scripts/little_loops/brainstorm_engine.py`, invoked from thin shell states as
`"$${LL_PYTHON:-python3}" -m little_loops.brainstorm_engine <command> --run-dir ${context.run_dir:shell}`
(`LL_PYTHON` is exported as `sys.executable` by `fsm/runners.py:333`; `sft-corpus.yaml` and `assumption-firewall.yaml` use `$${LL_PYTHON:-python3}` with heredocs. `autodev.yaml` uses a plain `python3 -m little_loops.autodev_summary`; the `LL_PYTHON` + `-m` combination has no in-repo precedent, so the first state to use it must be smoke-tested through `ll-loop run` in a consuming-project layout). LLM output reaches the module only as a file the state wrote (`capture:` + Bash builtin `printf '%s' ${captured.<name>.output:shell} > ${context.run_dir:shell}/raw.txt`; there is no `<state>_output.txt` capture). Use `:shell` outside literal quotes for every interpolated path/data/override argument, and quote the interpreter as above. Never interpolate captured text into Python source. Existing quoted heredocs are already protected by the interpolator's collision guard; prefer printf so a literal delimiter line is preserved as data rather than rejecting otherwise parseable output. Commands (full argv/files/exit-code table: **FEAT-3667 § CLI contract**): `resolve-profile`, `frame-apply`, `ingest`, `collapse`, `shortlist-apply`, `check-floors --stage generation|pre_tournament|final`, `build-schedule`, `next-round`, `record-round`, `probe-plan`, `rank`, `salvage`, `portfolio`, `validate`, `render-report`, `prompt-block`; FEAT-3583/3584/3585/3586 add `probe-anchor`, `materialize-check`, `annotate`. The YAML keeps only orchestration: prompts, routing, `evaluate:` clauses, and one-line module calls. Non-goal: moving prompts out of the YAML — the instructions stay visible to `ll-loop show`; engine commands print only the **data block** (axes/bins, extra fields, rubric, occupancy, idea list, round pair block) to stdout, which the state captures and interpolates inside a `<<<…>>>` fence (`UNTRUSTED_OUTPUT_ROLES`), so profile data reaches prompts and idea text is never unfenced. There is no `round_prompt.txt`. **Every LLM prompt state declares `next:` plus `on_error:` (or an explicit `evaluate:`)** — otherwise the default `llm_structured` evaluator (`executor.py` default-evaluation branch) adds a hidden LLM call per state and breaks the ≤ 30 call ceiling; a wiring test asserts it.

1. `frame` and engine `frame-apply` create the immutable lens ledger and consumable queue with empty framings; no reframe branch in v1.
2. `diverge` — one call per lens (empty framing in v1; `lenses.txt` lines are `lens_index|framing|lens`); the prompt reads `diverge_state.md` (running idea titles + per-cell occupancy) and asks for empty/under-filled cells; each idea is emitted as a tagged JSON line with `cell` (2 values, each from the profile's axis bins). **`ingest`** (script, after every `diverge`, routes back to `pop_lens`) reserves monotonic IDs, persists lens_index, flags off-grid cells, replaces that lens's rows in `ideas.jsonl`, and rewrites `diverge_state.md`; off-grid ideas do not count toward `min_cells`.
3. `dedup` — an LLM pass over `{id, title, body excerpt}` emits duplicate groups (`DUP_GROUPS_JSON:`) and blind cell re-tags (`RETAG_JSON:`); the engine `collapse` command collapses each group to its first-generated member and applies valid re-tags. Duplicate detection and per-cell representative selection are separate steps.
4. `shortlist` — script takes single-idea cells (excluding `grounded: false` ideas); one batched LLM call picks a representative for every multi-idea cell (fallback: first-generated). Cap at `max_finalists` first (lowest-occupancy cell dropped first; see Expected Behavior 4), then fill `reserve` when the profile asks for it; writes `finalists.json` (§ Data Contract → Finalists file).
5. `check_floors` — script gate at two stages (Expected Behavior 5): `generation` right after `shortlist`, `pre_tournament` after the optional `materialize` state and immediately before `tournament`; failure (`fail` token or `_` default) → `finalize_failed`.
6. `tournament` — a sub-loop state (`loop:`; the child runs its own executor and `max_steps`, so the parent spends one step). Round-robin per § Tournament Specification; script builds the pair schedule, one judge call per round (N/2 pairs), one batched probe call, script ranks. The child is `brainstorm-tournament.yaml` (see § Tournament Specification → Child loop); verify it against `ll-loop list`, `ll-verify-package-data`, and the built-in loop count in `README.md`.
7. `portfolio` — script writes `portfolio.json` (the one canonical portfolio format) and `winners.md`; no unjudged hybrid in v1 (`synthesize=true` is rejected at preflight; synthesis is deferred). A profile's `output_shape` affects only how `render_report` lays out `brainstorm.md`, never `portfolio.json`.
8. `resolve_profile` (script after `init`) — **engine implementation and all four presets belong to FEAT-3667**. This issue wires the existing command; default mode is artifact until FEAT-3583 adds auto. Init performs explicit-input preflight (`resolve-profile --validate-only`) so unsupported knobs fail before generation. Final resolution writes profile.json; every later prompt reads captured blocks derived from that file, without introducing another resolver.
9. `validate_portfolio` — gate before `route_sink`; reruns the `check_floors` body (§ Data Contract floors) and adds winner-reference integrity. Fails to `finalize_failed` with no sink executed.
10. `verify_artifacts` — report-integrity check after sinks.
11. `finalize_done` / `finalize_failed` — rewrite the prompts that name `ranked.md`/`clusters.md`/saturation artifacts (they no longer exist) to name `portfolio.json`, `ideas.jsonl`, `tournament.json`, and the grid map. `finalize_failed` writes its stub report through `render-report --failed` (FEAT-3667), so `render-report` stays the only writer of `brainstorm.md`.

Reuse `parse_tagged_json` and `queue_pop`'s evaluator/exit semantics from `lib/common.yaml`; override the latter's destructive action locally with a peek. Remove difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, `saturation.txt`.

### Data Contract

Owned by this issue; FEAT-3583..3586 extend it, never redefine it.

- **Idea IDs**: script-assigned (`i001`, `i002`, … in generation order), stable for the run; the LLM never invents IDs.
- **Common fields** (every profile): `id`, `title`, `body`, `framing`, `lens`, `cell`, `off_grid`, plus persisted `lens_index` and the optional top-level `grounded` (`true` | `false` | `"unknown"`; absent = unverified, counted as not-false — pinned 2026-09-29 so FEAT-3582's floors and FEAT-3584's writers agree). Profile-specific fields (`evidence`, `touchpoints`, `creates`, `palette`, …) live under an `extra: {}` object; `dedup` may record `extra.orig_cell`.
- **Legacy mapping** for `winners.md` / sinks: `title`→`text`, `body`→`rationale` (both keys written).
- **Cell vocabulary**: each profile declares `axes: [{name, bins: [str, …]}, {name, bins: [str, …]}]` (FEAT-3583). A cell is valid only if both values are in the bins. The core ships a default 3×3 grid for runs without a profile.
- **Floor defaults** (pinned 2026-09-28; a profile may lower them): `min_ideas: 12`, `min_cells: 4` (default 3×3 grid), `max_finalists: 8`. **These numbers live in the profile (`artifact` ships them), not in loop context.** The context keys `min_ideas`, `min_cells`, `max_finalists` default to `""` (inherit) per FEAT-3583's precedence rule (explicit non-empty context wins over the profile); with non-empty context defaults a profile could never lower a floor. `max_finalists` is clamped to ≤ 8 after resolution, whichever layer set it.
- **Floors**: generation floor `min_ideas` counts post-dedup, on-grid ideas with `grounded != false`; `min_cells` counts distinct on-grid cells among those ideas; finalist floor = at least 2 ids in `finalists`. `finalists` is reduced only by *filtering* steps (`ground_web`, `materialize`). Floors are enforced by `check_floors` at `generation` (after `shortlist`) and `pre_tournament` (after every filter, before `tournament`), and again at `final` in `validate_portfolio` — the same function at every stage.
- **Finalists file** (`${context.run_dir}/finalists.json`, owned here; written by `shortlist`, **rewritten in place by every filtering state**): `{finalists: [id], reserve: {cell_key: [id]}, dropped: {id: reason}, judge_mode: "text" | "image" | "html", assets: {id: {html: path, png: path}}}`. `judge_mode` defaults to `text` and `assets` to `{}` until FEAT-3585 fills them. `eligible` in `portfolio.json` is `finalists` at tournament entry. Filtering states move ids out of finalists into dropped (reason string). V1 does not promote reserves; same-cell reserve promotion belongs to deferred web grounding. Materialize chooses its complete eligible set once from the persisted pre-materialize shortlist; they never invent ids and never touch `ideas.jsonl` except to set `grounded`/`extra`. The tournament child judges `finalists` only and reads `judge_mode`/`assets` (§ Tournament Specification → Child loop).
- **`portfolio.json`**: `{winner: id, runner_up: id | null, wildcard: id | null, ranking: [id], eligible: [id], flags: {id: [str]}, tie_rate: float, abstention_rate: float, low_confidence: bool, partial: bool, probe_incomplete: bool}` (`tie_rate`/`abstention_rate`/`low_confidence`/`partial`/`probe_incomplete` copied from `tournament.json` so the report and FEAT-3596 read them from one file; `validate_portfolio` fails when `abstention_rate > 0.5`). `winner` is **always non-null** for a run that reaches `portfolio` (the floors guarantee ≥ 2 finalists); `validate_portfolio` fails a null winner. Runner-up/wildcard are null only when no qualifying candidate exists (recorded in the report). **Slot rules**: winner = first id in `ranking`; runner-up = the next id in `ranking`. Because `shortlist` keeps one finalist per cell, every finalist already occupies a distinct cell, so a different-cell test alone would make the wildcard merely third place. **Wildcard** = the highest-ranked remaining finalist whose cell differs from the winner's on **both** axes; if none exists, fall back to the highest-ranked remaining finalist and add `wildcard_fallback` to that id's `flags`. Later annotate-only features (FEAT-3586) add entries to `flags` and never touch slots. _(2026-09-29: `conceded`, nullable `winner`, and slot recompute after demotion were removed with FEAT-3586's demotion; see Review Decisions 23–24.)_
- **`top_k`**: removed. `winners.md` = the non-null portfolio members (winner, runner-up, wildcard); `sink_decision`/`sink_issue` iterate its lines instead of reading `top_k`.

### Tournament Specification

_Revised 2026-09-29 (pre-implementation review, `/ll:advise` with Opus; nothing here has been measured): per-round batched judging, a parent-timeout tail reserve, abstention accounting, and salvage edge cases._

- **Format**: full **round-robin** over N ≤ `max_finalists` (8) finalists — every pair exactly once (C(N,2) ≤ 28 pairs). Pairs are judged **one round per LLM call**: the circle-method schedule puts each finalist in exactly one pair per round, so a round is floor(N/2) disjoint pairs (plus a bye for odd N) in one prompt and the call returns one verdict per pair. ≤ 7 round calls + 1 batched probe call ≈ **8 judge calls** (was ≈ 31 one-per-pair calls). *Why batched*: each host session carries a large fixed overhead (≈ 94k tokens per call in the 2026-06-27 baseline run) and 31 serial sessions at the baseline 44–97 s per call is ≈ 23–50 min against a 2700 s child timeout — salvage would have been the normal path on slow hosts. *Cost of batching* (recorded dissent): the judge sees the other pairs of its round, which can add anchoring the one-pair-per-call design avoided; the prompt requires each pair be judged independently on the rubric, and the **probe stays an independent call** (§ Probe) so position sensitivity is still measured. FEAT-3596 measures `tie_rate` and `abstention_rate` before any further format change. *Why not Swiss*: 3 Swiss rounds give each finalist only ~3 comparisons and do not reliably order ranks 2–3, which the runner-up and wildcard slots depend on; round-robin gives every finalist N−1 comparisons and deletes the pairing algorithm, byes, rematch fallback, and Buchholz. **`max_finalists` stays ≤ 8** (a profile may lower it, never raise it): with batching the call count is linear in N (N−1 rounds), but round-robin pairs grow quadratically (C(N,2)), so prompt size, judge attention per pair and `tie_rate` all degrade above 8 — raising it needs FEAT-3596 measurements first.
- **Child loop**: `scripts/little_loops/loops/brainstorm-tournament.yaml` (top level, alongside `brainstorm.yaml`; `ll-loop list` uses `rglob`, so it is discoverable and runnable — accepted, and it declares `required_inputs: []` with a `description:` saying it is an internal child of `brainstorm`). The parent state is `loop: brainstorm-tournament` with `with:` bindings for `run_dir` and `brief` (the `with:` branch re-injects the parent `run_dir` via `setdefault`, `executor.py:1186`). Child states: `build_schedule` → `next_round` (engine `next-round`; exit 1 = no rounds left → `plan_probe`) → `judge_round` (LLM, one call; `timeout: 300`; captures the `next-round` stdout pair block, no `round_prompt.txt`) → `record_round` (engine `record-round`; routes back to `next_round`) → … → `plan_probe` → `judge_probe` (LLM, one call) → `record_probe` → `rank`. Contract: the child reads `${context.run_dir}/finalists.json` (§ Data Contract → Finalists file; it judges the `finalists` list only, never `reserve` or `dropped`, and reads `judge_mode`/`assets` — `text` here; FEAT-3585 adds the `image`/`html` judge prompts behind that switch without changing the child's inputs or outputs), reads the rubric from `profile.json`, calls the engine module (FEAT-3667 CLI contract), **atomically commits write-once round/probe batches into tournament.jsonl (keyed by round+pair+probe); a re-run from build_schedule verifies the complete judging-input digest, reuses the stable probe plan and skips recorded rounds. Identical canonical batches are no-ops; conflicting batches fail without overwriting results (FEAT-3667)**, writes `tournament.json`, and **never** re-runs `init` or touches `ideas.jsonl`. build_schedule delivers the current context brief safely through --brief-file; the engine pins it in judging_brief.txt and includes it in the judging-input digest. Round/probe blocks include the pinned brief, so judge prompts use that captured block rather than separately interpolating a changed context.brief. Register the child judge blocks in UNTRUSTED_OUTPUT_ROLES and nonce-fence the complete block, including the brief and candidate data.
- **Budgets** (re-pinned 2026-09-29): child `max_steps: 45` (per round: `next_round` + `judge_round` + `record_round` = 3 × 7 = 21, plus probe 3, plus ≈ 8 setup/finalize ≈ 32; FEAT-3585 no longer restarts the schedule mid-tournament, so 45 is a comfortable ceiling). Child `timeout: 1800` with matching state-level `timeout: 1800` on the parent `tournament` state (≈ 8 sequential judge calls of up to ≈ 3 min each ≈ 24 min worst case). **Judge-call overrun**: a judge call is not bounded by the child's *remaining* budget, so the child can end up to one call late; each judge state therefore carries `timeout: 300` (`JUDGE_CALL_TIMEOUT_S`) and the guard reserves it. Confirm the action-timeout path (`executor.py` action execution, `_wall_fallback`) with a `MockActionRunner` test before writing the routing. **Parent tail reserve**: the child is clamped to the parent's *remaining* budget (`executor.py:1353-1358`), and when the parent's own timeout fires (`executor.py:766-787`, `_finish("timeout")`) `salvage_tournament`, `portfolio`, the sinks and `finalize_*` never run. Size the parent `timeout` as at least `PRE_TOURNAMENT_WORST_S + TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + RETRY_SLEEP_RESERVE_S + TAIL_S`, with **5400** as a starting minimum (was 3600). Derive PRE_TOURNAMENT_WORST_S from declared prompt timeouts, up to nine lens visits, both transient retry budgets/backoffs and finite deterministic-action bounds; the earlier 1800 estimate is not authoritative. `TAIL_S >= 600` is the initial core reserve; its final value must cover the bounded actual sink/finalization work, including retries, per Runtime and tournament corrections. `check_floors --stage pre_tournament` takes `--elapsed-ms ${loop.elapsed_ms}` (the executor's active-time clock including the resume offset — a wall-clock `run_started_epoch` would overstate after a `spawn` handoff, pause/resume or sleep and false-fail healthy runs) and fails with `insufficient_time` when `PARENT_TIMEOUT_S − elapsed < TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + RETRY_SLEEP_RESERVE_S + TAIL_S` (a loud, early failure that keeps `ideas.jsonl`, instead of a silent no-report timeout). `PARENT_TIMEOUT_S`, `TOURNAMENT_TIMEOUT_S`, `JUDGE_CALL_TIMEOUT_S`, `RETRY_SLEEP_RESERVE_S`, `TAIL_S` are constants in the engine; a test asserts they match `brainstorm.yaml` (the derived parent timeout, baseline 5400, and tournament state `timeout: 1800`). FEAT-3596 verifies the core bound; optional children update their own bounds and ENH-3734 verifies the combined value.
- **Routing**: `on_yes` → `portfolio`; **`on_no`, `on_error` and `on_timeout`** (`extra_routes["timeout"]`) all → `salvage_tournament` (third review: a child that ends in a failure terminal after a judge-call error/429 must still salvage its completed rounds; `on_timeout` alone fires only when the child happens to be between states). `salvage_tournament` (engine `salvage`) rebuilds `tournament.json` from the rounds already in `tournament.jsonl`, counting only **complete rounds** (§ Schedule), with `partial: true` and `low_confidence: true`. **Salvage floor** = `max(1, min(3, rounds − 1))` complete rounds (`rounds` = N−1 for even N, N for odd), so N = 4 (3 rounds) can salvage after 2; fewer → `finalize_failed`. A timeout during the **probe phase** keeps the full round-robin ranking, sets `probe_incomplete: true` and `low_confidence: true`, and is **not** `partial`. `portfolio` copies `partial`/`probe_incomplete` into `portfolio.json`, and the report says so.
- **Schedule** (`build_schedule`, deterministic): circle-method round-robin over finalists indexed in **generation order** (idea ID) — never grid order. N even → N−1 rounds of N/2 pairs; N odd → a phantom player is added and its pair skipped (N rounds). `schedule.json` is `{judging_input_digest, rounds}`; rounds is a list of rounds, each an ordered list of pairs; even-N finalists play once per round; odd-N rounds include one bye, so partial salvage may have unequal games and is explicitly low-confidence. The schedule fixes the presentation order (`a` = shown first) using standard home/away alternation, so each finalist is shown first in ⌊(N−1)/2⌋ or ⌈(N−1)/2⌉ of its games — position bias is counterbalanced across the field rather than measured per pair. Within a round prompt the pair order is shuffled by a fixed seed (the round index) so pair position in the prompt is not correlated with seed order.
- **Scoring per pair**: the round call returns one JSON line per pair (`{pair: i, winner: "a"|"b"|null, rationale}`); a winner scores 1 / 0, and an abstention, missing pair, or malformed line scores 0.5 each, logged in `tournament.jsonl`. Each verdict carries a rubric-based `rationale` so the report can explain the ranking.
- **Abstention accounting** (new): `tournament.json` records `abstention_rate` = abstention rows / all unique committed main+probe rows, including missing/malformed/failed-proof rows but excluding unplayed salvage rounds. Valid probe disagreements are ties, not abstention rows (FEAT-3667 pins denominators and boundary behavior). `abstention_rate > 0.25` sets `low_confidence`; `abstention_rate > 0.5` makes `validate_portfolio` fail the run (no sink executes) — an all-abstain field would otherwise be ranked by generation order and reach the sinks as a "winner".
- **Probe** (position-sensitivity check): after the round-robin, take the top 3 by the ranking below and re-judge the ≤ 3 head-to-heads among them in the **reversed** presentation order in **one independent call** (the prompt contains no verdict from the round calls). For a probed pair: both orders agree → 1/0; orders disagree or either abstains → 0.5 each (replacing that pair's single-order score). Re-rank once; the probe set is not re-run.
- **Ranking** (`rank`): Copeland score (sum of pair scores) descending; ties → head-to-head result among the tied set (a mini-league over the pairs between tied players; a 2-way tie is decided by their direct result); still tied (a cycle, or all 0.5) → generation order, first-generated first. **Seed/grid order is never a tie-break.**
- **Judge reliability**: `tournament.json` records `tie_rate` = share of *probed* pairs whose two orders disagreed or abstained — a measure of position sensitivity where the podium is decided, not over all pairs. `low_confidence` is true when `tie_rate > 0.5`, **or** `abstention_rate > 0.25`, **or** the winner or runner-up slot was decided by the generation-order fallback; `partial: true` and `probe_incomplete: true` imply `low_confidence`. `portfolio` copies `tie_rate`, `abstention_rate`, `low_confidence`, `partial`, and `probe_incomplete` into `portfolio.json` and the report states them. FEAT-3596 reports `tie_rate` (with this definition) and `abstention_rate` in the old-vs-new comparison.
- **`tournament.json`**: `{ranking: [id], scores: {id: float}, tie_rate: float, abstention_rate: float, low_confidence: bool, partial: bool, probe_incomplete: bool, fallback_decided: bool}`.
- **Wildcard**: per the § Data Contract slot rules (differs from the winner on both axes; fallback flagged).

## Program Design

### Types

All symbols below live in `scripts/little_loops/brainstorm_engine.py` (importable, unit-tested directly) and are exposed through `python3 -m little_loops.brainstorm_engine <command>`.

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, lens_index: int, cell: [str, str] | None, off_grid: bool, grounded: bool | "unknown" | None, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `FinalistsFile`: `{finalists: [str], reserve: {str: [str]}, dropped: {str: str}, judge_mode: str, assets: dict}` — § Data Contract → Finalists file
- `PairVerdict`: `{pair: int, a: str, b: str, winner: str | null, probe: bool, round: int, rationale: str}` — `pair` is the pair index within the round (the upsert key with `round`/`probe`, matching `VERDICT_JSON`; added 2026-10-02 per FEAT-3667); `a` is the idea shown first; `winner: null` = abstention; `probe: true` = reversed-order re-judgment of a top-3 head-to-head; `round` is the schedule round (one LLM call per round)
- `Portfolio`: see § Data Contract

### Signatures

Engine signatures and command arguments are owned by FEAT-3667.

- `run_brainstorm_fixture(outputs: dict[str, str], tmp_path: Path) -> ExecutionResult` — YAML/executor test helper using FSMExecutor and MockActionRunner, not a second engine implementation.

 Consume `ingest_ideas` (lens record + watermark), `build_schedule(finalist_ids)`, `check_floors` (elapsed_ms), `rank`, `validate`, `portfolio`, `render_report` and `prompt_block` as defined there; do not maintain a second conflicting signature list in the YAML issue.

### Call Path

init (explicit-input preflight) -> resolve_profile (+ frame block) -> frame -> frame_apply -> pop_lens (+ diverge block) -> diverge -> ingest -> pop_lens ... -> dedup_block -> dedup -> collapse -> shortlist_block -> shortlist -> shortlist_apply -> check_floors (generation) -> check_floors_pre_tournament -> tournament -> [salvage_tournament, on child failure] -> portfolio -> render_report -> validate_portfolio -> route_sink -> verify_artifacts -> finalize_done

No optional states are pre-wired. Token aliases must map to actual orchestration states: collapse `shortlist` -> shortlist_block; generation check-floors `tournament` -> check_floors_pre_tournament; pre_tournament check-floors `tournament` -> tournament; portfolio `render` -> render_report. Later children add ground_codebase, materialize and premortem routes only when enabled. `check_floors --stage generation` may not jump straight to the child and bypass the elapsed-time guard.

### LLM-state pairing and step count (added 2026-09-30, fourth review)

A prompt state cannot run shell, so every LLM state that needs engine data is preceded by a shell state that captures the block on stdout. Proposed pairing (implementer confirms against the validator's capture-dominance and reachability rules; the fallback for any row is an explicit `<name>_block` state at +1 step):

| LLM state | Data block | Capturing shell state | Extra parent steps |
|---|---|---|---|
| `classify_mode` (FEAT-3583) | none (brief only) | — | 0 |
| `frame` | `prompt-block --kind frame` (profile lens catalog) | `resolve_profile` action also runs the `prompt-block` (its own stdout is an informational banner, not routed) | 0 |
| `diverge` | `prompt-block --kind diverge` | `pop_lens` action appends the `prompt-block` after a successful pop; the capture holds the lens line + block | 0 (an explicit per-lens `diverge_block` state would cost +L ≈ 9 — do not add one) |
| `dedup` | `prompt-block --kind dedup` | new `dedup_block` state, entered from the empty-queue `pop_lens` exit | +1 |
| `shortlist` | `prompt-block --kind shortlist` | new `shortlist_block` state | +1 |
| `judge_round` / `judge_probe` (child) | `next-round` / `probe-plan` stdout | `next_round` / `plan_probe` (child) | in the child's budget |
| `premortem_critic`/`premortem_defender` (FEAT-3586), `materialize_author`/`visual_canary` (FEAT-3585) | needs idea bodies / finalist list | each owning child pins either an engine block + capturing state (+1) or `Read` access to run-dir files under `scope:` (0) | owned by the child |

Enumerate every executed state on the nine-lens v1 path rather than relying on an estimate: each pop/diverge/ingest visit, the final empty pop, both block states, frame_apply/shortlist_apply, both floors, child call, report, validation, chosen sink and finalization. Assert the exact total in the end-to-end fixture. Core max_steps is 60; omit the deferred reframe visits. Optional children add their own exact increments in their enablement changes; ENH-3734 verifies the final cumulative bound.

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
| `scripts/little_loops/loops/brainstorm.yaml` | `frame` selects lenses; `pop_lens` queues them | preserved (lens queue feeds `diverge`; immutable ledger added; no reframe in v1) |
| `scripts/little_loops/loops/brainstorm.yaml` | `diverge` generates `ideas_per_round` ideas per lens | changed — sees running idea titles and per-cell occupancy (`diverge_state.md`) and tags a two-value `cell` from the profile's axis bins; a new per-lens `ingest` state assigns IDs and flags off-grid (per-idea `IdeaRecord` in `ideas.jsonl`) |
| `scripts/little_loops/loops/brainstorm.yaml` | `dedup_novelty` difflib dedup at `novelty_threshold` | dropped — replaced by `dedup`: an LLM pass over `{id, title, body excerpt}` emits duplicate groups, a script collapses each group to its first-generated member (per-cell representative selection is the separate `shortlist` step) |
| `scripts/little_loops/loops/brainstorm.yaml` | `saturation_gate` early exit after `max_saturation` zero-novel rounds | dropped — never fired in observed runs |
| `scripts/little_loops/loops/brainstorm.yaml` | `cluster` / `rank` single listwise LLM passes | changed — per-cell `shortlist`, a `check_floors` gate, then a round-robin pairwise `tournament` |
| `scripts/little_loops/loops/brainstorm.yaml` | `converge` synthesizes best-of hybrid | changed — `portfolio`; no unjudged hybrid in v1 (`synthesize=true` is rejected at preflight; synthesis is deferred) |
| `scripts/little_loops/loops/brainstorm.yaml` | `route_sink` + `sink_file`/`sink_issue`/`sink_decision` contract | preserved — sinks read `winners` from the portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` (a failing run can already create issues/decisions) | changed — `validate_portfolio` gates `route_sink`; no sink fires on an invalid run |
| `scripts/little_loops/loops/brainstorm.yaml` | `verify_artifacts` requires non-empty `brainstorm.md` | changed — still only checks `brainstorm.md` is non-empty (report integrity); the `min_ideas`/`min_cells` floors are enforced earlier by `check_floors` and by `validate_portfolio` (`final`) before any sink |
| `scripts/little_loops/loops/brainstorm.yaml` | `on_handoff: spawn`, `scope`, artifacts under `${context.run_dir}` | preserved |

### Files to Modify
- `scripts/little_loops/brainstorm_engine.py` — **new, owned by FEAT-3667** (this issue consumes it); `docs/reference/API.md` gains a `little_loops.brainstorm_engine` section (docs audience: cite the module, not `scripts/` paths)
- `scripts/little_loops/loops/brainstorm.yaml` — replace `frame`/`diverge`/`dedup_novelty`/`saturation_gate`/`cluster`/`rank`/`converge` with the new state graph (adds `ingest`, `check_floors` ×2, `salvage_tournament`, `render_report`), each script state a one-line engine-module call; tighten `verify_artifacts`; rewrite the `finalize_*` prompts; raise `timeout` to 5400; update `description:` and `context:` keys
- `scripts/little_loops/loops/brainstorm-tournament.yaml` — **new** child loop (round-robin tournament; see § Tournament Specification → Child loop); add to `test_builtin_loops.py` built-in set, `scripts/little_loops/loops/README.md`, and the `README.md` loop count (mirror `scripts/README.md`)
- `scripts/little_loops/fsm/fence.py` — UNTRUSTED_OUTPUT_ROLES entries for the child's captured judge blocks, including the immutable judging brief (no reframe in v1)

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `parse_tagged_json` / `queue_pop` — fragments to reuse for tagged-JSON extraction and lens/framing queues

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests (state graph, routing, wiring: each script state invokes `little_loops.brainstorm_engine`, and both `check_floors` states plus `validate_portfolio` pass a `--stage`)
- `scripts/tests/test_brainstorm_engine.py` — **new**; direct unit tests of the engine functions (no YAML extraction, no `_bash`)
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New engine unit tests: duplicate-group collapse (3 fixtures in § Acceptance Criteria) plus malformed-group fail-open, off-grid flagging and case/whitespace normalization, cap-selection at 9 occupied cells, wildcard slot rule and fallback, `ingest` ID assignment and `diverge_state.md` regeneration, `build_schedule` (every pair exactly once, every finalist once per round, first-position counts differ by ≤ 1, N odd/even, deterministic), `rank` (Copeland, head-to-head tie-break, 3-cycle → generation-order fallback, never grid order), probe rescoring (agree → 1/0, disagree → 0.5) and `tie_rate`/`low_confidence`, abstention scoring and the `abstention_rate` thresholds (> 0.25 → `low_confidence`; > 0.5 → `validate_portfolio` fails), `salvage_tournament` (floor `max(1, min(3, rounds − 1))`; N = 4 salvages after 2 rounds; probe-phase timeout → `probe_incomplete`, not `partial`), the `insufficient_time` guard at `pre_tournament`, blind re-tag (valid replaces, invalid keeps, `extra.orig_cell`), `check_floors` at all three stages (`generation`, `pre_tournament`, `final`) including a fixture where `finalists.json` shrinks below 2 between stages, `grounded: false` ideas excluded from `min_ideas`/`min_cells`/`shortlist`, cap-then-reserve ordering, `finalists.json` rewrite invariants (ids only move `finalists`→`dropped`, reserve promotion stays in-cell), null-winner rejected by `validate_portfolio`, dedup paraphrase-relabeled-into-empty-cell fixture

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions
- `README.md` — brainstorm mention (verify wording only)

### Configuration
- Context keys: add `mode` (default `artifact`), `min_ideas`, `min_cells`, `max_finalists` (all default `""` = inherit from the profile; the pinned numbers `12`/`4`/`8` live in the `artifact` profile — see § Data Contract), `synthesize`; change the existing `ideas_per_round` default from `"5"` to `""` (inherit; the profile carries `5`) so it does not silently beat profile values; remove `novelty_threshold`, `max_saturation`, `novelty_backend`, `top_k`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Fence registry: `scripts/little_loops/fsm/fence.py` `FENCE_ROLES` keys `("brainstorm.yaml", "frame")` and `("brainstorm.yaml", "diverge")` require the `<<<BRIEF … BRIEF>>>` fence in those prompt states; `KNOWN_UNFENCED_PROMPT_SITES` exempts `converge` and `finalize_done`. Any new state whose prompt interpolates `${context.brief}` (e.g. tournament judge; reframe is deferred) must be added to `FENCE_ROLES`, and a removed exempt state (`converge`) must leave `KNOWN_UNFENCED_PROMPT_SITES` — the fence completeness guard fails otherwise.
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
- **Step budget**: enumerate the actual nine-lens v1 path in the executor test, including final empty pop, all captured-block shell visits, init preflight, both floors, child invocation, report/validation and each sink/finalization branch. Core max_steps remains 60, child 45. Earlier rough 45/55 estimates and all-features ownership in FEAT-3596 are historical; ENH-3734 owns optional cumulative verification. Each optional child increases only its own measured/derived cost in the same change.

### Runtime and tournament corrections (2026-10-05)

- Init is create-if-absent and safe to re-enter after interruption; never truncate existing ideas/metadata/ledger/queue/report. A fresh run already has a fresh run_dir. Single-writer run artifacts are supported; validation-before-sinks does not imply exactly-once issue/decision effects across a manual replay.
- FEAT-3667 owns generation caps, off-grid re-tag recovery, write-once verdicts, judging-input digests and stable probe plans. Wiring fixtures exercise them through the real executor, including unchanged candidate IDs with changed brief/body/rubric, and child restart after committed rounds. Input conflicts fail the run; salvage may not rank stale verdicts against changed inputs.
- Child1800 is the binding elapsed-time bound; the sum of every judge call's maximum duration and retries can exceed it. The designed worst case is timeout -> salvage after sufficient complete rounds, or explicit failure below that floor. Budget fixtures verify recoverable exits and the reserved parent tail; do not promise a complete round-robin under every worst-case call duration.
- `next_round` and `plan_probe` require **evaluate: exit_code** with explicit 0/1/2 routes: next_round yes -> judge_round, no -> plan_probe, error -> the child failure terminal; plan_probe yes -> judge_probe, no -> rank (already committed), error -> child failure. `next:` plus `on_error:` is incorrect here because it treats normal queue exhaustion as error. A real executor fixture proves that a crash cannot masquerade as an exhausted schedule.
- Every child failure terminal is declared `failure: true`; otherwise a terminal named failed can still be reported as success. Child failure/runtime error/budget exhaustion all reach parent salvage. A salvage action error fails the run.
- A shell wrapper that combines queue_pop/resolve-profile with prompt-block propagates **each** command's status; a late successful block/echo must not hide an earlier failure. Preserve pop exit 1 versus missing-ledger/queue exit 2. No judge call occurs if data-block creation fails.
- All brainstorm prompt states set `max_rate_limit_retries: 0`, `rate_limit_max_wait_seconds: 0`, and `rate_limit_long_wait_ladder: [0]`, with exhaustion routed to their failure/skip path. The long-tier sleep occurs before the ordinary wait-budget check; without the third setting, the first 429 can still sleep 300 s. Current executor defaults otherwise sleep up to six hours (`executor.py:_handle_rate_limit`). This does not disable fixed API-error/infra retries: count their actual dispatches/state visits and backoffs in budget bounds. A fake-clock fixture verifies zero rate-limit sleeping, including the first long-tier attempt.
- With long waits disabled, the child may still overrun its timeout by the final judge call **plus one transient-handler backoff**. Add `RETRY_SLEEP_RESERVE_S = max(API error backoff, infra backoff)`, currently 30, to the pre_tournament guard and mirror-test: remaining >= child1800 + judge300 + retry_sleep30 + tail600 for the core. Keep child/state1800 and judge300; core parent5400/tail600 are starting minima. Derive the final tail/parent bound from the finite sink/finalize limits below and mirror constants in YAML/tests. Stub 429/API-error/infra-failure paths with a fake clock/sleep so pytest never waits.
- `record-round` validates each scheduled pair's identity/order, treats conflicting duplicates/missing/malformed outputs as explicit abstentions, and commits main rounds and the probe batch atomically. Replayed schedules/rounds/probe use FEAT-3667's persistence policy. rank's abstention/probe denominators and eligible-only distinct slots follow FEAT-3667 Additional validation contract; test N=2..8, odd/even bye rounds, reversed a/b mapping and partial salvage. For odd N a bye means unequal games in a partial set: only complete-round salvage is required, and its equal-game claim must not be made; low_confidence stays true.
- `synthesize=true` is rejected as unbuilt in v1; there is no deterministic specification for a useful hybrid and no budgeted hybrid LLM call. A later measured follow-up may add it without changing canonical ranked slots. Document this limitation rather than silently ignoring the request.
- Every core post-tournament prompt (sink_issue, sink_decision, finalize_done where still a prompt) has a finite declared action timeout and disabled rate-limit waits. Derive TAIL_S from the longest branch's actual invocation bound, including the existing two API-error and two infra retries/backoffs; one state timeout is not a bound on all retries. If the core tail600/parent5400 minima are insufficient, raise both deliberately and update guard/wiring tests before landing. Deterministic report/salvage/validation/sink_file overhead is included.
- `finalize_failed` is a **nonterminal** deterministic render-report --failed shell state with `next: failed` and `on_error: failed` (the FEAT-3667 flag-specific evaluator exception); every outcome reaches a separate actionless `failed` terminal with `failure: true`, never back to finalize_failed. `finalize_done` is likewise a nonterminal action followed by an actionless `done` terminal. The executor checks terminal before executing its action, so never attach report generation to a terminal; do not spend a final LLM call or rely on a prompt to preserve the failure report. finalize_done may summarize existing validated output, counts toward actual calls, and never overwrites brainstorm.md. The report stub tolerates missing optional/pre-init artifacts.

### Remaining implementation boundaries (2026-10-05)

- **Generation replay**: use FEAT-3667's peek/acknowledge contract. Tests interrupt after peek, block failure, idea publication and queue acknowledgement; test native resume as well as init re-entry during generation, repeated frame output and zero-valid-row ingestion. The queue must advance exactly once; unchanged shared queue_pop tests remain valid, while brainstorm's former destructive-pop assertions change.
- **Shell delivery**: one parameterized real-shell/executor fixture passes literal RAWEOF/PYEOF lines, quotes, `$()`, backticks and newlines in a captured payload, plus paths/overrides with shell metacharacters and an interpreter path containing spaces. The raw file preserves the payload, no sentinel command executes, and each engine argument remains one argument. Do not change the interpolation engine or add an exemption to the warning budget.
- **Pre-tournament duration**: every prompt, including frame/diverge/dedup/shortlist, declares a finite action timeout. Derive PRE_TOURNAMENT_WORST_S from actual visits (at most nine diverges) and FEAT-3667's attempt-bound helper, including both API and infra retry budgets/backoffs and deterministic-state bounds. The earlier 1800 estimate is not a bound. Choose finite prompt timeouts deliberately, publish the arithmetic, and size the parent timeout to cover that work plus child1800 + lastjudge300 + lastsleep30 + the separately derived tail. Mirror any final constants in the engine in this same change. Do not add per-lens runtime guard states or promise finalization after the executor's outer timeout.
- **Step exhaustion**: retain core max_steps60 and child45. Normal nine-lens visits must fit; transient retries also consume visits and can exhaust the cap. Set parent `on_max_steps: finalize_failed` so the deterministic failure report runs at the cap; child cap still routes to parent salvage. Fake-clock fixtures distinguish nominal completion, retry-triggered cap failure, child-timeout salvage and outer-timeout termination. The <=30-call evidence gate describes measured successful reference runs, not a guarantee that every retry pattern completes.
- **Merge evidence**: use EPIC-3581's single token-accounting definition and exact per-brief baseline totals. Input-context-only totals cannot serve as the denominator for a numerator that also includes output tokens.

## Implementation Steps

1. Define the idea record schema and grid-cell tagging contract.
2. Rewrite states per Expected Behavior; reuse `lib/common.yaml` fragments
   (`parse_tagged_json`, non-destructive local lens peek with queue_pop exit semantics).
3. _(Owned by FEAT-3667 — land it first.)_ Write `scripts/little_loops/brainstorm_engine.py` first (ingest, collapse, shortlist-apply, `check_floors(stage)`, schedule/rank/salvage, portfolio, validate) with `test_brainstorm_engine.py`, TDD; the YAML states are then one-line `"$${LL_PYTHON:-python3}" -m little_loops.brainstorm_engine …` calls. `check_floors` and `validate_portfolio` call the same function. Confirm the `-m` invocation resolves in a consuming project the way `autodev.yaml` `python3 -m little_loops.autodev_summary` does (runner-injected `LL_PYTHON=sys.executable` honored; an inherited value cannot replace it).
4. Tighten `verify_artifacts`; rewrite the `finalize_*` prompts (drop `ranked.md`/`clusters.md`/saturation references).
5. Update tests and the loop's description/docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Budget pinned (see Review Decisions); keep `test_max_steps_is_60` valid, add a test asserting the child tournament loop's `max_steps: 45`/`timeout: 1800`, the parent `tournament` state `timeout: 1800`, the parent derived timeout (baseline 5400) and judge-state `timeout: 300` (equal to the engine's `PARENT_TIMEOUT_S`/`TOURNAMENT_TIMEOUT_S`/`JUDGE_CALL_TIMEOUT_S`/`TAIL_S`), that the parent reaches the child via a `loop:` state, and that its `on_timeout` route reaches `salvage_tournament`
- Verify the child tournament loop's placement against loop discovery scanners and `ll-verify-package-data`
- Drop `top_k` from context and from `sink_decision`/`sink_issue` prompts; update `test_context_*` tests (floor/`max_finalists` knobs assert `""`, not the numbers)
- Wire `check_floors` twice (`generation` after `shortlist`, `pre_tournament` immediately before `tournament`); `shortlist` writes `finalists.json` per § Data Contract
- Add `little_loops.brainstorm_engine` to `docs/reference/API.md`; verify `ll-verify-package-data` (module ships with the package, no manifest edit expected)
- Update `scripts/tests/test_builtin_loops.py` fence/MR-11/heredoc-site/warning-budget assertions and `scripts/tests/data/loop_interpolation_baseline.json`
- Register tournament-judge captured blocks in fence.py UNTRUSTED_OUTPUT_ROLES; drop converge from KNOWN_UNFENCED_PROMPT_SITES
- Update `README.md:131` and mirror to `scripts/README.md`; add `CHANGELOG.md` entry under a concrete version (state that removed context keys are silently ignored, not rejected)
- Test engine logic by direct import (`test_brainstorm_engine.py`); YAML tests assert wiring only

## Impact

- **Priority**: P2 - core engine that FEAT-3583..3586 all depend on
- **Effort**: Medium - rewrites most states of one 459-line loop YAML and adds a child loop, but the engine module now lives in FEAT-3667 and this issue reuses `lib/common.yaml` fragments and existing sinks
- **Risk**: Medium - replaces the loop's core behavior; mitigated by `ll-loop validate brainstorm` and updated tests
- **Breaking Change**: Yes - drops the `novelty_threshold`, `max_saturation`, and `novelty_backend` context keys and changes `brainstorm.md` shape from best-of hybrid to portfolio

## Acceptance Criteria

- The Remaining implementation boundaries above have shell, native-resume and fake-clock fixtures; pre-tournament/parent bounds are derived rather than assumed, and actionless terminal/child-local failure routes are verified.
- The Runtime and tournament corrections above have wiring and real-executor fixtures, including exit-1 schedule exhaustion versus crash, explicit child failure terminals, mandatory pre_tournament guard, no six-hour retry inheritance, retry-sleep reserve, and odd-N salvage limitations.
- Lens ledger/IDs/phase and eligible-only portfolio integrity match the tested FEAT-3667 contract; synthesized/unbuilt requests fail preflight.
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
  round-batched pair verdicts are the LLM calls; the round-robin covers every finalist pair
  exactly once, with presentation order counterbalanced (first-position counts differ
  by ≤ 1); the top-3 head-to-heads are re-judged in reversed order in one independent
  batched call; every verdict carries a `rationale`.
- Round-robin schedule, Copeland ranking, head-to-head tie-break, generation-order
  fallback (never grid order), probe rescoring, and abstention scoring are covered by
  deterministic tests.
- A tournament timeout routes to `salvage_tournament`: at least `max(1, min(3, rounds − 1))` complete rounds yield a
  `partial: true`, `low_confidence: true` portfolio; fewer route to `finalize_failed`. A timeout in the probe phase yields `probe_incomplete: true` (not `partial`).
- `check_floors --stage pre_tournament` fails with `insufficient_time` when the remaining parent budget is below `TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + RETRY_SLEEP_RESERVE_S + TAIL_S` (kept: judge calls are **not** clamped to the remaining budget — `executor.py` falls back to the state/`default_timeout`/`_wall_fallback`, so a judge state without an explicit `timeout: 300` can run for up to an hour and break the tail reserve); a fixture proves the run fails before any judge call and `ideas.jsonl` survives.
- The tournament makes one judge call per **round** plus one probe call (≤ 8 calls for 8 finalists); `abstention_rate` is recorded, `> 0.25` sets `low_confidence`, and `> 0.5` makes `validate_portfolio` fail with no sink executed.
- Tournament failure routing: the parent `tournament` state's `on_no`, `on_error` and `on_timeout` all reach `salvage_tournament`; a fixture where a judge call errors after ≥ 3 complete rounds yields a `partial` portfolio, not `finalize_failed`. Judge states carry `timeout: 300` and the guard includes `JUDGE_CALL_TIMEOUT_S`.
- `brainstorm.md` is written only by `render_report`; a zero-content run never lets `sink_file` copy an empty report (`validate_portfolio` requires it non-empty).
- Every parent classify state calling `brainstorm_engine` lists its happy tokens and sets `_: finalize_failed`; child classify states (`record_round`, `record_probe`) send `fail`, `_` and `_error` to an actionless child terminal with `failure: true`, so parent routing can salvage. A wiring test checks targets within each loop (FEAT-3667 cannot enforce this since it changes no YAML); a fixture where the engine crashes with empty stdout lands in `finalize_failed`, and one where the engine prints a happy token and then crashes (trailing `fail`) routes to `finalize_failed`. Every LLM prompt state has `next:` + `on_error:` (or an explicit `evaluate:`) — asserted by a wiring test so no hidden evaluator call is added.
- Re-running `ingest` for a lens, `record-round`, or the child loop from `build_schedule` never double-counts verdicts or ideas.
- **Merge gate (before this issue's commit reaches `main`)**: `MockActionRunner` end-to-end runs (happy, floor-fail, child-timeout salvage, child-error salvage); one real run per pinned brief from the worktree with `PYTHONPATH=<worktree>/scripts` (the editable install otherwise resolves `main`'s package); the old-vs-new core comparison from FEAT-3596's baseline, **with the comparable metric/token/human evidence procedure defined in FEAT-3596 (the preserved baseline is already available), and a pass criterion**: on both pinned briefs the new winner **wins or ties a blind human A/B** against the old loop's top idea (both rendered in the same neutral title + body format so the comparison is actually blind), occupied cells ≥ the old loop's, retained duplicates ≤ the old loop's, ≤30 actual LLM calls, and total context tokens ≤1.5× the matching preserved old baseline (using EPIC-3581 § Comparable token gate (same formula, exact denominators, complete usage and retries)). Missing usage remains unverified, so the cost gate is enforced before this rewrite reaches main. The completed FEAT-3686 old tags are the starting point; blind evaluation of the new ideas uses the same definitions/duplicate criterion. Do not compare new self-tags to the old blind tags. The rewrite reaches `main` only after this passes (every project is `local-editable`; the quality risk lands with this issue, not with FEAT-3596). The loop keeps the name `brainstorm`. Also asserted by the merge-gate end-to-end test: the 9-lens happy-path parent step count equals the enumerated budget (§ Program Design → LLM-state pairing).
- Profile gates add no parent steps: `check_floors` and `portfolio` emit routing tokens, and there is no `*_gate` state.
- Off-grid cell values are flagged (after case/whitespace normalization) and excluded from `min_ideas`, `min_cells`, and `shortlist`.
- Malformed dedup output (unknown IDs, overlapping groups, unparseable text) never drops ideas.
- `portfolio.json` has a non-null `winner` and no `conceded` field; it carries `tie_rate`, `low_confidence`, and `partial`; `winners.md` lines carry a `role`; the report states the off-grid share; the wildcard differs from the winner on both axes or is flagged `wildcard_fallback`.
- The tournament child `brainstorm-tournament.yaml` has `max_steps: 45` and `timeout: 1800`, is reached via a `loop:` state whose parent state also carries `timeout: 1800`, and a child failure (`on_no`, `on_error`, `on_timeout`) routes to `salvage_tournament` (which itself routes to `finalize_failed` only below the salvage floor); the parent timeout is at least the 5400 baseline, raised if the derived pre- or post-tournament bound requires it. A wiring test asserts every judge state (`judge_round`, `judge_probe`) sets `timeout: 300`.
- Output `brainstorm.md` presents a portfolio + the grid map; `portfolio.json` is
  written for every successful run (failure has a stub report and partial artifacts, not a fabricated winner); `ideas.jsonl` records `id`, `cell`, `framing`, `lens` per
  idea.
- `ll-loop validate brainstorm` passes; artifacts only under `${context.run_dir}/`.
- Existing brainstorm tests updated; new dedup fixtures cover: distinct ideas that
  share a cell (both kept), paraphrases in different cells (collapsed), and a
  concise representative kept over a longer duplicate (first-generated wins), a
  paraphrase relabeled into an empty cell (collapsed via the body excerpt), and two ideas
  that share a framing but differ in mechanism (both kept).

## Review Decisions

_2026-10-05 implementation-boundary review; `/ll:advise` with claude-opus-5-5, confidence 0.78:_ Closed native-resume lens loss via peek/acknowledge, pinned printf/:shell transport and quoted interpreter tests, separated parent/child failure targets and nonterminal finalization, replaced assumed generation bounds with derived finite-timeout bounds, and specified deterministic parent step-cap reporting. Child overrun still reserves only one final action/sleep, since timeout is checked between retries.

_2026-10-05 follow-up review, `/ll:advise` with Opus (confidence 0.72):_ added the token cap to the pre-main merge gate, non-destructive init/restart fixtures and immutable judging-input/verdict/probe wiring; corrected the historical blanket claim that difflib never removes an idea. Child timeout/salvage is explicitly the worst-case behavior. No new live measurements or human A/B judgments were made.

_2026-10-05:_ reconciled active directives to the measured v1 scope (reframe/web deferred; four presets and engine owned by FEAT-3667). Closed concrete ledger, schedule/probe routing, failure-terminal, retry wait/backoff, and pre_tournament-bypass gaps. Historical decisions below explain earlier designs; current directive sections and FEAT-3667 own the implementation contract. Opus was unavailable due to an already-exhausted advisor budget.

_Added 2026-09-30 (FEAT-3686 spike results, `postmortems/brainstorm-spike/RESULTS.md`):_ **GO** — the grid, occupancy steering, blind re-tag and batched round judging (8 finalists) are validated on the two pinned briefs and stay as specified; this issue is unblocked once FEAT-3667 lands. Measured: steering lifts occupied cells +2 vs an unsteered control (6→7→9, 6→6→8) and generator self-tags overstate occupancy (claims 9, blind consensus 8–9), so the blind re-tag is load-bearing; batched round judging matches per-pair judging (τ 0.71, top-1 identical, swap-consistency 0.82, first-shown advantage ≈ 5–12 pp, so keep the counterbalanced schedule and the reversed probe). **Merge-gate baselines** (from `postmortems/brainstorm-spike/tags.jsonl` and RESULTS.md): old loop occupies **6** of 9 cells on both briefs; retains **5** (brief 1) and **≈ 19** (brief 2) redundant ideas under strict duplicate groups. The `dedup` prompt block takes a per-profile `duplicate_criterion` (FEAT-3667); the default "same underlying idea" wording is not enough for name-like ideas.

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus, structural/process pass; nothing measured):_
- **Spike dependency: FEAT-3686 (done).** The spike owned the common tagging pass and wrote the shared consensus tags (`postmortems/brainstorm-spike/tags.jsonl`) that the merge gate's "occupied cells" / "retained duplicates" comparison reads; this removes the earlier dependence on work owned by FEAT-3596 (which is itself blocked by this issue). A failing spike result changes this issue's contract (grid/re-tag/wildcard removed, or per-pair judging with `max_finalists` 6); apply the routing in FEAT-3686 § Outcomes and routing before starting.
- **`reframe` deferred to v2.** `BUILT_CAPABILITIES["reframe"] = {False}` (FEAT-3667): Expected Behavior 1's `reframe` state, `reframe_select`, and the `reframe` token from `frame_apply` are not built in v1; `frame_apply` always routes `pop_lens`. Supersedes the reframe wording in Expected Behavior 1, Call Path and the step budget (−1 LLM call and −2 steps when the profile would have enabled it).
- **Token ceiling.** The merge gate adds: total context tokens per brief ≤ 1.5× the old loop's baseline (≈ 880k per brief; the estimate is ≈ 22 calls × ≈ 63k ≈ 1.4M), on top of the ≤ 30-call ceiling. A run above it needs a documented reason or a cheaper design (smaller `dedup` excerpts, fewer lenses).
- **Rollback and migration.** The single commit must `git revert` cleanly (no partial renames, no data-file changes outside the commit). The CHANGELOG entry is a **breaking change** under a concrete version and states the removed keys are now ignored; additionally `init` emits a one-line warning when a removed context key (`novelty_threshold`, `max_saturation`, `novelty_backend`, `top_k`) is passed, so existing callers notice. Zero-idea silent success on the *old* loop is hotfixed separately in BUG-3688.
- **Import origin in run records.** Real merge-gate runs print `python3 -c 'import little_loops; print(little_loops.__file__)'` output into the run record, proving the worktree copy was used (`PYTHONPATH=<worktree>/scripts`).
- **Blind A/B is a smoke check.** One rater on n = 2 briefs cannot show significance; treat a tie-or-win as "no regression detected", not as proof of improvement, and say so in the record.

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

1. **Tournament as a sub-loop** — pairwise judging needs ≈ 8 batched calls (8 finalists; ≈ 31 before the 2026-09-29 batching, item 28) and ≈ 32 child steps; as parent states it would blow `max_steps: 60`. `loop:` states run a child executor and cost the parent one step (`executor.py:_execute_sub_loop`). Finalists capped at 8 (quadratic cost — never raised).
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
12. **Cap rule** — over-cap cells: drop lowest-occupancy first, ties by later grid order. _Superseded 2026-09-29 (item 33): ties by generation order of the cell's first idea, never grid order._
13. **Eligible floor vs concession** — _superseded 2026-09-29 (item 24): no concession exists._
14. **Child loop named** — `brainstorm-tournament.yaml`, `with:` bindings, `timeout: 1800` (raised to 2700, item 18; _superseded: 1800 again, item 28_), failure → `finalize_failed` (_superseded 2026-09-29, item 39: `on_no`/`on_error`/`on_timeout` → `salvage_tournament`_); off-grid normalization and dedup fail-open added.

_Added 2026-09-28 (second-opinion review, `/ll:advise` with Opus; nothing here has been measured):_

15. **Round-robin replaces Swiss** — 3 Swiss rounds over ≤ 8 finalists give ~3 comparisons each, do not order ranks 2–3 reliably (runner-up and wildcard depend on them), and tie-on-disagree turns position bias into ties so seed order decides. Round-robin: every finalist gets N−1 comparisons at ≈ Swiss's call count, with no pairing algorithm, byes, rematch handling, or Buchholz. Ranking = Copeland → head-to-head → generation order, **never grid/seed order** (grid order systematically favored low-index bins). Dissent recorded: if the judge proves order-consistent, Swiss + two orders would have been defensible; a cheaper middle path was Swiss with head-to-head + a decider call. Round-robin was preferred for simplicity and for ranking quality where slots are decided.
16. **Position bias: counterbalance, then probe** — one call per pair with presentation order counterbalanced across the field; only the top-3 head-to-heads are re-judged reversed. `tie_rate` therefore measures position sensitivity on the podium, and FEAT-3596 should measure it before any further format change.
17. **`check_floors` before `tournament`** — a doomed run (0 ideas, 1 finalist) must not spend judge calls or reach a 0/1-player tournament; one floor body is shared with `validate_portfolio`.
18. **Timeout headroom + salvage** — child `2700` (_superseded: 1800, item 28_), parent `5400`; a tournament `on_timeout` rebuilds a `partial` ranking from complete rounds (schedule is round-ordered so every finalist has equal games) instead of discarding them.
19. **Step budget re-pinned** — the per-lens `ingest` state (IDs, cell normalization, `diverge_state.md`) was uncounted; core ≈ 43 (was ≈ 32/33, an inconsistent pair); 2026-09-29 the second `check_floors` stage makes it ≈ 44. Render is folded into `ingest`.
20. **`reframe` scoring pinned** — LLM emits a 1–5 score per framing; script takes the top 3, ties by generation order. _Superseded 2026-09-29 (item 34): forced ranking, first 3._
21. **Dedup sees a body excerpt** — title-only dedup plus occupancy steering lets paraphrases be relabeled into empty cells, inflating `min_cells` and the finalist count.
22. **Minor** — off-grid share reported; `winners.md` lines carry `role`; runner-up "from a different cell" dropped from the Use Case (true by construction); `finalize_*` prompt rewrites are an explicit step.

_Added 2026-09-29 (EPIC-3581 second review, `/ll:advise` with Opus; nothing here has been measured):_

23. **Engine as a module, not inline YAML** — `scripts/little_loops/brainstorm_engine.py` holds ingest, collapse, shortlist, schedule, rank, salvage, portfolio, floors, validation (and, later, profile resolution, probes, annotation). YAML states are thin `"$${LL_PYTHON:-python3}" -m little_loops.brainstorm_engine <cmd>` calls (precedent: `autodev.yaml` → `little_loops.autodev_summary`). Removes the "shared script body" problem, most MR-11/`$${}` escaping and interpolation-baseline churn, and makes the Program Design signatures real, directly unit-testable symbols. Dissent recorded: logic no longer reads inline in `ll-loop show`; prompts stay in YAML.
24. **FEAT-3586 becomes annotate-only for v1** — nullable `winner`, `conceded`, the all-conceded validate path, the sink-skip branch, and post-`portfolio` slot recompute are removed from this contract. A P4 optional finisher should not add nullable-winner complexity to the P2 core before it is proven; a same-model defender supplies a mitigation almost every time, so script-determined concession rarely fired anyway. If demotion returns, it re-adds these fields in a follow-up with a concession signal that does not come from the defender.
25. **Floor gate re-run after filtering states** — `check_floors` runs at `generation` (after `shortlist`) and `pre_tournament` (after `ground_web`/`materialize`, before `tournament`); `validate_portfolio` runs `final`. FEAT-3584's "floor rechecked in `validate_portfolio`" would have allowed a 0/1-player tournament, contradicting item 17.
26. **`finalists.json` is a filter-pipeline contract** — `{finalists, reserve, dropped, judge_mode, assets}`, rewritten in place by every filtering state; the tournament judges only `finalists`. Order pinned: `dedup → ground_codebase → shortlist → check_floors(generation) → ground_web → materialize → check_floors(pre_tournament) → tournament`. `shortlist` excludes `grounded: false`, caps first, then fills `reserve`; floors count `grounded != false` ideas.
27. **Floor and knob defaults live in the profile** — context keys `min_ideas`/`min_cells`/`max_finalists` default to `""`; with non-empty context defaults FEAT-3583's "non-empty context overrides the profile" rule made every profile floor unlowerable.

_Added 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus; nothing here has been measured):_

28. **Per-round batched judging** — one judge call per round (N/2 disjoint pairs), one batched probe call: ≈ 8 calls instead of ≈ 31, cutting wall-clock (31 serial sessions ≈ 23–50 min against a 2700 s timeout) and the ≈ 94k-token per-session overhead. Dissent recorded: the judge sees the other pairs in its round (possible anchoring); the probe remains an independent call and FEAT-3596 measures `tie_rate`/`abstention_rate` before any further format change. Child `max_steps: 45`, `timeout: 1800`.
29. **Parent tail reserve** — a child clamped to the parent's remaining budget plus a parent timeout at the top of its loop (`executor.py:766-787`) skipped `salvage_tournament`, `portfolio`, sinks and `finalize_*`. Parent `timeout` 5400 = pre-tournament worst 1800 + tournament 1800 + tail 600 + headroom; `check_floors --stage pre_tournament` fails `insufficient_time` early instead of a silent no-report timeout.
30. **Split** — the engine module, its tests, the CLI contract, `resolve-profile` and `artifact.json` moved to **FEAT-3667**; this issue is the loop side, landed as one commit. Rationale: one change of 14 commands + most of a 459-line loop + a new child loop + ~10 rewritten tests is too large to land safely, and a half-landed rewrite breaks every `local-editable` project.
31. **Gates fold into engine tokens** — `check_floors` and `portfolio` print the next-state token; there are no `ground_gate`/`materialize_gate`/`premortem_gate` states, so a disabled feature costs zero parent steps.
32. **Abstention accounting** — `abstention_rate` in `tournament.json`/`portfolio.json`; `> 0.25` → `low_confidence`, `> 0.5` → `validate_portfolio` fails. Previously an all-abstain field was ranked by generation order and still reached the sinks.
33. **Cap tie-break by generation order** — grid order was the bias Review Decision 15 banned from ranking; it is banned from the cap rule too.
34. **`reframe` forced ranking** — independent 1–5 self-scores tie; the LLM returns framings best-first and the script takes the first 3.
35. **Blind cell re-tag in `dedup`** — the generator's own cell tag under occupancy steering is a self-claim; the dedup call re-tags cells without seeing the originals so `min_cells` and the diversity metric are not gameable. Original tag kept in `extra.orig_cell`.
36. **Salvage edge cases** — floor `max(1, min(3, rounds − 1))` (N = 4 has 3 rounds and could never salvage under a fixed floor of 3); a probe-phase timeout is `probe_incomplete`, not `partial`.
37. **`grounded` is a top-level optional field** (not `extra.grounded`) so floors and FEAT-3584 agree; `evidence`/`touchpoints`/`creates` stay in `extra`.
38. **Precedent corrections** — `autodev.yaml` uses a plain `python3 -m`; `$${LL_PYTHON:-python3}` (exported as `sys.executable`) is used with heredocs elsewhere, and `LL_PYTHON` + `-m` needs a smoke test; there is no `<state>_output.txt` capture. Removed context keys (`novelty_threshold`, `max_saturation`, `novelty_backend`, `top_k`) are **silently accepted** by `--context` (`context_seed.py`), so the CHANGELOG entry must say they are now ignored, not rejected.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus; nothing measured):_

39. **Tournament failure routing** — `on_no`/`on_error`/`on_timeout` → `salvage_tournament`; judge states `timeout: 300`; guard adds `JUDGE_CALL_TIMEOUT_S`. Confirm the action-timeout path with a `MockActionRunner` test first (Opus did not verify `_wall_fallback`).
40. **`render_report` owns `brainstorm.md`** — `converge` was the only writer and `init` empties the file; without an owner `sink_file` would copy an empty report.
41. **Active-time clock** — `--elapsed-ms ${loop.elapsed_ms}` instead of wall-clock `run_started_epoch`.
42. **Classify safety** — `fail` token, explicit happy tokens, `_: finalize_failed`.
43. **Idempotent state** — child/lens state is not resumed (`active_sub_loop` is observability-only); appends become upserts; framings sanitized.
44. **Prompt data via stdout blocks** inside fences; no `round_prompt.txt`; profiles carry `lenses`.
45. **No hidden LLM calls** — `next:` + `on_error:` on every prompt state.
46. **Merge gate, name kept** — Dissent recorded: shipping as `brainstorm-next` removes the local-editable blast radius entirely, but fence/baseline/test/README keys are filename-keyed so the rename would repeat that churn; the worktree real-run gate gives most of the protection.
47. **Scope cuts** — `ground_web` (FEAT-3584) and the `fallback_html` mid-tournament restart (FEAT-3585) are out of v1; `reserve` stays in the `finalists.json` schema (default `0`) for the web follow-up.

_Added 2026-09-30 (EPIC-3581 fourth review, `/ll:advise` with Opus; nothing measured; findings spot-checked against `executor.py`/`evaluators.py`):_

48. **Capability allowlist** — FEAT-3583 ships presets that name unbuilt features (`visual` `materialize=render`, `functional` `ground=codebase`+`premortem=true`, `business` `premortem=true`); the engine would print `materialize`/`premortem`/`ground_codebase` routing tokens into states that do not exist (`ll-loop validate` rejects the route, so it cannot be pre-wired) and a run would fail after ~13 calls (visual) or after the whole tournament (functional/business). `resolve-profile` now rejects any value outside `BUILT_CAPABILITIES` before any LLM call; each optional child widens it and flips its preset knob when it lands (FEAT-3667 § Capability allowlist).
49. **`frame-apply`** — the reframe skip (the default path) had no owner and no route; `lenses.txt` pinned to `lens_index|framing|lens`.
50. **Gate tokens** — `collapse` emits `ground_codebase|shortlist` (a `check_floors` token cannot gate a state that runs before `shortlist`); `portfolio` emits `premortem|render|fail`; state `check_floors_final` renamed `check_floors_pre_tournament`.
51. **Prompt-block delivery is a counted state pairing** (§ Program Design → LLM-state pairing) instead of an assertion; the step count is enumerated and asserted in the merge-gate end-to-end test. Opus's zero-step shared-capture scheme is unverified against the validator; explicit `*_block` states are the fallback.
52. **Blind A/B moves into this issue's merge gate** with a pass criterion (see Acceptance Criteria); the shortlist call (one batched listwise pick that discards most ideas) is the likeliest place for a quality regression, so the A/B is judged on the winner, not on mechanism metrics.
53. **`insufficient_time` guard kept** — `executor.py` judge-call timeout is `state.timeout or default_timeout or _wall_fallback`, not clamped to the parent's remaining budget; a wiring test asserts every judge state sets `timeout: 300`.
54. **Stale text fixed**: child failure → `salvage_tournament` (AC), guard formula includes `JUDGE_CALL_TIMEOUT_S`, `verify_artifacts` parity row, decisions 14/18 marked superseded.
55. **Grid contract checked and left alone** — with `min_cells: 4` the tournament always sees 4–8 finalists; the both-axes wildcard is guaranteed once ≥ 6 cells are occupied (a winner's row and column cover only 5), so the `wildcard_fallback` flag can only fire at 4–5 occupied cells. Watch in the A/B that the tournament is ranking cell champions, not ideas.

The two Confidence Check concerns below (unpinned defaults, `max_steps`) are resolved by items 2, 7, and 19; re-run `/ll:confidence-check` — the scores below predate the round-robin rewrite (items 15–22) and the 2026-09-29 contract changes (items 23–47).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Confidence Check Notes

Historical score; not re-run after this review. Cached frontmatter scores were cleared on 2026-10-05 because contracts changed; re-run confidence-check against the revised issue and landed prerequisites before implementation.

_Added by `/ll:confidence-check` on 2026-10-02 (re-scored after the FEAT-3667 split, batched judging, `PairVerdict.pair`, and the classify-route `_` acceptance criterion). Supersedes the 2026-09-29 notes (95/70)._

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override; raw tier would be PROCEED WITH CAUTION)
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Program Design, claim, parity, structure, decision, and learning-test gates are clean (`stale_file_ref` flags only the not-yet-created `brainstorm_engine.py`, which FEAT-3667 owns).
- Spec text is internally inconsistent on `reframe`: Expected Behavior 1, Call Path, and the Proposed Solution still describe `reframe`/`reframe_select`, while Review Decisions (2026-09-30) defer `reframe` to v2 (`BUILT_CAPABILITIES["reframe"] = {False}`; `frame_apply` always routes `pop_lens`). Implementer must follow the Review Decision.
- `format-check` reports `soft_dep_hard_edge: FEAT-3667` — the dependency is genuinely hard here (engine module must exist first), so the edge is correct; the lint is advisory.
- The parent step budget (≈ 45-50 of `max_steps: 60`) is an estimate to be recounted and asserted in the merge-gate end-to-end test.

### Gaps to Address
- **Unresolved `blocked_by`: FEAT-3667 (open)** — `brainstorm_engine.py`, the CLI contract, `resolve-profile`, and `artifact.json` do not exist yet, so every YAML state in this issue has nothing to call. Land FEAT-3667 first, then re-run `/ll:confidence-check`. (FEAT-3686, the spike, is completed/GO.)

### Outcome Risk Factors
- **Deep per-site complexity (Complexity 5/25)**: rewrites most of a 459-line loop, adds a new child loop, and touches the fence registry, interpolation baseline, README counts, and ~10 existing tests across 6-15 sites — expect iteration on validator warnings (MR-10/MR-11, warning budget).
- **Change surface (18/25)**: the `context:` key removals and `winners.md` schema mapping ripple into sinks, docs, and FEAT-3583..3586.
- **Ambiguity (20/25)**: the `reframe` v1/v2 text conflict above, plus judge rubric and `diverge` prompt wording left to the implementer.
- **Merge gate**: single-commit rewrite of a loop that every `local-editable` project runs; the blind A/B, token ceiling, and worktree real-run gates must pass before the commit reaches `main`.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Profile data vs FEAT-3667: the four preset JSONs (`artifact`, `visual`, `functional`, `business`) ship in FEAT-3667 with unbuilt knobs off; this issue owns only the state wiring that calls `resolve_profile`. "Ships with the built-in `artifact` profile only" is superseded; brief 2's `mode=functional` merge gate depends on the FEAT-3667 presets.

**Note** (added by `/ll:audit-issue-conflicts`): Init preflight vs FEAT-3583: this issue owns wiring `resolve-profile --validate-only` into `init` for explicit modes/knobs; FEAT-3583 only adds the auto-only `classify_mode` branch after that preflight.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-06T17:22:35 - `41577712-f527-4990-b326-7134aa659541.jsonl`
- Implementation-boundary review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.78; issue updates only) - 2026-10-05
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:27 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- `/ll:confidence-check` - 2026-10-03T03:33:35 - `7cd57e8e-71e0-4299-a1a4-ccd6bda98ee6.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 review follow-up: PairVerdict.pair, classify-route test) - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:03 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
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
