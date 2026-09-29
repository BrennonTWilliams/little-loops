---
target: importlib.metadata
date: '2026-09-26'
status: proven
assertions:
- claim: version(<installed dist>) returns a str
  result: pass
- claim: version(<missing dist>) raises PackageNotFoundError
  result: pass
- claim: PackageNotFoundError subclasses ModuleNotFoundError
  result: pass
- claim: distribution name lookup is normalized (case-insensitive, '-' and '_' equivalent)
  result: pass
- claim: entry_points(group=...) returns an EntryPoints collection whose items expose .name, .value and .group
  result: pass
- claim: distribution(x).metadata["Name"] returns the distribution name and .version matches version(x)
  result: pass
- claim: packages_distributions() returns a dict mapping top-level import names to lists of distribution names
  result: pass
- claim: stdlib modules are not distributions (version("os") raises PackageNotFoundError)
  result: pass
raw_output_path: .ll/learning-tests/raw/importlibmetadata.txt
---
