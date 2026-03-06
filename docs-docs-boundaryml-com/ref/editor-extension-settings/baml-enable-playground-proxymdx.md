---
url: https://docs.boundaryml.com/ref/editor-extension-settings/baml-enable-playground-proxy.mdx
scraped_at: 2026-03-06T01:00:45.287236
filepath: docs-docs-boundaryml-com/ref/editor-extension-settings/baml-enable-playground-proxymdx.md
---


| Type              | Value |
| ----------------- | ----- |
| `boolean \| null` | true  |When running VSCode from a remote machine, you likely need to set this to `false`.Many LLM providers don't accept requests from the browser. This setting enables a proxy that runs in the background and forwards requests to the LLM provider.

## Usage

```json settings.json
{
  "baml.enablePlaygroundProxy": false
}
```
