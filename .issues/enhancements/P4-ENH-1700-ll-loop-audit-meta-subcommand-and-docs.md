---
id: ENH-1700
type: ENH
status: done
completed_at: 2026-05-25T22:35:26Z
priority: P4
parent: ENH-1667
depends_on:
- ENH-1699
labels:
- telemetry
- loops
- meta-loop
- cli
- observability
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1700: ll-loop audit-meta subcommand and agent/doc updates

## Summary

Add the `ll-loop audit-meta <name>` subcommand that reads `meta-eval.jsonl`
from the run archive and prints a summary table (agreement rate, mean diff
size per verdict, divergence flags). Also adds the `evaluator-trivial`
failure-mode entry to `agents/loop-specialist.md` and updates CLI/API
documentation. Depends on ENH-1699 for the JSONL format.

## Parent Issue

Decomposed from ENH-1667: Meta-loop runtime divergence telemetry (follow-up)

## Implementation Steps

**Step 2 — `agents/loop-specialist.md`**

Add a new section "Auditing meta-loop telemetry" describing how to read
`meta-eval.jsonl` and the two divergence patterns to look for:
- LLM optimistic: long streak of `agreed: false` (LLM says yes, external says no)
- Trivial agreement: `agreed: true` with `diff_stats.files_changed == 0`
  (both passing, nothing changed — possible self-eval drift)

Add a new `[ ] evaluator-trivial` entry to the `## Failure modes observed`
checklist at lines 85–91 (currently six entries; this becomes the seventh).

**Step 3 — `scripts/little_loops/cli/loop/__init__.py`**

Register `"audit-meta"` in the `known_subcommands` frozenset (lines 40–65)
to prevent argparse shorthand promotion to `run`. Add an `elif args.command
== "audit-meta": cmd_audit_meta(args.name)` branch in the dispatch block
(lines 485–512). Add a usage example line to the argparse epilog string
(lines 80–95).

**Step 6 — Implement `cmd_audit_meta()` in `scripts/little_loops/cli/loop/info.py`**

Follow the `cmd_history()` pattern at line 517 — use `_list_archived_runs()`
at line 435 and `get_archived_events()` from `persistence.py` to locate the
archived `meta-eval.jsonl` for the named loop. Compute and print:

- Total iterations with `llm_structured` events
- Agreement rate (agreed / total)
- Mean diff size (files_changed) per verdict (agreed=true vs agreed=false)
- Flag: divergence patterns crossing thresholds:
  - `agreed: false` streak ≥ 3 → "LLM optimistic drift detected"
  - `agreed: true` with `diff_stats.files_changed == 0` streak ≥ 3 → "Trivial agreement detected"

Return type: `int` (exit code). Return 0 if no flags triggered, 1 if any threshold crossed.

**Step 7 — Registration**

Same as Step 3 — register dispatch + usage line in argparse epilog.

## Tests

- **`scripts/tests/test_ll_loop_execution.py`**: Add
  `test_audit_meta_subcommand_registered()` verifying `audit-meta` is in
  `known_subcommands` (follow lines 1365–1425 pattern — invoke `main_loop()`
  with `["ll-loop", "audit-meta", "--help"]` and assert `SystemExit(0)`).
- **`scripts/tests/test_ll_loop_commands.py`**: Add `TestCmdAuditMeta` class
  following `TestCmdHistory` / `TestHistoryTail` pattern at lines 935 and 982.
  Build a pre-populated `meta-eval.jsonl` under `tmp_path / ".loops" / ".history"`,
  call `cmd_audit_meta()` directly, capture output via `capsys`, assert on
  agreement rate and flag output.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — register `"audit-meta"` in
  `known_subcommands` frozenset (lines 40–65); add dispatch branch (lines 485–512);
  add argparse epilog usage example (lines 80–95)
- `scripts/little_loops/cli/loop/info.py` — add `cmd_audit_meta(name: str) -> int`
  following `cmd_history()` at line 517
- `agents/loop-specialist.md` — add "Auditing meta-loop telemetry" section;
  add `evaluator-trivial` to failure-mode checklist (lines 85–91)

### Documentation Updates

- `docs/reference/CLI.md` — add `audit-meta` to the ll-loop examples block
  (lines 567–596); add `#### ll-loop audit-meta` subsection matching
  `#### ll-loop next-loop` pattern
- `docs/reference/API.md` — update agents table row for `loop-specialist`
  at line 6663 (currently "six-mode taxonomy"; becomes seven when
  `evaluator-trivial` is added)

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `.codex/agents/loop-specialist.toml` — auto-generated Codex mirror of
  `agents/loop-specialist.md`; its `developer_instructions` body contains a
  verbatim copy of the failure-mode taxonomy and currently says "six modes"
  at line 27. Must be regenerated via `ll-adapt-agents-for-codex` after
  `agents/loop-specialist.md` is updated, otherwise the Codex mirror goes stale.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/run.py` — imports/invokes FSMExecutor /
  PersistentExecutor; no changes required but confirms composition path

## Verification

- `ll-loop audit-meta <name>` reads `meta-eval.jsonl` from the archive and
  prints a summary table.
- The subcommand returns exit 0 (no flags) or exit 1 (divergence detected).
- `audit-meta --help` works without error (subcommand registered correctly).
- `agents/loop-specialist.md` documents `evaluator-trivial` failure mode.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Gap 1 — Missing `subparsers.add_parser()` call (Step 3 is incomplete)**

Step 3 only mentions `known_subcommands` and the dispatch branch, but every subcommand also requires a `subparsers.add_parser(...)` block so that `--help` works and argparse knows the subcommand's arguments. Follow the `history_parser` pattern at `scripts/little_loops/cli/loop/__init__.py:336`:

```python
audit_meta_parser = subparsers.add_parser(
    "audit-meta", help="Summarize meta-eval.jsonl agreement stats from archived runs"
)
audit_meta_parser.set_defaults(command="audit-meta")
audit_meta_parser.add_argument("loop", help="Loop name")
audit_meta_parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")
```

This block belongs after `next_loop_parser` (line 484) and before the dispatch block.

**Gap 2 — Wrong dispatch call in Step 3**

The issue writes `cmd_audit_meta(args.name)` but `args.name` does not exist — all subcommands use `args.loop` as the positional loop-name argument. The correct dispatch (following the `cmd_history` pattern at line 534) is:

```python
elif args.command == "audit-meta":
    return cmd_audit_meta(args.loop, args, loops_dir)
```

**Gap 3 — `cmd_audit_meta()` function signature**

The issue says `cmd_audit_meta(name: str) -> int` following `cmd_history()`, but `cmd_history()` at `info.py:518` actually has the signature:

```python
def cmd_history(loop_name: str, run_id: str | None, args: argparse.Namespace, loops_dir: Path) -> int
```

`cmd_audit_meta()` does not need `run_id`, but it does need `args` (for `--json` flag) and `loops_dir`:

```python
def cmd_audit_meta(loop_name: str, args: argparse.Namespace, loops_dir: Path) -> int
```

**Gap 4 — No `get_archived_meta_eval()` function exists**

`persistence.py` has `get_archived_events()` (line 903) for `events.jsonl`, but has **no analog for `meta-eval.jsonl`**. The implementer must either:
- Inline the path construction (follow `archive_run()` at line 391 which writes to `archive_dir / "meta-eval.jsonl"`), or
- Add a new `get_archived_meta_eval_entries(loop_name, run_id, loops_dir)` helper in `persistence.py` that mirrors `get_archived_events()` but targets `meta-eval.jsonl`

The recommended pattern (inline, no new helper needed):
```python
from little_loops.fsm.persistence import HISTORY_DIR
history_root = loops_dir / HISTORY_DIR
for run_dir in sorted(history_root.glob(f"*-{loop_name}")):
    meta_eval_file = run_dir / "meta-eval.jsonl"
    if not meta_eval_file.exists():
        continue
    entries = [json.loads(line) for line in meta_eval_file.read_text().splitlines() if line.strip()]
    # compute stats from entries...
```

**Gap 5 — `known_subcommands` is a `set`, not `frozenset`**

The issue says "frozenset" but `scripts/little_loops/cli/loop/__init__.py:40` uses a plain `set`. The variable name is `known_subcommands` and it is defined at line 40. Add `"audit-meta"` there.

**Gap 6 — Step 7 is redundant**

Step 7 ("Same as Step 3") duplicates Step 3. Ignore Step 7; treat Step 3 as the single registration step.

**Gap 7 — Internal import line in `__init__.py` must include `cmd_audit_meta`** _(wiring pass)_

`main_loop()` in `scripts/little_loops/cli/loop/__init__.py` imports info commands
lazily inside the function body:

```python
from little_loops.cli.loop.info import cmd_fragments, cmd_history, cmd_list, cmd_show
```

The `audit-meta` dispatch branch (Gap 2) must add `cmd_audit_meta` to this same
import line; otherwise the dispatch will raise `NameError` at runtime.

**Gap 8 — `.codex/agents/loop-specialist.toml` must be regenerated** _(wiring pass)_

After updating `agents/loop-specialist.md` to add `evaluator-trivial` as the seventh
failure mode, run:

```bash
ll-adapt-agents-for-codex
```

This regenerates `.codex/agents/loop-specialist.toml` with the updated taxonomy text.
Failing to do this leaves the Codex mirror claiming "six modes" after the agent has
seven.

**Confirmed accurate:** `diff_stats.files_changed` is a real key (`persistence.py:84`). Archive path is `.loops/.history/{run_id}-{loop_name}/meta-eval.jsonl`. `cmd_history()` is at line 518; `_list_archived_runs()` is at line 436.

## Resolution

Implemented `ll-loop audit-meta <name>` subcommand that reads `meta-eval.jsonl` from archived runs and prints a summary table (agreement rate, mean diff size per verdict, divergence flags). Added `evaluator-trivial` as the seventh failure mode in `agents/loop-specialist.md`. Updated CLI and API documentation. Regenerated `.codex/agents/loop-specialist.toml`.

## Session Log
- `/ll:manage-issue` - 2026-05-25T22:35:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-25T22:27:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44ef8395-31bf-4c6e-9d6a-7d1cda7b6263.jsonl`
- `/ll:wire-issue` - 2026-05-25T22:23:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87e60316-bc4e-40aa-9f1d-972dd256302e.jsonl`
- `/ll:refine-issue` - 2026-05-25T22:18:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/935bd66b-c084-4890-a4fd-4cf3ddc57793.jsonl`
- `/ll:issue-size-review` - 2026-05-25T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1164a851-abd3-4d31-9115-03f9bcd570f7.jsonl`
- `/ll:confidence-check` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8dde9478-d2ec-413d-80de-5b32086b7f9a.jsonl`
