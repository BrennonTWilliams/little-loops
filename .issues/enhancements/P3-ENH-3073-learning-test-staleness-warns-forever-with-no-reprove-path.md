---
id: ENH-3073
priority: P3
type: ENH
status: open
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
labels:
- learning-tests
- release
- gates
testable: true
size: Small
---

# ENH-3073: Learning-test staleness warns on every release forever, with no path that clears it

## Summary

Three learning-test records trip the pre-release audit on **age alone** and will keep
doing so on every future release, because nothing in the release path re-proves them:

| Record | date | Age at 2026-08-05 |
|---|---|---|
| `.ll/learning-tests/hypothesis.md` | 2026-06-27 | 39d |
| `.ll/learning-tests/pytest.md` | 2026-06-26 | 40d |
| `.ll/learning-tests/questionary.md` | 2026-06-20 | 46d |

All three are `status: proven`; none is refuted. The gate runs in `warn` mode, prints the
table, and continues. Next release: same table, three days older. A gate that can only
ever print the same warning trains its reader to skip it — which is the failure mode that
matters, given BUG-3072 shows the same table is where a real problem would appear.

## Current Behavior

- `stale_after_days` defaults to **30** (`scripts/little_loops/config/features.py:486`, `:497`).
- `is_record_stale` (`scripts/little_loops/learning_tests/gate.py:40`) compares
  `record.date` to today; purely temporal, no reference to whether the API changed.
- `run_release_gate` (`scripts/little_loops/learning_tests/release_gate.py:36`) filters
  `r.status == "refuted" or is_record_stale(...)` at `:58`, intersects with actually-imported
  packages, prints the table, and returns 0 under `release_gate: "warn"` (`features.py:488`).
- `.ll/ll-config.json` sets only `"learning_tests": {"enabled": true}`, so both defaults
  (`30`, `warn`) are in force here.

**No automatic refresh exists.** `ll-learning-tests prove <target>` (`cli/learning_tests.py:47`)
can re-prove a record by running the `ready-to-implement-gate` loop, but nothing invokes
it from the release gate, and the gate's own message ("fix or re-prove the above records")
does not name that command. Clearing the warning is a manual, undocumented step.

The claims themselves are stable API semantics — pytest fixture visibility, `monkeypatch`
scoping, `questionary` prompt behavior, `hypothesis` strategy behavior. There is no reason
to expect drift in 30 days, and the gate has no signal that any occurred; only the calendar.

## Expected Behavior

The pre-release audit is quiet on a healthy registry, and any row it does print names a
remediation that clears that row. A record proven against a dependency whose installed
version has not changed does not become a warning purely by the passage of time.

## Motivation

Age is a proxy for "the API may have moved". The proxy is weak when the dependency's
installed version has not changed — which is directly observable and is not consulted.

## Proposed Solution

Options, to be decided:

- **A — make re-proving reachable.** Have the gate's output name the exact remediation
  command per row (`ll-learning-tests prove "<target>"`), and optionally add a
  `--reprove` flag to the release gate that runs it for each hit. Cheapest; removes the
  dead-end without changing policy.
- **B — gate on installed version, not the calendar.** Record the resolved package version
  in the record at prove time; treat a record as stale when the installed version differs
  from the proven one, falling back to age when no version was captured. Matches what
  staleness is actually a proxy for. Requires a schema field and a migration path for
  existing records.
- **C — raise `stale_after_days` for this project.** Set an explicit value in
  `.ll/ll-config.json`. Silences the symptom; the dead-end returns at the new threshold.

Recommend A now (small, unblocks the immediate noise) with B as the durable fix. C alone
is not sufficient.

Independent of the option chosen, the three current records should be re-proven or
explicitly re-dated so the release table is empty and a future entry means something.

## Scope Boundaries

**In scope**: the staleness predicate, the audit's output and remediation affordance, and
re-proving (or re-dating) the three currently-flagged records.

**Out of scope**:

- Anything about how a `proven` record's individual assertions are surfaced — that is
  BUG-3072, and it must not be conflated with staleness here.
- Changing `release_gate` from `warn` to `block` for this project.
- Moving the audit's position in the release sequence relative to `changelog`/`tag`
  (raised and deliberately deferred in BUG-3070).
- The `ready-to-implement-gate` loop's own behavior; option A only wires an existing
  command into the message.

## Program Design

**Invariant.** Every row the release audit prints names an action that, when taken, makes
that row disappear.

### Types

```python
stale_after_days: int = 30
release_gate: str = "warn"
```

### Signatures

```python
def is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool:
def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
def cmd_prove(args: argparse.Namespace) -> int:
```

### Call Path

- `commands/manage-release.md` → `##### Pre-Release: Learning Test Audit` →
  `run_release_gate` (`learning_tests/release_gate.py:36`)
- `run_release_gate` → `list_records` (`learning_tests/__init__.py:117`) →
  `is_record_stale` (`learning_tests/gate.py:40`)
- `run_release_gate` → `get_imported_packages` (`learning_tests/import_scan.py`)
- Remediation path, currently unwired: `cmd_prove` (`cli/learning_tests.py:47`) →
  `ll-loop run ready-to-implement-gate`

## Acceptance Criteria

- [ ] The audit's output names a concrete per-record remediation command.
- [ ] A test asserts the printed remediation text for a stale row references
      `ll-learning-tests prove`.
- [ ] The three currently-stale records no longer appear in the audit (re-proven or
      re-dated), verified by `python -c "from pathlib import Path; from
      little_loops.learning_tests.release_gate import run_release_gate;
      raise SystemExit(run_release_gate(Path.cwd()))"` printing no table.
- [ ] If option B is taken: a record proven against an unchanged installed version does
      not go stale on age alone.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

No functional breakage — `warn` mode never blocks. The cost is signal quality: the audit
currently emits a constant, uninformative warning at every release, so a genuinely new
entry (a refuted record, or the failing-assertion case in BUG-3072) arrives in a table the
reader has already learned to skim past.

Projects that opt into `release_gate: block` are affected harder: with BUG-3070's
reordering, a block now aborts *after* the changelog commit, so a purely age-based
false positive leaves a changelog commit with no tag.

## Integration Map

- `scripts/little_loops/learning_tests/release_gate.py` — audit output and exit behavior
- `scripts/little_loops/learning_tests/gate.py:40` — staleness predicate
- `scripts/little_loops/config/features.py:486-499` — defaults
- `scripts/little_loops/cli/learning_tests.py:47` — the unwired `prove` path
- `commands/manage-release.md` — `Pre-Release: Learning Test Audit` step
- `.ll/learning-tests/hypothesis.md`, `.ll/learning-tests/pytest.md`,
  `.ll/learning-tests/questionary.md` — the three affected records

## Related Issues

- ENH-2214 — release gate blocking on stale/refuted records (introduced this gate)
- BUG-3072 — failing assertions invisible under `proven` status
- BUG-3070 — release ordering; determines what a `block`-mode abort leaves behind

## Status

Open. Mechanism confirmed; policy option (A/B/C) undecided.
