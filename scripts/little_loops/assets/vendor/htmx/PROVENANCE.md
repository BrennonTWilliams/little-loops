# Vendored: htmx (htmax.js)

This directory holds the client half of ENH-3351's Level-3 SSE bridge
(`ll-loop run --serve`). `htmax.js` is inlined verbatim into the served
dashboard page's serve-only block, the same treatment `sql.js` already gets in
`ll-artifact dashboard` (FEAT-3304) — no build step, no network fetch from the
served page.

## Version and source

| field | value |
| --- | --- |
| package | [`htmx.org`](https://github.com/bigskysoftware/htmx) |
| version | **4.0.0** |
| upstream | `https://unpkg.com/htmx.org@4.0.0/dist/htmax.js` |
| vendored | 2026-08-28 |

## Files

| file | bytes | SHA-256 |
| --- | --- | --- |
| `htmax.js` | 209,139 | `7de7d3bd5882377164519af7170844b7375054c0f34f617faceca4f3a526f771` |

`htmax.js` is the npm package's `htmx.org@4.0.0` "htmx + extensions, one file"
bundle (`dist/htmax.js`, distinct from the smaller core-only `dist/htmx.js`) —
it ships `hx-sse` and the other first-party extensions this issue's morph-swap
live regions need in a single unminified, non-ESM script with no external
imports. Confirmed free of a literal `</script>` substring (see Update
procedure step 3), so it is safe to inject verbatim inside an inline
`<script>` tag.

**htmx 4.0 is one day old as of vendoring** (released 2026-08-28). Any 2.x
usage example is wrong for this bundle — the explicit `:inherited` attribute
model and the `htmx:before:request` → renamed event names both changed
between 2.x and 4.0. Do not copy 2.x snippets when touching the serve-only
template block; validate against this exact vendored file (see
`.ll/learning-tests/htmx.md`).

**Repo-weight cost:** ~209 KB of JS enters git, the sdist, and every wheel —
comparable to the `sql.js` glue file, well under the `sql-wasm.wasm` binary.

## License

`htmx.org` is BSD-0-Clause licensed (a public-domain-equivalent "zero clause"
BSD grant — no attribution or conditions required):

```
Copyright (c) 2020 Big Sky Software

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

## Update procedure

To bump to `<version>`:

1. Download the bundle:
   ```bash
   cd scripts/little_loops/assets/vendor/htmx
   curl -fsSLO "https://unpkg.com/htmx.org@<version>/dist/htmax.js"
   ```
2. Recompute hash and size: `shasum -a 256 htmax.js` / `wc -c htmax.js`.
3. Re-prove the `</script>` check — the bundle is injected as text inside an
   inline `<script>` tag, and a literal `</script>` anywhere in the file
   truncates the script in the browser:
   ```bash
   grep -c '</script>' htmax.js   # must print 0
   ```
4. Update the version/hash/size table above.
5. Confirm the file is still registered in `PACKAGE_DATA_ASSETS`
   (`scripts/little_loops/package_data.py`).
6. Re-run `python -m pytest scripts/tests/test_transport.py
   scripts/tests/test_package_data_manifest.py -k htmx`.
