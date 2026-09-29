---
target: omp
date: '2026-09-25'
status: proven
assertions:
- claim: omp is not on the default shell PATH; it resolves only via ~/.bun/bin
  result: pass
- claim: the installed @oh-my-pi/pi-coding-agent (18.1.17) declares engines bun >=1.3.14
  result: pass
- claim: omp --version under the installed Bun 1.3.9 fails with a SyntaxError and exit 1
  result: pass
- claim: omp cannot be run under Node because cli.js imports the bun URL scheme
  result: pass
- claim: omp --version prints a version string and exits 0
  result: fail
raw_output_path: .ll/learning-tests/raw/omp.txt
---
