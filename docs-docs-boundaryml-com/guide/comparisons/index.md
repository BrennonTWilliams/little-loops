---
url: https://docs.boundaryml.com/guide/comparisons/
scraped_at: 2026-03-06T01:00:26.230230
filepath: docs-docs-boundaryml-com/guide/comparisons/index.md
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

Why working with LLMs requires more than just LangchainWhen things go wrongMulti-model madnessTesting nightmareThe token mysteryEnter BAMLMulti-model support done rightThe bottom lineLimitations of BAML

[Why working with LLMs requires more than just Langchain](#why-working-with-llms-requires-more-than-just-langchain)
[When things go wrong](#when-things-go-wrong)
[Multi-model madness](#multi-model-madness)
[Testing nightmare](#testing-nightmare)
[The token mystery](#the-token-mystery)
[Enter BAML](#enter-baml)
[Multi-model support done right](#multi-model-support-done-right)
[The bottom line](#the-bottom-line)
[Limitations of BAML](#limitations-of-baml)

Langchainis one of the most popular frameworks for building LLM applications. It provides abstractions for chains, agents, memory, and more.

[Langchain](https://github.com/langchain-ai/langchain)

Let’s dive into how Langchain handles structured extraction and where it falls short.


### Why working with LLMs requires more than just Langchain


Langchain makes structured extraction look simple at first:


```
1from pydantic import BaseModel, Field2from langchain_openai import ChatOpenAI34class Resume(BaseModel):5name: str6skills: List[str]78llm = ChatOpenAI(model="gpt-4o")9structured_llm = llm.with_structured_output(Resume)10result = structured_llm.invoke("John Doe, Python, Rust")
```


That’s pretty neat! But now let’s add anEducationmodel to make it more realistic:

`Education`

```
1+class Education(BaseModel):2+    school: str3+    degree: str4+    year: int56class Resume(BaseModel):7name: str8skills: List[str]9+    education: List[Education]1011structured_llm = llm.with_structured_output(Resume)12result = structured_llm.invoke("""John Doe13Python, Rust14University of California, Berkeley, B.S. in Computer Science, 2020""")
```


Still works… but what’s actually happening under the hood? What prompt is being sent? How many tokens are we using?


Let’s dig deeper. Say you want to see what’s actually being sent to the model:


```
1# How do you debug this?2structured_llm = llm.with_structured_output(Resume)34# You need to enable verbose mode or dig into callbacks5from langchain.globals import set_debug6set_debug(True)78# Now you get TONS of debug output...
```


But even with debug mode, you still can’t easily:


Modify the extraction promptSee the exact token countUnderstand why extraction failed for certain inputs


### When things go wrong


Here’s where it gets tricky. Your PM asks: “Can we classify these resumes by seniority level?”


```
1from enum import Enum23class SeniorityLevel(str, Enum):4JUNIOR = "junior"5MID = "mid"6SENIOR = "senior"7STAFF = "staff"89class Resume(BaseModel):10name: str11skills: List[str]12education: List[Education]13seniority: SeniorityLevel
```


But now you realize you need to give the LLM context about what each level means:


```
1# Wait... how do I tell the LLM that "junior" means 0-2 years experience?2# How do I customize the prompt?34# You end up doing this:5CLASSIFICATION_PROMPT = """6Given the resume below, classify the seniority level:7- junior: 0-2 years experience8- mid: 2-5 years experience9- senior: 5-10 years experience10- staff: 10+ years experience1112Resume: {resume_text}13"""1415# Now you need separate chains...16classification_chain = LLMChain(llm=llm, prompt=PromptTemplate.from_template(CLASSIFICATION_PROMPT))17extraction_chain = llm.with_structured_output(Resume)1819# And combine them somehow...
```


Your clean code is starting to look messy. But wait, there’s more!


### Multi-model madness


Your company wants to use Claude for some tasks (better reasoning) and GPT-4-mini for others (cost savings). With Langchain:


```
1from langchain_anthropic import ChatAnthropic2from langchain_openai import ChatOpenAI34# Different providers, different imports5claude = ChatAnthropic(model="claude-3-opus-20240229")6gpt4 = ChatOpenAI(model="gpt-4o")7gpt4_mini = ChatOpenAI(model="gpt-4o-mini")89# But wait... does Claude support structured outputs the same way?10claude_structured = claude.with_structured_output(Resume)  # May not work!1112# You need provider-specific handling13if provider == "anthropic":14# Use function calling? XML? JSON mode?15# Different providers have different capabilities16pass
```


### Testing nightmare


Now you want to test your extraction logic without burning through API credits:


```
1# How do you test this?2structured_llm = llm.with_structured_output(Resume)34# Mock the entire LLM?5from unittest.mock import Mock6mock_llm = Mock()7mock_llm.with_structured_output.return_value.invoke.return_value = Resume(...)89# But you're not really testing your extraction logic...10# Just that your mocks work
```


With BAML, testing is visual and instant:


Test your prompts instantly without API calls or mocking


### The token mystery


Your CFO asks: “Why is our OpenAI bill so high?” You investigate:


```
1# How many tokens does this use?2structured_llm = llm.with_structured_output(Resume)3result = structured_llm.invoke(long_resume_text)45# You need callbacks or token counting utilities6from langchain.callbacks import get_openai_callback78with get_openai_callback() as cb:9result = structured_llm.invoke(long_resume_text)10print(f"Tokens: {cb.total_tokens}")  # Finally!
```


But you still don’t know WHY it’s using so many tokens. Is it the schema format? The prompt template? The retry logic?


## Enter BAML


BAML was built specifically for these LLM challenges. Here’s the same resume extraction:


```
1class Education {2school string3degree string4year int5}67class Resume {8name string9skills string[]10education Education[]11seniority SeniorityLevel12}1314enum SeniorityLevel {15JUNIOR @description("0-2 years of experience")16MID @description("2-5 years of experience")17SENIOR @description("5-10 years of experience")18STAFF @description("10+ years of experience, technical leadership")19}2021function ExtractResume(resume_text: string) -> Resume {22client GPT423prompt #"24Extract information from this resume.2526Resume:27---28{{ resume_text }}29---3031{{ ctx.output_format }}32"#33}
```


Now look what you get:


See exactly what’s sent to the LLM- The prompt is right there!Test without API calls- Use the VSCode playgroundSwitch models instantly- Just changeclient GPT4toclient ClaudeToken count visibility- BAML shows exact token usageModify prompts easily- It’s just a template string

`client GPT4`
`client Claude`

### Multi-model support done right


```
1// Define all your clients in one place2client<llm> GPT4 {3provider openai4options {5model "gpt-4o"6temperature 0.17}8}910client<llm> GPT4Mini {11provider openai12options {13model "gpt-4o-mini"14temperature 0.115}16}1718client<llm> Claude {19provider anthropic20options {21model "claude-3-opus-20240229"22max_tokens 409623}24}2526// Same function works with ANY model27function ExtractResume(resume_text: string) -> Resume {28client GPT4  // Just change this line29prompt #"..."#30}
```


Use it in Python:


```
1from baml_client import baml as b23# Use default model4resume = await b.ExtractResume(resume_text)56# Override at runtime based on your needs7resume_complex = await b.ExtractResume(complex_text, {"client": "Claude"})8resume_simple = await b.ExtractResume(simple_text, {"client": "GPT4Mini"})
```


### The bottom line


Langchain is great for building complex LLM applications with chains, agents, and memory. But for structured extraction, you’re fighting against abstractions that hide important details.


BAML gives you what Langchain can’t:


Full prompt transparency- See and control exactly what’s sent to the LLMNative testing- Test in VSCode without API calls or burning tokensMulti-model by design- Switch providers with one line, works with any modelToken visibility- Know exactly what you’re paying for and optimize costsType safety- Generated clients with autocomplete that always match your schemaSchema-Aligned Parsing- Get structured outputs from any model, even without function callingStreaming + Structure- Stream structured data with loading bars and type-safe parsing


Why this matters for production:


Faster iteration- See changes instantly without running Python codeBetter debugging- Know exactly why extraction failedCost optimization- Understand and reduce token usageModel flexibility- Never get locked into one providerTeam collaboration- Prompts are code, not hidden strings


We built BAML because we were tired of wrestling with framework abstractions when all we wanted was reliable structured extraction with full developer control.


### Limitations of BAML


BAML does have some limitations we are continuously working on:


It is a new language. However, it is fully open source and getting started takes less than 10 minutesDeveloping requires VSCode. Youcoulduse vim but we don’t recommend itIt’s focused on structured extraction - not a full LLM framework like Langchain


If you need complex chains and agents, use Langchain. If you want the best structured extraction experience with full control,try BAML.

[try BAML](https://docs.boundaryml.com/)