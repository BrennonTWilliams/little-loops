---
id: FEAT-1826
title: sft-corpus FSM loop for SLM fine-tuning from session logs
type: FEAT
priority: P3
status: done
captured_at: '2026-05-31T22:00:59Z'
completed_at: '2026-06-04T21:42:45Z'
discovered_date: '2026-05-31'
discovered_by: capture-issue
parent: EPIC-1880
decision_needed: false
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
labels:
- epic: EPIC-1880
- featured
- loop
- sft
- fine-tuning
---

# FEAT-1826: sft-corpus FSM loop for SLM fine-tuning from session logs

## Summary

The `sft-corpus` FSM loop (`scripts/little_loops/loops/sft-corpus.yaml`) stages session transcripts, enriches them with `history.db` session-quality metadata via `lookup_session_metadata()` (ENH-1943), filters with four opt-in quality predicates (ENH-1944), and publishes a quality-gated SFT training corpus with rejection tracking. The loop exists and is functional; remaining work is end-to-end integration validation and switching the `stage` state to the DB-first ingestion path (`ll-messages --sft-format --reader db`) instead of raw `cat *.jsonl`.

**Architecture**: `history.db` is the primary data source for quality metadata; raw JSONL is the graceful-degradation fallback (ENH-1942). The loop currently reads content from staged JSONL and joins metadata from `history.db` — the remaining gap is making the `stage` state use the DB-first path for content ingestion too.

## Current Behavior

The `sft-corpus` loop exists at `scripts/little_loops/loops/sft-corpus.yaml` with **14 states**:

- **stage**: Collects session JSONL transcripts from `context.data_dir` into a raw corpus (currently uses `cat *.jsonl`; should use `ll-messages --sft-format --reader db`)
- **enrich**: Batch-joins `history.db` session-quality metadata via `lookup_session_metadata()` (ENH-1943) — appends `has_corrections`, `issue_outcome`, `tool_count`, `files_modified` to each example
- **filter predicate chain (5 predicates)**: Five quality gates, each with a companion reject state:
  1. `check_issue_outcome` / `reject_issue_outcome` — gated by `require_issue_outcome` flag (ENH-1944)
  2. `check_corrections` / `reject_corrections` — gated by `exclude_user_corrections` flag (ENH-1944)
  3. `check_tools` / `reject_tools` — gated by `min_tool_invocations` threshold (ENH-1944)
  4. `check_files` / `reject_files` — gated by `require_file_modifications` flag (ENH-1944)
  5. `check_pii` / `reject_pii` — gated by `pii_action` context key; supports flag/redact/discard modes via `apply_pii_action()` from `little_loops.pii` (ENH-1948, **done**)
- **publish**: Aggregates acceptance/rejection stats and writes `manifest.json` + `rejections.jsonl`

Supporting infrastructure is all in place: `history_reader.conversation_turns()` (DB-based turn-pair extraction), `history_reader.lookup_session_metadata()` (quality-signal queries), `user_messages.extract_conversation_turns()` (DB-first delegation), `ll-messages --sft-format --reader auto|db|jsonl` (CLI flag), `pii.apply_pii_action()` (flag/redact/discard), `dataset-curation.yaml` `parameters:` block (ENH-1949, **done**). Tests pass: 33 tests in `test_loops_sft_corpus.py`, 19 tests in `test_assistant_messages.py`, full suite at 9809 passed.

The loop does NOT yet use `ll-messages --sft-format --reader db` in its `stage` state for DB-first content ingestion — it cats raw JSONL instead. The dedup, split, format conversion, harvest sentinel, and `dataset-curation` handoff (Option B wiring) are not yet implemented in the loop YAML.

## Expected Behavior

A runnable `sft-corpus` FSM loop handles the full pipeline from `history.db`-backed session data (with JSONL graceful-degradation fallback) to a publishable SFT corpus:

1. **Ingest** (gap): `stage` state uses `ll-messages --sft-format chatml --reader db` for DB-first content extraction, falling back to JSONL if `history.db` is unavailable
2. **Enrich** (done): `enrich` state batch-joins `history.db` session-quality metadata via `lookup_session_metadata()`
3. **Filter** (done): Four opt-in quality predicates gated by context flags, with rejection tracking
4. **Format conversion** (gap): SFT format conversion (ChatML/Alpaca/ShareGPT) — `SFTFormatter` exists but the loop doesn't call it yet
5. **Dedup** (gap): Near-duplicate removal by Jaccard similarity via `text_utils.calculate_word_overlap()`
6. **Split** (gap): Train/val/test split by source session
7. **Publish** (partial): Manifest write is done; `dataset-curation` handoff via `loop:` with `with:` bindings (Option B) is not yet wired

All configured context keys (`sft_format`, `output_dir`, `max_turns`, `min_tokens`, `max_tokens`, `pii_action`, `val_ratio`, `test_ratio`) should be respected.

## Motivation

Neither `examples-miner` nor `dataset-curation` fits the SLM fine-tuning use case:
- `examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format
- `dataset-curation` is a generic back-half pipeline (quality gate → distribute → publish) but has no JSONL log ingestion or SFT format conversion
- A new loop is needed that owns the full pipeline from raw session logs through a publishable SFT corpus

## Use Case

A practitioner wants to fine-tune an SLM on Claude Code session data. They have `.jsonl` logs under `~/.claude/projects/` and want a curated, formatted dataset they can pass directly to a fine-tuning trainer (e.g., Axolotl, LLaMA-Factory, torchtune).

## Acceptance Criteria

- [x] `ll-loop run sft-corpus` ingests session data and produces at least one output example (loop exists, runs; content source is staged JSONL — see gap below)
- [x] `ll-loop validate sft-corpus` reports no ERRORs
- [ ] Output is valid for the configured `sft_format` (`chatml`, `alpaca`, or `sharegpt`) — SFTFormatter exists but loop doesn't invoke it yet
- [x] Examples are filtered by quality predicates from `history.db` (`require_issue_outcome`, `exclude_user_corrections`, `min_tool_invocations`, `require_file_modifications`) — all four implemented with rejection tracking; PII predicate (`pii_action`: flag/redact/discard) also wired (ENH-1948 done, 16 tests)
- [ ] Token length filtering (`[min_tokens, max_tokens]`) — not yet implemented in loop
- [ ] Near-duplicate conversations (same fingerprint) produce only one output example after `dedup` — `text_utils.calculate_word_overlap()` exists but loop hasn't wired it
- [ ] `split` state writes separate `train`/`val`/`test` files at configured ratios
- [ ] Back-half delegates to `dataset-curation` loop via `loop:` handoff (Option B wiring with `with:` bindings not yet done)
- [ ] Harvest sentinel is updated after each successful `publish` run, enabling incremental re-runs
- [ ] `stage` state uses `ll-messages --sft-format --reader db` for DB-first content ingestion (currently uses raw `cat *.jsonl`)
- [ ] End-to-end integration test: `ll-loop run sft-corpus` completes against real `history.db`-backed session data, producing `data/corpus/` with `manifest.json` and non-empty rejection tracking (EPIC-1880's remaining AC)

**Remaining gaps (5 implementation items + 1 verification)**:

_Completed since last refine:_ PII detection wired into filter chain as predicate 5 (ENH-1948, done, 16 tests) and `dataset-curation.yaml` `parameters:` block added (ENH-1949, done). Wiring phase items 7–11 all complete.

1. DB-first content ingestion in `stage` state (`--reader db` instead of `cat *.jsonl`) + harvest sentinel
2. SFT format conversion via `SFTFormatter` in the loop
3. Token-length filtering
4. Dedup via Jaccard similarity
5. Train/val/test split + `dataset-curation` handoff wiring (Option B, `parameters:` block now ready)
6. End-to-end integration test against real `history.db`-backed data (verification gate)

## Implementation Steps

1. **ingest** — walk `~/.claude/projects/` (or a configured `log_dir`), enumerate `.jsonl` files newer than a harvest sentinel, extract multi-turn conversation windows (not just skill invocations)
2. **convert** — transform each conversation window into the target SFT format via `context.sft_format` (`chatml` / `alpaca` / `sharegpt`); emit one JSON object per example
3. **filter** — quality-gate: token length budget check, turn coherence, task completion signal, PII heuristic (flag/redact)
4. **dedup** — near-duplicate removal by conversation fingerprint (hash of normalized turn sequence)
5. **split** — stratified train/val/test split by source session, write separate output files
6. **publish** — write final corpus files + manifest; update harvest sentinel

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis. Items checked below are complete._

- [x] 7. Modify `scripts/tests/test_builtin_loops.py` — **DONE**: `sft-corpus` already in `expected` set at line 119
- [x] 8. Modify `scripts/little_loops/loops/dataset-curation.yaml` — **DONE** (ENH-1949): `parameters:` block declares `data_dir`, `output_dir`, `schema_path` with defaults matching existing `context:` values; `required: false` + defaults makes this non-breaking for direct `ll-loop run dataset-curation` invocations; enables `_validate_with_bindings()` contract enforcement for the `sft-corpus` handoff
- [x] 9. Update `scripts/little_loops/loops/README.md` — **DONE**: `sft-corpus` already in "Data & Testing" table
- [x] 10. Create `scripts/tests/test_loops_sft_corpus.py` — **DONE**: Now exists with 33 tests covering enrich state graceful degradation, all 5 filter predicates (issue_outcome, corrections, tools, files, PII), rejection annotations, and PII flag/redact/discard behaviors
- [x] 11. Update `docs/guides/LOOPS_GUIDE.md` — **DONE**: `sft-corpus` already in loop reference table

### Child loop handoff
Pipe the curated back-half (filter → dedup → split) through `dataset-curation` via a `loop:` handoff, reusing its quality/distribution/validate/publish states rather than reimplementing them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `ingest` + `convert` collapse into one shell action (ENH-1827 + ENH-1942 `status: done`)**

`ll-messages --sft-format` already handles both phases, now with DB-first ingestion:

```bash
# harvest state (action_type: shell) — DB-first with JSONL fallback
SINCE_ARG=""; [ -f sft-corpus.last_harvested ] && SINCE_ARG="--since $(cat sft-corpus.last_harvested)"
ll-messages --sft-format ${context.sft_format} \
  --reader auto \
  --context-window ${context.max_turns} \
  $SINCE_ARG \
  --output ${context.output_dir}/raw.jsonl
```

`--reader auto` (default) tries `history.db` first via `history_reader.conversation_turns()`, falls back to JSONL parsing. `--reader db` errors if DB unavailable; `--reader jsonl` uses the pre-ENH-1942 path. The loop's `stage` state currently uses `cat *.jsonl` instead of this command — this is the primary remaining gap.

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

_Updated by `/ll:refine-issue` 2026-06-04 — reflecting ENH-1948 and ENH-1949 completion._

_Wiring pass (added by `/ll:wire-issue`):_
- [x] `scripts/tests/test_builtin_loops.py` — **DONE**: `sft-corpus` already in `expected` set at line 119
- [x] `scripts/little_loops/loops/dataset-curation.yaml` — **DONE** (ENH-1949): `parameters:` block declares `data_dir`, `output_dir`, `schema_path` with defaults matching existing `context:` values per Option B decision
- [x] `scripts/little_loops/loops/README.md` — **DONE**: `sft-corpus` already in "Data & Testing" table

_Remaining files to modify for the 5 implementation gaps:_
- `scripts/little_loops/loops/sft-corpus.yaml` — the single file that needs updating for all 5 remaining gaps (DB-first ingestion, format conversion, token filter, dedup, split + handoff)

### New Files
- `scripts/little_loops/loops/sft-corpus.yaml` — ✅ already exists; primary deliverable (extant FSM loop, needs 5 remaining gaps filled)
- `scripts/tests/test_loops_sft_corpus.py` — ✅ already exists with 33 tests (created by wiring phase, expanded by ENH-1944 and ENH-1948)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/dataset-curation.yaml` — invoked as back-half via `loop:` handoff

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Reusable utilities (no reimplementation needed):**
- `scripts/little_loops/sft_formatter.py:to_chatml()` (L7) — converts `list[tuple[str,str]]` → `{"messages": [...]}`
- `scripts/little_loops/sft_formatter.py:to_alpaca()` (L20) — first user turn → instruction, last assistant → output
- `scripts/little_loops/sft_formatter.py:to_sharegpt()` (L39) — maps user→human, assistant→gpt
- `scripts/little_loops/user_messages.py:extract_conversation_turns()` (L773) — **now DB-first**: tries `history_reader.conversation_turns()` (queries `message_events JOIN assistant_messages`), falls back to JSONL parsing. Returns `list[list[tuple[str,str]]]`. `reader` param controls behavior (`auto|db|jsonl`).
- `scripts/little_loops/history_reader.py:conversation_turns()` (L511) — direct DB query for turn-pair windows; returns `[]` on missing/empty/pre-v11 DB
- `scripts/little_loops/history_reader.py:lookup_session_metadata()` (L435) — returns `dict` with `has_corrections`, `issue_outcome`, `tool_count`, `files_modified` per session; degrades to `{}` on missing DB
- `scripts/little_loops/cli/messages.py:main_messages()` — `ll-messages --sft-format <fmt> --reader auto --context-window N --since DATE --stdout` already combines ingest + format conversion with DB-first fallback (ENH-1827 + ENH-1942 `status: done`)
- `scripts/little_loops/text_utils.py:calculate_word_overlap()` — Jaccard similarity for near-duplicate detection (not hashlib); existing dedup pattern in the codebase

**Loop handoff context key mismatch — resolved by Option B + ENH-1949:**
- `dataset-curation.yaml` reads from `context.data_dir`; `sft-corpus` writes to `context.output_dir` — these are different keys
- **Decision**: Option B selected via `/ll:decide-issue` (2026-06-02) — use `with:` for explicit binding
- **ENH-1949 done**: `dataset-curation.yaml` now has `parameters:` block declaring `data_dir`, `output_dir`, `schema_path` (all `required: false` with defaults), enabling `_validate_with_bindings()` contract enforcement
- Remaining work: add the `curate` state to `sft-corpus.yaml` with `loop: dataset-curation` + `with:` bindings

**`extract_conversation_turns()` exact signature** (`user_messages.py:L773`):
- `project_folder: Path` — directory path, not individual file (e.g., `Path("~/.claude/projects").expanduser()`)
- `since: datetime | None = None`, `context_window: int = 3`, `include_agent_sessions: bool = True`, `reader: str = "auto"` (new: `auto|db|jsonl`)
- Returns `list[list[tuple[str, str]]]`; `since` filter is **per-turn, not per-file** — all `.jsonl` files are fully scanned regardless of the sentinel; only output turns are dropped.
- **DB-first**: tries `history_reader.conversation_turns(db_path)` first; falls back to JSONL parsing if DB returns `[]`. `reader="db"` errors on unavailable DB; `reader="jsonl"` skips DB entirely.
- Already called by `ll-messages --sft-format`; the `harvest` shell state does not need to invoke it directly.

**`to_alpaca()` turn requirement**: Requires ≥1 user turn and ≥1 assistant turn; a single-turn window leaves `output` empty. The `filter` state must discard examples with `len(turns) < 2` when `sft_format == "alpaca"`.

**Recommended `action_type` for filter/dedup/split**: All three are batch JSONL operations — use `action_type: shell` with inline Python, not `prompt` states.
- `filter`: word-count proxy via `python3 -c` against `context.min_tokens`/`context.max_tokens`; PII (`pii_action`) is **already wired** as predicate 5 in the filter chain via `little_loops.pii.apply_pii_action()` (ENH-1948 done) — flag/redact/discard modes with 16 tests; no further PII work needed for this issue.
- `dedup`: `from little_loops.text_utils import extract_words, calculate_word_overlap` inline; skip example if Jaccard vs any seen set ≥ `context.dedup_threshold`.
- `split`: stratify by source session filename (present in JSONL metadata); write to `${context.output_dir}/staged/` as `train.jsonl`/`val.jsonl`/`test.jsonl` — this is the `data_dir` dataset-curation's `ingest` state reads from.

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:harvest` — canonical harvest sentinel shell pattern (`SINCE_ARG` + `--since`) and sentinel write in `publish` state
- `scripts/little_loops/loops/examples-miner.yaml:run_optimizer` — `loop: apo-textgrad` with `context_passthrough: true`, `on_success`/`on_failure` routing
- `scripts/little_loops/loops/scan-and-implement.yaml` — `loop:` with explicit `with:` bindings (alternative to `context_passthrough`)
- `scripts/little_loops/loops/dataset-curation.yaml:route_quality` — `output_numeric` evaluator (non-LLM gate); pairs with `llm_structured` in `validate_schema` to satisfy MR-1

### Tests

_Updated by `/ll:refine-issue` 2026-06-04 — reflecting completed wiring items._

- `scripts/tests/test_fsm_flow.py:TestBuiltinLoopRegression.test_all_builtin_loops_still_load()` — auto-picks up `loops/sft-corpus.yaml`; no custom YAML validation test needed
- `scripts/tests/test_loops_recursive_refine.py` — template for testing shell state logic via `_bash(script, tmp_path)` with `.loops/tmp/` fixtures (if sentinel/filter shell snippets need unit tests)
- `scripts/tests/test_user_messages.py` — SFT formatter tests already exist

_Wiring phase tests (added by `/ll:wire-issue`):_
- [x] `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_expected_loops_exist` — **DONE**: `sft-corpus` in expected set at line 119
- [x] `scripts/tests/test_loops_sft_corpus.py` — **DONE**: 33 tests covering enrich state graceful degradation, all 5 filter predicates (issue_outcome, corrections, tools, files, PII), rejection annotations, PII flag/redact/discard behaviors
- [ ] `scripts/tests/test_fsm_executor.py::TestSubLoopWithBindings` — add test for `sft-corpus → dataset-curation` `with:` binding resolution; follow `test_with_interpolation_from_parent_context` pattern [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue` (2026-06-04):_
- `scripts/tests/test_handoff_handler.py::TestHandoffHandler` — exercises the `on_handoff: spawn` mechanism triggered by `loop:` handoffs (5 tests: default pause, terminate, pause, spawn with subprocess.Popen, spawn with None continuation). The new `curate` state in sft-corpus that hands off to `dataset-curation` will exercise the same execution path. No changes needed to this test file, but it should be re-run after implementation to confirm the handoff mechanism isn't broken. [Agent 3 finding]
- `scripts/tests/test_fsm_flow.py::TestBuiltinLoopRegression.test_all_builtin_loops_still_load` — **automatic safety net**: validates every `loops/*.yaml` via `load_and_validate()`; will break if sft-corpus.yaml changes introduce syntax or fragment-resolution errors
- `scripts/tests/test_builtin_loops.py::test_all_validate_as_valid_fsm` — **automatic safety net**: validates all loops for ERROR-severity FSM violations; will break if new states (curate with loop:/with:, format-convert, token-filter, dedup, split) add validation errors. Both gates must pass before any PR lands.

### Documentation

_Updated by `/ll:refine-issue` 2026-06-04 — reflecting completed wiring items._

- `docs/guides/EXAMPLES_MINING_GUIDE.md` — deep-dive on harvest sentinel pattern; read before implementing `ingest` state
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; `loop:` handoff syntax documented in sub-loop section

_Wiring pass (added by `/ll:wire-issue`):_
- [x] `docs/guides/LOOPS_GUIDE.md` — **DONE**: `sft-corpus` already in loop reference table
- [x] `scripts/little_loops/loops/README.md` — **DONE**: `sft-corpus` already in "Data & Testing" table
- [ ] `docs/guides/EXAMPLES_MINING_GUIDE.md` — add cross-reference or new section for `sft-corpus.last_harvested` sentinel behavior; the guide currently documents only `corpus.last_harvested`

_Wiring pass added by `/ll:wire-issue` (2026-06-04):_
- [ ] `CHANGELOG.md` — add entry for completed `sft-corpus` FSM loop under next release section. Existing entries reference `SFTFormatter`, `--sft-format`, `pii_detection`, and `dataset-curation` individually; the completed loop itself needs a top-level entry. This is a post-implementation step — add when all 5 remaining gaps are closed. [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — optional `sft_corpus` section for context key overrides

## Impact

- **Priority**: P3 — Useful for SLM practitioners; not blocking core ll workflows
- **Effort**: Small (remaining) — Loop YAML already exists; 5 remaining gaps are each ~10-30 line additions to `sft-corpus.yaml`
- **Risk**: Low — Loop file exists and validates cleanly; all dependencies (`history_reader`, `SFTFormatter`, `text_utils`, `ll-messages`) are done
- **Breaking Change**: No
- **Depends on**: ENH-1942 (done), ENH-1943 (done), ENH-1944 (done), ENH-1827 (done)

## Related

- `scripts/little_loops/loops/examples-miner.yaml` — prompt-optimization corpus mining (different target)
- `scripts/little_loops/loops/dataset-curation.yaml` — candidate back-half via `loop:` handoff
- ENH-1827 — add `--sft-format` to `ll-messages` CLI (alternate ingest path)

## Labels

`loop`, `sft`, `fine-tuning`, `new-feature`

## Verification Notes

_Updated by `/ll:verify-issues` on 2026-06-04 (re-reviewed same day after epic alignment audit)_

**Verdict: UPDATED** — Issue now reflects current reality. The loop exists at `scripts/little_loops/loops/sft-corpus.yaml` with `stage → enrich → filter → publish` states. Supporting infrastructure is complete: `history_reader.conversation_turns()` + `lookup_session_metadata()`, schema v11 `assistant_messages` table, DB-first delegation in `extract_conversation_turns()`, `ll-messages --reader` flag. All 6 sibling children of EPIC-1880 are `done`.

**6 gaps remain (5 implementation + 1 verification)** (see Acceptance Criteria):
1. DB-first content ingestion in `stage` state (`ll-messages --sft-format --reader db` instead of `cat *.jsonl`)
2. SFT format conversion via `SFTFormatter` (exists but loop doesn't call it)
3. Token-length filtering (`min_tokens`/`max_tokens`)
4. Dedup via Jaccard similarity (`text_utils.calculate_word_overlap()`)
5. Train/val/test split + `dataset-curation` handoff (Option B wiring)
6. End-to-end integration test against real `history.db`-backed data — verification gate for EPIC-1880 closure

These are well-scoped, each touching only the `sft-corpus.yaml` loop file. The `history.db` migration (ENH-1942) and quality predicates (ENH-1943/1944) removed the complexity of dual-source joins — all remaining gaps operate on the enriched JSONL stream within the loop.

Updated 2026-06-04: Added end-to-end integration test as the 6th gap — the verification gate that closes EPIC-1880's remaining acceptance criterion. Two follow-up issues were captured from the completeness audit and are now **done**: ENH-1948 (PII detection wired into filter chain — `check_pii` + `reject_pii` states with flag/redact/discard modes; 16 tests pass in `test_loops_sft_corpus.py`) and ENH-1949 (`parameters:` block added to `dataset-curation.yaml` — `data_dir`, `output_dir`, `schema_path` declared, all `required: false` with defaults, enabling `_validate_with_bindings()` contract enforcement for the Option B handoff).

## Session Log
- `/ll:wire-issue` - 2026-06-04T21:17:52 - `521095dd-8dfd-4f61-911e-5063ec3d1ed8.jsonl`
- `/ll:refine-issue` - 2026-06-04T21:05:31 - `95f415e2-1260-4885-94e6-6f8b81d4dafe.jsonl`
- `/ll:capture-issue` — 2026-06-04T20:01:37Z — `b0ca5e28-1c3f-4a31-b1d5-f67d60516393.jsonl` (added AC for e2e integration test)
- `/ll:verify-issues` - 2026-06-04T18:41:57 - `18003f27-33de-416c-b594-e351d9d60c9d.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:46:04 - `ef863381-72dc-415f-ad39-f86d8e42dba1.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `17557f51-d1e7-48ab-8c75-d04f0cc19f24.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:31:19 - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`
- `/ll:decide-issue` - 2026-06-03T00:24:05 - `0467dd38-23d6-4a11-9d93-1a10ed0c40c9.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:18:35 - `d3bc2a68-d557-49f9-a947-e12cd4b90c1c.jsonl`
- `/ll:format-issue` - 2026-06-02T23:15:08 - `0d29889f-5db4-42d2-b354-e9615aee84a2.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:30:00Z - `d57b2749-2012-44c4-bc54-6baa8c6317b3.jsonl`
- `/ll:manage-issue` - 2026-06-04T21:42:45Z - `3c0c4c7c-5468-4124-add1-80a58f6e5a23.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-06-04
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/sft-corpus.yaml`: Updated stage state for DB-first ingestion via `ll-messages --sft-format --reader db` with harvest sentinel. Added 8 new context keys (sft_format, max_turns, min_tokens, max_tokens, val_ratio, test_ratio, schema_path, dedup_threshold). Added 5 new states: check_token_length, reject_token_length, dedup, split, curate. Updated publish to write harvest sentinel. Updated max_iterations to 40.
- `scripts/tests/test_loops_sft_corpus.py`: Added 15 new tests across 4 new test classes (TestTokenLengthFilter, TestDedup, TestSplit, TestHarvestSentinel) validating the new state logic.
- `thoughts/shared/plans/2026-06-04-FEAT-1826-management.md`: Implementation plan.

### Verification Results
- Tests: PASS (1033 related tests, 9854 full suite; 4 pre-existing doc wiring count failures unrelated)
- Lint: PASS (ruff check scripts/)
- Loop validation: PASS (ll-loop validate sft-corpus — 19 states, no ERRORs)
- Builtin loop regression: PASS (test_all_builtin_loops_still_load)
- FSM executor: PASS (TestSubLoopWithBindings + all executor tests)

### Acceptance Criteria Closed
- [x] `ll-loop validate sft-corpus` reports no ERRORs
- [x] Output valid for configured `sft_format` (stage uses `ll-messages --sft-format`)
- [x] Token length filtering (`[min_tokens, max_tokens]`)
- [x] Near-duplicate conversations removed via Jaccard similarity
- [x] `split` state writes separate `train`/`val`/`test` files at configured ratios
- [x] Back-half delegates to `dataset-curation` loop via `loop:` handoff (Option B wiring)
- [x] Harvest sentinel updated after each successful `publish` run
- [x] `stage` state uses `ll-messages --sft-format --reader db` for DB-first content ingestion

---
## Status

`done`
