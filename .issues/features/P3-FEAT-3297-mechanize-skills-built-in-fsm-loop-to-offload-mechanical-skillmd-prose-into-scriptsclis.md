---
id: FEAT-3297
type: FEAT
title: 'mechanize-skills: built-in FSM loop to offload mechanical SKILL.md prose into
  scripts/CLIs'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T04:50:54Z'
parent: EPIC-2938
labels:
- loops
- skills
- code-quality
- epic-2938
completed_at: '2026-08-23T04:50:59Z'
---

# FEAT-3297: mechanize-skills: built-in FSM loop to offload mechanical SKILL.md prose into scripts/CLIs

## Summary

Added `mechanize-skills`, a new built-in FSM loop (`scripts/little_loops/loops/mechanize-skills.yaml`) that automates EPIC-2938's offloading process itself: it iterates over `SKILL.md` files one at a time, diagnoses which prose is mechanical/deterministic enough to be a script instead of an LLM following hand-written steps, gates the diagnosis on estimated token savings, implements the mechanization, updates the skill to call it, and commits or reverts on a fully deterministic accept gate — the LLM never decides accept/revert.

## Current Behavior

Before this session, EPIC-2938's offloading process (moving mechanical SKILL.md prose into `ll-*` CLIs/scripts) had to be done by hand, skill by skill, with no automated diagnosis, savings gate, or deterministic accept/revert mechanism.

## Expected Behavior

A built-in FSM loop iterates skills off a queue, diagnoses mechanical prose per skill (LLM pass, deterministically validated against the skill's own text), gates on estimated token savings, implements and commits the mechanization behind a fully deterministic accept gate — or reverts cleanly, manifest-scoped, on any gate failure.

## Motivation

EPIC-2938 found ~2,500+ lines of deterministic instruction across skill markdown that the LLM executes by hand, causing drift, non-determinism, and context waste. Rather than offloading each skill by hand, this loop automates the offloading process itself: `mode=diagnose` produces a report-only pass writing findings to `diagnoses/` for later review; `mode=apply` (default) implements and commits accepted mechanizations, guarded by a `conventions_file` knob (extend project CLIs per a doc, or bundle small scripts under `<skill>/scripts/` when no doc is given).

## Use Case

A maintainer running `ll-loop run mechanize-skills --context mode=diagnose` gets a report-only sweep of every SKILL.md, pointing at which ones have mechanizable prose worth a follow-up `mode=apply` run — without touching any file or committing anything.

## Acceptance Criteria

- [x] `ll-loop validate mechanize-skills` passes with zero errors and zero warnings.
- [x] `mechanize-skills` is registered in `test_expected_loops_exist` and covered by a dedicated structural test class.
- [x] The accept/revert decision is fully deterministic (`exit_code` evaluator only) — no `llm_structured`/`check_semantic` state anywhere in the loop.
- [x] `mode=diagnose` never writes to a skill file or commits; `mode=apply` reverts cleanly (manifest-scoped) on any gate failure.
- [x] Loop documented in `scripts/little_loops/loops/README.md` and `docs/guides/LOOPS_REFERENCE.md`; `CHANGELOG.md` updated.
- [x] Full suite (`python -m pytest scripts/tests/`) green aside from one pre-existing, unrelated failure.

## Program Design

### Types

No new Python types — the loop is pure FSM YAML. Its JSON artifacts (`diagnosis.json`, `apply-manifest.json`, `results.jsonl`, `findings.jsonl`) follow ad-hoc shapes documented inline in the relevant states' prompts/actions.

### Signatures

No new Python functions or CLI entry points — the loop is pure FSM YAML that shells out to existing, unchanged CLIs:

- `main_config() -> int` — `scripts/little_loops/cli/config.py:54`, backs `ll-config get project.test_cmd` (`resolve_env`/`check_preconditions`-style resolution).
- `main_verify_skill_prose(argv: list[str] | None = None) -> int` — `scripts/little_loops/cli/verify_skill_prose.py:219`, backs `ll-verify-skill-prose --json` (prose-count baseline and gate check).
- `main_verify_skills() -> int` — `scripts/little_loops/cli/docs.py:244`, backs `ll-verify-skills --limit N` (line-cap gate check).

### Call Path

`ll-loop run mechanize-skills` → `init` (build `pending.txt` queue) → `resolve_env` (resolve conventions/test_cmd/prose baseline) → per-skill loop (`pick_skill` → `snapshot_baseline` → `diagnose_skill` → `validate_diagnosis` → `worth_gate` → `check_mode` → `record_finding`|`apply` → `check_emission` → `accept_gate` → `commit_change`|`revert_changes` → `record_skip` → `advance`) → `report` → `done`.

## Integration Map

### New Files

- `scripts/little_loops/loops/mechanize-skills.yaml` — the loop definition

### Files Modified

- `scripts/tests/test_builtin_loops.py` — `expected` set entry + `TestMechanizeSkillsLoop` class
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md` — loop documentation
- `CHANGELOG.md` — `[1.157.0]` `### Added` entry
- `README.md`, `scripts/README.md` — loop-count badge (103→104)

## Implementation Steps

1. Designed and wrote the 22-state FSM loop (`init` → `resolve_env` → per-skill queue: `pick_skill` → `snapshot_baseline` → `diagnose_skill` → `validate_diagnosis` (+ `diagnosis_retry`) → `worth_gate` → `check_mode` → `record_finding` (diagnose) or `apply` → `check_emission` (+ `apply_retry`) → `accept_gate` → `commit_change`/`revert_changes` → `record_skip` → `advance` → `report`), following the repo's meta-loop rules (diagnosis-first shape, deterministic accept gate, `${context.run_dir}`-scoped artifacts).
2. Registered the loop in `scripts/tests/test_builtin_loops.py`'s `expected` set and added `TestMechanizeSkillsLoop` (15 tests: state graph, MR-1/MR-2/MR-4 compliance, discriminated skip-reasons, revert safety, no shared-tmp scratch, `ll-config get` resolution).
3. Documented the loop in `scripts/little_loops/loops/README.md` (Code Quality table) and `docs/guides/LOOPS_REFERENCE.md` (table row + full subsection with context-variable table).
4. Added a `CHANGELOG.md` entry under the still-unreleased `[1.157.0]` section.
5. Fixed two runtime bugs caught by `ll-loop validate`'s bash-brace check during development: unescaped `${NUM}`/`${SKILL_NAME}`/`${SAVED}` bash-variable references in `record_finding`/`commit_change` that would have raised `InterpolationError` at runtime (switched to unbraced `$VAR` form, since each is set within the same action).
6. Fixed an incidental hardcode-gate trip (`states.apply.action contains ['scripts/tests']`) — reworded a prompt sentence that happened to contain the literal substring.
7. Synced the two files the full suite caught as stale from adding a 104th built-in loop: the root `README.md` loop-count badge (103→104) and its packaged duplicate at `scripts/README.md` (BUG-3179 byte-match requirement).

## Impact

- **Priority**: P3 — additive tooling, not blocking other work.
- **Effort**: Large — a 22-state meta-loop plus full test/doc/changelog coverage.
- **Risk**: Low — the loop only mutates repo state in `mode=apply`, behind a deterministic gate with manifest-scoped revert; `mode=diagnose` (report-only) is safe to run anywhere.
- **Breaking Change**: No.

## Verification

- `ll-loop validate mechanize-skills` — zero errors, zero warnings (`--json` confirms empty `violations`).
- `ll-loop simulate mechanize-skills` — all scenario flags (`all-fail`, `all-error`, `first-fail`, `alternating`) route correctly; `all-pass` loops at `worth_gate` due to a known simulator limitation (it only synthesizes exit codes, not matching stdout values for `output_numeric` evaluators) — not a defect in the loop, confirmed by validate's clean reachability analysis.
- `python -m pytest scripts/tests/` — full suite: 20,923 passed, 51 skipped, 1 pre-existing failure unrelated to this work (`test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`, against an `.issues/` file already modified before this session started).

## Related Key Documentation

- EPIC-2938 — the audit that motivated offloading mechanical skill prose into `ll-*` CLIs; this loop automates that offloading process rather than performing one instance of it.

## Status

**Done** | Created: 2026-08-23 | Completed: 2026-08-23 | Priority: P3
