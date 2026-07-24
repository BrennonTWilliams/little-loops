# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.150.0] - 2026-07-23

### Added

- FEAT-2354: Built-in FSM loop that generates reusable Claude Code workflows
- FEAT-2711: FSM session reuse for continuity-of-reasoning state chains
- FEAT-2747: Assistant-inclusive session compaction (message_events + assistant_messages)
- FEAT-2751: autodev: generalize reconcile plateau gate beyond the spike path (stagnation backstop)

### Fixed

- BUG-2726: refine-to-ready-issue diagnose prompt carries no failure evidence, producing confabulated wrong-run diagnoses
- BUG-2731: FSM treats exit-143-after-result as a terminal action failure instead of retryable infra teardown, discarding in-flight subagent work
- BUG-2744: autodev's check_guard2_verdict can read stale cross-issue captured state
- BUG-2750: next-issue/next-issues log spurious "unknown issue" warnings for done/deferred/cancelled blockers
- BUG-2752: autodev: check_guard2_verdict regex misses real issue-size-review skip line
- BUG-2753: README overstates OpenCode/Pi host adapter support
- BUG-2754: Verify PyPI publication status matches README install instructions

### Changed

- ENH-2493: Persist ll-harness / eval outcomes into history.db
- ENH-2498: Capture prompt-optimization outcomes into history.db
- ENH-2506: Capture hook execution telemetry into history.db
- ENH-2507: Persist context-window pressure measurements into history.db
- ENH-2512: Persist read-side audit / review outcomes into history.db
- ENH-2719: EPIC-2456 realized-savings verification and closure gate
- ENH-2720: Default-flip tranche: orchestration.request_path cli → sdk/batch after parity verification
- ENH-2722: ll-ctx-stats waste view over history.db (split from ENH-2712)
- ENH-2727: autodev refine_current on_error collapses infra kills into the refine_failed ledger reason
- ENH-2736: Scope codegraph staleness dirty-file check to source-relevant paths
- ENH-2737: orchestration.request_path: fall back to cli on missing anthropic package or API key
- ENH-2739: harness_events schema, kind registration, and record_harness_event() recorder
- ENH-2740: Wire ll-harness producer to write harness_events (signature refactor + DSL per-task rows)
- ENH-2741: harness_events read API, ll-session CLI wiring, and docs
- ENH-2742: Verify state's classify() should distinguish "missing npm script" config error from real test failure
- ENH-2743: Add closed_via_recovery counter to sprint-refine-and-implement summary.json for parked-then-closed issues
- ENH-2745: Tier 0 before/after cost gate blocked on model-pricing drift
- ENH-2746: F3 compaction shrink ratio measured outside 50-70% gate band
- ENH-2748: Suppress flag for capture-reachability validator warning
- ENH-2749: set-status --reason can't express already_fixed for done transitions

### Documentation

- docs(readme): fix harness-optimize command name and CLI tool count; capture follow-up bugs (c4fa6a65)
- docs(api): document FailureType/classify_failure incl. INFRA_RETRY variant (4d8c49b6)
- docs(claude-md): add dependency-minimization guideline to code style (047516e1)

### Other

- style(tests): apply ruff format to test files (bc97d06a)

## [1.149.0] - 2026-07-22

### Added

- FEAT-2672: F1-prereq (b) — Deferred tool loading
- FEAT-2673: F1 — cache_control: ephemeral integration + cache-marking cost oracle
- FEAT-2674: F10 — Speculative cache warming hook (+ max_tokens=0 alt)
- FEAT-2703: init/introspect.py: manifest-declared commands + src_dir detection with provenance
- FEAT-2705: Rewrite /ll:init skill as plan → inspect → apply agentic flow
- FEAT-2710: Message Batches API request path (50% discount on batchable automation)
- FEAT-2716: Wire live Anthropic SDK/Batches API dispatch into fsm/executor.py
- EPIC-2670: Generic `ll-queue` — heterogeneous work-item queue on a shared runner abstraction

### Fixed

- BUG-2685: refine-to-ready-issue phantom-convergence on max_steps exhaustion
- BUG-2688: audit-docs crashes with context_length/concurrent-agent errors on full-scope unscoped file discovery
- BUG-2706: cli_event_context crashes every ll-* CLI when history.db is locked
- BUG-2718: run_claude_command's fixed 30s post-stream-close kill fires while legitimate synchronous parallel subagent work is still in flight
- BUG-2728: done issues still land in vestigial .issues/completed/, making blocked_by resolution report them as unknown and permanently blocking dependents
- BUG-2729: headless automation sessions that end their turn while awaiting subagents are torn down by claude -p shutdown (SIGTERM/exit 143), discarding in-flight work
- BUG-2730: headless automation prompt path carries no "stay in turn" contract, and parallel-agent skills invite the end-turn-and-wait pattern that triggers exit 143
- BUG-2732: finalize_decomposed_parent() moves closed parents into legacy .issues/completed/, reintroducing the directory BUG-2403 tried to retire
- BUG-2733: blocked_by resolution treats a done blocker parked in .issues/completed/ as unknown, permanently blocking dependents
- BUG-2734: autodev defers a ready, deliberately-non-decomposable Very Large issue as low_readiness instead of implementing it
- BUG-2735: evaluation-quality.yaml's sample state reads confidence_score/outcome_confidence/formatted fields that ll-issues list --json never returns
- fix(fsm): kwarg-gate automation_profile in action_runner.run() (72477db)

### Changed

- ENH-2466: Mirror Learning Test Registry records into history.db / search_index
- ENH-2495: Record session-lifecycle / handoff events into history.db
- ENH-2505: Link subagent session-tree (parent→child) into history.db
- ENH-2509: Capture worktree lifecycle events into session_lifecycle_events
- ENH-2686: recheck_set should retry an abandoned autodev-queue residual, not just newly-detected descendants
- ENH-2689: autodev: add reconcile step for stale issue-body sections after spike/refine plateau
- ENH-2690: rn-refine preflight_check heading match flags legitimate decompose rewrites as data loss
- ENH-2691: rn-refine synth_dispatch computes worker fail flag but never gates on it
- ENH-2692: rn-refine final_score rubric verdict has no effect on control flow
- ENH-2701: Call detect_documents() from _run_yes (headless/TUI parity)
- ENH-2702: Score template detection by match count instead of first-alphabetical
- ENH-2704: Enrich --plan with provenance + ambiguities; divergence warnings on re-init
- ENH-2707: rn-refine — soft-deadline drain: reserve wall-clock for synthesis so a timeout still yields a written-back partial plan
- ENH-2708: plan-node-refine sub-loop outcome durability
- ENH-2709: rn-refine run-dir observability (summary.json + writeback.json)
- ENH-2713: Per-state model pinning in loop YAML (haiku for verdict states)
- ENH-2714: Automation-context static-prefix pruning for FSM invocations
- ENH-2715: decide-issue --auto should reformat found-but-unstructured open decisions
- ENH-2717: autodev run_decide → run_size_review path wastes a full size-review call when decide-issue is killed mid-turn
- ENH-2721: usage_events run_id column + live per-invocation writer (split from ENH-2712)
- ENH-2723: usage_events run_id column — schema migration (v29)
- ENH-2724: usage_events live per-invocation run_id writer (on_usage_detailed)
- ENH-2725: usage_events run_id backfill on historical rows
- ENH-2504: Persist verification / readiness-review verdict outcomes into history.db (verdict_events, v33)

### Other

- docs: document SDK/Batches dispatch path (orchestration.request_path) (200799d)
- style: apply ruff format line-wrapping to executor and spike test (2aff155)

## [1.148.0] - 2026-07-19

### Added

- FEAT-2672: F1-prereq (b) — Deferred tool loading
- FEAT-2673: F1 — cache_control: ephemeral integration + cache-marking cost oracle
- FEAT-2674: F10 — Speculative cache warming hook (+ max_tokens=0 alt)
- FEAT-2598: F3 — Session-memory compaction: StreamingLLM eviction + 6-section schema
- FEAT-2665: Cross-run resurfacing/triage for automation-deferred issues
- FEAT-2671: F1-prereq (a) — Content-hash fragment store
- FEAT-2675: F4a — Heuristic prompt compressor core + config gate wiring
- FEAT-2679: F1-prereq (c) — Tool-definition JSON schema catalog for the Anthropic Messages API
- FEAT-2680: F1-prereq (c.1) — Catalog-assembly function deriving Anthropic tool definitions from skill/command/agent frontmatter
- FEAT-2681: F1-prereq (c.2) — Learning test: anthropic SDK/API accepts cache_control on a tool-definition block
- FEAT-2682: ll-queue persistence layer and add/list/status/remove commands
- FEAT-2683: ll-queue run: serial dequeue-and-execute worker loop
- FEAT-2684: ll-loop run --queue compat shim and ll-loop queue migration
- FEAT-2478: F5 — OTel gen_ai.usage.* emission + streaming parity + UUID + provider addendum
- FEAT-2652: Per-EPIC base-branch declaration + sprint-creation validation
- FEAT-2567: /ll:spike skill — prove unprecedented mechanisms in isolation before implementation
- EPIC-2570: Spike Workflow — Skill, Confidence Flag & Autodev Routing

### Fixed

- BUG-2685: refine-to-ready-issue phantom-convergence on max_steps exhaustion
- BUG-2662: code-run-gate interpolation crash falsely tags committed work GATE_FAILED_INFRA
- BUG-2650: Root-cause the doc-wiring string test flake under the epic verify gate
- BUG-2659: audit-issue-conflicts skill unreachable via /ll: slash command
- BUG-2644: Add append-only fragment storage for .ll/decisions.yaml to remove id/merge collisions
- BUG-2645: Add a fragment-update primitive for in-place decision mutation
- BUG-2646: Extend decisions validation gates to the fragment path
- BUG-2647: Update docs and config schema for .ll/decisions.d/ fragment storage
- BUG-2648: get_project_folder encoding drops dots, breaks session resolution in worktrees
- BUG-2649: Epic verify gate false-negatives on two non-hermetic tests under injected PYTHONPATH
- BUG-2651: ll-history-context <ID> silently returns empty for hyphenated issue IDs
- BUG-2654: autodev spike remedy bypassed for spike_needed issues on the decide path

### Changed

- ENH-2689: autodev: add reconcile step for stale issue-body sections after spike/refine plateau
- ENH-2686: recheck_set should retry an abandoned autodev-queue residual, not just newly-detected descendants
- ENH-2664: Tag automation deferral with a reason discriminator
- ENH-2668: Extract shared runner abstraction (RunnerType enum + ActionSpec) from ll-harness/ll-action/ll-loop
- ENH-2666: Reconcile autodev vs rn-implement "not ready" handling
- ENH-2678: Wire go-no-go correction_penalty into scoring + add ll-config get CLI
- ENH-2492: Capture orchestration run outcomes (ll-auto/ll-parallel/ll-sprint) into history.db
- ENH-2463: Add per-loop-run summary row to history.db
- ENH-2497: Discriminate sub-agent / Task spawns in history.db
- ENH-2511: Capture MCP tool-call telemetry in tool_events
- ENH-2660: Add --epic flag to rn-implement for auto-resolving children
- ENH-2661: Add learning state badge glyph to _ACTION_TYPE_BADGES
- ENH-2657: Detect an abandoned autodev queue in finalize (silent work loss on timeout)
- ENH-2653: ready-issue must name the branch it checked and not reject on suspected base-branch mismatch
- ENH-2658: Add ids filter to prompt-across-issues loop
- ENH-2656: Single source-of-truth EPIC base-branch resolver
- ENH-2640: autodev triage_outcome_failure spike branch routing
- ENH-2641: spike-gate.yaml wrapper loop
- ENH-2641: verify-detail.txt truncation hides the real failure
- ENH-2643: Persist a merge-failure diagnostic artifact when merge_epic_branch_to_base aborts
- ENH-2655: Standardize a .ll/ artifact directory for /ll:spike plan docs
- refactor(runners): extract shared RunnerType/ActionSpec dispatch abstraction (c835911a)

[1.150.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.149.0...v1.150.0
[1.149.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.148.0...v1.149.0
[1.148.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.147.0...v1.148.0

## [1.147.0] - 2026-07-15

### Added

- **OTel `gen_ai.usage.*` attribute emission** — `observability/tracing.py` shapes
  internal token-usage rows into canonical dotted OTel attributes
  (`gen_ai.usage.cache_read.input_tokens` etc.) with a per-CLI `gen_ai.invocation.id`
  UUID and a `gen_ai.provider.vendor` addendum; `usage.jsonl` rows carry the dotted
  keys, `usage_events` gains `invocation_id`/`provider_vendor` columns (schema v21),
  and `history_reader.cost_attribution()` rolls up token/cost by invocation or vendor
  (FEAT-2478).
- **`ll-loop queue list`** — lists pending run-queue entries and prunes dead-PID
  files as a side effect (FEAT-2618, ENH-2629).
- **`ll-loop queue remove <id>`** — cancels a queued waiter: SIGTERMs its process
  (psutil identity-checked unless `--force`) and deletes its `.queue/<uuid>.json`
  entry (FEAT-2619, ENH-2617).

### Fixed

- **Epic verify gate false-negative from editable-install path shadowing** — the
  gate imported main-tree `little_loops` instead of the branch's source because
  an editable install pins an absolute path, silently blocking merges for any
  branch touching source (BUG-2629).
- **`parse_frontmatter` rejects PyYAML-serialized lists** — emitted spurious
  "Unsupported YAML list syntax" warnings on frontmatter written by PyYAML's
  own dumper (BUG-2633).
- **`auto-refine-and-implement` reports false "done"** — the loop reported green
  when a dispatched issue was actually still in-flight (BUG-2636).
- **`merge_epic_branch` reads stale child status** — read the final child's
  status from the base tree rather than the EPIC branch tip, so the run that
  actually completes an EPIC could never auto-merge (BUG-2637).
- **`ll-issues next-issues` leaks EPIC ids into the implementable backlog** —
  caused autodev to attempt refining an EPIC as if it were a leaf issue
  (BUG-2638).
- **`_OP_ALT` operator ordering non-deterministic** — caused a flaky
  `edit-routes` test (BUG-2639).
- **`get_project_folder` encoding drops dots** — broke session resolution in
  worktrees whose paths contained dots (BUG-2648).
- **`ll-history-context <ID>` silently empty for hyphenated issue IDs** — FTS5
  parsed the `-NNN` suffix as a column filter instead of matching the literal
  id (BUG-2651).

### Changed

- **`wire-issue` graph-first discovery phase** — adds before/after token
  measurement to the graph-accelerated discovery path (ENH-2578).
- **`--json-schema` gated on `structured_output` host capability** — avoids
  requesting structured output from hosts that don't support it
  (ENH-2627).
- **`merge_epic_branch` reuses the verify verdict** — avoids re-running the
  full suite a second time when the verify state already ran it (ENH-2630).
- **Verify gate surfaces failure exit code and `collection_error` verdict** —
  previously discarded the failure message and exit code (ENH-2631).
- **`audit-issue-conflicts` scoped to a positional EPIC argument** — previously
  always scanned the full backlog even when a specific EPIC was given
  (ENH-2634).
- **`next-issue --include-blocked` reports pending `depends_on` prerequisites**
  (ENH-2635).
- **`verify-detail.txt` no longer truncates the real failure** (ENH-2641).
- **`ready-issue` names the branch it checked** — no longer rejects on a
  suspected base-branch mismatch without saying which branch it inspected
  (ENH-2653).
- **Standardized `.ll/` artifact directory for `/ll:spike` plan docs**
  (ENH-2655).
- **Single source-of-truth EPIC base-branch resolver** — consolidates base/name
  resolution logic used by `ll-parallel` (ENH-2656).

## [1.146.0] - 2026-07-15

### Added

- **Per-EPIC base branch (FEAT-2652)** — EPIC issues may declare an optional `base_branch:` (alias `target_branch:`) frontmatter field; its integration branch forks from that ref instead of the global `parallel.base_branch`. `ll-sprint` dispatch hard-stops if a declared base does not exist (local or remote), rather than degrading dependent children to a false `partial`.
- **`/ll:spike` skill** — retires concentrated technical risk on an issue by
  planning, implementing, and verifying a **code spike** (a standalone library +
  test class proving a novel *internal* mechanism in isolation) before the real
  integration point is touched. Reads the issue's `### Outcome Risk Factors`,
  writes a plan in the `plan-template.md` shape (Context, Approach, Critical files,
  Implementation, AC→test table with a mandatory regression-guard test,
  Verification, Out of Scope, Promotion), builds the spike under
  `scripts/tests/spike/<slug>/`, runs the AC suite plus named regression suites,
  and on success appends `## Spike Results` and sets `spike_completed: true` /
  `spike_attempted: true` so re-running `/ll:confidence-check` recovers the
  outcome-confidence points the unproven mechanism cost. A failed spike is also
  signal (writes `## Spike Findings`, routes to `/ll:decide-issue` /
  `/ll:issue-size-review`). Flags: `--auto`, `--check` (FSM exit-code evaluator),
  `--plan-only`, `--plan <file>`, `--force`. External-API risks are suppressed and
  routed to `/ll:explore-api` instead. Consumed downstream by ENH-2568's autodev
  routing (FEAT-2567, EPIC-2570).
- **autodev spike-remediation branch** — `autodev.yaml`'s `triage_outcome_failure`
  now routes an outcome-confidence failure caused by an unproven internal
  mechanism (`spike_needed: true`, set by `/ll:confidence-check` Phase 4.10)
  through three new states: `check_spike_needed` (predicate `spike_needed AND
  NOT spike_attempted`, a one-shot guard read from `ll-issues show --json`),
  `run_spike` (`/ll:spike --auto`), and `rerun_confidence_after_spike`
  (`/ll:confidence-check`, re-scoring before `enqueue_or_skip`). Inserted between
  the decide and missing-artifacts branches so an unproven mechanism is proven
  rather than mis-routed into decompose/size-review. `ll-issues show --json` now
  surfaces `spike_needed`/`spike_attempted`/`spike_completed`
  (ENH-2640, EPIC-2570).

### Fixed

- **Doc-wiring string test flake root-caused (BUG-2650)** — removed the
  `LL_VERIFY_GATE` skipif quarantine (BUG-2649) on `test_string_present_in_doc`
  (`test_wiring_skills_and_commands.py`). The epic-merge verify gate reads a
  `project_root`-anchored doc via a freshly `git worktree add`-checked-out tree in
  a test subprocess; `git worktree add` is synchronous and the read resolves off
  the path-collected `conftest.py` (not `cwd`/`PYTHONPATH`), so the read is
  deterministic. A 60× stress probe of that exact path produced 0 false-negatives;
  the lone historical failure was a genuinely stale EPIC-integration tip, not a
  nondeterministic read. Added a committed regression guard
  (`TestVerifyEpicBranchBeforeMerge::test_gate_read_is_deterministic_on_present_needle`)
  that loops the real gate's checkout→subprocess→read path and asserts it never
  false-negatives on a present needle.

## [1.145.0] - 2026-07-15

### Added

- **`spike_needed` frontmatter flag** — `/ll:confidence-check` gains Phase 4.10,
  which sets `spike_needed: true` when the Phase 4.5 Outcome Risk Factors describe
  an unproven **internal** mechanism (signal phrases like "no precedent" / "no
  existing test exercises") and the score condition holds (`score_test_coverage`
  <= 10 or Criterion A Depth Moderate/Deep). Risk factors naming an external API
  surface are suppressed and routed to `/ll:explore-api` instead; issues already
  carrying `spike_attempted`/`spike_completed` are never re-flagged. This turns the
  ad-hoc "you should spike this" advice into a machine-readable routing signal and
  a base-rate measurement for the spike lattice (ENH-2569, EPIC-2570).

## [1.144.0] - 2026-07-15

### Changed

- **Decisions log now uses hybrid append-only fragment storage** — new decision,
  rule, exception, and coupling entries are written as one append-only file per
  entry under `.ll/decisions.d/<uuid4>.json` (UUID4 ids) instead of appending to
  the single `.ll/decisions.yaml` flat file. This eliminates the concurrent-append
  id collision that blocked EPIC-branch merges when two branches minted the same
  count-based `ARCHITECTURE-NNN` id (BUG-2642). Reads union both tiers
  (`load_decisions()` / `ll-issues decisions list` merge the flat file with all
  fragments); compaction (`save_decisions()`) folds every fragment back into the
  flat file and deletes the fragment directory. A **fresh install now has only
  `.ll/decisions.d/`** until the first compaction — query through
  `ll-issues decisions list` rather than `cat`/`grep`-ing a single file. The
  fragment directory is derived from `decisions.log_path` (its `.d`-suffixed
  sibling) and is not independently configurable. `ll-verify-decisions`, the
  pre-commit hook, the pytest gate, and the Claude Code `PreToolUse` hook all
  validate both tiers (BUG-2644/2645/2646/2647).

### Fixed

- **Decisions governance no longer silently skipped on fresh installs** —
  `/ll:capture-issue`, `/ll:decide-issue`, `/ll:go-no-go`, `/ll:verify-issues`,
  and `/ll:ready-issue` gated their decisions-log step on `[ -f .ll/decisions.yaml ]`,
  which skipped governance entirely on any never-compacted install (where entries
  live only in `.ll/decisions.d/*.json`). The gates now accept either tier
  (`[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]`) (BUG-2647).

## [1.143.0] - 2026-07-13

### Added

- **`ll-issues clusters` graph-aware tree layout** — the default rendering is now
  an indented, multi-root dependency tree (`├──`/`└──` connectors) in which every
  edge appears in the primary layout; hub/parent hierarchies show depth naturally
  and DAG cross-edges / cycle back-edges render as `⤷` cross-references instead of
  being demoted to a trailing skip-edge list. Adds `--layout {tree,list,boxes}`
  (`tree` default; `list` is the compact renderer, aliased by `--compact`; `boxes`
  is the legacy box-stack); `--json` output is unchanged (FEAT-2337, EPIC-2370).

- **CodeQuery system** — a pluggable structural code-query provider protocol with
  a grep/AST fallback provider that needs no index day-one, plus the `ll-code`
  CLI (`status`/`callers-of`/`callees-of`/`importers-of`/`defines`/`references`/
  `impact-of`) (FEAT-2576); a `code_query` config block and `CodeQueryConfig`
  dataclass (ENH-2612); and a codegraph SQLite provider with staleness detection
  (ENH-2613).
- **Per-EPIC integration branch strategy** — the epic-branch strategy is now
  end-to-end: `_inspect_worktree()` epic-branch comparison (FEAT-2562), the
  `cli/sprint/run.py` in-place warning is epic-aware (FEAT-2563), CLI flags/TUI/
  docs/templates (FEAT-2450), pre-merge test/lint verification and the
  `epic_branches.verify_before_merge` flag (ENH-2600, ENH-2602, ENH-2603), FSM
  refine/implement loops gained epic-branch awareness and a post-implement verify
  state (ENH-2601), and mid-run decomposed children now route through the
  epic-branch worktree (ENH-2615) — decomposed from FEAT-2339 (EPIC-2451).
- **Session-store overhaul** — `raw_events` is now the source of truth with an
  `ll-session rebuild` subcommand (ENH-2581), real LLM token usage is persisted
  into `history.db` (ENH-2461), `raw_events` payload columns are losslessly
  zlib-compressed (ENH-2624), and `history.db_path` is configurable with unified
  DB-path resolution (ENH-2623).
- **Iframe-free Shadow DOM composition** for the interactive-component-generator
  loop (ENH-2625).
- **`refine-issue` decision recommendations** now emit enumerable options
  (ENH-2607).

### Fixed

- **FSM shell `${context.*}` injection** — values containing quotes, dollars,
  backticks, or backslashes no longer break bash tokenizing or misroute loops
  (BUG-2622, guarded by the new MR-11 lint).
- **Verdict recovery for non-Anthropic hosts** — recover the verdict from
  tag-format structured output (BUG-2597 glyphs; fsm executor fix).
- **Epic-branch merge-back** — the FSM epic-branch loop now merges the epic
  branch back to base (BUG-2614) and `checkout_epic_branch` commits are no longer
  dropped by the delegate (ENH-2609).
- **autodev decision gates** — no longer advances to `implement_current` without
  verifying `decision_needed` (BUG-2595), fast-path gates no longer bypass
  `check_decision_decidable`/`deposit_options` (BUG-2605), and `decide-issue`
  Phase 2.5 auto-recovery no longer short-circuits Phase 3b (BUG-2606).
- **Resume safety** — `rn-refine` now has a safe resume path after a mid-walk
  interruption (BUG-2610), and autodev's `skip_inflight` ledger write survives a
  `refine_current` crash (BUG-2611).
- **`save_decisions()`** no longer silently drops entry keys not declared on the
  dataclass (BUG-2588).
- **`ll_auto_learning_gate_check`** no longer crashes the loop on untrusted
  ll-auto output (BUG-2594).

### Changed

- **`ll-issues show` card rendering** — summary reflow and visual hierarchy
  overhaul for scanning-first UX (ENH-2574).
- **`ll-loop run` header/diagram** — the input value is shown in the run diagram
  header with the model packed onto the `run_dir` row (ENH-2596), and header
  lines merge onto one line when terminal width allows (ENH-2604).
- **general-task** — guards the `continue_work` convergence spin after
  `abandoned` (ENH-2585).
- **`.ll/decisions.yaml` integrity** — a Claude Code `PreToolUse` hook guards
  against corruption (ENH-2592).
- **`pixi-data-viz`** — renamed `input_key` to match the input-port convention
  (d1f2da2).
- **Epic verify gate** — the gate now surfaces the failure's exit code and detail:
  `verify_epic_branch_before_merge` returns `(ok, message, returncode)`, the
  `auto-refine-and-implement` verify state persists `verify-returncode.txt` /
  `verify-detail.txt`, and `summary.json` carries a `verify_returncode` field plus a
  distinct `collection_error` verdict class (pytest exit 2) so a harness/import error
  is triageable without a re-run (ENH-2631).

### Other

- **Docs** — documented `ll-verify-decisions` in CLAUDE.md and the CLI reference
  (3357363), applied the remaining docs/guides audit fixes from the 2026-07-12
  sweep (ENH-2621, b27281f), and removed a stray general-task loop audit artifact
  (ba5458c).

## [1.142.0] - 2026-07-11

### Added

- **Per-EPIC integration branch surface, continued** — `--epic-branches` CLI
  flag, TUI surface, docs, and templates (FEAT-2450); `_inspect_worktree()` and
  the in-place sprint/CLI warning are now epic-branch aware (FEAT-2562,
  FEAT-2563, ENH-2557); `auto-refine-and-implement`/`sprint-refine-and-implement`
  are now `epic_branches`-aware too — a new `checkout_epic_branch` state
  creates (without switching) the EPIC integration branch when `scope` is an
  EPIC-NNN id, and a new `verify` state runs `test_cmd`/`lint_cmd` after
  `delegate`, folding the pass/fail/skip verdict into `summary.json` as an
  additive `verify_verdict` key (ENH-2601).
- **`code-run-gate` oracle wiring** — the config schema for build/test/
  typecheck/lint/health checks (FEAT-2551) is now wired into `rn-remediate` and
  `rn-implement` as a real code-run gate (FEAT-2413, FEAT-2552).
- **`.ll/decisions.yaml` integrity belt** — a Claude Code `PreToolUse` hook
  (ENH-2592), a repo-local pre-commit hook (ENH-2590), a pytest CI gate for
  corruption (ENH-2591), and a standalone `ll-verify-decisions` validator CLI
  with malformed-input coverage (ENH-2589).
- **`ll-loop run` diagram/config polish** — the run diagram header now shows
  the input value and packs the model onto the `run_dir` row (ENH-2596); stub
  terminator glyphs at cut boundaries render with open half-circle arcs at
  decision points instead of the pre-decision filled-semicircle glyphs
  (ENH-2593, BUG-2597); `--delay` is config-defaultable via
  `loops.run_defaults` (ENH-2556).
- **`ll-loop list` default reverted to detailed table** — `--grid` is now
  opt-in (ENH-2572).
- **`ll-issues show` card rendering overhaul** — summary reflow and visual
  hierarchy tuned for scanning-first UX (ENH-2574).
- **`epic-consistency`** — recognizes `### FEAT-NNN` prose headings and
  downgrades `relates_to` membership to advisory (ENH-2564).
- **`find_nearest_epic_ancestor`** — promoted to a shared module-level helper
  for reuse across merge-routing consumers (FEAT-2561).

### Fixed

- **`save_decisions()` dropped unmodeled keys** — entries with keys not
  declared on the dataclass now round-trip intact (BUG-2588).
- **`autodev` skipped decision verification** — `implement_current` no longer
  advances after `run_decide` without re-verifying `decision_needed` is
  cleared (BUG-2595).
- **`ll_auto_learning_gate_check` crashed on untrusted `ll-auto` output** — the
  fragment now greps the run-dir file instead of interpolating raw output
  (BUG-2594).
- **Pinned FSM box diagram header overflow** — header lines are now clamped to
  terminal width in the pinned pane (BUG-2579).
- **`general-task` convergence spin** — `continue_work` is now guarded against
  spinning after abandoned steps (ENH-2585).
- **`general-task` `final_verify`** — errors/timeouts route to a partial-credit
  chain instead of forfeiting progress (ENH-2575).

### Changed

- **`ll-loop list` config defaults** — `--clear` and `--show-diagrams clean`
  default on for target projects, and generated configs enable
  `learning_tests` and `analytics` by default (ENH-2557, ENH-2560).

## [1.141.0] - 2026-07-09

### Added

- **Per-EPIC integration branch** — parallel workers now merge each EPIC's child
  issues onto a dedicated per-EPIC integration branch instead of a shared target.
  `WorkerResult` carries `epic_branch`, the `WorkerPool` threads it through, and
  merge/PR routing plus EPIC-completion detection fire against that branch behind
  a partial-failure gate (FEAT-2448, FEAT-2449, FEAT-2452, FEAT-2453). A shared
  `find_nearest_epic_ancestor` helper was promoted to module scope for reuse
  across the merge-routing consumers (FEAT-2561).
- **`rn-refine` parallel bottom-up integration + resume** — the integration phase
  is no longer serial (one internal node per cycle). A new `synth_dispatch` state
  background-spawns up to `synth_workers` (default 4) `oracles/integrate-node`
  workers that pop from a shared queue under an `flock`-guarded, readiness-gated
  pop (`little_loops.rn_synth_queue`): a node integrates only once all its children
  have a `final.md`, so independent same-depth nodes fold up concurrently while
  children-before-parent ordering holds. A run interrupted mid-integration (e.g. a
  wall-clock timeout) is now resumable via `--context resume=1 --context
  run_dir=<prior>` — `resume_build_synth` rebuilds the queue from on-disk `final.md`
  absence, reusing already-refined/integrated work and covering the
  popped-but-not-integrated node the old queue had dropped (ENH-2565).
- **Config-defaultable `ll-loop run` behavior** — `--delay` can now be defaulted
  via `loops.run_defaults` (ENH-2556), and `--clear` + `--show-diagrams clean`
  default on for target projects (ENH-2557). Generated configs enable
  `learning_tests` and `analytics` by default (ENH-2560).
- **`rn-remediate` / `rn-implement` reporting** — `rn-remediate` writes a
  `manual_review_handoff_<id>.md` with decision context on handoff (ENH-2530);
  `rn-implement` records per-issue outcomes and learning followups in
  `summary.json` (ENH-2533) and emits `UNRESOLVED` / `PARSE_ERROR` tokens from
  `check_blocked_by` (ENH-2534).
- **Streaming-vs-blocking cache-accounting parity trace set** — locks a trace set
  proving cache-accounting parity between streaming and blocking host calls
  (ENH-2479).

### Fixed

- **`ll-loop list` terminal-width overflow** — wide labels no longer overflow the
  terminal (BUG-2554), multi-line YAML descriptions collapse to fill the available
  width (BUG-2566), and columns align correctly under subgroup subheads (BUG-2571).
- **FSM diagram + color rendering** — box diagrams no longer lose color styling
  partway down deep FSMs (BUG-2546), and the shell kind-color no longer renders
  cyan as bright green on the warm-paper dark palette (BUG-2537).
- **`rn-refine` context refs + timeouts** — `ll-loop run rn-refine <plan.md>` no
  longer falsely reports `:default=` context refs as missing required variables
  (BUG-2553), and root-integration timeouts are handled more robustly.
- **`general-task.yaml`** — `check_done` / `continue_work` no longer read a
  `current-step.txt` that was already deleted (BUG-2538).
- **Orphan pytest-xdist worker sweep** — now registered locally rather than
  shipped as a built-in hook (BUG-2540).
- **`manage-release` 0-completed-issues regression** — `ll-issues list --json`
  now emits `completed_at` (stamped on `set-status done`), fixing the release
  changelog scan that reported zero completed issues (BUG-2558, BUG-2559).
- Sub-loop states now appear in the `ll-loop show` info overview table.

### Changed

- **`ll-loop list` scanning-first layout (ENH-2572)** — the default output is now
  a compact multi-column name grid (one column when stdout is not a TTY);
  `-l/--long` gives the detailed one-row-per-loop layout. The `kind` column is
  gone — built-in is the unlabeled default and only exceptions carry a
  `◆ project` / `◆ internal` / `◆ example` badge. Project loops are pinned
  exclusively in a `YOUR PROJECT` section at the top with a dim home-category
  tag; categories with fewer than 3 members fold into a trailing `OTHER` group;
  remaining categories are ordered by member count (descending) with
  `uncategorized` last. Long-layout descriptions truncate at word boundaries
  (preferring the first sentence) and shared leading boilerplate within a
  section renders dim so the distinguishing words stand out. The summary header
  uses `·` separators throughout, the footer gains
  `ll-loop show <name> for details · --category <cat> to filter` hints, and
  subgroup subheads now require only ≥3 members sharing a prefix (the old
  ≥50%-dominance rule is dropped). `--json` output is unchanged.
- **`ll-loop list` layout polish (precursors to ENH-2572)** — incremental work
  leading up to the scanning-first redesign: match `ll-issues list --group-by
  epic` styling (ENH-2539), all-caps section markers and palette fixes (ENH-2541),
  line-2 continuation display with subgroup glyph differentiation (ENH-2555), five
  additional high-impact fixes (ENH-2554), a steel-blue loop-name column in place
  of cyan (ENH-2542), and relative loop filename / `run_dir` paths instead of
  absolute ones (ENH-2573).
- **`epic-consistency`** — recognizes `### FEAT-NNN` prose headings and downgrades
  `relates_to` membership to advisory (ENH-2564).
- **Documentation** — documents the event-schema error-handling contract for JSON
  callers (ENH-2543) and the full `OUTPUT_STYLING.md` public-API rendering-helper
  surface (ENH-2545).

## [1.140.0] - 2026-07-08

### Added

- **`code-run-gate` oracle** — a new oracle that runs real build / test /
  typecheck / lint commands (plus an optional `health_url` probe) as a loop gate,
  wired into `rn-remediate` and `rn-implement` so remediation and implementation
  loops validate against actual command exit codes (FEAT-2551, FEAT-2552).
- **Coverage-aware decidability gate** — the decidability gate now factors
  coverage into its verdict (ENH-2446).
- **`rn-refine` finalize diff-invariant guard + rollback** — the in-place
  source-refinement finalize step now guards a diff invariant and rolls back on
  violation (ENH-2418).
- **Locked Tier 0 verification trace set** — pins the verification trace set at
  ≥2 traces for FEAT-2470 measurement (ENH-2518).
- **`ll-loop list` layout polish** — line-2 descriptions, differentiated
  subgroup headers, and five additional layout improvements.

### Fixed

- **`ll-init --yes` crashes on `config-schema.json` in wheel installs** — the
  schema is now shipped in the wheel via `importlib.resources` (BUG-2547).
- **Pre-run context validator ignored `:default=` and `?` guards** — the
  validator now honors both (fix(loop)).
- **`ll-loop list` rows overflow terminal width** — rows are now truncated to
  the terminal width (fix(loop)).
- **Loop box diagrams lost ANSI styling through the terminal-width clamp** — the
  clamp now preserves styling (fix(loop-diagrams)).

### Changed

- **Removed the unwired `epics.*` config subtree** — resolves the schema-only
  limbo in favor of dropping the keys (ENH-2544).

### Other

- **Docs** — documented the full `cli.output` public-API surface; added an Error
  Handling Contract section to `EVENT-SCHEMA`; applied Phase 1/2 audit fixes
  across 16 guides and `docs/reference/`; filled gaps from the update-docs window
  (FEAT-2447, ENH-2418, BUG-2547).
- **Decisions** — recorded ARCHITECTURE-122 (FEAT-2413 sub-loop oracle),
  ARCH-202/203/204 (terminal column budgets), and OTHE-201 (additive `--json`
  keys).
- **Tests / maintenance** — added a 3-trace streaming-vs-blocking
  cache-accounting parity gate; recorded opentelemetry + pytest-json-report
  learning-test proofs; import-ordering and multi-line-collapse style cleanups.

## [1.139.0] - 2026-07-08

### Added

- **Tier 0 token-cost behavioral quick-wins** — four infrastructure-free
  techniques from EPIC-2456 that cut avoidable token cost on every loop run — (FEAT-2470):
  - **Verbatim-output rule** appended to the six audit skills (`audit-loop-run`,
    `audit-claude-config`, `audit-docs`, `audit-issue-conflicts`, `review-epic`,
    `review-loop`) so findings quote evidence verbatim instead of re-summarizing.
    `audit-issue-conflicts`'s rule lives in a `verbatim-output.md` companion (500-line cap).
  - **Edit-batch nudge** — a `PostToolUse` hook (`edit_batch_nudge`, matcher
    `Edit|Write|MultiEdit`) that injects a batch-your-edits reminder into the
    model's context (exit 2), cutting edit round-trips. On by default; mirrored to Codex.
  - **`little_loops.output.parse`** — stop-sequence / prefill JSON output helpers
    (`extract_between_tags`, `parse_prefilled_json`) that bound LLM output-token cost.
  - **`little_loops.output_cleaner`** — anti-event + duplicate-window pre-filter
    (`filter_output`) that trims progress-bar/spinner/duplicate noise from tool/log output.
- **per-EPIC integration branch** — config schema, dataclasses, resolver, and
  serialization for whole-EPIC parallel runs — (FEAT-2447)

### Fixed

- **`ll-auto --only` race in autodev implementation phase** — Two concurrent
  `ll-loop run autodev` invocations previously reached `implement_current` on
  disjoint `${context.run_dir}` scopes and both shelled out to `ll-auto --only`
  on the main working tree, corrupting `.auto-manage-state.json` (double-processed
  issues, lost `--resume` history) and tangling git history. Added `singleton:
  bool = False` to `FSMLoop` and `ScopeLock`; `LockManager.find_conflict()` now
  treats any two locks with the same `loop_name` and `singleton=True` as a
  conflict regardless of scope, and `autodev.yaml` opts in with `singleton:
  true`. Users who relied on FEAT-1789's parallel-refinement goal can use
  `--worktree` (whole-loop filesystem isolation) or fork to a new loop name with
  `singleton: false`. (BUG-2526)
- **`ll-loop resume` drops `fsm.context` (including `input`)** — `LoopState` now
  persists and restores the full FSM context (positional `input`, `program.md`
  fields, `--context` values) across stop/resume. Context is kept internal to
  the on-disk `.state.json` (emitted only via `to_dict(include_context=True)`),
  so the `ll-loop status`/`list --json` contract is unchanged. `--context`
  overrides supplied at resume time still win over restored values — (BUG-2485)
- **autodev `check_decision_before_size_review` shares BUG-2513's `on_success`-coupled
  decision-gate defect** — (BUG-2519)
- **SIGINT subprocess test flakes under xdist parallel load** — (BUG-2523)
- **`--show-diagrams clean` emits broken connectors (trailing `───── ┘`) when the
  pinned pane overflows terminal width** — width-aware pinned-pane picker +
  render clamp — (BUG-2527)
- **`--show-diagrams clean` produces inconsistent color across invocations (some
  diagrams have color, others have none) for the same FSM and CLI flags** — (BUG-2536)
- **4 Tests in `TestEvalExport` Fail Without Project-Folder Fixture** — (BUG-2502)
- **xdist worker crashes on long-running rate-limit test** — (BUG-2524)
- **Scratch-pad redirect drops output file outside automation context** —
  preserve user-typed scratch files in cleanup sweep — (BUG-2525)
- **`refine-to-ready-issue` does not short-circuit on `decision_needed: true` set
  by mid-chain skills, wasting LLM budget on wire and confidence-check
  invocations** — (BUG-2528)
- **Shell kind-color cyan renders as bright green on warm-paper dark palette —
  recede via bright-black** — (BUG-2537)
- **`ll-init --yes` crashes with `FileNotFoundError` on `config-schema.json` in
  non-editable (wheel) installs** — `pip install little-loops` followed by
  `ll-init --yes` previously failed because the schema lived at the repo root
  (not packaged in the wheel) and `init/core.py:_load_schema` walked
  `Path(__file__).resolve().parents[3]` to find it (only valid in editable
  installs). Moved the canonical schema into `scripts/little_loops/config-schema.json`
  (ships inside the wheel), switched the loader to `importlib.resources`, and
  updated the GitHub-raw `$schema` URL emitted into user configs. `ll-verify-package-data`
  was already flagging the `parents[3]` escape — added a fast unit regression
  (`TestSchemaLoaderInWheelInstall`) and a wheel-install smoke test so the
  regression cannot recur silently.

## [1.139.1] - 2026-07-09

### Fixed

- **`ll-loop run` pre-run validator falsely flags `:default=` /
  `?`-guarded `${context.X}` refs as missing required context variables** —
  Pre-flight check now mirrors the engine split (fsm/interpolation.py:230-241)
  and the static-validator idiom (fsm/validation.py:135-156
  `_unguarded_captured_refs`), so guarded refs are skipped and only bare
  `${context.X}` references for keys absent from `fsm.context` trip the
  validator. Effect: every loop whose states rely on engine-native `:default=`
  guards (14 loops, including `rn-refine` — `floor_fraction`, `dry_run`,
  `confirm_overwrite`; `recursive-refine` — `order`, `commit_every`,
  `no_recursion`; `rl-coding-agent`; `composer.yaml` `include`, etc.) is
  once again runnable with `ll-loop run <loop> <input>` alone. Validator
  error message also drops the spurious `:default=` suffix from the printed
  key. (BUG-2553)

### Changed

- **All 30 `ll-*` Codex bridge skills now carry `disable-model-invocation: true`** —
  the stubs exist only for Codex Skills API discovery (via `agents/openai.yaml`);
  Claude Code users invoke the identically-named `/ll:` slash commands. Removes the
  bridges from the skill listing budget (~54% reduction); `ll-adapt --host codex`
  generates new bridges with the field included — (ENH-1615)
- **F5.1 — Existing-event audit (DES adoption prerequisite)** — (ENH-2475)
- **F6 (finishes) — Per-state cost attribution: stable JSON + per-state
  ceilings** — (ENH-2477)
- **Add per-event flush+fsync at StatePersistence append sites** for
  audit-trail durability — (ENH-2515)
- **Real-subprocess SIGINT integration test + SIGKILL documentation** — (ENH-2517)
- **`ll-issues show`: surface closure context, relationships, discovery, and
  decision coupling** — (ENH-2535)
- **Scope `prompt-across-issues` to full EPIC subtree (transitive children)** — (ENH-2481)
- **Make the edit-batching nudge stateful** — fire only after a run of unbatched
  single edits — (ENH-2499)
- **`prompt-across-issues`: per-run-dir pending file + scope declaration** — (ENH-2500)
- **Edit-batch nudge: fire at most once per session** — (ENH-2503)
- **Distinguish user-stop, OS-signal, and OOM in loop termination taxonomy** — (ENH-2522)
- **`rn-remediate` — `manual_review_handoff_<id>.md` with `decision_context`** — (ENH-2530)
- **Polish `ll-loop list` output to match `ll-issues list --group-by epic`** —
  per-category color, columns, rollup, all-caps, no-dim, palette fix, bold name
  with gray rollup — (ENH-2539)
- **`rn-implement` — `check_blocked_by` should emit `UNRESOLVED` / `PARSE_ERROR`
  tokens to stderr** — (ENH-2534)

## [Unreleased]

### Planned

- Windows compatibility testing (tracked: ENH-2472)
- Performance benchmarks for large repositories (tracked: ENH-2473)

## [1.138.0] - 2026-07-02

### Added

- **Source ll-init defaults from config-schema.json** — (ENH-2434)
- **Fully programmatic issue-format linter (renamed/empty/boilerplate) for the ensure_formatted gate** — (ENH-2426)
- **vega-viz — prevent panel-level params regression and raise step budget** — (ENH-2440)
- **Extend windowed rung to the non-TTY streaming FSM diagram path** — (ENH-2442)
- **decide-issue and rn-remediate should detect decision_needed:true issues with no enumerable options before MANUAL_REVIEW_NEEDED** — (ENH-2443)
- **Constrain `diverge` state in brainstorm loop via per-state `tools:` allowlist** — (ENH-2444)
- **Replace fragile test sleeps with deterministic signals and parallelize via pytest-xdist** — (ENH-2445)
- feat(issues): add skip_blocked kwarg to find_issues (19d4dd43)
- feat(tests): add breadth integration test for skip_blocked (f4091ee3)
- feat(issues): skip blocked issues by default for next-issue / next-issues (40c91e70)

### Fixed

- **brainstorm `init` doubles run_dir path when `${context.run_dir}` is already absolute** — (BUG-2435)
- **manage-issue final test run loses its scratch directory when the redirect hook doesn't fire; FSM spawn continuations lose automation permission_mode** — (BUG-2437)
- **scratch-cleanup.sh's blind `rm -rf .loops/tmp/scratch` races every OTHER concurrent session in the repo** — (BUG-2438)
- **`compute_epic_progress` counts only direct `parent:` children while `ll-issues list --group-by epic` buckets transitively — contradictory badges** — (BUG-2441)
- **ll-init never displays the bundled CLI logo** — (BUG-2439)

### Other

- docs(cli): document ll-init defaults source and epic-progress transitive rollup (4e3776d6)
- docs(issues): file EPIC-2456 (token-cost reduction), EPIC-2457 (history.db coverage expansion), and 9 child ENHs (19e4a04f)
- docs(decisions): log ARCH-091–096 from FEAT-2339 decomposition research (08e925a3)
- docs(decisions): log ARCH-171/172 from ENH-2444 + TEST-173 from ENH-2445 (95d3d074)
- docs(decisions): log ARCH-169/170 rules from BUG-2438 and BUG-2441 (87796dbb)
- perf(tests): replace fixed sleeps with deterministic signals + parallelize (fffea99d)
- chore(config): add prompt_optimization config key, disabled by default (75ddb743)
- style: fix mypy type error and apply ruff format (03261700)

## [1.137.0] - 2026-07-01

### Added

- **Score-plateau early-stop for generator-evaluator oracle** — Adds a `score_stall` evaluator that detects score plateaus and stops early. (ENH-2428)
- feat(rn-implement): auto-prove unproven learning-gate targets before blocking (52de8fa3)
- feat(learning-tests): add `ll-learning-tests prove` subcommand (84298f5f)

### Fixed

- **FSM diagrams overflow terminal width in non-TTY streaming render** — Bounds diagram width instead of an unbounded back-edge gutter. (BUG-2425)
- **`rn-implement` appears hung for hours** — `format_issue`'s 429 wait is now bounded to seconds instead of inheriting the 6-hour rate-limit budget. (BUG-2433)
- fix(history): treat empty sections list as render-all in project_digest (1a791b7e)

### Changed

- **Generator-evaluator non-convergence** — Converges via full-page screenshot + score-driven routing. (ENH-2429)
- **Windowed diagram fallback margin pipes** — Blank pass-through for back-edge/forward-skip margin pipes. (ENH-2432)
- refactor(manage-issue): move gate pseudocode from SKILL.md to templates.md (6868dbaf)

### Other

- style(tests): apply ruff formatting (b4b15de4)
- docs(claude-md): add score_stall to MR-1 non-LLM evaluator list (9356ba3d)
- docs(loops): document ENH-2429 full-page screenshot fix and score-driven pass/fail (bd3362d3)
- docs(issues): align ENH-2428 with template v2.0 structure (ae58c274)
- docs(issues): capture ENH-2430/2431 for learning-tests prove + rn-implement gate wiring (6956d779)
- docs(issues): record full-suite confirmation for BUG-2427 (64f72971)
- docs(issues): capture ENH-2428 score-plateau early-stop for generator-evaluator (4ea53bd9)
- docs(issues): capture ENH-2426 for programmatic issue-format linter (7d05b322)

## [1.136.0] - 2026-06-30

### Added

- **`ll-artifact policy-builder` emit + validate engine** — New subcommand emits a `file://`-safe visual builder for policy-router / rubric loop YAML (stamping design-token CSS, the grammar spec, and the skill catalog at generation time) and validates the produced policy. (FEAT-2390)
- **Topology-aware FSM diagram fallback for the pinned-pane ladder** — When the full state diagram won't fit the pinned pane, rendering now branches on *why* it doesn't fit and degrades to a windowed / scroll-to-active view instead of always collapsing to the neighborhood. (ENH-2410, ENH-2411)
- **Consistent learning-test gating across core implementation loops** — `rn-implement`, `autodev`, and `sprint-refine-and-implement` share learning-gate routing with a `skip_learning_gate` knob; `issue_manager` emits a `LEARNING_GATE_BLOCKED` stdout marker on block. (ENH-2402)
- **Learning gate proves registered targets instead of re-extracting** — The gate now threads the issue's registered `learning_tests_required` targets through rather than re-deriving them, so it validates the recorded contract. (ENH-2405)
- **`decide-issue` bullet-list options + Open-Questions fall-through fix** — Adds Pattern 4 bullet-style option handling and fixes the absent-Open-Questions fall-through. (ENH-2401)

### Fixed

- **Git-lifecycle completion commits over-stage the repo** — Fallback lifecycle and parallel-orchestrator completion commits are now scoped to the issue file instead of staging unrelated working-tree changes. (BUG-2421, BUG-2424)
- **Decisions-check invocations swallow CLI errors** — Guardrail reads no longer discard CLI errors via `2>/dev/null || true`, and the `--enforcement` filter is now registered on `decisions list`. (BUG-2423)
- **`feat-1680` stale-ref sweep fires every turn** — Cross-issue stale-ref sweep re-homed from the Stop hook to SessionEnd, so it runs once per session rather than every turn. (BUG-2422)
- **`scratch-pad-redirect` Stop-hook race and double-wrap** — Redirect hook no longer double-wraps commands or races the Stop-hook cleanup, and now unwraps `python -m <module>` in the allowlist match. (BUG-2420)
- **`ll-auto` plan short-circuit before the uncommitted-work check** — Phase-3 plan short-circuit is now gated on the absence of uncommitted work, preventing a headless stall. (BUG-2409)
- **`manage-issue` backgrounds the final test run** — Headless turns now require a foreground-blocking final test run so the turn doesn't complete before tests finish. (BUG-2408)
- **`auto-refine-and-implement` closure metric counts the vestigial `.issues/completed/`** — Closure verdict now unions the `completed/` and `status: done` diffs. (BUG-2403)
- **Unresolvable `loop:` refs demoted work to a silent warning** — Static `loop:` references that resolve to no YAML are promoted from WARNING to ERROR so they block load. (BUG-2400)
- **FSM `terminated_by` value misaligned with `state.json`** — Runner now emits `terminated_by: "interrupted"` (renamed from `"signal"`) so `events.jsonl` matches `state.json`. (BUG-2474)

### Changed

- **Worktree git calls routed through `GitLock`** — Remaining bare git calls in worktree management now go through `GitLock`, with a new concurrency regression test. (ENH-2326)
- **Removed fragile branch-name string-replace in the orchestrator** — `_inspect_worktree` no longer derives branch names via string replacement. (ENH-2325)
- **`ll-loop validate` flags never-scored `policy_rules` dimensions** — Validation warns when a `policy_rules` predicate references a rubric dimension that is never scored. (ENH-2309)
- **Rubric-gated compaction timing in the `pre_compact` hook** — Adds rubric-gated timing so compaction fires at a better point. (ENH-2341)
- **`autodev`/`auto-refine` summary preserves skip reasons** — Summary no longer drops skip reasons or gate-blocked issues. (ENH-2404)

## [1.135.0] - 2026-06-29

### Added

- **Generic host-parameterized `ll-init --upgrade` surface refresh** — Upgrade surface now accepts a host parameter for targeted, host-specific refreshes. (FEAT-2387)
- **GeminiEmitter + adapter infrastructure** — Full host-agnostic event emission for Gemini CLI; CodexEmitter and core adapter registry included. (FEAT-2392)
- **`ll-logs loop-fleet` subcommand** — Cross-project FSM run aggregation and fleet-view analytics for multi-repo loop monitoring. (a03e9f77)
- **MR-10 FSM validation rule** — Flags silent JSON parse-swallow with `exit 0` that discards failures without an `on_error:` route. (ec546490)
- **Auth-signature fast-fail for `ll-auto`-calling loops** — Loops now abort early on authentication failures instead of silently continuing. (bbf77018)
- **`auto-refine-and-implement` interleaved refine→implement** — Per-issue refine and implement phases are now interleaved rather than batched. (4aa90e44)

### Fixed

- **`re_enqueue_unblocked` in `rn-implement` missing `on_error:` route** — MR-10 violation resolved; parse failures now route explicitly instead of being swallowed with exit 0. (BUG-2394)
- **Worktree split-tracking, silent work loss, and stale PID suppression** — Three correlated bugs in loop worktree management resolved; work loss under concurrent runs no longer possible. (13fb3c89)
- **Tagged-JSON parse failures now surfaced** — Loop states that caught `JSONDecodeError` and exited 0 now propagate failures visibly. (947e565a)
- **Non-canonical `pending` status coerced to `open` on read** — Status normalization now applied consistently at read time across all issue loaders. (8da35039)

### Changed

- **`ensure_formatted` gate honors `deprecated` section flag** — Gate behavior now consistent with `is_formatted()` for deprecated sections; stops false ensure_formatted loops. (ENH-2398)
- **Issue assembler no longer emits `## Labels` body section** — New issues created post-ENH-1392 no longer include the deprecated body-section Labels block. (ENH-2399)
- **Documentation migration and alias retirement for `ll-adapt`** — Docs migrated to canonical locations; deprecated adapter aliases retired. (FEAT-2393)

## [1.134.0] - 2026-06-28

### Added

- **MR-9 FSM validation rule** — Flags over-escaped `$$` in shell action strings that PID-corrupt `run_dir` paths at runtime; existing violations fixed across 3 generator loops. (BUG-2368)
- **MR-7 FSM validation rule** — Flags unescaped bash `:-default` interpolation syntax that crashes the runner; replaces with engine-native `:default=` form. (feat(validation))
- **Phase 0 format guard in `rn-remediate`** — Ensures all required issue template sections exist before `assess` runs; auto-repairs with `/ll:format-issue --auto` on missing sections only. (ENH-2360)
- **HostEmitter Protocol + registry spike** — Foundation for host-agnostic event emission across Claude Code, Codex, and OpenCode adapters. (FEAT-2260)

### Fixed

- **`audit-loop-run` confabulates audit of nonexistent run** — Pre-flight existence gate added; aborts with a clear error instead of hallucinating results. (BUG-2361)
- **`recursive-refine` `parse_input` crashes on bare shell variables** — Bare `$VAR` in issue text no longer causes a crash for all callers. (BUG-2362)
- **`implement-issue-chain` routes passed issues to the caller's skip file** — Passed issues now routed to the dedup file; skip file is no longer polluted. (BUG-2374)
- **Scratch-pad redirect hook intercepts `Read` tool calls** — `Read` interception removed; `Edit`/`Write` tools no longer broken after a redirected command. (BUG-2357)
- **`is_runnable_loop` non-deterministic for `from:`-inheritance loops** — Cold/warm process ambiguity resolved for inherited loop definitions. (BUG-2344)
- **`auto-refine-and-implement` exit-proxy accounting** — Replaced exit-proxy heuristic with ground-truth closure; verdict table and go-no-go accounting now accurate.
- **`sprint-build-and-validate` launders sub-loop verdicts** — Sub-loop pass/fail no longer bubbles up as the sprint's own verdict.
- **`sprint-build-and-validate` requires a sprint name** — Sprint name argument is now optional; bare invocation works.
- **Bash `:-default` syntax in loop FSM files** — Seven sites replaced with engine-native `:default=` to prevent runtime interpolation crashes.
- **Learning-test extractor bypasses `resolve_host()`** — LLM call now routed through `resolve_host()` instead of direct Anthropic SDK; respects `LL_HOST_CLI`.

### Changed

- **`loops.run_defaults.include` config field** — New allowlist field for default loop routing; loop-router and composers respect the configured include list. (ENH-2371)
- **`ll-loop list` output formatting** — Improved readability and structure of loop catalog display. (ENH-2350)
- **`general-task` emits `summary.json` on terminal `done`** — Summary artifact is now written on every clean exit, not only on `max_steps`. (ENH-2365)
- **`audit-loop-run` captures literal values verbatim** — Captured FSM context values shown as-is; PID-corruption heuristic added to detect `$$`-escaped paths. (ENH-2367)
- **`interactive-component-generator` gains diagnose enrichment** — `failure_reason` discriminator and root-cause access added to the FSM. (ENH-2366)
- **Evidence-gate contract for LLM evaluator verdicts** — FSM `check_semantic`/`llm_structured` states now require verbatim citation; reduces self-grading optimism. (MR-8, improve(fsm))
- **PMI/lift scoring in sequence-suggestion ranking** — Analytics now ranks workflow suggestions by pointwise mutual information. (improve(analytics))
- **Brainstorm `novelty_threshold` lowered to 0.55** — Saturation/early-stop gate now activates in practice. (ENH-2356)
- **`scope-epic`/`link-epics` stop overloading `relates_to`** — Epic writers now use a dedicated field; post-write validation added. (EPIC-2330)
- **`ll-init` robustness improvements** — Graceful handling of unknown `--hosts` values, permission sweep, and version comparison. (ENH-2314)
- **Refine passes in `refine-to-ready-issue` and `autodev` switched to additive mode** — `--auto`/`--gap-analysis` flags passed consistently; no more full rewrites.
- **Auto-refine loops gain distinct error/skip routing** — Error and skip paths now separated; verdict finalized on loop exit.
- **Dedicated tests for incidental-only modules** — Coverage added for modules only exercised indirectly by other tests. (ENH-2328)

### Removed

- **`restore_best` and `snapshot_issue` states from `refine-to-ready-issue`** — Retired the best-snapshot retention guard (ENH-2037) now that all refine passes are additive (`--auto`/`--gap-analysis`); the "late rewrite regresses a better earlier iteration" failure mode no longer applies. `check_outcome.on_yes` now routes directly to `done`. `artifact_versioning: true` flag removed (was inert for `issue-management` category loops). (ENH-2364)

## [1.133.0] - 2026-06-27

### Added

- **`ll-issues epic-consistency` subcommand** — Detects and reconciles EPIC body/parent drift across the issue tree. (FEAT-2332)
- **`create-epics-from-unparented` skill** — New skill to generate EPIC issues from orphaned features and enhancements. (FEAT-2338)
- **`--include-summary` flag for `ll-issues list --json`** — Inline summary fields in JSON list output. (ENH-2345)
- **Interactive component generator loop** — FSM-driven harness for iterative component generation. (8f96b19a, 99978ec1)
- **Generic host-parametrized conformance harness** — Reusable conformance test framework across host targets. (9a00553c)

### Fixed

- **`ll-init` re-init clobbers unmodeled config keys** — Preserves unknown keys during re-initialization. (BUG-2310)
- **`ll-init` writes null leaves to generated config** — Strips `None` leaves from `build_config` output. (BUG-2311)
- **`ll-init --dry-run` preview diverges from actual `--yes` actions** — Routes `--dry-run` through real writers to eliminate preview drift. (BUG-2312)
- **`ll-init apply` is lossy vs `--yes`** — Apply path now produces identical artifacts to `--yes`. (BUG-2313)
- **`ll-parallel` silently skips learning gate for unrefined issues** — Resolves learning targets just-in-time per worktree. (BUG-2320)
- **Autoprompt enabled-default mismatch** — Flips default to `True` to match schema, restoring the feature on standard installs. (BUG-2321)
- **`cleanup-worktrees` drifts from canonical `_is_ll_worktree` logic** — Delegates to `ll-parallel --cleanup-orphans`. (BUG-2324)
- **`review-epic` counts `relates_to` as children** — Now uses `parent:` backrefs only, consistent with `epic-progress`. (BUG-2333)

### Changed

- **Learning-test target detection is now just-in-time** — Consistent across `ll-auto`, `ll-parallel`, and `ll-sprint`. (ENH-2319)
- **EPIC schema normalization** — Standardizes `type:` casing; migrates `children:` frontmatter to `relates_to:`. (ENH-2331)

## [1.132.0] - 2026-06-26

### Added

- **Package host-agnostic templates into the wheel** — Cross-host delivery of design tokens, hooks, and Codex adapter; all non-editable installs now resolve templates correctly. (FEAT-2274)
- **`ll-verify-package-data` — package-data completeness gate** — Left-shift guard that lints `__file__` escapes, checks MANIFEST.in coverage, and smoke-tests wheel contents; exits 1 on any violation. (ENH-2277)
- **4-tier issue template precedence lookup** — `resolve_templates_dir()` checks user override → project override → plugin root → shipped defaults in priority order. (ENH-2285)
- **`ll-issues sections` CLI subcommand** — List and query issue template sections from the command line. (ENH-2286)
- **`ll-init` deploys issue templates on init** — `deploy_issue_templates()` wired into the full init sequence. (ENH-2287)
- **Policy-router branch in `create-loop` wizard** — New wizard path generates policy-router FSM templates. (ENH-2299)

### Fixed

- **CLI logo excluded from wheel** — Repoints `get_logo()` to in-package `assets/` path; no longer returns `None` on non-editable installs. (BUG-2276)
- **`hooks/` package data excluded from wheel** — Prompt template and Codex adapter now included; prompt-optimization hook and Codex onboarding no longer silently break. (BUG-2275)
- **`skill_expander` disables prompt pre-expansion on non-editable installs** — Host-skill-dir awareness restored; pre-expansion no longer silently disabled. (BUG-2278)
- **Option J guillotine `usage_ratio` measures wrong metric** — Now measures context-window occupancy, not cumulative session tokens. (BUG-2280)
- **Option J guillotine missing `_check_issue_already_done` guard** — Guard added to prevent re-processing completed issues. (BUG-2281)
- **Per-character SGR wrapping in FSM diagrams** — Batch SGR sequences in `_draw_box` eliminate raw ANSI fragments in CLI recordings. (BUG-2284)
- **`rn-decompose` double-counts decomposed parents** — Removed double-write to `skipped.txt` from `enqueue_children`. (BUG-2289)
- **`_find_prompt_file` resolves wrong path when `CLAUDE_PLUGIN_ROOT` is set** — Drops stale `CLAUDE_PLUGIN_ROOT` branch; resolves correctly on all install types. (BUG-2295)
- **CUA loop never fast-fails on LLM auth failure** — Added `NON_RECOVERABLE` error class and `output_contains` error-pattern routing; dead-code path removed. (BUG-2302)
- **FSM diagram action-row border overflow** — Fixed layout rendering in `_draw_box`. (BUG-2303)
- **`loop_complete` event missing `error` field** — Field added and child error surfaced to parent context. (BUG-2304)
- **FSM validator silently passes unresolvable `loop:` references** — `_validate_loop_references()` now called at definition time; catches missing files before runtime. (BUG-2305)
- **FSM runner not hardened against broken-pipe and spawn failures** — Runner now catches and handles these errors gracefully.
- **`char_cap` default misaligned across config sources** — Aligned to 1200 across all sources.
- **`state_enter` schema `iteration_count` field inadvertently removed** — Field restored.

### Changed

- **Centralized model→context-window mapping with 1M support** — Single authoritative table; 1M-token models now handled correctly. (ENH-2282)
- **Updated doc/agent/skill references after hooks in-package move** — Post-BUG-2275 cleanup of all stale path references. (ENH-2291)
- **`general-task` OOM resilience** — Added token-budget and OOM-aware post-mortem to `do_work`. (ENH-2293)
- **`ll-issues list` truncates long titles** — Titles now fit one line in list output. (ENH-2284)
- **`audit-loop-run` auto-scales `--tail`** — Tail size now proportional to run size instead of fixed at 200. (ENH-2290)
- **`ll-logs tail` gains `--project DIR` flag** — Cross-project consistency with other `ll-logs` subcommands. (ENH-2297)

## [1.131.0] - 2026-06-25

### Added

- **OpenSCAD model generator built-in FSM loop** — New `openscad-model-generator` loop for generating and iterating on parametric 3D models using FSM-driven prompting. (FEAT-2269)
- **`ll-issues next-id --count N` batch allocation** — Allocates a block of N sequential IDs in one call, eliminating race conditions when scripts need multiple IDs. (ENH-2268)
- **Centralized model→context-window mapping with 1M support** — Context-window limits moved to a single authoritative table; 1M-token models now handled correctly.

### Fixed

- **FSM validator now emits WARNING for unresolvable `loop:` references at definition time** — `load_and_validate()` calls the new `_validate_loop_references()` check that catches missing files before runtime, shifting `FileNotFoundError` from deep sub-loop dispatch to a zero-cost definition-time warning. (BUG-2305)
- **Per-character SGR wrapping artifacts in FSM diagrams** — Batch SGR sequences in `_draw_box` to eliminate per-character wrapping that caused visual artifacts in video/terminal recordings. (BUG-2284)
- **`ll-session` skill events missing backfill path** — Added `_backfill_skill_events` to populate pre-init history so `ll-logs stats` no longer undercounts sessions. (BUG-2283)
- **`ll-issues set-status --cascade` follows wrong edges** — Restricted `--cascade` to `parent:` edges only; `relates_to` and `blocked_by` edges are no longer traversed. (BUG-2265)
- **`detect_installation` discards plugin scope** — Reads scope from discovery result and propagates `installPath`; project installs no longer mislabeled as global. (BUG-2266)
- **`rn-implement` report state writes only `}`** — Wrapped `report` summary `printf` block in group redirect so `summary.json` is written correctly. (BUG-2267)

### Changed

- **`rn-refine verify_score`** — Added diff-based phantom convergence check to prevent false-positive convergence signals.
- **`ll-issues list` title truncation** — Long issue titles now truncate to fit terminal width.
- **`--cascade` edge restriction documentation** — Clarified `--cascade` semantics in API docs and loop guides.

## [1.130.0] - 2026-06-22

### Changed

- **`ll-init` PyPI version-check and --upgrade flag** — Detects version drift against PyPI and exposes `--upgrade` flag for end-user upgrades. (ENH-2256)
- **`general-task` check_done section replacement** — `check_done` now replaces (not appends) the Sample Verification section on each pass, preventing duplicate accumulation. (ENH-2255)
- **`/ll:init` `--codex` flag removal** — Removed deprecated `--codex` flag from COMMANDS.md documentation. (ENH-2254)

### Fixed

- **`general-task` completion gate cleanup** — Removed `FAILED_SAMPLES` from the completion gate and added `WORK_COMPLETE` escape hatch. (33be1d1)

## [1.129.0] - 2026-06-21

### Added

- **`ll-session export` subcommand** — Streams `history.db` tables as JSONL with type discriminators; high-volume tables are opt-in; `--max-sessions` caps backfill runs; backfill now reads project config correctly. (ENH-2252)
- **`ll-init` install detection** — Detects existing plugin installations and version drift; `--yes` headless mode auto-installs or upgrades the pip package; new `install_source` field written to `ll-config.json`. (ENH-2253)

### Fixed

- **`brainstorm` loop resilience** — Added `on_error` routes to all states and set `on_handoff` to `spawn` for autonomous resumption after context handoffs. (ce7e680)
- **Skill count drift** — Corrected stale skill count in `CONTRIBUTING.md`, `README.md`, and test assertions. (3c3f2de, 8b7f543)

## [1.128.0] - 2026-06-20

### Added

- **Brainstorm built-in FSM loop** — New `brainstorm` loop for structured ideation with FSM-driven phases. (FEAT-2248)
- **`ll-init` wizard improvements** — Wizard pre-populates from existing `ll-config.json`; surfaces `decisions`, `scratch_pad`, `session_capture`, and `prompt_optimization` toggles; `--clear` and `--show-diagrams` are now recommended defaults. (ENH-2240, ENH-2241, ENH-2243)
- **`general-task` pre-flight test baseline** — Runs a test baseline before task work begins to surface pre-existing failures. (ENH-2244)
- **FSM recurrent-window circuit breaker** — Detects non-consecutive repeated state failures and halts runaway loops early. (ENH-2245)
- **Auto-invoke `explore-api` at learning test gate** — Missing or refuted learning test targets automatically trigger `explore-api` at the gate. (ENH-2242)

### Fixed

- **`rn-remediate` over-triggers `--full-rewrite`** — `refine_first`/`refine_followup` paths added; complexity gate and catch-all diagnose no longer route to `--full-rewrite`. (ENH-2247)
- **`rn-implement` diagnostic conflation** — `SCORES_MISSING` and `SIZE_REVIEW_FAILED` split into distinct diagnostic record states. (ENH-2250)
- **`continue_work` timeout detection** — `do_work` exit code 124 now detected and the oversized step is split automatically. (ENH-2246)
- **`ll-init` stale subdirectory references** — Replaced stale `completed`/`deferred` subdirs with `epics` in `_ISSUE_SUBDIRS`.

### Changed

- **`decisions.auto_generate` prefix filter** — `generate_from_completed` now respects the `auto_generate` prefix filter in config. (ENH-2239)
- **EPIC-1929 rescoped post-Hermes** — HITL adapter scope refined after Hermes integration; curated `.ll` artifacts tracked. (ENH-2249)
- **Harness optimization guide** — Added missing MR-2 row to design rules table; fixed incorrect MR-1 routing chain in canonical example. (ENH-2236, ENH-2237)
- **Policy router guide** — Corrected inaccurate `simulate` claim for policy-router loops. (ENH-2238)
- **Learning tests guide** — Fixed Release Gate section. (ENH-2235)

## [1.127.0] - 2026-06-19

### Added

- **Learning test suite integration** — `learning_tests_required` auto-populated by `refine-issue` and `wire-issue`; `ll-sprint` pre-flight batch gate; `ll-parallel` per-worktree proof-first-task wrapper; `ll-manage-release` blocks on stale/refuted dependencies; `create-loop` wizard inserts assumption-firewall for external API loops; `scope-epic` auto-generates learning test sub-issues; eval harness adds `learning_tests_required` as machine-checkable criterion. (ENH-2209, ENH-2210, ENH-2212, ENH-2214, ENH-2215, ENH-2219, ENH-2220, ENH-2221)
- **Learning test observability** — Orphaned record detection via `ll-learning-tests orphans`; records injected into `ll-history-context` output; `ll-ctx-stats` adds a learning test coverage dashboard section; `confidence-check` rubric wires in learning test evidence; `ll-history-context` adds per-issue level-0 condensed summaries. (ENH-2216, ENH-2217, ENH-2218, ENH-2231, ENH-2232)
- **FSM decision-table editor** — `edit-routes` adds a decision-table view for route configuration, state row deletion, terminal stub addition, and compound (multi-dimension) decision-table mode; `lib/policy-router` fragment provides a rubric + conjunctive decision table gate. (ENH-2164, ENH-2227, ENH-2228, ENH-2233)
- **`general-task` per-step `verify_step`** — Whole-suite gates no longer block every loop step; scoped per-step verification reduces false-positive gate failures. (ENH-2225)

### Fixed

- **`refine-issue` scope guard** — Edit tool restricted to `.issues/**`; refine-issue was implementing code in source files instead of documenting gaps. (BUG-2224)
- **`rn-remediate` diagnose routing** — Wrong confidence threshold caused the diagnose state to route `REFINE` on ready issues; now uses `diagnose_confidence_floor`. (BUG-2230)
- **`ll-logs --window-days` anchor semantics** — Standardized anchor to wall-clock time across all subcommands. (ENH-2130)
- **`ll-logs` stats JSON null fields** — Removed always-null `errors`/`error_rate` stubs from stats output. (ENH-2131)

### Changed

- **`ll-logs` signal detection** — Deduplicated `_extract_tool_name` / `_extract_eval_invocation` into a shared `_detect_ll_signal` helper. (ENH-2132)
- **`ll-logs` edge computation** — `_compute_edges` transition counter hoisted out of the per-n-gram loop; reduces complexity from O(K·N²) to O(K·N). (ENH-2133)
- **`ll-logs` code cleanup** — Removed double import, replaced `readlines()` with streaming read, wrapped bare string paths with `Path`. (ENH-2134)

## [1.126.0] - 2026-06-17

### Added

- **Feature branch workflow** — Full suite: `--feature-branches` CLI override for `ll-parallel`/`ll-sprint`, branch cut from `base_branch` (not `HEAD`), PR URL and branch name tracked in issue frontmatter, issues held at `in_progress` until PR merges, `--prune-merged-branches` for cleanup, sprint-wave awareness, end-to-end docs and integration test. (ENH-2173, ENH-2174, ENH-2175, ENH-2176, ENH-2177, ENH-2181, ENH-2182, ENH-2183)
- **Pre-compact handoff** — Core Python hook, Claude Code adapter, `PostToolUse` session-capture event hook, docs/config wiring, and event-log read path integration. (FEAT-1113, FEAT-1156, FEAT-1157, FEAT-1158, FEAT-1262, FEAT-1264)
- **Hermes integration enablement** — `ll-loop run` model/host action passthrough, `ll-loop list` visibility filter, JSON output contract stability, and integration docs transport fixes. (ENH-2197, ENH-2198, ENH-2199, ENH-2200)
- **Session-end hook** — Sweeps stale cross-issue status references at session close. (FEAT-1680)

### Fixed

- **FSM `InterpolationError` crashes on bypass paths** — Built-in loops that reference captures from states that may not have executed on bypass paths now carry `:default=` guards; 10 loops patched across the capture-ordering fix series. (BUG-2094, BUG-2111, BUG-2112)
- **`general-task` loop** — `verify_step` false-pass corrected for non-Python tasks; removed unbounded per-step retry spin. (BUG-2127)
- **`sprint-refine-and-implement`** — Now accepts both named sprint files and EPIC ids, matching `goal-cluster`'s dual-shape resolver. (BUG-2136)
- **Sprint test failures** — Fixed 21 test failures from stale monkeypatch targets and hintless-wave serialization edge cases. (BUG-2150)
- **Feature branch PR readiness** — `use_feature_branches` PR-ready signal now accurately reflects push and PR creation status. (BUG-2172)
- **Option J continuation scope-guard** — Single-issue `ll-auto --only` runs can no longer escape their scope and implement unrelated backlog issues; `rn-implement` gains a `check_issue_status` pre-flight gate. (BUG-2201)
- **`rn-implement` deferred re-enqueue** — `deferred.txt` entries are now filtered by reason before the re-enqueue check. (BUG-2202)
- **FSM dual-counter semantics** — `max_steps` counts total FSM steps while `max_iterations` counts loop body iterations; CLI flag renamed `max_iterations` → `max_steps` across CLI, tests, skills, docs, and loops. (BUG-2204, BUG-2205)

### Changed

- **FSM validator `:default=` guard recognition** — Validator now recognizes `:default=` guards in capture-reachability checks, eliminating false-positive `WARN` messages on bypass-path captures. (ENH-2128)
- **`loop-composer` and `loop-composer-adaptive` error routing** — `re_decompose` wired to `on_error`; `check_auto_plan` error paths route to the HITL gate instead of failing silently. (ENH-2135)
- **`loop-router` loop discovery** — `discover_loops` now passes `--visibility public` to filter hidden loops from selection. (ENH-2203)

[1.130.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.129.0...v1.130.0
[1.129.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.128.0...v1.129.0
[1.128.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.127.0...v1.128.0
[1.127.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.126.0...v1.127.0
[1.126.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.125.0...v1.126.0

## [1.125.0] - 2026-06-15

### Added

- **Marker-gated refine+wire enforcement in `rn-remediate`** — Above-minimal-complexity issues now require at least one refine and one wire pass before implementation, enforced by write-once markers. 8 new test cases validate the gate logic. (ENH-2163)
- **`classify` evaluator for multi-way FSM routing** — New evaluator type enables single-state multi-way routing without chaining multiple boolean states. (2178d861)
- **`from:` stub consolidation in built-in loop catalog** — Overlapping built-in loops consolidated into `from:` stub entries; stubs are hidden from `ll-loop list` output. (ENH-2161, ENH-2194)
- **`issue_snapshots` table and snapshot functions** — New `session_store` table records point-in-time issue snapshots with backfill support via `ll-session`. (74804b1f)
- **`rn-implement` re-enqueues deferred blockers** — When a blocker resolves within the same run, deferred issues are automatically re-enqueued for processing. (c62c6fdb)
- **`distill-decisions` loop and extract-from-completed** — New loop extracts decisions from completed issues and distills them into the decisions log. (b12ce4d7)
- **`lib/rubric-router.yaml` and `rubric-refine.yaml`** — New reusable library loops for rubric-driven routing and iterative refinement. (aa38dc03)
- **History-db integration points wired** — ENH-2151 integration complete; history entries now correlate session and issue data for enriched context. (a55ea77f)

### Fixed

- **`loop-composer-adaptive` correctness rewrite** — Fixed 8 design-level defects: step-output reference resolution (`{{step_id}}` placeholders), replan budget accounting (was consuming budget on CONTINUE), `validate_replan` state for plan validation, JSONL interpolation corruption, and dead LLM evaluator removal. Fixes propagated to `loop-composer.yaml`. (ENH-2168)
- **`os.killpg` for atomic process-group termination** — FSM shell states now use `os.killpg` to reliably terminate entire subprocess trees on timeout or stop. (d6a616fc)
- **Selector-based wall-clock I/O in FSM shell states** — Threading-based stderr drain replaced with selector-based I/O, eliminating subprocess output hangs. (a3fd43cc)
- **`ll-loop stop` kills descendant processes** — Stop signal now propagates to all descendant processes, not just the direct child. (8dbacec0)
- **`rn-remediate` verdict routing (BUG-2169)** — Replaced `on_success`/`on_error` with explicit verdict routing in decide, wire, and refine states. (4b9e9144)
- **`rn-remediate` grep dedup guard (BUG-2170)** — Replaced `grep -cxF` with `grep -qxF` to fix implemented-count undercount. (a584ba18)
- **`rn-remediate` wire/refine bypass gaps** — Fast-path and diagnose routing now correctly enforce wire and refine passes; CONVERGED_PASS branch guarded against `decision_needed`. (164188c4, 894b3fc3)
- **`loop-composer` catalog JSON injection** — Escaped `${captured.catalog.output}` in Python comment to prevent shell variable interpolation. (f1c60514)
- **`is_runnable_loop()` from: stub inheritance** — FSM correctly resolves inheritance for `from:` stubs in runability checks. (80cce461)
- **3 mypy type errors** — Fixed type errors in concurrency and decisions modules. (ab8994b6)
- **`ll-logs eval-export` `-j` short flag** — Added `-j` as an alias for `--json`. (27560827)

### Changed

- **`rn-remediate` routing migrated to `classify` evaluator** — Routing cascades now use the new classify evaluator and `route:` table syntax for cleaner multi-way dispatch. (004bcb4d)
- **Ancestor-process detection in `LockManager`** — `LockManager.find_conflict()` now detects conflicts with ancestor processes to prevent false lock-free signals. (43dbdeb2)

[1.125.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.124.0...v1.125.0

## [1.124.0] - 2026-06-14

### Added

- **`SprintWorkerContext` dataclass** — New type in `little_loops.parallel.types` (alongside `WorkerResult`) that carries `issue_id` and `branch` for sprint worker identity injection into guillotine continuation prompts. (BUG-2141)
- **`/ll:adversarial-verify-loop`** — New skill that generates an FSM adversarial verification loop from a single issue ID. Probes boundary values, malformed/hostile inputs, and failure modes; treats "fewer than 3 probe classes attempted" as a FAIL via a non-LLM `output_numeric` filesystem gate. Adversarial counterpart to `/ll:verify-issue-loop`. (ENH-2047)
- **`--intent` / `--intent-limit` flags** — `ll-history`, `ll-deps`, and `ll-workflows` now accept `--intent` to filter output to a specific intent and `--intent-limit` to cap results per-intent bucket.
- **JSONL-based cache hit rate in `ll-ctx-stats`** — `ll-ctx-stats` reports the session-level JSONL cache hit rate alongside the existing per-tool context savings.
- **Visibility tier in `ll-loop list`** — Loops are now classified as `public`, `internal`, or `example`; `ll-loop list` surfaces this tier to make the harness catalog easier to navigate.
- **`ll-issues decisions suggest-rules`** — Surfaces decision history entries that are strong candidates for promotion to active rules based on recurrence and outcome patterns.
- **`ll-issues decisions promote`** — Converts a selected decision into a standing rule written to `.ll/decisions.yaml` and synced into `ll.local.md`.
- **`cua-agent-desktop` built-in FSM loop** — New loop for computer-use agent desktop automation tasks, available out of the box.

### Fixed

- **Sprint Option J guillotine no longer deadlocks the orchestrator** — When a sprint worker session hits the context limit and Option J fires, the fresh continuation session now receives a `## Sprint Worker Context` framing block that tells it which single issue to complete and to exit immediately after. Previously the fresh session would process multiple visible issues and block asking "What next?", deadlocking `process_issue_inplace()` indefinitely. Fix threads `SprintWorkerContext(issue_id, branch)` through `process_issue_inplace()` → `run_with_continuation()` → `assemble_guillotine_prompt()` and through `WorkerPool._run_with_continuation()`, covering both the summary-blob path and the `run_dir` file-write path. Both sequential wave and sequential retry call sites in `sprint/run.py` now pass the context. (BUG-2141)
- **`general-task` loop `verify_step` false-pass on non-Python tasks** — The verification step no longer claims success on tasks where the result is not testable as Python; unbounded per-step retry spin is also resolved. (BUG-2127)
- **`sprint-refine-and-implement` accepts EPIC IDs** — Previously dead-ended when given an EPIC id rather than a sprint file; now resolves the EPIC's sub-issues and processes them correctly. (BUG-2136)
- **`ll-loop simulate` sub-loop awareness** — Simulated runs now correctly model loops that delegate to sub-loops, preventing false results when testing composite loop definitions. (BUG-2137)
- **Sprint hintless-wave serialization and stale monkeypatch targets** — Fixed conservative serialization of hintless issues in the wave splitter and repaired stale monkeypatch targets in the sprint test suite. (BUG-2150)
- **FSM validator recognizes `:default=` guard in capture-reachability check** — The validator no longer flags states that provide a `:default=` fallback as unreachable-capture violations. (ENH-2128)
- **`loop-composer` error-routing hardened** — Added `re_decompose` on error in `loop-composer` and `loop-composer-adaptive`; `check_auto_plan` now routes errors to the HITL gate rather than terminating. (ENH-2135)
- **`test_cmd` null-coercion guard in FSM shell state** — Loops that reference `test_cmd` when it is null no longer raise a coercion error; the shell state skips the step cleanly.
- **Context monitor skips `SYSTEM_PROMPT_BASELINE` when transcript baseline is available** — Prevents inflated context estimates when a real transcript baseline exists.
- **Context monitor refreshes transcript baseline per turn via mtime detection** — Baseline is reloaded whenever the transcript file mtime advances, keeping usage estimates accurate across long sessions.
- **Sprint per-issue wall-clock timeout** — A wall-clock deadline is now enforced per issue in `ll-sprint`, preventing Option J from holding the orchestrator indefinitely when a worker stalls.

### Changed

- **`recursive-refine` folds issue-refinement deltas and gains alias** — Issue-refinement delta logic from a standalone loop is now folded into `recursive-refine`; the standalone path is aliased for backwards compatibility.
- **`auto-refine-and-implement` gains `scope` param and sprint-loop alias** — The `scope` parameter limits which issues are processed; a sprint-loop alias provides a convenient entry point from sprint workflows.
- **`loops.run_defaults` wired into `ll-init` generated config** — `ll-init` now writes the `loops.run_defaults` block into the generated `.ll/ll-config.json` so persistent run flags are available from first use.
- **Confidence-check score verification extracted into oracle sub-loop** — The score verification step in the confidence-check flow is now a reusable oracle sub-loop, improving composability.

## [1.123.0] - 2026-06-13

### Added

- **`loops.run_defaults` persistent config for `ll-loop run`** — Set persistent default flags (`--clear`, `--show-diagrams`, `--mode`) via config so they apply on every run without repeating them on the CLI. (ENH-2109)
- **`/ll:loop-suggester --from-sequences` mode** — Wires `ll-logs sequences` output into the suggester so it can propose loops from logged command sequences rather than only message history. (ENH-2103)
- **`ll-ctx-stats` skill-health signals from `ll-logs`** — `ll-ctx-stats` now surfaces per-skill fail rates, dead-skill candidates, and sequence anomalies mined from session logs. (ENH-2104)
- **`/ll:configure` surfaces `loops.run_defaults`** — The configure skill now exposes the new run-defaults config section for interactive setup. (ENH-2114)

### Fixed

- **FSM interpolation crash on unexecuted-state captures** — Loops that reference captures from states that may not have executed no longer raise `InterpolationError` at runtime. (BUG-2094)
- **FSM `capture-ordering` Bucket B `:default=` guards** — Added `:default=` fallbacks to all Bucket B states and classified previously-unlisted ALLOWLIST entries to prevent ordering-dependent evaluation failures. (BUG-2111, BUG-2112)
- **`LL_NON_INTERACTIVE` signal not delivered to skill subprocesses** — FSM prompt actions now correctly deliver the non-interactive signal to skills spawned as subprocesses; auto-detect was previously dead code. (BUG-2110)
- **`rn-remediate` `re_assess` MR-4 violation** — Added explicit `on_partial` and `on_no` routes to the `re_assess` state; missing routes caused the subloop to terminate with an error on non-yes verdicts. (BUG-2115)
- **`rn-plan-apo` stale `category` field** — Removed stale `category` field from loop definition that caused validation noise.
- **`loop-composer` `validate_plan` catalog read** — Catalog is now read from disk in `validate_plan` and prior errors are fed back to the planner for self-correction.

### Changed

- **`rn-remediate` implemented counter moved to `emit_implemented`** — Counter increment now happens in `emit_implemented` rather than an earlier state, fixing double-counting on retries. (ENH-2119)
- **`rn-remediate` `WIRE(ambiguity)` heuristic guarded on `CHANGE_SURFACE == 0`** — Prevents the ambiguity branch from firing on decision-driven changes when the integration map already exists. (ENH-2116)
- **Sub-loop composition architecture decision recorded** — ARCHITECTURE-030 documents the decision to use reusable sub-loop composition over inlined per-issue states for orchestrator FSM layers 1+2. (ENH-2106)
- **`ll-loop simulate` `run_dir` parity documented** — Guides updated to note that simulate now injects `run_dir` into FSM context and how to wire `run_defaults` via configure.

## [1.122.0] - 2026-06-12

### Added

- **`ll-loop calibrate-budget` subcommand** — Analyzes whether increasing `max_iterations` will improve outcomes by checking evaluator variance (Bernoulli `p*(1-p)`) across recent runs; surfaces toothless evaluators before wasting token budget on additional iterations.
- **`check_substrate` feasibility gate for planning loops** — Optional state that validates loop inputs against known constraints before expensive planning begins, routing to `INFEASIBLE` on hard blockers. (ENH-2085)
- **`--cross-host` flag for `ll-loop run --baseline`** — Runs baseline evaluation across all configured host CLIs and reports per-host pass rates and CI deltas. (ENH-2086)
- **`--json` flag for `ll-loop validate`** — Emits validation findings as structured JSON for downstream tooling and CI integration. (ENH-2090)
- **`ll-init` TUI config-capability parity** — The interactive terminal TUI now covers all config fields reachable via `/ll:init`, including design tokens, analytics, scratch pad, and context monitor settings. (ENH-2092)
- **DSL eval task mode in `ll-harness` and `/ll:create-eval-from-issues`** — New `dsl` task type generates native `ll-loop` DSL fixtures from issue frontmatter, enabling replay-based regression testing of loop behavior. (ENH-2081)
- **`--model` flag for `ll-harness prompt`** — Override the inference model per `ll-harness` prompt invocation without modifying config.
- **Wilson 95% CI reporting in `ll-loop run --baseline` and `diagnose-evaluators`** — Pass rates now report `p ± margin` alongside raw counts, surfacing statistical uncertainty on small sample sizes.
- **Shallow-iteration failure mode detector in loop audit** — `ll-loop audit` now flags loops where the winning iteration is consistently iteration 1, indicating the loop adds no value over a single unguided call.

### Fixed

- **pytest OOM on `builtins.open` patch** — Test suite no longer allocates 100GB+ of memory when a test patches `builtins.open` with a bare `MagicMock`. (BUG-2108)
- **`from:` inheritance resolution in `_load_loop_meta`** — One level of `from:` inheritance is now resolved at load time; inherited config fields (e.g., `max_iterations`, `timeout`) propagate correctly to child loops. (ENH-2101)
- **Missing `on_partial` routes on LLM-judged states** — Added explicit `on_partial` routes to 9 built-in loops where an LLM-judged state had `on_yes` but no `on_partial`/`on_no`, causing silent dead-ends on non-yes verdicts. (ENH-2095)

### Changed

- **`/ll:init` skill deprecated; `ll-init` CLI is now the primary init path** — `/ll:init` now renders a redirect stub; all initialization flows route through the `ll-init` headless CLI. Closes EPIC-1978. (ENH-1982)
- **7 built-in loops migrated from `.loops/tmp/` to `${context.run_dir}`** — Intermediate artifacts are now isolated per run, preventing cross-run corruption when multiple instances execute concurrently. (ENH-2096)
- **`recursive-refine` / `implement-issue-chain` contract trio migrated to `${context.run_dir}`** — Shared-tmp references replaced with run-scoped paths for safe concurrent execution. (FEAT-2097)
- **`rn-remediate` `CONVERGED_STALLED` routing** — Routes through a budget-gated retry that reruns `diagnose` with a refreshed strategy rather than terminating silently. (ENH-2107)
- **`diff_stall` guards added to generator loop refine cycles** — Prevents infinite refinement when successive iterations produce identical output diffs.
- **`required_inputs` declared for all loops with a custom `input_key`** — Loops that require non-default inputs now declare them explicitly, enabling `ll-loop validate` to surface missing-input bugs before runtime.
- **`ll-logs scan-failures` enhanced** — Added project scoping, CLI allowlist filtering, and noise suppression to reduce false positives in failure mining.
- **`vega-viz` max-iterations summary handler** — Prevents silent termination when `max_iterations` is reached without a convergence verdict.

### Removed

- **`greenfield-builder` loop** — Removed the deprecated `greenfield-builder.yaml` loop. `rn-build` is the drop-in replacement for all spec-driven greenfield projects. (ENH-2100, FEAT-1993)

## [1.121.0] - 2026-06-10

### Added

- **`/ll:distill-traces` skill** — Mine successful execution history for a named loop and write reusable YAML state templates, transition patterns, and a `primitives.md` index to `scripts/little_loops/loops/lib/<loop-name>/`. Accepts `--min-success N` threshold (default 3); exits cleanly when history is insufficient. (FEAT-2078)
- **Per-state `model:` override for FSM loop states** — `StateConfig` now accepts an optional `model:` field. When set on a `prompt` or `slash_command` state, the specified model ID is passed as `--model <id>` to the host CLI for that state only; other states continue using the global default. A validation WARNING is emitted when `model:` is set on `shell`, `mcp_tool`, or `contract` states (where the host CLI is not invoked). Absent = existing behavior, fully backwards-compatible. (ENH-2073)
- **MR-6 generator-fix discipline rule in `ll-loop validate`** — Detects hand-patching anti-patterns where a `shell`-type state writes to the same file path as an LLM-generator state in the same loop, emitting a WARNING. Suppressed by `generator_fix_ok: true` for intentional post-processing cases. (ENH-2079)

### Fixed

- **`ll-issues` crashes on unrecognized argument `EPIC`** — `ll-issues list` no longer raises an unrecognized argument error when passed the `EPIC` type. (BUG-2069)
- **FSM shell actions crash on bash parameter expansion** — `${...}` in FSM `shell` actions no longer raises "Unknown namespace"; the interpolation engine now correctly passes through bash-style parameter expansions. (BUG-2074)
- **vega-viz phantom convergence** — `vega-viz` no longer terminates on the first `ALL_PASS` verdict while the judge still documents blocking defects; the convergence gate is now deterministic. (BUG-2066)
- **`rn-remediate` assess state missing routes** — Added `on_partial` and `on_no` routes to the `assess` state to prevent silent dead-ends on non-yes verdicts. (ab52d0df)
- **FSM rate-limit interceptor budget drain on success** — The interceptor now ignores `exit_code=0` and no longer consumes the `max_retries` budget on non-error responses. (fd25fcab)
- **`ll-logs` stale-worktree log severity** — Downgraded decoded-path log message from WARNING to DEBUG to reduce noise in normal operation. (a02045e3)

## [1.120.0] - 2026-06-09

### Added

- **`/ll:simplify-loop` skill** — Decompose loops into sub-loops and collapse state chains into flows. (FEAT-2063)
- **`rlhf-svg-generate` sub-loop** — Standalone SVG generation sub-loop extracted from `rlhf-animated-svg` for modular composition. (34189f86)
- **`rlhf-svg-refine` sub-loop** — Standalone refinement sub-loop for `rlhf-animated-svg`. (38742a7b)
- **`rlhf-svg-evaluate` sub-loop** — Standalone evaluation sub-loop for `rlhf-animated-svg`. (d19945fb)
- **`restore_best` guard in `refine-to-ready-issue`** — Score regression prevention in the refinement loop. (45edffd6)
- **`plan-research-iteration` oracle** — Extracted `rn-plan`/`rn-refine` research chain into a reusable oracle sub-loop. (0cfb0bfb)
- **Skip deferred issues in `verify-issues`** — `verify-issues` now skips deferred issues automatically. (20543eeb)
- **Session digest prompt in `/ll:init`** — The interactive init wizard now includes an ambient session digest option in Round 9.5. (ENH-2040)

### Changed

- **`rlhf-animated-svg` refactored to orchestration-only** — Parent loop now delegates evaluate/refine to sub-loops; ~400 lines reduced. (ENH-2050, ENH-2056)
- **`hitl-md` review loop simplified** — Reduced to core review surface with a lightweight confidence cue. (ENH-2058)
- **`VISION_*` env vars wired into `svg-image-generator`** — Vision feature gating now uses a `vision_gate` state. (ENH-2059)
- **Session digest enabled by default** — `SessionDigestConfig.enabled` now defaults to `True` with `char_cap: 800`. Sessions on fresh installs inject a capped ambient digest block at session start. Opt-out: set `history.session_digest.enabled: false` in `.ll/ll-config.json`. (ENH-2040)
- **CLAUDE.md update step in `ll-init` TUI** — Init wizard now includes a CLAUDE.md update step. (7deaadc0)
- **Evolution-trigger consumer in `analyze-history`** — Added consumer + correction retirement for evolution trigger patterns. (47de4e80)
- **`verify-issues` active-issues filter** — Filters to active issues only; fixes broken `ll-issues` call. (52535e31)

### Fixed

- **`fifo_pop` telemetry noise and convergence delta threshold** — Noise filtering and delta threshold corrected in FSM loops. (ENH-2061, 774eb499)
- **`ll-init` permission wiring** — Wired `deploy_design_tokens`, `history.session_digest`, and `explore-api` permission. (285a0b9c)
- **Loop routing assertions and oracle delegation** — Fixed FSM routing assertions, oracle delegation, and schema version in tests. (799b8c33, 3b060664)
- **Layered pinned-pane ladder diagram** — Added neighborhood fallback step. (a726ec9f)

## [1.119.0] - 2026-06-08

### Added

- **`ll-init` headless Python core** — New initialization command with a headless Python API for programmatic project setup. (FEAT-1979)
- **`ll-init` interactive terminal TUI** — New questionary + rich terminal UI for guided project initialization. (FEAT-1980)
- **`ll-init` host multi-select and adapter install dispatch** — `ll-init` can now configure multiple host adapters in a single run; replaces the `--codex` flag with a `--hosts` list for multi-host dispatch. (FEAT-1981)
- **`rlhf-animated-svg` built-in loop** — New FSM loop shipped as a built-in example for animated SVG generation with RLHF-style evaluation. (4cb6afb)
- **`apply-research` built-in FSM loop** — New loop for applying structured research artifacts to a codebase. (49f9cf8)
- **`--parent` filter for `ll-issues list`** — New `--parent` flag lets you filter issues by parent EPIC. (8abac80)
- **`scope-epic --auto` flag** — Non-interactive automation callers can now invoke `scope-epic` without HITL prompts. (004ea94)
- **`ll-loop` failure reason surfacing** — Loop completion summaries now display the failure reason when output is hidden. (4d2e65a)
- **`rn-build` `refine_seed` migration** — `refine_seed` moved from `issue-refinement` to `recursive-refine` for cleaner sub-loop separation. (2e7ce86)

### Changed

- **`ll-init` CLI reference** — Added `ll-init` documentation section to `docs/CLI.md`. (ENH-2019)
- **`rn-*` shared YAML fragments** — Extracted duplicated states (`plan_rubric_score`, `rate_limit_diagnostic`, and rn-* common states) into `common.yaml` fragments for maintainability. (e4df058, c6d657d)
- **`session_digest` enabled in project config** — Session digest is now enabled by default in the project configuration. (1c16c4d)
- **`analyze-history` evolution trigger detection** — Evolution trigger patterns are now surfaced in history analysis output. (7355afd)
- **CLI.md introduction accuracy** — Corrected CLI.md intro to accurately describe tool naming conventions. (ENH-2020)
- **`harness-optimize` trajectory paths** — Corrected trajectory artifact paths to use `.ll/runs/` prefix format. (ENH-2021)

### Fixed

- **`rn-build` scratch state isolation** — Moved `issue-refinement` scratch state from `.loops/tmp` to `run_dir` to prevent cross-run state corruption. (MR-3, a25c0ee)
- **`next-action` threshold resolution** — Threshold resolution is now config-first with 85/70 fallbacks instead of hardcoded values. (697eb2c)
- **`issue-refinement` broken-down issue gating** — Issues flagged as broken-down are now gated to the skip-list via `check_broke_down`, preventing re-processing. (de64d84)
- **`rn-remediate` implement counter** — Guarded against `api_error_retry` double-counting the implement counter. (9d1dff0)
- **`rn-build` multi-step harness fallback** — Added fallback discovery on resume for multi-step harnesses. (0799a0f)
- **`rn-build` `run_dir` preservation** — `run_dir` is now preserved across `with:` sub-loops; hard failures no longer masked. (002c901)
- **`rn-build` scope routing** — Hardened `scope_project` routing and added timeout guard for `tech_research`. (6c40bb1)
- **`rn-build` bash array expansion** — Escaped bash array expansion to prevent FSM interpolation collision. (5df42d0)
- **`goal-cluster` dispatch** — Fixed `--json` flag usage and corrected goal key passing to dispatch sub-loop. (8823199)
- **`harness-optimize` run_dir migration** — Migrated trajectory paths to runner-injected `run_dir`. (MR-3, 3ce98c1)
- **BUG-2022: HOST_COMPATIBILITY.md footnote count** — Corrected footnote reference from 'seven call sites' to match the actual six-row table; added `ll-sprint` to orchestration CLI table.

## [1.118.0] - 2026-06-07

### Added

- **`rn-build` resume-from-epic path** — Multi-session builds can now resume from a prior epic checkpoint, re-reading completed children and seeding the implementation queue from unfinished leaves. (ENH-2016)
- **`vega-viz` generator-evaluator loop** — New FSM harness for Vega / Vega-Lite data visualizations. Compile-gates broken specs via deterministic exit-code before LLM scoring; supports optional real data (CSV/JSON path via `--context data_path=`); defaults to Vega-Lite and escalates to full Vega only for custom/interactive composition; Playwright captures three interaction states as multimodal PNG input for the judge. `on_handoff: spawn`, `max_iterations: 20`, 2h timeout. (ENH-2010)
- **`canvas-sketch-generator` generator-evaluator loop** — New FSM harness for canvas-sketch (Matt DesLauriers) still-image generative art. Objective non-blank render gate (pixel statistics) hard-gates blank sketches before the LLM judge runs; per-iteration snapshots with deterministic best-iteration selection (`best.html`); `on_max_iterations: finalize` ensures `best.html` is always published. `on_handoff: spawn`, `max_iterations: 40`, 2h timeout.
- **`rn-implement` `blocked_by` pre-gate** — New `check_blocked_by` + `route_blocked_by` states gate all scheduling modes: issues with unmet `blocked_by` frontmatter deps are deferred (with named blockers) before entering the remediation budget, preventing the full `max_remediation_passes` budget from being spent on a structural blocker that prose remediation cannot clear. Fail-open: malformed frontmatter passes the gate. (ENH-2008)
- **`ll-auto` FSM loop + A/B parity harness** — New `ll-auto.yaml` FSM loop with an `ll-auto` shim and A/B parity harness for automated sequential issue processing. (FEAT-1902)

### Changed

- **`rn-build` normalize_spec pre-gate** — Validates and normalizes malformed specs before the first loop iteration, surfacing schema errors early rather than propagating them into sub-loop state. (ENH-2017)
- **`rn-refine` required_inputs + handoff mode** — `rn-refine` now declares `required_inputs` and sets `on_handoff: spawn` to match the autonomous rn-* contract.

### Fixed

- **FSM `max_iterations` context injection** — `max_iterations` is now injected into the FSM context at loop start, allowing loop body templates to reference `{{ max_iterations }}`. (ff45e10)
- **`rn-implement` init queue seed bash escaping** — Fixed unquoted bash parameter expansion that could corrupt queue entries when issue titles contained special characters. (83ecdab)
- **`rn-build` empty-loop crash** — Added `check_harness_name` guard to prevent a crash when the sub-loop name resolved to an empty string. (254bb29)
- **`vega-viz` EVAL_PASS token** — Corrected the evaluation pass token; added `canvas-sketch-generator` loop entries. (ed1d061)
- **Session store / logs path redirection** — `resolve_history_db` is now the single path-resolution entry point for both the session store and logs paths, fixing `LL_HISTORY_DB` overrides not propagating to the logs writer. (69e81a5)
- **BUG-2009: autodev/recursive-refine issue resolution routing** — Routes issue resolution through `ll-issues` path instead of autodev, preventing silent loss of unresolved issues. (e2b297f)
- **`rn-implement` stall+no-children routing** — Routes stalled issues with no children to `defer` instead of silently skipping them. (a5fd199)
- **`rn-implement` sub-loop `on_error` classifier laundering** — Splits `on_error` routing from classifier laundering to prevent error states from being misclassified as completions. (21162f0)
- **`rn-decompose` early `visited.txt` write** — `enqueue_children` no longer writes `visited.txt` before children are confirmed, preventing premature exclusion of valid subtasks. (b1ca34c)
- **BUG-2007: `rn-remediate` routing/convergence defects** — Fixed four routing defects: stale convergence detection, missed `CONVERGED_STALLED` route, premature budget exhaustion, and duplicate result emission. (c36343b)
- **`rn-*` issue ID type-prefix mismatch tolerance** — Resolution logic now tolerates ID mismatches where the file prefix doesn't match the stored reference prefix. (b49dc70)

## [1.117.0] - 2026-06-06

### Added

- **`rn-build` capstone orchestration loop** — New FSM loop that orchestrates the full rn-* sub-loop suite (refine, decompose, implement, remediate) as a capstone pipeline. Accepts a high-level goal, runs the rn-* suite in sequence, and returns a structured build summary. (FEAT-1992)
- **`rn-build` orchestration loop + `value_ranked` schedule mode** — Intermediate `rn-build` loop wires `schedule_mode: value_ranked` into the `goal-cluster` executor, enabling priority-ordered dequeuing of implementation work. (FEAT-1991)
- **`loop-composer` orchestration loop** — New built-in FSM loop that accepts a natural-language goal too large for a single loop, decomposes it into an ordered DAG of up to 8 loop-router (or direct sub-loop) invocations, presents the plan for HITL approval, then walks the DAG sequentially, returning a structured JSON summary of all step results. Use `ll-loop run loop-composer --input "your goal"`. Controlled by `orchestration.composer.*` config settings. (FEAT-1808)
- **`loop-composer-adaptive` orchestration loop** — Fault-tolerant variant of `loop-composer`. When a sub-loop fails, a reassess gate decides `CONTINUE` / `REPLAN_TAIL` / `ABORT` — preserving completed-step checkpoints and replacing only the unexecuted tail on `REPLAN_TAIL`. Replanning is bounded by `max_replans` (default 2); `ABORT` fires on exhaustion or irrecoverable failure. Use when mid-plan recovery is preferred over a full restart. (FEAT-1983)
- **`orchestration.composer.adaptive` config settings** — New config sub-object wiring the `loop-composer-adaptive` catalog (`enabled`, `max_replans`, `reassess_timeout`). Set `orchestration.composer.adaptive.enabled: true` to prefer the adaptive variant by default. (FEAT-1984)
- **`ClusterConfig` / `orchestration.cluster` settings** — New `ClusterConfig` dataclass and `orchestration.cluster` config block for the `goal-cluster` loop: `max_batch_size` (default 5), `enable_dedup` (default true), `propagate_context` (default true). Controls how related goals are batched and how cross-batch hints are propagated. (FEAT-1987)
- **`goal-cluster` orchestration loop** — New built-in FSM loop for sprint- or EPIC-shaped input. Accepts a list of goals (raw multi-line, sprint name, EPIC ID, or JSON list), normalizes them, groups related goals into batches by predicted loop, executes each batch sequentially with per-batch reassess gates, propagates cross-cutting context between batches, and synthesizes a cluster-wide summary. Use when you have multiple related goals that share context, rather than `loop-composer` (single decomposable goal) or `loop-router` (single goal). (FEAT-1988)
- **`goal-cluster` as 4th option in `/ll:create-loop` orchestration wizard** — The orchestration branch of the `/ll:create-loop` wizard now offers `goal-cluster` as a fourth template choice alongside `loop-router`, `loop-composer`, and `loop-composer-adaptive`. Selects the multi-goal fan-out template with cross-batch context propagation.
- **`ll-logs-telemetry-digest` FSM loop** — New loop that mines telemetry events from `ll-logs stats` output into a digest report, with configurable retention windows and structured JSON output. (FEAT-1925)
- **Session-store retention/compaction policy** — `history.db` raw event tables now support configurable retention and compaction via the `history.*` config namespace, keeping DB size bounded on long-running projects.
- **`ll-logs eval-export` subcommand** — New subcommand that reconstructs `ll-harness` EvalFixture files from session log JSONL, enabling replay-based regression testing of skill behavior. (FEAT-1971)
- **`ll-logs diff` subcommand** — Session behavioral comparison tool: diffs two session logs to surface added/removed tool calls, changed outputs, and behavior regressions. (ENH-1924)
- **EvalFixture v1 design spec** — Captured design specification for the eval-export fixture format, wired into `ll-harness` as a structured test primitive. (FEAT-1968)
- **FSM static validation of captured variable reachability** — `ll-loop validate` now statically checks that every `{{ var }}` interpolation in a loop has a reachable `capture:` source in the FSM graph, surfacing missing-capture bugs before runtime. (ENH-1961)
- **FSM `:default=` and `?` safe interpolation syntax** — Variables can now be written as `{{ var:default=fallback }}` or `{{ var? }}` to suppress "missing variable" errors when an optional context key is absent.
- **`decisions` coupling entry type** — New `coupling:` decision entry type records architectural coupling decisions; surfaced in `/ll:wire-issue` static analysis layer. (FEAT-1736)
- **`ll-logs scan-failures` subcommand** — Mines failed `ll-*` Bash invocations from interactive session JSONL logs. Pairs assistant `tool_use` blocks with `tool_result` records to detect nonzero exits (`is_error: True`) and Python tracebacks. Suppresses transient errors (rate limits, timeouts) and expected-nonzero gates (`ll-verify-*`). Clusters failures by `(tool, normalized-error-signature)` and emits candidates as text or `--json`. `--capture` creates BUG issue files for each distinct cluster. (ENH-1922)
- **`ll-logs stats` subcommand** — Aggregates per-skill invocation frequency, correction count, and correction rate from `skill_events` in `.ll/history.db`. Prints a box-drawn table (or `--json` array) sorted by invocation count or correction count. (ENH-1921)
- **`ll-logs sequences` subcommand** — Mines tool-level n-grams (ordered chains of ll skill/command/tool invocations) from extracted log corpora, with occurrence counts and per-edge transition frequencies. Reusable extraction primitive for `loop-suggester`. (ENH-1919)
- **`ll-logs dead-skills` subcommand** — Identifies skills that appear in SKILL.md definitions but have zero invocations in session history, flagging candidates for removal or consolidation.
- **`ll-verify-triggers` CLI** — New CLI tool that validates skill description trigger accuracy against should-fire and should-NOT-fire phrasings. Reports per-skill precision/recall and cross-skill collision matrix. Exits non-zero when a skill falls below threshold or collides with another. (FEAT-1910)
- **Syrupy snapshot testing for CLI output** — Added `syrupy` as a test dependency; CLI output snapshot tests now use snapshot assertions for regression detection. (ENH-1965)
- **170+ new CLI-layer tests** — New parametrized test suites for loop subpackage (100 tests), sprint subpackage (69 tests), and dedicated P1 coverage-gap files. (ENH-1966)
- **`ll-history-context --for-skill` flag** — Gates history-context injection on `history.planning_skills` config; exits 0 with no output when the calling skill is not configured, reducing noise.
- **`rn-loops` parent↔sub-loop orchestration contract hardening** — Enforced the interface contract between `rn-implement` and its sub-loops (`rn-decompose`, `rn-remediate`), preventing silent contract drift. (ENH-1977)

### Changed

- **Option J guillotine now uses `/ll:resume` in loop contexts** — When `run_with_continuation` (and `WorkerPool._run_with_continuation`) receive a `run_dir`, the Option J fresh session is seeded with `/ll:resume <run_dir>/guillotine-prompt.md` instead of a lossy transcript-summary blob. Fallback to `assemble_guillotine_prompt` is preserved when `run_dir` is `None`. (ENH-1996)
- **`decide-issue --auto` skips resolved questions** — In `--auto` mode, Phase 3b now filters out `decision_needed` questions that already have an `outcome:` recorded in `.ll/decisions.yaml`, preventing re-prompts for decisions already made interactively. (ENH-1986)
- **Sub-loop missing-capture validation downgraded to WARNING** — `ll-loop validate` now emits WARNING (not ERROR) for missing captures inside included sub-loop fragments, reducing noise for optional sub-loop inputs. (ENH-1998)
- **Background Workflow children reaped via process group** — `subprocess_utils` now sends `SIGKILL` to the entire process group of detached Workflow children on shutdown, preventing zombie background processes. (ENH-1999)
- **FSM per-iteration artifact versioning** — Built-in FSM loops now snapshot intermediate artifacts per iteration under `${run_dir}/` instead of overwriting, enabling post-hoc inspection of generate→evaluate cycles.
- **CodexRunner `sandbox_mode` parameter exposed** — `CodexRunner.build_streaming()` and `build_blocking_json()` now accept a `sandbox_mode` parameter, enabling per-call sandbox override.
- **FSM `input_hash` auto-injected into loop context** — The FSM runner auto-injects `input_hash` at startup, providing a stable fingerprint for checkpoint deduplication across resume cycles.

### Fixed

- **BUG-1997: Multi-source capture in reachability check** — FSM static validator now correctly handles variables with multiple `capture:` sources (e.g., from different route branches), no longer flagging them as unreachable.
- **BUG-1995: Test DB isolation via `LL_HISTORY_DB`** — Tests that exercise session-store code now set `LL_HISTORY_DB` to a temp path, preventing accidental writes to `.ll/history.db`.
- **BUG-1985: `rn-remediate` `CONVERGED_STALLED+decision_needed` routing** — The `converged` state now routes `CONVERGED_STALLED` verdicts that also have `decision_needed: true` to `NEEDS_MANUAL_REVIEW` instead of silently terminating.
- **BUG-1882: Session-store migration race condition** — Migration now uses a file-level lock (`fcntl.flock`) around schema-version reads and `PRAGMA user_version` writes, preventing the `no such table` crash when two processes opened the DB concurrently during first-run migration.
- **BUG-1975: `rn-decompose` missing `on_partial`/`on_no` routes** — Added explicit routing from `run_size_review` for partial and no verdicts, preventing silent dead-ends.
- **BUG-1972: `run_dir` not wired into `rn-implement` remediation delegation** — Sub-loop invocations from `rn-implement` now correctly forward `run_dir`, enabling per-run artifact isolation in nested loops.
- **`ll-issues list --group-by epic` parent chain walk** — Epic grouping now walks the full parent chain (via `parent:` frontmatter) rather than only the direct parent, so grandchild issues are correctly bucketed under their EPIC.
- **`context-monitor` 1M-model limit detection** — Corrected detection logic for models with 1M-token context windows; also clamps corrupt baseline reads to sane defaults.
- **`loop-monitor` model display** — Now reads the current model name from `action_complete` events rather than stale session start state.
- **`rn-remediate` `retry_counter` fragment replaced with `exit_code` evaluator** — Eliminated a self-evaluation loop in score-persistence states; satisfies MR-1.
- **`general-task.yaml` migrated to per-run artifact isolation** — Intermediate files now written under `${run_dir}/` instead of shared `.loops/tmp/`, satisfying MR-3.
- **Skills staging** — `/ll:commit` now stages only touched issue files rather than the entire `.issues/` directory, preventing accidental commits of unrelated changes.
- **`subprocess_utils` pipe EOF blocking** — Fixed a hang where the event reader blocked waiting for pipe EOF instead of breaking on the `result` event.

## [1.116.0] - 2026-06-04

### Added

- **`sft-corpus` FSM loop** — Complete end-to-end loop for SLM fine-tuning corpus generation with PII detection, session-quality filtering, enrichment, and quality predicates. (ENH-1941, ENH-1948)
- **`rn-implement` recursive plan-and-implement loop** — New FSM loop that recursively plans, decomposes, implements, and remediates issues using a queue-orchestrator pattern delegating to `rn-decompose` and `rn-remediate` sub-loops. (FEAT-1933, ENH-1936)
- **LCM-style summary DAG over session history** — Session store now builds a hierarchical summary DAG with parent_id linkage, three-level LCM Algorithm 3 escalation, and two-hop traversal for condensed summary nodes in `grep` and `expand`. (FEAT-1712, BUG-1926, BUG-1928)
- **Recursive cross-session condensation** — Schema v12 adds a `level` column and cross-session dedup index; N-level recursive CTE enables project-root summary traversal via `ll-session expand --deep`. (ENH-1927, ENH-1955)
- **Host-aware session log discovery** — `ll-logs discover` and `ll-session backfill` now auto-detect the host CLI (Codex/OpenCode/Pi) and search the correct log directories per host. (ENH-1945)
- **MR-4 loop validator warning** — New validation rule flags LLM-judged FSM states that set `on_yes` but omit `on_no`/`on_partial` routing, preventing silent dead-ends on non-yes verdicts. (ENH-1917)
- **Project-context snapshot at session start** — `ll-session start` now injects a project-level context block (branch, recent commits, active issues) into the session store. (ENH-1907)
- **User corrections mined from message events** — `session_store.py` now extracts user corrections from `message_events` during backfill, with broadened `is_correction()` detection including phrase-internal patterns. (ENH-1887)
- **`required_inputs` FSM guard** — Loops can now declare `required_inputs` keys that must be present before execution begins. (FEAT-1925)
- **`vision_gate` state in `html-website-generator`** — Optional aesthetic scoring pass using vision-model evaluation for generated websites. (ENH-1914)
- **`history.*` config namespace** — New configuration area for history DB settings, wired into `/ll:configure` and `ll-config.json`. (ENH-1905, ENH-1912)
- **Orchestration pattern shapes in `/ll:create-loop`** — Wizard now offers pre-built orchestration templates (pipeline, generator-evaluator, enumerate-prove, specialist-role). (ENH-1912)
- **FSM fragment runtime parameterization** — `with:` bindings on fragment states enable caller-provided parameter injection at inclusion time. (ENH-1915)

### Fixed

- **BUG-1947: Design tokens guard type error** — Changed guard from key-existence (`in`) to truthiness check to handle empty string design token values correctly.
- **BUG-1950: `dequeue_next` pipeline fallback** — Fixed crash when `depth_map.txt` is missing by adding a graceful fallback path.
- **BUG-1951: Template engine `${DEPTH:-0}` syntax** — Escaped default-value syntax that the single-pass interpolation engine couldn't resolve in `rn-implement`.
- **Adversarial-redesign `${DIFF_SIZE}` escaping** — Parallel fix for default-value syntax in the adversarial-redesign loop template.
- **`subprocess_utils` TokenUsage closure** — Fixed capture of init-event model reference in closure for accurate token accounting.
- **Session backfill issue_id derivation** — Derive `issue_id` from filename when frontmatter `id` field is absent during backfill.
- **`generate` state partial/no routing** — Fixed `generator-evaluator` loop where `on_yes`-only routing on the generate state silently dead-ended on partial/no verdicts.
- **`verify-cli` grep bug in `cli-anything-bootstrap`** — Fixed regex pattern and added delegate/convergence guards.

### Changed

- **`rn-implement` rewritten as queue orchestrator** — Refactored from monolithic FSM to a queue-driven orchestrator delegating implementation work to `rn-decompose` and `rn-remediate` sub-loops.
- **Session store schema v12** — Added `level` column and cross-session dedup index for recursive condensation support.
- **`ll-session` N-level DAG traversal** — Recursive CTE enables deep summary traversal beyond single-hop lookups.
- **PII detection in `sft-corpus` filter chain** — Automated PII screening integrated into the corpus generation pipeline.
- **Analytics capture config extensibility** — `correction_patterns` in `ll-config.json` now supports user-defined regex patterns for custom correction detection.
- **Effort/velocity reads in planning skills** — `ll-history-context --effort` now feeds cycle-time data into `/ll:refine-issue`, `/ll:ready-issue`, and `/ll:confidence-check`.
- **`svg-textgrad` loop hardening** — Added `seal_artifacts`, `on_error` routing, and tighter convergence gating.
- **`/ll:configure` history area** — New interactive configuration area for history DB settings with EPIC-1707 backlinks.
- **`go-no-go` and `capture-issue` thresholds parameterized** — Configurable confidence thresholds replace hard-coded values.

## [1.115.0] - 2026-06-03

### Added

- **Rules and Decisions Log** — New `ll-issues decisions` CLI subcommand and `.ll/decisions.yaml` data layer for tracking opt-in compliance rules and decisions. Includes `list`, `add`, `outcome`, `generate` (LLM-assisted), and `sync` subcommands. Skill bridges wire the decisions log into `/ll:go-no-go` and `/ll:ready-issue`. (FEAT-948, FEAT-1892, FEAT-1893)
- **`ll-verify-skills` line-count linter** — New CLI that checks every `SKILL.md` against a configurable line limit (default 500) and exits 1 on any violation. Supports `--limit N` and `--json` output. Run before release to enforce the flat-companion-file convention. (c53f0089)
- **history.db wired into `/ll:go-no-go` and `/ll:capture-issue`** — `go-no-go` now queries `ll-history-context` after Step 3a and applies a −0.2 signal on GO/NO-GO confidence for each matched correction. `capture-issue` performs an FTS5 near-duplicate check via `ll-session` in Phase 2 with graceful degradation when `history.db` is absent. (ENH-1888)
- **`is_correction()` broadened detection** — `session_store.py` adds phrase-internal patterns (`_PHRASE_RE`: "instead", "you missed", "should be", "wrong approach", "remember that", "always/never use", "from now on", "I meant…not") and an explicit `!remember` escape-hatch prefix (`_REMEMBER_RE`). More user corrections are now captured automatically in `history.db` without requiring a correction-style opening prefix. (ENH-1887)
- **`analytics.enabled` wired into `/ll:init` and `/ll:configure`** — `ll:init` wizard gains a mandatory Round 9 (Analytics) that writes `analytics.enabled: true/false` with the full `capture` sub-block; `ll:configure analytics` provides a 3-way Enable/Disable/Keep area and `--show` output for the enabled and capture fields. (ENH-1884)
- **`learning_tests_required` gate in `/ll:ready-issue` and `/ll:go-no-go`** — Issues with `learning_tests_required:` frontmatter are now checked against the learning-test registry at gate time: proven → PASS, stale → WARN, missing/refuted → NOT_READY / NO-GO blocking. Gate is opt-in; absent or empty field is always PASS. (452affed)
- **Variant C specialist-role pipeline template in `/ll:create-loop`** — New "Harness a skill — Variant C" option decomposes a task into four specialist roles (Plan, Research, Implement, Report) as distinct FSM states. Reference example: `loops/harness-plan-research-implement-report.yaml`. (FEAT-1798)
- **`append_to_messages` FSM state field** — Loops can now build a run-scoped narrative log: each state that sets `append_to_messages: "${captured.X.output}"` appends to a `__messages__` accumulator passed as a prior-context block to all subsequent states. (7adff000)
- **SFTFormatter + `ll-messages --sft-format`** — New `SFTFormatter` module supports `chatml`, `alpaca`, and `sharegpt` conversation formats. `ll-messages` gains `--sft-format <format>` (mutually exclusive with `--examples-format`) and a shared `--context-window N` (default 3) flag. (EPIC-1880)
- **PII detection utility** — New `pii_detection` module for filtering personally identifiable information from SFT training corpora. (106b2ae2)
- **Learning-test discoverability gate via PreToolUse hook** — Hooks into `PreToolUse` to surface relevant learning tests at dispatch time, improving discoverability for issue workflows. (b10ebc19)

### Fixed

- **BUG-1890: `ll:init` Codex auto-detect guard** — `ll:init` now reads `LL_HOST_CLI` / `LL_HOOK_HOST` before probing for the `codex` binary and skips Codex auto-detection entirely when the active host is `claude-code`. Prevents accidental `.codex/hooks.json` writes when running inside Claude Code. (efbda12f)
- **PostToolUse hook wired into Claude Code** — The `post_tool_use` hook handler was not registered in the Claude Code hook config; it is now wired, enabling `tool_events` / `file_events` population and the auto-commit gate. (ad20d757)
- **Session store: sessions populated before tool/message backfill** — `SQLiteTransport` now inserts session rows before the background JSONL backfill runs, eliminating FK-constraint violations on `tool_events` / `message_events` that referenced session IDs not yet present. (5c858662)
- **autodev: stale inflight issue re-queued after context handoff resume** — When `ll-auto` resumes after a `CONTEXT_HANDOFF` signal, in-flight issues that were interrupted mid-processing are now correctly re-queued rather than dropped. (1693649e)
- **Loop preset tuning** — Lowered `min_action_rows` threshold for clean/slim presets in the pinned pane. (50f938e7)

### Changed

- **500-line `SKILL.md` limit enforced via companion files** — Skill directories now extract reference and template content into flat companion files (`*.md` peers to `SKILL.md`). `ll-verify-skills` mechanically enforces the limit; `ll-adapt-skills-for-codex` was updated to skip companion files during Codex bridging. (8bf9b23b)
- **`ready-to-implement-gate` loop uses `type: learning` states** — The built-in gate loop now uses the FSM `type: learning` mechanism for assumption validation instead of ad-hoc shell checks, picking up the standard retry / `on_blocked` routing. (8db260ba)
- **`ll-messages` mtime pre-filter** — `extract_conversation_turns()` now applies a file-level mtime pre-filter, skipping log files not modified since the requested start time, significantly improving performance on large log directories. (65b731a8)

## [1.114.0] - 2026-06-02

### Added

- **`migrate-sdk-version` loop** — FSM loop for bulk re-proving stale learning-test records after a dependency bump. Iterates the stale queue, re-runs `/ll:explore-api` for each target, classifies each result as `still-valid`, `needs-upgrade`, or `refuted`, and produces a triage report. Counterpart to `learning-tests-audit`: run after it marks records stale. (FEAT-1813)

- **`parse_tagged_json` fragment** — New `lib/common.yaml` fragment that injects `action_type: shell` into states that extract a tagged JSON line from LLM output. Eliminates duplicated `action_type` declarations across 3 integration loops. No default `action:` is provided (the FSM interpolation engine is single-pass; nested `${captured.${context.var}.output}` raises `InterpolationError`); callers supply `action:` referencing the captured variable by its literal name. (ENH-1861)
- **3 integration loops converted to `parse_tagged_json`** — `adopt-third-party-api.yaml`, `integrate-sdk.yaml`, and `assumption-firewall.yaml` now declare `fragment: parse_tagged_json` on their parse states and `import: ["lib/common.yaml"]`. Existing `action:`, `capture:`, `evaluate:`, and routing fields are unchanged. (ENH-1861)
- **`ll-harness` CLI** — New one-shot runner evaluation CLI that invokes a skill (`skill`), shell command (`cmd`), MCP tool (`mcp`), or raw Claude prompt (`prompt`), captures output, and evaluates against optional exit-code and semantic criteria. Exits `0` (PASS), `1` (FAIL), or `2` (error/timeout). Registered as `ll-harness` in `pyproject.toml`. (FEAT-1689)
- **`ll-history-context` CLI** — New CLI tool that renders a `## Historical Context` block for an issue from `.ll/history.db`, surfacing recent user corrections and FTS5 matches (capped at 5 rows, stale-filtered at 30 days). Graceful degradation: empty output when DB is absent or no matches. (ENH-1846)
- **Historical context in `refine-issue`** — New Step 2.5 queries `ll-history-context` and injects a `## Historical Context` block into the gap-filling prompt context when prior corrections exist. (ENH-1847)
- **Historical context in `ready-issue`** — Step 2 validation now queries `ll-history-context` and surfaces matched corrections as `Historical Concerns` sub-bullets with `warning` severity. (ENH-1847)
- **Historical context in `confidence-check`** — Phase 1 context-gathering queries `ll-history-context`; each matched correction applies a −0.1 signal to the Outcome Confidence Score. (ENH-1847)
- **`cli_events` table + `cli_event_context()`** — `history.db` schema v8 adds a `cli_events` table recording every `ll-` CLI invocation (binary, args, exit code, duration). `cli_event_context()` is a context manager that inserts the row on entry and updates `exit_code` + `duration_ms` on exit via `finally`. Enables `ll-session recent --kind cli` and `ll-session search --kind cli`. (ENH-1848)
- **`cli_event_context` wired into all CLI entry points** — All 27 `ll-` CLI files (29 entry points registered in `pyproject.toml`) are now wrapped with `cli_event_context`, so every command invocation is recorded in `history.db`. (ENH-1849)
- **`refine-issue --gap-analysis` / `--full-rewrite` flags** — `--gap-analysis` is an additive-only mode that inventories existing sections, detects stale anchors and missing files, and applies only additions — never removes content; exempt from `max_refine_count`. `--full-rewrite` is an explicit opt-in for legacy full-rewrite behavior. Existing automation (`refine-to-ready-issue`, `autodev`) retains `--full-rewrite` so behavior is unchanged. (ENH-1782)
- **`auto_commit` config layer for issues** — New `issues.auto_commit` (bool, default `false`) and `issues.auto_commit_prefix` (string, default `"chore(issues)"`) fields in `ll-config.json`. When enabled, a PostToolUse hook automatically stages and commits issue file writes/edits; skips gracefully when the working tree has other staged or unstaged changes. (ENH-1843, ENH-1844)
- **`ll-doctor` + `/ll:configure` expose `auto_commit` flag** — `ll-doctor` prints an Issues section showing `auto_commit` enabled/disabled status; `/ll:configure` issues display and hooks table updated to reflect both new config fields. (ENH-1845)
- **`analytics.capture` config sub-object** — New `analytics.capture` block in `ll-config.json` with per-category gates: `skills` (list of skill names or `["*"]`), `cli_commands` (list or `["*"]`), `corrections` (bool), `file_events` (bool). All default to permissive (capture everything). `feature_enabled_for()` glob-matching helper added. (ENH-1840, ENH-1841)
- **`skill_events` table — track `/ll:` skill invocations** — `history.db` schema v7 adds a `skill_events` table. The `user_prompt_submit` hook detects `/ll:<name>` patterns and records a skill event at dispatch time. Enables `ll-session recent --kind skill` and FTS search with `kind='skill'`. (ENH-1833)
- **`generator-evaluator` oracle sub-loop** — New `loops/oracles/generator-evaluator.yaml` drives a generate → evaluate → revise cycle for any skill; converts 5 existing harness loops to thin wrappers. Includes `playwright_screenshot` fragment. (ENH-1775)
- **`enumerate-and-prove` oracle** — New oracle that enumerates candidates and proves each satisfies a predicate; converts 2 integration loops. (ENH-1776)
- **`convergence_gate` + `ll_rubric_score` fragments** — Shared fragments for convergence exit predicates and numeric rubric scoring; converts 5 convergence callers. (ENH-1776)
- **`implement-issue-chain` oracle** — Reusable chained-implementation sub-loop extracted from `auto` and `sprint-refine-and-implement` for standardized chained issue execution.
- **`research-coverage` oracle** — Coverage-driven research sub-loop extracted from `deep-research` loops as a reusable primitive.
- **`diff_stall_gate` fragment** — Extracted evaluator config fragment for diff stall detection; shared across callers.
- **`queue_pop` + `queue_track` fragments** — `lib/common.yaml` fragments for queue-based issue processing; `dequeue_next` and `skip` states in auto/sprint loops converted to use these. (ENH-1875)
- **`/ll:scope-epic` skill** — Decomposes a theme or product area into a structured EPIC with scaffolded child issues.
- **`/ll:review-epic` skill** — Audits EPIC health: assesses completeness, dependency ordering, and implementation risk.
- **`ll-workflows propose` subcommand** — Step 3 of the workflow analysis pipeline; proposes automation loop designs from patterns identified in prior steps.
- **`ll-issues epic-progress` subcommand** — Aggregates per-type completion statistics across an EPIC's child issues with progress percentage.
- **`ll-deps tree --epic` subcommand** — Renders the EPIC child hierarchy as an ASCII dependency tree with edge labels. (ENH-1858)
- **`check_contract` FSM evaluator** — Detects boundary-mismatch violations where an action output crosses a defined scope contract. (FEAT-1791)
- **`--cascade` flag for `ll-issues set-status`** — Propagates EPIC closure to all incomplete child issues when setting an EPIC to `done`.
- **Per-state token/cost telemetry in `ll-loop run`** — Each state transition records token usage and estimated cost; summarized in the run report.
- **Session-end sweep hook for stale cross-issue refs** — Post-session hook sweeps `relates_to:` / `parent:` fields for references to closed or cancelled issues.

### Fixed

- **Log path resolution via `cwd` field** — `ll-logs` now uses the `cwd` field from JSONL records to correctly resolve project-relative paths. (aed16b18)
- **FSM stall detector false positives on bookkeeping writes** — `exclude_paths` added to the diff-stall evaluator config so issue-file housekeeping writes no longer mask real stalls. (BUG-1767)
- **Session log stores filename not absolute path** — Session ID records now store the JSONL filename instead of an absolute path, enabling cross-machine portability. (9e06b8cf)

### Changed

- **EPIC critical-path awareness in `review-sprint`** — Sprint review now surfaces EPIC-blocking issues and warns when critical-path items are absent from the sprint. (EPIC-1859)
- **Built-in design token profiles in `/ll:configure`** — Configure scaffolds the selected token profile into `.ll/design-tokens.yaml` on first selection.

## [1.113.0] - 2026-05-31

### Added

- **`proof-first-task` loop** — Opt-in wrapper that gates any implementation loop on an assumption-firewall check before code changes begin. (FEAT-1738)
- **`learning-tests-audit` loop** — FSM loop for stale record detection and triage reporting in the Learning-Test Registry. (FEAT-1739)
- **Learning-tests opt-in feature flag** — `/ll:init` and `config-schema.json` now wire learning-tests as an opt-in feature flag. (FEAT-1743)
- **`ll-loop monitor` subcommand** — Live state polling and log tail for running loops. (FEAT-1764)
- **Parallel-safe autodev for disjoint issues** — `autodev` now declares `scope: ["${context.run_dir}"]`, enabling concurrent instances with different issue sets to refine in parallel. (FEAT-1789)
- **`ll-loop run --baseline` blind A/B comparison** — Runs paired harness/baseline arms in parallel, feeds both outputs into an anonymized LLM judge, and aggregates results into `ab.json` with pass-rate deltas and token/duration ratios. (FEAT-1790, FEAT-1822)
- **`assumption-firewall` `--assume` flag** — Records untestable claims directly via CLI without interactive prompts. (ENH-1740)
- **`history_reader` module** — Typed read-only query API for `history.db`. (ENH-1752)
- **Multi-profile design-tokens system** — Active profile selector with profile-scoped token sets. (ENH-1768)
- **W3C DTCG `$value` token format** — Design-tokens resolver now supports the W3C DTCG `$value` field alongside the legacy `value` field. (ENH-1769)
- **`ll-loop diagnose-evaluators` subcommand** — Detects non-discriminating evaluator states from run history by computing per-state Bernoulli variance; flags states below threshold with pattern-matched recommendations. (ENH-1792)
- **`audit-issue-conflicts --cross-theme` flag** — Phase 2b fingerprint sweep catches conflicts between issues in different thematic groups; uses `ll-issues fingerprint` to identify file-overlap pairs across batch boundaries without an LLM call, then dispatches targeted single-pair agents only for matched pairs. (ENH-1801)
- **`ll-issues fingerprint` / `ll-issues fp` subcommand** — Extracts a structured fingerprint (id, `files_to_modify`, `key_terms`) from an issue file as JSON; no LLM call. Used by `audit-issue-conflicts --cross-theme` Phase 2b. (ENH-1801)
- **`action_stall` FSM evaluator** — Detects repeated-action loops by hashing configurable context keys (`track`) across consecutive iterations; routes `no` after `max_repeat` identical-hash rounds. File-backed; no git repository required. Exit-code-aware (exempt from the non-zero short-circuit). (ENH-1827)
- **`comparator` FSM evaluator** — Blind A/B comparison of the current run output against a stored baseline via LLM judge; supports majority-vote across `min_pairs` pairs. Baselines live under `.loops/baselines/<loop>/output.txt`; auto-promoted on first success when `auto_promote: true`. (FEAT-1790)
- **`ll-loop promote-baseline` subcommand** — Manually promotes the latest run's action output as the new comparator baseline; reads `action_output` events from `.loops/.history/` and writes to `.loops/baselines/<loop>/output.txt`. Alternative to `auto_promote: true`.
- **`sessions` table + `ll-session path` subcommand** — `history.db` schema v4 adds a `sessions` table indexed by session ID. `ll-session path <session_id>` resolves and prints the JSONL transcript path for a given session. (ENH-1710)
- **`issue_sessions` VIEW + `ll-history sessions` subcommand** — `history.db` schema v5 adds the `issue_sessions` VIEW joining `issue_events` to `message_events` via overlapping timestamps. `ll-history sessions <ISSUE_ID>` lists sessions that co-occurred with an issue's active period; supports `--limit N` and `--json`. Requires a prior `ll-session backfill` pass. (ENH-1711)

### Fixed

- **ll-auto CONTEXT_HANDOFF signal forwarding** — `ll-auto` now correctly forwards `CONTEXT_HANDOFF` signals to the outer FSM loop. (BUG-1759)
- **Background loop scope conflict silent failure** — Scope lock conflicts in background loops now surface a clear error message instead of failing silently. (BUG-1771)
- **`ll-loop list --json` missing description field** — The `description` field is no longer omitted from JSON output. (BUG-1779)
- **Nested loop name crashes in background runs** — Nested loop names no longer cause background run crashes. (BUG-1788)
- **`audit-issue-conflicts` scans terminal issues** — The command no longer includes `done`/`deferred` issues alongside active ones. (BUG-1799)
- **`audit-issue-conflicts` unstaged files** — `git add .issues/` no longer stages unrelated untracked files. (BUG-1800)
- **`audit-issue-conflicts` duplicate Scope Boundary / Scope Addition sections** — Phase 4b now checks for existing audit-authored sections before appending; repeated runs on an unchanged backlog no longer accumulate duplicate sections. (ENH-1802)
- **`hitl-md` generate state missing `on_error` routing** — Missing `on_error` in the generate state no longer causes fatal loop termination. (BUG-1803)
- **`hitl-md` density filter hiding segments** — The density filter in `hitl-md` no longer incorrectly suppresses segments that pass the rubric; additional rubric gaps (blank-line handling, trailing whitespace) also addressed.

### Changed

- **`general-task` retry hardening** — Applies existing `max_retries` field uniformly across `general-task.yaml` loop states. (ENH-1677)
- **FSM scope context template variables** — FSM `scope` field now supports `${context.*}` template variables for per-file locking. (ENH-1787)
- **`--no-lock` flag for `ll-loop run`** — Bypasses scope lock conflict detection when explicitly requested. (ENH-1778)
- **`hitl-md` prompt extracted to shared fragment** — 16 KB generate prompt moved to a shared file fragment for reuse. (ENH-1804)
- **LLM model shown in `ll-loop run` and `ll-loop monitor` headers** — Active model name now visible in run headers. (ENH-1805)

## [1.112.0] - 2026-05-28

### Added

- **`integrate-sdk` FSM loop** — New built-in loop for proof-driven SDK integration with exploration and verification states. (FEAT-1692)
- **EPIC IDs as sprint arguments** — `SprintManager.load_or_resolve()` accepts EPIC issue IDs, expanding them into their child issues for sprint execution. (FEAT-1737)
- **`design-tokens` config schema and dataclass infrastructure** — `DesignTokensConfig` dataclass with six fields (`enabled`, `path`, `primitives_file`, `semantic_file`, `themes_dir`, `active_theme`), JSON Schema wiring, and deep-merge support in `BRConfig`. (FEAT-1747)
- **`design-tokens` default WCAG AA palette template set** — Four scaffold files (`primitives.json`, `semantic.json`, `themes/light.json`, `themes/dark.json`) with accessible default values generated by `/ll:init` and `/ll:configure design-tokens`. (FEAT-1748)
- **`design-tokens` FSM context pre-injection** — `ll-loop run` and `ll-loop resume` resolve and inject the active design-token set into the FSM initial context before the first state is entered. (FEAT-1749)
- **`design-tokens` init/configure UX and docs** — `/ll:init` prompts for design-tokens opt-in; `/ll:configure design-tokens` provides an interactive setup wizard; `CONFIGURATION.md`, `API.md`, `ARCHITECTURE.md`, `README.md`, and `CHANGELOG.md` fully document the feature. (FEAT-1756, FEAT-1757, FEAT-1758)
- **JSON output for `ll-session recent`** — `--json` flag added to the session recent command for programmatic consumption.

### Fixed

- **Playwright screenshot URL** — `html-website-generator` now uses absolute `file://` URLs for Playwright screenshots, fixing rendering on some platforms.
- **EPIC grouping edge cases** — `ll-issues list --group-by epic` no longer includes EPICs in child buckets, and only groups by actual EPIC parents.

### Changed

- **Always-on foreground log capture** — Foreground loop runs now tee stdout/stderr (ANSI-stripped) to `.loops/.running/<instance-id>.log` via `_TeeWriter`, matching background run behavior. (ENH-1703, ENH-1704)
- **Crash-recovery checkpoint in `general-task`** — Plan step index is persisted before execution, enabling resume from the correct step after a crash. (ENH-1735)

## [1.111.0] - 2026-05-27

### Added

- **`ready-to-implement-gate` sub-loop primitive** — FSM sub-loop for gating issue implementation against readiness criteria before execution begins. (FEAT-1695)
- **`assumption-firewall` loop** — Gates issues against the Learning-Test Registry, surfacing untested assumptions before implementation. (FEAT-1696)
- **`adopt-third-party-api` FSM loop** — Automates the process of exploring and adopting third-party API integrations. (FEAT-1697)
- **`link-epics` skill** — Links issues to their parent epics with frontmatter wiring and catalog registration. (ENH-1729, ENH-1730)

### Fixed

- **Dead-PID reconciliation in `list_running_loops`** — Loops that exited without cleanup are now marked `done` when `ll-loop list` is called, preventing stale entries from accumulating. (BUG-1731)

### Changed

- **`run_dir` injection for built-in loops** — Each loop run now gets a dedicated artifact directory under `.loops/runs/<loop>/<run-id>/`; built-in loops migrated to use `run_dir` for all per-run output. (ENH-1726)
- **`--show-diagrams slim` preset** — New `slim` preset renders FSM diagrams in a compact single-column layout for narrow terminals. (ENH-1702)
- **Always-on foreground log capture via `_TeeWriter`** — Foreground runs now always tee stdout and stderr (ANSI-stripped) to `.loops/.running/<instance-id>.log`, matching background run behavior. `log_file` in `ll-loop status --json` is now a path for all run modes; `null` only for `--foreground-internal` children or pre-ENH-1703 state files. (ENH-1703)
- **`ll-issues list --group-by epic`** — Issues can now be grouped by their parent epic in list output. (EPIC-1727)
- **`general-task` execute split into 4 sub-states** — Execution phase decomposed into granular states for better observability and recovery. (ENH-1732)
- **Deepest active loop shown in pinned pane** — Pinned status pane now shows only the innermost running loop rather than the outermost.
- **`ll-issues set-status` subcommand** — New CLI subcommand for directly setting an issue's status field.
- **FSM diagram rendered in dry-run mode** — Passing `--show-diagrams` to `ll-loop run --dry-run` now renders the diagram without executing.

## [1.110.0] - 2026-05-26

### Added

- **`AutoManager` wires `EventBus`/`SQLiteTransport` directly** — `ll-auto` now records issue lifecycle events (`issue.completed`, `issue.deferred`, `issue.skipped`, `issue.started`, `issue.closed`, `issue.failure_captured`) live into `.ll/history.db` without requiring `events.transports: ["sqlite"]` in config. New `db_path` constructor parameter overrides the default path. (ENH-1733)
- **Documentation updates for EventBus wiring** — `AutoManager.__init__` signature, new `issue.skipped`/`issue.started` event types, CLI wiring table `ll-auto` row, backfill framing, and `config-schema.json` sqlite description updated to reflect ENH-1691/1733 implementation. (ENH-1734)
- **`ll-loop audit-meta` subcommand** — Detects evaluator-trivial failure mode in meta-loops; includes updated loop-specialist agent and docs. (ENH-1700)
- **`ll-action list --json` exposes `args` hint** — Per-skill input schema now surfaced for agent callers. (ENH-1660)
- **Meta-eval telemetry write and archive** — Meta-loop evaluation results written to a persistent telemetry store and archived per run. (ENH-1699)
- **`--show-diagrams` options wired into `ll-loop show`** — Topology, preset, and modifier flags available in the `show` subcommand.
- **Learning Tests Guide** — New documentation for the learning test registry added to docs.

### Fixed

- **Missing `default_timeout` in FSM loop YAMLs** — Added default and per-state timeouts to unprotected loops to prevent indefinite hangs. (BUG-1724)
- **hitl-md loop tests reflect finalize state** — Corrected test drift caused by FSM shape change.

### Changed

- **hitl-md inline highlights + popover affordances** — Diff highlights rendered inline with popover UI; final HTML copied to cwd on completion.
- Prompt inputs truncated to single-line preview in default `ll-loop` output for cleaner display.

## [1.109.0] - 2026-05-24

### Added

- **`SQLiteTransport` handles `issue.*` events (ENH-1690)** — `SQLiteTransport.send()` now records `issue.*` lifecycle events into `issue_events` alongside loop events, with `_derive_transition()` mapping event types to canonical status strings (`issue.completed` → `"done"`, etc.). `_backfill_issues()` switched to `INSERT OR IGNORE` backed by a new `idx_issue_events_dedup` unique index on `(issue_id, transition)`, preventing duplicates from repeated backfill calls. Schema bumped to v3. Prerequisite for ENH-1691 live-write wiring.

## [1.108.0] - 2026-05-24

### Changed

- **`--show-diagrams` restructured into topology/preset/modifier axes (ENH-1672)** — The old `main|full|mini` string values are replaced by a composable flag set. Preset aliases (`summary`, `detailed`, `clean`) and named topologies (`layered`, `neighborhood`, `inline`) act as the primary flag; three new modifier flags apply orthogonal overrides: `--diagram-edge-labels` (show/hide edge labels), `--diagram-state-detail` (show/hide state body), `--diagram-scope` (filter visible states). Bare `--show-diagrams` defaults to the `summary` preset. **Breaking change**: scripts passing `--show-diagrams=main`, `--show-diagrams=full`, or `--show-diagrams=mini` must migrate to `summary`, `detailed`, and `clean` respectively.

## [1.107.0] - 2026-05-24

### Added

- **Final verify-and-close gate in `general-task` loop** — Added `final_verify` (prompt) and `count_final` (shell) states between `count_done` and `done`. On every successful completion `final_verify` re-verifies **every** DoD criterion from evidence (not just the per-iteration 3-item sample), appending a `## Final Verification` section. `count_final` counts failures in the most-recent section and routes to `done` on zero or back to `continue_work` if any criterion fails. Structurally prevents false-positive completion: reaching `done` now always implies full end-to-end re-verification in the same iteration. (ENH-1681)

## [1.106.0] - 2026-05-23

### Added

- **`--show-diagrams=mini` skeleton mode** — `ll-loop run --show-diagrams=mini` and `ll-loop resume --show-diagrams=mini` render each FSM state box as title-only (no body lines / verdict listings) with unlabeled connector edges. Inherits `main`'s happy-path edge filter; active-state highlighting still applies; falls back to `full` if the active state is off the main path. Useful as a "map view" for large loops where `main` is still too dense. (ENH-1652)
- **Unified Session Store (SQLite + FTS5)** — New `ll-session` CLI and `.ll/session.db` provide a queryable, full-text-indexed store of Claude Code session events; supports `search --fts`, `recent --kind`, and `backfill` subcommands. (FEAT-1112)
- **Context Window Analytics (`ll-ctx-stats`)** — New CLI command and PostToolUse hook capture per-tool byte vs. context savings from the session DB, giving visibility into context consumption across tools. (FEAT-1160, FEAT-1623, FEAT-1624, FEAT-1625, EPIC-1626)
- **`ll-history` and `analyze-workflows` query session DB** — Both commands now read from the unified session store instead of re-parsing raw log files. (ENH-1621)
- **`ll-session` wired across docs, help, and config** — Reference docs, init permissions, and CLAUDE.md now surface the new session store. (ENH-1619)

### Fixed

- **Nested loops discoverable in `ll-loop list` and doc verifier** — Recursive discovery now finds runnable loops under `loops/oracles/` and other subdirectories. (BUG-1633, BUG-1634)
- **FSM failure-terminal diagnostic convention** — Tooling, docs, `create-loop` wizard, and validation now enforce a `diagnose` state before failure terminals to surface root causes. (BUG-1607)
- **`SKILL.md` block-scalar description parsing** — `doc_counts` and two CLI parsers now resolve YAML block-scalar descriptions via `yaml.safe_load` instead of regex. (11afb38, a963048)

### Changed

- **Session store renamed `.ll/session.db` → `.ll/history.db`** — The per-project SQLite + FTS5 store accumulates events across every session, not just the current one; the new name reflects that. `ensure_db()` performs a one-time transparent rename of the legacy file (and any `-shm`/`-wal` sidecars) on first call after upgrade, so existing projects keep their history. Config key `events.sqlite.path`, the `ll-session` CLI, and the `session_store` module name are unchanged. (ENH-1635)
- **README agent description** — Rephrased to be drift-proof rather than naming a fixed agent count. (ENH-1441)
- **Status one-shot cleanup** — Normalized non-canonical `status:` values (e.g. `completed` → `done`) across all issue files via `ll-migrate-status`. (ENH-1551)
- **`ll-loop --show-diagrams` accepts `main|full` mode** — `ll-loop run --show-diagrams` and `ll-loop resume --show-diagrams` now take an optional `main|full` argument. Bare `--show-diagrams` defaults to the new `main` mode, which hides off-happy-path edges (`error`, `partial`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`, `throttle_hard`) and the states only reachable through them, leaving the happy-path skeleton. Pass `--show-diagrams=full` for the legacy all-edges view. If the active state is hidden in `main`, the renderer falls back to `full` for that iteration and prepends `(showing full diagram: active state '<name>' is off the main path)`. Soft breaking change: scripts depending on the previous all-edges output must pass `--show-diagrams=full`. (ENH-1641)

### Other

- Multiple issue refinements, plan documents (ctx-stats epic, ll-loop list readability, Hermes Agent PRD), and `ruff format` passes across `doc_counts`, ctx-stats files, and tests.

## [1.105.0] - 2026-05-21

### Added

- **`rn-refine` apply commands in report** — The `rn-refine` loop now prints apply commands during the report state for easier execution. (0670eda)

### Fixed

- **`rn-refine` plan writeback** — Refined plans are now written back to the original file instead of requiring manual copy. (9fe683a)
- **`hitl-compare` image embedding** — Images in generated HTML are now embedded as base64 data URIs for portability. (75f660a)
- **Lint: ambiguous variable** — Renamed ambiguous variable `l` to `line` in `test_ll_loop_commands`. (0bce6b7)

### Changed

- **`ll-loop list` output** — Enhanced list output with column alignment, truncation, and label badges for improved readability. (ENH-1614)

## [1.104.0] - 2026-05-18

### Added

- **`hitl-md` FSM Loop** — New built-in harness for interactive single-document review. Decomposes a markdown file into GP-TSM saliency-modulated segments (LLM-in-prompt, no external ML dependencies) and generates a self-contained HTML page with per-segment color coding, keyboard/mouse navigation, five per-segment edit affordances (delete / insert-before / insert-after / inline-edit / flag-for-AI), a "Copy AI prompt" control for flagged segments, and a "Copy updated markdown" reconstruction control. Run via `ll-loop run hitl-md path/to/doc.md`. (FEAT-1613)
- **`rn-refine` FSM Loop** — New built-in loop for iterative refinement of existing plan documents using an 8-dimension scoring rubric. Run via `ll-loop run rn-refine`.
- **`mcp-call --timeout` Flag** — Configurable request timeout for MCP tool invocations.
- **`missing_artifacts` Gate in `recursive-refine`** — New gate state detects missing output artifacts and routes to `repair` before proceeding.

### Fixed

- **Pre-terminal Diagnose States in 12 FSM Loops** — Added `diagnose` states before failure terminals in `refine-to-ready-issue`, `rl-coding-agent`, `agent-eval-improve`, `general-task`, `recursive-refine`, `prompt-across-issues`, `rl-policy`, `html-anything`, `svg-textgrad`, `svg-image-generator`, `rn-plan`, and `rn-refine`. Eliminates silent failures and surfaces root-cause before exit. (BUG-1606)
- **`rn-refine` task field** — `task:` field in `plan-rubric.md` now updated correctly after `synthesize` rewrites the plan.
- **`rn-refine` report state** — Added `report` state so final summary executes before terminal.
- **Doc-count skills regex** — Narrowed regex to avoid false-positive on 'skill descriptions'.
- **`html-anything` evaluate routing** — Routes `on_no`/`on_error` to `score` instead of `generate`.
- **FSM bash default-value syntax** — Escaped `${VAR:-default}` syntax in `rn-refine`, `rn-plan`, and `deep-research` init actions.
- **FSM diagram arrowhead direction** — Corrected arrowhead direction for same-layer right-to-left back-edges.
- **`verify_work_was_done` mid-phase commits** — Now recognizes commits made during mid-phase work.
- **Issue parser title preference** — Prefers frontmatter `title:` field over filename stem in list output.
- **`TYPE-NNN` show lookup** — Resolved show command for legacy filenames without P-prefix.

### Changed

- **Interrupted loops resumable** — FSM loops interrupted mid-run can now be resumed from their last stable state. (ENH-1605)
- **`hitl-compare` write-in affordance** — Added subtle write-in custom option per review item.
- **`rn-refine` score verification** — Added `verify_score` shell state to confirm rubric file content.
- **`rn-plan` rubric dimensions** — Replaced `granularity`/`outcome_confidence` with `feasibility`, `testability`, `risk_mitigation`.
- **FSM authoring conventions** — New documentation section for authoring conventions and corrected failure-routing guidance.

## [1.103.0] - 2026-05-17

### Added

- **`deep-research` FSM Loop** — New built-in iterative web research synthesis loop that accepts a research topic or question, generates an initial set of faceted search queries, iteratively performs web searches via WebSearch/WebFetch tools, evaluates and deduplicates sources, scores per-facet coverage on a 1–5 scale, and iterates until coverage is sufficient or `max_iterations` is exhausted. Uses the inline sentinel convergence pattern (`COVERAGE_SUFFICIENT`) modeled on `rn-plan`. Produces a structured `report.md` with executive summary, key findings, deduplicated source table, coverage gaps, and conclusion. All artifacts written to `.loops/research/<slug>/`. Run via `ll-loop run deep-research "your research topic"`. (FEAT-1540)
- **`rn-plan-apo` FSM Loop** — New built-in APO (Automatic Prompt Optimization) loop for iterative plan-quality gradient optimization.
- **Loop-Specialist Agent** — New `loop-specialist` agent with diagnosis taxonomy, doc wiring, and an evaluation harness for monitoring, analyzing, refining, and optimizing FSM-based automation loops. (FEAT-1532, FEAT-1544)
- **`ll-loop next-loop` Sub-command** — History-based loop suggestion sub-command that recommends the most relevant built-in loop given recent session context. (FEAT-1546)
- **FSM `TargetStateSpec` / `TargetFileSpec` Schema** — New schema types and validation for per-FSM-state and per-file targeting in `harness-optimize`. (ENH-1552)

### Fixed

- **`html-anything` Silent Infinite Cycle on Playwright Failure** — `evaluate` state now routes `on_no`/`on_error` to `score` instead of `generate`, preventing a silent 20-iteration cycle when Playwright is absent. `score` action gains a screenshot-or-HTML fallback preamble for LLM-only graceful degradation. Corrects stale LOOPS_GUIDE FSM diagram and prose. (BUG-1602)
- **Renderer Inter-Layer Label Collision** — Prevents label collisions when two edges share a source row across adjacent layers. (BUG-1501)
- **Renderer Back-Edge Label Collision** — Prevents label collisions when back-edges share a midpoint row.
- **Renderer Forward-Edge Label Truncation** — Truncates merged forward-edge labels that exceed the available column width.
- **Outer-Loop-Eval Terminal States** — Adds distinct `fail_sub_loop` and `fail_error` terminal states plus `fail_missing_input` for clearer error reporting.
- **Confidence-Check Signal Detection** — Extends Phase 4.6 signal phrase list for more reliable decision detection.

### Changed

- **harness-optimize State-Mode** — State machine extension with `init_run` state, per-run trajectory paths, state-mode wiring, and docs. (ENH-1554, ENH-1555)
- **Meta-APO Per-FSM-State Targeting** — `harness-optimize` now accepts `TargetStateSpec` to focus optimization on individual loop states. (ENH-1535)
- **Status Synonym Normalization** — Frontmatter `status:` synonyms (e.g. `completed` → `done`, `wip` → `in_progress`) are normalized on parse; `ll-migrate-status` migrates on-disk files; regression tests and docs added. (ENH-1539)
- **`svg-textgrad`** — Fixed gradient quoting, universal score recording, and optional external pass evaluator. (ENH-1548)
- **`review-loop`** — Adopts all seven harness-design best practices. (ENH-1547)
- **`ll-verify-docs`** — FSM loop tracking and bridge-skill filter added. (ENH-1038)
- **Loops ruamel.yaml Round-Trip Editor** — New round-trip YAML state editor for in-place FSM edits that preserve formatting and comments. (ENH-1553)

## [1.102.0] - 2026-05-16

### Added

- **`hitl-compare` FSM Loop** — New built-in human-in-the-loop comparison harness that reads whitespace-separated inputs (file paths or raw text), extracts candidate review items with 2+ options each, prunes implementation-level micro-decisions via an LLM `prune` state, and generates a single self-contained interactive HTML page with per-item toggle/select controls and an "Export selections" affordance that yields a copy-pasteable markdown block for feeding chosen decisions back to the coding agent. Evaluates the rendered page against a 5-criterion rubric (clarity, scannability, comparison_ergonomics, export_affordance, inline_constraint) via Playwright screenshot with graceful degradation to LLM-only scoring when Playwright is unavailable. Run via `ll-loop run hitl-compare "<space-separated inputs>"`. (FEAT-1545)

- **`html-anything` FSM Loop** — New built-in generalized HTML artifact harness that classifies artifact type (email, social card, résumé, invoice, dashboard, component, poster, presentation, or website) from a natural language description, atomically writes a platform-specific `brief.md` and dynamic `rubric.md` with 4–6 per-artifact-type criteria, then iteratively generates and refines a self-contained `index.html` via Playwright CLI. Per-criterion thresholds (not a weighted average) enforce platform constraints — e.g. `inline_styles` with threshold 8 for email, `dimensional_accuracy` with threshold 8 for social cards. `evaluate` gracefully degrades to LLM-only scoring when Playwright is unavailable. Run via `ll-loop run html-anything "<description>"`. (FEAT-1541)
- **`rn-plan` FSM Loop** — New built-in recursive planning loop (`rn-plan`) that accepts a natural language task description, generates a structured plan and 8-dimension scoring rubric (breadth, depth, complexity, granularity, clarity, consistency, logic_strategy, outcome_confidence), then iteratively researches and refines the plan until all dimensions reach VERY-HIGH or `max_iterations` is exhausted. Run via `ll-loop run rn-plan "task description"`. (FEAT-1534)
- **Host Runner Abstraction Framework** — All host CLI invocations now route through `resolve_host()` in `host_runner.py`; `HostInvocation` carries binary + args without embedding host literals. Supports `CodexRunner`, `OpenCodeRunner`, and `PiRunner` stubs with streaming, blocking-JSON, detached, and version-check build modes. Set `LL_HOST_CLI` or `orchestration.host_cli` in config to override. (FEAT-1465, FEAT-1467, FEAT-1469, FEAT-1470, FEAT-1471, FEAT-1472, FEAT-1473)
- **Codex/OpenCode Hook Wiring** — `post_tool_use` fires fire-and-forget for Codex and OpenCode adapters; `pre_tool_use` benchmarked for latency characterization. (FEAT-1489)
- **`ll-adapt-agents-for-codex` CLI** — Generates `.codex/agents/*.toml` from `agents/*.md` so Codex CLI can discover and invoke ll agents via `--agent <name>`; includes full documentation and integration tests. (FEAT-1527, FEAT-1528)

### Fixed

- **`completed` Status Missing from Terminal Filter** — `find_issues` and `skip.py` now recognize `completed` as a terminal status, preventing stale issues from being re-queued for processing. (BUG-1485)

## [1.101.0] - 2026-05-15

### Added

- **Hook-Intent Abstraction Layer** — Defines little-loops hooks in terms of host-agnostic *intents* (`PreCompact`, `SessionStart`) backed by `LLHookEvent`/`LLHookResult` dataclasses. Python handlers in `little_loops.hooks.*` replace per-host shell scripts; adapters under `hooks/adapters/<host>/` translate each host's native event into the wire format and back. (FEAT-1116)
- **PreCompact and SessionStart Python Handlers** — Ported `precompact-state.sh` and the session-start injector to pure-Python core handlers, with a Claude Code bash shim adapter and an OpenCode TypeScript adapter (`hooks/adapters/opencode/index.ts`). (FEAT-1449, FEAT-1450, FEAT-1455)
- **`LLHookIntentExtension` Protocol** — Third-party packages can contribute hook intent handlers via a `provided_hook_intents()` method; detected via `hasattr()` in `wire_extensions()` and merged into the global hook-intent registry. (FEAT-1452)
- **OpenCode Adapter for Hook Intents** — OpenCode TypeScript plugin calls `python -m little_loops.hooks <intent>` via `Bun.spawn`, setting `LL_HOOK_HOST=opencode` so dispatched handlers can identify their caller. (FEAT-1451)
- **"Write a Hook" Authoring Guide** — New `docs/claude-code/write-a-hook.md` covers the intent model, handler signature, `LLHookIntentExtension` registration, adapter flow, and pure-function + subprocess testing patterns. (FEAT-1458)
- **`type: learning` FSM State** — Learning states prove external-API/SDK assumptions against the learning-tests registry before advancing. Iterates `targets` in order; missing or stale records trigger `/ll:explore-api`; refuted records or exhausted retries route to `on_blocked`. Exempt from `hard_max` enforcement. (FEAT-1283)
- **`/ll:verify-issue-loop` Skill** — Generates a ready-to-run FSM verification loop YAML from a single issue's acceptance criteria. Each criterion becomes a dedicated `verify` state that fails fast if unmet. (FEAT-1310, FEAT-1446)
- **`/ll:explore-api` Skill** — Explores an external API or SDK target and writes a `LearnTestRecord` to the learning-tests registry (`.ll/learning-tests/<slug>.md`). Used by `type: learning` FSM states. (FEAT-1287)
- **`ll-learning-tests` CLI** — Query and manage learning-test registry records: `check`, `list`, `mark-stale`. Entry point at `scripts/little_loops/cli/learning_tests.py`. (FEAT-1286)
- **Per-Edge Cycle Detection** — `max_edge_revisits` (default 100) terminates a loop immediately with `terminated_by="cycle_detected"` when any state→state edge fires more than the limit, preventing tight two-state oscillations from draining the entire `max_iterations` budget. Edge counts survive `--resume`. (dd2603625)
- **Goals Discovery Fallback for `scan-product`** — When `.ll/ll-goals.md` is absent, `scan-product` synthesizes a temporary goals context from existing docs (README, roadmaps, vision files) instead of hard-stopping. (ENH-1442)
- **Hook-Intent Reference Documentation** — Updated `docs/reference/API.md`, `EVENT-SCHEMA.md`, `CONFIGURATION.md`, and `ARCHITECTURE.md` with full field tables and dispatch contract for hook intents. (FEAT-1453, FEAT-1459)

### Changed

- **Progressive Throttling for FSM Loop Tool Calls** — FSM loops now apply exponential back-off when tool-call rates exceed configurable thresholds, preventing runaway tool use in tight loops. (ENH-1115)
- **`autodev` Routes Dead-End Decisions Before Size-Review** — When a `decide` state fails, `autodev` now routes through triage before size-review, preventing incorrect decomposition of well-scoped issues whose bottleneck is an unresolved decision. (ENH-1415)
- **New-Skill Classification Policy** — Added a skill classification decision tree to `CONTRIBUTING.md` and `ll-generate-skill-descriptions` CLI for managing the skill listing budget. (ENH-1395, ENH-1396)
- **Product Analyzer Improvements** — Fixed output schema inconsistencies, removed double-deduplication between `product-analyzer` and `scan-product`, and wired product setup into `/ll:init`. (ENH-1401, ENH-1402, ENH-1403)

## [1.100.0] - 2026-05-10

### Added

- **EPIC Type — Core Registration and Parsing** — Registers EPIC as a first-class issue type with core infrastructure, parsing, and schema support. (FEAT-1405)
- **EPIC Type — Skills, Commands, and Documentation Updates** — Extends all skills, commands, and documentation surfaces to recognize and handle EPIC type issues. (EPIC-1407)
- **EPIC Type — CLI Display, Argparse Choices, and Tests** — Adds EPIC to all CLI display paths, argparse choices, and test coverage. (EPIC-1410)
- **EPIC Type — Regex-Based Callers, Anchor Sweep, and Tests** — Extends regex-based callers and anchor sweep to include EPIC type patterns. (FEAT-1411)
- **Startup Reconciliation Sweep for Stale `.running/` Files** — FSM startup now detects and cleans up stale `.running/` state files left from interrupted sessions. (ENH-1399)

### Fixed

- **`decide-issue --auto` Asks Interactive Questions** — Adds Phase 3b inline provisional scan for `--auto` mode so provisional decisions are resolved non-interactively. (BUG-1416)
- **`ll-loop` Go/No-Go Gate Broken** — Restored go/no-go gate by using the `invoke` subcommand in the `ll-action` call for loop states. (91a9166)
- **`implement_issue` Hangs on Already-Completed Issues** — Added completion guard to prevent the FSM from hanging when `implement_issue` is invoked on an issue already marked done. (1f16f7c)
- **`ll-issues list` Treats `status: completed` as Open** — Status `completed` is now treated as `done` in list output, matching the canonical status vocabulary. (d55db5c)

### Changed

- **Issue Status Decoupled from Directory Location** — `IssueInfo.status` field now drives all status checks across `ll-issues`, `ll-sync`, sprint runner, parallel orchestrator, and `issue_manager`; directory-based status methods are deprecated. (ENH-1417, ENH-1423, ENH-1424, ENH-1426, ENH-1427)
- **Confidence-Check Criterion A Split into Breadth × Depth** — Criterion A (Complexity) is replaced by two sub-scores — Breadth (number of call sites) and Depth (layer-crossing) — for more precise assessment. (ENH-1413)
- **Confidence-Check Criterion D Credits Mechanical Fanouts** — The Change Surface rubric now credits enumerated mechanical fanouts such as CLI flags and serialization fields. (ENH-1412)
- **Relationship Migration Script** — Added `ll-migrate-relationships` to rename deprecated `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files. (ENH-1434)
- **Issue Model: `milestone:` and `labels:` Frontmatter Fields** — Added `milestone:` (with `--milestone` filter) and `labels:` (with `--label` filter) to `IssueInfo` and CLI. (a052e18, 85653bf)
- **Dependency Graph Enhancements** — Added `depends_on_edges` field and soft-ordering of `depends_on` targets in `get_execution_waves()`. (0cc0fad, 22d2dce)
- **Relationship Field Standardization** — Standardized `blocked_by`, `duplicate_of`, `relates_to`, and `parent` relationship fields across skills, docs, and GitHub sync. (16a3ae6, 694ea9f, e7d4d5d)
- **`disable-model-invocation` Added to 16 Operational Skills** — Prevents accidental model calls from operational skills that should only perform file/tool operations. (2bc2e2f)

## [1.99.0] - 2026-05-09

### Added

- **go/no-go Gate for refine-and-implement Loops** — Added a `go_no_go` state between `implement_next` and `implement_issue` in both `auto-refine-and-implement` and `sprint-refine-and-implement` loops to filter low-value issues before costly implementation. (ENH-1387)
- **Issue Model Alignment Capture** — Captures issue model alignment issues for platform compatibility when scanning issues. (50c290b)

### Fixed

- **Skill descriptions exceed Claude Code context budget, causing 38 silent drops** — Trimmed all 28 `skills/*/SKILL.md` description fields to single-line inline values (≤100 chars), reducing token footprint by 57% to fit within the default 1% context budget. (BUG-1379)
- **`recursive-refine` `dequeue_next` bash expansion crashes interpolator, causing infinite sprint loops** — Fixed by using `$${}` escape syntax to pass bash parameter expansions through interpolation unchanged. (BUG-1380)
- **subprocess output parser silently discards result events** — Extended the `result` event branch in `run_claude_command()` to extract and report errors via stderr. (BUG-1381)
- **Worker pool error messages use only stderr, ignoring stdout** — Added stdout fallback in error message construction for both failure sites in `_process_issue()`. (BUG-1382)
- **Orchestrator state file overwrites failure details with generic "Failed" string** — Accumulated per-issue worker error strings replace the generic overwrite with actual error messages. (BUG-1383)
- **FSM interpolation engine rejects bash default-value syntax in escaped variables** — Added regression tests and documentation for bash-operator support inside `$${...}` escapes. (BUG-1384)
- **`--resume` fails in print mode during Option E context-handoff continuation** — Changed to `--continue` in `subprocess_utils.run_claude_command()` for correct print-mode session continuations without requiring an explicit session ID. (BUG-1385)
- **Phantom failure after Option J guillotine fresh session** — Added `_just_ran_fresh_session` guard to skip Option E after fresh session completes, and classified "requires a valid session id" as TRANSIENT failure. (BUG-1386)
- **UnixSocketTransport skips initial state seed on client connect** — New `on_connect` callback seeds new clients with current running loop state from `.loops/.running/*.state.json`. (BUG-1388)

## [1.98.0] - 2026-05-07

### Added

- **Progressive Tool-Call Throttling** — Loop states can now declare a `throttle:` block to detect and halt runaway action loops within a single state visit. Three configurable thresholds: `normal_max` (default 3) is the expected call count, `warn_max` (default 8) emits a `throttle_warn` event, and `hard_max` (default 12) transitions to `on_throttle_hard` (or falls back to `on_error`). Mark a state `state_type: learning` to exempt it from `hard_max` enforcement for states that legitimately make many tool calls per visit (e.g. batch operations). (ENH-1115)
- **`decision_needed` Gate in `recursive-refine`** — A new `check_decision_needed` state between `check_depth` and `run_size_review` skips size-review for issues with `decision_needed: true`, preventing premature decomposition before competing implementation options are resolved. Skipped issues are written to `recursive-refine-skipped-decision.txt` and the shared `recursive-refine-skipped.txt`; the done summary includes a `Decision (%d)` row and the decomposition tree labels them as `(skipped: decision-needed)`. (ENH-1371)
- **`--skip-issue-creation` and `--auto` Flags for Loop Analysis Skills** — `/ll:debug-loop-run` and `/ll:audit-loop-run` now accept `--skip-issue-creation` (suppress issue filing) and `--auto` (non-interactive headless mode), enabling invocation from loop states without blocking on interactive prompts. (ENH-1373)

### Changed

- **Renamed `analyze-loop` → `debug-loop-run` and `assess-loop` → `audit-loop-run`** — Clearer names: `debug-loop-run` emphasizes per-run debugging, `audit-loop-run` emphasizes effectiveness auditing. All references across skills, tests, docs, and FSM loops updated atomically. (ENH-1378)
- **`outer-loop-eval` Delegates to `/ll:debug-loop-run` and `/ll:audit-loop-run`** — Refactored inline analysis states to invoke the corresponding skills, eliminating code duplication and ensuring future skill improvements automatically benefit the outer loop. (ENH-1328)

### Fixed

- **`ll-auto` Context Handoff Reliability** — PostToolUse `exit 2` feedback was silently dropped in `-p` mode, so `context-monitor.sh` warnings never reached Claude and sessions ran until "Prompt is too long". Fixed via Options E+G+J: writing the continuation prompt before the tool call completes (E), reading accumulated stream output immediately before spawning the continuation session (G), and broadening handoff signal detection patterns (J). (BUG-1377)
- **Accurate Context Token Counts from `result` Stream Events** — `run_claude_command` now parses `input_tokens`/`output_tokens` from stream-json `result` events and writes `result_token_count` to `.ll/ll-context-state.json`. The context monitor uses this authoritative count (tier 1 in the three-tier priority) instead of heuristic weight estimates, which significantly undercounted large sessions and prevented the handoff threshold from firing. (ENH-1376)
- **"Prompt is too long" Classified as TRANSIENT Failure** — `classify_failure` in `issue_lifecycle.py` now matches the `"prompt is too long"` API error string and returns `FailureType.TRANSIENT`. This prevents `ll-auto` from filing a spurious P1 BUG issue and halting when a subprocess exhausts the context window; instead it attempts a continuation round. (BUG-1375)
- **Autodev Re-runs `confidence-check` After `decide-issue`** — Added `rerun_confidence_after_decide` state that invokes `/ll:confidence-check` to refresh frontmatter scores after `/ll:decide-issue` resolves an ambiguity. Previously `recheck_after_decide` read stale pre-decision scores, so issues whose low outcome confidence was caused by an unresolved design question could never pass the gate even after the decision was made. (BUG-1378)

## [1.97.0] - 2026-05-05

### Added

- **WebhookTransport** — POSTs batched FSM events to a configurable HTTP endpoint, enabling remote dashboards, Slack bots, and CI systems to subscribe to ll loop activity without polling the filesystem. Events are queued non-blocking and flushed on a configurable interval (default 1000 ms); failed POSTs retry with exponential backoff (3 retries, 0.5 s–8 s). Activate with `events.transports: ["webhook"]` and configure via `events.webhook.url`, `events.webhook.batch_ms`, and `events.webhook.headers`. Requires `pip install 'little-loops[webhooks]'`; the base package import is unaffected when the optional extra is absent. (FEAT-1314)
- **`commands:` Key for Loop YAML** — Loop authors can now add a top-level `commands:` list to their loop YAML to override the Commands section displayed by `ll-loop show`. Each entry is a `{cmd, comment}` pair providing copy-paste-ready examples with the correct `--param` or `--context` flags for that specific loop, replacing the generic five-command default. (ENH-1367)
- **Optional `sprint_name` Input for `sprint-build-and-validate`** — Pass a sprint name as a positional argument (`ll-loop run sprint-build-and-validate my-sprint`) to reuse an existing sprint definition at `.sprints/<name>.yaml` and skip the sprint-creation phase. When omitted, the loop creates a new sprint from the backlog as before. (ENH-1372)

### Changed

- **`sprint-build-and-validate` Refinement Pipeline** — Replaced the inline size-review/verify pipeline with the `recursive-refine` sub-loop, giving sprint issues the same depth-first decomposition, cycle detection, and budget-cap guarantees used by `auto-refine-and-implement`. Issues that fail refinement or are decomposed into children are written to a skip file and excluded from subsequent sprint execution.

## [1.96.0] - 2026-05-04

### Added

- **OTelTransport** — Maps ll loop executions to OpenTelemetry traces and spans (loop = trace root, state = child span, action = grandchild span), exporting via OTLP to Grafana, Jaeger, Datadog, and other OTel-compatible backends. Activate with `events.transports: ["otel"]` and configure via `events.otel.endpoint` / `events.otel.service_name`. Requires `pip install 'little-loops[otel]'`; the base package import is unaffected when the optional extras are absent. (FEAT-1312)
- **`flow:` Linear Shorthand for Loop YAML** — Declare a linear state chain with `flow: [state1, state2, ...]` instead of writing a verbose `states:` map. The last entry is implicitly terminal; non-terminal entries transition unconditionally forward. Supports `name?yes:no` ternary syntax for single-branch gates. Optional `state_defs:` deep-merges bodies into generated states. `flow:` and `states:` are mutually exclusive; a child loop's `flow:` overrides a parent's `states:`.
- **`--issues` Filter for `/ll:align-issues`** — Pass a comma-separated list of issue IDs (`ENH-123,BUG-456`) to scope alignment checks to specific issues instead of scanning all active issues. (ENH-1362)
- **`--issues` Filter for `/ll:tradeoff-review-issues`** — Same comma-separated `--issues` argument available on the tradeoff-review command; when omitted, all active issues are reviewed. (ENH-1363)

### Fixed

- **Queued loops missing `instance_id` on retry-acquire** — `ll-loop run --queue` now correctly passes `instance_id` to the retry-acquire call inside the queue wait loop, preventing a scope mismatch that caused queued loops to fail at startup after winning the queue. (BUG-1360)
- **Orphaned queue entries from dead processes block live waiters** — `_is_earliest_waiter` now skips and removes stale queue entries whose PID is no longer alive, so crashes or kills no longer block subsequent `--queue` runs indefinitely. (BUG-1361)
- **`refine-to-ready-issue`: score-persistence miss triggers spurious size-review** — The loop now retries the confidence-check action once when `verify_scores_persisted` detects that scores were not written, rather than immediately routing to `breakdown_issue`. (BUG-1365)
- **`refine-to-ready-issue`: low outcome score routes to `breakdown_issue` despite `decision_needed`** — Added a `check_decision_needed` gate between `check_outcome` and `breakdown_issue`. When `decision_needed: true`, the loop exits via `done` (so the autodev pipeline's `decide` step can resolve the ambiguity) instead of incorrectly triggering a size-review decomposition. (BUG-1366)

## [1.95.0] - 2026-05-04

### Added

- **Multi-Instance Loop Support** — Loops can now run as multiple named instances with isolated file paths (`instance_id` scoping) and aggregated CLI operations (`status`/`stop`/`resume`/`list`) across all instances. (ENH-1354, ENH-1356, ENH-1357)
- **`recursive-refine` Depth Limiting** — Per-subtree `max_depth` parameter with YAML FSM `check_depth` gate and config schema support prevents unbounded recursion. (ENH-1346, ENH-1347)
- **`recursive-refine` Cycle Detection** — Visited-set guard prevents revisiting already-processed issues during recursive refinement. (ENH-1338)
- **`recursive-refine` Budget Cap** — Per-issue refinement budget cap enforces work limits during recursive processing. (ENH-1339)
- **`recursive-refine` Parent Aggregation** — Children's outcomes are aggregated back to their parent issue on completion. (ENH-1340)
- **`recursive-refine` Decomposition Tree Rendering** — Done summary now renders the full decomposition tree. (ENH-1341)
- **`recursive-refine` Real-Time Progress** — Dequeue progress lines emitted to stderr in real time; queue peek lines emitted after enqueue operations. (ENH-1348, ENH-1349)
- **`recursive-refine` Skipped Reason Categories** — "Skipped" output bucket now splits into meaningful per-reason categories. (ENH-1350)
- **`recursive-refine` `max_depth` Documentation** — `max_depth` parameter and `check_depth` gate documented in the loop reference. (ENH-1345)

### Fixed

- **`ll-loop stop` ignores live PID on interrupted loops** — `stop` now acts on `interrupted` loops when a valid lock-file PID is present. (BUG-1353)
- **`ll-loop status` reports null PID** — Status command now reads PID from the `.lock` file instead of returning `null`. (BUG-1352)
- **outer-loop-eval scope conflict blocks sub-loop execution** — Scope conflict resolved by switching to native sub-loop execution. (BUG-1359)
- **outer-loop-eval dead state causes validation error on startup** — Removed dead benchmark fragment; added missing `load_definition` state and error handling. (BUG-1358)
- **`ll-loop run --background` drops positional input argument** — Background subprocess now correctly forwards the positional input argument. (BUG-1308)
- Normalize timezone-aware datetimes to naive UTC when parsing `captured_at` (b2271de4)
- **`check-duplicate-issue-id` hook TOCTOU race allows parallel duplicate IDs** — New `check-duplicate-issue-id-post.sh` PostToolUse Write hook reactively deletes any issue file whose integer ID already exists on disk, closing the race window between the PreToolUse "allow" response and the file landing on disk. (BUG-1364)

[Unreleased]: https://github.com/BrennonTWilliams/little-loops/compare/v1.124.0...HEAD
[1.124.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.123.0...v1.124.0
[1.123.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.122.0...v1.123.0
[1.122.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.121.0...v1.122.0
[1.121.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.120.0...v1.121.0
[1.120.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.119.0...v1.120.0
[1.119.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.118.0...v1.119.0
[1.118.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.117.0...v1.118.0
[1.117.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.116.0...v1.117.0
[1.116.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.115.0...v1.116.0
[1.115.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.114.0...v1.115.0
[1.114.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.113.0...v1.114.0
[1.113.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.112.0...v1.113.0
[1.112.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.111.0...v1.112.0
[1.111.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.110.0...v1.111.0
[1.110.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.109.0...v1.110.0
[1.109.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.108.0...v1.109.0
[1.108.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.107.0...v1.108.0
[1.107.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.106.0...v1.107.0
[1.106.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.105.0...v1.106.0
[1.105.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.104.0...v1.105.0
[1.104.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.103.0...v1.104.0
[1.103.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.102.0...v1.103.0
[1.102.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.101.0...v1.102.0
[1.101.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.100.0...v1.101.0
[1.100.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.99.0...v1.100.0
[1.99.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.98.0...v1.99.0
[1.98.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.97.0...v1.98.0
[1.97.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.96.0...v1.97.0
[1.96.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.95.0...v1.96.0
[1.95.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.94.0...v1.95.0

## [1.94.0] - 2026-05-03

### Added

- **`/ll:audit-loop-run` Skill for Loop Effectiveness Auditing** — New skill that judges whether a loop execution achieves its stated goals using a goal-vs-outcome scorecard and rubric audit, with sub-loop scope awareness. (FEAT-1325, FEAT-1329, FEAT-1330)

### Changed

- **Five deterministic effectiveness signals in `/ll:debug-loop-run`** — Adds signals 1–5: Stub Action, Iter-1 Convergence, Degenerate Gate, Capture Vacuum, and Numeric Trajectory Stall. Outputs are grouped into Fault and Effectiveness sections with fixtures and synthesis tests. (ENH-1326, ENH-1327, ENH-1335, ENH-1336, ENH-1342, ENH-1343)
- **Sub-loop visibility in `/ll:debug-loop-run` and `/ll:audit-loop-run`** — Both skills now call `ll-loop show --resolved --json` so child loop state maps appear under `_subloop` keys in the FSM output. `/ll:debug-loop-run` Step 3 emits a new `BUG — Sub-loop verdict discarded` (P3) signal when a state with `loop:` routes child success and child failure to the same destination (`on_yes == on_no`). (ENH-1334)
- **`ll-loop show --resolved` CLI flag and sub-loop expansion** — New `--resolved` flag expands sub-loop references inline with full state resolution and JSON output support, including tests. (ENH-1333)
- **FIFO ordering enforced for `--queue` waiters** — Queue waiters now execute in deterministic first-in, first-out order; default wait timeout set to 24 hours (86400s). (ENH-1332)
- **Orphan scan extended to ll-loop worktrees** — `ll-parallel` orphan detection now covers worktrees created by `ll-loop`, preventing stale worktrees from accumulating. (ENH-1255)
- **`description:` field enforced in loop YAML** — FSM warns at startup when a loop YAML file lacks a top-level `description:` field; built-in loop definitions migrated from comment-based descriptions. (ENH-1331)

[1.94.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.93.0...v1.94.0

## [1.93.0] - 2026-05-02

### Added

- **SessionStart Context Injector** - Implement a SessionStart hook that reads `ll-continue-prompt.md` and injects it into Claude's context via `additionalContext` JSON, enabling hands-off session resume without manual `/ll:resume`. (FEAT-1263)
- **Typed Parameter Contract for Sub-Loop Calls** - Add `parameters:` block to loop YAML and per-call `with:` block for sub-loop states, replacing `context_passthrough` with explicit validated named bindings. Includes 33 new tests and schema updates. (FEAT-1311)
- **Loop YAML Template Inheritance via `from:` Field** - Add `from: <loop-name>` field enabling child loops to inherit a parent's state graph and override only deltas, with cycle detection and deep merge semantics. (FEAT-1308)
- **Transport Protocol Foundation and JsonlTransport** - Introduce pluggable `Transport` protocol with `EventBus` abstraction and initial `JsonlTransport` backend for file-based event streaming. (FEAT-918)
- **Transport Foundation — Core Module and EventBus Refactor** - Core `transport` module with `EventBus` refactored to use pluggable transport backends. (FEAT-1322)
- **UnixSocketTransport for Real-Time Local Streaming** - Unix domain socket transport enabling real-time local event streaming without polling. (FEAT-1313)
- **Transport CLI Wiring Pass and Documentation** - Wire all transport backends at CLI entry points; add transport documentation. (FEAT-1323)

### Fixed

- **`/ll:confidence-check` Phase 4 LLM Edit unreliably persists scores** - Replace non-deterministic LLM edit with deterministic `ll-issues set-scores` CLI call; add `verify_scores_persisted` loop state with retry. (BUG-1307)

### Changed

- **`issue-size-review` TDD-aware wiring-split heuristic** - Add TDD project detection to prevent spurious split recommendations when test files outnumber implementation files. (ENH-1320)
- **`parent_issue` frontmatter field for child issues** - Define `parent_issue` field in child issue templates generated by `issue-size-review` for traceability back to the parent. (ENH-1324)

[1.93.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.92.1...v1.93.0

## [1.92.1] - 2026-04-29

### Fixed

- **`issue-parser` collapses issue ID to priority digit when type token is omitted** — Preserve the issue number when the type token is missing from the filename. (BUG-1306)

### Changed

- Refactor autodev FSM loop to run `/ll:decide-issue` after `/ll:confidence-check` when `decision_needed` is true (c5fee57c)

## [1.92.0] - 2026-04-27

### Added

- **Anchor resolver module and `ll-issues anchor-sweep`** — New subcommand that builds an anchor map from source files, sweeps all issue docs for stale `file:line` references, and rewrites them to anchor-based equivalents with regression lint integration. (ENH-1300)
- feat(loops): add description fields to built-in loop definitions (e5e54b04)

### Changed

- **Convert issue-authoring pipelines from `file:line` to anchor-based references** — Updated `refine-issue`, `wire-issue`, and related pipeline commands to use anchor-based references throughout. (ENH-1298)
- **Fix `file:line` references in issue-authoring pipeline source files** — Migrated all stale `file:line` refs in issue-authoring pipeline source files to anchors. (ENH-1299)
- **Fix `file:line` references in agent source files** — Replaced stale `file:line` references in agent definitions with anchor-based equivalents. (ENH-1302)
- **Fix `file:line` references in skill source files** — Replaced stale `file:line` references in skill source files with anchor-based equivalents. (ENH-1303)
- **Fix `file:line` references in `commands/refine-issue.md` and add verification test** — Replaced stale refs and added a verification test. (ENH-1304)
- **Improve `issue-size-review` with scope completeness and ordering checks** — Added scope gap guard and ordering analysis to the skill. (ENH-1301)
- **Harden `wire-issue` Phase 4 subagent prompts against infinite loops** — Added safeguards to prevent runaway subagent execution during Phase 4 wiring. (ENH-1305)
- **Enforce `slash_command` action_type for skill invocations in loops** — Loop YAML now uses `slash_command` action type consistently for all skill invocations. (ENH-1295)
- docs(.claude): update skill count and document ll-action CLI tool (7ac4149e)
- docs(ll-issues): document check-flag, check-readiness, and loop description field (98ed0148)

### Fixed

- **`ll-issues clusters` drops skip-level edges and ignores one-sided `blocks:` declarations** — Fixed dependency graph rendering to correctly render skip-level edges and honour one-sided `blocks:` declarations. (BUG-1297)
- **`autodev run_decide` bypasses score gate when reached from score-failing paths** — Added `recheck_after_decide` state to guard implementation behind the score gate. (BUG-1296)

## [1.91.0] - 2026-04-26

### Added

- feat(diagram): render FSM off-path non-linear topologies via DAG layout (30da8f18)
- feat(diagram): render FSM off-path linear chains vertically (10a3c178)
- feat(diagram): switch FSM box diagram to vertical layout (86cc6ec4)

### Fixed

- **autodev triage_outcome_failure uses score_ambiguity proxy instead of decision_needed flag** — Fixed silent data loss where issues with `decision_needed: true` but high `score_ambiguity` were dropped from the pipeline. The `triage_outcome_failure` state now checks the `decision_needed` flag as the authoritative signal. (BUG-1294)
- fix(workflow-analyzer): compute entities_matched before all_entities mutation (269c297b)

## [1.90.0] - 2026-04-26

### Added

- **`LearnTestRecord` Registry Module** — New `little_loops.learning_tests` module implementing the learning test registry. Provides `LearnTestRecord` and `Assertion` dataclasses and five public functions: `write_record`, `read_record`, `list_records`, `mark_stale`, and `check_learning_test`. Records are stored as YAML-frontmatter Markdown files under `.ll/learning-tests/<slug>.md` with `proven`/`refuted`/`stale` status and a list of typed assertions. (FEAT-1285)
- **Learning Test Registry Foundation** — Decomposed the learning-test infrastructure initiative into FEAT-1285 (registry module), FEAT-1286, and FEAT-1287; established module interface and `ll:explore-api` skill architecture. (FEAT-1282)
- **`autodev` Outcome Failure Triage Before Size-Review** — When confidence thresholds are not met, `autodev` now enters a `triage_outcome_failure` state that reads `score_ambiguity` before routing. Issues with `score_ambiguity ≤ 10` route directly to `/ll:decide-issue` (low ambiguity indicates an unresolved decision is the cause); issues with higher ambiguity fall through to `detect_children` and size-review as before. This prevents incorrect decomposition of well-scoped issues whose low outcome confidence stems from an unresolved competing option. (ENH-1288)
- **`autodev` Missing-Artifact Routing Branch in `triage_outcome_failure`** — `triage_outcome_failure` now has a third routing leg: after ruling out an unresolved decision (`score_ambiguity > 10`), the loop enters a new `check_missing_artifacts` gate that reads the `missing_artifacts` frontmatter flag. If `true` (set by `/ll:confidence-check` Phase 4.7 when Outcome Risk Factors contain artifact-absence signal phrases), the loop routes to `run_wire` (`/ll:wire-issue --auto`) before re-queuing instead of falling through to size-review. Issues with genuine scope bigness still reach `detect_children` unchanged. Adds `run_wire`, `run_refine`, and `check_missing_artifacts` states to the autodev FSM; adds `missing_artifacts: bool | None` field to `IssueInfo` and `ll-issues show --json` output; adds Phase 4.7 to the `confidence-check` skill. (ENH-1291)
- **`.ll/program.md` Steering Convention for Long-Horizon Loop Runs** — Added `--program-md` flag to `ll-loop run` with a heading-based parser for `Directive`, `Targets`, `Benchmark`, and `Budget` sections. CLI args take precedence over `program.md` over loop defaults; `harness-optimize` loop now consumes the file's fields directly. (ENH-1121)
- **`ll-issues` Atomic Writes via `file_utils.py`** — Created `scripts/little_loops/file_utils.py` with `atomic_write()` helper using `tempfile` + `os.rename()`. Replaced all `Path.write_text()` calls in `session_log.py` and `issue_lifecycle.py` to prevent partial writes. (ENH-1280)

### Fixed

- **Queued Loops Race on Lock Release** — Fixed race condition where queued loops exited with code 1 instead of retrying after losing lock acquisition. Replaced single `acquire()` call with a budget-bounded retry loop in `scripts/little_loops/cli/loop/run.py`. (BUG-1281)
- **`confidence-check` Phases 4.5/4.6 Respect Configurable `outcome_threshold`** — Phases 4.5 (Outcome Risk Factors) and 4.6 (decision signal detection) previously used a hardcoded threshold. They now read `config.commands.confidence_gate.outcome_threshold` (default: 75), so project-level overrides in `ll-config.json` take effect. (BUG-1289)

### Changed

- **`issue-size-review --auto` Qualitative Skip Guard** — Phase 5 Auto Mode now skips decomposition for Large/Very Large issues when `score_ambiguity ≥ 18` and `score_complexity ≥ 18`, preventing spurious breakdown of issues whose bottleneck is qualitative rather than scope size. (ENH-1290)
- **Executor-Level API Resilience** — Extended `classify_failure` to recognize server-error patterns; added `_handle_api_error` with flat backoff retry (≤2 attempts, ~30 s each). Sub-loop execution now forwards remaining budget to clamp child FSM timeout to parent's remaining time, preventing silent budget overrun. (ENH-1293)
- **TROUBLESHOOTING Docs for Worktree SIGKILL** — Verified and finalized two sections in `docs/development/TROUBLESHOOTING.md` covering worktree SIGKILL recovery; removed `<!-- TODO: update-docs stub -->` markers. (ENH-1261)
- **README Documents `ll-generate-schemas`** — Updated CLI tools count from 16 → 17 and added `### ll-generate-schemas` section with description and usage example. (ENH-1292)

## [1.89.0] - 2026-04-24

### Added

- **`harness-optimize` Loop** — New built-in score-gated hill-climbing loop that iteratively improves a configured set of target files (agent definitions, skills, commands, or `CLAUDE.md`) against a benchmark. Each iteration proposes an edit, runs a benchmark via the `run_benchmark` fragment (`lib/benchmark.yaml`), accepts the change if the score rises and reverts otherwise, and commits accepted mutations to a branch. Trajectory is logged to `.loops/tmp/harness-optimize-trajectory.jsonl`. (FEAT-1120)
- **Benchmark Fragment in `outer-loop-eval` and `agent-eval-improve`** — The `run_benchmark` fragment (`lib/benchmark.yaml`) is now wired into `outer-loop-eval.yaml` and `agent-eval-improve.yaml` as optional opt-in states, enabling score-based evaluation steps in loop analysis and agent improvement workflows. (FEAT-1245)

### Fixed

- **`issue_parser` Splits Comma-Separated `blocked_by`/`blocks` Strings** — When `blocked_by` or `blocks` frontmatter fields contain a comma-separated string (e.g., `"ENH-419, ENH-422"`), the parser now splits them into individual IDs. Previously the entire string was treated as a single unknown ID, producing spurious "blocked by unknown issue" warnings in `ll-issues clusters` and `ll-sprint`. (BUG-1276)
- **`autodev` Decide Gate Missing from Confidence-Fail Path** — The `decide_current`/`run_decide` states were only reachable after both confidence thresholds passed. Issues with unresolved decisions that caused low outcome confidence now route to the decide gate before size-review, preventing incorrect decomposition. (BUG-1277)
- **`confidence-check` Now Sets `decision_needed: true`** — When `confidence-check` identifies unresolved design decisions in its Outcome Risk Factors prose, it now writes `decision_needed: true` to the issue frontmatter. Previously the flag was never set, so the `autodev` loop's decision gate never fired for confidence-check-identified decisions. (BUG-1278)

## [1.88.0] - 2026-04-23

### Added

- **`ll-logs` CLI Tool** — New command-line tool for discovering, extracting, and tailing Claude Code session logs. Three subcommands: `discover` (identifies ll-relevant sessions), `extract` (writes sessions to `logs/<project-slug>/<session-id>.jsonl` with `--project`/`--all` scope and optional `--cmd` filter), and `tail` (streams live JSONL entries from an active loop session). After extraction, generates `logs/index.md` with a summary table. (FEAT-1271, FEAT-1270, FEAT-1273, FEAT-1274, FEAT-1003, FEAT-1005, FEAT-1006)
- **Benchmark Fragment & Harbor Scorer Evaluator** — Added `harbor_scorer` as a core evaluator type. New `lib/benchmark.yaml` reusable FSM fragment accepts a benchmark spec and returns a numeric score compatible with Harbor-format public task sets. (FEAT-1244)

### Changed

- **Configurable Loop Queue Wait Timeout** — `queue_wait_timeout_seconds` is now configurable in the `loops` config section, replacing the hardcoded 3600s default. (ENH-1231)

## [1.87.0] - 2026-04-22

### Added

- **`ll-issues clusters` Subcommand** — Visualizes issue dependency clusters as box diagrams. Supports `--include-orphans` (include isolated issues), `--min-connections N` (filter small clusters), and `--json` (machine-readable output). Useful for understanding which issues form tightly coupled implementation groups before sprint planning.
- **`autodev` `decide_current` Gate** — The `autodev` loop now checks `decision_needed: true` after refinement and routes to a new `decide_current` state before implementation. This invokes `/ll:decide-issue` to resolve competing options inline, preventing implementation with an unresolved multi-option solution. (ENH-1243)
- **PID Liveness Check in `cleanup-worktrees`** — The `/ll:cleanup-worktrees` command now probes `.ll-session-<pid>` files before removing each worktree directory, preventing accidental removal of worktrees owned by an active `ll-parallel` run. (ENH-1249)
- **Benchmark Adapter Fragment (`lib/benchmark.yaml`)** — New reusable FSM loop fragment that accepts a benchmark spec (task directory + scorer command) and returns a numeric score. Harbor-format compatible so public `tasks/` sets work out of the box. Hooks into `outer-loop-eval.yaml` and `agent-eval-improve.yaml` as a pluggable scoring step. (FEAT-1119)

### Fixed

- **`ll-auto` Exits 0 on Decision Gate Block** — When `ll-auto --only <ISSUE_ID>` encounters `decision_needed: true`, it now exits non-zero so the `autodev` loop correctly detects the gate block instead of silently recording the issue as processed. (BUG-1256)
- **Issue Parser Ignored Frontmatter `blocked_by`/`blocks` Fields** — The issue parser now reads `blocked_by` and `blocks` from YAML frontmatter as the authoritative source, falling back to `## Blocked By` / `## Blocks` body sections. Conflicts between the two sources emit a warning. This fix corrects dependency graphs in `ll-issues clusters` and `ll-sprint`. (BUG-1257)
- **Frontmatter Parser Dropped Inline YAML Arrays** — `frontmatter.py` now parses inline array syntax (`blocked_by: [ID1, ID2]`) correctly instead of storing the entire bracket string as a scalar. (BUG-1258)
- **`ll-issues clusters` Inflated Cluster via Conflicting `blocked_by` Sources** — When an issue had conflicting `blocked_by` data in frontmatter vs. body sections, both were merged, creating spurious edges. The parser now prefers frontmatter and warns on conflict, eliminating false cluster bridges. (BUG-1259)
- **`worktree-health` Loop Always Reported 0 Orphans** — Fixed broken grep pattern in `worktree-health.yaml` that matched no actual worktree names, and extended orphan scan to cover `ll-loop --worktree` worktrees (which use `<timestamp>-<safe-name>` naming, not `worker-*`). (ENH-1248, ENH-1254)

### Changed

- **`debug-loop-run` Step 3b Semantic Synthesis** — Added semantic synthesis phase to `debug-loop-run` Step 3b; documented Execution Summary output format; added synthesis test coverage. (ENH-1265, ENH-1266)
- **`review-loop` SR-* Semantic Flow Checks** — Added SR-* (Semantic Review) check category to `review-loop` for semantic flow validation beyond structural checks.
- **`ll-loop -q` Shorthand Reassigned to `--queue`** — The `-q` flag now maps to `--queue` (wait for conflicting scoped loops) instead of `--quiet`. Use `--quiet` explicitly to suppress progress output.
- **`/ll:confidence-check` Two-Branch Escalation** — When readiness score stays below 70 after 2+ refinement passes, escalation now branches on `score_ambiguity`: ≤ 10 routes to `/ll:decide-issue` (competing options unresolved); > 10 routes to `/ll:issue-size-review` (issue too large). Previously always routed to size review regardless of cause. (ENH-1250)
- **`/ll:issue-size-review` Independently-Shippable Decomposition Principle** — Phase 4 decomposition guidance now enforces splitting along capability seams, not artifact type lines. The governing test: each child must produce a meaningful PR on its own. Hard constraint added against separating tests/docs from the code they cover. (ENH-1242)
- **Worktree Unlock Hardening** — `worktree_utils.cleanup_worktree()`, `merge_coordinator._cleanup_worktree()`, and `orchestrator._cleanup_orphaned_worktrees()` now run `git worktree unlock` before `git worktree remove --force` to prevent cleanup failures when a SIGKILL stranded a lock file. (ENH-1247, ENH-1251, ENH-1252, ENH-1253)
- **Ghost Ref Startup Scan** — `ll-parallel` orchestrator startup scan now iterates `.git/worktrees/` and prunes ghost metadata entries whose on-disk worktree path no longer exists, preventing "already exists" failures on the next `git worktree add`. (ENH-1246)
- **Scratch-Pad Docs and Path Updates** — Documentation and inline references updated to reflect the correct scratch-pad path (`.loops/tmp/scratch/` instead of `/tmp/ll-scratch/`); CLAUDE.md and CONFIGURATION.md updated to describe automatic enforcement via the `scratch_pad` config block. (ENH-1130)

## [1.86.0] - 2026-04-21

### Added

- **`/ll:decide-issue` Skill** — New skill resolves competing implementation options by spawning parallel `codebase-pattern-finder` agents per option, scoring each across Consistency/Simplicity/Testability/Risk dimensions, annotating the winner inline with `> **Selected:**`, and clearing `decision_needed: false` in issue frontmatter. Integrates with `ll-auto`/`ll-parallel` via the `decide_command` config template; triggered automatically when `decision_needed: true`. (FEAT-1238, FEAT-1239, FEAT-1240)
- **ll-action Thin CLI Wrapper** — New `ll-action` CLI entry point wraps the Claude Code skill invocation interface, enabling shell scripts and external tools to trigger any `/ll:*` skill directly (FEAT-1229)
- **Parallel State FSM API Exports and Config Wiring** — FSM parallel-state API exported from `little_loops` package; parallel config wiring hooked into `BRConfig` loader (FEAT-1080)
- **Parallel State Core API Exports and Config Wiring** — Core parallel-state types and orchestrator API surface exported for downstream consumers (FEAT-1227)
- **Parallel State Tests** — Full test coverage for parallel-state FSM logic including unit, integration, and edge cases (FEAT-1077)
- **Parallel Runner Unit Tests** — Comprehensive unit test suite for `ll-parallel` runner covering queue, worker, and lifecycle paths (FEAT-1199)
- **Parallel State Schema, Validation, and Fuzz Tests** — Schema validation and property-based fuzz tests for parallel-state event types (FEAT-1200)
- **Parallel State Executor, Integration, and Display Tests** — End-to-end integration and display-layer tests for parallel state executor (FEAT-1201)
- **Real-Threading Concurrency Tests** — `TestParallelRunnerRealThreading` test class verifies race-condition safety under actual OS threads (FEAT-1203)
- **Parallel Glyph Config** — `ll-loop --parallel` glyph is now configurable via `LoopsGlyphsConfig` in `.ll/ll-config.json`

### Fixed

- **autodev Skips Implementation After Size Review Decline** — `recheck_after_size_review` state added to re-evaluate leaf-sized issues that were already ready, preventing autodev from silently skipping implementation (BUG-1230)
- **autodev Drops Breakdown Result on Timeout** — Pending shell state is now flushed on timeout and in-flight autodev work is tracked, preventing breakdown result loss between `refine_current` and `copy_broke_down` (BUG-1226)

[1.92.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.92.0...v1.92.1
[1.92.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.91.0...v1.92.0
[1.91.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.90.0...v1.91.0
[1.90.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.89.0...v1.90.0
[1.89.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.88.0...v1.89.0
[1.88.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.87.0...v1.88.0
[1.87.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.86.0...v1.87.0
[1.86.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.85.0...v1.86.0

## [1.85.0] - 2026-04-19

### Added

- **Issue Capture and Completion Timestamps** — `captured_at` and `completed_at` ISO 8601 UTC timestamps are now written to issue frontmatter at capture time and at every completion path (sequential lifecycle, parallel orchestrator, and `manage-issue`). New `update_frontmatter` write utility in `frontmatter.py` powers the injection. `ll-issues show` displays both timestamps; `ll-issues search/list` prefer `captured_at` in date resolution; `ll-history` analytics and `CompletedIssue` model carry the new fields. (FEAT-1155, FEAT-1161, FEAT-1162, FEAT-1169, FEAT-1170, FEAT-1171, FEAT-1172, FEAT-1179, FEAT-1180, FEAT-1181)
- **Parallel State Core Reference Documentation** — New reference docs for the parallel state core (FEAT-1083)
- **`labels` Field on `IssueInfo`** — `ll-issues` JSON output now includes a `labels` field sourced from issue frontmatter
- **Queue Entry File While Waiting for Scope Lock** — `ll-loop` writes a queue entry file while waiting for the scope lock so peers can see queued work

### Fixed

- **Score-State PASS Pattern Overmatches Annotations** — Loop evaluator score-state `PASS` token disambiguated to `ALL_PASS` so it no longer matches per-criterion `PASS` annotations (BUG-1182)
- **`autodev` Silently Skipped Parent After Breakdown Signal** — New children are now required to shortcut the `check_broke_down` path, preventing silent skip when no children are actually created (BUG-1183)
- **`ll-loop --verbose` Truncated FSM State Output** — `action_start` and evaluate output are no longer truncated under `--verbose` (BUG-1154)

### Changed

- **FSM Executor `on_error` Routing** — FSM executor now wraps `run_action` in `execute_state` with `on_error` routing (BUG-1168)
- **Agent Model/Tool Tuning and Handoff Threshold** — `.claude/settings.json` agent models, tool allowlists, and context-handoff threshold tuned
- **Ruff Format and `datetime.UTC` Modernization** — Codebase reformatted and `datetime.utc` usages modernized to `datetime.UTC`

### Other

- Issue audits and guide refreshes: `audit-issue-conflicts` findings recorded, 2026-04-18 audit entry added, stale `refine-issue` prompt path corrected, README FSM loop count fixed (42)

[1.85.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.84.0...v1.85.0

## [1.84.0] - 2026-04-17

### Added

- **Multi-Hour 429 Resilience with Shared Circuit Breaker** — Two-tier retry ladder (short-burst + long-wait) with wall-clock budget; `rate_limit_waiting` heartbeat events; cross-worktree circuit breaker to pre-sleep peers; new `StateConfig` fields `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` (ENH-1131, ENH-1132, ENH-1133, ENH-1136, ENH-1137, ENH-1139)
- **Configurable `next-issue` Selection** — `ll-issues next-issue` / `next-issues` sort order is now driven by `issues.next_issue` in `.ll/ll-config.json`; `strategy` accepts named presets `confidence_first` (default, byte-identical to legacy ordering) and `priority_first`; `sort_keys` overrides `strategy` with a custom list of `{key, direction}` entries across priority, confidence, impact/effort, and score dimensions. Unknown values raise `ValueError` at config load (ENH-1123, ENH-1124, ENH-1125, ENH-1126)
- **Scratch-Pad Enforcement via PreToolUse Hook** — New `scratch-pad-redirect.sh` hook automatically redirects large file reads and command outputs to scratch files, keeping automation context lean and preventing context blowout in long-running loops (ENH-1111, ENH-1128, ENH-1129)

### Fixed

- **`ll-loop run --verbose` Truncated LLM Responses** — Multi-paragraph assistant responses now display in full with paragraph breaks preserved, instead of being clipped to a single line (BUG-1118)
- **Rate-Limit Exhaustion in `autodev` `run_size_review`** — `autodev` no longer silently skips size-review work on 429 exhaustion; exhaustion is now handled gracefully

### Changed

- **`autodev` Interleaved Refine-and-Implement** — The `autodev` loop now interleaves refinement and implementation instead of draining the full decomposition tree before running any implementation. Each leaf is implemented via `ll-auto --only` as soon as it passes refinement; decomposed children are prepended to the queue depth-first and refined-and-implemented before the next sibling. Behavior for non-decomposed inputs is unchanged. Known tradeoff: sibling children often share implicit dependencies, so a child implementation failure can silently invalidate the context under which later siblings were refined. (ENH-1127)

## [1.83.0] - 2026-04-16

### Added

- **`autodev` FSM Loop** — New built-in loop definition for automated development workflows (FEAT-1116)

### Fixed

- **FSM 429 Rate Limit Detection and Retry** — FSM executor now detects 429 rate-limit responses, retries in-place with exponential backoff and jitter, and persists retry counts across pause/resume (BUG-1107)
- **Rate Limit StateConfig, Validation, and UI** — Added `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` fields to StateConfig with paired-field validation, storm detection, configurable edge colors, and `with_rate_limit_handling` fragment (BUG-1108)
- **Rate Limit Tests and Documentation** — Comprehensive test coverage for rate-limit fields, events, fragments, and edge rendering; documentation updates across 6 files (BUG-1109)
- **FSM Loops Silently Skip Work on 429 Rate Limits** — Root cause fix: sub-loops hitting 429 errors no longer silently skip all work; decomposed into targeted detection, config, and testing issues (BUG-1105)

### Changed

- **`refine-to-ready` Sub-Loop** — Removed unnecessary `/ll:format-issue` step that added latency; `/ll:refine-issue` already establishes the needed template structure (ENH-1110)

## [1.82.0] - 2026-04-14

### Added

- **`svg-textgrad` FSM Loop** — New built-in loop applying gradient-based text optimization to SVG generation; tracks gradient history across iterations with escalating refinement prompts, best-artifact retention, and convergence detection (FEAT-1098)
- **`svg-image-generator` FSM Loop** — New built-in generator-evaluator harness for SVG icon and illustration creation; accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI with four SVG-specific scoring criteria (`visual_clarity` 2×, `originality` 2×, `craft` 1×, `scalability` 1×); creates a timestamped run folder under `.loops/tmp/` for each execution (FEAT-1094, ENH-1097)

### Changed

- **`ll-issues show` Score Dimension Columns** — Card output now displays `cmplx`, `tcov`, `ambig`, and `chsrf` score dimension columns for richer issue triage at a glance (ENH-1100)
- **`ll-issues refine-status` Score Dimension Columns** — `refine-status` table now includes score dimension columns sourced from issue frontmatter (ENH-1099)
- **`ll-issues impact-effort` JSON Output** — Added `--json` flag for machine-readable impact/effort data (ENH-1101)
- **`svg-image-generator` Error Routing** — Added error routing and explicit failure terminal states to the loop (ENH-1100)
- **`svg-textgrad` Robustness** — Added error handlers, per-iteration score history, best-artifact tracking, and convergence detection (ENH-1103)
- **`ll-generate-schemas` Internal Tooling** — Marked as internal dev tooling with a notice in CLI help and documentation; added `ll-generate-schemas` and `mcp-call` entry points to CLI reference docs (ENH-1025, ENH-1093)

### Fixed

- **`auto-refine-and-implement` Skip File Accumulation** — Added `init` state to clear the skip file at the start of each run, preventing premature exit when skips accumulate across runs (BUG-1095)
- **`recursive-refine` Parent Cleanup** — Decomposed parent issues are now correctly moved to `.issues/completed/` after breakdown (BUG-1096)
- **`svg-textgrad` Evaluate State URI** — Resolved invalid `file://` URI in the evaluate state of svg loops that caused repeated exit-code-1 failures (BUG-1102)
- **Loop Run History Archiving** — Loop runs are now archived to history immediately upon completion rather than deferred to the next run (BUG-1104)

## [1.81.1] - 2026-04-13

### Added

- **Parallel State Type for FSM Loops** — New `parallel:` state type enables concurrent sub-loop fan-out for processing multiple issues simultaneously within a single FSM loop (FEAT-1072)
- **Parallel State Wiring, Display, and Docs** — Full wiring of parallel state execution with status display and updated documentation (ENH-1078)
- **Parallel State Documentation** — Comprehensive reference documentation for the parallel FSM state type (FEAT-1082)

### Changed

- **Logger and `configure_output` Wiring** — Wired `Logger` and `configure_output` to all non-compliant CLI commands for consistent output handling across tools (ENH-1064)
- **`confidence-check` Unconditional Write-Back** — `confidence-check` now always writes concern findings back to the issue file without prompting (ENH-1087)
- **`ll-issues show` Additional Fields** — Added `source`, `norm`, and `fmt` fields to card and JSON output (ENH-1088)
- **`issue-size-review` Size Frontmatter** — After assessment, `issue-size-review` writes the size rating directly to the issue file's frontmatter for downstream use (ENH-1090)
- **`ll-issues refine-status` Size Column** — `refine-status` now shows a Size column sourced from `issue-size-review` frontmatter (ENH-1091)

### Fixed

- **`ll:update` Relative Path Fix** — Fixed the update skill to use an absolute path from `pip show` instead of `./scripts`, allowing it to work when invoked outside the little-loops repo (BUG-1071)
- **`recursive-refine` Duplicate `issue-size-review`** — Guarded against `issue-size-review` running twice when `breakdown_issue` fires during recursive refinement (BUG-1079)
- **Hooks Installation via Plugin** — Removed broken manual hooks install step; hooks are now managed automatically via the plugin mechanism (BUG-863)

## [1.81.0] - 2026-04-12

### Added

- **`sprint-refine-and-implement` FSM Loop** — New built-in loop that runs the same refine → implement pipeline as `auto-refine-and-implement` but scoped to a named sprint's issue list, processing issues in sprint YAML order rather than confidence ranking; accepts sprint name as a positional argument (`ll-loop run sprint-refine-and-implement <sprint-name>`) (FEAT-1063)
- **`sprint-build-and-validate` Size Review and Recovery** — Added a `size_review` gate before sprint runs: Very Large issues (score ≥ 8) are decomposed first via `recursive-refine`; non-zero sprint exits now route to `extract_unresolved` → `refine_unresolved` recovery path to prevent silent failure of oversized or blocked issues (ENH-1052)
- **Extension SDK Documentation** — Updated `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md`, and `README.md` to reflect the complete extension SDK including `LLTestBus` and `ll-create-extension` (FEAT-1045, #916)

### Changed

- **`ll-sprint show` Contention Threshold Display** — Serialized wave headers now include the active `overlap_min_files` and `overlap_min_ratio` threshold values (e.g., `serialized — file overlap [min_files=2, ratio=0.25]`) and a tuning hint pointing to `dependency_mapping` in `ll-config.json` (ENH-1059)
- **File Overlap Detection AND Logic** — Overlap is now triggered only when both `overlap_min_files` AND `overlap_min_ratio` thresholds are met (previously OR); reduces false serialization for issue pairs that share a large number of small files or a high ratio across few files (ENH-1060)
- **Directory Hints Scoped to "Files to Modify"** — In parallel runs, directory-level hints extracted from issue files are now inserted only within the "Files to Modify" section rather than throughout the prompt body, preventing spurious directory context from inflating unrelated sections (ENH-1061)
- **Post-Update Config Health Check** — `/ll:update` now validates `.ll/ll-config.json` against the current schema after updating and reports unknown or invalid keys (ENH-1047)

### Fixed

- **Logger ANSI Leak to Piped Output** — `Logger` color state is now correctly wired through `configure_output`; ANSI escape codes no longer bleed into piped or redirected output when color is disabled (BUG-1054)
- **`recursive-refine` Spurious Child Enqueuing** — Child detection now uses a two-step parent-reference filter: only issues whose file contains `Decomposed from <PARENT_ID>` are accepted as children, preventing unrelated issues created concurrently from being incorrectly enqueued (BUG-1058)
- **`extensions` Key Placement in `config-schema.json`** — Fixed invalid JSON schema where `extensions` was placed outside the `properties` block; added regression test asserting correct placement (ENH-1046)

## [1.80.0] - 2026-04-12

### Added

- **`LLTestBus` Test Harness** — Standalone class in `little_loops/testing.py` that loads a recorded `.events.jsonl` file and replays events through registered extensions offline for assertion-based testing without running a live loop (FEAT-1043)
- **`ll-create-extension` Core CLI** — New `ll-create-extension <name>` command scaffolds an extension repo with `pyproject.toml` entry points, a skeleton `on_event` handler implementing `LLExtension`, and an example test using `LLTestBus` (FEAT-1048)
- **`ll-create-extension` Documentation Wiring** — Registered in `commands/help.md`, `skills/init/SKILL.md`, and `skills/configure/areas.md` (FEAT-1049)
- **Extension SDK Documentation** — Updated `docs/reference/API.md` (Module Overview table), `docs/ARCHITECTURE.md` (directory trees, bug-fix on `cli/loop/testing.py` comment), `docs/reference/CONFIGURATION.md` (extension authoring cross-references), `CONTRIBUTING.md` (Authoring Extensions workflow section), `.claude/CLAUDE.md` (CLI Tools list), and `README.md` (tool count and CLI section) to reflect the complete extension SDK (FEAT-1045)

### Changed

- **`ll-loop run` LLM Response Preview** — Non-verbose mode now shows up to 5 lines of LLM response output for prompt/AI-agent states, matching the existing shell state output preview (ENH-1051)
- **`sprint-build-and-validate` Linear Flow Refactor** — Replaced the confidence-check/fix-issues retry cycle with a streamlined linear flow: create sprint → map dependencies → audit conflicts → verify issues → commit → run sprint (ENH-1051)
- **`ll-loop run` Config-Driven Colors** — `display_progress()` and `print_execution_plan()` now read verdict symbol and terminal marker colors from the config-driven `edge_label_colors` dict instead of hardcoded ANSI codes (ENH-1050)
- **Post-Update Config Health Check** — `/ll:update` now validates `.ll/ll-config.json` against the current schema after updating and reports unknown or invalid keys (ENH-1040)
- **`auto-refine-and-implement` Max Iterations** — Raised `max_iterations` to 500 to support longer autonomous refinement runs (90d03ac)

### Fixed

- Remove redundant f-string prefixes and reformat argument parser (f4e67a1)
- Move `extensions` key inside `properties` block in config-schema (ace6216)

## [1.79.0] - 2026-04-11

### Added

- **Extension SDK with Scaffolding and Test Harness** — Full extension SDK with project scaffolding tooling and eval test harness (FEAT-916, #916)
- **`description` Field for FSM Shared State Fragments** — Adds optional `description` field to fragment libraries and `ll-loop fragments` sub-command for documentation and discoverability (FEAT-1042, #1042)
- **`ll-deps apply` Sub-Command** — New `apply` sub-command writes inferred dependency relationships back to issue files, enabling automated dep wiring from the CLI (FEAT-1007, #1007)
- **`/ll:audit-issue-conflicts` Core Skill** — New skill detects ID conflicts, duplicate summaries, and inconsistent states across backlog and completed issue directories (FEAT-1028, #1028)
- **`audit-issue-conflicts` Documentation Wiring** — Integrated into all documentation surfaces: help, README, ARCHITECTURE, API reference, and skills index (FEAT-1030, #1030)
- **`audit-issue-conflicts` Structural Tests** — Test suite covering skill invocation, conflict detection, and auto-apply behavior (FEAT-1031, #1031)

### Fixed

- **FSM Validator False-Positive for `llm_structured` Custom `on_*` Routing** — Fixed false-positive validation error and broken routing for `llm_structured` evaluators using custom `on_<verdict>` keys (BUG-1039, #1039)

### Changed

- **`refine-to-ready-issue` Skips Retry on Outcome Confidence Failure** — Outcome confidence failure no longer triggers a retry loop; only structural/completeness failures trigger refinement retry (ENH-1033, #1033)
- **`/ll:publish` Moved to Project-Level Command** — `publish` is now a project-local command rather than a built-in; prevents accidental invocation outside the little-loops source repo (ENH-1034, #1034)
- **Consolidated Redundant Test Coverage** — Replaced duplicated parametrized test pairs with single parametrize calls across `test_cli.py`, `test_orchestrator.py`, and `test_worker_pool.py` (ENH-1035, ENH-1036, ENH-1037)

## [1.78.0] - 2026-04-11

### Added

- **`agent:` and `tools:` FSM State Fields — Tests and Subprocess Pass-Through** — Full implementation of per-state `agent:` and `tools:` config fields with subprocess argument pass-through; test coverage for state-level overrides (FEAT-1011)
- **HTML Website Generator Built-In Loop** — New `html-website-generator` built-in FSM loop with generator-evaluator harness for iterative website generation and quality assessment (FEAT-1023)
- **`/ll:audit-issue-conflicts` Skill with Auto-Apply** — New skill scans issues for ID conflicts, duplicate summaries, and inconsistent states; detects and optionally auto-resolves conflicts across backlog and completed directories (FEAT-1027)
- **`audit-issue-conflicts` Wiring, Docs, and Tests** — Integration wiring, documentation, and test suite for the `audit-issue-conflicts` skill (FEAT-1029)
- **`/ll:publish` Maintainer Command** — New command bumps version in all source files (`plugin.json`, `marketplace.json`, `pyproject.toml`, `__init__.py`) and commits; guards against running outside the little-loops source repo (ENH-1020)

### Changed

- **`agent:` and `tools:` API Reference** — Added `agent:` and `tools:` parameters to `run_claude_command()` documentation in `docs/reference/API.md` (ENH-1015)
- **`agent:` and `tools:` Create-Loop Reference** — Updated `skills/create-loop/reference.md` with `agent:` and `tools:` field descriptions, valid values, and examples (ENH-1016)
- **`/ll:update` Consumer-First** — Rewrote `/ll:update` to always update both pip package and Claude Code plugin regardless of repo type; removed source-repo guards and marketplace steps from the consumer update flow (ENH-1020)
- **Issue-by-ID Lookups Use `ll-issues path`** — 8 skills and commands (`manage-issue`, `format-issue`, `go-no-go`, `confidence-check`, `issue-size-review`, `wire-issue`, `refine-issue`, `ready-issue`) now resolve issue IDs via `ll-issues path <ID>` instead of ad-hoc `find | grep` loops; completed and deferred issues are now found correctly (ENH-1022)

### Fixed

- **`refine-to-ready-issue` Retry Routing** — Fixed incorrect FSM transition from `retry` state that caused infinite loops instead of properly routing back to the refine pipeline (BUG-1026)
- **`refine-to-ready-issue` Score-Failure to Breakdown Path** — Added direct transition from `check_refine_limit` budget exhaustion to `breakdown_issue`; prevents dead-end state when issue cannot be refined further (BUG-1032)
- **`ll-gitignore` Missing from Permissions and Help** — Added `ll-gitignore` to the canonical permissions block in `/ll:init`, the permissions authorization list in `/ll:configure`, and the CLI TOOLS section in `/ll:help`; tool count updated from 12 to 13 (ENH-1024)

## [1.77.0] - 2026-04-10

### Added

- **`ll-issues path` Sub-command** — New `path` (alias `p`) sub-command resolves issue IDs in any format (`1009`, `TYPE-NNN`, or `P-TYPE-NNN`) to relative file paths in `.issues/`; supports `--json` flag for programmatic use (FEAT-1009)
- **`agent:` and `tools:` State-Level Fields** — FSM loop states now accept `agent:` and `tools:` config fields for per-state model and tool overrides; documented in create-loop wizard and API reference (FEAT-1010, ENH-1012, ENH-1014)

### Changed

- **`auto-refine-and-implement` Wired to `recursive-refine`** — Replaced the flat `refine-to-ready-issue` sub-loop call with `recursive-refine`, enabling automatic decomposition of oversized issues into child issues before implementation; the outer loop now batches all passed issues from `recursive-refine-passed.txt` into an implementation queue and processes them sequentially before moving to the next backlog issue (ENH-1021)
- **Skip `size-review` When Scores Already Pass** — `recursive-refine` loop adds a `recheck_scores` gate to bypass redundant size-review execution on issues that already meet readiness thresholds (ENH-1018)

### Fixed

- **`confidence_check` Invalid Evaluator Type** — Split `confidence_check` state into two steps and added load-time validator to catch unknown evaluator types; fixes crash in `refine-to-ready-issue` sub-loop (BUG-1019)
- **FSM Sub-loop Outcome Routing** — Fixed executor to route sub-loop outcomes by terminal state name (`done` vs `failed`) rather than termination reason, preventing failed sub-loops from being treated as successes (BUG-1017)
- **`resolve_fragments()` Built-In Loops Fallback** — Fragment resolution now automatically falls back to the built-in loops directory when user paths are absent, enabling shared library imports without manual copying (BUG-1008)

[1.84.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.83.0...v1.84.0
[1.83.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.82.0...v1.83.0
[1.82.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.81.1...v1.82.0
[1.81.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.81.0...v1.81.1
[1.81.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.80.0...v1.81.0
[1.80.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.79.0...v1.80.0
[1.79.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.78.0...v1.79.0
[1.78.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.77.0...v1.78.0
[1.77.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.76.0...v1.77.0

## [1.76.0] - 2026-04-08

### Added

- **`recursive-refine` Built-In Loop** — New built-in FSM loop that recursively refines all backlog issues through nested sub-loops; handles JSON input unpacking and runs until all issues are refined or exhausted (FEAT-1000)
- **`auto-refine-and-implement` Built-In Loop** — New issue-management loop that refines each backlog issue to ready (via `refine-to-ready-issue` sub-loop) then implements it (via `/ll:manage-issue`); skips and tracks issues that fail refinement; runs until backlog is exhausted (FEAT-996)
- **`ReferenceInterceptorExtension`** — Passthrough reference implementation of `InterceptorExtension` in `extensions/reference_interceptor.py`; copy-paste starting point for custom interceptors (FEAT-995)
- **`before_issue_close` Veto Hook** — `close_issue()` now accepts an `interceptors` list; any interceptor returning `False` from `before_issue_close()` vetoes the close and aborts the move (FEAT-994)
- **`wire_extensions()` Executor Support** — `wire_extensions()` gains an optional `executor` parameter; when provided, extensions implementing `ActionProviderExtension`, `EvaluatorProviderExtension`, or `InterceptorExtension` are wired into the `FSMExecutor` registry (FEAT-993)
- **FSMExecutor Core Hook Dispatch** — Attributes, action, evaluator, and interceptor dispatch wired into `FSMExecutor`; extension registry integration complete (FEAT-987)
- **Log Discovery and Extraction for `ll-loop` and `ll-commands`** — New log discovery and extraction capabilities for loop and command execution history (FEAT-1001)
- **`ll-logs` Documentation and Wiring** — Documentation and wiring updates for log management across ll-loop and ll-commands (FEAT-1004)

### Changed

- **`ll-loop` JSON Input Auto-Unpack** — `ll-loop run` now automatically unpacks JSON input into named context variables for cleaner loop state management (ENH-999)
- **`ll-auto` Shell Action for Issue Implementation** — Replaced `implement_issue` prompt with `ll-auto --only` shell action in loops for more reliable execution (ENH-997)
- **Enforce Cross-Type Integer ID Uniqueness** — `duplicate-id` hook now enforces unique integer IDs across all issue types, not just within a single type (ENH-986)

### Fixed

- **`recursive-refine` Loop Bash Interpolation Clash** — Dropped braces from bare bash variables to fix syntax clash causing immediate loop exit (BUG-999)
- **`outer-loop-eval` Silent Failure on Empty Loop Name** — Added input validation to prevent hallucinated reports when `loop_name` is empty (BUG-998)
- **`ll-loop --show-diagrams --clear` Ghost Fragments** — Used alternate screen buffer to prevent ghost diagram fragments in scrollback (BUG-989)

[1.76.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.75.0...v1.76.0


## [1.75.0] - 2026-04-07

### Added

- **Bidirectional Extension Hooks with Interceptors** — Contributed actions and bidirectional plugin extension hooks (FEAT-915)
- **`ll-history` Integration Tests** — Integration tests for `ll-history export --type` and `--scoring` CLI options (FEAT-978)
- **`ll-auto --verbose` Full Content** — `--verbose` now displays full prompt content without truncation for complete debugging visibility (ENH-979)
- **`/ll:wire-issue` in Refine-Issue Next Steps** — Added `/ll:wire-issue` as first recommended next step in refine-issue workflow (ENH-981)

### Changed

- **Route Over-Refined Issues to `issue-size-review`** — Loops now redirect over-refined issues to the size review workflow instead of failing (ENH-980)
- **`ll-auto` Prompt Display Formatting** — Improved prompt display formatting for better readability (ENH-964)
- **`refine_waves_for_contention` Performance** — Eliminated double pair iteration when conflicts exist (ENH-973)
- **`find_issues` Hot Loop Performance** — Replaced double `Path.exists()` syscalls with frozenset lookup (ENH-971)
- **`scan_completed_issues` Performance** — Replaced N+1 `git log` subprocess calls with batched calls (ENH-970)

### Fixed

- **Handoff Reminder Silenced by Stale Continue-Prompt File** — Context monitor now resets `handoff_complete` to `false` on new sessions (BUG-982)
- **Naive `datetime.now()` Usage** — Replaced timezone-naive datetime calls with `_iso_now()` in state manager and issue lifecycle (BUG-969)
- **`_is_lifecycle_file_move` Substring Match Too Broad** — Anchored lifecycle path checks with `startswith` to prevent false matches (BUG-968)
- **Orphaned Worktree Stash on Pop Failure** — Fixed stash orphan when `git stash pop` fails in `_handle_conflict` (BUG-967)
- **`--skill` Filter Not Applied to Commands in `ll-messages`** — Skill session filter now correctly applies to the commands list (BUG-966)
- **Circuit Breaker Bypass on Exception Path** — `_consecutive_failures` now incremented on all failure paths including exceptions (BUG-965)
- **`agent-eval-improve` Loop Missing Terminal State** — Added `failed` terminal state to prevent infinite loops on evaluation failure (aafc47fb)

[1.75.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.74.0...v1.75.0

## [1.74.0] - 2026-04-06

### Added

- **`create-eval-from-issues` Skill** — New `/ll:create-eval-from-issues` skill generates FSM eval harnesses from issue IDs for automated user-perspective quality evaluation (FEAT-953)
- **`improve-claude-md` Skill** — New `/ll:improve-claude-md` skill rewrites CLAUDE.md using `<important if>` block restructuring for improved LLM instruction adherence (FEAT-949)
- **`ll-issues skip` Subcommand** — New `ll-issues skip <ID>` deprioritizes stuck issues with optional priority override and audit trail (FEAT-955)
- **Sprint Scoping for `confidence-check` and `issue-size-review`** — Both skills now support `--sprint <name>` to restrict analysis to sprint-specific issues (ENH-956)
- **`issue-size-review` Usage Documentation** — Added guidance clarifying when to invoke `issue-size-review` as a follow-up to failed readiness checks (ENH-963)

### Fixed

- **Nested `${}` in `check_lifetime_limit`** — Replaced broken bash variable interpolation in the `refine-to-ready-issue` loop that was silently crashing automation runs (BUG-954)

[1.74.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.73.0...v1.74.0

## [1.73.0] - 2026-04-05

### Added

- **JSON Schema Generation for Event Types** — 19 machine-readable JSON Schema files for all `LLEvent` types in `docs/reference/schemas/`; CLI command `ll-generate-schemas` (FEAT-919)
- **`wire-issue` Skill** — Post-refinement integration wiring pass tracing dependency graphs, missing callers, registrations, doc coupling, and test gaps; supports `--auto` and `--dry-run` (FEAT-951)
- **`max_refine_count` Configuration** — Lifetime refinement cap for `refine-to-ready-issue` loop; configurable via `ll-config.json` (3502f2fd)
- **Skill Pre-Expansion (`skill_expander`)** — `ll-auto` now pre-expands skill/command Markdown into self-contained prompt strings before spawning Claude subprocesses, eliminating the `ToolSearch → Skill` deferred-tool round-trip. Falls back transparently to the original slash command on any failure. (`fc296bdf`)

### Changed

- **Expanded `lib/common.yaml` State Fragments** — Added `llm_gate` and `numeric_gate` reusable fragments covering 15+ built-in loop patterns (ENH-947)
- **CLI Fragment Library `lib/cli.yaml`** — 12 tool-specific fragments for `ll-auto`, `ll-issues`, `ll-history`, and more; eliminates copy-paste of CLI invocations (ENH-950)
- **`--skip` Flag for `ll-issues next-issue`** — Prevents loop starvation by excluding specified issues from queue selection (ENH-952)

### Fixed

- **`confidence_check` Loop** — Replaced `llm_structured` eval with `shell_exit` for reliable exit-code-based confidence checking (391c5ad4)

[1.73.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.72.0...v1.73.0

## [1.72.0] - 2026-04-04

### Added

- **outer-loop-eval Built-in Loop** — New built-in loop for observing and evaluating loop quality; 6-state FSM (analyze_definition, run_sub_loop, analyze_execution, generate_report, refine_analysis, done) (FEAT-933)
- **Shared Fragment Libraries for Cross-Loop State Reuse** — Reusable state fragments in `.loops/lib/` for DRY state definition across loops; supports `import:` key and `fragment:` references with deep-merge semantics; migrates 10 built-in loops to shared `shell_exit` fragment (FEAT-937)
- **rename-loop Skill** — New skill for renaming built-in or project-level loops and updating all references (89d40d7e)

[1.72.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.71.0...v1.72.0

## [1.71.0] - 2026-04-03

### Added

- **`--worktree` Flag for `ll-loop run`** — `ll-loop run` now supports `--worktree` for isolated branch execution in a temporary git worktree, preventing state leakage between loop runs (ENH-945)

### Fixed

- **`ll-loop` Slash Command Steps** — Fixed slash command steps failing due to ToolSearch timeout with `--no-session-persistence`; now uses `run_claude_command()` correctly (BUG-946)
- **`manage-release` Completed Issues Count** — Fixed `manage-release` showing 0 completed issues due to date-filter approach; now uses git-log for accurate detection (BUG-942)
- **Lint, Type, and Format Issues** — Resolved outstanding lint, type checking, and format issues across the scripts package (83592edd)

### Changed

- **Loop History Per-Run Timestamped Folder** — Loop execution history is now saved to flat timestamped folders per run, making individual runs easier to inspect (ENH-944)
- **Expanded `_parse_completion_date` Regex** — `_parse_completion_date` now uses a broader regex with git-log as a fallback, improving date detection reliability (ENH-943)

[1.71.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.70.0...v1.71.0

## [1.70.0] - 2026-04-03

### Added

- **Prompt-Across-Issues Built-In Loop** — New `prompt-across-issues` FSM automation loop for running a prompt across all issues in the backlog (ae5709f9)
- **Refine Limit Guard and Dynamic Thresholds** — `refine-to-ready-issue` loop now enforces a maximum refinement round limit and uses dynamic confidence thresholds to prevent runaway loops (c295070c)
- **`--skip` Flag for `ll-issues next-action`** — Added `--skip` flag to prevent issue starvation when a specific issue blocks the queue (256c5e82)
- **Parallel Merge** — Completed ENH-825: parallel orchestrator now merges worktree results back to main concurrently (b2bfa48e)
- **Category and Labels for FSM Loops** — Loop schema now supports `category` and `labels` fields; `ll-loop list` surfaces them for filtering (b49f29d8)

### Changed

- **Generalized Sub-Loop Diagram Display** — `ll-loop show` now renders nested sub-loop diagrams to arbitrary depth N, not just one level (b4a2bef5)
- **GIT_DIR/GIT_WORK_TREE in Worktree Sessions** — Subprocess launcher now sets `GIT_DIR` and `GIT_WORK_TREE` env vars so git commands resolve correctly inside worktrees (c6b265f9)
- **Configurable `pull_issues` Limit** — `SyncConfig` now exposes `pull_limit` to cap how many issues are pulled from GitHub per sync run (6981527a)
- **FSM Executor Refactored** — Result types and runner functions extracted from `executor.py` into dedicated modules for better separation of concerns (e530b52c)

### Fixed

- **`on_error` Fires When `next` Is Also Defined** — FSM `on_error` handler now correctly activates on non-zero exit even when a `next` transition is present (80846d6f)
- **Trailing Newlines Stripped from Shell Output** — Captured shell command output no longer includes trailing newlines that caused downstream comparison failures (beb25a5d)
- **`input_key` and Template Variable Escaping in `greenfield-builder`** — Fixed missing `input_key` binding and incorrect template variable escaping in the greenfield-builder loop (90bc05a5)
- **Surgical Rebase When Main Advances Past Leaked Commits** — `ll-parallel` now attempts a surgical rebase when the main branch has advanced past commits that leaked from a worktree (e2af31e6)
- **Done/Active Counts in Parallel Merge Path** — Fixed incorrect Done and Active counters during the parallel merge phase (7c97439f)
- **Score Fallback When `confidence_check` Times Out** — `refine-to-ready` loop now uses a fallback score when the confidence check subprocess times out (dc38c539)
- **CWD-Relative Manifest Reads Guarded in Update Skill** — `update` skill no longer crashes when `.claude-plugin/` is absent from the current working directory (7bcecb4a)

[1.70.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.69.0...v1.70.0

## [1.69.0] - 2026-04-02

### Added

- **Extension Architecture (LLExtension Protocol)** — Introduced a formal extension protocol with `LLExtension`, `ExtensionLoader`, and `wire_extensions` API; extensions plug into the EventBus for live event observation without modifying core internals (FEAT-911)
- **Greenfield Builder and Eval-Driven Development Loops** — Added `greenfield-builder` and `eval-driven-development` FSM automation loops for bootstrapping new projects and iterating on AI-evaluated output (FEAT-914)
- **Topic-Based EventBus Filtering** — Extensions and subscribers can now filter events by topic pattern, enabling targeted observation without processing every emitted event (ENH-926)

### Changed

- **EventBus Emission in StateManager** — StateManager now emits lifecycle events on state transitions, making internal state changes observable by extensions (ENH-920)
- **EventBus Emission in Parallel Orchestrator** — ll-parallel now emits issue start/complete/fail events on the EventBus for real-time parallel run observability (ENH-921)
- **ExtensionLoader Wired to Live EventBus in CLI Entry Points** — Extensions registered via `wire_extensions` are now connected to the live EventBus at CLI startup (ENH-922)
- **`ll-sprint show` Enhanced Detail and Output Quality** — Sprint show command now displays richer issue detail, cleaner formatting, and improved output structure (ENH-923)

### Fixed

- **context-monitor.sh Hook Timeout** — Reduced jq invocations from ~15 to ~5 per hook call, eliminating PostToolUse read hook timeouts under load (BUG-924)

[1.69.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.68.0...v1.69.0

## [1.68.0] - 2026-04-02

### Added

- **CLI Short Forms for Shared Arguments** — Added `-j`, `-o`, `-f`, `-s`, and other short flags across all CLI commands for a consistent, ergonomic developer experience (ENH-907, ENH-910)
- **New FSM Automation Loops** — Added `agent-eval-improve`, `dataset-curation`, `prompt-regression-test`, `test-coverage-improvement`, and `incremental-refactor` loops (be2c634c, da3e802c)
- **Configurable FSM Box Diagram Glyphs** — FSM loop box diagrams now support configurable glyph mappings (387e1d53)

### Changed

- **Rewrite Skill Descriptions as Trigger Documents** — All 21 skill descriptions restructured for better auto-activation and discoverability (ENH-493)
- **`/ll:update` Skips Already-Current Components** — Update command now detects and skips plugin/package steps when already at the latest version (ENH-905)
- **`ll-loop status` Shows Log File Details** — Status output now includes log file path and line counts for active loops (ENH-899)
- **Delegate issue-refinement to refine-to-ready sub-loop** — Reduced code duplication by delegating issue-refinement loop FSM states to the `refine-to-ready-issue` sub-loop (ENH-901)
- **Document `ll-loop list` Flags in README** — Added missing `--running`, `--all`, and `--format` flag documentation to CLI quick-reference (ENH-902)

### Fixed

- **`ll-loop list --running` Misses Recently-Started Loops** — `list_running_loops` now includes loops in the `starting` state so they appear immediately after launch (BUG-897)
- **FSM context_passthrough passes full capture dicts** — Fixed to pass `.output` strings instead of raw capture dicts in context passthrough (bd2f4cd5)
- **`/ll:update` reads plugin.json unconditionally** — Guarded `plugin.json` reads behind `DO_MARKETPLACE` flag to avoid errors in non-marketplace environments (da8e8c3f)
- **`refine-to-ready-issue` loop missing verify_issue state** — Added `verify_issue` FSM state to the sub-loop for complete issue lifecycle coverage (42724be3)

### Documentation

- Auto-format source and test files with ruff (58366a35)

[1.68.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.2...v1.68.0

## [1.67.2] - 2026-03-31

### Changed

- **Migrate ll Runtime Files from `.claude/` to `.ll/` Directory** — All little-loops runtime and configuration files now live in `.ll/` to avoid Claude Code write permission prompts (ENH-896)
- **Migrate workflow-analysis and user-messages paths from `.claude/` to `.ll/`** — Completed directory migration for workflow-analysis paths and user-messages files (ENH-900)
- **Delegate issue-refinement to refine-to-ready-issue sub-loop** — Refactored loops to use sub-loop delegation for issue refinement (09d46be)

### Migration

- **Breaking**: Move your config file: `mkdir -p .ll && mv .claude/ll-config.json .ll/ll-config.json`
- Other runtime files (`.ll-lock`, `ll-context-state.json`, `ll-continue-prompt.md`, etc.) will be recreated automatically in `.ll/` on next session
- Local overrides file moved: `.claude/ll.local.md` → `.ll/ll.local.md`
- Update `.gitignore` if you have custom entries referencing `.claude/ll-*` paths

### Documentation

- Remove resolved FEAT-862 update-docs stub from FSM loop docs (a1ee5d5)
- Add missing `ll-loop list` flags to CLI quick-reference in README (6908461)
- Correct loop count to 26 and add ENH-902 for `ll-loop list` flags (073c4a8)
- Update issue-refinement loop description to reflect sub-loop delegation (65034c7)
- Document general-task loop lifecycle in LOOPS_GUIDE (131ab59)

### Other

- Add continuation prompt and loop-suggestions to `.gitignore` (afaf00b)

## [1.67.1] - 2026-03-30

### Changed

- **Init interactive CLAUDE.md prompt** — Init wizard now prompts users to add ll- CLI command documentation to their project's CLAUDE.md (ENH-894)

### Fixed

- **Plugin identifier in update skill** — Use fully qualified plugin identifier `ll@little-loops` in `/ll:update` (f9b1391)

### Documentation

- Update FSM loop count to 27 (80e32fc)

### Other

- Add `docs/research/` to `.gitignore` (27d8cfd)
- Add BUG-897 and BUG-898 for loop listing and update skill bugs (347cfed)

## [1.67.0] - 2026-03-26

### Added

- **`/ll:update` Slash Command for Plugin and Package Updates** — New skill for updating little-loops components (plugin marketplace listing, Claude Code plugin, and pip package) with per-component control via `--only` flag (FEAT-892)

### Changed

- **Configurable thresholds in refine-to-ready-issue loop** — Added `context:` block to `refine-to-ready-issue.yaml` with `readiness_threshold` and `outcome_threshold` defaults; replaced hardcoded values with `${context.*}` variable interpolation (ENH-893)
- Add CLAUDE.md documentation step to `ll-init` interactive wizard (7253feac)

### Fixed

- Fix stale status values in GETTING_STARTED.md (e91a84fc)

### Documentation

- Update FSM loop count to 26 and document general-task loop (d296df44)
- Add `--only` flag to `ll-sprint run` documentation (261729db)
- Update skill count to 21 and add cleanup-loops to all reference docs (1e32ea65)
- Add `/ll:update` references and general-purpose loops section to guides (cd9de7eb)
- Document interactive wizard behavior and register new builtin loops in init docs (2b7b3725)

## [1.66.1] - 2026-03-26

### Changed

- Move general-task and refine-to-ready-issue loop YAML configs from `.loops/` into `scripts/little_loops/loops/` to co-locate them with the Python package (97236ca5)

## [1.66.0] - 2026-03-26

### Added

- **Add /ll:cleanup-loops Skill for Stuck/Failed Loop Management** — New skill for finding, diagnosing, and cleaning up stuck or stale loops; investigates PIDs, kills dead processes, cleans state files, and reports where each loop got stuck (FEAT-890)

### Fixed

- **ll-loop --background fails: Missing `__main__.py`** — Fixed immediate crash when running `ll-loop run <loop-name> --background`; added `__main__.py` entry point to `little_loops/cli/loop/` package (BUG-891)

### Documentation

- Update skills count and add cleanup-loops to command reference (d4578818)
- Add cleanup-loops skill to all reference docs (9bc0df0f)

## [1.65.0] - 2026-03-25

### Added

- **refine-to-ready-issue automation loop** — Add FSM automation loop for automatically refining issues to ready state (375d159)

### Fixed

- **context-monitor.sh default context limit too low** — Updated default context limit from 150K to 1M tokens to match current Claude model capabilities (BUG-809)
- **ParallelAutomationConfig `stream_subprocess_output` key not read** — Read `stream_subprocess_output` key correctly in `from_dict` (0c12718)
- **Config schema `cli` section placement** — Move `cli` section inside `properties` in config-schema.json (a1dfd5f)
- **BRConfig.to_dict() parallel/automation key mismatch** — Align `BRConfig.to_dict()` parallel/automation keys with schema (5a26dde)

### Changed

- **ConfidenceGateConfig schema alignment** — Remove legacy threshold field, align with schema (b4e6569)

### Documentation

- Add loop issues section for built-in loops packaging bug (d40f400)
- Update reference docs for config alignment changes (2dfc1c8)

## [1.64.1] - 2026-03-25

### Fixed

- **Built-in loops missing after pip install** — Bundle `loops/` directory as package data so built-in FSM loop configs are included in the installed package (BUG-885)

### Documentation

- Clarify and expand documentation across all guides (74439c2b)

## [1.64.0] - 2026-03-24

### Added

- **`refine-status` ISSUE-ID single-issue filter** — Filter `refine-status` output to inspect a single issue (FEAT-873)
- **`next-issue` command sorted by confidence and readiness** — New `ll-issues next-issue` subcommand to find the most implementation-ready issue by confidence and readiness scores (FEAT-874)
- **`next-issues` subcommand with ranked list output** — New `ll-issues next-issues` subcommand showing a ranked list of issues prioritized for implementation (ENH-884)

### Fixed

- **Display timing bug in non-TTY environments** — Add `flush=True` to all `print()` calls so output appears immediately when running in external projects (BUG-876)
- **`check_semantic` evaluator receives no evidence from skill execution** — Wire execute-phase output to the `check_semantic` LLM evaluator so it has context to evaluate (BUG-880)
- **`AUTOMATIC_HARNESSING_GUIDE` incorrectly describes `check_semantic` access** — Correct the echo-output explanation to accurately describe how `check_semantic` accesses prior output (BUG-881)
- **Scraper type safety** — Tighten types and defer crawler assignment until after `start()` (7a672ad3)

### Changed

- **`--auto` flag for `commit` skill** — Enable non-interactive automation use of the commit skill for use in FSM loops and ll-auto (ENH-875)
- **Add `refine_status` and `cli` to Full Configuration Example** — Fill in missing sections in the configuration reference documentation (ENH-877)
- **Loop-name header bar above top-level FSM diagram** — Display a visual header bar with the loop name when `--show-diagrams` is used (ENH-878)
- **Elevate `check_skill` prominence in harness wizard** — Distinguish evaluation phases by observability rather than cost, making check_skill the recommended first choice (ENH-879)
- **Harness wizard pre-selects `check_stall` for `action_type: prompt`** — Improve wizard defaults to auto-select stall detection when the execute phase uses a prompt action (ENH-882)
- **Harness wizard generates multi-criteria `check_semantic` evaluation prompts** — Wizard now generates richer, multi-criteria evaluation prompts for `check_semantic` phases (ENH-883)

## [1.63.0] - 2026-03-23

### Added

- **`use_feature_branches` config boolean for `ll-parallel` and `ll-sprint`** — Opt-in feature branch isolation per worker; each issue gets its own branch when enabled (795160cb)
- **Per-loop config overrides in FSM loop YAML** — Individual loop definitions can now override global config fields without affecting other loops (0d66fc81)

### Changed

- **Throttle orchestrator `_save_state` writes to 5-second intervals** — Reduces I/O overhead during high-frequency loop execution (8b0a239b)

## [1.62.0] - 2026-03-23

### Added

- **`init` and `configure` auto-update pip package** — ENH-864: Auto-update the little-loops pip package when an outdated version is detected at startup

### Fixed

- **FSM diagram horizontal shift on state highlight** — BUG-759: Strip ANSI codes before measuring diagram line width to prevent layout shifts
- **`/ll:init` prompts hook loading method for plugin users** — BUG-864: Remove hook installation step for plugin users in init flow
- **context-monitor exits 2 on every tool call after threshold** — BUG-865: Rate-limit exit 2 reminders to once per 60 seconds
- **handoff_complete state lost on session restart** — BUG-866: Preserve handoff_complete flag across session restarts in context-monitor
- **context-monitor.sh missing jq fallbacks on tool input parsing** — BUG-867: Add jq fallbacks to prevent exit on malformed input
- **optimize-prompt-hook.md path broken in user-prompt-check.sh** — BUG-868: Use SCRIPT_DIR to resolve optimize-prompt-hook.md path
- **context-monitor.sh lock timeout leaves only 1s before hook timeout** — BUG-869: Reduce context-monitor lock timeout from 4s to 3s
- **issue-completion-log.sh shell vars injected into Python string literals** — BUG-870: Pass paths via env vars instead of shell variable interpolation

### Changed

- **check-duplicate-issue-id.sh config resolution** — ENH-871: Use `ll_resolve_config` for consistent config file fallback
- **UserPromptSubmit hook timeout increased** — ENH-872: Increase timeout from 3s to 5s to reduce false timeouts
- Update `init` and `configure` command reference docs

## [1.61.1] - 2026-03-23

### Fixed

- **`${CLAUDE_PLUGIN_ROOT}` not resolved in hooks installed to settings files** — BUG-863: Resolve variable before writing hooks to settings files in both `init` and `configure` entry points

### Changed

- **Simplified `ll-config.json`** — Remove unused fields and add state files to `.gitignore`

## [1.61.0] - 2026-03-23

### Added

- **`ll-issues next-action` subcommand** — ENH-860: New CLI subcommand that suggests the next recommended action for the highest-priority active issue
- **Duplicate detection config** — ENH-842: Implement `duplicate_detection` configuration for `IssuesConfig` to control duplicate issue detection behavior
- **Definition-of-done state in general-task loop** — Add a `done` state to the built-in general-task FSM loop for explicit completion tracking (672cdf99)
- **Hooks area in `/ll:configure`** — feat(configure): Add `hooks` management area with `show`, `install`, and `validate` sub-commands (2db66f7b)

### Fixed

- **Parallel config `timeout_per_issue` key silently ignored** — BUG-843: Fix `automation.py` reading wrong config key, causing per-issue timeouts to be ignored
- **Deprecated fields in CLI docs and issue-refinement loop** — Remove stale deprecated field references causing confusion (b49fa5a1)

### Changed

- **review-loop and create-loop prefer ll- CLI commands** — ENH-861: Update skill docs to recommend ll-cli commands and the Glob tool over raw bash patterns

## [1.60.0] - 2026-03-23

### Added

- **Session log auto-linking hook** — Automatically link session logs on issue completion via all code paths (ad2e346a)
- **go-no-go findings write-back** — Write significant findings back to issue file during go-no-go analysis (606ea658)
- **go-no-go NO-GO sub-classification** — Add NO-GO REASON sub-classification to verdict output for clearer feedback (f6a7fdf2)

### Fixed

- **Loop `--clear` screen flush** — Guard screen flush to depth-0 `state_enter` events only, preventing spurious clears (6fb5f96f)
- **Docs index link case** — Correct docs index link case in README (5d6bd5d8)

### Changed

- **Workflow sequence category index** — ENH-550: Cache UUID→category index for O(1) lookups, eliminating repeated O(C×E) scans per message
- **Boundary computation optimization** — ENH-551: Pre-compute entity sets in `_compute_boundaries` to reduce `extract_entities` calls from 2*(N-1) to N
- **GitHub sync performance** — Batch-fetch GitHub issue bodies in `diff_all` for faster sync (d9318e40)
- **Workflow sequence module** — Refactored into a package for improved organization (97870cfd)

### Documentation

- **Context-health-monitor loop** — Added to README with updated loop count (3b2428b1)
- **Session log auto-linking hook** — Documented new hook and associated CLI flags (5bde3449)
- **go-no-go verdict** — Documented NO-GO REASON sub-classification and findings write-back behavior (b0c5638d)

## [1.59.0] - 2026-03-21

### Added

- **Co-evolutionary examples mining loop** — New built-in loop for co-evolutionary examples mining in apo-textgrad (2e00b9dc)
- **MkDocs brand theme** — Apply brand theme to MkDocs documentation site (c3ea5d35)

### Fixed

- **Homepage logo scheme-awareness** — Add home-logo class for scheme-aware homepage logo coloring (a6f37a4a)
- **MkDocs logo color scheme** — Invert logo color per color scheme in MkDocs theme (9e1c3db0)

### Documentation

- **Co-evolutionary examples guide** — New guide for the co-evolutionary examples mining workflow (c574b83d)
- **Docs index cleanup** — Remove stale research, demo, and Claude Code reference sections from index (3259f914)
- **Logo width constraint** — Constrain docs logo width to 200px (838f245a)
- **Oracle calibration** — Tighten oracle calibration language and update confidence scores in FEAT-849 loop (8f6f6076)

## [1.58.0] - 2026-03-21

### Added

- **`ll-history` date range filters** — New `--since` and `--until` flags for `ll-history analyze` to scope analysis to a time window (dcf6bb8f)
- **`ll-issues sequence` type filter** — New `--type` flag to filter sequence output by issue type (b9e3cea6)

### Fixed

- **`INDEX.md` case-sensitivity** — Renamed `INDEX.md` to `index.md` to generate the root `index.html` correctly on case-sensitive filesystems (2d4b046, ad38703)

### Changed

- **Behavioral quality stack** — Replaced completion-as-quality assumption with explicit behavioral quality evaluation in FEAT-849 loop (c290863a)

### Documentation

- **APO loop descriptions** — Expanded APO loop descriptions to block scalars for improved readability (bd023823)
- **FSM evaluator docs** — Documented `diff_stall` and `mcp_result` evaluators, and removed unimplemented paradigm compilation docs (04f73bc8, 66bb0c6c)
- **FSM verdict terminology** — Updated all docs from `success`/`failure` verdict terminology to `yes`/`no` (7f4f505, 7aff407)
- **Docs site branding** — Added site logo/favicon, updated index branding, and removed stale nav entries (a2b2a61)

### Maintenance

- **Cloudflare Pages deployment** — Added `site/` build output to version control for Cloudflare Pages deployment (c8cb43f)

## [1.57.0] - 2026-03-21

### Added

- **`ll-loop history` filters** — New `--event`, `--state`, and `--since` filters for targeted history queries (FEAT-543)
- **`ll-messages` skill/examples flags** — New `--skill` filter and `--examples-format` flags for targeted message extraction (153706b)
- **`workflow-analyzer` default input** — `ll-workflows analyze` now defaults `--input` to the ll-messages pipeline output path (FEAT-559)
- **MkDocs Material docs site** — Full documentation site with Cloudflare Pages deployment config (FEAT-852)
- **`context-health-monitor` FSM loop** — New built-in loop for monitoring and responding to context pressure (3c1f07f)
- **Unified harness example loops** — Example loops merged with built-in loops directory for consistent discoverability (ENH-851)

### Fixed

- **`_find_test_file` path resolution** — Anchors test file search to project root instead of process CWD (ENH-828)
- **Parse errors now logged** — JSONL parse errors emit a warning instead of being silently swallowed (64fbadf)
- **Orphaned worktree branch derivation** — Uses `git rev-parse` for reliable branch name detection in cleanup (BUG-823)
- **`go-no-go` agents authentication** — Removed worktree isolation from adversarial agents to fix "Not logged in" failure (BUG-849)

### Changed

- **`_extract_messages_with_context` performance** — O(n²) inner scan replaced with O(n) single-pass using index map (ENH-827)

### Documentation

- **Loops guide**: harness examples table and `--tail` flag entry (bf4db8d)
- **CLI/COMMANDS reference**: `mcp-call` and `check-code` build mode docs (661cf4a)
- **Workflow analyzer**: updated `--input` flag documentation (6b1f583)

[1.67.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.1...v1.67.2
[1.67.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.0...v1.67.1
[1.67.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.66.1...v1.67.0
[1.66.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.66.0...v1.66.1
[1.66.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.65.0...v1.66.0
[1.65.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.64.1...v1.65.0
[1.64.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.64.0...v1.64.1
[1.64.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.63.0...v1.64.0
[1.63.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.62.0...v1.63.0
[1.62.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.61.1...v1.62.0
[1.61.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.61.0...v1.61.1
[1.61.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.60.0...v1.61.0
[1.60.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.59.0...v1.60.0
[1.59.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.58.0...v1.59.0
[1.58.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.57.0...v1.58.0
[1.57.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.56.0...v1.57.0

## [1.56.0] - 2026-03-20

### Fixed

- **`--verbose` flag for stream-json with `--print`** — Adds required `--verbose` flag so stream-json output works correctly when `--print` is active (25d4737)
- **Implementation Failure — FEAT-543** — Tracked and resolved failed FEAT-543 implementation attempt (BUG-848)

### Changed

- **Show LLM model name in ll-auto header** — Displays active model name in `ll-auto` run header using stream-json init event (ENH-838)
- **Harness FSM diagram shows all 5 evaluation phases** — LOOPS_GUIDE harness FSM diagram now correctly shows all 5 evaluation phases instead of 3 (ENH-847)

### Maintenance

- style: apply ruff formatting to subprocess_utils and test files (5697233)

[1.56.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.55.0...v1.56.0

## [1.55.0] - 2026-03-20

### Added

- **Sub-loop FSM diagram rendering** — Child FSM diagram renders alongside parent during sub-loop execution with `--show-diagrams` (46bfa69)
- **Sub-loop events forwarded to parent callback** — Sub-loop state transitions are forwarded to parent callback with depth annotation (632bc9a)
- **`ll-sync reopen` subcommand** — Reopen closed GitHub Issues from local issue files (e9df9cb)
- **`--status` flag for `ll-issues count`** — Count issues by status with the new `--status` filter flag (1449881)
- **`--date-field=updated` search** — Search issues by last-updated date using Session Log timestamps (cc192c2)
- **Deferred directory search in `ll-issues show`** — `ll-issues show` now searches deferred issues in addition to active ones (4ad1e72)

### Fixed

- **`StateManager.save` atomic write** — Prevents state file corruption on crash by using atomic write (1dfa79b)
- **`_current_process` tracking in FSMExecutor** — Adds `_current_process` tracking to `FSMExecutor._run_subprocess` for reliable subprocess management (f0a270f)
- **Missed handoff signals failure** — Missed continuation handoff now correctly signals failure with `returncode=1` (642a477)
- **Parent state highlighted during sub-loop execution** — Parent FSM diagram keeps current state highlighted while sub-loop runs (4f124df)
- **Configurable `remote_name` in `ll-parallel` and `ll-sprint`** — Hardcoded "origin" remote replaced with configurable `remote_name` option (f62e476)
- **Undefer issue commits undeferred section** — `undefer_issue` now correctly commits the undeferred section (3aa2738)
- **`ll-parallel` leak detection uses configured src/test dirs** — Leak detection now respects `src_dir`/`test_dir` from config instead of hardcoding paths (cf1aba2)
- **Comma-separated `--priority` in `ll-issues`** — `ll-issues list` and `ll-issues count` now accept comma-separated priority values (887dbeb)
- **Logger type fix in `load_loop`** — Corrects Logger type annotation in `load_loop` call (2934b4c)
- **YAML block sequence frontmatter parsing** — Parses YAML block sequences in issue frontmatter without spurious warnings (964c0fb)
- **Lint errors resolved** — Fix lint errors and reformat to pass ruff checks (548be51)

### Changed

- **Documentation: `ll-gitignore` CLI tool** — Added `ll-gitignore` to CLAUDE.md and README documentation (2e65c0e)
- **Documentation: sub-loop FSM diagram `--show-diagrams`** — Added guide for visualizing sub-loop execution (789d338)
- **Documentation: harness FSM diagram annotation** — Simplified annotation and fixed inaccuracies in harness FSM diagram guide (76663a9, 7271b44, 8a8dc63)
- **Documentation: CLI flags** — Added `--context-limit`, `--priority`, `--idle-timeout`, `--builtin` flags and new sort fields to CLI reference (69f2dba, f3d0dae)
- **Documentation: README ll-sync subcommands** — Added `diff`, `close`, `reopen` subcommands and bumped CLI tool count to 13 (63263bc, f4dc17a)

[1.55.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.54.0...v1.55.0

## [1.54.0] - 2026-03-19

### Added

- **Example FSM harness loops** — Built-in harness loop examples for automatic harnessing workflows (198abf8)
- **`/ll:go-no-go` skill** — Adversarial issue assessment that stress-tests implementation plans before coding begins (202d59f)
- **Auto-detect model from JSONL in context monitor** — Context monitor reads session JSONL to detect which model is active and select the correct context limit (0cfbc0c)

### Fixed

- **FSM tmp paths scoped to project CWD** — Temporary files created by FSM loops are now scoped to the project directory, preventing cross-project collisions (3dde2d0)
- **`general-task` plan file scoped to project dir** — Plan files are now project-scoped, avoiding conflicts between concurrent sessions (828086d)
- **`ll-continue-prompt.md` write permission** — Added `Write(ll-continue-prompt.md)` to canonical permissions so handoff no longer prompts for approval (BUG-811)
- **Context monitor default limit raised from 150K to 1M** — Prevents premature handoffs on modern models with large context windows (BUG-809)

### Changed

- **FSM diagram visual improvements** — State box titles are bold; transition line characters are color-coded by edge type; edge label colors are configurable via `ll-config.json` (1da47fb, 8fc6508, 49d574f)
- **`debug-loop-run` name-based analysis scoped to most recent execution** — Avoids false positives from older loop runs with the same name (7cf3373)
- **Context monitor uses JSONL transcript baseline** — More accurate token estimation via JSONL transcript rather than conversation estimates (8749815)
- **`on_handoff` set to `spawn` across all built-in loop configs** — Ensures consistent session handoff behavior (533cc27)

## [1.53.0] - 2026-03-18

### Added

- **`--priority` filter for `ll-auto`** — Filter issue processing by priority level; also fixes validation in `ll-parallel` (b2d242d)
- **FSM state box unicode composition badges** — State boxes now render unicode badges indicating state type, replacing text annotations (fca522b)

### Fixed

- **Route states missing unicode badge in FSM diagram** — `_get_state_badge()` now checks `state.route` so routing/branching states receive a distinct visual badge (BUG-806)
- **Numeric-only `--only` filter support** — `ll-auto`, `ll-parallel`, and `ll-sprint` now correctly accept numeric-only values for the `--only` filter (4d0942a)

### Changed

- **FSM state box badge moved to top border** — Badge character is now embedded in the box's top border line with one space of padding on each side, rather than appearing in the first content row (ENH-807)

### Documentation

- Fixed documentation accuracy issues across 5 guide files: LOOPS_GUIDE (10 fixes), AUTOMATIC_HARNESSING_GUIDE (10 fixes), SESSION_HANDOFF (8 fixes), WORKFLOW_ANALYSIS_GUIDE (9 fixes), SPRINT_GUIDE (5 fixes) (9ab98f1, 1026be3, f6a32a0, 159a2e2, d739fa2)

## [1.52.0] - 2026-03-17

### Added

- **Hierarchical sub-loop states for composable FSM loops** — FSM loops can now delegate to specialized sub-loops as named states (930fd7e)
- **Evaluation-quality FSM loop** — Built-in loop for multi-dimensional health checks across quality dimensions (d6dc7e4)
- **`plan` state in `general-task` loop** — Decomposes tasks into steps before execution for improved planning (fc42348)
- **`testable` field in `IssueInfo` dataclass** — Tracks whether an issue can be automatically validated (ENH-800)
- **Auto-detect `testable: false` for doc-only issues** — Pipeline and `manage-issue` automatically mark documentation-only issues as non-testable (ENH-802)

### Fixed

- **LLM evaluator uses `--json-schema` flag** — Prevents LLM preamble from corrupting structured output in evaluators (BUG-794)
- **`on_error` handlers in issue-refinement loop prompt states** — Prevents silent failures when prompt states encounter errors (BUG-773)
- **RL coding agent stall detection and live LLM judge** — More accurate stall detection with live LLM judging prevents false stalls (ENH-793)

### Changed

- **`debug-loop-run` distinguishes intentional cycling from stuck retries** — Retry flood detection no longer conflates on_no routing with true stuck retries (ENH-775)
- **`create-loop` wizard uses structural patterns** — Templates and questions refactored to guide users toward pattern-based loop design (ENH-756)
- **`parse_frontmatter` warns on unsupported YAML syntax** — Surfaces warnings when YAML lists or colon-containing values are silently dropped (ENH-693)
- **`rl-coding-agent` reads `test_cmd`/`lint_cmd` from `ll-config.json`** — Agent uses project-configured commands instead of defaults (ENH-793)
- **`issue-history` uses `statistics.linear_regression`** — Replaced manual OLS implementation with Python standard library (5aad93f)
- **BFS edge case coverage for coupling cluster analysis** — Added tests for `_build_coupling_clusters` edge cases (ENH-697)

### Documentation

- **Sub-loop composition guide** — Architecture and guides updated to cover hierarchical sub-loop composition patterns (cee79f5)
- **Claude Code structured outputs guide** — New guide covering structured output generation with `--json-schema` (b1bf58f)
- **Docs accuracy fixes** — Corrected `diff_stall` verdicts, `capture_template` config, and loops catalog entries (9e2840b)

## [1.51.0] - 2026-03-16

### Added

- **Enhance `ll-sprint show` CLI Output Styling** — Colorized output and improved visual formatting for sprint status (ENH-745)
- **`plan_call` Action Type for FSM States** — New FSM action type that invokes plan mode during state execution (ENH-778)
- **`rl-coding-agent` Policy+RLHF composite loop** — New built-in loop combining policy gradient and RLHF for coding agent workflows (a124f8e)
- **`ll-gitignore` CLI command** — New command to expose the built-in gitignore suggestion library (d24aaf2)
- **`--sort`/`--asc`/`--desc` flags for `ll-issues list`** — Sort issue list output by any field in ascending or descending order (e8dcf75)
- **`--limit`/`-n` flag for `ll-issues list`** — Cap list output to N issues (3cb3013)
- **Confidence-check Phase 4.5 findings write-back** — Confidence check now persists Phase 4.5 evaluation findings back to issue files (64e650d)
- **Error states and `on_handoff` pause in RL loop configs** — RL loops handle error states and support pausing on handoff events (a04e5b3)
- **`EntityCluster.span` and `inferred_workflow` in workflow-analyzer** — Enriched entity cluster data with temporal span and inferred workflow context (8bfef3e)

### Changed

- **Init validates hook script dependencies and version alignment** — Step 9.5 hook dependency validation added to the init wizard (ENH-705)
- **Preserve `--only` argument order in `ll-auto`** — Issue processing order now matches the order arguments were provided (2e16ae0)
- **Type misclassification detection in `normalize-issues`** — Detects and flags issues filed under an incorrect type (1ca7753)

### Fixed

- **`debug-loop-run` no longer treats exit_code=1 as failure when `on_no` is defined** — Prevents false failure signals when a no-branch is configured (d695b62)
- **Loop evaluate classifier splits `NEEDS_FORMAT` from `NEEDS_VERIFY`** — Cleaner evaluation state distinction avoids conflating format and verify signals (483ab8d)
- **Session log skips fake `## Session Log` headings in code blocks** — Uses last-match strategy to avoid false positives from headings inside fenced code (d6386c8)
- **`ll-issues list` display text normalization** — Fixed inconsistent output text in the list subcommand (9fdfdff)

## [1.50.0] - 2026-03-16

### Added

- **Loop-level `default_timeout` for FSM executor** — Per-state action timeout fallback eliminates hardcoded timeouts and per-state annotations (ENH-777)
- **APO built-in loops** — OPRO, beam search, and TextGrad loops for automatic prompt optimization (1694797, 1dc689d, 5e471a8, a87703f)
- **RL built-in loop types** — `rl-bandit`, `rl-rlhf`, and `rl-policy` reinforcement-learning loop variants (affc355)
- **TDD issue implementation loop** — Built-in loop for test-driven development workflows (0dcb159)
- **`--handoff-threshold` flag** — Added to `ll-loop run` and `resume` for session handoff control (32b9360)
- **`--status` flag for `ll-issues list`** — Filter issues by status in the list subcommand (a476fb3)
- **`allowed-tools` area in configure skill and init wizard** — Configure allowed tools interactively (748d398)

### Fixed

- **Friendly error for missing context variables** — Loop executor now surfaces clear messages when context vars are absent (5c6e8d6)
- **APO convergence check on_error routing** — Route to `generate_variants` instead of failing on convergence errors (e3bc2ab)
- **`general-task` loop on_error routing** — Added on_error routing and failure terminal to prevent silent hangs (31336cd)

### Changed

- **Dynamic column elision in refine-status** — Narrow terminal widths now gracefully elide lower-priority columns (814f12b)

## [1.49.0] - 2026-03-15

### Changed

- **Add route_create guard to sprint-build-and-validate** — Prevents invalid route creation in sprint build loops (f5dfd76)
- **Remove one-off workflow loops from built-in catalog** — Cleans up catalog of ad-hoc loops not intended for general use (b8dad90)

### Fixed

- **FSM on_blocked shorthand field and routing branch** — Added `on_blocked` shorthand support with proper routing branch handling (a428d91)
- **LLM evaluation timeout raised to 1800s** — Default timeout increased from 30s to prevent premature evaluation failures (9fda9ca)
- **Context variable interpolation in llm_structured evaluate prompt** — Properly interpolates context vars in evaluation prompts (f565209)

### Documentation

- Fixed three inaccuracies in harnessing guide (bae4fdf)

## [1.48.0] - 2026-03-15

### Changed

- **Parameterized confidence thresholds in sprint-build-and-validate** — Added `readiness_threshold` and `outcome_threshold` to loop context with defaults (85/70), replaced 3 hardcoded occurrences, with runtime override support (8118b99)

### Fixed

- **FSM diagram label truncation** — Corrected back_edge_margin calculation and non-adjacent edge label placement (714e862)

### Documentation

- Marked all 18 skills with ^ suffix in COMMANDS.md Quick Reference to distinguish from commands (3e8f7cd)
- Refined ENH-753 and ENH-757 with complete codebase reference maps and confidence scoring
- Corrected skill count from 17 to 18 in CLAUDE.md

## [1.47.0] - 2026-03-15

### Added

- **--handoff-threshold CLI override** — Added to ll-auto, ll-parallel, ll-sprint for per-run session handoff threshold configuration (8475824)
- **--type filter for impact-effort** — New `--type` flag on `ll-issues impact-effort` to filter by issue type (b6dd14e)
- **--json output for ll-loop** — `ll-loop status` and `ll-loop show` now support `--json` for machine-readable output (968ce1c)
- **--json output for ll-issues** — `ll-issues show` and `ll-issues sequence` now support `--json` for machine-readable output (740bafb)

### Documentation

- Fixed default_max_workers value in SPRINT_GUIDE (ed3bb0b)
- Fixed two inaccuracies found during reference docs audit (dca73b6)
- Fixed stale skill counts and documented missing ll-issues subcommands (28d969a)
- Documented --handoff-threshold flag in CLI reference and SESSION_HANDOFF guide (c12b368)
- Added check_skill evaluation phase for skill-as-judge verification (fea5775)
- Documented MCP tool gates as optional evaluation phase (8933eb6)
- Documented --json and --type flags added in FEAT-701/702/703 (2305d6b)

## [1.46.0] - 2026-03-15

### Added

- **Update-docs skill** — Automated documentation maintenance triggered by code changes (FEAT-751)
- **MCP tool action type for FSM Loops** — New `action_type: mcp_tool` with MCP result evaluator support (FEAT-729)
- **ll-loop positional string input** — `ll-loop run` now accepts a positional string input argument (FEAT-725)
- Automatic Harnessing Guide for FSM loops (9ff9ae6)

### Fixed

- **Loop `/tmp` scratch files use global names** — Fixed cross-project conflicts from non-unique scratch file names (BUG-744)
- **format-issue --auto `formatted` flag** — Fixed flag never being set, causing infinite loops in issue-refinement (BUG-743)

### Changed

- **Verbose loop history LLM call details** — Loop history verbose mode now shows full LLM call details (ENH-740)
- **Stall detection via diff comparison** — FSM loops now detect stalls by comparing state diffs (ENH-714)
- **Deferred `detect_regression_or_duplicate`** — Lazy evaluation eliminates eager calls for displaced matches (ENH-691)

## [1.45.0] - 2026-03-14

### Added

- **4-section anchored schema for session handoff** — `handoff` skill now uses a structured 4-section schema for richer session continuity (ecaff979)
- **Session linking for loop history** — Loop history now captures session IDs for prompt states, enabling cross-session traceability (c1579dc)
- **Per-state retry limits for FSM** — FSM states support `max_retries` and `on_retry_exhausted` for fine-grained retry control (4f68e5a)
- **`ll-issues search` subcommand** — New search subcommand with filters and sorting for issue discovery (221c059)

### Fixed

- **FSM yes/no schema** — Updated schema and validation to use `on_yes`/`on_no` fields replacing `on_success`/`on_failure` (357073a)
- **Loop CLI display** — Updated CLI display to reflect yes/no verdict rename (dd6b854)
- **Loop config files** — Updated built-in loop configs for yes/no verdict and on_yes/on_no rename (169e588)
- **Quality checks** — Resolved lint, format, and type check failures (70ce0f4)

### Changed

- **FSM verdict naming** — Renamed `success`/`failure` verdicts to `yes`/`no` and `on_success`/`on_failure` to `on_yes`/`on_no` for clearer semantics (a18e79e, 45c9956)
- **`review-loop` LLM state detection** — Detects replaceable LLM prompt states for optimization recommendations (63d0b19)
- **Config module refactor** — Split `config.py` into a `config/` subpackage for better organization (cde1bbe)
- **Issue history deduplication** — Extracted `get_issue_content()` helper eliminating 10 code duplicates (b1be301)
- **Issue discovery performance** — Deferred `detect_regression_or_duplicate` to after loop in Passes 2 and 3 (26b8d06)

## [1.44.0] - 2026-03-14

### Added

- **`ll-issues append-log` subcommand** — New CLI subcommand for appending session log entries; five commands (`refine-issue`, `verify-issues`, `scan-codebase`, `tradeoff-review-issues`, `ready-issue`) now use the CLI instead of direct Bash calls (ENH-747)

### Changed

- **Sprint planner worktree safety** — Separated `overlaps_with()` and `contends_with()` in `FileHints`; `ll-parallel` now uses the more conservative `contends_with()` to prevent false positive file-overlap serialization (ENH-746)

## [1.43.0] - 2026-03-14

### Added

- **Suggest FSM loop configs from commands, prompts, and workflows** — `loop-suggester --from-commands` mode analyzes the command and skill catalog to propose ready-to-use FSM loop configurations (FEAT-716)
- **Loop run history archiving** — Loop runs are now archived to `.loops/.history/` before clearing, enabling persistent history retrieval across sessions (FEAT-733)
- **Harness loop type for `create-loop`** — New `Harness` loop type wraps existing skills and prompts into FSM loops without custom state logic (469a98f)
- **plugin-health-check convergence FSM loop** — Extended the `plugin-health-check` built-in loop into a full convergence FSM loop with self-healing transitions (bc2f910)
- **`description` field for FSMLoop schema** — FSM loop definitions now support an optional human-readable description field (c7ed2b8)
- **Workflow analyzer cross-references** — Workflow analyzer cross-references workflows to entity clusters and populates `handoff_points` for richer handoff context (27f482d)
- **backlog-flow-optimizer built-in loop** — New `backlog-flow-optimizer` loop replaces `issue-throughput-monitor` with improved flow-based optimization (81500eb)

### Fixed

- **Loop scratch files use project-scoped directory** — Scratch files now write to `.loops/tmp/` instead of system `/tmp/`, preventing cross-project collisions (9ddd8d1)
- **`format-issue` session log in auto mode** — Fixed programmatic session log write in auto mode (0b7fccb)
- **FSM diagram back-edge connector rendering** — Fixed rendering glitches in back-edge connectors (c5704ca)
- **Built-in loop configs audit** — Removed `secret-scan` loop and updated semantics across multiple built-in loop configs (10f9873, 09562b7)
- **`docs-sync` loop `on_error` routing** — Added missing `on_error` routing to `route_results` state in the docs-sync loop (35d39c4)
- **Issue refinement budget exhaustion** — Prevented budget exhaustion on stubborn issues in the `issue-refinement` loop (9a0abf3)

### Changed

- **Stall detection via diff comparison** — New `diff_stall` evaluator detects FSM iteration stalls by comparing successive diffs (ENH-714)
- **`ll-loop list` visual polish** — Colorized output matches `ll-issues` quality with priority and status indicators (ENH-715)
- **`ll-loop history --verbose` LLM details** — Verbose history output now includes LLM call counts and token details per iteration (8a881e6)
- **`create-sprint` surfaces refinement status** — Sprint creation now shows issue refinement status to help curate sprint candidates (1ddae71)
- **`ll-loop init` wizard simplified** — Removed product analysis and auto-timeout prompts from the interactive initialization wizard (6a333fb)
- **FSM BFS optimization** — Replaced `list.pop(0)` with `deque.popleft()` for O(1) BFS traversal (c452331)

## [1.42.0] - 2026-03-13

### Added

- **Parallel merge coordinator** — New merge coordinator for `ll-parallel` enabling concurrent issue processing with safe state transitions (76cb72d)

### Fixed

- **FSM layout: same-layer connectors occluding intermediate state boxes** — Prevented connectors on the same layer from drawing over intermediate state boxes (6057136)
- **`IssueManager`: too-narrow except clause in `gather_all_issue_ids`** — Broadened except to catch `ImportError`, `OSError`, and all other exceptions to prevent `IssueManager` construction crashes (BUG-690, 548c386)
- **FSM: SIGKILL'd prompt actions route to next state instead of shutdown** — Route prompt actions terminated by SIGKILL to the shutdown state (6c33e5f)
- **Merge coordinator: unprotected `_current_issue_id` reads and writes** — Added locking around `_current_issue_id` access for thread safety (dc5470b)
- **Orchestrator: unprotected concurrent state mutations** — Added `_state_lock` to protect concurrent state mutations in the orchestrator (76b0a52)
- **WorkerPool: unprotected `_active_workers` reads and writes** — Added locking to `_active_workers` for thread-safe worker pool management (1bbdd99)
- **Merge coordinator: `_current_issue_id` not cleared on error exit** — Wrapped `_process_merge` in outer try/finally to guarantee `_current_issue_id` is cleared (e1652dd)
- **Subprocess: ambiguous returncode check** — Replaced `returncode or 0` with explicit `None` check to correctly handle zero exit codes (fc0b331)

## [1.41.0] - 2026-03-13

### Added

- **`--clear` flag for `ll-loop run` and `resume`** — Emits ANSI clear-screen before each iteration; combine with `--show-diagrams` for a live in-place FSM dashboard. Suppressed when stdout is not a tty (ENH-718)
- **`--delay <SECONDS>` flag for `ll-loop run` and `resume`** — Inserts an interruptible pause between FSM iterations; useful for recording terminal sessions. Overrides `backoff:` from the loop YAML. (ENH-735)
- **`ll-loop analyze` skill** — Synthesizes actionable issues from loop execution history; captures patterns across iterations into BUG/ENH/FEAT issue files (FEAT-719)
- **20 built-in FSM loop definitions** — Common dev workflow loops bundled with `ll-loop` for immediate use (c1b18fe)

### Fixed

- **FSM diagram disconnected box-drawing junction characters** — Upgraded box-drawing corners to junctions on character collision (BUG-710)
- **`issue-refinement` loop: three logic defects** — Fixed counter reset, LLM-managed iteration, and LLM ceiling-acceptance defects (BUG-720)
- **`issue-refinement` loop: LLM parses issue ID instead of shell** — Replaced LLM-driven ID extraction with deterministic shell `parse_id` state (BUG-721)
- **`--show-diagrams` suppressed by `--quiet`** — Allow `--show-diagrams` to work alongside `--quiet` (BUG-727)
- **`--json` flag missing from `ll-loop history` and `ll-loop list --running`** — Added `--json` support to both subcommands (b27bd30)
- **FSM bugs across built-in loop configs** — Audited and fixed 18+ bugs across 24 built-in FSM loops plus 6 simplifications (5867dbd, 1708235, d66c3ac)
- **FSM layout: multi-branch horizontal connector gaps** — Connected multi-branch horizontal connectors across source box gaps and skip-layer edge horizontals (f8ba63c, 6ebff0e)
- **`format-issue` missing confidence gate** — Added confidence gate to interactive mode questions (8c8c3cd)

## [1.40.0] - 2026-03-12

### Added

- **`--check` flag for issue prep skills** - Added check-only evaluation mode with exit code routing for FSM loop evaluators across 8 skills (ENH-668)
- **`--auto` flag for issue prep skills** - Non-interactive mode for verify-issues, map-dependencies, and issue-size-review with conservative defaults (ENH-669)
- **`count` sub-command for `ll-issues`** - Lightweight issue volume queries with `--type`, `--priority` filters and `--json` output (ENH-677)
- **`issue-discovery-triage` builtin loop** - New FSM loop for automated issue discovery and triage (2a515c6)

### Fixed

- **FSM diagram branch edges to terminal states not rendered** - Added right-margin forward-skip edge renderer for edges spanning 2+ layers (BUG-678)
- **FSM diagram main-path cycle edges not rendered** - Extended edge reclassification to scan forward_edge_labels for backward-pointing main-path edges (BUG-679)
- **`init --interactive` does not create .issues directory structure** - Refactored interactive init to auto-detect and create issue directories (BUG-656)
- **Dependency mapper inflated default scores** - Applied overlap guards and fixed scoring in dependency mapper (30a0453)
- **Refine-status table too wide for narrow terminals** - Reduced column widths saving ~21 chars per row (ENH-676)
- **`ll-loop show` States section visibility** - Gated States section behind `--verbose` flag (0f87a97)
- **Test: add issue-discovery-triage to expected builtin loops set** (00b639c)

### Changed

- **Optimize FSM diagram edge classification** - Replaced O(n) `bfs_order.index()` calls with O(1) dict lookup (ENH-542)
- **Add `/ll:review-loop` to COMMANDS.md reference** (ENH-680)
- **Documentation updates** - Fixed stale counts, paths, and missing entries in ARCHITECTURE and CONTRIBUTING (a57e67c)

## [1.39.0] - 2026-03-11

### Added

- **Adaptive layout engine for FSM diagrams** - New layout engine that automatically adjusts FSM diagram geometry based on graph structure (5f2df71)
- **`--json` flag for `ll-issues`, `ll-loop`, and `ll-sprint` list commands** - Machine-readable JSON output for all list subcommands (7f88574, 8477dda)

### Fixed

- **FSM back-edge rendering: corner characters and arrow direction** - Corrected corner chars and arrow direction for back-edge pipes; consolidated three successive fix iterations (8c35e70, 48703d5, 3f33e0b)

### Changed

- **Remove deprecated paradigm compilation system** - Removed `compile_paradigm` from FSM engine runtime load path and deleted deprecated paradigm compilation code (09c83ab, d0692bd)
- **Remove 4 Paradigms concept from docs** - Updated all documentation to reflect FSM YAML as the canonical loop format (c6021ef)

## [1.38.0] - 2026-03-09

### Added

- **New `/ll:review-loop` FSM Loop Quality Auditor** - Comprehensive skill for auditing FSM loop configurations, analyzing logic, and suggesting improvements (FEAT-660)
- **Issue-refinement-git FSM loop** - Automated issue refinement workflow using git integration (88baf5d)

### Fixed

- **FSM Diagram Off-Path Arrows and Back-Edges Broken** - Fixed rendering of off-path arrows and back-edges in FSM diagrams for multi-state chains (BUG-664)
- fix(review-loop): rename FA-N checks to QC-8/QC-13 to prevent early termination (e99931c)

### Changed

- **Add Unknown-Key Detection to `load_and_validate()`** - Improved FSM validation with detection of unknown keys in loop configurations (ENH-661)
- **review-loop FSM Logic Analysis Phase** - Enhanced review-loop with comprehensive FSM logic analysis and evaluation (ENH-662)
- **Extract Shared `_process_alive` to Eliminate Duplication** - Refactored concurrency module to eliminate code duplication between `concurrency.py` and `lifecycle.py` (ENH-537)
- **Pre-resolve Scope Paths to Eliminate O(n×m) stat Calls** - Performance optimization for `_scopes_overlap` path resolution (ENH-629)
- **FSM Test Coverage for `maintain` Mode and `direction="maximize"`** - Added missing executor-level tests (ENH-538, ENH-631)

## [1.37.3] - 2026-03-09

### Fixed

- **Correct FSM diagram for linear off-path chains** - Fixed FSM diagram rendering where linear off-path chains were not correctly represented in the state machine visualization (BUG-658)

## [1.37.2] - 2026-03-08

### Fixed

- **`ll-loop history` `--tail` counts suppressed `action_output` events, hiding earlier iterations** - Filters `action_output` events before applying `--tail` so iteration history is not crowded out by verbose shell output (BUG-657)

## [1.37.1] - 2026-03-08

### Fixed

- fix(issues): refine BUG-656 with root cause, solution, and confidence scores (7975326)

### Changed

- improve(init): remove 11 interactive prompts and use sensible defaults (eb70156)

### Documentation

- docs: update install instructions to reference PyPI package (58f27dc)

## [1.37.0] - 2026-03-08

### Added

- **TDD Mode in Round 3a advanced features** - Moved TDD Mode selection to Round 3a advanced features during `ll-init` setup (feat(init): 2045a2a)

### Fixed

- **Off-Path State Highlighting Missing in FSM Diagram** - Fixed `ll-loop run --show-diagrams` to properly highlight off-path states with green borders and bold text when they become the active state (BUG-655)
- fix(config): replace hardcoded issue paths with config-driven resolution (ed5b3ad)
- fix(schema): align worktree_copy_files default with code (470ef08)
- fix(config): add test_dir field to ProjectConfig (ce3fc59)
- fix(schema): correct default_max_workers default from 4 to 2 (e783ae7)

### Changed

- docs(schema): add three undocumented config fields to config-schema.json (aadf455)
- docs(issues): clarify skills in README and update FEAT-638 verification logs (93411ce)

## [1.36.1] - 2026-03-07

### Fixed

- **ll-issues refine-status ID column truncates 4-digit FEAT IDs** - Replaced hardcoded `_ID_WIDTH = 8` with a dynamic column width computed from the longest issue ID in the dataset (BUG-647)

### Changed

- **API.md missing documentation sections** - Added documentation for `work_verification`, `session_log`, config classes (`SprintsConfig`, `LoopsConfig`, `GitHubSyncConfig`, etc.), FSM submodules (`handoff_handler`, `concurrency`, `signal_detector`), parallel types, and CLI entry points (ENH-646)

[1.37.3]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.2...v1.37.3
[1.37.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.1...v1.37.2
[1.37.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.0...v1.37.1
[1.37.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.36.1...v1.37.0
[1.36.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.36.0...v1.36.1

## [1.36.0] - 2026-03-07

### Added

- feat(loop): add `--show-diagrams` flag to `ll-loop run` and `resume` — display FSM box diagram with active state highlighted during verbose run (cbae36b, 8d6585d)
- feat(loop): add `--context KEY=VALUE` CLI override for `run` and `resume` (f307e13)
- feat(loop): add `--exit-code` to `ll-loop test` for slash-command states (952e653)
- feat(fsm): add numeric range checks to `validate_fsm` (db4d8e0)
- feat(fsm): add `on_stall` override to convergence paradigm compiler (7ad4673)
- feat(compilers): add `on_partial_target` field to all paradigm compilers (c101325)
- feat(simulate): add all-error scenario for non-interactive error-verdict testing (b8c060a)

### Fixed

- fix(evaluators): raise `ValueError` when `output_numeric` or convergence target is `None` (e17c3d3)
- fix(evaluators): guard `output_numeric` target against non-numeric strings (c2860a8)
- fix(executor): drain stderr in background thread to prevent pipe deadlock (d961aab)
- fix(fsm): remove `on_error="fix"` from `compile_goal` evaluate state (ea6d525)
- fix(fsm): clear `_pending_error` on resume alongside `_pending_handoff` (37700a7)
- fix(loop): write PID file for foreground runs so `cmd_stop` sends SIGTERM (df233e6)
- fix(loop): forward `--verbose` flag to background process (f6edb97)
- fix(persistence): map timeout termination to `timed_out` status (7096c9c)
- fix(validation): add `on_partial` to `_validate_state_routing` shorthand check (763823a)
- fix(handoff): anchor continuation prompt path to project root (9c8232a)
- fix(issue_parser): add session log check to `is_formatted` (28622fe)
- fix(docs): correct API.md signatures, data class schemas, and goals_parser reference (c242966, 955c370, 31f8165)
- fix(docs): correct `$schema` relative path in CONFIGURATION.md example (e3d018a)

### Changed

- refactor(fsm): extract `_is_prompt_action` helper in `FSMExecutor` (cd0b742)

[1.36.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.35.0...v1.36.0

## [1.35.0] - 2026-03-06

### Added

- feat(ll-loop): add paradigm/description display and --status filter to list (9549f7a)
- feat(workflows): add --format json output option to ll-workflows analyze (d6f7c10)
- feat(workflows): add per-stage verbose progress to analyze_workflows (1e49376)
- feat(workflows): expose overlap_threshold and boundary_threshold via CLI and API (4a7e87d, 63a7a41)
- feat(cli): add --idle-timeout flag to ll-auto and ll-parallel (58d9889)
- feat(sprint): add --only flag to ll-sprint run (7f251e6)
- feat(ll-loop): add --state flag to ll-loop test (5f67587)
- feat(ll-loop): add --background flag to resume command (8c5dc4d)

### Fixed

- fix(file-hints): require colon delimiter in scope/component pattern (9de08ed)
- fix(sprint): route BLOCKED verdict to skipped_blocked_issues, not failed (e789a46)
- fix(sprint): prevent stale orchestrator state loading on fresh wave run (23cc8a2)
- fix(ready-issue): add BLOCKED verdict for unresolved blocking dependencies (b295b2e)

[1.35.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.34.0...v1.35.0

## [1.34.0] - 2026-03-06

### Added

- **Fix `ll-loop show` box truncation and add diagram centering** (ENH-589)
- **Colorize ll-issues show card output** (ENH-593)
- **Colorize ll-loop run output** (ENH-595)
- **Colorize ll-issues refine-status output** (ENH-596)
- feat(doc-scraper): add BoundaryML docs scraper and scraped output (5dcbb2c)
- feat(cli): add subcommand aliases to ll-issues, ll-loop, and ll-sprint (e5d428e)

### Fixed

- fix(persistence): remove redundant route-event state save (f284a1c)
- fix(loop): map terminated_by to distinct exit codes (83de39f)
- fix(loop): remove PID file after SIGTERM/SIGKILL stop (7f9fead)
- fix(persistence): warn on corrupted state file instead of silently returning None (ebf96f5)
- fix(loop): use FSMLoop.to_dict() in cmd_compile to preserve all fields (31140c8)
- fix(loop): extract signal handler to _helpers and register in cmd_resume (32e2f1c)
- fix(cli): normalize args.command to canonical name for subcommand aliases (89078d8)
- fix(workflow-analyzer): handle malformed JSONL lines in _load_messages (9090819)

## [1.33.1] - 2026-03-05

### Fixed

- **FSM diagram off-path states side-by-side** - Off-path FSM states now render side-by-side instead of stacking vertically (BUG-598)
- **issue-refinement loop infinite cycle** - Resolve 5 infinite cycle bugs caused by fmt/priority issues in the loop configuration (BUG-599)

### Changed

- **fix-quality-and-tests loop** - Run tests via shell for improved test execution in the quality gate loop (ea06153)
- **issue-refinement loop** - Remove map-dependencies step and tests-until-passing loop from issue-refinement configuration (b7ab12e, ba52386)

## [1.33.0] - 2026-03-05

### Added

- **fix-quality-and-tests FSM loop** - Sequential quality gate loop: lint/format/types must pass before tests are checked; auto-fixes violations and loops back after fixing test failures to catch regressions (b6eb5a9)

### Fixed

- **`ll-loop stop` process termination** - Kill running subprocess on SIGTERM and escalate to SIGKILL; `ll-loop stop` now terminates active processes immediately (BUG-592)
- **ISSUE_TEMPLATE.md section count** - Correct internally inconsistent section count claim in issue template documentation (BUG-597)

### Changed

- **`ll-loop history` colored output** - Structured, colored output for `ll-loop history` command (ENH-566)
- **`ll-issues show` card colorization** - Colorize `ll-issues show` card output for improved readability (ENH-593)
- **`ll-issues impact-effort` color and layout** - ANSI color, dynamic layout, and summary count for `ll-issues impact-effort` (ENH-594)
- **`ll-loop run` colored output** - Colorize `ll-loop run` output for improved readability (ENH-595)
- **`ll-issues refine-status` colorization** - Colorize `ll-issues refine-status` output (ENH-596)
- **Built-in loops cleanup** - Remove built-in loops except issue-refinement; simplify loops directory (84e26ad)

## [1.32.1] - 2026-03-05

### Changed

- **`ll-loop show` box rendering** - Fix box truncation and add diagram centering in `ll-loop show` output (ENH-589)
- **Issue-refinement loop** - Audit and fix issue-refinement loop configuration, move to canonical `loops/` directory (ENH-590)
- **`ll-issues` output styling** - Fix output styling consistency and colorize `ll-issues` CLI commands (ENH-591)
- **CLI output styling reference** - Add reference documentation for CLI output styling (284a2d7)

## [1.32.0] - 2026-03-05

### Added

- **FSM live output streaming** - Stream live output from prompt and shell states in real-time (feat(fsm): 9b785ae)

### Fixed

- **FSM JSON schema** - Embed JSON schema in prompt instead of using --json-schema flag (fix(fsm): a12a570)
- **Executor session flag** - Replace --verbose with --no-session-persistence in claude CLI call (fix(executor): 65939d0)
- **Code quality** - Fix lint errors and reformat codebase (fix(code-quality): 90bb731)

### Changed

- **Refine-status columns configurable** - Make refine-status table columns configurable via ll-config.json (improve(issues): 3df3707)
- **ll-loop verbose polish** - Visual polish for ll-loop show --verbose output (improve(cli): a13e68d)

## [1.31.0] - 2026-03-04

### Added

- **FSM evaluate.source field** - FSMExecutor._evaluate() now supports evaluate.source field for dynamic source configuration (feat(fsm): 63f8fd1)
- **FSM multiline fix auto-detect** - Auto-detect multiline fix tool as prompt in compile_goal (feat(fsm): ad2b8d9)
- **CLI color output configurable** - CLI color output now configurable via ll-config.json (feat(cli): 2d0310c)
- **Responsive terminal output** - Responsive terminal output using stdlib utilities (feat(cli): 6b08081)
- **Sprint pre-validation** - `ll-sprint run` pre-validates issues are still active before wave dispatch (ENH-581)
- **ll-loop validation warnings** - Surface validation warnings in cmd_validate output (feat(ll-loop): 3b2e206)
- **refine-status template detection** - Detect issue formatting from template config instead of session log (feat(refine-status): 7a1398d)

### Fixed

- **Sprint contention sub-waves** - Route contention sub-waves through sequential in-place execution (fix(sprint): b30a3aa)
- **Parallel orphan cleanup** - Guard orphan cleanup against concurrent session worktrees (fix(parallel): 7e86ba3)
- **Workflow-analyzer entities_matched** - Compute entities_matched before all_entities mutation (fix(workflow-analyzer): de0d0a9)
- **FSM prev_result capture** - Capture prev_result in next-routed state action (fix(fsm): 6d00499)
- **Workflow-analyzer evidence list** - Preserve full evidence list in SessionLink (fix(workflow-analyzer): ccbcfce)
- **ll-loop stuck in evaluate** - Fix ll-loop stuck in evaluate state and improve timeout output clarity (fix(fsm): a2a2e08)
- **Parallel committed leaks** - Detect and recover committed leaks to main repo (fix(parallel): 56b62ba)
- **Hooks worktree cleanup** - Skip worktree cleanup when session runs inside a worktree (fix(hooks): 12ea54c)
- **FSM --no-llm flag** - Honor --no-llm flag in FSMExecutor._evaluate() (fix(fsm): 2f8ded0)

[1.33.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.32.1...v1.33.0
[1.32.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.32.0...v1.32.1
[1.32.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.31.0...v1.32.0
[1.31.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.30.0...v1.31.0

## [1.30.0] - 2026-03-04

### Added

- **Goal paradigm per-tool action_type** - Goal paradigm YAML spec supports per-tool action_type configuration (FEAT-572)

### Fixed

- **Mixed timestamp crashes** - Handle mixed naive/aware timestamps in workflow-analyzer (BUG-546)
- **ll-loop prompt output** - Improve output for prompt actions (BUG-564)
- **ll-loop shell output truncated** - Show last 8 lines of shell command output on handoff (BUG-566)
- **on_partial transition dropped** - Add on_partial as first-class FSM transition (BUG-567)
- **File hints scope** - Scope overlap detection to write-target sections only (BUG-571)
- **FSM diagram multi-label edges** - Join all multi-label edges in FSM diagram (BUG-574)

### Changed

- **ll-loop show verbose** - Improved verbose output quality with action-type-aware truncation, on_handoff display, evaluate prompt and state-level fields (ENH-568, ENH-569, ENH-570, ENH-573, ENH-575)
- **Section JSON alignment** - Align bug/enh section JSON with format-issue templates v2.0 (ENH-576)
- **Sprint stability** - Reduce default_max_workers to 2 for sprint stability (7921151)
- **Template alignment** - Align section JSONs and config with templates.md v2.0 (122167f)

[1.30.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.29.0...v1.30.0

## [1.29.0] - 2026-03-04

### Added

- **FSM executor improvements** - Enhanced event system, CLI display, interruptible sleep with backoff enforcement (40f1741, e83879c)
- **LLM evaluator migration** - Migrate FSM LLM evaluator from Anthropic SDK to Claude CLI (da750eb)
- **ll-issues refine-status subcommand** - New `ll-issues refine-status` with dynamic column table: Key, Norm, source/tradeoff/map columns, and refine-run counts (ENH-560, ENH-561)
- **Dual confidence thresholds** - Configurable dual confidence thresholds in confidence-check config (ENH-562)
- **BM25 relevance scoring** - Hybrid BM25 relevance scoring in `ll-history export` (2ae2133)
- **Session Log audit trail** - Session log steps added to issue-modifying commands and skills (ENH-524)

### Fixed

- **Loop resume elapsed time** - Restore elapsed time correctly across loop resume (BUG-527)
- **Concurrency TOCTOU race** - Eliminate TOCTOU race condition in LockManager.acquire() (b96efcf)
- **Process signal distinction** - Distinguish ESRCH from EPERM in _process_alive (e43fc6f)
- **FSM signal handling** - Handle FATAL_ERROR and LOOP_STOP signals in FSMExecutor (0da74d8)
- **Issue-refinement loop** - Fix evaluate prompt and convert from goal to FSM paradigm (9f459c3, 2041c5f)

### Changed

- **Frontmatter deduplication** - Remove duplicate frontmatter parsing between sync.py and parsing.py (ENH-484)
- **Dependency mapper module** - Split monolithic dependency_mapper into focused sub-package (275a1b4)
- **Issue parser performance** - Replace prefix loop with pre-compiled union regex (6de1002)
- **ll-history export rename** - Rename `generate-docs` subcommand to `export` (6772aca)

[1.29.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.28.1...v1.29.0

## [1.28.1] - 2026-03-02

### Fixed

- fix(ll-history): replace Jaccard with intersection scoring (d253f0b)

[1.28.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.28.0...v1.28.1

## [1.28.0] - 2026-03-02

### Added

- **ll-sync diff and close subcommands** - New `ll-sync diff [ID]` to show content differences between local and GitHub versions, and `ll-sync close [ID]` to close GitHub issues when local counterparts are completed (399e95c)

### Other

- docs(issues): update ENH-484 line refs and mark blockers resolved (1ae3d75)
- docs(readme): correct CLI tools count from 13 to 12 (043d252)
- docs(index): add 17 missing entries to docs/INDEX.md (8325dc7)

[1.28.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.27.0...v1.28.0

## [1.27.0] - 2026-03-02

### Added

- **ll-history generate-docs subcommand** - Synthesize architecture documentation from completed issue history with relevance scoring and progressive construction (FEAT-503)

### Changed

- enhance(format-issue): default to highest-priority issue when no args (b395620)
- enhance(sync): use issue-sections.json template in ll-sync pull (25bc374)
- enhance(architecture): extract output_parsing from parallel/ to root package (bbd577c)
- enhance(cli): remove redundant ll-next-id standalone tool (bac9428)
- enhance(cli): sharpen CLI tool descriptions for unambiguous tool selection (c576cd9)
- refactor(templates): split issue-sections.json into per-type files (50231fb)

### Other

- docs(ll-history): document generate-docs subcommand across all references (e7c2a61)
- style: apply ruff formatting to 4 files (1a7ca55)

[1.27.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.26.0...v1.27.0

## [1.26.0] - 2026-03-01

### Added

- **ll-issues show sub-command** - View issue summary cards with detail fields and full summary in dedicated card section (FEAT-505)
- **ll-loop --background daemon mode** - Run FSM loops as background daemon processes (feat, 6d4d58c)

### Fixed

- fix(cli): wrap long summary text in ll-issues show card (853053e)
- fix(docs): correct 20 documentation issues found by full audit (0e51bc8)
- fix(docs): address 5 remaining documentation audit findings (caa31d2)

### Changed

- **Forward-message pattern investigation** - Investigated coordinator synthesis behavior for ll-parallel result fidelity; closed as low utility (ENH-501)
- **ll-issues list layout** - Enhanced list output with type-based grouping, section headers, counts, and `--flat` flag (ENH-509)
- **issue_discovery module split** - Refactored 954-line module into focused package with matching, extraction, and search sub-modules (ENH-471)
- **Confidence-check outcome scoring** - Added dual-score output with Readiness Score and Outcome Confidence Score (ENH-446)
- **Init conflicting flags and dry-run** - Added conflict detection for mutually exclusive flags and `--dry-run` preview mode (ENH-458)
- **Audit frontmatter validation** - Extended plugin-config-auditor with 8 agent fields and 5 skill fields validation (ENH-464)

### Other

- docs(readme): add recently-added CLI features to README (43a0263)
- style: apply ruff formatting to scripts (d11cfb2)
- style: fix formatting in issues show card renderer (2afb4c2)

[1.26.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.25.0...v1.26.0

## [1.25.0] - 2026-02-27

### Added

- **Configurable dependency mapping thresholds** - All overlap and conflict thresholds now configurable via `ll-config.json` with `DependencyMappingConfig` dataclass and per-project overrides (ENH-514)

### Fixed

- **Impact-effort matrix row labels** - Fixed repeated "IMPACT" labels on every row of the 2×2 ASCII matrix (BUG-508)
- fix(deps): prune generic keywords from section and type matching to reduce false positives (9fb7605)
- fix(parallel): add thresholds to overlap detection to reduce false serialization (3f352ef)

### Changed

- **Sprint runner optimization** - Disabled redundant runtime overlap detection in sprint path since wave splitting already guarantees no overlap (ENH-512)

### Other

- docs(api): add text_utils module to API reference (bc28e52)
- docs: fix outdated directory trees and wrong API doc path (46a37e8)

[1.25.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.24.0...v1.25.0

## [1.24.0] - 2026-02-26

### Added

- **Grouped ll-issues list output** - `ll-issues list` now groups output by type (BUG, FEAT, ENH) with section counts and a total footer; added `--flat` flag for backward-compatible scripting output (ENH-509)

### Other

- docs(architecture): fix outdated counts and CLI directory structure (54f1f83)
- style: fix lint and format issues in scripts (3fec926)
- chore(issues): tradeoff review of 23 active issues (7ba83dd)

[1.24.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.23.0...v1.24.0

## [1.23.0] - 2026-02-26

### Added

- **TDD mode for issue implementation** - Add test-first development mode to manage-issue skill with Phase 3a (Write Tests — Red), config toggle, and plan template updates (0c54487)
- **Observation masking scratch pad pattern** - Add scratch pad behavioral instructions for handling large tool outputs (>200 lines) to reduce context window usage in automation (010df53)

[1.23.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.22.0...v1.23.0

## [1.22.0] - 2026-02-25

### Added

- **Deferred issues folder support** - Add support for deferred issues folder in issue management (6a62ba9)

### Fixed

- **Config-driven category lists** - Replace hardcoded category lists with config-driven values (c18269c)
- **Impact-effort grid alignment** - Fix grid alignment and axis labels in impact-effort visualization (d7e8fdc)
- **Impact-effort row labels** - Fix row label repetition in impact-effort grid (5c0cd76)

### Changed

- refactor(issues): refine issue files with updated scores and research (8f6b06e)

### Other

- test(workflow-analyzer): add unit tests for internal pipeline functions (68f3f4c)
- docs(plans): add implementation plan for ENH-471 issue_discovery split (6391fc1)
- chore: update session continuation prompt (91348c4)

[1.22.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.21.0...v1.22.0

## [1.21.0] - 2026-02-25

### Added

- **ll-issues CLI Command** - New `ll-issues` command with sub-commands: `next-id`, `list`, `sequence` (dependency-aware topological sort), and `impact-effort` (ASCII 2×2 quadrant visualization) (FEAT-505)

### Changed

- **issue_discovery Module** - Split monolithic `issue_discovery.py` into domain-organized package by finding type (ENH-471)

### Other

- docs(guides): fix factual errors and broken links in user guides (d3d0409)
- docs(readme): fix CLI tool count from 12 to 13 (a24f067)
- docs(release): fix v1.20.0 changelog — tests-until-passing is a built-in loop, not a paradigm (b888598)
- chore(issues): map cross-issue dependencies via ll-deps analyze (8c8004b)
- chore(issues): verify issues and correct stale references (3d9ccce)

[1.21.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.20.0...v1.21.0

## [1.20.0] - 2026-02-24

### Added

- feat(loops): add `tests-until-passing` built-in loop — runs pytest and iterates fix/evaluate cycles until all tests pass (79e5251)

### Fixed

- **Failed Sprint Wave Resume** - Prevent failed issues from being skipped on resume in ll-sprint (BUG-473)
- **YAML Frontmatter Corruption** - Fix frontmatter corruption on yaml.safe_load/dump round-trip (BUG-474)
- **Malformed github_issue Crash** - Handle malformed github_issue values in sync module (BUG-475)
- **Session Log Append** - Only replace first occurrence of section header in session_log (BUG-476)
- **ll-messages CLI Flag** - Correct epilog flag from --include-commands to --skip-cli (BUG-477)
- **IssueParser Silent Exception** - Log warning instead of swallowing exception on unreadable file (BUG-478)
- **Stash Pop Verification** - Verify stash pop success before re-queueing in merge_coordinator (BUG-479)
- **WorkerResult Docstring** - Remove stale "(not implemented)" from should_close docstring (BUG-480)

### Changed

- **Context Degradation Checkpoints** - Add checkpoints between issues in ll-auto to detect and respond to context degradation (ENH-499)
- refactor(cli): split cli/sprint.py into cli/sprint/ package (63635c7)

### Other

- docs: fix broken link to Loops Guide in README (dcaf618)
- docs: add getting started and sprint guides, reorganize structure (912f364)
- docs(loops): expand LOOPS_GUIDE with advanced features, CLI reference, and troubleshooting (1cdf7a5)
- chore: add management plans and session continuation prompt (ef7764f)
- chore(quality): fix lint and formatting issues in scripts (a51d5cd)
- chore(issues): verify and correct stale line numbers and function refs (e3615ac)
- chore(issues): format all active issues to template v2.0 (0f9bed6)
- chore(issues): verify issues and close ENH-482 as already resolved (c816422)

[1.20.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.19.1...v1.20.0

## [1.19.1] - 2026-02-24

### Fixed

- fix(issues): correct BUG-473 to identify same bug in both sprint code paths (3fb733e)

### Changed

- refactor(issue_history): split analysis.py into focused sub-modules (7324591)

### Other

- docs: reorganize docs/ folder into semantic subdirectories (95d4139)
- docs: move guide docs into docs/guides/ subfolder (be3855e)
- docs: add Issue Management Guide end-to-end workflow tutorial (edcd83e)
- chore(issues): add ENH-491 for using issue-sections.json in ll-sync pull (50b344c)
- chore(issues): add 18 issues from codebase scan (7614085)
- chore: remove completed ENH-448 issue, update logo asset, and refresh test sprint fixtures (036f834)
- chore(issues): re-prioritize issues (dfb15d8)

[1.19.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.19.0...v1.19.1

## [1.19.0] - 2026-02-24

### Changed

- **Add `__all__` to cli/loop/__init__.py** - Maintains consistency with other 5 package init files that already define `__all__` (ENH-472)
- enhance(configure): audit and expose unreachable config-schema fields (896c4ea)

### Other

- docs(loops): add user-facing loops guide with paradigm examples (0d13f53)
- chore(issues): add tradeoff review notes to FEAT-440 and ENH-470 (5066b9a)
- chore(issues): verify 8 open issues against codebase (08239b5)
- chore(issues): auto-format 6 issues to template v2.0 structure (1f41aef)

[1.19.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.18.0...v1.19.0

## [1.18.0] - 2026-02-23

### Changed

- **Audit settings hierarchy validation** - Full settings hierarchy validation in audit-claude-config (ENH-465)
- **Confidence-check outcome scoring** - Add outcome confidence scoring dimension (ENH-446)
- **Init auto-create issue directories** - Offer to create issue directories during initialization (ENH-453)
- **Init wizard round renumbering** - Renumber wizard rounds to eliminate Round 6.5 (ENH-454)
- **Init wizard expanded coverage** - Expand parallel, commands, and issues coverage in wizard (ENH-455)
- **Init wizard intro and descriptions** - Add intro context and improve feature descriptions (ENH-456)
- **Init templates as single source of truth** - Reconcile templates/*.json with presets.md (ENH-457)
- **MCP audit across all scopes** - Extend MCP audit to all scopes with env var expansion validation (ENH-466)
- **Init conflicting flags and dry-run** - Handle conflicting flags and add --dry-run (ENH-458)
- **Init command validation** - Optional command validation during init (ENH-460)
- **Command table completeness** - Add 7 missing skills to README and COMMANDS.md command tables (ENH-467)

### Fixed

- fix(loop): resolve mypy type error in FSM diagram renderer (bae6844)

### Other

- docs(audit): fix INDEX.md missing entry and track incomplete command tables (ab949ec)

[1.18.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.17.0...v1.18.0

## [1.17.0] - 2026-02-22

### Added

- **Init wizard: sprints, loops, and automation** - Add sprints, loops, and automation sections to interactive wizard (ENH-451)
- **Init wizard progress indicator** - Add progress indicator to interactive wizard rounds (ENH-452)

### Fixed

- fix(agents): update plugin-config-auditor to recognize all 17 hook event types (30fc2bc)
- fix(init): add missing state files to .gitignore step (40faae4)
- fix(init): split Round 5 into 5a/5b to respect AskUserQuestion 4-question limit (b44d28e)
- fix(skills): remove disable-model-invocation from all skills (d70e63f)
- fix(ci): resolve documentation link check failures (618cc6e)

### Changed

- **Audit frontmatter validation** - Add agent and skill frontmatter field validation to audit (ENH-464)
- **Audit config surfaces** - Add 5 missing config surfaces to audit-claude-config (ENH-462)

### Other

- deps(issues): map cross-issue dependencies for 22 active issues (2834d71)
- issues: add 13 issues from /ll:init interactive mode audit (82ead60)
- ci: remove documentation link check workflow (c778a02)

[1.17.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.16.0...v1.17.0

## [1.16.0] - 2026-02-22

### Added

- **Confidence score blocking gate for manage-issue** - ConfidenceGateConfig with enabled/threshold settings, Phase 2.5 gate check, `--force-implement` flag, and configure skill integration (ENH-447)

### Other

- chore(issues): add ENH-446, ENH-447, ENH-448 to backlog (87c469f)

[1.16.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.15.0...v1.16.0

## [1.15.0] - 2026-02-19

### Changed

- **2D ASCII renderer for FSM loop diagrams** - Replaced flat 1D text diagram with a 2D Unicode box renderer; main-path states rendered as boxes connected by labeled arrows, with self-loops indicated by ↺ marker (ENH-444)
- **FSM graph diagram in `ll-loop show`** - Implemented `_render_fsm_diagram()` with BFS-based edge classification rendering main flow, branches, and back-edges sections with labeled edges (ENH-443)
- **Per-iteration progress display in `ll-loop run`** - Fixed event callback wiring in `run_foreground`; added `[iter X] state: name (Xs)` format respecting `--quiet` flag (ENH-442)

### Other

- docs: fix ll-loop compile argument name in README (18b2af8)
- docs: remove unsupported action_type from paradigm templates (1f10d4e)
- style: fix lint and format issues in loop display code (ff1f49f)
- style: apply ruff formatting to 3 files (df48bb2)

[1.15.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.14.1...v1.15.0

## [1.14.1] - 2026-02-15

### Fixed

- **worktree_copy_files directory crash** - Skip directory entries in worktree file copying to prevent IsADirectoryError (BUG-438)
- **Hardcoded main branch references** - Auto-detect base branch in ll-sprint/ll-parallel instead of hardcoding "main"; update test assertions accordingly (BUG-439)

### Other

- docs(readme): add missing CLI subcommands for ll-loop and ll-history (4e81bf8)

[1.14.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.14.0...v1.14.1

## [1.14.0] - 2026-02-15

### Added

- **Sprint conflict analysis CLI** - `ll-sprint analyze` command for detecting conflicts between sprint issues (FEAT-433)
- **Dependency auto-repair** - `ll-deps fix` command to auto-repair broken dependency references (FEAT-432)
- **Metrics export** - Export historical metrics from `ll-history` (FEAT-435)
- **Git sync conflict resolution** - Commands for resolving sync conflicts with GitHub (FEAT-436)
- **Standalone overlap detection** - Pre-flight overlap detection command for sprint planning (FEAT-434)

### Fixed

- **Bare exception in merge loop** - Narrow bare exception to `queue.Empty` in merge coordinator (BUG-424)
- **Lock file race condition** - Replace TOCTOU race with `missing_ok=True` in LockManager (BUG-423)
- **Subprocess timeouts** - Add `timeout=30` to all `subprocess.run` calls in issue lifecycle (BUG-422)
- **File deletion race** - Replace TOCTOU file deletion race with `missing_ok=True` (BUG-421)
- **Process.wait() timeout** - Add timeout to `process.wait()` calls to prevent indefinite blocking (BUG-420)
- **UnboundLocalError** - Initialize result before loop to prevent `UnboundLocalError` in `_run_with_continuation()` (BUG-419)
- **Return code masking** - Fix `process.returncode` None being masked as success (BUG-425)

### Changed

- **Issue ID extraction** - Centralize issue ID extraction logic into shared utility (ENH-429)
- **Code fence stripping** - Centralize code fence stripping utility (ENH-430)
- **Wave refinement performance** - Fix O(N²) wave refinement with synchronous file reads (ENH-427)
- **Test coverage** - Add missing test coverage for core modules (ENH-426)
- **README template coverage** - Update template list to reflect all 9 project-type templates (ENH-437)

### Other

- docs(readme): add missing CLI subcommands for ll-sprint and ll-deps (c3b96f8)
- docs(issues): tech-debt audit — close 6 issues, narrow 2 (21828a1)
- docs(issues): architectural audit — close 6 issues, annotate 3 (b2d756c)
- docs(issues): add 18 issues from codebase scan (e09d628)
- docs(CLAUDE.md): distinguish skills from commands in capability list (71616c7)
- style(tests): auto-format test files with ruff (90b70c6)

[1.14.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.13.0...v1.14.0

## [1.13.0] - 2026-02-14

### Added

- **ll-auto content marker checking** - Verify phase fallback chain now checks implementation markers in issue file content (ENH-328)
- **Sprint sequential retry** - Merge-failed issues are retried sequentially after parallel waves complete (feat, 6c27480)

### Fixed

- fix(code-quality): resolve lint error and reformat 10 files (d50cb78)
- fix(docs): update CONTRIBUTING.md skills tree to list all 15 directories (21254eb)
- fix(docs): update README Skills table to list all 15 skills (872ebad)
- fix(docs): correct command and skill counts, reopen regressed doc issues (88025ba)

### Changed

- **Skill invocation allocation** - Audit and optimize skill invocation allocation across commands (ENH-279)
- **Test coverage improvements** - Add 59 tests across 6 modules, improving coverage from 86% to 89% (ENH-410)
- **Batched git log calls** - Batch git log calls in issue discovery for reduced subprocess overhead (ENH-352)
- enh(docs): update CLAUDE.md date and add skills count (eb95e2a)
- enh(sprint): relabel "file contention" to "file overlap" in sprint show output (8df1e2e)
- enh(plugin): add explicit agents declaration to plugin.json (0cf3e99)
- enh(commands): replace hardcoded tool names with config references (7a59449)
- enh(commands): add flag conventions to commands and skills (1267f27)
- enh(cli): add --type flag to ll-auto, ll-parallel, and ll-sprint (e53a574)
- enh(audit-claude-config): add Skills to Commands cross-reference validation (e480671)
- perf(link-checker): parallelize HTTP URL checking with ThreadPoolExecutor (e3d62c7)
- perf(issue-discovery): batch git log calls into single subprocess (01c60d4)
- perf(issue-history): cache issue file contents across analysis pipeline (60dfdce)
- refactor(text-utils): consolidate duplicated file path extraction into shared module (69175d2)
- refactor(cli-loop): split monolithic loop.py into focused subcommand package (8898582)
- refactor(issue-history): split god module into focused package (b51acb9)

### Other

- chore(issues): verify and correct stale file references in ENH-387, ENH-276, ENH-342 (cbd655b)

[1.13.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.2...v1.13.0

## [1.12.2] - 2026-02-13

### Other

- chore: standardize remaining underscore command/skill refs to hyphens (c74c178)

[1.12.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.1...v1.12.2

## [1.12.1] - 2026-02-13

### Fixed

- fix(commands): standardize all command/skill names to hyphens (28ff0f5)

### Other

- chore(issues): verify 19 open issues and fix stale references (22186c1)
- chore(issues): deprioritize FEAT-324 to P6 and FEAT-417 to P7 (30fae5a)
- close(issues): won't-fix 5 low-value enhancements after architecture review (d5b5a04)

[1.12.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.0...v1.12.1

## [1.12.0] - 2026-02-13

### Added

- **Sprint show improvements** - Nested sub-wave display and health summary in `ll-sprint show` (7f000dc)
- **Confidence check batch mode** - `--all` and `--auto` flags for batch processing (ENH-408)
- **Sprint theme grouping** - Theme-based grouping options in `create_sprint` (ENH-407)

### Fixed

- **Sprint dependency graph** - Use structural root detection in dependency graph rendering (588ff3d)
- **Issue heading IDs** - Correct mismatched IDs in issue headings (cd4e206)
- **Dependency references** - Clean up resolved blockers and stale dependency references (9c7f22f)
- **Plugin config auditor** - Complete hook event types and handler validation (ENH-368)

### Changed

- **Skills --all flag** - `--all` flag implicitly enables `--auto` behavior (ENH-416)
- **Confidence check labels** - Type-specific criterion 3 labels and rubrics (ENH-418)
- **Hooks configuration** - Add description and statusMessage fields to hooks.json (ENH-371)
- **Hook matchers** - Remove silently-ignored matchers from UserPromptSubmit and Stop events (a706be4)
- **Hook feedback** - Use exit 2 in precompact-state.sh for user-visible feedback (d646559)
- **Command frontmatter** - Add argument-hint frontmatter to 27 command/skill files (ENH-401)
- **Skill frontmatter** - Add model and allowed-tools frontmatter to 8 skills (ENH-398)
- **Skill migration** - Migrate 8 oversized commands to skill directories (ENH-400)
- **Agent frontmatter** - Add model and tools frontmatter fields to all agents (ENH-355)
- **Command tools** - Add allowed-tools frontmatter to 25 commands (ENH-399)
- **Manage issue resume** - Read continuation prompt on `--resume` (cf788e1)

### Other

- docs(cli): document ll-next-id in README, CLAUDE.md, and cli/__init__.py (b9aaae5)
- docs(issues): capture ENH-418, ENH-416, FEAT-417, ENH-405 (352f022, 7f42a6c)
- style(sprint): auto-format and fix line length in sprint modules (4123c21, ad3867f)

[1.12.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.11.1...v1.12.0

## [1.11.1] - 2026-02-13

### Fixed

- fix(docs): update CONTRIBUTING.md project tree cli.py → cli/ package (703da46)
- fix(docs): add review_sprint to all command documentation (76498c8)

### Other

- docs: fix README counts and create issues for undocumented commands/tools (a641b33)
- style: apply ruff format to scripts (925b8ce)

[1.11.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.11.0...v1.11.1

## [1.11.0] - 2026-02-13

### Added

- **Parallel merge for BUG-402** - Enable parallel merge workflow for bug fix processing (27ee877)

### Fixed

- **Config test fixtures** - Remove stale default_mode from test fixtures (8063ff6)
- **Cross-type issue references** - Resolve false "nonexistent" warnings for cross-type issue references (ff50bc6)
- **Command $ARGUMENTS placement** - Add explicit $ARGUMENTS placement to 6 command files (e339afe)
- **Sync status errors** - Surface GitHub query failures in sync status (aa3b2a3)
- **Mutable default aliasing** - Prevent mutable default aliasing in ProcessingState.from_dict (37c05c3)
- **Scan command tools** - Add missing tools to allowed-tools in scan commands (6c3af0b)
- **Sprint dependency graph** - Suppress flat dependency graph when no intra-sprint edges exist (3d7713c)

### Other

- close(bugs): BUG-403 - Closed - Already Fixed (2ab0411)
- close(bugs): BUG-365 - Closed - Invalid (09ca349)
- docs(issues): add test and documentation coverage to 29 active issues (36b4241)
- docs(issues): resolve BUG-364 marketplace version mismatch (c1bc313)
- docs(issues): auto-format and verify 42 active issues (b689764)
- docs(issues): add cross-issue dependency references for command/skill audit issues (72d6326)

[1.11.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.10.1...v1.11.0

## [1.10.1] - 2026-02-12

### Added

- **Plugin config audit issues** - Add plugin config audit issues and update ENH-371 with once field (130dd65)
- **Cross-issue dependency mappings** - Add cross-issue dependency mappings and ENH-396 issue (c14cbc4)
- **`ll-next-id` command** - Consolidate issue ID assignment with new CLI command (cc50082)
- **Sprint review skill** - Add `/ll:review-sprint` skill for AI-guided sprint health checks (c4b6b11)
- **Sprint edit subcommand** - Add `ll-sprint edit` subcommand for sprint modifications (6c195f2)
- **Sprint-scoped dependency analysis** - Add `--sprint` flag to `ll-deps` for sprint-scoped analysis (dee0890)

### Fixed

- **Sprint review plugin discovery** - Move review_sprint from skill to command for plugin discovery (264a3de)
- **Sprint skill arguments** - Add missing `$ARGUMENTS` section to review_sprint skill (1dd0c1c)
- **Documentation module listings** - Update ARCHITECTURE and API module listings from audit (2c063eb)

### Other

- docs: add Claude Code reference documentation for hooks, plugins, and skills (f54a723)
- style(cli): fix line length formatting in loop and sprint modules (4550a0a)

[1.10.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.10.0...v1.10.1

## [1.10.0] - 2026-02-12

### Added

- **Auto-mode for prioritize_issues** - Run priority assignment without interactive prompts (FEAT-380, ENH-389)
- **Re-prioritize option** - Re-prioritize already-prioritized issues when backlog shifts (ENH-389)
- **Refine issue command** - New `refine_issue` with codebase-driven research for deeper issue refinement (FEAT-380)
- **`ll-loop show` command** - Inspect loop configuration details from the CLI (FEAT-345)
- **CLI tool loop templates** - Ship built-in loop templates for common CLI tool workflows (ENH-332)
- **Pre-implementation confidence check** - Validate implementation readiness before coding begins (ENH-277)
- **Abstract base classes for CLI commands** - Shared ABC for CLI command structure (FEAT-001)
- **Session log linking** - Link session JSONL logs to issue files for traceability (FEAT-323)

### Fixed

- **Prioritize issues gate logic** - Simplify and fix re-prioritize gate wording and AskUserQuestion reliability (BUG-361)
- **Normalize issues duplicate detection** - Include `completed/` directory in duplicate ID detection (BUG-382)
- **Configure phantom section** - Remove phantom workflow configuration section (BUG-367)
- **Sprint issue parsing** - Log warning when issue file parsing fails instead of crashing (BUG-348)
- **Hook timeout values** - Correct timeout values from milliseconds to seconds (BUG-376)
- **Hook prompt handling** - Use `exit 0` + stdout instead of `exit 2` + stderr in user-prompt-check (BUG-361)
- **Absolute path removal** - Replace absolute paths with relative/generic paths for public repo distribution (BUG-338)
- **Issue size review reference** - Correct command reference in issue-size-review skill (BUG-358)
- **README skills count** - Fix skills count (7 vs 8) and add missing loop-suggester to table (BUG-381)
- **CONTRIBUTING directory trees** - Update outdated directory trees for skills, loops, and docs (BUG-382)
- **Help references** - Correct multiple stale and missing references in help.md (BUG-336)
- **Create loop wizard** - Present paradigms instead of use-case templates (BUG-333)
- **Context monitor compaction** - Reset token estimate after context compaction (BUG-329)
- **Manage issue improve action** - Clarify that improve action requires full implementation (BUG-326, BUG-327)

### Changed

- **Behavioral rules extraction** - Split CLAUDE.md behavioral rules into core docs (ENH-278)
- **Test file splitting** - Split large test files into focused modules (ENH-311)
- **Text dependency graphs** - Replace mermaid dependency graphs with ASCII text diagrams in CLI (ENH-334)
- **Documentation reorganization** - Organize docs with command and skill groupings (ENH-335)
- **Dependency mapping delegation** - `map-dependencies` skill delegates to `dependency_mapper.py` (ENH-337)
- **Configurable continuation path** - Continuation prompt path now configurable (ENH-340)
- **CLI package split** - Split `cli.py` into `cli/` package for maintainability (ENH-344)
- **Serialization mixin** - Extract serialization mixin for dataclass `to_dict` boilerplate (ENH-354)
- **Agent model fields** - Add missing `model` field to all agent frontmatter (ENH-355)
- **CLAUDE.md completeness** - Document orphan commands and CLI tools (ENH-356)
- **Settings validation** - `audit_claude_config` now validates `settings.json` content (ENH-369)
- **Command examples** - Add missing Examples sections to commit and tradeoff_review_issues commands (ENH-373)
- **Remove .mcp.json placeholder** - Remove empty `.mcp.json` placeholder file (ENH-375)
- **Rename refine_issue** - Rename `refine_issue` to `format_issue` for honest naming (ENH-379)
- **Audit docs direct fix** - Add direct fix option for auto-fixable findings in audit_docs (ENH-383)
- **Context monitor tracking** - Track Claude output and user message tokens (ENH-330)

[1.10.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.9.0...v1.10.0

## [1.9.0] - 2026-02-11

### Added

- **Pre-implementation confidence-check skill** - New skill for validating implementation readiness before starting work (ENH-277)
- **Session log linking** - Link Claude Code JSONL session logs to issue files for traceability (FEAT-323)
- **Context monitor token tracking** - Track Claude output and user message tokens with compaction reset (ENH-330)

### Fixed

- **Config schema cleanup** - Remove 5 unused schema sections with no implementation (ENH-343)
- **Hardcoded path removal** - Replace hardcoded paths with config template refs in commands and skills (ENH-341)
- **Loops directory config** - Read loops directory path from ll-config.json instead of hardcoding (BUG-339)
- **Hook directory config** - Read hook directory paths from ll-config.json (BUG-338)
- **Help references** - Correct stale references in help.md (BUG-336)
- **Create loop wizard** - Present paradigms instead of use-case templates in wizard (BUG-333)
- **Context monitor compaction** - Reset token estimate after context compaction (BUG-329)
- **Issue manager resume** - Use `--resume` flag for continuation sessions (BUG-327)

### Changed

- **CLI package split** - Split `cli.py` god module into `cli/` package for better maintainability (ENH-344)
- **Dependency mapping delegation** - `map-dependencies` skill now delegates to `ll-deps` CLI (ENH-337)
- **ASCII dependency graphs** - Replace mermaid dependency graphs with ASCII text diagrams (ENH-334)
- **Documentation reorganization** - Organize commands and skills under 9 capability groupings (ENH-335)

[1.9.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.8.0...v1.9.0

## [1.8.0] - 2026-02-11

### Added

- **Auto mode for issue refinement** - `refine_issue` now supports automatic template v2.0 alignment without interactive Q&A (ENH-325, FEAT-256)
- **Session linking and history DB issues** - New issues for session continuity and historical tracking (FEAT-255)
- feat(refine_issue): add auto mode for template v2.0 alignment (2fb8ab4)

### Fixed

- **Improve action clarity** - `manage_issue` improve action now clearly requires full implementation, not just plans (BUG-326)
- **Template v2.0 section names** - Corrected old v1.0 template section names in 3 files (BUG-322)

### Changed

- refactor(issue): reduce ENH-319 scope from 12 to 6 enhancements (8e6ec6e)
- chore: add .sprints/ to .gitignore (e7ab913)
- chore: ignore generated loop-suggestions cache directory (f8e7ce4)
- style: fix lint errors and reformat with ruff (ae44c67)

[1.8.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.7.0...v1.8.0

## [1.7.0] - 2026-02-10

### Added

- **Issue template v2.0 with Integration Map** - New template format with integration analysis section for better cross-component awareness (ENH-320, ENH-321)

### Fixed

- **Null command guards** - Commands no longer crash when project commands (lint_cmd, type_cmd, format_cmd, test_cmd) are null (BUG-312)
- **Sprint duplicate status lines** - Suppress duplicate status output during parallel execution (BUG-305)
- **Documentation accuracy** - Correct 3 config default values, command count, `max_continuations` section placement, missing commands in README tables, ghost `find_demo_repos` entry, and `--include-p0` flag docs (BUG-313, BUG-315, BUG-316, BUG-317, BUG-318)

### Changed

- **Sprint file contention warnings** - Execution plan now shows file contention warnings for better parallel planning (ENH-309)
- **build_cmd verification** - `check_code` now includes build_cmd verification step (ENH-310)
- **run_cmd config field** - Added run_cmd to config and wired into manage_issue verification (ENH-311)
- **README config documentation** - Added sync, sprints, documents, and missing config sections to README (ENH-314, ENH-318)
- docs(contributing): add issue creation guidelines for v2.0 (fe6fea5)
- docs(commands): update commands for template v2.0 (317144c)

[1.7.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.6.0...v1.7.0

## [1.6.0] - 2026-02-10

### Changed

- **Semantic conflict analysis in dependency mapper** - Detect semantic conflicts within shared files, distinguishing safe parallel modifications from true conflicts (ENH-300)
- **Dependency mapper integration** - Integrate dependency mapping into sprint creation and execution workflows for improved wave splitting (ENH-301)
- **File-contention-aware wave splitting** - Intelligent wave splitting based on file contention analysis for optimized parallel execution (ENH-306)

### Fixed

- **Sprint subprocess hang in automation mode** - Prevent subprocess hang when Claude calls AskUserQuestion in `-p` mode (BUG-302)
- **Parallel wave overlap detection** - Enable overlap detection for parallel wave execution (BUG-305)
- **Sprint state per-issue tracking** - Use per-issue tracking from orchestrator queue instead of wave-level exit code (BUG-307)
- fix(config): disable idle timeout by default to prevent false kills (6f3f6e0)

[1.6.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.5.0...v1.6.0

<!-- Versions 1.2.0-1.4.0 were internal development milestones without tagged releases. -->

## [1.5.0] - 2026-02-09

### Added

- **GitHub Issues sync** - Bidirectional sync with GitHub Issues including `ll-sync` CLI tool, `--dry-run` support, and `--labels` filtering (FEAT-222, FEAT-226)
- **Release management** - `/ll:manage-release` command for git tags, changelogs, GitHub releases, and version bumping (FEAT-268)
- **Product analysis** - `/ll:product-analyzer` skill and `/ll:scan-product` command for product-focused codebase analysis (FEAT-022)
- **Issue dependency mapping** - Automated cross-issue dependency discovery with semantic conflict analysis (FEAT-261)
- **Loop automation** - `/ll:create-loop` and `/ll:loop-suggester` skills for FSM loop configuration; ship 5 built-in loops (FEAT-219, FEAT-270)
- **Tradeoff review** - `/ll:tradeoff-review-issues` skill for issue utility vs complexity evaluation (FEAT-257)
- **Issue refinement** - `/ll:refine-issue` skill with content-quality analysis for interactive issue clarification (FEAT-225)
- **Open PR command** - `/ll:open-pr` command and skill for pull request creation (FEAT-228)
- **GitHub sync in init wizard** - Add sync setup to `/ll:init` and `/ll:configure` (ENH-227)
- **Sprint management** - `ll-sprint` CLI tool with YAML sprint definitions and quiet mode
- **Workflow analysis** - `/ll:analyze-workflows` and `/ll:workflow-automation-proposer` skills
- **History analysis** - `/ll:analyze-history` skill for project health insights
- **CLI command extraction** - `ll-messages --include-commands` for CLI command history (FEAT-221)
- **End-to-end CLI tests** - Comprehensive CLI workflow tests (FEAT-210)
- **Fuzz testing** - Fuzz testing for critical parsers (ENH-216)
- **Documentation tooling** - CLI link checker (ENH-267), automated doc count verification (ENH-265), central documentation index (ENH-266)
- **Real-time progress** - Worktree progress visibility in `ll-parallel` (ENH-262)
- **Quiet mode** - `--quiet` flag for `ll-auto` and `ll-sprint`

### Fixed

- **ll-auto verification** - Detect plan creation in Phase 3 verification (BUG-280)
- **Process management** - Reap child process after timeout kill to prevent zombies (BUG-231); close selector to prevent file descriptor leak (BUG-230); detach spawned continuation process as daemon (BUG-236)
- **Parallel processing** - Ensure worker callback invoked on future exception (BUG-229); narrow exception catch in priority queue to `queue.Empty` (BUG-233)
- **GitHub sync** - Use global issue numbering to prevent collision with completed issues (BUG-234); pass `--labels` flag to `gh issue list` during pull (BUG-235)
- **Documentation accuracy** - Correct README command count, skills table, and plugin.json path (BUG-273); update outdated directory trees across README, CONTRIBUTING, and ARCHITECTURE (BUG-274)
- **FSM documentation** - Clarify max_iterations defaults vs recommended values (BUG-194); add notation legend to FSM Compilation Reference (BUG-197); update ll-loop test output docs (BUG-199)
- **ll-messages** - Aggregate all assistant turns for `--include-response-context` (BUG-220)
- **Plugin configuration** - Correct relative paths for commands and skills directories; correct marketplace.json source path
- **Create loop docs** - Document missing `action_type` field (BUG-192) and `on_handoff` feature (BUG-193)

### Changed

- **Frontmatter parsing** - Consolidated duplicated parsing into shared module
- **Work verification** - Consolidated duplicated verification code into single source
- **CLI architecture** - Extracted shared CLI argument definitions to `cli_args` module
- **Plugin structure** - Converted `refine_issue` from skill to command
- **Error messages** - Standardized error message format across paradigm validators
- **Templates** - Extracted issue section checks into shared template file
- **Hooks** - Unified feature flag checking with shared functions
- **Issue management** - Added integration analysis to lifecycle; added product impact fields to issue parsing
- **Config** - Added configurable duplicate detection thresholds

### Testing

- Improved `issue_manager.py` test coverage to 87% (ENH-207)
- Improved `merge_coordinator.py` test coverage to 80% (ENH-208)
- Improved `orchestrator.py` test coverage (ENH-209)
- Added concurrent access tests (ENH-217)
- Improved error message validation in tests (ENH-215)
- Added comprehensive testing documentation (ENH-214)
- Split large test files into focused modules
- Added tests for loop-suggester and create_loop skill artifacts

[1.5.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.1.0...v1.5.0

## [1.1.0] - 2026-02-01

### Added

- **`ll-history` CLI tool** - View completed issue statistics including total count, date range, velocity (issues/day), and breakdowns by type and priority. Supports `--json` flag for scripting.

[1.1.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.0.0...v1.1.0

## [1.0.0] - 2026-01-02

### Added

- **20 slash commands** for development workflows:
  - `/ll:init` - Project initialization with auto-detection for 7 project types
  - `/ll:help` - Command reference and usage guide
  - `/ll:toggle-autoprompt` - Toggle automatic prompt optimization
  - `/ll:check-code` - Code quality checks (lint, format, types)
  - `/ll:run-tests` - Test execution with scope filtering
  - `/ll:find-dead-code` - Unused code detection
  - `/ll:manage-issue` - Full issue lifecycle management
  - `/ll:ready-issue` - Issue validation with auto-correction
  - `/ll:prioritize-issues` - Priority assignment (P0-P5)
  - `/ll:verify-issues` - Issue verification against codebase
  - `/ll:normalize-issues` - Fix invalid issue filenames
  - `/ll:scan-codebase` - Issue discovery
  - `/ll:audit-docs` - Documentation auditing
  - `/ll:audit-architecture` - Architecture analysis
  - `/ll:audit-claude-config` - Comprehensive config audit
  - `/ll:describe-pr` - PR description generation
  - `/ll:commit` - Git commit creation with approval
  - `/ll:iterate-plan` - Plan iteration and updates
  - `/ll:handoff` - Generate continuation prompt for session handoff
  - `/ll:resume` - Resume from previous session's continuation prompt

- **7 specialized agents**:
  - `codebase-analyzer` - Implementation details analysis
  - `codebase-locator` - File and feature discovery
  - `codebase-pattern-finder` - Code pattern identification
  - `consistency-checker` - Cross-component consistency validation
  - `plugin-config-auditor` - Plugin configuration auditing
  - `prompt-optimizer` - Codebase context for prompt enhancement
  - `web-search-researcher` - Web research capability

- **Sequential automation** (`ll-auto`):
  - Priority-based issue processing
  - State persistence for resume capability
  - Real-time output streaming
  - Configurable timeouts

- **Parallel automation** (`ll-parallel`):
  - Git worktree isolation per worker
  - Concurrent issue processing
  - Automatic merge coordination
  - `--show-model` flag for model verification
  - Configurable worker count

- **Configuration system**:
  - JSON Schema validation
  - 9 project-type templates (Python, JavaScript, TypeScript, Go, Rust, Java Maven/Gradle, .NET, Generic)
  - Variable substitution in command templates
  - Command override support

- **Issue management**:
  - Auto-correction during validation
  - Automatic issue closure for invalid/resolved issues
  - Fallback lifecycle completion
  - Work verification before marking complete

### Fixed

- Safety checks for stale state in close/complete functions
- Circular import in parallel orchestrator
- Markdown bold formatting in verdict parsing
- Type annotations and shadowed variable issues

### Security

- All subprocess calls use argument lists (no shell=True)
- Git operations constrained to repository directory
- Claude CLI invoked with `--dangerously-skip-permissions` (documented requirement for automation)

[1.90.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.89.0...v1.90.0
[1.89.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.88.0...v1.89.0
[1.88.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.87.0...v1.88.0
[1.87.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.86.0...v1.87.0
[1.86.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.85.0...v1.86.0
[1.85.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.84.0...v1.85.0
[1.84.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.83.0...v1.84.0
[1.83.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.82.0...v1.83.0
[1.82.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.81.1...v1.82.0
[1.81.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.81.0...v1.81.1
[1.81.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.80.0...v1.81.0
[1.80.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.79.0...v1.80.0
[1.79.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.78.0...v1.79.0
[1.78.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.77.0...v1.78.0
[1.77.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.76.0...v1.77.0
[1.76.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.75.0...v1.76.0
[1.75.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.74.0...v1.75.0
[1.74.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.73.0...v1.74.0
[1.73.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.72.0...v1.73.0
[1.72.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.71.0...v1.72.0
[1.71.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.70.0...v1.71.0
[1.70.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.69.0...v1.70.0
[1.69.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.68.0...v1.69.0
[1.68.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.2...v1.68.0
[1.67.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.1...v1.67.2
[1.67.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.67.0...v1.67.1
[1.67.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.66.1...v1.67.0
[1.66.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.66.0...v1.66.1
[1.66.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.65.0...v1.66.0
[1.65.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.64.1...v1.65.0
[1.64.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.64.0...v1.64.1
[1.64.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.63.0...v1.64.0
[1.63.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.62.0...v1.63.0
[1.62.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.61.1...v1.62.0
[1.61.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.61.0...v1.61.1
[1.61.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.60.0...v1.61.0
[1.60.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.59.0...v1.60.0
[1.59.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.58.0...v1.59.0
[1.58.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.57.0...v1.58.0
[1.57.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.56.0...v1.57.0
[1.56.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.55.0...v1.56.0
[1.55.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.54.0...v1.55.0
[1.131.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.130.0...v1.131.0
[1.130.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.129.0...v1.130.0
[1.54.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.53.0...v1.54.0
[1.53.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.52.0...v1.53.0
[1.52.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.51.0...v1.52.0
[1.51.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.50.0...v1.51.0
[1.50.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.49.0...v1.50.0
[1.49.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.48.0...v1.49.0
[1.48.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.47.0...v1.48.0
[1.47.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.46.0...v1.47.0
[1.46.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.45.0...v1.46.0
[1.45.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.44.0...v1.45.0
[1.44.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.43.0...v1.44.0
[1.43.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.42.0...v1.43.0
[1.42.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.41.0...v1.42.0
[1.41.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.40.0...v1.41.0
[1.40.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.39.0...v1.40.0
[1.134.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.133.0...v1.134.0
[1.133.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.132.0...v1.133.0
[1.132.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.131.0...v1.132.0
[1.39.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.38.0...v1.39.0
[1.38.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.3...v1.38.0
[1.34.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.33.1...v1.34.0
[1.33.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.33.0...v1.33.1
[1.0.0]: https://github.com/BrennonTWilliams/little-loops/compare/v0.0.1...v1.0.0
[1.147.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.143.0...v1.147.0
[1.143.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.142.0...v1.143.0
[1.142.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.141.0...v1.142.0
[1.141.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.140.0...v1.141.0
[1.140.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.139.0...v1.140.0
[1.139.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.138.0...v1.139.0
[1.138.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.137.0...v1.138.0
[1.137.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.136.0...v1.137.0
