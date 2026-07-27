---
target: codegraph
date: '2026-07-27'
status: proven
assertions:
- claim: the codegraph binary is resolvable via shutil.which("codegraph") on PATH
  result: pass
- claim: codegraph sync --quiet <path> exits 0 and produces no stdout when the index is already up to date
  result: pass
- claim: codegraph sync --quiet completes in well under a second on a clean tree (~906 files)
  result: pass
- claim: codegraph status -j <path> reports pendingChanges added/modified/removed as 0 after a successful sync on a clean tree
  result: pass
- claim: codegraph sync does not change fileCount/nodeCount/edgeCount when there are no pending changes
  result: pass
raw_output_path: .ll/learning-tests/raw/codegraph.txt
---
