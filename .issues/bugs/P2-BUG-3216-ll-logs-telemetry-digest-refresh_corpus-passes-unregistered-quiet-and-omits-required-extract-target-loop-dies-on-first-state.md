---
id: BUG-3216
type: BUG
title: ll-logs-telemetry-digest refresh_corpus passes unregistered --quiet and omits
  required extract target; loop dies on first state
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T21:57:52Z'
labels:
- ll-logs
- loops
- cli-consistency
---

# BUG-3216: ll-logs-telemetry-digest refresh_corpus passes unregistered --quiet and omits required extract target; loop dies on first state

## Summary

`.loops/ll-logs-telemetry-digest.yaml`'s `refresh_corpus` state has never
succeeded. Its two commands are both malformed against the actual `ll-logs`
argument surface, so the state always echoes `REFRESH_FAILED`, its
`output_contains: "REFRESHED"` gate always evaluates false, and `on_no: done`
terminates the loop on its first state. Every downstream state (`run_stats`,
`run_sequences`, `scan_failures`, dead-skill detection, triage, digest) is
unreachable.

## Current Behavior

```yaml
# .loops/ll-logs-telemetry-digest.yaml:15-16
ll-logs discover --quiet 2>/dev/null || true
ll-logs extract --quiet 2>/dev/null && echo "REFRESHED" || echo "REFRESH_FAILED"
```

Two independent defects, either of which alone is fatal to the state:

1. **`--quiet` is not a registered argument anywhere on `ll-logs`.**
   `grep -n quiet scripts/little_loops/cli/logs.py` returns zero matches — no
   subcommand parser and no top-level parser defines it. argparse treats it as
   unrecognized and exits 2.

2. **`extract` requires a target and is given none.** `extract_parser` calls
   `add_corpus_target_args(extract_parser, ...)` (`logs.py:2108`), which builds
   a `required=True` mutually exclusive group (`cli_args.py:275`). So
   `ll-logs extract` with neither `--project` nor `--all` is a usage error
   regardless of `--quiet`.

Observed directly:

```
$ ll-logs extract --quiet; echo "exit=$?"
usage: ll-logs extract [-h] (--project DIR | --all) [--cmd TOOL]
ll-logs extract: error: one of the arguments --project --all is required
exit=2

$ ll-logs discover --quiet; echo "exit=$?"
usage: ll-logs [-h] {discover,tail,extract,...} ...
exit=2
```

(argparse reports the missing-target error before reaching the unrecognized
`--quiet`, which is why fixing only the flag would leave the state still
broken — the second defect is masked by the first.)

Because the loop redirects stderr to `/dev/null`, the usage errors are
invisible; the state simply reports `REFRESH_FAILED` with no diagnostic. The
`discover` line is `|| true`-guarded so its failure is silent and harmless, but
the `extract` line's failure short-circuits the `&&` and drives the loop to
`done`.

There is no run history for this loop under `.loops/.history/`, consistent with
it never having produced a usable run.

## Steps to Reproduce

Reproduce the two argument-surface errors directly (no loop run needed):

```bash
$ ll-logs extract --quiet; echo "exit=$?"
# usage: ll-logs extract [-h] (--project DIR | --all) [--cmd TOOL]
# ll-logs extract: error: one of the arguments --project --all is required
# exit=2

$ ll-logs extract --all --quiet; echo "exit=$?"
# error: unrecognized arguments: --quiet
# exit=2

$ grep -c quiet scripts/little_loops/cli/logs.py
# 0
```

Then reproduce the loop-level consequence — the exact shell from
`refresh_corpus`:

```bash
$ ll-logs extract --quiet 2>/dev/null && echo "REFRESHED" || echo "REFRESH_FAILED"
REFRESH_FAILED
```

The state's `evaluate` is `output_contains: "REFRESHED"`, so this is a false
branch, and `on_no: done` ends the run. A full `ll-loop run
ll-logs-telemetry-digest` terminates after one state with no digest produced.

## Expected Behavior

`refresh_corpus` refreshes the corpus and proceeds to `run_stats`. Both
invocations use flags that exist and supply the required target:

```yaml
ll-logs discover 2>/dev/null || true
ll-logs extract --all 2>/dev/null && echo "REFRESHED" || echo "REFRESH_FAILED"
```

If output suppression is genuinely wanted, `--quiet` should be wired via the
existing shared `add_quiet_arg(parser)` helper (`cli_args.py:209-215`) rather
than dropped — see Proposed Solution for the two-part choice.

## Proposed Solution

Two separable parts; the first is required, the second is a judgment call.

**Required — fix the loop.** Add `--all` to the `extract` invocation and drop
`--quiet` from both lines (or keep it only if part 2 ships first). This alone
restores the loop.

**Optional — wire `--quiet` on `ll-logs`.** `add_quiet_arg` already exists and
is used by the sprint/parallel parsers (`cli_args.py:531`, `:554`). Wiring it
on `ll-logs` subcommands would honor the original FEAT-1002 spec. Note this
interacts with ENH-2926, which adds success-path summary output to
`_cmd_extract` — a `--quiet` flag is most useful *after* extract has output to
suppress, so sequencing it after ENH-2926 is reasonable. Not a blocker in
either direction.

**Also consider** replacing the `2>/dev/null` on the `extract` line with
capture-to-`${context.run_dir}`, so the next argument-surface drift produces a
diagnosable artifact instead of a silent `REFRESH_FAILED`.

## Impact

- **Priority**: P2 — a shipped loop in the corpus is 100% non-functional and
  fails silently. Low blast radius (one loop, no library code), but total
  within that radius, and the silence is what makes it worth fixing promptly.
- **Effort**: Small — a two-line YAML fix restores function.
- **Risk**: Low. Repairing the state exposes downstream states that have never
  executed; expect follow-up issues from their first real run.
- **Breaking Change**: No

## Root Cause

`--quiet` was part of the original `ll-logs` CLI specification. A FEAT-1005
refinement record preserved in `.loops/.history/` notes the FEAT-1002 spec
included global flags "`--verbose`, `--config`, `--dry-run`, `--quiet`" and
flags them as missing from the issue's draft flag table. The implementation
that shipped never added them; the loop was authored against the specified
surface rather than the built one, and nothing gated the mismatch:

- Loop `action` strings are opaque shell to `ll-loop validate` — it checks FSM
  structure (MR-1..MR-14), not whether the commands inside an action parse.
- The `output_contains: "REFRESHED"` gate matches the wrapper's own `echo`
  text, so a total command failure is indistinguishable from a clean
  no-op-but-ran. The gate cannot detect its own subject failing.

## Scope Boundaries

**In scope:** `.loops/ll-logs-telemetry-digest.yaml`'s `refresh_corpus` state;
optionally wiring `add_quiet_arg` onto `ll-logs` parsers.

**Out of scope:** `_cmd_extract`'s success-path reporting and `-j/--json`
(ENH-2926); the rest of the digest loop's states, which are unverified only
because they have been unreachable — they may hold their own defects, and
reaching them for the first time is expected to surface some.

## Program Design

### Types
No new types. The required fix is YAML-only. The optional `--quiet` part
reuses the existing `add_quiet_arg(parser: argparse.ArgumentParser) -> None`
helper (`scripts/little_loops/cli_args.py:209-215`), which sets a boolean
`args.quiet`.

### Signatures
- `add_quiet_arg(parser)` — existing, exported at `cli_args.py:583`; already
  used by the sprint and parallel parsers (`cli_args.py:531`, `:554`). Wiring
  it onto `ll-logs` subcommand parsers in `cli/logs.py` is the whole of the
  optional part; no new helper is needed.
- `add_corpus_target_args(parser, *, required=True, ...)` (`cli_args.py:260`)
  — unmodified. Its `required=True` group is why `extract` needs an explicit
  `--project`/`--all`; the loop must supply one rather than the flag being
  relaxed.

### Call Path
`ll-loop run ll-logs-telemetry-digest` -> FSM executor -> `refresh_corpus`
`action` (shell) -> `ll-logs extract ...` -> `main_logs()`
(`cli/logs.py:2328`) -> `extract_parser.parse_args` **-> argparse SystemExit(2)
before `_cmd_extract` is ever reached** -> `&&` short-circuits -> `echo
"REFRESH_FAILED"` -> `evaluate: output_contains "REFRESHED"` false ->
`on_no: done`.

The failure is entirely in argument parsing; `_cmd_extract` never runs, which
is why no partial extraction or diagnostic appears.

### Decision Rules
- Whether to keep `--quiet` in the loop: keep only if the optional CLI part
  ships in the same change; otherwise remove it. Do not leave a flag in the
  loop that the CLI does not define.
- Which target to pass `extract`: `--all`, matching the state's intent to
  refresh the whole corpus (the `discover` line on the preceding row is
  likewise corpus-wide). No threshold or heuristic involved.

## Acceptance Criteria

- [ ] `refresh_corpus` reaches `run_stats` on a project with ll activity.
- [ ] Every command in `.loops/ll-logs-telemetry-digest.yaml` parses against
      the current `ll-logs` argument surface — no unregistered flags, no
      missing required arguments.
- [ ] `extract` is invoked with an explicit `--project`/`--all` target.
- [ ] If `--quiet` remains in the loop, it is registered via `add_quiet_arg`
      and covered by a test; otherwise it is removed.
- [ ] A test guards against recurrence: assert the loop's `ll-logs`
      invocations parse (e.g. via the subcommand parsers with
      `parse_known_args`), so spec/implementation drift fails the suite rather
      than silently disabling the loop.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- `docs/reference/CLI.md` `## ll-logs` section (~line 3129) — documents the
  real flag surface; confirm it does not advertise a `--quiet` that does not
  exist.
- `.claude/CLAUDE.md` § Loop Authoring — per-run artifact isolation under
  `${context.run_dir}` is the convention the diagnostic-capture suggestion
  above follows.

## Status

**Open** | Created: 2026-08-16 | Priority: P2
