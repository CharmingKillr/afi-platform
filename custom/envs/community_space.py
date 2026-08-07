"""Domain-specific community tools for Emergence World.

The public EW catalog contains complaint, community-event, and trust actions.
They are stateful social mechanisms rather than arbitrary records, so this
environment gives them explicit parameters, ownership rules, bounded state,
same-step idempotency, append-only audit events, and workspace recovery.

This module follows the typed/replayable environment pattern introduced by
the PR #2 mobility/relationship environments, but keeps the public EW tool
names stable.  It intentionally depends only on AgentSociety2 and the
standard library because custom environments run inside the AS process.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager


_STATE_REL = "state/COMMUNITY_STATE.json"
_EVENT_LOG_REL = "state/community_event_log.jsonl"
_VALID_COMPLAINT_STATUS = {"submitted", "acknowledged", "resolved", "closed"}
_VALID_EVENT_STATUS = {"proposed", "scheduled", "cancelled", "completed"}
_CLAIM_STATUSES = {"unverified", "supported", "refuted", "blocked"}
_MAX_TEXT = 10_000
_MAX_EVENTS = 20_000
_MAX_QUERY_ITEMS = 100


class CommunitySpace(EnvBase):
    """Auditable community complaints, events, and trust ratings."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("complaints_filed", "INTEGER"),
        ColumnDef("events_proposed", "INTEGER"),
        ColumnDef("trust_ratings_given", "INTEGER"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("complaint_count", "INTEGER"),
        ColumnDef("open_complaints", "INTEGER"),
        ColumnDef("community_event_count", "INTEGER"),
        ColumnDef("trust_pair_count", "INTEGER"),
        ColumnDef("audit_event_count", "INTEGER"),
        ColumnDef("next_complaint_id", "INTEGER"),
        ColumnDef("next_event_id", "INTEGER"),
    ]

    def __init__(
        self,
        agent_ids: list[int] | None = None,
        case_id: str = "",
        default_claim_status: str = "unverified",
        max_events: int = _MAX_EVENTS,
        enabled_tools: list[str] | None = None,
        **kwargs,
    ):
        # Keeping unknown kwargs non-fatal is consistent with the other custom
        # environments and makes scenario configs forward-compatible.
        super().__init__()
        self._agent_ids = [int(agent_id) for agent_id in (agent_ids or [1, 2, 3, 4, 5])]
        if not self._agent_ids or len(self._agent_ids) != len(set(self._agent_ids)):
            raise ValueError("agent_ids must be a non-empty list of unique IDs")
        self._case_id = str(case_id or "").strip() or None
        self._default_claim_status = str(default_claim_status or "unverified").strip().lower()
        if self._default_claim_status not in _CLAIM_STATUSES:
            raise ValueError(f"unknown default_claim_status: {self._default_claim_status}")
        self._max_events = max(1000, int(max_events))
        self._complaints: dict[int, dict] = {}
        self._events: dict[int, dict] = {}
        self._trust: dict[str, dict] = {}
        self._audit_events: list[dict] = []
        self._dedup: dict[str, dict] = {}
        self._next_complaint_id = 1
        self._next_event_id = 1
        self._next_audit_event_id = 1
        self._step_counter = 0
        self._pending_replay_rows: list[dict] = []
        self._lock = asyncio.Lock()

        registered_names = set(self._registered_tools)
        requested = registered_names if enabled_tools is None else {str(name) for name in enabled_tools}
        if enabled_tools is not None and len(list(enabled_tools)) != len(requested):
            raise ValueError("enabled_tools must not contain duplicate names")
        unknown = requested - registered_names
        if unknown:
            raise ValueError(f"unknown CommunitySpace tools: {sorted(unknown)}")
        self._enabled_tools = sorted(requested)
        self._tool_manager = ToolManager(
            tools=[obj for name, obj in self._registered_tools.items() if name in requested]
        )
        self._llm_tools = [
            item for item in self._llm_tools
            if item["function"]["name"] in requested
        ]
        self._readonly_llm_tools = [
            item for item in self._readonly_llm_tools
            if item["function"]["name"] in requested
        ]

    @classmethod
    def description(cls) -> str:
        return "Auditable EW community tools: complaints, events, and trust ratings."

    @classmethod
    def init_description(cls) -> str:
        return """CommunitySpace implements six EW community tools.

Complaints have an owner, category, status, and case/evidence metadata.
Community events have a proposed-to-completed lifecycle, and trust ratings
replace the current rater-to-target value while retaining an append-only
rating history.  Read tools do not expose another agent's complaint body.
Identical writes in the same simulation step are idempotent and all state can
be restored from COMMUNITY_STATE.json plus community_event_log.jsonl.
"""

    @staticmethod
    def _success(**payload) -> dict:
        return {"status": "success", **payload}

    @staticmethod
    def _fail(reason: str, **payload) -> dict:
        return {"status": "fail", "reason": reason, **payload}

    @staticmethod
    def _text(value: str | None, field: str, *, required: bool = True, maximum: int = _MAX_TEXT):
        if value is None:
            return (None, f"{field} is required") if required else (None, None)
        if not isinstance(value, str):
            return None, f"{field} must be a string"
        value = value.strip()
        if required and not value:
            return None, f"{field} must not be empty"
        if len(value) > maximum:
            return None, f"{field} must be at most {maximum} characters"
        return value, None

    def _known_agent(self, agent_id: int) -> bool:
        return int(agent_id) in self._agent_ids

    def _metadata(
        self,
        case_id: str | None,
        artifact_id: str | None,
        claim_status: str | None,
        evidence_refs: list[str] | None,
    ) -> tuple[dict | None, str | None]:
        normalized_case = str(case_id if case_id is not None else (self._case_id or "")).strip()
        if self._case_id and normalized_case != self._case_id:
            return None, f"case_id must be {self._case_id}"
        normalized_artifact = None if artifact_id is None else str(artifact_id).strip()
        if normalized_artifact is not None and (not normalized_artifact or len(normalized_artifact) > 160):
            return None, "artifact_id must be a non-empty string of at most 160 characters"
        status = str(
            claim_status if claim_status is not None else self._default_claim_status
        ).strip().lower()
        if status not in _CLAIM_STATUSES:
            return None, f"claim_status must be one of {sorted(_CLAIM_STATUSES)}"
        refs = [] if evidence_refs is None else evidence_refs
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            return None, "evidence_refs must be a list of non-empty strings"
        if status == "supported" and not refs:
            return None, "supported claims require at least one evidence_refs item"
        return {
            "case_id": normalized_case or None,
            "artifact_id": normalized_artifact,
            "claim_status": status,
            "evidence_refs": [ref.strip() for ref in refs],
        }, None

    def _key(self, tool_name: str, agent_id: int, args: tuple, kwargs: dict) -> str:
        return json.dumps(
            [self._step_counter, tool_name, int(agent_id), args, kwargs],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _record(self, action: str, agent_id: int, *, readonly: bool = False, **details) -> dict:
        event = {
            "event_id": self._next_audit_event_id,
            "action": action,
            "agent_id": int(agent_id),
            "readonly": readonly,
            "step": self._step_counter,
            "t": str(getattr(self, "t", "")),
            **details,
        }
        self._next_audit_event_id += 1
        self._audit_events.append(event)
        if len(self._audit_events) > self._max_events:
            del self._audit_events[: len(self._audit_events) - self._max_events]
        return event

    def _write_once(self, key: str, mutate) -> dict:
        cached = self._dedup.get(key)
        if cached is not None:
            return {**copy.deepcopy(cached), "deduplicated": True}
        result = mutate()
        if result.get("status") == "success":
            self._dedup[key] = copy.deepcopy(result)
        return result

    def _limit(self, limit: int) -> int:
        try:
            return min(_MAX_QUERY_ITEMS, max(1, int(limit)))
        except (TypeError, ValueError):
            return 20

    def _trust_key(self, rater_id: int, target_id: int) -> str:
        return f"{int(rater_id)}:{int(target_id)}"

    def _counts(self) -> dict[str, int]:
        return {
            "complaint_count": len(self._complaints),
            "open_complaints": sum(
                1 for complaint in self._complaints.values()
                if complaint["status"] not in {"resolved", "closed"}
            ),
            "community_event_count": len(self._events),
            "trust_pair_count": len(self._trust),
            "audit_event_count": len(self._audit_events),
            "next_complaint_id": self._next_complaint_id,
            "next_event_id": self._next_event_id,
        }

    def _agent_counts(self, agent_id: int) -> dict[str, int]:
        return {
            "agent_id": int(agent_id),
            "complaints_filed": sum(1 for item in self._complaints.values() if item["owner_id"] == agent_id),
            "events_proposed": sum(1 for item in self._events.values() if item["owner_id"] == agent_id),
            "trust_ratings_given": sum(1 for item in self._trust.values() if item["rater_id"] == agent_id),
        }

    async def step(self, tick: int, t: datetime) -> None:
        async with self._lock:
            self.t = t
            self._step_counter += 1
            self._dedup.clear()
            for agent_id in self._agent_ids:
                self._pending_replay_rows.append({
                    **self._agent_counts(agent_id),
                    "step": self._step_counter,
                    "t": t.isoformat(),
                })
        await self.to_workspace()

    async def close(self) -> None:
        await self.to_workspace()

    async def get_env_state(self) -> dict:
        return self._counts()

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        root = self._workspace_root
        if root is None:
            return
        root = Path(root)
        state = {
            "agent_ids": self._agent_ids,
            "case_id": self._case_id,
            "default_claim_status": self._default_claim_status,
            "complaints": {str(k): v for k, v in self._complaints.items()},
            "events": {str(k): v for k, v in self._events.items()},
            "trust": self._trust,
            "audit_events": self._audit_events,
            "dedup": self._dedup,
            "next_complaint_id": self._next_complaint_id,
            "next_event_id": self._next_event_id,
            "next_audit_event_id": self._next_audit_event_id,
            "step_counter": self._step_counter,
            "current_time": getattr(self, "t", None).isoformat() if getattr(self, "t", None) else None,
        }
        atomic_write_text(root / _STATE_REL, json.dumps(state, ensure_ascii=False, indent=2))
        atomic_write_text(
            root / _EVENT_LOG_REL,
            "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in self._audit_events),
        )
        if self._pending_replay_rows:
            replay_dir = root.parent.parent / "replay"
            replay_dir.mkdir(parents=True, exist_ok=True)
            shard = replay_dir / f"community_agent_state.{self._step_counter:06d}.jsonl"
            atomic_write_text(
                shard,
                "\n".join(json.dumps(row, ensure_ascii=False) for row in self._pending_replay_rows) + "\n",
            )
            self._pending_replay_rows = []

    async def restore(self, workspace_path=None) -> bool:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        root = self._workspace_root
        if root is None:
            return False
        path = Path(root) / _STATE_REL
        if not path.is_file():
            return False
        state = json.loads(path.read_text(encoding="utf-8"))
        ids = [int(agent_id) for agent_id in state.get("agent_ids", [])]
        if not ids:
            raise ValueError("CommunitySpace state has no agent IDs")
        self._agent_ids = ids
        self._case_id = state.get("case_id") or None
        self._default_claim_status = state.get("default_claim_status", "unverified")
        self._complaints = {int(k): v for k, v in state.get("complaints", {}).items()}
        self._events = {int(k): v for k, v in state.get("events", {}).items()}
        self._trust = state.get("trust", {})
        self._audit_events = state.get("audit_events", [])
        self._dedup = state.get("dedup", {})
        self._next_complaint_id = int(state.get("next_complaint_id", 1))
        self._next_event_id = int(state.get("next_event_id", 1))
        self._next_audit_event_id = int(
            state.get(
                "next_audit_event_id",
                max((int(event.get("event_id", 0)) for event in self._audit_events), default=0) + 1,
            )
        )
        self._step_counter = int(state.get("step_counter", 0))
        current_time = state.get("current_time")
        if current_time:
            self.t = datetime.fromisoformat(current_time)
        self._lock = asyncio.Lock()
        self._pending_replay_rows = []
        return True

    @tool(readonly=False)
    async def file_complaint(
        self,
        agent_id: int,
        content: str,
        category: str = "general",
        location: str | None = None,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """File an owned complaint in the ``submitted`` state."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            content, error = self._text(content, "content")
            if error:
                return self._fail(error)
            category, error = self._text(category, "category", maximum=160)
            if error:
                return self._fail(error)
            location, error = self._text(location, "location", required=False, maximum=240)
            if error:
                return self._fail(error)
            metadata, error = self._metadata(case_id, artifact_id, claim_status, evidence_refs)
            if error:
                return self._fail(error)
            key = self._key("file_complaint", agent_id, (content, category, location), metadata)

            def mutate() -> dict:
                complaint_id = self._next_complaint_id
                self._next_complaint_id += 1
                complaint = {
                    "id": complaint_id,
                    "owner_id": agent_id,
                    "content": content,
                    "category": category,
                    "location": location,
                    "status": "submitted",
                    "created_step": self._step_counter,
                    **metadata,
                }
                self._complaints[complaint_id] = complaint
                self._record(
                    "complaint_submitted",
                    agent_id,
                    item_id=complaint_id,
                    case_id=complaint.get("case_id"),
                    artifact_id=complaint.get("artifact_id"),
                )
                return self._success(complaint=dict(complaint))

            return self._write_once(key, mutate)

    @tool(readonly=True)
    async def check_complaint_status(self, agent_id: int, complaint_id: int) -> dict:
        """Read a complaint status; only its owner receives the body."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            complaint = self._complaints.get(int(complaint_id))
            if complaint is None:
                return self._fail("complaint not found")
            self._record("complaint_status_read", agent_id, readonly=True, item_id=int(complaint_id))
            if complaint["owner_id"] == agent_id:
                view = dict(complaint)
            else:
                view = {
                    key: complaint[key]
                    for key in (
                        "id", "category", "location", "status", "created_step",
                        "case_id", "artifact_id", "claim_status", "evidence_refs",
                    )
                    if key in complaint
                }
            return self._success(complaint=view, owner_view=complaint["owner_id"] == agent_id)

    @tool(readonly=False)
    async def propose_community_event(
        self,
        agent_id: int,
        title: str,
        description: str,
        location: str,
        starts_at: str | None = None,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Create an event in the ``proposed`` lifecycle state."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            fields = {}
            for value, field, maximum in (
                (title, "title", 240), (description, "description", _MAX_TEXT),
                (location, "location", 240),
            ):
                normalized, error = self._text(value, field, maximum=maximum)
                if error:
                    return self._fail(error)
                fields[field] = normalized
            starts_at, error = self._text(starts_at, "starts_at", required=False, maximum=80)
            if error:
                return self._fail(error)
            metadata, error = self._metadata(case_id, artifact_id, claim_status, evidence_refs)
            if error:
                return self._fail(error)
            key = self._key("propose_community_event", agent_id, (fields, starts_at), metadata)

            def mutate() -> dict:
                event_id = self._next_event_id
                self._next_event_id += 1
                event = {
                    "id": event_id,
                    "owner_id": agent_id,
                    **fields,
                    "starts_at": starts_at,
                    "status": "proposed",
                    "created_step": self._step_counter,
                    **metadata,
                }
                self._events[event_id] = event
                self._record(
                    "community_event_proposed",
                    agent_id,
                    item_id=event_id,
                    case_id=event.get("case_id"),
                    artifact_id=event.get("artifact_id"),
                )
                return self._success(event=dict(event))

            return self._write_once(key, mutate)

    @tool(readonly=True)
    async def list_community_events(
        self,
        agent_id: int,
        status: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List bounded community events, optionally filtered by lifecycle state."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            if status is not None and status not in _VALID_EVENT_STATUS:
                return self._fail(f"status must be one of {sorted(_VALID_EVENT_STATUS)}")
            events = list(self._events.values())
            if status:
                events = [event for event in events if event["status"] == status]
            self._record("community_events_listed", agent_id, readonly=True, count=len(events))
            return self._success(events=events[-self._limit(limit):], count=len(events))

    @tool(readonly=False)
    async def rate_agent_trust(
        self,
        agent_id: int,
        target_id: int,
        rating: int,
        reason: str,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Write or replace a rater-to-target trust value and retain its history."""
        async with self._lock:
            agent_id, target_id = int(agent_id), int(target_id)
            if not self._known_agent(agent_id) or not self._known_agent(target_id):
                return self._fail("unknown agent_id or target_id")
            if agent_id == target_id:
                return self._fail("an agent cannot rate itself")
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                return self._fail("rating must be an integer from 1 to 5")
            if not 1 <= rating <= 5:
                return self._fail("rating must be an integer from 1 to 5")
            reason, error = self._text(reason, "reason", maximum=2000)
            if error:
                return self._fail(error)
            metadata, error = self._metadata(case_id, artifact_id, claim_status, evidence_refs)
            if error:
                return self._fail(error)
            key = self._key("rate_agent_trust", agent_id, (target_id, rating, reason), metadata)

            def mutate() -> dict:
                trust_key = self._trust_key(agent_id, target_id)
                previous = self._trust.get(trust_key)
                record = {
                    "rater_id": agent_id,
                    "target_id": target_id,
                    "rating": rating,
                    "reason": reason,
                    "step": self._step_counter,
                    **metadata,
                }
                self._trust[trust_key] = record
                self._record(
                    "trust_rating_written", agent_id,
                    target_id=target_id, previous_rating=previous.get("rating") if previous else None,
                    rating=rating,
                    case_id=record.get("case_id"),
                    artifact_id=record.get("artifact_id"),
                )
                return self._success(rating=dict(record), replaced=previous is not None)

            return self._write_once(key, mutate)

    @tool(readonly=True)
    async def check_agent_trust(self, agent_id: int, target_id: int) -> dict:
        """Read the public aggregate trust summary for an agent."""
        async with self._lock:
            agent_id, target_id = int(agent_id), int(target_id)
            if not self._known_agent(agent_id) or not self._known_agent(target_id):
                return self._fail("unknown agent_id or target_id")
            ratings = [item for item in self._trust.values() if item["target_id"] == target_id]
            distribution = {str(value): sum(1 for item in ratings if item["rating"] == value) for value in range(1, 6)}
            self._record("trust_summary_read", agent_id, readonly=True, target_id=target_id, count=len(ratings))
            return self._success(
                target_id=target_id,
                average=sum(item["rating"] for item in ratings) / len(ratings) if ratings else None,
                ratings=len(ratings),
                distribution=distribution,
                case_id=self._case_id,
                artifact_ids=sorted({item["artifact_id"] for item in ratings if item.get("artifact_id")}),
                evidence_refs=sorted({ref for item in ratings for ref in item.get("evidence_refs", [])}),
            )
