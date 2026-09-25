---
target: bash
date: '2026-09-25'
status: proven
assertions:
- claim: a command whose exit status is tested by an if condition does not trigger a set -e abort
  result: pass
- claim: without pipefail a pipeline's exit status is that of the last command only
  result: pass
- claim: with set -o pipefail a pipeline exits non-zero when any stage fails and reports the rightmost failing stage's status
  result: pass
- claim: local var=$(false) masks the failure (exit 0) while plain var=$(false) yields exit status 1
  result: pass
- claim: variable assignments inside a subshell are not visible in the parent shell
  result: pass
- claim: $$ reports the top-level shell PID inside a subshell while $BASHPID reports the subshell PID
  result: pass
- claim: an EXIT trap fires when set -e terminates the script early
  result: pass
raw_output_path: .ll/learning-tests/raw/bash.txt
---
