---
url: https://docs.boundaryml.com/ref/prompt-syntax/conditionals.mdx
scraped_at: 2026-03-06T01:00:51.380965
filepath: docs-docs-boundaryml-com/ref/prompt-syntax/conditionalsmdx.md
---


***

## title: Conditionals

Use conditional statements to control the flow and output of your templates based on conditions:

```jinja
function MyFunc(user: User) -> string {
  prompt #"
    {% if user.is_active %}
      Welcome back, {{ user.name }}!
    {% else %}
      Please activate your account.
    {% endif %}
  "#
}
```
