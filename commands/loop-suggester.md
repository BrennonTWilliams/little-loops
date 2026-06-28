---
description: |
  Analyze user message history to suggest FSM loop configurations automatically. Uses ll-messages output to identify repeated workflows and generate ready-to-use loop YAML. Also supports --from-commands mode to suggest loops from the available command/skill catalog without requiring message history, and --from-sequences mode to suggest loops from ll-logs sequences n-gram output.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow", "create loop from messages", "analyze messages for loops", "ll-messages loop", "suggest automation", "detect patterns for loops", "suggest loops from commands", "loop from catalog", "from-commands", "suggest loops from sequences", "from-sequences", "loop from ll-logs"
argument-hint: "[messages.jsonl|--from-commands|--from-sequences]"
allowed-tools:
  - Read
  - Write
  - Glob
  - Bash(ll-messages:*)
  - Bash(ll-logs:*)
arguments:
  - name: input
    description: Path to JSONL file from ll-messages, or --from-commands to suggest loops from the command/skill catalog (no message history required), or --from-sequences to suggest loops from ll-logs sequences n-gram output
    required: false
---

# Loop Suggester

Analyze user message history from `ll-messages` output to identify repeated workflows and suggest FSM loop configurations. This command bypasses the interactive `/ll:create-loop` wizard by automatically detecting patterns and generating ready-to-use loop YAML.

## Arguments

$ARGUMENTS

- **input** (optional): Path to existing JSONL file from ll-messages
  - If provided, read and analyze that file
  - If omitted, run `ll-messages --include-response-context -n 200 --stdout` to extract recent messages
- **--from-commands** (optional flag): Analyze the command/skill catalog instead of message history
  - Enumerates `skills/*/SKILL.md`, `commands/*.md`, and CLI entry points from `scripts/pyproject.toml`
  - Works on fresh installations with zero message history
  - Cannot be combined with a JSONL file path
- **--from-sequences** (optional flag): Analyze `ll-logs sequences` n-gram output instead of message history
  - Reads repeated command invocation chains from the telemetry log store
  - Maps each chain's tool sequence to a loop paradigm and generates FSM YAML
  - Falls back to the message-history path with a notice if sequences output is empty or unavailable
  - Cannot be combined with a JSONL file path or `--from-commands`

**Mode Selection**: If `--from-sequences` is present in `$ARGUMENTS`, skip to [From-Sequences Mode](#from-sequences-mode). If `--from-commands` is present in `$ARGUMENTS`, skip to [From-Commands Mode](#from-commands-mode). Otherwise, proceed with message history analysis below.

## Process

### Step 1: Load Messages

1. If `$ARGUMENTS` is provided, read the JSONL file at that path
2. If empty, use Bash to run: `ll-messages --include-response-context -n 200 --stdout`
3. Parse each line as JSON, extracting:
   - `content`: The user's message text
   - `timestamp`: When the message was sent
   - `session_id`: Session identifier for grouping
   - `response_metadata.tools_used`: List of tools used in response (critical for pattern detection)
   - `response_metadata.files_modified`: Files that were changed

### Step 2: Build Tool Sequences

For each message with `response_metadata`:

1. Extract the `tools_used` array (e.g., `[{tool: "Bash", count: 2}, {tool: "Edit", count: 1}]`)
2. Create a normalized tool sequence: `["Bash", "Edit"]`
3. Group by session_id to identify within-session patterns
4. Track file types modified to understand domain (Python, JS, etc.)

### Step 3: Detect Loop-Worthy Patterns

Apply these detection rules:

#### Pattern: Check-Fix Cycle (→ Goal Paradigm)

Look for sequences where:
- Same check tool appears before AND after Edit/Write
- Pattern: `Bash(check) → Edit → Bash(check)`
- Common checks: tools configured via `{{config.project.*}}` (e.g., `pytest`, `mypy`, `ruff`, `eslint`, `tsc`)

**Confidence boost**: +0.2 if pattern appears in 5+ messages

#### Pattern: Multi-Constraint Sequence (→ Invariants Paradigm)

Look for sequences where:
- Multiple different checks run in succession
- All checks must pass before proceeding
- Pattern: `Bash(check1) → Bash(check2) → Bash(check3)`

**Indicators**:
- Different check tools in same session
- Consistent ordering across sessions

#### Pattern: Metric Tracking (→ Convergence Paradigm)

Look for:
- Numeric output comparison (test count, coverage %, error count)
- Repeated measurement with changes in between
- User messages mentioning "reduce", "increase", "target", "goal"

**Note**: This pattern is harder to detect from tool usage alone; rely on message content keywords.

#### Pattern: Step Sequence (→ Imperative Paradigm)

Look for:
- Consistent ordered steps without branching
- Pattern: `tool1 → tool2 → tool3 → check → repeat`
- Multi-stage builds or deployments

### Step 4: Map Patterns to Paradigms

| Pattern Type | Paradigm | Min Frequency | Confidence Base |
|--------------|----------|---------------|-----------------|
| Single check-fix-verify cycle | `goal` | 3 | 0.70 |
| Multiple sequential constraints | `invariants` | 3 | 0.65 |
| Metric improvement tracking | `convergence` | 2 | 0.55 |
| Ordered step sequence | `imperative` | 3 | 0.60 |

**Confidence adjustments**:
- +0.15 if pattern appears in 5+ messages
- +0.10 if pattern spans multiple sessions
- +0.05 if tool commands are identical (not just tool type)
- -0.10 if pattern has high variance in tool count

### Step 5: Generate FSM YAML

For each detected pattern, generate the appropriate FSM YAML configuration using the templates below.

#### Fix Until Clean (Check-Fix Cycle)

Use when a single condition must be satisfied through iterative check-fix rounds.

```yaml
name: "{name}"
initial: evaluate
max_iterations: 10
states:
  evaluate:
    action: "{command that returns exit 0 on success, non-zero on failure}"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "The check command failed with the above output. Analyze the errors and fix them."
    action_type: prompt
    next: evaluate
  done:
    terminal: true
```

**Detected from**: `Bash(check) → Edit → Bash(check)` sequences where the same check tool appears before and after edits.

#### Maintain Constraints (Multi-Constraint)

Use when multiple independent constraints must all pass simultaneously.

```yaml
name: "{name}"
initial: check_{check_1_name}
max_iterations: 15
states:
  check_{check_1_name}:
    action: "{command_1}"
    on_yes: check_{check_2_name}
    on_no: fix_{check_1_name}
  fix_{check_1_name}:
    action: "One or more checks failed. Review and fix the underlying issues without breaking passing checks."
    action_type: prompt
    next: check_{check_1_name}
  check_{check_2_name}:
    action: "{command_2}"
    on_yes: check_{check_3_name}   # or all_valid if last
    on_no: fix_{check_2_name}
  fix_{check_2_name}:
    action: "Fix the failing check."
    action_type: prompt
    next: check_{check_2_name}
  # ... repeat for each constraint
  all_valid:
    terminal: true
```

**Detected from**: Multiple different check tools running in succession within the same session, with consistent ordering across sessions.

#### Drive a Metric (Metric Tracking)

Use when a numeric metric must reach a target value through iterative improvement.

```yaml
name: "{name}"
initial: measure
max_iterations: 20
states:
  measure:
    action: "{command that outputs a numeric value}"
    evaluate:
      type: convergence
      toward: {target_value}
      tolerance: {acceptable_delta}
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "The current metric has not reached the target. Analyze the codebase and make changes to improve the metric."
    action_type: prompt
    next: measure
  done:
    terminal: true
```

**Detected from**: Repeated numeric output comparisons with changes in between.

#### Run a Sequence (Step Sequence)

Use when a fixed sequence of steps must execute in order, optionally repeating.

```yaml
name: "{name}"
initial: step_0
max_iterations: 5
states:
  step_0:
    action: "{instruction for step 1}"
    action_type: prompt
    next: step_1
  step_1:
    action: "{instruction for step 2}"
    action_type: prompt
    next: step_2
  step_2:
    action: "{instruction for step 3}"
    action_type: prompt
    next: check_done
  check_done:
    action: "{optional final verification command}"
    on_yes: done
    on_no: step_0
  done:
    terminal: true
```

**Detected from**: Consistent ordered steps without branching.

#### Pattern-to-Loop-Type Mapping

| Signal | Loop type | Why |
|--------|-----------|-----|
| Single pass/fail check repeated | **Fix until clean** | One exit condition, simple cycle |
| Multiple independent checks must all pass | **Maintain constraints** | Fixing one check may break another |
| Numeric output being optimized | **Drive a metric** | Needs target tracking and direction |
| Ordered steps, no branching | **Run a sequence** | Sequence matters, not conditions |
| Single check + metric output | **Fix until clean** (not drive-metric) | If pass/fail is sufficient, prefer simpler loop |
| Two checks, one depends on other | **Fix until clean** with combined check | Avoid maintain-constraints if checks aren't independent |

**General rule**: prefer simpler loop types. Fix until clean > Maintain constraints > Drive a metric > Run a sequence when multiple fit.

### Step 6: Calculate Confidence Score

```
confidence = base_confidence
           + (frequency_bonus if count >= 5)
           + (session_bonus if multi_session)
           + (consistency_bonus if identical_commands)
           - (variance_penalty if high_variance)

Clamp to range [0.0, 1.0]
```

### Step 7: Generate Output

Write suggestions to `.ll/loop-suggestions/suggestions-{timestamp}.yaml` using this output schema:

```yaml
analysis_metadata:
  source_file: "[path to JSONL or 'live extraction']"
  messages_analyzed: [count]
  analysis_timestamp: "[ISO 8601]"
  skill: loop-suggester
  version: "1.0"

summary:
  total_suggestions: [count]
  by_loop_type:
    fix_until_clean: [count]
    maintain_constraints: [count]
    drive_metric: [count]
    run_sequence: [count]

suggestions:
  - id: "loop-001"
    name: "[suggested loop name]"
    loop_type: "[fix_until_clean|maintain_constraints|drive_metric|run_sequence]"
    confidence: [0.0-1.0]
    rationale: "[2-3 sentences explaining detection]"
    yaml_config: |
      [Complete FSM YAML]
    usage_instructions: |
      1. Save to {{config.loops.loops_dir}}/[name].yaml
      2. Run: ll-loop validate [name]
      3. Test: ll-loop test [name]
      4. Execute: ll-loop run [name]
```

## From-Sequences Mode

When `--from-sequences` is present in `$ARGUMENTS`, perform n-gram analysis on `ll-logs sequences` output instead of raw message history. This mode uses the telemetry primitive shipped in ENH-1919 as a real input source.

### Step FS-1: Load Sequences Data

**Input priority:**
1. If `--from-sequences <path>` — read the JSONL file at the given path (output of a prior `ll-logs sequences --json` run)
2. If `--from-sequences` (no path argument) — run: `ll-logs sequences --json --min-count 2`

**Graceful fallback**: If the command errors, returns a non-zero exit code, or returns an empty array `[]`:
- Log a notice: "⚠ No sequences data found. Falling back to message-history analysis."
- Continue with the standard message-history flow (Step 1 above) instead of stopping.

**Parsed schema** per entry (matches `ChainResult.to_dict()` in `scripts/little_loops/cli/logs.py`):
```json
{"chain": ["ll-scan-codebase", "ll-manage-issue"], "count": 5, "edges": [{"from": "ll-scan-codebase", "to": "ll-manage-issue", "freq": 0.8, "pmi": 1.23, "lift": 3.4}], "pmi": 1.23, "lift": 3.4}
```

Each entry must have:
- `chain`: ordered list of tool/command names (the n-gram)
- `count`: number of times this chain was observed
- `edges`: list of `{from, to, freq}` transition objects

Each entry may also have (when unigram corpus data is available):
- `pmi`: minimum pointwise mutual information across edges (log-scale; positive = above frequency prior)
- `lift`: minimum lift across edges — `P(b|a)/P(b)`; values < `LIFT_THRESHOLD` (1.0) indicate a
  frequency-prior-equivalent pair that should not earn confidence bonuses

Record `chains_analyzed` = total chains examined before filtering.

### Step FS-2: Filter Chains

Apply these filters to keep only actionable candidates:
- Minimum frequency: `count >= 2` (chains below this are too infrequent to warrant automation)
- Minimum chain length: `len(chain) >= 2` (single-item chains have no sequence to model)

If all chains are filtered out, apply the graceful fallback (see Step FS-1).

### Step FS-3: Map Chains to Paradigms

For each filtered chain, detect the paradigm using chain structure:

| Chain characteristic | Paradigm | Rationale |
|---|---|---|
| Contains a known check command (pytest, ruff, mypy, ll-check-code, ll-run-tests) | `fix_until_clean` | Check-fix cycle — iterative until clean |
| Sequential without checks, all steps distinct | `run_sequence` | Ordered workflow pipeline |
| Contains both check and numeric-output commands | `drive_metric` | Numeric tracking toward target |
| Three or more distinct tools with varied edge frequencies | `maintain_constraints` | Multiple independent constraints |

**Paradigm priority**: `fix_until_clean` > `maintain_constraints` > `drive_metric` > `run_sequence` when multiple fit — prefer simpler types.

**State mapping**:
- Each item in `chain` becomes a state name (kebab-cased, with `ll-` prefix stripped if present)
- `edges[].freq` feeds the consistency_bonus in the confidence formula
- For `fix_until_clean`, the last check-command state gets `on_yes: done` / `on_no: fix`

**Confidence calculation** (same formula as message-history mode, with lift-threshold guard):

```
LIFT_THRESHOLD = 1.0  # pairs at or below the frequency prior earn no bonuses

IF "lift" field is present AND lift < LIFT_THRESHOLD:
  # Frequency-prior-equivalent: the co-occurrence is no more surprising than
  # random chance predicts.  Mark it and cap at base confidence.
  frequency_prior_equivalent = true
  confidence = base_confidence

ELSE:
  confidence = base_confidence (from paradigm table in Step 4)
             + frequency_bonus  (+0.15 if count >= 5)
             + consistency_bonus (+0.05 if max(edges[].freq) > 0.80)
             - variance_penalty  (-0.10 if stddev(edges[].freq) > 0.30)
  Clamp to [0.0, 1.0]
```

### Step FS-4: Generate FSM YAML Proposals

For each mapped chain, generate a complete FSM YAML using the templates from Step 5 (Generate FSM YAML) of the message-history mode as structural blueprints.

**Naming convention**: kebab-join of chain items, truncated to 5 terms maximum.

**Required fields per proposal**:
```
id: "loop-001"  # sequential
name: "<kebab-chain-name>"
loop_type: "<fix_until_clean|maintain_constraints|drive_metric|run_sequence>"
confidence: <0.0-1.0>
rationale: "<2-3 sentences: the chain, its frequency, why the paradigm fits>"
yaml_config: |
  <complete valid FSM YAML>
usage_instructions: |
  1. Save to {{config.loops.loops_dir}}/<name>.yaml
  2. Run: ll-loop validate <name>
  3. Test: ll-loop test <name>
  4. Execute: ll-loop run <name>
```

### Step FS-5: Write Output and Present

Ensure the output directory exists: `mkdir -p .ll/loop-suggestions/`.

Write suggestions to `.ll/loop-suggestions/suggestions-{timestamp}.yaml` using this schema (with `source: "sequences"` to distinguish from `"commands-catalog"` and message-history mode):

```yaml
analysis_metadata:
  source: "sequences"
  sequences_file: "[path or 'll-logs sequences --json --min-count 2']"
  chains_analyzed: [count before filtering]
  analysis_timestamp: "[ISO 8601]"
  skill: loop-suggester
  version: "1.0"

summary:
  total_suggestions: [count]
  by_loop_type:
    fix_until_clean: [count]
    maintain_constraints: [count]
    drive_metric: [count]
    run_sequence: [count]

suggestions:
  - id: "loop-001"
    name: "[kebab-chain-name]"
    loop_type: "[paradigm]"
    confidence: [0.0-1.0]
    rationale: "[2-3 sentences]"
    yaml_config: |
      [Complete FSM YAML]
    usage_instructions: |
      1. Save to {{config.loops.loops_dir}}/[name].yaml
      2. Run: ll-loop validate [name]
      3. Test: ll-loop test [name]
      4. Execute: ll-loop run [name]
```

After writing, display a summary table to the user identical in format to the From-Commands Mode Step FC-5 table. Do NOT automatically write to `.loops/` — present the suggestions and let the user decide which to activate.

## From-Commands Mode

When `--from-commands` is present in `$ARGUMENTS`, perform catalog analysis instead of message history analysis. This mode works on fresh installations with zero Claude Code message history.

### Step FC-1: Enumerate Catalog

Collect three source lists in parallel:

**1. Skills** — Use `Glob` to find all `skills/*/SKILL.md` files. For each file, read its YAML frontmatter and extract:
- `name`: the directory name (e.g., `skills/manage-issue/SKILL.md` → `manage-issue`)
- `description`: full value, including any "Trigger keywords:" lines
- `argument-hint`: short usage hint (if present)
- `type`: `"skill"`

**2. Commands** — Use `Glob` to find all `commands/*.md` files (exclude `commands/README.md` if present). For each file, read its YAML frontmatter and extract:
- `name`: filename without `.md` extension
- `description`: full value
- `argument-hint`: short usage hint (if present)
- `type`: `"command"`

**3. CLI entry points** — Read `scripts/pyproject.toml`. Parse the `[project.scripts]` section to extract all `ll-*` entries as:
- `name`: the CLI command name (e.g., `ll-loop`, `ll-sprint`)
- `description`: derive from the entry-point module name and cross-reference with `commands/*.md` or `CLAUDE.md` if available
- `type`: `"cli"`

Deduplicate: if a skill and command have the same effective name, keep the skill entry (more descriptive frontmatter).

Record total counts: `skills_enumerated`, `commands_enumerated`, `cli_enumerated`.

### Step FC-2: Group by Workflow Theme

Map each catalog entry to one of five workflow themes based on keyword matching in its `name` and `description`:

| Theme | Keyword signals | Representative entries |
|---|---|---|
| `issue-management` | issue, scan, capture, refine, prioritize, align, format, verify, sprint, manage, ready, size, confidence, dependency | scan-codebase, manage-issue, create-sprint, prioritize-issues |
| `code-quality` | check, lint, test, format, type, audit, dead, build, quality | check-code, run-tests, find-dead-code, audit-docs |
| `git-release` | commit, pr, push, release, sync, worktree, branch, tag | commit, open-pr, manage-release, sync-issues |
| `loops-automation` | loop, workflow, automate, suggest, create-loop, debug-loop-run, ll-loop, ll-workflows, ll-sprint, distill | create-loop, review-loop, loop-suggester, ll-loop, distill-traces |
| `analysis-meta` | analyze, history, product, audit-claude, message, parallel, deps, issues, ll-auto, ll-parallel | analyze-history, product-analyzer, ll-messages |

Each entry belongs to exactly one theme; if ambiguous, assign to the first matching theme in the table order above.

### Step FC-3: Generate FSM Proposals

Generate **3–5 FSM loop proposals** — at least one from `issue-management`, one from `code-quality`, and one from either `git-release` or `loops-automation`. Each proposal must:

- Have **3–7 states** referencing real command/skill names from the enumerated catalog as `action` values
- Use `action_type: slash_command` for skills and commands (prefixed with `/ll:`), `action_type: prompt` for LLM reasoning steps, `action_type: shell` for CLI tools
- Conform to the FSM schema: required fields `name`, `initial`, `states`; optional `max_iterations`, `timeout`, `on_handoff`
- Map to one of the four loop paradigms: `fix_until_clean`, `maintain_constraints`, `drive_metric`, `run_sequence`

Use the YAML templates from Step 5 (Generate FSM YAML) of the message history mode as structural blueprints. Choose the paradigm that best fits the theme's natural workflow:

| Theme | Natural paradigm | Rationale |
|---|---|---|
| `issue-management` | `run_sequence` | Issues flow through fixed stages: scan → refine → implement → verify |
| `code-quality` | `fix_until_clean` | Iterative: check → fix until all checks pass |
| `git-release` | `run_sequence` | Ordered steps: check → commit → push → release |
| `loops-automation` | `maintain_constraints` | Multiple loop types must each be valid |
| `analysis-meta` | `run_sequence` | Sequential analysis pipeline |

**Naming convention**: `<theme-short>-<paradigm-short>` e.g. `issue-lifecycle`, `code-quality-fix`, `release-prep`.

**Required fields per proposal**:
```
id: "loop-001"  # sequential
name: "<descriptive-kebab-name>"
loop_type: "<fix_until_clean|maintain_constraints|drive_metric|run_sequence>"
theme: "<theme-name>"
confidence: <0.70–0.90>  # catalog-sourced proposals start at 0.75 base
rationale: "<2-3 sentences explaining why this sequence is useful>"
yaml_config: |
  <complete valid FSM YAML>
usage_instructions: |
  1. Save to {{config.loops.loops_dir}}/<name>.yaml
  2. Run: ll-loop validate <name>
  3. Test: ll-loop test <name>
  4. Execute: ll-loop run <name>
```

**Confidence scoring for catalog mode** (base 0.75):
- +0.10 if all referenced commands/skills exist in the enumerated catalog
- +0.05 if the theme has 5+ catalog entries (rich domain coverage)
- -0.10 if any referenced command/skill is not found in the catalog
- Clamp to [0.0, 1.0]

### Step FC-4: Write Output

Write suggestions to `.ll/loop-suggestions/suggestions-{timestamp}.yaml` using this schema (same as message history mode, with `source: "commands-catalog"` to distinguish):

```yaml
analysis_metadata:
  source: "commands-catalog"
  source_file: "skills/*/SKILL.md + commands/*.md + scripts/pyproject.toml"
  skills_enumerated: [count]
  commands_enumerated: [count]
  cli_enumerated: [count]
  analysis_timestamp: "[ISO 8601]"
  skill: loop-suggester
  version: "1.0"

summary:
  total_suggestions: [count]
  by_loop_type:
    fix_until_clean: [count]
    maintain_constraints: [count]
    drive_metric: [count]
    run_sequence: [count]
  by_theme:
    issue-management: [count]
    code-quality: [count]
    git-release: [count]
    loops-automation: [count]
    analysis-meta: [count]

suggestions:
  - id: "loop-001"
    name: "[loop name]"
    loop_type: "[fix_until_clean|maintain_constraints|drive_metric|run_sequence]"
    theme: "[theme name]"
    confidence: [0.0-1.0]
    rationale: "[2-3 sentences]"
    yaml_config: |
      [Complete FSM YAML]
    usage_instructions: |
      1. Save to {{config.loops.loops_dir}}/[name].yaml
      2. Run: ll-loop validate [name]
      3. Test: ll-loop test [name]
      4. Execute: ll-loop run [name]
```

Ensure the output directory exists: `mkdir -p .ll/loop-suggestions/`.

### Step FC-5: Present Proposals

After writing the output file, display a summary table to the user:

```
Found [N] loop proposals from [S] skills, [C] commands, [L] CLI tools:

#  Name                    Theme              Paradigm           Confidence
1  issue-lifecycle         issue-management   run_sequence       0.85
2  code-quality-fix        code-quality       fix_until_clean    0.80
3  release-prep            git-release        run_sequence       0.75

Full proposals written to: .ll/loop-suggestions/suggestions-{timestamp}.yaml

To use a proposal:
  1. Copy the yaml_config to .loops/<name>.yaml
  2. ll-loop validate <name>
  3. ll-loop run <name>
```

Do NOT automatically write to `.loops/` — present the suggestions and let the user decide which (if any) to activate.

## Guidelines

### When to Suggest Loops

- **DO** suggest when pattern appears 3+ times
- **DO** suggest when pattern spans multiple sessions (indicates habitual workflow)
- **DO** prefer simpler loop types (fix-until-clean over maintain-constraints when both fit)
- **DO** include realistic confidence scores (rarely above 0.9)

### When NOT to Suggest Loops

- **DON'T** suggest for patterns appearing fewer than 3 times
- **DON'T** suggest for highly variable tool sequences
- **DON'T** suggest for one-time complex tasks
- **DON'T** suggest if no clear exit condition exists

## Comparison with /ll:create-loop

| Aspect | /ll:create-loop | /ll:loop-suggester |
|--------|-----------------|-------------------|
| Input | Interactive questions | Message history analysis |
| Output | Single loop | Multiple suggestions |
| Loop type selection | User chooses | Auto-detected |
| Best for | Known automation needs | Discovering automation opportunities |

Use `/ll:create-loop` when you know what loop you want. Use `/ll:loop-suggester` when you want to discover what loops might help based on your actual usage patterns.

## Examples

```bash
# Analyze recent messages (extracts last 200 with response context)
/ll:loop-suggester

# Suggest loops from command/skill catalog (no message history needed)
/ll:loop-suggester --from-commands

# Suggest loops from ll-logs sequences n-gram output (telemetry-driven)
/ll:loop-suggester --from-sequences

# Suggest loops from a saved sequences JSON file
/ll:loop-suggester --from-sequences .ll/sequences-2026-06-13.json

# Analyze existing JSONL file
/ll:loop-suggester messages.jsonl

# Analyze custom extraction
/ll:loop-suggester ~/.claude/exports/session-analysis.jsonl
```

## See Also

- Create loops interactively: `/ll:create-loop`
- Workflow analysis: `/ll:analyze-workflows`
- Suggest loops from catalog: `/ll:loop-suggester --from-commands`
- Suggest loops from telemetry: `/ll:loop-suggester --from-sequences`
- Extract sequences: `ll-logs sequences --json`
