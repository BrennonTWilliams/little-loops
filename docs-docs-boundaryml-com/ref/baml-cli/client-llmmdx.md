---
url: https://docs.boundaryml.com/ref/baml/client-llm.mdx
scraped_at: 2026-03-06T01:00:37.422478
filepath: docs-docs-boundaryml-com/ref/baml-cli/client-llmmdx.md
---


***

## title: LLM Clients (client\)

Clients are used to configure how LLMs are called, like so:

```rust BAML
function MakeHaiku(topic: string) -> string {
  client "openai/gpt-4o"
  prompt #"
    Write a haiku about {{ topic }}.
  "#
}
```

`/` shorthand for the Named Client version of `MyClient`:

```rust BAML
clientMyClient {
  provider "openai"
  options {
    model "gpt-5"
    // api_key defaults to env.OPENAI_API_KEY
  }
}

function MakeHaiku(topic: string) -> string {
  client MyClient
  prompt #"
    Write a haiku about {{ topic }}.
  "#
}
```

Consult the [provider documentation](#fields) for a list of supported providers
and models, and the default options.

If you want to override options like `api_key` to use a different environment
variable, or you want to point `base_url` to a different endpoint, you should use
the latter form.If you want to specify which client to use at runtime, in your Python/TS/Ruby code,
  you can use the [client registry](/ref/baml_client/client-registry) to do so.

  This can come in handy if you're trying to, say, send 10% of your requests to a
  different model.## FieldsThis configures which provider to use. The provider is responsible for handling the actual API calls to the LLM service. The provider is a required field.

  The configuration modifies the URL request BAML runtime makes.

  | Provider Name      | Docs                                                                    | Notes                                                                                                                                                                                                                                                                                                           |
  | ------------------ | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `anthropic`        | [Anthropic](/ref/llm-client-providers/anthropic)                        | Supports [/v1/messages](https://docs.anthropic.com/en/api/messages) endpoint                                                                                                                                                                                                                                    |
  | `aws-bedrock`      | [AWS Bedrock](/ref/llm-client-providers/aws-bedrock)                    | Supports [Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) and [ConverseStream](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) endpoint                                                                                           |
  | `google-ai`        | [Google AI](/ref/llm-client-providers/google-ai-gemini)                 | Supports Google AI's [generateContent](https://ai.google.dev/api/generate-content) and [streamGenerateContent](https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent) endpoints                                                                                                       |
  | `vertex-ai`        | [Vertex AI](/ref/llm-client-providers/google-vertex)                    | Supports Vertex's [generateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent) and [streamGenerateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/streamGenerateContent) endpoints |
  | `openai`           | [OpenAI](/ref/llm-client-providers/open-ai)                             | Supports [/chat/completions](https://platform.openai.com/docs/api-reference/chat) endpoint                                                                                                                                                                                                                      |
  | `openai-responses` | [OpenAI Responses API](/ref/llm-client-providers/open-ai-responses-api) | Supports OpenAI's most advanced [/responses](https://platform.openai.com/docs/api-reference/responses) endpoint                                                                                                                                                                                                 |
  | `azure-openai`     | [Azure OpenAI](/ref/llm-client-providers/open-ai-from-azure)            | Supports Azure's [/chat/completions](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions) endpoint                                                                                                                                                                            |
  | `openai-generic`   | [OpenAI (generic)](/ref/llm-client-providers/openai-generic)            | Any other provider that supports OpenAI's `/chat/completions` endpoint                                                                                                                                                                                                                                          |

  A non-exhaustive list of providers you can use with `openai-generic`:

  | Inference Provider | Docs                                                             |
  | ------------------ | ---------------------------------------------------------------- |
  | Azure AI Foundry   | [Azure AI Foundry](/ref/llm-client-providers/azure-ai-foundary)  |
  | Groq               | [Groq](/ref/llm-client-providers/groq)                           |
  | Hugging Face       | [Hugging Face](/ref/llm-client-providers/huggingface)            |
  | Keywords AI        | [Keywords AI](/ref/llm-client-providers/keywordsai)              |
  | Litellm            | [Litellm](/ref/llm-client-providers/litellm)                     |
  | LM Studio          | [LM Studio](/ref/llm-client-providers/lmstudio)                  |
  | Ollama             | [Ollama](/ref/llm-client-providers/ollama)                       |
  | OpenRouter         | [OpenRouter](/ref/llm-client-providers/openrouter)               |
  | Vercel AI Gateway  | [Vercel AI Gateway](/ref/llm-client-providers/vercel-ai-gateway) |
  | TogetherAI         | [TogetherAI](/ref/llm-client-providers/together)                 |
  | Unify AI           | [Unify AI](/ref/llm-client-providers/unify)                      |
  | vLLM               | [vLLM](/ref/llm-client-providers/vllm)                           |

  We also have some special providers that allow composing clients together:

  | Provider Name | Docs                                                  | Notes                                        |
  | ------------- | ----------------------------------------------------- | -------------------------------------------- |
  | `fallback`    | [Fallback](/ref/llm-client-strategies/fallback)       | Used to chain models conditional on failures |
  | `round-robin` | [Round Robin](/ref/llm-client-strategies/round-robin) | Used to load balance                         |These vary per provider. Please see provider specific documentation for more
  information. Generally they are pass through options to the POST request made
  to the LLM.The name of the retry policy. See [Retry
  Policy](/ref/llm-client-strategies/retry-policy).
