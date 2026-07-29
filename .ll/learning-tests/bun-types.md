---
target: bun-types
date: '2026-07-29'
status: proven
assertions:
- claim: index.d.ts does NOT reference test-globals.d.ts, so bun:test globals (test, describe, expect, ...) are unavailable without an explicit opt-in
  result: pass
- claim: adding /// <reference types="bun-types/test-globals" /> explicitly opts a file into the bun:test globals
  result: pass
- claim: the Bun namespace is available as a global (no import needed) via bun.ns.d.ts's `declare global { export import Bun = BunModule }`
  result: pass
- claim: bun-types declares @types/node as a regular dependency (not peer), so installing bun-types alone pulls in Node types
  result: pass
- claim: bun-types declares @types/react as a peerDependency (^19), making it optional and only relevant for JSX/React usage
  result: pass
- claim: overrides.d.ts's declare global {} block patches/conflicts with existing DOM/Node ambient globals rather than adding new symbols
  result: untested
raw_output_path: .ll/learning-tests/raw/bun-types.txt
---
