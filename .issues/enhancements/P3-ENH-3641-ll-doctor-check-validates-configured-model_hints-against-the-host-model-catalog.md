---
id: ENH-3641
type: ENH
title: ll-doctor check validates configured model_hints against the host model catalog
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T20:53:36Z'
parent: EPIC-3563
labels:
- multi-host
learning_tests_required:
- codex
---

# ENH-3641: ll-doctor check validates configured model_hints against the host model catalog

## Summary

Add an `ll-doctor` check that validates the user's `orchestration.model_hints` values against the host's own model catalog, and warns when a configured model is hidden, upgraded or retiring. It runs only in `ll-doctor`, never on the loop run path, so hint resolution stays deterministic and offline.

## Current Behavior

`resolve_model_hint` (`little_loops.host_runner`) passes `orchestration.model_hints` values through as literals on every CLI backend. Nothing checks that a configured value is a model the host still accepts. Non-Claude hosts have no built-in hint mapping (EPIC-3563 scope), so every Codex/Gemini/Kimi/Qwen/OMP user who declares hints writes model IDs by hand, and those IDs go stale silently. The first sign is a failed host invocation mid-run.

Codex publishes the data needed to catch this: `codex debug models` (codex-cli 0.152.1) prints a catalog JSON (`{"models": [...]}`) with per-model `slug`, `priority`, `visibility` (`list`/`hide`) and `upgrade {model, migration_markdown, retirement_at}`. Example seen 2026-09-28: `gpt-5.5` carries `upgrade.model = "gpt-5.6-sol"`, `retirement_at = 2026-10-14T19:00:00Z`.

## Expected Behavior

`ll-doctor` shows a "Model hints" section. For each backend/hint pair in `orchestration.model_hints` whose host exposes a catalog (Codex today):

- slug not in the catalog → WARN "not in <host> catalog"
- `visibility: hide` → WARN "hidden in <host> catalog"
- `upgrade` present → WARN naming the replacement and `retirement_at`, plus a copy-pasteable config line (`orchestration.model_hints.codex.coding = "gpt-5.6-sol"`)
- otherwise OK

Hosts without a catalog probe, a missing binary, a non-zero exit, a timeout or an unparseable/changed JSON shape each yield one informational "catalog unavailable" row; the check never fails the doctor run. With no `model_hints` configured, the section prints a single "none configured" row.

## Motivation

EPIC-3563 decided against runtime catalog probes and heuristics (second-opinion consult, 2026-09-28): a run-time heuristic is a silent fallback by another name and breaks run reproducibility. That leaves user config as the only path on non-Claude hosts. This check gives config a staleness detector, which also removes the reason seeded/suggested config values were rejected earlier (no update path once copied).

## Proposed Solution

Follow the advisor section pattern in `little_loops.cli.doctor` (`_advisor_data` → `_print_advisor_section` → `@register_check _advisor_check`):

- `_model_hints_data() -> list[dict]` — no-arg, sources `BRConfig(Path.cwd()).orchestration.model_hints`; per catalog-capable backend, calls a probe; emits rows with `name`, `status`, `severity`, `note`.
- `_probe_codex_catalog() -> dict[str, dict] | None` — runs the Codex binary via `resolve_host_named("codex")` (never a `"codex"` literal; see Host CLI Abstraction) with args `debug models`, short timeout, returns `{slug: entry}` or `None` on any failure. Memoize like `_probe_advisor_version`.
- Keep the probe table keyed by backend so a second host can register a catalog probe later without touching the row logic.
- Severity: `CheckResult.severity` is only `error`/`informational` (no `warning`), so every row is `informational` — WARN rows use `status="partial"`, OK rows `status="full"`, unavailable rows `status="unsupported"`. That keeps the doctor exit code untouched (`_exit_code_for` fails only on `error` + `unsupported`).

`codex debug` is a debug subcommand with no stability promise. The probe must treat any schema surprise as "catalog unavailable", and tests must pin the parsed fields (`slug`, `visibility`, `upgrade.model`, `upgrade.retirement_at`) with a fixture, not the live binary.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Live catalog shape (verified 2026-09-28 against codex-cli 0.152.1, `codex debug models`)**: top-level object with a `models` list (6 entries). Each entry carries `slug`, `visibility` (`list`/`hide`), `priority`, and an `upgrade` key; `upgrade` is `null` for models with no successor and an object `{model, migration_markdown, retirement_at}` otherwise (`gpt-5.5` → `gpt-5.6-sol`, `2026-10-14T19:00:00Z`). Entries also carry ~35 unrelated large fields (`base_instructions`, etc.), so the parser must read only the four pinned fields and must treat `upgrade: null` as "no upgrade", not as a schema surprise.
- **Row granularity is unspecified and must be pinned by a test**: Expected Behavior is per backend/hint pair for catalog-capable hosts, but "hosts without a catalog probe … each yield one informational row" does not say per-pair or per-backend. `model_hints` may also hold `False` values (skipped) and backends that have no host binary (`anthropic-api`, `fake`), and existing sections split between multi-row list data (`_advisor_data`, named rows) and single-row dict data (`_code_query_data`) — the choice affects the `--json` shape and the docs bullet.
- **Failure-containment precedent**: `_code_query_data` wraps its probes in `except Exception:` ("doctor must never crash on a probe") and returns an informational row; `_advisor_data` catches only `HostNotConfigured` because `_probe_version` already swallows OS-level errors. The no-raise AC for a probe that also parses JSON needs the broader containment, since `json.JSONDecodeError`, `KeyError`/`TypeError` on schema drift and a non-dict `models` are not covered by `_probe_version`'s exception tuple. `doctor.py` has no shared JSON-or-None helper (`fleet_improve._parse_json_or_none` exists but is unrelated to doctor).
- **Memoization scope**: `_probe_advisor_version` is `@lru_cache` keyed on host name specifically so it does not leak across `monkeypatch.chdir` / patched-`BRConfig` test boundaries, and exceptions are not memoized. A zero-arg `_probe_codex_catalog` cache has no key to discriminate tests, so cache-clearing in tests is load-bearing.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Files to modify**: `scripts/little_loops/cli/doctor.py` (new section), `docs/reference/CLI.md` (`### ll-doctor`, ~line 490), `docs/reference/CONFIGURATION.md` (`model_hints` row under `### orchestration`, ~line 1370). Tests belong beside the advisor tests in `scripts/tests/test_cli_doctor_install_checks.py` (`TestAdvisor`) and `scripts/tests/test_cli_doctor.py` (`--json`/text wiring).
- **Section wiring is hand-written at three sites, none auto-discovered** (`doctor.py`): the `--json` branch of `_print_report` (`data = {... "advisor": _advisor_data(), "code_query": _code_query_data()}`), the `if not args.json:` block of `main_doctor` (`_print_advisor_section()` then `_print_code_query_section()`), and `@register_check`. `CheckResult` objects feed only the exit code (`_exit_code_for`), never `--json` — so "`--json` includes its rows" (AC 1) is satisfied only by adding a key to `_print_report`'s `data` dict, not by registering the check.
- **Status/severity vocabulary (verified)**: `CheckResult.status` is `Literal["full","partial","unsupported"]`; `severity` is `Literal["error","informational"]`; `_STATUS_SYMBOLS` has exactly `full` ✓ / `partial` ○ / `unsupported` ✗ (an unknown status prints `?`). `_exit_code_for` fails only on `severity == "error" and status == "unsupported"`, so every proposed row (all `informational`) is exit-code-neutral.
- **Existing probe does not fit the catalog call as-is**: `_probe_version(runner)` runs `[invocation.binary, *invocation.args]` (i.e. `codex --version`) with `timeout=10`, gates on `runner.detect()` (`shutil.which("codex")`), and never inspects `returncode` — it returns `stdout.strip()`. `CodexRunner.build_version_check()` returns `HostInvocation(binary="codex", args=["--version"], ...)`, so `[invocation.binary, "debug", "models"]` is well-formed but drops `invocation.args`. The non-zero-exit AC therefore needs new handling; no existing doctor test exercises a non-zero exit (the mocked `subprocess.run` never sets `returncode`).
- **Spawn-site gate**: `scripts/tests/test_enh3184_spawn_site_guard.py` pins per-module `(spawns, exempted)` counts; `little_loops/cli/doctor.py` is pinned at `(1, 1)` (the `_probe_version` `subprocess.run`, marked `# ll-no-project: detection probe, no task payload (ENH-3184 AC2)`). A second `subprocess.run` in `doctor.py` — or an unmarked one — fails that test, and it must be reconciled deliberately (marker comment + updated pin, or routing through the existing spawn site).
- **Config read path and mock hazard**: `BRConfig(Path.cwd()).orchestration.model_hints` is `dict[backend, dict[hint, str | False]]` (`config/orchestration.py:_validate_model_hints`; backend keys come from `hint_backend_keys()` = `RUNTIME_HOST_CAPABILITIES` ∪ `TEST_ONLY_HOSTS` ∪ `{"anthropic-api"}`; hint names from `MODEL_HINTS = ("coding","reasoning","burst")`; missing config → `{}`). `main_doctor` already builds `BRConfig(Path.cwd())` unguarded, and `test_cli_doctor.py` patches `little_loops.config.BRConfig` with a bare `MagicMock`, where `.orchestration.model_hints` is not a dict — the advisor path survives only via its `isinstance(advisor.host, str)` guard, so the new data function needs an equivalent non-dict guard. `_FakeOrchestrationConfig` in `test_cli_doctor_install_checks.py` carries only `host_cli` (no `model_hints`), so fixtures need extending.
- **Test conventions in force**: data-function tests `monkeypatch.chdir(tmp_path)`, patch at the import site (`little_loops.config.BRConfig`, `little_loops.host_runner.resolve_host_named`), call `_x_data()` directly, and assert `status`/`severity`/`note`; exit-code neutrality is asserted as `_exit_code_for(_x_check()) == 0`; subprocess is faked via `patch("little_loops.cli.doctor.subprocess.run", ...)` with `MagicMock(stdout=...)`, `TimeoutExpired`, `FileNotFoundError`. The autouse `_clear_advisor_probe_cache` fixture is keyed to `_probe_advisor_version` by name, so a new `lru_cache`d probe needs its own `cache_clear()` fixture or results leak across tests.
- **Docs**: `### ll-doctor` prose lists sections in bold with issue IDs ("always runs 7 default install-surface checks"), its `--json` bullet enumerates every JSON key with its row shape, and its exit-code paragraph states informational rows never affect the exit code (it calls the advisor "always a warning" although no `warning` severity exists). `CONFIGURATION.md:1370` documents `model_hints` with no `ll-doctor` reference. `docs/reference/` is end-user audience — no `scripts/tests/` paths.
- **Out-of-scope consumers of `model_hints` (must stay untouched)**: `fsm/executor.py:_preflight_model_hints`, `cli/loop/header.py`, `cli/loop/run.py`, `cli/loop/lifecycle.py`. `doctor.py` and `RUNTIME_HOST_CAPABILITIES` do not reference `model_hints` today.

## Program Design

### Types

- `model_hints: dict[str, dict[str, str | Literal[False]]]` — `BRConfig.orchestration.model_hints`, already validated by `_validate_model_hints`; `False` values mean "no model" and are skipped
- `catalog: dict[str, dict[str, Any]]` — Codex `slug` → catalog entry (`visibility`, `upgrade.model`, `upgrade.retirement_at`)
- `_CATALOG_PROBES: dict[str, Callable[[], dict[str, dict[str, Any]] | None]]` — backend name → probe; only `"codex"` registered

### Signatures

- `_probe_codex_catalog() -> dict[str, dict[str, Any]] | None` — `@lru_cache`; runs `[invocation.binary, "debug", "models"]` from `resolve_host_named("codex").build_version_check()` with a short timeout; `None` on `HostNotConfigured`, `FileNotFoundError`, `OSError`, `TimeoutExpired`, non-zero exit, bad JSON, or missing `models` key
- `_model_hints_data() -> list[dict[str, Any]]` — no-arg; builds `BRConfig(Path.cwd())`, emits rows with `name`, `status`, `severity`, `note`
- `_print_model_hints_section() -> None` — prints the "Model hints" section using `_STATUS_SYMBOLS`
- `_model_hints_check() -> list[CheckResult]` — `@register_check`; maps `_model_hints_data()` rows to `CheckResult`

### Call Path

`main_doctor` -> `_print_model_hints_section` -> `_model_hints_data` -> `_probe_codex_catalog` -> `resolve_host_named`

`main_doctor` -> `_run_registered_checks` -> `_model_hints_check` -> `_model_hints_data`

## Impact

- **Priority**: P3 — no shipped loop declares `model_hint` today; this is the safety net for users who configure non-Claude hints.
- **Effort**: Small — one doctor section on an existing pattern plus fixtures.
- **Risk**: Low — read-only diagnostic; the unstable `codex debug` surface is contained to "catalog unavailable".
- **Breaking Change**: No.

## Scope Boundaries

- **In**: doctor-only check; Codex catalog probe; row/print/register wiring; docs row in `docs/reference/CLI.md` (`ll-doctor`) and a note in `docs/reference/CONFIGURATION.md` (`orchestration.model_hints`).
- **Out**: any use of the catalog during `ll-loop run` or `ll-loop validate`; auto-writing config; models.dev or other network catalogs; built-in non-Claude mappings (see the Codex host-default issue).

## Acceptance Criteria

- [ ] `ll-doctor` prints a Model hints section; `--json` includes its rows.
- [ ] Fixture-driven tests cover: OK slug, unknown slug, hidden slug, upgraded slug (replacement + date + suggested config line in the note), no `model_hints` configured, binary missing, non-zero exit, timeout, malformed JSON, missing `models` key.
- [ ] No failure path raises out of the check or changes the doctor exit code.
- [ ] Codex binary resolved through `host_runner`, not a string literal.

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-28T22:17:13 - `6f422968-702e-4b64-aab8-1417160db4d7.jsonl`
- `/ll:format-issue` - 2026-09-28T22:12:20 - `3482ce67-14f8-4ba7-ad30-d5a96bb26e45.jsonl`
