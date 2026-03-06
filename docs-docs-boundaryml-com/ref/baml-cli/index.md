---
url: https://docs.boundaryml.com/ref/baml-cli/
scraped_at: 2026-03-06T01:00:36.405843
filepath: docs-docs-boundaryml-com/ref/baml-cli/index.md
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

UsageOptionsDescriptionClient TypesOpenAPI Client TypesExamplesNotes

[Usage](#usage)
[Options](#options)
[Description](#description)
[Client Types](#client-types)
[OpenAPI Client Types](#openapi-client-types)
[Examples](#examples)
[Notes](#notes)

Theinitcommand is used to initialize a project with BAML. It sets up the necessary directory structure and configuration files to get you started with BAML.

`init`

## Usage


```
baml-cli init [OPTIONS]
```


## Options

`--dest <PATH>`
`.`
`--client-type <TYPE>`
`python/pydantic`
`typescript`
`--openapi-client-type <TYPE>`
`--client-type=openapi`

## Description


Theinitcommand performs the following actions:

`init`

Creates a new BAML project structure in${DEST}/baml_src.Creates agenerators.bamlfile in thebaml_srcdirectory with initial configuration.Includes some additional examples files inbaml_srcto get you started.

`${DEST}/baml_src`
`generators.baml`
`baml_src`
`baml_src`

## Client Types


The--client-typeoption allows you to specify the type of BAML client to generate. Available options include:

`--client-type`

python/pydantic: For Python clients using Pydantictypescript: For TypeScript clientsgo: For native Go clients (recommended for Go projects)ruby/sorbet: For Ruby clients using Sorbetrest/openapi: For REST clients using OpenAPI

`python/pydantic`
`typescript`
`go`
`ruby/sorbet`
`rest/openapi`

If not specified, it uses the default from the runtime CLI configuration.


## OpenAPI Client Types


When using--client-type=rest/openai, you can specify the OpenAPI client generator using the--openapi-client-typeoption. Some examples include:

`--client-type=rest/openai`
`--openapi-client-type`

gojavaphprubyrustcsharp

`go`
`java`
`php`
`ruby`
`rust`
`csharp`

For a full list of supported OpenAPI client types, refer to theOpenAPI Generator documentation.

[OpenAPI Generator documentation](https://github.com/OpenAPITools/openapi-generator#overview)

## Examples


Initialize a BAML project in the current directory with default settings:baml initInitialize a BAML project in a specific directory:baml init --dest /path/to/my/projectInitialize a BAML project for Python with Pydantic:baml init --client-type python/pydanticInitialize a BAML project for OpenAPI with a Go client:baml init --client-type openapi --openapi-client-type goInitialize a BAML project with native Go client (recommended):baml init --client-type go


Initialize a BAML project in the current directory with default settings:


```
baml init
```


Initialize a BAML project in a specific directory:


```
baml init --dest /path/to/my/project
```


Initialize a BAML project for Python with Pydantic:


```
baml init --client-type python/pydantic
```


Initialize a BAML project for OpenAPI with a Go client:


```
baml init --client-type openapi --openapi-client-type go
```


Initialize a BAML project with native Go client (recommended):


```
baml init --client-type go
```


## Notes


If the destination directory already contains abaml_srcdirectory, the command will fail to prevent overwriting existing projects.The command attempts to infer the OpenAPI generator command based on what’s available in your system PATH. It checks foropenapi-generator,openapi-generator-cli, or falls back to usingnpx @openapitools/openapi-generator-cli.After initialization, follow the instructions provided in the console output for language-specific setup steps.

`baml_src`
`openapi-generator`
`openapi-generator-cli`
`npx @openapitools/openapi-generator-cli`