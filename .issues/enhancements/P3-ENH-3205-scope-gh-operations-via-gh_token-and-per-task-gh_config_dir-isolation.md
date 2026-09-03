---
id: ENH-3205
type: ENH
title: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation
priority: P3
status: open
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3233
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: true
learning_tests_required:
- gh
---

# ENH-3205: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation

## Summary

gh operations bypass `host_runner` entirely. `sync.py`'s `_run_gh_command()`/`_check_gh_auth()` rely on the ambient `gh auth login` session, which is repo- or org-broad, with no per-task token minted or injected anywhere.

**Env projection alone does not de-scope gh.** Its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`, so removing that variable from the child leaves the broad session fully usable. Constraining gh requires injecting an explicit `GH_TOKEN` **and** redirecting `GH_CONFIG_DIR` to a per-task directory so the ambient login is not visible. Both, or neither.

This is the one place where ENH-3203's guarantee visibly does not reach, and gh is what FSM loops actually use to make changes to the outside world — so it is the highest-value gap and the one most likely to be misread as already covered.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no projection code has landed yet. "Gated on a declaration" requires a declaration surface: the FSM shell path (this issue's primary gh surface, per Current Behavior) is ENH-3235, hence `blocked_by: [ENH-3233, ENH-3235]`. If gh scoping should also cover the `ll-action`/`ll-queue`/`ll-harness` path, add ENH-3234 to `blocked_by` when deciding scope. Decide this in or out explicitly; leaving it ambiguous is how the largest hole ships open.

## Current Behavior

- `scripts/little_loops/sync.py` — `_run_gh_command()`/`_check_gh_auth()` shell out to gh directly, bypassing the host-runner layer entirely, and inherit whatever session the operator logged in with.
- FSM loops invoke gh through `DefaultActionRunner`'s `bash -c` branch (`fsm/runners.py:297`), so the shell-action path is the larger surface, not `sync.py`.
- Even under ENH-3203's projection, stripping `GITHUB_TOKEN` from a child changes nothing: gh falls back to the keyring / `~/.config/gh/hosts.yml`, which `HOME` still points at.

## Expected Behavior

A task declaring GitHub access receives an explicit `GH_TOKEN` and a `GH_CONFIG_DIR` pointing at a per-task directory containing no ambient login. A task not declaring it can neither read `GH_TOKEN` nor reach the operator's gh session.

If this is not implemented, ENH-3203 must state plainly that gh is unscoped rather than imply coverage it does not deliver.

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — `_run_gh_command()`, `_check_gh_auth()`.
- The projection helper in `scripts/little_loops/host_runner.py` — `GH_CONFIG_DIR` redirection is a projection concern, not a `sync.py` one, since the `bash -c` path is where most gh calls originate.

### Tests
- A test proving a scoped child's `gh auth status` does not see the ambient login.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **Chokepoint convention**: subprocess env construction has a single chokepoint, `project_child_env()` (`scripts/little_loops/host_runner.py:1865`). An AST-based static test, `test_enh3184_spawn_site_guard.py`, enforces every task-path `subprocess.*` call in a pinned per-module table routes through it (directly, via a variable assigned from it, or via an inline `# ll-no-project:` exemption comment). `scripts/little_loops/sync.py` is **not currently in that pinned table** — `_run_gh_command()`'s `subprocess.run(cmd, capture_output=True, text=True, check=check)` (`sync.py:98-124`) passes no `env=` at all, so this guard enforces nothing about `sync.py` today.
- **No deny primitive yet**: `project_child_env()` only supports additive overrides (`invocation.env`, `extra={...}`) — it has no primitive to deny/clear an inherited variable. ENH-3233 (a direct `blocked_by` of this issue) specifies an `env_allow: frozenset[str] | None` parameter to add that capability, but as of this pass it exists only as design text in ENH-3233 — no `env_allow` symbol exists anywhere under `scripts/` yet.
- **One-off keys via `extra=`**: one-off env keys are passed as `project_child_env(extra={...})` rather than mutated onto the returned dict afterward — e.g. `git_operations.py:728`, `worker_pool.py:859-861`, `fsm/runners.py:305`.
- **Both-or-neither pairing has no validator**: existing "set together, never one without the other" pairs (`GIT_DIR`/`GIT_WORK_TREE` in `host_runner.py:425-433` and its `CodexRunner`/`GeminiRunner` counterparts; `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` in `_apply_automation_env()`, `host_runner.py:1898-1915`) achieve pairing only by code-block co-location. No runtime or test-level assertion enforces the pairing in either case — searched repo-wide, no such helper exists to reuse.
- **Per-task directory lifecycle, two existing shapes**: (a) a `tempfile.TemporaryDirectory()` scoped to a `with` block and reused across multiple subprocess calls sharing one `env` dict (`git_operations.py::preserve_dirty_tree()`, lines 725-749); (b) a heavier explicit create → out-of-tree registry entry → in-tree pid marker → cleanup pairing (`worktree_utils.py::setup_worktree()`/`cleanup_worktree()`, lines 283-472, with `_write_registry_entry()`/`_remove_registry_entry()`). Neither is GH_CONFIG_DIR-specific.
- **Nearest allow-set shape precedent**: `MUTATING_TOOLS`, a bare module-level `frozenset[str]` consulted via `in` (`scripts/little_loops/mcp_server/policy.py:55-63`). ENH-3233's own research already names this as "shape precedent only" — no per-entry metadata, no fail-loud-on-unknown-name behavior.
- **Test convention for "child cannot see ambient credential"**: this codebase asserts it two ways — (a) spawn a subprocess whose own `python3 -c` one-liner inspects its own `os.environ` and communicates via exit code (`test_worktree_utils.py::test_ll_python_scrubbed_from_child_env`, lines 1359-1388, and the positive-case sibling `test_verify_gate_marker_set_in_child_env`, lines 1336-1357); (b) assert directly on `project_child_env()`'s returned dict with no subprocess spawned (`test_host_runner.py::TestProjectChildEnv`, lines 96-139, parametrized across every `HostRunner` subclass). No shared/reusable "assert credential not visible" fixture exists — every instance inlines its own check.
- **Searched, no hits**: `GH_TOKEN`/`GH_CONFIG_DIR` literals, `env_allow`, a both-or-neither validator, and token-minting code were all searched repo-wide across `scripts/` with no filter — none exist in shipped code.

## Program Design

### Types
- No new type is required. The `GH_TOKEN`/`GH_CONFIG_DIR` pair is two entries in the allow-set ENH-3203 already computes.

### Signatures
- `_run_gh_command(args: list[str], logger: Logger, check: bool = True) -> subprocess.CompletedProcess[str]` — the sync-layer entry point that must receive a projected environment instead of inheriting one (`sync.py:98`).
- `_check_gh_auth(logger: Logger) -> bool` — the auth probe, which must report against the projected session rather than the ambient one (`sync.py:127`).

### Call Path
`resolve_host` → projection helper → `_run_gh_command` / `_check_gh_auth`

The shell branch `DefaultActionRunner` (`fsm/runners.py:297`) reaches the same CLI by the same route, which is why the redirect belongs in the helper rather than in the sync layer.

### Decision Rules
- Both `GH_TOKEN` and `GH_CONFIG_DIR` are set, or neither is. Setting only the token leaves the ambient login reachable and produces the appearance of scoping without the fact of it.
- Undeclared specs are unaffected, consistent with ENH-3203's AC5.

## Scope Boundaries

Explicitly **out of scope**:

- **Token minting.** No GitHub App installation tokens. Without minting, this projects an equally broad token to fewer processes — see Open Decision #1.
- **The declaration mechanism** — ENH-3203.
- **Other keyring-backed credentials** (`~/.aws/credentials`, `~/.netrc`, the macOS keychain). gh is singled out because it is what loops actually use to change the outside world, not because it is the only one.
- **`HOME` redirection.** `GH_CONFIG_DIR` is a targeted redirect; relocating `HOME` wholesale is a much larger change with its own breakage surface.

## Open Decisions

1. **Where does `GH_TOKEN` come from?** The operator's ambient env is the only source without minting — which means the "scope" is a projection of an equally broad token, not a narrower one. If genuine narrowing is wanted, that is GitHub App installation tokens, i.e. token minting, explicitly out of scope for this family. Decide whether projection-only gh scoping is worth having.
2. **Per-task `GH_CONFIG_DIR` lifecycle** — created per run, per spawn, or per declared spec, and who cleans it up.

## Impact

- **Priority**: P3 — the highest-value remaining gap, but its value is bounded by Open Decision #1: without minting, this isolates *which* processes see a broad token rather than narrowing the token itself.
- **Effort**: Medium — two call sites plus config-dir lifecycle, but the keyring interaction is easy to get subtly wrong.
- **Risk**: Medium — a `GH_CONFIG_DIR` redirect that breaks the operator's interactive gh usage, or a scoped child that silently falls back to the ambient session and appears to work while proving nothing.
- **Breaking Change**: No, if gated on a declaration.

## Status

**Open** | Created: 2026-08-15 | Priority: P3

## Verification Notes (2026-09-03)

- `fsm/runners.py:266` citations corrected to `:297` (bash-c branch moved).

## Session Log
- `/ll:refine-issue` - 2026-09-03T19:37:52 - `e69aa141-6d57-4757-9f35-bf5dfd784b25.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
