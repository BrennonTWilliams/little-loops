---
name: explore-api
description: Use when exploring an external API/library and recording proof to the Learning Test Registry.
argument-hint: "<target> [--assume <claim>]..."
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ll-learning-tests:*, mkdir:*, mv:*, python:*, node:*, ls:*, cat:*)
arguments:
  - name: target
    description: Free-text description of the system or API to explore (e.g., "Anthropic SDK streaming").
    required: true
  - name: assume
    description: Pre-seed a claim as assumed-true without running a proof. Repeatable (--assume "<claim>" --assume "<claim>").
    required: false
metadata:
  short-description: Use when exploring an external API/library and recording proof to the Learning T
---

# Explore API

Guide the agent through the four-phase **Feathers Learning Test** lifecycle for an external system — Ingest → Hypothesize → Execute → Refine — and persist a `LearnTestRecord` to the Learning Test Registry (`.ll/learning-tests/<slug>.md`).

## When to Use

Run when you need to understand how an external API, SDK, or library actually behaves before writing production code that depends on it. Use cases:

- Unsure what events an SDK emits during streaming
- Verifying response shape of a third-party HTTP API
- Confirming the precise return type of a stdlib function
- Building a shared knowledge base so future agents can skip re-discovery (via `ll-learning-tests check "<target>"`)

Do **not** use this skill for testing your own project code — that is what `scripts/tests/` is for. This skill is for external-system exploration only.

## Arguments

$ARGUMENTS

Parse the input as follows:

```
TARGET = ""           # required positional, first non-flag token
ASSUMED_CLAIMS = []   # repeatable, each --assume "<claim>" appends

tokens = shell-tokenize($ARGUMENTS)
i = 0
while i < len(tokens):
    if tokens[i] == "--assume":
        ASSUMED_CLAIMS.append(tokens[i+1])
        i += 2
    elif tokens[i].startswith("--assume="):
        ASSUMED_CLAIMS.append(tokens[i].split("=", 1)[1])
        i += 1
    elif TARGET == "":
        TARGET = tokens[i]
        i += 1
    else:
        # extra positional — append to TARGET with a space
        TARGET = TARGET + " " + tokens[i]
        i += 1

if TARGET == "":
    print "Error: target is required"
    print 'Usage: /ll:explore-api "<target>" [--assume "<claim>"]...'
    exit 1
```

Repeatable-flag convention: each `--assume "<claim>"` token-pair contributes one pre-seeded claim. The first non-flag token (or all of them, joined) is the target description.

## Compute Slug

The output filename is derived by slugifying the target. The skill must compute the slug to know where to write — and to preview it to the user before doing so.

Algorithm (matches `little_loops.issue_parser.slugify`):

```python
import re
def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-").lower()
```

Example: `"Anthropic SDK streaming"` → `anthropic-sdk-streaming`. Resolved paths:

- Record: `.ll/learning-tests/anthropic-sdk-streaming.md`
- Raw output: `.ll/learning-tests/raw/anthropic-sdk-streaming.txt`

Print the resolved slug before proceeding so the user can correct the target if it slugified unexpectedly.

---

## Phase 1: Ingest

Determine what is already known before generating new hypotheses.

1. **Check the registry first** — query for a prior record of this target:

   ```bash
   ll-learning-tests check "$TARGET"
   ```

   - **Exit 0** (record exists): print the existing JSON record and ask whether to short-circuit and reuse it, or proceed with a fresh exploration (which will overwrite the prior file). If reusing, report the record and stop.
   - **Exit 1** (no record): proceed.

2. **Read relevant docs and code samples** — use `Read`, `Glob`, and `Grep` to gather:
   - Any vendor docs already mirrored under `docs/` (e.g., from the `scrape-docs` skill)
   - Existing source code in the project that already uses this API
   - Type stubs, dataclasses, or schema files describing the system

3. **Summarize known facts** in 3–5 sentences. This summary scopes the hypotheses generated in Phase 2.

---

## Phase 2: Hypothesize

Generate **3–7 falsifiable claims** about the target's behavior. Each claim must:

- Be a single observable statement (not a compound assertion)
- Be testable by a minimal proof script
- Be specific enough that the script's stdout or exception will clearly prove or refute it

Examples for `"Anthropic SDK streaming"`:

- `streaming events are dicts with a "type" key`
- `the first event has type "message_start"`
- `text deltas arrive on event.delta.text when event.type == "content_block_delta"`
- `the stream emits a final event with type "message_stop"`

Pre-seed any `--assume` claims into the list with `result: untested`. They will appear in the final record but will not be exercised by the proof script unless they happen to be covered by the script's assertions.

Present the full claim list to the user before moving to Phase 3.

---

## Phase 3: Execute

Build and run a minimal proof script that exercises each non-assumed claim.

1. **Pick a language** — Python is the default. Use Node/TypeScript if the target is JS-only.

2. **Scaffold the script to a temp path first** (not directly to `.ll/learning-tests/raw/`), so a failed run does not pollute the registry directory:

   ```bash
   TEMP_DIR=$(mktemp -d)
   SCRIPT="$TEMP_DIR/proof.py"   # or proof.ts / proof.mjs
   OUT="$TEMP_DIR/out.txt"
   ```

   Use the `Write` tool to author the script. Keep it focused — only enough code to surface evidence for the claims, no error handling beyond what is essential.

3. **Run and capture** stdout+stderr together:

   ```bash
   python "$SCRIPT" > "$OUT" 2>&1
   echo "exit: $?"
   ```

4. **On success**, move the raw output into the registry:

   ```bash
   mkdir -p .ll/learning-tests/raw/
   mv "$OUT" ".ll/learning-tests/raw/${SLUG}.txt"
   ```

   `raw_output_path` in the record will be the relative string `".ll/learning-tests/raw/<slug>.txt"`.

5. **On failure** (non-zero exit or no useful output), record the stderr in the raw output anyway — a refuted exploration is still a valuable record. Set the record `status` to `refuted` in Phase 4 if no claims could be proven.

---

## Phase 4: Refine

Diff expected vs actual and emit the registry record.

1. **For each claim**, classify the result:
   - `pass` — the script's output supports the claim
   - `fail` — the script's output contradicts the claim
   - `untested` — the script did not produce evidence for or against this claim (also use for `--assume`-pre-seeded claims that were not exercised)

2. **Determine record status**:
   - `proven` — at least one assertion is `pass`
   - `refuted` — all exercised assertions are `fail` (no passes)
   - `stale` — reserved for `ll-learning-tests mark-stale`; do not set on initial write

3. **Emit the record** with the `Write` tool. The on-disk format (verbatim shape produced by `little_loops.learning_tests.write_record()`):

   ```yaml
   ---
   target: <TARGET verbatim>
   date: '<YYYY-MM-DD today, ISO date>'
   status: proven
   assertions:
   - claim: <claim text>
     result: pass
   - claim: <claim text>
     result: fail
   - claim: <pre-seeded assumed claim>
     result: untested
   raw_output_path: .ll/learning-tests/raw/<slug>.txt
   ---
   ```

   - File body is **empty** — frontmatter fences only, then a single trailing newline.
   - Use single-quoted ISO date (`'2026-05-11'`) to match `yaml.dump` output.
   - `target` is the original free-text string, not the slug.
   - Write path: `.ll/learning-tests/<slug>.md` (the directory was already ensured to exist by the `mkdir -p .ll/learning-tests/raw/` in Phase 3, but call `mkdir -p .ll/learning-tests/` as well if the raw step was skipped).

4. **Verify** with the registry CLI:

   ```bash
   ll-learning-tests check "$TARGET"
   ```

   Expect exit 0 and a JSON dump matching the record just written.

5. **Report results** to the conversation:

   ```
   ✓ Learning test record written: .ll/learning-tests/<slug>.md
     Status: proven | refuted
     Proven: N
     Refuted: M
     Untested (incl. assumed): K
     Raw output: .ll/learning-tests/raw/<slug>.txt
   ```

   List each claim with its result so the user can scan-read the findings without opening the file.

---

## CLI Surface Reminder

`ll-learning-tests` exposes three subcommands only:

| Subcommand | Purpose | Exit |
|---|---|---|
| `check "<target>"` | Print JSON record by target name | 0 if found, 1 if missing |
| `list` | Print JSON array of all records | always 0 |
| `mark-stale "<target>"` | Set `status: stale` on an existing record | 0 |

There is intentionally **no `write` subcommand** — record creation is owned by skills/agents (this one and any future variants) so the prompt context can capture the proof reasoning, not just the result. To persist a new record, use the `Write` tool as described in Phase 4.

## Examples

```bash
# Explore from scratch
/ll:explore-api "Anthropic SDK streaming"

# Pre-seed assumed claims that will not be exercised by the proof script
/ll:explore-api "Claude API tool use" --assume "tools is a list" --assume "stop_reason is tool_use"

# Multi-word target (joined as one string)
/ll:explore-api "Python pathlib"
```

## Acceptance Signals

After running, the following should be true:

- `.ll/learning-tests/<slug>.md` exists and parses as YAML frontmatter
- At least one assertion is `pass` or `fail` (not all `untested`)
- `ll-learning-tests check "$TARGET"` returns exit 0 and the JSON record
- `raw_output_path` points to an existing file with the proof script's captured output
