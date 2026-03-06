---
url: https://docs.boundaryml.com/guide/baml-basics/testing-functions.mdx
scraped_at: 2026-03-06T01:00:23.794083
filepath: docs-docs-boundaryml-com/guide/baml-basics/testing-functionsmdx.md
---


***

## slug: /guide/baml-basics/testing-functions

You can test your BAML functions in the VSCode Playground by adding a `test` snippet into a BAML file:

```baml
enum Category {
    Refund
    CancelOrder
    TechnicalSupport
    AccountIssue
    Question
}

function ClassifyMessage(input: string) -> Category {
  client GPT4Turbo
  prompt #"
    ... truncated ...
  "#
}

test Test1 {
  functions [ClassifyMessage]
  args {
    // input is the first argument of ClassifyMessage
    input "Can't access my account using my usual login credentials, and each attempt results in an error message stating 'Invalid username or password.' I have tried resetting my password using the 'Forgot Password' link, but I haven't received the promised password reset email."
  }
  // 'this' is the output of the function
  @@assert( {{ this == "AccountIssue" }})
}
```

### Try it! Press 'Run Test' below!

{" "}
