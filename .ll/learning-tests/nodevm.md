---
target: node:vm
date: '2026-09-19'
status: proven
assertions:
- claim: vm.runInNewContext returns the value of the last evaluated expression
  result: pass
- claim: process and require are not defined inside a new context (a V8 built-in console still is)
  result: pass
- claim: sandbox properties are visible as globals, and assignments (including var and globalThis.x) write back to the sandbox object
  result: pass
- claim: arrays created inside a context are not instanceof the host Array but Array.isArray is true
  result: pass
- claim: the timeout option aborts an infinite loop with error code ERR_SCRIPT_EXECUTION_TIMEOUT
  result: pass
- claim: new vm.Script throws SyntaxError at construction, not at run time
  result: pass
- claim: one vm.Script can be run in several contexts with per-context isolated state
  result: pass
- claim: node:vm is not a security boundary (this.constructor.constructor reaches the host process)
  result: pass
raw_output_path: .ll/learning-tests/raw/nodevm.txt
---
