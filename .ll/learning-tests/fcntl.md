---
target: fcntl
date: '2026-08-08'
status: proven
assertions:
- claim: 'flock is per-open-file-description: two SEPARATE open() calls of the same path within the SAME process each acquire LOCK_EX independently (no contention)'
  result: fail
- claim: flock is automatically released when the fd is closed (no need for explicit LOCK_UN before close())
  result: pass
- claim: fcntl.fcntl(fd, fcntl.F_GETFL) returns an int bitmask whose low bits (masked by os.O_ACCMODE) match the file's access mode (os.O_RDONLY/O_WRONLY/O_RDWR)
  result: pass
- claim: setting O_NONBLOCK via fcntl.fcntl(fd, F_SETFL, flags | os.O_NONBLOCK) on a pipe's read end causes a read on an empty pipe to raise BlockingIOError instead of blocking
  result: pass
- claim: fcntl.flock(fd, LOCK_EX) without LOCK_NB, held by another process, blocks the caller until the holder releases it (rather than failing immediately)
  result: pass
- claim: a child process created via os.fork() shares the parent's open-file-description, so re-locking the SAME inherited fd with LOCK_EX|LOCK_NB succeeds as a no-op (not a contention failure)
  result: pass
raw_output_path: .ll/learning-tests/raw/fcntl.txt
---
