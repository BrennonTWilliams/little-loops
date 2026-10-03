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
relates_to:
- FEAT-3686
confidence_score: 90
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3667: Brainstorm engine module: deterministic core, CLI contract, and artifact profile

## Summary

Implement `scripts/little_loops/brainstorm_engine.py` and `scripts/tests/test_brainstorm_engine.py` — the pure-Python deterministic core of the EPIC-3581 brainstorm engine — **before and independently of** the loop rewrite. No YAML changes. FEAT-3582 (loop rewrite, tournament child loop, wiring, docs) is blocked by this issue and consumes the CLI contract below.

_Split from FEAT-3582 on 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus). FEAT-3582's § Data Contract, § Tournament Specification and § Program Design remain the **spec of record**; this issue implements them and owns the CLI contract table._

## Current Behavior

`brainstorm.yaml` embeds its only deterministic logic (difflib dedup, saturation counter) as inline Python heredocs. No importable brainstorm module exists.

## Expected Behavior

- `little_loops.brainstorm_engine` exposes every function in FEAT-3582 § Program Design and the CLI commands below, invoked as `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <cmd> --run-dir DIR ...` (`LL_PYTHON` is exported as `sys.executable` by `fsm/runners.py`, so the idiom is robust in consuming projects).
- Includes `render-report`, `prompt-block`, `resolve-profile` and all four built-in preset JSONs (`artifact`, `visual`, `functional`, `business`, each with a `lenses` catalog and per-bin axis definitions; unbuilt knobs off) under `scripts/little_loops/loops/brainstorm-profiles/`, so the loop rewrite and FEAT-3583 never re-touch these.
- Everything is unit-tested by direct import, test-first; nothing here depends on the FSM executor.
- Landing this issue changes no user-visible behavior (the module is unused until FEAT-3582), so it is safe to merge to `main` on its own.

### CLI contract

All commands: `python3 -m little_loops.brainstorm_engine <cmd> --run-dir DIR [args]`. **Exit 0** = success; **exit 1** = negative domain outcome (a violation: floors/validation/invalid profile, listed on stderr one per line; or, for exit-code-routed commands, a result such as "no rounds left" / "below salvage floor"); **exit 2** = crash or usage error (never used for a domain result). LLM output reaches the module only as a file (`--*-file`). Commands that route print their **routing token as the last stdout line**.

**Routing-token safety** (2026-09-29, third review): FSM `evaluate: classify` reads stdout only and ignores exit codes, so an engine crash with empty stdout would silently follow the `_` default. Therefore every routed command (a) prints the literal token `fail` as its last stdout line on exit 1 **and** exit 2 (best effort on crash, via a top-level `try/finally` in `main`, with argparse's `SystemExit(2)` handled inside that try), (b) documents its happy tokens explicitly, and (c) is wired with `_: finalize_failed` (never a happy-path default) on every classify state. A test asserts each routed command prints `fail` on a forced violation and on a forced exception.

**Token ordering and atomicity** (2026-10-02 Opus review): an empty stdout is already caught by `_: finalize_failed`; the trailing `fail`'s real job is overriding a *happy token printed before a late crash* (e.g. `collapse` prints `shortlist`, then dies writing `dedup.log`; `classify` reads the last non-empty line). So every routed command prints its happy token as its **last statement, after all file writes**, and writes files as tmp + `os.replace`. The guarantee that every classify state calling the engine routes `_` to `finalize_failed` lives in FEAT-3582's YAML and cannot be enforced here (this issue changes no YAML); it is a FEAT-3582 follow-up (see Dependent Files).

**Idempotency** (2026-09-29): child-loop and per-lens state is not resumed (`active_sub_loop` is observability-only), so a re-run must never double-count. `record-round` upserts by `(round, pair, probe)` and always writes **every scheduled pair of the round**, a missing or malformed verdict becoming an explicit abstention row, so a round is atomic (recorded = all pairs present) and `next-round` skipping and salvage's "complete rounds" agree; `next-round` skips rounds already recorded in `tournament.jsonl`; `ingest` replaces all ideas of the same lens index instead of appending (lens identity is the `lens_index` field of each `lenses.txt` line — `lens_index|framing|lens`, assigned once by `frame-apply` — not the lens text and not the line number, since `pop_lens` deletes lines as it pops; idea IDs are allocated from a persisted high-water mark (`next_id` in the sidecar `ideas.meta.json`, written atomically with `ideas.jsonl` via tmp + `os.replace`) and **never reused**; "highest existing id" alone cannot guarantee this, because replacing the lens that owned the top ids lowers the max and the next ingest would reuse them. A replaced lens's old ids are retired and generation order is numeric id order; a replace therefore sorts the new ideas after all existing ones, so it changes generation order versus a clean run and the cap tie-break depends on whether a retry happened. Accepted and documented); `collapse` and `shortlist-apply` are pure rewrites. **Phase guard:** `ingest` records the stage in `ideas.meta.json` and exits 1 once `collapse` has run (a later ingest would mix pre- and post-dedup ideas). Framings written to `lenses.txt` are sanitized (`|` and newlines replaced by a space).

**Prompt blocks** (2026-09-29): YAML prompts can only interpolate `${context.*}`/`${captured.*}`, so commands that feed an LLM state print the data block **to stdout** (the state captures it and interpolates it inside a `<<<…>>>` fence). The instructions stay in the YAML; the engine never writes a whole prompt file. Untrusted text (briefs, idea titles/bodies, framings) is only ever emitted inside the block.

| Command | Args | Reads | Writes | Stdout token |
|---|---|---|---|---|
| `resolve-profile` | `--mode M` `--set key=value`… (empty = inherit; values are coerced **before** the `BUILT_CAPABILITIES` check: bool knobs accept only `true`/`false`, int knobs must parse, an unknown key exits 1) `--decision-file F` (optional classifier output) | `brainstorm-profiles/*.json` | `profile.json` (incl. `overridden`, clamped `max_finalists`) | the `Mode: <x> (…)` banner line (informational, not routed); **exit 1 before any LLM call** when a mode or knob value is invalid **or names a capability not yet built** (see § Capability allowlist) |
| `frame-apply` | `--raw-file F` | `profile.json` | `lenses.txt` (`lens_index\|framing\|lens`; empty framing; sanitized), `diverge_state.md` | `pop_lens` (v1: `reframe` is pinned off; the `reframe` token branch is v2, see appendix); `fail` on violation |
| `ingest` | `--raw-file F` `--lens-index N` | `profile.json`, `ideas.jsonl` | `ideas.jsonl` (replace-by-lens-index, idempotent), `ideas.meta.json` (`next_id`, stage), `diverge_state.md` | ideas added |
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
| `prompt-block` | `--kind frame\|diverge\|dedup\|shortlist` (`reframe` is v2) | `profile.json`, `ideas.jsonl`, `diverge_state.md` | — (block on stdout: lens catalog, axes/bins, extra fields, rubric, occupancy, idea list) | — |

**Input file formats** (pinned 2026-09-29; tagged NDJSON — one JSON object per line prefixed by the tag, other lines ignored, malformed lines skipped and counted, never fatal):

| File (`--*-file`) | Tag and line shape |
|---|---|
| `ingest --raw-file` | `IDEAS_JSON: {"title": str, "body": str, "cell": [bin_a, bin_b], "extra": {…}?}` |
| `collapse --groups-file` | `DUP_GROUPS_JSON: [["i003", "i007"], …]` and optional `RETAG_JSON: {"i001": [bin_a, bin_b], …}` |
| `shortlist-apply --picks-file` | `PICKS_JSON: {"<bin_a>\|<bin_b>": "i012", …}` — one id per multi-idea cell |
| `record-round --verdicts-file` | `VERDICT_JSON: {"pair": int, "winner": "a" \| "b" \| null, "rationale": str, "seen": [str, str]?}` — one per pair; `seen` only in image mode |

**Evaluator per command** (2026-09-30 fourth review): classify-routed (stdout token, `_: finalize_failed`, print `fail` on exit 1 **and** 2): `frame-apply`, `collapse`, `check-floors`, `record-round`, `portfolio`, `validate`, `render-report`. Exit-code-routed (`next:` + `on_error:`, or `evaluate: exit_code`; exempt from the print-`fail` rule because the exit code *is* the route): `resolve-profile`, `ingest`, `shortlist-apply`, `build-schedule`, `next-round` (exit 1 = no rounds left), `probe-plan`, `rank`, `salvage` (exit 1 = below salvage floor), `prompt-block`. Each CLI-table row is tested against this list.

**Capability allowlist** (2026-09-30 fourth review): `resolve-profile` holds a module constant `BUILT_CAPABILITIES` (v1 = `{"ground": {"none"}, "materialize": {"none"}, "premortem": {False}, "reframe": {False}}`; `reframe` narrowed to `{False}` by the 2026-09-30 fifth review — see Review Decisions), and rejects (exit 1, violation on stderr, before any LLM call) any profile or override value outside it — including explicit overrides like `materialize=render`. FEAT-3584/3585/3586 each widen it in the same change that lands their states, and flip their preset knob (FEAT-3583 § Pinned Preset Contents). This is what keeps shipped presets from emitting a routing token (`materialize`, `premortem`, `ground_codebase`) whose target state does not exist yet.

**Prompt-block delivery** (2026-09-30 fourth review): a prompt state cannot run shell, so every LLM state that needs a data block is preceded by a shell state that captures `prompt-block --kind <k>` (or `next-round`/`probe-plan`) stdout. This issue pins only the command side (which `--kind`s exist); the state-by-state pairing table and the resulting parent step count are owned by FEAT-3582 § Program Design.

Rows are **frozen once FEAT-3582 merges**; until then this review's amendments may still change them, and later children only add commands (`probe-anchor`, `materialize-check`, `annotate`). `render-report` is owned here: `brainstorm.md` has exactly one writer (including the `--failed` stub `finalize_failed` calls) and later children extend its sections (gallery, risks, grounding flags) by adding inputs, not by writing the file. Report contents: mode header (`Mode: <x> (auto, confidence <c>) — rerun with mode=<y> to override`), portfolio (`output_shape` picks the layout; `grid` adds the grid map), off-grid share, dropped cells, `tie_rate`/`abstention_rate`/`low_confidence`/`partial`/`probe_incomplete`/`wildcard_fallback`, `grounded: unknown` flags, re-tag agreement rate and pre/post cell occupancy from `dedup.log` (a blind re-tagger drifting to middle bins would otherwise silently shrink `min_cells`), and optional gallery/risks sections when their inputs exist. The zero-idea and failure paths still get a stub report from `finalize_failed`, which calls `render-report --failed`.

## v2 appendix (not in the v1 contract)

Moved here 2026-10-02 so the CLI table and its "each row is tested" rule cover v1 only. The follow-up that builds reframe restores these:

- CLI row: | `reframe-select` (**v2, not built here**; see Review Decisions) | `--raw-file F` | `profile.json`, `lenses.txt` | `lenses.txt` (fills the framing field round-robin), `diverge_state.md` | count |
- Input format row: | `reframe-select --raw-file` | `FRAMING_JSON: {"framing": "How might we …"}` — in ranked order, best first |
- `prompt-block --kind reframe`, and `frame-apply`'s `reframe` routing token (from `profile.json` `reframe`); both unreachable while `BUILT_CAPABILITIES["reframe"] == {False}`.

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
- `PairVerdict`: `{pair: int, a: str, b: str, winner: str | null, probe: bool, round: int, rationale: str}` (`pair` is the upsert key with `round`/`probe`; FEAT-3582 § Data Contract must add it too)
- `Profile`: `{mode: str, lenses: [str] (per-profile lens catalog; `frame` reads it), reframe: bool, min_ideas: int, min_cells: int, max_finalists: int, ideas_per_round: int, reserve: int, axes: [Axis, Axis] (each `Axis` = `{name, bins: [str], definitions: {bin: one-line str}}`; definitions mandatory), duplicate_criterion: str (printed by `prompt-block --kind dedup`), extra_fields: [str] (profile-specific idea fields under `extra`; `prompt-block --kind diverge` prints them), ground: "none" | "codebase", materialize: str, rubric: str, premortem: bool, output_shape: str, overridden: [str]}` — knob values outside `BUILT_CAPABILITIES` fail `resolve-profile` (§ Capability allowlist)

### Signatures

- `main(argv: list[str] | None = None) -> int` — the `python -m` entry point; one `argparse` subparser per command in the CLI contract table; returns 0 / 1 / 2 per the exit-code contract
- `check_floors(ideas: list[IdeaRecord], finalists: FinalistsFile, profile: Profile, stage: str, elapsed_ms: int | None = None) -> list[str]` — returns the violations (empty = pass); the single function behind `check-floors` and `validate`; `elapsed_ms` is required at `stage == "pre_tournament"` (drives the `insufficient_time` guard) and ignored otherwise
- `ingest_ideas(raw: str, ideas: list[IdeaRecord], profile: Profile) -> list[IdeaRecord]` — assigns stable IDs, normalizes and validates cells, flags `off_grid`
- `build_schedule(finalist_ids: list[str]) -> list[list[tuple[str, str]]]` — deterministic circle-method round-robin over `FinalistsFile.finalists` (idea IDs) as a list of rounds
- `render_report(run_dir: Path, failed: bool = False) -> str` — deterministic `brainstorm.md` renderer behind `render-report`; `failed=True` renders the `--failed` stub used by `finalize_failed`
- `prompt_block(kind: str, run_dir: Path) -> str` — data block for an LLM state, behind `prompt-block` and the `next-round`/`probe-plan` stdout
- `rank(verdicts: list[PairVerdict], finalists: list[IdeaRecord]) -> list[str]` — Copeland score, then head-to-head, then generation order
- `resolve_profile(mode: str, overrides: dict[str, str], decision: dict | None) -> Profile` — base profile from `mode`, non-empty overrides win, empty string inherits

### Call Path

`main` -> `ingest_ideas` -> `check_floors` -> `build_schedule` -> `rank` -> `render_report`

## Motivation

The 2026-09-29 review found FEAT-3582 too large to implement safely as one change (new 14-command module + rewrite of most of a 459-line loop + a new child loop + ~10 rewritten tests + registry/baseline/README/CHANGELOG/docs), and repo history shows large issues repeatedly ending a session mid-implementation. A half-landed loop rewrite on `main` breaks brainstorm in every `local-editable` project. The pure-Python core has no such hazard and can be built test-first.

## Proposed Solution

Follow FEAT-3582 § Implementation Steps step 3 (module first, TDD). Build in this order: `Idea`/`Finalists` I/O and `check_floors` → `ingest` → `collapse` → `shortlist-apply` → `build_schedule`/`next-round` → `record-round`/`rank`/`probe-plan`/`salvage` → `portfolio`/`validate` → `resolve-profile` + the four preset JSONs.

Rules pinned by the review (also reflected in FEAT-3582's spec):

- **Cap tie-break** (over-`max_finalists` cells) drops the lowest-occupancy cell, ties by **generation order of the cell's first idea** — never grid order.
- **Salvage floor** = `max(1, min(3, rounds − 1))` complete rounds (`rounds` = N−1 for even N, N for odd); N = 4 has 3 rounds so it can salvage after 2. A timeout during the probe phase keeps the full round-robin ranking, sets `probe_incomplete` and `low_confidence`, and is **not** `partial`.
- **Abstention**: `tournament.json` and `portfolio.json` carry `abstention_rate` (share of pair verdicts that abstained or failed proof). `> 0.25` sets `low_confidence`; `> 0.5` fails `validate` (no sink runs).
- **Cell re-tag**: `collapse --groups-file` accepts an optional `RETAG_JSON` block (`{id: [axis1_bin, axis2_bin]}`) produced by a dedup call that never saw the original tags; a valid on-grid re-tag replaces `cell` (original kept in `extra.orig_cell`), an invalid one keeps the original.
- **`reframe-select`** (_v2, deferred: not built in this issue; kept as the follow-up's spec_): the LLM returns framings in **ranked order** (best first, a forced ranking, not independent 1–5 scores that will tie); the script takes the first 3.
- **`grounded`** is a top-level optional `IdeaRecord` field (`true` | `false` | `"unknown"`; absent = unverified, counted as not-false). `evidence`/`touchpoints`/`creates` live in `extra`.
- **Time guard**: `check-floors --stage pre_tournament` also fails with the violation `insufficient_time` when `PARENT_TIMEOUT_S − elapsed < TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + TAIL_S` (`JUDGE_CALL_TIMEOUT_S = 300`: a judge call is not bounded by the child's remaining budget, so the child can overrun by one call) (`elapsed` from `--elapsed-ms ${loop.elapsed_ms}` — the executor's active-time clock incl. the resume offset, `fsm/executor.py` `elapsed_offset_ms`; **never** a wall-clock epoch, which overstates after a `spawn` handoff, pause/resume or sleep; `PARENT_TIMEOUT_S` mirrors `brainstorm.yaml` `timeout`, asserted equal by a test in FEAT-3582). See FEAT-3582 § Tournament Specification → Budgets.

## Integration Map

### Files to Modify
- `scripts/little_loops/brainstorm_engine.py` — new
- `scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.json` — new (`.json` so unfiltered `rglob("*.yaml")` scanners never read it); all four ship here with unbuilt knobs (`ground`, `materialize`, `premortem`, `reframe`) off, per FEAT-3583 § Shipped vs target. Axes/bins are provisional until FEAT-3686 reports; FEAT-3583 adds only the classifier, overrides and tuning
- `docs/reference/API.md` — `little_loops.brainstorm_engine` section (docs audience: cite the module, not `scripts/` paths)

### Tests
- `scripts/tests/test_brainstorm_engine.py` — new; the full list in FEAT-3582 § Integration Map → Tests, plus: CLI exit-code contract (0/1/2) per command, the `fail` token on a forced violation **and** a forced exception for every routed command, idempotency (re-running `ingest`/`record-round`/`next-round` never double-counts; salvage's round count is unchanged), framing sanitization (`|`, newline), `render-report` golden fixtures (grid/portfolio/winner_risks shapes, partial/low-confidence flags, missing optional inputs), prompt-block content and fencing, `insufficient_time` guard driven by `--elapsed-ms` (incl. the `JUDGE_CALL_TIMEOUT_S` term), salvage-floor arithmetic (N = 2..8), abstention thresholds, re-tag fallback, cap tie-break by generation order (no `reframe-select` tests: v2)
- **Executor smoke test** (2026-09-30 fourth review; a test, not a gate): a throwaway loop YAML defined inside the test (never a shipped loop) run through the real executor, whose shell states call `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine check-floors …` from a non-repo cwd. It proves the `$${}` escaping, that `LL_PYTHON` + `-m` resolves, and that the `fail` token and empty-stdout crash route through the real `classify` evaluator to `_`. This is the only in-scope way to de-risk the idiom before FEAT-3582, since this issue changes no YAML.
- CLI-table conformance: every command's evaluator class matches § Evaluator per command; `resolve-profile` rejects `materialize=render`, `ground=codebase`, `premortem=true` while `BUILT_CAPABILITIES` excludes them; `frame-apply` always routes `pop_lens` and writes empty framings in v1 (`reframe` is pinned off by `BUILT_CAPABILITIES`; the `reframe` token branch exists only for v2); `collapse` emits `ground_codebase` \| `shortlist`; ids are never reused on re-ingest; `render-report --failed` writes the stub; `collapse` records re-tag agreement and occupancy in `dedup.log`
- `ll-verify-package-data` must pass (module and `brainstorm-profiles/` ship with the package; `pyproject.toml` includes `little_loops/**`)
- 2026-10-02 review additions: id high-water mark (replace the highest-numbered lens twice; no id ever reappears); atomic partial round (missing/malformed verdicts become abstention rows; `next-round` and salvage agree); happy token printed last after atomic writes (crash after the token still routes `fail`); `--set` coercion (`premortem=false` accepted as `False`, bad bool/int and unknown key exit 1); `ingest` after `collapse` exits 1; unreachable tokens (`materialize`, `premortem`, `ground_codebase`) tested only with `BUILT_CAPABILITIES` monkeypatched so the allowlist stays the single gate; `ll-loop validate`/list ignore the JSON-only `brainstorm-profiles/` subdirectory; the smoke test asserts an inherited `LL_PYTHON` does not override the runner's `sys.executable` (BUG-3689)

### Dependent Files
- FEAT-3582 (consumes the CLI contract), FEAT-3583/3584/3585/3586 (add commands)
- **Follow-ups to land in FEAT-3582** (2026-10-02 review): add `pair: int` to its § Data Contract `PairVerdict`; add an acceptance criterion and test that every classify state calling `brainstorm_engine` routes `_` to `finalize_failed`.

## Implementation Steps

0. **Commit checkpoints** (2026-10-02 review, in place of a split): commit after each group below with the suite green, so a session that stops mid-issue leaves a coherent, tested partial module on `main` (it is unused until FEAT-3582). Tick each box in the commit that closes the group, so a resumed session knows where to start:
   - [ ] (a) `IdeaRecord`/`FinalistsFile` I/O, CLI skeleton with the 0/1/2 exit and `fail`-token contract, and the executor smoke test
   - [ ] (b) `check-floors`, `build-schedule`, `next-round`, `record-round`, `rank`, `probe-plan`, `salvage`
   - [ ] (c) `ingest`, `frame-apply`, `collapse`, `shortlist-apply`
   - [ ] (d) `resolve-profile` + four presets, `prompt-block`, `portfolio`, `validate`, `render-report`, then docs
1. Write `test_brainstorm_engine.py` fixtures first (FEAT-3582 § Integration Map → Tests, plus the FEAT-3667 additions), then implement in the order given in Proposed Solution.
2. Define the CLI contract: one `argparse` subparser per command in the table, exit-code discipline (0/1/2), routing token as the last stdout line.
3. Add `resolve-profile` and the four preset JSONs (`artifact`, `visual`, `functional`, `business`); run `ll-verify-package-data`, `ruff check`, `ruff format` (changed files only), `mypy`, and the full pytest suite.

## Impact

- **Priority**: P2 - first link of the EPIC-3581 chain; FEAT-3582 is blocked by it
- **Effort**: Large - one new module with 15 v1 commands, four preset JSONs, golden render fixtures, an executor smoke test (relabelled 2026-10-02; was Medium)
- **Risk**: Low - unused until FEAT-3582; no behavior change
- **Breaking Change**: No

## Acceptance Criteria

- `render-report` is the only writer of `brainstorm.md`; routed commands print `fail` on any non-zero exit and print their happy token last, after atomic writes; the re-run tests listed under Tests pass (ingest/record-round/next-round never double-count, ids never reused, partial rounds recorded atomically).
- Every command in the CLI contract table except `reframe-select` (deferred to v2) exists with the documented args, files, exit codes and stdout token, covered by direct-import and `python -m` subprocess tests.
- All floors, schedule, ranking, probe, salvage, abstention, wildcard and dedup fixtures listed in FEAT-3582 pass.
- No YAML file is modified; `python -m pytest scripts/tests/` and `ll-verify-package-data` pass; `ruff` and `mypy` clean for the new module.
- `docs/reference/API.md` documents the module.
- The executor smoke test passes (`$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine` through the real classify evaluator, incl. the empty-stdout crash → `_`); each command's evaluator class matches § Evaluator per command; `resolve-profile` enforces `BUILT_CAPABILITIES`; `frame-apply` and `render-report --failed` exist; ids are never reused on re-ingest.
- `--set` values are coerced before the `BUILT_CAPABILITIES` check; the CLI table and its conformance tests cover v1 commands only (reframe leftovers live in the v2 appendix).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-02_ (replaces the stale 2026-09-29 notes)

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **Spec of record is split across two issues.** The CLI table is complete here, but only 8 of the 15 v1 commands have signatures in `## Program Design`; the rest (`frame-apply`, `collapse`, `shortlist-apply`, `next-round`, `record-round`, `probe-plan`, `salvage`, `portfolio`, `validate`) rely on FEAT-3582 § Program Design / § Data Contract / § Tournament Specification. The implementer must read both.
- **FEAT-3582 follow-ups are not yet confirmed landed** (`PairVerdict.pair` appears in FEAT-3582 already; the "every classify state routes `_` to `finalize_failed`" acceptance criterion and test are still to verify). They do not block this issue, since it changes no YAML.
- **`$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine` has no in-repo precedent.** The executor smoke test (checkpoint a) is the de-risking step; keep it first.
- `stale_file_ref` flags on `brainstorm_engine.py` / `test_brainstorm_engine.py` are expected until the files exist. `ll-history-context` matched only the pre-implementation review prompt (not a correction; no penalty).

### Outcome Risk Factors
- **Moderate per-site complexity (Complexity 10/25)**: ~7 change sites, but one new module whose 15 commands share cross-command file contracts (`ideas.jsonl` + `ideas.meta.json` high-water mark, `round_current.json`, `tournament.jsonl`, `profile.json`) and atomicity/token-ordering rules. Mitigated by test-first order, the pinned CLI table, and checkpoints (a)-(d).
- **Residual ambiguity (18/25)**: preset axes/bins are provisional (`functional.approach` agreement 0.72, FEAT-3583 owns the re-measure); the replace-by-lens-index generation-order drift is accepted but means retries are not byte-reproducible versus a clean run.
- **Session-length risk**: Effort is Large and the issue was deliberately not split; if a session stops before checkpoint (b), reopen the split decision (see Review Decisions dissent).

## Review Decisions

_Added 2026-10-02 (second pre-implementation review, `/ll:advise` with Opus, confidence 0.85; nothing measured):_ Fixed the id-allocation contradiction (persisted high-water mark in `ideas.meta.json`), added `pair` to `PairVerdict`, made rounds atomic in `record-round`, clarified that the trailing `fail` token exists to override a happy token printed before a late crash (token last, tmp + `os.replace`), pinned `--set` coercion, moved the `reframe` leftovers to a v2 appendix, added an `ingest` phase guard, fixed the Call Path and exit-1 wording, and added resumable checkpoint boxes. Dissent: the (a)+(b) tournament half needs only a fixture `profile.json`, so the "every split point leaks through `profile.json`" argument against splitting is weaker than recorded; the no-split decision was not reopened.

_Added 2026-10-02 (pre-implementation review, `/ll:advise` with Fable, confidence 0.85; nothing measured):_ Fixed four internal contradictions: the spike gate is marked superseded; `reframe-select` is marked v2 everywhere; all four presets ship here; signatures now match the CLI (`check_floors` `elapsed_ms`, `render_report` `failed`, `build_schedule` takes IDs). Effort relabelled Large. **Not split:** every candidate split point leaks through the shared `profile.json`, so commit checkpoints (Implementation Steps, step 0) guard against a mid-session stop instead. Dissent: given this repo's history of large issues stalling mid-session, a hard split is the stronger guard; revisit if an implementation session stops before checkpoint (b).

_Added 2026-09-30 (FEAT-3686 spike results, `postmortems/brainstorm-spike/RESULTS.md`; measured on 2 baseline briefs, 160 calls):_ **GO — the "held until FEAT-3686 reports" gate on the grid-dependent commands is lifted; build them as specified**, with these amendments: (1) every profile axis carries a one-line **definition per bin** and `prompt-block` prints them (blind tagging agreed only 0.51–0.67 on bin names alone, 0.62–0.83 with definitions); (2) `Profile` gains `duplicate_criterion`, printed by `prompt-block --kind dedup` (the default "same underlying idea" prompt gave precision 0.63 on names; a strict criterion gave 1.0/1.0); (3) `functional.json` `approach` bins/definitions are provisional until re-measured (per-axis agreement 0.72 < 0.75; FEAT-3583 owns the re-measure); (4) `cell` stays nullable as defence, but the grid is not dropped. Expect **6–9 finalists**, not always 8: the old loop's ideas occupy only 6 of 9 cells; steered runs reach 8–9.

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus, structural/process pass; nothing measured):_
- ~~**Spike gate (FEAT-3686).**~~ _Superseded 2026-09-30 by the FEAT-3686 results above (gate lifted; build the grid commands as specified). Kept for history._ The grid-dependent parts of this module — `ingest` cell normalization/`off_grid`, `collapse` re-tag, `shortlist-apply`, `check-floors` `min_cells`, the wildcard slot in `portfolio`, and the grid map in `render-report` — are **held until FEAT-3686 reports** (a failing grid result removes them from the contract). `cell` is therefore `[str, str] | None` in `IdeaRecord`. The grid-independent commands (`IdeaRecord`/`FinalistsFile` I/O, `check-floors` idea/finalist floors, `build-schedule`, `next-round`, `record-round`, `rank`, `probe-plan`, `salvage`, `validate`, `render-report` skeleton, `prompt-block`, the executor smoke test) may start in parallel with the spike. If the batched-judge row fails, `next-round`/`build-schedule` emit one pair per call and `max_finalists` is lowered to 6.
- **All four preset JSONs ship here** (unbuilt knobs off) so FEAT-3582's brief-2 merge gate runs `mode=functional` rather than the artifact axes; FEAT-3583 no longer introduces preset files.
- **`reframe` deferred to v2.** `BUILT_CAPABILITIES["reframe"] = {False}`: the `reframe` state and `reframe-select` are not built in v1 (`frame-apply` always takes the empty-framing path); an explicit `reframe=true` fails at `resolve-profile`. The `reframe-select` row and its tests are superseded until the follow-up brings measurements.
- **Import-origin guard.** The executor smoke test and `test_brainstorm_engine.py` assert `little_loops.__file__` resolves inside the checkout under test and pass `PYTHONPATH` through to the subprocess (`LL_PYTHON` = `sys.executable`). Verify gates already inject the worktree `PYTHONPATH` (`worktree_utils.py`), so a worktree run before this module is on `main` fails loudly with `ModuleNotFoundError`; after it lands, a run without `PYTHONPATH` would silently import `main`'s copy, which the guard catches.

_Added 2026-09-30 (EPIC-3581 fourth review, `/ll:advise` with Opus; nothing measured):_ `frame-apply` added (the reframe-skip path — the **default** for `artifact` — had no command writing empty-framing `lenses.txt` lines and no route around `reframe`); `lenses.txt` pinned to `lens_index|framing|lens` (the two prior spellings, `framing|lens_index` here and `framing|lens` in FEAT-3582, disagreed and neither survives `pop_lens` deleting lines); `collapse` prints the `ground_codebase|shortlist` token (FEAT-3584's gate cannot be `check_floors`, which runs after `shortlist`); `portfolio`'s happy token renamed `validate` → `render` (it routes to `render_report`, not `validate_portfolio`); `render-report --failed` keeps a single writer; `BUILT_CAPABILITIES` allowlist in `resolve-profile`; evaluator classes pinned; freeze rule loosened to "once FEAT-3582 merges"; ids never reused; smoke test added to this issue's tests; re-tag agreement/occupancy logged.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus; nothing measured):_ `render-report` and `prompt-block` added (no owner existed for `brainstorm.md` or for profile data reaching prompts); `fail` routing token on every routed command; idempotent appends keyed by round/pair/lens index; `--elapsed-ms` replaces `run_started_epoch`; `JUDGE_CALL_TIMEOUT_S` added to the time guard; `record-round`'s `fallback_html` token removed with FEAT-3585's restart; `lenses` added to `Profile`; `ground` type narrowed to `none | codebase`.

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-03T03:33:35 - `7cd57e8e-71e0-4299-a1a4-ccd6bda98ee6.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 pre-implementation review; edits applied) - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:26 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:confidence-check` - 2026-09-29T20:35:46 - `c1a7470e-ae08-48cc-8ac1-d91f782a8804.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue owns `Profile`/`Axis`, the four preset JSONs, and the override-aware `resolve_profile` (precedence tests live here). FEAT-3583 adds only the classifier, override plumbing, `mode` default flip, and tuning. `reframe` is deferred to v2 (`BUILT_CAPABILITIES` pins `reframe: {False}`); ground/materialize/premortem are owned by EPIC-3687.
