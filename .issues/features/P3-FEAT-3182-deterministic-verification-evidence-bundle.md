---
id: FEAT-3182
title: Deterministic verification-evidence bundle from verify-loop runs
type: FEAT
priority: P3
status: open
parent: EPIC-2087
discovered_date: '2026-08-15'
labels:
- path-a
- verification
- audit-evidence
unproven_mechanism: true
decision_needed: false
spike_attempted: true
spike_completed: true
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

## Summary

Export a reproducible evidence bundle from `verify-loop` / `adversarial-verify-loop` runs, assembled **only** from deterministic sources — git predicates, `history.db` records, and on-disk run artifacts. No LLM self-evaluation contributes to the attestation.

## Current Behavior

A `verify-issue-loop` run leaves behind an archived run directory (`state.json`, `events.jsonl`) and a `loop_runs` row, but no artifact ties them to the commit that was verified, the loop YAML that ran, or the issue file whose criteria were checked. Adversarial `probe-*.json` files stay in a gitignored, never-archived `run_dir`. Nothing distinguishes LLM-graded verdicts from mechanically established facts, so a reviewer cannot re-check what was verified without re-running the loop.

## Expected Behavior

`ll-loop evidence <run>` emits a plain-JSON bundle whose `evidentiary` section holds only facts a reviewer can re-derive from git, `history.db`, and the archived run directory; LLM verdicts sit in a labeled `context_non_evidentiary` section; every missing input is an enumerated gap; re-running over unchanged inputs is byte-identical.

## Use Case

A reviewer is asked to merge an agent-produced branch three weeks after `ll-loop run` verified it in adversarial mode. They run `ll-loop evidence --latest verify-feat-1234-adversarial --json`, see the recorded `head_sha` still resolves and is an ancestor of the branch tip, the loop YAML hash and issue-file blob hash match what they can regenerate from the repo, three `probe-*.json` files were archived, and the gap list is empty. They then read the segregated LLM verdicts as context, knowing which claims they can re-derive themselves and which they cannot.

## Motivation

An attestation that a change was verified is only as trustworthy as its weakest input. A bundle assembled from git refs, `history.db` rows, and run-directory files can be re-checked by anyone holding the repo. A bundle that folds in a model's own assessment of its own work inherits the self-evaluation bias MR-1 documents, and cannot be handed to a reviewer who did not run the loop.

Two consumers need the first kind and cannot use the second: a team reviewing agent-produced changes at merge time, and any process that has to answer "what was checked, and how do you know" months after the run.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

No implementation exists yet (searched repo-wide: no `Bundle`-named class, no `export_bundle`/`cmd_*export*` function, no `attestation`/`evidentiary` vocabulary anywhere but this issue). This codebase's closest shape precedent for a report exporter is the `Report`-suffixed dataclass family (`CostReport`, `scripts/little_loops/fsm/cost_graph.py:106-139`: plain fields, locked-shape `to_dict()`, sibling human-render method), and its closest CLI-placement precedent is `scripts/little_loops/cli/artifact/dashboard.py` (a `history.db`-plus-files exporter producing a portable, host-independent artifact — the "readable without little-loops installed" AC has a direct analogue there).

A prior, unresolved question determines the bundle's actual shape (see `## Program Design` → Decision Rules): `verify-issue-loop`'s only real pass/fail judgment is LLM-graded (`llm_structured` states in both `criteria` and `adversarial` modes), and its only non-LLM gates (`_aggregate_state`, `count_probes`) aggregate *over* those judgments rather than independently establishing them. Two ways to resolve this were identified; neither is a foregone conclusion and it should be treated as a decision for a human before implementation, not settled by this pass:

**Option A**: Bundle only structural/existence facts as evidentiary content — that a run occurred, which states executed, artifact/probe file existence and hashes, probe counts (recomputed the way the shipped `count_probes` gate does), `loop_runs` row fields, git ref/diff state. LLM verdicts (criterion pass/fail, `break_found`) are attached as a segregated, explicitly labeled-non-evidentiary section for human context. This satisfies AC3 literally, but the resulting attestation is "a check was attempted, here is what exists" rather than "the criteria passed" — a materially weaker claim than "verification evidence" implies to a reviewer.

> **Selected:** Option A — satisfies AC3 literally, matches the shipped `count_probes` non-LLM segregation precedent, and its mechanism is already validated by this issue's own spike (7/7 passing tests).

**Option B**: Treat the LLM verdict fields as evidentiary, wrapped with the deterministic provenance that produced them (artifact existence/hash, the `_aggregate_state`/`count_probes` gate result) so a reviewer can independently re-derive whether the loop's own non-LLM aggregation passed. This makes the *aggregation* deterministic and re-checkable, but the underlying per-criterion/per-probe judgment remains LLM-sourced — it does not satisfy AC3's "No LLM self-evaluation contributes to the attestation" for that content.

**Recommended**: Neither option is implementation-ready without a human decision — the tension is structural, not a research gap this pass can close. Flagged via `unproven_mechanism: true` rather than resolved here. Recommend `/ll:spike` to prototype Option A against a real `verify-issue-loop` run and confirm the resulting (weaker) bundle is still useful to a reviewer before committing to full implementation.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-02.

**Selected**: Option A — structural/existence facts only as evidentiary content, LLM verdicts segregated as labeled non-evidentiary context.

**Reasoning**: Option A is the only option that literally satisfies AC3 ("No LLM self-evaluation contributes to the attestation"); Option B directly contradicts it and the MR-1 self-grading doctrine. A live, shipped precedent for the exact evidentiary/non-evidentiary split already exists in production (`count_probes`, `scripts/little_loops/cli/loop/scaffold_verify.py:245`), and Option A's mechanism was already prototyped and validated by this issue's own spike (`scripts/tests/spike/verify_evidence_bundle/`, 7/7 tests passing, including reproducibility and gap-list coverage).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B | 0/3 | 1/3 | 2/3 | 1/3 | 4/12 |

**Key evidence**:
- Winner: the `count_probes` gate (`scaffold_verify.py:245-251`) already ships the same structural-facts-only, non-LLM-verdict pattern in production; `LoopRun` (`history_reader.py:242-256`), `verify_evidence.py`'s git-fact/hash helpers, and `FormatGaps`/`Gap`/`GapAnalysis` each have a direct reusable analog; the spike proves the segregation mechanism holds (no LLM-sourced field ever lands in `evidentiary`).
- Rejected: `evaluate_llm_structured()` (`fsm/evaluators.py:1135-1149`) shows provenance-wrapped LLM output is an established shape, but no precedent packages an LLM verdict as evidentiary content, and doing so would contradict AC3 and MR-1 outright — the issue's own spike built and passed tests enforcing the segregated shape instead.

Note: the spike also surfaced a real product-value tradeoff outside this scoring's scope — the selected bundle shape's evidentiary section contains no pass/fail content, only structural facts (see `## Spike Results`). That is a question of whether the resulting attestation is useful, not of codebase fit, and does not change the selection: AC3 makes the rejected shape non-compliant regardless.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

No implementation module exists yet; the findings below identify where one would live, what it would read, and the conventions already established for exporters of this shape.

### Files to Modify
- No exporter module exists yet. Convention: deterministic, `history.db`-reading CLI exporters live in `scripts/little_loops/cli/artifact/` alongside `dashboard.py`, `extract.py`, `status.py`, `templatize.py`, `policy_builder.py` — a new module there follows that placement convention.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:585` — `archive_run()`: copies `.loops/.running/<instance>.{state.json,events.jsonl}` (+ `summary.json`/`meta-eval.jsonl` if present) into `.loops/.history/<run_id>/` on run completion — the on-disk artifact set the bundle exporter reads. **The archive directory's basename is the `run_id` itself** — `derive_run_id()` (`scripts/little_loops/fsm/executor.py:152-159`) returns `<started_at[:17]>-<loop_name>`, and `archive_run()` uses that string unchanged as the folder name. Earlier passes wrote `<run_id>-<loop_name>`; there is no extra suffix to strip — the exporter passes the directory basename straight to `find_loop_run()`. **Does not copy `probe-*.json`** (see `## Design Review` item 2); must be extended to do so.
- `scripts/little_loops/history_reader.py:2017` — `find_loop_run(run_id, *, db=...) -> LoopRun | None`: the by-`run_id` reader of `loop_runs`; the exporter's sole `history.db` read. `LoopRun` (`history_reader.py:242-256`) is the row dataclass.
- `scripts/little_loops/session_store/writers.py:1472` — `record_loop_run_summary()` writes with **`INSERT OR IGNORE`**. A resumed run keeps its `run_id` (`started_at` is preserved across resume, `executor.py:547-549`), so the second `_finish()` never updates the row: `final_state`/`terminated_by`/`iterations`/`ended_at` reflect the *first* finish (e.g. `interrupted`), not the last. See `## Design Review (third pass)` item 1 and step 3h.
- `scripts/little_loops/fsm/executor.py:1646` — `_prepatch_git(repo_root, args, ok_codes)`: the executor's existing git-subprocess helper (explicit cwd, `capture_output`, 30 s timeout, returns `None` on non-zero/OSError/timeout). Step 3's run-time git capture reuses it rather than adding a second `subprocess.run(["git", ...])` site.
- `scripts/little_loops/cli/loop/run.py:193-200` — sets `${context.run_dir}` to `.loops/runs/<instance_id>/` where `instance_id` is always `<loop_name>-<YYYYMMDDTHHMMSS>` (`_make_instance_id`, `cli/loop/_helpers.py:1547`) — **per-run, keyed by instance id**. The archive dir is keyed by `run_id` (`derive_run_id(started_at, loop_name)`, `fsm/executor.py:152`), a different key. Adversarial-mode `probe-*.json` files (`scaffold_verify.py:217`) and `prepatch_evidence_*.json` (`fsm/executor.py:1838`) are written to run_dir, which is gitignored (`.gitignore:88`) and never pruned or archived. The archived `state.json` carries `context.run_dir` (`persistence.py:1194`), so the original run_dir is locatable from the archive as a fallback, but the files themselves are not in the archive dir the way the original Integration Map and the spike fixture assumed.
- `scripts/little_loops/fsm/executor.py:551` — `_emit("loop_start", {})` emits an empty payload; no git ref is recorded anywhere in the FSM at run time (repo-wide search for `head_sha`/`rev-parse` in `fsm/` returns nothing). See `## Design Review` item 1.
- `scripts/little_loops/session_store/schema.py:563-580` — `loop_runs` table (v23/ENH-2463): `run_id` (unique, matches the archive dir name), `loop_name`, `started_at`, `ended_at`, `final_state`, `iterations`, `terminated_by`, `error`, `evaluator_score`, `diagnostics_path`, `head_sha`, `branch`, `failure_terminal`.
- `scripts/little_loops/session_store/writers.py:1428-1499` — `record_loop_run_summary()`, the sole writer of `loop_runs` rows.
- `scripts/little_loops/fsm/executor.py:3895-3931` — `FSMExecutor._finish()`, the sole production caller of `record_loop_run_summary()`. It supplies only `run_id`/`loop_name`/`started_at`/`final_state`/`iterations`/`terminated_by`/`error`/`failure_terminal`; `evaluator_score`, `diagnostics_path`, `head_sha`, and `branch` are never passed and stay NULL on every live run today. An exporter cannot join `loop_runs` to a commit via these columns as-is — it would need to derive `run_id -> .loops/.history/<run_id>/` itself and compute git facts independently.
- `scripts/little_loops/cli/loop/scaffold_verify.py` — `_criteria_states()` (line 111) and `_adversarial_states()` (line 199) generate the `llm_structured` evaluator states whose verdicts are the loop's primary output; `_aggregate_state()` (line 67) and `count_probes` (line 245) are the loop's only non-LLM (`output_contains`/`output_numeric`) gates, aggregating over `${captured.*.verdict}`. The `FSMLoop(...)` it builds (line 328-335) sets **no `context:`** — neither `issue_id` nor the resolved issue path reaches the run's `state.json`, so today an exporter has nothing but the loop-name slug to join a run back to its issue (see `## Design Review (second pass)` item 2).
- `scripts/little_loops/fsm/executor.py:3478-3488` — `_emit()` spreads the event payload at the **top level** of each `events.jsonl` record (`{"event", "ts", "run_id", "loop", **data}`), and the `evaluate` emit (`executor.py:2798-2805`) spreads `result.details` likewise. This is why the `"llm_model" in event` segregation predicate works; it must not be "fixed" into a nested `details` lookup.
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` carries no source-path attribute (searched `source_path`/`yaml_path`/`loop_path`: no hits), so the executor cannot hash the YAML it is running without `cli/loop/run.py` plumbing the resolved path in.
- `scripts/little_loops/cli/loop/audit.py:85,177` — `resolve_run()`/`audit_run()`: existing reader of the same on-disk run-directory shape (`events.jsonl` + `state.json` + `summary.json`), the closest existing per-run exporter precedent. It does not read `history.db` or git predicates, and does not segregate LLM-produced content today.
- `scripts/little_loops/prepatch_check.py` — fully deterministic (module docstring: "no LLM calls, no FSM or CLI-orchestrator knowledge") evidence-collection precedent; its `PrePatchEvidence` dataclass (`to_dict()` -> `prepatch_evidence.evidence_json`) is the one existing "evidence bundle" term and shape in this codebase, though scoped to test-failure reconstruction only, not acceptance-criterion/adversarial-probe verdicts.

### Conventions in Force
- Report/analysis dataclasses expose a locked-shape `to_dict()` paired with a human-render method, not a custom encoder class — evidence: `CostReport.to_dict()`/`.table()` (`scripts/little_loops/fsm/cost_graph.py:106-139`).
- Incomplete/missing data is modeled as an explicit, enumerable gap list (one `list[str]` field per category plus a derived `has_gaps` property) rather than silent omission — evidence: `FormatGaps` (`scripts/little_loops/issue_parser.py:505-533`, doc'd as a reusable model), `Gap`/`GapAnalysis` (`scripts/little_loops/issue_history/models.py:281-324`).
- Byte-identical reproducibility across renders is achieved by normalizing time-variant inputs (e.g. `gzip.compress(..., mtime=0)`) and proven with a frozen-clock, render-twice-and-diff test — evidence: `scripts/little_loops/cli/artifact/dashboard.py:179-210`, `test_gzip_snapshot_is_reproducible_across_renders` (`scripts/tests/test_feat3304_artifact_dashboard.py:892-919`).
- Canonical/hashable JSON uses the inline idiom `json.dumps(obj, sort_keys=True, default=str)` at each call site — no shared `canonical_json()` helper exists anywhere in the codebase — evidence: `fragment_key()` (`scripts/little_loops/prompts/fragment_store.py:20-32`), `cli/verify_evidence.py:1258`.
- Self-documenting JSON artifacts carry an inline `"_comment"` field naming what the file is, how to regenerate it, and whether it is policy vs. disposable cache — evidence: `write_baseline()` (`scripts/little_loops/cli/verify_evidence.py:1288-1302`) vs. `VerdictCache` (same file, 1144-1261).
- No existing convention labels content "non-evidentiary" or distinguishes LLM- vs. deterministic-origin fields on a record — searched repo-wide for `evidentiary`/`non_evidentiary`, no hits besides this issue's own text. `session_store/schema.py:258-265` documents `summary_nodes` as "LLM-generated" only via a schema *comment*, not a queryable field.
- No `Bundle`-suffixed class exists anywhere in the codebase (searched repo-wide) — the nearest shape precedent is the `Report`-suffixed dataclass family (`CostReport`, `DependencyReport`, `TamperReport`).

### Tests
- `scripts/tests/test_feat3304_artifact_dashboard.py` — golden reproducibility pattern (frozen clock, byte-identical render assertion) directly applicable to AC2 ("re-running the exporter over unchanged inputs produces byte-identical output").
- `scripts/tests/test_prepatch_check.py`, `scripts/tests/test_work_verification.py` — precedent for testing a deterministic evidence dataclass.
- No existing test file covers this exporter (net-new).

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 ("every `check_semantic`/`llm_structured` state pairs with ≥1 non-LLM evaluator... self-grades are unreliable") is the rule this issue's own Motivation cites; it governs how loops must be *authored*, not how a downstream bundle labels LLM- vs. deterministic-origin output — the two are related but distinct problems.
- `docs/reference/API.md`, `docs/reference/CLI.md` — no FEAT-3182-specific section exists yet; a new exporter CLI would need an entry in both.

### Terminology note
- The issue's own `verify-loop`/`adversarial-verify-loop` names predate ENH-2881 (done), which merged the two into the single `verify-issue-loop` skill's `--mode criteria|adversarial` flag (`skills/verify-issue-loop/SKILL.md`, `scripts/little_loops/cli/loop/scaffold_verify.py`). No standalone built-in loop YAML exists under either of the old names. This is a naming drift only — the runs the issue means to capture are per-issue FSM loops generated by `scaffold_verify()` and executed via `ll-loop run`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

No existing types/signatures/call path cover this feature; the findings below trace the current data flow up to the point where a new exporter would attach, and flag one unresolved design question the flow surfaces.

### Types
- No existing `Bundle`-suffixed type exists in this codebase (confirmed by repo-wide search). The nearest shape convention to model a new bundle dataclass on is the `Report`-suffixed family: `CostReport` (`scripts/little_loops/fsm/cost_graph.py:106-139`), `DependencyReport`/`ValidationResult` (`scripts/little_loops/dependency_mapper/models.py:~50-83`), `TamperReport` (`scripts/little_loops/test_tamper_guard.py`) — plain dataclass fields, a locked-shape `to_dict()`, no custom encoder classes.

### Signatures
- `record_loop_run_summary(...)` (`scripts/little_loops/session_store/writers.py:1428-1499`) — accepts `evaluator_score`, `diagnostics_path`, `head_sha`, `branch` but its sole caller, `FSMExecutor._finish()` (`scripts/little_loops/fsm/executor.py:3895-3931`), never supplies them; they default to `None`/NULL on every live `loop_runs` row today.
- `archive_run()` (`scripts/little_loops/fsm/persistence.py:585`) — copies `.loops/.running/<instance>.{state.json,events.jsonl}` (+ `summary.json`/`meta-eval.jsonl` if present) into `.loops/.history/<run_id>/`, keyed by `run_id` matching `loop_runs.run_id`.
- `resolve_run()`/`audit_run()` (`scripts/little_loops/cli/loop/audit.py:85,177`) — existing reader of the identical on-disk run-directory shape; `resolve_run()` is reused directly for run resolution (see CLI surface below); `audit_run()` is a shape precedent only.

### CLI surface (decided in `## Design Review`, 2026-09-02)
- `ll-loop evidence <run-dir-name> | --latest LOOP [--output PATH] [--json]` — new subcommand in `scripts/little_loops/cli/loop/evidence.py`, registered next to `audit` in `cli/loop/__init__.py:980`. Reuses `resolve_run()` from `audit.py:85` verbatim. `ll-artifact` was rejected as the home: its namespace is design/template artifacts (`cli/artifact/__init__.py` docstring), and the bundle's inputs and resolution logic are all `ll-loop`-side.
- `assemble_bundle(loop_runs_row: dict | None, run_dir: Path | None, git_predicates: dict[str, str]) -> EvidenceBundle` — promoted from the spike, with `EvidenceBundle.to_dict()`/`.canonical_json()` and the `EvidenceEntry`/`ContextEntry`/`GapEntry` records unchanged in shape.

### Call Path
`ll-loop run` (`cli/loop/run.py`) -> `FSMExecutor` evaluate loop (`fsm/executor.py`; each `llm_structured` state's verdict written to `state.capture`'d `captured.<key>.verdict` and emitted as an `evaluate` event in `events.jsonl` with LLM-origin fields `reason`/`evidence`/`raw`/`llm_model`/`llm_prompt`) -> `FSMExecutor._finish()` (`executor.py:3895`) -> `record_loop_run_summary()` (`session_store/writers.py:1428`) writes the `loop_runs` row (`head_sha`/`branch`/`evaluator_score`/`diagnostics_path` NULL) -> `archive_run()` (`fsm/persistence.py:585`) copies run-dir artifacts into `.loops/.history/<run_id>/` -> **[bundle exporter, not yet implemented — `ll-loop evidence`]** reads the `loop_runs` row (now carrying run-time `head_sha`/`branch`, step 3) + `.loops/.history/<run_id>/{state.json,events.jsonl,probe-*.json}` (probes archived per step 3a; `loop_start`/`loop_complete` events carrying `head_sha`/`branch`/`worktree_digest`/`loop_yaml_path`/`loop_yaml_sha256`; `state.json` `context.issue_path` from the scaffold, step 3b) + export-time `git` for ref-liveness and `rev-parse <head_sha>:<issue_path>` only -> assembles the bundle.

### Decision Rules
- **Resolved by `/ll:decide-issue` (2026-09-02) — see `## Proposed Solution` → Decision Rationale.** In the current system the loop's *primary output* — the actual pass/fail verdict for each acceptance criterion and each adversarial probe — is itself LLM-graded (`llm_structured` evaluator states, `scaffold_verify.py:111,199`). The only non-LLM gates in the loop (`_aggregate_state()` at `scaffold_verify.py:67`, `count_probes` at `scaffold_verify.py:245`) aggregate *over* those LLM verdicts (`output_contains`/`output_numeric` on `${captured.*.verdict}`); they do not independently establish pass/fail. The bundle treats only structural facts — that a run occurred, which states executed, artifact/probe file existence, counts, git ref/diff state — as evidentiary, with the LLM verdict included only as segregated, labeled-non-evidentiary context. This satisfies AC3 ("No LLM self-evaluation contributes to the attestation"); the resulting attestation is "a check was attempted," not "the check passed" — an accepted, documented tradeoff, not an open question.
- No existing codebase site draws the evidentiary/non-evidentiary line: searched repo-wide for `evidentiary`/`non_evidentiary`, no hits besides this issue's own text; `session_store/schema.py:258-265`'s "LLM-generated" label on `summary_nodes` is prose-only, not a queryable field or established pattern. This determines the exporter's field list (which fields go in the enumerable evidentiary list vs. the segregated context section) and is now decided, not open.
  > ✓ Mechanism proven — `scripts/tests/spike/verify_evidence_bundle/` (7/7 tests) validates evidencing a check whose verdict is itself LLM-graded via structural-facts-only segregation

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

1. The Option A vs. Option B decision (`## Proposed Solution`) is resolved via `/ll:decide-issue` before implementation begins — the exporter's evidentiary field list is not fixed until then.
2. A bundle-shaped dataclass (following the `Report`-suffixed `to_dict()` convention, e.g. `CostReport` at `scripts/little_loops/fsm/cost_graph.py:106-139`) enumerates every entry's deterministic source: the `loop_runs` row (`scripts/little_loops/session_store/schema.py:563-580`), the archived run-directory artifacts under `.loops/.history/<run_id>/` (`scripts/little_loops/fsm/persistence.py:585`), and any adversarial-mode `probe-*.json` files.
3. **Capture git facts at run time, not export time** — see `## Design Review` item 1.
   > ⚠ Superseded — the original step 3 directed the exporter to "derive `head_sha`/`branch` independently at export time"; that attests to whatever HEAD is when the exporter runs, not the tree the loop verified, and is replaced by the run-time capture below. `FSMExecutor.run()` records `head_sha`, `branch`, and a `worktree_digest` (sha256 of `git status --porcelain` + `git diff HEAD` output) alongside the existing `loop_start` event at `scripts/little_loops/fsm/executor.py:551`, and `_finish()` (`executor.py:3895`) passes `head_sha`/`branch` through to `record_loop_run_summary()`, whose columns already exist (`session_store/writers.py:1428-1443`). The exporter reads these as `history_db_row`/`run_dir_file` sources and uses export-time `git` only for ref-liveness predicates (`git cat-file -e <head_sha>`, `git merge-base --is-ancestor <head_sha> HEAD`), reported as `git_ref` entries. A `loop_runs` row with NULL `head_sha` (any pre-existing run) produces a `missing_head_sha` gap.
   - **Git cwd**: all three facts are computed with cwd = `self.working_dir or Path.cwd()` (the executor's own subprocess cwd, `executor.py:271`), never the project root. ll-parallel workers and `worktree:` sub-loops run with cwd set to a worktree (`executor.py:237,662`); the bundle must attest to the tree the loop actually ran against.
   - **Resume**: `run()` re-emits `loop_start` on every resume (`executor.py:551`; `started_at`/`run_id` are preserved at 547-549). The exporter takes the **first** `loop_start` record's facts, and emits a `head_sha_changed_across_resume` gap when any later `loop_start` disagrees.
   - **End-of-run digest**: `_finish()` recomputes `worktree_digest` and adds it to the `loop_complete` payload (`executor.py:3902-3908`). The exporter emits a `worktree_changed_during_run` gap when it differs from the `loop_start` value, so a probe that edited source is distinguishable from a read-only run. A single start-time digest cannot detect this.
   - **Digest scope (documented limitation)**: `git status --porcelain` lists untracked *names* only and `git diff HEAD` excludes untracked *content*, so the digest is a tracked-content digest — a probe that edits an untracked file leaves it unchanged. Documented in the bundle's `_comment` and API docs as `worktree_digest` covering tracked files plus untracked names; not extended to untracked content in this issue. `.loops/` is gitignored (`.gitignore:85-90`), so the run's own artifacts never perturb the digest.
   - **Git helper and failure mode**: all git calls go through the existing `_prepatch_git()` (`executor.py:1646`; explicit cwd, 30 s timeout, `None` on any failure). Outside a git repo, or on any git failure, every fact is `None` — no exception, no stderr, and the `loop_start` payload carries the keys with `null` values so the exporter's `missing_head_sha` gap fires rather than a `KeyError`.
   - **Capture is opt-in via a constructor kwarg** (`FSMExecutor(..., capture_git_facts: bool = False)`); `cli/loop/run.py` passes `True`. Rationale: the test suite constructs `FSMExecutor` ~470 times, most with `working_dir=None` (cwd = this checkout), and five git subprocesses per run at 5–25 ms each would add tens of seconds serially while attesting to the developer's dirty tree. The exporter treats a run without the keys as `missing_head_sha`, identical to a pre-existing run.
3a. Extend `archive_run()` (`fsm/persistence.py:585`) to copy `probe-*.json` and `prepatch_evidence_*.json` from `run_dir` into the archive dir, so the bundle reads only from `.loops/.history/<run_id>/`. A run archived before this change produces a `missing_probe_files` gap, not a silent zero count. (Rationale corrected: run_dir is per-instance and never overwritten — `cli/loop/run.py:193-200` — but it is keyed by instance id, not `run_id`, is gitignored, and is never archived or pruned; see `## Design Review (second pass)` item 1.)
3b. Add the *verified criteria* as evidentiary entries: the loop YAML that ran and the issue file it verified. **Both are captured at run time, not resolved at export time**:
   - `cli/loop/run.py` already resolves the YAML path (via `fsm/loop_paths.py`) before constructing the executor; it passes that path through so the `loop_start` payload carries `loop_yaml_path` + `loop_yaml_sha256`. `FSMLoop` has no source-path attribute, so this is a `run.py` → executor plumb (constructor kwarg or `context` key), not a schema change. Hashing at export time is wrong because `ll-loop scaffold-verify` regenerates the same file on every invocation.
   - `scaffold_verify()` (`scaffold_verify.py:328-335`) sets `context: {issue_id: <ID>, issue_path: <repo-relative path>}` on the generated `FSMLoop`, so both land in the archived `state.json` `context` (`persistence.py:1194`). The exporter reads `issue_path` from there and computes `git rev-parse <head_sha>:<issue_path>` as a `git_ref` entry. Runs whose `state.json` has no `issue_path` produce a `missing_issue_path` gap; an issue file that is untracked or uncommitted at `head_sha` (the common case for a freshly captured issue) produces an `issue_not_committed_at_head` gap, with the export-time working-tree sha256 of the file recorded as a separate, clearly labeled `run_dir_file`-sourced entry rather than as the blob hash.
3c. The expected probe count is read from the archived `state.json`/loop YAML (number of `probe-*` states), not the literal `3` the spike hard-codes; criteria mode has zero probe files and that is not a gap. **Zero probe files in adversarial mode is a `missing_probe_files` gap** — the spike's `if probe_files and len(probe_files) < 3` guard silently passes the zero case and must not be promoted as-is.
3d. **Evidentiary `loop_runs` fields are an explicit allowlist**, not a column dump. The spike copies every row column into `evidentiary`; `error` (free text, may embed host/LLM output) and `evaluator_score` (semantics unpinned, indexed at `session_store/schema.py:573,580`) are not guaranteed deterministic in origin. Allowlist: `run_id`, `loop_name`, `started_at`, `ended_at`, `final_state`, `iterations`, `terminated_by`, `failure_terminal`, `head_sha`, `branch`. `error` and `evaluator_score` go to `context_non_evidentiary` when non-NULL.
3e. The bundle's top level carries `schema_version` (int, starting at 1) and a `_comment` string naming the file, the regenerating command (`ll-loop evidence <run>`), and that the file is evidence, not cache — per the self-documenting-JSON convention in `## Integration Map` → Conventions in Force (`write_baseline()`, `cli/verify_evidence.py:1288-1302`). Neither is present in the spike shape. No timestamp field: reproducibility (step 4) forbids it.
3f. CLI output contract: `ll-loop evidence <run>` prints a short human summary (run id, head_sha, evidentiary entry count, gap list) to stdout by default; `--json` prints the canonical bundle JSON to stdout; `--output PATH` writes the canonical bundle JSON to PATH regardless of `--json`. Mirrors `ll-loop audit`'s default/`--json` split.
3g. On promotion, delete `scripts/tests/spike/verify_evidence_bundle/`. Its `test_spike_does_not_import_production_session_store_or_fsm` guard is by construction contradicted by the production module, and keeping both is duplicate maintenance. The seven behavioral tests move to the new test module (step 7) with the fixture rebuilt to match the extended `archive_run()` layout.
3h. **Resumed runs: cross-check the `loop_runs` row against the last `loop_complete` event.** `record_loop_run_summary()` writes `INSERT OR IGNORE` (`session_store/writers.py:1472`) and a resumed run reuses its `run_id`, so the row holds the *first* finish's `final_state`/`terminated_by`/`iterations`/`ended_at`/`head_sha`/`branch`. The exporter reads the **last** `loop_complete` record in `events.jsonl` as the authoritative end-of-run fact (a `run_dir_file` entry) and emits a `loop_runs_row_stale` gap when the row's allowlisted fields disagree with it; the row is still included, labeled with its source. A run with no `loop_complete` event at all (killed, or archived by a stale-run sweep) yields a `missing_loop_complete` gap. The writer is **not** changed to upsert — that is an ENH-2463 semantics change outside this issue.
3i. **Run resolution**: `ll-loop evidence <run>` takes the archive directory basename, which *is* the `run_id` (`derive_run_id`, `executor.py:152-159`); the exporter passes it unchanged to `find_loop_run()` (`history_reader.py:2017`). No suffix stripping. `--latest LOOP` reuses `resolve_run()`'s suffix match.
3j. **Sequencing**: land the executor/persistence/scaffold prerequisites before the exporter, each as its own commit with its own test — (i) step 3 git-fact capture + `record_loop_run_summary` pass-through, (ii) step 3a `archive_run()` probe copying, (iii) step 3b scaffold `context:` + `run.py` YAML-path plumbing, then (iv) the `ll-loop evidence` exporter and step 3g spike removal. After (i), spot-check the five `loop_start`/`loop_complete` readers named in `## Confidence Check Notes` (`cli/logs.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`, `cli/loop/audit.py`, `analytics/variance.py`).
4. Re-running the exporter over an unchanged `loop_runs` row and an unchanged archived run directory produces byte-identical output — verified the way `test_gzip_snapshot_is_reproducible_across_renders` (`scripts/tests/test_feat3304_artifact_dashboard.py:892-919`) verifies it: freeze the clock, render twice, assert equality.
5. A `loop_runs` row whose archived run directory no longer exists (or the reverse) produces an explicit, enumerable gap entry in the bundle rather than a bundle that silently omits it — following the enumerable-gap-list convention (`FormatGaps`, `scripts/little_loops/issue_parser.py:505-533`; `Gap`/`GapAnalysis`, `scripts/little_loops/issue_history/models.py:281-324`).
6. The exporter's output requires no little-loops-specific decoding — plain JSON with no custom encoder classes, matching `ll-session export` (`scripts/little_loops/cli/session.py:925-945`) and `ll-artifact dashboard` (`scripts/little_loops/cli/artifact/dashboard.py`).
7. Coverage: a new test module (none currently exists for this exporter) asserts reproducibility (step 4) and gap reporting (step 5) against a fixture `loop_runs` row and archived run directory; `python -m pytest scripts/tests/` passes.

## Acceptance Criteria

- Bundle contents are enumerable, and each entry traces to a deterministic source (git ref/diff, `history.db` row, or run-directory file).
- **Reproducible**: re-running the exporter over unchanged inputs produces byte-identical output.
- Any LLM-produced content included for context is segregated and labeled non-evidentiary.
- A run whose evidence is incomplete produces an explicit gap list rather than a bundle that looks complete.
- The bundle is readable without little-loops installed — it is evidence, not a proprietary format.
- The bundle's `head_sha`/`branch`/`worktree_digest` are the values recorded at `loop_start` by the executor, never computed at export time; a run without a recorded `head_sha` yields a `missing_head_sha` gap.
- Adversarial-mode `probe-*.json` files are archived by `archive_run()` and read from the archive dir; a run archived without them yields a `missing_probe_files` gap rather than a zero count.
- The bundle includes the sha256 of the loop YAML that ran and the blob hash of the issue file at the recorded `head_sha`. Both the YAML path/hash and the issue path are captured at run time (`loop_start` payload and scaffolded `context:` respectively), never resolved at export time; an issue file not committed at `head_sha` yields an `issue_not_committed_at_head` gap.
- Git facts are computed with the executor's cwd (`working_dir` or process cwd), so a run inside an ll-parallel or `worktree:` worktree attests to that worktree's HEAD. A resumed run with a differing later `loop_start` SHA yields a `head_sha_changed_across_resume` gap.
- `worktree_digest` is recorded at both `loop_start` and `loop_complete`; a mismatch yields a `worktree_changed_during_run` gap.
- Zero `probe-*.json` files in adversarial mode is a `missing_probe_files` gap; zero in criteria mode is not a gap.
- Evidentiary `loop_runs` fields are an explicit allowlist (step 3d); `error` and `evaluator_score` never appear in `evidentiary`.
- The bundle carries `schema_version` and `_comment` at the top level and no timestamp.
- CLI: `ll-loop evidence <run> | --latest LOOP [--output PATH] [--json]` — human summary by default, canonical JSON with `--json`/`--output` — documented in `docs/reference/CLI.md`; `assemble_bundle`/`EvidenceBundle` documented in `docs/reference/API.md`.
- `scripts/tests/spike/verify_evidence_bundle/` is removed on promotion; its behavioral tests live in the new production test module.
- A resumed run whose `loop_runs` row disagrees with the last `loop_complete` event yields a `loop_runs_row_stale` gap; a run with no `loop_complete` event yields `missing_loop_complete`. The last `loop_complete` event is the evidentiary end-of-run fact; `record_loop_run_summary()` keeps `INSERT OR IGNORE`.
- Run-time git capture is opt-in (`capture_git_facts` kwarg, enabled only by `ll-loop run`), goes through `_prepatch_git()`, and outside a git repo produces `null` facts with no exception or stderr. The default test suite's executor construction count and wall time are unchanged by the capture (no git subprocess when the kwarg is off).
- `worktree_digest`'s tracked-content-plus-untracked-names scope is stated in the bundle `_comment` and in `docs/reference/API.md`.
- The exporter resolves the `loop_runs` row via `find_loop_run(<archive dir basename>)` with no suffix manipulation.

## Design Review

_2026-09-02, pre-implementation review of the refined/decided/spiked issue. Option A stands; the following corrections to the Integration Map and Implementation Steps are folded in above._

1. **Git facts were going to be wrong.** Nothing in the FSM records HEAD (`_emit("loop_start", {})` at `fsm/executor.py:551`; `_finish()` never passes `head_sha`/`branch`). Step 3 originally said "derive `head_sha` independently at export time" — that attests to whatever HEAD is when the exporter runs, not the tree the loop verified. Fixed: record at `loop_start`, pass through `record_loop_run_summary()` (columns already exist), plus a `worktree_digest` so a dirty-tree run is distinguishable from a clean one. Export-time `git` is limited to ref-liveness predicates.
2. **`probe-*.json` is not in the archive dir.** `archive_run()` copies only `state.json`/`events.jsonl`/`meta-eval.jsonl`/`summary.json`. The spike fixture placed probes inside the archive dir, which never happens in production. Fixed: extend `archive_run()` (step 3a); pre-existing runs produce a gap.
   > ⚠ Superseded — this item originally described `${context.run_dir}` as `.loops/runs/<loop_name>/`, per-loop and overwritten on rerun. It is per-instance (`<loop_name>-<timestamp>`); see `## Design Review (second pass)` item 1 for the corrected rationale.
3. **The verified criteria were absent from the bundle.** "Which states executed" is unreadable without the loop YAML and the issue text they were generated from. Fixed: step 3b adds both as hashed evidentiary entries.
4. **CLI surface was still unnamed** despite the 2026-08-28 note requiring it. Fixed: `ll-loop evidence`, reusing `resolve_run()`; `ll-artifact` rejected (design-artifact namespace).
5. **Expected probe count was a literal `3`** in the spike. Fixed: step 3c.
6. Accepted as-is: the spike labels every `captured.*.verdict` as LLM-sourced, including the deterministic `count_probes`/`_aggregate_state` captures. This is the conservative direction for AC3 and the bundle recomputes the probe count itself; the segregation predicate on `events.jsonl` (`"llm_model" in event`, confirmed present in `evaluate_llm_structured` details at `fsm/evaluators.py:1144`) should additionally accept `type in {"llm_structured", "check_semantic"}` so a future evaluator that omits `llm_model` still segregates.

Re-run `/ll:confidence-check` after these land in the plan; the prior outcome score (67 vs. threshold 65) was depressed by items 1 and 2.

## Design Review (second pass)

_2026-09-02, pre-implementation review after the first Design Review landed. Option A and the readiness verdict stand; every citation in the Integration Map was re-verified against the working tree. Corrections and additions are folded into `## Integration Map`, `## Implementation Steps` (3, 3a–3g), and `## Acceptance Criteria`._

1. **First-pass item 2 misdescribed `run_dir`.** It is not `.loops/runs/<loop_name>/` and is not overwritten on rerun: `cli/loop/run.py:193-200` always derives `<loop_name>-<timestamp>` via `_make_instance_id`. The actual defect is that run_dir is keyed by instance id while the archive is keyed by `run_id`, run_dir is gitignored, and nothing archives or prunes it. Step 3a is unchanged; its rationale is corrected. The archived `state.json` carries `context.run_dir`, which the exporter may use as a fallback locator for pre-3a runs before declaring `missing_probe_files`.
2. **The exporter had no way to find the issue.** `scaffold_verify()` sets no `context:` on the generated loop, so `issue_id`/`issue_path` never reach `state.json`, and step 3b's `git rev-parse <sha>:<issue_path>` had no path to use. Fixed: scaffold emits `context: {issue_id, issue_path}`; gaps `missing_issue_path` and `issue_not_committed_at_head` defined.
3. **The loop YAML hash was computed at the wrong time.** Step 3b hashed the YAML at export via `loop_paths.py`; `scaffold-verify` regenerates that file, so the export-time hash can differ from what ran. `FSMLoop` has no source-path attribute. Fixed: `run.py` plumbs the resolved path into the executor, which records path + sha256 in `loop_start`.
4. **One `worktree_digest` cannot detect a tree changed mid-run.** Fixed: `_finish()` recomputes it into `loop_complete`; mismatch is a `worktree_changed_during_run` gap.
5. **Git cwd and resume were unspecified.** `head_sha` must come from `self.working_dir or Path.cwd()` (ll-parallel workers and `worktree:` sub-loops run in worktrees, `executor.py:237,662`), and `run()` re-emits `loop_start` on resume. Fixed: first-`loop_start`-wins rule plus `head_sha_changed_across_resume` gap.
6. **Spike dumped every `loop_runs` column into `evidentiary`.** `error` and `evaluator_score` are not deterministic in origin. Fixed: allowlist in step 3d.
7. **Spike's probe gap missed the zero case** (`if probe_files and len(...) < 3`). Fixed in 3c.
8. **Bundle shape lacked `schema_version`/`_comment`**, contradicting the issue's own conventions list. Fixed: 3e.
9. **`[--json]` was ambiguous** for an output that is already JSON. Fixed: 3f pins summary-by-default, JSON with `--json`/`--output`.
10. **Segregation predicate depends on event flattening.** `_emit()` (`executor.py:3478-3488`) spreads payload and evaluator `details` at the top level of each `events.jsonl` record, which is why `"llm_model" in event` works. Documented in the Integration Map so it is not refactored into a nested lookup.
11. **Spike disposition was undefined.** Fixed: 3g deletes the spike dir on promotion.
12. `docs/reference/API.md` was named in the Integration Map but absent from the ACs. Added.

## Design Review (third pass)

_2026-09-02, pre-implementation review after the second pass. Option A and the readiness verdict stand; every Integration Map citation re-checked against the working tree. Corrections folded into `## Integration Map`, `## Implementation Steps` (3, 3h–3j), and `## Acceptance Criteria`._

1. **Resumed runs left a stale evidentiary row.** `record_loop_run_summary()` is `INSERT OR IGNORE` (`writers.py:1472`) and `run_id` survives resume, so the row attests to the first partial finish. Fixed: step 3h — last `loop_complete` event is authoritative, `loop_runs_row_stale`/`missing_loop_complete` gaps, writer unchanged.
2. **Run-time git capture would have hit the whole test suite.** ~470 `FSMExecutor(` constructions in `scripts/tests/`, mostly with `working_dir=None`; five git subprocesses per run against this checkout. Fixed: opt-in `capture_git_facts` kwarg, `_prepatch_git()` reuse, explicit not-a-repo behavior (step 3).
3. **`worktree_digest` cannot see untracked-file content.** Accepted and documented as a tracked-content digest rather than extended (step 3).
4. **Archive dir name was described as `<run_id>-<loop_name>`.** It is `<run_id>` — `derive_run_id()` already embeds the loop name, and it lives in `fsm/executor.py:152`, not `persistence.py`. `find_loop_run()` (`history_reader.py:2017`) was never cited as the row reader. Fixed: Integration Map, step 3i.
5. **Format gates were failing** (`fmt: ✗`): `count_probes` appeared only in Option B's paragraph and the Selected callout, so `unapplied_decision` computed it as a rejected-only identifier; first-pass item 2 was corrected but not marked superseded; FEAT template sections were missing; old loop-YAML names read as file paths. All fixed in place.
6. **Prerequisite changes were unsequenced.** Fixed: step 3j orders four independent commits and names the downstream event readers to spot-check.

Verified sound, no change: `events.jsonl` is opened append-mode (`persistence.py:221`), so first-`loop_start`-wins holds across resume; every executor exit path returns through `_finish()`, so `loop_complete` is always emitted on a normal exit; `FSMLoop.context` (`fsm/schema.py:1386`) exists and round-trips through `dump_fsm_yaml`, so the scaffold change in step 3b is a one-line addition.

## Impact

- **Priority**: P3 — audit-evidence for agent-produced changes; valuable but no active consumer is blocked on it.
- **Effort**: Medium — four small prerequisite commits (executor payload, `archive_run()`, scaffold context, `run.py` plumbing) plus a net-new exporter module and test module.
- **Risk**: Low-Medium — prerequisite changes are additive fields on dict-based event readers; the exporter is read-only.

## Status

**Open** | Created: 2026-08-15 | Priority: P3

## Notes

_2026-08-28, unparented-issues review:_ downgraded P2 → P3 and parented under
EPIC-2087 (Loop Harness Quality & Evaluation Tooling). The motivation and ACs
are sound, but the issue has had no refine/wire/confidence pass — no proposed
solution, no integration map, no file references. **Run `/ll:refine-issue
FEAT-3182` before scheduling implementation**; at minimum it must identify the
verify-loop run artifacts and `history.db` tables the bundle draws from, and
the exporter's CLI surface.


## Spike Results

_Added by `/ll:spike` on 2026-09-02_

Plan: `.ll/spikes/spike-FEAT-3182.md`. Spike location: `scripts/tests/spike/verify_evidence_bundle/`.

**Retired risks**

| Risk (from Program Design → Decision Rules / Proposed Solution) | Proven by | Result |
|---|---|---|
| No precedent distinguishing LLM- vs. deterministic-origin fields on a bundle | `test_llm_sourced_fields_never_land_in_evidentiary` | ✓ pass |
| AC1: enumerable, source-traced evidentiary entries | `test_every_evidentiary_entry_traces_to_deterministic_source` | ✓ pass |
| AC2: reproducible across reruns of unchanged inputs | `test_rerun_over_unchanged_inputs_is_byte_identical` | ✓ pass |
| AC4: incomplete evidence produces an explicit gap, not a silently smaller bundle | `test_missing_run_dir_produces_explicit_gap_not_silent_bundle`, `test_missing_loop_runs_row_produces_explicit_gap` | ✓ pass |
| AC5: readable without little-loops installed (plain JSON, no custom types) | `test_bundle_is_plain_json_no_custom_types` | ✓ pass |
| Isolation guard | `test_spike_does_not_import_production_session_store_or_fsm` | ✓ pass |

**Verification**: 7 spike tests pass + 37 tests pass across 2 named regression suites (3 commands total, all exit 0):
```
python -m pytest scripts/tests/spike/verify_evidence_bundle/ -v            # 7 passed
python -m pytest scripts/tests/test_feat3304_artifact_dashboard.py -v -k reproducible   # 1 passed
python -m pytest scripts/tests/test_prepatch_check.py -v                   # 36 passed
```

**Empirical finding (the question this spike was scoped to answer)**: the segregation mechanism itself works cleanly — no LLM-sourced field ever leaks into `evidentiary`, and reruns are byte-identical. But the rendered sample bundle (`driver.py`, run against the fixture) shows the tradeoff the issue's `## Proposed Solution` named is real, not hypothetical: `evidentiary` contains only structural facts (git ref, `loop_runs` row fields, file hashes, a probe count of 3) — **no pass/fail content anywhere in that section**. Both criterion outcomes ("yes"/"yes") exist only in `context_non_evidentiary`, explicitly labeled `llm_sourced: true`. A reviewer reading only the evidentiary section of an Option A bundle cannot tell whether the check passed — only that a run occurred, produced expected artifacts, and ran 3 probes. This is consistent with the issue's own framing ("a check was attempted" vs. "the check passed") and should inform `/ll:decide-issue`'s choice between Option A and Option B rather than being treated as a spike failure — the mechanism works exactly as designed; whether that weaker attestation is still useful is the actual decision to make.

**Promotion**: move to `scripts/little_loops/cli/loop/evidence.py` (decided in `## Design Review`; `cli/artifact/` rejected), wired to real `history.db` reads, then delete the spike dir (step 3g). Note the spike fixture's probe-file placement inside the archive dir does not match production until step 3a lands — the promoted test fixture must build the archive dir the way the extended `archive_run()` does. Do not promote the spike's `loop_runs` column dump, the `len < 3` probe guard, or the bare `{evidentiary, context_non_evidentiary, gaps, has_gaps}` top level as-is; see `## Design Review (second pass)` items 6–8.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-02_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Criterion 4 (Issue Well-Specified) capped at 10/20: `format-check`'s `stale_cli_flag` flags `ll-loop evidence (no such subcommand)` — expected for a not-yet-implemented CLI surface, not a real specification gap.
- Criterion C (Ambiguity) capped at 10/25: `unapplied_decision` flags "Program Design still specifies `count_probes` (rejected option)". This reads as a likely false positive — `count_probes` is cited in `## Proposed Solution` → Decision Rationale as supporting evidence for the *winning* Option A, not as a rejected option's identifier left unmarked. Worth a quick look before trusting the cap, but not escalated to a blocking gap per policy.

### Outcome Risk Factors
- Change surface (18/25): `FSMExecutor`'s `loop_start`/`loop_complete` event payload changes (Implementation Steps 3, 3a) are read by 5 downstream consumers (`cli/logs.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`, `cli/loop/audit.py`, `analytics/variance.py`). Additive fields are low-risk for these dict-based readers, but this is not a fully isolated change — spot-check them after landing the executor changes.
- Ambiguity (10/25, capped): see Concerns above — the `unapplied_decision` gap on `count_probes` caps this criterion regardless of the otherwise-low ambiguity in this issue.

## Session Log
- `/ll:confidence-check` - 2026-09-02T19:11:42 - `3a147a77-c572-4741-8be9-efbfc5354c69.jsonl`
- `/ll:confidence-check` - 2026-09-02T18:25:12 - `84e0bbf3-d0f7-4d45-a3b6-ea9216ba3165.jsonl`
- `/ll:confidence-check` - 2026-09-02T18:04:39 - `816beb27-9b86-42b0-9b64-63f61826d1c0.jsonl`
- `/ll:confidence-check` - 2026-09-02T17:52:11 - `852881be-b9ae-4653-91cb-48f6a2940c2a.jsonl`
- `/ll:decide-issue` - 2026-09-02T17:43:55 - `b56fa4ef-4a26-4110-aa7f-162711184ed7.jsonl`
- `/ll:spike` - 2026-09-02T17:34:43 - `31beec40-f765-410a-8519-571661ae2696.jsonl`
- `/ll:refine-issue` - 2026-09-02T17:19:59 - `2cfeb4de-9401-4270-a496-a50f1f1de3d7.jsonl`
