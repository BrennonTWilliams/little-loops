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
verify_verdict: NON_VALID
---

# FEAT-3717: ll-loop export: bundle a loop with its sub-loops, fragments and version pin to run standalone

## Summary

Add `ll-loop export <loop> -o <dir>`. It writes a self-describing bundle that runs in any repo with only the `little-loops` wheel and a supported host CLI: no `ll-init`, no plugin, no `.issues/`. The bundle holds the loop, its sub-loops and imported fragments (as a drop-in `.loops/` tree), a version pin checked at load, and a README with a one-line run command. Pilot: the rewritten brainstorm loop (EPIC-3581).

## Context

Captured 2026-10-03 from a portability review (ll-product hub session). Source-verified at `8baa8a471`:

- **No new runtime needed.** `ll-loop run <path>` already works in a bare repo (`fsm/loop_paths.py:46-48`; state dirs created on demand at `cli/loop/run.py:390`, `session_store/schema.py:1722`).
- **`ll-loop install` is single-file.** It runs `shutil.copy2` at `cli/loop/config_cmds.py:134` and `:181`. An installed loop's `import:` fragments and `loop:` sub-loops still resolve from the **installed wheel's** built-in library (`fsm/fragments.py:99-110`; `fsm/executor.py:1166-1167` via `resolve_loop_path`). An installed loop therefore silently tracks whatever wheel version the user has, and a wheel upgrade can change its fragments and children underneath it.
- **Resolution order makes bundling cheap.** Fragments resolve `<loop_dir>/<import>` before the built-in library, and sub-loops resolve project `.loops/` before the built-in library. A bundle laid out as a `.loops/` tree therefore pins its fragments and children **without rewriting any references**.
- **What actually works across hosts.** Wired hosts: claude-code, codex, gemini, omp, kimi-code, qwen. `opencode` and `pi` are registered stubs that raise `HostNotConfigured` (`host_runner.py:1646-1774`; `README.md:41`). Bundle docs must not list them.
- **`uvx` is undocumented in this repo.** Install docs are uniformly `pip install little-loops && ll-init`. A `uvx --from little-loops==X ll-loop run …` path is plausible because the wheel is self-contained and `LL_PYTHON` is injected as `sys.executable` (`fsm/runners.py:333`), but it is untested.

Strategy tie-in (hub): B1 "give away the loops, sell the trust" and B2 services. A loop that runs in a client's repo with zero ecosystem adoption is the engagement artifact for the managed-AI-ops Stage 1 ("Observe"). Each bundle run also writes `.ll/history.db` with the typed event record, so the free half distributes the L5 asset the paid half ingests. The hub's on-the-stack §8 Q6 names a consumer-who-is-not-the-author as the only real test of the seams; export is the tool for running that test.

## Current Behavior

There is no way to hand someone a loop. `install` copies one YAML file and leaves its dependencies tied to the recipient's wheel version. Nothing tells the recipient what the loop needs, which host it supports, or which states call into the issue system.

## Expected Behavior

```
ll-loop export brainstorm -o ./brainstorm-bundle
```

produces:

```
brainstorm-bundle/
  README.md                 # what it does, requirements, run commands, tier, adapters
  .loops/
    brainstorm.yaml         # with `requires:` pin added
    brainstorm-tournament.yaml   # sub-loops, transitively
    lib/common.yaml         # imported fragments, transitively, same relative paths
```

- Recipient copies `.loops/` into their repo (or runs from the bundle dir) and runs `ll-loop run brainstorm "brief"`. Both resolve correctly because `.loops/` is checked before the built-in library.
- **Version pin.** New top-level `requires: {little-loops: ">=X.Y,<X+1"}` (schema addition, not required), checked when the loop is loaded. Export writes the current version. A mismatch fails before the first state with an actionable message. Loops without the field behave as today.
- **Portability gate.** Export uses the FEAT-3716 portability classifier. `requires-plugin` / `requires-issues` loops are refused unless `--allow-tier <tier>` is given. Adapter states (`adapter: true`) are kept, and the README lists them as opt-in, with their requirements. An adapter route that is selected at runtime without its requirement present fails with a clear message, not a confused LLM step.
- README is generated from loop metadata: description, context keys / `with:` inputs and their defaults, tier and adapters, wired hosts, minimum version, and run commands for `pip` and (once smoke-tested) `uvx`.
- **Not exported:** Python helper modules (e.g. `little_loops.brainstorm_engine`). They ship in the pinned wheel, and the pin covers them. There is no vendored executor.

## Motivation

- Users want to run a specific loop (brainstorm first) in their own project without adopting the ecosystem.
- `install`'s silent wheel-tracking is a correctness gap independent of export. A pinned, self-contained `.loops/` tree fixes it.
- It is a concrete test of the loop-schema seam under an outside consumer (client engagements).

## Proposed Solution

`cli/loop/export.py`:

1. `resolve_loop_path` → collect the closure of `import:` paths (from `fragments.resolve_fragments` traversal; expose a `collect_imports()` helper rather than re-parsing) and `loop:` references (static names only; error on interpolated names unless `--include <name>` is supplied).
2. Copy files preserving relative paths under `<out>/.loops/`. Inject `requires:` into the root loop only, editing text so that comments are preserved.
3. Run the portability classifier and enforce the gate. Render the README from a template.
4. Run `ll-loop validate` against the bundle from a temp cwd with the built-in library **masked** (env/flag that disables the built-in fallback), proving the bundle is closed. A missing dependency then fails export instead of failing on the recipient's machine.

Reuse `ll-loop install` for the copy step, or extend `install --with-deps` to share the closure walk. Decide in refinement, but keep one closure implementation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Constraint on the closure design**: whatever walk is chosen must reproduce each file's own resolution base (see Integration Map finding on directory-relative resolution), include `from:` parents read from the raw dict, and keep a single implementation shared with `install --with-deps` if that route is taken.
- **Convention for the output flag**: `ll-loop` output-path flags are long-form `type=Path`, `metavar="PATH"` (`--output` in `evidence`, `--out` in `scaffold-eval`/`scaffold-verify`); `-o` is unused by any `ll-loop` subparser, so `-o` here would be an alias, not a precedent.
- **Convention for overwrite refusal**: two shapes exist — `cmd_templatize` pre-checks `out_dir.exists() and not args.force`, builds in a sibling `<out>.tmp-<pid>` and promotes atomically (`cli/artifact/templatize.py:promote`); `cmd_install` refuses without `--force` and returns 1. A partially written bundle is the failure mode the first shape avoids.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/export.py` (new): closure walk, copy, `requires:` injection, README render, masked-library self-validate
- `scripts/little_loops/cli/loop/__init__.py`: `export` subparser
- `scripts/little_loops/cli/loop/config_cmds.py:106-184` `cmd_install`: share the closure walk (`--with-deps`) or call into export; one implementation
- `scripts/little_loops/fsm/fragments.py`: expose `collect_imports()` (transitive import paths) and a flag/env to disable the `_BUILTIN_LOOPS_DIR` fallback (fragments.py:31, :99-110)
  > ⚠ Superseded — anchors stale (now :40); no nested imports to traverse
- `scripts/little_loops/fsm/loop_paths.py`: same built-in-fallback mask for `resolve_loop_path`
- `scripts/little_loops/fsm/fsm-loop-schema.json`: top-level `requires`
- `scripts/little_loops/fsm/validation/structural_rules.py`: `requires:` version check at load

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.requires` field + `from_dict`/`to_dict` (omit at default so `show --json`/persistence output is unchanged) [Agent 2 finding]
- `scripts/little_loops/fsm/validation/_base.py` — add `"requires"` to `KNOWN_TOP_LEVEL_KEYS`; re-exported via `fsm/validation/__init__.py` (docstring map and `__all__`, update both) [Agent 1 + 2 finding]
- `scripts/little_loops/fsm/validation/reachability.py:_validate_artifact_output_subloop_reachability` (line 127, `roots = {loop_dir, get_builtin_loops_dir()}`) — binds `get_builtin_loops_dir` by name at import; must honour the built-in mask [Agent 1 + 2 finding]
- `scripts/little_loops/cli/loop/info.py` — `get_builtin_loops_dir()` at :203 (listing/lib-path fallback `builtin_candidate = get_builtin_loops_dir() / lib_path` in `cmd_fragments`) and :1742; `resolve_inheritance` at :71; each needs the mask or an explicit note that it is out of the closure proof [Agent 1 + 2 finding]
- `scripts/little_loops/cli/loop/rename.py` (:49, :72, :186), `cli/loop/header.py` (:57), `cli/doctor.py` (:1000), `cli/logs.py` (:2052), `fleet_improve.py` (:335) — remaining by-name `get_builtin_loops_dir` consumers; decide mask-or-exempt for each so the "every path that reads the fallback" claim is accurate [Agent 2 finding]
- `scripts/little_loops/fsm/topology.py:load_fsm` (:119) — second loader (`resolve_inheritance` → `resolve_flow` → `resolve_fragments` → `FSMLoop.from_dict`) that bypasses `load_and_validate`; the `requires:` check will not run here, and `from_dict` must still accept the key [Agent 2 finding]
- `scripts/little_loops/package_data.py` `PACKAGE_DATA_ASSETS` — register the README template if shipped as a file; also checked by `cli/verify_package_data.py` [Agent 1 finding]
- `scripts/little_loops/cli/loop/__init__.py:main_loop` — the `known_subcommands` set (:64) must gain `"export"` (otherwise rewritten to `run export`); the `install` parser (:687) and dispatch `elif args.command == "install"` (:1167) are the sibling pattern [Agent 1 finding]

### Dependent Files (Callers/Importers)
- FEAT-3716 `classify_portability()` (tier gate, adapter list)
- `host_runner.py:2560-2571` `_HOST_RUNNER_REGISTRY` + `TEST_ONLY_HOSTS` (README host list; exclude stub runners)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/topology.py:load_fsm` — imports `resolve_fragments`/`resolve_inheritance`; any `collect_imports`/`from:`-walk change must stay compatible [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py:71` (spec-loading helper calling `resolve_inheritance(spec, path.parent)`) — same compatibility constraint [Agent 1 + 2 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py` — `resolve_inheritance` called at :2047 (unknown-key pre-scan helper) and :2153 (main load); the `requires:` check lives beside the latter [Agent 2 finding]
- `scripts/little_loops/cli/loop/run.py:149` (`cmd_run` load, `raise_on_error=True` — runtime consumer of the pin), `fsm/executor.py:1163` `_execute_sub_loop` (`raise_on_error=False`, so a pin on a child would not fail fast), `cli/loop/edit_routes.py:51`, `cli/doctor.py:1022`, `cli/logs.py:2358`, `cli/artifact/policy_revision.py:95` — other `load_and_validate` callers; none change signature [Agent 2 finding]
- `scripts/little_loops/cli/advise.py:136` — only non-host_runner consumer of `registered_host_names()`; no stub-filter predicate exists, so the README host list needs a new one (stubs still returned today) [Agent 1 + 3 finding]
- `scripts/little_loops/cli/loop/lifecycle.py`, `cli/loop/edit_routes.py`, `cli/queue.py` (lazy), `cli/loop/testing.py`, `cli/loop/feed.py`, `cli/loop/runner.py`, `cli/loop/audit.py`, `analytics/variance.py` (lazy) — import `resolve_loop_path` / `load_loop*`; unaffected unless the mask changes their signatures [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py`, `cli/loop/_scaffold_core.py`, `cli/loop/scaffold_eval.py` — consume `FSMLoop.to_dict`/`from_dict`; `requires` must be omitted at default [Agent 2 finding]
- `scripts/little_loops/loops/fleet-loop-improve.yaml:55` — reads `get_builtin_loops_dir()` directly (pinned by `test_builtin_loops.py` `"get_builtin_loops_dir" in action`); do not rename the symbol [Agent 2 finding]

### Similar Patterns
- `cli/loop/evidence.py` (FEAT-3182): existing bundle-writing command for run evidence
- `cli/loop/config_cmds.py` `cmd_install`: name/path resolution and collision handling

### Tests
- New `scripts/tests/test_loop_export.py`: closure (loop → child → fragment → nested fragment), masked-library validate, `requires:` mismatch, tier refusal, dynamic sub-loop refusal, collision
- CI smoke: fresh venv (+ `uvx` when present), bare `git init`, fake host, exported portable loop end to end

_Wiring pass added by `/ll:wire-issue`:_

Existing tests to update:
- `scripts/tests/test_cli_loop_dispatch.py` — add `("little_loops.cli.loop.export", ["cmd_export"])` to the `_mock_handlers` `handler_specs` list and a `test_export_routes_to_handler` modelled on `test_scaffold_eval_routes_to_handler` [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` (~:1740-1867) — add a "registered in `known_subcommands`" + `--help` exits 0 test beside the fragments/audit/edit-routes ones [Agent 2 + 3 finding]
- `scripts/tests/test_fsm_schema.py` — add `requires` coverage in the `TestFSMLoopArtifactMode` shape (~:4257: defaults, omit-at-default, `from_dict`, round trip, `"requires" in KNOWN_TOP_LEVEL_KEYS`) plus a schema-JSON presence check beside `TestTamperGuard` (~:4937) [Agent 2 + 3 finding]
- `scripts/tests/test_fsm_fragments.py` — new `collect_imports` class beside `TestResolveFragmentsImport` (reuse its `lib_dir`/`common.yaml` fixtures; add nested-import and cycle cases only if nested `import:` is added) [Agent 3 finding]
- `scripts/tests/test_fsm_loop_paths.py` — mask tests in the `test_resolve_loop_path_*(tmp_path)` style (masked fallback raises `FileNotFoundError`; cwd same-name file does not leak) [Agent 3 finding]
- `scripts/tests/test_fsm_validation_reachability.py` `TestLoopReferenceValidation` (~:978) — currently relies on the real built-in dir via by-name binding at `reachability.py:13`; add masked-closure cases here [Agent 3 finding]

Tests that may break:
- `scripts/tests/test_cli_loop_next.py` `TestCmdInstall` (~:350-566) — patches `little_loops.cli.loop.config_cmds.get_builtin_loops_dir` by name; if `cmd_install` is refactored to share the closure walk with `export.py`, the patch no longer reaches the moved read [Agent 2 + 3 finding]
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopInstall` (~:838-915) — full `main_loop()` install path, incl. `test_install_accepts_arbitrary_path_via_full_cli` (BUG-3367) [Agent 2 + 3 finding]
- `scripts/tests/test_ll_loop_commands.py` (~55 patches of `little_loops.cli.loop.info.get_builtin_loops_dir`), `test_feat_3352_mcp_loop_list.py`, `test_json_output_contracts.py:69` — do not rename or move that symbol in `info.py` [Agent 3 finding]
- `scripts/tests/test_json_output_contracts.py` — pins `show`/`list` JSON shape; verifies `requires` is omitted at default [Agent 2 finding]
- `scripts/tests/test_cli_doctor_install_checks.py` (~:638-679) and `test_cli_loop_rename_cleanup.py:173` — patch `little_loops.fsm.loop_paths.get_builtin_loops_dir`; a mask implemented there must keep that name patchable [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` `GATED_HOSTS` mirror gate — trips on any `skills/create-loop/*.md` edit; run `ll-adapt --host <gemini|kimi-code|qwen> --apply` [Agent 2 finding]

New tests to write (patterns):
- Subcommand module test: follow `scripts/tests/test_ll_loop_scaffold_eval.py` (`_make_project(tmp_path)` + `monkeypatch.chdir`, call handler directly) for `test_loop_export.py` [Agent 3 finding]
- Export → validate round trip: precedent `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` (generate, then validate via `main_loop(["ll-loop", "validate", path])`) [Agent 3 finding]
- Fake-host e2e: `ll-fake-host` + `LL_HOST_CLI=fake`, skipping on `shutil.which("ll-fake-host") is None` (`test_enh3538_token_observations.py::_fake_host_env`); no existing test runs a full `ll-loop run` against it, so this is the first [Agent 3 finding]
- Fresh-venv smoke: model on `scripts/tests/test_wheel_smoke.py` `TestWheelSmoke` (`installed_venv` fixture, `@pytest.mark.integration`, gated on `PYTEST_INTEGRATION=1`); no `uv`/`uvx` skip helper exists — add one beside `tests/helpers.py::require_node` [Agent 3 finding]
- Bare-repo project fixture: `test_cli_e2e.py` `E2ETestFixture.e2e_project_dir` (git init + `.ll/ll-config.json`) [Agent 3 finding]
- Optional doc-presence pin: `test_wiring_cli_registry.py` `DOC_STRINGS_PRESENT` (~:147-162) for `ll-loop export` in `CLI.md`/`LOOPS_GUIDE.md` [Agent 2 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md`: sharing loops section
- `README.md`: standalone/`uvx` usage only after the smoke test passes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — new `#### \`ll-loop export\`` section beside `ll-loop install <loop>` (~:1308), `fragments` (~:1350), `edit-routes` (~:1542); document the load-time `requires:` ERROR in the validation-rules list (~:1134-1167) [Agent 2 finding]
- `docs/reference/API.md` — `FSMLoop` dataclass block (~:5786-5834) add `requires`; `little_loops.fsm.fragments` row (~:5745) add `collect_imports()`; `load_and_validate` section (~:6751) new ERROR/`Raises`; new `little_loops.cli.loop.export` section beside `scaffold_eval` (~:4486) / `evidence` (~:4522) [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — subcommand table (~:1080-1100, `install` row at ~:1094) add `export` row; cross-reference from "Reusable State Fragments" (~:1245) and "Loop Template Inheritance via `from:`" (~:1294) [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — "Optional Loop-Level Settings" (~:362-388) add `requires:` [Agent 2 finding]
- `docs/reference/loops.md` — loop-level keys near `circuit:` (~:1111) [Agent 2 finding]
- `docs/ARCHITECTURE.md:190` — file tree line `config_cmds.py   # validate, install`; add `export.py` [Agent 2 finding]
- `skills/create-loop/reference.md` (~:797 "Related top-level keys: `import:` … `fragments:`") — add `requires:`; triggers the ll-adapt mirror gate (`.gemini/`, `.qwen/` copies) [Agent 2 finding]
- `scripts/little_loops/loops/README.md` (~:5, :203) — install/`.loops/` customization prose; add pointer to export [Agent 2 finding]
- `docs/runbooks/FLEET_LOOP_REVIEW.md:191` — "Shadowed" trap names `ll-loop install`; an exported `.loops/` tree shadows built-ins identically (note, no required edit) [Agent 2 finding]
- `README.md:146` / `scripts/README.md:146` (mirrored; `command cp -f README.md scripts/README.md` after edit) — "When a built-in is almost right…" line; export mention only after the smoke test passes [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — no new `ll-*` entry point needed (`ll-loop = "little_loops.cli:main_loop"`); touched only if `packaging` is added, with a justification comment beside the pin per CLAUDE.md [Agent 1 + 2 finding]
- `.claude/CLAUDE.md`, `.claude-plugin/plugin.json`, `hooks/hooks.json`, `config-schema.json` — checked, no `ll-loop` subcommand list; no change [Agent 1 + 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Closure has three edges, not two.** `from:` parents (`fsm/fragments.py:resolve_inheritance`, resolved via `resolve_loop_path` with built-in fallback; e.g. `loops/lib/apo-shape-a.yaml` has `from: lib/apo-base`) are a third dependency edge the Summary omits. A parent's `import:`/`fragments:` survive the merge and resolve relative to the **child's** `loop_dir`, not the parent's.
- **`import:` is one level deep today.** `resolve_fragments` reads only `lib_data.get("fragments", {})`; a library's own `import:` is never read and no file under `scripts/little_loops/loops/lib/` has one. `collect_imports()` can only be transitive if nested-import resolution is also added to `resolve_fragments`; otherwise "transitive fragments" is vacuous for the shipped library. Cycle handling exists only for `from:` (`_seen` tuple, `ValueError("Circular `from:` chain")`).
- **The built-in fallback lives in more places than the two the Files-to-Modify list names.** It is `fsm/fragments.py` `_BUILTIN_LOOPS_DIR` (separate constant, duplicates `get_builtin_loops_dir()`), `fsm/loop_paths.py` `resolve_loop_path` step 4, and direct `get_builtin_loops_dir()` use that bypasses `resolve_loop_path`: `fsm/validation/reachability.py:_validate_artifact_output_subloop_reachability` (scans `{loop_dir, builtin}` with `rglob`), `cli/loop/info.py:cmd_fragments`, `cli/loop/run.py` `--builtin`, `cli/doctor.py`, `cli/logs.py`. Each importer binds `get_builtin_loops_dir` by name, so a mask on `loop_paths` alone does not reach `config_cmds`, `info` or `reachability`. A closure proof is only as strong as the mask's coverage of these.
- **`resolve_loop_path` checks `Path(name_or_path).exists()` first, relative to cwd**, before `loops_dir`. A masked self-validate run from a temp cwd must not have a same-named file/dir there.
- **No `LL_*` toggle is read anywhere under `fsm/`** (only `LL_PYTHON` is injected at `fsm/runners.py:333`). Repo convention for toggles is `LL_`-prefixed `os.environ.get` at the point of use; ambient `LL_*` vars leak into descendant processes, so an env-based mask set around the self-validate must be scoped and restored.
- **`requires:` plumbing**: `fsm-loop-schema.json` has top-level `additionalProperties: false` (documentation/test artifact; no runtime loader). At runtime an unknown top-level key is only a WARNING from `load_and_validate` via `KNOWN_TOP_LEVEL_KEYS` (`fsm/validation/_base.py`). Fields are added in `fsm/schema.py` (`FSMLoop` dataclass, `to_dict` omit-at-default, `from_dict`) + `_base.py`; the JSON schema is updated for some fields (`tamper_guard`, `default_idle_timeout`) and not others (`artifact_mode`, `visibility`) — no test enforces parity.
- **Load-time check sits in `load_and_validate`** (`fsm/validation/structural_rules.py`), not in a `structural_rules` rule function. `cmd_run` loads with `raise_on_error=True` before building any executor; sub-loops load in `executor._execute_sub_loop` with `raise_on_error=False`, so a pin on a child would not fail fast — the pin belongs on the root only, as the issue says.
- **No version-specifier machinery exists.** `packaging` is neither declared in `scripts/pyproject.toml` nor imported; `init/install_check.py` (`check_version`, `_version_key`) does ordering only, and `init/validate.py:_check_little_loops_version` is a plain `!=`. A range pin like `">=X.Y,<X+1"` therefore needs either a new dependency (CLAUDE.md requires a justification comment beside the pin) or a deliberately restricted hand-parsed grammar. Installed version source elsewhere: `importlib.metadata.version("little-loops")`; `little_loops.__version__` is `scripts/little_loops/__init__.py:97`.
- **Subcommand registration is four edits in `main_loop`** (`cli/loop/__init__.py`): the `known_subcommands` set (~line 64; without it `ll-loop export …` is rewritten to `ll-loop run export …`), `add_parser` + `set_defaults(command=…)`, the `elif args.command` dispatch, and the lazy import. `-o` is unused by any `ll-loop` subparser; bundle-writing siblings use `--output` (`evidence`) and `--out` (`scaffold-eval`/`scaffold-verify`).
- **Host list**: `registered_host_names()` (`host_runner.py`) removes only `TEST_ONLY_HOSTS`, so it still returns `opencode` and `pi`. Nothing marks a runner as a stub; the discriminators available are the `HostNotConfigured` raise in `build_*` and `RUNTIME_HOST_CAPABILITIES[...].report_rows` carrying an `"unsupported"` entry with empty `HostCapabilities()`. The "wired hosts" filter the AC requires has no existing predicate.
- **Stale anchors in this issue** (verified 2026-10-04): `fragments.py:31` is now `:40`; `executor.py:1166-1167` is now `:1161-1163` (`_execute_sub_loop`); `run.py:390` is now `:391`; `README.md:41` is now `README.md:37` and `:77`. `config_cmds.py:134`/`:181` `copy2` sites and `host_runner.py:1646-1774`/`:2560-2571` are accurate.
- **FEAT-3716 is not in code.** `classify_portability`, `PortabilityTier`, the tier strings, `adapter: true` and a `portability:` field appear only in the two issue files; planned home is `fsm/validation/portability_rules.py` (does not exist). `scripts/tests/test_portability_gate.py` is an unrelated BSD/GNU shell scanner.
- **Brainstorm pilot is pre-rewrite.** `scripts/little_loops/loops/brainstorm.yaml` has `import: [lib/common.yaml]`, no `loop:` states, no `from:`; `brainstorm_engine.py`, `brainstorm-profiles/` and the tournament child do not exist yet (FEAT-3582/FEAT-3667). Wheel-shipped assets are reached via `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine`; no mechanism lets a loop read a data directory relative to its own file, and no `assets:` declaration exists in the schema.

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Bundle layout invariant is directory-relative, not bundle-root-relative.** `import:` resolves `<dir of the file being loaded>/<import>` then the built-in fallback (`fsm/fragments.py:resolve_fragments`); `from:` parents resolve via `resolve_loop_path(parent, <child dir>)` and a grandparent resolves against the *parent file's* directory (`resolve_inheritance`). Built-in loops under `loops/oracles/` (`generator-evaluator`, `plan-node-refine`, `resolve-decision`, `enumerate-and-prove`, `research-coverage`) declare `import: [lib/…]` but `loops/oracles/lib/` does not exist — they resolve only through the built-in fallback today. A bundle that copies an `oracles/` loop into `.loops/oracles/` with fragments at `.loops/lib/` would fail masked validate. "Pins fragments without rewriting references" therefore holds only for loops whose import base directory contains the imported path; the closure walk must record, per source file, the directory its references resolve against.
- **Static and runtime sub-loop resolution use different base directories.** `_validate_loop_references` and `_validate_with_bindings` resolve with the validated file's `path.parent`; `executor._execute_sub_loop` resolves with the run's `loops_dir`. For a sub-loop reference inside a subdirectory loop the two can disagree, so a masked self-validate does not by itself prove the runtime resolution succeeds.
- **`FSMLoop.imports` already exists** (`fsm/schema.py`, populated from `data.get("import", [])`, not serialized by `to_dict`); consumers are `fsm/validation/meta_rules.py` and `cli/loop/edit_routes.py`. It holds strings as written, not resolved paths.
- **`from:` is stripped during load** (`resolve_inheritance` pops it after merge), so the parent edge is visible only in the raw YAML dict; a closure walk must read the raw spec, not `FSMLoop`.
- **Static `loop:` extraction is not shared.** The `"${" in name` dynamic-name test is repeated inline (`reachability.py:_validate_loop_references`, `topology.py:_is_dynamic`, `cli/loop/header.py`, `structural_rules.py`); no helper returns a set of `loop:` targets to a caller, and no closure walker exists for any edge type.
- **Comment-preserving `requires:` injection has no top-level precedent.** Round-trip edits use `ruamel.yaml` `YAML(typ="rt")` + `file_utils.atomic_write` (`loops/yaml_state_editor.py:replace_action`, `fsm/route_table.py:RouteTableApplier`), both state-scoped; `cli/loop/rename.py` does line-oriented regex edits with `write_text`. `ruamel.yaml>=0.18` is already a declared dependency.
- **Installed-version accessor exists**: `init/install_check.py:installed_package_version() -> str | None` is documented as the single source of truth for the installed version; the Program Design's direct `importlib.metadata.version` call should go through it or state why not. Version comparison elsewhere is ordering (`check_version`) or `!=` (`init/validate.py:_check_little_loops_version`); no specifier grammar exists.

## Implementation Steps

1. `collect_imports()` + built-in-fallback mask; prove a closure validates masked.
2. `requires:` schema + load check.
3. `export` command + README template + tier gate (after FEAT-3716).
4. Smoke test; export brainstorm post-FEAT-3582 as the acceptance run.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- The built-in fallback can be disabled for **every** path that reads it (`fragments._BUILTIN_LOOPS_DIR`, `resolve_loop_path`, and the direct `get_builtin_loops_dir()` users in `reachability.py`, `info.py`, `config_cmds.py`), verified by a test that a bundle missing one fragment/child fails masked validate. Decide whether nested `import:` resolution is added alongside `collect_imports()`; today it is one level.
- `requires:` parses, round-trips through `FSMLoop.to_dict`/`from_dict`, is in `KNOWN_TOP_LEVEL_KEYS`, and a mismatch raises from `load_and_validate` under `raise_on_error=True`. Coverage follows the `TestFSMLoopArtifactMode` shape in `scripts/tests/test_fsm_schema.py` (defaults, omit-at-default, from_dict, round trip, known-key). Resolve the `packaging`-vs-restricted-grammar question first; either way `scripts/pyproject.toml` and its comment are touched only if a dependency is added.
- `ll-loop export` is dispatched (not rewritten to `run export`), `--help` exits 0, and it has a dispatch-test entry in `test_cli_loop_dispatch.py` and a `--help` smoke test in `test_ll_loop_execution.py`. Docs landing sites: `docs/reference/CLI.md` (`#### \`ll-loop export\``), `docs/reference/API.md` module section, `docs/guides/LOOPS_GUIDE.md`; a README template file, if shipped as a file, must be listed in `package_data.PACKAGE_DATA_ASSETS` (`test_package_data_manifest.py`).
- Tier gate and README adapter list are wired only after FEAT-3716 lands; until then they are unreachable, which is why that blocker is a hard edge.
- Verification: `python -m pytest scripts/tests/test_loop_export.py scripts/tests/test_fsm_schema.py scripts/tests/test_cli_loop_dispatch.py -v`, then the full `python -m pytest scripts/tests/`.

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Correction to the prior pass**: `requires` is **not** present in `FSMLoop`, `from_dict`, `to_dict` or `KNOWN_TOP_LEVEL_KEYS` today (it only triggers the `Unknown top-level keys` WARNING). The earlier bullet describing it as parsing/round-tripping states the *target* behavior, not current code.
- Masked-closure proof must cover subdirectory loops: a fixture loop in a subdirectory whose `import:` names `lib/…` is the case that distinguishes a correct bundle layout from a flat copy.
- Exit-code convention for `cmd_export`: `0` success, `1` bad input/IO/refusal, `2` a distinct "needs attention" outcome (as `cmd_templatize`, `cmd_evidence`, `cmd_edit_routes` document in their docstrings); the tier refusal is a candidate for `2`.
- If a new `LL_*` toggle is used for the mask, add it to the autouse scrub tuple `_CMD_RUN_ENV_VARS` in `scripts/tests/conftest.py` so teardown restores it; `fsm/` reads no `LL_*` var today.
- Fake-host e2e: suites disagree on a missing `ll-fake-host` (`conftest.py` and `test_fake_host.py` fail; `test_enh3538_token_observations.py` skips; `conformance/test_host_composition.py` uses `skipif`). The issue's "skip gracefully" gate matches the skip precedent, not the fail-hard one.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `fsm/schema.py` + `fsm/validation/_base.py` + `fsm/fragments.py` + `fsm/validation/__init__.py` — `requires` field, `KNOWN_TOP_LEVEL_KEYS` entry (and its re-export docstring/`__all__`), `collect_imports()`
- Update `fsm/validation/structural_rules.py:load_and_validate` — `requires:` ERROR; note `fsm/topology.py:load_fsm` bypasses it (accept the key in `from_dict`; no check needed there)
- Update the mask's reach — implement it so it covers `fragments._BUILTIN_LOOPS_DIR`, `loop_paths.resolve_loop_path`, and the by-name `get_builtin_loops_dir` imports in `fsm/validation/reachability.py`, `cli/loop/info.py`, `cli/loop/config_cmds.py` (patching `loop_paths` alone does not reach them); keep `little_loops.cli.loop.info.get_builtin_loops_dir` and `...config_cmds.get_builtin_loops_dir` patchable for existing tests
- Update `cli/loop/__init__.py:main_loop` — add `"export"` to `known_subcommands`, parser, dispatch `elif`, lazy import (the `install` parser/dispatch at :687/:1167 is the model; flag name `--output`/`--out` convention rather than `-o` alone)
- Update `package_data.PACKAGE_DATA_ASSETS` if the README template ships as a file
- Update `tests/test_cli_loop_dispatch.py`, `tests/test_ll_loop_execution.py`, `tests/test_fsm_schema.py`, `tests/test_fsm_fragments.py`, `tests/test_fsm_loop_paths.py`, `tests/test_fsm_validation_reachability.py` — per the Tests subsection above
- Guard `tests/test_cli_loop_next.py::TestCmdInstall` — if `cmd_install` shares the closure walk, keep its `get_builtin_loops_dir` read in `config_cmds` or update the patches
- Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/ARCHITECTURE.md`, `skills/create-loop/reference.md` — then `ll-adapt --host <gemini|kimi-code|qwen> --apply`, and `command cp -f README.md scripts/README.md` if README.md changes

## Program Design

### Types
- `FSMLoop.requires: dict[str, str]` — new optional top-level field (default `{}`, omitted from `to_dict()` at default), mapping distribution name → PEP 440 specifier; only `little-loops` is meaningful. Parsed in `FSMLoop.from_dict` (`fsm/schema.py`).
- `KNOWN_TOP_LEVEL_KEYS: frozenset[str]` (`fsm/validation/_base.py`) — gains `"requires"`; otherwise `load_and_validate` emits an `Unknown top-level keys` WARNING.
- `ExportClosure` (new dataclass, `cli/loop/export.py`) — `loops: dict[str, Path]` (name → source file), `fragments: dict[str, Path]` (import path as written → source file), `parents: dict[str, Path]` (`from:` targets).

### Signatures
- `collect_imports(raw_loop_dict: dict[str, Any], loop_dir: Path) -> list[Path]` — new, `fsm/fragments.py`; sibling of existing `resolve_fragments(raw_loop_dict: dict[str, Any], loop_dir: Path) -> dict[str, Any]` and `resolve_inheritance(raw_loop_dict, loop_dir, _seen=())`.
- `cmd_export(args: argparse.Namespace, loops_dir: Path) -> int` — new, `cli/loop/export.py`; exit codes documented in its docstring.
- `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints=None) -> tuple[FSMLoop, list[ValidationError]]` — existing (`fsm/validation/structural_rules.py`); the load-time `requires:` ERROR is emitted from here so `cmd_run`'s `raise_on_error=True` load fails before any executor exists.
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path` and `get_builtin_loops_dir() -> Path` — existing (`fsm/loop_paths.py`); the built-in-fallback mask must be honoured by both these and `fragments._BUILTIN_LOOPS_DIR`.
- `registered_host_names() -> list[str]` — existing (`host_runner.py`); excludes `TEST_ONLY_HOSTS` only, so it still returns the `opencode` and `pi` stubs.

### Call Path
`main_loop` (`cli/loop/__init__.py`) -> `cmd_export` -> `load_and_validate` (root, unmasked, to read the raw spec) -> `collect_imports` / static `state.loop` + `from:` walk -> copy to `<out>/.loops/` -> `load_and_validate` on the bundle with the fallback masked -> README render

Runtime consumer of the pin: `cmd_run` (`cli/loop/run.py`) -> `load_and_validate` -> `ValueError("FSM validation failed: ...")` -> `logger.error`, return 1.

### Decision Rules
- **Dynamic sub-loop names**: a state's `loop` value containing the substring `${` is dynamic (same test as `_validate_loop_references` in `fsm/validation/reachability.py` and `topology._is_dynamic`). Export refuses unless every such name is covered by `--include <name>`; the error lists the candidates.
- **Version pin**: export writes `requires: {little-loops: ">=<major>.<minor>,<<major+1>.0"}` derived from `little_loops.__version__`; load check compares `importlib.metadata.version("little-loops")` against the specifier. A loop without the field is not checked. Mismatch is an ERROR (not WARNING) because the pin must fail before the first state.
- **Tier gate**: tiers `requires-plugin` / `requires-issues` refuse export unless `--allow-tier <tier>` names that tier; `adapter: true` states never refuse, they are listed in the README. Escape hatch is `--allow-tier` only. Depends on FEAT-3716 (no classifier exists in code yet).
- **Overwrite**: export refuses a pre-existing `<out>` unless `--force`; it never writes into an existing `.loops/` tree.

## Impact

- **Priority**: P3, deliberately behind the brainstorm chain. Blocked by FEAT-3582 (pilot loop and its tournament child must exist) and by FEAT-3716 (portability classifier). Do not inject into the EPIC-3581 merge gate.
- **Effort**: Medium.
- **Risk**: Low–medium. New command plus two additive schema fields. The load-time `requires:` check is the only behavior change, and it applies only to loops that declare the field.
- **Breaking Change**: No.

## Use Case

A consultant wants to run the brainstorm loop inside a client's repository during an engagement. The client will not install the Claude plugin or adopt `.issues/`. The consultant runs `ll-loop export brainstorm -o ./bundle`, copies `bundle/.loops/` into the client repo, and runs `pip install 'little-loops>=X.Y'` then `ll-loop run brainstorm "brief" --context sink=file`. The run uses exactly the fragments and child loops that were exported, fails fast if the installed wheel is too old, and leaves a `.ll/history.db` record behind.

## Acceptance Criteria

- [ ] `ll-loop export <loop> -o <dir>` writes the layout above. The closure includes transitive fragments and sub-loops (fixture loop → child loop → fragment).
- [ ] The exported bundle validates with the built-in library masked (closure check).
- [ ] `requires:` in the schema, enforced at load. A mismatched version fails before the first state.
- [ ] `requires-plugin` / `requires-issues` loops are refused without `--allow-tier`. Adapter states are listed in the README.
- [ ] README lists only wired hosts (generated from `_HOST_RUNNER_REGISTRY` minus stubs/test-only, not hand-written).
- [ ] CI smoke test: fresh venv (and `uvx` if available on the runner), bare `git init` dir, no `ll-init`, run an exported `portable` loop end to end against the fake host. Only after this passes may the README template print a `uvx` command.
- [ ] Brainstorm (post-FEAT-3582) exports as `portable (adapters: requires-plugin)` and runs from a bare repo with `sink: file`.

## Edge Cases

- Interpolated sub-loop names → refuse with the list of candidates, or require `--include`.
- Name collision: a recipient already has `.loops/brainstorm.yaml` → bundle README tells them to copy into a subdir and run by path. Export never overwrites in place.
- Fragments that themselves `import:` other fragments → transitive closure. Cycle guard.
- JSON data dirs a loop reads (e.g. `brainstorm-profiles/`, FEAT-3667) → must be included in the closure via an explicit `assets:`/data-path declaration, or they come from the wheel and are covered by the pin. Decide which in refinement; the brainstorm profiles force the decision.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Data-dir decision is narrowed by what exists.** Fragment libraries are the only non-loop files the loader resolves relative to `loop_dir`. FEAT-3667 as written places the brainstorm profiles under `scripts/little_loops/loops/brainstorm-profiles/` and reaches them through the engine module, which puts them inside the wheel and under the version pin. An `assets:`/data-path declaration would be a new schema field with a new loader; nothing today needs it.
- **`from:` parents** must be copied alongside sub-loops and fragments, and their `import:` paths resolve against the child's directory — the bundle layout must keep those relative paths valid after copy.
- **Collision logic precedent**: `cmd_install` suffixes (`-2`, `-3`, …) against both `loops_dir` and the built-in dir; the issue's rule is the opposite (refuse, never overwrite, README advises a subdir). Pre-existing `<out>` handling elsewhere refuses without `--force` (`cli/artifact/templatize.py`).

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- README rendering: no generated-README precedent exists under `ll-loop`. Both conventions exist elsewhere — line-list string assembly (`init/writers.py:_render_commands_block`) and a packaged Jinja2 template (`cli/artifact/dashboard.py` via `artifact_templates.py`; `jinja2>=3.1` is declared). A packaged template file must be registered in `package_data.PACKAGE_DATA_ASSETS` (one entry per file, no globs, with an issue-ID comment).
- Loops in `loops/oracles/` currently depend on the built-in fallback for `lib/…` imports; exporting one is the concrete case where a flat `.loops/` copy breaks the closure (see Integration Map).

## Out of Scope

- Compiling loops to another harness's format (Claude Code workflow JS, skills). FEAT-2354 § Portability & Lock-in Analysis holds that analysis; it is lossy for evaluator-gated states and stays parked until a named consumer asks.
- A single-file export with a vendored executor. It would drift from the main runtime and duplicate the pip path.

## Related Key Documentation

- FEAT-3716: portability classifier (tiers, `adapter:` marker)
- EPIC-3581 / FEAT-3582 / FEAT-3667 (pilot loop, engine module)
- FEAT-2354 § Portability & Lock-in Analysis
- Hub: `ll-product/docs/architecture/little-loops-on-the-stack/` §5 loop contract seam, §8 Q6

## Labels

`loops`, `cli`, `portability`, `distribution`

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-04T02:47:52 - `334d5872-a8ff-4d86-9e1f-5c1cd897a218.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-04T02:44:23 - `80601c5b-ccf3-4432-90f3-bdfce27b419c.jsonl`
- `/ll:wire-issue` - 2026-10-04T02:34:45 - `eb45c0ef-1b4d-4bd9-87ed-0bffc9a78c6e.jsonl`
- `/ll:refine-issue` - 2026-10-04T02:26:46 - `42cdd517-6a19-4408-982f-a99f1aebdc70.jsonl`
