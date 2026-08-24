---
name: advise
description: Use when asked for a second opinion from a different, stronger model on a specific decision, question, or stalled judgment call.
disable-model-invocation: false
argument-hint: "--signal SIGNAL --question QUESTION [--context-file PATH] [--host HOST] [--model MODEL]"
allowed-tools:
  - Bash(ll-advise:*)
  - Read
  - Write
arguments:
  - name: signal
    description: "What prompted this consult (e.g. user_requested, score_stall). Required — there is no unsignalled consult path."
    required: true
  - name: question
    description: "The consult prompt — the specific decision or question to put to the advisor host."
    required: true
metadata:
trigger_fixtures:
  should_fire:
    - "get a second opinion from a different model on whether this design is sound"
    - "consult the advisor about this stalled decision before we proceed"
  should_not_fire:
    - "adversarial review of whether this issue is worth implementing, go or no-go"
    - "run a pre-implementation confidence check on this issue"
---

# Advise — Second-Model Consult

Wraps the `ll-advise` CLI: assemble decision context from the current
transcript, call `ll-advise`, and surface the structured verdict back into
the transcript. This is the model-decided invocation path for a
second-model consult — distinct from a hand-typed `ll-advise` shell call
and from FEAT-3038's future gate-wired auto-consult.

**Distinct from `/ll:go-no-go`**: go-no-go is a same-model adversarial
debate via `Agent` subagents; `/ll:advise` is a one-shot consult to a
different (typically stronger) model.

## Process

1. **Assemble context.** Gather the decision context already present in
   the current transcript — the question, and any relevant file or diff
   excerpts — into a context payload. Write it to a temporary file (e.g.
   `.loops/tmp/advise-context.txt`) with `Write` and pass it as
   `--context-file`. Never auto-slurp the working tree; only include what
   is already part of the conversation.
2. **Require an explicit signal.** If no `--signal` value is supplied or
   resolvable from the invocation, do not call `ll-advise` with a
   silently-defaulted signal:

   ```
   Error: --signal is required
   Usage: /ll:advise --signal SIGNAL --question QUESTION [--context-file PATH]
   ```

   Stop here — do not guess a signal value.
3. **Invoke `ll-advise --json`**, capturing both stdout and stderr and the
   exit code:

   ```bash
   ll-advise --signal "$SIGNAL" --question "$QUESTION" --context-file "$CONTEXT_FILE" --json
   ```

   On exit 0, parse stdout's 7-key JSON payload (`recommendation`, `risks`,
   `confidence`, `dissent`, `signal`, `host`, `model`) and surface
   `recommendation`, `risks`, `confidence`, and `dissent` back into the
   transcript.
4. **On a non-zero exit, render the captured stderr line verbatim** — never
   a paraphrase, never a raw traceback, never a silent swallow, and never a
   parsed JSON `error` field (no such field exists on this path; `--json`
   has no effect on failure output). Two distinct cases:
   - exit 2 with `could not read --context-file ...` — the payload file was
     unwritable/unreadable; the consult never ran and no budget was spent.
   - exit 2 with one of the seven fail-soft `skipped_reason` messages,
     optionally suffixed `: <error detail>`:
     - `disabled` — "advisor is disabled (advisor.enabled: false)"
     - `trigger_not_allowed` — "signal not in advisor.triggers allowlist"
     - `budget_exhausted` — "advisor consult budget exhausted for this task
       (advisor.max_consults_per_task)"
     - `not_configured` — "advisor host not configured — set advisor.host
       in .ll/ll-config.json or pass --host"
     - `floor_violation` — "capability floor violation"
     - `failed` — "advisor consult failed"
     - `timeout` — "advisor consult timed out"
5. **Budget side effect.** Every invocation spends one unit of
   `advisor.max_consults_per_task`, reserved *before* the host call — so a
   hung or failed consult still counts against the same per-task budget
   that FEAT-3038's gate-wired auto-consult will later draw from. Do not
   invoke this skill repeatedly expecting each call to be free.

## Examples

```bash
ll-advise --signal user_requested --question "Is this design sound?" --json
ll-advise --signal score_stall --question "..." --context-file notes.md --json
ll-advise --signal user_requested --question "..." --host codex --model gpt-5.1 --json
```
