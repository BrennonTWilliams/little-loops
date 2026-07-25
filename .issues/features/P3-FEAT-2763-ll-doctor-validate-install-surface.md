---
id: FEAT-2763
type: feature
priority: P3
status: done
captured_at: '2026-07-24T19:36:28Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 96
outcome_confidence: 50
score_complexity: 10
score_test_coverage: 15
score_ambiguity: 15
score_change_surface: 10
decision_needed: true
size: Very Large
---

# FEAT-2763: Expand ll-doctor to validate little-loops' own install surface

## Summary

`ll-doctor` today checks only the *host CLI's* capabilities plus two config
echoes. It validates nothing about little-loops itself: whether the 46 console
entry points declared in `scripts/pyproject.toml` are importable, whether skills
and commands resolve, whether `.ll/decisions.d/` or `.ll/history.db` are healthy,
whether loops validate, or whether the learning-test registry is intact. Users
reasonably read "doctor" as "is my install coherent?" — and it does not answer
that question.

Notably, the project already ships a family of single-purpose checkers
(`ll-verify-docs`, `ll-verify-skills`, `ll-verify-skill-budget`,
`ll-verify-triggers`, `ll-verify-decisions`, `ll-verify-package-data`,
`ll-verify-kinds`, `ll-verify-design-tokens`, `ll-verify-des-audit`,
`ll-check-links`) with no aggregation point. `ll-doctor` is the natural one.

## Use Case

A user installs or upgrades little-loops, or returns to a project after a
version bump, and runs `ll-doctor`. Instead of a host-only table, they get a
single verdict on whether this installation is coherent: entry points resolve,
skills and commands are discoverable, the decisions store and history DB are
readable, loops validate, and the host supports what the configured loops
require. When something is broken, they get the specific failing check and the
command to investigate it.

## Current Behavior

- `ll-doctor` prints host capabilities, `analytics.capture` state, and
  `issues.auto_commit` state. Nothing else.
- Install-integrity signals are scattered across ~10 `ll-verify-*` CLIs that a
  user must know about individually and run by hand.
- Drift like a stale CLI allowlist or a missing package-data asset surfaces only
  at failure time.

## Expected Behavior

`ll-doctor` reports install health in clearly separated sections, keeps the
existing host-capability section, and exits non-zero on genuine problems. Each
check is fast, read-only, and degrades gracefully when its subject is absent
(e.g. no `.ll/history.db` yet is not an error on a fresh install).

## Acceptance Criteria

- [ ] `ll-doctor` verifies every `[project.scripts]` entry point in
      `scripts/pyproject.toml` resolves to an importable callable, and reports
      any that do not.
- [ ] Reports discoverability counts and any load failures for skills
      (`skills/*/SKILL.md`) and commands (`commands/*.md`).
- [ ] Reports presence/health of `.ll/decisions.yaml` and/or `.ll/decisions.d/`
      (accepting either — a fresh install has only the fragment dir).
- [ ] Reports `.ll/history.db` presence and readability; absent is informational,
      not a failure.
- [ ] Reports FSM loop validity (aggregating `ll-loop validate`) without running any loop.
- [ ] Aggregates the existing `ll-verify-*` checks behind an opt-in flag
      (e.g. `--full`), so the default run stays fast.
- [ ] All new checks are read-only and never mutate project state.
- [ ] Exit code semantics are documented and distinguish "unsupported host
      capability" from "broken install."
- [ ] `--json` includes every new section (depends on ENH-2762's parity fix).
- [ ] Absent optional subsystems produce an informational status, not a failure.

## Motivation

Diagnosing a half-broken little-loops install currently requires knowing which
of ~10 verifiers to run and in what order. Consolidating them behind the command
literally named "doctor" turns tribal knowledge into one invocation, and gives
new-project onboarding (`ll-init`) a single post-install verification step.

## API/Interface

```python
# ll-doctor                 # host capabilities + fast install checks (default)
# ll-doctor --full          # additionally aggregate the ll-verify-* family
# ll-doctor --json          # all sections, machine-readable
```

Design decisions to settle during refinement:
- ~~Whether aggregation shells out to each `ll-verify-*` binary or imports their
  `main_*` functions directly~~ **Resolved**: import. Every `ll-verify-*`
  checker already separates a pure `_run()` from its argparse-owning
  `main_verify_*()` wrapper (e.g. `verify_decisions.py:50-78`/`81-124`,
  `verify_kinds.py:38-47`/`50-70`), so `--full` aggregation can call each
  verifier's `_run()` directly in-process — no verifier requires shell-out.
- **Still open**: how to keep the check inventory from going stale. Codebase
  research surfaced two competing shapes with no clear winner: (a) a
  module-level `_CHECKS` list of `Callable[[], CheckResult]` (mirrors
  `CapabilityEntry`/`CapabilityReport`'s frozen-dataclass shape), vs. (b) no
  registry at all — independent `_<name>_section_data()`/`_print_<name>_section()`
  pairs merged by the CLI entrypoint, the pattern `doctor.py` and `ctx_stats.py`
  already use. Needs a human call before implementation.

## Proposed Solution

Introduce a lightweight check-registry protocol (name, category, run → status +
note) and have `ll-doctor` iterate it, rendering with the existing
`_STATUS_SYMBOLS` vocabulary. Register the host-capability report as one
category so the current output is preserved rather than special-cased. Verifiers
opt in by registering, which keeps `doctor.py` from becoming a hardcoded
inventory that drifts (the exact failure mode this issue is trying to fix).

Gate the expensive checks behind `--full` so the default stays sub-second.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — the aggregation surface
- `scripts/pyproject.toml` — source of truth for entry points to verify

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_*.py` (and siblings) — the checks to aggregate
- `scripts/little_loops/init/` — `ll-init` could invoke doctor as a post-install step
- `scripts/little_loops/host_runner.py` — existing capability path stays intact

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports and exports `main_doctor` in `__all__` (line ~64, ~114); no change needed unless new install-surface helper functions are also meant to be publicly importable [Agent 1 finding]
- `scripts/little_loops/init/writers.py` — lists `"Bash(ll-doctor:*)"` in the `_LL_PERMISSIONS` tuple (line ~43) and documents `ll-doctor` in the generated CLI tools list (line ~109-125); update the docstring/comment if doctor's scope description changes [Agent 1 finding]
- `docs/codex/usage.md` — "Note for CI/`ll-doctor` consumers" section documents historical exit-code behavior tied solely to `agent_select` capability status; will read as incomplete once install-surface failures can also cause exit 1 [Agent 2 finding]
- `docs/codex/README.md:42` — "Run `ll-doctor` ... to see exactly which capabilities and hook intents are wired" implies capability-only scope; update wording once install-surface sections exist [Agent 2 finding]

### Similar Patterns
- The `ll-verify-*` family's shared exit-code convention (1 on any violation)
- `ll-ctx-stats` — another aggregate-reporting CLI to match in output style

### Tests
- New `scripts/tests/test_cli_doctor_install_checks.py`
- `scripts/tests/test_cli_doctor.py` — ensure existing output is unchanged by default
  (existing test style: direct `main_doctor()` calls with `sys.argv`/`resolve_host`/
  `BRConfig`/`print` patched, e.g. `_make_runner()` at lines 30-34 and
  `_json_safe_config()` at 43-53; JSON-mode tests parse captured print lines with
  `json.loads()`. New install-surface tests should follow the same direct-call
  pattern, per `test_verify_kinds.py`'s `TestRun` (pure-function, no argv mocking)
  vs. `TestMainVerifyKinds` (wrapper, `patch("sys.argv", ...)`) split.)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor.py::TestMainDoctor.test_exit_zero_on_real_claude_code_report` (line ~83) exercises the *real* `ClaudeCodeRunner()` with no cwd control; if new install-surface checks run unconditionally (not gated behind `--full`) and touch real filesystem paths (`pyproject.toml`, `.ll/decisions.d/`, `.ll/history.db`), this test will break unless the new logic is mocked or gated by `--full` [Agent 3 finding]
- `scripts/tests/test_cli_doctor.py::TestMainDoctor.test_json_output_flag` (line ~260) asserts `assert "hooks" not in data` as a BUG-2760 regression guard; a companion negative-assertion test pinning the exact new install-surface JSON key surface is worth adding alongside the new sections [Agent 3 finding]
- `scripts/tests/test_tool_catalog.py` — tests `assemble_tool_catalog()` directly against `tmp_path` fixtures; the new doctor catalog-discoverability check should `patch("little_loops.cli.doctor.assemble_tool_catalog", ...)` rather than duplicate this suite's fixture coverage [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — exhaustively covers `load_and_validate()`'s validation rules across 10+ call sites; the new doctor loop-validity check should `patch("little_loops.cli.doctor.load_and_validate", ...)` with a canned `(fsm, warnings)` tuple rather than re-deriving that coverage [Agent 3 finding]
- Convention confirmed by `test_verify_decisions.py`/`test_verify_package_data.py`: unit-test each new check's pure helper directly (dedicated `Test<Helper>` class per function), then one or two `TestMainDoctor`-style CLI-wrapper tests exercising it end-to-end — not full edge-case re-coverage at the CLI layer [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md:228` — `ll-doctor` section
- `docs/reference/HOST_COMPATIBILITY.md` — clarify doctor is no longer host-only
- `commands/help.md:296` — one-line description
- `.claude/CLAUDE.md:235` — CLI tools list entry

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:235` — exit-code line ("`0` = all capabilities supported, `1` = one or more capabilities unsupported") is stale the moment install-surface checks can also flip the code — needs rewording alongside the new sections [Agent 2 finding]
- `docs/reference/API.md` — two `CapabilityReport`/`describe_capabilities` entries note `ll-doctor --json`'s payload adds `analytics_capture`/`issues` keys on top of the report; needs another sentence for any new top-level keys the install-surface checks add [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `CapabilityReport` table row repeats the same "superset... analytics_capture/issues keys" framing that will go stale with new keys [Agent 2 finding]
- `CONTRIBUTING.md:666` — references "0 skill descriptions dropped" wording near an `ll-doctor` mention; cross-verify against the new catalog-discoverability section's exact wording so the instruction stays actionable [Agent 2 finding]
- Constrained by (do not remove the literal `"ll-doctor"` substring from any of these — asserted by wiring tests): `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md` (`test_wiring_cli_registry.py`), `docs/reference/HOST_COMPATIBILITY.md` (`test_wiring_guides_and_meta.py`, `test_wiring_reference_docs.py`), `skills/configure/areas.md` (`test_wiring_init_and_configure.py`), `CONTRIBUTING.md` (`test_wiring_guides_and_meta.py`) [Agent 3 finding]

### Configuration
- May read `.ll/ll-config.json` for which subsystems are enabled (e.g. skip
  history checks when `history` is disabled).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current `doctor.py` shape** (`scripts/little_loops/cli/doctor.py`): `_STATUS_SYMBOLS`
  (lines 18-22) is a 3-entry dict already shared across sections. Each section
  follows a `_<name>_section_data()` (pure dict builder) / `_print_<name>_section()`
  (text renderer) pair — `_capture_section_data()`/`_print_capture_section()` (25-64),
  `_issues_section_data()`/`_print_issues_section()` (36-77). `_print_report()`
  (103-141) merges every section's data dict into one JSON payload — confirms
  ENH-2762's JSON/text parity fix already lands both sections in `--json`. New
  install-surface sections should follow this exact `_data()`/`_print_()` pair
  shape. `main_doctor()`'s exit code today is `0 if not any(c.status ==
  "unsupported" for c in report.capabilities) else 1` (line 200) — install-surface
  failures are not yet wired into this, matching the AC's open exit-code question.
- **`ll-verify-*` reusable-without-argparse split**: `verify_decisions.py` (and
  `verify_kinds.py`, `docs.py`'s `main_verify_skills`) each separate a pure
  `_run() -> tuple[int, ...]` from the argparse-owning `main_verify_*()` wrapper
  (e.g. `verify_decisions.py:50-78` / `81-124`, `verify_kinds.py:38-47` / `50-70`).
  This resolves the issue's open "shell out vs import" question in favor of
  **import**: `--full` aggregation can call each verifier's `_run()` directly
  in-process, sidestepping both subprocess overhead and `sys.argv` mutation —
  no verifier requires shell-out.
- **No decorator-based check registry exists in this codebase.** The closest
  analogues: `HostRunner` is a `@runtime_checkable Protocol` (`host_runner.py:158`)
  where each runner (`ClaudeCodeRunner`, `CodexRunner`, etc.) implements
  `describe_capabilities() -> CapabilityReport` inline (no self-registration);
  and `extension.py`'s `ExtensionLoader.from_entry_points()` (135-180) discovers
  extensions via `importlib.metadata.entry_points(group="little_loops.extensions")`
  with a try/except-per-item load. A `CheckRegistry` for doctor would be new
  code — most naturally a `list[Callable[[], CheckResult]]` populated by a
  module-level `_CHECKS` list in `doctor.py` (mirroring `CapabilityEntry` /
  `CapabilityReport`'s frozen-dataclass shape at `host_runner.py:131,144`) rather
  than an entry-points registry, since checks are internal to little-loops
  itself, not third-party-pluggable.
- **Skill/command discovery already has a canonical helper**: `assemble_tool_catalog()`
  in `scripts/little_loops/tool_catalog.py` walks `skills/*/SKILL.md` and
  `commands/*.md` frontmatter — reuse this instead of a fresh glob (the issue's
  Integration Map didn't list this file; it's the source of truth `tool_catalog.py`
  vs. the simpler `.glob("*/SKILL.md")` idiom in
  `cli/generate_skill_descriptions.py:98`).
- **Loop validation is directly callable, no subprocess needed**:
  `load_and_validate(path, raise_on_error=False)` in `fsm/validation.py:3022-3047`
  returns `(FSMLoop, list[ValidationError])`; `cli/loop/config_cmds.py:12-69`
  (`cmd_validate`) shows the call-site idiom, checking
  `any(v.severity == ValidationSeverity.ERROR for v in violations)`.
- **`.ll/history.db` readability check**: `session_store.py` exposes
  `DEFAULT_DB_PATH = Path(".ll/history.db")` (line 121) and `connect()` (1364) /
  `ensure_db()` (1323) as the existing low-level primitives to probe.
- **`.ll/decisions.d/` health check**: `decisions.py:load_decisions()` (354-370)
  merges the flat file with fragments but silently skips malformed fragments
  (BUG-2644); `verify_decisions.py:_run()` (50-78) demonstrates the stricter
  two-pass idiom (load_decisions() for the flat file, then a direct re-glob of
  `.ll/decisions.d/*.json` via `_entry_from_dict()` to surface fragment
  corruption load_decisions() would otherwise swallow) — reuse this two-pass
  pattern rather than calling `load_decisions()` alone.
- **Entry-point enumeration source**: `scripts/pyproject.toml:57-105` lists
  `[project.scripts]` as `ll-<name> = "little_loops.<module>:<function>"` pairs.
  No existing helper parses this generically; new logic would need `tomllib`
  (stdlib, Python 3.11+) to read the TOML and `importlib.import_module()` +
  `getattr()` per pair, distinguishing "module not found" from "function
  renamed/removed" failures — the same try/except-per-item shape as
  `extension.py`'s `from_config()` (135-157).
- **Line-number correction** (2026-07-25 refine pass): the earlier research's
  "`_capture_section_data()`/`_print_capture_section()` (25-64)" and
  "`_issues_section_data()`/`_print_issues_section()` (36-77)" ranges each
  collapse a data-builder and its printer into one span. Actual current
  ranges in `doctor.py`: `_capture_section_data` 25-33, `_issues_section_data`
  36-41, `_print_capture_section` 44-64, `_print_issues_section` 67-77.
  `_print_report()` (103-141) and `main_doctor()`'s exit-code line (~200,
  `return 0 if not any(... unsupported ...) else 1`) are unchanged and still
  unwired to any install-surface check. No `--full` flag, registry, or new
  sections exist yet — the file's overall shape is otherwise unchanged.
- **Two additional aggregate-report patterns beyond `HostRunner`/`ExtensionLoader`**
  (not covered by the prior pattern-finder pass): (1) `link_checker.py`'s
  `LinkResult` (per-item dataclass: `status: str` free-form + optional `error`)
  paired with `LinkCheckResult` (parent aggregate: counters + `results: list[...]`
  + a derived `has_errors` property used for exit-code decisions) — a simpler
  alternative to a decorator-registry if the check-registry design favors a
  plain aggregate-dataclass over a `Protocol`/self-registering list. (2)
  `cli/ctx_stats.py` independently calls section builders (e.g.
  `_aggregate_skill_stats` from `cli/logs.py`) and merges their output into one
  JSON payload/printed report — the same "independent section builders merged
  by the CLI entrypoint" shape `doctor.py` already uses for
  `_capture_section_data`/`_issues_section_data`, reinforcing that new
  install-surface sections should follow this shape rather than a registry
  abstraction if simplicity is prioritized over the "opt-in checks" goal in
  Proposed Solution.
- **Sibling issues under the same EPIC-2765 overlap this issue's surface** and
  are worth sequencing awareness for: BUG-2759 (doctor always exits 1 on
  Claude Code — exit-code correctness, feeds directly into this issue's exit-code
  AC), ENH-2762 (JSON parity — appears already implemented per `_print_report()`
  analysis above), ENH-2761 (host version probe), BUG-2760 (capability report
  hooks section never populated), BUG-2764 (permission-preset drift, whose fix
  is `ll-verify-cli-allowlist` — a candidate `--full` check this issue's own AC
  already lists as part of the `ll-verify-*` family).

## Implementation Steps

1. Inventory the existing `ll-verify-*` family and decide shell-out vs. import.
2. Define the check-registry protocol and port the host-capability report onto it.
3. Implement the fast default checks (entry points, skills/commands, decisions,
   history DB, loop validity).
4. Add `--full` aggregation of the verifier family.
5. Settle and document exit-code semantics; wire `--json` output.
6. Update CLI docs, help, and CLAUDE.md.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/API.md` and `docs/ARCHITECTURE.md` — extend the `CapabilityReport`/`--json` payload notes to cover new top-level keys.
8. Update `docs/codex/usage.md` and `docs/codex/README.md:42` — the CI/exit-code note and capability-only framing both go stale once install-surface failures can flip the exit code.
9. Verify `CONTRIBUTING.md:666`'s "0 skill descriptions dropped" wording against the new catalog-discoverability section's actual output text.
10. When adding new tests, mock `assemble_tool_catalog()` and `load_and_validate()` at their `cli.doctor` import site rather than re-deriving `test_tool_catalog.py`/`test_fsm_validation.py` coverage; add a `--full`/cwd-independence guard so `test_exit_zero_on_real_claude_code_report` doesn't break.

## Impact

- **Priority**: P3 - High long-term value for onboarding and drift detection, but
  no user is currently blocked.
- **Effort**: Large - Touches many subsystems and needs a registry design plus an
  exit-code policy decision; a strong candidate for decomposition into a
  registry-foundation issue and per-category check issues.
- **Risk**: Medium - Aggregating verifiers risks slow or flaky default runs and
  false failures on fresh/partial installs; mitigated by `--full` gating and
  graceful-absence handling. Changing exit-code semantics could affect anything
  scripting `ll-doctor`.
- **Breaking Change**: Possibly — new failure categories can flip exit codes for
  existing automation. Decide whether new checks affect exit status by default or
  only under `--full`.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CLI.md` | ll-doctor and the ll-verify-* family |
| `.claude/CLAUDE.md` | Canonical CLI tool inventory |
| `docs/ARCHITECTURE.md` | Where a check registry would sit |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-25_

**Readiness Score**: 96/100 → READY
**Outcome Confidence**: 50/100 → Low

### Concerns
- All four dependency issues (ENH-2762, BUG-2759, BUG-2760, BUG-2764) are confirmed `done`, so the readiness score is high, but the issue itself flags "Large" effort and is a "strong candidate for decomposition" — this is reflected in the low outcome confidence below.

### Outcome Risk Factors
- Broad enumeration across 15+ sites (doctor.py, pyproject.toml, ~6 test files, ~8 doc files) spanning multiple subsystems (CLI, tests, docs) with non-uniform, per-site changes rather than a mechanical sweep — lower change-surface verifiability.
- Deep per-site complexity: the check-registry protocol is new design (no existing decorator/registry analogue in the codebase), not a mechanical extension of an established pattern.
- Open decision point on exit-code semantics: whether new install-surface checks affect the default exit status or only under `--full` is explicitly unresolved in the issue's own "Design decisions to settle" and Impact/Breaking-Change sections — resolve before implementing, since it affects any automation scripting `ll-doctor`.

## Session Log
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-into-FEAT-2793,2794,2795,2796`
- `/ll:decide-issue` - 2026-07-25T13:46:39 - `71a939cf-d4b0-4e35-96bf-69575fcb8cac.jsonl`
- `/ll:refine-issue` - 2026-07-25T13:44:39 - `bfe26309-5437-4983-8b89-f9017370c458.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `934bbd58-3513-406d-abcc-3ef8fb9ab46e.jsonl`
- `/ll:wire-issue` - 2026-07-25T13:38:44 - `0a306329-f2d2-4e3b-8fab-3741ff1d88f9.jsonl`
- `/ll:refine-issue` - 2026-07-25T13:29:07 - `70f9cf40-9443-47df-bc6c-072be163aa66.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-25
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- FEAT-2793: Introduce ll-doctor check-registry protocol and settle exit-code semantics
- FEAT-2794: Add ll-doctor fast default install-surface checks
- FEAT-2795: Add ll-doctor --full aggregation of the ll-verify-* family
- FEAT-2796: Document ll-doctor's new install-surface sections

## Status

**Done** | Created: 2026-07-24 | Priority: P3
