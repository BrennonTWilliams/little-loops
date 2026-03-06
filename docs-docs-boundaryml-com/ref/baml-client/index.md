---
url: https://docs.boundaryml.com/ref/baml_client/
scraped_at: 2026-03-06T01:00:40.538270
filepath: docs-docs-boundaryml-com/ref/baml-client/index.md
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

Quick StartCommon Use CasesBasic ConfigurationPer-call TagsParallel ExecutionStreaming ModeAPI Referencewith_options ParametersConfigured Client PropertiesRelated Topics

[Quick Start](#quick-start)
[Common Use Cases](#common-use-cases)
[Basic Configuration](#basic-configuration)
[Per-call Tags](#per-call-tags)
[Parallel Execution](#parallel-execution)
[Streaming Mode](#streaming-mode)
[API Reference](#api-reference)
[with_options Parameters](#with_options-parameters)
[Configured Client Properties](#configured-client-properties)
[Related Topics](#related-topics)

Added in 0.79.0


Thewith_optionsfunction creates a new client with default configuration options for logging, client registry, and type builders. These options are automatically applied to all function calls made through this client, but can be overridden on a per-call basis when needed.

`with_options`

## Quick Start


```
1from baml_client import b2from baml_py import ClientRegistry, Collector34# Simple: just set the client name5my_b = b.with_options(client="openai/gpt-5-mini")67# Or with full options for advanced use cases8collector = Collector(name="my-collector")9client_registry = ClientRegistry()10client_registry.set_primary("openai/gpt-5-mini")11env = {"BAML_LOG": "DEBUG", "OPENAI_API_KEY": "key-123"}1213# Create client with default options14my_b = b.with_options(collector=collector, client_registry=client_registry, env=env)1516# Uses the default options17result = my_b.ExtractResume("...")1819# Override options for a specific call20other_collector = Collector(name="other-collector")21result2 = my_b.ExtractResume("...", baml_options={"collector": other_collector})
```


## Common Use Cases


### Basic Configuration


Usewith_optionsto create a client with default settings that will be applied to all function calls made through this client. These defaults can be overridden when needed.

`with_options`

```
1from baml_client import b2from baml_py import ClientRegistry, Collector34def run():5# Configure options6collector = Collector(name="my-collector")7client_registry = ClientRegistry()8client_registry.set_primary("openai/gpt-5-mini")910# Create configured client11my_b = b.with_options(collector=collector, client_registry=client_registry)1213# All calls will use the configured options14res = my_b.ExtractResume("...")15invoice = my_b.ExtractInvoice("...")1617# Access configuration18print(my_b.client_registry)19# Access logs from the collector20print(collector.logs)21print(collector.last)
```


### Per-call Tags


Add tags to a specific BAML function call. Tags are useful for correlating requests, A/B versions, user IDs, etc.


```
1from baml_client import b2from baml_py import Collector34collector = Collector(name="tags-collector")5res = b.TestOpenAIGPT4oMini(6"hello",7baml_options={8"collector": collector,9"tags": {"call_id": "first", "version": "v1"},10},11)1213print(collector.last.tags)
```


### Parallel Execution


When running functions in parallel,with_optionshelps maintain consistent configuration across all calls. This works seamlessly with theCollectorfunctionality.

`with_options`
[Collector](/ref/baml_client/collector)
`Collector`

```
1from baml_client.async_client import b2from baml_py import ClientRegistry, Collector3import asyncio45async def run():6collector = Collector(name="my-collector")7my_b = b.with_options(collector=collector, client_registry=client_registry)89# Run multiple functions in parallel10res, invoice = await asyncio.gather(11my_b.ExtractResume("..."),12my_b.ExtractInvoice("...")13)1415# Access results and logs16print(res)17print(invoice)18# Use tags or iterate logs to correlate specific calls19for log in collector.logs:20print(log.usage)
```


### Streaming Mode


with_optionscan be used with streaming functions while maintaining all configured options.

`with_options`

```
1from baml_client.async_client import b2from baml_py import Collector34async def run():5collector = Collector(name="my-collector")6my_b = b.with_options(collector=collector, client_registry=client_registry)78stream = my_b.stream.ExtractResume("...")9async for chunk in stream:10print(chunk)1112result = await stream.get_final_result()13# Use tags or collector.last / collector.logs for usage14print(collector.last.usage)
```


## API Reference


### with_options Parameters


These can always be overridden on a per-call basis with thebaml_optionsparameter in any function call.

`baml_options`
`client`
`string`
`client_registry.set_primary()`
`collector`
[Collector](/ref/baml_client/collector)
`Collector`
`client_registry`
`ClientRegistry`
`type_builder`
[TypeBuilder](/ref/baml_client/type-builder)
`TypeBuilder`
`env`
`Dict/Object`
`tags`
`Dict/Object`

### Configured Client Properties


The configured client maintains the same interface as the basebaml_client, so you can use all the same functions and methods.

`baml_client`

## Related Topics


Collector- Track function calls and usage metricsTypeBuilder- Build custom types for your functionsClient Registry- Manage LLM clients and their configurationsEnvironment Variables- Set environment variablesAbortController- Cancel in-flight operations

[Collector](/ref/baml_client/collector)
[TypeBuilder](/ref/baml_client/type-builder)
[Client Registry](/ref/baml_client/client-registry)
[Environment Variables](/ref/baml/general-baml-syntax/environment-variables)
[AbortController](/ref/baml_client/abort-signal)

The configured client maintains the same interface as the base client, so you can use all the same functions and methods.
