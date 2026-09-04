# Runbook: Fleet Loop Review

> This is the first runbook in `docs/runbooks/`. A *guide* (`docs/guides/*`) explains a
> feature; a *runbook* documents an **operational procedure executed on a cadence**, with a
> checklist and a recorded baseline. Every runbook leads with the same five sections, in this
> order: **Purpose · Cadence · Phases · Baseline / Re-measure contract · In-scope rule**.

## Purpose

Other projects on this machine that use little-loops act as a **fleet-wide test bed** for
this repo's **built-in loops** (`loops/*.yaml`, ~104 at time of writing). Their real run
history — successes, stalls, and failures — is unbiased evidence this repo cannot self-grade:
a loop only knows it works because *other people's projects* keep converging when they run it.

This runbook turns "use other projects' logs to continuously fix and improve this repo's
built-in loops" into a repeatable, documented cycle instead of an ad-hoc investigation:

```
HARVEST (cross-project, read-only)
  → ATTRIBUTE each failure/stall to a built-in loop
    → DIAGNOSE + FIX (in this repo)
      → RE-MEASURE (next harvest's failure delta = acceptance signal)
```

The final arrow is mandatory. Per the meta-loop rules in `.claude/CLAUDE.md`, a harness
"improvement" is only proven when an *external* measure moves — here, the fleet's failure rate
for that loop, not a self-graded claim that a fix "looks right."

## Cadence

**On-demand, run manually — or as one cycle of the `fleet-loop-improve` built-in meta-loop.**
This is not a cron job. Run it whenever you suspect a built-in loop is misbehaving, before/after
landing a loop fix, or periodically as general maintenance hygiene.

The automated form of the whole cycle is:

```bash
ll-loop run fleet-loop-improve      # from this repo only; preflight refuses elsewhere.
                                    # A flagged loop whose YAML is dirty is skipped, not fatal.
```

It runs HARVEST with the flags above, applies the ATTRIBUTE rule, runs DIAGNOSE inside each
project that produced the runs, has the `loop-specialist` agent write its artifact and apply
the smallest fix, gates the fix with `ll-loop validate` plus the built-in loop tests, commits,
and records the fix as `pending` in `.loops/diagnostics/fleet-loop-improve-ledger.jsonl`. Its
RE-MEASURE is deliberately one invocation late: the *next* run's `measure_externally` state
compares the fresh harvest against each pending fix's recorded baseline (see § 4). See
[`docs/guides/LOOPS_REFERENCE.md#fleet-loop-improve`](../guides/LOOPS_REFERENCE.md#fleet-loop-improve)
for its states and knobs. A scheduled capture (cron) remains deferred.

## Phases

### 1. HARVEST (cross-project, read-only)

Run from **this repo** (`little-loops`) so the source repo's own dev-iteration runs don't
dominate the sample and stale pytest fixture projects don't spam stderr:

```bash
ll-logs fleet-review --all --existing-only --exclude-project .
```

This runs the `loop-fleet`, `scan-failures`, and `sequences` collectors in-process against every
other project with `ll` activity, derives a zero-run-built-ins list, validates every flagged
loop's YAML, and writes a stamped report plus a JSON sidecar under `.loops/diagnostics/` (see
the Baseline / Re-measure contract below). It never mutates anything — HARVEST is read-only by
design.

Useful variations:

- `--threshold N` (default `50`) / `--min-runs N` (default `3`) — tune the flagging rule (see
  ATTRIBUTE below).
- `--appendix-top N` (default `20`, `0` = unlimited) / `--no-appendices` — the `scan-failures`
  and `sequences` appendices are context, not flagging inputs, and can be expensive
  (~45s combined on a full fleet); skip them for a fast RE-MEASURE-only run.
- `--exclude-project DIR` (repeatable) — exclude any project, not just `.`; useful when a
  project's runs are known-noisy (e.g. mid-refactor) and would skew the sample.
- `--json` — prints the sidecar dict to stdout and **writes no files**. Use this for scripting;
  it never enters the baseline chain.

See `docs/reference/CLI.md` for the full flag reference.

### 2. ATTRIBUTE

The flagging rule is computed entirely from the `loop-fleet` aggregates — `scan-failures` and
`sequences` are unattributed context appendices, never flagging inputs (they carry no
loop-name key). A loop is flagged when **all** of the following hold:

- `attribution == "builtin"` (never `custom` or `shadowed` — see the In-scope rule below), and
- `runs >= --min-runs` (default `3`), and
- `success_pct < --threshold` (default `50`) **or** `top_outcome` is one of the four failure
  outcomes: `error`, `max-steps`, `stalled`, `failed`.

The full outcome vocabulary emitted by `_derive_loop_outcome()` is:

```
converged | failed | error | max-steps | stalled | interrupted | signal
```

Only `error`, `max-steps`, `stalled`, and `failed` count as flagging failures. `interrupted`
and `signal` are operator/infra exits (user stop, kernel signal), not loop-logic failures, so
they are deliberately excluded from the outcome clause — but they still count against
`success_pct` (which is `converged / runs`), so a loop dominated by `interrupted` runs can still
surface via the threshold clause. There is no dismissal list: a false positive is handled by
skipping it in DIAGNOSE and noting why under the report's "Reviewed, not fixed" section.

The report also lists two non-flagged categories for context:

- **Zero-run built-ins** — built-in loops nobody ran anywhere in the harvested window.
- **Shadowed built-ins** — see the In-scope rule below.

### 3. DIAGNOSE + FIX

For each flagged loop, the report gives the exact command to run **from inside the project
that produced the failing runs** — not from this repo:

```bash
cd <project> && ll-loop diagnose-evaluators <loop>
cd <project> && ll-loop calibrate-budget <loop>
```

This `cd` is required, not cosmetic: `diagnose-evaluators` and `calibrate-budget` only read the
*current* project's local `.loops/.history/` under its config-resolved `loops_dir`, and
`ll-loop` has no `--project`/`--loops-dir` flag. Run from this repo, both commands print "No
history" for any loop that only ran elsewhere. The `project` field on each flagged loop's
records (absolute path, copy-pasteable) is exactly what the report lists for this purpose.
Other projects' `.loops/.history/` is gitignored and prunable, so diagnose promptly after
harvest.

Once you have a diagnosis, the actual fix work — classifying the failure mode, proposing a
YAML change, and verifying it with a real iteration — is the **[`loop-specialist`
agent](../../agents/loop-specialist.md)**'s job. It also writes its own diagnosis artifact to
`.loops/diagnostics/<loop-name>-<UTC-timestamp>.md`, alongside this runbook's
`fleet-review-<stamp>.md`/`.json` in the same directory.

Fixes land in this repo's `loops/*.yaml`, go through normal review, and ship to the fleet on
the consuming projects' next little-loops update.

### 4. RE-MEASURE

Run HARVEST again later (after the fix has had time to accumulate fresh runs across the
fleet). The new report's **Delta vs baseline** table diffs the current sidecar against the
newest prior one, showing Δsuccess_pct, Δruns, Δconverged, and Δ for each failure outcome, per
loop. A positive Δsuccess_pct (or a failure outcome dropping out of `top_outcome`) for the
loop you fixed is the acceptance signal — proof against real fleet data, not a self-graded
claim that the fix "should" help. This is the meta-loop "measure-externally" step required by
`.claude/CLAUDE.md`.

`fleet-loop-improve` performs this step automatically at the start of every run: for each
ledger entry still `pending`, it takes the new sidecar's `runs`/`converged` minus the values
recorded when the fix landed and, once at least `min_new_runs` (default 3) fresh runs exist,
records `improved` / `regressed` / `unchanged`. A harvest with a different `window_days` or
`--exclude-project` set is reported as not comparable and the entry stays `pending`.
Regressions are recorded and printed, never auto-reverted — reverting is your call.

## Baseline / Re-measure contract

- The baseline is a **machine-local, gitignored JSON sidecar**:
  `.loops/diagnostics/fleet-review-<stamp>.json`, where `<stamp>` is `YYYYMMDDTHHMMSSZ` (UTC),
  e.g. `fleet-review-20260902T214729Z.json`. It is **never committed** — `.loops/` is
  gitignored and excluded from `ll-verify-private-refs`, and the sidecar may quote other
  projects' absolute filesystem paths (`projects`, `excluded_projects`, per-loop project
  breakdowns). This is by design: the baseline is per-machine, not shared across contributors.
- Every `fleet-review` run (except `--json` runs, which write nothing) automatically loads the
  **lexically-newest prior sidecar** in `.loops/diagnostics/` — excluding the sidecar it is
  about to write itself — and renders the delta table against it. You never point at a baseline
  file by hand.
- **Two runs are only comparable if their run population matches.** Changing `--window-days`
  / `--since` / `--until`, or the `--exclude-project` set, changes which runs feed the
  aggregates, so a delta against a differently-scoped prior run is meaningless. A comparability
  warning fires **automatically** in the report's Summary whenever the prior sidecar's window
  fields or its `excluded_projects`/`projects_scanned` lists differ from the current run's —
  you don't need to remember to check this yourself, but you do need to read the warning
  when it appears rather than trusting the delta table blindly.
- A run with no prior sidecar in the directory renders a "no prior baseline" line instead of a
  delta table — this is expected on the very first run.
- `fleet-loop-improve` writes its harvest through the same command, so a loop-driven sidecar
  is the newest baseline for your next manual run too. The loop keeps its own per-fix
  baselines in the ledger and does not depend on this delta table.

## In-scope rule

**Only this repo's built-in loops are fixed here.** Cross-project data is *evidence*, never a
mandate to change another project's files — a project's own custom loop, or its own modified
copy of a built-in, is fixed in that project, not back-ported into this repo. This is a
mechanical filter, not a judgment call: every harvested run carries an `attribution` of
`"builtin"`, `"custom"`, or `"shadowed"`, and only `"builtin"` runs ever feed the flagging rule.

**"Shadowed" is the trap this rule exists to prevent.** `ll-loop install` (and manual copying)
can create a project-local `.loops/<name>.yaml` or `.loops/<name>.fsm.yaml` file with the same
name as a built-in loop. Because `resolve_loop_path` prefers a project's own copy over the
package copy, every run of that name in that project actually executes the **project's
modified copy**, not this repo's loop — even though the run history has no other way to tell
the two apart (events carry only `loop` and `ts`, no provenance). Attributing those runs as
plain `"builtin"` would flag this repo's loop against failures it never produced. `fleet-review`
detects this at harvest time (a `.loops/<name>.yaml` or `.loops/<name>.fsm.yaml` file present in
the project) and labels those runs `"shadowed"` instead: they are **never flagged**, **never
counted as zero-run evidence** (a loop that only ran as a shadowed copy is still zero-run
*here*), and are listed separately in the report's "Shadowed built-ins" section (loop, absolute
project path, run count) so you can see the divergence without misattributing it. If a shadowed
copy is genuinely broken, that is a fix for the project that owns the copy — not this repo.

Reports and their sidecars live in `.loops/diagnostics/`, alongside the
[`loop-specialist` agent](../../agents/loop-specialist.md)'s own per-loop diagnosis artifacts —
both are recurring, tool-generated, gitignored, and private-refs-exempt, which is why this
runbook's output lives there rather than in `postmortems/` (reserved for ad-hoc run forensics).

## See also

- `docs/reference/CLI.md` — full `ll-logs fleet-review` flag reference and examples.
- [`agents/loop-specialist.md`](../../agents/loop-specialist.md) — the fix step: failure-mode
  taxonomy, diagnosis artifact structure, and verification protocol.
- `.claude/CLAUDE.md` § Loop Authoring — the meta-loop rules this runbook's RE-MEASURE step
  satisfies (diagnosis-first, non-LLM evaluator, per-run artifact isolation).
