---
url: https://docs.boundaryml.com/ref/editor-extension-settings/baml-generate-code-on-save.mdx
scraped_at: 2026-03-06T01:00:45.479413
filepath: docs-docs-boundaryml-com/ref/editor-extension-settings/baml-generate-code-on-savemdx.md
---


| Type                  | Default Value |
| --------------------- | ------------- |
| `"always" \| "never"` | "always"      |

* `always`: Generate code for `baml_client` on every save
* `never`: Do not generate `baml_client` on any save

If you have a generator of type `rest/*`, `"always"` will not do any code generation. You will have to manually run:

```
path/to/baml-cli generate
```

## Usage

```json settings.json
{
  "baml.generateCodeOnSave": "never",
}
```
