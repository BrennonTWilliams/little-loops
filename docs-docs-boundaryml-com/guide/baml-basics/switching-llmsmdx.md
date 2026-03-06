---
url: https://docs.boundaryml.com/guide/baml-basics/switching-llms.mdx
scraped_at: 2026-03-06T01:00:23.435121
filepath: docs-docs-boundaryml-com/guide/baml-basics/switching-llmsmdx.md
---


***

title: Switching LLMs
slug: guide/baml-basics/switching-llms
--------------------------------------

BAML Supports getting structured output from **all** major providers as well as all OpenAI-API compatible open-source models. See [LLM Providers Reference](/ref/llm-client-providers/open-ai) for how to set each one up.BAML can help you get structured output from **any Open-Source model**, with better performance than other techniques, even when it's not officially supported via a Tool-Use API (like o1-preview) or fine-tuned for it! [Read more about how BAML does this](https://www.boundaryml.com/blog/schema-aligned-parsing).### Using `client "/"`

Using `openai/model-name` or `anthropic/model-name` will assume you have the ANTHROPIC\_API\_KEY or OPENAI\_API\_KEY environment variables set.

```rust BAML
function MakeHaiku(topic: string) -> string {
  client "openai-responses/gpt-5-mini" // or anthropic/claude-sonnet-4-20250514
  prompt #"
    Write a haiku about {{ topic }}.
  "#
}
```

### Using a named clientUse this if you are using open-source models or need customizationThe longer form uses a named client, and supports adding any parameters supported by the provider or changing the temperature, top\_p, etc.

```rust BAML
clientMyClient {
  provider "openai"
  options {
    model "gpt-5-mini"
    api_key env.OPENAI_API_KEY
    // other params like temperature, top_p, etc.
    temperature 0.0
    base_url "https://my-custom-endpoint.com/v1"
    // add headers
    headers {
      "anthropic-beta" "prompt-caching-2024-07-31"
    }
  }

}

function MakeHaiku(topic: string) -> string {
  client MyClient
  prompt #"
    Write a haiku about {{ topic }}.
  "#
}
```

Consult the [provider documentation](/ref/llm-client-providers/open-ai) for a list of supported providers
and models, the default options, and setting [retry policies](/ref/llm-client-strategies/retry-policy).If you want to specify which client to use at runtime, in your Python/TS/Ruby code,
  you can use the [client registry](/ref/baml_client/client-registry) to do so.

  This can come in handy if you're trying to, say, send 10% of your requests to a
  different model.
