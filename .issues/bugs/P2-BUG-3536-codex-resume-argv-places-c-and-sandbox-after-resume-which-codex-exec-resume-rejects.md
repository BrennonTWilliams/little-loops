---
id: BUG-3536
type: BUG
title: Codex resume argv places -C and --sandbox after resume, which codex exec resume
  rejects
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:52:52Z'
labels:
- multi-host
- parallel
relates_to:
- BUG-3529
---

# BUG-3536: Codex resume argv places -C and --sandbox after resume, which codex exec resume rejects

## Summary

`CodexRunner.build_streaming(resume=True)` emits `codex exec resume --last <sandbox args> --json --skip-git-repo-check [-C dir] <prompt>`. The `codex exec resume` subcommand parser (codex-cli 0.152.1) does not accept `-C/--cd` or `--sandbox <mode>`; both are options of the parent `codex exec` and must appear before `resume`. Any resume with a `working_dir` fails at argument parsing, which today includes the ll-parallel context-handoff turn.

## Current Behavior

- `host_runner.py` `CodexRunner.build_streaming` appends `resume --last` immediately after `exec`, then `_sandbox_args(sandbox_mode)`, `--json`, `--skip-git-repo-check`, and `-C <working_dir>`.
- `codex exec resume --help` accepts `--last`, `-m/--model`, `--json`, `--skip-git-repo-check`, `--dangerously-bypass-approvals-and-sandbox`, `-c`, `-i`, `-o`, `--output-schema` and others, but not `-C/--cd` or `--sandbox`.
- **Live failure**: `parallel/worker_pool.py` sends the explicit handoff instruction via `_run_claude_command(..., working_dir, resume_session=True)`, which reaches `build_streaming(resume=True, working_dir=<worktree>)`. Under `LL_HOST_CLI=codex`, that invocation fails to parse, so the handoff turn never runs.
- **Latent failure**: no production caller passes `sandbox_mode` to `build_streaming` today, but it is public API; `resume=True` with any non-`off` sandbox mode fails.
- `issue_manager.py` resumes without `working_dir`, so it is unaffected today.
- The existing Codex resume test (`test_build_streaming_resume_restructures_subcommand`) checks `args[:3]` and never exercises a parser. Sandbox and directory tests cover fresh invocations separately, leaving their combination with resume untested.

## Expected Behavior

Parent-level `codex exec` options (`--sandbox <mode>`, `-C <dir>`) are placed between `exec` and `resume`; resume-accepted options (`--last`, `--json`, `--skip-git-repo-check`, `--dangerously-bypass-approvals-and-sandbox`, and `--model` once BUG-3529 lands) follow `resume`. Fresh (non-resume) argv is byte-identical to today.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: `CodexRunner.build_streaming`
- **Cause**: the builder enters the resume subparser before emitting options accepted only by the parent parser.

## Proposed Solution

On the resume path, assemble parent options before `resume --last`, then emit resume options and the prompt. Preserve `_sandbox_args` validation and selection: explicit modes emit `--sandbox <mode>` before `resume`; `None` and `"off"` emit the existing bypass flag after `resume`, with no `--sandbox`. Emit `-C` exactly once before `resume` when a directory is supplied. Preserve the fresh path and invocation environment.

Representative argv (each directory and prompt remains a single argument):

```text
exec --sandbox read-only -C DIR resume --last --json --skip-git-repo-check PROMPT
exec -C DIR resume --last --dangerously-bypass-approvals-and-sandbox --json --skip-git-repo-check PROMPT
```

Keep the implementation local to `CodexRunner.build_streaming`. Use unconditional parameterized argv assertions plus an installed-CLI parser smoke test. A hand-maintained option allowlist is not independent parser evidence; no general CLI grammar framework is needed.

BUG-3529 already declares `depends_on: [BUG-3536]`: implement this issue first. Model forwarding stays in BUG-3529, which must extend the parser cases with a supplied model when it implements forwarding. Place that future `--model` after `resume`, even when sandbox arguments now precede it.

## Integration Map

- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming` resume argv assembly; `_sandbox_args` (placement only, output unchanged).
- Callers: `parallel/worker_pool.py` (handoff resume with `working_dir`), `issue_manager.py`, `subprocess_utils.run_claude_command` (`resume_session` → `resume`).
- Tests: `scripts/tests/test_host_runner.py` (builder matrix and optional real parser checks), `scripts/tests/test_worker_pool.py` (handoff trigger), and `scripts/tests/test_subprocess_utils.py` (spawned argv, if using split integration coverage).
- Existing worker test `test_sentinel_triggers_explicit_handoff_instruction` mocks `_run_claude_command`, so it checks the resume trigger but cannot detect malformed argv. Add coverage below that boundary with the real Codex builder and mocked process launch. Alternatively, retain the worker trigger test and add a subprocess-boundary test for `resume_session=True` plus a worktree directory. Explicitly override the subprocess suite's autouse Claude runner fixture for Codex cases.
- Documentation/configuration: no public interface or configuration changes required.

## Program Design

### Types

- No new types; `HostInvocation` is unchanged.

### Signatures

- `CodexRunner.build_streaming(self, *, prompt: str, resume: bool = False, working_dir: Path | None = None, sandbox_mode: str | None = None, model: str | None = None) -> HostInvocation` — (other keyword parameters unchanged) emits parent options before `resume` on the resume path.

### Call Path

- `WorkerPool._run_claude_command` → `run_claude_command(resume_session=True)` → `CodexRunner.build_streaming(resume=True)` → `HostInvocation`

## Implementation Steps

1. Add failing resume cases covering directory/sandbox combinations and an optional real parser smoke test, retaining fresh invocation expectations.
2. Reorder resume argv assembly while preserving flag selection, prompt handling, and environment construction.
3. Verify the worker trigger and actual Codex argv at the subprocess boundary without launching a model session.
4. Run focused host-runner/worker/subprocess tests, then the required local suite (`python -m pytest scripts/tests/`).

## Impact

- **Priority**: P2 — breaks ll-parallel context handoff on Codex; latent for sandboxed resume.
- **Effort**: Small.
- **Risk**: Low — resume argv only; fresh argv unchanged.
- **Unblocks**: BUG-3529 (adds `--model` to the same argv; already depends on this issue).

## Steps to Reproduce

1. `python -c "from pathlib import Path; from little_loops.host_runner import CodexRunner; print(CodexRunner().build_streaming(prompt='p', resume=True, working_dir=Path('/tmp')).args)"` → `['exec', 'resume', '--last', '--dangerously-bypass-approvals-and-sandbox', '--json', '--skip-git-repo-check', '-C', '/tmp', 'p']`.
2. `codex exec resume --last --json --skip-git-repo-check -C /tmp p --help` → `error: unexpected argument '-C' found`.
3. `codex exec resume --last --sandbox read-only --json --skip-git-repo-check p --help` → `error: unexpected argument '--sandbox' found`.
4. Control: `codex exec --sandbox read-only -C /tmp resume --last --json --skip-git-repo-check -m x --help` parses.

Use trailing `--help` for parser probes so valid invocations exit without resuming a real session. These probes establish argument acceptance, not runtime sandbox enforcement or successful session selection.

## Acceptance Criteria

- [ ] Parameterize resume tests over `working_dir=None` and a path containing spaces, crossed with `sandbox_mode=None`, `"off"`, `"read-only"`, `"workspace-write"`, and `"danger-full-access"`. Explicit modes emit exactly one `--sandbox M` before `resume` and no bypass flag; `None`/`"off"` emit exactly one bypass flag after `resume` and no `--sandbox`. A supplied directory emits exactly one `-C D` before `resume`; an absent directory emits none.
- [ ] Resume retains exactly one `resume --last`, `--json`, and `--skip-git-repo-check`; the prompt is the final, unchanged single argument. Invalid sandbox values still raise `ValueError`. Existing worktree environment and persona behavior are preserved.
- [ ] Fresh (`resume=False`) argv is byte-identical to today for all existing test inputs.
- [ ] Parser coverage invokes the complete generated argv plus trailing `--help`, with captured output and a bounded timeout, using `HostInvocation.binary` and `.args`. Skip only external CLI cases when the binary is absent; unconditional builder assertions still run. Include negative controls for the original misplaced `-C` and `--sandbox` on the verified CLI grammar, demonstrating rejection as well as acceptance. Include the installed CLI version in failure diagnostics. Parser acceptance alone is not an end-to-end execution claim.
- [ ] Integration coverage links the worker handoff trigger to spawned Codex argv: `resume_session=True` and the worktree directory reach the real builder, and captured `Popen` arguments contain `-C <worktree>` before `resume`, with `cwd` still set to that directory. Do not mock the builder or stop at `_run_claude_command` when asserting argv; split worker/subprocess coverage as described above is sufficient.

## Verification Notes

Reviewed on `main` in the little-loops repository with a clean working tree before review and installed `codex-cli 0.152.1`. The code and worker/subprocess call chain confirm the defect. For all five sandbox settings with a directory containing spaces, generated argv plus trailing `--help` exits 2; moving only `--sandbox <mode>` (when present) and `-C <dir>` before `resume` exits 0 in all five cases. No model session was launched. Initial format/design checks pass; no blocking dependencies or active required decision rules were found. BUG-3529 is downstream, not a blocker.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-24T02:07:33 - `294f94b4-388d-48a0-aa53-cb5a7c8aa062.jsonl`
- `/ll:ready-issue` - 2026-09-24T02:01:51 - `7ee029e4-88ce-4fa6-8e18-bd8b5cfa3ced.jsonl`
