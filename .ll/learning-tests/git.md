---
target: git
date: '2026-09-10'
status: proven
assertions:
- claim: git status --porcelain=v1 emits two-character XY status codes followed by a space then the path, with no leading git status header (X or Y may individually be a space)
  result: pass
- claim: an untracked file shows status code ?? in porcelain output
  result: pass
- claim: git rev-parse --show-toplevel prints the absolute repo root with no trailing content besides a newline
  result: pass
- claim: git worktree list --porcelain emits blank-line-separated stanzas, each starting with a worktree <path> line
  result: pass
- claim: git diff --quiet exits 1 when the worktree has unstaged changes and 0 when clean, printing nothing to stdout either way
  result: pass
- claim: git ls-files --others --exclude-standard lists untracked files but omits files matched by .gitignore
  result: pass
- claim: git symbolic-ref --short HEAD prints the branch name on a branch and exits nonzero (128) on detached HEAD
  result: pass
raw_output_path: .ll/learning-tests/raw/git.txt
---
