"""EW personal planning tools as an AgentSociety custom environment.

This is a clean-room adaptation of the six ``Planning & Organization`` tool
descriptions published by Emergence World:
https://github.com/EmergenceAI/Emergence-World/tree/main/tools

Only the public names and behavior descriptions are used; no upstream code is
copied.  State is private per agent, persisted across workspace restore, and
snapshotted to replay on every simulation step.

stdlib + agentsociety2 only (this module runs in the AS environment and must
not import ``afi``).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from functools import wraps
from typing import ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text


_STATE_REL = "state/PLANNING_STATE.json"
_logger = get_logger()


def idempotent_write(func):
    """Return the original result when an agent retries a write in one step."""
    @wraps(func)
    async def wrapped(self, *args, **kwargs):
        key = json.dumps([self._step_counter, func.__name__, args, kwargs], sort_keys=True, default=str)
        async with self._dedup_lock:
            if key in self._dedup:
                duplicate = {**self._dedup[key], "deduplicated": True}
                if func.__name__ == "complete_todo" and duplicate.get("ok"):
                    duplicate["already_completed"] = True
                return duplicate
            result = await func(self, *args, **kwargs)
            self._dedup[key] = dict(result)
            return result
    return wrapped


class PlanningSpace(EnvBase):
    """Private per-agent to-do lists and calendars."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("pending_todos", "INTEGER"),
        ColumnDef("completed_todos", "INTEGER"),
        ColumnDef("upcoming_calendar_entries", "INTEGER"),
    ]

    def __init__(self, agent_ids: List[int] | None = None, **kwargs):
        if kwargs:
            _logger.warning(
                f"PlanningSpace unknown kwargs ignored: {list(kwargs.keys())}"
            )
        super().__init__()
        ids = [int(agent_id) for agent_id in (agent_ids or [1, 2, 3, 4, 5])]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("agent_ids must be a non-empty list of unique IDs")

        self._agent_ids = ids
        self._todos: dict[int, dict[int, dict]] = {agent_id: {} for agent_id in ids}
        self._calendar: dict[int, dict[int, dict]] = {
            agent_id: {} for agent_id in ids
        }
        self._next_todo_id = 1
        self._next_event_id = 1
        self._step_counter = 0
        self._dedup: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._dedup_lock = asyncio.Lock()

    @classmethod
    def description(cls) -> str:
        return "EW personal planning: persistent private to-do lists and calendars."

    @classmethod
    def init_description(cls) -> str:
        return """PlanningSpace implements EW's six Planning & Organization tools.

Each agent can only access its own planning state. Calendar timestamps use
ISO 8601 and must be in the future relative to simulation time.

**Initialization Parameters:**
- agent_ids (list[int]): agent IDs to track. Default [1..5].

**Tools:**
- add_todo(agent_id, task): add a personal task
- complete_todo(agent_id, todo_id): mark a task complete
- list_todo(agent_id): list pending tasks
- add_to_calendar(agent_id, title, start_at, end_at?, description?): schedule an event
- check_calendar(agent_id, limit?): list upcoming events in chronological order
- remove_from_calendar(agent_id, event_id): cancel an event
"""

    @staticmethod
    def _parse_datetime(value: str, field: str) -> datetime:
        """Parse ISO 8601 into a comparable, UTC-naive datetime."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty ISO 8601 timestamp")
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid ISO 8601 timestamp") from exc
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _now(self) -> datetime:
        current = getattr(self, "t", None)
        if not isinstance(current, datetime):
            return datetime.min
        if current.tzinfo is not None:
            return current.astimezone(timezone.utc).replace(tzinfo=None)
        return current

    def _known_agent(self, agent_id: int) -> bool:
        return int(agent_id) in self._todos

    @staticmethod
    def _error(message: str) -> dict:
        return {"ok": False, "status": "fail", "error": message}

    @staticmethod
    def _success(**payload) -> dict:
        return {"ok": True, "status": "success", **payload}

    def _snapshot(self, agent_id: int, now: datetime | None = None) -> dict:
        todos = self._todos[agent_id].values()
        current = now or self._now()
        upcoming = sum(
            1
            for event in self._calendar[agent_id].values()
            if self._parse_datetime(event["start_at"], "start_at") >= current
        )
        return {
            "pending_todos": sum(1 for item in todos if not item["completed"]),
            "completed_todos": sum(1 for item in todos if item["completed"]),
            "upcoming_calendar_entries": upcoming,
        }

    async def step(self, tick: int, t: datetime):
        async with self._lock:
            self.t = t
            self._step_counter += 1
            self._dedup.clear()
            for agent_id in self._agent_ids:
                await self._write_agent_state(
                    agent_id,
                    self._step_counter,
                    t,
                    **self._snapshot(agent_id, self._now()),
                )

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("PlanningSpace workspace is not bound")
        async with self._lock:
            state = {
                "agent_ids": self._agent_ids,
                "todos": {
                    str(agent_id): {str(item_id): item for item_id, item in items.items()}
                    for agent_id, items in self._todos.items()
                },
                "calendar": {
                    str(agent_id): {str(event_id): event for event_id, event in items.items()}
                    for agent_id, items in self._calendar.items()
                },
                "next_todo_id": self._next_todo_id,
                "next_event_id": self._next_event_id,
                "step_counter": self._step_counter,
                "dedup": self._dedup,
                "current_time": self._now().isoformat(),
            }
            atomic_write_text(
                self._workspace_root / _STATE_REL,
                json.dumps(state, ensure_ascii=False, indent=2),
            )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        path = self._workspace_root / _STATE_REL
        if not path.is_file():
            return False
        state = json.loads(path.read_text(encoding="utf-8"))
        ids = [int(agent_id) for agent_id in state.get("agent_ids", [])]
        if not ids:
            raise ValueError("PlanningSpace state has no agent IDs")

        self._agent_ids = ids
        self._todos = {
            agent_id: {
                int(item_id): item
                for item_id, item in state.get("todos", {}).get(str(agent_id), {}).items()
            }
            for agent_id in ids
        }
        self._calendar = {
            agent_id: {
                int(event_id): event
                for event_id, event in state.get("calendar", {}).get(str(agent_id), {}).items()
            }
            for agent_id in ids
        }
        self._next_todo_id = int(state.get("next_todo_id", 1))
        self._next_event_id = int(state.get("next_event_id", 1))
        self._step_counter = int(state.get("step_counter", 0))
        self._dedup = state.get("dedup", {})
        saved_time = state.get("current_time")
        self.t = (
            self._parse_datetime(saved_time, "current_time")
            if saved_time
            else datetime.min
        )
        self._lock = asyncio.Lock()
        self._dedup_lock = asyncio.Lock()
        return True

    @tool(readonly=False)
    @idempotent_write
    async def add_todo(self, agent_id: int, task: str) -> dict:
        """Add a task to your personal to-do list.

        :param agent_id: Acting agent ID
        :param task: Task description
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            task = str(task).strip()
            if not task:
                return self._error("task must not be empty")
            item_id = self._next_todo_id
            self._next_todo_id += 1
            item = {
                "id": item_id,
                "task": task,
                "completed": False,
                "created_step": self._step_counter,
                "completed_step": None,
            }
            self._todos[agent_id][item_id] = item
            return self._success(todo=dict(item))

    @tool(readonly=False)
    @idempotent_write
    async def complete_todo(self, agent_id: int, todo_id: int) -> dict:
        """Mark one of your personal tasks as complete.

        :param agent_id: Acting agent ID
        :param todo_id: Task ID returned by add_todo
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            item = self._todos[agent_id].get(int(todo_id))
            if item is None:
                return self._error(f"todo {todo_id} not found")
            if item["completed"]:
                return self._success(todo=dict(item), already_completed=True)
            item["completed"] = True
            item["completed_step"] = self._step_counter
            return self._success(todo=dict(item), already_completed=False)

    @tool(readonly=True)
    async def list_todo(self, agent_id: int) -> dict:
        """View all pending tasks in your personal to-do list.

        :param agent_id: Acting agent ID
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            pending = [
                dict(item)
                for item in self._todos[agent_id].values()
                if not item["completed"]
            ]
            return self._success(todos=pending, count=len(pending))

    @tool(readonly=False)
    @idempotent_write
    async def add_to_calendar(
        self,
        agent_id: int,
        title: str,
        start_at: str,
        end_at: str | None = None,
        description: str = "",
    ) -> dict:
        """Schedule a future event in your personal calendar.

        :param agent_id: Acting agent ID
        :param title: Event title
        :param start_at: ISO 8601 start timestamp, later than simulation time
        :param end_at: Optional ISO 8601 end timestamp, not earlier than start_at
        :param description: Optional event details
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            title = str(title).strip()
            if not title:
                return self._error("title must not be empty")
            try:
                start = self._parse_datetime(start_at, "start_at")
                end = self._parse_datetime(end_at, "end_at") if end_at else None
            except ValueError as exc:
                return self._error(str(exc))
            if start <= self._now():
                return self._error("start_at must be later than simulation time")
            if end is not None and end < start:
                return self._error("end_at must not be earlier than start_at")

            event_id = self._next_event_id
            self._next_event_id += 1
            event = {
                "id": event_id,
                "title": title,
                "start_at": start.isoformat(),
                "end_at": end.isoformat() if end is not None else None,
                "description": str(description),
                "created_step": self._step_counter,
            }
            self._calendar[agent_id][event_id] = event
            return self._success(event=dict(event))

    @tool(readonly=True)
    async def check_calendar(self, agent_id: int, limit: int = 20) -> dict:
        """View upcoming personal calendar entries in chronological order.

        :param agent_id: Acting agent ID
        :param limit: Maximum entries to return, from 1 through 100
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return self._error("limit must be an integer from 1 through 100")
            if not 1 <= limit <= 100:
                return self._error("limit must be an integer from 1 through 100")
            now = self._now()
            upcoming = [
                dict(event)
                for event in self._calendar[agent_id].values()
                if self._parse_datetime(event["start_at"], "start_at") >= now
            ]
            upcoming.sort(key=lambda event: (event["start_at"], event["id"]))
            return {
                "ok": True,
                "status": "success",
                "events": upcoming[:limit],
                "count": min(len(upcoming), limit),
                "total_upcoming": len(upcoming),
            }

    @tool(readonly=False)
    @idempotent_write
    async def remove_from_calendar(self, agent_id: int, event_id: int) -> dict:
        """Cancel an event from your personal calendar.

        :param agent_id: Acting agent ID
        :param event_id: Event ID returned by add_to_calendar
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            event = self._calendar[agent_id].pop(int(event_id), None)
            if event is None:
                return self._error(f"calendar event {event_id} not found")
            return self._success(removed=event)
