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
  short-description: Generate an FSM verification loop (criteria mode) or adversarial probe loop
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

Generate a ready-to-run FSM verification loop YAML from a single issue ID via
`ll-loop scaffold-verify` (FEAT-2948). Two modes:

- **`mode: criteria`** (**default**) — walks each acceptance criterion in order and asks
  an LLM whether the implementation satisfies it, failing fast on any criterion that
  fails. Cheap: cost scales with criterion count.
- **`mode: adversarial`** (**explicit opt-in**) — tries to *break* the feature via
  three distinct probe classes (boundary values, malformed/hostile inputs, failure
  modes) instead of confirming it works. **Verdict rule: attempting fewer than 3
  genuine probe classes is itself a FAIL**, even if every attempted probe passed.
  Expensive: a fixed floor of three open-ended probe states before a verdict.

Both modes emit only `llm_structured` verify/probe states — this skill has no
generator flag for the deterministic pre-patch check (ENH-3142/ENH-2997/ENH-2998).
That check is a separate, opt-in guard: a `prepatch_check: fail | warn | allow`
field on a guarded FSM state (or `FSMLoop.prepatch_check` as its loop-level
default), gated by `config.prepatch_check.enabled` (default `false`), that reruns
candidate tests against a pre-patch worktree and produces its own
`flagged` / `clean` / `skipped` verdict — independent of, and not a substitute
for, an emitted loop's `llm_structured` acceptance-criteria verdict. The same
check also runs on the non-FSM `ll-auto`/`ll-parallel` path via
`work_verification.verify_work_was_done()`. Hand-add `prepatch_check:` to a
generated loop's guarded states if you want both signals.

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

## Step 1: Generate the Loop

`ll-loop scaffold-verify` owns issue resolution, criteria extraction (with
bullet-marker normalization — checkboxes, plain bullets, numbered lists; sub-bullets
skipped), state chaining, timeout selection (1800 criteria / 2700 adversarial), and
in-process FSM validation. Both open and completed issues resolve (no
`completed/`/`deferred/` directory split).

```bash
ISSUE_LOWER=$(echo "$ISSUE_ID" | tr '[:upper:]' '[:lower:]')
PREFIX="verify"
if [ "$MODE" = "adversarial" ]; then PREFIX="adversarial"; fi
FLAG=""
if [ "$MODE" = "adversarial" ]; then FLAG="--adversarial"; fi

mkdir -p .loops/
ll-loop scaffold-verify "$ISSUE_ID" $FLAG --json > /tmp/scaffold-verify-result.json
```

Read the JSON result (`yaml_text`, `validated`, `errors`). If `yaml_text` is empty
(e.g. `criteria` mode found no Acceptance Criteria/Expected Behavior bullets), report
the `errors` list verbatim and stop — do not write a file:

```
Error: issue <ISSUE-ID> has no Acceptance Criteria section (or it is empty).
Run /ll:refine-issue <ISSUE-ID> to add criteria, or /ll:format-issue <ISSUE-ID>
to fix the section heading. No file was written.
```

## Step 2: Write and Report

The generated `yaml_text` is immediately runnable — criteria/adversarial mode
prompts are fully determined by the issue's own title and criterion text, so there
are no `<PLACEHOLDER>` slots to fill (unlike `/ll:create-eval-from-issues`, whose
harness prompts genuinely require LLM authoring).

Write it to `.loops/<PREFIX>-<issue-id-lower>-<title-slug>.yaml` (use the `name:`
field inside the returned YAML for the exact slug), then report:

```
✓ Verification loop generated: .loops/<name>.yaml

Issue: <ISSUE-ID>: <title>
Mode: criteria | adversarial
Validation: PASS / FAIL
  [errors if FAIL]

To run:
  ll-loop run <name>
```

If `validated` is `false`, show the `errors` and explain what needs fixing before
the loop can run — `ll-loop scaffold-verify` already ran `validate_fsm()` in-process,
so no separate `ll-loop validate` call is needed.

**See also:** `/ll:create-loop`, `/ll:go-no-go`, `/ll:create-eval-from-issues`
