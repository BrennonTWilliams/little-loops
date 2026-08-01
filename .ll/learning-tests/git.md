---
target: git
date: '2026-08-01'
status: proven
assertions:
- claim: git status --porcelain=v1 emits two-character XY status codes followed by
    a space then the path, with no leading git status header
  result: pass
- claim: an untracked file shows status code ?? in porcelain output
  result: pass
- claim: git rev-parse --show-toplevel prints the absolute repo root with no trailing
    content besides a newline
  result: pass
- claim: git rev-parse --is-inside-work-tree prints true and exits 0 inside a repo
  result: pass
- claim: git worktree list --porcelain emits blank-line-separated stanzas, each starting
    with a worktree <path> line
  result: pass
- claim: running git status --porcelain=v1 inside a repo with no changes produces
    empty stdout and exit code 0
  result: pass
- claim: git diff --name-only lists modified-but-unstaged file paths, one per line,
    with no other decoration
  result: pass
raw_output_path: .ll/learning-tests/raw/git.txt
---
