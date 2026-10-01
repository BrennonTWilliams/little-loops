---
id: FEAT-3667
type: FEAT
title: 'Brainstorm engine module: deterministic core, CLI contract, and artifact profile'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T17:40:21Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
blocks:
- FEAT-3582
- FEAT-3583
- FEAT-3596
confidence_score: 94
outcome_confidence: 82
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 24
relates_to:
- FEAT-3686
---

# FEAT-3667: Brainstorm engine module: deterministic core, CLI contract, and artifact profile

## Summary

Implement `scripts/little_loops/brainstorm_engine.py` and `scripts/tests/test_brainstorm_engine.py` — the pure-Python deterministic core of the EPIC-3581 brainstorm engine — **before and independently of** the loop rewrite. No YAML changes. FEAT-3582 (loop rewrite, tournament child loop, wiring, docs) is blocked by this issue and consumes the CLI contract below.

_Split from FEAT-3582 on 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus). FEAT-3582's § Data Contract, § Tournament Specification and § Program Design remain the **spec of record**; this issue implements them and owns the CLI contract table._

## Current Behavior

`brainstorm.yaml` embeds its only deterministic logic (difflib dedup, saturation counter) as inline Python heredocs. No importable brainstorm module exists.

## Expected Behavior

- `little_loops.brainstorm_engine` exposes every function in FEAT-3582 § Program Design and the CLI commands below, invoked as `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <cmd> --run-dir DIR ...` (`LL_PYTHON` is exported as `sys.executable` by `fsm/runners.py`, so the idiom is robust in consuming projects).
- Includes `render-report`, `prompt-block`, `resolve-profile` and the built-in `artifact` profile JSON (with a `lenses` catalog) (`scripts/little_loops/loops/brainstorm-profiles/artifact.json`) so the loop rewrite and FEAT-3583 never re-touch these.
- Everything is unit-tested by direct import, test-first; nothing here depends on the FSM executor.
- Landing this issue changes no user-visible behavior (the module is unused until FEAT-3582), so it is safe to merge to `main` on its own.

### CLI contract

All commands: `python3 -m little_loops.brainstorm_engine <cmd> --run-dir DIR [args]`. **Exit 0** = success; **exit 1** = domain violation (floors/validation/invalid profile; violations listed on stderr, one per line); **exit 2** = crash or usage error (never used for a domain result). LLM output reaches the module only as a file (`--*-file`). Commands that route print their **routing token as the last stdout line**.

**Routing-token safety** (2026-09-29, third review): FSM `evaluate: classify` reads stdout only and ignores exit codes, so an engine crash with empty stdout would silently follow the `_` default. Therefore every routed command (a) prints the literal token `fail` as its last stdout line on exit 1 **and** exit 2 (best effort on crash, via a top-level `try/finally` in `main`), (b) documents its happy tokens explicitly, and (c) is wired with `_: finalize_failed` (never a happy-path default) on every classify state. A test asserts each routed command prints `fail` on a forced violation and on a forced exception.

**Idempotency** (2026-09-29): child-loop and per-lens state is not resumed (`active_sub_loop` is observability-only), so a re-run must never double-count. `record-round` upserts by `(round, pair, probe)`; `next-round` skips rounds already recorded in `tournament.jsonl`; `ingest` replaces all ideas of the same lens index instead of appending (lens identity is the `lens_index` field of each `lenses.txt` line — `lens_index|framing|lens`, assigned once by `frame-apply` — not the lens text and not the line number, since `pop_lens` deletes lines as it pops; idea IDs are allocated monotonically from the highest existing id and **never reused**, so a replaced lens's old ids are retired and generation order stays numeric id order); `collapse` and `shortlist-apply` are pure rewrites. Framings written to `lenses.txt` are sanitized (`|` and newlines replaced by a space).

**Prompt blocks** (2026-09-29): YAML prompts can only interpolate `${context.*}`/`${captured.*}`, so commands that feed an LLM state print the data block **to stdout** (the state captures it and interpolates it inside a `<<<…>>>` fence). The instructions stay in the YAML; the engine never writes a whole prompt file. Untrusted text (briefs, idea titles/bodies, framings) is only ever emitted inside the block.

| Command | Args | Reads | Writes | Stdout token |
|---|---|---|---|---|
| `resolve-profile` | `--mode M` `--set key=value`… (empty = inherit) `--decision-file F` (optional classifier output) | `brainstorm-profiles/*.json` | `profile.json` (incl. `overridden`, clamped `max_finalists`) | the `Mode: <x> (…)` banner line (informational, not routed); **exit 1 before any LLM call** when a mode or knob value is invalid **or names a capability not yet built** (see § Capability allowlist) |
| `frame-apply` | `--raw-file F` | `profile.json` | `lenses.txt` (`lens_index\|framing\|lens`; empty framing; sanitized), `diverge_state.md` | `reframe` \| `pop_lens` (from `profile.json` `reframe`); `fail` on violation |
| `reframe-select` | `--raw-file F` | `profile.json`, `lenses.txt` | `lenses.txt` (fills the framing field round-robin), `diverge_state.md` | count |
| `ingest` | `--raw-file F` `--lens-index N` | `profile.json`, `ideas.jsonl` | `ideas.jsonl` (replace-by-lens-index, idempotent), `diverge_state.md` | ideas added |
| `collapse` | `--groups-file F` | `ideas.jsonl`, `profile.json` | `ideas.jsonl`, `dedup.log` (fail-open; kept count, re-tag agreement rate, pre/post cell occupancy) | `ground_codebase` \| `shortlist` (from `profile.json` `ground`); `fail` on violation |
| `shortlist-apply` | `--picks-file F` | `ideas.jsonl`, `profile.json` | `finalists.json`, `shortlist.json` | finalists count |
| `check-floors` | `--stage generation\|pre_tournament\|final` `--elapsed-ms N` (pre_tournament; from `${loop.elapsed_ms}`) | ideas, finalists, profile | — (violations on stderr) | next-state token from the profile (`materialize` \| `tournament`; `ok` at `final`; `ground_web` is deferred, see EPIC-3581); `fail` on violation |
| `build-schedule` | — | `finalists.json` | `schedule.json` (rounds → ordered pairs) | round count |
| `next-round` | — | `schedule.json`, `tournament.jsonl`, `finalists.json`, `profile.json` | `round_current.json`; **stdout = the pair block + rubric** (captured by `judge_round`) | exit 1 = no rounds left (queue-pop semantics) |
| `record-round` | `--verdicts-file F` | `round_current.json`, `finalists.json` | `tournament.jsonl` (upsert by round+pair+probe) | `ok` \| `fail` |
| `probe-plan` | — | `tournament.jsonl` | `round_current.json`; stdout = reversed top-3 head-to-head pair block | pair count |
| `rank` | — | `tournament.jsonl` | `tournament.json` | — |
| `salvage` | — | `tournament.jsonl`, `schedule.json` | `tournament.json` (`partial`) | exit 1 = below salvage floor |
| `portfolio` | `--synthesize` | `tournament.json`, `ideas.jsonl` | `portfolio.json`, `winners.md` | `premortem` \| `render` \| `fail` |
| `validate` | — | portfolio, ideas, finalists, profile, `brainstorm.md` | — | `ok` \| `fail` |
| `render-report` | `--failed` (optional: stub mode for `finalize_failed`) | `profile.json`, `ideas.jsonl`, `finalists.json`, `shortlist.json`, `tournament.json`, `portfolio.json`, `premortem.json`?, `materialize.json`?, `dedup.log`? | `brainstorm.md` (**the only writer**, incl. the `--failed` stub; `init` empties it) | `ok` \| `fail` |
| `prompt-block` | `--kind frame\|diverge\|dedup\|shortlist\|reframe` | `profile.json`, `ideas.jsonl`, `diverge_state.md` | — (block on stdout: lens catalog, axes/bins, extra fields, rubric, occupancy, idea list) | — |

**Input file formats** (pinned 2026-09-29; tagged NDJSON — one JSON object per line prefixed by the tag, other lines ignored, malformed lines skipped and counted, never fatal):

| File (`--*-file`) | Tag and line shape |
|---|---|
| `reframe-select --raw-file` | `FRAMING_JSON: {"framing": "How might we …"}` — in ranked order, best first |
| `ingest --raw-file` | `IDEAS_JSON: {"title": str, "body": str, "cell": [bin_a, bin_b], "extra": {…}?}` |
| `collapse --groups-file` | `DUP_GROUPS_JSON: [["i003", "i007"], …]` and optional `RETAG_JSON: {"i001": [bin_a, bin_b], …}` |
| `shortlist-apply --picks-file` | `PICKS_JSON: {"<bin_a>\|<bin_b>": "i012", …}` — one id per multi-idea cell |
| `record-round --verdicts-file` | `VERDICT_JSON: {"pair": int, "winner": "a" \| "b" \| null, "rationale": str, "seen": [str, str]?}` — one per pair; `seen` only in image mode |

**Evaluator per command** (2026-09-30 fourth review): classify-routed (stdout token, `_: finalize_failed`, print `fail` on exit 1 **and** 2): `frame-apply`, `collapse`, `check-floors`, `record-round`, `portfolio`, `validate`, `render-report`. Exit-code-routed (`next:` + `on_error:`, or `evaluate: exit_code`; exempt from the print-`fail` rule because the exit code *is* the route): `resolve-profile`, `reframe-select`, `ingest`, `shortlist-apply`, `build-schedule`, `next-round` (exit 1 = no rounds left), `probe-plan`, `rank`, `salvage` (exit 1 = below salvage floor), `prompt-block`. Each CLI-table row is tested against this list.

**Capability allowlist** (2026-09-30 fourth review): `resolve-profile` holds a module constant `BUILT_CAPABILITIES` (v1 = `{"ground": {"none"}, "materialize": {"none"}, "premortem": {False}, "reframe": {False}}`; `reframe` narrowed to `{False}` by the 2026-09-30 fifth review — see Review Decisions), and rejects (exit 1, violation on stderr, before any LLM call) any profile or override value outside it — including explicit overrides like `materialize=render`. FEAT-3584/3585/3586 each widen it in the same change that lands their states, and flip their preset knob (FEAT-3583 § Pinned Preset Contents). This is what keeps shipped presets from emitting a routing token (`materialize`, `premortem`, `ground_codebase`) whose target state does not exist yet.

**Prompt-block delivery** (2026-09-30 fourth review): a prompt state cannot run shell, so every LLM state that needs a data block is preceded by a shell state that captures `prompt-block --kind <k>` (or `next-round`/`probe-plan`) stdout. This issue pins only the command side (which `--kind`s exist); the state-by-state pairing table and the resulting parent step count are owned by FEAT-3582 § Program Design.

Rows are **frozen once FEAT-3582 merges**; until then this review's amendments may still change them, and later children only add commands (`probe-anchor`, `materialize-check`, `annotate`). `render-report` is owned here: `brainstorm.md` has exactly one writer (including the `--failed` stub `finalize_failed` calls) and later children extend its sections (gallery, risks, grounding flags) by adding inputs, not by writing the file. Report contents: mode header (`Mode: <x> (auto, confidence <c>) — rerun with mode=<y> to override`), portfolio (`output_shape` picks the layout; `grid` adds the grid map), off-grid share, dropped cells, `tie_rate`/`abstention_rate`/`low_confidence`/`partial`/`probe_incomplete`/`wildcard_fallback`, `grounded: unknown` flags, re-tag agreement rate and pre/post cell occupancy from `dedup.log` (a blind re-tagger drifting to middle bins would otherwise silently shrink `min_cells`), and optional gallery/risks sections when their inputs exist. The zero-idea and failure paths still get a stub report from `finalize_failed`, which calls `render-report --failed`.

## Use Case

**Who**: The maintainer implementing EPIC-3581, and later the agent implementing FEAT-3582 who needs a stable, tested engine to call from YAML.

**Context**: The brainstorm rewrite has ~14 deterministic operations (ingest, dedup collapse, shortlist, round-robin schedule, ranking, salvage, floors, portfolio, validation). Written inline in YAML they cannot be unit-tested and drift between the `check_floors` and `validate_portfolio` copies.

**Goal**: Have every deterministic operation as an importable, directly unit-tested function behind a documented CLI, before any loop YAML changes.

**Outcome**: `python -m little_loops.brainstorm_engine <cmd>` implements the full CLI contract; FEAT-3582 reduces to thin YAML calls.

## Program Design

All symbols live in `scripts/little_loops/brainstorm_engine.py` and are exposed through `python3 -m little_loops.brainstorm_engine <command>`; the full types, the tournament/floor/portfolio semantics and the remaining signatures are the spec of record in FEAT-3582 § Program Design and § Data Contract.

### Types

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, cell: [str, str] | None, off_grid: bool, grounded: bool | "unknown" | None, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `FinalistsFile`: `{finalists: [str], reserve: {str: [str]}, dropped: {str: str}, judge_mode: str, assets: dict}`
- `PairVerdict`: `{a: str, b: str, winner: str | null, probe: bool, round: int, rationale: str}`
- `Profile`: `{mode: str, lenses: [str] (per-profile lens catalog; `frame` reads it), reframe: bool, min_ideas: int, min_cells: int, max_finalists: int, ideas_per_round: int, reserve: int, axes: [Axis, Axis] (each `Axis` = `{name, bins: [str], definitions: {bin: one-line str}}`; definitions mandatory), duplicate_criterion: str (printed by `prompt-block --kind dedup`), extra_fields: [str] (profile-specific idea fields under `extra`; `prompt-block --kind diverge` prints them), ground: "none" | "codebase", materialize: str, rubric: str, premortem: bool, output_shape: str, overridden: [str]}` — knob values outside `BUILT_CAPABILITIES` fail `resolve-profile` (§ Capability allowlist)

### Signatures

- `main(argv: list[str] | None = None) -> int` — the `python -m` entry point; one `argparse` subparser per command in the CLI contract table; returns 0 / 1 / 2 per the exit-code contract
- `check_floors(ideas: list[IdeaRecord], finalists: FinalistsFile, profile: Profile, stage: str) -> list[str]` — returns the violations (empty = pass); the single function behind `check-floors` and `validate`
- `ingest_ideas(raw: str, ideas: list[IdeaRecord], profile: Profile) -> list[IdeaRecord]` — assigns stable IDs, normalizes and validates cells, flags `off_grid`
- `build_schedule(finalists: list[IdeaRecord]) -> list[list[tuple[str, str]]]` — deterministic circle-method round-robin as a list of rounds
- `render_report(run_dir: Path) -> str` — deterministic `brainstorm.md` renderer behind `render-report`
- `prompt_block(kind: str, run_dir: Path) -> str` — data block for an LLM state, behind `prompt-block` and the `next-round`/`probe-plan` stdout
- `rank(verdicts: list[PairVerdict], finalists: list[IdeaRecord]) -> list[str]` — Copeland score, then head-to-head, then generation order
- `resolve_profile(mode: str, overrides: dict[str, str], decision: dict | None) -> Profile` — base profile from `mode`, non-empty overrides win, empty string inherits

### Call Path

`pop_lens` -> `diverge` -> `main` -> `ingest_ideas` -> `check_floors` -> `build_schedule` -> `rank` -> `render_report` -> `verify_artifacts`

## Motivation

The 2026-09-29 review found FEAT-3582 too large to implement safely as one change (new 14-command module + rewrite of most of a 459-line loop + a new child loop + ~10 rewritten tests + registry/baseline/README/CHANGELOG/docs), and repo history shows large issues repeatedly ending a session mid-implementation. A half-landed loop rewrite on `main` breaks brainstorm in every `local-editable` project. The pure-Python core has no such hazard and can be built test-first.

## Proposed Solution

Follow FEAT-3582 § Implementation Steps step 3 (module first, TDD). Build in this order: `Idea`/`Finalists` I/O and `check_floors` → `ingest` → `collapse` → `shortlist-apply` → `build_schedule`/`next-round` → `record-round`/`rank`/`probe-plan`/`salvage` → `portfolio`/`validate` → `resolve-profile` + `artifact.json`.

Rules pinned by the review (also reflected in FEAT-3582's spec):

- **Cap tie-break** (over-`max_finalists` cells) drops the lowest-occupancy cell, ties by **generation order of the cell's first idea** — never grid order.
- **Salvage floor** = `max(1, min(3, rounds − 1))` complete rounds (`rounds` = N−1 for even N, N for odd); N = 4 has 3 rounds so it can salvage after 2. A timeout during the probe phase keeps the full round-robin ranking, sets `probe_incomplete` and `low_confidence`, and is **not** `partial`.
- **Abstention**: `tournament.json` and `portfolio.json` carry `abstention_rate` (share of pair verdicts that abstained or failed proof). `> 0.25` sets `low_confidence`; `> 0.5` fails `validate` (no sink runs).
- **Cell re-tag**: `collapse --groups-file` accepts an optional `RETAG_JSON` block (`{id: [axis1_bin, axis2_bin]}`) produced by a dedup call that never saw the original tags; a valid on-grid re-tag replaces `cell` (original kept in `extra.orig_cell`), an invalid one keeps the original.
- **`reframe-select`**: the LLM returns framings in **ranked order** (best first, a forced ranking, not independent 1–5 scores that will tie); the script takes the first 3.
- **`grounded`** is a top-level optional `IdeaRecord` field (`true` | `false` | `"unknown"`; absent = unverified, counted as not-false). `evidence`/`touchpoints`/`creates` live in `extra`.
- **Time guard**: `check-floors --stage pre_tournament` also fails with the violation `insufficient_time` when `PARENT_TIMEOUT_S − elapsed < TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + TAIL_S` (`JUDGE_CALL_TIMEOUT_S = 300`: a judge call is not bounded by the child's remaining budget, so the child can overrun by one call) (`elapsed` from `--elapsed-ms ${loop.elapsed_ms}` — the executor's active-time clock incl. the resume offset, `fsm/executor.py` `elapsed_offset_ms`; **never** a wall-clock epoch, which overstates after a `spawn` handoff, pause/resume or sleep; `PARENT_TIMEOUT_S` mirrors `brainstorm.yaml` `timeout`, asserted equal by a test in FEAT-3582). See FEAT-3582 § Tournament Specification → Budgets.

## Integration Map

### Files to Modify
- `scripts/little_loops/brainstorm_engine.py` — new
- `scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.json` — new (`.json` so unfiltered `rglob("*.yaml")` scanners never read it); all four ship here with unbuilt knobs (`ground`, `materialize`, `premortem`, `reframe`) off, per FEAT-3583 § Shipped vs target. Axes/bins are provisional until FEAT-3686 reports; FEAT-3583 adds only the classifier, overrides and tuning
- `docs/reference/API.md` — `little_loops.brainstorm_engine` section (docs audience: cite the module, not `scripts/` paths)

### Tests
- `scripts/tests/test_brainstorm_engine.py` — new; the full list in FEAT-3582 § Integration Map → Tests, plus: CLI exit-code contract (0/1/2) per command, the `fail` token on a forced violation **and** a forced exception for every routed command, idempotency (re-running `ingest`/`record-round`/`next-round` never double-counts; salvage's round count is unchanged), framing sanitization (`|`, newline), `render-report` golden fixtures (grid/portfolio/winner_risks shapes, partial/low-confidence flags, missing optional inputs), prompt-block content and fencing, `insufficient_time` guard driven by `--elapsed-ms` (incl. the `JUDGE_CALL_TIMEOUT_S` term), salvage-floor arithmetic (N = 2..8), abstention thresholds, re-tag fallback, cap tie-break by generation order, `reframe-select` forced-ranking parse
- **Executor smoke test** (2026-09-30 fourth review; a test, not a gate): a throwaway loop YAML defined inside the test (never a shipped loop) run through the real executor, whose shell states call `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine check-floors …` from a non-repo cwd. It proves the `$${}` escaping, that `LL_PYTHON` + `-m` resolves, and that the `fail` token and empty-stdout crash route through the real `classify` evaluator to `_`. This is the only in-scope way to de-risk the idiom before FEAT-3582, since this issue changes no YAML.
- CLI-table conformance: every command's evaluator class matches § Evaluator per command; `resolve-profile` rejects `materialize=render`, `ground=codebase`, `premortem=true` while `BUILT_CAPABILITIES` excludes them; `frame-apply` routes `reframe` \| `pop_lens` and writes empty framings when `reframe` is off; `collapse` emits `ground_codebase` \| `shortlist`; ids are never reused on re-ingest; `render-report --failed` writes the stub; `collapse` records re-tag agreement and occupancy in `dedup.log`
- `ll-verify-package-data` must pass (module and `brainstorm-profiles/` ship with the package; `pyproject.toml` includes `little_loops/**`)

### Dependent Files
- FEAT-3582 (consumes the CLI contract), FEAT-3583/3584/3585/3586 (add commands)

## Implementation Steps

1. Write `test_brainstorm_engine.py` fixtures first (FEAT-3582 § Integration Map → Tests, plus the FEAT-3667 additions), then implement in the order given in Proposed Solution.
2. Define the CLI contract: one `argparse` subparser per command in the table, exit-code discipline (0/1/2), routing token as the last stdout line.
3. Add `resolve-profile` and `artifact.json`; run `ll-verify-package-data`, `ruff check`, `ruff format` (changed files only), `mypy`, and the full pytest suite.

## Impact

- **Priority**: P2 - first link of the EPIC-3581 chain; FEAT-3582 is blocked by it
- **Effort**: Medium - one new module, one JSON profile, one test file
- **Risk**: Low - unused until FEAT-3582; no behavior change
- **Breaking Change**: No

## Acceptance Criteria

- `render-report` is the only writer of `brainstorm.md`; routed commands print `fail` on any non-zero exit; appends are idempotent.
- Every command in the CLI contract table exists with the documented args, files, exit codes and stdout token, covered by direct-import and `python -m` subprocess tests.
- All floors, schedule, ranking, probe, salvage, abstention, wildcard and dedup fixtures listed in FEAT-3582 pass.
- No YAML file is modified; `python -m pytest scripts/tests/` and `ll-verify-package-data` pass; `ruff` and `mypy` clean for the new module.
- `docs/reference/API.md` documents the module.
- The executor smoke test passes (`$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine` through the real classify evaluator, incl. the empty-stdout crash → `_`); each command's evaluator class matches § Evaluator per command; `resolve-profile` enforces `BUILT_CAPABILITIES`; `frame-apply` and `render-report --failed` exist; ids are never reused on re-ingest.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- Program Design gate initially failed (section missing); a `## Program Design` section was added and the gate now passes.
- Input-file schemas for the five `--*-file` arguments were unpinned; a table was added (2026-09-29), lifting Ambiguity from 18 to 22.
- The `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine` idiom has no in-repo precedent (only `python3 -m` in `autodev.yaml`, `$${LL_PYTHON}` with heredocs elsewhere). Smoke-test one command through `ll-loop run` early.
- `stale_file_ref` flags on the three new files are expected until they exist.

### Outcome Risk Factors
- **Complexity (16/25)**: 14 commands in one module with cross-command file contracts; mitigated by test-first order and a pinned CLI table.
- **Ambiguity (22/25)**: remaining judgement calls are prompt wording (FEAT-3582) and profile bin names (FEAT-3583); neither blocks this issue.

## Review Decisions

_Added 2026-09-30 (FEAT-3686 spike results, `postmortems/brainstorm-spike/RESULTS.md`; measured on 2 baseline briefs, 160 calls):_ **GO — the "held until FEAT-3686 reports" gate on the grid-dependent commands is lifted; build them as specified**, with these amendments: (1) every profile axis carries a one-line **definition per bin** and `prompt-block` prints them (blind tagging agreed only 0.51–0.67 on bin names alone, 0.62–0.83 with definitions); (2) `Profile` gains `duplicate_criterion`, printed by `prompt-block --kind dedup` (the default "same underlying idea" prompt gave precision 0.63 on names; a strict criterion gave 1.0/1.0); (3) `functional.json` `approach` bins/definitions are provisional until re-measured (per-axis agreement 0.72 < 0.75; FEAT-3583 owns the re-measure); (4) `cell` stays nullable as defence, but the grid is not dropped. Expect **6–9 finalists**, not always 8: the old loop's ideas occupy only 6 of 9 cells; steered runs reach 8–9.

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus, structural/process pass; nothing measured):_
- **Spike gate (FEAT-3686).** The grid-dependent parts of this module — `ingest` cell normalization/`off_grid`, `collapse` re-tag, `shortlist-apply`, `check-floors` `min_cells`, the wildcard slot in `portfolio`, and the grid map in `render-report` — are **held until FEAT-3686 reports** (a failing grid result removes them from the contract). `cell` is therefore `[str, str] | None` in `IdeaRecord`. The grid-independent commands (`IdeaRecord`/`FinalistsFile` I/O, `check-floors` idea/finalist floors, `build-schedule`, `next-round`, `record-round`, `rank`, `probe-plan`, `salvage`, `validate`, `render-report` skeleton, `prompt-block`, the executor smoke test) may start in parallel with the spike. If the batched-judge row fails, `next-round`/`build-schedule` emit one pair per call and `max_finalists` is lowered to 6.
- **All four preset JSONs ship here** (unbuilt knobs off) so FEAT-3582's brief-2 merge gate runs `mode=functional` rather than the artifact axes; FEAT-3583 no longer introduces preset files.
- **`reframe` deferred to v2.** `BUILT_CAPABILITIES["reframe"] = {False}`: the `reframe` state and `reframe-select` are not built in v1 (`frame-apply` always takes the empty-framing path); an explicit `reframe=true` fails at `resolve-profile`. The `reframe-select` row and its tests are superseded until the follow-up brings measurements.
- **Import-origin guard.** The executor smoke test and `test_brainstorm_engine.py` assert `little_loops.__file__` resolves inside the checkout under test and pass `PYTHONPATH` through to the subprocess (`LL_PYTHON` = `sys.executable`). Verify gates already inject the worktree `PYTHONPATH` (`worktree_utils.py`), so a worktree run before this module is on `main` fails loudly with `ModuleNotFoundError`; after it lands, a run without `PYTHONPATH` would silently import `main`'s copy, which the guard catches.

_Added 2026-09-30 (EPIC-3581 fourth review, `/ll:advise` with Opus; nothing measured):_ `frame-apply` added (the reframe-skip path — the **default** for `artifact` — had no command writing empty-framing `lenses.txt` lines and no route around `reframe`); `lenses.txt` pinned to `lens_index|framing|lens` (the two prior spellings, `framing|lens_index` here and `framing|lens` in FEAT-3582, disagreed and neither survives `pop_lens` deleting lines); `collapse` prints the `ground_codebase|shortlist` token (FEAT-3584's gate cannot be `check_floors`, which runs after `shortlist`); `portfolio`'s happy token renamed `validate` → `render` (it routes to `render_report`, not `validate_portfolio`); `render-report --failed` keeps a single writer; `BUILT_CAPABILITIES` allowlist in `resolve-profile`; evaluator classes pinned; freeze rule loosened to "once FEAT-3582 merges"; ids never reused; smoke test added to this issue's tests; re-tag agreement/occupancy logged.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus; nothing measured):_ `render-report` and `prompt-block` added (no owner existed for `brainstorm.md` or for profile data reaching prompts); `fail` routing token on every routed command; idempotent appends keyed by round/pair/lens index; `--elapsed-ms` replaces `run_started_epoch`; `JUDGE_CALL_TIMEOUT_S` added to the time guard; `record-round`'s `fallback_html` token removed with FEAT-3585's restart; `lenses` added to `Profile`; `ground` type narrowed to `none | codebase`.

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:26 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:confidence-check` - 2026-09-29T20:35:46 - `c1a7470e-ae08-48cc-8ac1-d91f782a8804.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue owns `Profile`/`Axis`, the four preset JSONs, and the override-aware `resolve_profile` (precedence tests live here). FEAT-3583 adds only the classifier, override plumbing, `mode` default flip, and tuning. `reframe` is deferred to v2 (`BUILT_CAPABILITIES` pins `reframe: {False}`); ground/materialize/premortem are owned by EPIC-3687.
