---
url: https://docs.boundaryml.com/ref/llm-client-providers/lmstudio.mdx
scraped_at: 2026-03-06T01:00:48.002934
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/lmstudiomdx.md
---


***

## title: LMStudio

[LMStudio](https://lmstudio.ai/docs) supports the OpenAI client, allowing you
to use the [`openai-generic`](/docs/snippets/clients/providers/openai) provider
with an overridden `base_url`.

See [https://lmstudio.ai/docs/developer/openai-compat/chat-completions](https://lmstudio.ai/docs/developer/openai-compat/chat-completions) for more information.

```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    base_url "http://localhost:1234/v1"
    model "TheBloke/phi-2-GGUF"
  }
}
```
