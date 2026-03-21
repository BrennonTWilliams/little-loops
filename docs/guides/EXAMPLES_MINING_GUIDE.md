# Co-evolutionary Examples Mining Guide

Static `examples.json` files have a natural expiry date. When `apo-textgrad` is first set up, examples are written for the prompt's current capability — but as the prompt improves, those examples become trivially easy, `PASS_RATE` saturates, the gradient signal disappears, and optimization stalls at a local optimum. Meanwhile, the skill itself evolves: new conventions, new file layouts, new issue formats. The corpus quietly goes stale.

`examples-miner` breaks this pattern by coupling the corpus to the project's own history. Every completed issue with a session log is an implicit human approval — the agent's output was good enough that a human accepted it and the issue closed. `examples-miner` harvests these real labeled invocations, quality-gates them through a three-layer judge, calibrates difficulty to an informative 40–80% band, runs `apo-textgrad` as an inner sub-loop to extract a gradient signal, and synthesizes adversarial examples targeting exactly the failure pattern the optimizer found. Repeat, and difficulty always leads the prompt's current capability.

---

## Table of Contents

- [The Problem with Static Examples](#the-problem-with-static-examples)
- [What examples-miner Does](#what-examples-miner-does)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [How the Pipeline Works](#how-the-pipeline-works)
  - [Stage 1: Harvest](#stage-1-harvest)
  - [Stage 2: Judge — Three-Layer Quality Stack](#stage-2-judge-three-layer-quality-stack)
  - [Stage 3: Calibrate](#stage-3-calibrate)
  - [Stage 4: Write + Optimize](#stage-4-write-optimize)
  - [Stage 5: Synthesize — Adversarial Examples](#stage-5-synthesize-adversarial-examples)
  - [Stage 6: Screen → Score → Merge](#stage-6-screen-score-merge)
  - [Stage 7: Diversify + Publish](#stage-7-diversify-publish)
- [The examples.json Schema](#the-examplesjson-schema)
- [Configuration Reference](#configuration-reference)
- [File I/O Reference](#file-io-reference)
- [Configuring for a Different Skill](#configuring-for-a-different-skill)
- [Incremental Harvesting](#incremental-harvesting)
- [The Oracle Sub-loop (v2 Upgrade)](#the-oracle-sub-loop-v2-upgrade)
- [Monitoring a Run](#monitoring-a-run)
- [Tips](#tips)
- [Troubleshooting](#troubleshooting)
- [See Also](#see-also)

---

## The Problem with Static Examples

`apo-textgrad` works by testing the current prompt against a batch of `(input, expected)` pairs, counting how many pass, and computing a text gradient from the failures. This gradient drives the next prompt revision. The mechanism is powerful — but it depends entirely on the examples being informative.

When examples are hand-crafted at the time the skill is written:

1. **The prompt improves** — iterations drive the pass rate up toward 100%.
2. **The examples become trivially easy** — the prompt now handles them without effort.
3. **`PASS_RATE` saturates** → the loop emits `CONVERGED` and stops.
4. **The prompt still fails on harder real inputs** that were never in the corpus — but the optimizer doesn't know this.

The result is a prompt optimized for the hand-crafted corpus, not for the full distribution of real invocations. The corpus is also frozen in time: as the skill's conventions evolve, examples reference old file paths, old issue formats, old tool patterns. The optimizer silently reinforces stale behavior.

`examples-miner` solves both problems. It sources examples from the project's completed issue history — real invocations that real humans accepted. It continuously recalibrates difficulty to keep examples in the informative 40–80% pass-rate band. And after each optimizer run, it synthesizes new adversarial examples that specifically target the current gradient's failure pattern, so the corpus always stays ahead of the prompt's current capability.

---

## What examples-miner Does

Two loops coupled together:

```
┌── OUTER LOOP: examples-miner ───────────────────────────────────────────┐
│                                                                          │
│  harvest ──→ judge ──→ calibrate ──→ write_examples                     │
│                                              │                          │
│                                        run_optimizer                    │
│                                    (inner: apo-textgrad)                │
│                                        │         │                      │
│                                    SUCCESS    FAILURE                   │
│                                        │         │                      │
│                                     synthesize   │                      │
│                                        │         │                      │
│                           screen_adversarial     │                      │
│                                        │         │                      │
│                            score_adversarial     │                      │
│                                        │         │                      │
│                                      merge       │                      │
│                                        │         │                      │
│                                     diversify ←──┘                      │
│                                        │                                │
│                                     publish ──→ done                    │
└──────────────────────────────────────────────────────────────────────────┘
```

The **outer loop** mines, calibrates, and publishes the corpus. The **inner loop** (`apo-textgrad`) runs as a child FSM via sub-loop chaining (`context_passthrough: true`), inheriting the outer loop's `prompt_file` and `examples_file`. After the inner loop completes, the outer loop reads its gradient signal from `${captured.run_optimizer.gradient.output}` and uses it to synthesize adversarial examples that target the exact failure pattern the optimizer found.

---

## When to Use

| Situation | Use examples-miner? |
|-----------|---------------------|
| `apo-textgrad` `PASS_RATE` plateaus ≥90% but prompt still fails on real invocations | Yes — corpus is stale or too easy |
| `examples.json` was hand-crafted months ago and the skill has evolved | Yes — conventions have drifted |
| No `examples.json` exists yet and you want one from real project history | Yes — first-run builds from scratch |
| You have a brand-new skill with no completed issues yet | No — harvest will be empty; write initial examples manually, then use the miner |
| You want to run `apo-textgrad` against a specific curated test set | No — manage that corpus manually |

---

## Quick Start

```bash
# 1. Check that session data exists for the skill
ll-messages --skill capture-issue --examples-format --stdout | head -3

# 2. First run: mine all history, optimize the prompt, publish examples.json
ll-loop run examples-miner \
  --context skill_name=capture-issue \
  --context prompt_file=skills/capture-issue/SKILL.md

# 3. Verify the output
python3 -c "
import json
with open('examples.json') as f:
    data = json.load(f)
print(f'{len(data)} examples')
print('Sources:', set(e.get(\"source\") for e in data))
print('Difficulty range:', min(e.get(\"difficulty_score\", 0) for e in data),
      '–', max(e.get(\"difficulty_score\", 0) for e in data))
"
```

On the first run, no `corpus.last_harvested` sentinel exists so all session history is harvested. Subsequent runs are incremental — only sessions newer than the sentinel are re-processed.

---

## How the Pipeline Works

### Stage 1: Harvest

```
harvest (shell, 120s)
  runs: ll-messages --skill <skill_name> --examples-format --context-window 3 [--since <sentinel>] --stdout
  produces: harvested_examples (JSON lines)
```

The `harvest` state runs `ll-messages` with `--examples-format` to extract `(input, expected)` pairs from Claude Code session logs. Each record is a JSON object on its own line:

```json
{
  "type": "example",
  "skill": "capture-issue",
  "input": "<N preceding user messages concatenated>",
  "output": "{\"tools_used\": [\"Read\", \"Write\"], \"files_modified\": [\".issues/features/P3-FEAT-849-...\"], \"completion_status\": \"success\"}",
  "session_id": "361c2c3a-bd3c-417b-9d69-cfd541e136fc",
  "timestamp": "2026-03-21T22:21:36",
  "context_window": 3
}
```

**Important**: the `output` field is not free text. It is a JSON-serialized `ResponseMetadata` object recording what tools the agent used and what files it changed — not the raw assistant response. The oracle judge evaluates tool choices and file changes, not prose quality.

On the first run, no sentinel file exists and all sessions are harvested. On subsequent runs, `--since $(cat corpus.last_harvested)` limits the query to sessions added after the last publish.

---

### Stage 2: Judge — Three-Layer Quality Stack

```
judge (prompt, 300s)
  reads: harvested_examples
  produces: judge_scores (JSON array with per-example metadata)
```

Every harvested candidate passes through three sequential quality layers. Failing any layer discards the candidate.

**Layer 1 — Code persistence** (objective, uses Bash tool):

For each candidate, the judge checks `files_modified` from the `output` JSON against the current repository:

```bash
git log --follow --oneline <file> 2>/dev/null | wc -l
```

- `persistence_score` = fraction of `files_modified` still tracked in HEAD
- `persistence_age` = average commit count for still-present files

Candidates where `persistence_score = 0` (all modified files are absent from HEAD) are discarded immediately. If the agent created a file that was later deleted, the output was likely incorrect or superseded — not worth training on.

**Layer 2 — Revision distance** (heuristic, uses Bash tool):

For each surviving candidate, the judge estimates how much the linked issue was revised after the invocation:

- 1–2 session log entries in `## Session Log` → `revision_distance ≈ 0.1` (output accepted quickly)
- 3–4 entries → `revision_distance ≈ 0.4`
- 5+ entries → `revision_distance ≈ 0.7` (heavily revised before acceptance)

Low distance signals the output was accepted nearly as-is — high training utility. High distance means the output needed substantial correction — lower confidence.

**Layer 3 — Oracle rubric** (LLM scoring):

For candidates that clear layers 1–2, the judge scores the `output` JSON against skill-specific criteria (0–100 pts):

- `tools_used` quality: were appropriate tools used for this skill? (0–33 pts)
- `files_modified` quality: are the file paths realistic and relevant? (0–33 pts)
- `completion_status` validity: is `"success"` the correct status for an accepted output? (0–34 pts)

**Deduplication**: when multiple candidates exist for the same issue (same invocation context, multiple refinement passes), only the highest-ranked is kept. The ranking metric is:

```
downstream_stability = persistence_score × persistence_age × (1 − revision_distance)
```

The surviving candidates are emitted as a JSON array with all computed metadata fields.

---

### Stage 3: Calibrate

```
calibrate (prompt, 120s)
  reads: judge_scores, corpus_state_file (optional)
  produces: calibrated_corpus (JSON array, overwrites on re-runs)
```

The calibrate state assigns a `difficulty_score` (0–100) to each surviving candidate and applies the difficulty band filter:

| Score range | Classification | Action |
|-------------|----------------|--------|
| 0–39 | Trivially easy | Excluded — won't produce gradient signal |
| 40–80 | Informatively challenging | **Included** |
| 81–100 | Noise-level hard | Excluded — will always fail, wasting LLM calls |

If `corpus_state_file` (default: `corpus.json`) exists, calibrate loads it, decays each existing entry's `freshness_weight` by ×0.9, and merges with today's included set (deduplicating by input text). This preserves the accumulated corpus across runs while progressively down-weighting stale examples.

The output is a JSON array capturing all metadata. The final line is a sentinel: `CALIBRATED_COUNT=N`.

---

### Stage 4: Write + Optimize

```
write_examples (prompt, 60s)
  reads: calibrated_corpus
  writes: examples_file to disk
  produces: write_examples_result

run_optimizer (sub-loop: apo-textgrad, context_passthrough: true)
  reads: examples_file (from disk), prompt_file (from disk)
  on_success → synthesize
  on_failure → diversify
```

`apo-textgrad` reads `examples_file` from disk — it cannot receive the corpus via FSM captures. The `write_examples` state handles this by writing the calibrated corpus to `examples_file` before the optimizer starts. This is the intermediate write; `publish` performs the final write at the end.

`run_optimizer` invokes `apo-textgrad` as a child FSM. With `context_passthrough: true`, the child inherits the parent's `prompt_file`, `examples_file`, and other context variables. The child runs to completion independently (up to its own `max_iterations: 20`), then routes the parent:

- **SUCCESS** (child reached its `done` terminal state): gradient signal is available in `${captured.run_optimizer.gradient.output}` → proceed to `synthesize`
- **FAILURE** (child hit `max_iterations` or timed out): no gradient available → skip adversarial synthesis, go directly to `diversify`

---

### Stage 5: Synthesize — Adversarial Examples

```
synthesize (prompt, 300s)
  reads: run_optimizer.gradient.output, calibrated_corpus
  produces: adversarial_candidates (JSON array)
```

If the optimizer produced a gradient (not `CONVERGED`), the synthesize state uses it to generate adversarial examples. The gradient includes:

```
FAILURE_PATTERN: <common theme across all failures>
ROOT_CAUSE: <what is wrong in the current prompt>
GRADIENT: <precise instruction for how to change the prompt>
```

The `FAILURE_PATTERN` is matched to one of five perturbation types:

| Perturbation type | What it does | When to use |
|-------------------|--------------|-------------|
| `complexity_injection` | Adds a second symptom that may or may not belong in the same issue | Prompt fails to exercise scope boundary judgment |
| `ambiguity_injection` | Strips specific file/function names, forcing discovery rather than copying | Prompt over-fits to copying literal references |
| `domain_shift` | Reproduces the same failure pattern in a different subsystem | Prompt passes in training domain but fails in others |
| `priority_boundary` | Edge case sitting between two adjacent priority levels | Prompt misclassifies borderline priority cases |
| `type_confusion` | Description that looks like FEAT but is BUG (or vice versa) | Prompt mis-classifies issue types |

Seeds are selected as the up to 5 examples nearest the 80% difficulty boundary (highest `difficulty_score` ≤ 80) — the region with the highest information density for perturbation.

**Critical constraint**: only the seed's INPUT is perturbed. The original expected output is never reused. A fresh expected output is generated for each perturbed input — this prevents ground-truth corruption where the expected output no longer matches the perturbed input.

---

### Stage 6: Screen → Score → Merge

```
screen_adversarial (prompt, 120s)
  reads: adversarial_candidates
  produces: screened_adversarial

score_adversarial (prompt, 300s)
  reads: screened_adversarial, calibrated_corpus
  produces: validated_adversarial

merge (prompt, 60s)
  reads: calibrated_corpus, validated_adversarial
  produces: calibrated_corpus (overwritten — now contains both harvested + adversarial)
```

**Screen**: mechanical quality checks. Discards candidates with missing required fields, non-JSON `expected` values, empty inputs, or `perturbation_type` values outside the five-type taxonomy. File path plausibility is a soft check (flags but does not discard).

**Score**: oracle rubric applied to screened candidates:
- Perturbation coherence: is the perturbation type correctly applied? (0–34 pts)
- Expected output quality: does the fresh expected output correctly reflect what the skill should produce? (0–33 pts)
- Adversarial value: does this example target a real weakness from the failure cluster? (0–33 pts)

Only candidates in the 40–80 difficulty band are accepted. The adversarial cap is enforced here: `source: adversarial` examples must stay ≤ 30% of the final corpus size. If accepted candidates would exceed the cap, the lowest-scoring ones are trimmed first.

**Merge**: concatenates the calibrated harvested corpus with the validated adversarial examples. Overwrites `calibrated_corpus` so the rest of the pipeline sees the combined set. Each example retains its `source` field (`"harvested"` or `"adversarial"`) as provenance.

---

### Stage 7: Diversify + Publish

```
diversify (prompt, 120s)
  reads: calibrated_corpus (merged)
  produces: calibrated_corpus (overwritten — final diversified version)

publish (prompt, 60s)
  reads: calibrated_corpus (final)
  writes: examples_file, corpus.last_harvested
  produces: publish_result
```

**Diversify**: enforces per-axis coverage minimums when the corpus has ≥ 10 examples:
- At least 2 examples per represented issue type (BUG / FEAT / ENH)
- At least 1 example per represented priority band (P0–P5)
- Adversarial examples ≤ 30% of corpus (trim lowest `oracle_score` first)

Sub-sampling removes the easiest examples (lowest `difficulty_score`) from over-represented groups. If coverage targets are already met, the corpus passes through unchanged. The final line is a sentinel: `FINAL_COUNT=N`.

**Publish**: writes the final corpus to `examples_file` (overwriting the intermediate write from `write_examples`) and updates the harvest sentinel:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ > corpus.last_harvested
```

The sentinel records the UTC timestamp of this publish. The next run's `harvest` state reads it to limit `ll-messages` to new sessions only.

---

## The examples.json Schema

Each object in the published `examples.json` array has the following fields:

```json
{
  "input": "User message history preceding the skill invocation (N messages concatenated)",
  "expected": "{\"tools_used\": [\"Read\", \"Write\"], \"files_modified\": [\".issues/features/P3-FEAT-849-...\"], \"completion_status\": \"success\"}",
  "source": "harvested",
  "difficulty_score": 62,
  "failure_cluster": null,
  "freshness_weight": 0.9,
  "persistence_score": 1.0,
  "persistence_age": 14,
  "revision_distance": 0.1,
  "oracle_score": 87
}
```

| Field | Type | Description |
|-------|------|-------------|
| `input` | string | Concatenated preceding user messages (context window) |
| `expected` | string | JSON-serialized `ResponseMetadata` — NOT free text |
| `source` | `"harvested"` \| `"adversarial"` | Provenance |
| `difficulty_score` | 0–100 | Estimated pass-rate difficulty; 40–80 = active band |
| `failure_cluster` | string \| null | `FAILURE_PATTERN` tag for adversarial examples; null for harvested |
| `freshness_weight` | 0.0–1.0 | Decays ×0.9 per run; new examples start at 1.0 |
| `perturbation_type` | string \| absent | Adversarial only: which of the five types was applied |
| `seed_id` | string \| absent | Adversarial only: `session_id` of the source example |
| `persistence_score` | 0.0–1.0 | Harvested: fraction of `files_modified` still in HEAD |
| `persistence_age` | integer | Harvested: average commit count for still-present files |
| `revision_distance` | 0.0–1.0 | Harvested: how much the linked issue was revised post-invocation |
| `oracle_score` | 0–100 | Quality gate score from the oracle rubric |

`apo-textgrad` reads only `input` and `expected` — the other fields are miner bookkeeping and are preserved across re-runs.

---

## Configuration Reference

Set context variables with `--context key=value` flags or by editing the loop's `context:` block after `ll-loop install`.

| Variable | Default | Notes |
|----------|---------|-------|
| `skill_name` | `capture-issue` | Controls `ll-messages --skill` filter; must match a real skill name exactly |
| `prompt_file` | `system.md` | Path to the prompt being optimized; passed to the inner `apo-textgrad` loop |
| `examples_file` | `examples.json` | Written twice per run: intermediate (before optimizer) and final (at publish) |
| `corpus_state_file` | `corpus.json` | If this file exists, calibrate loads it and decays `freshness_weight` ×0.9 |
| `target_pass_rate` | `0.6` | Center of the 40–80% difficulty band (fraction, 0–1); used only in the calibrate prompt |

---

## File I/O Reference

| File | Read by | Written by | Purpose |
|------|---------|------------|---------|
| `corpus.last_harvested` | `harvest` (incremental `--since` flag) | `publish` (UTC timestamp) | Incremental harvest sentinel |
| `corpus.json` (or `corpus_state_file`) | `calibrate` (Read tool, optional) | Not written by the miner | Persisted calibration state for freshness decay |
| `examples.json` (or `examples_file`) | `run_optimizer` inner loop | `write_examples` (intermediate), `publish` (final) | The training corpus for `apo-textgrad` |
| `.issues/completed/*.md` | `judge` (session log entry count via Bash) | Never | Source of revision distance heuristic |
| Session JSONL files in `~/.claude/projects/` | `ll-messages` in `harvest` | Never | Source of raw harvested candidates |

---

## Configuring for a Different Skill

The default `skill_name: capture-issue` is just a starting point. The miner works for any skill that has completed issues with session logs.

```bash
# Example: mine refine-issue sessions
ll-loop run examples-miner \
  --context skill_name=refine-issue \
  --context prompt_file=skills/refine-issue/SKILL.md \
  --context examples_file=refine-examples.json \
  --context corpus_state_file=refine-corpus.json

# Verify
python3 -c "import json; d=json.load(open('refine-examples.json')); print(len(d), 'examples')"
```

**Steps for a new skill:**

1. **Check harvest availability**: `ll-messages --skill <name> --examples-format --stdout | wc -l` — if 0, the skill has no eligible session history yet
2. **Set `skill_name`** to the skill's exact name (e.g., `ready-issue`, `manage-issue`)
3. **Set `prompt_file`** to the skill's SKILL.md or equivalent prompt file
4. **Use a separate `examples_file`** per skill to avoid cross-contaminating corpora
5. **Use a separate `corpus_state_file`** per skill for independent freshness tracking

**On the inline oracle**: the judge's oracle rubric is generic — it scores `tools_used`, `files_modified`, and `completion_status` without knowing what the "correct" tools or files are for a given skill. For skill-specific precision (e.g., knowing that `refine-issue` must always modify an issue file), see the Oracle Sub-loop section below.

---

## Incremental Harvesting

The sentinel file `corpus.last_harvested` is the key to efficient re-runs:

```
First run:
  corpus.last_harvested not present
  → harvest state: SINCE_ARG=""
  → ll-messages harvests ALL session history
  → publish writes: 2026-03-21T22:00:00Z > corpus.last_harvested

Second run (next day):
  corpus.last_harvested = "2026-03-21T22:00:00Z"
  → harvest state: SINCE_ARG="--since 2026-03-21T22:00:00Z"
  → ll-messages harvests only sessions from the past day
  → publish updates sentinel to current time
```

**Important**: the sentinel is written only by `publish`. If the loop terminates early (e.g., `judge` is blocked, or the loop times out), the sentinel is NOT updated. The next run will re-harvest the same window — no sessions are skipped.

**Forcing a full reharvest** (e.g., after a major skill refactor):

```bash
rm corpus.last_harvested
ll-loop run examples-miner --context skill_name=<name> ...
```

**Resetting the corpus** (start fresh, ignore freshness decay):

```bash
rm corpus.last_harvested corpus.json examples.json
ll-loop run examples-miner --context skill_name=<name> ...
```

---

## The Oracle Sub-loop (v2 Upgrade)

The built-in `examples-miner.yaml` uses inline LLM judging in the `judge` and `score_adversarial` states. This is a generic rubric that works across all skills but doesn't know skill-specific invariants.

For production use on a specific skill, upgrade to a dedicated oracle sub-loop:

### 1. Install the loop

```bash
ll-loop install examples-miner
# copies to .loops/examples-miner.yaml
```

### 2. Create the oracle YAML

Copy the reference implementation and adapt for your skill:

```bash
mkdir -p .loops/oracles
cp loops/oracles/oracle-capture-issue.yaml .loops/oracles/oracle-<skill>.yaml
```

Edit `.loops/oracles/oracle-<skill>.yaml`:
- Update `skill_name` in the context block
- Customize `check_mechanical`'s Python check for the skill's `files_modified` invariants (e.g., `refine-issue` should always modify an issue file in `.issues/`)
- Update the `score_semantic` prompt for the skill's specific tool expectations

### 3. Wire the oracle into judge

In `.loops/examples-miner.yaml`, replace the `judge` state's `action_type: prompt` with a sub-loop delegation:

```yaml
judge:
  loop: oracles/oracle-<skill>
  context_passthrough: true
  on_success: calibrate
  on_failure: done
```

> **Note**: The `loop:` field does not support context interpolation — `loop: oracles/oracle-${context.skill_name}` does NOT work. Hardcode the oracle path.

### 4. Calibrate the oracle

Use ensemble agreement bootstrapping to validate the oracle before deploying:

1. Run the oracle at multiple temperatures against the full candidate pool
2. Examples where all temperature variants agree strongly → use as fixture set
3. Validate against deliberately degraded candidates (strip required sections, corrupt file paths in known-good examples) — the oracle must score these low; if it doesn't, it is miscalibrated
4. If oracle scores on the fixture set drift significantly across consecutive runs, halt and re-calibrate rather than corrupting the corpus

---

## Monitoring a Run

Use `--verbose` to see candidate counts at each state:

```bash
ll-loop run examples-miner --verbose \
  --context skill_name=capture-issue \
  --context prompt_file=skills/capture-issue/SKILL.md
```

What to watch at each stage:

| State | What to look for |
|-------|-----------------|
| `harvest` | Line count of JSON output = raw candidate count; 0 lines means no matching sessions |
| `judge` | Length of JSON array in output = survivors after quality gating; watch for discards |
| `calibrate` | `CALIBRATED_COUNT=N` on last output line; N=0 means all candidates outside band |
| `write_examples` | `WRITTEN=N`; confirms intermediate corpus write succeeded |
| `run_optimizer` | Sub-loop states shown with `  ` indent; watch for `CONVERGED` vs exhausting iterations |
| `synthesize` | Length of JSON array = adversarial candidates generated; `[]` means no gradient / optimizer converged |
| `screen_adversarial` | `SCREENED_COUNT=N` |
| `score_adversarial` | `ADVERSARIAL_ACCEPTED=N`; also watch adversarial cap enforcement in output |
| `diversify` | `FINAL_COUNT=N` |
| `publish` | `PUBLISHED=N` = final corpus size; confirms sentinel updated |

The loop exits at `done` (terminal). If it exits early via `on_blocked: done` on `judge` or `calibrate`, the corpus was not published and the sentinel was not updated.

---

## Tips

- **Start with `--verbose`** on the first run to see candidate counts at each stage and diagnose empty-corpus issues early.
- **Verify harvest first**: run `ll-messages --skill <name> --examples-format --stdout | wc -l` standalone before running the full loop — it confirms the session data exists and the skill name is correct.
- **Separate `examples_file` per skill**: don't share `examples.json` across skills; each skill's corpus should be isolated for clean gradient signals.
- **Delete `corpus.last_harvested` after major refactors**: when skill conventions change significantly (new file layout, renamed commands), force a full reharvest to pick up all historical examples under the new conventions.
- **Use `corpus_state_file`** for long-running projects: it preserves `freshness_weight` decay across runs and prevents corpus churn when recent sessions produce no new candidates.
- **The `synthesize → []` result is the happy path**: if the optimizer converged and `FAILURE_PATTERN` is absent, `synthesize` correctly outputs `[]`. No adversarial examples means the corpus is already doing its job.
- **Install before customizing**: `ll-loop install examples-miner` copies the YAML to `.loops/` so you can tune timeouts, adjust the difficulty band, or wire a skill-specific oracle without affecting the built-in.
- **The intermediate `write_examples` matters**: if this state is blocked, `run_optimizer` will read whatever `examples.json` was on disk before the run — potentially stale. Check `write_examples` output in `--verbose` mode if the optimizer behaves unexpectedly.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `harvest` produces 0 lines | No sessions match `--skill` filter; or sentinel timestamp is in the future | Run `ll-messages --skill <name> --stdout` standalone to verify; delete `corpus.last_harvested` to reset the window |
| `judge` outputs empty array `[]` | All candidates discarded: files absent from HEAD, or oracle_score too low | Use `--verbose` to see which layer is discarding; check `git log` for `files_modified` paths; the skill may not modify trackable files |
| `calibrate` outputs `CALIBRATED_COUNT=0` | All judged candidates outside 40–80 difficulty band | Corpus may be all easy (prompt too good for history) or all hard (few quality examples); delete `corpus.json` to clear stale accumulated state |
| Loop skips to `diversify` after `run_optimizer` | Inner `apo-textgrad` hit `max_iterations` or timed out | Expected behavior on timeout; increase outer loop `timeout:` (default 7200s) or override inner loop via context; check `--verbose` for inner loop state |
| `synthesize` outputs `[]` | Gradient is `CONVERGED` or `FAILURE_PATTERN` absent | This is the happy path — the optimizer converged on the current corpus; no adversarial synthesis is needed |
| `ADVERSARIAL_ACCEPTED=0` | All adversarial candidates outside 40–80 band, below oracle threshold, or cap already full | Check `synthesize` output in `--verbose`; the perturbation type may not match the actual failure pattern; or harvested corpus is already at/near the 30% adversarial cap |
| Final corpus is empty | All paths produced empty arrays | Run with `--verbose` and trace which state first produced `[]`; the most common cause is an empty harvest (no sessions) flowing through to an empty judge and calibrate |
| `publish` writes the intermediate corpus | `diversify` was blocked or skipped; `publish` reads whatever `calibrated_corpus` last held | Check `diversify` in `--verbose` for blocking; increase the `diversify` timeout |
| Sentinel `corpus.last_harvested` has wrong date | System clock skew or a previous run wrote a future timestamp | `cat corpus.last_harvested` to inspect; delete and let the next run rebuild from scratch |

---

## See Also

- [LOOPS_GUIDE.md](LOOPS_GUIDE.md) — quick-reference section for `examples-miner`: context variables table, FSM flow diagram, perturbation taxonomy, basic invocations
- [`loops/examples-miner.yaml`](../../loops/examples-miner.yaml) — full annotated loop source (12 states with complete action prompts)
- [`loops/oracles/oracle-capture-issue.yaml`](../../loops/oracles/oracle-capture-issue.yaml) — reference implementation for the v2 oracle sub-loop (two-phase: shell mechanical checks + LLM semantic scoring)
- [`loops/apo-textgrad.yaml`](../../loops/apo-textgrad.yaml) — inner optimizer loop invoked by `run_optimizer`; reads `examples_file`, emits `FAILURE_PATTERN` / `ROOT_CAUSE` / `GRADIENT`
- [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) — related guide for wrapping skills in layered quality evaluation pipelines
- [FSM Loop Architecture](../generalized-fsm-loop.md) — sub-loop chaining (`context_passthrough`), state field reference, evaluator catalog
