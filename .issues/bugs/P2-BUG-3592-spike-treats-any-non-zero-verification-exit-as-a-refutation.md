---
id: BUG-3592
type: BUG
title: Spike treats any non-zero Verification exit as a refutation
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:40:43Z'
parent: EPIC-3565
supersedes:
- BUG-3572
blocked_by:
- BUG-3591
blocks:
- BUG-3593
- BUG-3574
- ENH-3577
confidence_score: 100
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3592: Spike treats any non-zero Verification exit as a refutation

## Summary

Part (b) of BUG-3572's split: the spike verdict contract. `skills/spike/SKILL.md` Phase 5
says "If any command exits non-zero, the spike **failed**", and Phase 6/7 send every failure
down one branch that recommends `/ll:decide-issue`. BUG-3591 (done, `fb3d305`) already
softened the Phase 6 wording to "the cause may be the approach or the environment", but
the skill still cannot tell the two apart. Import errors, no tests collected, environment
failures, a failing regression-guard test and an unrelated regression-suite failure all
take the same route as a real refutation. This child adds a deterministic classifier (proven / refuted / inconclusive), a
`spike_refuted` flag, and the refuted write-back that `/ll:decide-issue` can act on.

The full design record is BUG-3572 (cancelled, superseded by this issue, BUG-3591 and
BUG-3593). Its Proposed Solution items 1–3 are the source of this child.

## Current Behavior

Phase 5 runs `python -m pytest "$SPIKE_DIR/" -v` plus the named regression suites and
routes every non-zero exit to the failure branch. The exit code cannot say *which* test
failed: the plan's regression-guard test lives in `$SPIKE_DIR` next to the AC tests, and
exit 1 also covers test-time errors. Phase 7 then prints one failure message routing to
`/ll:decide-issue` / `/ll:issue-size-review`, so an environment failure is sent to a
decision it cannot inform.

## Expected Behavior

A CLI classifies each Verification run from role-tagged JUnit XML plus recorded exception
types, and the skill writes the full flag set for the verdict. Only an `AssertionError` in
an AC test, with all guard tests and regression suites passing, reads as refuted.
Everything ambiguous reads as inconclusive and does not claim the approach is wrong.

## Steps to Reproduce

1. Take an issue with `unproven_mechanism: true` and a spike plan whose AC test imports a module that is not installed
2. Run `/ll:spike --auto`; pytest raises `ModuleNotFoundError` in the test body and exits 1
3. Observe Phase 6 take the failure branch and write `## Spike Findings` saying the approach is disproven, though nothing about the mechanism was tested

## Root Cause

- **File**: `skills/spike/SKILL.md`
- **Anchor**: Phase 5 (Verification) and Phase 6 ("On failure")
- **Cause**: verdict is derived from the aggregate exit code, which conflates refutation
  with collection/import/environment failures and guard/regression failures.

## Proposed Solution

1. **Encoding — boolean `spike_refuted: true`** (not a `spike_verdict` enum), matching the
   lowercase-bool `spike_*` convention and `ll-issues check-flag`:
   - **proven**: `spike_completed: true`
   - **refuted**: `spike_attempted: true` + `spike_refuted: true`
   - **inconclusive**: `spike_attempted: true` with neither — also how every legacy
     attempted-only issue reads, so legacy issues fail safe (BUG-3591 keeps them capped).
2. **Exception-type recording — a generated `conftest.py`, not `-p little_loops...`.** The
   spike runs in the consuming project's own `python -m pytest`, where `little_loops` is
   not importable under a pipx / uv-tool install, so `-p little_loops.spike_junit_plugin`
   would fail there. The exception type is only needed for the `spike` suite (regression
   suites only need pass/fail), so the hook goes in `conftest.py` inside `$SPIKE_DIR`, written by
   ll-issues `spike-verdict --emit-conftest --out <spike-dir>/conftest.py` (single source of
   truth in the package; `ll-issues` is always on PATH and pre-approved by `Bash(ll-issues:*)`,
   so no shell redirect is needed). The CLI **appends a sentinel-delimited block**
   (`# >>> ll-spike-verdict hook >>>` … `# <<< ll-spike-verdict hook <<<`) and replaces an
   existing block in place: a spike may ship its own `conftest.py` with fixtures, which
   must not be overwritten, and a `--force` rerun must not duplicate the hook. The hook is a
   `pytest_runtest_makereport` hookwrapper that, on a failed `call` phase, appends to
   **`item.user_properties`** (not `rep.user_properties`: junitxml reads properties from
   the teardown report, which copies the item's list — verified 2026-09-24):
   - `("ll_exc_type", call.excinfo.type.__name__)` — for the Findings cause line;
   - `("ll_assertion", "true"|"false")` — the value the classifier keys on. It is `"true"`
     when `isinstance(call.excinfo.value, AssertionError)` (covers subclasses and
     `unittest` `assertEqual`, which raises `AssertionError`), **or** the exception is
     pytest's `Failed` outcome with a message starting `DID NOT RAISE` / `DID NOT WARN`
     (a `pytest.raises` / `pytest.warns` block whose expected exception never came — a real
     refutation). Verified 2026-09-24: a non-raising `pytest.raises` records
     `ll_exc_type=Failed`, so an exact-name `AssertionError` match would misread it as
     inconclusive. A bare `pytest.fail(...)` stays `"false"` (conservative: it is also used
     for environment bail-outs).

   Result: `<property name="ll_exc_type" value="AssertionError"/>` and
   `<property name="ll_assertion" value="true"/>` inside the `<testcase>`. The plan
   template's **Promotion** section notes that the sentinel block is not promoted.
   Why JUnit `<failure>` alone is not enough (verified 2026-09-24): pytest emits `<failure>`
   for **any** exception in the call phase (`ModuleNotFoundError`, `FileNotFoundError`
   included); only fixture/setup errors produce `<error>`; `<failure>` carries only a
   `message`, and a bare `assert` has message `"assert 1 == 2"` with no type prefix.
3. **Report location.** Delete stale reports, then run every planned Verification command
   with `--junitxml=<reports-dir>/<role>-<n>.xml`:
   - inside an FSM loop: `<reports-dir>` = `${context.run_dir}/spike-junit/`
   - interactively (no `run_dir`): a `mktemp -d` directory, removed after classification.
     **Never** `.ll/spikes/`: that fallback is git-tracked (not in `.gitignore`), and JUnit
     XML there would be committed noise.
   - `allowed-tools` gains `Bash(mktemp:*)` and `Bash(rm:*)` (today only `mkdir`, `find`,
     `git`, `python -m pytest`, `ll-issues`, `ll-config` are pre-approved), or the
     interactive path prompts on every run.
   - Each command also gets `--maxfail=0`, appended after the plan's own flags. A project
     `addopts = -x` would otherwise stop at the first AC failure before the guard tests
     run, so every refutation would read inconclusive ("zero guard tests passed"). A later
     `--maxfail` overrides `-x`'s `maxfail=1` (verified 2026-09-24: with `addopts = -x`,
     `1 failed` → `2 failed, 1 passed` once `--maxfail=0` is appended).
4. **Evidence contract and rule** — `ll-issues spike-verdict --report <role>:<xml>:<exit> ...`
   prints `PROVEN|REFUTED|INCONCLUSIVE` plus a one-line cause and exits 0 / 1 / 3 (2 is
   argparse's usage error). `role` is `spike` (the `$SPIKE_DIR` suite: AC + guard tests) or
   `regression` (a named existing suite). Guard tests are identified by the name prefix
   `test_guard_` (set by the plan template; `@pytest.mark.*` does not appear in JUnit
   output — verified). Every non-guard test in a `spike` report is an AC test.
   - **Evaluation order: inconclusive triggers are checked first and win.** A run matching
     any inconclusive trigger below is inconclusive even if it also meets the refuted
     conditions (e.g. one AC `AssertionError` plus one AC `ModuleNotFoundError` →
     inconclusive).
   - **Proven** only when every report is present and well-formed, every command exited 0,
     ≥1 guard test **passed**, and **every** AC test passed — none skipped or xfailed.
     Each AC row retires a named risk, so a skipped AC leaves its risk unproven.
   - **Refuted** only when ≥1 AC test is `<failure>` and **every** AC `<failure>` carries
     `ll_assertion == "true"`, **and** every guard test passed, **and** every `regression`
     report is fully passing, **and** the `spike` command exited 1.
   - **Inconclusive** otherwise: a missing/malformed report or a planned command with no
     report; any `<error>`; any AC `<failure>` whose `ll_assertion` is absent or `"false"`;
     collection errors; no tests collected (exit 5); exit 2–4; timeouts; zero AC or zero
     guard tests; **any** AC test skipped/xfailed; any guard test skipped; a failing guard
     test; a failing regression report; a nonzero exit with an all-pass report.
   - Residual, accepted: an AC `AssertionError` caused by a bug in the spike's own code
     reads as refuted. The Findings entry quotes the failing assertion so a human can tell.
5. **Flag transitions — every verdict writes the full flag set** (extends BUG-3591's
   proven-vs-not split):

   | Verdict | `spike_attempted` | `spike_completed` | `spike_refuted` | `decision_needed` |
   |---|---|---|---|---|
   | proven | set | set | **remove** | unchanged |
   | refuted | set | **remove** | set | set |
   | inconclusive | set | **remove** | **remove** | unchanged |

   Removing `spike_refuted` on a later verdict does not clear a `decision_needed` the
   refutation armed; that stays owned by `/ll:decide-issue`.
6. **Refuted write-back that decide-issue can actually decide.** `/ll:decide-issue` only
   finds options through `issue_parser.locate_enumerable_options` (`### Option` headers,
   bold labels, numbered/bullet items — Phase 2.5); a free-text Open Questions item gives
   it nothing, and under `--auto` it falls back to `/ll:refine-issue --auto` or ends
   `decision_unresolved`. And the refuted approach is still in `## Proposed Solution`, so
   decide-issue could select it again. On refuted, the spike skill therefore:
   - rewrites `## Proposed Solution` into **`### Option <X>: <title>` header blocks only**
     (the `section_header` tier). The existing proposal body moves verbatim under
     `### Option A: <refuted approach>`; each alternative from `## Spike Findings` becomes
     `### Option B…`. Header blocks are mandatory, not just any enumerable shape: an
     original Proposed Solution usually holds numbered design steps (this issue's does),
     and without headers `locate_enumerable_options` would read those steps as `numbered`
     options;
   - adds one numbered item under `## Open Questions` (created before `## Status` /
     `## Session Log` if absent) in exactly the **refuted-option marker** shape below;
   - arms `decision_needed: true`.

   **Refuted-option marker — literal shape** (the single definition; BUG-3574 writes the
   same line for `PROPOSAL_UNSOUND` with its B6 evidence in place of the assertion):

   ```markdown
   1. **Refuted option**: Option A — /ll:spike 2026-09-24: `assert result.ready is True`. Which remaining option replaces it?
   ```

   - Parsed by a new `issue_parser.refuted_option_labels(content) -> set[str]`, regex
     `^\s*(?:\d+[.)]|[-*])\s+\*\*Refuted option\*\*:\s*(?P<label>.+?)\s+—` over the
     `## Open Questions` body. `label` must equal a `LocatedOption.label` exactly
     (compared case-insensitively, whitespace-collapsed).
   - The trailing `?` is deliberate: `_OPEN_QUESTION_SIGNAL_RE` only counts an item that
     carries a signal, so the unresolved marker counts as an open question and keeps
     refine-to-ready's `check_hedges` (`ll-issues check-open-questions`) blocking until a
     replacement is chosen.
   - The parser reads the marker **whether or not it is resolved**. A `✅ RESOLVED` suffix
     closes the question but never makes the refuted option eligible again.

   **Exclusion is deterministic, in the option locators — not in skill prose.** Today a
   refuted spike with no alternative leaves one option, so decide-issue's
   `Only one option present — no decision required. Clearing decision_needed if set.`
   branch (`skills/decide-issue/SKILL.md` § Option Count Check) would **select the refuted
   option**. So:
   - `LocatedOption` gains `eligible: bool = True` (in `to_dict()`), set `False` for labels
     in `refuted_option_labels(content)`; `locate-options --json` emits it and adds
     `eligible_count`.
   - `locate_unresolved_decisions` (returns `list[DecisionGroup]`) marks refuted options
     ineligible within each group, so `check-unresolved-decisions --json` never offers
     one as a candidate. A group left with zero eligible options **stays in the
     unresolved list** with `all_refuted: true` in `DecisionGroup.to_dict()`: it must keep
     Phase 7b's re-verify gate from clearing `decision_needed`, and must not be read as a
     one-option group.
   - decide-issue Phase 2.5/3 read `eligible_count` rather than `count`; Phase 3b's
     provisional-language scan skips refuted-marker items and never takes a refuted
     label as a candidate.

   **decide-issue outcomes on a refuted issue:**
   - ≥1 eligible option → select among the eligible options as usual, then append
     ` ✅ RESOLVED (YYYY-MM-DD by /ll:decide-issue: <selected label>)` to the marker item.
   - 0 eligible options (refuted and no alternative) → emit a new result token and leave
     both the marker unresolved and `decision_needed: true`:

     ```
     ## RESULT: ALL_OPTIONS_REFUTED
     reason: every option in ## Proposed Solution is named by a refuted-option marker
     decision_needed remains true
     exit_code: 1
     ```

     This is **not** `NO_ACTIONABLE_DECISIONS`: that exit (Phase 3b-i) fires only when
     every Open Questions item is already marked resolved, which the unresolved marker
     prevents. Exit 1 makes the resolve-decision oracle fail, which is what BUG-3593
     routes to `record_decision_unresolved`.

   BUG-3574 step 3 (`PROPOSAL_UNSOUND`) reuses the marker, the parser, the exclusion and
   `ALL_OPTIONS_REFUTED` unchanged.
7. **Findings and messages.** Inconclusive writes a `## Spike Findings` entry naming the
   classifier's cause and does not claim the approach is wrong. Phase 7 prints a distinct
   message per verdict; the inconclusive message names `/ll:spike <ID> --force` as the
   recovery after fixing the cause. Only the refuted message routes to
   `/ll:decide-issue`; the inconclusive one must not (a decision cannot fix an
   environment failure).
8. **`--check` mode stays exit-code-only.** `spike-gate.yaml` only needs pass/fail, and any
   non-pass is correctly blocking. Do not route `--check` through the classifier.

## Program Design

### Types

- `spike_refuted: bool` — new frontmatter flag written by `/ll:spike` on a refuted result and removed by it on a later proven/inconclusive verdict (BUG-3593 adds removal by `/ll:decide-issue` on re-arm); emitted by `show --json` as `'true'`/`None` like the other `spike_*` flags.
- `SpikeReport` — dataclass `(role: str, junit_path: Path, exit_code: int)`; `role` is `spike` or `regression`.
- `SpikeVerdict` — dataclass `(verdict: str, cause: str)`; `verdict` is `PROVEN`, `REFUTED` or `INCONCLUSIVE`; `cause` is a one-line reason quoted into `## Spike Findings`.
- `LocatedOption.eligible: bool = True` — new field on the existing dataclass; `False` when the label is named by a refuted-option marker. Emitted by `to_dict()`.
- `DecisionGroup` — existing; `to_dict()` gains `all_refuted: bool`.
- `ALL_OPTIONS_REFUTED` — new `/ll:decide-issue` result token (exit 1, `decision_needed` stays true).

### Signatures

- `classify_spike_junit(reports: list[SpikeReport], guard_prefix: str = "test_guard_") -> SpikeVerdict` — new pure function applying the Proposed Solution 4 rule.
- `cmd_spike_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new ll-issues `spike-verdict`; `--report <role>:<xml>:<exit> ...` prints the verdict and cause and exits 0 / 1 / 3; `--emit-conftest --out <path>` writes (or replaces in place) the sentinel-delimited conftest hook block and exits 0. `--report` is split as `role` = text before the first `:`, `exit` = text after the last `:`, `xml` = everything between.
- `refuted_option_labels(content: str) -> set[str]` — new in `issue_parser`; normalized labels named by refuted-option markers in `## Open Questions`, resolved or not.
- `locate_enumerable_options(content: str) -> LocatedOptions` — existing; sets `eligible` on each option from `refuted_option_labels`.
- `locate_unresolved_decisions(content: str, *, include_approximate_tiers: bool = False) -> list[DecisionGroup]` — existing; excludes refuted options as candidates and flags zero-eligible groups `all_refuted`.
- `cmd_locate_options(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues locate-options`; `--json` gains per-option `eligible` and top-level `eligible_count`.
- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show`; its `--json` spike-flag block gains `spike_refuted`.

### Call Path

`cmd_spike_verdict` -> `classify_spike_junit`; `cmd_locate_options` -> `locate_enumerable_options` -> `refuted_option_labels`; `cmd_check_unresolved_decisions` -> `locate_unresolved_decisions` -> `refuted_option_labels`; `cmd_show` -> `_parse_card_fields` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/spike_verdict.py` (new) — `SpikeReport`, `SpikeVerdict`, `classify_spike_junit`, `cmd_spike_verdict`, conftest hook source for `--emit-conftest`
- `scripts/little_loops/cli/issues/__init__.py` — register `spike-verdict` in dispatch and the `_USAGE` epilog
- `scripts/little_loops/cli/issues/show.py` — emit `spike_refuted` as a lowercased string alongside the other `spike_*` flags (`show.py:134-148`); required for loop predicates to read it
- `skills/spike/SKILL.md` — `allowed-tools` gains `Bash(mktemp:*)`, `Bash(rm:*)`; Phase 4/5 write the conftest block via `--emit-conftest --out`, pick `<reports-dir>`, delete stale reports, run each Verification command with `--junitxml` and `--maxfail=0`, call `spike-verdict`; Phase 6 three-verdict flag table and refuted write-back (`### Option` headers + marker); Phase 7 messages. Currently 315 lines against the 500-line `SKILL.md` cap (`ll-verify-skills`, `test_enh494_skill_companions.py`); if the write-back instructions push it near the cap, move them to a companion file (ENH-494 pattern)
- `skills/spike/plan-template.md` — guard tests named `test_guard_*` (rename the example `test_spike_does_not_import_production_core`); Verification section tags each command `spike` or `regression`; Promotion notes the conftest sentinel block is not promoted
- `scripts/little_loops/issue_parser.py` — new `refuted_option_labels`; `LocatedOption.eligible`; `locate_enumerable_options` sets it; `locate_unresolved_decisions` excludes refuted candidates and flags `all_refuted` groups
- `scripts/little_loops/cli/issues/locate_options.py` — `--json` emits `eligible` and `eligible_count`
- `scripts/little_loops/cli/issues/check_unresolved_decisions.py` — `--json` carries `all_refuted`; the human-readable output names refuted-exhausted groups
- `skills/decide-issue/SKILL.md` — Phase 2.5/3 read `eligible_count`; Option Count Check never takes a refuted option through the one-option clear; Phase 3b skips marker items; marks the marker `✅ RESOLVED` on selection; `ALL_OPTIONS_REFUTED` token and exit
- `docs/reference/CLI.md` — new ll-issues `spike-verdict` section alongside the other `ll-issues` subcommands (the ~2273 anchor is inside `check-flag`; it only needs a cross-reference to `spike_refuted`), plus the `locate-options` / `check-unresolved-decisions` JSON fields; `docs/reference/ISSUE_TEMPLATE.md` — `spike_refuted` row (pinned by `test_wiring_reference_docs.py`); `docs/reference/COMMANDS.md`; `docs/reference/API.md` — `refuted_option_labels`, `LocatedOption.eligible`, and the `spike_verdict` module if its classifier is public

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_open_questions.py` — read-only; the unresolved marker must count via `_OPEN_QUESTION_SIGNAL_RE` (trailing `?`) and stop counting once `✅ RESOLVED` is appended
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — read-only; confirm `ALL_OPTIONS_REFUTED`'s exit 1 with `decision_needed` still true fails the oracle (BUG-3593 routes it)
- `commands/reconcile-issue.md` (~L144) — mirrors `/ll:spike`'s `spike_attempted` convention; update if it describes the failure contract
- `scripts/tests/spike/*/` — existing spike packages name their guard tests without the `test_guard_` prefix (e.g. `enh3549_read_side_fake_hosts::test_spike_does_not_edit_production_registries`); a `--force` rerun would read inconclusive ("zero guard tests"). Rename them, or record in the docs that pre-BUG-3592 spikes need the prefix before a rerun

### Tests
- `scripts/tests/test_spike_verdict.py` (new) — classifier + conftest hook over **real pytest-generated JUnit** (run pytest in `tmp_path` with the emitted conftest): bare `assert` → refuted; `unittest` `assertEqual` → refuted; non-raising `pytest.raises` (`Failed: DID NOT RAISE`) → refuted; bare `pytest.fail` → inconclusive; `ImportError` / `OSError` in a test body → inconclusive; one AC `AssertionError` plus one AC `ModuleNotFoundError` → inconclusive (precedence); fixture `<error>` → inconclusive; failing guard test; failing `regression` report; missing report; malformed XML; no tests collected; one AC skipped with the rest passing → inconclusive; all AC skipped; zero AC / zero guard tests; nonzero exit with an all-pass report; `addopts = -x` project with `--maxfail=0` still runs the guard tests; all-pass → proven. `--emit-conftest --out`: appends to an existing fixture conftest without clobbering it, and a second run replaces the block rather than duplicating it
- `scripts/tests/test_show.py` — `show --json` surfaces `spike_refuted` (pattern at `:373-438`)
- `scripts/tests/test_spike_skill.py` — literal-string assertions for the three verdicts, the flag table (incl. refuted → proven clearing `spike_refuted`), the report location (never `.ll/spikes/`), `--maxfail=0`, the `mktemp`/`rm` allowed-tools, and the refuted write-back (`### Option` headers + the literal marker line)
- `scripts/tests/test_issue_parser.py` (or the existing `locate_enumerable_options` test module) — `refuted_option_labels` matches resolved and unresolved markers; `eligible` is `False` for the named label; a realistic refuted write-back whose original Proposed Solution had numbered steps yields `pattern == "section_header"` with the expected option count; `locate_unresolved_decisions` flags a zero-eligible group `all_refuted` and keeps it unresolved; `count_open_questions_in_sections` counts the unresolved marker and not the resolved one
- `scripts/tests/test_decide_issue_skill.py` — refuted option never reaches the one-option clear; `ALL_OPTIONS_REFUTED` token with `decision_needed` left true; marker gets `✅ RESOLVED` on selection; Phase 3b skips marker items
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gate for all five `GATED_HOSTS`

## Implementation Steps

1. `spike_verdict.py` (classifier, CLI, `--emit-conftest --out` block writer) + `test_spike_verdict.py` matrix
2. `show.py` emits `spike_refuted`
3. `issue_parser.py`: `refuted_option_labels`, `LocatedOption.eligible`, `all_refuted` groups; `locate-options` / `check-unresolved-decisions` JSON fields; parser tests
4. Plan template: `test_guard_` prefix, role tags, Promotion note; rename guard tests in existing `scripts/tests/spike/*` packages
5. Spike skill: `allowed-tools`; Phases 4–7 (conftest, report dir, `--maxfail=0`, classifier call, flag table, write-back, messages)
6. Decide-issue: `eligible_count`, Phase 3b skip, marker resolution, `ALL_OPTIONS_REFUTED`
7. Docs; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Acceptance Criteria

- [ ] A Verification failure caused by collection/import/env errors, a non-assertion exception in a test body, a test-time `<error>`, a failing guard test, a failing regression suite, a missing/malformed report, any skipped AC test, or zero matching AC/guard tests is recorded as inconclusive, not refuted
- [ ] An AC failure from `assert`, a `unittest` assertion, or a non-raising `pytest.raises` / `pytest.warns` counts as an assertion; a mix of assertion and non-assertion AC failures is inconclusive
- [ ] Refuted/inconclusive classification is made by ll-issues `spike-verdict` from role-tagged JUnit XML with recorded exception types, not by the model reading exit codes
- [ ] The exception-type hook works in a project where `little_loops` is not importable by the project's pytest (conftest, not `-p`), and never overwrites or duplicates content in an existing spike `conftest.py`
- [ ] JUnit reports are never written under `.ll/spikes/`
- [ ] Every verdict writes the full flag set: a failed `--force` rerun clears a stale `spike_completed`; a proven rerun clears a stale `spike_refuted`
- [ ] A refuted spike leaves ≥1 enumerable option for `/ll:decide-issue` when an alternative exists, and decide-issue never re-selects the refuted option — including when it is the only option left
- [ ] The refuted-option exclusion is computed by `locate-options` / `check-unresolved-decisions`, not by skill prose
- [ ] With no eligible option, decide-issue emits `ALL_OPTIONS_REFUTED`, exits 1 and leaves `decision_needed: true`; after a replacement is selected, the marker item is `✅ RESOLVED` and `check-open-questions` no longer counts it
- [ ] `ll-issues show --json` emits `spike_refuted`
- [ ] `--check` mode is unchanged

## Impact

- **Priority**: P2 - refutations and environment failures are indistinguishable, so the loops cannot route correctly
- **Effort**: Medium-Large - new CLI + hook, spike skill rewrite of Phases 4–7, option-locator eligibility, decide-issue exclusion
- **Risk**: Medium - changes the spike contract that BUG-3593 and BUG-3574 build on, and the `locate-options` / `check-unresolved-decisions` JSON every decide caller reads (additive fields only)
- **Breaking Change**: No (legacy attempted-only issues read as inconclusive). Behavior change: a proven verdict now requires a `test_guard_*` test, so a `--force` rerun of a pre-existing spike without one reads inconclusive
- **Sequencing**: BUG-3591 is done (`fb3d305`), so this issue is unblocked

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-25T04:25:20 - `9aefaaf2-024d-4b80-b438-1a2a0085bef6.jsonl`
