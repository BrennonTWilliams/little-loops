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
- The only existing test (`test_build_streaming_resume_restructures_subcommand`) checks `args[:3]` and never exercises a parser.

## Expected Behavior

Parent-level `codex exec` options (`--sandbox <mode>`, `-C <dir>`) are placed between `exec` and `resume`; resume-accepted options (`--last`, `--json`, `--skip-git-repo-check`, `--dangerously-bypass-approvals-and-sandbox`, and `--model` once BUG-3529 lands) follow `resume`. Fresh (non-resume) argv is byte-identical to today.

## Integration Map

- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming` resume argv assembly; `_sandbox_args` (placement only, output unchanged).
- Callers: `parallel/worker_pool.py` (handoff resume with `working_dir`), `issue_manager.py`, `subprocess_utils.run_claude_command` (`resume_session` → `resume`).
- Tests: `scripts/tests/test_host_runner.py` (Codex `build_streaming` resume tests).

## Program Design

### Types

- No new types; `HostInvocation` is unchanged.

### Signatures

- `CodexRunner.build_streaming(self, *, prompt: str, resume: bool = False, working_dir: Path | None = None, sandbox_mode: str | None = None, model: str | None = None) -> HostInvocation` — (other keyword parameters unchanged) emits parent options before `resume` on the resume path.

### Call Path

- `WorkerPool._run_claude_command` → `run_claude_command(resume_session=True)` → `CodexRunner.build_streaming(resume=True)` → `HostInvocation`

## Impact

- **Priority**: P2 — breaks ll-parallel context handoff on Codex; latent for sandboxed resume.
- **Effort**: Small.
- **Risk**: Low — resume argv only; fresh argv unchanged.
- **Related**: BUG-3529 (adds `--model` to the same argv; land together or coordinate placement).

## Steps to Reproduce

1. `python -c "from little_loops.host_runner import CodexRunner; print(CodexRunner().build_streaming(prompt='p', resume=True, working_dir='/tmp').args)"` → `['exec', 'resume', '--last', '--dangerously-bypass-approvals-and-sandbox', '--json', '--skip-git-repo-check', '-C', '/tmp', 'p']`.
2. `codex exec resume --last --json --skip-git-repo-check -C /tmp p` → `error: unexpected argument '-C' found`.
3. `codex exec resume --last --sandbox read-only --json --skip-git-repo-check p` → `error: unexpected argument '--sandbox' found`.
4. Control: `codex exec --sandbox read-only -C /tmp resume --last --json --skip-git-repo-check -m x --help` parses.

## Acceptance Criteria

- [ ] `build_streaming(resume=True, working_dir=D, sandbox_mode=M)` places `--sandbox M` and `-C D` before `resume`, for every valid `M` and for `M=None`/`"off"`.
- [ ] Fresh (`resume=False`) argv is byte-identical to today for all existing test inputs.
- [ ] Parser-level coverage: a test validates the complete resume argv against the `codex exec resume` option grammar — shelling out to `codex exec ... --help` when the binary is present (skip when absent), plus a pinned allowlist of resume-accepted options so the check runs without the binary.
- [ ] A worker-pool-level test (Codex host) shows the handoff resume invocation carries `-C <worktree>` before `resume`.

## Status

**Open** | Created: 2026-09-24 | Priority: P2
