---
url: https://docs.boundaryml.com/examples/prompt-engineering/
scraped_at: 2026-03-06T01:00:18.144183
filepath: docs-docs-boundaryml-com/examples/prompt-engineering/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

Interactive ExamplesPrompt EngineeringReducing HallucinationsClassificationChatTools / Function CallingChain of ThoughtSymbol TuningToken OptimizationPII Data Extraction / ScrubbingAction Item ExtractionRetrieval Augmented Generation


Interactive Examples

[Interactive Examples](/examples/interactive-examples)

Reducing HallucinationsClassificationChatTools / Function CallingChain of ThoughtSymbol TuningToken OptimizationPII Data Extraction / ScrubbingAction Item ExtractionRetrieval Augmented Generation

[Reducing Hallucinations](/examples/prompt-engineering/reducing-hallucinations)
[Classification](/examples/prompt-engineering/classification)
[Chat](/examples/prompt-engineering/chat)
[Tools / Function Calling](/examples/prompt-engineering/tools-function-calling)
[Chain of Thought](/examples/prompt-engineering/chain-of-thought)
[Symbol Tuning](/examples/prompt-engineering/symbol-tuning)
[Token Optimization](/examples/prompt-engineering/token-optimization)
[PII Data Extraction / Scrubbing](/examples/prompt-engineering/pii-data-extraction-scrubbing)
[Action Item Extraction](/examples/prompt-engineering/action-item-extraction)
[Retrieval Augmented Generation](/examples/prompt-engineering/retrieval-augmented-generation)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

1. Set temperature to 0.0 (especially if extracting data verbatim)2. Reduce the number of input tokens2. Use reasoning or reflection prompting3. Watch out for contradictions and word associations

[1. Set temperature to 0.0 (especially if extracting data verbatim)](#1-set-temperature-to-00-especially-if-extracting-data-verbatim)
[2. Reduce the number of input tokens](#2-reduce-the-number-of-input-tokens)
[2. Use reasoning or reflection prompting](#2-use-reasoning-or-reflection-prompting)
[3. Watch out for contradictions and word associations](#3-watch-out-for-contradictions-and-word-associations)

We recommend these simple ways to reduce hallucinations:


### 1. Set temperature to 0.0 (especially if extracting data verbatim)


This will make the model less creative and more likely to just extract the data that you want verbatim.


```
1client<llm> MyClient {2provider openai3options {4temperature 0.05}6}
```


### 2. Reduce the number of input tokens


Reduce the amount of data you’re giving the model to process to reduce confusion.


Prune as much data as possible, or split your prompt into multiple prompts analyzing subsets of the data.


If you’re processingimages, try cropping the parts of the image that you don’t need. LLMs can only handle images of certain sizes, so every pixel counts. Make sure you resize images to the model’s input size (even if the provider does the resizing for you), so you can gauge how clear the image is at the model’s resolution. You’ll notice the blurrier the image is, the higher the hallucination rate.

`images`

Let us know if you want more tips for processing images, we have some helper prompts we can share with you, or help debug your prompt.


### 2. Use reasoning or reflection prompting


Read ourchain-of-thought guidefor more.

[chain-of-thought guide](/examples/prompt-engineering/chain-of-thought)

### 3. Watch out for contradictions and word associations


Each word you add into the prompt will cause it to associate it with something it saw before in its training data. This is why we have techniques likesymbol tuningto help control this bias.

[symbol tuning](/examples/prompt-engineering/symbol-tuning)

Let’s say you have a prompt that says:


```
Answer in this JSON schema:But when you answer, add some comments in the JSON indicating your reasoning for the field like this:Example:---{// I used the name "John" because it's the name of the person who wrote the prompt"name": "John"}JSON:
```


The LLM may not write the// commentinline, because it’s been trained to associate JSON with actual “valid” JSON.

`// comment`

You can get around this with some more coaxing like:


```
Answer in this JSON schema:But when you answer, add some comments in the JSON indicating your reasoning for the field like this:---{// I used the name "John" because it's the name of the person who wrote the prompt"name": "John"}It's ok if this isn't fully valid JSON,we will fix it afterwards and remove the comments.JSON:
```


The LLM made an assumption that you want “JSON” — which doesn’t use comments — and our instructions were not explicit enough to override that bias originally.


Keep on reading for more tips and tricks! Or reach out in our Discord
