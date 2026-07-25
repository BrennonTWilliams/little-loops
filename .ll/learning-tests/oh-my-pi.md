---
target: oh-my-pi
date: '2026-07-25'
status: proven
assertions:
- claim: omp binary is not present on PATH in this environment
  result: pass
- claim: bun install -g @oh-my-pi/pi-coding-agent successfully installs an omp binary
  result: pass
- claim: omp requires Bun >= 1.3.14 per upstream docs; this environment's Bun (1.3.9)
    is below that minimum
  result: pass
- claim: omp --version prints a version string and exits 0
  result: fail
- claim: omp -p "<prompt>" runs one-shot print mode and exits 0
  result: fail
- claim: omp --mode json emits a JSONL event stream
  result: untested
- claim: --continue/-c resumes the most recent session in the current working directory
  result: untested
- claim: --tools <comma-list> natively allowlists tools
  result: untested
raw_output_path: .ll/learning-tests/raw/oh-my-pi.txt
---
