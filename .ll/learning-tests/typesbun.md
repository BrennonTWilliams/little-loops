---
target: '@types/bun'
date: '2026-07-29'
status: proven
assertions:
- claim: 'installing @types/bun (not bun-types) and setting tsconfig "types": ["bun"]
    lets tsc resolve without a TS2688 "cannot find type definition" error'
  result: pass
- claim: '@types/bun is a thin DefinitelyTyped re-export whose index.d.ts is just
    `/// <reference types="bun-types" />`, and its package.json dependencies pulls
    in bun-types at the matching version — it does not replace bun-types, it wraps it'
  result: pass
- claim: '@types/bun declares no peerDependencies (empty {}), so no extra peer install
    step is needed beyond the package itself'
  result: pass
- claim: with @types/bun installed and tsconfig fixed, hooks/adapters/opencode/index.ts
    fails tsc --noEmit with real type errors (TS2339 Property 'cwd' does not exist
    on type 'PluginInput'), confirming the typecheck is not a no-op once the type
    package resolves
  result: pass
- claim: bun install resolves @types/bun to a pinned exact version (no caret/tilde
    needed) and reports a newer version available separately (1.3.14 vs the pinned
    1.3.9), consistent with the issue's exact-pin convention
  result: pass
raw_output_path: .ll/learning-tests/raw/typesbun.txt
---
