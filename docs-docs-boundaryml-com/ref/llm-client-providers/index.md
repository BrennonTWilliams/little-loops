---
url: https://docs.boundaryml.com/ref/llm-client-providers/
scraped_at: 2026-03-06T01:00:46.274347
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

Overviewbaml-cliinitgeneratetestservedevfmtLanguage ReferenceGeneral BAML SyntaxTypesfunctiontesttemplate_stringclient<llm>classenumgeneratorGenerated baml_clientwith_options(..)AbortSignal / CancellationCollectorlogging / env varsAsyncClient / SyncClientTypeBuilderClientRegistryclient OptionOnTickMultimodalImageAudioPdfVideoErrorsReact/Next.jsAttributesWhat are attributes?@alias / @@alias@description / @@description@skip@assert@checkJinja in Attributes@@dynamicLLM Client ProvidersOverviewAWS BedrockAnthropicGoogle AI: GeminiGoogle: VertexOpenAIOpenAI Responses APIOpenAI from AzureOpenRouteropenai-genericMicrosoft Foundry (openai-generic)Cerebras (openai-generic)Groq (openai-generic)Hugging Face (openai-generic)Keywords AI (openai-generic)Llama API (openai-generic)Litellm (openai-generic)LM Studio (openai-generic)Ollama (openai-generic)Vercel AI Gateway (openai-generic)Tinfoil (openai-generic)TogetherAI (openai-generic)Unify AI (openai-generic)vLLM (openai-generic)LLM Client StrategiesTimeout ConfigurationRetry PolicyFallbackRound RobinPrompt SyntaxWhat is jinja?Jinja Filtersctx.output_formatctx.client_.roleVariablesConditionalsLoopsEditor Extension Settingsbaml.cliPathbaml.generateCodeOnSavebaml.enablePlaygroundProxybaml.syncExtensionToGeneratorVersion


Overview

[Overview](/ref/overview)

initgeneratetestservedevfmt

[init](/ref/baml-cli/init)
[generate](/ref/baml-cli/generate)
[test](/ref/baml-cli/test)
[serve](/ref/baml-cli/serve)
[dev](/ref/baml-cli/dev)
[fmt](/ref/baml-cli/fmt)

General BAML SyntaxTypesfunctiontesttemplate_stringclient<llm>classenumgenerator

[Types](/ref/baml/types)
[function](/ref/baml/function)
[test](/ref/baml/test)
[template_string](/ref/baml/template-string)
[client<llm>](/ref/baml/client-llm)
[class](/ref/baml/class)
[enum](/ref/baml/enum)
[generator](/ref/baml/generator)

with_options(..)AbortSignal / CancellationCollectorlogging / env varsAsyncClient / SyncClientTypeBuilderClientRegistryclient OptionOnTickMultimodalImageAudioPdfVideoErrorsReact/Next.js

[with_options(..)](/ref/baml_client/with-options)
[AbortSignal / Cancellation](/ref/baml_client/abort-signal)
[Collector](/ref/baml_client/collector)
[logging / env vars](/ref/baml_client/config)
[AsyncClient / SyncClient](/ref/baml_client/client)
[TypeBuilder](/ref/baml_client/type-builder)
[ClientRegistry](/ref/baml_client/client-registry)
[client Option](/ref/baml_client/client-option)
[OnTick](/ref/baml_client/on-tick)
[Multimodal](/ref/baml_client/media)
[Image](/ref/baml_client/image)
[Audio](/ref/baml_client/audio)
[Pdf](/ref/baml_client/pdf)
[Video](/ref/baml_client/video)

What are attributes?@alias / @@alias@description / @@description@skip@assert@checkJinja in Attributes@@dynamic

[What are attributes?](/ref/attributes/what-are-attributes)
[@alias / @@alias](/ref/attributes/alias)
[@description / @@description](/ref/attributes/description)
[@skip](/ref/attributes/skip)
[@assert](/ref/attributes/assert)
[@check](/ref/attributes/check)
[Jinja in Attributes](/ref/attributes/jinja-in-attributes)
[@@dynamic](/ref/attributes/dynamic)

OverviewAWS BedrockAnthropicGoogle AI: GeminiGoogle: VertexOpenAIOpenAI Responses APIOpenAI from AzureOpenRouteropenai-genericMicrosoft Foundry (openai-generic)Cerebras (openai-generic)Groq (openai-generic)Hugging Face (openai-generic)Keywords AI (openai-generic)Llama API (openai-generic)Litellm (openai-generic)LM Studio (openai-generic)Ollama (openai-generic)Vercel AI Gateway (openai-generic)Tinfoil (openai-generic)TogetherAI (openai-generic)Unify AI (openai-generic)vLLM (openai-generic)

[Overview](/ref/llm-client-providers/overview)
[AWS Bedrock](/ref/llm-client-providers/aws-bedrock)
[Anthropic](/ref/llm-client-providers/anthropic)
[Google AI: Gemini](/ref/llm-client-providers/google-ai-gemini)
[Google: Vertex](/ref/llm-client-providers/google-vertex)
[OpenAI](/ref/llm-client-providers/open-ai)
[OpenAI Responses API](/ref/llm-client-providers/open-ai-responses-api)
[OpenAI from Azure](/ref/llm-client-providers/open-ai-from-azure)
[OpenRouter](/ref/llm-client-providers/openrouter)
[openai-generic](/ref/llm-client-providers/openai-generic)
[Microsoft Foundry (openai-generic)](/ref/llm-client-providers/microsoft-foundry)
[Cerebras (openai-generic)](/ref/llm-client-providers/cerebras)
[Groq (openai-generic)](/ref/llm-client-providers/groq)
[Hugging Face (openai-generic)](/ref/llm-client-providers/huggingface)
[Keywords AI (openai-generic)](/ref/llm-client-providers/keywordsai)
[Llama API (openai-generic)](/ref/llm-client-providers/llama-api)
[Litellm (openai-generic)](/ref/llm-client-providers/litellm)
[LM Studio (openai-generic)](/ref/llm-client-providers/lmstudio)
[Ollama (openai-generic)](/ref/llm-client-providers/ollama)
[Vercel AI Gateway (openai-generic)](/ref/llm-client-providers/vercel-ai-gateway)
[Tinfoil (openai-generic)](/ref/llm-client-providers/tinfoil)
[TogetherAI (openai-generic)](/ref/llm-client-providers/together)
[Unify AI (openai-generic)](/ref/llm-client-providers/unify)
[vLLM (openai-generic)](/ref/llm-client-providers/vllm)

Timeout ConfigurationRetry PolicyFallbackRound Robin

[Timeout Configuration](/ref/llm-client-strategies/timeouts)
[Retry Policy](/ref/llm-client-strategies/retry-policy)
[Fallback](/ref/llm-client-strategies/fallback)
[Round Robin](/ref/llm-client-strategies/round-robin)

What is jinja?Jinja Filtersctx.output_formatctx.client_.roleVariablesConditionalsLoops

[What is jinja?](/ref/prompt-syntax/what-is-jinja)
[Jinja Filters](/ref/prompt-syntax/jinja-filters)
[ctx.output_format](/ref/prompt-syntax/ctx-output-format)
[ctx.client](/ref/prompt-syntax/ctx-client)
[_.role](/ref/prompt-syntax/role)
[Variables](/ref/prompt-syntax/variables)
[Conditionals](/ref/prompt-syntax/conditionals)
[Loops](/ref/prompt-syntax/loops)

baml.cliPathbaml.generateCodeOnSavebaml.enablePlaygroundProxybaml.syncExtensionToGeneratorVersion

[baml.cliPath](/ref/editor-extension-settings/baml-cli-path)
[baml.generateCodeOnSave](/ref/editor-extension-settings/baml-generate-code-on-save)
[baml.enablePlaygroundProxy](/ref/editor-extension-settings/baml-enable-playground-proxy)
[baml.syncExtensionToGeneratorVersion](/ref/editor-extension-settings/baml-sync-extension-to-generator-version)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

Fields

[Fields](#fields)

Clients are used to configure how LLMs are called, like so:


```
1function MakeHaiku(topic: string) -> string {2client "openai/gpt-4o"3prompt #"4Write a haiku about {{ topic }}.5"#6}
```


<provider>/<model>shorthand for the Named Client version ofMyClient:

`<provider>/<model>`
`MyClient`

```
1client<llm> MyClient {2provider "openai"3options {4model "gpt-5"5// api_key defaults to env.OPENAI_API_KEY6}7}89function MakeHaiku(topic: string) -> string {10client MyClient11prompt #"12Write a haiku about {{ topic }}.13"#14}
```


Consult theprovider documentationfor a list of supported providers
and models, and the default options.

[provider documentation](/ref/llm-client-providers/overview#fields)

If you want to override options likeapi_keyto use a different environment
variable, or you want to pointbase_urlto a different endpoint, you should use
the latter form.

`api_key`
`base_url`

If you want to specify which client to use at runtime, in your Python/TS/Ruby code,
you can use theclient registryto do so.

[client registry](/ref/baml_client/client-registry)

This can come in handy if you’re trying to, say, send 10% of your requests to a
different model.


## Fields


This configures which provider to use. The provider is responsible for handling the actual API calls to the LLM service. The provider is a required field.


The configuration modifies the URL request BAML runtime makes.

`anthropic`
[Anthropic](/ref/llm-client-providers/anthropic)
[/v1/messages](https://docs.anthropic.com/en/api/messages)
`aws-bedrock`
[AWS Bedrock](/ref/llm-client-providers/aws-bedrock)
[Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
[ConverseStream](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
`google-ai`
[Google AI](/ref/llm-client-providers/google-ai-gemini)
[generateContent](https://ai.google.dev/api/generate-content)
[streamGenerateContent](https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent)
`vertex-ai`
[Vertex AI](/ref/llm-client-providers/google-vertex)
[generateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent)
[streamGenerateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/streamGenerateContent)
`openai`
[OpenAI](/ref/llm-client-providers/open-ai)
[/chat/completions](https://platform.openai.com/docs/api-reference/chat)
`openai-responses`
[OpenAI Responses API](/ref/llm-client-providers/open-ai-responses-api)
[/responses](https://platform.openai.com/docs/api-reference/responses)
`azure-openai`
[Azure OpenAI](/ref/llm-client-providers/open-ai-from-azure)
[/chat/completions](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions)
`openai-generic`
[OpenAI (generic)](/ref/llm-client-providers/openai-generic)
`/chat/completions`

A non-exhaustive list of providers you can use withopenai-generic:

`openai-generic`
[Azure AI Foundry](/ref/llm-client-providers/azure-ai-foundary)
[Groq](/ref/llm-client-providers/groq)
[Hugging Face](/ref/llm-client-providers/huggingface)
[Keywords AI](/ref/llm-client-providers/keywordsai)
[Litellm](/ref/llm-client-providers/litellm)
[LM Studio](/ref/llm-client-providers/lmstudio)
[Ollama](/ref/llm-client-providers/ollama)
[OpenRouter](/ref/llm-client-providers/openrouter)
[Vercel AI Gateway](/ref/llm-client-providers/vercel-ai-gateway)
[TogetherAI](/ref/llm-client-providers/together)
[Unify AI](/ref/llm-client-providers/unify)
[vLLM](/ref/llm-client-providers/vllm)

We also have some special providers that allow composing clients together:

`fallback`
[Fallback](/ref/llm-client-strategies/fallback)
`round-robin`
[Round Robin](/ref/llm-client-strategies/round-robin)

These vary per provider. Please see provider specific documentation for more
information. Generally they are pass through options to the POST request made
to the LLM.


The name of the retry policy. SeeRetry
Policy.

[Retry
Policy](/ref/llm-client-strategies/retry-policy)