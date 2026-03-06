---
url: https://docs.boundaryml.com/ref/llm-client-providers/groq.mdx
scraped_at: 2026-03-06T01:00:46.994203
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/groqmdx.md
---


***

## title: groq

[Groq](https://groq.com) supports the OpenAI client, allowing you to use the
[`openai-generic`](/docs/snippets/clients/providers/openai) provider with an
overridden `base_url`.

See [https://console.groq.com/docs/openai](https://console.groq.com/docs/openai) for more information.

```baml BAML
clientMyClient {
  provider openai-generic
  options {
    base_url "https://api.groq.com/openai/v1"
    api_key env.GROQ_API_KEY
    model "llama-3-groq-70b-tool-use"
  }
}
```
