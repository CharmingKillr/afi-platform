---
name: ew-world-tools
description: Use Emergence World's navigation, memory, planning, public-content, research, community, identity, event, routine, and physical-world tools through ask_environment.
---

# EW World Tools

Use the exact EW tool name through `ask_environment`. Every tool in
`EWToolSpace` accepts your integer `agent_id` and a `request` dictionary.

Keep request dictionaries small and semantic. Common fields are:

- navigation: `place`, `x`, `z`, or `target_id`
- writing and memory: `content`, `title`, `date`, `query`, and `limit`
- stored records: `item_id`; creation may include arbitrary metadata
- social actions: `target_id`, `content`, `type`, `rating`, and `reason`
- code execution: `code` containing a safe literal arithmetic expression

Writes are idempotent within a simulation step. Read tools return at most 100
items unless the environment is configured with a smaller bound. Use economy,
governance, energy, crime, and direct-message tools from their specialized
environment modules when those modules are present.
