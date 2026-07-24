---
id: FEAT-2763
type: feature
priority: P3
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
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
- Whether aggregation shells out to each `ll-verify-*` binary or imports their
  `main_*` functions directly (import is faster and avoids process overhead, but
  couples ll-doctor to their internals).
- How to keep the check inventory from going stale — a registry the verifiers
  opt into is better than a hardcoded list in `doctor.py`.

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

### Similar Patterns
- The `ll-verify-*` family's shared exit-code convention (1 on any violation)
- `ll-ctx-stats` — another aggregate-reporting CLI to match in output style

### Tests
- New `scripts/tests/test_cli_doctor_install_checks.py`
- `scripts/tests/test_cli_doctor.py` — ensure existing output is unchanged by default

### Documentation
- `docs/reference/CLI.md:228` — `ll-doctor` section
- `docs/reference/HOST_COMPATIBILITY.md` — clarify doctor is no longer host-only
- `commands/help.md:296` — one-line description
- `.claude/CLAUDE.md:235` — CLI tools list entry

### Configuration
- May read `.ll/ll-config.json` for which subsystems are enabled (e.g. skip
  history checks when `history` is disabled).

## Implementation Steps

1. Inventory the existing `ll-verify-*` family and decide shell-out vs. import.
2. Define the check-registry protocol and port the host-capability report onto it.
3. Implement the fast default checks (entry points, skills/commands, decisions,
   history DB, loop validity).
4. Add `--full` aggregation of the verifier family.
5. Settle and document exit-code semantics; wire `--json` output.
6. Update CLI docs, help, and CLAUDE.md.

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

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
