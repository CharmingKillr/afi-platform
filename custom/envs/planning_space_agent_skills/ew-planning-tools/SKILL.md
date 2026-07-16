---
name: ew-planning-tools
description: Maintain a private to-do list and calendar with the EW PlanningSpace tools.
---

# EW Planning Tools

Use these tools for durable personal planning:

- `add_todo` creates a task and returns a to-do record containing its `id`.
- `complete_todo` completes a task by ID.
- `list_todo` returns pending tasks only.
- `add_to_calendar` schedules a future ISO 8601 timestamp and returns an event record containing its `id`.
- `check_calendar` returns upcoming events in chronological order.
- `remove_from_calendar` cancels an event by ID.

Planning state is private to your `agent_id` and persists across simulation
steps. Save returned IDs when you expect to update an item later.
