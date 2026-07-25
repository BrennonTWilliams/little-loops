---
id: FEAT-2796
type: feature
priority: P3
status: done
parent: EPIC-2765
blocked_by: FEAT-2794, FEAT-2795
relates_to:
- FEAT-2763
confidence_score: 100
outcome_confidence: 88
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 23
testable: false
completed_at: '2026-07-25T15:21:18Z'
---

# FEAT-2796: Document ll-doctor's new install-surface sections

## Summary

Once FEAT-2793/2794/2795 land the check-registry, fast default checks, and
`--full` aggregation, update every doc site that describes `ll-doctor`'s scope
so none of them still read as "host-capability-only."

## Current Behavior

Every doc site listed under Files still frames `ll-doctor` as
host-capability-only: `commands/help.md:296`, `.claude/CLAUDE.md:236`, and
`scripts/little_loops/cli/__init__.py:40` all read verbatim "Check host CLI
capability support for little-loops features"; `docs/reference/API.md` and
`docs/ARCHITECTURE.md` document only the ENH-2762 `analytics_capture`/`issues`
keys; `docs/codex/usage.md`/`docs/codex/README.md` frame doctor's exit code
around `agent_select` alone; and `CONTRIBUTING.md:666` cites an output string
("0 skill descriptions dropped") that does not exist anywhere in
`doctor.py` — the real output is `"{N} tool(s) discovered"`.

## Expected Behavior

Every doc site accurately describes `ll-doctor`'s shipped install-surface
scope: the 5 default checks (entry points, skills/commands discoverability,
decisions store, history DB, loop validity), the `--full` aggregation of the
10 verifier adapters, the corresponding new `--json` top-level keys, and the
severity-based exit-code policy — with no lingering "host-capability-only" or
factually incorrect wording.

## Impact

Stale docs mislead contributors and CI/Codex consumers about what `ll-doctor`
actually validates and how its exit code is derived, and the incorrect
`CONTRIBUTING.md` output string would send a release-checklist reader looking
for text that was never emitted.

## Use Case

N/A — documentation-only issue; no end-user workflow changes.

## Parent Issue

Decomposed from FEAT-2763: Expand ll-doctor to validate little-loops' own
install surface. This child covers Implementation Steps 6-9 (the parent's
wiring-phase doc touchpoints). It is documentation for already-shipped
behavior (FEAT-2793/2794/2795), not new-behavior docs split from their
implementation — the exception `issue-size-review`'s "never split docs into a
dedicated child" rule allows.

## Acceptance Criteria

- [x] `docs/reference/CLI.md:228` `ll-doctor` section describes the new
      default sections and `--full`.
- [x] `docs/reference/HOST_COMPATIBILITY.md` clarifies doctor is no longer
      host-only.
- [x] `commands/help.md:296` one-line description updated.
- [x] `.claude/CLAUDE.md:236` CLI tools list entry updated.
- [x] `docs/reference/API.md` — `CapabilityReport`/`describe_capabilities`
      entries note the new top-level `--json` keys the install-surface checks
      add.
- [x] `docs/ARCHITECTURE.md` — `CapabilityReport` table row updated with the
      same new-keys framing.
- [x] `docs/codex/usage.md` "Note for CI/`ll-doctor` consumers" section
      updated: exit-code behavior is no longer tied solely to `agent_select`
      capability status.
- [x] `docs/codex/README.md:42` wording updated — no longer implies
      capability-only scope.
- [x] `CONTRIBUTING.md:666` "0 skill descriptions dropped" wording verified
      against the new catalog-discoverability section's actual output text.
- [x] The literal `"ll-doctor"` substring is preserved in every file listed
      above (asserted by existing wiring tests: `test_wiring_cli_registry.py`,
      `test_wiring_guides_and_meta.py`, `test_wiring_reference_docs.py`,
      `test_wiring_init_and_configure.py`).
- [x] `docs/reference/CLI.md:235` exit-code line matches the FEAT-2793 policy
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:40` — third independent one-line
  `ll-doctor` description (module docstring listing), reading `"Check host
  CLI capability support for little-loops features"` — same stale
  host-capability-only framing as `commands/help.md:296` and
  `.claude/CLAUDE.md:236`; will drift stale unless updated in the same pass
  [Agent 2/Agent 1 finding, cross-confirmed]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — `DOC_STRINGS_PRESENT` has
  no `"ll-doctor"`-related row for `docs/reference/API.md`; add one for the
  new `--json` key names once written, so a future edit can't silently drop
  them [Agent 3 finding]
- `scripts/tests/test_wiring_guides_and_meta.py` — `DOC_STRINGS_PRESENT` has
  no `"ll-doctor"`-related row for `docs/ARCHITECTURE.md`, `docs/codex/usage.md`,
  or `docs/codex/README.md`; add rows for each once their new wording lands
  (follow the existing `(doc_path, needle, "FEAT-2796")` tuple convention —
  no new test file needed) [Agent 3 finding]
- Confirmed safe: `CONTRIBUTING.md:666`'s stale phrase correction does not
  break `test_doc_counts.py:249` (`test_no_match_skill_descriptions_phrase`
  uses a hardcoded literal fixture, not a read of the real file) [Agent 3
  finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of the shipped
FEAT-2793/2794/2795 implementation (`scripts/little_loops/cli/doctor.py`,
878 lines — all doctor logic lives in this one module):_

**Check-registry protocol** (already shipped, for accurate doc wording):
`CheckResult` (frozen dataclass) has `name`, `status: Literal["full","partial","unsupported"]`,
`note`, `severity: Literal["error","informational"] = "error"`. `_CHECKS` is the
default-run registry (populated via `register_check()`); `_FULL_CHECKS` is the
parallel `--full`-only registry (via `register_full_check()`), kept separate so
the default run never executes them. `_exit_code_for(results)` returns `1` iff
any `severity="error"` result has `status="unsupported"` — `informational`
results never affect exit code.

**Default (non-`--full`) install-surface checks** (run unconditionally):
1. `_entry_points_check()` — validates every `[project.scripts]` entry in
   `pyproject.toml` is importable/callable; "Entry Points" section.
2. `_skills_commands_check()` — discoverability count via
   `assemble_tool_catalog()`; "Skills & Commands" section; **actual note text
   is `"{N} tool(s) discovered"`** (e.g. `"42 tool(s) discovered"`), status
   `full` on success or `"catalog load failed: {exc}"`/`unsupported` on
   failure — there is no "dropped" concept and no comparison against a prior
   count.
3. `_decisions_store_check()` — probes `.ll/decisions.yaml` +
   `.ll/decisions.d/*.json`; absent store is `severity="informational"`.
4. `_history_db_check()` — presence/readability probe on `.ll/history.db`
   (read-only, never create-on-demand); absent DB is informational.
5. `_loop_validity_check()` — aggregates `fsm.validation.load_and_validate()`
   over builtin + project-local loop YAMLs; no-loops-found is informational.

**`--full` aggregation** — runs `_run_full_checks()` in addition to defaults,
printed under header **"Full Verification (--full)"**. Wraps 10 verifiers
(name-prefixed `full:`): `docs` → `ll-verify-docs`, `skill_budget` →
`ll-verify-skill-budget`, `skills` → `ll-verify-skills`, `triggers` →
`ll-verify-triggers`, `decisions` → `ll-verify-decisions`, `package_data` →
`ll-verify-package-data`, `kinds` → `ll-verify-kinds`, `design_tokens` →
`ll-verify-design-tokens`, `des_audit` → `ll-verify-des-audit`,
`check_links` → `ll-check-links`. **Does NOT wrap `ll-verify-cli-allowlist`.**

**New `--json` top-level keys** (beyond existing `host`/`binary`/`version`/
`capabilities`/`analytics_capture`/`issues` from ENH-2762, already documented
in API.md/ARCHITECTURE.md): `entry_points` (list of `{name, status, note}`),
`skills_commands` (`{status, note, total}`), `decisions_store`
(`{status, note}`), `history_db` (`{status, note}`), `loop_validity`
(`{status, note, total, invalid}`), and `full` (only present when `--full`
is passed — dict keyed by verifier name → `{status, note}`).

**Exit-code policy** — no longer solely tied to `agent_select`/any single
capability. Any `severity="error"` `CheckResult` with `status="unsupported"`
fails the exit code, whether it originates from a host capability, a default
install-surface check, or (under `--full`) a verifier adapter. This is
**already correctly described** at `docs/reference/CLI.md:235` per
codebase-pattern-finder's read of the current file — AC's instruction to
"match exactly, avoid re-diverging" means don't touch that line's wording,
just verify it still matches (it does, as of this research pass).

**BUG confirmed**: `CONTRIBUTING.md:666` currently reads `...run `ll-doctor`
(`scripts/little_loops/cli/doctor.py`) and verify "0 skill descriptions
dropped".` — this exact string does not exist anywhere in `doctor.py`. The
real output is `"{N} tool(s) discovered"` under the "Skills & Commands"
section (see finding 2 above). This AC line needs a correction, not just
verification.

**Current stale surfaces to update:**
- `docs/reference/CLI.md:228-263` — `ll-doctor` section uses freeform
  `**Flags:**` bullets (not a table, matching `ll-ctx-stats` style
  immediately below it, not the `| Flag | Short | Description |` table style
  used by `ll-verify-docs`/`ll-verify-skill-budget`). It documents `--json`
  and the exit-code split but has **no mention of `--full`, no section names
  for the 5 default install-surface checks, and no example output for
  them** — only the JSON payload's `analytics_capture`/`issues` keys are
  shown in the example.
- `docs/reference/API.md:8757-8767` (`describe_capabilities` section) and
  `docs/ARCHITECTURE.md:875` (`CapabilityReport` table row) — both currently
  document only the ENH-2762 `analytics_capture`/`issues` superset keys; need
  the 6 new keys added above.
- `docs/codex/usage.md:96` and `docs/codex/README.md:42` — both currently
  frame `ll-doctor`/exit-code behavior around `agent_select`/capabilities
  only; need the install-surface framing.
- `commands/help.md:296` and `.claude/CLAUDE.md:236` (not 235 — the `ll-doctor`
  line has shifted one line down from the AC's stated anchor) both currently
  read verbatim `"Check host CLI capability support for little-loops
  features"` — needs updating to reflect the broader install-surface scope.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

11. Update `scripts/little_loops/cli/__init__.py:40` — module docstring
    one-liner for `ll-doctor`, same wording fix as `commands/help.md` and
    `.claude/CLAUDE.md`.
12. Add `DOC_STRINGS_PRESENT` rows to `scripts/tests/test_wiring_reference_docs.py`
    (for `docs/reference/API.md`) and `scripts/tests/test_wiring_guides_and_meta.py`
    (for `docs/ARCHITECTURE.md`, `docs/codex/usage.md`, `docs/codex/README.md`)
    asserting the new doctor-related wording lands and survives future edits.

## Execution Pattern

Strictly sequential after FEAT-2794 and FEAT-2795 — the doc content depends on
what those two issues actually ship (exact `--json` keys, exact `--full`
section names, exact output wording).

## Session Log
- `/ll:manage-issue implement` - 2026-07-25T15:20:37Z - `274595fc-17f2-4213-8ff3-aa8bbe0d7fd7.jsonl`
- `/ll:ready-issue` - 2026-07-25T15:14:07 - `c01706ab-1a52-4d56-b774-1b9f5aaf1ee4.jsonl`
- `/ll:confidence-check` - 2026-07-25T15:11:42 - `12881021-b83a-4bec-9a34-3b801ada89d8.jsonl`
- `/ll:wire-issue` - 2026-07-25T15:10:45 - `4f890011-0c7c-44a3-b5e1-e89657d02ccb.jsonl`
- `/ll:refine-issue` - 2026-07-25T15:06:21 - `219497a4-da53-4a69-8cb2-6a09b68ba811.jsonl`
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
