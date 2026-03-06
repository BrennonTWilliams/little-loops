---
url: https://docs.boundaryml.com/home.mdx
scraped_at: 2026-03-06T01:00:33.612897
filepath: docs-docs-boundaryml-com/homemdx.md
---


***

title: "\U0001F3E0 Welcome"
description: The easiest way to use LLMs
slug: home
layout: overview
hide-toc: false
---------------

**BAML is a domain-specific language to generate structured outputs from LLMs -- with the best developer experience.**

With BAML you can build reliable Agents, Chatbots with RAG, extract data from Pdfs, and more.

### A small sample of features:

1. **An amazingly fast developer experience** for prompting in the BAML VSCode playground
2. **Fully type-safe outputs**, even when streaming structured data (that means autocomplete!)
3. **Flexibility** -- it works with **any LLM**, **any language**, and **any schema**.
4. **State-of-the-art structured outputs** that even [outperform OpenAI with their own models](https://www.boundaryml.com/blog/sota-function-calling?q=0) -- plus it works with OpenSource models.

## ProductsEverything you need to know about how to get started with BAML. From installation to prompt engineering techniques.An online interactive playground to playaround with BAML without any installations.Examples of prompts, projects, and more.Language docs on all BAML syntax. Quickly learn syntax with simple examples and code snippets.## Motivation

Prompts are more than just f-strings; they're actual functions with logic that can quickly become complex to organize, maintain, and test.

Currently, developers craft LLM prompts as if they're writing raw HTML and CSS in text files, lacking:

* Type safety
* Hot-reloading or previews
* Linting

The situation worsens when dealing with structured outputs. Since most prompts rely on Python and Pydantic, developers must *execute* their code and set up an entire Python environment just to test a minor prompt adjustment, or they have to setup a whole Python microservice just to call an LLM.

BAML allows you to view and run prompts directly within your editor, similar to how Markdown Preview function -- no additional setup necessary, that interoperates with all your favorite languages and frameworks.

Just as TSX/JSX provided the ideal abstraction for web development, BAML offers the perfect abstraction for prompt engineering. Watch our [demo video](/guide/introduction/what-is-baml#demo-video) to see it in action.

## Comparisons

Here's our in-depth comparison with a couple of popular frameworks:

* [BAML vs Pydantic](/guide/comparisons/baml-vs-pydantic)
* [BAML vs Marvin](/guide/comparisons/baml-vs-marvin)

{/*
