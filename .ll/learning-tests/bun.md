---
target: bun
date: '2026-08-30'
status: proven
assertions:
- claim: bun --version prints a version string and exits 0
  result: pass
- claim: bun install with package.json + devDependencies installs deps and exits 0
  result: pass
- claim: Bun.spawn can spawn a subprocess, capture stdout via a Response wrapper,
    and .exited resolves to the process exit code
  result: pass
- claim: Bun.spawn can pipe data to a subprocess's stdin via .write and .end, and
    the subprocess reads it
  result: pass
- claim: Bun.which resolves an executable's absolute path on PATH or returns null
    if absent
  result: pass
- claim: bun x tsc --noEmit -p tsconfig.json runs a clean TypeScript typecheck via
    an installed devDependency
  result: pass
raw_output_path: .ll/learning-tests/raw/bun.txt
---
