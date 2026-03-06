---
url: https://docs.boundaryml.com/ref/llm-client-providers/llama-api.mdx
scraped_at: 2026-03-06T01:00:47.695905
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/llama-apimdx.md
---


***

## title: llama-api

[Llama API](https://llama.developer.meta.com/docs) supports the OpenAI client, allowing you to use the
[`openai-generic`](/docs/snippets/clients/providers/openai) provider with an
overridden `base_url`.Note that to call Llama, you must use its OpenAI-compatible
  `/compat/v1` endpoint. See [Llama's OpenAI compatibility
  documentation](https://llama.developer.meta.com/docs/features/compatibility).```baml
clientLlamaAPI {
  provider openai-generic
  retry_policy Exponential
  options {
    base_url "https://llama-api.meta.com/compat/v1"
    model "Llama-3.3-8B-Instruct"
    api_key env.LLAMA_API_KEY
    // see openai-generic docs for more options
  }
}
```
