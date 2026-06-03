---
id: FEAT-1826
title: sft-corpus FSM loop for SLM fine-tuning from session logs
type: FEAT
priority: P3
status: open
captured_at: '2026-05-31T22:00:59Z'
discovered_date: '2026-05-31'
discovered_by: capture-issue
parent: EPIC-1880
decision_needed: false
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1826: sft-corpus FSM loop for SLM fine-tuning from session logs

## Summary

New FSM loop that extracts multi-turn conversations from Claude Code `.jsonl` session logs, converts them into SFT training format (ChatML / Alpaca / ShareGPT), applies quality filtering and deduplication, and produces a train/val/test split ready for fine-tuning a small language model.

## Current Behavior

No dedicated pipeline exists for extracting SFT training data from Claude Code session logs. Practitioners must manually extract `.jsonl` logs, write custom conversion scripts for each target format (ChatML/Alpaca/ShareGPT), implement quality filtering and deduplication, and handle train/val/test splits — a multi-step process with no ll-native tooling.

## Expected Behavior

A runnable `sft-corpus` FSM loop handles the full pipeline from raw `.jsonl` session logs to a publishable SFT corpus, respecting all configured context keys (`sft_format`, `output_dir`, `max_turns`, `min_tokens`, `max_tokens`, `pii_action`, `val_ratio`, `test_ratio`). The back-half (filter → dedup → split → publish) delegates to `dataset-curation` via a `loop:` handoff.

## Motivation

Neither `examples-miner` nor `dataset-curation` fits the SLM fine-tuning use case:
- `examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format
- `dataset-curation` is a generic back-half pipeline (quality gate → distribute → publish) but has no JSONL log ingestion or SFT format conversion
- A new loop is needed that owns the full pipeline from raw session logs through a publishable SFT corpus

## Use Case

A practitioner wants to fine-tune an SLM on Claude Code session data. They have `.jsonl` logs under `~/.claude/projects/` and want a curated, formatted dataset they can pass directly to a fine-tuning trainer (e.g., Axolotl, LLaMA-Factory, torchtune).

## Acceptance Criteria

- [ ] `ll-loop run sft-corpus` ingests `.jsonl` files from `log_dir` and produces at least one output example
- [ ] Output is valid for the configured `sft_format` (`chatml`, `alpaca`, or `sharegpt`)
- [ ] Examples outside `[min_tokens, max_tokens]` token range are discarded by the `filter` state
- [ ] Near-duplicate conversations (same fingerprint) produce only one output example after `dedup`
- [ ] `split` state writes separate `train`/`val`/`test` files at configured ratios
- [ ] Back-half delegates to `dataset-curation` loop via `loop:` handoff (no reimplementation of quality/distribute/validate/publish)
- [ ] Harvest sentinel is updated after each successful `publish` run, enabling incremental re-runs

## Implementation Steps

1. **ingest** — walk `~/.claude/projects/` (or a configured `log_dir`), enumerate `.jsonl` files newer than a harvest sentinel, extract multi-turn conversation windows (not just skill invocations)
2. **convert** — transform each conversation window into the target SFT format via `context.sft_format` (`chatml` / `alpaca` / `sharegpt`); emit one JSON object per example
3. **filter** — quality-gate: token length budget check, turn coherence, task completion signal, PII heuristic (flag/redact)
4. **dedup** — near-duplicate removal by conversation fingerprint (hash of normalized turn sequence)
5. **split** — stratified train/val/test split by source session, write separate output files
6. **publish** — write final corpus files + manifest; update harvest sentinel

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Modify `scripts/tests/test_builtin_loops.py` — add `"sft-corpus"` to `expected` set in `test_expected_loops_exist()` (test breaks otherwise)
8. Modify `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block declaring `data_dir`, `output_dir`, `schema_path` with defaults matching existing `context:` values; `required: false` + defaults makes this non-breaking for direct `ll-loop run dataset-curation` invocations; enables `_validate_with_bindings()` contract enforcement for the `sft-corpus` handoff
9. Update `scripts/little_loops/loops/README.md` — add `sft-corpus` to "Data & Testing" table (line 114)
10. Create `scripts/tests/test_loops_sft_corpus.py` — sentinel file read/write tests + structural YAML validation; follow `test_loops_recursive_refine.py` (shell state via `_bash`) and `test_rn_plan.py` (structural YAML) patterns
11. Update `docs/guides/LOOPS_GUIDE.md` — add `sft-corpus` to loop reference table; optionally add deep-dive section parallel to `### examples-miner`

### Child loop handoff
Pipe the curated back-half (filter → dedup → split) through `dataset-curation` via a `loop:` handoff, reusing its quality/distribution/validate/publish states rather than reimplementing them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `ingest` + `convert` collapse into one shell action (ENH-1827 `status: done`)**

`ll-messages --sft-format` already handles both phases:

```bash
# harvest state (action_type: shell)
SINCE_ARG=""; [ -f sft-corpus.last_harvested ] && SINCE_ARG="--since $(cat sft-corpus.last_harvested)"
ll-messages --sft-format ${context.sft_format} \
  --context-window ${context.max_turns} \
  $SINCE_ARG \
  --output ${context.output_dir}/raw.jsonl
```

**Harvest sentinel pattern** (from `examples-miner.yaml:harvest/publish`):
- Read: `[ -f sft-corpus.last_harvested ] && SINCE_ARG="--since $(cat sft-corpus.last_harvested)"`
- Write: `date -u +%Y-%m-%dT%H:%M:%SZ > sft-corpus.last_harvested` (in terminal/publish state)

**`loop:` handoff syntax** (from `examples-miner.yaml:run_optimizer`, `schema.py:L381`):
- `context_passthrough: true` — forwards parent context wholesale; mutually exclusive with `with:`
- `with:` block — explicit bindings; required when child context key names differ from parent
- `on_success`/`on_failure` are aliases for `on_yes`/`on_no` in `StateConfig.from_dict`

**Token filtering**: No `tiktoken` in codebase. Use word-count approximation as proxy:
```bash
python3 -c "import sys,json; d=json.loads(sys.stdin.read()); \
  print(sum(len(m.get('content','').split()) for m in d.get('messages', [])))"
```
Or instruct the `filter` prompt state to estimate turn lengths from the example JSON.

**Dedup**: `scripts/little_loops/text_utils.py:calculate_word_overlap()` uses Jaccard similarity — same pattern the codebase uses for near-duplicate detection. No hashlib approach needed.

**dataset-curation context key mismatch — see `decision_needed` options below.**

**Run command**: `ll-loop run sft-corpus` — auto-discovered from `scripts/little_loops/loops/sft-corpus.yaml`

---

**Proposed Solution — dataset-curation handoff strategy (3 options)**

This is the primary implementation decision. `context_passthrough` and `with:` are mutually exclusive, and `dataset-curation` uses `context.data_dir` while `sft-corpus` writes to `context.output_dir`.

**Option A: Align context keys in sft-corpus**

Add `data_dir` as an alias in sft-corpus's `context:` block pointing to the staging directory. Use `context_passthrough: true` — child inherits `data_dir` from parent.

```yaml
context:
  data_dir: "data/sft/staged"   # staging dir; passed to dataset-curation via context_passthrough
  output_dir: "data/sft"
  ...

curate:
  loop: dataset-curation
  context_passthrough: true
  on_success: update_sentinel
  on_failure: done
```

Pro: No changes to `dataset-curation.yaml`. Con: `data_dir` semantics in sft-corpus are slightly misleading.

**Option B: Use `with:` for explicit binding**

> **Selected:** Option B — explicit `with:` binding via `ParameterSpec` is the purpose-built mechanism for cross-loop context key mapping, matching the `scan-and-implement.yaml` pattern exactly.

Add a formal `parameters:` block to `dataset-curation.yaml` declaring `data_dir`, then use `with:` from sft-corpus to bind it explicitly.

```yaml
# in sft-corpus.yaml
curate:
  loop: dataset-curation
  with:
    data_dir: "${context.output_dir}/staged"
    output_dir: "${context.output_dir}"
    schema_path: "${context.schema_path}"
  on_success: update_sentinel
  on_failure: done
```

Pro: Explicit and type-safe; no key aliasing confusion. Con: Requires adding `parameters:` to `dataset-curation.yaml`.

**Option C: sft-corpus owns filter/dedup/split; dataset-curation handles only validate+publish**

sft-corpus implements all 6 states itself and uses `dataset-curation` only for final schema validation and publishing. The `loop:` handoff to `dataset-curation` starts from its `validate_schema` state.

Pro: No context key mismatch; cleaner separation of concerns. Con: Reimplements distribution-balance logic that `dataset-curation` already has; the `loop:` field doesn't support specifying a start-state in the child FSM (child always begins at `initial`).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Option B: Use `with:` for explicit binding

**Reasoning**: Option B uses the purpose-built `ParameterSpec` + `with:` mechanism (`schema.py:208`) that was designed precisely for cross-loop context key mapping, and matches the established `scan-and-implement.yaml:77` handoff pattern. Option A (context_passthrough with an alias key) works but introduces a misleading `data_dir` in sft-corpus's context block. Option C is technically non-viable: `loop:` handoffs have no `start_state` parameter and `dataset-curation`'s `initial` state is `ingest` — the child FSM cannot be entered at `validate_schema`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 3/3 | 2/3 | 3/3 | 10/12 |
| Option B | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option C | 0/3 | 0/3 | 1/3 | 0/3 | 1/12 |

**Key evidence**:
- **Option A**: `examples-miner.yaml:138` uses `context_passthrough: true` — established pattern, but adding a `data_dir` alias key in sft-corpus purely for child compatibility has no prior precedent in the codebase.
- **Option B**: `scan-and-implement.yaml:77` uses `with:` for explicit bindings; `ParameterSpec` (`schema.py:208`) is the designed mechanism for exactly this use case. Adding `parameters:` to `dataset-curation.yaml` with defaults is non-breaking.
- **Option C**: `dataset-curation.yaml:19` sets `initial: ingest`; no `start_state` field exists in `StateConfig` (`schema.py:381`). The `loop:` handoff cannot target `validate_schema` as entry point — this option is architecturally blocked without FSM runner changes.

## API / Interface

Context keys (`.ll/ll-config.json` or loop `context:` block):

```yaml
context:
  log_dir: "~/.claude/projects"
  sft_format: "chatml"          # chatml | alpaca | sharegpt
  output_dir: "data/sft"
  max_turns: 20                 # max turns per conversation window
  min_tokens: 50                # discard very short exchanges
  max_tokens: 4096              # discard context-overflow examples
  pii_action: "flag"            # flag | redact | discard
  val_ratio: 0.1
  test_ratio: 0.1
  schema_path: "schemas/sft.json"  # passed to dataset-curation via with: binding (Option B)
  dedup_threshold: 0.9             # Jaccard similarity threshold for near-duplicate removal
```

## Integration Map

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — add `"sft-corpus"` to `expected` set in `test_expected_loops_exist()` — test **breaks** without this update [Agent 1/2/3 finding]
- `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block declaring `data_dir`, `output_dir`, `schema_path` with defaults matching existing `context:` values per Option B decision (also listed as Dependent File; must be modified to satisfy `with:` contract enforcement) [Agent 1 finding]
- `scripts/little_loops/loops/README.md` — add `sft-corpus` to "Data & Testing" table (line 114) [Agent 2 finding]

### New Files
- `scripts/little_loops/loops/sft-corpus.yaml` — primary deliverable (new FSM loop)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/dataset-curation.yaml` — invoked as back-half via `loop:` handoff

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Reusable utilities (no reimplementation needed):**
- `scripts/little_loops/sft_formatter.py:to_chatml()` (L7) — converts `list[tuple[str,str]]` → `{"messages": [...]}`
- `scripts/little_loops/sft_formatter.py:to_alpaca()` (L20) — first user turn → instruction, last assistant → output
- `scripts/little_loops/sft_formatter.py:to_sharegpt()` (L39) — maps user→human, assistant→gpt
- `scripts/little_loops/user_messages.py:extract_conversation_turns()` (L765) — sliding-window extraction from `.jsonl` logs with `since` filter; returns `list[list[tuple[str,str]]]`
- `scripts/little_loops/cli/messages.py:main_messages()` — `ll-messages --sft-format <fmt> --context-window N --since DATE --stdout` already combines ingest + format conversion (ENH-1827 `status: done`)
- `scripts/little_loops/text_utils.py:calculate_word_overlap()` — Jaccard similarity for near-duplicate detection (not hashlib); existing dedup pattern in the codebase

**Loop handoff context key mismatch (see Proposed Solution / decision_needed):**
- `dataset-curation.yaml` reads from `context.data_dir`; `sft-corpus` writes to `context.output_dir` — these are different keys; binding strategy is the implementation decision

**`extract_conversation_turns()` exact signature** (`user_messages.py:L765`):
- `project_folder: Path` — directory path, not individual file (e.g., `Path("~/.claude/projects").expanduser()`)
- `since: datetime | None = None`, `context_window: int = 3`, `include_agent_sessions: bool = True`
- Returns `list[list[tuple[str, str]]]`; `since` filter is **per-turn, not per-file** — all `.jsonl` files are fully scanned regardless of the sentinel; only output turns are dropped.
- Already called by `ll-messages --sft-format`; the `harvest` shell state does not need to invoke it directly.

**`to_alpaca()` turn requirement**: Requires ≥1 user turn and ≥1 assistant turn; a single-turn window leaves `output` empty. The `filter` state must discard examples with `len(turns) < 2` when `sft_format == "alpaca"`.

**Recommended `action_type` for filter/dedup/split**: All three are batch JSONL operations — use `action_type: shell` with inline Python, not `prompt` states.
- `filter`: word-count proxy via `python3 -c` against `context.min_tokens`/`context.max_tokens`; PII (`pii_action`) has no existing utility — use simple regex heuristic in v1 (email, phone, SSN patterns) or treat `flag` as a no-op pass for the initial release.
- `dedup`: `from little_loops.text_utils import extract_words, calculate_word_overlap` inline; skip example if Jaccard vs any seen set ≥ `context.dedup_threshold`.
- `split`: stratify by source session filename (present in JSONL metadata); write to `${context.output_dir}/staged/` as `train.jsonl`/`val.jsonl`/`test.jsonl` — this is the `data_dir` dataset-curation's `ingest` state reads from.

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:harvest` — canonical harvest sentinel shell pattern (`SINCE_ARG` + `--since`) and sentinel write in `publish` state
- `scripts/little_loops/loops/examples-miner.yaml:run_optimizer` — `loop: apo-textgrad` with `context_passthrough: true`, `on_success`/`on_failure` routing
- `scripts/little_loops/loops/scan-and-implement.yaml` — `loop:` with explicit `with:` bindings (alternative to `context_passthrough`)
- `scripts/little_loops/loops/dataset-curation.yaml:route_quality` — `output_numeric` evaluator (non-LLM gate); pairs with `llm_structured` in `validate_schema` to satisfy MR-1

### Tests
- `scripts/tests/test_fsm_flow.py:TestBuiltinLoopRegression.test_all_builtin_loops_still_load()` — auto-picks up new `loops/sft-corpus.yaml`; no custom YAML validation test needed
- `scripts/tests/test_loops_recursive_refine.py` — template for testing shell state logic via `_bash(script, tmp_path)` with `.loops/tmp/` fixtures (if sentinel/filter shell snippets need unit tests)
- `scripts/tests/test_user_messages.py` — SFT formatter tests already exist; add `extract_conversation_turns` coverage if testing that path directly

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_expected_loops_exist` — update: add `"sft-corpus"` to hardcoded expected set (lines 69–135); **test breaks** when `sft-corpus.yaml` is added without this update [Agent 1/2/3 finding]
- `scripts/tests/test_loops_sft_corpus.py` — new file: sentinel read/write tests (`test_harvest_passes_since_when_sentinel_exists`, `test_harvest_omits_since_when_no_sentinel`) + structural YAML validation; follow `test_loops_recursive_refine.py::TestDepthMapInit` and `test_rn_plan.py::TestRnPlanYaml` patterns [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::TestSubLoopWithBindings` — add test for `sft-corpus → dataset-curation` `with:` binding resolution; follow `test_with_interpolation_from_parent_context` pattern [Agent 3 finding]

### Documentation
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — deep-dive on harvest sentinel pattern; read before implementing `ingest` state
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; `loop:` handoff syntax documented in sub-loop section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — add `sft-corpus` to loop reference table (line ~337, "General-Purpose" table); currently not listed; may also warrant a `### sft-corpus` deep-dive section parallel to the existing `### examples-miner` section (line ~2328) [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — add `sft-corpus` to "Data & Testing" table (line 114) [Agent 2 finding]
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — add cross-reference or new section for `sft-corpus.last_harvested` sentinel behavior; the guide currently documents only `corpus.last_harvested` (line ~405 artifact table, line ~580 troubleshooting table) [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — optional `sft_corpus` section for context key overrides

## Impact

- **Priority**: P3 — Useful for SLM practitioners; not blocking core ll workflows
- **Effort**: Large — New 6-phase FSM loop with format conversion, PII handling, and `dataset-curation` handoff
- **Risk**: Low — New YAML artifact only; no changes to existing scripts, loops, or APIs
- **Breaking Change**: No

## Related

- `scripts/little_loops/loops/examples-miner.yaml` — prompt-optimization corpus mining (different target)
- `scripts/little_loops/loops/dataset-curation.yaml` — candidate back-half via `loop:` handoff
- ENH-1827 — add `--sft-format` to `ll-messages` CLI (alternate ingest path)

## Labels

`loop`, `sft`, `fine-tuning`, `new-feature`

## Session Log
- `/ll:refine-issue` - 2026-06-03T00:46:04 - `ef863381-72dc-415f-ad39-f86d8e42dba1.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `17557f51-d1e7-48ab-8c75-d04f0cc19f24.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:31:19 - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`
- `/ll:decide-issue` - 2026-06-03T00:24:05 - `0467dd38-23d6-4a11-9d93-1a10ed0c40c9.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:18:35 - `d3bc2a68-d557-49f9-a947-e12cd4b90c1c.jsonl`
- `/ll:format-issue` - 2026-06-02T23:15:08 - `0d29889f-5db4-42d2-b354-e9615aee84a2.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`

---
## Status

`open`
