---
target: importlib.resources
date: '2026-08-21'
status: proven
assertions:
- claim: files() returns a Traversable whose str() is a real filesystem path in an editable install
  result: pass
- claim: joinpath() chains without touching disk, no exception on a non-existent path
  result: pass
- claim: is_file() returns False (not an exception) for a joined path that doesn't exist
  result: pass
- claim: a path under little_loops/ that exists on disk is is_file() True and read_text() returns its contents
  result: pass
- claim: a path outside the package directory (repo-root skills/) is not reachable through files("little_loops")
  result: pass
- claim: files() in this editable install resolves to the actual scripts/little_loops source directory
  result: pass
raw_output_path: .ll/learning-tests/raw/importlibresources.txt
---
