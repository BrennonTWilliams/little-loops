---
id: BUG-3102
priority: P3
type: BUG
status: open
captured_at: '2026-08-08T04:44:28Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
labels:
- learning-tests
- loops
relates_to:
- BUG-3100
- BUG-3101
- ENH-3073
- FEAT-1813
decision_needed: false
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 15
score_ambiguity: 23
score_change_surface: 23
---

# BUG-3102: `migrate-sdk-version` queues only `status: stale` records, never age-stale ones

## Summary

`migrate-sdk-version` is the bulk re-prove loop (FEAT-1813): it iterates the stale set,
re-proves each target, and classifies the result. Its `list_stale` state selects records with

```python
stale = [r for r in records if r.get("status") == "stale"]
```

But staleness has two independent forms in this system, and that filter sees only one:

| Form | Where it lives | Set by | Seen by `list_stale`? |
|---|---|---|---|
| status staleness | the record's `status:` field | `ll-learning-tests mark-stale` | yes |
| **age staleness** | **computed, never stored** | `is_record_stale(record, days)` vs `date:` | **no** |

The release gate, the `type: learning` FSM state, and `cmd_check` all use age staleness. The
bulk loop built to remediate staleness is the one consumer that ignores it.

## Current Behavior

All 31 records in this repo are `status: proven`; none carries `status: stale`. Verified on
`2371728a`:

```
$ ll-learning-tests list | python3 -c "import json,sys; from collections import Counter; \
    print(Counter(r.get('status') for r in json.load(sys.stdin)))"
Counter({'proven': 31})
```

Seven of those are age-stale and are flagged by the release gate today (`anthropic`, `fcntl`,
`hypothesis`, `phoenix`, `pytest`, `questionary`, `ruamel.yaml` — 31 to 50 days old against
`stale_after_days: 30`).

`ll-loop run migrate-sdk-version` queues **zero** of them, prints `No stale records found.`,
exits 1, and routes `done_empty`.

The workaround — `mark-stale` each target first, converting age staleness into status
staleness — does queue them, but is unsafe in its own right: it flips records to a status that
makes `cmd_check` return 1, blocking `ll-auto`'s learning gate on those targets, and if the
re-prove pass fails partway they stay that way. Reversible only by the re-prove that just
failed. (It also does not currently help, because of [[BUG-3100]].)

## Expected Behavior

`list_stale` selects every record that any other consumer would consider stale — status-stale
**or** age-stale — so the loop's queue matches the set the release gate reports.

Running the bulk loop on a repo with age-stale records queues and processes them, without any
`mark-stale` pre-step and without transiting records through a status that blocks other gates.

## Motivation

This is the gap between what the loop is documented to do and what it does. FEAT-1813 describes
it as the counterpart to `learning-tests-audit`: "After audit marks records stale on dependency
bumps, this loop iterates the stale set." That framing assumes `mark-stale` always runs first —
true for the registry-version-bump path FEAT-1739 automates, false for calendar-driven staleness,
which is the form the release gate actually reports and the form 7 records are in right now.

The practical cost: there is no bulk remediation path for the staleness users are actually shown.
The alternative is N sequential single-target `ll-learning-tests prove` runs — one LLM session
each, seven today.

This surfaced while trying to clear [[ENH-3073]]'s seven flagged records, where the bulk loop was
the recommended path and turned out to queue nothing.

## Root Cause

`scripts/little_loops/loops/migrate-sdk-version.yaml`, `list_stale` state — the record filter
tests the `status` field only. Age staleness is a computed predicate
(`little_loops.learning_tests.gate.is_record_stale`) that is never written back to the record, so
a field-equality filter cannot observe it. The loop's inline `python3` heredoc does not import
the predicate.

## Proposed Solution

Have `list_stale` apply both forms, reusing the canonical predicate rather than re-deriving the
date arithmetic:

```python
from little_loops.config.core import BRConfig
from little_loops.learning_tests import list_records
from little_loops.learning_tests.gate import is_record_stale

lt = BRConfig(Path.cwd()).learning_tests
days = lt.stale_after_days

def _is_stale(r):
    return r.status == "stale" or (
        lt.enabled and r.status == "proven" and is_record_stale(r, days)
    )
```

Reusing `is_record_stale` keeps the loop's definition of stale identical to the release gate's,
which is the property that failed here. Re-implementing the comparison inside the heredoc would
reintroduce the same class of divergence.

Consider also emitting the two forms distinctly in the queue file or the triage report, since
`needs-upgrade` vs `still-valid` classification is more meaningful for a version bump than for a
calendar expiry.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

The codebase-analyzer and codebase-pattern-finder research passes surfaced a fork this
issue's own snippet above does not resolve: `list_records()`/`LearnTestRecord` (attribute
access) is not what the loop currently consumes. `list_stale`'s heredoc loads records via
`subprocess.run(["ll-learning-tests", "list"])` -> JSON dict (`.get()` access) — the pattern
shared by the *only other* loop-YAML state that reads this registry
(`learning-tests-audit.yaml`'s `list_records` state, also subprocess+dict). No existing
loop-YAML heredoc in this codebase imports `list_records()` in-process; every non-loop
consumer of `is_record_stale` (`release_gate.py:55-59`, `cli/learning_tests.py:53`,
`fsm/executor.py:1112-1140`) does import it in-process and uses dataclass attribute access.
`is_record_stale()` itself requires a `LearnTestRecord` — it accesses `record.date` as an
attribute, so a plain dict from the subprocess path cannot be passed to it directly without
first reconstructing a dataclass.

**Option A**: Switch `list_stale` to the in-process loader — `from little_loops.learning_tests import list_records`, drop the `ll-learning-tests list` subprocess call entirely, filter `LearnTestRecord` objects directly with `r.status == "stale" or (lt.enabled and is_record_stale(r, lt.stale_after_days))`. Matches the issue's own snippet above and every non-loop consumer's access pattern; removes a serialize/deserialize round-trip (`to_dict()` -> JSON -> `json.loads`) that exists only for this one call site's sake.

> **Selected:** Option A — matches every non-loop consumer's in-process attribute-access convention and removes the serialize/deserialize round-trip; the loop-YAML CLI-subprocess convention it departs from is not shown to be load-bearing.

**Option B**: Keep the subprocess `ll-learning-tests list` call (matching `learning-tests-audit.yaml`'s established loop-YAML convention), but reconstruct each dict back into a `LearnTestRecord` via `LearnTestRecord.from_dict(r)` before calling `is_record_stale(record, days)`. Preserves the loop's existing process boundary (CLI subprocess, not direct import of internals) at the cost of a redundant to-dict/from-dict conversion on every record.

**Recommended**: Option A — the subprocess round-trip serves no purpose here (the loop already runs in-process Python inside the heredoc; there is no process-isolation reason to shell out), and reusing `list_records()`/`is_record_stale()` directly is exactly the "reuse the canonical predicate" principle this issue's own Proposed Solution already argues for. Option B is included because it matches the *only* existing loop-YAML precedent for this registry read, in case that subprocess boundary is deliberate for reasons not visible from research.

### Decision Rationale

**Selected: Option A** (in-process loader via `list_records()` + `is_record_stale()`, attribute access).

Every non-loop consumer of `is_record_stale` — `release_gate.py:53-59`, `fsm/executor.py:1112-1163`, `cli/learning_tests.py:41,53`, `hooks/learning_tests_gate.py:28,134`, `hooks/install_learning_gate.py:31,122` — imports it in-process and calls it with `LearnTestRecord` attribute access. Option A is the only choice that matches that convention directly rather than through an extra `to_dict()`/`from_dict()` round-trip. The loop-YAML layer's competing convention (reading the registry via `ll-learning-tests list` subprocess/shell, as in `learning-tests-audit.yaml:22` and this file's own current `list_stale` heredoc) is real but not load-bearing: no process-isolation rationale for it exists anywhere in the codebase, and this same file's `apply_update` state (`migrate-sdk-version.yaml:174-184`) and `assumption-firewall.yaml:61,123,153` already import `little_loops` internals directly inside identical `python3 <<'PYEOF'` heredocs. Option A also removes a redundant serialize/deserialize hop that exists only to let a CLI-subprocess result be re-coerced into the dataclass `is_record_stale` requires.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 3 |
| Simplicity | 3 | 1 |
| Testability | 3 | 2 |
| Risk | 3 | 2 |
| **Total** | **11/12** | **8/12** |

Key evidence: `release_gate.py:53-59` and `fsm/executor.py:1112-1163` both do `is_record_stale(record, stale_after_days)` on an in-process `LearnTestRecord`, the exact shape Option A produces; `LearnTestRecord.from_dict()` (`learning_tests/__init__.py:63-71`) exists and works but is needed only under Option B, purely to undo the `to_dict()` the CLI already performed.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
- `target: str` — one field of `LearnTestRecord` (`scripts/little_loops/learning_tests/__init__.py:44-81`); the dataclass also carries `date: str`, `status: Literal["proven","refuted","stale"]`, `assertions: list[Assertion]`, `raw_output_path: str | None`. `list_records()` returns instances of this (attribute access). The `ll-learning-tests list` CLI instead serializes via `to_dict()` into plain JSON dicts (`.get()` access) — two distinct shapes for the same registry; `list_stale`'s current heredoc consumes the dict shape via a subprocess round-trip.
- `enabled: bool` — one field of `LearningTestsConfig` (`scripts/little_loops/config/features.py:480-501`); the dataclass also carries `stale_after_days: int = 30`.

### Signatures
- `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool` — `scripts/little_loops/learning_tests/gate.py:45-63`. Takes the dataclass, not a dict (`record.date` attribute access). Clamps `stale_after_days` to a minimum of 1. Catches `(ValueError, TypeError, AttributeError)` around `date.fromisoformat(record.date)` and returns `False` on a missing/malformed date — an unparseable date is treated as fresh, not stale.
- `list_records(*, base_dir: Path | None = None) -> list[LearnTestRecord]` — `scripts/little_loops/learning_tests/__init__.py:126-136`. In-process loader; the alternative to shelling out to `ll-learning-tests list`.
- `BRConfig(project_root).learning_tests -> LearningTestsConfig` — `scripts/little_loops/config/core.py:331-334`. `.enabled` / `.stale_after_days` are the confirmed attribute names.

### Call Path
Current: `list_stale` heredoc -> `subprocess.run(["ll-learning-tests", "list"])` -> `cmd_list()` -> `list_records()` -> `[r.to_dict() for r in records]` JSON on stdout -> `json.loads` -> `list[dict]` -> `r.get("status") == "stale"` filter (status-only, the bug).

Reconciled (matches `release_gate.py:55-59`, `cli/learning_tests.py:53`, `fsm/executor.py:1112-1140`): record -> `status == "stale" or (lt.enabled and is_record_stale(record, lt.stale_after_days))` -> queue file -> exit 0/1 -> `reprove_next` / `done_empty`. `stale_after_days` is read only after `enabled` is checked, matching every existing call site (`worker_pool.py:67`, `sprint/run.py:215`, `fsm/executor.py:1135-1140`, `release_gate.py:47-50`) — none reads it unconditionally.

### Decision Rules
N/A — no new gap kind, gate, or threshold is introduced; the fix reuses the existing `stale_after_days` threshold and `is_record_stale`'s existing comparison. See the loader-choice decision point folded into Proposed Solution below (Option A/B) — that is an implementation-route fork, not new decision logic within the running system.

## Impact

- No bulk remediation path exists for age-stale records; N single-target sessions is the only
  option.
- The loop silently reports `No stale records found.` on a repo with 7 stale records — the
  message is accurate to its filter and misleading about the registry.
- Blocks the practical clearing of [[ENH-3073]]'s seven records, though [[BUG-3100]] blocks it
  more fundamentally: fixing this bug alone makes the loop queue seven targets that it then
  cannot re-prove.

## Integration Map

- `scripts/little_loops/loops/migrate-sdk-version.yaml` — `list_stale` state, the filter
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale`, the predicate to reuse
- `scripts/little_loops/learning_tests/release_gate.py` — the consumer whose definition should match
- `scripts/little_loops/config/features.py` — `stale_after_days`, `enabled`
- `scripts/tests/test_builtin_loops.py` — existing built-in loop coverage

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Tests
- No existing loop-YAML fixture-registry test exists for `list_stale`. `scripts/tests/test_builtin_loops.py`'s `TestMigrateSdkVersionLoop` (~line 11911) is structural-only — it `yaml.safe_load`s the loop file and asserts on required states/keys, never executes the heredoc or exercises it against a real registry.
- The established fixture-registry pattern for this kind of test lives in `scripts/tests/test_release_gate.py`: `_write_record_file(project_dir, target, status, date=None)` (line ~41-55, writes a `LearnTestRecord` via `write_record()`) paired with `_write_config(project_dir, enabled=..., stale_after_days=...)` (line ~18-38) and `_base_dir(project_dir)` (line ~64-65). AC 2/3's fixture tests (one age-stale `proven` record; empty/all-fresh registries) should follow this shape rather than inventing a new one.

### Conventions in Force
- Loop-YAML heredocs import `little_loops` modules directly (`from little_loops.X import Y`, no `sys.path` fixup) — established across 30+ states in `scripts/little_loops/loops/*.yaml`, e.g. `migrate-sdk-version.yaml:174-176` (`apply_update` state, same file) and `assumption-firewall.yaml:61,123,153`. Whichever loader Option A/B (Proposed Solution) lands on, the import itself follows this existing convention.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `## Learning Test Registry` → `### CLI Surface` states "Once records are marked stale, run `ll-loop run migrate-sdk-version` to re-prove them ... Together these two loops form the two-step registry maintenance workflow." Goes stale once `list_stale` also queues age-stale records without a `mark-stale` pre-step; update to describe both trigger paths. [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — `## API Adoption` table, `migrate-sdk-version` row: "Run after `learning-tests-audit` marks records stale." Same stale sequencing claim; update to note age-staleness is queued directly. [Agent 2 finding]

### Tests (execution harness)

_Wiring pass added by `/ll:wire-issue`:_
- No test currently executes `list_stale`'s heredoc — `TestMigrateSdkVersionLoop` (`test_builtin_loops.py:11911`) is `yaml.safe_load`-only and has no execution helper of its own. The fixture-registry-execution test this issue's AC 2/3 require should combine `test_release_gate.py:18-65`'s `_write_config`/`_write_record_file`/`_base_dir` with `test_brainstorm.py:18-19`'s `_bash(script, cwd)` helper (runs a loop-YAML `action` string, `${...}` placeholders manually `.replace()`d first, via `bash -c` in a fixture project dir) — the only existing precedent in the suite for executing a loop-YAML heredoc end-to-end. `list_stale`'s action has two placeholders to substitute before invoking `_bash`: `${context.run_dir}` and `${context.targets}` (yaml lines 30, 35). [Agent 3 finding]

## Acceptance Criteria

- [ ] `list_stale` queues records that are `status: stale` **or** age-stale per
      `is_record_stale`, using the imported predicate rather than inline date arithmetic.
- [ ] A test with a fixture registry containing one age-stale `proven` record and no
      `status: stale` record asserts the queue file is non-empty and the state exits 0.
- [ ] A test asserts an empty registry, and a registry of only fresh `proven` records, still
      route `done_empty`.
- [ ] The `targets` context filter continues to narrow the queue as before.
- [ ] Running the loop in this repo queues the 7 currently age-stale targets.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3100 — `/ll:explore-api` refuses to re-prove existing records; this loop's remedy step
  hits it, so fixing BUG-3102 alone yields a loop that queues work it cannot complete
- BUG-3101 — the learning-state re-check bug; the same remedy path
- FEAT-1813 — introduced this loop with the `status == "stale"` filter
- FEAT-1739 — `learning-tests-audit`, the `mark-stale` producer this filter assumes always ran
- ENH-3073 — the seven age-stale records this loop was expected to clear

## Status

Open. Mechanism confirmed by reading `list_stale` and by observing `Counter({'proven': 31})`
against a release gate reporting 7 stale rows on `2371728a`. Lower priority than BUG-3100 and
BUG-3101: this bug limits the *scale* of remediation, those two prevent remediation entirely.


## Session Log
- `/ll:confidence-check` - 2026-08-08T05:41:06 - `c085045c-d657-4355-b399-137e1eeb2bb5.jsonl`
- `/ll:verify-issues` - 2026-08-08T05:38:58 - `2a0fa600-4e14-4188-af49-4750ba927fcc.jsonl`
- `/ll:wire-issue` - 2026-08-08T05:37:30 - `1c4fe591-3df3-4261-b9e9-0c2500d76b1f.jsonl`
- `/ll:decide-issue` - 2026-08-08T05:32:54 - `7d708d97-06b6-4fb5-b712-102008b71d42.jsonl`
- `/ll:refine-issue` - 2026-08-08T05:28:28 - `d1bad67d-d6b8-487c-9858-33ef80a49710.jsonl`
- `/ll:capture-issue` - 2026-08-08T04:47:04 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
