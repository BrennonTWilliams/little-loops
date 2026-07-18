---
id: FEAT-2598
title: "F3 \u2014 Session-memory compaction: StreamingLLM eviction + 6-section schema"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-11T00:00:00Z'
discovered_date: 2026-07-11
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2486
labels:
- token-cost
- fsm
- compaction
- tier-3
decision_needed: false
confidence_score: 97
outcome_confidence: 66
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
---

# FEAT-2598: F3 — Session-memory compaction

## Summary

Add a session-memory compaction module combining two complementary passes:
(a) a **StreamingLLM sink-and-window eviction** pass — instant, structural,
keep the first-N sink *messages* + the recent window, drop the middle
(~80 LOC) — and (b) the cookbook's **6-section semantic summarization
schema** (User Intent / Completed Work / Errors & Corrections / Active Work
/ Pending Tasks / Key References), which fires in a background thread once
the soft threshold (7,500 tokens) is crossed. This is EPIC-2456 § Children
[TBD-12] — directly serves Goal #4 in the EPIC.

This is **not** a greenfield build: it extends the existing LCM compaction
surface already in the tree (`session_store._compact_session_conn` at
`session_store.py:2682` + the `summary_nodes` SQL schema at
`session_store.py:497`), reuses
ENH-1954's cross-session condensation, and reuses the existing
`history.compaction` config (4096-token budget) — no new config keys are
needed for the base mechanism.

## Motivation

Long-running FSM loops and `ll-parallel` sessions accumulate context that
gets re-embedded into every subsequent prompt. Eviction handles the
hard-limit swap-in instantly (lossless-enough structural pass); semantic
summarization catches up in the background at the soft threshold so the
two together keep long sessions cheap without stalling on synchronous
summarization. Vendor-measured cookbook anchors (`session_memory_compaction.ipynb`,
`automatic-context-compaction.ipynb`) show **88% reduction (12,847 → 1,526
tokens)** as the semantic-summarization upper bound and **58.6% (122,392
tokens saved)** on a 5-ticket workflow — those are cited as context for how
large the lever is, not as this issue's bar; see Acceptance Criteria for
the actual target.

## Use Case

_Added by `/ll:ready-issue` — required FEAT section, missing from prior passes:_

A developer kicks off a long-running `rn-implement` FSM loop against a large
EPIC. By hour three the session has accumulated tens of thousands of tokens
of tool output and prior turns, and every subsequent prompt re-embeds that
full history — inflating per-call cost and pushing the session toward the
model's context window. With this feature: once the session crosses the
7,500-token soft threshold, a background thread produces a 6-section summary
(User Intent / Completed Work / Errors & Corrections / Active Work / Pending
Tasks / Key References) without stalling the loop; if the session instead
hits a hard limit before that summary lands, the instant sink-and-window
eviction pass drops the middle of the transcript (preserving system/CLAUDE.md
blocks and the most recent turns) so the loop can keep running rather than
fail outright. The developer never has to manually intervene or restart the
loop — the session's context footprint stays bounded automatically.

## Current Behavior

- `session_store._compact_session_conn` and the `summary_nodes` SQL schema
  (`session_store.py:2682` / `:497`) already implement cross-session condensation
  (ENH-1954) at the existing 4096-token `history.compaction` budget
  boundary.
- No instant structural eviction pass exists — compaction is
  summarization-only today, which means a hard-limit hit has no fast
  fallback while summarization catches up.
- No 6-section schema (User Intent / Completed Work / Errors & Corrections
  / Active Work / Pending Tasks / Key References) — existing summaries use
  whatever shape ENH-1954 produces.

## Expected Behavior

- A new `compaction/instant.py` module exposes both passes:
  - **Eviction**: keeps the first-N sink *messages* (not tokens — this
    project operates at message granularity, not KV-cache granularity)
    plus the most recent window; drops the middle. Must preserve
    system/CLAUDE.md blocks unconditionally.
  - **Semantic summarization**: fires in a background thread once the
    soft threshold (7,500 tokens) is crossed; produces a summary in the
    6-section schema.
- A new `compaction/result.py` module exposes `CompactResult` — a thin
  Python dataclass wrapper (`summary_message`, `compacted_messages`,
  `summary_text`, `context_token_estimate`) over the *existing*
  `summary_nodes` SQL rows. No schema change.
- A new skill `skills/ll-compact-session/SKILL.md` lets a user manually
  trigger compaction on the current session.
- Eviction+summarization together land in the 50–70% context-size
  reduction range on a locked trace set (see Acceptance Criteria) without
  measurable quality regression on a held-out eval set.

## Proposed Solution

1. **`scripts/little_loops/compaction/instant.py`** (new, ~270 LOC):
   - `evict_sink_and_window(messages, sink_n, window_n)` — the
     StreamingLLM-style structural pass (~80 LOC); message-granularity,
     preserves system/CLAUDE.md blocks by construction (never evicted).
   - Letta-style sliding-window selection for the semantic pass (~150
     LOC): `goal_tokens = (1 - sliding_window_percentage) × context_window`,
     an `is_valid_cutoff` predicate adapted to this project's
     chunk-grouping boundaries, `APPROX_TOKEN_SAFETY_MARGIN = 1.3`
     byte/4 heuristic, monotonic-update path that reuses ENH-1954's
     cross-session condensation.
   - `summarize_6_section(messages) -> str` — background-thread
     summarizer producing the cookbook schema.
2. **`scripts/little_loops/compaction/result.py`** (new, ~50 LOC):
   - `CompactResult(summary_message, compacted_messages, summary_text,
     context_token_estimate)` dataclass, populated from existing
     `summary_nodes` rows via `session_store._compact_session_conn`.
3. **`skills/ll-compact-session/SKILL.md`** (new): manual-trigger skill
   invoking the same compaction path used automatically at the soft
   threshold.
4. Wire the soft-threshold trigger (7,500 tokens) into whichever call
   site currently invokes `session_store._compact_session_conn` at the
   4096-token cross-session boundary — confirm during implementation
   whether that's a shared entry point or needs a new one.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

5. **Register the CLI entry point** — add `ll-compact-session =
   "little_loops.cli:main_compact_session"` to `scripts/pyproject.toml`
   `[project.scripts]`, define + export `main_compact_session` in
   `scripts/little_loops/cli/__init__.py` (`__all__`), and add the
   dispatch/module in `cli/session.py` (or a new `cli/compact_session.py`)
   — keeping it visibly distinct from the existing retention `ll-session
   compact` subcommand.
6. **Register the skill** — add `skills/ll-compact-session/` to
   `.claude-plugin/plugin.json`, and decide the SKILL.md convention
   (full-content vs. Codex-bridge stub + new `commands/compact-session.md`).
7. **Verify the `rebuild()` output contract** — confirm the eviction
   pre-pass does not silently change `counts["summaries"]` semantics
   surfaced by `ll-session rebuild` / `backfill --and-rebuild`
   (`cli/session.py:582-588`, `--json`).
8. **Guard the downstream reader** — run `test_history_reader.py`
   `TestSummaryDagRetrieval` and confirm `condensed_nodes_for_issue()`
   (feeding `ll-history-context`) still resolves `kind='condensed'
   AND level=0` nodes unchanged.
9. **Update docs** — `docs/ARCHITECTURE.md:750` (Token cost layer row),
   `docs/reference/API.md` (new module reference + `condensed_nodes_for_issue`
   accuracy), `CONTRIBUTING.md:310` (file-tree comment), and the
   `.claude/CLAUDE.md` `## CLI Tools` listing for `ll-compact-session`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 4 resolved — there is a shared *core* but two distinct *triggers*.**
  Both `compact_session(session_id, db, *, config)` (public single-session
  API, `session_store.py:2930`) and `rebuild(db, config, max_sessions)`
  (batch pipeline, `session_store.py:3161` → `_compact_sessions:2775` →
  loop call at `:2807`) ultimately call the shared low-level worker
  `_compact_session_conn` (`session_store.py:2682`). Each trigger re-reads
  `history.compaction` independently and constructs its own
  `CompactionConfig`. The soft-threshold trigger is best wired at the
  shared core (`_compact_session_conn`) or as a new pre-pass invoked by
  both, rather than duplicated per trigger.
- **Compaction is opt-in.** `CompactionConfig.enabled` defaults to `False`
  (`config/features.py:995`); `_compact_sessions` returns `0` immediately
  when disabled (`session_store.py:2799-2800`). The new eviction pass must
  decide whether it is gated on the same `enabled` flag or always-on for
  the instant/structural path.
- **⚠ Naming-collision hazard for the skill/CLI.** A *different*
  `compact()` function (`session_store.py:3357`, ENH-1906/ENH-2581
  retention sweep over `raw_events`, `kind='retention'`) already exists,
  and `ll-session` already exposes a `compact` subcommand
  (`cli/session.py:216-233`) bound to it. That is a different compaction
  axis than this issue's LCM/`compact_session` summarization. Name the new
  skill/entry point to avoid confusion with the existing retention
  `compact` (e.g. keep `ll-compact-session` distinct from `ll-session
  compact`).
- **Existing summarizer is reusable for the 6-section pass.**
  `_summarize_block` (`session_store.py:2506`, LCM Algorithm 3 three-level
  escalation) calls `_call_llm_for_summary` (`session_store.py:2581`),
  which shells out via `resolve_host().build_blocking_json(...)` (the
  sanctioned host-CLI path — do not add raw `"claude"` literals per
  `.claude/CLAUDE.md` § Host CLI Abstraction). Model `summarize_6_section`
  on this rather than reinventing the host invocation.
- **`goal_tokens` calc has an existing helper.** The sliding-window
  formula `goal_tokens = (1 - sliding_window_percentage) × context_window`
  can reuse `context_window.py:context_window_for()` +
  `MODEL_CONTEXT_WINDOW` for the per-model context-window size.

### Decision Resolutions

_Added by `/ll:refine-issue --auto` — two implementation-time decisions that
`/ll:confidence-check` flagged as open are resolved below by codebase evidence:_

#### Decision 1 — Skill/CLI authoring convention

**Option A**: Author full content directly in `skills/ll-compact-session/SKILL.md`
(the map-dependencies / go-no-go full-content template).

**Option B**: Ship `skills/ll-compact-session/SKILL.md` as a thin Codex-bridge
stub and first create a companion `commands/compact-session.md` holding the
real content.

> **Selected:** Option A (full content in the skill) — matches the uniform
> repo convention that bare-named skills hold real content and `ll-*` variants
> are thin Codex bridges.

**Recommended**: Option A — full content in the skill. All 30 existing
`skills/ll-*/SKILL.md` files are thin Codex-bridge stubs (12–26 lines) that
bridge to a target that *already existed* (`skills/ll-help/SKILL.md:9-12`,
`skills/ll-go-no-go/SKILL.md:23-27` → `skills/go-no-go/SKILL.md`); none were
created backward from a stub. The bare-named skill is where real content lives
(`skills/map-dependencies/SKILL.md`, 252 lines, has no `commands/map-dependencies.md`
at all). Inventing a stub-only `commands/compact-session.md` just to satisfy the
bridge pattern would invert the convention. **Refinement**: to match the
convention exactly, put full content in `skills/compact-session/SKILL.md`
(bare name) and, only if Codex parity is required, add a thin
`skills/ll-compact-session/SKILL.md` stub bridging to it — mirroring how
`ll-go-no-go` bridges to `go-no-go`.

#### Decision 2 — Does the eviction pass gate on `CompactionConfig.enabled`?

**Option A**: Gate the new eviction pass on the existing
`CompactionConfig.enabled` flag (`config/features.py:995`, default `False`) —
consistent with the summarization path.

**Option B**: Run eviction always-on, independent of `CompactionConfig.enabled`
(optionally behind a *new* dedicated `history.compaction.eviction_enabled`
kill-switch defaulting `True`, never reusing `enabled`).

> **Selected:** Option B (eviction always-on, independent of
> `CompactionConfig.enabled`) — that flag gates opt-in LLM summarization cost,
> not structural safety; gating eviction on it defeats its instant-fallback
> purpose for the 100% of installs that default it off.

**Recommended**: Option B — always-on. `CompactionConfig.enabled` gates an
opt-in *LLM cost* ("Disabled by default to avoid background LLM calls without
user opt-in," `config/features.py:982-993`), not structural safety.
`_compact_sessions` (`session_store.py:2775-2800`) and `cli/history_context.py:334`
both treat the flag as "is summarization active." Eviction is a lossless-enough
structural pass with no LLM cost; gating it on `enabled` means the 100% of
installs that never opted into `history.compaction` get zero protection against
context blowup — exactly the "hard-limit hit, no fast fallback" gap this issue
cites as its motivation (`:67-69`). Since eviction sits on a different axis
(structural/deterministic vs. semantic/LLM), give it its own concern: always-on,
or a dedicated new flag rather than overloading `enabled`.

## Integration Map

### Files to Modify

- `scripts/little_loops/compaction/instant.py` (new)
- `scripts/little_loops/compaction/result.py` (new)
- `scripts/little_loops/session_store.py` — verify/extend
  `_compact_session_conn` call sites to invoke the new eviction pass
  ahead of (or alongside) existing summarization

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/pyproject.toml` — add `ll-compact-session =
  "little_loops.cli:main_compact_session"` to `[project.scripts]`
  (`:52-94`), following the `ll-<name> = "little_loops.cli:main_<name>"`
  convention [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — add + export
  `main_compact_session` in `__all__` (models `main_session` at `:76`,
  `:122`) [Agent 1 finding]
- `scripts/little_loops/cli/session.py` (or a new `cli/compact_session.py`
  module) — the entry point importing `evict_sink_and_window` /
  `summarize_6_section` from `compaction/instant.py` and `CompactResult`
  from `compaction/result.py`. **Naming-collision guard**: this file
  already binds a *different* `compact` subcommand (`:216-233`, dispatch
  `:624-643`) to the retention `compact()` (`session_store.py:3357`,
  ENH-1906/ENH-2581 `kind='retention'`) — keep `ll-compact-session`
  visibly distinct from `ll-session compact` [Agent 1 + Agent 2 finding]
- `.claude-plugin/plugin.json` — register the new `skills/ll-compact-session/`
  entry [Agent 1 finding]
- `.claude/CLAUDE.md` — add `ll-compact-session` to the `## CLI Tools`
  listing (repo convention: every `ll-*` entry point is documented there)
  [wiring inference]
- `commands/compact-session.md` (decision point) — all `skills/ll-*/SKILL.md`
  are Codex-bridge stubs pointing at a `commands/*.md`; there is no
  `commands/compact-session.md`, so either author `ll-compact-session/SKILL.md`
  with full content OR create this companion command first [Agent 1 +
  existing research finding]

### Dependent Files (Callers/Importers)

- The not-yet-filed F8 child (EPIC-2456 § Children Tier 3, subagent
  handoff compaction) will import `compaction/instant.py` from a new
  `subagents/handoff.py` — this issue's module is a hard dependency for
  that future work; no action needed here beyond keeping the module's
  public surface stable.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store.py` — **`rebuild()` (`:3161`) is the
  sole production call site of `_compact_sessions`** (`:2775-2929`). If the
  new eviction pre-pass changes `_compact_session_conn` from "purely
  additive" to deleting/evicting `message_events`, that behavior flows
  through `rebuild()`'s `counts["summaries"]` return value — printed via
  `logger.success(...)` in `cli/session.py:580-589` and emitted as
  `--json` output. Treat `rebuild()`'s output contract as a coupling point
  [Agent 2 finding]
- `scripts/little_loops/history_reader.py` — `condensed_nodes_for_issue()`
  reads `summary_nodes WHERE kind='condensed' AND level=0` (the downstream
  consumer feeding `ll-history-context <id>`'s `## Prior Work (condensed)`
  block). Since `CompactResult` wraps existing rows with no schema change,
  this must not regress: preserve `kind`/`level` semantics for existing
  `condensed` nodes [Agent 2 finding]
- `scripts/little_loops/cli/history_context.py` — reads
  `_cfg.history.compaction.enabled` (`:334`) to gate condensed-node
  loading; confirm the `enabled` flag's meaning is unchanged if eviction
  is gated on it [Agent 1 + Agent 2 finding]
- `scripts/little_loops/context_window.py` — `context_window_for()` (`:39`)
  + `MODEL_CONTEXT_WINDOW` (`:19`); the new sliding-window `goal_tokens`
  calc imports these (dependency, not caller) [Agent 1 finding]
- `scripts/little_loops/config/features.py` — `CompactionConfig` (`:980-1014`)
  consumed via `BRConfig.history.compaction` (established pattern in
  `cli/history_context.py`); the eviction pass must decide if it gates on
  `CompactionConfig.enabled` (defaults `False`, `:995`) or is always-on
  for the instant/structural path [Agent 1 + Agent 2 finding]

### Similar Patterns

- `session_store._compact_session_conn` + `summary_nodes` schema
  (`session_store.py:2682` / `:497`) — the existing LCM compaction surface this
  issue extends, not replaces.
- ENH-1954 — cross-session condensation; the monotonic-update path in
  the sliding-window selector should reuse this rather than duplicate it.

### Tests

- `scripts/tests/test_compaction.py` (new) — eviction preserves
  system/CLAUDE.md blocks (regression test); soft/hard threshold
  triggers; 6-section schema shape; 50–70% reduction range on the
  locked trace set.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_compaction.py` (new) — **add a `message_events`
  row-count-unchanged regression** paired with the system/CLAUDE.md
  preservation test: no existing test asserts eviction is non-destructive,
  and the current "purely additive" guarantee (issue `:431`, Codebase
  Research Findings) must be re-proven if the pre-pass drops middle
  messages structurally [Agent 3 finding]
- `scripts/tests/test_session_store.py` — `class TestCompactSession`
  (`:2143+`) tests assume purely-additive semantics and need
  re-validation once eviction wires into `_compact_session_conn`:
  `test_compact_session_creates_leaf_nodes` (`:2167`),
  `test_compact_session_creates_spans` (`:2208`, span-linkage may change
  for dropped messages), `test_compact_session_condensed_node_when_multiple_leaves`
  (`:2233`), `test_backfill_with_compaction_enabled` (`:2292`) [Agent 3
  finding]
- `scripts/tests/test_session_store.py` — **log-string coupling**:
  `test_escalation_logs_warning` (`:2719-2730`) asserts the literal
  `"escalating to level 2"` from `_summarize_block` (`:2549-2554`); if
  `summarize_6_section` reuses/wraps `_summarize_block`, keep this string
  intact [Agent 2 finding]
- `scripts/tests/test_ll_session.py` — `class TestCompactSubcommand`
  (`:988-1021`) covers the *retention* `compact` axis; **do not name the
  new eviction test class `TestCompactSubcommand`** (collision) [Agent 2 +
  Agent 3 finding]
- `scripts/tests/test_history_reader.py` — `class TestSummaryDagRetrieval`
  (`:963-1254`) bootstraps DB state via `compact_session(...)`; re-run to
  confirm the eviction pre-pass doesn't alter the DAG it reads [Agent 3
  finding]
- `scripts/tests/test_merge_coordinator.py` — threading-test template for
  `summarize_6_section`'s background-thread firing. Use the **ad-hoc
  raw-thread pattern** (`:922-928`, `:958-968`: spawn → `.join(timeout=)`
  → assert on resulting `summary_nodes` row), not the persistent
  `TestThreadLifecycle` coordinator pattern (`:1507`), since the
  summarizer is fire-once, not a `start()/shutdown()` loop [Agent 3
  finding]

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section (shared across
  EPIC-2456 children).
- `docs/reference/API.md` — document `compaction/instant.py` +
  `compaction/result.py`.

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md` (`:755`) — the exact "Token cost layer" table row
  for `compact_session()` documents current behavior; update its prose to
  mention the eviction pre-pass + 6-section schema [Agent 2 finding]
- `docs/reference/API.md` (`:7353-7377`) — the `### condensed_nodes_for_issue`
  section documents the `history.compaction.enabled` dependency + `## Prior
  Work (condensed)` integration; verify it stays accurate under the new
  `CompactResult` semantics [Agent 2 finding]
- `CONTRIBUTING.md` (`:310`) — file-tree comment names `compact_session`
  in the `session_store.py` description; extend to reflect the new
  eviction pass [Agent 2 finding]

### Configuration

- N/A — reuses existing `history.compaction` config (4096-token budget);
  no new config keys required for the base mechanism.

_Wiring pass added by `/ll:wire-issue` (advisory — no change required if
the 7,500-token soft threshold stays hardcoded):_

- `scripts/little_loops/config-schema.json` (`:1819-1852`) — the
  `history.compaction` block would only need new properties **if** the
  soft threshold / `sink_n` / `window_n` are made configurable. **Precision
  note**: a *different* `compaction` concept exists at `:1333-1366` (the
  `pre_compact` hook's rubric-gated context-window compaction) — be
  explicit about which block any schema PR touches [Agent 2 finding]
- `.ll/ll-config.json` (`:118-123`) — **this repo's own DB has
  `history.compaction.enabled: true`**, so little-loops' own `.ll/history.db`
  is a live consumer: a destructive eviction pass affects this repo's
  history on the next `rebuild`/`backfill` run, not just downstream
  projects [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ **Anchor correction (RESOLVED by `/ll:ready-issue` on 2026-07-18):** the
> `session_store.py:1747+` reference used throughout this issue (Summary,
> Current Behavior, Files-to-Modify, Similar Patterns) was stale — line 1747
> is unrelated `issue_snapshots`/frontmatter-backfill logic. All `:1747`
> occurrences, plus every other line-number anchor in this issue, have been
> rewritten below and throughout the file against the current tree (~320
> lines were added to `session_store.py` between the `/ll:refine-issue` pass
> and this correction).

**Existing compaction surface (verified anchors):**
- `summary_nodes` table DDL — `session_store.py:497-507` (in the migration
  block starting `:482`; `level` column added v12 at `:546`). Columns:
  `id, kind, content (single opaque TEXT — no sections today), tokens,
  parent_id, session_id, ts_start, ts_end, created_at, level`. Companion
  `summary_spans(summary_id, message_event_id)` at `:508-512`.
- `_compact_session_conn` — `session_store.py:2682-2774` (greedy
  single-pass block grouping by `_estimate_tokens`, `INSERT OR IGNORE`
  idempotency via partial unique indexes; **purely additive — never
  deletes `message_events`, confirming no eviction pass exists today**).
- `_compact_sessions` — `session_store.py:2775-2929` (ENH-1954
  cross-session condensation; the **monotonic-update / re-parent path** to
  reuse is at `:2914-2918`, `WHERE id IN (...) AND parent_id IS NULL` — a
  node is parented exactly once, never re-parented on re-run).
- `compact_session` (public wrapper) — `session_store.py:2930`.
- `_estimate_tokens` — `session_store.py:2501-2503`, `len(text) // 4` ("LCM
  convention"). This is the byte/4 heuristic to base
  `APPROX_TOKEN_SAFETY_MARGIN = 1.3` on; same convention independently in
  `doc_counts.py:353`.
- `_summarize_block` — `session_store.py:2506-2580`;
  `_call_llm_for_summary` — `session_store.py:2581-2681`.
- `CompactionConfig` — `config/features.py:980-1014`; schema in
  `config-schema.json:1819-1852`.

**New sub-package layout (templates to model after):**
- `scripts/little_loops/dependency_mapper/__init__.py:61-93` and
  `scripts/little_loops/issue_history/__init__.py` — the `models.py`
  (pure dataclasses) + logic-module split with a curated `__all__` and
  private helpers re-exported for test access. Model `compaction/__init__.py`
  on this.
- `CompactResult` dataclass models: `FixResult`
  (`dependency_mapper/models.py:105-118`) and `SkillBudgetResult`
  (`doc_counts.py:269-277`) — typed fields, `field(default_factory=...)`
  for mutable containers, docstring naming field semantics. Note existing
  `session_store` query fns return `list[dict]` via `dict(row)`, not
  dataclasses — `CompactResult` is intentionally new in wrapping rows as a
  dataclass.

**Background-thread pattern (semantic summarizer):**
- `parallel/merge_coordinator.py:81-93` — closest analog: `threading.Thread(
  target=..., daemon=True, name=...)` + `Queue` handoff + `threading.Event`
  shutdown, dispatched on a triggering event. Simpler daemon-thread forms:
  `fsm/host_guard.py:277`, `transport.py:526`.

**Skill authoring:**
- `skills/map-dependencies/SKILL.md` is the real full-content template
  (frontmatter with `disable-model-invocation`, `allowed-tools`; `## When
  to Activate`, `## Arguments`, `## How to Use`, `## Examples` table).
  **Note:** all `skills/ll-*/SKILL.md` are Codex-bridge stubs pointing at a
  `commands/*.md`; there is no `commands/compact-session.md`, so
  `ll-compact-session/SKILL.md` needs full content OR a companion command
  created first — pick a convention during implementation.
- If a one-shot CLI is needed, add `ll-compact-session =
  "little_loops.cli:main_compact_session"` to `scripts/pyproject.toml`
  `[project.scripts]` (`:51-95`), following the `ll-<name> =
  "little_loops.cli:main_<name>"` convention.

**Test conventions:**
- Model `test_compaction.py` on `class TestCompactSession`
  (`scripts/tests/test_session_store.py:2143+`): per-class
  `_make_db_with_messages` builder, `tmp_path` SQLite DBs via `connect(db)`,
  explicit run-twice idempotency asserts, and **mock `subprocess` so
  summarization never shells out to the real host CLI** (`:2244`).

## Acceptance Criteria

- Compaction triggers at the configured soft threshold (default 7,500
  tokens).
- Eviction preserves system/CLAUDE.md blocks — covered by a regression
  test.
- The eviction+summarization combo reduces context size to the **50–70%
  range** on a locked trace set, without measurable quality regression on
  a held-out eval set. (The cookbook's 88% figure is the
  semantic-summarization upper bound, reserved for a possible future
  upgrade — not this issue's bar.)
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: instant eviction pass, 6-section semantic summarization,
  `CompactResult` wrapper, manual-trigger skill.
- **Out**: subagent handoff compaction (future F8 child — will import
  this module but is filed separately); parent-prefix cache hoisting
  (also future F8 scope); any change to `cache_control` (Claude-only
  primitive, tracked under the separate not-yet-filed F1 child).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Children Tier 3 [TBD-12], Goal #4 |
| `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` | EPIC-CHILD-6 spec detail (sliding-window algorithm, module layout) |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier 3 prioritization rationale, vendor-measured anchors |
| ENH-2486 | Adjacent `fsm/runners.py` prompt-assembly leverage point (not a blocking dependency) |

## Impact

- **Priority**: P2 — high-leverage, compounds across every long-running
  loop/session, but no current production user is blocked on its absence.
- **Effort**: Medium — ~320 LOC (270 instant.py + 50 result.py), builds on
  existing LCM surface rather than net-new infrastructure.
- **Risk**: Low — well-trodden pattern (eviction + summarization); no new
  pip deps; no schema change.
- **Breaking Change**: No — additive; existing compaction behavior
  unchanged unless the new soft-threshold trigger is wired in as a strict
  addition ahead of the existing summarization-only path.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-16; updated 2026-07-17 after
`/ll:decide-issue` resolved both open decisions_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 66/100 → LOW

### Outcome Risk Factors
- Moderate depth: the sliding-window selector integrates with ENH-1954's
  cross-session condensation and touches `_compact_session_conn`'s
  purely-additive contract — regression risk against 4 existing test classes
  (`TestCompactSession`, `TestSummaryDagRetrieval`, `TestCompactSubcommand`,
  `test_escalation_logs_warning`) that assume current behavior.
- Broad enumeration across ~13 touch sites (core module, CLI wiring, skill
  registration, docs) — largely mechanical registration work, but increases
  the chance of a missed wiring step (e.g. `plugin.json` registration,
  `__all__` export).

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-18T05:08:35 - `b50b5d3c-2ef8-4088-bf21-2dd93301043a.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `b50b5d3c-2ef8-4088-bf21-2dd93301043a.jsonl`
- `/ll:decide-issue` - 2026-07-17T04:04:52 - `9b2a6c2d-1f82-482f-81a0-7bf1d1c2e405.jsonl`
- `/ll:confidence-check` - 2026-07-16T00:00:00Z - `cf3b0ae1-2f93-485f-aec6-d9be1ab4d928.jsonl`
- `/ll:wire-issue` - 2026-07-17T03:54:06 - `227c564e-bdcb-41dc-a8dd-8daf6484b451.jsonl`
- `/ll:refine-issue` - 2026-07-17T02:46:17 - `26f8f56e-63ed-48a4-831c-98fbdf32a442.jsonl`
- `/ll:capture-issue` - 2026-07-11T00:00:00Z - filed from EPIC-2456 § Children [TBD-12] per `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` (EPIC-CHILD-6) and `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` (Tier 3).
