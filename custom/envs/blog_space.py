"""EW content tools as a domain-specific AgentSociety environment.

The public EW catalog exposes six blog operations. This module keeps their
names but gives them a real content contract instead of the generic
``agent_id + request`` envelope used by ``EWToolSpace``.

The module intentionally depends only on AgentSociety2 and the standard
library because it is loaded inside the AS environment process.
"""
from __future__ import annotations

import asyncio
import json
from functools import wraps
from typing import ClassVar

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager


_STATE_REL = "state/BLOG_STATE.json"
_VALID_VISIBILITY = {"public", "private"}
_VALID_STATUS = {"draft", "published"}
_MAX_TITLE = 160
_MAX_CONTENT = 10000
_MAX_COMMENT = 2000
_MAX_BLOGS = 10000
_MAX_COMMENTS_PER_BLOG = 1000


def _idempotent_write(func):
    """Return the first result for an identical write in the same step."""

    @wraps(func)
    async def wrapped(self, *args, **kwargs):
        key = json.dumps(
            [self._step_counter, func.__name__, args, kwargs],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        async with self._dedup_lock:
            if key in self._dedup:
                return {**self._dedup[key], "deduplicated": True}
            result = await func(self, *args, **kwargs)
            if result.get("status") == "success":
                self._dedup[key] = dict(result)
            return result

    return wrapped


class BlogSpace(EnvBase):
    """Domain-specific blog storage for EW's six content tools."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("owned_blogs", "INTEGER"),
        ColumnDef("comments_written", "INTEGER"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("blog_posts", "INTEGER"),
        ColumnDef("published_posts", "INTEGER"),
        ColumnDef("blog_comments", "INTEGER"),
    ]

    def __init__(self, agent_ids: list[int] | None = None, enabled_tools: list[str] | None = None, **kwargs):
        super().__init__()
        ids = [int(agent_id) for agent_id in (agent_ids or [1, 2, 3, 4, 5])]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("agent_ids must be a non-empty list of unique IDs")
        self._agent_ids = ids
        self._blogs: dict[int, dict] = {}
        self._next_blog_id = 1
        self._next_comment_id = 1
        self._step_counter = 0
        self._dedup: dict[str, dict] = {}
        self._events: list[dict] = []
        self._lock = asyncio.Lock()
        self._dedup_lock = asyncio.Lock()

        registered_names = set(self._registered_tools)
        if enabled_tools is None:
            allowed_tools = registered_names
        else:
            requested_names = [str(name) for name in enabled_tools]
            if len(requested_names) != len(set(requested_names)):
                raise ValueError("enabled_tools must not contain duplicate names")
            requested_tools = set(requested_names)
            unknown_tools = requested_tools - registered_names
            if unknown_tools:
                raise ValueError(f"unknown BlogSpace tools: {sorted(unknown_tools)}")
            allowed_tools = requested_tools
        self._enabled_tools = sorted(allowed_tools)
        self._tool_manager = ToolManager(
            tools=[tool_obj for name, tool_obj in self._registered_tools.items() if name in allowed_tools]
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
        return "EW content tools: validated blogs with visibility, lifecycle, comments, and audit state."

    @classmethod
    def init_description(cls) -> str:
        return """BlogSpace implements EW's six content tools.

Each blog has an owner, title, content, visibility (public/private), status
(draft/published), comments, and creation/update steps. Only owners can
update or delete their blogs; private blogs are visible only to their owner.

Tools:
- write_blog(agent_id, title, content, visibility?, status?): create a blog
- update_blog(agent_id, blog_id, title?, content?, visibility?, status?): edit a blog
- delete_blog(agent_id, blog_id): delete an owned blog
- comment_on_blog(agent_id, blog_id, content): add a bounded comment
- list_blogs(agent_id, limit?): list visible blogs
- read_blog(agent_id, blog_id): read a visible blog

PIC-001 may add ``case_id``, ``artifact_id``, ``claim_status`` and
``evidence_refs`` to writes. These fields describe the claim state and
references; they do not certify external truth. ``enabled_tools`` restricts
the active router surface to an exact list.
"""

    @staticmethod
    def _success(**payload) -> dict:
        return {"ok": True, "status": "success", **payload}

    @staticmethod
    def _error(message: str) -> dict:
        return {"ok": False, "status": "fail", "error": message}

    def _known_agent(self, agent_id: int) -> bool:
        return int(agent_id) in self._agent_ids

    @staticmethod
    def _text(value: str, field: str, maximum: int) -> tuple[str | None, str | None]:
        if not isinstance(value, str):
            return None, f"{field} must be a string"
        value = value.strip()
        if not value:
            return None, f"{field} must not be empty"
        if len(value) > maximum:
            return None, f"{field} must be at most {maximum} characters"
        return value, None

    @staticmethod
    def _validate_visibility(visibility: str) -> str | None:
        value = str(visibility).strip().lower()
        return value if value in _VALID_VISIBILITY else None

    @staticmethod
    def _validate_status(status: str) -> str | None:
        value = str(status).strip().lower()
        return value if value in _VALID_STATUS else None

    @staticmethod
    def _validate_case_metadata(
        case_id: str | None,
        artifact_id: str | None,
        claim_status: str | None,
        evidence_refs: list[str] | None,
    ) -> tuple[dict, str | None]:
        allowed_claim_status = {"unverified", "supported", "refuted", "blocked"}
        if case_id is not None:
            case_id = str(case_id).strip()
            if not case_id or len(case_id) > 80:
                return {}, "case_id must be a non-empty string of at most 80 characters"
        if artifact_id is not None:
            artifact_id = str(artifact_id).strip()
            if not artifact_id or len(artifact_id) > 160:
                return {}, "artifact_id must be a non-empty string of at most 160 characters"
        if claim_status is not None:
            claim_status = str(claim_status).strip().lower()
            if claim_status not in allowed_claim_status:
                return {}, f"claim_status must be one of {sorted(allowed_claim_status)}"
        if evidence_refs is not None:
            if not isinstance(evidence_refs, list) or len(evidence_refs) > 50:
                return {}, "evidence_refs must be a list with at most 50 entries"
            normalized_refs = []
            for reference in evidence_refs:
                reference = str(reference).strip()
                if not reference or len(reference) > 500:
                    return {}, "each evidence reference must be non-empty and at most 500 characters"
                normalized_refs.append(reference)
            evidence_refs = normalized_refs
        metadata = {}
        if case_id is not None:
            metadata["case_id"] = case_id
            metadata["claim_status"] = claim_status or "unverified"
        elif claim_status is not None:
            metadata["claim_status"] = claim_status
        if artifact_id is not None:
            metadata["artifact_id"] = artifact_id
        if evidence_refs is not None:
            metadata["evidence_refs"] = evidence_refs
        return metadata, None

    def _visible(self, agent_id: int, blog: dict) -> bool:
        return blog["visibility"] == "public" or blog["owner_id"] == agent_id

    def _record_event(self, kind: str, agent_id: int, blog_id: int, **extra) -> None:
        self._events.append({
            "event": kind,
            "agent_id": agent_id,
            "blog_id": blog_id,
            "step": self._step_counter,
            **extra,
        })
        if len(self._events) > _MAX_BLOGS:
            del self._events[:-_MAX_BLOGS]

    def _validate_agent_and_blog(self, agent_id: int, blog_id: int) -> tuple[int, dict | None, dict | None]:
        agent_id = int(agent_id)
        if not self._known_agent(agent_id):
            return agent_id, None, self._error(f"unknown agent_id {agent_id}")
        blog = self._blogs.get(int(blog_id))
        if blog is None:
            return agent_id, None, self._error(f"blog {blog_id} not found")
        return agent_id, blog, None

    async def step(self, tick: int, t):
        async with self._lock:
            self.t = t
            self._step_counter += 1
            self._dedup.clear()
            for agent_id in self._agent_ids:
                await self._write_agent_state(
                    agent_id,
                    self._step_counter,
                    t,
                    owned_blogs=sum(1 for b in self._blogs.values() if b["owner_id"] == agent_id),
                    comments_written=sum(
                        1
                        for b in self._blogs.values()
                        for comment in b["comments"]
                        if comment["agent_id"] == agent_id
                    ),
                )
            await self._write_env_state(
                self._step_counter,
                t,
                blog_posts=len(self._blogs),
                published_posts=sum(1 for b in self._blogs.values() if b["status"] == "published"),
                blog_comments=sum(len(b["comments"]) for b in self._blogs.values()),
            )

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("BlogSpace workspace is not bound")
        async with self._lock:
            current_time = getattr(self, "t", None)
            state = {
                "agent_ids": self._agent_ids,
                "blogs": {str(blog_id): blog for blog_id, blog in self._blogs.items()},
                "next_blog_id": self._next_blog_id,
                "next_comment_id": self._next_comment_id,
                "step_counter": self._step_counter,
                "dedup": self._dedup,
                "events": self._events,
                "current_time": current_time.isoformat() if current_time else None,
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
            raise ValueError("BlogSpace state has no agent IDs")
        self._agent_ids = ids
        self._blogs = {int(blog_id): blog for blog_id, blog in state.get("blogs", {}).items()}
        self._next_blog_id = int(state.get("next_blog_id", 1))
        self._next_comment_id = int(state.get("next_comment_id", 1))
        self._step_counter = int(state.get("step_counter", 0))
        self._dedup = state.get("dedup", {})
        self._events = state.get("events", [])
        self._lock = asyncio.Lock()
        self._dedup_lock = asyncio.Lock()
        return True

    @tool(readonly=False)
    @_idempotent_write
    async def write_blog(
        self,
        agent_id: int,
        title: str,
        content: str,
        visibility: str = "public",
        status: str = "draft",
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Create a validated blog draft or published post.

        Optional case metadata makes the post auditable in PIC-001. A case
        post defaults to ``unverified``; a URL or reference is never treated
        as verified merely because it has valid syntax.
        """
        async with self._lock:
            agent_id = int(agent_id)
            if not self._known_agent(agent_id):
                return self._error(f"unknown agent_id {agent_id}")
            title, error = self._text(title, "title", _MAX_TITLE)
            if error:
                return self._error(error)
            content, error = self._text(content, "content", _MAX_CONTENT)
            if error:
                return self._error(error)
            visibility = self._validate_visibility(visibility)
            if visibility is None:
                return self._error("visibility must be public or private")
            status = self._validate_status(status)
            if status is None:
                return self._error("status must be draft or published")
            metadata, metadata_error = self._validate_case_metadata(
                case_id, artifact_id, claim_status, evidence_refs
            )
            if metadata_error:
                return self._error(metadata_error)
            if len(self._blogs) >= _MAX_BLOGS:
                return self._error("blog capacity reached")
            blog_id = self._next_blog_id
            self._next_blog_id += 1
            if metadata.get("case_id") and not metadata.get("artifact_id"):
                metadata["artifact_id"] = f"blog:{blog_id}"
            blog = {
                "id": blog_id,
                "owner_id": agent_id,
                "title": title,
                "content": content,
                "visibility": visibility,
                "status": status,
                "created_step": self._step_counter,
                "updated_step": self._step_counter,
                "comments": [],
                **metadata,
            }
            self._blogs[blog_id] = blog
            self._record_event(
                "blog_created",
                agent_id,
                blog_id,
                status=status,
                visibility=visibility,
                case_id=blog.get("case_id"),
                artifact_id=blog.get("artifact_id"),
                claim_status=blog.get("claim_status"),
            )
            return self._success(blog=dict(blog))

    @tool(readonly=False)
    @_idempotent_write
    async def update_blog(
        self,
        agent_id: int,
        blog_id: int,
        title: str | None = None,
        content: str | None = None,
        visibility: str | None = None,
        status: str | None = None,
        case_id: str | None = None,
        artifact_id: str | None = None,
        claim_status: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Update an owned blog with validated optional fields and case metadata."""
        async with self._lock:
            agent_id, blog, error = self._validate_agent_and_blog(agent_id, blog_id)
            if error:
                return error
            if blog["owner_id"] != agent_id:
                return self._error("only the owner may edit")
            changes = {}
            if title is not None:
                title, message = self._text(title, "title", _MAX_TITLE)
                if message:
                    return self._error(message)
                changes["title"] = title
            if content is not None:
                content, message = self._text(content, "content", _MAX_CONTENT)
                if message:
                    return self._error(message)
                changes["content"] = content
            if visibility is not None:
                visibility = self._validate_visibility(visibility)
                if visibility is None:
                    return self._error("visibility must be public or private")
                changes["visibility"] = visibility
            if status is not None:
                status = self._validate_status(status)
                if status is None:
                    return self._error("status must be draft or published")
                changes["status"] = status
            metadata_requested = any(
                value is not None
                for value in (case_id, artifact_id, claim_status, evidence_refs)
            )
            if metadata_requested:
                metadata, metadata_error = self._validate_case_metadata(
                    case_id, artifact_id, claim_status, evidence_refs
                )
                if metadata_error:
                    return self._error(metadata_error)
                changes.update(metadata)
            if not changes:
                return self._error("at least one editable field is required")
            blog.update(changes)
            blog["updated_step"] = self._step_counter
            self._record_event("blog_updated", agent_id, blog["id"], fields=sorted(changes))
            return self._success(blog=dict(blog))

    @tool(readonly=False)
    @_idempotent_write
    async def delete_blog(self, agent_id: int, blog_id: int) -> dict:
        """Delete an owned blog and its comments."""
        async with self._lock:
            agent_id, blog, error = self._validate_agent_and_blog(agent_id, blog_id)
            if error:
                return error
            if blog["owner_id"] != agent_id:
                return self._error("only the owner may delete")
            removed = self._blogs.pop(blog["id"])
            self._record_event("blog_deleted", agent_id, blog["id"])
            return self._success(deleted=dict(removed))

    @tool(readonly=False)
    @_idempotent_write
    async def comment_on_blog(self, agent_id: int, blog_id: int, content: str) -> dict:
        """Add a bounded comment to a visible blog."""
        async with self._lock:
            agent_id, blog, error = self._validate_agent_and_blog(agent_id, blog_id)
            if error:
                return error
            if not self._visible(agent_id, blog):
                return self._error("blog is private")
            content, error_message = self._text(content, "content", _MAX_COMMENT)
            if error_message:
                return self._error(error_message)
            if len(blog["comments"]) >= _MAX_COMMENTS_PER_BLOG:
                return self._error("comment capacity reached")
            comment = {
                "id": self._next_comment_id,
                "agent_id": agent_id,
                "content": content,
                "created_step": self._step_counter,
            }
            self._next_comment_id += 1
            blog["comments"].append(comment)
            self._record_event("blog_commented", agent_id, blog["id"], comment_id=comment["id"])
            return self._success(comment=dict(comment))

    @tool(readonly=True)
    async def list_blogs(self, agent_id: int, limit: int = 20) -> dict:
        """List public blogs and the requesting agent's private blogs."""
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
            visible = [dict(blog) for blog in self._blogs.values() if self._visible(agent_id, blog)]
            visible = visible[-limit:]
            return self._success(blogs=visible, count=len(visible))

    @tool(readonly=True)
    async def read_blog(self, agent_id: int, blog_id: int) -> dict:
        """Read a public blog or one owned by the requesting agent."""
        async with self._lock:
            agent_id, blog, error = self._validate_agent_and_blog(agent_id, blog_id)
            if error:
                return error
            if not self._visible(agent_id, blog):
                return self._error("blog is private")
            return self._success(blog=dict(blog))
