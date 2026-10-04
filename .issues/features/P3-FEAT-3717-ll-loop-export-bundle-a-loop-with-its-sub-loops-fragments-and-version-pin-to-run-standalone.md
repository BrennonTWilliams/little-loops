---
id: FEAT-3717
type: FEAT
title: 'll-loop export: bundle a loop with its sub-loops, fragments and version pin
  to run standalone'
priority: P3
status: open
discovered_by: portability-review
discovered_date: '2026-10-03'
captured_at: '2026-10-03T22:42:26Z'
labels:
- loops
- cli
- portability
- distribution
blocked_by:
- FEAT-3582
- FEAT-3716
relates_to:
- EPIC-3581
- FEAT-3667
- FEAT-2354
---

# FEAT-3717: ll-loop export: bundle a loop with its sub-loops, fragments and version pin to run standalone

## Summary

Add `ll-loop export <loop> --output <new-directory>` (`-o` alias). Write a self-describing `.loops/` tree containing the selected loop's static YAML dependencies and an exact runtime version requirement. The recipient runs from the bundle directory, or copies the complete tree into their runtime loop directory. Pilot: the rewritten brainstorm loop after FEAT-3582 and FEAT-3716.

V1 is deliberately bounded: static references, a new destination, honest plugin/Issue prerequisites, no vendored executor or Python helpers. No `--include`, `--force`, `install --with-deps` or general asset-declaration feature. Unsupported resolution shapes fail before any output is published.

## Current Behavior

- `ll-loop install` copies one file; its fragments/children continue resolving against the recipient's wheel. Leave that existing single-file behavior intact.
- Imports resolve relative to each consuming loop, then the wheel library. Inheritance parents resolve at each ancestor's directory, but effective inherited imports resolve relative to the final child.
- Runtime children resolve against the shared runtime `loops_dir`, with cwd-literal lookup first. They do not automatically resolve beside a root invoked by an arbitrary explicit path.
- Fragment libraries do not recursively expand their own `import:` entries. Neither a recursive library-import loader nor a dependency closure exporter exists.
- A root's static-child validation checks that a child path exists; it does not prove every child's imports and grandchildren are bundled.
- `requires` is absent from `FSMLoop` and `KNOWN_TOP_LEVEL_KEYS`. `load_and_validate(..., raise_on_error=False)` returns ERRORs; the child executor currently discards that list, so an ordinary new load-time error alone would not enforce a child version pin.
- `__version__` identifies runtime code; `installed_package_version()` identifies installed distribution metadata. They can differ in this local-editable checkout (observed 2026-10-04: source/pyproject 1.166.0, metadata 1.165.0). A reproducible export must not stamp one while claiming it contains the other.

## Expected Behavior

~~~text
ll-loop export brainstorm --output ./brainstorm-bundle

brainstorm-bundle/
  README.md
  .loops/
    brainstorm.yaml
    brainstorm-tournament.yaml
    lib/common.yaml
~~~

Every copied runnable YAML gets `requires: {little-loops: "==<runtime-version>"}`. Fragments stay byte-identical. Loop comments and authored references are preserved. The README describes the root command, exact matching wheel, input/defaults, actual independent core/adapter requirements, detected unresolved limitations, and runtime-supported hosts.

Supported recipient layouts:

1. `cd brainstorm-bundle`, then `LL_HOST_CLI=<host> ll-loop run brainstorm "brief"`; the runtime loop root is this directory's `.loops`.
2. Copy the entire `.loops` tree into the recipient's configured runtime loop directory after checking destination conflicts, then run the documented root alias. Export does not perform that merge.

Running a root by a path in an arbitrary subdirectory does **not** redirect its children's runtime loop root. Do not repeat the old collision advice to "copy into a subdir and run by path"; use an isolated bundle working directory instead.

## Proposed Solution

### Dependency closure and layout

Consume FEAT-3716's `resolve_loop_graph(root_file, loops_dir=..., cwd=...)` and its edge/file-read trace. Use the same loader/resolvers as validation/runtime; do not add a second raw-regex dependency walker. The graph keeps a resolved-source identity and each placement context, not dictionaries keyed only by basename or authored import text.

`ExportFile` records source, destination-relative path and role; `ExportClosure` records the root alias, planned placements, dependency edges and every runnable placement to validate. A source can be copied to multiple destinations when the loader's consumer-relative semantics require that. A destination can receive only identical bytes from multiple sources; conflicting content is a refusal naming both edges/sources.

- Root: preserve its alias/path relative to the project/built-in runtime root and the winning `.fsm.yaml`/`.yaml` suffix. An explicit root outside those roots is allowed and gets its source filename under `.loops/`; the generated README uses that actual alias.
- Static `loop: <name>` children: place the winning file at the matching alias under the bundle's shared `.loops` root. Preserve suffix priority and project shadowing. Resolve all descendants against that same runtime root.
- `from:` parents: place each parent at its referenced alias relative to the destination of the consumer that loads it; recurse through ancestor references. Parent fields are merged by the existing loader, not flattened into the child.
- Effective fragment imports: place each library at the authored relative path beside the final consuming loop. In a new test fixture, a built-in `lib/common.yaml` needed by `oracles/example.yaml` (new) is therefore copied to `.loops/oracles/lib/common.yaml` (new output file). An inherited import is copied relative to the final child's destination, as runtime expects.
- If a copied parent is independently runnable, conservatively collect/validate its own static closure as another consumer too. This can include dependencies overridden by the exported child; document that v1 errs toward a complete set of copied runnable files.
- Collect static child references from resolved states after flow/fragment expansion, not just the root's raw `states` block. Imported fragment actions can contain `loop:` references.
- Treat cycles as graph revisits keyed by source and placement context. A cycle that generates unbounded new placements is refused with the offending chain; a simple same-placement child cycle is collected once. Analysis termination is separate from runtime termination.
- Fragment libraries are copied as the current loader reads them. Refuse a library that itself declares a nonempty `import:`; the current loader silently ignores those nested declarations. Do not add recursive library `import:` semantics; "transitive fragments" means imports of recursively collected runnable loops/parents.

### Refusals and portability allowance

Refuse, with a concise source/state/reference diagnostic:

- Any dynamic `loop:` reference, including in an optional adapter. `--include` cannot prove which runtime names an interpolation will produce, so it is outside v1.
- Absolute or `..`-component dependency references (`from`/`import`/`loop`), or destination paths escaping the staged `.loops` tree. A user-specified absolute root input is allowed; dependencies must still be relocatable.
- Child/parent lookup through a literal cwd file or a `runs/*/workflow.yaml`/internal-name draft fallback. These resolution shapes are not safely alias-preserving; promote the draft or use normal project-loop aliases first.
- Missing/malformed dependencies, source/destination collisions, incompatible preexisting requirements, or a copied runnable file whose closure cannot be validated.
- An incomplete core **or adapter** dependency report. An allowance acknowledges a known requirement, not an unknown graph.

Follow symlinked source files as the existing loader does, copying their file bytes rather than exporting symlinks. Canonicalize source identities for cycle detection and check computed destination containment; do not emit a link to the author's checkout. Do not rename colliding dependencies silently.

Use repeatable `--allow-tier requires-plugin` and `--allow-tier requires-issues` flags, mapping to independent requirement acknowledgments `plugin` and `issues`. Both are needed when the effective core needs both; allowing issues does not implicitly allow the plugin. Core requirements include author declarations as specified in FEAT-3716. Adapter requirements remain in the README without requiring a core allowance.

For conservatively included runnable parents, report any additional requirements separately in the README; require allowances for their core requirements as well, because those files are independently runnable in the emitted bundle. The README distinguishes the selected root's report from additional files' reports.

Adapters are retained, with states and prerequisites named. `adapter: true` is metadata, not a runtime installation guard. Remove the original promise of generic cross-host adapter preflight: no reliable cross-host plugin predicate exists. Brainstorm's tests establish that `sink=none`/`file` bypass its Issue adapters; selecting an Issue adapter requires the documented installation and data.

### Exact runtime requirement

V1 supports a single dependency key and an exact version identity only:

~~~yaml
requires:
  little-loops: "==1.166.0"
~~~

This is an exact-identity contract, **not general PEP 440 support**. No `packaging` dependency or hand-written version-order parser is needed. The only supported string is `==` followed by a nonempty, whitespace-free runtime identity, without wildcards, commas or additional operators. Compare that identity with `little_loops.__version__` as an opaque string; prerelease/local identities must match exactly.

- Optional `FSMLoop.requires: dict[str, str]` defaults to `{}` and is omitted at default. Validate raw mapping/value types, unknown package keys and unsupported constraint forms before dataclass parsing can hide them. Bad metadata produces a clear ERROR at `requires`/`requires.little-loops`, never a traceback.
- If the field is absent/empty, behavior is unchanged. On a feature-aware runtime, if present, emit a version-mismatch ERROR with required/current identity and an install-matching-wheel hint.
- Export writes the exact runtime identity into every runnable placement (root, children and runnable parents). A matching existing pin remains; an incompatible/unsupported pin refuses export. Do not silently replace or weaken it.
- Check inherited effective requirements too: a root cannot overwrite an incompatible requirement from a parent and call the result compatible.
- Preserve `load_and_validate`'s ordinary `raise_on_error=False` return contract. A dedicated requirement checker is used at execution boundaries. Run/resume check before constructing an executor; `_execute_sub_loop` explicitly enforces the child's requirement after loading even though the other validation errors are returned rather than raised. Do not make all previously ignored child errors fatal incidentally.
- Check every runnable node during export validation. A root pin alone is insufficient when a recipient runs an exported child directly.
- Before export, compare runtime identity with `installed_package_version()`. Missing metadata or code/metadata disagreement refuses export with an actionable reinstall/build instruction. This is specifically export provenance, not an extra global runtime requirement for old unpinned loops.
- If installed metadata identifies an editable install, label the README as a development export: an exact version string does not freeze uncommitted helper code, and public-wheel availability/reproduction is unverified. Require a matching built wheel for the recipient acceptance smoke; do not claim that a numeric pin freezes arbitrary source edits.

Older runtimes cannot retroactively enforce this field: today `load_and_validate` warns about unknown `requires` and otherwise ignores it. Capture/document that current behavior before implementing the checker. The README must require installing the exact matching feature-aware wheel, not claim an older wheel will reject the bundle. Supported run commands begin with that install; the YAML field alone is not an old-runtime bootstrap guard.

Use the already-declared `ruamel.yaml` round-trip loader to add requirements while preserving comments and scalar styles. Reparse each emitted loop and compare its raw mapping with the input plus the intended requirement change. No duplicate `requires` keys, unrelated semantic edits or mutation of the input files. Reject malformed/multiple-document YAML through the existing single-mapping contract.

### Closure proof and output publication

Build in a unique sibling temporary directory on the destination filesystem. The destination must not exist, including a dangling symlink (`lstat`/`lexists` semantics). V1 has no overwrite option; choose a new directory.

Before promoting the stage:

1. Run resolution in an isolated subprocess with cwd set to the staged bundle and runtime `loops_dir` set to staged `.loops`. Analyze the root and every runnable placement, recording all resolved/read YAML sources.
2. Assert every recorded source is inside the staged `.loops` tree, and every planned runnable/library/parent was actually exercised in the relevant consumer context. An original-checkout or wheel fallback fails closure even when that fallback file exists and would validate successfully.
3. Run `load_and_validate` on every runnable placement, forwarding the same runtime root and read trace; fail on any ERROR. A root-only validation pass is insufficient. Assert no dependency lookup/read performed by validation escapes the bundle.
4. Apply the report/allowance gate, render README, and only then promote the directory.

Run this proof through an internal verification driver with explicit bundle root/loops directory, using `sys.executable` rather than invoking the public CLI/config discovery. Never walk upward to an ancestor project config, instantiate its BRConfig, or resolve its host. Scrub inherited `LL_*` and `PYTHONPATH` from the child environment; add only the driver's explicit trace/output inputs. Capture a bounded stderr diagnostic and return export exit 1 for timeout/nonzero/crash. The matching interpreter is intentional; fresh-wheel integration separately proves installation isolation. Add an ancestor `.ll/ll-config.json` poison fixture, in addition to cwd/source/builtin poison cases.

This read-trace containment proof replaces the draft's broad "disable built-in library" environment flag. The normal fallback can remain enabled: its use is observable and fails the proof. Do not change unrelated catalog/rename/doctor/admin APIs to mask the wheel, mutate cwd in the caller, or mock the entire filesystem into a false-green result. Resolver instrumentation must include inheritance, fragments and child lookup, including helpers used by filesystem validation.

Trace scope is selected-loop dependency YAML resolution/loading, not every file opened by the process. Catalogue-wide advisory scans (for example artifact-output sub-loop reachability), Python helpers and arbitrary action assets are outside the closure trace. Use the shared typed resolution seam; do not patch `open` or install a global audit hook. An actual dependency lookup must never be reclassified as an advisory read to make the proof pass.

Require an existing destination parent and explicit `--output/-o`. Create a unique sibling stage with `tempfile.mkdtemp`, check destination absence with `os.lstat` immediately before promotion, and publish with `os.rename` (never `shutil.move`, which may nest/copy). Map existing-content/type errors to refusal; clean only the owned stage, never unlink/rmdir the destination. Preexisting empty directories are refused. Contract: export never overwrites/deletes existing content or merges into an existing tree. A concurrent empty directory created in the final check/rename window may be replaced on POSIX; this is the documented residual case, with no file content lost. Do not add platform-specific rename syscalls or claim this standard-library operation provides an absolute no-replace guarantee. Return 0 on success, 1 for input/IO/closure/version/tier refusals, and standard argparse 2 for invalid options. Success prints the bundle path/root command only after promotion; failures leave no final bundle and no traceback.

### README and runtime assets

- Render description, root alias, `input_key`/`required_inputs`, root `parameters` and authored context defaults. Separate caller inputs from runner-injected `run_dir`; child `with:` bindings are internal wiring, not extra root inputs.
- Show exact runtime requirement, independent core/adapter prerequisites, external-file limitations and supported layouts. Additional copied runnable files' reports are available without confusing them with the selected root.
- Enumerate runtime-wired hosts from registry/capability metadata, excluding `TEST_ONLY_HOSTS` and the `opencode`/`pi` stubs. This list means the runtime implements them; it does not certify the particular loop on every host. Use `LL_HOST_CLI`/`resolve_host` in examples and smoke tests.
- Python modules and brainstorm profiles come from the matching wheel (FEAT-3667). No `assets:` schema or helper vendoring. Arbitrary file paths in shell/prompt/context text are not dependencies that export automatically copies; identify them as caller-supplied inputs/requirements.
- Plain install instructions use the matching wheel/version; never silently fall back to latest. Generated `uvx` instructions are deferred from v1 unless an actual optional integration smoke is implemented and passes; an unavailable/skipped test is not evidence.
- A packaged README template is optional. Prefer small typed rendering unless a template helps; register any template file in `PACKAGE_DATA_ASSETS`. Do not create an entire templating framework.

## Integration Map

### Files to Modify

- New `cli/loop/export.py` (new): placements, collision/refusal rules, requirement stamping, isolated closure proof, README and staged promotion.
- `cli/loop/__init__.py`: `export` in `known_subcommands`, parser (`--output/-o`, repeatable `--allow-tier`), lazy import and dispatch.
- FEAT-3716's `fsm/loop_dependencies.py` (new) plus instrumentation in `fsm/fragments.py`/`fsm/loop_paths.py` and filesystem validators: extend only where export needs destination-context tracing; keep one resolver contract.
- `fsm/schema.py`, `fsm/fsm-loop-schema.json`, `fsm/validation/_base.py` and `fsm/validation/__init__.py`: `requires` parsing/round-trip/default omission/known key and checker exports.
- `fsm/validation/structural_rules.py` and `fsm/requirements.py` (new): load diagnostics with unchanged return semantics.
- `cli/loop/run.py`, `cli/loop/lifecycle.py`, `fsm/executor.py`: requirement enforcement before root/resumed/child execution; retain explicit runtime-root forwarding from FEAT-3716.
- `init/install_check.py`: reuse `installed_package_version`; read editable provenance without a host/network probe.
- `package_data.py` only if a new README template file is added.

### Dependent Files and Constraints

- `fsm/topology.load_fsm` bypasses validation. It accepts/round-trips the field for inspection but is not an execution boundary; no unnecessary version rejection there.
- `fsm/persistence.py` and scaffold serialization must retain a nonempty pin; default omission preserves old unpinned JSON/YAML.
- Leave `cmd_install`, its signature and by-name `get_builtin_loops_dir` tests alone. No new install flags or symbol moves are required.
- Keep host invocations behind `resolve_host` and existing runner APIs. No literal host-binary subprocess calls, new paid CI or PR-triggered workflow.

### Tests

- New `test_loop_export.py`: root/child/grandchild/fragment closure, `from:` chains, flow-generated and fragment-generated child refs, compiled suffix priority, project-over-built-in shadowing, nested oracle import placement, effective inherited imports at the final child, same source at multiple destinations, conflicting same-name libraries, cycles and unsupported placement-expanding cycles.
- Refusal fixtures: dynamic core/adapter children, missing dependencies, absolute/`..` refs, cwd-only dependencies, draft fallback, malformed YAML, nested library imports, incomplete reports, both independent allowance flags, incompatible pins, source/metadata drift, existing/nonempty/empty/dangling-symlink destinations and staging cleanup after an injected failure. Simulate a concurrently created nonempty destination/type change at promotion and assert its content survives; characterize the documented concurrent-empty-directory outcome instead of requiring impossible no-replace behavior from plain POSIX rename.
- Read-trace closure fixtures must first demonstrate a normal successful resolution that uses the wheel/original source, then assert the exporter rejects it as outside the stage. Remove/rename original sources after a good export and resolve/execute the bundle with deliberately differing original/built-in fragment contents. Include both inheritance and nested child paths so an uninstrumented seam cannot pass unnoticed.
- `test_fsm_schema.py` and focused requirement tests: raw invalid shapes/operators/packages, exact identity equality, defaults/round trip, inherited mismatch, direct child run, root run/resume and child execution despite `raise_on_error=False`. Assert a fake action-runner counter stays zero for the mismatching FSM. Mock the installed-version/provenance accessor in in-process unit/default smoke fixtures so this checkout's metadata drift does not determine their result; the fresh-wheel integration uses real matching metadata.
- `test_cli_loop_dispatch.py` / `test_ll_loop_execution.py`: registered subcommand/help, output-path type/alias and filter forwarding. Preserve `show`/persistence default JSON shapes in `test_json_output_contracts.py`.
- Default-suite fake-host end-to-end test in a bare git repo, no `ll-init`/plugin/Issue tree: export a portable fixture containing a prompt step and a child/helper shell step, then run it with a poisoned PATH `python3` and verify `LL_PYTHON` reaches the installed package. Use deterministic response fixtures and bounded timeouts; no real model call.
- Fresh-wheel test under the existing integration/`PYTEST_INTEGRATION` convention: build/install the matching local wheel into a fresh venv, run the exported fixture from a bare repo, no local-editable source/PYTHONPATH leakage. Verify helper/profile files resolve from that wheel, not the source checkout.
- Pilot acceptance after FEAT-3582: export brainstorm, run `sink=file` with deterministic fake-host/domain fixtures and an explicit output path, assert valid report/portfolio and no Issue-system writes. Also retain none/file adapter-route tests owned by FEAT-3716.
- `uvx` smoke is integration-marked and skips when unavailable, with no docs/runtime correctness claims derived from a skip.

### Documentation

Update `docs/reference/{CLI,API,loops}.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/ARCHITECTURE.md`, `skills/create-loop/reference.md` and `loops/README.md`. Describe exact-only `requires`, strict static closure, allowances, independent requirements, supported working-directory/root layouts and development-export limitations. Add existing CLI/docs wiring assertions; regenerate existing touched host mirrors if applicable. Mirror `README.md` to `scripts/README.md` if edited. Do not advertise `uvx` or all-host compatibility before evidence exists.

## Program Design

### Types

- `ExportFile`: `source: Path`, `destination: Path` (relative to the stage), `role: str` and incoming dependency edge(s).
- `ExportClosure`: `root_alias: str`, `files: list[ExportFile]`, `runnable_placements: list[Path]` and source/placement guards. Keys include destination context; authored names alone are insufficient.
- `FSMLoop.requires: dict[str, str]` — exact-runtime identity map, default `{}`. New known/schema key; omission at default.
- Reuse `LoopDependencyGraph`/`PortabilityReport` from FEAT-3716; no parallel graph representation for dependency resolution.

### Signatures

- `collect_export_closure(graph: LoopDependencyGraph, *, loops_dir: Path, cwd: Path) -> ExportClosure` — new planner in `cli/loop/export.py` (new), using the established resolver/read trace for each placement context.
- `validate_requires(fsm: FSMLoop, runtime_version: str) -> list[ValidationError]` and `enforce_requires(fsm: FSMLoop) -> None` — new `fsm/requirements.py`. Raw metadata validation precedes parsing; the first helper reports mismatches, the second raises `ValueError` at execution boundaries.
- `cmd_export(args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — new handler; exit codes 0/1 as specified above.
- `verify_export_closure(bundle_dir: Path, closure: ExportClosure) -> None` — new isolated proof driver; raises a bounded diagnostic on an outside path or ERROR.
- `render_export_readme(closure: ExportClosure, reports: Mapping[str, PortabilityReport], runtime_version: str) -> str` — new typed renderer.
- `installed_package_version(pkg_name: str = "little-loops") -> str | None` — existing metadata accessor, reused for export provenance.

### Call Path

`main_loop` → `cmd_export` → `resolve_loop_path` / `resolve_loop_graph` → `collect_export_closure` → source/pin/report checks → stage copy and round-trip pin edits → `verify_export_closure` → README → promotion.

Execution: `cmd_run` / `cmd_resume` → `load_and_validate` / `enforce_requires` → `PersistentExecutor`. Child: `FSMExecutor._execute_sub_loop` → `load_and_validate(..., raise_on_error=False, loops_dir=shared_root)` → `enforce_requires` → child `FSMExecutor`.

### Decision Rules

The closure/refusal/exact-pin/publication rules in Proposed Solution are normative. No outside lookup, unknown dependency, incompatible pin or existing destination may be converted into an implicit fallback or a successful partially written bundle.

## Implementation Steps

1. Consume the landed FEAT-3716 resolver/report/trace contract. Build the placement plan with unsupported-shape and collision fixtures before CLI wiring.
2. Add exact-only `requires` field, load diagnostics, execution-boundary enforcement and round-trip stamping; validate every runnable placement.
3. Build isolated closure proof and new-directory staging/promotion; verify failure leaves inputs/destination untouched.
4. Add export CLI, report allowances and concise README with supported root-layout commands.
5. Run default-suite fake-host/interpreter-isolation tests and the post-rewrite brainstorm acceptance run; run matching fresh-wheel integration smoke before advertising a distributable pilot. Update docs, then full local suite, lint and type checks.

## Impact

- **Priority**: P3 — blocked by FEAT-3582 and FEAT-3716, outside the EPIC-3581 merge gate.
- **Effort**: Large — consumer-relative placement, runtime resolution and isolated closure proof are the substantial work.
- **Risk**: Medium — a false-green closure or weak version pin silently shifts behavior on a recipient's machine.
- **Breaking Change**: No for unpinned loops or existing install. Exact pins intentionally refuse mismatching runtimes.

## Acceptance Criteria

- [ ] Export is a real dispatched subcommand with `--output/-o` and repeatable independent tier allowances; no include/force/install scope is added.
- [ ] Root, static children, parents and effective imports form a relocatable tree, respecting shared child-root lookup and final-consumer fragment directories; collisions/unsupported references fail explicitly.
- [ ] Closure proof exercises every runnable placement and all dependency kinds, validates every runnable YAML, and rejects any lookup/read outside staged `.loops` even when the wheel fallback succeeds.
- [ ] Exact-only `requires` is known/schema-declared, raw-validated, preserved and enforced before run/resume/child actions. Each runnable placement is pinned; incompatible inherited/existing pins and export code/metadata drift refuse.
- [ ] Source comments/styles/semantics are preserved except intended pin additions; source files are unchanged. Staging publishes only after all gates pass, refuses preexisting destinations and never replaces/deletes existing content; concurrent-empty-directory behavior is documented/tested.
- [ ] Reports/allowances use independent plugin/issues requirements; known adapters are documented without a runtime-preflight promise, and unknown adapter dependencies still refuse export.
- [ ] README names real inputs/defaults, wired runtime hosts, assets provided by the matching wheel and caller-supplied files; arbitrary path invocation is not presented as changing the runtime child root.
- [ ] Bare-repo fake-host/interpreter-isolation smoke passes in the default suite; matching fresh-wheel integration smoke and post-FEAT-3582 brainstorm `sink=file` acceptance pass before calling the pilot distributable.
- [ ] Existing JSON/persistence/install/dispatch/docs gates remain valid; `python -m pytest scripts/tests/`, lint and type checks pass. An unavailable uvx never supplies positive test evidence.

## Out of Scope

Dynamic candidate-domain declarations; nested fragment-library imports; asset discovery/vendoring; alternate-harness compilation; generic adapter installation preflight; overwrite/replacement; install-with-dependencies; environment lockfiles; host-by-host certification. Exact identity pins the little-loops runtime, not all Python dependencies, host versions or model outputs.

## Review Notes

2026-10-04: Reconciled the earlier contradictory research after source review and `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.74). Removed the stale NON_VALID label rather than claiming an unrun re-verification. Accepted a static refuse-first scope, shared source-resolution trace, independent requirements, exact-only pins on every runnable file, explicit child enforcement, isolated containment proof and new-directory publication. Used the already-declared ruamel round-trip support instead of an append-only YAML edit; no packaging dependency is needed for the restricted identity contract. Opus's dissent favored patch-compatible PEP 440 pins or deferring export until the classifier is exercised; v1 makes no untested patch-compatibility claim and retains the existing blocker on FEAT-3716.

Second Opus pass (2026-10-04, confidence 0.74) found no structural contradiction after minimum refinements. Added explicit driver/environment/config isolation, nested-library refusal, old-runtime pin limits, deterministic metadata fixtures and the precise POSIX publication contract. Kept one resolver-event seam rather than tracing arbitrary file opens. The atomic no-replace guarantee was narrowed to protecting existing content; kernel-specific rename wrappers would exceed this v1 scope.

## Related

FEAT-3716 provides classification/resolution. FEAT-3582 provides the rewritten brainstorm/tournament pilot; FEAT-3667 supplies wheel-owned helpers/profiles. EPIC-3581 and FEAT-2354 establish the standalone/core-adapter boundary.

## Use Case

A consultant exports brainstorm for a client who will install the matching wheel and a host CLI but will not run ll-init or adopt an issue tree. The client runs from the isolated bundle directory with sink=file and an explicit output path; the bundled tournament/fragments resolve locally, the resulting report is validated, and a different runtime version fails before executing the mismatching loop.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-04T02:47:52 - `334d5872-a8ff-4d86-9e1f-5c1cd897a218.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-04T02:44:23 - `80601c5b-ccf3-4432-90f3-bdfce27b419c.jsonl`
- `/ll:wire-issue` - 2026-10-04T02:34:45 - `eb45c0ef-1b4d-4bd9-87ed-0bffc9a78c6e.jsonl`
- `/ll:refine-issue` - 2026-10-04T02:26:46 - `42cdd517-6a19-4408-982f-a99f1aebdc70.jsonl`
