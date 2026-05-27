# Learning Tests Guide

## Contents

- [What Is a Learning Test?](#what-is-a-learning-test)
- [Quick Start](#quick-start)
- [The Four-Phase Workflow](#the-four-phase-workflow)
- [The Record Format](#the-record-format)
- [CLI Reference](#cli-reference)
- [Pre-Seeding Assumptions with `--assume`](#pre-seeding-assumptions-with---assume)
- [Using Learning Tests in Loops](#using-learning-tests-in-loops)
- [Marking a Record Stale](#marking-a-record-stale)
- [Practical Patterns](#practical-patterns)
- [Further Reading](#further-reading)

---

## What Is a Learning Test?

A learning test is a small, evidence-bearing record of what an external API, SDK, or other black-box system actually does — not what its docs claim, not what the model guessed, what running code proved. The term is Michael Feathers' (see [the philosophy essay](../deterministic-backpressure-learning-tests.md) for the long version); the short version is: before you write integration code against an unknown system, run a proof script against it, write the observed shape down as a set of pass/fail/untested claims, and commit it to a registry the next agent (or the next session of you) can read.

little-loops gives you three things to make this routine:

- `/ll:explore-api` — a skill that walks the agent through Ingest → Hypothesize → Execute → Refine and writes the record for you.
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

The slug is derived by `little_loops.issue_parser.slugify`: lowercase, strip non-word characters, collapse whitespace and hyphens. `"Anthropic SDK streaming"` → `anthropic-sdk-streaming`. The skill prints the resolved slug before writing so you can correct the target if it slugifies unexpectedly.

## The Four-Phase Workflow

`/ll:explore-api "<target>"` runs the Feathers Learning Test lifecycle as four explicit phases. Knowing what each phase does helps you steer mid-run and read the resulting record.

### 1. Ingest

The skill first calls `ll-learning-tests check "<target>"`. If a record already exists, it prints it and asks whether to short-circuit and reuse it, or proceed with a fresh exploration that will overwrite the prior file. If no record exists, it reads any relevant docs (including anything previously mirrored by `/ll:scrape-docs`), grep/globs for existing in-project usage of the API, and summarises what's already known in 3–5 sentences. That summary scopes the hypotheses.

### 2. Hypothesize

The skill generates 3–7 **falsifiable claims** about the target's behavior — each a single observable statement, each testable by a minimal proof script. Examples for `"Anthropic SDK streaming"`:

- `streaming events are dicts with a "type" key`
- `the first event has type "message_start"`
- `text deltas arrive on event.delta.text when event.type == "content_block_delta"`
- `the stream emits a final event with type "message_stop"`

Pre-seeded `--assume` claims (see below) are added at this stage with `result: untested`.

### 3. Execute

The skill scaffolds a minimal proof script (Python by default, Node if the target is JS-only) to a tempdir, runs it, and captures stdout+stderr together. On success it moves the captured output to `.ll/learning-tests/raw/<slug>.txt`. On failure (non-zero exit or no useful output) it keeps the stderr there anyway — a refuted exploration is still a valuable record.

The script is intentionally minimal: only enough code to surface evidence for the claims, no error handling beyond what the proof needs. The point is observation, not robustness.

### 4. Refine

The skill diffs each claim against the captured output and classifies the result as `pass`, `fail`, or `untested`. It sets the record `status`:

- `proven` — at least one assertion passed.
- `refuted` — every exercised assertion failed.
- `stale` — reserved for `ll-learning-tests mark-stale` later; never set on initial write.

It then writes `.ll/learning-tests/<slug>.md` and verifies the write by calling `ll-learning-tests check "<target>"` (expects exit 0). Finally it reports the per-claim results in chat so you can scan the findings without opening the file.

## The Record Format

Records are YAML-frontmatter Markdown files with an empty body. The shape is exactly what `little_loops.learning_tests.write_record()` emits:

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
| `date` | `str` | ISO date when the record was written. Single-quoted to match `yaml.dump`. |
| `status` | `proven` \| `refuted` \| `stale` | `proven` when ≥1 assertion passes; `refuted` when all exercised assertions fail; `stale` set later via `mark-stale`. |
| `assertions` | `list` of `{claim, result}` | `result` is `pass` / `fail` / `untested`. `untested` covers both `--assume`-pre-seeded claims and claims the proof script did not exercise. |
| `raw_output_path` | `str \| None` | Relative path to the captured proof output. |

The dataclass definitions are in [`scripts/little_loops/learning_tests.py`](../../scripts/little_loops/learning_tests.py) — `LearnTestRecord` and `Assertion`.

## CLI Reference

`ll-learning-tests` is intentionally narrow: it owns reads and stale-marking, never writes.

| Subcommand | Purpose | Exit |
|---|---|---|
| `check "<target>"` | Print the matching record as JSON | `0` if found, `1` if missing |
| `list` | Print every record as a JSON array | always `0` |
| `mark-stale "<target>"` | Set `status: stale` on an existing record | `0` on success, `1` if not found |

```bash
ll-learning-tests check "Anthropic SDK streaming"
ll-learning-tests list
ll-learning-tests mark-stale "Anthropic SDK streaming"
```

There is no `write` subcommand — and this is deliberate. Record creation is owned by `/ll:explore-api` (and any future authoring skills) so the prompt context that produces the record also captures the reasoning behind it, not just the answer. If you want to persist a new record, run the skill; if you only want to read, query, or invalidate, use the CLI.

## Pre-Seeding Assumptions with `--assume`

`--assume "<claim>"` pre-seeds a claim into the record with `result: untested` without exercising it in the proof script. It's repeatable. Use it for claims you believe to be true but don't want to (or can't) test directly — typically because they require expensive setup, depend on long-running behavior, or are stated by vendor docs without a cheap way to falsify them locally.

```bash
/ll:explore-api "Claude API tool use" \
  --assume "tools is a list of objects with name and input_schema" \
  --assume "stop_reason is tool_use when the model invokes a tool"
```

Assumed claims appear in the final record alongside the proven ones, but they're flagged `result: untested` so a future reader knows they haven't been independently verified. If the proof script happens to cover one, the result is updated to `pass` or `fail` accordingly.

## Using Learning Tests in Loops

FSM loops can gate execution on proven assumptions via `type: learning` states. When a loop enters a learning state, the executor iterates `learning.targets`: proven targets pass through immediately, missing or stale records auto-trigger `/ll:explore-api <target>` (up to `learning.max_retries` times), and refuted records (or exhausted retries) route to `on_blocked`. Learning states are exempt from the per-state `hard_max` throttle because they legitimately make N tool calls per visit.

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

Required fields: `learning.targets` (non-empty), `on_yes`, and one of `on_blocked` / `on_no`. The dispatch emits `learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, and `learning_blocked` events for observability.

This is the integration point that makes the registry pay for itself: a loop that touches a third-party API can declare its assumptions up front, and the first run pays the discovery cost while every subsequent run skips straight to the actual work. See [LOOPS_GUIDE.md → Progressive tool-call throttling](LOOPS_GUIDE.md#progressive-tool-call-throttling) for the full `type: learning` reference and the related event schema.

## Marking a Record Stale

When an upstream system changes — a new SDK release, a breaking API revision, a behavior you discover is no longer accurate — invalidate the record without deleting it:

```bash
ll-learning-tests mark-stale "Anthropic SDK streaming"
```

This sets `status: stale` and preserves every other field, so the prior assertions remain visible for context. `/ll:explore-api` treats `stale` records like missing records: on the next run, it proposes a fresh exploration rather than reusing the prior result. FSM `type: learning` states also treat `stale` as "needs re-exploration" and auto-trigger `/ll:explore-api` for that target.

Delete a record outright (`rm .ll/learning-tests/<slug>.md`) only when the target itself is no longer relevant to the project. Stale is the right tool for "needs refreshing"; deletion is for "we don't care anymore".

## Practical Patterns

**Prove before integrating.** Run `/ll:explore-api` against any new SDK, undocumented HTTP API, or stdlib corner you're uncertain about *before* writing the integration code. Cheaper than discovering the behavior mid-implementation.

**Cite the record in the code.** When you write the integration code, reference the record path in a comment near the call site (e.g. `# Verified shape: .ll/learning-tests/anthropic-sdk-streaming.md`). Future readers — human or agent — get a direct pointer to the evidence.

**Survey what's already proven at session start.** `ll-learning-tests list` prints every record as JSON. Pipe through `jq -r '.[] | "\(.status)\t\(.target)"'` for a one-shot inventory of verified targets before planning new work.

**Pair with `/ll:scrape-docs`.** When the target has vendor documentation, mirror the docs locally first (the `scrape-docs` skill writes them under `docs/`), then run `/ll:explore-api` — the Ingest phase will read the mirrored docs and produce sharper hypotheses than running against nothing.

**Full end-to-end adoption with `adopt-third-party-api`.** To go from a vendor docs URL straight to a verified, citation-linked integration playbook in one command, use the `adopt-third-party-api` loop — it combines `/ll:scrape-docs`, LLM enumeration of up to 7 key surfaces, and `ready-to-implement-gate` proof in a single automated pipeline:

```bash
ll-loop run adopt-third-party-api "https://manual.raycast.com/extensions"
# Writes docs/integration-manual-raycast-com.md with one section per proven LT record
```

Partial coverage (some targets refuted or exhausted) still produces a playbook — unverified sections are flagged at the top with citations to the relevant LT records. See [LOOPS_GUIDE.md → API Adoption](LOOPS_GUIDE.md#api-adoption) for details.

**Gate an issue against the registry with `assumption-firewall`.** When you want to block implementation on an issue until its external-API assumptions are proven (without scraping new docs), use `assumption-firewall`. It extracts up to 7 API assumptions from the issue ID via LLM, delegates proof to `ready-to-implement-gate`, and routes `done`, `blocked`, or `no_external_deps`:

```bash
ll-loop run assumption-firewall --context input="FEAT-1234"
# done          → all assumptions proven; safe to implement
# blocked       → one or more assumptions refuted; check LT records for details
# no_external_deps → no external-API assumptions found; proceed unconditionally
```

Use `assumption-firewall` as a lightweight pre-implementation check before delegating to `autodev` or `ll-auto`. Unlike `adopt-third-party-api`, it works from an issue ID rather than a docs URL and does not produce an integration playbook.

**Re-prove after major version bumps.** After upgrading a dependency that has a learning-test record, `mark-stale` the record and re-run `/ll:explore-api`. The diff between the old (stale) record's assertions and the new one is a concise migration checklist.

## Further Reading

- [Agentic Workflow Architecture: Designing Deterministic Backpressure Systems](../deterministic-backpressure-learning-tests.md) — the philosophy: why proof-based exploration beats LLM-on-LLM critique.
- [ARCHITECTURE.md → Learning Test Registry](../ARCHITECTURE.md#learning-test-registry) — registry design, slug derivation, and integration with the rest of the system.
- [CLI Reference → ll-learning-tests](../reference/CLI.md#ll-learning-tests) — terse subcommand reference.
- [LOOPS_GUIDE.md → Progressive tool-call throttling](LOOPS_GUIDE.md#progressive-tool-call-throttling) — the `type: learning` FSM state reference and event payloads.
- [`skills/explore-api/SKILL.md`](../../skills/explore-api/SKILL.md) — the authoring skill, including the exact slug algorithm and per-phase Bash invocations.
