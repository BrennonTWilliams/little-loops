---
url: https://docs.boundaryml.com/guide/framework-integration/
scraped_at: 2026-03-06T01:00:29.299653
filepath: docs-docs-boundaryml-com/guide/framework-integration/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

IntroductionWhat is BAML?Why BAML?What's the baml_src folderWhat's baml_clientInstallation: EditorsVSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthersInstallation: LanguagePythonTypescriptGoRubyRustREST API (other languages)ElixirFramework IntegrationReact/Next.jsDevelopmentEnvironment VariablesTerminal LogsUpgrade BAML versionsDeployingBAML BasicsPrompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / CancellationBAML AdvancedCollector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt OptimizationBoundary CloudObservabilityComparisonsBAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs PydanticContact


What is BAML?Why BAML?What's the baml_src folderWhat's baml_client

[What is BAML?](/guide/introduction/what-is-baml)
[Why BAML?](/guide/introduction/why-baml)
[What's the baml_src folder](/guide/introduction/baml_src)
[What's baml_client](/guide/introduction/baml_client)

VSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthers

[VSCode Extension](/guide/installation-editors/vs-code-extension)
[Cursor Extension](/guide/installation-editors/cursor-extension)
[JetBrains IDEs](/guide/installation-editors/jetbrains)
[Zed](/guide/installation-editors/zed)
[Claude Code](/guide/installation-editors/claude-code)
[Others](/guide/installation-editors/others)

PythonTypescriptGoRubyRustREST API (other languages)Elixir

[Python](/guide/installation-language/python)
[Typescript](/guide/installation-language/typescript)
[Go](/guide/installation-language/go)
[Ruby](/guide/installation-language/ruby)
[Rust](/guide/installation-language/rust)
[REST API (other languages)](/guide/installation-language/rest-api-other-languages)
[Elixir](/guide/installation-language/elixir)

React/Next.js


Environment VariablesTerminal LogsUpgrade BAML versionsDeploying

[Environment Variables](/guide/development/environment-variables)
[Terminal Logs](/guide/development/terminal-logs)
[Upgrade BAML versions](/guide/development/upgrade-baml-versions)

Prompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / Cancellation

[Prompting with BAML](/guide/baml-basics/prompting-with-baml)
[Switching LLMs](/guide/baml-basics/switching-llms)
[Testing functions](/guide/baml-basics/testing-functions)
[Streaming](/guide/baml-basics/streaming)
[Multi-Modal (Images / Audio)](/guide/baml-basics/multi-modal)
[Error Handling](/guide/baml-basics/error-handling)
[Configuring Timeouts](/guide/baml-basics/timeouts)
[Concurrent Calls](/guide/baml-basics/concurrent-calls)
[AbortSignal / Cancellation](/guide/baml-basics/abort-signal)

Collector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt Optimization

[Collector (track tokens)](/guide/baml-advanced/collector-track-tokens)
[LLM Client Registry](/guide/baml-advanced/llm-client-registry)
[Dynamic Types](/guide/baml-advanced/dynamic-types)
[Reusing Prompt Snippets](/guide/baml-advanced/reusing-prompt-snippets)
[Prompt Caching / Message Role Metadata](/guide/baml-advanced/prompt-caching-message-role-metadata)
[Checks and Asserts](/guide/baml-advanced/checks-and-asserts)
[Modular API](/guide/baml-advanced/modular-api)
[Prompt Optimization](/guide/baml-advanced/prompt-optimization)

Observability


BAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs Pydantic

[BAML vs Langchain](/guide/comparisons/baml-vs-langchain)
[BAML vs Marvin](/guide/comparisons/baml-vs-marvin)
[BAML vs Ai-SDK](/guide/comparisons/baml-vs-ai-sdk)
[BAML vs OpenAI SDK](/guide/comparisons/baml-vs-open-ai-sdk)
[BAML vs Pydantic](/guide/comparisons/baml-vs-pydantic)

Contact

[Contact](/guide/contact)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

Example UsageQuick StartReference DocumentationCore ConceptsHook ConfigurationNext Steps

[Example Usage](#example-usage)
[Quick Start](#quick-start)
[Reference Documentation](#reference-documentation)
[Core Concepts](#core-concepts)
[Hook Configuration](#hook-configuration)
[Next Steps](#next-steps)

This guide walks you through setting up BAML with React/Next.js, leveraging Server Actions and React Server Components for optimal performance.


Requirements:This integration requiresNext.js 15 or higher.


## Example Usage


BAML automatically generates a server action and React hook for your BAML functions, with built-in support for both streaming and non-streaming modes. For details on the generated hooks, seeGenerated Hooks.

[Generated Hooks](/ref/baml_client/react-next-js/use-function-name-hook)

```
1class Story {2title string @stream.not_null3content string @stream.not_null4}56function WriteMeAStory(input: string) -> Story {7client "openai/gpt-5"8prompt #"9Tell me a story1011{{ ctx.output_format() }}1213{{ _.role("user") }}1415Topic: {{input}}16"#17}
```


## Quick Start


Follow the step-by-step instructions below to set up BAML in a new or existing Next.js project.

[1](/guide/framework-integration/react-next-js/quick-start#create-a-new-nextjs-project)

### Create a New Next.js Project


First, create a new Next.js project with the App Router:


```
$npx create-next-app@latest my-baml-app
```


When prompted, make sure to:


SelectYesfor “Would you like to use TypeScript?”SelectYesfor “Would you like to use the App Router? (recommended)”Configure other options as needed for your project

[2](/guide/framework-integration/react-next-js/quick-start#install-dependencies)

### Install Dependencies


Next, install BAML and its dependencies:


```
$npm install @boundaryml/baml @boundaryml/baml-nextjs-plugin
```

[3](/guide/framework-integration/react-next-js/quick-start#configure-nextjs)

### Configure Next.js


Update yournext.config.mjs:

`next.config.mjs`

```
1import { withBaml } from '@boundaryml/baml-nextjs-plugin';2import type { NextConfig } from 'next';34const nextConfig: NextConfig = {5// ... existing config6};78export default withBaml()(nextConfig);
```

[4](/guide/framework-integration/react-next-js/quick-start#initialize-baml)

### Initialize BAML


Create a new BAML project in your Next.js application:


```
$npx baml-cli init
```


This will create abaml_srcdirectory with starter code.

`baml_src`
[5](/guide/framework-integration/react-next-js/quick-start#setup-environment-variables)

### Setup Environment Variables


Setup provider specific API Keys.


```
1OPENAI_API_KEY=sk-...
```


To enable observability with BAML, you’ll first need to sign up for aBoundary Studioaccount.

[Boundary Studio](https://studio.boundaryml.com/)

```
1BOUNDARY_API_KEY=your_api_key_here23OPENAI_API_KEY=sk-...
```

[6](/guide/framework-integration/react-next-js/quick-start#setup-baml-nextjs-generator)

### Setup BAML Next.js Generator


Update thebaml_src/generators.bamlfile to use the React/Next.js generator.

`baml_src/generators.baml`

```
1generator typescript {2-  output_type "typescript"3+  output_type "typescript/react"4output_dir "../"5version "0.76.2"6}
```

[7](/guide/framework-integration/react-next-js/quick-start#generate-baml-client)

### Generate BAML Client


```
$npx baml-cli generate
```


If you need baml_client to be ‘ESM’ compatible, you can add the followinggeneratorconfiguration to your.bamlfile:

`generator`
`.baml`

```
1generator typescript {2...3module_format "esm" // the default is "cjs" for CommonJS4}
```

[8](/guide/framework-integration/react-next-js/quick-start#generated-react-hooks)

### Generated React Hooks


BAML automatically generates type-safe Next.js server actions and React hooks for your BAML functions.


```
1class Story {2title string @stream.not_null3content string @stream.not_null4}56function WriteMeAStory(input: string) -> Story {7client "openai/gpt-5"8prompt #"9Tell me a story1011{{ ctx.output_format() }}1213{{ _.role("user") }}1415Topic: {{input}}16"#17}
```

[9](/guide/framework-integration/react-next-js/quick-start#update-package-scripts)

### Update Package Scripts


Update yourpackage.jsonscripts:

`package.json`

```
1{2"scripts": {3"prebuild": "npm run generate",4"generate": "baml-cli generate",5"dev": "next dev",6"build": "next build",7"start": "next start",8}9}
```


## Reference Documentation


For complete API documentation of the React/Next.js integration, see:


### Core Concepts


Generated Hooks- Auto-generated hooks for each BAML function

[Generated Hooks](/ref/baml_client/react-next-js/use-function-name-hook)

### Hook Configuration


HookInput- Configuration options for hooksHookOutput- Return value types and statesError Types- Error handling and types

[HookInput](/ref/baml_client/react-next-js/hook-input)
[HookOutput](/ref/baml_client/react-next-js/hook-output)
[Error Types](/ref/baml_client/errors/overview)

## Next Steps


Check out theBAML Examplesfor more use cases

[BAML Examples](https://github.com/BoundaryML/baml-examples/tree/main/nextjs-starter)