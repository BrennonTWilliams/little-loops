---
name: init
description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap config.
disable-model-invocation: true
argument-hint: "[flags]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(ll-init:*)
  - Bash
arguments:
  - name: flags
    description: "Optional flags: --force, --dry-run, --hosts, --codex, --upgrade"
    required: false
metadata:
  short-description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap
---

# Initialize Configuration

<!-- PLUGIN_VERSION: 1.106.0 -->

`/ll:init` is the intelligence layer over `ll-init`'s `--plan` / `apply --config`
seam: run the plan, settle every ambiguous or unverified value by reading the
repo, apply the corrected plan, then smoke-check the settled commands. A
fully-declared repo (all `provenance: declared`) is nearly as fast as
`ll-init --yes` — there's nothing to settle, so Inspect is a no-op.

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
FORCE_FLAG=""
DRY_RUN=false
HOSTS_FLAG=""
CODEX_FLAG=""
UPGRADE=false

if [[ "$FLAGS" == *"--force"* ]]; then FORCE_FLAG="--force"; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--hosts"* ]]; then
    HOSTS_VALUE=$(echo "$FLAGS" | grep -oP '(?<=--hosts\s)\S+' || true)
    if [[ -n "$HOSTS_VALUE" ]]; then HOSTS_FLAG="--hosts $HOSTS_VALUE"; fi
fi
if [[ "$FLAGS" == *"--codex"* ]]; then CODEX_FLAG="--codex"; fi
if [[ "$FLAGS" == *"--upgrade"* ]]; then UPGRADE=true; fi
```

### 2. Plan

Run the plan and capture its JSON:

```bash
ll-init --plan $HOSTS_FLAG $CODEX_FLAG
```

Parse `detected`, `proposed_config`, `host_options`, `warnings`, `provenance`,
and `ambiguities` from stdout.

### 3. Inspect

For each `provenance` entry whose `provenance` is `inferred` or `default`, and
for each `ambiguities` entry, read the relevant repo files (manifests, CI
config, README, Makefile/justfile, lockfiles) to settle the value:

- Keys with `declared` provenance are already trusted — do **not** re-derive
  or touch them.
- Edit **only** the corresponding key inside `proposed_config` — `ll-init
  apply` reads solely `proposed_config` (or the plan itself, if that key is
  absent); any `provenance`/`ambiguities` keys you leave in the JSON are
  ignored by apply, so settled values must land inside `proposed_config`
  itself.
- If a value is genuinely undecidable after reading the repo:
  interactively (no `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS`
  env and no automation flag), ask the user; headless/auto contexts, keep
  the default and note it in the final report instead of guessing.
- Skip this step entirely (go straight to Apply) if both `provenance` and
  `ambiguities` contain nothing needing settlement — that's the
  fully-declared fast path.

### 4. Apply

Write the corrected plan JSON (same shape returned by step 2, with
`proposed_config` edited in place) to a temp file, then:

```bash
ll-init apply --config <plan.json> $FORCE_FLAG
```

**`--dry-run`**: stop here instead — print the corrected plan and exit
without calling `apply`. Nothing is written.

### 5. Handle `--upgrade`

`ll-init apply` has no upgrade path (it always installs adapters at the
current version). If `UPGRADE` is true, after Apply completes run the
upgrade side effects as a separate step:

```bash
ll-init --yes --upgrade $HOSTS_FLAG $CODEX_FLAG
```

### 6. Verify (Smoke Check)

Skip this step if `--dry-run` was set (nothing was applied). Run the
settled `test_cmd` and `lint_cmd` from the applied config once each,
foreground-blocking, skip-if-null per command — mirroring
`skills/manage-issue/SKILL.md`'s Phase 4 Verify:

```bash
mkdir -p .loops/tmp/scratch
{{config.project.test_cmd}} > .loops/tmp/scratch/init-verify-test.txt 2>&1; tail -20 .loops/tmp/scratch/init-verify-test.txt
{{config.project.lint_cmd}} > .loops/tmp/scratch/init-verify-lint.txt 2>&1; tail -20 .loops/tmp/scratch/init-verify-lint.txt
```

A failing command is a **warning**, not a rollback: report it with the
output excerpt, but the applied config stays intact.

### 7. Report

Print a summary: which keys were settled and how (repo evidence, cited
per key), any keys left at their default with a note, host adapters
installed, and the Verify pass/fail per command (or `SKIP` if unconfigured).

## Examples

```bash
/ll:init                 # plan -> inspect ambiguous/default keys -> apply -> smoke-check
/ll:init --force         # reset to template defaults, then run the same flow
/ll:init --dry-run       # plan -> inspect -> print corrected plan; writes nothing
/ll:init --hosts codex   # also install Codex hook adapter
/ll:init --upgrade       # apply, then run `ll-init --yes --upgrade` for adapter/package upgrade
```

## Related

- `scripts/little_loops/init/cli.py:525-573` (`_run_plan`) and `:595-677`
  (`_run_apply`) — the CLI seam this skill wraps; not modified by this skill.
- `skills/manage-issue/SKILL.md` Phase 4 — the Verify/smoke-check pattern this
  skill's step 6 mirrors.
- `skills/spike/SKILL.md` — the plan-artifact + bounded-verify +
  warning-not-rollback shape this skill's steps 4/6 follow.
