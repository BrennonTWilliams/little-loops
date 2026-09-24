---
id: ENH-3539
title: Run the deterministic test layer on both macOS and Linux
type: ENH
priority: P1
status: done
discovered_date: '2026-09-23'
labels: []
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
completed_at: '2026-09-24T18:07:09Z'
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
  runner alone does not catch it. Where it does fire, the failure is fatal, not
  cosmetic: under `/bin/bash` 3.2, `$((1727000000N / 1000000))` raises "value
  too great for base" and the script **exits 1** without running later lines,
  so the Stop hook errors every session. That breaks the script's own "never
  fails the calling hook" contract.

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

### Review Corrections (2026-09-24)

_Manual review after refine; supersedes the conflicting claims above._

- **Loop YAML shell actions do have divergences.** The refine note that nothing turned up in `loops/*.yaml` was wrong. The shipped loops live under `scripts/little_loops/loops/` (there is no top-level `loops/`), and they run on users' machines on both OSes:
  - `scripts/little_loops/loops/cli-anything-bootstrap.yaml:214` runs `sed -i '' '/^```/d' "$RUBRIC"`. That is the **BSD-only** form. GNU `sed` reads `''` as the script and `/^```/d` as a filename, so the step fails on Linux. **This is a live Linux bug.**
  - `scripts/little_loops/loops/oracles/plan-node-refine.yaml:346` uses `sort -V`. That is **not** a divergence: macOS `/usr/bin/sort` (`2.3-Apple`) supports `-V` (verified: `printf 'a10\na2\n' | sort -V` sorts `a2` first). `sort -V` is dropped from the flagged forms.
  - `cua-agent-desktop.yaml:1017` and `oracles/generator-evaluator.yaml:118,125` use a same-line `stat -f %m ... || stat -c %Y ...` pair. That form is portable, and the gate has to accept it.
  - `harness-multi-item.yaml:42`, `mechanize-skills.yaml:662`, and `prompt-across-issues.yaml:138-139` mention `sed -i` only inside `#` comments. The gate must skip comment lines.
- **The `sed -i` rule was backwards.** "`sed -i` without a suffix argument" would let `sed -i ''` through, and that is exactly the BSD-only form. Only an **attached** suffix (`sed -i.bak`) works under both BSD and GNU. Bare `sed -i` is GNU-only, and `sed -i ''` / `sed -i ""` are BSD-only.
- **macOS ships `jq` in `/usr/bin`.** `/usr/bin/jq` exists on the maintainer's Darwin 25, and `validate_json()` gates on `command -v jq` (`lib/common.sh:168`). Shrinking PATH to `/usr/bin:/bin` (the `test_record_hook_event_shim.py:94-107` precedent) does **not** remove `jq` on macOS. The no-`jq` test needs a shim dir that holds only symlinks to the binaries the function uses.
- **The bash version differs across platforms.** macOS `/bin/bash` is 3.2.57, which is what many users' hooks resolve to via `bash ${CLAUDE_PLUGIN_ROOT}/...`. GitHub's macOS runner images are believed to put Homebrew bash 5 first on PATH (verify from the userland step below). If they do, the macOS leg would not catch bash-4-only syntax. No bash-4-only syntax exists today in `hooks/` or `scripts/little_loops/hooks/adapters/` (`declare -A`, `mapfile`, `readarray`, `${x,,}`, `${x^^}`, `&>>`, `|&`, `coproc`, `local -n`: zero hits), so a static rule for it costs nothing.
- **Node version on the runners is unconfirmed.** The unit job sets `LL_REQUIRE_NODE: "1"` on the basis that the Ubuntu runner ships Node >= 22. The macOS image has not been checked. `ci.yml` has no `actions/setup-node` step, so the Node version drifts with the runner image.

### Review Corrections — second pass (2026-09-24)

_Supersedes conflicting claims above._

- **`validate_json()` is dead code.** It has zero callers in `hooks/`, `scripts/little_loops/hooks/adapters/`, or the shipped loops. The `test_validate_json_*` tests in `test_cli_deps.py` / `test_dependency_mapper.py` / `test_cli_loop_dispatch.py` cover the unrelated Python `validate --json` CLI. Delete the function instead of fixing it. That also removes the no-`jq` shim-PATH test and the macOS `/usr/bin/jq` concern.
- **`record-hook-event.sh` does not always exit 0.** The `%N` arithmetic error aborts the script with exit 1 (verified under `/bin/bash` 3.2.57). See Current Behavior.
- **No `python3` fallback in hooks.** On macOS, `/usr/bin/python3` is the xcode-select stub. Without the command-line tools it opens a GUI install dialog, here inside a Stop hook with a 5s timeout. Use a pure-shell `now_ms` helper instead (see Scope 4). The measured span only covers the stdin read and one `jq` call, so a seconds-resolution last resort is acceptable.
- **bash 3.2 is not exercised by either leg.** On the maintainer machine `command -v bash` is `/opt/homebrew/bin/bash` (bash 5), and hook tests invoke bare `bash`. The macOS runner image likely does the same. `/bin/bash` 3.2, which many users' hooks resolve to, is only covered statically unless tests call it explicitly.
- **BSD grep answers `--version`.** It prints `grep (BSD grep, GNU compatible) 2.6.0-FreeBSD` and exits 0, so a userland check of the form "`grep --version` succeeds ⇒ GNU" would fail every macOS run.
- **Gate prototype confirms the Decision Rules.** A regex prototype of the rules over the 180-file scan set produced exactly six hits, with no false positives in loop-YAML text: `lib/common.sh:108` and `:151` (need suppression markers), `lib/common.sh:174` (goes away with the deletion above), `record-hook-event.sh:43,49`, and `cli-anything-bootstrap.yaml:214`.
- **Out of scope:** `scripts/verify_learning_citations.sh` (tracked, dev-only, not shipped), `.github/scripts/ci-history.sh` (runs only on Linux Thinky), and `scripts/tests/fixtures/**/*.sh`.

## Expected Behavior

- Every push to `main` runs the unit tier on both `ubuntu-latest` (GNU) and `macos-latest` (BSD) with independent pass/fail signals; the macOS leg is proven to use BSD `date`/`grep`/`sed`.
- A static portability gate, part of the unit tier, fails on GNU-only, BSD-only, and bash-4-only forms in shipped shell and loop-YAML shell actions, so the divergence class is caught on any runner.
- `record-hook-event.sh` never fails its calling hook regardless of `date` flavor or bash version (3.2 and 5), and `cli-anything-bootstrap.yaml` works on Linux.
- `.claude/CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `ci.yml` agree on the runner split and "no *paid* CI" policy.

## Scope

1. Add a `macos-latest` job (GitHub-hosted, same trigger and posture as the
   existing `ubuntu-latest` unit-tests job: push to `main` + `workflow_dispatch`,
   no `pull_request`) running the same unit tier. GitHub-hosted runners are
   free for public repos, matching the existing `ubuntu-latest` job.
   **Shape (decided):** convert `unit-tests` to a matrix over
   `os: [ubuntu-latest, macos-latest]` with `fail-fast: false`, so one OS
   failing does not cancel the other leg's signal. Rename the upload artifact to
   `pytest-unit-failures-${{ matrix.os }}-${{ github.run_id }}-${{ github.run_attempt }}`
   so the legs do not collide. `conformance` keeps `needs: [unit-tests]`,
   which waits on both legs. That is intended: conformance runs only
   after the deterministic tier is green on both OSes. Add
   `actions/setup-node@v4` with `node-version: '22'` on both legs so
   `LL_REQUIRE_NODE=1` does not depend on runner-image drift. Add a
   "Report userland" step that prints `bash --version`, `/bin/bash --version`,
   `command -v bash date grep sed`, and `date --version 2>&1 || echo BSD date`.
   On the macOS leg, fail if `date`, `grep`, or `sed` resolve to GNU, detected as:
   `date --version` must fail, `sed --version` must fail, and
   `grep --version | grep -q BSD` must pass. (BSD grep answers `--version`, so
   a bare exit-code check is wrong.) A macOS leg running GNU tools off Homebrew
   would be pointless. Rename the job to `Unit tests (${{ matrix.os }})`, and
   update the `ci.yml` header comment (lines 6 and 11–17 describe
   `unit-tests -> ubuntu-latest`).
   **Rollout:** before merging to `main`, validate the matrix from the feature
   branch with `gh workflow run ci.yml --ref <branch>` (`workflow_dispatch`
   already exists on `main`). A red macOS leg on `main` blocks conformance. Treat
   that first run as a runtime measurement against the inherited
   `timeout-minutes: 120`. The hosted macOS runner has 3 vCPUs, and the suite
   has a history of macOS file-churn slowdowns.
2. Update `.claude/CLAUDE.md` § Testing & CI Policy to match `ci.yml` (hosted
   `ubuntu-latest` + `macos-latest` unit jobs, self-hosted Thinky conformance
   only) and restate the rule as "no *paid* CI". Also update its artifact
   paragraph: unit artifacts are now `pytest-unit-failures-<os>-<run_id>-<run_attempt>`.
3. Add a deterministic static portability gate (pytest). It scans every
   tracked `*.sh` under `hooks/` and `scripts/little_loops/hooks/adapters/`,
   plus the shipped loop YAMLs under `scripts/little_loops/loops/**/*.yaml`
   (line-based; `#` comment lines are skipped). It flags GNU-only forms:
   `date +%N` / `%s%N`, `grep -P`, `\s`/`\b`/`\w` inside `grep -E` patterns,
   bare `sed -i`, `readlink -f`, and `stat -c` / `date -d` not paired with a
   BSD fallback. It also flags the BSD-only form `sed -i ''` / `sed -i ""`,
   and bash-4-only syntax (`declare -A`, `mapfile`/`readarray`, `${x,,}`,
   `${x^^}`, `&>>`, `|&`, `coproc`, `local -n`). `sort -V` is **not** flagged
   because macOS sort supports it. Allow a per-line suppression marker for
   justified uses.
4. Fix every divergence the audit/gate finds:
   - `record-hook-event.sh` `%N`: add a `now_ms` helper to `lib/common.sh`
     (already sourced by the script) and use it for `START_MS`/`END_MS`. Try in
     order: `$EPOCHREALTIME` (bash 5; strip the `.` and truncate to ms), then
     `date +%s%N` **only if** the output is all digits, then `$(date +%s)000`.
     Do **not** fall back to `python3` (the macOS xcode-select stub opens a GUI
     dialog when the command-line tools are missing). `perl` is unnecessary.
   - `lib/common.sh` `validate_json()`: **delete it** (zero callers). This
     removes the `:174` `\s` hit.
   - `scripts/little_loops/loops/cli-anything-bootstrap.yaml:214`: replace
     `sed -i '' '/^```/d' "$RUBRIC"` with a portable form (a `grep -v` into a
     temp file plus `mv`, or `sed -i.bak ... && rm -f "$RUBRIC.bak"`).
5. Document the portability convention (point at `lib/common.sh` helpers,
   including `now_ms`) and the Bash-tool `ugrep` authoring hazard in
   `CONTRIBUTING.md`. State that bash-3.2 compatibility is enforced statically
   (Scope 3 bash-4 rules) plus the explicit `/bin/bash` runs in Scope 6. The
   hook suite as a whole runs under whichever `bash` is first on PATH.
6. **bash 3.2 behavioral coverage (decided: targeted, not suite-wide).** The new
   `record-hook-event.sh` tests are parametrized over the distinct available
   interpreters: `bash` on PATH, plus `/bin/bash` on darwin when it exists and
   resolves to a different binary. The macOS leg therefore runs them under
   3.2 as well as Homebrew bash 5. Retrofitting every existing hook test is out
   of scope.

## Acceptance Criteria

- [ ] `ci.yml` runs the unit tier on both `ubuntu-latest` and `macos-latest`
      on push to `main`; neither job has a `pull_request` trigger.
- [ ] The matrix uses `fail-fast: false`. Artifact names include `matrix.os`.
      The job name is `Unit tests (${{ matrix.os }})`. Both legs pin Node 22
      via `actions/setup-node`. The macOS leg has a userland step that fails
      unless `date --version` fails, `sed --version` fails, and
      `grep --version` output contains `BSD`.
- [ ] A `workflow_dispatch` run of the matrix from the feature branch is green
      on both legs before merging to `main`. Record its macOS leg duration in
      the Resolution.
- [ ] `.claude/CLAUDE.md` § Testing & CI Policy accurately describes the
      runner split and the per-OS artifact names. The same stale
      "paid/hosted CI" wording is fixed in `AGENTS.md:142` and
      `CONTRIBUTING.md:426`, and the `ci.yml` header comment no longer says
      unit tests run only on `ubuntu-latest`.
- [ ] `validate_json()` is removed from `lib/common.sh`, and nothing
      references it.
- [ ] A pytest portability gate fails on each form listed in Scope 3 (one
      fixture per form, including `sed -i ''` and a bash-4 construct). It
      passes on same-line `stat -f ... || stat -c ...` pairs and on `#`
      comment lines. It passes on the current tree, including
      `scripts/little_loops/loops/`, after the Scope 4 fixes.
- [ ] `cli-anything-bootstrap.yaml:214` no longer uses `sed -i ''`.
- [ ] With a prepended PATH shim `date` that prints a literal `N` for
      `+%s%N`, `record-hook-event.sh` exits 0 with empty stderr and passes an
      all-digit `--duration-ms` to a fake `ll-session` on the same shim dir.
      The test runs under each distinct available bash (PATH `bash`, plus
      `/bin/bash` on darwin), is not marked `integration`, and runs in the
      unit tier on both legs.
- [ ] Hooks do not invoke `python3` for timing. `now_ms` is pure shell
      (`$EPOCHREALTIME` → digit-checked `date +%s%N` → `$(date +%s)000`).
- [ ] `CONTRIBUTING.md` documents the portable-pattern convention and the
      `ugrep` Bash-tool authoring hazard.

## Integration Map

- `.github/workflows/ci.yml` — matrix the `unit-tests` job over OS
  (`fail-fast: false`, `matrix.os` in the artifact name and job name,
  `setup-node` 22, macOS userland assertion step); rewrite the header comment
  (lines 6, 11–17).
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:214` — `sed -i ''` fix.
- `AGENTS.md:142`, `CONTRIBUTING.md:426` — stale CI-policy text.
- `.claude/CLAUDE.md` — Testing & CI Policy section, including the artifact
  naming paragraph.
- `hooks/scripts/record-hook-event.sh` — use `now_ms` for `START_MS`/`END_MS`.
- `hooks/scripts/lib/common.sh` — add `now_ms`; delete dead `validate_json()`.
- `scripts/tests/` — new portability gate test; `record-hook-event.sh`
  PATH-shim test (extend `test_record_hook_event_shim.py`), parametrized over
  available bash interpreters.
- `CONTRIBUTING.md` — convention docs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- `hooks/scripts/lib/common.sh:165` `validate_json()` — second divergence (`\s` in `grep -E` at :174). _Superseded (second-pass review): the function has zero callers and is deleted instead of fixed._
- `AGENTS.md:142` and `CONTRIBUTING.md:426` — carry the same stale "no hosted/paid CI" policy text as `.claude/CLAUDE.md:142`; AC 2's "accurately describes the runner split" is not true repo-wide unless these agree.
- `hooks/scripts/record-hook-event.sh` is invoked only from `hooks/hooks.json` `Stop` block (`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record-hook-event.sh Stop hooks/scripts/session-cleanup.sh`, timeout 5). `DURATION_MS` (:50) is passed as `--duration-ms` to `ll-session record-hook-event` (:52-58). The script is designed to always exit 0, but the `%N` arithmetic error makes it exit 1 where `date` lacks `%N` (see Current Behavior).
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
- Existing, to be deleted: `validate_json()` — dead code at `hooks/scripts/lib/common.sh:165` (zero callers); deleting it removes the `\s`-in-`grep -E` hit at :174.
- New: `now_ms()` — prints current epoch milliseconds as an integer on stdout, pure shell, lives in `hooks/scripts/lib/common.sh`; order `$EPOCHREALTIME` → `date +%s%N` if all digits → `$(date +%s)000`; never spawns `python3`.
- Existing test helper touching the `%N` fix: `_run_shim(cwd: Path, event_name: str = "Stop", stdin: str = "{}") -> subprocess.CompletedProcess` (`scripts/tests/test_record_hook_event_shim.py:33`). Asserting the duration needs a read of the value passed to `ll-session record-hook-event --duration-ms`; a fake `ll-session` on the prepended PATH shim dir is one way to observe it without depending on `shutil.which("ll-session")`.
- Precedent for the gate's scanner shape: `scan_audience(text: str, markers: tuple[AudienceMarker, ...] = AUDIENCE_MARKERS) -> list[tuple[int, str, str]]` (`scripts/tests/test_docs_audience_gate.py:123`).

- `scan_audience(text: str, markers: tuple[AudienceMarker, ...]) -> list[tuple[int, str, str]]` — scanner-shape precedent for the gate (same-line / preceding-line suppression)
- `record_hook_event(db_path: Path | str, *, event_name: str, duration_ms: int | None, ...) -> None` — terminal writer the shell duration lands in (`scripts/little_loops/session_store/writers.py`); reached through `main_session()` in `scripts/little_loops/cli/session.py`, whose `record-hook-event` branch passes `args.duration_ms` through

### Call Path
`hooks/hooks.json` Stop entry -> `hooks/scripts/record-hook-event.sh` (`date +%s%N` at :43/:49, replaced by `now_ms` -> `DURATION_MS` at :50 -> `ll-session record-hook-event --duration-ms`) -> `main_session` -> `record_hook_event`

### Decision Rules
- Gate scan set: every tracked `*.sh` under `hooks/` and `scripts/little_loops/hooks/adapters/`, plus every tracked `scripts/little_loops/loops/**/*.yaml`, excluding any path containing `node_modules/` (180 files today). Explicitly out of scope: `scripts/verify_learning_citations.sh`, `.github/scripts/ci-history.sh`, `scripts/tests/fixtures/**`. Lines whose stripped form starts with `#` are skipped. (`ll-verify-*` modules contain no shell to scan — see Current Behavior findings.)
- Flagged forms (literal):
  - `%N` in a `date` format
  - `grep -P`
  - `\s`, `\b`, `\w` inside a `grep -E`/`egrep` pattern
  - `sed -i` **not** immediately followed by an attached suffix (`sed -i.ext`); this covers both bare `sed -i` (GNU-only) and `sed -i ''`/`sed -i ""` (BSD-only)
  - `readlink -f`
  - bash-4-only syntax: `declare -A`, `mapfile`, `readarray`, `${var,,}`, `${var^^}`, `&>>`, `|&`, `coproc`, `local -n`
  - `stat -c` and `date -d`, **unless** the same line also contains the BSD counterpart (`stat -f` / `date -j`) or the suppression marker
- Not flagged: `sort -V` (macOS sort supports it).
- Escape hatch: a per-line suppression token (name is the implementer's choice; `ll-audience-ok:` is the existing precedent) honored on the same line or the line immediately above. The GNU halves of the multi-line paired fallbacks in `lib/common.sh` (`date -d` at :108, `stat -c` at :151) are the known required suppressions. The same-line `stat -f ... || stat -c ...` pairs in `cua-agent-desktop.yaml:1017` and `oracles/generator-evaluator.yaml:118,125` pass via the same-line pairing rule.
- Pass condition: zero unsuppressed hits on the current tree after Scope 4 fixes; each rule has a positive fixture that fires.

## Impact

- **Priority**: P1 — fixes a live Linux break (`sed -i ''` in a shipped loop) and a Stop-hook failure on bash 3.2/older BSD `date`, and closes the manual-only macOS coverage gap.
- **Effort**: Medium — CI matrix conversion, one new pytest gate, three small shell/YAML fixes, doc updates.
- **Risk**: Low–Medium — a red macOS leg on `main` blocks `conformance` (mitigated by validating via `workflow_dispatch` from the branch first); macOS runtime may stress `timeout-minutes: 120`.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: `unit-tests` OS matrix in `ci.yml`, static portability gate, `now_ms` helper and `record-hook-event.sh` fix, `validate_json()` deletion, `cli-anything-bootstrap.yaml:214` fix, CI-policy and portability docs, targeted `/bin/bash` 3.2 coverage for the new `record-hook-event.sh` tests.
- **Out of scope**: `pull_request` triggers or any paid CI; retrofitting every existing hook test to run under `/bin/bash` 3.2; `scripts/verify_learning_citations.sh`, `.github/scripts/ci-history.sh`, `scripts/tests/fixtures/**`; model/prompt-layer multi-host divergence and host artifact parity; `python3`/`perl` timing fallbacks.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-24 (graph: provider=`codegraph`, freshness=`fresh`; not needed for any verdict)._

Verdict: **VALID** — no corrections needed.

- Confirmed: `record-hook-event.sh:43,49` `date +%s%N`; `lib/common.sh` `to_epoch` (:90, `date -d` :108), `get_mtime` (:134, `stat -c` :151), `validate_json` (:165) with zero callers in `hooks/`, adapters, and shipped loops; `cli-anything-bootstrap.yaml:214` `sed -i ''`; `sed -i` in the other loop YAMLs appears only in `#` comments; no `readlink -f`/`mapfile`/`readarray`/`declare -A`/`grep -P` in scope.
- Confirmed: `ci.yml` has `unit-tests` on `ubuntu-latest` only, `conformance` `needs: [unit-tests]` (:163), artifact name without an OS discriminator (:148), `workflow_dispatch` (:47), no `pull_request`, no `setup-node`; stale "paid/hosted" text at `AGENTS.md:142`, `.claude/CLAUDE.md:142`, `CONTRIBUTING.md:426`.
- `ll-verify-evidence`: clean (0 findings). Proposal-vs-code check (B6): no unsound consequences found; every Integration Map point has a matching AC. Decisions check: no conflicts.

## Resolution

**Implemented 2026-09-24.** `ci.yml` `unit-tests` is now an OS matrix (`ubuntu-latest`, `macos-latest`, `fail-fast: false`, Node 22, userland report + macOS BSD assertion, per-OS artifact names). Added `scripts/tests/test_portability_gate.py` (static BSD/GNU/bash-4 gate, `ll-portability-ok:` suppression). Added pure-shell `now_ms` to `lib/common.sh` and used it in `record-hook-event.sh`; deleted dead `validate_json()`; fixed `sed -i ''` in `cli-anything-bootstrap.yaml`. Extended `test_record_hook_event_shim.py` with a literal-`N` `date` shim test parametrized over PATH bash and `/bin/bash` (3.2). Updated CLAUDE.md, AGENTS.md, CONTRIBUTING.md (policy + portability section).

**Not done locally:** the `workflow_dispatch` matrix run from a branch (AC 3) and macOS-leg duration measurement require GitHub; run `gh workflow run ci.yml --ref <branch>` before/after pushing. Full local suite: 25393 passed; 1 pre-existing unrelated failure (`test_no_new_unverifiable_evidence`, BUG-1688 quote).

## Status

**Open** | Created: 2026-09-23 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-09-24T18:07:08 - `bb1eb081-85cd-48d3-92d1-ffd7b53652ce.jsonl`
- `/ll:ready-issue` - 2026-09-24T17:59:35 - `4d79ad0e-1c9e-4936-b081-4554b45ec99a.jsonl`
- `/ll:confidence-check` - 2026-09-24T17:57:52 - `215cd4b7-a015-4e0f-8d0a-2c0f5092b353.jsonl`
- `/ll:verify-issues` - 2026-09-24T17:54:36 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
- `/ll:format-issue` - 2026-09-24T17:51:52 - `f302ede5-3bd4-4d4c-9d95-f837dfdf259d.jsonl`
- Manual review (second pass) - 2026-09-24 - `validate_json()` is dead code, so delete it (drops the jq-shim AC); `%N` makes the hook exit 1 under bash 3.2; no `python3` fallback (macOS xcode-select stub), use a pure-shell `now_ms`; bash 3.2 is untested by either leg, so targeted `/bin/bash` parametrization; BSD-grep-aware userland check; branch `workflow_dispatch` rollout; stale ci.yml header, job name, and CLAUDE.md artifact text; gate prototype confirmed 6 hits over 180 files
- `/ll:confidence-check` - 2026-09-24T17:39:27 - `facad079-34ac-4ff6-9162-d08bebc806a4.jsonl`
- `/ll:verify-issues` - 2026-09-24T17:33:31 - `96d01310-c604-4961-b5bd-6b1925aee00d.jsonl`
- Manual review - 2026-09-24 - found `sed -i ''` in the loop YAMLs (live Linux break); dropped `sort -V`; fixed the `sed -i` rule; added bash-4 rules, the macOS `/usr/bin/jq` shim requirement, and the matrix/Node/userland CI decisions
- `/ll:confidence-check` - 2026-09-24T05:15:41 - `27ae30f6-009c-4b0e-9ac3-8684b7ff61cd.jsonl`
- `/ll:refine-issue` - 2026-09-24T05:03:01 - `ba06500e-9e68-4c34-9f78-d2557696e4a2.jsonl`
- Manual review - 2026-09-23 - corrected grep/ugrep premise, CI-policy drift, added `%N` divergence and static gate scope
