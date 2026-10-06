---
id: FEAT-3716
type: FEAT
title: 'Loop portability tiers: classify ecosystem dependencies in ll-loop validate,
  list and show'
priority: P3
status: open
decision_needed: false
reconcile_attempted: true
discovered_by: portability-review
discovered_date: '2026-10-03'
captured_at: '2026-10-03T22:42:15Z'
labels:
- loops
- validation
- portability
relates_to:
- FEAT-2248
- EPIC-3581
- FEAT-2354
- FEAT-3717
blocks:
- FEAT-3717
learning_tests_required:
- pyyaml
---

# FEAT-3716: Loop portability tiers: classify ecosystem dependencies in ll-loop validate, list and show

## Summary

Classify a loop's detected little-loops plugin and Issue-system requirements, including resolved fragments, inheritance and static child loops. Surface a consistent report in `validate`, `list` and `show`, with a declared tier checked by the validator. Keep independent requirement sets beneath the three display tiers; `requires-issues` does not imply that the plugin is installed or needed.

This issue supplies the resolution/report contract consumed by FEAT-3717. "Portable" means no detected little-loops plugin or Issue-system coupling. It does not certify arbitrary shell programs, credentials, network access, helper scripts, host capabilities or an entire runtime environment.

## Current Behavior

- There are no `portability` or `adapter` fields in `FSMLoop`/`StateConfig` or the loop schema. No current catalog entry has a portability report.
- `load_and_validate` resolves YAML through `resolve_inheritance` → `resolve_flow` → `resolve_fragments` before parsing. Imported/inherited actions therefore count; descriptions and YAML comments do not.
- `resolve_loop_path` checks a literal path in the working directory before project `.fsm.yaml`/`.yaml` files, built-ins, then generator drafts. Child execution uses the shared runtime `loops_dir`; inheritance supplies each ancestor's source directory as its named-lookup root, still after cwd literals. Imports use the final consumer directory without a cwd-literal step. The current filesystem validation rules use `path.parent` for child lookup, so they can disagree with runtime for nested loops.
- `_validate_with_bindings` calls full child validation and catches all exceptions. A cycle with `with:` bindings repeatedly reloads children even if the new classifier itself has a visited set. Binding checks need resolve-only child contracts too.
- Inheritance parents can be partial mappings, not independently runnable loops. Overridden parent actions and unused library fragments are absent from the final executable definition. The same source reached through two symlink paths can also resolve different consumer-relative fragment libraries.
- Catalog enumeration currently accepts only `loops_dir`, while MCP's `loop_list` is anchored to a separately supplied `project_root`. Cwd-first dependency lookup can therefore select a different source from a CLI launched in that project. `list --running`/`--all-runs`/`--status` use a separate saved-run branch with no catalog analysis.
- `is_runnable_loop` checks resolved required fields, not the proposed declarations/markers. Inheritance/fragment expansion currently retains no winning-field source provenance; a file-read trace alone cannot identify which ancestor supplied a declaration.
- `ValidationSeverity` has only ERROR/WARNING. A portability report is informational data, not a new severity.
- `agent: loop-specialist` is used by shipped prompt states without any `/ll:` token. `ll-history` is wheel-installed but reads issue history, defaulting to `.issues`; wheel membership is not proof of ecosystem independence.
- Brainstorm currently has unconditional `scope: [ ..., ".issues/", ... ]`. This is a concurrency reservation, not an Issue-system prerequisite: `LockManager` normalizes the path without requiring or creating it and stores its locks under `.loops/.running`. Preserve the reservation so optional issue sinks remain protected from concurrent writers.

## Expected Behavior

| Display tier | Core requirements |
|---|---|
| `portable` | Neither plugin nor issues |
| `requires-plugin` | Plugin, without issues |
| `requires-issues` | Issues, with plugin also reported separately if present |

The ordered display rank remains `portable < requires-plugin < requires-issues`. The stored sets are authoritative for prerequisites and export allowances.

A report carries core and adapter requirements separately, with completeness for each. Dynamic/unreadable child dependencies produce unresolved evidence and an incomplete channel; "unknown" is a display outcome, not a fourth declared tier. A loop with known issue coupling and an unresolved child retains both facts rather than losing the known requirement.

`ll-loop list --portability portable` includes only complete, portable cores. An optional adapter does not raise the core tier, and unknown adapters remain visible. FEAT-3717 applies the stricter rule that the whole exported YAML graph, including adapters, must be statically closed.

## Proposed Solution

### One resolution contract

Add a small resolve-only graph helper in `fsm/loop_dependencies.py`:

`resolve_loop_graph(root_file: Path, *, loops_dir: Path, cwd: Path, resolution_context: LoopResolutionContext | None = None) -> LoopDependencyGraph`.

Executable nodes are the requested root and statically referenced children. Each loads YAML using the existing inheritance, flow and fragment helpers; successful nodes make a parsed `FSMLoop` available to consumers, while failed children retain the outcomes below. Keep raw source records for inheritance parents and libraries separately: a partial parent must not be forced through `FSMLoop.from_dict`, and a `from`/`import` edge alone must not make its source an executable node. Classify the final consumer's resolved states; overridden ancestor actions and unused fragments contribute no requirements. A parent requested separately as a runnable root has its own report. The helper does not run validators, load config, interpolate actions, select a host, or execute anything. Move/reuse the common resolve-only loading steps rather than making a second subtly different loader.

Distinguish requested-root failures from child failures. A failure in the root's read/parse/inheritance/flow/fragment expansion/dataclass parsing prevents constructing its FSM and propagates through the existing load-error API; `validate --json` keeps its early-error shape. A static child's lookup/read/parse/expansion failure is instead retained as typed graph failure data, including the failing stage, source/reference and lookup trace, plus any already-read snapshots. The parsed root, successful siblings and their evidence remain available. Attribute unresolved evidence to every referencing state/channel; a failing ancestor/library needed by a child is a child failure relative to the requested root. Cache selected-source failures by the same context key as successful nodes; a lookup miss has no source identity and is keyed by its reference and lookup context, not by a shared `None` key. Catch only expected I/O/YAML/documented load failures at this seam, not arbitrary programming exceptions. Recognized authored-data shape/type errors must become documented load failures at the shared parsing seam; do not blanket-catch every `TypeError`/`KeyError` from arbitrary code. When the failed child is requested directly, its failure is an ordinary root load error. Inheritance cycles remain expansion failures; resolved `loop:` back-edges are graph revisits.

Have the existing lookup/loading primitives emit the same typed resolution events to both graph analysis and runtime loading (candidate paths, chosen path and lookup mode). Record dependency edges with kind (`from`, `import`, `loop`), authored reference, consumer, resolved source and resolution mode. Record every YAML file read, including inherited ancestors and libraries, retaining its original byte snapshot and digest so FEAT-3717 can copy exactly the analyzed bytes. Parse from that snapshot; do not reconstruct bytes from normalized text/YAML or replace the snapshot during a later source recheck. Use an optional per-operation context/recorder through the resolver helpers; no process-global cache, working-directory changes, or filesystem writes. FEAT-3717 consumes this trace; there is no need to add source/path fields to `FSMLoop`.

Graph analysis and its lookup/read/expansion/classification helpers emit no prints or logs, including on expected child failures. In recorded analysis mode, retain duplicate-draft ambiguity and skipped candidates in the lookup trace rather than printing `resolve_loop_path`'s existing Note; default runtime lookup keeps that diagnostic. Use an explicit resolver option/recorder policy, not global stdout/stderr redirection. Catalog/MCP render only their result; validate renders the requested root's collected diagnostics once. Warning-bearing children are not recursively validated or logged merely to classify them.

Cache raw reads by canonical source identity, but key resolved executable nodes by source **and the loader-visible consumer directory** within the explicit cwd/shared-loop-root context. Do not canonicalize away the directory used for relative imports. Two symlink aliases to the same YAML can resolve different libraries and must remain distinct analysis nodes. An operation-owned `LoopResolutionContext` exposes resolved graphs/reports to CLI consumers and is optionally accepted by `load_and_validate`/`resolve_loop_graph`; supplied contexts must agree on cwd and runtime root. This supplies report reuse without changing the loader's 2-tuple return or attaching hidden report fields to `FSMLoop`.

Capture cwd once per operation. Anchor relative `root_file`/`loops_dir` paths to that cwd without resolving away symlink consumer directories. With a supplied context, omitted `load_and_validate` cwd/root arguments inherit its bases; explicit contradictory bases are rejected before reading. Extend `enumerate_loop_catalog` with optional keyword-only `cwd`, defaulting to the captured `Path.cwd()` for CLI callers. MCP `loop_list` passes `cwd=project_root`, including when its configured loop directory is outside the usual `.loops/` location. Its report describes CLI execution from that project root, not from the MCP server's process directory. Never infer cwd from `loops_dir.parent` or change process cwd. This is catalog analysis wiring, not a change to detached MCP `loop_start` execution.

Use the resolver's optional recorder to retain a narrow winning-field provenance sidecar for `portability`, `ecosystem_requires` and each resolved state's `adapter`. Update it at the actual inheritance/fragment merge, including state overrides and explicit-empty list resets; do not replay merge precedence in the classifier. An inherited marker remains inherited when a child overrides only that state's action. Keep these records outside `FSMLoop` and serialized YAML; recorder omission preserves existing resolved content. Declaration evidence and raw-field diagnostics cite the winning authored source, with fragment identity when applicable. This is not a general YAML source-map feature.

Cached raw snapshots, resolved templates and reports are analysis-owned. Return a defensive copy of the parsed FSM and any raw spec at mutating-consumer boundaries; their nested context/bindings must not alias the cache or another returned FSM. `FSMLoop.from_dict` currently reuses the input `context` dictionary, so merely reparsing a cached mapping is insufficient. Preserve YAML alias relationships within an individual copy. Runner context injection, child binding and caller mutation must not change later reports, source-parity comparisons or another root's defaults. Cache lifetime ends at the analysis/load operation (one CLI invocation or one MCP request); do not retain it across MCP requests, child executions or a long-running/resumed executor. Each actual child invocation still reloads its current definition. This is an operation-local ownership rule, not a new immutable public FSM API; cached expansion/parsing and bounded file reads remain reusable.

Resolution follows the existing precedence with an explicit working-directory and runtime-loop-root context:

- Child `loop:` references resolve against the shared runtime `loops_dir`, including project overrides and cwd-first literal lookup, matching `FSMExecutor._execute_sub_loop`.
- `from:` uses the same cwd-literal-first `resolve_loop_path` precedence, then each ancestor's own source directory for the `.fsm.yaml`/`.yaml` candidates, followed by built-ins and drafts. The analyzer substitutes explicit cwd for process cwd without changing this existing priority; a cwd literal can shadow an ancestor-relative parent.
- After inheritance merging, the effective `import:` list resolves against the final consumer's directory. It is not resolved against whichever ancestor originally wrote the list.
- Fragment imports keep consumer-directory-then-built-in lookup; they have no cwd-literal step. Record the actual resolver's candidate/chosen paths rather than applying one uniform path policy to all edge kinds.
- Fragment-library `import:` keys are not recursive today. Do not add nested-library semantics here or in FEAT-3717.
- Dynamic children are unresolved edges. Missing/malformed/unreadable static children produce incomplete reports with actionable source/state evidence; an existing missing-reference ERROR must not be duplicated.

Thread optional keyword-only runtime `loops_dir`, cwd and operation context through `load_and_validate` and its filesystem child-reference/binding helpers, defaulting to `path.parent`/`Path.cwd()` for existing callers. CLI run/resume/validate/show, catalog and child execution supply the actual shared runtime root. Reuse them consistently in all filesystem child rules; do not merely correct the classifier while leaving validation looking up a different child. Keep the 2-tuple return and `validate_fsm` signature unchanged.

`_validate_with_bindings` obtains the child's parsed parameter contract from that resolve-only context instead of calling full `load_and_validate`. Keep unknown/required/type binding checks and existing missing-reference diagnostics, but do not recursively validate the child graph merely to read parameters or swallow `RecursionError` as a successful check. Cyclic bound children must terminate in both graph analysis and ordinary `load_and_validate`, not just in the classifier.

### Detection rules

Scan resolved `StateConfig.action` (all action types), evaluator prompt text (`prompt`, advisor `question`, contract-pair `contract`) and operational evaluator paths (`scope`, `history_file`, `baseline_path`, contract-pair `producer`/`consumer`), plus prompt-state `agent`. Also scan literal string leaves in state-owned `with:`/`fragment_bindings` and applicable unbound fragment parameter defaults, attributing them to that state's channel; an issue command passed to a reusable action must not disappear merely because the action uses `${param.cmd}`. This does not execute interpolation or propagate caller bindings into child analysis. `EvaluateConfig.path` is an output-JSON selector, not a filesystem path. Use a finite field/type table backed by `fsm/evaluators.py`, not a recursive scan of every string in the schema. Do not scan descriptions, YAML comments, unused library fragment definitions, `tools` allowlists, arbitrary `context` values or top-level `FSMLoop.scope` lock reservations. A lock reservation alone neither reads/writes an issue tree nor requires it to exist; actual action/evaluator references still count. The scan is intentionally static and conservative: text mentioning an issue command in a scanned literal counts even if phrased as a negative example or data. Reword such examples if necessary; no suppression field in v1.

The finite table also includes `circuit.repeated_failure.progress_paths` and authored `artifact_output.from`/`artifact_output.to` paths. These are operational filesystem fields: the executor stats progress paths and persistent execution can copy a deliverable into the authored destination. Attribute their requirements to that loop's core, inheriting the caller's adapter channel as usual. Count artifact paths conservatively for standalone capability even when a child invocation does not promote them. Do not scan `exclude_paths` solely because they exclude a path, or `commands` display metadata. These additions classify known coupling; they do not vendor artifacts, interpolate paths or inspect arbitrary assets.

- Reuse `_SKILL_INVOKE_RE` for `/ll:<name>` → `plugin`.
- A nonempty `agent` on an effective prompt action → `plugin`. Match the executor's explicit `prompt`/`slash_command` modes and `/`-prefix inference when `action_type` is omitted; explicit shell wins over that heuristic. Treat a named agent conservatively as an external agent definition; document the possible false positive for a host-native/user-defined agent. Ignore an inert agent field on a shell action.
- An effective learning dispatch (`type: learning` with a `learning` block, excluding terminal/sub-loop/human-approval dispatch) implies the packaged requirements of `/ll:explore-api`, currently `plugin` only, with evidence kind `implicit_skill` at the owning state's `learning` field. The executor synthesizes that remedy even when `action` is absent. Share a small pure dispatch predicate/remedy-name constant with `_learning_remedy_state`, or enforce their parity with a direct test; do not import/instantiate an executor in the classifier. Scan literal learning targets/`targets_csv` as generated prompt inputs using the bounded text rules. Use the same slash-skill judgment table; do not execute the remedy, read the learning registry or decide portability from whether a target happens to be proven. Conservatively retain the requirement for zero-retry configurations. A bare `type: learning` marker without a learning block does not add it.
- A bounded literal `.issues` path (with or without trailing slash, including nested/absolute paths), or `${config.issues...}` reference in a scanned field → `issues`. Do not match `.issues-backup`. Custom paths hidden behind arbitrary context interpolation remain a documented limitation of detection.
- Match issue-dependent console-script tokens in shell actions **and scanned prompt text**, using a closed set and token boundaries: `ll-issues`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-deps`, `ll-sync`, `ll-history`, `ll-history-context`, `ll-migrate`, `ll-migrate-relationships`, `ll-migrate-labels`, `ll-migrate-status`, and `ll-verify-evidence`. The latter CLI's default evidence check consumes issue files; `ll-history-context`'s issue mode resolves issue frontmatter. Conservatively count multi-mode commands even when a particular invocation (for example `--project`) is independent. A token such as `ll-issues-helper` must not match `ll-issues`.
- Other wheel commands do not automatically raise a tier. `ll-loop`, `ll-config`, `ll-logs` and `ll-session` are examples. A table test partitions current `[project.scripts]` names into issue-coupled and other commands, forcing an explicit judgment for newly registered CLIs. This partition is a maintenance gate, not a claim that every subcommand of an "other" CLI is independent.
- `ll-lint` marker comments and `ll-test-results` scratch filenames are not issue commands. An action that invokes a shell wrapper or Python function that internally touches issues can evade the static scan. Commands/paths supplied only through arbitrary top-level context, loop parameter defaults, captures, environment or caller inputs are not expanded by v1, even when a literal default is locally available. State-owned literal bindings/defaults above are the bounded exception. State these limitations in CLI/docs/export README; they do not create unresolved YAML edges or trigger a general interpolation/asset scanner. An author who knows such a core requirement must declare it explicitly.

### Adapter and declaration rules

Walk executable child dependencies over `(resolved node/context key, adapter channel)` pairs, with a fresh visited set for each requested report root within the operation. A dependency is core when at least one reference path to it crosses no `adapter: true` state. Reaching the same child through a core and an adapter call must preserve core evidence. Cycles terminate without dropping other reachable requirements; the guard is for analysis, not a claim that recursive execution will terminate. Share source/resolved-node caches across catalog roots, but cache only finished root-relative reports. Never reuse another root's visited set or memoize a partial child report while a cycle back-edge is active. A simple per-root traversal is sufficient; no new cycle-solving framework is required.

A `loop:` back-edge to an already visited/in-progress node/channel adds no unresolved evidence and does not itself make a report incomplete. Completeness reflects failed/dynamic dependencies and invalid portability metadata, not recursion alone; known requirements elsewhere in the cycle still contribute to every requested root's report.

Scan every resolved state in each referenced loop; "reachable dependencies" here means the file-reference graph, not pruning states by FSM control-flow reachability. Adapter channels follow explicit markers on states/sub-loop calls, not guesses about which transition or context value will win.

- `adapter: true` moves that state's action/evaluator/agent requirements and its entire child subtree into the adapter channel. A non-adapter caller preserves its child's core and optional adapter channels. Loop-level declarations stay core relative to that loop, and inherit the caller's channel when the whole child is invoked as an adapter. Loop-level concurrency scope is not a detected requirement by itself.
- `adapter` is an author assertion that a route is optional. It does not prove a default will avoid the state, imply a runtime preflight, or automatically mark downstream states in the same loop. Authors mark all dependent adapter states; a shared core state still counts as core. Reject `adapter: true` on the initial state and require explicit tests for the pilot's default route.
- Add optional loop-level `ecosystem_requires: [plugin, issues]` for requirements hidden behind wrappers/interpolation. It is an additive author assertion, distinct from FEAT-3717's runtime-version `requires` mapping. Validate a YAML list of unique enum strings (`plugin`/`issues`); reject scalars, mappings, null, duplicates and unknown/non-string entries. Omission/default `[]` serializes as absent; an explicit empty list is valid so a child can clear an inherited list through normal list-replacement semantics. `portability` and `ecosystem_requires` follow normal inheritance/override rules. This field declares that loop's core requirements and inherits an enclosing adapter call's channel; it does not suppress detection or certify an unknown graph.
- Validate resolved raw field types before parsing: `adapter` must be a YAML boolean; `portability`, when supplied, must be one of the three enum strings; `ecosystem_requires` follows the list contract above. Invalid types/values are ERRORs, not coerced truthy values or dropped keys. Omission retains existing behavior.
- For an otherwise parseable loop, invalid new metadata also yields source/field-specific unresolved evidence (`invalid_declaration` or `invalid_adapter`) and makes the affected channel incomplete. An invalid adapter, including `adapter: true` on that loop's initial state, is treated as core for analysis; it cannot hide requirements in adapters or produce a complete portable catalog match. Retain detected requirements and any individually valid explicit requirement entries as conservative evidence, without accepting the invalid field as a valid declaration. Invalid tiers contribute no implied requirement. Safe defaults/subsets are only a reporting projection: preserve the authored value in diagnostics/trace, return the ERROR with `raise_on_error=False`, and reject ordinary loads. Invalid metadata in an adapter-reached child makes the parent's adapter channel incomplete, without invalidating an otherwise complete parent core. Unrelated structural FSM errors do not by themselves make dependency analysis incomplete.
- The declaration is a conservative authored tier. Add the requirement implied by a nonportable declaration to the effective report, with declaration evidence; retain `declared_tier` and `detected_tier` separately. Overstatement is allowed. If a known effective core requirement exceeds the declaration, emit an ERROR naming the offending loop/state/field/match, even if other edges remain unresolved.
- Union explicit `ecosystem_requires` entries into effective requirements with source/field declaration evidence; exclude them from `detected_tier`. Apply the same tier-understatement check to the resulting effective core. For example, detected issue-only MCP use plus hidden plugin use is expressible as `portability: requires-issues` and `ecosystem_requires: [plugin]`: effective requirements are `[issues, plugin]`, detected tier remains `requires-issues`. `portability: portable` with either explicit requirement is an ERROR. The unverified-declaration WARNING concerns an authored tier, not merely a lower-bound requirement list without a tier. Export acknowledgments/README consume these effective sets.
- Understatement compares display ranks, not whether a tier names every member of the requirement set. `requires-issues` plus detected plugin use is permitted overstatement and retains effective `[issues, plugin]`. Conversely, `portable` plus a core child's explicit issues requirement is an ERROR even with no literal issue detection; the root's own explicit requirements are checked too. Do not exempt root `ecosystem_requires` or let the root's implied tier conceal a higher known core requirement. Malformed metadata already has a field ERROR; do not add an unverified-tier WARNING solely for a raw-invalid tier.
- Emit declaration diagnostics for the requested validation root against **its own root-relative core**; do not recursively re-emit child declaration violations through the caller. An inaccurately declared child reached only through an adapter affects the parent's adapter report, and fails when validated directly. The corpus/export gates validate every runnable child as its own root. Aggregate detected requirements (including implicit runtime remedies) separately from conservative declaration requirements: `detected_tier` excludes declarations, while effective `tier`/`requirements` include all core-reachable declarations. A root declaration cannot understate an effective requirement promised by its core child. Evidence for effective inherited `portability`/`ecosystem_requires` declarations identifies the authored source. Deduplicate root diagnostics by field/evidence, including when a child is reached through both channels.
- An incomplete core with a declaration emits one WARNING that the declaration is unverified; an undeclared incomplete core is reported without a portability violation. Adapter incompleteness does not invalidate a complete core declaration, but stays in the adapter report.
- Do not add `portability_ignore`. Blanket state exemption would hide true dependencies from the export gate. This replaces earlier notes proposing that field.

### Report and CLI contract

`PortabilityReport` is a frozen dataclass with `declared_tier`, `detected_tier`, effective `tier`, sorted `requirements`, `complete: bool`, an `adapters` object (`tier`, `requirements`, `complete`), `evidence` and `unresolved`. Nested channel/evidence records are immutable; collection fields are tuples internally and fresh lists in each JSON serialization. Requirement values are `plugin`/`issues`. Evidence records the dependency loop, state (or root), field, match/kind and channel; carry `fragment_name` when available. Stable ordering is source/state/field/kind/match, independent of traversal/set order. Mutating a serialized report must not alter the cached report.

Wire semantics: `tier`, `detected_tier` and `adapters.tier` always contain one of the three tier strings, even when incomplete. They are known lower bounds; an empty known set yields `portable`, which certifies portability only with the corresponding `complete: true`. `detected_tier` uses core detection evidence only; `tier` additionally includes effective core declarations, and `adapters.tier` uses effective adapter requirements. `declared_tier` is a valid effective authored enum or `null` when omitted/raw-invalid; raw-invalid values remain in diagnostics/trace and unresolved evidence. Never serialize `unknown` as a tier. Human rendering still shows `unknown (detected: <tier>)` for an incomplete core and also shows its known effective requirements when declarations make them stronger. All JSON consumers, including FEAT-3717, must inspect completeness separately; core and adapter completeness are independent.

- Keep informational data separate from `ValidationError`. Register only declaration/marker diagnostics in `load_and_validate`; no INFO severity and no warning for an ordinary undeclared, statically resolved loop.
- `cmd_validate` loads with `raise_on_error=False` in both output modes, renders collected violations itself, reports portability even on a parsed-but-invalid loop, and returns 1 for ERRORs / 0 for warnings only. Early read/parse/config failures retain the existing `{loop, valid, violations}` JSON shape, with no portability object. Avoid duplicate warnings and preserve the BUG-3230 boundary that prevents a pipe failure from printing a second JSON document.
- Successful parsed `validate --json` adds `portability: <report object>`. Human output starts `Portability:` and displays `unknown (detected: <tier>)` when core completeness is false; adapter requirements/unknowns are explicit.
- `LoopCatalogEntry.to_json_item` adds the same `portability` report object, shared byte-for-byte with MCP `loop_list`. An enumerated runnable candidate whose dependency/analysis fails remains listed with an incomplete report; the metadata fallback must never turn that failure into `portable`. Preserve existing runnable-file discovery: a wholly unreadable/malformed root that `is_runnable_loop` excludes is not newly presented as a loop, and fragment-only libraries remain excluded. This is not a malformed-file inventory feature.
- `--portability <tier>` matches effective core tier only when core is complete. Apply after visibility filtering so existing `hidden_counts` semantics are preserved. Keep terminal-width and minimal-layout-dict handling valid.
- Matching is exact (`tier == requested tier`), not a maximum-rank filter. `--portability` applies to the definition catalog only. Reject combinations with `--running`, `--all-runs` or `--status` as a usage error (exit 2, diagnostic on stderr, no stdout JSON), before the saved-run branch or any run-state reads. Preserve saved-run JSON and standalone run-list behavior; do not analyze current YAML as though it described a persisted run snapshot.
- Add the same filter to MCP's strict `loop_list` input schema and forwarding. Retaining this small existing parity surface avoids two different catalog behaviors.
- Human `show` prints evidence. `show --json` remains `fsm.to_dict()` (authored schema, not an enriched report); document this distinction rather than changing its wire shape.
- Reuse parsed nodes/report within one operation. Catalog analysis must not rerun every validation rule for every dependency or use a persistent cache that can miss project edits.

### Brainstorm pilot

The classifier can land against the current brainstorm loop; FEAT-3717 owns the final pilot run after FEAT-3582 rewrites it and supplies its tournament child. Set `portability: portable`; mark issue/decision sink states as adapters; preserve the existing top-level concurrency scope, including `.issues/`. Do not misuse state `scopes`, which are credential scopes, as filesystem scope. Sinks still carry their actual issue/plugin references, reported as independent adapter requirements (currently both `plugin` and `issues`), not a hardcoded `requires-plugin` result.

Test that default `sink=none` and `sink=file` bypass issue/decision adapters and touch no issue tree. Adapter prerequisites are documented; automatic cross-host "plugin installed" preflight is outside this issue and FEAT-3717.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Active MCP arguments are another bounded operational field: scan literal string leaves in `StateConfig.params` only when the effective action mode is `mcp_tool`. `FSMExecutor._run_action` interpolates this mapping and passes it to the tool, so an argument containing a bounded issue path or issue-command token must contribute to its owning state's core/adapter channel. Ignore inert `params` on other action modes. This does not expand arbitrary context/environment values or collect MCP assets.
- The literal-leaf walk needs an object-identity guard independent of the loop-file cycle guard. PyYAML can construct recursive dict/list aliases. A revisit must terminate while preserving every other reachable string leaf, and aliases reused by another state/channel must still receive that state's evidence. Scope traversal guards to the owning scan/channel rather than globally suppressing an aliased value after its first use. This guards analysis only; it does not certify recursive data for execution.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Classify known issue-dependent `/ll:` skills/commands as both `plugin` and `issues`; the existing blanket slash-token rule remains the minimum `plugin` result. For example, `/ll:manage-issue` and `/ll:capture-issue` need issues even without an issue path/console-script literal; `/ll:check-code` is plugin-only. Maintain an explicit partition against the canonical shipped `commands/*.md` and `skills/*/SKILL.md` invocation inventory, including supported aliases and deduplicating names, with a test that requires judgment for every new name. Use the same conservative multi-mode policy as console scripts. Unknown/custom names remain at least plugin; indirect/custom skill behavior is a documented detection limit. Runtime classification uses the packaged judgment table, not checkout-only plugin discovery.
- On effective MCP actions, recognize exact tool-name suffixes in the current `server/tool` action syntax using an explicit partition of little-loops' registered tool names. Known issue tools such as `issues_query`, `issue_get`, `deps_check`, `issue_capture`, `issue_set_status`, `issue_link` and `issue_append_log` imply `issues` without implying the plugin. Do not use prefix substrings or assume the configured server key is literally little-loops; document that a same-named tool on another server can over-detect. `history_search` reads session history through `history_reader`/`resolve_history_db`, so it does not imply an issue tree merely because its name contains history. A table test covers the complete current MCP tool inventory and keeps newly registered names explicit.
- A recognized MCP `loop_start` action is an unresolved operational loop dependency in its owning core/adapter channel. The server binds its own project root and may start a detached run, so do not reinterpret `params.loop` as a normal executor `loop:` reference or fabricate a resolved/read YAML edge. Its report is incomplete and export refuses it, including in an adapter. Unknown MCP behavior and shell/prompt-launched loops retain the existing documented static limits.

## Integration Map

### Files to Modify

- New `fsm/loop_dependencies.py` (new): resolve-only helper, graph/edge/read-trace dataclasses, per-operation guard.
- `fsm/fragments.py` and `fsm/loop_paths.py`: reuse loading/lookup steps and optional read/resolution recording without changing normal resolution precedence. `load_loop_with_spec`, catalog discovery/metadata and `is_runnable_loop` reuse operation-owned raw records where available rather than rereading YAML just to expose its metadata/required fields; preserve their existing default APIs.
- New `fsm/validation/portability_rules.py` (new); `structural_rules.py` and `reachability.py`: diagnostics, explicit runtime-root forwarding and common filesystem resolution.
- `fsm/schema.py`, `fsm/fsm-loop-schema.json`, `fsm/validation/_base.py`, `fsm/validation/__init__.py`: `FSMLoop.portability`, `FSMLoop.ecosystem_requires`, `StateConfig.adapter`, parsing/serialization/default omission, known keys/constants and public exports/module map.
- `cli/loop/{config_cmds,info,__init__,run,lifecycle}.py` and `fsm/executor.py`: root-context forwarding, reports, filter, display and dispatch. `load_loop`/`load_loop_with_spec` forward the supplied runtime root.
- `mcp_server/tools.py`: strict filter schema/forwarding and explicit project-root cwd for catalog analysis; report arrives through the canonical catalog serializer.
- `scripts/little_loops/loops/brainstorm.yaml`: declaration/adapter changes against the current loop, preserving concurrency scope. Add a small verified portable catalog subset so the corpus gate cannot pass vacuously. Package-relative module paths above are under `scripts/little_loops/`; shipped loops no longer live in a repository-root `loops/` directory.

### Dependent Files and Constraints

- Do not widen `ValidationSeverity`.
- Preserve `validate_fsm`; `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py` pins that signature. `scaffold_verify`/`scaffold_eval` in-process validation has no filesystem context and must document that it does not classify transitive dependencies.
- `cli/logs._validate_builtin_loop` returns a tuple of validity/violations, not a JSON payload. Preserve that API; it receives registered diagnostics automatically and does not need an invented report key. `ll-doctor` and `fleet_improve` continue consuming errors/warnings.
- `_GATE_COMPLETENESS_TABLES` checks routing vocabulary. Portability is metadata, not a routing token set; do not register its enum there.
- `fsm.to_dict` is used by persistence/scaffolding; omit absent `portability`, empty `ecosystem_requires` and false `adapter`, preserving existing output.
- Preserve project-over-builtin shadowing, drafts, compiled loops and inherited stubs in catalog enumeration. Keep by-name `get_builtin_loops_dir` imports patchable.
- This classification is distinct from the existing BSD/GNU shell-portability gate and `ll-portability-ok:` suppressions.

### Behavior Parity

| Artifact | Behavior | Result |
|---|---|---|
| `scripts/little_loops/loops/brainstorm.yaml` | Current engine/artifact validation, inputs/defaults and sink routing | Preserved; this issue does not rewrite the engine |
| `scripts/little_loops/loops/brainstorm.yaml` | Issue/decision sinks selected explicitly | Preserved; new adapter metadata reports their prerequisites |
| `scripts/little_loops/loops/brainstorm.yaml` | Global `.issues/` concurrency scope | Preserved; missing paths can be reserved, and optional issue sinks retain conflict protection |
| `scripts/little_loops/loops/brainstorm.yaml` | Default none/file paths | Preserved; tested without issue writes |
| `cli/loop/config_cmds.py` | Human/JSON validation, exit 1 for errors and parse failures | Preserved; parsed results gain a report, diagnostics render once |
| `cli/loop/info.py` | Catalog shadowing, visibility counts, width handling and `show --json` | Preserved; list gains a report/filter and human show gains evidence |

### Tests

- New `test_fsm_validation_portability.py` and resolver tests: direct text, prompt issue CLI, named agent, bounded path tokens, marker/type validation, fragment/flow/inheritance, effective child-directory imports, project-shadowed built-in children, missing/malformed children, core/adapter dynamic children, cycles and the same child reachable in both channels. A top-level `.issues/` lock reservation alone remains portable; the same path in an action/evaluator is detected.
- Regression fixtures cover partial inheritance templates, overridden ancestor issue actions, two symlinked consumers of one source with different libraries, advisor-question/contract text and operational evaluator paths, inferred prompt agents, `ll-history-context`, core/adapter literal bindings and fragment defaults, and documented context injection limits. An invalid child declaration is diagnosed on direct child validation without being re-emitted by its adapter caller; conservative child declarations affect effective requirements without inflating literal `detected_tier`.
- An explicit shell action containing a slash-skill token and an inert `agent` remains plugin-coupled by text but has no agent evidence. Prompt inference follows the executor's literal `/`-prefix test, including its handling of leading whitespace; do not substitute a validator's broader LLM-state heuristic.
- Assert analysis does not call full validation recursively, execute actions, mutate cwd/config, or read the same resolved node repeatedly within the same context.
- Cache-ownership regression: obtain two FSMs through one operation context, mutate the first one's nested context/binding/default values as run/child loading does, and assert the second FSM, cached source/resolved templates and subsequent reports remain unchanged. Preserve shared aliases inside each returned copy and retain the read-counter guarantees.
- Detection fixtures cover implicit learning remedies without an authored action, adapter learning, inert bare learning markers and dispatch precedence. Registry/proof state must not affect classification. Issue-coupled progress/artifact paths count, while lock reservations, exclusion-only paths and display metadata remain excluded; artifact paths on a child retain the documented conservative classification.
- Declaration fixtures cover detected issues plus explicitly declared hidden plugin use, invalid/duplicate list entries, inherited lists and explicit-empty overrides, tier contradictions, child adapter attribution and fresh JSON list serialization. Existing requirement-table gates include the implicit remedy's plugin-only classification. Two real child dispatches must not share an analysis context that makes the second use stale YAML.
- A validate-plus-report read counter and two catalog roots sharing a child prove operation-context reuse. A cwd-literal fixture supplies a cwd different from the process cwd and proves that resolution uses the explicit context.
- Catalog/context fixtures put conflicting child and inheritance-parent literals under the explicit cwd and process cwd; check their selected sources against runtime precedence. Include relative root/loop-root arguments anchored to the explicit cwd. MCP analysis from another process directory matches CLI analysis from `project_root`, also with a configured loop root that is not `project_root/.loops`. A supplied context's omitted bases are reused; explicit mismatches fail before reads. Fragment imports remain consumer-relative despite a same-named cwd file.
- Shared-context reports for `A -> B -> A`, with a requirement in A, retain it for both A and B roots regardless of catalog order. A child reached as an adapter from one root and core from another has independent channel evidence. Assert bounded file reads without reusing a partial cyclic report or another root's traversal guard.
- Failure-boundary fixtures give a parseable root multiple siblings, with one child failing lookup/read/YAML/inheritance/fragment expansion/dataclass parsing. Preserve successful sibling evidence, attribute each failed reference/channel, reuse cached failures without collapsing distinct misses, and emit a report for the root; validating the failed child directly retains early-error JSON without a report. Expected failures are contained, while an injected programming exception reaches the caller's error boundary. Static child cycles alone stay complete; a real missing/dynamic edge within the cycle makes only its owning channel incomplete.
- Silence/lifetime fixtures include duplicate-name drafts, broken children and children whose direct validation would warn. Graph/catalog analysis emits no stdout/stderr/logs; default runtime lookup still emits its draft Note. Validate JSON emits one document with diagnostics once. A second MCP catalog request after editing a child rereads it and updates the report.
- Provenance fixtures cover parent/ancestor declarations, explicit-empty list resets, fragment adapter overridden to false, and an inherited adapter retained when only the action is overridden. Initial-state adapter errors cite the winning authored source. Recorder omission preserves current resolution content and output shape.
- Raw-invalid tier/list/marker fixtures (including null, duplicates, an adapter string and an inherited initial-state adapter) stay listed with incomplete affected channels, preserve known evidence, fail validation and never match a complete-core filter. Compare with an unrelated routing error whose analyzed dependencies remain complete. Pin rank-only declaration checks, including root/child explicit requirements contradicting a portable declaration.
- Ordinary `load_and_validate` on cyclic static children with nonempty `with:` terminates with bounded resolve-only reads and still checks both parameter contracts. A guard only around `classify_portability` does not satisfy this regression.
- `test_fsm_schema.py`: new fields/schema/known-key round trips and omission defaults. `test_fsm_validation_structural.py`: declaration diagnostics. Keep ordinary minimal loop violations empty.
- `test_ll_loop_commands.py` / `test_cli_loop_dispatch.py` / `test_json_output_contracts.py`: report shapes, parsed invalid vs early-error JSON, warning/error exit codes, filter forwarding, unknown exclusion, evidence and terminal widths.
- Parser fixtures reject every saved-run/filter combination before dispatch and leave stdout empty even with `--json`; existing saved-run JSON fixtures remain unchanged. Exact-tier filtering includes both core prerequisites and preserves hidden-count ordering.
- Pin lower-bound JSON serialization for incomplete empty/plugin/issues cores and adapters, stronger declaration evidence and raw-invalid tiers. Every incomplete core is excluded from its matching tier filter, including `requires-issues`; an adapter-only failure still permits a complete portable core match. CLI/MCP reports match under the same explicit cwd/runtime root/source snapshots.
- `test_feat_3352_mcp_loop_list.py`: report/filter parity with CLI, including project overrides and an incomplete entry.
- `test_builtin_loops.py`: enumerate runnable built-ins including nested/from-only loops; require a nonempty declared-portable subset (including brainstorm), assert its cores are complete and error-free, and print detected distribution without pinning the old grep count. Include a fixture that introduces issue coupling and proves the gate fails.
- Bare-interpreter warning remains shell-only and path-aware-independent: detect `python`/`python3 -m little_loops.X`, including a command in a later line; allow `$${LL_PYTHON:-python3}` after FSM dollar escaping, ignore comments/description prose and quoted `echo` examples. Register this filesystem-free rule in `validate_fsm`, so scaffold checks see it. Add a zero-budget warning category to both corpus and brainstorm warning ratchets; the catalog is clean since `21583aae3`.
- `test_brainstorm.py` tests current adapter markers, preserved concurrency scope and deterministic none/file paths with no issue writes. Verify locking a missing issue path creates no issue tree and still conflicts with another writer; FEAT-3717 repeats acceptance against the FEAT-3582 rewrite.

### Documentation

Update `docs/reference/{CLI,API,json-output-contracts,loops}.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`, `docs/generalized-fsm-loop.md`, `docs/ARCHITECTURE.md`, `docs/guides/MCP_SERVER_GUIDE.md`, `skills/{create-loop,review-loop}/reference.md` and `scripts/little_loops/loops/README.md`. Describe detection limitations, implicit learning remedies, independent requirements, `ecosystem_requires`, declared vs detected tiers, incomplete reports and the adapter author assertion. Update relevant docs wiring gates; regenerate only existing touched host mirrors with `ll-adapt`, and mirror `README.md` to `scripts/README.md` if edited.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Direct validity/edit consumers also need an explicit resolution policy: `scripts/little_loops/cli/logs.py:_validate_builtin_loop` validates nested built-ins; `scripts/little_loops/cli/doctor.py:_loop_validity_data` enumerates project and built-in files; `scripts/little_loops/cli/loop/edit_routes.py:cmd_edit_routes` knows the caller's runtime `loops_dir`. Their load calls currently omit that root. Forward the appropriate known shared root so diagnostics agree with run/validate; preserve existing result shapes. Cover these seams in `scripts/tests/test_ll_logs.py`, `scripts/tests/test_cli_doctor_install_checks.py` and `scripts/tests/test_ll_loop_edit_routes.py`.
- `scripts/little_loops/cli/artifact/policy_revision.py:validate_policy_revision` validates temporary candidate YAML below a policy-builder directory. Its standalone candidate-validation scope must remain explicit rather than silently treating the temporary file's parent as a configured project runtime root. No runtime-root inference or project config loading belongs in the resolve-only helper.
- `scripts/little_loops/fsm/executor.py:_run_action` is the evidence for the active MCP `params` scan: it sends interpolated arguments directly to `mcp-call`. Recursive-container handling already has a bounded ancestry-identity convention in `scripts/little_loops/cli/issues/create.py:validate_metadata`; the new analysis must uphold termination while retaining repeated state/channel attribution, rather than copy that unrelated command's rejection policy.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- `scripts/little_loops/loops/harness-single-shot.yaml` contains a core `/ll:manage-issue` action without an issue CLI/path token; it is the concrete regression for slash-skill issue inference. Canonical `commands/` and `skills/` are the source inventory for the new maintenance partition, not generated host mirrors.
- `scripts/little_loops/mcp_server/tools.py` owns registered tool names and issue/session-history handlers; `scripts/little_loops/mcp_server/tasks.py` owns project-root/run dispatch for loop starts. Test the known MCP requirement partition without importing optional MCP SDK dependencies into the normal classifier. Reuse the existing MCP action-mode contract exercised by `scripts/tests/test_fsm_executor.py`.

## Program Design

### Types

- `DependencyEdge`: `kind: str`, `reference: str`, `consumer: Path`, `resolved: Path | None`, `resolution_mode: str`, `state: str | None`. Dynamic/read failures are explicit unresolved edges.
- `DependencyFailure`: typed failure kind (`not_found`, `read_error`, `parse_error`, `expand_error`), failing stage, authored reference, consumer/selected source, message and lookup trace. Missing sources stay edge failures; selected-source failures are cached node outcomes. Root errors keep their existing exception API rather than requiring a new public exception class.
- `ResolvedLoopNode`: canonical source identity, loader-visible consumer directory/context key, optional resolved raw mapping and file-read records; a successful outcome has a parsed `FSMLoop`, a failed child outcome has `DependencyFailure`. Validate raw marker types before using them to choose an adapter channel. Partial parents/libraries are raw source records, not necessarily nodes with a parsed FSM.
- `LoopDependencyGraph`: root context key, executable nodes/outcomes, raw source records, edges/failures and file-read snapshots/digests; per-operation traversal context includes the shared `loops_dir` and explicit cwd. A returned graph always has a successfully parsed requested root.
- `LoopResolutionContext`: operation-owned read/expansion caches and graph/report results keyed by root/context. Consumers can obtain the report without changing `load_and_validate`'s return type; no global/persistent cache.
- Cached templates/reports stay analysis-owned; parsed FSMs returned to mutating callers are independent defensive copies, including nested values. Copying does not reread or re-expand YAML.
- `PortabilityReport`: frozen core/adapter, declaration/detection, completeness and evidence records specified above, with tuple collections internally and fresh JSON arrays. `FSMLoop.portability: str | None`, `FSMLoop.ecosystem_requires: list[str] = []` (default factory) and `StateConfig.adapter: bool = False` are the authored fields.

### Signatures

- `resolve_loop_graph(root_file: Path, *, loops_dir: Path, cwd: Path, resolution_context: LoopResolutionContext | None = None) -> LoopDependencyGraph` — new, `fsm/loop_dependencies.py`.
- `classify_portability(graph: LoopDependencyGraph) -> PortabilityReport` — new, `fsm/validation/portability_rules.py`; pure analysis of resolved nodes/edges, with no further reads or validation recursion.
- `_validate_portability_fields(raw: dict[str, Any]) -> list[ValidationError]` and `_validate_portability_declaration(report: PortabilityReport) -> list[ValidationError]` — new diagnostic helpers.
- `_validate_package_interpreter(fsm: FSMLoop) -> list[ValidationError]` — new filesystem-free shell warning helper.
- `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints=None, loops_dir: Path | None = None, cwd: Path | None = None, resolution_context: LoopResolutionContext | None = None) -> tuple[FSMLoop, list[ValidationError]]` — retain existing arguments/return; add optional runtime root/cwd/context. Without a supplied context, omitted cwd defaults to `Path.cwd()` and omitted root to `path.parent`; with one, omissions inherit its bases and explicit contradictions are rejected. Reuse the graph/report through that operation-owned context without storing it on the FSM.
- `enumerate_loop_catalog(*, loops_dir: Path, category=None, label=None, visibilities=None, builtin_only=False, portability: str | None = None, cwd: Path | None = None) -> LoopCatalog` — extend the existing canonical catalog function; capture default cwd once, and accept MCP's explicit project root.

### Call Path

`main_loop` → `cmd_validate` → `load_and_validate` → `resolve_loop_graph` → existing `resolve_inheritance`/`resolve_flow`/`resolve_fragments`/`resolve_loop_path` → `classify_portability` → diagnostics and separate report rendering.

`cmd_list` / `mcp_server.tools._tool_loop_list` → `enumerate_loop_catalog` → resolve/classify once per operation context → `LoopCatalogEntry.to_json_item`. `cmd_show` uses the same report for human evidence while keeping `fsm.to_dict()` as its JSON output.

### Decision Rules

The detection/channel/declaration/report rules in Proposed Solution are normative. Missing or invalid adapter metadata never moves a dependency out of core; unresolved reads never become a successful portable result. Analysis uses no full-validator recursion or persistent/global cache.

## Implementation Steps

1. Land the resolve-only loader/graph/trace and runtime-root context with resolution/recursion fixtures. Freeze this interface for FEAT-3717; do not build a general dependency framework.
2. Add fields/raw validation and static detection, independent requirement sets, channel traversal and deterministic completeness/evidence reports.
3. Add declaration diagnostics and the bare-interpreter warning at their respective filesystem-aware/pure seams.
4. Wire validate/list/show/MCP and explicit root forwarding. Check existing catalog/JSON/layout/validation contracts.
5. Mark the current brainstorm pilot and a verified portable catalog subset; run nonvacuous corpus and pilot tests. Document semantics and run the full local test suite, lint and type checks.

## Impact

- **Priority**: P3 — independently unblocks export and prevents another interpreter regression.
- **Effort**: Large — shared resolution-context parity, cache ownership, maintained detection inventories and transitive channel analysis span the loader, validators and CLI/MCP surfaces. Implement in the ordered phases above; freeze the resolver/report interface only after its focused fixtures pass.
- **Risk**: Medium — recursive revalidation, project shadowing or silent catalog fallback can produce misleading tiers.
- **Breaking Change**: No for valid loops omitting the new metadata. Invalid markers/declarations or an understated tier fail validation; JSON gains additive report fields.

## Acceptance Criteria

- [ ] One resolve-only graph handles runtime child-root semantics, final-consumer fragment bases, flow/inheritance, cwd precedence and project overrides; analysis terminates on cycles without entering full validators. Expected child failures preserve the parsed root/sibling evidence, while requested-root failures retain the existing early-error API/JSON boundary.
- [ ] Raw source records are distinct from executable nodes; partial parents load, overridden actions do not count, source/context aliases retain their different resolutions, and cyclic `with:` binding validation also terminates without recursive full validation.
- [ ] Returned FSM mutation cannot alter cached snapshots/templates/reports or another consumer's defaults/bindings. Implicit learning remedies and operational progress/artifact paths receive channel-correct evidence without running actions or consulting registry state.
- [ ] `ecosystem_requires` expresses hidden independent prerequisites, including both plugin and issues, with raw validation/default omission/inheritance tests. It contributes declaration evidence to effective sets without changing detected tiers or bypassing declaration diagnostics.
- [ ] Plugin/issues are independent requirement sets; wire tiers are known lower bounds, completeness stays separate, and reports/evidence are deterministic. Static cycles alone remain complete; incomplete cores never match any exact-tier filter. Named agents, prompt issue commands and `ll-history` are detected.
- [ ] Raw marker/declaration types are validated and round-trip; no `portability_ignore` field or INFO severity is introduced.
- [ ] Adapter state/subtree requirements are separated without losing core requirements on alternate paths. Declared understatement errors; declared unresolved core warns; unknown remains visible.
- [ ] Validate/list/show surfaces and MCP catalog/filter parity follow the shapes above; incomplete catalog entries never masquerade as portable, and `show --json` retains its schema contract.
- [ ] Explicit catalog cwd, supplied-context defaults/mismatch checks and per-root cyclic traversal preserve runtime lookup/channel semantics across MCP, CLI and shared caches. Analysis is silent, preserves resolver diagnostics as trace data, and a new MCP request observes edits without a process-lifetime cache. Winning declaration/marker provenance survives inheritance, fragment overrides and list resets.
- [ ] Invalid portability metadata retains known evidence but makes its owning channel incomplete; invalid adapters remain core. Exact-tier filters reject saved-run modes with exit 2 before dispatch and preserve existing run JSON.
- [ ] Bare package-module interpreter calls warn with `$${LL_PYTHON:-python3}` as the fix; shipped loops have zero such warnings and the warning budget enforces that.
- [ ] Brainstorm's concurrency scope is preserved and excluded from requirement inference by itself; its complete core is declared portable, its issue/decision adapters report their actual prerequisites, and none/file paths avoid issue writes while conflict protection remains active.
- [ ] Corpus testing covers a nonempty declared-portable subset, records distribution and detects a deliberate regression; it does not assert equality to the historical 39/97 raw-text grep.
- [ ] Docs and relevant wiring gates are updated; `python -m pytest scripts/tests/`, lint and type checks pass. Use the existing suite, with no new CI workflow.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- [ ] Nested literal MCP arguments count only on effective MCP actions, with core/adapter attribution; the same inert mapping on a shell action contributes nothing.
- [ ] Recursive YAML binding/default/MCP-argument aliases cannot recurse indefinitely or hide sibling requirements. Shared acyclic aliases used by different states or channels retain each relevant evidence record.
- [ ] Nested built-in/project validity diagnostics and route-edit validation use their explicit shared runtime root and agree with run/validate on child shadowing; standalone temporary candidate validation retains its documented scope.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- [ ] Issue-dependent slash skills imply both independent requirements, including `/ll:manage-issue` and `/ll:capture-issue`; `/ll:check-code` stays plugin-only. Brainstorm's adapter issues requirement survives removing unrelated decision-sink CLI text. Canonical command/skill inventory coverage is nonvacuous.
- [ ] Known issue MCP tool names imply issues with exact suffix boundaries; session-history search alone does not. The MCP inventory partition requires explicit judgments, and a recognized `loop_start` produces an incomplete owning channel rather than a fictitious closed child graph.

## Review Notes

2026-10-06 final contract review on `main`, with `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.80): clarified the root-versus-child load-error boundary, typed/cached child failures without a shared missing-source identity, lower-bound tier serialization, silent recorded lookup including duplicate-draft diagnostics, cycle completeness and one-MCP-request cache lifetime. Kept the existing load exception API and human unknown display; no new root exception class/null-tier schema is needed. Opus's main residual risk is a consumer ignoring completeness, so the wire contract and exact-filter fixtures now state it explicitly. Existing loader/path/inheritance/fragment tests passed (225); format/design, dependency and learning-proof checks passed, with no active required decision rules. These checks support the issue contract, not implementation acceptance. No further design decision blocks the ordered implementation phases.

2026-10-06 follow-up pre-implementation review, with `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.78): added explicit MCP catalog cwd and supplied-context defaults, cwd-first inheritance lookup parity, narrow merge-time declaration/marker provenance, conservative malformed-metadata reporting, exact filters and saved-run option rejection. Current-source probes confirmed cwd literals can override an explicit loop root, malformed proposed declarations still satisfy runnable discovery, and inheritance clears lists/preserves winning fields without retaining their origins. Clarified fresh root-relative cycle/channel traversal so operation-owned catalog reuse cannot cache partial cyclic results. Specified corresponding regression fixtures and rank-check examples. Accepted Opus's main wiring/provenance findings; declined its root `ecosystem_requires` exemption because it contradicts the existing portable-declaration rule, and its invalid-adapter completeness exemption because it would let malformed metadata match a complete portable filter. Generator draft lookup already derives from the supplied loop root without loading config, so no speculative new draft fallback rule was added. These checks reviewed the issue contract; they did not implement or certify the feature.

2026-10-06 pre-implementation review on `main`, with `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.80): accepted implicit learning-remedy detection, explicit independent `ecosystem_requires` and analysis-cache ownership. A pure helper probe produced `/ll:explore-api example` from a learning state with no authored action. A parser probe confirmed two FSMs built from one raw mapping share its context and see one another's mutations. Added operational progress/artifact path detection, immutable report serialization and mutation/copy/read-count fixtures. Preserve the stated interpolation limits and registry-independent conservative detection. Allow explicit-empty requirement lists to clear inherited lists; keep implicit requirements even with zero retries. Increased the effort estimate to Large and made interface freezing depend on focused fixtures. These are issue-contract changes backed by inspection/probes, not implemented feature acceptance.

2026-10-05 source/probe review and `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.72): a partial parent lacking `name`/`initial` successfully loaded through its child, and an overridden `.issues/` action disappeared from the effective FSM. A bounded cyclic-binding probe reached nine child reload attempts; a classifier-only cycle guard would not repair that validator path. Two symlink aliases to the same source selected different relative fragment libraries. These observations motivate the raw-source/executable-node distinction, context-aware keys and resolve-only binding contracts above. Accepted Opus's explicit operation context/report access, root-relative declaration diagnostics and bounded state-binding detection; also filled literal evaluator/issue-command gaps and clarified catalog discovery limits. Kept the interpreter warning here because FEAT-3667 already depends on this ownership. These were inspection/load probes, not execution of the proposed feature or a full-suite result.

2026-10-04: Reconciled the accumulated research into this single contract after source review and an Opus consult via `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.74). The old NON_VALID verdict described the superseded draft and was removed, not replaced with an unrun verification claim. Accepted independent requirements, shared resolution context/trace, channel-based cycle traversal, honest static limits, no blanket suppression and no runtime adapter-preflight promise. Kept the existing MCP parity surface and declaration enforcement at load/validate; Opus suggested omitting those, but they are small existing integration contracts worth preserving. Dynamic declared cores warn and remain unverified; export refuses them. The classifier and current pilot annotations can land independently; FEAT-3717 retains the final rewritten-pilot prerequisite.

Second Opus pass (2026-10-04, confidence 0.74) found no structural contradiction after the minimum refinements. Accepted a shared typed resolver-event seam and independent classifier sequencing.

Final source check corrected a lock-scope false positive: `cli/loop/run.py` uses `FSMLoop.scope` only for concurrency, and `fsm/concurrency.py` reserves absent paths without creating them. A temporary-directory probe confirmed that a `.issues/` reservation succeeds, leaves the issue tree absent and detects conflicting writers. Preserve brainstorm's scope and exclude lock declarations from prerequisite detection; deleting it would weaken concurrency protection for the adapters.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

Follow-up pre-implementation review on 2026-10-05 used the issue-refinement research axes plus one `/ll:advise --signal user_requested --host claude-code --model opus` consult (confidence 0.78). Accepted the new slash-skill/MCP partitions: the core manage-issue action in harness-single-shot otherwise has no literal issue path or console command. Added active MCP argument detection, explicit loader-consumer roots and recursive-container guards. A bounded loader probe accepted recursive context aliases with no violations; comparing separately loaded copies raised recursion, and a patched simulation probe demonstrated dispatch/evaluator paths bypassing the simulation runner without executing real commands or model calls. These findings motivate finite analysis and the export restrictions recorded in the companion issue.
Opus also suggested scanning loop parameter defaults. Kept the existing explicit limitation: those defaults/arbitrary context are outside v1's state-owned detection, and authors declare known hidden core requirements. Declined treating MCP `history_search` as issue-coupled: its current handler reads session history, unlike issue history. Classification tables require explicit source-backed judgments; tool names alone are not a semantic inventory. Structure/citation/evidence checks verify the edited issue, not implementation acceptance or a full test-suite result.

## Related

FEAT-3717 consumes this report/graph. FEAT-3582 supplies the rewritten pilot; FEAT-3667 ships its engine/profiles in the wheel. FEAT-2248, EPIC-3581 and FEAT-2354 establish the core/adapter boundary for Issue integration.

## Use Case

A developer searches for a loop to run in a client repo with no issue setup. The portable filter returns only complete cores; a selected brainstorm loop explicitly lists the optional issue/decision adapter prerequisites. Adding a core issue command to a declared-portable loop produces a validation error before it is shipped.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- Final contract review; `/ll:advise` with Opus, confidence 0.80; failure/serialization/output/lifetime clarifications and 225 existing loader tests passed - 2026-10-06
- Follow-up pre-implementation review; `/ll:advise` with Opus, confidence 0.78; resolution/provenance/report corrections and regression requirements - 2026-10-06
- Pre-implementation review on main; `/ll:advise` with Opus, confidence 0.80; learning/context probes and contract updates - 2026-10-06
- `/ll:refine-issue:gap-analysis` - 2026-10-05T20:31:49 - `e4d031f4-efb7-4acd-b532-6b7d02eab780.jsonl`
- Pre-implementation review (Codex; `/ll:advise` with Opus, confidence 0.72; source and bounded load probes) - 2026-10-05
- `/ll:verify-issues` - 2026-10-04T02:15:17 - `7338e0e0-45bb-417c-9acd-76d793d69fe6.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-04T02:12:21 - `e92024fd-e3f0-4727-b856-b77ba777115a.jsonl`
- `/ll:reconcile-issue` - 2026-10-04T02:02:28 - `ff3c4eb4-2263-4904-8752-da1b86a5b6a0.jsonl`
- `/ll:wire-issue` - 2026-10-04T01:59:31 - `03599537-a8c3-4077-be10-3fe84481da10.jsonl`
- `/ll:decide-issue` - 2026-10-04T01:41:39 - `dfdca29c-b349-4087-8e1f-8022626b9966.jsonl`
- `/ll:refine-issue` - 2026-10-04T01:38:39 - `9cf7f744-4459-4907-b6cf-6671c4a04f78.jsonl`
