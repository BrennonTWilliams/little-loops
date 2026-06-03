# Learning Tests Guide

## Contents

- [What Is a Learning Test?](#what-is-a-learning-test)
- [Quick Start](#quick-start)
- [The Four-Phase Workflow](#the-four-phase-workflow)
- [Record Status: proven, refuted, stale](#record-status-proven-refuted-stale)
- [The Record Format](#the-record-format)
- [CLI Reference](#cli-reference)
- [Pre-Seeding Assumptions with `--assume`](#pre-seeding-assumptions-with---assume)
- [Using Learning Tests in Loops](#using-learning-tests-in-loops)
- [Troubleshooting](#troubleshooting)
- [Practical Patterns](#practical-patterns)
- [Using Learning Tests in Issue Lifecycle Gates](#using-learning-tests-in-issue-lifecycle-gates)
- [Further Reading](#further-reading)

---

## What Is a Learning Test?

You are about to write code against an unfamiliar API, SDK, or stdlib corner. Instead of guessing its shape from docs (which may be wrong, out of date, or silent on the edge cases you care about), run a tiny script against it, write down what it actually returned, and save that evidence to a file the next agent — or the next session of you — can read.

That file is a learning test — a term from Michael Feathers, repurposed here for harness engineering. The underpinning idea is *deterministic backpressure*: agents go wrong when they rely on probabilistic feedback (a model guessing, or a second model grading the first), because a reviewer drawn from the same latent space tends to share the builder's wrong assumptions. The fix is to ground the agent in non-opinionated, observable truth — run real code against the real system and persist exactly what it returned. That captured evidence is a fact, not an opinion, so every later session reuses verified behavior instead of re-hallucinating the API's shape.

little-loops gives you three things to make this routine:

- `/ll:explore-api` — a skill that runs the exploration and writes the record for you.
- `.ll/learning-tests/` — a per-project registry of YAML-frontmatter Markdown files, one per target.
- `ll-learning-tests` — a read-only CLI other skills and FSM loops use to check whether a target is already proven before re-doing the work.

The point is to stop re-discovering the same API behavior every session. Once a target is proven, every future agent gets the verified interface for free.

## Quick Start

```bash
# 1. Prove an API
/ll:explore-api "Anthropic SDK streaming"

# 2. Inspect the record
ll-learning-tests check "Anthropic SDK streaming"

# 3. Future sessions: skip re-discovery
ll-learning-tests check "Anthropic SDK streaming" && echo "already proven, reuse it"
```

The record lives at `.ll/learning-tests/anthropic-sdk-streaming.md`. The raw proof output is at `.ll/learning-tests/raw/anthropic-sdk-streaming.txt`.

## The Four-Phase Workflow

`/ll:explore-api "<target>"` runs four explicit phases. Knowing what each does helps you steer mid-run and read the resulting record.

### 1. Ingest

The skill calls `ll-learning-tests check "<target>"`. If a record already exists, it prints it and asks whether to reuse it or overwrite with a fresh exploration. If no record exists, it reads any relevant docs (including anything previously mirrored by `/ll:scrape-docs`), greps for existing in-project usage, and summarises what's already known in 3–5 sentences. That summary scopes the hypotheses.

### 2. Hypothesize

The skill generates 3–7 **falsifiable claims** about the target's behavior — each a single observable statement, each testable by a minimal proof script. Examples for `"Anthropic SDK streaming"`:

- `streaming events are dicts with a "type" key`
- `the first event has type "message_start"`
- `text deltas arrive on event.delta.text when event.type == "content_block_delta"`
- `the stream emits a final event with type "message_stop"`

A good claim names a specific field, event type, or behavior. `"the API returns data"` is too vague — it will always pass. `"the response object has a .usage.input_tokens field"` is specific enough that running code either confirms or denies it. Avoid compound claims (`"X and Y both work"`) — split them; each claim should be independently evaluable.

Pre-seeded `--assume` claims (see below) are added at this stage with `result: untested`.

### 3. Execute

The skill scaffolds a minimal proof script (Python by default, Node if the target is JS-only) to a tempdir, runs it, and captures stdout+stderr together. On success it moves the captured output to `.ll/learning-tests/raw/<slug>.txt`. On failure (non-zero exit or no useful output) it keeps the stderr there anyway — a refuted exploration is still a valuable record.

The script is intentionally minimal: only enough code to surface evidence for the claims, no error handling beyond what the proof needs. The point is observation, not robustness.

### 4. Refine

The skill diffs each claim against the captured output and classifies the result as `pass`, `fail`, or `untested`, then sets the record status (see next section). It writes `.ll/learning-tests/<slug>.md`, verifies the write by calling `ll-learning-tests check "<target>"`, and reports the per-claim results in chat.

## Record Status: proven, refuted, stale

Every record carries one of three statuses:

- **`proven`** — at least one assertion passed. This is a deliberately loose threshold: partial proof is still useful evidence, and the per-assertion `pass`/`fail`/`untested` results in the record itself give the reader the full picture. A `proven` record with 1/5 passes is not the same as 5/5; read the assertions before relying on it.
- **`refuted`** — every exercised assertion failed. Something you assumed about the API is wrong. The raw output (see `raw_output_path`) usually shows the actual error or shape; read it before deciding what to do.
- **`stale`** — the record was valid when written but has been explicitly invalidated (see [Troubleshooting](#troubleshooting) for `mark-stale`). Never set on initial write.

**When a refuted record is the right next step:** read `cat .ll/learning-tests/raw/<slug>.txt` to see what actually came back — often a wrong field name or missing import explains all the failures. Then either delete the record and re-run `/ll:explore-api` with corrected claims, or, if the API itself changed, `mark-stale` it so the prior assertions remain visible as reference during debugging.

In FSM loops, `refuted` is terminal — the state routes to `on_blocked` without retrying. Missing and stale records, by contrast, auto-trigger a fresh `/ll:explore-api`.

## The Record Format

Records are YAML-frontmatter Markdown files with an empty body:

```yaml
---
target: Anthropic SDK streaming
date: '2026-05-25'
status: proven
assertions:
- claim: streaming events are dicts with a "type" key
  result: pass
- claim: the first event has type "message_start"
  result: pass
- claim: text deltas arrive on event.delta.text when event.type == "content_block_delta"
  result: pass
- claim: the stream emits a final event with type "message_stop"
  result: fail
- claim: stop_reason is "end_turn" when generation completes naturally
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic-sdk-streaming.txt
---
```

| Field | Type | Notes |
|---|---|---|
| `target` | `str` | The original free-text name you passed to `/ll:explore-api`, not the slug. |
| `date` | `str` | ISO date when the record was written. |
| `status` | `proven` \| `refuted` \| `stale` | See [Record Status](#record-status-proven-refuted-stale). |
| `assertions` | `list` of `{claim, result}` | `result` is `pass` / `fail` / `untested`. |
| `raw_output_path` | `str \| None` | Relative path to the captured proof output, or `null` when the proof script crashed before producing any output. |

## CLI Reference

`ll-learning-tests` is intentionally narrow: it owns reads and stale-marking, never writes. Record creation is owned by `/ll:explore-api` so the prompt context that produces the record also captures the reasoning behind it.

| Subcommand | Purpose | Exit |
|---|---|---|
| `check "<target>"` | Print the matching record as JSON | `0` if found, `1` if missing |
| `list` | Print every record as a JSON array | always `0` |
| `mark-stale "<target>"` | Set `status: stale` on an existing record | `0` on success, `1` if not found |

```bash
ll-learning-tests check "Anthropic SDK streaming"
ll-learning-tests list | jq -r '.[] | "\(.status)\t\(.target)"'
ll-learning-tests mark-stale "Anthropic SDK streaming"
```

## Pre-Seeding Assumptions with `--assume`

`--assume "<claim>"` pre-seeds a claim into the record with `result: untested`, without exercising it in the proof script. It's repeatable.

Why bother recording something you didn't test? Because an `untested` claim is a structured TODO, not a comment. It travels with the record, shows up in `ll-learning-tests check` output, and gets upgraded to `pass` or `fail` automatically if a future proof script happens to cover it. Use it for claims you believe to be true but can't cheaply test now — typically because they require expensive setup, depend on long-running behavior, or are stated by vendor docs without a local way to falsify them.

The `assumption-firewall` loop (see [LOOPS_GUIDE.md](LOOPS_GUIDE.md#api-adoption)) now auto-records untestable claims via `--assume`: after extracting API assumptions from an issue file, it classifies each as testable or untestable, and records the untestable ones as structured TODOs in the Learning-Test Registry. This eliminates false gate blocks from assumptions that require live credentials or vendor-only environments.

```bash
/ll:explore-api "Claude API tool use" \
  --assume "tools is a list of objects with name and input_schema" \
  --assume "stop_reason is tool_use when the model invokes a tool"
```

Assumed claims appear in the final record alongside the proven ones, flagged `result: untested` so a future reader knows they haven't been independently verified.

## Using Learning Tests in Loops

FSM loops can gate execution on proven assumptions via `type: learning` states. When a loop enters a learning state, the executor resolves the target list at runtime: if `learning.targets_csv` is set, it is interpolated and CSV-split into individual targets; otherwise `learning.targets` is used directly. The retry limit is resolved the same way — `learning.max_retries_expr` (if set) is interpolated and `int()`-cast; otherwise `learning.max_retries` (default 2) is used. Proven targets pass through immediately, missing or stale records auto-trigger `/ll:explore-api <target>` (up to the resolved retry limit), and refuted records (or exhausted retries) route to `on_blocked`. Learning states are exempt from the per-state `hard_max` throttle because they legitimately make N tool calls per visit.

Static target list (original form):

```yaml
states:
  learn:
    type: learning
    learning:
      targets:
        - "Anthropic SDK streaming"
        - "GitHub API rate limits"
      max_retries: 2
    on_yes: planning      # all targets proven → continue
    on_blocked: blocked   # any target refuted, or retries exhausted
```

Runtime CSV form — used by `ready-to-implement-gate` (the canonical built-in example):

```yaml
states:
  prove:
    type: learning
    learning:
      targets_csv: "${context.targets}"           # resolved + CSV-split at runtime
      max_retries_expr: "${context.max_retries}"  # resolved to int at runtime
    on_yes: done
    on_blocked: blocked
```

`on_blocked` fires when a target is `refuted` (no retries attempted) or when the retry limit is exhausted without it becoming proven. `on_no` is the fallback if `on_blocked` is not defined; prefer `on_blocked` for clarity.

Required fields: one of `learning.targets` (non-empty list) or `learning.targets_csv` (non-empty string), plus `on_yes`, and one of `on_blocked` / `on_no`. The dispatch emits `learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, and `learning_blocked` events for observability.

This is the integration point that makes the registry pay for itself: a loop that touches a third-party API can declare its assumptions up front, and the first run pays the discovery cost while every subsequent run skips straight to the actual work. See [LOOPS_GUIDE.md → Progressive tool-call throttling](LOOPS_GUIDE.md#progressive-tool-call-throttling) for the full `type: learning` reference and event schema.

## Troubleshooting

**`ll-learning-tests check` returns exit 1 for a record I believe exists**

The lookup is slug-based. The slug is derived by `little_loops.issue_parser.slugify`: lowercase, strip non-word characters (dots, slashes, colons), collapse whitespace and hyphens. `"Anthropic SDK streaming"` → `anthropic-sdk-streaming`; `"v1.2.3"` → `v123`; `"path/to/api"` → `pathtoapi`. Run `ll-learning-tests list | jq -r '.[].target'` to see all stored targets, or check the filenames under `.ll/learning-tests/` directly. The `/ll:explore-api` skill prints the resolved slug before writing.

**The proof script runs but all claims fail**

Check `.ll/learning-tests/raw/<slug>.txt` for the actual output. Common causes: wrong import path for the SDK, missing auth env var (the skill scaffolds scripts against your current shell environment — `ANTHROPIC_API_KEY` and similar must already be exported), or an SDK that changed its output shape since the record was written (use `mark-stale` and re-run).

**Marking a record stale**

When an upstream system changes — new SDK release, breaking API revision, behavior you discover is no longer accurate — invalidate the record without deleting it:

```bash
ll-learning-tests mark-stale "Anthropic SDK streaming"
```

This sets `status: stale` and preserves every other field, so the prior assertions remain visible for context. `/ll:explore-api` treats `stale` like missing on the next run. Delete a record outright (`rm .ll/learning-tests/<slug>.md`) only when the target itself is no longer relevant to the project.

**Bulk staleness detection**

For automated detection of stale records across the entire registry — e.g., after a dependency upgrade or at sprint start — use the `learning-tests-audit` loop:

```bash
ll-loop run learning-tests-audit
```

The loop enumerates installed packages (pip + npm), uses the LLM to map record targets to canonical package names, queries PyPI and npm registries for newer versions, bulk-marks stale records via `ll-learning-tests mark-stale`, and produces a four-section triage report under `.loops/runs/learning-tests-audit/report-<timestamp>.md`. See `docs/guides/LOOPS_GUIDE.md` → API Adoption for details.

**`/ll:explore-api` asks to overwrite a record I want to keep**

Phase 1 (Ingest) prompts before overwriting. Answer "reuse" to short-circuit. To guard against this in scripts, run `ll-learning-tests check "<target>"` first and skip the skill call if exit code is 0.

> Loop-state troubleshooting (`type: learning` states that re-trigger, `No valid transition` errors) lives in [LOOPS_GUIDE.md → Troubleshooting](LOOPS_GUIDE.md).

## Practical Patterns

**Prove before integrating.** Run `/ll:explore-api` against any new SDK, undocumented HTTP API, or stdlib corner you're uncertain about *before* writing the integration code. Cheaper than discovering the behavior mid-implementation.

**Cite the record in the code.** When you write the integration code, reference the record path in a comment near the call site (e.g. `# Verified shape: .ll/learning-tests/anthropic-sdk-streaming.md`). Future readers — human or agent — get a direct pointer to the evidence.

**Survey what's already proven at session start.** `ll-learning-tests list | jq -r '.[] | "\(.status)\t\(.target)"'` gives a one-shot inventory of verified targets before planning new work.

> For end-to-end workflows that chain learning tests into larger automations — `adopt-third-party-api` (docs URL → integration playbook) and `assumption-firewall` (issue ID → pre-implementation gate) — see [LOOPS_GUIDE.md → API Adoption](LOOPS_GUIDE.md#api-adoption).

## Using Learning Tests in Issue Lifecycle Gates

The `learning_tests_required` frontmatter field connects the registry to the interactive issue workflow — the complement to the FSM-layer `type: learning` state documented in [Using Learning Tests in Loops](#using-learning-tests-in-loops).

Declare assumptions in the issue file:

```yaml
learning_tests_required:
  - "Anthropic SDK streaming events"
  - "GitHub API pagination"
```

`/ll:ready-issue` queries each target via `ll-learning-tests check`:
- **Proven** → PASS row in VALIDATION table
- **Stale** → WARN row: re-run `/ll:explore-api "<target>"`
- **Refuted** → hard NOT_READY; includes the refutation summary
- **Missing** → NOT_READY: `❌ Unproven assumption: "<target>" — run /ll:explore-api "<target>"`

Issues without `learning_tests_required` are unaffected — the gate is opt-in.

`/ll:go-no-go` pre-fetches registry status for all declared targets and injects a **Learning Test Context** block into both adversarial agent prompts and the judge prompt before Phase 3b, so unproven assumptions surface in the judge's RATIONALE without requiring numeric score deltas.

## Further Reading

- [ARCHITECTURE.md → Learning Test Registry](../ARCHITECTURE.md#learning-test-registry) — registry design, slug derivation, and integration with the rest of the system.
- [CLI Reference → ll-learning-tests](../reference/CLI.md#ll-learning-tests) — terse subcommand reference.
- [LOOPS_GUIDE.md → Progressive tool-call throttling](LOOPS_GUIDE.md#progressive-tool-call-throttling) — the `type: learning` FSM state reference and event payloads.
- [`skills/explore-api/SKILL.md`](../../skills/explore-api/SKILL.md) — the authoring skill, including the exact slug algorithm and per-phase Bash invocations.
