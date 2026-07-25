---
id: FEAT-2796
type: feature
priority: P3
status: open
parent: FEAT-2763
blocked_by: FEAT-2794, FEAT-2795
---

# FEAT-2796: Document ll-doctor's new install-surface sections

## Summary

Once FEAT-2793/2794/2795 land the check-registry, fast default checks, and
`--full` aggregation, update every doc site that describes `ll-doctor`'s scope
so none of them still read as "host-capability-only."

## Parent Issue

Decomposed from FEAT-2763: Expand ll-doctor to validate little-loops' own
install surface. This child covers Implementation Steps 6-9 (the parent's
wiring-phase doc touchpoints). It is documentation for already-shipped
behavior (FEAT-2793/2794/2795), not new-behavior docs split from their
implementation — the exception `issue-size-review`'s "never split docs into a
dedicated child" rule allows.

## Acceptance Criteria

- [ ] `docs/reference/CLI.md:228` `ll-doctor` section describes the new
      default sections and `--full`.
- [ ] `docs/reference/HOST_COMPATIBILITY.md` clarifies doctor is no longer
      host-only.
- [ ] `commands/help.md:296` one-line description updated.
- [ ] `.claude/CLAUDE.md:235` CLI tools list entry updated.
- [ ] `docs/reference/API.md` — `CapabilityReport`/`describe_capabilities`
      entries note the new top-level `--json` keys the install-surface checks
      add.
- [ ] `docs/ARCHITECTURE.md` — `CapabilityReport` table row updated with the
      same new-keys framing.
- [ ] `docs/codex/usage.md` "Note for CI/`ll-doctor` consumers" section
      updated: exit-code behavior is no longer tied solely to `agent_select`
      capability status.
- [ ] `docs/codex/README.md:42` wording updated — no longer implies
      capability-only scope.
- [ ] `CONTRIBUTING.md:666` "0 skill descriptions dropped" wording verified
      against the new catalog-discoverability section's actual output text.
- [ ] The literal `"ll-doctor"` substring is preserved in every file listed
      above (asserted by existing wiring tests: `test_wiring_cli_registry.py`,
      `test_wiring_guides_and_meta.py`, `test_wiring_reference_docs.py`,
      `test_wiring_init_and_configure.py`).
- [ ] `docs/reference/CLI.md:235` exit-code line matches the FEAT-2793 policy
      exactly (avoid re-diverging from that issue's wording).

## Files

- `docs/reference/CLI.md`
- `docs/reference/HOST_COMPATIBILITY.md`
- `commands/help.md`
- `.claude/CLAUDE.md`
- `docs/reference/API.md`
- `docs/ARCHITECTURE.md`
- `docs/codex/usage.md`
- `docs/codex/README.md`
- `CONTRIBUTING.md`
- `skills/configure/areas.md` (verify literal substring only, per wiring test)

## Execution Pattern

Strictly sequential after FEAT-2794 and FEAT-2795 — the doc content depends on
what those two issues actually ship (exact `--json` keys, exact `--full`
section names, exact output wording).

## Session Log
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
