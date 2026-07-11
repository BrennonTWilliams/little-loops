---
id: ENH-2587
title: Guard .ll/decisions.yaml with a load-time validation check on commit/CI
type: ENH
status: done
priority: P2
size: Very Large
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T21:08:10Z'
decision_needed: false
labels:
- decisions
- data-integrity
- tooling
- pre-commit
- ci
confidence_score: 99
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2587: Guard `.ll/decisions.yaml` with a load-time validation check on commit/CI

## Summary

`.ll/decisions.yaml` can be — and in practice is — edited by hand / by an agent
rather than exclusively through `save_decisions()`. When that happens, PyYAML's
emitter (which escapes and quotes correctly) is bypassed, so a malformed scalar can
be committed and silently break every tool that later reads the file. This happened
with the `OTHE-203` entry (see the corruption fixed on 2026-07-10): a double-quoted
`rationale` contained an unescaped `` `""` ``, which is invalid inside a
double-quoted YAML scalar, so `yaml.safe_load` failed with
`ParserError: expected <block end>, but found '<scalar>'`. The broken file was
committed to `HEAD`, so nothing caught it until a reader crashed.

There is currently no automated check that `.ll/decisions.yaml` is loadable before
it lands in a commit.

## Motivation

- The file is the source of truth for team-enforced rules, decisions, exceptions,
  and coupling entries; a parse failure disables `load_decisions()` and everything
  built on it.
- Hand/agent edits bypass the serializer's escaping, so syntax corruption is a
  recurring failure mode, not a one-off.
- A parse failure has no localized blast radius — the whole file becomes unreadable
  from the first bad byte onward.

## Proposed Enhancement

Add a lightweight validation gate that runs `load_decisions()` (not just
`yaml.safe_load`) against `.ll/decisions.yaml` and fails non-zero on any error:

- A `pre-commit` hook scoped to `.ll/decisions.yaml` so corruption is caught before
  it is committed locally.
- The same check mirrored in CI so `--no-verify` and non-hook edit paths can't slip
  a broken file into the branch.

Validating through `load_decisions()` / `_entry_from_dict()` (rather than a bare
YAML parse) means the gate also catches schema-level problems — missing `id`,
unknown `type` — not merely syntax.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Where to slot the validator — two clear homes (decision required):**

- **Option A: New `ll-verify-decisions` entry in the `ll-verify-*` family.**

> **Selected:** Option A — New `ll-verify-decisions` entry in the `ll-verify-*` family — matches the canonical home for repo-boundary validation gates and drops directly into a `repo: local` `.pre-commit-config.yaml` `entry:` line.

  Mirror `scripts/little_loops/cli/verify_package_data.py:235-316` (`main_verify_package_data`)
  and register the console-script in `scripts/pyproject.toml:63-89` next to
  `ll-verify-package-data`, `ll-verify-design-tokens`, `ll-verify-des-audit`,
  and `ll-verify-triggers`. Add `"Bash(ll-verify-decisions:*)"` to the
  allowlist at `scripts/little_loops/init/writers.py:38`. Reusable from a
  `.pre-commit-config.yaml` `repo: local` hook (entry: `ll-verify-decisions`),
  the pytest-gate subprocess, and ad-hoc CLI invocation.

- **Option B: New `validate` subcommand under `ll-issues decisions`.**
  Extend `add_decisions_parser` at `scripts/little_loops/cli/issues/decisions.py:14`
  alongside `list` / `add` / `outcome` / `generate` / `sync` / `suggest-rules` /
  `extract-from-completed` / `promote`. The `_cmd_validate` body can mirror the
  simple path-only shape of `_cmd_sync` at `scripts/little_loops/cli/issues/decisions.py:528`.
  Reuses the configured path automatically (`config.project_root /
  config.decisions.log_path`). Does NOT slot into a `.pre-commit-config.yaml`
  `repo: local` hook as cleanly (pre-commit frameworks expect a single binary
  entry).

**What `load_decisions()` actually raises — the validator must catch:**

- YAML syntax errors: `yaml.YAMLError` (specifically `yaml.parser.ParserError`
  for the OTHE-203 case — `yaml.parser.ParserError ⊂ yaml.scanner.ScannerError
  ⊂ yaml.YAMLError`). Raised from the single `yaml.safe_load` call at
  `scripts/little_loops/decisions.py:278`.
- Unknown `type` discriminator: `ValueError("Unknown entry type: '<value>'")`
  from `_entry_from_dict` at `scripts/little_loops/decisions.py:268`.
- Missing required fields (`id`, `result`, `measured_at`, `rule_ref`): raw
  `KeyError` from each `from_dict` classmethod (RuleEntry:67, DecisionEntry:117,
  ExceptionEntry:167, CouplingEntry:216).
- Absent / empty file: returns `[]` gracefully (NOT an error). The validator
  should treat absence as PASS (gate fires only when corruption exists), or
  fail explicitly with a clear "no decisions log" message — pick one for
  consistency.

**Where the "pre-commit" hook lives — also two forks:**

- **Git pre-commit framework (`.pre-commit-config.yaml` `repo: local`):** add
  `language: system`, `entry: ll-verify-decisions` (or the appropriate CLI from
  Option A/B above), `files: ^\.ll/decisions\.yaml$`. Fires on `git commit`;
  requires `pre-commit` install; does NOT catch `--no-verify` or non-hook edit
  paths.
- **Claude Code host PreToolUse (`hooks/hooks.json`):** mirror
  `hooks/scripts/check-duplicate-issue-id.sh:1-50` — bash script under
  `hooks/scripts/check-decisions-yaml.sh`, registered against matcher
  `Write|Edit` with `timeout: 5`. Fires whenever Claude's tools write the file;
  does NOT fire when developers edit outside Claude. Complements the
  `.pre-commit-config.yaml` path; both can coexist.

The most defensive posture is BOTH: `.pre-commit-config.yaml` for git-side,
`hooks/hooks.json` PreToolUse for Claude-side, plus the pytest gate for catch-all CI.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-10.

**Selected**: Option A — New `ll-verify-decisions` entry in the `ll-verify-*` family

**Reasoning**: Option A mirrors the established `main_verify_*` signature used by 7 sibling CLIs (`scripts/little_loops/cli/verify_package_data.py:235-316` is the canonical template), slots alphabetically into the console-script registration cluster at `scripts/pyproject.toml:86-89`, joins the sibling permission allowlist at `scripts/little_loops/init/writers.py:38-40`, and — critically — the single-binary form (`ll-verify-decisions`) works natively as a `.pre-commit-config.yaml` `repo: local` `entry:` line. Option B fits the `ll-issues decisions` parser shape (`add_decisions_parser:14`, `_cmd_sync:528`) but contradicts the project's stronger convention that repo-boundary file validation lives in the `ll-verify-*` family (not nested under topic subcommands; the closer siblings — `format-check`, `check-readiness`, `check-decidable`, `check-open-questions`, `check-flag` — are all top-level under `ll-issues`), and is incompatible with `pre-commit`'s `repo: local` `entry:` model without a wrapper shell script.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: `ll-verify-decisions` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B: `ll-issues decisions validate` | 1/3 | 2/3 | 3/3 | 1/3 | 7/12 |

**Key evidence**:
- **Option A**: Reuse score 3/3 — every wiring surface (signature, `cli_event_context`, argparse shape, console-script registration, permission allowlist, in-process CLI test pattern at `scripts/tests/test_verify_package_data.py:264-365`, pytest-subprocess gate pattern at `scripts/tests/test_policy_builder_node_gate.py:1-72`) exists and is reused unchanged; only the validator body is new. `load_decisions()` exception surface (`yaml.YAMLError` / `KeyError` / `ValueError` at `scripts/little_loops/decisions.py:264-282`) provides a precise catch set without new helpers.
- **Option B**: Reuse score 3/3 within the `ll-issues decisions` family (parser registration, dispatch site, `_cmd_sync` mirror, path resolution at `decisions.py:285`); but the project's `ll-verify-*` family is the canonical home for repo-boundary file validation (the closest precedent, `main_verify_des_audit` at `scripts/little_loops/cli/verify_des_audit.py:97-164`, is explicitly a "gate" per its docstring), and `pre-commit` `repo: local` `entry:` cannot accept the multi-token form `entry: ll-issues decisions validate` without a wrapper shim.

## Acceptance Criteria

- A committed check loads `.ll/decisions.yaml` via `load_decisions()` and exits
  non-zero on any parse or schema error, with a message pointing at the file.
- The check runs both as a `pre-commit` hook and in CI.
- A deliberately corrupted `decisions.yaml` (e.g. the `OTHE-203`
  unescaped-quote case) is rejected by the check; a valid file passes.
- The check is fast enough (single file load) to run on every commit without
  friction.

## Notes

- Related fixed corruption: `OTHE-203` rationale unescaped `` `""` `` in
  `.ll/decisions.yaml` (repaired 2026-07-10 by escaping to `` `\"\"` ``).
- Complements ENH's sibling capture on lossy serialization (see BUG-2588): a
  schema-aware validator and a non-lossy serializer address the write and read
  halves of the same integrity gap.

### Adjacent work surfaced during research

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `FEAT-1891` — original decisions-log data layer; ENH-2587 validates the dataclasses defined here.
- `FEAT-1893` — earlier validation FEAT; ENH-2587 is the **commit/CI-side** instantiation of that earlier work.
- `FEAT-1895` — pre-existing sync pathway that writes `decisions.yaml` content into `ll.local.md`; the gate fires before sync reads the file.
- `BUG-2423` — existing guardrail CLI invocation bug (silent error swallow). Latent in the `decisions-cli` invocation path; ENH-2587 should NOT regress this.
- `ENH-2152`, `ENH-2125`, `ENH-2464` — adjacent decisions-log enhancements to be aware of during planning.
- **OTHE-203 corruption fixture:** confirmed via research — the entry at `.ll/decisions.yaml:4776-4796` is the canonical fixture the gate must reject (a double-quoted YAML scalar containing literal `""`, which raises `yaml.parser.ParserError: expected <block end>, but found '<scalar>'`). The pytest gate should hard-code this fixture as a `tmp_path` file under `scripts/tests/test_decisions_yaml_gate.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/decisions.py:14, 265` — extend `add_decisions_parser` and `cmd_decisions` dispatch. _Only if Option B (validator home is `ll-issues decisions validate`)._
- `scripts/little_loops/cli/verify_decisions.py` (new) — mirror `scripts/little_loops/cli/verify_package_data.py:235-316`. _Only if Option A (new `ll-verify-decisions` console-script)._
- `scripts/little_loops/cli/__init__.py:82-85` — re-export `main_verify_decisions` if Option A (mirror existing `main_verify_*`).
- `scripts/pyproject.toml:63-89` — add `ll-verify-decisions = "little_loops.cli:main_verify_decisions"` if Option A.
- `scripts/little_loops/init/writers.py:38` — add `"Bash(ll-verify-decisions:*)"` to the allowlist if Option A.
- `.pre-commit-config.yaml` — append `repo: local` block: `language: system`, `entry: ll-verify-decisions`, `files: ^\.ll/decisions\.yaml$`.
- `scripts/tests/test_decisions_yaml_gate.py` (new) — pytest gate mirroring `scripts/tests/test_policy_builder_node_gate.py:1-72`.
- `scripts/tests/test_decisions.py:~75` — extend `TestLoadDecisions` with malformed-input cases using `pytest.raises(yaml.YAMLError)` / `KeyError` / `ValueError`.
- `scripts/tests/test_cli_decisions.py` — add CLI-level tests for the new `validate` subsubs (or the new `ll-verify-decisions` CLI), mirroring `test_verify_package_data.py:264-334`.
- `hooks/hooks.json:41-74` — register the new `check-decisions-yaml.sh` if Claude Code PreToolUse path chosen.
- `hooks/scripts/check-decisions-yaml.sh` (new) — bash hook mirroring `hooks/scripts/check-duplicate-issue-id.sh:1-50`.

### Dependent Files (Callers — anything that benefits from the gate)
- `scripts/little_loops/decisions.py:272` (`load_decisions`) — the load path the validator exercises.
- `scripts/little_loops/decisions.py:285` (`save_decisions`) — sibling write path (BUG-2588 owns its integrity gap; ENH-2587 covers the read half).
- `scripts/little_loops/decisions_sync.py:26` (`sync_to_local_md`) — currently bypasses the validator; the gate gives this caller a free layer of safety.
- `scripts/little_loops/cli/issues/decisions.py:265` (`cmd_decisions`) — list/add/outcome/sync dispatch site, which today silently lets parse errors propagate.
- `skills/decide-issue/SKILL.md`, `skills/capture-issue/SKILL.md`, `skills/format-issue/SKILL.md` — heaviest consumers of decisions; today they crash with a `ParserError` on first bad byte.

### Similar Patterns
- `scripts/tests/test_policy_builder_node_gate.py:1-72` — pytest gate for the policy-builder JS conformance suite (FEAT-2390); canonical shape for "wrap a check as a pytest test" under the no-hosted-CI policy.
- `scripts/little_loops/cli/verify_package_data.py:235-316` — `main_verify_package_data`, the most polished `ll-verify-*` CLI.
- `scripts/little_loops/cli/verify_des_audit.py:97-164` — explicitly called a "gate" in its docstring (ENH-2475 F5 adoption); closest sibling in spirit.
- `hooks/scripts/check-duplicate-issue-id.sh:1-50` — bash PreToolUse hook with path-scope gate; shape to mirror for `check-decisions-yaml.sh`.
- `scripts/tests/test_verify_package_data.py:264-334` — in-process CLI exit-code tests with `patch("sys.argv", ...)`.
- `scripts/tests/test_decisions.py:75-118` — existing `TestLoadDecisions` graceful-absence baseline (must NOT regress).
- `scripts/tests/test_decisions.py:251-280` — `pytest.raises(ExcType, match=...)` pattern for malformed input.

### Tests
- `scripts/tests/test_decisions.py` — extend `TestLoadDecisions` with malformed-input cases (currently covers only happy paths).
- `scripts/tests/test_decisions_yaml_gate.py` (new) — CI gate mirroring `test_policy_builder_node_gate.py`.
- `scripts/tests/test_cli_decisions.py` — add CLI-level tests for `validate` subsubs (in-process `patch("sys.argv", ...)`, mirroring `test_verify_package_data.py`).

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — explain why the gate exists, how `--no-verify` bypass works, and how to repair a corrupt file (point at the OTHE-203 corruption pattern).
- `docs/reference/API.md` — new `main_verify_decisions` (or `cmd_decisions validate`) entry point.
- `docs/reference/COMMANDS.md` — new command documentation.
- `docs/reference/CONFIGURATION.md` — mirror any new `decisions.validate_on_commit` config knob.
- `CHANGELOG.md` — single-line release entry on promote (NOT under `[Unreleased]` per project convention).

### Configuration
- `.ll/ll-config.json` — no current `decisions.*` block (`DecisionsConfig` defaults: `enabled: false`, `log_path: ".ll/decisions.yaml"` per `scripts/little_loops/config/features.py:505`). A `decisions.validate_on_commit: true` knob is OPTIONAL.
- `scripts/little_loops/config-schema.json` — mirror the new knob if added.
- `scripts/pyproject.toml:118` — already lists `pre-commit>=3.0` in dev extras; no new deps expected.

## Implementation Steps

1. **Pick validator home (Option A vs Option B).** See "## Proposed Enhancement" § "Where to slot the validator." The choice flows into Steps 2–3.
2. **Add the validator CLI.** Option A: create `scripts/little_loops/cli/verify_decisions.py` mirroring `scripts/little_loops/cli/verify_package_data.py:235-316`. Option B: extend `add_decisions_parser` at `scripts/little_loops/cli/issues/decisions.py:14` and add `_cmd_validate` dispatch. The validator body wraps `load_decisions()` (via subprocess or direct import) and catches `yaml.YAMLError` / `KeyError` / `ValueError` per the table under "## Proposed Enhancement" § "What `load_decisions()` actually raises."
3. **Register the entry point.** Option A: add `ll-verify-decisions = "little_loops.cli:main_verify_decisions"` to `scripts/pyproject.toml:63-89`, re-export from `scripts/little_loops/cli/__init__.py:82-85`, and add `"Bash(ll-verify-decisions:*)"` to the allowlist in `scripts/little_loops/init/writers.py:38`.
4. **Wire the `.pre-commit-config.yaml` local hook.** Append a `repo: local` block with `language: system`, `entry: ll-verify-decisions` (or the Option B subcommand form), `files: ^\.ll/decisions\.yaml$`.
5. **(Optional) Wire the Claude Code host PreToolUse hook.** Create `hooks/scripts/check-decisions-yaml.sh` mirroring `hooks/scripts/check-duplicate-issue-id.sh:1-50`, register under `hooks/hooks.json:41-74` PreToolUse with `matcher: Write|Edit` and `timeout: 5`. Skip if the git-side hook + pytest gate suffice.
6. **Add the pytest CI gate.** Create `scripts/tests/test_decisions_yaml_gate.py` mirroring `scripts/tests/test_policy_builder_node_gate.py:1-72`. Use the subprocess or in-process form per the patterns at `test_verify_package_data.py:264-334`. Skip gracefully when the validator is absent using the `pytest.skip` idiom from `test_policy_builder_node_gate.py:52`.
7. **Extend `TestLoadDecisions` with malformed-input cases.** Add to `scripts/tests/test_decisions.py:~75-118`. Use `pytest.raises(yaml.YAMLError)` for an OTHE-203 fixture (`rationale: "abc "" def"`), `pytest.raises(KeyError)` for a missing-id entry, and `pytest.raises(ValueError, match="Unknown entry type")` for an unknown-type entry. Mirrors `scripts/tests/test_decisions.py:251-280`.
8. **Add CLI-level tests.** In `scripts/tests/test_cli_decisions.py`, test: clean returns 0, dirty returns 1, both via `patch("sys.argv", [...])` mirroring `scripts/tests/test_verify_package_data.py:264-334`.
9. **Verify the gate.** Run `python -m pytest scripts/tests/test_decisions_yaml_gate.py -v` (per `project.test_cmd` in `.ll/ll-config.json`). Run the full suite once to ensure no regression elsewhere: `python -m pytest scripts/tests/`.
10. **Documentation pass.** Update `docs/guides/DECISIONS_LOG_GUIDE.md` (purpose + bypass notes), `docs/reference/API.md` (new entry point), `docs/reference/COMMANDS.md` (new command), `docs/reference/CONFIGURATION.md` (any new config knob), `CHANGELOG.md` (single-line entry on release — no `[Unreleased]` per project convention).

## Session Log
- `/ll:decide-issue` - 2026-07-10T22:01:05 - `3e23b1e0-cada-4674-bedc-e3c643f8cf6f.jsonl`
- `/ll:refine-issue` - 2026-07-10T21:55:19 - `c8eaa3e3-d68c-4c01-ad0e-a589fa0a0079.jsonl`
- manual session - 2026-07-10T21:08:10Z - captured from decisions.yaml corruption investigation
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-10
- **Reason**: Score 11/11 (Very Large); 18+ files across 3 transport layers (pre-commit framework, pytest CI gate, Claude Code host PreToolUse) plus the validator CLI itself. Decomposed into 4 independently shippable children to bound each session's surface.

### Decomposed Into
- ENH-2589: Add `ll-verify-decisions` validator CLI + unit tests
- ENH-2590: Wire `.pre-commit-config.yaml` repo-local hook for `.ll/decisions.yaml`
- ENH-2591: Add pytest CI gate for `.ll/decisions.yaml`
- ENH-2592: Add Claude Code PreToolUse hook for `.ll/decisions.yaml`

### Ordering
- ENH-2589 must land first — the three transport hooks consume its CLI.
- ENH-2590, ENH-2591, ENH-2592 can land in any order once ENH-2589 ships (each is an independently testable subsystem).

