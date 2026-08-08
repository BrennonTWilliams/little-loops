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
learning_tests_required:
- anthropic
- fcntl
- hypothesis
- phoenix
- pytest
- questionary
- ruamel.yaml
decision_needed: false
reconcile_attempted: true
blocked_by:
- BUG-3100
- BUG-3101
relates_to:
- BUG-3100
- BUG-3101
- BUG-3102
size: Small
confidence_score: 95
outcome_confidence: 77
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
---

# ENH-3073: Learning-test staleness warns on every release forever, with no path that clears it

## Summary

Seven learning-test records trip the pre-release audit on **age alone** and will keep
doing so on every future release, because nothing in the release path re-proves them:

| Record | date | Age at 2026-08-07 |
|---|---|---|
| `.ll/learning-tests/ruamelyaml.md` (`target: ruamel.yaml`) | 2026-06-19 | 49d |
| `.ll/learning-tests/questionary.md` | 2026-06-20 | 48d |
| `.ll/learning-tests/pytest.md` | 2026-06-26 | 42d |
| `.ll/learning-tests/hypothesis.md` | 2026-06-27 | 41d |
| `.ll/learning-tests/phoenix.md` | 2026-07-05 | 33d |
| `.ll/learning-tests/anthropic.md` | 2026-07-07 | 31d |
| `.ll/learning-tests/fcntl.md` | 2026-07-07 | 31d |

> **Revised 2026-08-07.** This issue was written against a three-row table
> (`hypothesis`, `pytest`, `questionary`). [[BUG-3089]] has since landed — `release_gate.py:67`
> now reads `normalize_target(r.target) in imported_packages` — so the audit sees records it
> previously skipped and the real table is seven rows. Verified by running the gate on
> `main` at 2026-08-07. The pre-step cost below is therefore **seven** re-proofs, not three;
> the sequencing note was originally calibrated on three.

All seven are `status: proven`; none is refuted. The gate runs in `warn` mode, prints the
table, and continues. Next release: same table, a few days older. A gate that can only
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

**Refresh machinery exists but is unreachable from the gate.** There are three separate
remediation paths, and the audit's output names none of them:

| Path | What it does | Status |
|---|---|---|
| `ll-learning-tests prove "<target>"` (`cli/learning_tests.py:47`) | re-proves **one** record via the `ready-to-implement-gate` loop | exists, unadvertised, unhardened |
| `ll-loop run migrate-sdk-version` (`loops/migrate-sdk-version.yaml`) | *intends* to iterate the stale set and re-prove each; in fact queues only `status: stale` records, so it sees **none** of the seven — [[BUG-3102]] | shipped by [[FEAT-1813]] (`done`), but non-functional for age staleness |
| `ll-loop run learning-tests-audit` (`loops/learning-tests-audit.yaml`) | detects + bulk `mark-stale`s, emits a triage report | shipped by [[FEAT-1739]] (`done`) |

> **Superseded 2026-08-08.** The row above originally read "iterates the **whole** stale set."
> That was inferred from FEAT-1813's description, not verified. Execution showed all three
> paths are non-functional — see the BLOCKED note in `## Status`. The corrected claim is that
> the machinery *exists* but none of it works on an age-stale record.

_Corrected 2026-08-07._ This section previously read "**No automatic refresh exists.**"
That was wrong — `migrate-sdk-version` is exactly a bulk re-prove loop, and it is already
in `scripts/little_loops/loops/`. The defect is narrower than originally stated: not that
remediation is missing, but that **the gate's message ("fix or re-prove the above records")
names none of the three paths**, so a reader has no way to get from the warning to any of
them. Clearing the warning is undocumented, not unimplemented.

This also changes the shape of the fix — see the bulk-vs-per-row note under Proposed
Solution — and materially lowers Option B's cost, since `migrate-sdk-version` already
performs installed-version comparison for arbitrary third-party targets.

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

**Option A**: make re-proving reachable. Have the gate's output name the exact remediation
command per row (`ll-learning-tests prove "<target>"`). Cheapest; removes the
dead-end without changing policy.

> **Bulk vs per-row — revised 2026-08-07.** With the table at seven rows and
> `migrate-sdk-version` shipped (see Current Behavior), advertising seven separate
> `ll-learning-tests prove` invocations is worse advice than one bulk command. Emit both,
> selected on hit count:
>
> - `len(hits) == 1` → per-row `ll-learning-tests prove "<target>"` only.
> - `len(hits) > 1` → per-row commands **plus** a single trailing line naming
>   `ll-loop run migrate-sdk-version`, which handles the whole stale set in one pass.
>
> The per-row text still satisfies the invariant (every row names an action that clears
> that row); the bulk line keeps the advice proportionate to the table's actual size.

> **Selected:** Option A — `cmd_prove` and its `ll-loop run ready-to-implement-gate`
> invocation already exist and are directly callable; wiring them in is incremental, not
> new infrastructure.

> **`--reprove` is declined.** Option A was originally written with an optional
> `--reprove` flag on the release gate that would run `cmd_prove` for each hit. Rejected:
> each `cmd_prove` call shells out to a full `ll-loop run ready-to-implement-gate` LLM
> session (`cli/learning_tests.py:66-76`), so a three-hit gate would fire three LLM
> sessions in the middle of a release. That is a materially different thing from a
> warning, and it is not what a `warn`-mode gate should do unasked. The remediation stays
> a command the human runs. Consequence: every `--reprove`-conditional bullet in the
> wiring map below is dropped.

**Option B**: gate on installed version, not the calendar. Record the resolved package version
in the record at prove time; treat a record as stale when the installed version differs
from the proven one, falling back to age when no version was captured. Matches what
staleness is actually a proxy for. Requires a schema field and a migration path for
existing records.

- **C — raise `stale_after_days` for this project.** Set an explicit value in
  `.ll/ll-config.json`. Silences the symptom; the dead-end returns at the new threshold.

**Recommended**: Option A now (small, unblocks the immediate noise) with Option B as the
durable fix. Option C alone is not sufficient.

### Sequencing: re-prove the seven records **before** implementation starts

_Added 2026-08-06 during pre-implementation review; revised 2026-08-07._ This issue's
frontmatter declares `learning_tests_required` listing precisely the stale records it is
about. So `ll-auto` runs the learning gate on all of them *before* it will implement
anything here, and that gate run is the one that produced ENH-3084's worked example
(`Learning gate impl-failed for ENH-3073`).

**Consequence:** AC 4 ("the flagged records were re-proven") is not an implementation step
— it is a **pre-step**. Refresh the records first, confirm they are re-dated, and only then
start implementation. Attempting the reverse order gates the issue on itself.

**The list is now seven, not three** (`anthropic`, `fcntl`, `hypothesis`, `phoenix`,
`pytest`, `questionary`, `ruamel.yaml`), because BUG-3089 widened what the audit sees.
Seven sequential `ll-learning-tests prove` runs is seven LLM sessions; prefer the single
`ll-loop run migrate-sdk-version` pass, which was built for exactly this set-wide refresh
(FEAT-1813) and writes the same fields. Fall back to per-target `prove` only for targets
that loop leaves unrefreshed.

Two adjacent issues reduce the friction but are not prerequisites: BUG-3087 (scope the
issue-lifecycle loops so they stop locking the repo root, removing the false conflict) and
ENH-3084 (a verdict that distinguishes this infra failure from an implementation failure).
Neither has to land first if the three records are proven up front.

### Clearing the seven current records

Option A changes the gate's *output*, not `is_record_stale` — so it does not by itself
clear any row. The records must be refreshed separately. Three ways, in preference order:

1. **`ll-loop run migrate-sdk-version`** — one pass over the whole stale set, re-running
   `/ll:explore-api` per target and rewriting `date`/`assertions`/`status`. Preferred:
   one session instead of seven, and it classifies drift rather than just re-dating.
2. `ll-learning-tests prove "<target>"` per target — the per-record fallback for anything
   (1) leaves unrefreshed.
3. Hand-edit `date:` in the files. **Rejected.**

**Never (3).** Hand-editing the date is a false assertion in the registry: bumping
`.ll/learning-tests/pytest.md` from `2026-06-26` to today claims its six assertions were
re-verified today when they were not, which corrupts the exact signal this issue is
trying to protect. The claims are stable-API semantics and cheap to re-prove, so run the
loop and let it write the dates.

If a proof run genuinely fails, that record is a real finding — leave it flagged and note
it, rather than re-dating around it.

### Follow-up for Option B

Option B (stale on installed-version drift rather than calendar age) is deferred, not
declined: at `stale_after_days: 30` the same dead-end returns 31 days after these records
are re-proven. File a follow-up ENH capturing the version-stamp design so it does not
vanish when this issue closes.

> **Revised 2026-08-07 — Option B is cheaper than its 1/3 simplicity score implies.** That
> score rested on "extending version-stamping to arbitrary third-party dependencies
> requires a new generic version resolver," and on `_warn_adapter_staleness` being
> hardcoded to little-loops' own version. But `loops/migrate-sdk-version.yaml` (FEAT-1813,
> `done`) already resolves installed versions for arbitrary targets and classifies the
> result as `still-valid` / `needs-upgrade` / `refuted`. The follow-up ENH should start
> from that loop's resolver rather than from scratch, and should re-score Option B on that
> basis. The `is_record_stale` signature-change caller list and the frontmatter migration
> remain genuine costs; the version resolver does not.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-05.

**Selected**: Option A — make re-proving reachable

**Reasoning**: `cmd_prove` (`cli/learning_tests.py:47`) and its underlying
`ll-loop run ready-to-implement-gate` invocation already exist and are directly callable
as-is; the "name the exact fix-it command per row" shape has two direct precedents in this
codebase (`normalize.py:491`, `rn-implement.yaml:1658`), and a config-gated auto-reprove
architecture already exists in `rn-implement.yaml`/ENH-2487. Option B's version-stamp
mechanic is precedented too (`_warn_adapter_staleness`), but only for little-loops' own
version — extending it to arbitrary third-party dependencies requires a new generic
version resolver, a widened `is_record_stale` signature that ripples through 7 production
call sites plus a full existing test class, and no existing migration mechanism for
`.ll/learning-tests/*.md` frontmatter.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Option A: `cmd_prove` is already a callable module-level function shelling to
  `ll-loop run ready-to-implement-gate`; the release gate already prints a generic
  remediation line (`release_gate.py:87-91`) that naming a per-row command only extends.
- Option B: the version-stamp-and-compare shape is precedented via
  `_warn_adapter_staleness`/`installed_package_version`, but that helper is hardcoded to
  `little-loops`'s own version and `is_record_stale`'s 2-arg signature has 7 production
  call sites plus a dedicated 6-test class that would need updating.

## Scope Boundaries

**In scope**: the audit's output and remediation affordance, re-proving the three
currently-flagged records, and making `cmd_prove` safe to advertise (see below).

**`cmd_prove` hardening — in scope.** Naming a command in gate output makes that command
a supported path, and `cmd_prove` is not currently one:

- `subprocess.run` (`cli/learning_tests.py:66`) passes no `check` and discards
  `returncode`, so a loop that fails to launch is indistinguishable from one that ran and
  left the record unchanged — the user sees the same stale record and no error.
- `ll-loop` absent from `PATH` raises an uncaught `FileNotFoundError` traceback.
- _Added 2026-08-07._ `capture_output=True` swallows all loop output. The command runs a
  full LLM session; a user who runs the newly-advertised command sits through it with zero
  feedback. Either stream (drop `capture_output`) or, at minimum, echo captured stderr
  when the loop exits non-zero.
- _Added 2026-08-07._ The `return 1` path conflates three distinct outcomes: the loop
  failed to run, no record was found, and the record was legitimately re-proven as
  `refuted`. Only the last is a real finding; the first two are infrastructure failures.
  Give them distinct messages (distinct exit codes optional) so the advertised command's
  failure mode is legible.

All four must be handled before the gate points users at this command.

**Out of scope**:

- Changing `is_record_stale` or the staleness predicate itself — that is Option B, now a
  follow-up ENH.

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

**Print `record.target` verbatim, never the normalized form.** _Added 2026-08-07._
`release_gate.py:67` compares `normalize_target(r.target)` against the import scan
(`target.split()[0].lower()`), but the remediation command must embed the **raw**
`record.target`, quoted. `cmd_prove` resolves its argument through
`check_learning_test` → `slugify`, which is a different normalization: the record whose
`target: ruamel.yaml` lives at `.ll/learning-tests/ruamelyaml.md`. Emitting
`ll-learning-tests prove "ruamelyaml"` would not resolve. Reusing `normalize_target` to
build the message is the specific mistake to avoid; the printed table already uses
`record.target` correctly at `:80`.

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

- [ ] The audit's output names a concrete per-record remediation command
      (`ll-learning-tests prove "<target>"`, embedding the raw `record.target`) for each
      printed row, in both `warn` and `block` mode.
- [ ] When the table has more than one row, the output additionally names the bulk path
      `ll-loop run migrate-sdk-version` on a single trailing line. A one-row table prints
      only the per-row command.
- [ ] A test asserts the printed remediation text for a stale row references
      `ll-learning-tests prove` and the row's own target name, via `capsys` in
      `scripts/tests/test_release_gate.py`. A second test covers the multi-row case and
      asserts the bulk line appears exactly once.
- [ ] A test asserts a record with a dotted target (`ruamel.yaml`) is advertised as
      `ll-learning-tests prove "ruamel.yaml"` — **not** the normalized or slugified form.
- [ ] `cmd_prove` no longer discards the loop's exit status: a non-zero `ll-loop`
      returncode is surfaced to the user, a missing `ll-loop` binary produces a readable
      error rather than a `FileNotFoundError` traceback, loop stderr reaches the user on
      failure rather than being swallowed by `capture_output`, and "loop failed" /
      "no record found" / "record is refuted" produce distinct messages instead of a bare
      shared `return 1`. Covered by tests in `scripts/tests/test_cli_learning_tests.py`.
- [ ] The seven currently-stale records (`anthropic`, `fcntl`, `hypothesis`, `phoenix`,
      `pytest`, `questionary`, `ruamel.yaml`) were re-proven via
      `ll-loop run migrate-sdk-version` — or per-target `ll-learning-tests prove` for any
      it leaves unrefreshed — and **not** by hand-editing `date:`. Any target whose proof
      run fails is left flagged and called out in this issue rather than re-dated.
- [ ] Those seven targets no longer appear in the audit's table, verified by `python -c
      "from pathlib import Path; from little_loops.learning_tests.release_gate import
      run_release_gate; raise SystemExit(run_release_gate(Path.cwd()))"`.
      **The table need not be empty** — see the note below.
- [ ] `docs/guides/LEARNING_TESTS_GUIDE.md:387-416` example output block matches the new
      remediation text, and the stale `<!-- TODO: ENH-2621 -->` comment at line 407 is
      **removed** (ENH-2621 is `status: done`).
- [ ] ~~The two verbatim mirrors of the `manage-release` gate step —
      `.kimi-code/skills/ll-manage-release/SKILL.md:317-318` and
      `.gemini/commands/manage-release.toml:296-297` — are updated in lockstep.~~
      **N/A, confirmed 2026-08-07.** Both mirrors contain only the two-line
      `run_release_gate` import + `sys.exit`; neither carries remediation text, and
      Option A changes only `release_gate.py`'s print statements. No mirror edit is due.
- [ ] A follow-up ENH is filed for Option B (version-stamped staleness) and linked from
      Related Issues here. It must reference `loops/migrate-sdk-version.yaml`'s existing
      version resolver as the starting point (see Follow-up for Option B).

> **On "the audit prints no table" — revised 2026-08-07.** The original AC required an
> empty table. That is not achievable and not a fair merge gate: at
> `stale_after_days: 30` across 31 records, new rows cross the threshold continuously —
> `opentelemetry` and `pytest-json-report` (both `2026-07-08`) hit exactly 30 days on
> 2026-08-07, and `pyyaml` is at 28. Rows will appear between the re-prove pass and PR
> review, failing the AC for reasons unrelated to this change — which is the same
> signal-quality confusion this issue exists to fix. The AC is therefore scoped to the
> seven named targets. Making the table durably empty is Option B's job, not Option A's.
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
- `scripts/little_loops/loops/migrate-sdk-version.yaml` — the bulk re-prove path the new
  remediation text advertises; also the pre-step used to clear the seven records
- `.ll/learning-tests/{anthropic,fcntl,hypothesis,phoenix,pytest,questionary,ruamelyaml}.md`
  — the seven affected records (note `ruamelyaml.md` carries `target: ruamel.yaml`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/ll-manage-release/SKILL.md:317-318` — verbatim mirror of the
  `run_release_gate` invocation in `commands/manage-release.md`; drifts if the canonical
  invocation or its exit-1 remediation text changes and this copy isn't updated in lockstep
- `.gemini/commands/manage-release.toml:296-297` — same verbatim-mirror risk as the kimi-code copy

> Dropped from this issue: the `is_record_stale` caller list (`fsm/executor.py:1113,1161`,
> `hooks/learning_tests_gate.py:28,129`, `hooks/install_learning_gate.py:31,122`,
> `cli/ctx_stats.py:31`, `cli/history_context.py`) applied only to Option B's signature
> change. Carry it into the Option B follow-up ENH — it is the main reason B scored 1/3 on
> simplicity. The `--reprove` epilog bullet is dropped with the flag itself.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LEARNING_TESTS_GUIDE.md:387-416` — `## Release Gate` section's literal example
  output block ends with the exact current remediation string (`"✗ Release blocked: fix or
  re-prove the above records, or set release_gate: warn to proceed."`, line 415); already carries
  a `<!-- TODO: ENH-2621 -->` comment (line 407) noting this example can drift from
  `release_gate.py` — must be updated to match whatever remediation text option A adds
- `docs/reference/CLI.md:4208,4219` — the `prove <target>` row and usage example; update only if
  `cmd_prove`'s user-visible behavior changes under the hardening above (no new flags)

> Dropped: `docs/reference/CONFIGURATION.md:893-905` and `docs/ARCHITECTURE.md:690` were
> Option-B-only (new version-drift field). Carry into the follow-up ENH.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_release_gate.py` (`TestReleaseGateWarnMode`, `TestReleaseGateBlockMode`) —
  existing tests assert only the integer return code, never printed stdout; the AC's "test
  asserts the printed remediation text" requirement has no home yet and must be added here via
  `capsys`, following the `capsys.readouterr()` pattern already used in
  `test_cli_learning_tests.py`
- `scripts/tests/test_cli_learning_tests.py` (`TestMainLearningTestsProve`, lines 354-453) — home
  for the two `cmd_prove` hardening cases: a mocked `subprocess.run` returning non-zero, and one
  raising `FileNotFoundError`. Existing tests here already patch `subprocess.run` for `prove`;
  extend that pattern rather than adding a new class
- `scripts/tests/test_release_gate.py` (`TestReleaseGateWarnMode`, `TestReleaseGateBlockMode`) has
  **no `capsys` usage anywhere in the file today** — every existing test asserts only the integer
  return code, so a new `capsys`-based test class (e.g. `TestReleaseGateRemediationText`) is the
  first of its kind here; follow the `capsys.readouterr().out`/`.err` substring-assertion pattern
  already used in `test_cli_learning_tests.py` (`TestMainLearningTestsOrphans.test_no_orphans_prints_message`,
  `:482-494`)

> Dropped: `test_cli_surface.py`'s frozen `_METAVAR_SUBCOMMANDS_HELP` set was
> `--reprove`-as-subcommand-only — no new subcommand is being added, so the set stays
> `{"check", "list", "mark-stale", "orphans", "prove"}` untouched.
> `test_learning_tests_discoverability.py` (`TestIsRecordStale`), `test_config.py`
> (`TestLearningTestsConfig`), and `test_install_learning_gate.py` were Option-B-only.
> Carry all into the follow-up ENH.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1046-1051,1069-1074` — `stale_after_days` and
  `release_gate` schema entries; **unaffected by this issue**. Option B's new record field plus a
  frontmatter migration path for existing `.ll/learning-tests/*.md` belongs to the follow-up ENH.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/little_loops/learning_tests/__init__.py` — `LearnTestRecord` dataclass and `list_records()` (called by `run_release_gate`, feeds `is_record_stale`)
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — the loop `cmd_prove()` invokes for re-proving a record; the unwired remediation target for option A's `--reprove` flag
- `scripts/little_loops/loops/learning-tests-audit.yaml` — separate audit loop for learning-test triage; distinct from the release-gate path but reads the same `.ll/learning-tests/*.md` records
- Additional test files exercising this area not previously listed: `scripts/tests/test_learning_tests.py`, `scripts/tests/test_learning_tests_gate.py`, `scripts/tests/test_learning_state.py`, `scripts/tests/test_learning_tests_extractor.py`

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/little_loops/loops/learning-tests-audit.yaml` — separate audit loop that reads the
  same `.ll/learning-tests/*.md` records as `run_release_gate`; a second consumer of the
  staleness predicate not previously listed here.
- BUG-3072 landed as commit `430a8db4` ("fix(learning-tests): surface failing claims on proven
  records", `status: done`). It touched `.ll/learning-tests/pytest.md` (corrected `claim3`'s
  assertion from `result: fail` to `result: pass`) but did not change the record's `date` field
  (still `2026-06-26`, still 40+ days old) — confirms this issue's Scope Boundaries separation
  from BUG-3072 held: the failing-claim fix did not touch or reset staleness age.

## Related Issues

- ENH-2214 — release gate blocking on stale/refuted records (introduced this gate)
- BUG-3072 — failing assertions invisible under `proven` status
- BUG-3070 — release ordering; determines what a `block`-mode abort leaves behind
- **BUG-3100 — blocker.** `/ll:explore-api` asks an interactive question instead of re-proving
  when a record already exists, so no automated re-prove path can refresh a record. Option A's
  advertised `ll-learning-tests prove "<target>"` provably cannot clear the row it is printed
  next to (verified 2026-08-08 at `2371728a`).
- **BUG-3101 — blocker.** The learning state's in-loop re-check omits the date-staleness nulling
  applied before the loop, so a no-op remedy is scored `learning_target_proven` and
  `ready-to-implement-gate` returns a false `done`. This is what made BUG-3100 invisible.
- BUG-3102 — `migrate-sdk-version` filters `status == "stale"` and so queues none of the
  age-stale records; not a blocker for Option A's output change, but it is why the bulk
  remediation line this issue adds has nothing to act on until it lands
- BUG-3089 — the audit's import-scan relevance filter misses most records; filed 2026-08-06
  from this issue's adjacent-defect note. **`status: done` as of 2026-08-07** — the
  prerequisite has landed, and landing it is what took this issue's table from three rows
  to seven (see Summary).
- FEAT-1813 — `migrate-sdk-version` loop; the bulk re-prove path this issue should
  advertise, and the source of Option B's version resolver (`status: done`)
- FEAT-1739 — `learning-tests-audit` loop; stale detection + triage report over the same
  records (`status: done`)
- ENH-2621 — docs-guide audit fixes; `status: done`, but left a stale `TODO` marker in
  `LEARNING_TESTS_GUIDE.md:407` that this issue removes
- _(to file)_ Option B follow-up — version-stamped staleness instead of calendar age; carries
  the `is_record_stale` signature-change caller list and schema/migration work dropped above

**Adjacent defect — now filed as [[BUG-3089]] (P2).** This note originally read: "`run_release_gate`
matches `r.target in imported_packages` raw (`release_gate.py:67`), while `cmd_orphans`
normalizes with `r.target.split()[0].lower()` (`cli/learning_tests.py:157`) … worth its own
BUG." Investigation on 2026-08-06 found the divergent normalization is the *smaller* half of
the problem: `get_imported_packages`'s regex is `^`-anchored and dot-free, so it sees neither
function-local imports nor dotted module names. Four of this repo's own records
(`anthropic`, `opentelemetry`, `concurrent.futures`, `ruamel.yaml`) are consequently invisible
to the gate today.

**This raised ENH-3073's sequencing — now resolved.** Making remediation reachable does not
help for rows that never print, and BUG-3089 was exactly why they did not print. BUG-3089
landed (`status: done`); `release_gate.py:67` now normalizes both sides via
`normalize_target`. ENH-3073's per-row remediation text will therefore apply to an audit
that flags what it should — and the immediate consequence is that the flagged set grew
from three records to seven.

## Status

Open and ready to implement. Mechanism confirmed. Option A selected (see Decision
Rationale); `--reprove` declined; Option B deferred to a follow-up ENH. Remaining work is
the gate's per-row remediation text plus a bulk line, `cmd_prove` hardening (four gaps),
and re-proving the seven flagged records via `ll-loop run migrate-sdk-version`.

**BLOCKED as of 2026-08-08 — `blocked_by: [BUG-3100, BUG-3101]`.** An attempt to execute this
issue's pre-step (re-proving the seven flagged records) established that **no working re-prove
path exists**. Every route terminates in `/ll:explore-api` asking an unanswerable interactive
question (BUG-3100), and the false `done` verdict that hides it (BUG-3101). Verified by direct
reproduction at `2371728a`:

| Path | Result |
|---|---|
| `ll-learning-tests prove "ruamel.yaml"` | exit 0, `date` unchanged |
| `ll-loop run ready-to-implement-gate` | explore-api asked a question → false `done`, 1 iteration |
| `ll-loop run migrate-sdk-version` | queues 0 records (BUG-3102) |
| `mark-stale` + gate loop | asked twice → `blocked`, `date` unchanged (reverted) |

**Consequence for Option A.** Its invariant is "every row the audit prints names an action that,
when taken, makes that row disappear." The action it selected does not make the row disappear —
it exits 0 and changes nothing. Shipping as specified would replace a dead-end warning with a
warning naming a command that silently lies, which is strictly worse. The `cmd_prove` hardening
already in scope catches the *silence* but not the underlying no-op.

Option A remains the right destination; it is not implementable until BUG-3100 and BUG-3101 land.
The seven records cannot be cleared before then by any means short of hand-editing `date:`, which
this issue explicitly rejects.

**Pre-implementation review pass — 2026-08-07.** Re-verified against `main` at `4c78cbd6`.
Seven corrections applied: the flagged set is seven records, not three (BUG-3089 landed);
"no automatic refresh exists" was false (`migrate-sdk-version` and `learning-tests-audit`
both ship); the empty-table AC was unachievable and is now scoped to the seven named
targets; the kimi-code/gemini mirror AC is a confirmed no-op; the remediation string must
use raw `record.target`, not `normalize_target`; `cmd_prove` has two hardening gaps beyond
the two originally listed; and the ENH-2621 TODO marker should simply be removed. Option A
remains the right call — none of these change the decision, only its scope and cost.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-05_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- ~~Unresolved ambiguity residue: the `## Status` footer still reads "policy option
  (A/B/C) undecided", contradicting the `Decision Rationale` section's explicit
  selection of Option A.~~ **Resolved 2026-08-05** — footer rewritten.
- ~~The Acceptance Criteria and Dependent-Files/Documentation/Tests sections retain
  several `if option B is taken` conditional bullets even though Option A was
  selected.~~ **Resolved 2026-08-05** — all Option-B and `--reprove` conditionals
  removed from the wiring map and rolled into the follow-up ENH note.

_Review pass 2026-08-05 additionally found: AC "the three records no longer appear" was
unachievable by Option A's change alone and did not pick between re-proving and
re-dating (now resolved in favor of re-proving); the `--reprove` half of Option A was
left undecided inside a decided option (now declined); `cmd_prove` was not safe to
advertise (hardening now in scope); Option B had no successor issue (now an AC); and the
LEARNING_TESTS_GUIDE / kimi-code / gemini mirror updates had no AC (now added)._

## Session Log
- `/ll:capture-issue` - 2026-08-08T04:47:47 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:14:18 - `2714e173-0113-42e1-b8e8-e7f650c61db7.jsonl`
- `/ll:ready-issue` - 2026-08-06T06:18:23 - `947fa9b7-8ab1-44ef-9fcd-dc534fce8613.jsonl`
- `/ll:confidence-check` - 2026-08-06T04:30:52 - `be4424fb-bd22-4a4d-8f91-9e0d0eb44d1c.jsonl`
- `/ll:reconcile-issue` - 2026-08-06T04:23:34 - `b80e47d8-635f-4079-b216-2ccd61850853.jsonl`
- `/ll:confidence-check` - 2026-08-06T04:21:44 - `fde16fb9-dfe9-4d3c-b7c4-2dc8bf0e171d.jsonl`
- `/ll:wire-issue` - 2026-08-06T04:16:16 - `5575a942-ec0f-465f-9cb3-a989e3f3d563.jsonl`
- `/ll:decide-issue` - 2026-08-06T04:10:08 - `2ccb54ed-3c09-40c8-a5de-ca5f2244d26f.jsonl`
- `/ll:refine-issue` - 2026-08-06T04:06:39 - `d69578eb-cc9b-4928-97bc-631b38148add.jsonl`
- `/ll:refine-issue` - 2026-08-06T04:04:21 - `2ccb54ed-3c09-40c8-a5de-ca5f2244d26f.jsonl`
- `/ll:wire-issue` - 2026-08-06T03:47:02 - `f0e9ad86-a944-4acc-a368-a18a0cfd6c1c.jsonl`
- `/ll:refine-issue` - 2026-08-06T03:31:53 - `657c1532-4b4b-49ec-ba80-7e4debdd4dbe.jsonl`
