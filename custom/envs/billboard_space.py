"""Domain-specific public Billboard tools for Emergence World.

The Billboard is a public expression surface, not a generic key/value record
store.  This environment gives each post a stable artifact id, an owner,
case/evidence metadata, explicit parent-child replies, one reaction per agent,
soft deletion, append-only audit events, replay snapshots, and workspace
restore.  It intentionally depends only on AgentSociety2 and the standard
library because custom environments are loaded inside the AgentSociety
process.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime
from typing import ClassVar

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager


_STATE_REL = "state/BILLBOARD_STATE.json"
_EVENT_LOG_REL = "state/billboard_event_log.jsonl"
_CLAIM_STATUSES = {"unverified", "supported", "refuted", "blocked"}
_REACTIONS = {"thumbs_up", "thumbs_down", "question", "flag"}
_MAX_CONTENT = 10_000
_MAX_TOPIC = 160
_MAX_EVIDENCE_REFS = 50
_MAX_REF_LENGTH = 240


class BillboardSpace(EnvBase):
    """Public Billboard with explicit evidence and interaction semantics."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("posts_created", "INTEGER"),
        ColumnDef("replies_created", "INTEGER"),
        ColumnDef("reactions_cast", "INTEGER"),
        ColumnDef("posts_deleted", "INTEGER"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("active_posts", "INTEGER"),
        ColumnDef("deleted_posts", "INTEGER"),
        ColumnDef("reply_count", "INTEGER"),
        ColumnDef("reaction_count", "INTEGER"),
        ColumnDef("public_expression_count", "INTEGER"),
        ColumnDef("event_count", "INTEGER"),
        ColumnDef("next_post_id", "INTEGER"),
    ]

    def __init__(
        self,
        agent_ids: list[int] | None = None,
        case_id: str = "",
        default_claim_status: str = "unverified",
        max_events: int = 20_000,
        enabled_tools: list[str] | None = None,
        **kwargs,
    ):
        if kwargs:
            # Keep construction forward-compatible while making accidental
            # config drift visible in the AS process logs.
            import logging

            logging.getLogger(__name__).warning(
                "BillboardSpace unknown kwargs ignored: %s", sorted(kwargs)
            )
        super().__init__()
        self._agent_ids = [int(agent_id) for agent_id in (agent_ids or [1, 2, 3, 4, 5])]
        if not self._agent_ids or len(self._agent_ids) != len(set(self._agent_ids)):
            raise ValueError("agent_ids must be a non-empty list of unique IDs")
        self._case_id = str(case_id or "").strip() or None
        self._default_claim_status = str(default_claim_status or "unverified").strip().lower()
        if self._default_claim_status not in _CLAIM_STATUSES:
            raise ValueError(f"unknown default_claim_status: {self._default_claim_status}")
        self._max_events = max(1000, int(max_events))
        self._posts: dict[int, dict] = {}
        self._next_post_id = 1
        self._step_counter = 0
        self._next_event_id = 1
        self._events: list[dict] = []
        self._dedup: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self.t = datetime.min

        registered_names = set(self._registered_tools)
        if enabled_tools is None:
            allowed_tools = registered_names
        else:
            requested = [str(name) for name in enabled_tools]
            if len(requested) != len(set(requested)):
                raise ValueError("enabled_tools must not contain duplicate names")
            unknown = set(requested) - registered_names
            if unknown:
                raise ValueError(f"unknown BillboardSpace tools: {sorted(unknown)}")
            allowed_tools = set(requested)
        self._enabled_tools = sorted(allowed_tools)
        self._tool_manager = ToolManager(
            tools=[
                tool_obj
                for name, tool_obj in self._registered_tools.items()
                if name in allowed_tools
            ]
        )
        self._llm_tools = [
            item for item in self._llm_tools
            if item["function"]["name"] in allowed_tools
        ]
        self._readonly_llm_tools = [
            item for item in self._readonly_llm_tools
            if item["function"]["name"] in allowed_tools
        ]

    @classmethod
    def description(cls) -> str:
        return "Public evidence Billboard with owner-controlled posts, replies, reactions, and audit history."

    @classmethod
    def init_description(cls) -> str:
        return """BillboardSpace models the public expression stage of a case.

Every post is a public artifact with a stable id, owner, creation step, and
case/evidence metadata. Replies retain their parent artifact id. A post owner
may edit or soft-delete the post; deletion remains visible in the audit state.
An agent may cast at most one reaction per post. Same-step retries of an
identical write are idempotent.

PIC-001 requires ``case_id`` and keeps ``claim_status`` explicit. A
``supported`` claim must include at least one ``evidence_refs`` item; local
references are metadata and are not external fact verification.
"""

    @staticmethod
    def _success(**payload) -> dict:
        return {"status": "success", **payload}

    @staticmethod
    def _fail(reason: str, **payload) -> dict:
        return {"status": "fail", "reason": reason, **payload}

    @staticmethod
    def _deduplicated(result: dict) -> dict:
        """Return a cached successful result with an explicit retry marker."""
        payload = copy.deepcopy(result)
        payload["deduplicated"] = True
        return payload

    def _known_agent(self, agent_id: int) -> bool:
        return int(agent_id) in self._agent_ids

    @staticmethod
    def _text(value: str | None, field: str, maximum: int, *, required: bool = False) -> tuple[str | None, str | None]:
        if value is None:
            return (None, f"request.{field} is required") if required else (None, None)
        if not isinstance(value, str):
            return None, f"{field} must be a string"
        value = value.strip()
        if not value and required:
            return None, f"{field} must not be empty"
        if len(value) > maximum:
            return None, f"{field} must be at most {maximum} characters"
        return value, None

    def _validate_metadata(
        self,
        *,
        case_id: str | None,
        claim_status: str | None,
        evidence_refs: list[str] | None,
        expected_case_id: str | None = None,
    ) -> tuple[dict | None, str | None]:
        normalized_case = str(case_id if case_id is not None else (self._case_id or "")).strip()
        if self._case_id and normalized_case != self._case_id:
            return None, f"case_id must be {self._case_id}"
        if expected_case_id and normalized_case != expected_case_id:
            return None, "parent and child case_id must match"
        if self._case_id and not normalized_case:
            return None, "case_id is required for a case-scoped Billboard artifact"

        normalized_status = str(
            claim_status if claim_status is not None else self._default_claim_status
        ).strip().lower()
        if normalized_status not in _CLAIM_STATUSES:
            return None, f"claim_status must be one of {sorted(_CLAIM_STATUSES)}"

        refs = [] if evidence_refs is None else evidence_refs
        if not isinstance(refs, list):
            return None, "evidence_refs must be a list"
        if len(refs) > _MAX_EVIDENCE_REFS:
            return None, f"evidence_refs must contain at most {_MAX_EVIDENCE_REFS} items"
        normalized_refs: list[str] = []
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                return None, "evidence_refs items must be non-empty strings"
            ref = ref.strip()
            if len(ref) > _MAX_REF_LENGTH:
                return None, f"each evidence_refs item must be at most {_MAX_REF_LENGTH} characters"
            normalized_refs.append(ref)
        if normalized_status == "supported" and not normalized_refs:
            return None, "supported claims require at least one evidence_refs item"
        return {
            "case_id": normalized_case or None,
            "claim_status": normalized_status,
            "evidence_refs": normalized_refs,
        }, None

    @staticmethod
    def _request_key(tool_name: str, agent_id: int, request: dict, step: int) -> str:
        return json.dumps(
            [step, tool_name, int(agent_id), request],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _write_once(self, tool_name: str, agent_id: int, request: dict, mutate) -> dict:
        key = self._request_key(tool_name, agent_id, request, self._step_counter)
        cached = self._dedup.get(key)
        if cached is not None:
            return {**copy.deepcopy(cached), "deduplicated": True}
        result = mutate()
        if result.get("status") == "success":
            self._dedup[key] = copy.deepcopy(result)
        return result

    def _new_post_id(self) -> int:
        post_id = self._next_post_id
        self._next_post_id += 1
        return post_id

    def _artifact_exists(self, artifact_id: str) -> bool:
        for post in self._posts.values():
            if post.get("artifact_id") == artifact_id:
                return True
            if any(reply.get("artifact_id") == artifact_id for reply in post.get("replies", [])):
                return True
        return False

    def _record_event(self, action: str, agent_id: int, *, item_id: int | None = None, **details) -> dict:
        event = {
            "event_id": self._next_event_id,
            "action": action,
            "agent_id": int(agent_id),
            "item_id": item_id,
            "step": self._step_counter,
            "t": str(self.t),
            **details,
        }
        self._next_event_id += 1
        self._events.append(event)
        if len(self._events) > self._max_events:
            del self._events[: len(self._events) - self._max_events]
        return event

    def _post(self, item_id: int) -> dict | None:
        return self._posts.get(int(item_id))

    def _active_post(self, item_id: int) -> tuple[dict | None, dict | None]:
        post = self._post(item_id)
        if post is None:
            return None, self._fail("billboard item not found")
        if post.get("deleted"):
            return None, self._fail("billboard item has been soft-deleted")
        return post, None

    def _counts(self) -> dict[str, int]:
        active = [post for post in self._posts.values() if not post.get("deleted")]
        replies = sum(len(post.get("replies", [])) for post in active)
        reactions = sum(len(post.get("reactions", {})) for post in active)
        expression_actions = {"post_created", "reply_created", "reaction_cast"}
        public_expression_count = sum(
            1 for event in self._events if event.get("action") in expression_actions
        )
        return {
            "active_posts": len(active),
            "deleted_posts": sum(1 for post in self._posts.values() if post.get("deleted")),
            "reply_count": replies,
            "reaction_count": reactions,
            # This is cumulative expression volume. Active/deleted counts are
            # reported separately so a later soft-delete does not erase the
            # fact that a public expression happened.
            "public_expression_count": public_expression_count,
            "event_count": len(self._events),
            "next_post_id": self._next_post_id,
        }

    def _agent_counts(self, agent_id: int) -> dict[str, int]:
        posts = list(self._posts.values())
        return {
            "agent_id": int(agent_id),
            "posts_created": sum(1 for post in posts if post.get("owner_id") == agent_id),
            "replies_created": sum(
                1
                for post in posts
                for reply in post.get("replies", [])
                if reply.get("owner_id") == agent_id
            ),
            "reactions_cast": sum(
                1
                for post in posts
                for reaction in post.get("reactions", {}).values()
                if reaction.get("agent_id") == agent_id
            ),
            "posts_deleted": sum(1 for post in posts if post.get("deleted_by") == agent_id),
        }

    # ── public tools ─────────────────────────────────────────────────────

    @tool(readonly=False)
    async def add_to_billboard(
        self,
        agent_id: int,
        content: str,
        topic: str | None = None,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Create a public Billboard post with explicit case metadata."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            content, error = self._text(content, "content", _MAX_CONTENT, required=True)
            if error:
                return self._fail(error)
            topic, error = self._text(topic, "topic", _MAX_TOPIC)
            if error:
                return self._fail(error)
            metadata, error = self._validate_metadata(
                case_id=case_id, claim_status=claim_status, evidence_refs=evidence_refs
            )
            if error:
                return self._fail(error)
            artifact = str(artifact_id).strip() if artifact_id is not None else ""
            if artifact and self._artifact_exists(artifact):
                return self._fail("artifact_id already exists")
            request = {
                "content": content,
                "topic": topic,
                "case_id": metadata["case_id"],
                "artifact_id": artifact or None,
                "claim_status": metadata["claim_status"],
                "evidence_refs": metadata["evidence_refs"],
            }

            def mutate() -> dict:
                item_id = self._new_post_id()
                record = {
                    "id": item_id,
                    "artifact_id": artifact or f"billboard:{item_id}",
                    "owner_id": agent_id,
                    "content": content,
                    "topic": topic,
                    **metadata,
                    "created_step": self._step_counter,
                    "updated_step": self._step_counter,
                    "deleted": False,
                    "replies": [],
                    "reactions": {},
                }
                self._posts[item_id] = record
                event = self._record_event("post_created", agent_id, item_id=item_id, artifact_id=record["artifact_id"])
                return self._success(item=copy.deepcopy(record), event=event)

            return self._write_once("add_to_billboard", agent_id, request, mutate)

    @tool(readonly=True)
    async def read_billboard(
        self,
        agent_id: int,
        item_id: int | None = None,
        query: str | None = None,
        case_id: str | None = None,
        claim_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
    ) -> dict:
        """Read active public posts or one post by stable id."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return self._fail("limit must be an integer from 1 through 100")
            if not 1 <= limit <= 100:
                return self._fail("limit must be an integer from 1 through 100")
            if item_id is not None:
                post = self._post(item_id)
                if post is None:
                    return self._fail("billboard item not found")
                if post.get("deleted") and not (include_deleted and post.get("owner_id") == agent_id):
                    return self._fail("billboard item has been soft-deleted")
                return self._success(item=copy.deepcopy(post), case_id=self._case_id)

            normalized_case = str(case_id).strip() if case_id is not None else None
            normalized_status = str(claim_status).strip().lower() if claim_status is not None else None
            if normalized_status is not None and normalized_status not in _CLAIM_STATUSES:
                return self._fail(f"claim_status must be one of {sorted(_CLAIM_STATUSES)}")
            posts = []
            for post in self._posts.values():
                if post.get("deleted") and not (include_deleted and post.get("owner_id") == agent_id):
                    continue
                if normalized_case is not None and post.get("case_id") != normalized_case:
                    continue
                if normalized_status is not None and post.get("claim_status") != normalized_status:
                    continue
                if query and str(query).lower() not in json.dumps(post, ensure_ascii=False).lower():
                    continue
                posts.append(copy.deepcopy(post))
            posts = posts[-limit:]
            return self._success(items=posts, count=len(posts), case_id=self._case_id)

    @tool(readonly=False)
    async def edit_billboard(
        self,
        agent_id: int,
        item_id: int,
        content: str | None = None,
        topic: str | None = None,
        case_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Edit an owned active post while preserving its stable artifact id."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            post, error_result = self._active_post(item_id)
            if error_result:
                return error_result
            if post["owner_id"] != agent_id:
                return self._fail("only the post owner may edit")
            changes: dict = {}
            if content is not None:
                content, error = self._text(content, "content", _MAX_CONTENT, required=True)
                if error:
                    return self._fail(error)
                changes["content"] = content
            if topic is not None:
                topic, error = self._text(topic, "topic", _MAX_TOPIC)
                if error:
                    return self._fail(error)
                changes["topic"] = topic
            metadata_requested = any(value is not None for value in (case_id, claim_status, evidence_refs))
            if metadata_requested:
                metadata, error = self._validate_metadata(
                    case_id=case_id if case_id is not None else post.get("case_id"),
                    claim_status=claim_status if claim_status is not None else post.get("claim_status"),
                    evidence_refs=evidence_refs if evidence_refs is not None else post.get("evidence_refs", []),
                    expected_case_id=post.get("case_id"),
                )
                if error:
                    return self._fail(error)
                changes.update(metadata)
            if not changes:
                return self._fail("at least one editable field is required")
            request = {"item_id": int(item_id), **changes}

            def mutate() -> dict:
                post.update(changes)
                post["updated_step"] = self._step_counter
                event = self._record_event("post_edited", agent_id, item_id=int(item_id), fields=sorted(changes))
                return self._success(item=copy.deepcopy(post), event=event)

            return self._write_once("edit_billboard", agent_id, request, mutate)

    @tool(readonly=False)
    async def delete_from_billboard(self, agent_id: int, item_id: int) -> dict:
        """Soft-delete an owned post while retaining its audit history."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            request = {"item_id": int(item_id)}
            cached = self._dedup.get(
                self._request_key("delete_from_billboard", agent_id, request, self._step_counter)
            )
            if cached is not None:
                return self._deduplicated(cached)
            post, error_result = self._active_post(item_id)
            if error_result:
                return error_result
            if post["owner_id"] != agent_id:
                return self._fail("only the post owner may delete")

            def mutate() -> dict:
                post["deleted"] = True
                post["deleted_by"] = agent_id
                post["deleted_step"] = self._step_counter
                event = self._record_event("post_soft_deleted", agent_id, item_id=int(item_id), artifact_id=post["artifact_id"])
                return self._success(deleted=copy.deepcopy(post), event=event)

            return self._write_once("delete_from_billboard", agent_id, request, mutate)

    @tool(readonly=False)
    async def reply_to_billboard(
        self,
        agent_id: int,
        parent_item_id: int,
        content: str,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Append a public reply linked to an existing parent artifact."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            parent, error_result = self._active_post(parent_item_id)
            if error_result:
                return error_result
            content, error = self._text(content, "content", _MAX_CONTENT, required=True)
            if error:
                return self._fail(error)
            metadata, error = self._validate_metadata(
                case_id=case_id if case_id is not None else parent.get("case_id"),
                claim_status=claim_status if claim_status is not None else parent.get("claim_status"),
                evidence_refs=evidence_refs if evidence_refs is not None else parent.get("evidence_refs", []),
                expected_case_id=parent.get("case_id"),
            )
            if error:
                return self._fail(error)
            artifact = str(artifact_id).strip() if artifact_id is not None else ""
            if artifact and self._artifact_exists(artifact):
                return self._fail("artifact_id already exists")
            request = {
                "parent_item_id": int(parent_item_id),
                "content": content,
                "case_id": metadata["case_id"],
                "artifact_id": artifact or None,
                "claim_status": metadata["claim_status"],
                "evidence_refs": metadata["evidence_refs"],
            }

            def mutate() -> dict:
                reply_id = self._new_post_id()
                reply = {
                    "id": reply_id,
                    "artifact_id": artifact or f"billboard-reply:{reply_id}",
                    "parent_artifact_id": parent["artifact_id"],
                    "owner_id": agent_id,
                    "content": content,
                    **metadata,
                    "created_step": self._step_counter,
                }
                parent.setdefault("replies", []).append(reply)
                event = self._record_event(
                    "reply_created",
                    agent_id,
                    item_id=int(parent_item_id),
                    reply_id=reply_id,
                    parent_artifact_id=parent["artifact_id"],
                )
                return self._success(item=copy.deepcopy(reply), parent_item_id=int(parent_item_id), event=event)

            return self._write_once("reply_to_billboard", agent_id, request, mutate)

    @tool(readonly=False)
    async def react_to_billboard(self, agent_id: int, item_id: int, reaction: str) -> dict:
        """Cast one controlled reaction per agent on an active post."""
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._fail("unknown agent_id")
            post, error_result = self._active_post(item_id)
            if error_result:
                return error_result
            reaction = str(reaction).strip().lower()
            if reaction not in _REACTIONS:
                return self._fail(f"reaction must be one of {sorted(_REACTIONS)}")
            request = {"item_id": int(item_id), "reaction": reaction}
            cached = self._dedup.get(
                self._request_key("react_to_billboard", agent_id, request, self._step_counter)
            )
            if cached is not None:
                return self._deduplicated(cached)
            if str(agent_id) in post.setdefault("reactions", {}):
                return self._fail("one reaction per agent per Billboard post")

            def mutate() -> dict:
                record = {
                    "agent_id": agent_id,
                    "reaction": reaction,
                    "artifact_id": post["artifact_id"],
                    "case_id": post.get("case_id"),
                    "step": self._step_counter,
                }
                post["reactions"][str(agent_id)] = record
                event = self._record_event("reaction_cast", agent_id, item_id=int(item_id), reaction=reaction)
                return self._success(reaction=copy.deepcopy(record), item_id=int(item_id), event=event)

            return self._write_once("react_to_billboard", agent_id, request, mutate)

    # ── replay / workspace persistence ──────────────────────────────────

    async def step(self, tick: int, t: datetime):
        """Advance the internal replay step; ``tick`` is duration, not a key."""
        self.t = t
        self._step_counter += 1
        self._dedup.clear()
        counts = self._counts()
        await self._write_env_state(self._step_counter, t, **counts)
        await self._write_agent_state_batch(
            self._step_counter,
            t,
            [self._agent_counts(agent_id) for agent_id in self._agent_ids],
        )

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("BillboardSpace workspace is not bound")
        state = {
            "_agent_ids": self._agent_ids,
            "_case_id": self._case_id,
            "_default_claim_status": self._default_claim_status,
            "_max_events": self._max_events,
            "_enabled_tools": self._enabled_tools,
            "_posts": self._posts,
            "_next_post_id": self._next_post_id,
            "_step_counter": self._step_counter,
            "_next_event_id": self._next_event_id,
            "_events": self._events,
            "_dedup": self._dedup,
        }
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
        )
        atomic_write_text(
            self._workspace_root / _EVENT_LOG_REL,
            "".join(json.dumps(event, ensure_ascii=False, default=str) + "\n" for event in self._events),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        state_path = self._workspace_root / _STATE_REL
        if not state_path.is_file():
            return False
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self._agent_ids = [int(agent_id) for agent_id in state.get("_agent_ids", self._agent_ids)]
        self._case_id = state.get("_case_id")
        self._default_claim_status = state.get("_default_claim_status", self._default_claim_status)
        self._max_events = int(state.get("_max_events", self._max_events))
        self._posts = {
            int(item_id): value for item_id, value in state.get("_posts", {}).items()
        }
        self._next_post_id = int(state.get("_next_post_id", 1))
        self._step_counter = int(state.get("_step_counter", 0))
        self._next_event_id = int(state.get("_next_event_id", 1))
        self._events = list(state.get("_events", []))
        self._dedup = dict(state.get("_dedup", {}))
        self._lock = asyncio.Lock()
        return True
