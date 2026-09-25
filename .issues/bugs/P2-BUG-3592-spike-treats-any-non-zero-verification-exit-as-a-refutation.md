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
---

# BUG-3592: Spike treats any non-zero Verification exit as a refutation

## Summary

Part (b) of BUG-3572's split: the spike verdict contract. `skills/spike/SKILL.md` Phase 5
says "If any command exits non-zero, the spike **failed**", and Phase 6 calls a failed spike
"the approach is wrong". Import errors, no tests collected, environment failures, a failing
regression-guard test and an unrelated regression-suite failure are all reported as a
refutation. This child adds a deterministic classifier (proven / refuted / inconclusive), a
`spike_refuted` flag, and the refuted write-back that `/ll:decide-issue` can act on.

The full design record is BUG-3572 (cancelled, superseded by this issue, BUG-3591 and
BUG-3593). Its Proposed Solution items 1–3 are the source of this child.

## Current Behavior

Phase 5 runs `python -m pytest "$SPIKE_DIR/" -v` plus the named regression suites and
routes every non-zero exit to the failure branch. The exit code cannot say *which* test
failed: the plan's regression-guard test lives in `$SPIKE_DIR` next to the AC tests, and
exit 1 also covers test-time errors.

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
   suites only need pass/fail), so the skill writes a `conftest.py` in `$SPIKE_DIR` with the hook,
   taking the content from ll-issues `spike-verdict --emit-conftest` (single source of
   truth in the package; `ll-issues` is always on PATH). The hook is a
   `pytest_runtest_makereport` hookwrapper that, on a failed `call` phase, appends
   `("ll_exc_type", call.excinfo.type.__name__)` to **`item.user_properties`** (not
   `rep.user_properties`: junitxml reads properties from the teardown report, which copies
   the item's list — verified 2026-09-24). Result:
   `<property name="ll_exc_type" value="AssertionError"/>` inside the `<testcase>`.
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
4. **Evidence contract and rule** — `ll-issues spike-verdict --report <role>:<xml>:<exit> ...`
   prints `PROVEN|REFUTED|INCONCLUSIVE` plus a one-line cause and exits 0 / 1 / 3 (2 is
   argparse's usage error). `role` is `spike` (the `$SPIKE_DIR` suite: AC + guard tests) or
   `regression` (a named existing suite). Guard tests are identified by the name prefix
   `test_guard_` (set by the plan template; `@pytest.mark.*` does not appear in JUnit
   output — verified). Every non-guard test in a `spike` report is an AC test.
   - **Proven** only when every report is present and well-formed, every command exited 0,
     and ≥1 AC test and ≥1 guard test **passed** (not skipped).
   - **Refuted** only when ≥1 AC test is `<failure>` with `ll_exc_type == AssertionError`,
     **and** every guard test passed, **and** every `regression` report is fully passing.
   - **Inconclusive** otherwise: a missing/malformed report or a planned command with no
     report; any `<error>`; an AC `<failure>` whose `ll_exc_type` is absent or not
     `AssertionError`; collection errors; no tests collected (exit 5); exit 2–4; timeouts;
     zero AC or zero guard tests; all AC or all guard tests skipped; a failing guard test;
     a failing regression report; a nonzero exit with an all-pass report.
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
   - writes the alternatives from `## Spike Findings` as enumerable option blocks under
     `## Proposed Solution` (the shape `locate_enumerable_options` recognizes), keeping the
     refuted approach as one labelled option;
   - adds an `## Open Questions` item with one **refuted-option marker** naming the refuted
     option and quoting the failing assertion;
   - arms `decision_needed: true`.

   `/ll:decide-issue` treats any option named by a refuted-option marker as ineligible:
   with ≥1 remaining option it selects among them; with none it exits without clearing
   `decision_needed` (the correct stop for a refuted approach with no replacement). The
   marker shape and the exclusion are shared with BUG-3574 step 3 (`PROPOSAL_UNSOUND`):
   define them once here; BUG-3574 reuses them.
7. **Findings and messages.** Inconclusive writes a `## Spike Findings` entry naming the
   classifier's cause and does not claim the approach is wrong. Phase 7 prints a distinct
   message per verdict; the inconclusive message names `/ll:spike <ID> --force` as the
   recovery after fixing the cause.
8. **`--check` mode stays exit-code-only.** `spike-gate.yaml` only needs pass/fail, and any
   non-pass is correctly blocking. Do not route `--check` through the classifier.

## Program Design

### Types

- `spike_refuted: bool` — new frontmatter flag written by `/ll:spike` on a refuted result and removed by it on a later proven/inconclusive verdict (BUG-3593 adds removal by `/ll:decide-issue` on re-arm); emitted by `show --json` as `'true'`/`None` like the other `spike_*` flags.
- `SpikeReport` — dataclass `(role: str, junit_path: Path, exit_code: int)`; `role` is `spike` or `regression`.
- `SpikeVerdict` — dataclass `(verdict: str, cause: str)`; `verdict` is `PROVEN`, `REFUTED` or `INCONCLUSIVE`; `cause` is a one-line reason quoted into `## Spike Findings`.

### Signatures

- `classify_spike_junit(reports: list[SpikeReport], guard_prefix: str = "test_guard_") -> SpikeVerdict` — new pure function applying the Proposed Solution 4 rule.
- `cmd_spike_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new ll-issues `spike-verdict`; `--report <role>:<xml>:<exit> ...` prints the verdict and cause and exits 0 / 1 / 3; `--emit-conftest` prints the conftest hook source and exits 0.
- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show`; its `--json` spike-flag block gains `spike_refuted`.

### Call Path

`cmd_spike_verdict` -> `classify_spike_junit`; `cmd_show` -> `_parse_card_fields` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/spike_verdict.py` (new) — `SpikeReport`, `SpikeVerdict`, `classify_spike_junit`, `cmd_spike_verdict`, conftest hook source for `--emit-conftest`
- `scripts/little_loops/cli/issues/__init__.py` — register `spike-verdict` in dispatch and the `_USAGE` epilog
- `scripts/little_loops/cli/issues/show.py` — emit `spike_refuted` as a lowercased string alongside the other `spike_*` flags (`show.py:134-148`); required for loop predicates to read it
- `skills/spike/SKILL.md` — Phase 4/5 write a `conftest.py` in `$SPIKE_DIR`, pick `<reports-dir>`, delete stale reports, run each Verification command with `--junitxml`, call `spike-verdict`; Phase 6 three-verdict flag table and refuted write-back; Phase 7 messages
- `skills/spike/plan-template.md` — guard tests named `test_guard_*`; Verification section tags each command `spike` or `regression`
- `skills/decide-issue/SKILL.md` — refuted-option marker makes an option ineligible
- `docs/reference/CLI.md` (~2273) — `spike-verdict` subcommand; `docs/reference/ISSUE_TEMPLATE.md` — `spike_refuted` row (pinned by `test_wiring_reference_docs.py`); `docs/reference/COMMANDS.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` (read-only consumer of the write-back shape; confirm the refuted write-back yields ≥2 options)
- `commands/reconcile-issue.md` (~L144) — mirrors `/ll:spike`'s `spike_attempted` convention; update if it describes the failure contract

### Tests
- `scripts/tests/test_spike_verdict.py` (new) — classifier + conftest hook over **real pytest-generated JUnit** (run pytest in `tmp_path` with the emitted conftest): assert failure → refuted; `ImportError` / `OSError` in a test body → inconclusive; fixture `<error>` → inconclusive; failing guard test; failing `regression` report; missing report; malformed XML; no tests collected; all AC skipped; zero AC / zero guard tests; nonzero exit with an all-pass report; all-pass → proven
- `scripts/tests/test_show.py` — `show --json` surfaces `spike_refuted` (pattern at `:373-438`)
- `scripts/tests/test_spike_skill.py` — literal-string assertions for the three verdicts, the flag table (incl. refuted → proven clearing `spike_refuted`), the report location (never `.ll/spikes/`), and the refuted write-back
- decide-issue skill contract test — a refuted-option marker excludes that option; with no remaining option `decision_needed` stays set
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gate for all five `GATED_HOSTS`

## Implementation Steps

1. `spike_verdict.py` (classifier, CLI, conftest source) + `test_spike_verdict.py` matrix
2. `show.py` emits `spike_refuted`
3. Plan template: `test_guard_` prefix and role tags
4. Spike skill Phases 4–7: conftest, report dir, classifier call, flag table, write-back, messages
5. Decide-issue refuted-option exclusion
6. Docs; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Acceptance Criteria

- [ ] A Verification failure caused by collection/import/env errors, a non-`AssertionError` exception in a test body, a test-time `<error>`, a failing guard test, a failing regression suite, a missing/malformed report, or zero matching AC/guard tests is recorded as inconclusive, not refuted
- [ ] Refuted/inconclusive classification is made by ll-issues `spike-verdict` from role-tagged JUnit XML with recorded exception types, not by the model reading exit codes
- [ ] The exception-type hook works in a project where `little_loops` is not importable by the project's pytest (conftest, not `-p`)
- [ ] JUnit reports are never written under `.ll/spikes/`
- [ ] Every verdict writes the full flag set: a failed `--force` rerun clears a stale `spike_completed`; a proven rerun clears a stale `spike_refuted`
- [ ] A refuted spike leaves ≥1 enumerable option for `/ll:decide-issue` when an alternative exists, and decide-issue never re-selects the refuted option
- [ ] `ll-issues show --json` emits `spike_refuted`
- [ ] `--check` mode is unchanged

## Impact

- **Priority**: P2 - refutations and environment failures are indistinguishable, so the loops cannot route correctly
- **Effort**: Medium - new CLI + hook, spike skill rewrite of Phases 4–7, decide-issue exclusion
- **Risk**: Medium - changes the spike contract that BUG-3593 and BUG-3574 build on
- **Breaking Change**: No (legacy attempted-only issues read as inconclusive)

## Status

**Open** | Created: 2026-09-25 | Priority: P2
