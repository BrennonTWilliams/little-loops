---
target: fcntl
date: '2026-07-07'
status: proven
assertions:
- claim: fcntl.flock(fd, fcntl.LOCK_EX) on an unlocked fd acquires an exclusive lock without raising
  result: pass
- claim: re-acquiring fcntl.flock(fd, fcntl.LOCK_EX) on the SAME fd (same open-file-description) from the same process is idempotent and returns silently
  result: pass
- claim: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB) on an fd held by another PROCESS raises BlockingIOError (subclass of OSError) with errno in {EAGAIN, EACCES}
  result: pass
- claim: after LOCK_UN on the holding fd, a competing process can acquire LOCK_EX on the same path without raising
  result: pass
- claim: 'flock is per-open-file-description: two SEPARATE open() calls of the same path within the SAME process each acquire LOCK_EX independently (no contention)'
  result: fail
- claim: flock is automatically released when the fd is closed (no need for explicit LOCK_UN before close())
  result: untested
raw_output_path: .ll/learning-tests/raw/fcntl.txt
---