---
url: https://docs.boundaryml.com/ref/llm-client-strategies/
scraped_at: 2026-03-06T01:00:50.584711
filepath: docs-docs-boundaryml-com/ref/llm-client-strategies/index.md
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

OverviewTimeout OptionsTimeout CompositionExampleTimeout EvaluationInteraction with Retry PoliciesRuntime OverridesError HandlingValidation RulesSee Also

[Overview](#overview)
[Timeout Options](#timeout-options)
[Timeout Composition](#timeout-composition)
[Example](#example)
[Timeout Evaluation](#timeout-evaluation)
[Interaction with Retry Policies](#interaction-with-retry-policies)
[Runtime Overrides](#runtime-overrides)
[Error Handling](#error-handling)
[Validation Rules](#validation-rules)
[See Also](#see-also)

Configure timeouts on any BAML client to prevent requests from hanging indefinitely.


## Overview


Timeouts can be configured on leaf clients (OpenAI, Anthropic, etc.).


## Timeout Options


All timeout values are specified inmillisecondsas positive integers.


Maximum time to establish a network connection to the provider.


Default:No timeout (infinite)


```
1client<llm> MyClient {2provider openai3options {4model "gpt-4"5api_key env.OPENAI_API_KEY6http {7connect_timeout_ms 5000  // 5 seconds8}9}10}
```


Maximum time to receive the first token after sending the request.


Default:No timeout (infinite)


Particularly useful for detecting when a provider accepts the request but takes too long to start generating.


```
1client<llm> MyClient {2provider openai3options {4model "gpt-4"5api_key env.OPENAI_API_KEY6http {7time_to_first_token_timeout_ms 10000  // 10 seconds8}9}10}
```


Maximum time between receiving consecutive data chunks.


Default:No timeout (infinite)


Important for detecting stalled streaming connections.


```
1client<llm> MyClient {2provider openai3options {4model "gpt-4"5api_key env.OPENAI_API_KEY6http {7idle_timeout_ms 15000  // 15 seconds8}9}10}
```


Maximum total time for the entire request-response cycle.


Default:No timeout (infinite)


For streaming responses, this applies to the entire stream duration (first token to last token).


```
1client<llm> MyClient {2provider openai3options {4model "gpt-4"5api_key env.OPENAI_API_KEY6http {7request_timeout_ms 60000  // 60 seconds8}9}10}
```


## Timeout Composition


When composite clients reference subclients with their own timeouts, theminimum (most restrictive) timeout wins.


### Example


```
1client<llm> FastClient {2provider openai3options {4model "gpt-3.5-turbo"5api_key env.OPENAI_API_KEY6http {7connect_timeout_ms 30008request_timeout_ms 200009}10}11}1213client<llm> SlowClient {14provider openai15options {16model "gpt-4"17api_key env.OPENAI_API_KEY18http {19request_timeout_ms 6000020}21}22}2324client<llm> MyFallback {25provider fallback26options {27strategy [FastClient, SlowClient]28http {29connect_timeout_ms 5000      // Parent timeout30idle_timeout_ms 15000        // Parent timeout31}32}33}
```


Effective timeouts:


When callingFastClient:

`FastClient`

connect_timeout_ms:min(5000, 3000)=3000ms(FastClient is stricter)request_timeout_ms:min(∞, 20000)=20000ms(only FastClient defines it)idle_timeout_ms:min(15000, ∞)=15000ms(only parent defines it)

`connect_timeout_ms`
`min(5000, 3000)`
`request_timeout_ms`
`min(∞, 20000)`
`idle_timeout_ms`
`min(15000, ∞)`

When callingSlowClient:

`SlowClient`

connect_timeout_ms:min(5000, ∞)=5000ms(only parent defines it)request_timeout_ms:min(∞, 60000)=60000ms(only SlowClient defines it)idle_timeout_ms:min(15000, ∞)=15000ms(only parent defines it)

`connect_timeout_ms`
`min(5000, ∞)`
`request_timeout_ms`
`min(∞, 60000)`
`idle_timeout_ms`
`min(15000, ∞)`

## Timeout Evaluation


All timeouts are evaluated concurrently. A request fails whenanytimeout is exceeded:


Connection phase:connect_timeout_msappliesAfter connection:time_to_first_token_timeout_msstarts when request is sentrequest_timeout_msstarts when request is sentidle_timeout_msstarts after each chunk is received

`connect_timeout_ms`

time_to_first_token_timeout_msstarts when request is sentrequest_timeout_msstarts when request is sentidle_timeout_msstarts after each chunk is received

`time_to_first_token_timeout_ms`
`request_timeout_ms`
`idle_timeout_ms`

## Interaction with Retry Policies


When a client has both timeouts and a retry policy:


Each retry attempt gets thefull timeout durationA timeout triggers the retry mechanism (if configured)Total elapsed time = (number of attempts) × (timeout per attempt) + (retry delays)


Example:


```
1retry_policy Exponential {2max_retries 33strategy {4type exponential_backoff5}6}78client<llm> MyClient {9provider openai10retry_policy Exponential11options {12model "gpt-4"13api_key env.OPENAI_API_KEY14http {15request_timeout_ms 30000  // Each attempt gets 30 seconds16}17}18}
```


Maximum possible time: ~30s × 4 attempts + exponential backoff delays


## Runtime Overrides


Override timeout values at runtime using the client registry:


```
1import { b } from './baml_client'23const result = await b.MyFunction(input, {4clientRegistry: b.ClientRegistry.override({5"MyClient": {6options: {7http: {8request_timeout_ms: 10000,9idle_timeout_ms: 500010}11}12}13})14})
```


Runtime overrides follow the same composition rules: the minimum timeout wins when composing runtime values with config file values.


## Error Handling


Timeout errors are represented byBamlTimeoutError, a subclass ofBamlClientError:

`BamlTimeoutError`
`BamlClientError`

```
BamlError└── BamlClientError└── BamlTimeoutError
```


Timeout errors include structured fields:


client: The client name that timed outtimeout_type: The specific timeout that was exceededconfigured_value_ms: The configured timeout value in millisecondselapsed_ms: The actual elapsed time in millisecondsmessage: A human-readable error message

`client`
`timeout_type`
`configured_value_ms`
`elapsed_ms`
`message`

```
1from baml_py.errors import BamlTimeoutError23try:4result = await b.MyFunction(input)5except BamlTimeoutError as e:6print(f"Timeout: {e.timeout_type}")7print(f"Configured: {e.configured_value_ms}ms")8print(f"Elapsed: {e.elapsed_ms}ms")
```


## Validation Rules


BAML validates timeout configurations at compile time:


Positive values:All timeout values must be positive integersLogical constraints:request_timeout_msmust be ≥time_to_first_token_timeout_ms(if both are specified)

`request_timeout_ms`
`time_to_first_token_timeout_ms`

Invalid configurations will cause BAML to raise validation errors with helpful messages.


## See Also


Configuring Timeouts Guide- User guide with examplesFallback Strategy- Using timeouts with fallback clientsRetry Policies- Using timeouts with retriesError Handling- Handling timeout errors

[Configuring Timeouts Guide](/guide/baml-basics/timeouts)
[Fallback Strategy](/ref/llm-client-strategies/fallback)
[Retry Policies](/ref/llm-client-strategies/retry-policy)
[Error Handling](/guide/baml-basics/error-handling)