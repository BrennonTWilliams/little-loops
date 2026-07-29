---
name: verify-issue-loop
description: Use when asked to generate an FSM verification loop YAML from a single issue's acceptance criteria, or an adversarial variant that tries to break the feature via boundary/malformed/failure-mode probes.
argument-hint: "<issue-id> [--mode criteria|adversarial]"
allowed-tools:
  - Bash(ll-issues:*, ll-loop:*, mkdir:*)
  - Read
  - Write
arguments:
  - name: issue_id
    description: A single issue ID (e.g., FEAT-919, ENH-950, BUG-347). Accepts open or completed issues.
    required: true
  - name: mode
    description: "criteria (default) — one state per acceptance criterion, fails fast; adversarial — three probe states (boundary, malformed/hostile, failure-mode) plus a filesystem-derived probe-count gate. Optional; an absent mode resolves silently to criteria."
    required: false
metadata:
trigger_fixtures:
  should_fire:
    - "generate a verification loop from this single issue's acceptance criteria"
    - "create an FSM loop verifying this issue's acceptance criteria"
    - "generate an adversarial verification loop that tries to break this feature with boundary values and malformed inputs"
    - "create an FSM loop probing failure modes via malformed inputs for this feature"
  should_not_fire:
    - "generate an FSM eval harness yaml from issue ids"
---

# Verify Issue Loop

Generate a ready-to-run FSM verification loop YAML from a single issue ID. Two modes:

- **`mode: criteria`** (**default**) — walks each acceptance criterion in order and asks
  an LLM whether the implementation satisfies it, failing fast on any criterion that
  fails. Cheap: cost scales with criterion count.
- **`mode: adversarial`** (**explicit opt-in**) — tries to *break* the feature via
  three distinct probe classes (boundary values, malformed/hostile inputs, failure
  modes) instead of confirming it works. **Verdict rule: attempting fewer than 3
  genuine probe classes is itself a FAIL**, even if every attempted probe passed.
  Expensive: a fixed floor of three open-ended probe states before a verdict.

This is the verification counterpart to `/ll:create-eval-from-issues`. Where
`create-eval-from-issues` exercises a feature *as a user would* and judges experience
quality, `verify-issue-loop` checks that the *implementation* meets each acceptance
criterion (`criteria` mode) or survives adversarial probing (`adversarial` mode).

### Choosing a mode

`criteria` is the default because it is the cheaper, bounded, fail-fast path — a bare
`/ll:verify-issue-loop <ID>` (or an FSM state wiring it in without knowing `mode`
exists) must not silently opt into the far more expensive adversarial path. The two
modes cost the same to *run* (resolve, emit one YAML, validate) but the loops they
emit do not: adversarial carries `timeout: 2700` against criteria's `1800`, and always
pays a fixed floor of three open-ended probe states, whereas criteria's cost scales
with the acceptance-criterion count and fails fast on criterion 1. Prefer `criteria`
for confirming implementation conformance; reach for `mode: adversarial` deliberately
when you specifically want boundary/malformed/failure-mode robustness testing, not as
a casual default.

## Overview

Both modes share a spine:
1. Resolve the issue ID to a file path using `ll-issues show <ID> --json`
2. Read the issue file to extract criteria (and title, for adversarial mode)
3. Synthesize mode-specific states (see Mode sections below)
4. Wire routing
5. Write the file to `.loops/<prefix>-<ISSUE-ID>-<slug>.yaml` (`verify-` for
   `criteria`, `adversarial-` for `adversarial` — output paths stay
   mode-distinguished so already-generated loops are unaffected)
6. Validate with `ll-loop validate` and report the result

## Arguments

$ARGUMENTS

Parse arguments:

```bash
ISSUE_ID=""
MODE="criteria"
for token in $ARGUMENTS; do
  case "$token" in
    --mode=*) MODE="${token#--mode=}" ;;
    --mode) MODE="__next__" ;;
    --*) ;;  # skip other flags (reserved for future use)
    *)
      if [ "$MODE" = "__next__" ]; then
        MODE="$token"
      else
        ISSUE_ID="$token"
      fi
      ;;
  esac
done

if [ -z "$ISSUE_ID" ]; then
  echo "Error: an issue ID is required."
  echo "Usage: /ll:verify-issue-loop FEAT-919 [--mode criteria|adversarial]"
  exit 1
fi

if [ "$MODE" != "criteria" ] && [ "$MODE" != "adversarial" ]; then
  echo "Error: --mode must be 'criteria' or 'adversarial' (got: $MODE)."
  exit 1
fi
```

`mode` is optional and defaults to `criteria`. An absent `mode` resolves silently —
never error or prompt for it.

## Step 1: Resolve Issue File (shared)

Resolve the issue file path:

```bash
ll-issues show "$ISSUE_ID" --json
```

Use the `path` field from the JSON result. If `ll-issues show` fails, report the error and stop.

**Both open and completed issues are accepted.** The `ll-issues show` command finds an issue by ID regardless of its `status:` frontmatter (open, done, deferred, etc.) — there is no `completed/` or `deferred/` directory.

## Step 2: Extract Title and Acceptance Criteria (shared)

Read the resolved issue file directly and extract:

1. **Title** — from the YAML frontmatter `title:` field or the first `# ISSUE-NNN:` heading
2. **Acceptance Criteria section** — the `## Acceptance Criteria` section body

Parse the criteria into an ordered list. Accept any bullet style:
- `- [ ] ...` / `- [x] ...` (checkbox style — strip the leading marker)
- `- ...` / `* ...` (plain bullets)
- `1. ...` / `2. ...` (numbered list)

Strip the marker and whitespace; keep the criterion text. Skip blank lines and
sub-bullets (indented items belong to their parent criterion).

**Mode-specific handling of a missing/empty section:**

- `mode: criteria` — **halt** with a clear error:
  ```
  Error: issue <ISSUE-ID> has no Acceptance Criteria section (or it is empty).
  Run /ll:refine-issue <ISSUE-ID> to add criteria, or /ll:format-issue <ISSUE-ID>
  to fix the section heading. No file was written.
  ```
  Do **not** write a YAML file in this case.
- `mode: adversarial` — **do not halt**; fall back to the issue title and Summary
  section as the probe target. The criteria text (if any) is used only to focus
  probe prompts on what the feature is supposed to do.

## Step 3 & 4: Synthesize States and Wire Transitions

See [templates.md](templates.md) for the full per-mode state-synthesis prompts,
transition wiring, and fully-expanded YAML templates:

- **`mode: criteria`** — one `verify-criterion-N` state per criterion, `llm_structured`
  pass/fail, linear `on_yes: verify-criterion-<N+1>` chaining (final state's
  `on_yes: done`), `on_no: failed`, `on_partial: failed`. `initial:
  verify-criterion-1`. Terminals: `done`, `failed`.
- **`mode: adversarial`** — three fixed probe states (`probe-boundary`,
  `probe-malformed-hostile`, `probe-failure-mode`), each `llm_structured`, chained on
  `on_yes`, `on_no: failed_with_finding`. Final probe's `on_yes` routes to
  `count_probes` — **not `done`**. `initial: probe-boundary`. Terminals: `done`,
  `failed_with_finding`, `failed_too_few`.

  **`count_probes` (load-bearing, keep prominent — do not bury in prose):** a
  `action_type: shell` state that counts probe-result JSON files physically written
  during the run (`ls "${context.run_dir}"/probe-*.json 2>/dev/null | wc -l`),
  evaluated with `output_numeric` (`operator: ge`, `target: 3`). This gate is
  filesystem-derived, not LLM-self-reported — the same self-evaluation-bias concern
  MR-1 encodes. **Attempting fewer than 3 genuine probe classes is itself a FAIL**
  (routes to `failed_too_few`), even if every attempted probe passed.

## Step 5: Slug Generation and Output Path (shared)

```bash
ISSUE_LOWER=$(echo "$ISSUE_ID" | tr '[:upper:]' '[:lower:]')
TITLE_SLUG=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
PREFIX="verify"
if [ "$MODE" = "adversarial" ]; then PREFIX="adversarial"; fi
LOOP_NAME="${PREFIX}-${ISSUE_LOWER}-${TITLE_SLUG}"
OUTPUT_FILE=".loops/${LOOP_NAME}.yaml"
```

If the issue title cannot be extracted cleanly, fall back to
`LOOP_NAME="${PREFIX}-${ISSUE_LOWER}"`.

Generate fully-expanded YAML (self-contained, no `from:` inheritance) per the
templates in [templates.md](templates.md). `mode: criteria` loops get
`timeout: 1800`; `mode: adversarial` loops get `timeout: 2700`. Both get
`max_steps: 20` and per-state `timeout: 300`.

## Step 6: Write and Validate (shared)

```bash
mkdir -p .loops/
```

Use the Write tool to write the YAML to `.loops/<loop-name>.yaml`.

Then validate:

```bash
ll-loop validate <loop-name>
```

Report the validation result. If validation fails, show the errors and explain what needs to be fixed.

## Output Format

See [templates.md](templates.md) for the per-mode Output Format block and Example.

**See also:** `/ll:create-loop`, `/ll:go-no-go`, `/ll:create-eval-from-issues`
