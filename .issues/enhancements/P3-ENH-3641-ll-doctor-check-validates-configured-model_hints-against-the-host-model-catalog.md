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

Add an `ll-doctor` check that validates the user's `orchestration.model_hints` values against the host's own model catalog, and warns when a configured model is hidden, upgraded or retiring. It runs only in `ll-doctor`, never on the loop run path, so hint resolution during `ll-loop run`/`validate` stays deterministic and offline. The doctor output itself is not offline-deterministic: it reads Codex's refreshed catalog, which can change between runs (see Proposed Solution).

## Current Behavior

`resolve_model_hint` (`little_loops.host_runner`) passes `orchestration.model_hints` values through as literals on every CLI backend. Nothing checks that a configured value is a model the host still accepts. Non-Claude hosts have no built-in hint mapping (EPIC-3563 scope), so every Codex/Gemini/Kimi/Qwen/OMP user who declares hints writes model IDs by hand, and those IDs go stale silently. The first sign is a failed host invocation mid-run.

Codex publishes the data needed to catch this: `codex debug models` (codex-cli 0.152.1) prints a catalog JSON (`{"models": [...]}`) with per-model `slug`, `priority`, `visibility` (`list`/`hide`) and `upgrade {model, migration_markdown, retirement_at}`. Example seen 2026-09-28: `gpt-5.5` carries `upgrade.model = "gpt-5.6-sol"`, `retirement_at = 2026-10-14T19:00:00Z`.

## Expected Behavior

`ll-doctor` shows a "Model hints" section. Row granularity (pinned by tests):

- **Catalog-capable backend (Codex today), probe succeeded** → one row per configured backend/hint pair, named `<backend>.<hint>` (e.g. `codex.coding`). Verdict per slug, in this precedence (first match wins; hidden is appended to the upgrade note when both apply):
  1. `upgrade` present → WARN naming the replacement and `retirement_at` ("retires 2026-10-14", or "retired on 2026-10-14" once past), plus a plain instruction: set `orchestration.model_hints.codex.coding` to `"gpt-5.6-sol"`. (`ll-config` has only a `get` subcommand, so the note must not pretend to be command or file syntax.)
  2. `visibility: hide` → WARN "hidden in codex catalog"
  3. slug not listed → WARN "not listed in codex catalog (retired, or a custom-provider model)". The refreshed catalog drops older models the host may still accept (`gpt-5.4`, `gpt-5.2` on 2026-09-28), so the wording must not claim the host rejects it.
  4. otherwise OK
- **Catalog-capable backend, probe failed** (missing binary, non-zero exit, timeout, unparseable JSON, missing/non-list `models`) → one row per backend named `<backend>`, "catalog unavailable: <reason>".
- **Codex configured with a non-OpenAI `model_provider`** → one row per backend, "not checked: custom model_provider <name>"; the catalog does not describe that provider's models.
- **Backend with no catalog probe** (`claude-code`, `gemini`, …) → one row per backend, "not checked: no model catalog for <host>". Printed with `–`, not `✗`, so Claude-only users do not see an error-looking symbol for a non-problem.
- **Skipped entirely**: hint values set to `False`; the `anthropic-api` and test-only fake backends (no host binary).
- **No `model_hints` configured** → a single "none configured" row.

The check never fails the doctor run and never raises.

## Motivation

EPIC-3563 decided against runtime catalog probes and heuristics (second-opinion consult, 2026-09-28): a run-time heuristic is a silent fallback by another name and breaks run reproducibility. That leaves user config as the only path on non-Claude hosts. This check gives config a staleness detector, which also removes the reason seeded/suggested config values were rejected earlier (no update path once copied).

## Proposed Solution

Follow the advisor section pattern in `little_loops.cli.doctor` (`_advisor_data` → `_print_advisor_section` → `@register_check _advisor_check`):

- `_model_hints_data() -> list[dict]` — no-arg, sources `BRConfig(Path.cwd()).orchestration.model_hints` (guarded with `isinstance(..., dict)`); per catalog-capable backend, calls its probe; emits rows with `name`, `status`, `severity`, `checked`, `note`.
- `_probe_catalog(backend: str) -> dict[str, dict] | None` — `@lru_cache` keyed on the backend name, mirroring `_probe_advisor_version(host)` so results do not leak across tests. Looks up the backend in `_CATALOG_PARSERS`, resolves the binary via `resolve_host_named(backend)` (never a `"codex"` literal; see Host CLI Abstraction), gates on `runner.detect()`, runs the backend's catalog args, checks `returncode`, and returns `{slug: entry}` or `None` on any failure (broad `except Exception`, as in `_code_query_data`). Exceptions are not memoized.
- `_CATALOG_PARSERS: dict[str, tuple[list[str], Callable[[str], dict[str, dict] | None]]]` — backend → (catalog args, stdout parser). Only `"codex"` → (`["debug", "models"]`, `_parse_codex_catalog`) is registered; a second host adds an entry without touching the row logic.
- **Catalog mode: refreshed (default), not `--bundled`.** Verified 2026-09-28 on codex-cli 0.152.1, the two disagree: refreshed shows `gpt-5.5` → upgrade `gpt-5.6-sol` (retires 2026-10-14) and omits `gpt-5.4`/`gpt-5.2`; `--bundled` shows `gpt-5.5` with no upgrade, `gpt-5.4` hidden with upgrade → `gpt-5.6-terra`, and `gpt-5.2` listed. The bundled catalog is frozen at the binary's release date, so it misses exactly the retirements this check exists to catch. The refresh may do network I/O (Codex caches it in `~/.codex/models_cache.json`), so use `timeout=20` (live call took ~1s) and document that doctor output can change between runs.
- **`model_provider` guard**: read top-level `model_provider` from Codex's `config.toml` (in the `CODEX_HOME` directory, default `~/.codex`) with stdlib `tomllib`; if set and not `"openai"`, emit the "not checked: custom model_provider" row and skip the probe. Profile-level providers are out of scope. Any read/parse failure → treat as unset.
- **Spawn site**: the probe gets its own `subprocess.run` marked `# ll-no-project: detection probe, no task payload (ENH-3184 AC2)`, and the `test_enh3184_spawn_site_guard.py` pin for `little_loops/cli/doctor.py` moves `(1, 1)` → `(2, 2)`. Do not reuse `_probe_version`: it ignores `returncode` and drops `invocation.args`, and changing it would touch the working version probe.
- Severity: `CheckResult.severity` is only `error`/`informational` (no `warning`), so every row is `informational` — OK rows use `status="full"`, WARN rows `status="partial"`, catalog-unavailable and not-checked rows `status="unsupported"`. Not-checked rows carry `checked: False` and `_print_model_hints_section` prints them with `–` instead of `✗`. All rows are exit-code-neutral (`_exit_code_for` fails only on `error` + `unsupported`).

`codex debug` is a debug subcommand with no stability promise. The probe must treat any schema surprise as "catalog unavailable", and tests must pin the parsed fields (`slug`, `visibility`, `upgrade.model`, `upgrade.retirement_at`) with a fixture, not the live binary. The `codex` learning-test record is proven but does not cover `debug models`; the fixture and its provenance README are the contract for this surface.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Live catalog shape (verified 2026-09-28 against codex-cli 0.152.1, `codex debug models`)**: top-level object with a `models` list (6 entries). Each entry carries `slug`, `visibility` (`list`/`hide`), `priority`, and an `upgrade` key; `upgrade` is `null` for models with no successor and an object `{model, migration_markdown, retirement_at}` otherwise (`gpt-5.5` → `gpt-5.6-sol`, `2026-10-14T19:00:00Z`). Entries also carry ~35 unrelated large fields (`base_instructions`, etc.), so the parser must read only the four pinned fields and must treat `upgrade: null` as "no upgrade", not as a schema surprise.
- **Row granularity is unspecified and must be pinned by a test**: Expected Behavior is per backend/hint pair for catalog-capable hosts, but "hosts without a catalog probe … each yield one informational row" does not say per-pair or per-backend. `model_hints` may also hold `False` values (skipped) and backends that have no host binary (`anthropic-api`, `fake`), and existing sections split between multi-row list data (`_advisor_data`, named rows) and single-row dict data (`_code_query_data`) — the choice affects the `--json` shape and the docs bullet. **Resolved (review 2026-09-28)**: see Expected Behavior — per pair for a successful catalog probe, per backend for every other row; the section is a multi-row list like `_advisor_data`.
- **Failure-containment precedent**: `_code_query_data` wraps its probes in `except Exception:` ("doctor must never crash on a probe") and returns an informational row; `_advisor_data` catches only `HostNotConfigured` because `_probe_version` already swallows OS-level errors. The no-raise AC for a probe that also parses JSON needs the broader containment, since `json.JSONDecodeError`, `KeyError`/`TypeError` on schema drift and a non-dict `models` are not covered by `_probe_version`'s exception tuple. `doctor.py` has no shared JSON-or-None helper (`fleet_improve._parse_json_or_none` exists but is unrelated to doctor).
- **Memoization scope**: `_probe_advisor_version` is `@lru_cache` keyed on host name specifically so it does not leak across `monkeypatch.chdir` / patched-`BRConfig` test boundaries, and exceptions are not memoized. A zero-arg `_probe_codex_catalog` cache has no key to discriminate tests, so cache-clearing in tests is load-bearing. **Resolved (review 2026-09-28)**: the probe is `_probe_catalog(backend: str)`, keyed like `_probe_advisor_version`, and one autouse `cache_clear()` fixture in `scripts/tests/conftest.py` covers every doctor test file.

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

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md:767` — section list "Entry Points, Skills & Commands, Decisions Store, History DB, FSM Loop Validity, Schema Drift, and Advisor" in the `ll-doctor` install-surface paragraph; append "Model hints" [Agent 2 finding]
- `docs/ARCHITECTURE.md:922` — `--json` key enumeration (`entry_points`, …, `schema_drift`, `advisor`, `full`) in the `CapabilityReport` table row; add `model_hints` [Agent 2 finding]
- `scripts/little_loops/cli/doctor.py:1351` — add `"model_hints": _model_hints_data()` to the `--json` dict in `_print_report`, beside `"advisor": _advisor_data()` [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:1468` — call `_print_model_hints_section()` in `main_doctor`'s `if not args.json:` block after `_print_code_query_section()` [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:1296` — `_probe_version` cannot be reused for the catalog call (no `returncode` check, drops `invocation.args`, single spawn site pinned at `(1, 1)`); the new probe gets its own `subprocess.run` with `# ll-no-project:` marker and the pin in `test_enh3184_spawn_site_guard.py` updated to `(2, 2)` (decided in review 2026-09-28; the shared-helper alternative would change the working version probe) [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py:211` — `_tool_capabilities` mirrors only the `CapabilityReport` fields of `_print_report`'s dict (not the install-surface keys); no change needed [Agent 1 finding]
- `scripts/little_loops/config-schema.json:2343` — `skill_budget` description cites `cli/doctor.py:536-555`, which is **already stale** (the skill-budget check is `_full_skill_budget_data`, ~line 920). Replace the line range with the symbol name (`cli/doctor.py:_full_skill_budget_data`) so it stops drifting [Agent 1 finding; corrected in review 2026-09-28]
- `scripts/little_loops/cli/__init__.py:66` — re-exports `main_doctor`; no change needed [Agent 1 finding]
- No loop YAML, hook, skill or command consumes `ll-doctor --json` keys (searched `.loops/`, `scripts/little_loops/loops/`, `hooks/`, `skills/`, `commands/`) [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3184_spawn_site_guard.py:42` — `_TASK_PATH_MODULES["little_loops/cli/doctor.py"] = (1, 1)` pin in `test_every_spawn_is_projected_or_exempted`; a second `subprocess.run` fails it unless marked and re-pinned [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py:627` — `_FakeOrchestrationConfig` carries only `host_cli`; add a `model_hints` attribute [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py:648` — autouse `_clear_advisor_probe_cache` is keyed to `_probe_advisor_version`; add one autouse `cache_clear()` fixture for `_probe_catalog` in `scripts/tests/conftest.py` so every doctor test file is covered [Agent 3 finding; simplified in review 2026-09-28]
- `scripts/tests/test_cli_doctor.py:54` — `_json_safe_config()` is a bare `MagicMock`; `.orchestration.model_hints` becomes a `MagicMock` that breaks `print_json` (`TypeError`) unless `_model_hints_data` guards with `isinstance(model_hints, dict)`; affects every `main_doctor` test in `TestMainDoctor`, `TestVersionProbe` and `TestCheckRegistry` [Agent 3 finding]
- `scripts/tests/test_cli_doctor.py:624` — `test_skips_probe_when_binary_not_detected` asserts `mock_run.assert_not_called()`; breaks if the Model hints section reaches a probe under a mocked config [Agent 3 finding]
- `scripts/tests/test_cli_doctor.py:24` — `_canned_code_query` autouse fixture pattern (also `test_cli_doctor_full.py:30`, `test_cli_doctor_trim.py:17`); add a matching canned `_model_hints_data` so the three files never spawn a real `codex` [Agent 3 finding]
- `scripts/tests/test_cli_doctor.py:777` — copy `test_json_payload_includes_advisor_key` for the `model_hints` `--json` key, and `test_text_mode_prints_advisor_section` (:799) for the text section [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py:961` — copy `test_magicmock_config_guard_attempts_no_resolution` for the non-dict `model_hints` guard, and `test_floor_violation_is_informational_and_does_not_fail_exit_code` (:702) for `_exit_code_for(_model_hints_check()) == 0` on each failure path [Agent 3 finding]
- `scripts/tests/test_cli_doctor.py:661` — `test_probe_timeout_falls_back_to_unknown` and `:687` `test_probe_failing_binary_falls_back_to_unknown` are the `TimeoutExpired`/`FileNotFoundError` fakes to copy; no doctor test sets `returncode`, so the non-zero-exit case follows `MagicMock(returncode=1, stdout="", stderr="boom")` from `test_host_runner.py:2510` `test_codex_cleanup_paths_unlinked_on_failure` [Agent 3 finding]
- `scripts/tests/test_stray_ll_regression.py:36` — `test_ll_doctor_from_subdirectory_creates_no_stray_ll` runs the real `ll-doctor --json` in a scratch project (empty `model_hints`, so no probe); the new section's `BRConfig(Path.cwd())` must not create a stray `.ll/` [Agent 1 finding]
- `scripts/tests/fixtures/codex/models-catalog.json` (new) — catalog fixture pinned to `slug`, `visibility`, `upgrade.model`, `upgrade.retirement_at`, including an `upgrade: null` entry, a hidden entry, an upgraded entry with a future `retirement_at`, one with a past `retirement_at`, and one both hidden and upgraded (bundled `gpt-5.4` shape); load via the `fixtures_dir` fixture (`conftest.py:569`), record capture provenance in `scripts/tests/fixtures/codex/README.md` (codex-cli 0.152.1, sanitization note), and run `ll-verify-private-refs` on it [Agent 3 finding]
- No test asserts the exact `--json` key set, exact stdout or registered-check count, so adding a key/section/check breaks none of them [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:497` — `--json` bullet enumerating each key with its row shape in `ll-doctor`; add `model_hints` [Agent 2 finding]
- `docs/reference/CLI.md:494` — section list and "7 default install-surface checks" count in `ll-doctor`; add **Model hints** with the issue ID [Agent 2 finding]
- `docs/codex/usage.md:150` — default install-surface check list ("Entry Points, … FSM Loop Validity") in the CI/`ll-doctor` consumers note; already omits Schema Drift/Advisor, add only if the list is refreshed [Agent 2 finding]
- `README.md:68` and `scripts/README.md:68` — generic `ll-doctor` mention, no section list; no edit expected, and if `README.md` is edited re-sync with `command cp -f README.md scripts/README.md` [Agent 1 finding]
- Docs gates in scope: `test_docs_audience_gate.py` covers `CLI.md`/`CONFIGURATION.md` (no `scripts/tests/` paths); `test_wiring_cli_registry.py:25` requires `ll-doctor` in `CLI.md` [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1819` — `orchestration.model_hints` description has no `ll-doctor` reference; add a one-line pointer to the doctor staleness check (schema text only, no key change) [Agent 2 finding]

## Program Design

### Types

- `model_hints: dict[str, dict[str, str | Literal[False]]]` — `BRConfig.orchestration.model_hints`, already validated by `_validate_model_hints`; `False` values mean "no model" and are skipped
- `catalog: dict[str, dict[str, Any]]` — Codex `slug` → catalog entry (`visibility`, `upgrade.model`, `upgrade.retirement_at`)
- `_CATALOG_PARSERS: dict[str, tuple[list[str], Callable[[str], dict[str, dict[str, Any]] | None]]]` — backend name → (catalog args, stdout parser); only `"codex"` → (`["debug", "models"]`, `_parse_codex_catalog`) registered

### Signatures

- `_probe_catalog(backend: str) -> dict[str, dict[str, Any]] | None` — `@lru_cache` keyed on backend; resolves `resolve_host_named(backend)`, gates on `runner.detect()`, runs `[runner.build_version_check().binary, *args]` with `timeout=20` (refreshed catalog, not `--bundled`), checks `returncode`; `None` on any exception, non-zero exit, or a parser `None`
- `_parse_codex_catalog(stdout: str) -> dict[str, dict[str, Any]] | None` — reads only `slug`, `visibility`, `upgrade.model`, `upgrade.retirement_at`; `upgrade: null` means no upgrade; `None` on bad JSON or a missing/non-list `models`
- `_codex_model_provider() -> str | None` — top-level `model_provider` from Codex's `config.toml` (in `CODEX_HOME`, default `~/.codex`) via `tomllib`; `None` on absence or any error
- `_model_hints_data() -> list[dict[str, Any]]` — no-arg; builds `BRConfig(Path.cwd())`, emits rows with `name`, `status`, `severity`, `checked`, `note`
- `_print_model_hints_section() -> None` — prints the "Model hints" section using `_STATUS_SYMBOLS`, with `–` for `checked: False` rows
- `_model_hints_check() -> list[CheckResult]` — `@register_check`; maps `_model_hints_data()` rows to `CheckResult`

### Call Path

`main_doctor` -> `_print_model_hints_section` -> `_model_hints_data` -> `_probe_catalog` -> `resolve_host_named`

`main_doctor` -> `_run_registered_checks` -> `_model_hints_check` -> `_model_hints_data`

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `"model_hints": _model_hints_data()` to `_print_report`'s `--json` dict and `_print_model_hints_section()` to `main_doctor`'s text block in `scripts/little_loops/cli/doctor.py`; `CheckResult`s never feed `--json`, so registering the check alone does not satisfy AC 1
- Give `_probe_catalog` its own `subprocess.run` with the `# ll-no-project:` marker and re-pin `scripts/tests/test_enh3184_spawn_site_guard.py` to `(2, 2)`
- Guard `_model_hints_data` with `isinstance(model_hints, dict)` and broad `except Exception` around probe + parse (matches `_code_query_data`); add one autouse `_probe_catalog.cache_clear()` fixture in `scripts/tests/conftest.py`
- Extend `_FakeOrchestrationConfig` with `model_hints`; add a canned `_model_hints_data` autouse fixture beside `_canned_code_query` in `test_cli_doctor.py`, `test_cli_doctor_full.py`, `test_cli_doctor_trim.py`
- Add `scripts/tests/fixtures/codex/models-catalog.json` (with an `upgrade: null` entry) and a `README.md` provenance note; run `ll-verify-private-refs` on it
- Update `docs/reference/CLI.md` (`### ll-doctor`: section list, `--json` bullet), `docs/reference/CONFIGURATION.md` (`model_hints` row), `docs/reference/HOST_COMPATIBILITY.md:767` and `docs/ARCHITECTURE.md:922` section/key lists; add a pointer in `config-schema.json` `orchestration.model_hints` description
- Replace the stale `cli/doctor.py:536-555` citation in `config-schema.json:2343` with `cli/doctor.py:_full_skill_budget_data`
- Docs (`CLI.md` `ll-doctor` entry): state that the check reads Codex's refreshed catalog, may do network I/O, and can report differently between runs

## Impact

- **Priority**: P3 — no shipped loop declares `model_hint` today; this is the safety net for users who configure non-Claude hints.
- **Effort**: Small — one doctor section on an existing pattern plus fixtures.
- **Risk**: Low — read-only diagnostic; the unstable `codex debug` surface is contained to "catalog unavailable".
- **Breaking Change**: No.

## Scope Boundaries

- **In**: doctor-only check; Codex catalog probe; row/print/register wiring; docs row in `docs/reference/CLI.md` (`ll-doctor`) and a note in `docs/reference/CONFIGURATION.md` (`orchestration.model_hints`).
- **Out**: any use of the catalog during `ll-loop run` or `ll-loop validate`; auto-writing config; models.dev or other network catalogs; built-in non-Claude mappings (ENH-3642); Codex profile-level `model_provider` overrides.

## Acceptance Criteria

- [ ] `ll-doctor` prints a Model hints section; `--json` includes its rows.
- [ ] Fixture-driven tests cover: OK slug, `upgrade: null` slug (OK), unlisted slug, hidden slug, upgraded slug with future retirement (replacement + "retires <date>" + set-key instruction in the note), upgraded slug with past retirement ("retired on <date>"), slug both hidden and upgraded (upgrade verdict, hidden appended), no `model_hints` configured, `False` hint value skipped, backend with no catalog probe ("not checked", `checked: False`), non-OpenAI `model_provider` ("not checked"), binary missing, non-zero exit, timeout, malformed JSON, missing `models` key.
- [ ] Probe invokes the refreshed catalog (`debug models` with no `--bundled`).
- [ ] No failure path raises out of the check or changes the doctor exit code.
- [ ] Codex binary resolved through `host_runner`, not a string literal.

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-28T22:36:29 - `29b6f7a1-cbe3-4641-a1f5-b4e98b2d2120.jsonl`
- `/ll:refine-issue` - 2026-09-28T22:17:13 - `6f422968-702e-4b64-aab8-1417160db4d7.jsonl`
- `/ll:format-issue` - 2026-09-28T22:12:20 - `3482ce67-14f8-4ba7-ad30-d5a96bb26e45.jsonl`
