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
---

# FEAT-3667: Brainstorm engine module: deterministic core, CLI contract, and artifact profile

## Summary

Implement `scripts/little_loops/brainstorm_engine.py` and `scripts/tests/test_brainstorm_engine.py` — the pure-Python deterministic core of the EPIC-3581 brainstorm engine — **before and independently of** the loop rewrite. No YAML changes. FEAT-3582 (loop rewrite, tournament child loop, wiring, docs) is blocked by this issue and consumes the CLI contract below.

_Split from FEAT-3582 on 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus). FEAT-3582's § Data Contract, § Tournament Specification and § Program Design remain the **spec of record**; this issue implements them and owns the CLI contract table._

## Current Behavior

`brainstorm.yaml` embeds its only deterministic logic (difflib dedup, saturation counter) as inline Python heredocs. No importable brainstorm module exists.

## Expected Behavior

- `little_loops.brainstorm_engine` exposes every function in FEAT-3582 § Program Design and the CLI commands below, invoked as `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <cmd> --run-dir DIR ...` (`LL_PYTHON` is exported as `sys.executable` by `fsm/runners.py`, so the idiom is robust in consuming projects).
- Includes `resolve-profile` and the built-in `artifact` profile JSON (`scripts/little_loops/loops/brainstorm-profiles/artifact.json`) so the loop rewrite and FEAT-3583 never re-touch these.
- Everything is unit-tested by direct import, test-first; nothing here depends on the FSM executor.
- Landing this issue changes no user-visible behavior (the module is unused until FEAT-3582), so it is safe to merge to `main` on its own.

### CLI contract

All commands: `python3 -m little_loops.brainstorm_engine <cmd> --run-dir DIR [args]`. **Exit 0** = success; **exit 1** = domain violation (floors/validation/invalid profile; violations listed on stderr, one per line); **exit 2** = crash or usage error (never used for a domain result). LLM output reaches the module only as a file (`--*-file`). Commands that route print their **routing token as the last stdout line**.

| Command | Args | Reads | Writes | Stdout token |
|---|---|---|---|---|
| `resolve-profile` | `--mode M` `--set key=value`… (empty = inherit) `--decision-file F` (optional classifier output) | `brainstorm-profiles/*.json` | `profile.json` (incl. `overridden`, clamped `max_finalists`) | resolved mode |
| `reframe-select` | `--raw-file F` | `profile.json` | `lenses.txt` framing seeds (`framing\|lens`), `diverge_state.md` | count |
| `ingest` | `--raw-file F` | `profile.json`, `ideas.jsonl` | `ideas.jsonl` (append), `diverge_state.md` | ideas added |
| `collapse` | `--groups-file F` | `ideas.jsonl` | `ideas.jsonl`, `dedup.log` (fail-open) | ideas kept |
| `shortlist-apply` | `--picks-file F` | `ideas.jsonl`, `profile.json` | `finalists.json`, `shortlist.json` | finalists count |
| `check-floors` | `--stage generation\|pre_tournament\|final` | ideas, finalists, profile | — (violations on stderr) | next-state token from the profile (`ground_web` \| `materialize` \| `tournament`; `ok` at `final`) |
| `build-schedule` | — | `finalists.json` | `schedule.json` (rounds → ordered pairs) | round count |
| `next-round` | — | `schedule.json` | `round_current.json`, `round_prompt.txt` | exit 1 = no rounds left (queue-pop semantics) |
| `record-round` | `--verdicts-file F` | `round_current.json`, `finalists.json` | `tournament.jsonl` (append) | `ok` \| `fallback_html` (round-1 image-proof check, see FEAT-3585) |
| `probe-plan` | — | `tournament.jsonl` | `round_current.json` (reversed top-3 head-to-heads) | pair count |
| `rank` | — | `tournament.jsonl` | `tournament.json` | — |
| `salvage` | — | `tournament.jsonl`, `schedule.json` | `tournament.json` (`partial`) | exit 1 = below salvage floor |
| `portfolio` | `--synthesize` | `tournament.json`, `ideas.jsonl` | `portfolio.json`, `winners.md` | `premortem` \| `validate` |
| `validate` | — | portfolio, ideas, finalists, profile | — | `ok` |

**Input file formats** (pinned 2026-09-29; tagged NDJSON — one JSON object per line prefixed by the tag, other lines ignored, malformed lines skipped and counted, never fatal):

| File (`--*-file`) | Tag and line shape |
|---|---|
| `reframe-select --raw-file` | `FRAMING_JSON: {"framing": "How might we …"}` — in ranked order, best first |
| `ingest --raw-file` | `IDEAS_JSON: {"title": str, "body": str, "cell": [bin_a, bin_b], "extra": {…}?}` |
| `collapse --groups-file` | `DUP_GROUPS_JSON: [["i003", "i007"], …]` and optional `RETAG_JSON: {"i001": [bin_a, bin_b], …}` |
| `shortlist-apply --picks-file` | `PICKS_JSON: {"<bin_a>\|<bin_b>": "i012", …}` — one id per multi-idea cell |
| `record-round --verdicts-file` | `VERDICT_JSON: {"pair": int, "winner": "a" \| "b" \| null, "rationale": str, "seen": [str, str]?}` — one per pair; `seen` only in image mode |

Later children add commands here and never change existing rows (`probe-anchor`/`probe-source`, `materialize-check`, `annotate`, `render-report`).

## Use Case

**Who**: The maintainer implementing EPIC-3581, and later the agent implementing FEAT-3582 who needs a stable, tested engine to call from YAML.

**Context**: The brainstorm rewrite has ~14 deterministic operations (ingest, dedup collapse, shortlist, round-robin schedule, ranking, salvage, floors, portfolio, validation). Written inline in YAML they cannot be unit-tested and drift between the `check_floors` and `validate_portfolio` copies.

**Goal**: Have every deterministic operation as an importable, directly unit-tested function behind a documented CLI, before any loop YAML changes.

**Outcome**: `python -m little_loops.brainstorm_engine <cmd>` implements the full CLI contract; FEAT-3582 reduces to thin YAML calls.

## Program Design

All symbols live in `scripts/little_loops/brainstorm_engine.py` and are exposed through `python3 -m little_loops.brainstorm_engine <command>`; the full types, the tournament/floor/portfolio semantics and the remaining signatures are the spec of record in FEAT-3582 § Program Design and § Data Contract.

### Types

- `IdeaRecord`: `{id: str, title: str, body: str, framing: str, lens: str, cell: [str, str], off_grid: bool, grounded: bool | "unknown" | None, extra: dict}` — one JSON line per idea in `ideas.jsonl`
- `FinalistsFile`: `{finalists: [str], reserve: {str: [str]}, dropped: {str: str}, judge_mode: str, assets: dict}`
- `PairVerdict`: `{a: str, b: str, winner: str | null, probe: bool, round: int, rationale: str}`
- `Profile`: `{mode: str, reframe: bool, min_ideas: int, min_cells: int, max_finalists: int, ideas_per_round: int, reserve: int, axes: [Axis, Axis], ground: str, materialize: str, rubric: str, premortem: bool, output_shape: str, overridden: [str]}`

### Signatures

- `main(argv: list[str] | None = None) -> int` — the `python -m` entry point; one `argparse` subparser per command in the CLI contract table; returns 0 / 1 / 2 per the exit-code contract
- `check_floors(ideas: list[IdeaRecord], finalists: FinalistsFile, profile: Profile, stage: str) -> list[str]` — returns the violations (empty = pass); the single function behind `check-floors` and `validate`
- `ingest_ideas(raw: str, ideas: list[IdeaRecord], profile: Profile) -> list[IdeaRecord]` — assigns stable IDs, normalizes and validates cells, flags `off_grid`
- `build_schedule(finalists: list[IdeaRecord]) -> list[list[tuple[str, str]]]` — deterministic circle-method round-robin as a list of rounds
- `rank(verdicts: list[PairVerdict], finalists: list[IdeaRecord]) -> list[str]` — Copeland score, then head-to-head, then generation order
- `resolve_profile(mode: str, overrides: dict[str, str], decision: dict | None) -> Profile` — base profile from `mode`, non-empty overrides win, empty string inherits

### Call Path

`pop_lens` -> `diverge` -> `main` -> `ingest_ideas` -> `check_floors` -> `build_schedule` -> `rank` -> `verify_artifacts`

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
- **Time guard**: `check-floors --stage pre_tournament` also fails with the violation `insufficient_time` when `PARENT_TIMEOUT_S − elapsed < TOURNAMENT_TIMEOUT_S + TAIL_S` (`elapsed` from `run_started_epoch` written by `init`; `PARENT_TIMEOUT_S` mirrors `brainstorm.yaml` `timeout`, asserted equal by a test in FEAT-3582). See FEAT-3582 § Tournament Specification → Budgets.

## Integration Map

### Files to Modify
- `scripts/little_loops/brainstorm_engine.py` — new
- `scripts/little_loops/loops/brainstorm-profiles/artifact.json` — new (`.json` so unfiltered `rglob("*.yaml")` scanners never read it)
- `docs/reference/API.md` — `little_loops.brainstorm_engine` section (docs audience: cite the module, not `scripts/` paths)

### Tests
- `scripts/tests/test_brainstorm_engine.py` — new; the full list in FEAT-3582 § Integration Map → Tests, plus: CLI exit-code contract (0/1/2) per command, `insufficient_time` guard, salvage-floor arithmetic (N = 2..8), abstention thresholds, re-tag fallback, cap tie-break by generation order, `reframe-select` forced-ranking parse
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

- Every command in the CLI contract table exists with the documented args, files, exit codes and stdout token, covered by direct-import and `python -m` subprocess tests.
- All floors, schedule, ranking, probe, salvage, abstention, wildcard and dedup fixtures listed in FEAT-3582 pass.
- No YAML file is modified; `python -m pytest scripts/tests/` and `ll-verify-package-data` pass; `ruff` and `mypy` clean for the new module.
- `docs/reference/API.md` documents the module.

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

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-29T20:35:46 - `c1a7470e-ae08-48cc-8ac1-d91f782a8804.jsonl`
