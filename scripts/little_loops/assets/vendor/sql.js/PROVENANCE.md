# Vendored: sql.js

This directory holds the only vendored third-party binary in little-loops. It is
inlined (base64) into every artifact produced by `ll-artifact dashboard`
(FEAT-3304), so it is a supply-chain surface, not an ordinary asset — hence this
file, which establishes the codebase's first vendored-binary provenance record
(D8).

## Version and source

| field | value |
| --- | --- |
| package | [`sql.js`](https://github.com/sql-js/sql.js) |
| version | **1.14.2** |
| upstream | `https://cdn.jsdelivr.net/npm/sql.js@1.14.2/dist/` |
| vendored | 2026-08-25 |

## Files

| file | bytes | SHA-256 |
| --- | --- | --- |
| `sql-wasm.wasm` | 658,410 | `38c14f6e379210bc942bdc4ebca44e7bfdb4318ecc1c72ca666a28fdce96670a` |
| `sql-wasm.js` | 46,535 | `f1c84000dbc856c9d87f4f3aabc4d3654bd436165db4be3da13751db3a9c20d7` |

`sql-wasm.js` is the universal (Node + browser) emscripten glue. It is proven to
initialize with an explicit `wasmBinary` and issue no `fetch()` at all, which is
what makes a `file://`-opened artifact work — see `.ll/learning-tests/sqljs.md`.
`dist/` also ships `sql-wasm-browser.{js,wasm}` (~20 KB smaller, Node `fs` shims
stripped); swapping to it is a provenance + `PACKAGE_DATA_ASSETS` edit, not a
design change.

**Repo-weight cost:** ~700 KB of binary enters git, the sdist, and every wheel.
This is a deliberate, one-time cost accepted so artifacts need no network.

**Embedded cost per artifact:** 877,880 B (base64 `.wasm`) + 46,535 B (glue,
verbatim text) = a fixed ~924 KB floor, counted against
`artifacts.export.max_artifact_bytes`.

## Licenses

`sql.js` is MIT-licensed. SQLite itself, which it compiles, is public domain
(https://sqlite.org/copyright.html) and imposes no license obligation.

```
The MIT License (MIT)

Copyright (c) 2017 Ophir LOJKINE

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Update procedure

To bump to `<version>`:

1. Download both files:
   ```bash
   cd scripts/little_loops/assets/vendor/sql.js
   curl -fsSLO "https://cdn.jsdelivr.net/npm/sql.js@<version>/dist/sql-wasm.wasm"
   curl -fsSLO "https://cdn.jsdelivr.net/npm/sql.js@<version>/dist/sql-wasm.js"
   ```
2. Recompute hashes and sizes: `shasum -a 256 sql-wasm.*` / `wc -c sql-wasm.*`.
3. Re-prove the `</script>` check (D23) — the glue is injected as text inside an
   inline `<script>` tag, and a literal `</script>` anywhere in the minified
   emscripten output truncates the script in the browser, a failure no Node test
   catches:
   ```bash
   grep -c '</script>' sql-wasm.js   # must print 0
   ```
   `test_feat3304_artifact_dashboard.py` asserts this too, so a bump that
   regresses it fails the suite. If a future version ever does contain the
   substring, the fallback is embedding the glue base64 like the wasm.
4. Update the version/hash/size tables above.
5. Confirm both files are still registered in `PACKAGE_DATA_ASSETS`
   (`scripts/little_loops/package_data.py`) — one tuple per file; the manifest
   has no directory-glob form.
6. Re-run `python -m pytest scripts/tests/test_feat3304_artifact_dashboard.py
   scripts/tests/test_package_data_manifest.py`.
