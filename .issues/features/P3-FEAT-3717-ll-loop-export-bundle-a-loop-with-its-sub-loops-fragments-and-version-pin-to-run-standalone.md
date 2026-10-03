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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/export.py` (new): closure walk, copy, `requires:` injection, README render, masked-library self-validate
- `scripts/little_loops/cli/loop/__init__.py`: `export` subparser
- `scripts/little_loops/cli/loop/config_cmds.py:106-184` `cmd_install`: share the closure walk (`--with-deps`) or call into export; one implementation
- `scripts/little_loops/fsm/fragments.py`: expose `collect_imports()` (transitive import paths) and a flag/env to disable the `_BUILTIN_LOOPS_DIR` fallback (fragments.py:31, :99-110)
- `scripts/little_loops/fsm/loop_paths.py`: same built-in-fallback mask for `resolve_loop_path`
- `scripts/little_loops/fsm/fsm-loop-schema.json`: top-level `requires`
- `scripts/little_loops/fsm/validation/structural_rules.py`: `requires:` version check at load

### Dependent Files (Callers/Importers)
- FEAT-3716 `classify_portability()` (tier gate, adapter list)
- `host_runner.py:2560-2571` `_HOST_RUNNER_REGISTRY` + `TEST_ONLY_HOSTS` (README host list; exclude stub runners)

### Similar Patterns
- `cli/loop/evidence.py` (FEAT-3182): existing bundle-writing command for run evidence
- `cli/loop/config_cmds.py` `cmd_install`: name/path resolution and collision handling

### Tests
- New `scripts/tests/test_loop_export.py`: closure (loop → child → fragment → nested fragment), masked-library validate, `requires:` mismatch, tier refusal, dynamic sub-loop refusal, collision
- CI smoke: fresh venv (+ `uvx` when present), bare `git init`, fake host, exported portable loop end to end

### Documentation
- `docs/guides/LOOPS_GUIDE.md`: sharing loops section
- `README.md`: standalone/`uvx` usage only after the smoke test passes

### Configuration
- N/A

## Implementation Steps

1. `collect_imports()` + built-in-fallback mask; prove a closure validates masked.
2. `requires:` schema + load check.
3. `export` command + README template + tier gate (after FEAT-3716).
4. Smoke test; export brainstorm post-FEAT-3582 as the acceptance run.

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
