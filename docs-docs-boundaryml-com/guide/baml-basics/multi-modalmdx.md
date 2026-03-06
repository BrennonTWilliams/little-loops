---
url: https://docs.boundaryml.com/guide/baml-basics/multi-modal.mdx
scraped_at: 2026-03-06T01:00:22.962995
filepath: docs-docs-boundaryml-com/guide/baml-basics/multi-modalmdx.md
---


***

## slug: /guide/baml-basics/multi-modal

## Multi-modal input

You can use `audio`, `image`, `pdf`, or `video` input types in BAML prompts. Just create an input argument of that type and render it in the prompt.

Switch from "Prompt Review" to "Raw cURL" in the playground to see how BAML translates multi-modal input into the LLM Request body.

```baml
// "image" is a reserved keyword so we name the arg "img"
function DescribeMedia(img: image) -> string {
  client "openai-responses/gpt-5"  // GPT-5 has excellent multimodal support
  // Most LLM providers require images or audio to be sent as "user" messages.
  prompt #"
    {{_.role("user")}}
    Describe this image: {{ img }}
  "#
}

// See the "testing functions" Guide for more on testing Multimodal functions
test Test {
  functions [DescribeMedia]
  args {
    img {
      url "https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png"
    }
  }
}
```

See how to [test images in the playground](/guide/baml-basics/testing-functions#images).

## Try it! Press 'Run Test' below!
