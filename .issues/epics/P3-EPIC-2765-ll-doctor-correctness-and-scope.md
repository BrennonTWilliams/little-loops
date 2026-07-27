---
id: EPIC-2765
title: 'll-doctor: report correctness and install-surface scope'
type: EPIC
priority: P3
status: open
captured_at: '2026-07-24T19:36:28Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
relates_to:
- BUG-2759
- BUG-2760
- ENH-2761
- ENH-2762
- BUG-2764
- FEAT-2793
- FEAT-2794
- FEAT-2795
- FEAT-2796
- ENH-2836
labels:
- cli
- doctor
- host-runner
- dx
---

# EPIC-2765: ll-doctor — report correctness and install-surface scope

## Summary

`ll-doctor` is documented as the preflight/CI gate for little-loops, but an
audit of the command found it both **incorrect within its own scope** and
**narrower than its name promises**.

Within scope, the report has drifted: it exits `1` on a fully-healthy
`claude-code` host because two capability entries describe the same
`--json-schema` flag with opposite verdicts; its "Hooks" section renders from a
field no runner ever populates; it never probes the host version despite
shipping a `build_version_check()` with no callers; and `--json` emits strictly
less than the human output.

Beyond scope, the command validates nothing about little-loops itself — not the
46 declared console entry points, not skills or commands, not the decisions
store, history DB, or loop validity. The ~10 `ll-verify-*` checkers that *do*
answer those questions have no aggregation point. A representative instance of
the resulting drift is included as a child: the `configure` skill's permission
preset still claims to authorize "all 31 ll- CLI tools" when there are 46.

## Goal

Make `ll-doctor` a report you can trust and act on: every line it prints is
true, `exit 0` genuinely means healthy, `--json` is a complete machine-readable
equivalent, and the command answers "is this installation coherent?" rather than
only "what can the host CLI do?".

## Scope

**In scope**
- Correcting the capability report's contradictory and unpopulated entries.
- Restoring meaningful exit-code semantics for the default host.
- Achieving text/JSON output parity.
- Wiring the existing, uncalled version probe.
- Extending the command to validate little-loops' own install surface, with the
  `ll-verify-*` family aggregated behind an opt-in flag.
- Fixing the stale CLI permission preset as a concrete instance of hand-maintained
  inventory drift, and gating it against recurrence.

**Out of scope**
- Gating individual capability statuses on detected host versions (a separate
  compatibility-matrix decision).
- Adding new host runners or changing host capability semantics.
- Any change to hook *execution*; BUG-2760 covers hook *reporting* only.
- Migrating the `ll-verify-*` tools themselves — they are aggregated, not replaced.

## Children

- **BUG-2759** — ll-doctor always exits 1 on claude-code due to a contradictory `json_schema` capability entry
- **BUG-2760** — `CapabilityReport.hooks` is never populated, so the Hooks section is dead code and the docs promise output that never renders
- **ENH-2761** — ll-doctor never probes the host binary version despite an unused `build_version_check()`
- **ENH-2762** — `ll-doctor --json` omits the Analytics Capture and Issues config sections
- **FEAT-2763** — Expand ll-doctor to validate little-loops' own install surface and aggregate the `ll-verify-*` family
- **BUG-2764** — The configure skill's ll- CLI permission allowlist is stale (31 of 46 tools)
- **ENH-2836** — `ll-check-links` conflates network timeouts with broken links and exits 1, so `ll-doctor --full` fails on ambient network conditions

### Suggested sequencing

1. **BUG-2759** first — smallest change, restores the exit-code contract that
   everything downstream depends on for meaning.
2. **ENH-2762** next — establishes text/JSON parity, which FEAT-2763 needs so its
   new sections aren't born human-only.
3. **BUG-2760** and **ENH-2761** are independent of each other and can proceed in
   parallel; both touch `describe_capabilities()` across all six runners, so
   coordinate to avoid conflicting edits.
4. **FEAT-2763** last among the doctor changes — it is the largest, built on
   ENH-2762, and should land after the report's existing surface is correct.
5. **BUG-2764** is fully independent (different file, different subsystem) and can
   be done at any point.

Note: FEAT-2763 is sized Large in its own Impact section and flags itself as a
decomposition candidate. Expect `/ll:issue-size-review` to split it into a
check-registry foundation plus per-category check issues; those splits become
grandchildren of this epic.

## Motivation

`ll-doctor` occupies a position of authority — `docs/guides/LOOPS_GUIDE.md`
tells users to run it before relying on `suppress_catalog` / `suppress_claude_md`,
and `docs/codex/usage.md` treats its exit code as the CI signal. A gate that is
permanently red on the default host and prints a section that never appears
trains users and automation to ignore it, which quietly nullifies the entire
capability-reporting layer built out across the FEAT-1496/1503/1504/1524/1525
chain.

The scope half matters for a different reason: diagnosing a half-broken install
currently requires knowing which of ~10 verifiers to run and in what order.
Consolidating them behind the command named "doctor" converts tribal knowledge
into one invocation and gives `ll-init` a natural post-install verification step.

## Success Metrics

- `ll-doctor` exits `0` on a healthy `claude-code` host.
- No capability entry contradicts another, enforced by a test.
- Every section shown in text output is present in `--json`, enforced by a parity test.
- The report contains no rendering branch that no producer populates.
- `[project.scripts]` entry points are verified by the tool and gated in the
  permission preset by a test, so neither inventory can drift silently again.

## Impact

- **Priority**: P3 - No user is blocked, but a documented gate is untrustworthy
  and the fixes are mostly small and independently landable.
- **Effort**: Large in aggregate; four children are Small and one (FEAT-2763) is
  Large and expected to decompose further.
- **Risk**: Medium - Concentrated in FEAT-2763 (exit-code policy changes could
  affect anything scripting `ll-doctor`; aggregating verifiers risks slow or
  flaky default runs and false failures on fresh installs). The four correctness
  children are Low risk individually.
- **Breaking Change**: Possibly, via FEAT-2763 — new failure categories can flip
  exit codes for existing automation. BUG-2759 also changes the claude-code exit
  code from 1 to 0, which is the intended fix but should be confirmed against any
  automation currently depending on the failure.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — the report surface (all doctor children)
- `scripts/little_loops/host_runner.py` — `describe_capabilities()` across six runners
- `skills/configure/areas.md` — permission preset (BUG-2764)
- `scripts/pyproject.toml` — source of truth for the entry-point inventory

### Dependent Files (Callers/Importers)
- `ll-action capabilities` — shares `CapabilityReport`; affected by every change to it
- `scripts/little_loops/cli/verify_*.py` and siblings — aggregation targets for FEAT-2763
- `scripts/little_loops/init/` — candidate caller for a post-install doctor run

### Similar Patterns
- The `ll-verify-*` family's shared exit-code convention (1 on any violation)
- `ll-ctx-stats` — another aggregate-reporting CLI to match in output style

### Tests
- `scripts/tests/test_cli_doctor.py`
- `scripts/tests/test_host_runner.py`
- New: install-check tests, JSON/text parity test, entry-point allowlist gate

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — capability matrix, exit-code contract, the unfulfilled per-hook claim
- `docs/reference/CLI.md:228` — `ll-doctor` section
- `docs/reference/API.md` — `CapabilityReport` / `HookEntry` model
- `docs/codex/usage.md:96`, `docs/codex/README.md:42` — exit-code and capture-state notes
- `.claude/CLAUDE.md:235`, `commands/help.md:296` — CLI inventory entries

### Configuration
- Reads `.ll/ll-config.json` (`analytics.capture`, `issues`, and potentially
  per-subsystem enablement for FEAT-2763); no new keys expected.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Capability matrix and the exit-code contract this epic restores |
| `docs/reference/API.md#capabilityreport` | `CapabilityReport` / `HookEntry` data model |
| `docs/ARCHITECTURE.md` | `CapabilityReport` row (~line 875); where a check registry would sit |
| `.claude/CLAUDE.md` | Canonical CLI tool inventory |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
