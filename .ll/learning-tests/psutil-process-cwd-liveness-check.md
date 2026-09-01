---
target: psutil process cwd liveness check
date: '2026-09-01'
status: proven
assertions:
- claim: psutil.Process(pid).cwd() returns a real filesystem path for a live process
    whose cwd was set via subprocess cwd=
  result: pass
- claim: on macOS, a worktree path under /tmp/... does not string-prefix-match cwd()'s
    return value unresolved, because cwd() resolves through the /tmp -> /private/tmp
    symlink; Path.resolve() on both sides is required
  result: pass
- claim: psutil.Process(pid).cwd() raises psutil.AccessDenied for at least some
    other-user/system processes (e.g. low-numbered system pids)
  result: pass
- claim: psutil.AccessDenied and psutil.NoSuchProcess are both subclasses of psutil.Error,
    distinguishable from a wholesale process_iter() failure
  result: pass
- claim: psutil.process_iter(['pid', 'cwd']) lets a single sweep collect cwd for
    all processes, with per-process AccessDenied surfaced as a catchable exception
    while iterating
  result: fail
- claim: Path(proc_cwd).resolve().is_relative_to(worktree_path.resolve()) correctly
    matches a live process whose actual on-disk cwd differs textually via symlink
    (/tmp vs /private/tmp on macOS)
  result: pass
raw_output_path: .ll/learning-tests/raw/psutil-process-cwd-liveness-check.txt
---
