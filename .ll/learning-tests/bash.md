---
target: bash
date: '2026-08-22'
status: proven
assertions:
- claim: bash -c script exit code is that of the last command executed, not the
    first failing one, when set -e is not used
  result: pass
- claim: bash -c with a nonexistent command exits 127, with stderr populated and
    stdout empty
  result: pass
- claim: a shell-level `exit N` (N=137) yields Popen.returncode == N (positive),
    distinct from a signal kill
  result: pass
- claim: a process killed via os.killpg(pgid, SIGKILL) reports Popen.returncode
    == -9 (negative signal number) to the Python parent
  result: pass
- claim: with start_new_session=True, killing the process group via os.killpg also
    terminates a background grandchild spawned inside the script (not just the top-level
    bash process)
  result: pass
- claim: referencing an unset variable (no set -u) expands to an empty string, prints
    without error, and exits 0
  result: pass
raw_output_path: .ll/learning-tests/raw/bash.txt
---
