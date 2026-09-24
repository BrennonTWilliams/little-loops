---
id: 3539
title: Run the deterministic test layer on both macOS and Linux
type: ENH
priority: P1
status: open
discovered_date: '2026-09-23'
labels: []
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# Run the deterministic test layer on both macOS and Linux

## Summary

The `ll-verify-*` family and the shipped bash hooks depend on `grep`, `date`,
`sort`, and `stat` — every one of which diverges between BSD and GNU. Users run
both platforms. Today each platform is covered by exactly one surface: macOS/BSD
only by the maintainer's manual local run, Linux/GNU only by CI. Neither
surface alone catches the class, and the macOS half is not automated.

Add automated macOS coverage to the deterministic (free, gating) test layer,
and add a static portability gate so the class is caught on any runner.

Distinct from multi-host divergence at the model/prompt layer (divergence runs
for prompt-shaped changes) and host artifact parity — this is OS-level
divergence inside the deterministic tooling itself.

## Current Behavior

- `.github/workflows/ci.yml` runs the unit tier (`-m "not integration and not
  conformance"`) on GitHub-hosted `ubuntu-latest` (GNU userland) on push to
  `main` only; conformance runs on self-hosted Thinky (Linux). There is no
  `pull_request` trigger (public repo; self-hosted RCE surface).
- The authoritative gate is the local `python -m pytest scripts/tests/` run,
  which on the maintainer's machine is macOS (BSD userland). It is manual.
- `.claude/CLAUDE.md` § Testing & CI Policy is stale: it says the unit suite
  runs on the self-hosted Thinky runner and forbids "paid/hosted" CI, while
  `ci.yml` already moved unit tests to GitHub-hosted `ubuntu-latest`
  (Buzz #ci-cd 2026-08-18).
- `hooks/scripts/lib/common.sh:101-151` already implements the portable
  pattern for `date` (`date -j -f` then `date -d`) and `stat` (`stat -f %m`
  then `stat -c %Y`).
- Known divergence: `hooks/scripts/record-hook-event.sh:43,49` computes
  `$(($(date +%s%N 2>/dev/null || echo 0) / 1000000))`. On older BSD `date`,
  `%N` emits a literal `N` with exit 0, so the `|| echo 0` fallback never fires
  and the arithmetic expansion errors. Darwin 25's `/bin/date` supports `%N`,
  so this passes on current macOS (including likely `macos-latest`) — a macOS
  runner alone does not catch it.

### Correction: the `grep` → `ugrep` hazard

The original capture claimed the Claude Code harness's `grep` alias masks
GNU-only patterns in hooks. It does not: the alias is a shell function from the
Bash tool's shell snapshot (`~/.claude/shell-snapshots/`). Hooks run as
`bash script.sh` subprocesses and resolve `/usr/bin/grep` (`bash -c 'type
grep'` → `/usr/bin/grep`); pytest subprocesses likewise. The hazard is narrower:
a pattern **hand-tested through the Claude Bash tool** runs under `ugrep` and may
behave differently from the same pattern in a shipped hook. Treat that as a
documented authoring hazard, not a runtime masking bug.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- **Full audit of GNU-only / BSD-divergent forms** (searched all `*.sh` under `hooks/` and `scripts/little_loops/hooks/adapters/`, plus `loops/*.yaml` shell actions). Two unpaired divergences exist, not one:
  1. `hooks/scripts/record-hook-event.sh:43,49` — `date +%s%N` (already described above).
  2. `hooks/scripts/lib/common.sh:174` — `validate_json()`'s no-`jq` fallback runs `grep -qE '^\s*[{\[].*[}\]]\s*$'`. **Confirmed divergent on the current maintainer macOS**: `/usr/bin/grep` (`grep (BSD grep, GNU compatible) 2.6.0-FreeBSD`) returns no match for `'  {"a":1}  '`, while GNU grep matches. Unlike `%N`, this one *does* diverge on current Darwin, so a `macos-latest` runner can catch it — but only on the path where `jq` is absent (the function returns early via `jq empty` when `jq` is on PATH, and hosted runners ship `jq`).
- Paired (already portable) forms, all in `hooks/scripts/lib/common.sh`: `to_epoch()` (`date -j -f` at :101, `date -d` at :108) and `get_mtime()` (`stat -f %m` at :144, `stat -c %Y` at :151). A naive static gate that flags every `date -d` / `stat -c` line would false-positive on these; "paired with a BSD fallback" has to be expressible (suppression marker, or a same-function pairing rule).
- `mktemp -d -t <template> 2>/dev/null || mktemp -d` in `hooks/scripts/check-decisions-yaml.sh:58` and `hooks/scripts/check-private-refs.sh:61` is an explicit portable pair, not a divergence.
- `grep -oE` in `check-duplicate-issue-id.sh:64,72,78`, `check-duplicate-issue-id-post.sh:52,58`, `issue-completion-log.sh:75`, `issue-auto-commit.sh:53` uses only POSIX bracket classes — portable.
- No hits anywhere in scope for `grep -P`, `sed -i`, `readlink -f`, `realpath`, `sort -V`, `xargs -r`, `find -printf`, `timeout <cmd>`, `base64 -w`, `head -n -N`, `tac`, `seq`, `md5sum`/`sha256sum`, `awk gensub`.
- **`ll-verify-*` gates contain no shell to scan.** Every `subprocess` call under `scripts/little_loops/cli/` from a `verify_*.py` module invokes `git` plumbing (e.g. `verify_evidence.py` `git log --all --raw`, `git cat-file --batch`, `git ls-files -z`; `verify_private_refs.py` `git diff --cached -U0`, `git ls-files -z`); none shell out to `grep`/`date`/`sort`/`stat`, and there are no `shell=True` snippets. The Scope 3 "shell snippets in shipped `ll-verify-*` gates" clause therefore has an empty target set today.
- Shell files outside `hooks/scripts/` that ship or run: 11 `hooks/adapters/claude-code/*.sh`, the per-host adapters under `scripts/little_loops/hooks/adapters/{codex,gemini,kimi,qwen}/*.sh`, and `.github/scripts/ci-history.sh` (CI-only, runs on Linux Thinky). `scripts/little_loops/hooks/adapters/omp/node_modules/**` also contains a `.sh` — vendored third-party, must be excluded from any glob.
- Stale CI-policy text exists in two more places beyond `.claude/CLAUDE.md:142`: `AGENTS.md:142` (the Codex-flavored copy of CLAUDE.md, same "Do not add **paid/hosted** CI" line) and `CONTRIBUTING.md:426` ("there is no hosted/paid CI").

## Scope

1. Add a `macos-latest` job (GitHub-hosted, same trigger and posture as the
   existing `ubuntu-latest` unit-tests job: push to `main` + `workflow_dispatch`,
   no `pull_request`) running the same unit tier. GitHub-hosted runners are
   free for public repos, matching the existing `ubuntu-latest` job.
2. Update `.claude/CLAUDE.md` § Testing & CI Policy to match `ci.yml` (hosted
   `ubuntu-latest` + `macos-latest` unit jobs, self-hosted Thinky conformance
   only) and restate the rule as "no *paid* CI".
3. Add a deterministic static portability gate (pytest) that scans
   `hooks/scripts/**/*.sh` (and any shell snippets in shipped `ll-verify-*`
   gates) for GNU-only forms: `date +%N` / `%s%N`, `grep -P`, `\s`/`\b`/`\w`
   inside `grep -E` patterns, `sed -i` without a suffix argument,
   `readlink -f`, `stat -c` / `date -d` not paired with a BSD fallback, and
   `sort -V`. Allow a per-line suppression marker for justified uses.
4. Fix every divergence the audit/gate finds — starting with
   `record-hook-event.sh` `%N` (use a portable millisecond source, e.g. a
   `python3 -c` / `perl` fallback, or validate the `date` output is numeric
   before arithmetic).
5. Document the portability convention (point at `lib/common.sh` helpers) and
   the Bash-tool `ugrep` authoring hazard in `CONTRIBUTING.md`.

## Acceptance Criteria

- [ ] `ci.yml` runs the unit tier on both `ubuntu-latest` and `macos-latest`
      on push to `main`; neither job has a `pull_request` trigger.
- [ ] `.claude/CLAUDE.md` § Testing & CI Policy accurately describes the
      runner split, and the same stale "paid/hosted CI" wording is fixed in
      `AGENTS.md:142` and `CONTRIBUTING.md:426`.
- [ ] `lib/common.sh` `validate_json()`'s no-`jq` fallback matches padded
      JSON under BSD grep (replace `\s` with `[[:space:]]`); a test runs it
      with `jq` removed from PATH.
- [ ] A pytest portability gate fails on each GNU-only form listed in Scope 3
      (fixture per form) and passes on the current `hooks/scripts/` tree.
- [ ] `record-hook-event.sh` produces a numeric duration when `date +%s%N`
      prints a literal `N` (test simulates BSD `date` via a PATH shim).
- [ ] `CONTRIBUTING.md` documents the portable-pattern convention and the
      `ugrep` Bash-tool authoring hazard.

## Integration Map

- `.github/workflows/ci.yml` — new macOS job (or matrix over the unit-tests job).
- `.claude/CLAUDE.md` — Testing & CI Policy section.
- `hooks/scripts/record-hook-event.sh` — `%N` fix.
- `hooks/scripts/lib/common.sh` — reference implementation; possible home for
  a portable `now_ms` helper.
- `scripts/tests/` — new portability gate test; `record-hook-event.sh`
  PATH-shim test.
- `CONTRIBUTING.md` — convention docs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- `hooks/scripts/lib/common.sh:165` `validate_json()` — second divergence to fix (`\s` in `grep -E` at :174); in scope under Scope 4.
- `AGENTS.md:142` and `CONTRIBUTING.md:426` — carry the same stale "no hosted/paid CI" policy text as `.claude/CLAUDE.md:142`; AC 2's "accurately describes the runner split" is not true repo-wide unless these agree.
- `hooks/scripts/record-hook-event.sh` is invoked only from `hooks/hooks.json` `Stop` block (`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record-hook-event.sh Stop hooks/scripts/session-cleanup.sh`, timeout 5). `DURATION_MS` (:50) is passed as `--duration-ms` to `ll-session record-hook-event` (:52-58); the script always exits 0.
- `.github/workflows/ci.yml` constraints a macOS job must satisfy: `conformance` declares `needs: [unit-tests]` (:163) — turning `unit-tests` into a matrix makes conformance wait on *every* leg, and a separate macOS job is not waited on unless added to `needs`. The upload step names the artifact `pytest-unit-failures-${{ github.run_id }}-${{ github.run_attempt }}` (:138-153), which would collide across matrix legs without an OS discriminator. Unit-job setup that is Linux-agnostic but must keep working on macOS: `fetch-depth: 0` (BUG-3442), the `pytest-xdist<3.8` pin assertion (BUG-3208), `LL_REQUIRE_NODE: "1"` (BUG-3522 — macOS runner must also ship Node >= 22 or those gates fail), and the `$RUNNER_TEMP/host-stub/claude` PATH step.

### Conventions in Force

- Bash hook tests run the script as `subprocess.run(["bash", str(SCRIPT)], input=<json>, capture_output=True, text=True, cwd=..., timeout=N)` with a module-level `REPO_ROOT = Path(__file__).resolve().parents[2]` constant — evidence: `scripts/tests/test_record_hook_event_shim.py:28-43` (`_run_shim`), `scripts/tests/test_check_private_refs_hook.py:32-61`, `scripts/tests/test_check_decisions_yaml_hook.py:43-55`. `test_hooks_integration.py` differs (per-test path fixtures, `monkeypatch.chdir`).
- Fake binaries are written into `tmp_path`, chmod'd executable, and **prepended** to the real `PATH` (not replacing it) — evidence: `scripts/tests/test_hooks_integration.py:1682-1689`. No existing test fakes a coreutil such as `date`. Contrast: `test_record_hook_event_shim.py:94-107` simulates *absence* by shrinking PATH to `/usr/bin:/bin`.
- `scripts/tests/test_record_hook_event_shim.py` is the existing test home for `record-hook-event.sh`; it covers exit-0, row-write when analytics enabled, disabled/absent-config skips, and missing `ll-session` — it never asserts the recorded duration value. The row-write test is gated on `shutil.which("ll-session")` (:61-63).
- Static-scan gates carry a per-line suppression token checked on the same line and the preceding line, with each rule proven by an inline-string unit test and a parametrized repo-wide test that `pytest.fail`s with `path:line [rule] text` — evidence: `scripts/tests/test_docs_audience_gate.py` (`SUPPRESS_TOKEN = "ll-audience-ok:"` :39, `scan_audience()` :123, `TestScanAudience` :147, repo-wide tests :202/:214). No existing gate scans `*.sh`.
- Tool-availability skips use `shutil.which(...)` → `pytest.skip(...)` (module fixture or inline); a skip→fail escalation under CI is done via an env flag in a shared helper (`tests/helpers.py` `require_node()` + `LL_REQUIRE_NODE`, tested in `test_require_node_guard.py`). No hook test uses `sys.platform` skips.
- Marker split is contested: `test_hooks_integration.py:15` sets `pytestmark = pytest.mark.integration` (excluded from the CI unit tier), while `test_record_hook_event_shim.py`, `test_check_private_refs_hook.py`, `test_check_decisions_yaml_hook.py` are unmarked (run in the unit tier). A new hook/portability test only runs on the macOS CI job if it is **not** marked `integration`/`conformance`.

## Program Design

### Types
- N/A for Python data shapes beyond a rule record. If the portability gate models rules the way the audience gate does, the precedent is `AudienceMarker` (`scripts/tests/test_docs_audience_gate.py:43`: `name`, `pattern: re.Pattern`, `rationale`).

### Signatures
- Existing, reused as the portable-pattern reference: `to_epoch()` (`hooks/scripts/lib/common.sh:90`), `get_mtime()` (`hooks/scripts/lib/common.sh:134`) — BSD branch first, GNU branch second, `"0"` on both failing.
- Existing, to be fixed: `validate_json()` (`hooks/scripts/lib/common.sh:165`) — its no-`jq` fallback must accept leading/trailing whitespace on both BSD and GNU `grep` (POSIX `[[:space:]]` is the portable class).
- Existing test helper touching the `%N` fix: `_run_shim(cwd: Path, event_name: str = "Stop", stdin: str = "{}") -> subprocess.CompletedProcess` (`scripts/tests/test_record_hook_event_shim.py:33`). Asserting the duration needs a read of the value passed to `ll-session record-hook-event --duration-ms`; a fake `ll-session` on the prepended PATH shim dir is one way to observe it without depending on `shutil.which("ll-session")`.
- Precedent for the gate's scanner shape: `scan_audience(text: str, markers: tuple[AudienceMarker, ...] = AUDIENCE_MARKERS) -> list[tuple[int, str, str]]` (`scripts/tests/test_docs_audience_gate.py:123`).

- `scan_audience(text: str, markers: tuple[AudienceMarker, ...]) -> list[tuple[int, str, str]]` — scanner-shape precedent for the gate (same-line / preceding-line suppression)
- `record_hook_event(db_path: Path | str, *, event_name: str, duration_ms: int | None, ...) -> None` — terminal writer the shell duration lands in (`scripts/little_loops/session_store/writers.py`); reached through `main_session()` in `scripts/little_loops/cli/session.py`, whose `record-hook-event` branch passes `args.duration_ms` through

### Call Path
`hooks/hooks.json` Stop entry -> `hooks/scripts/record-hook-event.sh` (`date +%s%N` at :43/:49 -> `DURATION_MS` at :50 -> `ll-session record-hook-event --duration-ms`) -> `main_session` -> `record_hook_event`

### Decision Rules
- Gate scan set: every tracked `*.sh` under `hooks/` and `scripts/little_loops/hooks/adapters/`, excluding any path containing `node_modules/`. (`ll-verify-*` modules contain no shell to scan — see Current Behavior findings.)
- Flagged forms (literal): `%N` in a `date` format; `grep -P`; `\s`, `\b`, `\w` inside a `grep -E`/`egrep` pattern; `sed -i` not followed by a suffix argument; `readlink -f`; `sort -V`; `stat -c` and `date -d` **unless** the same line carries the suppression marker.
- Escape hatch: a per-line suppression token (name is the implementer's choice; `ll-audience-ok:` is the existing precedent) honored on the same line or the line immediately above. The GNU halves of the paired fallbacks in `lib/common.sh` (`date -d` at :108, `stat -c` at :151) are the known required suppressions if the `date -d`/`stat -c` rules are line-based.
- Pass condition: zero unsuppressed hits on the current tree after Scope 4 fixes; each rule has a positive fixture that fires.

## Status

**Open** | Created: 2026-09-23 | Priority: P1

## Session Log
- `/ll:confidence-check` - 2026-09-24T05:15:41 - `27ae30f6-009c-4b0e-9ac3-8684b7ff61cd.jsonl`
- `/ll:refine-issue` - 2026-09-24T05:03:01 - `ba06500e-9e68-4c34-9f78-d2557696e4a2.jsonl`
- Manual review - 2026-09-23 - corrected grep/ugrep premise, CI-policy drift, added `%N` divergence and static gate scope
