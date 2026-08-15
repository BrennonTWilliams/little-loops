---
id: BUG-3186
type: BUG
title: CLI.md missing subcommands (check-acceptance-criteria, check-verify-verdict,
  epic-consistency, sync reconcile, compact-session) and qwen host list gaps
priority: P3
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:32Z'
completed_at: '2026-08-15T19:31:32Z'
---

# BUG-3186: CLI.md missing subcommands (check-acceptance-criteria, check-verify-verdict, epic-consistency, sync reconcile, compact-session) and qwen host list gaps

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/reference/CLI.md` and several other reference docs are missing real, currently-installed CLI surface, and multiple docs undercount the fully-wired host list by omitting `qwen`.

## Current Behavior

- `docs/reference/CLI.md` has no `####` entry for `ll-issues check-acceptance-criteria` (`scripts/little_loops/cli/issues/check_acceptance_criteria.py`, ENH-3031), `ll-issues check-verify-verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py`, ENH-3031), or `ll-issues epic-consistency` / alias `ec` (`scripts/little_loops/cli/issues/epic_consistency.py`).
- The `ll-sync` section lists subcommands but omits `ll-sync reconcile` ("Promote feature-branch issues to done when their PR is merged", `scripts/little_loops/cli/sync.py:96-99`).
- `ll-compact-session` is a real installed entry point (`scripts/pyproject.toml`, `little_loops.cli:main_compact_session`) with no `### ll-compact-session` section anywhere in CLI.md.
- `qwen` is a fully-wired host (`install_qwen_adapter` in `scripts/little_loops/init/cli.py`, identical treatment to `claude-code`/`codex`/`kimi-code`) but is missing from the "fully wired hosts" list in `docs/reference/CLI.md:37,49`, `README.md`, `docs/guides/GETTING_STARTED.md:101`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:364` (`--cross-host` probe order), and `docs/reference/CONFIGURATION.md:1234` (`orchestration.host_cli` enum).

### The host-list problem is broader than a missing `qwen` (amended 2026-08-15)

Inserting `qwen` into five lists fixes today's symptom and leaves the underlying
defect: **there are three different host sets in the code and the docs conflate them
into one undefined phrase, "fully wired."** Verified 2026-08-15:

| Axis | Source of truth | Members |
|---|---|---|
| **Orchestration runners** — valid `orchestration.host_cli` / `LL_HOST_CLI` values | `_HOST_RUNNER_REGISTRY`, `scripts/little_loops/host_runner.py` | `claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`, `kimi-code`, `qwen` (8) |
| **`ll-init --hosts` accepted values** | `_KNOWN_HOSTS`, `scripts/little_loops/init/cli.py` (`--hosts` help at `:962-971`) | `claude-code`, `codex`, `opencode`, `kimi-code`, `pi`, `qwen` (6 — **no `gemini`, no `omp`**) |
| **Hook-adapter installers that actually write a file** | `install_*_adapter` in `scripts/little_loops/init/writers.py` | `codex`, `kimi-code`, `qwen` (3). `claude-code` needs no installer — plugin hooks fire natively. `opencode`/`pi` hit explicit "adapter not yet available" branches (`init/cli.py`, `opencode` → info branch, `pi` → EPIC-1622). |

Consequences the original bullet missed:

- `docs/reference/CONFIGURATION.md:1234` is an **orchestration-runner** enum, so its
  only gap is `qwen` — but `gemini` and `omp` are legitimately there and appear in **no**
  "fully wired" prose list anywhere. An implementer working from the original bullet may
  read that asymmetry as a second bug and "fix" it by adding `gemini`/`omp` to the
  `--hosts` lists, where they are not valid values.
- `hooks/adapters/opencode/` exists on disk but contains only `bun.lock` — a stub. The
  prose "recognized, adapter not yet available" is correct; the stub dir is not evidence
  against it. **Do not** promote `opencode` to fully-wired on the strength of the directory.

## Expected Behavior

- CLI.md documents `ll-issues check-acceptance-criteria`, `ll-issues check-verify-verdict`, `ll-issues epic-consistency`/`ec`, `ll-sync reconcile`, and `ll-compact-session`.
- **Define the three tiers once and point every site at that definition**, rather than
  patching five parallel lists:
  - **Adapter-wired** (`ll-init --hosts` installs a hook adapter): `codex`, `kimi-code`, `qwen`, plus `claude-code` (native, no adapter file).
  - **Recognized, adapter pending**: `opencode`, `pi`.
  - **Orchestration-only** (valid `LL_HOST_CLI`, not an `--hosts` value): `gemini`, `omp`.
- Sites to update: `docs/reference/CLI.md:37,49`, `README.md`, `docs/guides/GETTING_STARTED.md:101`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:364`, `docs/reference/CONFIGURATION.md:1234` (add `qwen` only — the enum's other members are correct).
- The canonical tier table should live in **one** doc (suggest `docs/reference/HOST_COMPATIBILITY.md`, already the host-compat home per CLAUDE.md) with the other five sites linking to it.

## Acceptance Criteria

- [ ] `docs/reference/CLI.md` has `####` entries for `ll-issues check-acceptance-criteria`, `ll-issues check-verify-verdict`, `ll-issues epic-consistency` (+ `ec` alias), and `ll-sync reconcile`; a `### ll-compact-session` section exists.
- [ ] A single canonical three-tier host table exists in `docs/reference/HOST_COMPATIBILITY.md`, its members matching `_HOST_RUNNER_REGISTRY`, `_KNOWN_HOSTS`, and the `install_*_adapter` set respectively.
- [ ] All five listed sites either include `qwen` at the correct tier or link to the canonical table.
- [ ] `gemini`/`omp` are **not** added to any `--hosts` list; `opencode` is **not** promoted to adapter-wired.
- [ ] **A test asserts the canonical table against code.** Add a case to `scripts/tests/test_wiring_guides_and_meta.py` that derives the three sets — `_HOST_RUNNER_REGISTRY` (`scripts/little_loops/host_runner.py`), `_KNOWN_HOSTS` (`scripts/little_loops/init/cli.py`), and the `install_*_adapter` functions (`scripts/little_loops/init/writers.py`) — and fails if the canonical table's tiers disagree. Adding a host to any of the three registries without updating the table must red `python -m pytest scripts/tests/`.

  This assertion belongs **here, not in ENH-3195** (the sibling derive-and-assert gate). ENH-3195's other checks bind to shapes that already exist; this one binds to a table this issue creates, whose location and format are decided by whoever implements it. Writing the test in the same change — when the anchor is known — is cheaper and far less brittle than specifying it upstream. See ENH-3195 § "Deliberately out of scope: host-tier coverage".

**Scope note (triage, 2026-08-15):** this issue owns **every** `qwen` host-list edit,
including `docs/guides/GETTING_STARTED.md:101`. BUG-3191 separately edits
`GETTING_STARTED.md:86` and `:97-98` and has been amended to leave `:101` alone. If the
two are worked in parallel, expect them to touch the same file within ~15 lines —
sequence them or accept a trivial merge.

## Motivation

Undocumented subcommands are invisible to users grepping CLI.md for capability, and the missing `qwen` entries make host support look narrower than it is — both erode trust in the reference doc as authoritative (CLAUDE.md states `<cmd> --help` is authoritative over prose, but CLI.md is meant to mirror it).

## Impact

- **Priority**: P3 — no functional bug, but affects discoverability of existing features.
- **Effort**: Small-Medium — the CLI.md sections are mechanical additions following the existing `####`/`###` patterns; the canonical host table plus its wiring test is the larger half. Revised up from Small when the host-tier assertion moved here from ENH-3195.
- **Risk**: Low. **No longer strictly doc-only** — the last acceptance criterion adds a test to `scripts/tests/test_wiring_guides_and_meta.py`. The doc edits carry no risk; the test carries the usual risk of a new gate (a wrong assertion reds the suite for everyone), so derive all three sets by importing the registries rather than by parsing source text.
- **Breaking Change**: No.


## Status

**Open** | Created: 2026-08-15 | Priority: P3
