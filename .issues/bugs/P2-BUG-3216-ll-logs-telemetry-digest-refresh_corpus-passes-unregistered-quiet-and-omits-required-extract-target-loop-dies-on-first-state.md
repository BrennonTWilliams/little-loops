---
id: BUG-3216
type: BUG
title: ll-logs-telemetry-digest omits the required --project/--all target on all five
  corpus states and reports failures as empty results
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
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
---

# BUG-3216: ll-logs-telemetry-digest omits the required --project/--all target on all five corpus states and reports failures as empty results

## Summary

`.loops/ll-logs-telemetry-digest.yaml` has never produced a usable run, and the
defect is not confined to one state. **Five states invoke `ll-logs` corpus
subcommands without the required `--project`/`--all` target**; every one of them
exits 2 at argparse before any command body runs.

`refresh_corpus` is the first and loudest: its two commands are both
malformed (unregistered `--quiet` *and* missing target), so the state always
echoes `REFRESH_FAILED`, its `output_contains: "REFRESHED"` gate always
evaluates false, and `on_no: done` terminates the loop on its first state.

Fixing `refresh_corpus` alone does not restore the loop — it converts a loud
failure into a **silent false negative**. See
[Post-Partial-Fix Failure Mode](#post-partial-fix-failure-mode) below; that
degradation, not the first-state death, is the main reason to fix this whole.

`refresh_corpus` is also **structurally different from the other four**, not
merely the loudest instance of one defect: no downstream state reads what
`extract` writes, and `extract --all` cannot return non-zero. Repairing its
arguments therefore yields a gate that is both vacuous and gating work the
digest never consumes. See
[refresh_corpus gates work nothing consumes](#refresh_corpus-gates-work-nothing-consumes).

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

### The same missing-target defect affects four more states

Defect 2 above is **not specific to `refresh_corpus`**. Every corpus-scoped
`ll-logs` subcommand takes the same `required=True` target group, and four
downstream states omit it exactly as `extract` does:

| State | Line | Invocation | Bare exit |
|---|---|---|---|
| `run_stats` | :29 | `ll-logs stats` | 2 |
| `scan_failures` | :41 | `ll-logs scan-failures --json` | 2 |
| `run_sequences` | :86 | `ll-logs sequences --top 20 --min-count 3` | 2 |
| `check_dead_skills` | :99 | `ll-logs dead-skills --json` | 2 |

Verified directly:

```
$ for c in stats scan-failures sequences dead-skills; do
    printf "%-14s --help exit=" "$c"; ll-logs $c --help >/dev/null 2>&1; echo -n "$?  "
    printf "bare exit="; ll-logs $c >/dev/null 2>&1; echo "$?"
  done
stats          --help exit=0  bare exit=2
scan-failures  --help exit=0  bare exit=2
sequences      --help exit=0  bare exit=2
dead-skills    --help exit=0  bare exit=2
```

Note the `--help` column: each of those four states gates its call behind an
`ll-logs <sub> --help >/dev/null 2>&1` capability probe, and **the probe passes
while the real invocation fails**. argparse services `-h` and exits 0 before it
validates required groups, so a `--help` probe structurally cannot detect a
missing required argument. The probe pattern is part of the root cause, not a
mitigation.

### refresh_corpus gates work nothing consumes

Three facts about `refresh_corpus` that do not apply to the other four states,
each verified against `cli/logs.py`:

**(a) No downstream state reads the corpus `extract` writes.** `_cmd_extract`
(`logs.py:740-796`) writes `Path.cwd() / "logs" / <slug> / <session-id>.jsonl`
(`:787-793`) and then `generate_index(Path.cwd() / "logs")` (`:795`). Nothing
in this loop opens `logs/`. The four analysis subcommands read their own
sources directly:

| State | Subcommand | Reads | Source |
|---|---|---|---|
| `run_stats` | `stats` | `<project>/.ll/history.db` | `logs.py:1336-1342` |
| `scan_failures` | `scan-failures` | `~/.claude/projects/<folder>/*.jsonl` | `logs.py:1112-1131` |
| `run_sequences` | `sequences` | `~/.claude/projects/<folder>/*.jsonl` | `logs.py:630-648` |
| `check_dead_skills` | `dead-skills` | `<project>/.ll/history.db` | `logs.py:972-978` |

`scan-failures` and `sequences` resolve session JSONL through
`get_project_folder(cwd_path)` — the same `~/.claude/projects/` tree `extract`
reads *from* — so they are independent of whether `extract` ever ran. The loop's
description ("refresh the ll-logs corpus, run all available analysis
subcommands") asserts a data dependency that does not exist in the code.

**(b) `extract --all` cannot fail.** `_cmd_extract` returns `1` only inside the
`args.project` branch, when `get_project_folder` yields `None` (`:745-747`).
The `--all` branch (`:749-755`) has no failure path and falls through to
`return 0` (`:796`) regardless of how many projects were found or how many
records were extracted. So once `--all` is supplied per Decision Rules, the
state's `&& echo "REFRESHED" || echo "REFRESH_FAILED"` wrapper always takes the
success arm, `output_contains: "REFRESHED"` is always true, and the `on_no:
done` edge becomes unreachable. **The gate is vacuous after the argument fix** —
Required part 2's failure-vs-emptiness work buys nothing on this state.

**(c) `--all` is a write, not a read.** `out_base = Path.cwd() / "logs" / slug`
(`:787`) means `extract --all` materializes one subdirectory *per discovered
project on the machine* under this repo's `logs/`. That directory already
exists here with 40+ project subdirectories. `logs/` is gitignored
(`.gitignore:21`), so this is not a correctness problem — but Decision Rules
should not justify `--all` on `refresh_corpus` as a "corpus-wide read," because
it is corpus-wide write amplification into the working repo.

### Post-Partial-Fix Failure Mode

Repairing only `refresh_corpus` makes the loop strictly harder to diagnose,
because the four states above swallow their own failures into plausible
success values:

- `ll-logs scan-failures --json > "$OUT" 2>&1` writes argparse's **usage text**
  into `failures.json` (stderr is merged into the file, not discarded).
- The inline `python3 -c` `json.load` raises on that text, hits its bare
  `except: print(0)`, so `COUNT=0`.
- `[ "$COUNT" -eq 0 ] && echo "NO_FAILURES"` → the evaluator takes `on_yes`,
  and `triage_failures` never runs.
- `check_dead_skills` follows the identical path to `NO_DEAD_SKILLS`.
- `run_stats` / `run_sequences` write usage text to `stats.txt` /
  `sequences.txt` and echo `STATS_ERR` / `SEQUENCES_ERR`, which nothing
  evaluates — both states are plain `next:` transitions.
- `synthesize_digest` then reads four artifacts containing argparse usage
  messages and writes a digest reporting **zero failures and zero dead
  skills**, printing `DIGEST_WRITTEN`. The run "succeeds."

So the current behavior fails loudly on state one; the partially-fixed
behavior emits a confident, wrong clean bill of health. That is a regression in
diagnosability, and it is why the four downstream states are in scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- Exact current `scan_failures` block (`.loops/ll-logs-telemetry-digest.yaml:37-63`, python at :42-50):
  ```
  OUT="${context.run_dir}/failures.json"
  if ll-logs scan-failures --help >/dev/null 2>&1; then
    ll-logs scan-failures --json > "$OUT" 2>&1
    COUNT=$(python3 -c "
  import json
  try:
      d = json.load(open('$OUT'))
      items = d.get('failures', d) if isinstance(d, dict) else d
      print(len(items) if isinstance(items, list) else 0)
  except Exception:
      print(0)
  " 2>/dev/null || echo 0)
    [ "$COUNT" -eq 0 ] && echo "NO_FAILURES" || echo "FAILURES_FOUND:$COUNT"
  else
    echo "NO_FAILURES"
  fi
  ```
  `check_dead_skills` (:95-121, python at :100-108) is structurally identical, differing only in the `OUT` path (`dead-skills.json`), the probed dict key (`d.get('dead', d)`), and the literals (`NO_DEAD_SKILLS`/`DEAD_SKILLS_FOUND:$COUNT`).
- The line `ll-logs scan-failures --json > "$OUT" 2>&1` (:41) and its `dead-skills` counterpart (:99) have **no** `$?`/`&&`/`||` check at all before the Python parse runs — unlike `run_stats` (:29: `... > "$OUT" 2>&1 && echo "STATS_OK" || echo "STATS_ERR"`) and `run_sequences` (:86-87), which do react to exit status (though neither persists the numeric code). So in `scan_failures`/`check_dead_skills` the bare `except Exception: print(0)` is the *only* place a non-zero `ll-logs` exit is observed, and it maps that failure to the same `print(0)` output as a legitimate empty result.

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

Every `ll-logs` invocation in the file parses against the built argument
surface and supplies an explicit target. `refresh_corpus` refreshes the corpus
and proceeds to `run_stats`; the four downstream states produce real artifacts
rather than argparse usage text; and a failed invocation is reported as a
failure rather than as an empty result.

```yaml
ll-logs discover 2>/dev/null || true
ll-logs extract --all 2>/dev/null && echo "REFRESHED" || echo "REFRESH_FAILED"
```

If output suppression is genuinely wanted, `--quiet` should be wired via the
existing shared `add_quiet_arg(parser)` helper (`cli_args.py:209-215`) rather
than dropped — see Proposed Solution for the two-part choice.

## Proposed Solution

Three parts. The first two are required; the third is a judgment call.

**Required (1) — supply a target on all five states.** Add an explicit
`--project`/`--all` to `extract` (`refresh_corpus`), `stats`, `scan-failures`,
`sequences`, and `dead-skills`, and drop `--quiet` from `refresh_corpus`'s two
lines (or keep it only if part 3 ships first). See Decision Rules for which
target each state should get — it is not uniform.

**Required (2) — make failure distinguishable from emptiness.** Fixing the
arguments without this leaves the loop one drift away from the false-clean
digest described above. Two changes:

- `scan_failures` and `check_dead_skills` must check the invocation's exit
  status *separately* from the parsed count, and must not report
  `NO_FAILURES`/`NO_DEAD_SKILLS` when the command exited non-zero. The current
  `except: print(0)` idiom makes an unparseable artifact look like an empty
  one.
- Replace `2>/dev/null` (and the stderr-into-artifact `2>&1` redirects) with
  capture to a distinct file under `${context.run_dir}`, so the next
  argument-surface drift leaves a diagnosable artifact. This was previously
  listed as optional; the post-partial-fix failure mode makes it required.

Do **not** extend the `ll-logs <sub> --help` capability probe to
`refresh_corpus`. The probe exits 0 for all four subcommands that then fail
(evidence above), so it provides false confidence rather than capability
detection. Either replace it with a probe that exercises the real argument
surface, or leave the real invocation's exit code as the signal.

**Optional (3) — wire `--quiet` on `ll-logs`.** `add_quiet_arg` already exists
and is used by the sprint/parallel parsers (`cli_args.py:531`, `:554`). Wiring
it on `ll-logs` subcommands would honor the original FEAT-1002 spec. Note this
interacts with ENH-2926, which adds success-path summary output to
`_cmd_extract` — a `--quiet` flag is most useful *after* extract has output to
suppress, so sequencing it after ENH-2926 is reasonable. Not a blocker in
either direction.

## Impact

- **Priority**: P2 — the loop is 100% non-functional and fails silently.
  **Blast radius is this repo only**: there is no copy of this loop under
  `scripts/little_loops/loops/` (`find . -name "*telemetry-digest*"` returns
  only the repo-root `.loops/` file and two issue files), so it is not a
  built-in shipped to consuming projects. It *is* git-tracked, so it is real
  committed content, not local scratch. Within that radius the failure is
  total, and the silence is what makes it worth fixing promptly.
- **Effort**: Small-to-moderate — the argument fixes are five one-line YAML
  edits, but the failure-vs-emptiness work (Required part 2) touches the two
  inline `python3 -c` count blocks.
- **Risk**: Low for the change itself. The notable risk is *under*-fixing:
  repairing only `refresh_corpus` yields a loop that completes and reports a
  false clean corpus (see Post-Partial-Fix Failure Mode), which is worse than
  today's fail-fast. Repairing all five states exposes downstream states that
  have never executed; expect follow-up issues from their first real run.
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
- `add_corpus_target_args(..., required=True)` (`cli_args.py:260-286`) is the
  shared factory for all six corpus subcommands, so a single authoring
  assumption ("these commands default to the current project") produced the
  same defect five times.

Beyond the mismatch itself, the loop contains **three independent
error-swallowing constructs**, each of which converts a hard failure into a
plausible success. This is one pattern, not three coincidences: *the loop never
observes the exit status of the thing it is gating on.*

1. **Echo-wrapper gates** — `... 2>/dev/null && echo "REFRESHED" || echo
   "REFRESH_FAILED"` with `output_contains: "REFRESHED"`. The gate matches the
   wrapper's own `echo` text, so a total command failure is indistinguishable
   from a clean no-op-but-ran. The gate cannot detect its own subject failing.
2. **Count-defaulting JSON parses** — the inline `python3 -c` blocks in
   `scan_failures` and `check_dead_skills` wrap `json.load` in a bare
   `except: print(0)`, so an artifact containing an argparse usage message
   yields `COUNT=0`, which the state reports as `NO_FAILURES` /
   `NO_DEAD_SKILLS`.
3. **`--help` capability probes** — `if ll-logs <sub> --help >/dev/null 2>&1`
   is used by four states to decide whether a subcommand is implemented.
   argparse services `-h` and exits 0 *before* validating required argument
   groups, so the probe returns 0 for all four subcommands whose real
   invocation exits 2 (verified above). The probe proves the subcommand exists;
   it proves nothing about whether the loop's actual invocation parses.

Construct 3 is worth calling out specifically because a prior reading of this
file treated the probe pattern as the good convention that `refresh_corpus`
failed to follow. It is not — copying it into `refresh_corpus` would add false
confidence without detecting anything.

## Scope Boundaries

**In scope:** all five states in `.loops/ll-logs-telemetry-digest.yaml` that
invoke a corpus-scoped `ll-logs` subcommand — `refresh_corpus`, `run_stats`,
`scan_failures`, `run_sequences`, `check_dead_skills` — covering both the
missing `--project`/`--all` target and the failure-vs-emptiness reporting in
the latter two; the unregistered `--quiet` in `refresh_corpus`; optionally
wiring `add_quiet_arg` onto `ll-logs` parsers.

**Out of scope:** `_cmd_extract`'s success-path reporting and `-j/--json`
(ENH-2926); the loop's `action_type: prompt` states (`triage_failures`,
`file_dead_skill_issues`, `synthesize_digest`, `commit`) and the
`commit_if_needed` shell state, which contain no `ll-logs` invocation. Those
prompt states have still never executed and may hold their own defects;
reaching them for the first time is expected to surface some, and those belong
in follow-up issues.

> **Note — earlier scoping was self-contradictory.** A prior revision listed
> the four downstream states as out of scope on the grounds that they were
> merely "unverified because unreachable," while simultaneously requiring (in
> Acceptance Criteria) that *every* command in the file parse. They are not
> unverified: `ll-logs stats|scan-failures|sequences|dead-skills` were each run
> directly and each exits 2. They are verifiably broken by the same defect, and
> are now in scope.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` (states `run_build`:192-222, `run_typecheck`:284-312, `run_lint`:314-339, `service_health`:341-397) is an existing in-repo precedent for capturing exit status alongside redirected output under a run-scoped dir: `bash -c "$CMD" > "$${ABS_DIR}/out.txt" 2>&1; RC=$?; echo "exit_code=$RC" >> "$${ABS_DIR}/out.txt"; echo "exit_code=$RC"` paired with `evaluate: {type: exit_code}` — the RC is appended into the same output file the command wrote to.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml` (lines 271-278, 291-329) is a second precedent, differing in shape: it captures `$?` into a named variable immediately after each redirected command (`INSTALL_RC`, `ROOT_RC`, `PYTEST_RC`) and, on non-zero, writes a distinct report file separate from the raw log (e.g. `$RUN_DIR/verify-cli.txt` vs `$RUN_DIR/install.log`) before an early `exit 1`.
- The two precedents agree that command output must land in a `${run_dir}`-scoped file (never `/dev/null`, never silently merged) and that `$?` must be captured on the line immediately following the redirected command; they disagree on whether the RC is appended into the same file the evaluator reads or drives a distinct report file via an early-exit branch.
- Within `.loops/ll-logs-telemetry-digest.yaml` itself, `${context.run_dir}` is already used for every state's output artifact — `run_stats` (`stats.txt`, :27), `scan_failures` (`failures.json`, :39), `run_sequences` (`sequences.txt`, :84), `check_dead_skills` (`dead-skills.json`, :97) — so routing stderr/diagnostics there follows an in-file precedent, not new syntax.
- `run_stats` (:29) and `run_sequences` (:86-87) already gate on exit status via `&&`/`||` immediately after the redirected command, but neither persists the numeric `$?` anywhere; `scan_failures` (:41) and `check_dead_skills` (:99) have no `$?` capture at all — success/failure is inferred purely from the downstream JSON parse.

### Files to Modify
All edits are in the single file `.loops/ll-logs-telemetry-digest.yaml`
(git-tracked; confirmed via `git ls-files .loops/`), plus an optional CLI change
and a new test:

- `:15-16` — `refresh_corpus`: drop the unregistered `--quiet` from both `discover` and `extract`; add a target to `extract`; capture stderr to `${context.run_dir}` instead of `/dev/null`
- `:29` — `run_stats`: add a target to `ll-logs stats`
- `:41` — `scan_failures`: add a target to `ll-logs scan-failures --json`; separate exit-status checking from the JSON count so a failed call cannot report `NO_FAILURES`
- `:86` — `run_sequences`: add a target to `ll-logs sequences --top 20 --min-count 3`
- `:99` — `check_dead_skills`: add a target to `ll-logs dead-skills --json`; same exit-status/count separation as `scan_failures`
- `scripts/little_loops/cli/logs.py` — **optional only** (Proposed Solution part 3): `add_quiet_arg` on the relevant subcommand parsers in `_build_parser()` (`:2065`)
- `scripts/tests/` — new regression test guarding the loop's `ll-logs` invocations (see Tests below for why it cannot join `TestBuiltinLoopFiles`)

### Dependent Files (Callers/Importers of `cli/logs.py`)
- `scripts/tests/test_ll_logs.py:16` — imports `logs.py` symbols directly (`ChainResult`, `Edge`, ...)
- `scripts/little_loops/cli/ctx_stats.py:20` — imports `_aggregate_skill_stats` from `logs.py`
- `scripts/little_loops/cli/__init__.py:73` — imports `main_logs` for top-level dispatch
- `scripts/little_loops/cli/loop/_helpers.py:19` — loop-running helper module that imports `logs.py`
- `scripts/tests/test_cli_ctx_stats.py:13`, `scripts/tests/test_enh_3166_qwen_normalizer.py:32` — transitive impact set via `ctx_stats.py`/`__init__.py`

### Conventions in Force
- `add_corpus_target_args(parser, *, required=True, ...)` (`cli_args.py:260-286`) is the shared factory for every corpus-scoped `ll-logs` subcommand; it is called identically by `extract_parser` (`logs.py:2107`), `sequences_parser` (`:2118`), `stats_parser` (`:2147`), `scan_failures_parser` (`:2161`), `dead_skills_parser` (`:2186`), and `loop_fleet_parser` (`:2257`) — all six require an explicit `--project`/`--all` selector by default.
- `add_quiet_arg(parser)` (`cli_args.py:209-215`) is a shared flag helper, but its only callers anywhere in the codebase are `add_common_auto_args` (`cli_args.py:531`) and `add_common_parallel_args` (`cli_args.py:554`) — confirming it has never been wired onto any `ll-logs` subcommand parser (`_build_parser()`, `logs.py:2065`).
- Elsewhere in this same loop file, `run_stats` (`:28`), `scan_failures` (`:40`), `run_sequences` (`:85`), and `check_dead_skills` (`:98`) each gate their `ll-logs` invocation behind a `ll-logs <sub> --help` capability probe first — a pattern `refresh_corpus` does not follow before calling `discover`/`extract`. **This is an anti-pattern to fix, not a convention to adopt:** the probe exits 0 for all four subcommands while their real invocation exits 2 (verified in Current Behavior), because argparse services `-h` before validating required groups. None of these four states pass `--all`/`--project` either, so there is no in-loop example of a correctly-targeted corpus-subcommand call to copy from within `.loops/` — the only correct examples are in `docs/reference/CLI.md` (see Documentation below).
- CLI-testing convention (evidence, not a template to copy verbatim): every test that exercises `ll-logs` subcommands drives the real `main_logs()` entry point via `patch.object(sys, "argv", ["ll-logs", ...])` then asserts on exit code/output — e.g. `TestMainLogsIntegration` (`scripts/tests/test_cli.py:2940`) and `TestEvalExport.test_no_regression_extract` (`scripts/tests/test_ll_logs.py:3885-3893`, which asserts `SystemExit(0)` and `"--project" in` help output). No test in the codebase parses a shell string with `shlex` and feeds it into an imported parser object's `parse_known_args` directly — the established convention is to drive `main_logs()` under a patched `sys.argv`, not to introspect `_build_parser()` (`logs.py:2065`, module-private) as an object.

### Tests
- `scripts/tests/test_ll_logs.py` — main `ll-logs` CLI test suite; `TestEvalExport.test_no_regression_extract` (`:3885-3893`) is the closest existing precedent for a regression guard on subcommand argument surface.
- `scripts/tests/test_cli.py:2940` — `TestMainLogsIntegration`, exercises `discover`/`stats`/etc. through `main_logs()`.
- `scripts/tests/test_cli_args.py:562-600` — `TestAddCorpusTargetArgs`, covers `add_corpus_target_args`'s required-group behavior directly.
- `scripts/tests/test_builtin_loops.py:28-31` — `TestBuiltinLoopFiles` runs structural checks (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, etc.) over every loop under `BUILTIN_LOOPS_DIR` (`scripts/little_loops/loops/`). **`.loops/ll-logs-telemetry-digest.yaml` lives at the repo-root `.loops/` directory, not under `BUILTIN_LOOPS_DIR`, so it is not covered by this suite** — a new regression test for this file needs its own explicit path reference; no existing test class in the codebase targets a repo-root `.loops/` file this way.
- **Referencing it by path is safe.** `git ls-files .loops/` lists `.loops/ll-logs-telemetry-digest.yaml`, so the file is committed content available to any checkout, and `.gitignore` excludes only runtime subdirectories under `.loops/` (`.running/`, `.history/`, `.queue/`, `tmp/`, `runs/`, …), not the loop YAMLs themselves. A test may therefore assert on it directly. Because it is a source-repo file rather than packaged data, the test belongs to this repo's suite only and should skip cleanly if the path is absent, per the existing convention for source-repo-only artifacts.
- No existing test in `scripts/tests/` parses a loop YAML's `action:` shell strings and validates the embedded CLI invocations against argparse — this is the gap Acceptance Criteria's last bullet asks to fill, not a pattern already present elsewhere.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug_2816_cli_invocations.py` — exact precedent pattern for the new regression test: it guards `BUILTIN_LOOPS_DIR` loop YAMLs (not repo-root `.loops/`) against broken embedded CLI/skill invocations from the same defect class (BUG-2816). Its `_text()`/`yaml.safe_load()` helper plus string-membership assertions on an extracted `action` block (e.g. `TestApplyResearchFix`, `TestLoopInputFlagSweep:106-122`) is the template to adapt with a `REPO_ROOT_LOOPS_DIR` pointed at `.loops/` instead of `BUILTIN_LOOPS_DIR`; none of it round-trips through real `argparse.parse_args()`, so the acceptance criterion's "parses against the current argument surface" bar still needs `main_logs()` (`TestEvalExport.test_no_regression_extract`, `test_ll_logs.py:3885-3893`) or a direct parser call layered on top.

### Documentation
- `docs/reference/CLI.md:3263-3265` — documents `ll-logs extract --all`, `ll-logs extract --project /path/to/proj`, `ll-logs extract --all --cmd ll-history`; the only existing examples of a correctly-targeted `extract` invocation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:3294-3306` — the `## ll-logs` section's "Companion loop" prose narratively describes this loop's pipeline and shows `ll-loop run ll-logs-telemetry-digest`; a second reference site (beyond :3263-3265) worth rechecking for staleness once the fix lands, though it makes no claim the loop currently works.
- `docs/reference/CLI.md:20` — the "Common Flags" table's `--quiet` row lists `Used by: ll-auto, ll-parallel, ll-sprint run, ll-sync`; `ll-logs` is absent. **Only needs an edit if optional Part 3 ships** (wiring `add_quiet_arg` onto `ll-logs` subcommand parsers) — otherwise no action.

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
- **Which target each state gets — not uniform.** The rule is whether the
  state's output feeds issue *filing* in this project or read-only aggregate
  reporting:
  - `refresh_corpus` (`extract`), `run_stats`, `run_sequences` → **`--all`**.
    These are corpus-wide reads whose output lands in the digest; the
    `discover` line on `refresh_corpus`'s preceding row is likewise
    corpus-wide.
  - `scan_failures`, `check_dead_skills` → **`--project .`** by default. Both
    feed `action_type: prompt` states (`triage_failures`,
    `file_dead_skill_issues`) that run `/ll:capture-issue`, which files issue
    files **into this repo's `.issues/`**. Under `--all`, this repo's backlog
    accumulates issues describing *other projects'* failures and unused
    skills. The CLI already treats this as a hazard worth an explicit opt-in:
    `scan-failures` ships `--capture-foreign` (`logs.py:2166`) precisely to
    gate cross-project capture. Note `dead-skills`' `--all` help text
    ("catalog loaded from current directory") means `--all` there compares a
    *local* catalog against corpus-wide counts — coherent, but it makes
    locally-defined skills look used because another project invoked them.
  - If corpus-wide triage is actually wanted, that is a deliberate design
    change: pass `--all` *and* narrow the prompt states' capture instructions,
    rather than letting `--all` reach issue-filing implicitly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Additional Call Path Detail (confirmed via codebase-analyzer)
- `discover_parser` (`logs.py:2082-2092`) is wired with only `add_json_arg(discover_parser)` (`:2086`)
  and a locally-defined `--existing-only` (`:2087-2092`) — no `add_quiet_arg` call, confirming
  `--quiet` is unregistered on `discover` specifically, not just `extract`.
- `main_logs()` (`logs.py:2295`) calls `parser.parse_args()` (`:2306`) with no
  `parse_known_args` fallback — an unrecognized token or an unsatisfied required
  mutually-exclusive group triggers argparse's `error()` (usage message + exit
  code 2) before any of `main_logs()`'s own dispatch body (`:2308-2351`) executes.
- FSM side: `_run_action()` (`fsm/executor.py:2092`) executes the state's shell
  block via `self.action_runner.run(...)` (`:2274`); `_evaluate()`
  (`fsm/executor.py:2557`) routes to `evaluate_output_contains()`
  (`fsm/evaluators.py:436-490`), which does `re.search("REFRESHED", "REFRESH_FAILED\n")`
  → `None` → `verdict="no"` (`evaluators.py:471`) → executor resolves
  `state.on_no` = `"done"` and transitions straight to the terminal `done:` state
  (`.loops/ll-logs-telemetry-digest.yaml` line 195).
- No `error_patterns` are configured on `refresh_corpus`, so the evaluator's
  `verdict == "error"` branch (`evaluators.py:474-485`) is never reached — the
  argparse failure is indistinguishable from a clean "ran but found nothing" no,
  confirming the Root Cause section's claim that the gate cannot detect its own
  subject failing.

## Acceptance Criteria

- [ ] `refresh_corpus` reaches `run_stats` on a project with ll activity.
- [ ] Every command in `.loops/ll-logs-telemetry-digest.yaml` parses against
      the current `ll-logs` argument surface — no unregistered flags, no
      missing required arguments.
- [ ] **All five states invoking corpus subcommands — `refresh_corpus`
      (`extract`), `run_stats`, `scan_failures`, `run_sequences`,
      `check_dead_skills` — pass an explicit `--project`/`--all` target**,
      chosen per Decision Rules rather than uniformly.
- [ ] **A failed `ll-logs` call is distinguishable from an empty result.**
      `scan_failures` and `check_dead_skills` check the invocation's exit
      status separately from the parsed count, and do not report
      `NO_FAILURES` / `NO_DEAD_SKILLS` when the command exited non-zero. A
      forced failure of either command must not yield a digest claiming a
      clean corpus.
- [ ] **`--help` capability probes are not treated as proof that the real
      invocation parses.** Either the probe is replaced with one that
      exercises the actual argument surface, or the real invocation's exit
      code is the signal — and the probe is not copied into `refresh_corpus`.
- [ ] **Command output and stderr are captured under `${context.run_dir}`**
      rather than discarded to `/dev/null` or merged into an artifact that a
      JSON parser will then choke on, so the next drift leaves a diagnosable
      file.
- [ ] If `--quiet` remains in the loop, it is registered via `add_quiet_arg`
      and covered by a test; otherwise it is removed.
- [ ] A test guards against recurrence: assert the loop's `ll-logs`
      invocations parse (e.g. via the subcommand parsers with
      `parse_known_args`), covering all five states rather than
      `refresh_corpus` alone, so spec/implementation drift fails the suite
      rather than silently disabling the loop.
- [ ] `python -m pytest scripts/tests/` exits 0.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- The regression test in the last criterion above cannot piggyback on `TestBuiltinLoopFiles`
  (`scripts/tests/test_builtin_loops.py:28-31`) — that suite only walks
  `BUILTIN_LOOPS_DIR` (`scripts/little_loops/loops/`), and `.loops/ll-logs-telemetry-digest.yaml`
  lives at the repo-root `.loops/` directory instead, so it needs its own explicit
  path reference.
- No prior test in this codebase parses a loop's `action:` shell string with `shlex`
  and feeds tokens into an imported parser object's `parse_known_args` — the
  established convention for exercising `ll-logs` argument surfaces is instead to
  drive the real `main_logs()` entry point under `patch.object(sys, "argv", [...])`
  and assert on exit code/output (`TestMainLogsIntegration`,
  `scripts/tests/test_cli.py:2940`; `TestEvalExport.test_no_regression_extract`,
  `scripts/tests/test_ll_logs.py:3885-3893`) — evidence for which approach fits this
  codebase's existing test shape, not a mandated implementation.

## Related Key Documentation

- `docs/reference/CLI.md` `## ll-logs` section (~line 3129) — documents the
  real flag surface; confirm it does not advertise a `--quiet` that does not
  exist.
- `.claude/CLAUDE.md` § Loop Authoring — per-run artifact isolation under
  `${context.run_dir}` is the convention the diagnostic-capture suggestion
  above follows.

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/enhancements/P3-ENH-2317-ll-logs-cwd-defaults-all-opt-in-host-audit.md`
  (status `deferred`) and
  `.issues/enhancements/P3-ENH-2318-retarget-scan-failures-at-user-own-failures-with-ll-tools-flag.md`
  — both open issues build their back-compat rationale on this loop's
  *current, pre-fix* call shape ("`scan-failures`/`dead-skills` invoked with
  no scope flag"). ENH-2318 lists resolving that gap as one of its own open
  items (option "(c) add `--all` to the loop YAML"). Once this issue lands,
  both need a follow-up note: the "no scope flag" premise their designs
  protect against no longer holds.

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-08-16T23:31:17 - `595e4216-652b-4848-8dd6-c7dffee1e3bc.jsonl`
- `/ll:wire-issue` - 2026-08-16T23:29:41 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
- `/ll:refine-issue` - 2026-08-16T23:21:46 - `f105a63f-bfd2-4442-8228-f308dc8f7f01.jsonl`
- `/ll:refine-issue` - 2026-08-16T23:08:11 - `09f214c5-efef-498d-8c5a-346f6f1baa05.jsonl`
