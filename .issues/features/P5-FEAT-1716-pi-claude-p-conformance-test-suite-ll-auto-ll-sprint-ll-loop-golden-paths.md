---
id: FEAT-1716
title: Pi `claude -p` conformance test suite (ll-auto / ll-sprint / ll-loop golden paths)
type: FEAT
status: open
priority: P5
captured_at: "2026-05-26T02:06:59Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1713
depends_on: [FEAT-1714, FEAT-1480]
relates_to: [FEAT-992, FEAT-1478]
labels: [feat, captured, pi-adapter, testing, host-compat, conformance]
---

# FEAT-1716: Pi `claude -p` conformance test suite (ll-auto / ll-sprint / ll-loop golden paths)

## Summary

Run the existing `claude -p`-dependent orchestration entry points
(`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`) against
Pi as the host and assert behavioral equivalence on a small golden-path
suite. The output is a pass/fail report per entry point that turns the
hand-wavy "Pi as `claude -p` replacement" claim into a measurable one.

## Motivation

FEAT-992's Current Behavior section says, verbatim:

> Commands and skills may work via any compatible path fallback Pi
> supports

That is unverified. FEAT-1478's adapter integration test only proves
that `LL_HOOK_HOST=pi` propagates and that the 2 wired events dispatch.
Nothing exercises the actual orchestration paths users invoke daily.

Without a conformance suite:

- Regressions in `PiRunner.build_*` won't be caught
- New `claude -p` flags added to Claude Code's invocation paths won't
  surface as Pi gaps until a user hits them in production
- Marketing/docs language like "first-class Pi support" has no evidence
  behind it

## Acceptance Criteria

- A test module (e.g. `scripts/tests/conformance/test_pi_claude_p_parity.py`)
  with a small but representative golden-path suite covering:
  - `ll-action` invoking a trivial skill end-to-end against Pi
  - `ll-auto` processing a single tiny throwaway issue against Pi
  - `ll-loop run <a-no-op-loop>` completing successfully against Pi
  - At least one FSM evaluator path (`fsm/evaluators.py:609`
    `build_blocking_json` call) producing a structured response on Pi
  - At least one `fsm/handoff_handler.py:116` `build_detached` path
    spawning correctly on Pi
- Tests are **skipped** (not failed) when `pi` is not on PATH, so the
  suite is safe to ship in CI without forcing every CI worker to install
  Pi
- A `make conformance-pi` (or `pytest -m conformance_pi`) entrypoint so
  the suite can be run on demand on a machine with Pi installed
- A `docs/development/CONFORMANCE.md` (or section in TESTING.md) entry
  documenting how to run and interpret the suite
- Initial baseline run captured in the same doc — every path either ✓
  or ✗ with a citation to the breaking flag/event (which then becomes
  a real issue rather than folklore)

## Use Case

A maintainer touching `PiRunner` runs `pytest -m conformance_pi` locally
before pushing. They get a 5-row green/red board telling them whether
their change preserves end-to-end equivalence with Claude Code, not
just whether unit-level argv snapshots still match.

## Proposed Solution

### Step 1: Inventory `claude -p` call sites

Confirm the canonical list of `resolve_host().build_*` callers
(currently per FEAT-1480 integration map):
- `scripts/little_loops/subprocess_utils.py:263` — `build_streaming`
- `scripts/little_loops/cli/action.py:149` — `build_version_check`
- `scripts/little_loops/parallel/worker_pool.py:576` — `build_blocking_json`
- `scripts/little_loops/fsm/evaluators.py:609` — `build_blocking_json`
- `scripts/little_loops/fsm/handoff_handler.py:116` — `build_detached`

### Step 2: Design golden paths

For each call site, pick the smallest user-facing entry point that
exercises it. Keep total wall-clock under ~2 minutes so the suite is
runnable interactively.

### Step 3: Implement the test module

- Decorate tests with `@pytest.mark.skipif(shutil.which("pi") is None,
  reason="pi CLI not installed")`
- Force the host via `monkeypatch.setenv("LL_HOST_CLI", "pi")` rather
  than relying on probe order
- Use temp directories / fixture repos for any disk-touching paths
- Assert on observable outcomes (exit code, output file existence,
  expected stdout fragment) — not on internal argv shape (those tests
  live in `test_host_runner.py`)

### Step 4: Document the baseline

Run the suite once Pi is wired (after FEAT-1480 + FEAT-1714 land),
capture the initial pass/fail board in `docs/development/CONFORMANCE.md`,
and file follow-up issues for any ✗ entries.

## Integration Map

### Files to Create
- `scripts/tests/conformance/__init__.py` (if `conformance/` subdir
  doesn't exist)
- `scripts/tests/conformance/test_pi_claude_p_parity.py` — the suite
- `docs/development/CONFORMANCE.md` (or new section in
  `docs/development/TESTING.md`) — how to run; baseline results

### Files to Modify
- `pyproject.toml` — register `conformance_pi` pytest marker so it can
  be selected/deselected
- `Makefile` (if it exists) — `conformance-pi` target wrapping the
  pytest invocation

### Reference Files (Read-Only)
- `scripts/tests/test_host_runner.py` — argv-snapshot precedent (not
  what this suite does, but useful to avoid duplicating)
- `scripts/tests/test_codex_adapter.py` — closest analog for
  cross-host integration testing
- `scripts/little_loops/host_runner.py` — call surface to exercise

## Out of Scope

- Conformance suites for OpenCode or Codex (worth doing later but not
  this issue's job)
- Performance/latency benchmarking (separate concern)
- UI-level testing of any host (none of these CLIs are graphical)

## Dependencies

- **`depends_on: FEAT-1714`** — the suite needs `PiRunner` to be wired
  with real (audited) flags; without FEAT-1714 the wiring is
  speculative and any ✗ could be either a Pi-CLI gap or a wiring bug
- **`depends_on: FEAT-1480`** — `PiRunner.build_*` must not raise
  `HostNotConfigured` for the suite to run at all

## Impact

- **Priority**: P5 — matches Pi-adapter tier; gates aspirational
  "first-class replacement" claims
- **Effort**: Small (suite is small by design); long pole is
  setting up a Pi-installed test environment
- **Risk**: Low — additive test surface; doesn't change product
  behavior

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | The matrix this suite validates |
| `docs/development/TESTING.md` | Existing test conventions to follow |

## Labels

`feat`, `pi-adapter`, `testing`, `conformance`, `host-compat`, `captured`

## Verification Notes

2026-06-13 (OUTDATED): Conformance test suite not created. `scripts/tests/conformance/` directory does not exist. `docs/development/CONFORMANCE.md` does not exist. Cannot start until FEAT-1714 (Pi CLI audit) and FEAT-1480 (PiRunner wiring) are complete.

2026-06-18 (BLOCKED): Still blocked. `scripts/tests/conformance/` does not exist. `docs/development/CONFORMANCE.md` does not exist. Both deps (FEAT-1714 and FEAT-1480) remain open and unstarted.

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:13:02 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:55 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:17 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:06:59Z - `3eaac8be-eba9-48b8-a2d9-322df5114921.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Step 4 (Document the baseline) must cross-reference FEAT-1714's capability gap research note (`thoughts/research/pi-headless-cli.md`). Any ✗ row in the conformance baseline should cite the specific flag or capability gap identified in FEAT-1714's audit — e.g., "✗ build_streaming: Pi lacks `--output-format stream-json` equivalent (see FEAT-1714 research note § Streaming output)." This creates traceability from test evidence back to the audit that motivated the ✗, and ensures follow-up issues can be filed with precise flag references rather than folklore.
