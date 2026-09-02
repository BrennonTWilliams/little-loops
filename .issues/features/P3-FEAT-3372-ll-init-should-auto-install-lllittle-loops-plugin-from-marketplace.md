---
id: FEAT-3372
type: FEAT
title: ll-init should auto-install ll@little-loops plugin from marketplace
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T03:55:51Z'
completed_at: '2026-09-02T03:32:24Z'
unproven_mechanism: false
verify_verdict: VALID
size: Medium
learning_tests_required:
- 'claude CLI plugin subsystem: headless `claude plugin marketplace add <source>'
- "`claude plugin install ll@little-loops -y` \u2014 non-interactive install flow\
  \ for FEAT-3372"
confidence_score: 100
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 20
---

# FEAT-3372: ll-init should auto-install ll@little-loops plugin from marketplace

## Summary

`ll-init` never installs the `ll@little-loops` Claude Code plugin from the marketplace on behalf of the user. It detects whether the plugin is already present and reports staleness, but when it's absent it leaves the user to run `claude plugin marketplace add` / `claude plugin install` manually — even when the user selected `claude-code` as a host during the wizard.

## Current Behavior

`detect_installation()` (`scripts/little_loops/init/install_check.py:60`) shells out to `[binary, "plugin", "list", "--json"]` to check whether `ll@little-loops` is installed, returning `(None, None, None)` when it isn't found — this is read-only detection, not installation.

`_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:94`) is what actually acts on the selected hosts list during `ll-init`. For every other host (`codex`, `kimi-code`, `qwen`) it writes adapter files. For `claude-code` there is no branch that does anything — the loop falls through to a bare comment: `# claude-code: no adapter file needed; plugin hooks fire when globally enabled` (`scripts/little_loops/init/cli.py:169`). Nothing in that path calls `claude plugin marketplace add` or `claude plugin install`, so a user who selects `claude-code` in the wizard (or gets it via auto-detection in `_detect_hosts()`, `scripts/little_loops/init/cli.py:73`) but hasn't already installed the plugin ends `ll-init` with `/ll:*` commands, skills, agents, and hooks still unavailable.

## Expected Behavior

When `claude-code` is among the selected/detected hosts and the `ll@little-loops` plugin is not present in `claude plugin list`, `ll-init` should install it from the marketplace automatically — unless the user explicitly deselected `claude-code` in the TUI's host checklist (`scripts/little_loops/init/tui.py:519`) or via `--hosts` on the headless path.

This applies on the `--upgrade` path too: `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:223`) delegates to `_dispatch_host_adapters(hosts, project_root, plugin_root, force=True)`, so `ll-init --upgrade` with the plugin absent installs it (deliberate — matches the existing docs table wording "pass `--upgrade` to install automatically", `docs/guides/GETTING_STARTED.md:126`). The `plugin update` step in `_dispatch_host_upgrade()` remains separate and is not duplicated.

> **Design correction (2026-09-01 review):** the gate must be a direct **plugin-presence probe**, NOT `detect_installation()`'s `install_source is None`. `ll-init` is a pip entry point (`scripts/pyproject.toml:127`), so `importlib.metadata.version("little-loops")` always succeeds in the environment running it, and `detect_installation()` (`install_check.py:74-78`) checks pip metadata *first* and returns `"pypi"`/`"local-editable"` without ever reaching the plugin-list check. Gating on `install_source is None` would make the branch dead code for exactly the Use Case user (pip-installed, plugin absent). Pip-package presence and Claude Code plugin presence are independent facts.

## Motivation

Today, running `ll-init` with Claude Code as the target host doesn't actually get you working `/ll:*` commands unless you separately know to run the marketplace/install commands yourself. That's a broken first-run experience for exactly the host `ll-init`'s wizard treats as the default checked option (`tui.py:140`, `tui.py:288`).

## Proposed Solution

Add a `claude-code` branch inside `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:169`) parallel to the existing `codex`/`kimi-code`/`qwen` branches:

1. Factor the `claude plugin list --json` probe out of `detect_installation()` (`install_check.py:88-112`) into a reusable helper, e.g. `plugin_installed(binary: str) -> bool` in `install_check.py` (`detect_installation()` keeps its behavior by calling it). This is required because pip metadata shadows the plugin check inside `detect_installation()` — see Expected Behavior's design correction.
2. In the new branch: resolve the `claude` binary the same way `fetch_latest_plugin()` already does (`resolve_host().build_version_check().binary` / the pattern in `install_check.py:83`); if the binary is present and `plugin_installed(binary)` is False, run the marketplace-add + install subprocess sequence, reporting success/failure via `info()`/`warning()`.

### Decisions (resolved 2026-09-01 review)

- **Marketplace source**: prefer the local path when `plugin_root / ".claude-plugin" / "plugin.json"` exists (true for editable/dev checkouts, where `_plugin_root()` resolves to the repo root); otherwise fall back to the GitHub source `BrennonTWilliams/little-loops` (matching `docs/guides/GETTING_STARTED.md:40`). Rationale: for a site-packages install, `_plugin_root()`'s `__file__`-relative fallback lands in `lib/python3.x/` — not a plugin root — so the local-path source only works for dev checkouts.
- **Install scope**: `-s user` (the `claude plugin install` default, matching the manual instructions in `GETTING_STARTED.md`). Do not pass `-s project` — that would silently change how later runs classify `install_source` (`project-claude-code`) and unlock `_dispatch_host_upgrade`'s auto-update path.
- **`local-editable` dev checkouts**: the branch fires for them too — the gate is purely plugin absence, regardless of pip state. (Every consuming project on this machine is `local-editable`; if the plugin is already installed globally the probe skips, so this only acts when `/ll:*` genuinely wouldn't work.)
- **`marketplace add` failure handling**: best-effort — don't gate the `plugin install` call on marketplace-add's returncode (it fails benignly when the marketplace is already added). Mirrors `fetch_latest_plugin()`'s precedent (`install_check.py:141-184`), which never checks its `marketplace update` step's returncode.
- **Subprocess style for the two calls (2026-09-01 review)**: stdout/stderr **not captured** (the user should see `claude`'s install progress, as with `_dispatch_host_upgrade`'s `plugin update` call), but **with `timeout=120`** wrapped in `try/except (subprocess.TimeoutExpired, FileNotFoundError, OSError)`. A GitHub-sourced `plugin install` performs a network clone, so a hang is realistic; Pattern 1's bare `check=False` (no timeout) cannot satisfy the "times out → warning" acceptance criterion. Read `plugin install`'s returncode to split `info()` (0) from `warning()` (non-zero / exception). This is a hybrid of the two existing styles, chosen deliberately — see Program Design → Codebase Research Findings for the pattern survey.
- **Host resolution caveat**: `resolve_host()` honors `LL_HOST_CLI` / `orchestration.host_cli`, so in a codex-configured project this branch would probe the codex binary. `detect_installation()` (`install_check.py:79-81`) has the identical limitation and documents it as "only meaningful when the active host is claude-code"; carry the same comment into the new branch rather than special-casing.
- **Mechanism proven**: the headless `marketplace add` + `plugin install -y` sequence is proven by the two Learning Test Registry entries listed in `learning_tests_required` (both `status: proven`, see Codebase Research Findings dated 2026-09-02). `unproven_mechanism` is therefore `false` — no spike required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- No existing code path in this repository ever runs `claude plugin marketplace add` followed by `claude plugin install` — the combination this issue's remedy depends on. Every other `claude plugin`/`claude plugin marketplace` subprocess call in the codebase (`plugin update`, `plugin list`, `plugin marketplace update`) is a read-only or already-configured-target operation; none add a new marketplace source or perform a first-time install headlessly.
   ⚠ Unproven mechanism — no headless add+install precedent in repo

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- Two Learning Test Registry entries, both dated 2026-09-01 and `status: proven`, directly test the mechanism the marker above flags as unproven:
  - `.ll/learning-tests/claude-cli-plugin-subsystem-headless-claude-plugin-marketplace-add-source.md` proves `claude plugin marketplace add <source>` succeeds non-interactively for a local path, is idempotent on re-add, errors cleanly (exit 1) on a nonexistent path, accepts a bare `owner/repo` GitHub shorthand, and honors `--scope project`. Critically, its final assertion — "after marketplace add, `plugin install <name>@<marketplace>` also runs non-interactively" — passed, with raw evidence showing `claude plugin install ll@little-loops` exiting 0 immediately after the marketplace add (`.ll/learning-tests/raw/claude-cli-plugin-subsystem-headless-claude-plugin-marketplace-add-source.txt:47-49`). This is a direct headless add-then-install precedent, run in this exact repo.
  - `.ll/learning-tests/claude-plugin-install-lllittle-loops-y-non-interactive-install-flow-for-feat-3372.md` (named for this issue) proves `claude plugin install ll@little-loops -y` exits 0 reporting "already installed" on a repeat install, that `-s project` writes the declaration to a project-scoped settings file under that directory's `.claude/` (not user config), and that default scope is `user`. One assertion — "without `-y`, in a non-TTY context, install exits non-zero" — is recorded as **fail**: the observed run exited 0 without `-y` (raw: lines 14-17) — but that run targeted an already-installed plugin, so whether `-y` is load-bearing for a *fresh* install in a non-TTY context remains untested by this evidence; the Program Design section's basis for requiring `-y` (the `--help` text) stands unmodified.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_dispatch_host_adapters()` claude-code branch
- `scripts/little_loops/init/install_check.py` — extract `plugin_installed(binary) -> bool` from `detect_installation()` (the gate; see Expected Behavior's design correction)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/tui.py` (calls `_dispatch_host_adapters` at line 902) and `scripts/little_loops/init/cli.py` (headless paths at lines 223, 672, 879)

### Similar Patterns
- `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:172`) already has claude-code-specific, scope-aware subprocess logic to model the install branch after
- `detect_installation()` / `fetch_latest_plugin()` (`scripts/little_loops/init/install_check.py`) for the `resolve_host()` + subprocess pattern

### Tests
- TBD — needs a test covering: host selected + not installed → install invoked; host deselected → not invoked; host selected + already installed → not invoked

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py` — ~14 existing tests mock `little_loops.init.install_check.detect_installation` to return `(None, None, None)` and run `main_init` without `--dry-run`, without mocking `little_loops.init.cli._subprocess.run`: `test_yes_creates_config` (:1780), `test_yes_merges_existing_config` (:1797), `test_yes_preserves_unmodeled_keys` (:1826), `test_yes_force_drops_unmodeled_keys` (:1868), `test_yes_enable_feature_flags_write_sections` (:1982), `test_yes_enable_prompt_optimization_writes_enabled` (:2009), `test_yes_deploys_design_tokens_when_enabled` (:2342), `test_yes_deploys_issue_templates_when_enabled` (:2366), `test_yes_adds_explore_api_permission_when_learning_tests` (:2391), `test_no_git_repo_prints_notice` (:2686), `test_git_repo_prints_no_notice` (:2705), `test_git_worktree_file_counts_as_repo` (:2726), `test_bare_upgrade_implies_yes_never_launches_wizard` (:2473, reaches the new branch via `_dispatch_host_upgrade` → `_dispatch_host_adapters(force=True)`), and the "live" second `main_init` call in `test_dry_run_output_matches_yes_writes` (:2679) — once the claude-code branch lands these will attempt real, unmocked `claude plugin marketplace add`/`claude plugin install` subprocess calls and need `_subprocess.run`/`resolve_host` mocks (or a non-`None` `detect_installation` stub) to stay hermetic [Agent 3 finding]
- `scripts/tests/test_init_audit_fixes.py:484` (`test_apply_honors_requested_upgrade`) and `:501` (`test_apply_ignores_requested_upgrade_in_dry_run`) — drive `--hosts claude-code` through `_run_apply`, mocking only `_dispatch_host_upgrade`, not `detect_installation`/`_subprocess.run`; the direct `_dispatch_host_adapters` call at `cli.py:879` is unmocked and would hit the new branch [Agent 1 finding]
- `scripts/tests/test_init_core.py:2960` (`test_hosts_claude_code_no_adapter_file`) and `:3008` (`test_hosts_claude_code_no_agents_md`) — currently pass only because this dev environment's ambient `local-editable` install source is non-`None` (no explicit `detect_installation` mock); add one so pass/fail doesn't depend on incidental repo state [Agent 3 finding]
- `scripts/tests/test_init_core.py:2526` (`test_project_scoped_plugin_install_source_written_to_config`, BUG-2266 regression) — drives `main_init(["--yes", ...])` through the same `detect_installation()` call path the new branch sits next to; useful precedent for asserting `install_source` handling doesn't regress [Agent 1 finding]
- `scripts/tests/test_init_core.py:3117` (`TestDispatchHostUpgrade::test_project_scoped_runs_plugin_update`) — exact mock template to follow for the new test: `_subprocess.run` patched at `little_loops.init.cli._subprocess.run` with a `record(cmd, **kwargs)` closure appending argv, `resolve_host` patched at `little_loops.host_runner.resolve_host` (its defining module) returning a `MagicMock` with `.build_version_check.return_value.binary` set [Agent 3 finding]
- New test needed (no existing precedent for headless `marketplace add` + `install` together): `plugin_installed(binary)` mocked False + `host == "claude-code"` → assert `marketplace add`/`plugin install ll@little-loops -y` subprocess argv; companion case with `plugin_installed` mocked True asserting `_subprocess.run` not called; `dry_run=True` case asserting no subprocess call; `--upgrade` case (via `_dispatch_host_upgrade`) with plugin absent asserting the install argv is issued alongside (not instead of) the existing update behavior [Agent 3 finding; gate corrected 2026-09-01 review — was `install_source is None`, which the design correction rejects]

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — "Existing Installation Detection" table (~line 122-128) describes the not-installed case as "warns only by default — pass `--upgrade` to install automatically"; needs updating since claude-code will now auto-install without `--upgrade` [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md` — "Step 2: Install the Plugin" (lines 34-51), manual `/plugin marketplace add` + `/plugin install` instructions; note that `ll-init --hosts claude-code` can now do this automatically [Agent 2 finding]
- `README.md` (lines 70-75) and `scripts/README.md` (lines 70-75) — same manual plugin-install block, duplicated in both files [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-init` section (lines 35-96): `--hosts` flag description and the Screen 1/7 "Plugin Install" TUI-screen description don't mention the new headless auto-install side effect [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — "Host tiers" table + note (lines 22-49) describes claude-code's `_dispatch_host_adapters` behavior as a pure no-op ("no adapter file to write"); needs updating once it performs a marketplace-install side effect [Agent 2 finding]
- `skills/update/SKILL.md:106` — prints `claude plugin install ll@little-loops` as a manual fallback message; cross-check wording consistency with the new automated path [Agent 1 finding]

### Follow-up (out of scope)

- The TUI "Plugin Install" screen (`scripts/little_loops/init/tui.py:184-262`) reports only pip-package absence/staleness and prompts "install/upgrade separately after"; it never reports plugin absence, so after this change the wizard silently auto-installs the plugin without the screen saying so. Capture as a separate ENH: have the screen say the plugin will be installed automatically when `claude-code` is selected and `plugin_installed(binary)` is False.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:94`) does NOT currently take an `install_source` parameter — only `_dispatch_host_upgrade()` does. `project_root` is already a parameter, so the new claude-code branch can call `detect_installation(project_root)` internally without a signature change.
- Existing writer branches (codex/kimi-code/qwen) follow a tri-state contract: their `install_*_adapter()` calls return `bool | None` — `None` → `warning()`, truthy + not dry_run → `info()`, falsy → silent. The claude-code branch has no equivalent call today (bare comment only, `cli.py:169`).
- `_KNOWN_HOSTS` (`cli.py:41-50`) already includes `"claude-code"` — no registration change needed for a new branch.
- Two entry points reach `_dispatch_host_adapters()`: `_run_yes()` (`cli.py:672`, mutually exclusive with `_dispatch_host_upgrade()` based on `upgrade and not dry_run`) and `_run_apply()` (`cli.py:879`, called unconditionally, with `_dispatch_host_upgrade()` separately conditional at `cli.py:890`). A new claude-code branch in `_dispatch_host_adapters()` is reached identically by both.
- Existing tests: `TestHostDispatch` (`scripts/tests/test_init_core.py:2950-3098`, drives through `main_init()` with `--hosts`, asserts filesystem/stdout side effects) and `TestDispatchHostUpgrade` (`scripts/tests/test_init_core.py:3106+`, calls `_dispatch_host_upgrade()` directly). No existing test exercises a positive/install action for `claude-code` in `_dispatch_host_adapters` — only negative-outcome tests (`test_hosts_claude_code_no_adapter_file`, `test_hosts_claude_code_no_agents_md`).
- Mocking pattern used by `TestDispatchHostUpgrade` (reusable for the new branch's tests): patch `"little_loops.init.cli._subprocess.run"` with a `side_effect` recorder closure appending argv lists, and patch `"little_loops.host_runner.resolve_host"` (the *defining* module, not `little_loops.init.cli.resolve_host` — the import is local inside the function body) returning a `MagicMock` whose `.build_version_check.return_value.binary` is set.

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- Confirmed (analyzer): `_apply_config()` in `tui.py` calls `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)` at `tui.py:902` with no `dry_run` kwarg — it inherits the function's own default of `False`. The TUI path has no `--dry-run` concept at all, so this branch always executes for real when reached from the TUI, unlike the headless `_run_yes`/`_run_apply` paths which explicitly thread `dry_run`.
- Convention (pattern-finder): resolving the CLI binary via `resolve_host()` rather than a hardcoded `"claude"` string is enforced by an existing test, `test_uses_resolve_host_not_hardcoded_claude` (`scripts/tests/test_init_install.py:336`) — the new claude-code branch's binary resolution should follow the same no-hardcoding rule this test polices.

## Program Design

### Types

No new types.

### Signatures

- `plugin_installed(binary: str) -> bool` — NEW helper in `scripts/little_loops/init/install_check.py`: the `claude plugin list --json` probe factored out of `detect_installation()` (`install_check.py:88-112`), returning True iff `ll@little-loops` appears; `detect_installation()` refactored to call it (behavior unchanged)
- `_dispatch_host_adapters(hosts: list[str], project_root: Path, plugin_root: Path, force: bool = False, dry_run: bool = False) -> None` — add a `claude-code` branch alongside the existing `codex`/`kimi-code`/`qwen` branches (`scripts/little_loops/init/cli.py:169`)

Do NOT gate on `detect_installation()`'s `install_source` — pip metadata shadows the plugin probe (see Expected Behavior's design correction).

### Call Path

`_dispatch_host_adapters()` -> `resolve_host().build_version_check().binary` -> (binary present and not `plugin_installed(binary)` and not `dry_run`) -> `subprocess.run([binary, "plugin", "marketplace", "add", <source>], check=False, timeout=120)` (best-effort, returncode ignored) -> `subprocess.run([binary, "plugin", "install", "ll@little-loops", "-y"], check=False, timeout=120)`, both inside `try/except (TimeoutExpired, FileNotFoundError, OSError)`, reporting via `info()` on returncode 0 / `warning()` on non-zero or exception — `<source>` per the Decisions block (local `plugin_root` when it contains `.claude-plugin/plugin.json`, else `BrennonTWilliams/little-loops`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Two divergent subprocess-invocation styles exist for `resolve_host().build_version_check().binary` calls. Pattern 1 (`_dispatch_host_upgrade`, `cli.py:197-218`) — bare `_subprocess.run([...], check=False)`, no `capture_output`, no `timeout`. Pattern 2 (`install_check.py` `detect_installation()`/`fetch_latest_plugin()`) uses `capture_output=True, text=True, timeout=<N>` wrapped in `try/except (subprocess.TimeoutExpired, FileNotFoundError, OSError)`. There is no shared helper — each site inlines its own call. **Selected (superseding the earlier Pattern 1 choice, 2026-09-01 review): hybrid** — Pattern 1's uncaptured output plus Pattern 2's `timeout` + exception wrapping, per the Decisions block's "Subprocess style" entry. Rationale: the AC requires a timeout to surface as a warning, which Pattern 1 cannot deliver.
- Confirmed via `claude plugin install --help` (local CLI, this machine): `claude plugin install <plugin>` accepts `-y`/`--yes` — "required when stdin or stdout is not a TTY" — and `-s`/`--scope <user|project|local>` (default `user`). `ll-init` in `--yes`/headless mode has no TTY, so `-y` is load-bearing, not optional, for this call to complete non-interactively.
- Confirmed via `claude plugin marketplace add --help`: takes a `<source>` (URL, path, or GitHub repo) and `--scope <user|project|local>` (default `user`). `_plugin_root()` (`cli.py:59`, env-var-first: `CLAUDE_PLUGIN_ROOT` then `__file__`-relative) is already computed by every caller of `_dispatch_host_adapters()` and passed through as the `plugin_root` parameter — this is a ready-made local-path `<source>` value matching the docs' local-install pattern (`docs/guides/GETTING_STARTED.md:49`, `/plugin marketplace add /path/to/little-loops`).
- No existing subprocess call anywhere in this codebase exercises `plugin marketplace add` or `plugin install` — the only precedented `claude plugin`/`claude plugin marketplace` subcommands actually invoked via subprocess are `plugin update` (`_dispatch_host_upgrade`), `plugin list --json`/`plugin list --available --json` (`detect_installation`, `fetch_latest_plugin`), and `plugin marketplace update` (`fetch_latest_plugin`). `marketplace add`+`install` together, non-interactively, is untested territory for this codebase even though both subcommands exist per `--help`.

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- `dry_run` contract (analyzer): every existing branch in `_dispatch_host_adapters()` that performs a write/subprocess side effect conditions it on `dry_run` — codex/kimi-code/qwen thread `dry_run=dry_run` into their writer (`writers.py:708-710`: `if dry_run: info(...); return True`) and the caller additionally gates its own follow-up `info()` on `elif installed and not dry_run:` (`cli.py:122`). The new claude-code branch has no writer to delegate to, so this contract is not automatically inherited — the marketplace-add/install subprocess calls need their own explicit `if dry_run:` short-circuit to stay consistent with every sibling branch. Neither the issue's Implementation Steps nor Acceptance Criteria currently state this.
- Subprocess-invocation style is a three-way, not two-way, contested convention: (1) `install_check.py`'s `capture_output=True, text=True, timeout=N` wrapped in `try/except (TimeoutExpired, FileNotFoundError, OSError)` (already documented); (2) `_dispatch_host_upgrade`'s bare `check=False`, no returncode read, comment-justified as "a missing/unauthenticated host must never abort init" (`cli.py:206-213`, already documented); (3) newly found — `_run_yes()`'s pip-install calls (`cli.py:478-485`, `:521-534`, `:541-554`) use `check=True` + `except _subprocess.CalledProcessError as exc: print(f"Warning: auto-install failed: {exc}", file=sys.stderr)`. All three styles coexist in this codebase with no stated precedent for which a marketplace-add+install sequence should follow.
- `fetch_latest_plugin()`'s existing "marketplace update, then plugin list" sequence (`install_check.py:141-184`, already cited in Call Path) never checks step 1's returncode at all — only step 2's. This is the closest existing precedent for a two-step `marketplace X` → `plugin Y` sequence, and it treats the first call as pure best-effort.
- `warning()`/`info()` (`scripts/little_loops/cli/output.py:264-291`) both print to **stdout** (not stderr); only `error()` uses stderr. Tests asserting on the new branch's warning/info output should use stdout-capturing `capsys`, not stderr.

## Implementation Steps

1. Factor the `claude plugin list --json` probe out of `detect_installation()` into `plugin_installed(binary: str) -> bool` in `scripts/little_loops/init/install_check.py`; refactor `detect_installation()` to use it (behavior unchanged — existing `detect_installation` tests must stay green)
2. Add a `claude-code` branch to `_dispatch_host_adapters()` (`scripts/little_loops/init/cli.py:169`): resolve the host binary via `resolve_host().build_version_check().binary`; short-circuit (no-op) when the binary is missing, `dry_run` is set, or `plugin_installed(binary)` is True
3. Otherwise run `claude plugin marketplace add <source>` (best-effort, returncode ignored; `<source>` = `plugin_root` if it contains `.claude-plugin/plugin.json`, else `BrennonTWilliams/little-loops`) then `claude plugin install ll@little-loops -y` (default user scope). Both calls: output uncaptured, `check=False`, `timeout=120`, wrapped in `try/except (TimeoutExpired, FileNotFoundError, OSError)`. Report through `info()` on install returncode 0 and `warning()` on non-zero returncode, timeout, or OS error. Add a comment noting the `resolve_host()` host-override caveat (same as `detect_installation()`).
4. Add tests covering: host selected + plugin absent → install invoked **even when pip metadata reports `pypi`/`local-editable`** (the shadowing case); host deselected/omitted from `--hosts` → not invoked; host selected + plugin present → not invoked; `dry_run=True` → not invoked; install subprocess non-zero returncode → `warning()`; `TimeoutExpired` raised by the mocked `_subprocess.run` → `warning()`, not an exception; source selection (local path vs GitHub fallback); `--upgrade` path with plugin absent → install invoked via `_dispatch_host_upgrade`'s delegation

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update the ~14 tests in `test_init_core.py` and the 2 tests in `test_init_audit_fixes.py` listed under Integration Map → Tests to mock the new `plugin_installed` gate (and/or `_subprocess.run`/`resolve_host`) so they stay hermetic once the claude-code branch fires real subprocess calls — note their existing `detect_installation` mocks no longer shield them, since the gate is now the plugin probe, not `install_source`
- Add an explicit `plugin_installed` mock to `test_hosts_claude_code_no_adapter_file` and `test_hosts_claude_code_no_agents_md` (`test_init_core.py:2960`, `:3008`) so they don't depend on this machine's incidental plugin-install state
- Update `docs/guides/GETTING_STARTED.md` ("Existing Installation Detection" table and "Step 2: Install the Plugin"), `README.md`, `scripts/README.md`, `docs/reference/CLI.md` (`### ll-init`), and `docs/reference/HOST_COMPATIBILITY.md` ("Host tiers") to describe the new automatic claude-code install behavior
- Choose `info()`/`warning()` message text for the new branch that avoids colliding with existing substring assertions elsewhere in `TestHostDispatch` (e.g. `"not yet available"`, `"Unknown host"`)

## Impact

- **Priority**: P3 - First-run UX gap (default host ends up with no working `/ll:*` commands), not a regression or data-loss risk, so below P0-P2
- **Effort**: Medium - One new branch plus a `plugin_installed()` extraction from `detect_installation()`, but ~16 existing tests need `detect_installation`/`_subprocess.run` mocks retrofitted to stay hermetic (see Integration Map → Tests)
- **Risk**: Low - Change is additive and gated behind plugin absence; existing hosts' branches and the already-installed path are untouched
- **Breaking Change**: No

## Use Case

A developer runs `ll-init` in a new project, accepts the default host selection (Claude Code checked), and expects `/ll:capture-issue`, `/ll:manage-issue`, etc. to work immediately afterward without a separate manual plugin-install step.

## Acceptance Criteria

- If `claude-code` is selected/detected as a host, the `claude` binary resolves, and the `ll@little-loops` plugin is absent from `claude plugin list` (`plugin_installed(binary)` False), `ll-init` runs the marketplace add + `plugin install ll@little-loops -y` — **including when pip metadata reports `pypi`/`local-editable`** (pip-package presence must not suppress the install; see Expected Behavior's design correction).
- If the user unchecks `claude-code` in the TUI host checklist (or omits it from `--hosts`), no install is attempted.
- If the plugin is already installed (`plugin_installed(binary)` True), no redundant install is attempted; the upgrade case stays with `_dispatch_host_upgrade()` (`scripts/little_loops/init/cli.py:172`) and is not duplicated.
- `--dry-run` performs no marketplace-add/install subprocess calls (consistent with every sibling branch's `dry_run` contract).
- Failure to install (e.g. `claude` binary present but the install subprocess exits non-zero, raises `TimeoutExpired` against the `timeout=120` bound, or raises an OS error) is surfaced as a warning, not a silent no-op and not an uncaught exception, consistent with the `warning()`/`info()` pattern already used for the other hosts in `_dispatch_host_adapters()`.
- `ll-init --upgrade` with `claude-code` selected and the plugin absent installs it (via `_dispatch_host_upgrade()`'s delegation to `_dispatch_host_adapters(force=True)`); the existing `plugin update` behavior for the already-installed case is unchanged.
- `detect_installation()`'s observable behavior is unchanged after the `plugin_installed()` refactor (existing tests stay green).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Gap (gap-analysis structural check): none of the four existing Acceptance Criteria state expected behavior when `ll-init` runs with `--dry-run`. Per the established `dry_run` contract documented under Program Design → Codebase Research Findings (every side-effecting branch in `_dispatch_host_adapters()` gates on `dry_run`), a dry-run invocation with `claude-code` selected and no installed source should not actually shell out to `claude plugin marketplace add`/`claude plugin install` — this is implied by precedent but not currently asserted as a criterion.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-01 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-09-02
- **Status**: Completed

### Changes Made
- `scripts/little_loops/init/install_check.py`: added `_probe_plugin()`/`plugin_installed(binary) -> bool`, refactored `detect_installation()` to call the shared probe (behavior unchanged)
- `scripts/little_loops/init/cli.py`: added a `claude-code` branch to `_dispatch_host_adapters()` — resolves the host binary, no-ops on missing binary/`dry_run`/already-installed, otherwise runs best-effort `marketplace add` then `plugin install ll@little-loops -y` (`timeout=120`, `info()`/`warning()` reporting)
- `scripts/tests/test_init_core.py`: new `TestClaudeCodeAutoInstall` class (10 tests) plus an autouse `_default_plugin_installed` fixture stubbing the new gate to `True` for the rest of the file
- `scripts/tests/test_init_tui.py`: extended the existing autouse `mock_detect_installation` fixture with the same `plugin_installed` stub (TUI's `_apply_config()` calls `_dispatch_host_adapters()` with no `dry_run` kwarg)
- `scripts/tests/test_init_audit_fixes.py`, `scripts/tests/test_init_skill_fixtures.py`, `scripts/tests/integration/test_init_e2e.py`: added the same stub to each file's shared `_run()`/`_run_init()` helper
- `docs/guides/GETTING_STARTED.md`, `README.md`, `scripts/README.md`, `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`: documented the new auto-install behavior

### Verification Results
- Tests: PASS (22352 passed, 42 skipped, full suite)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:manage-issue` - 2026-09-02T03:32:17 - `fd57def2-5d14-4292-ae17-dbabd176ae11.jsonl`
- `/ll:confidence-check` - 2026-09-02T03:08:14 - `bb906cb6-447a-4e73-92c7-9067b87990ec.jsonl`
- `/ll:refine-issue` - 2026-09-02T02:50:47 - `e1ccf5f9-3d11-46da-b6d8-7e77648d884b.jsonl`
- `/ll:verify-issues` - 2026-09-01T04:44:53 - `8486b04b-164d-4f78-8378-f72d0c6fa4d3.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-01T04:42:38 - `07acdd53-4d5d-4207-99c9-310382b1a8e5.jsonl`
- `/ll:verify-issues` - 2026-09-01T04:38:12 - `40b7a789-f8db-4653-baaa-e3175b0ea699.jsonl`
- `/ll:wire-issue` - 2026-09-01T04:35:51 - `f8a17cf2-c664-4f0b-8a41-7619ae34b9bf.jsonl`
- `/ll:refine-issue` - 2026-09-01T04:27:13 - `ccaa2b41-32ae-4c21-ae8d-777bf39b68ad.jsonl`
- `/ll:format-issue` - 2026-09-01T04:14:36 - `e78ad427-afac-4f8a-8262-9a68ce395c55.jsonl`
- `/ll:capture-issue` - 2026-09-01T03:55:58 - `54b7abda-af7a-4b45-bfa4-e6f3cd9335a3.jsonl`
