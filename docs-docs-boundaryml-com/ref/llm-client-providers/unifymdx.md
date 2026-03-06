---
url: https://docs.boundaryml.com/ref/llm-client-providers/unify.mdx
scraped_at: 2026-03-06T01:00:49.626101
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/unifymdx.md
---


***

## title: Unify AI

[Unify AI](https://www.unify.ai/) supports the OpenAI client, allowing you
to use the [`openai-generic`](/docs/snippets/clients/providers/openai) provider
with an overridden `base_url`.

See [https://docs.unify.ai/universal\_api/making\_queries#openai-python-package](https://docs.unify.ai/universal_api/making_queries#openai-python-package) for more information.

```baml BAML
clientUnifyClient {
    provider "openai-generic"
    options {
        base_url "https://api.unify.ai/v0"
        api_key env.MY_UNIFY_API_KEY
        model "llama-3.1-405b-chat@together-ai"
    }
}
```
