"""Scalable implementation of the public Emergence World tool catalog.

The specialized afi environments remain the source of truth for economy,
governance, energy, messaging, crime, and landmark data.  This module covers
the rest of EW's public catalog with a uniform request envelope, indexed state,
same-step idempotency, bounded query responses, replay summaries, and resume.

Every generated method is inserted into this class's own namespace before
``EnvMeta`` runs, so CodeGenRouter sees a normal, individually named MCP tool.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
from datetime import datetime
from typing import Any, ClassVar

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager

from afi.world.ew_tools import EW_PUBLIC_TOOLS, validate_tool_request

_STATE_REL = "state/ENV_STATE.json"

# Names already implemented by specialized modules and therefore deliberately
# not duplicated here.  The B1 coverage test checks the union of all modules.
SPECIALIZED_TOOLS = {
    "list_landmarks", "send_message", "read_messages",
    "add_to_billboard", "read_billboard", "edit_billboard",
    "delete_from_billboard", "reply_to_billboard", "react_to_billboard",
    "add_todo", "complete_todo", "list_todo",
    "add_to_calendar", "check_calendar", "remove_from_calendar",
    "submit_grant_pitch", "vote_for_pitch", "list_credit_pitches",
    "deposit_credits_to_bank", "withdraw_credits_from_bank", "take_bank_loan",
    "repay_bank_loan", "check_bank_balance", "transact_compute_credits",
    "victory_arch_pitch_winners",
    "write_blog", "update_blog", "delete_blog", "comment_on_blog", "list_blogs", "read_blog",
    "submit_townhall_proposal", "list_proposals", "read_townhall_proposal",
    "vote_on_proposal", "comment_on_proposal", "update_proposal",
    "read_constitution", "submit_final_report",
    "file_complaint", "check_complaint_status", "propose_community_event",
    "list_community_events", "rate_agent_trust", "check_agent_trust",
}

_CATEGORY_NAMES = {
    "navigation": "go_to_place go_home run_to_place go_to_coordinates turn_towards get_distance_to list_agents get_nearby follow_agent",
    "communication": "say_to_agent read_messages think_aloud",
    "memory": "add_to_longterm_memory remove_from_memory retrieve_specific_memories add_to_soul remove_from_soul write_diary search_diary_for_keywords show_diary_entries_from_day",
    "planning": "add_todo complete_todo list_todo add_to_calendar check_calendar remove_from_calendar",
    "expression": "show_emoticon set_mood_and_terminate assign_relationship put_on_fire",
    "governance": "submit_townhall_proposal list_proposals read_townhall_proposal vote_on_proposal comment_on_proposal update_proposal read_constitution submit_final_report",
    "research": "do_deep_research_on_internet todays_news_from_human_world web_fetch browse_scientific_papers publish_to_archive search_archive archive_index",
    "billboard": "add_to_billboard read_billboard edit_billboard delete_from_billboard reply_to_billboard react_to_billboard",
    "analytics": "extract_code_for_tool read_agent_manifesto browse_tool_registry check_weather tool_usage_analytics_by_character overall_tool_usage_analytics_by_date social_event_history",
    "community": "file_complaint check_complaint_status propose_community_event list_community_events rate_agent_trust check_agent_trust pray read_advertisements post_advertisements",
    "self_care": "self_care idle recharge_energy",
    "content": "write_blog update_blog delete_blog comment_on_blog list_blogs read_blog generate_image execute_python_code_tool upload_data_for_sharing take_picture",
    "social_physical": "physical_action dance neural_link_request_memory neural_link_share_memory",
    "identity": "change_name read_personality update_personality_line",
    "events": "create_personal_event invite_to_event accept_event_invitation decline_event_invitation review_event rsvp_to_event event_present event_respond",
    "routines": "create_routine run_routine list_routines delete_routine",
    "building": "put_brick_in_pixel",
    "utility": "ignore",
}
TOOL_CATEGORY = {
    name: category for category, names in _CATEGORY_NAMES.items() for name in names.split()
}

READONLY_TOOLS = set(
    "get_distance_to list_agents get_nearby read_messages retrieve_specific_memories "
    "search_diary_for_keywords show_diary_entries_from_day list_todo check_calendar "
    "list_proposals read_townhall_proposal read_constitution todays_news_from_human_world "
        "web_fetch browse_scientific_papers search_archive archive_index "
    "extract_code_for_tool read_agent_manifesto browse_tool_registry check_weather "
    "tool_usage_analytics_by_character overall_tool_usage_analytics_by_date "
    "social_event_history check_complaint_status list_community_events check_agent_trust "
    "read_advertisements list_blogs read_blog read_personality list_routines".split()
)

_CLAIM_STATUSES = {"unverified", "supported", "refuted", "blocked"}
def _make_catalog_tool(name: str, readonly: bool):
    """Create one named MCP tool with a stable extensible request envelope."""
    async def generated(self, agent_id: int, request: dict | None = None) -> dict:
        return await self._dispatch(name, int(agent_id), request or {})

    generated.__name__ = name
    generated.__qualname__ = f"EWToolSpace.{name}"
    action = name.replace("_", " ")
    generated.__doc__ = (
        f"Perform the EW **{action}** operation in the {TOOL_CATEGORY[name]} category.\n\n"
        "The operation uses local deterministic state unless its result explicitly says "
        "that an external capability provider is required.\n\n"
        ":param agent_id: Acting or requesting agent ID.\n"
        ":param request: Extensible operation fields; IDs, content, query, limits, or metadata.\n"
    )
    generated.__signature__ = inspect.Signature([
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("agent_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int),
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=dict | None, default=None),
    ], return_annotation=dict)
    return tool(readonly=readonly)(generated)


class EWToolSpace(EnvBase):
    """Indexed, bounded state for EW tools not owned by specialized spaces."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("location", "TEXT"),
        ColumnDef("mood", "TEXT"),
        ColumnDef("memory_count", "INTEGER"),
        ColumnDef("todo_count", "INTEGER"),
        ColumnDef("relationship_count", "INTEGER"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("event_count", "INTEGER"),
        ColumnDef("blog_posts", "INTEGER"),
        ColumnDef("community_events", "INTEGER"),
        ColumnDef("archive_items", "INTEGER"),
    ]

    def __init__(
        self,
        agent_ids: list[int] | None = None,
        agent_names: dict | None = None,
        homes: dict | None = None,
        landmarks: list[dict] | None = None,
        manifesto: str = "",
        constitution: str = "",
        max_events: int = 20000,
        max_query_items: int = 100,
        enabled_categories: list[str] | None = None,
        enabled_tools: list[str] | None = None,
        case_id: str = "",
        default_claim_status: str = "unverified",
        active_public_tools: list[str] | None = None,
        **kwargs,
    ):
        super().__init__()
        requested_categories = set(enabled_categories or _CATEGORY_NAMES)
        unknown_categories = requested_categories - set(_CATEGORY_NAMES)
        if unknown_categories:
            raise ValueError(f"unknown EW tool categories: {sorted(unknown_categories)}")
        self._enabled_categories = sorted(requested_categories)
        registered_names = set(self._registered_tools)
        if enabled_tools is None:
            allowed_tools = {
                name for name, category in TOOL_CATEGORY.items()
                if category in requested_categories and name in registered_names
            }
            self._enabled_tools = sorted(allowed_tools)
        else:
            requested_names = [str(name) for name in enabled_tools]
            if len(requested_names) != len(set(requested_names)):
                raise ValueError("enabled_tools must not contain duplicate names")
            requested_tools = set(requested_names)
            unknown_tools = requested_tools - registered_names
            if unknown_tools:
                raise ValueError(
                    f"unknown or non-EWToolSpace tools: {sorted(unknown_tools)}"
                )
            category_mismatch = {
                name for name in requested_tools
                if TOOL_CATEGORY[name] not in requested_categories
            }
            if category_mismatch:
                raise ValueError(
                    "enabled_tools contains tools outside enabled_categories: "
                    f"{sorted(category_mismatch)}"
                )
            allowed_tools = requested_tools
            self._enabled_tools = sorted(requested_tools)
        self._tool_manager = ToolManager(tools=[tool_obj for name, tool_obj in self._registered_tools.items() if name in allowed_tools])
        self._llm_tools = [item for item in self._llm_tools if item["function"]["name"] in allowed_tools]
        self._readonly_llm_tools = [item for item in self._readonly_llm_tools if item["function"]["name"] in allowed_tools]
        ids = [int(x) for x in (agent_ids or range(1, 11))]
        self._agent_ids = ids
        self._names = {int(k): str(v) for k, v in (agent_names or {}).items()}
        self._homes = {int(k): str(v) for k, v in (homes or {}).items()}
        self._landmarks = {str(x.get("name")): dict(x) for x in (landmarks or [])}
        self._manifesto = manifesto
        self._constitution = constitution
        self._case_id = str(case_id or "").strip() or None
        self._default_claim_status = str(default_claim_status or "unverified").strip()
        if self._default_claim_status not in _CLAIM_STATUSES:
            raise ValueError(f"unknown default_claim_status: {self._default_claim_status}")
        public_tools = [str(name) for name in (active_public_tools or sorted(allowed_tools))]
        if len(public_tools) != len(set(public_tools)):
            raise ValueError("active_public_tools must not contain duplicate names")
        unknown_public = set(public_tools) - set(EW_PUBLIC_TOOLS)
        if unknown_public:
            raise ValueError(f"active_public_tools contains unknown EW tools: {sorted(unknown_public)}")
        self._active_public_tools = public_tools
        self._max_events = max(1000, int(max_events))
        self._max_query_items = min(500, max(10, int(max_query_items)))
        self._step_counter = 0
        self._next_id = 1
        self._positions = {aid: {"place": self._homes.get(aid, "home"), "x": 0.0, "z": 0.0} for aid in ids}
        self._follows: dict[int, int] = {}
        self._facing: dict[int, int] = {}
        self._mailboxes = {aid: [] for aid in ids}
        self._memories = {aid: [] for aid in ids}
        self._souls = {aid: [] for aid in ids}
        self._diaries = {aid: [] for aid in ids}
        self._todos = {aid: {} for aid in ids}
        self._calendars = {aid: {} for aid in ids}
        self._moods = {aid: "neutral" for aid in ids}
        self._personalities = {aid: [] for aid in ids}
        self._relationships: dict[str, dict] = {}
        self._trust: dict[str, dict] = {}
        self._blogs: dict[int, dict] = {}
        self._archive: dict[int, dict] = {}
        self._complaints: dict[int, dict] = {}
        self._proposals: dict[int, dict] = {}
        self._events: dict[int, dict] = {}
        self._routines: dict[int, dict] = {}
        self._advertisement: dict | None = None
        self._uploads: dict[int, dict] = {}
        self._bricks: dict[str, dict] = {}
        self._neural_requests: dict[str, dict] = {}
        self._event_log: list[dict] = []
        self._read_audit: list[dict] = []
        self._usage: dict[str, dict[int, int]] = {}
        self._dedup: dict[str, dict] = {}
        # Domain state for the generic EW surface.  These collections keep
        # the tools useful in a large scenario without pretending to be a
        # real map, calendar service, media store, or external provider.
        self._thoughts = {aid: [] for aid in ids}
        self._social_actions: list[dict] = []
        self._routine_runs: list[dict] = []
        self._energy = {aid: 100.0 for aid in ids}
        self._lock = asyncio.Lock()

    @classmethod
    def description(cls) -> str:
        return "EW public tool catalog: navigation, memory, content, community, identity, events, and utilities."

    @classmethod
    def init_description(cls) -> str:
        return """EWToolSpace supplies the public Emergence World tools not owned by specialized modules.

        It is sized for 10 agents and 360 steps by default, with indexed per-agent
        state, bounded query responses, capped event history, replay snapshots,
        resume support, same-step idempotency, and optional category gating to keep
        the active LLM tool surface small. Each operation is exposed under
        its exact EW tool name and accepts **agent_id** plus an extensible **request**
        dictionary. Common request keys are target_id, content, query, item_id,
        limit, place, x, z, date, title, and metadata.

        ``enabled_tools`` optionally restricts this module to an exact list;
        specialized owners are rejected rather than silently duplicated.
        In a case-scoped run, public artifacts carry **case_id**,
        **claim_status**, and **evidence_refs**. A supported claim requires
        at least one evidence reference; a URL-shaped string alone is not
        treated as verified evidence.
        """

    def _new_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _limit(self, request: dict) -> int:
        try:
            value = int(request.get("limit", 20))
        except (TypeError, ValueError):
            value = 20
        return min(self._max_query_items, max(1, value))

    def _target_agent(self, request: dict, *, field: str = "target_id") -> tuple[int | None, dict | None]:
        """Resolve and validate an agent target for relationship-like tools."""
        try:
            target = int(request.get(field, 0))
        except (TypeError, ValueError):
            return None, {"status": "fail", "reason": f"request.{field} must be an integer"}
        if target not in self._agent_ids:
            return None, {"status": "fail", "reason": f"unknown {field}"}
        return target, None

    def _event_id(self, request: dict) -> int:
        """Accept the public event_id name and the common item_id alias."""
        try:
            return int(request.get("event_id", request.get("item_id", request.get("id", 0))))
        except (TypeError, ValueError):
            return 0

    def _event_view(self, event: dict) -> dict:
        """Return a JSON-safe event view with deterministic participant lists."""
        view = dict(event)
        for key in ("invitations", "responses", "attendance"):
            if isinstance(view.get(key), dict):
                view[key] = {str(k): v for k, v in view[key].items()}
        view["participant_ids"] = sorted({int(x) for x in view.get("participants", {})})
        return view

    def _append_event(self, tool_name: str, agent_id: int, request: dict) -> dict:
        event = {"id": self._new_id(), "tool": tool_name, "agent_id": agent_id, "request": request, "step": self._step_counter, "t": str(self.t)}
        self._event_log.append(event)
        if len(self._event_log) > self._max_events:
            del self._event_log[: len(self._event_log) - self._max_events]
        by_agent = self._usage.setdefault(tool_name, {})
        by_agent[agent_id] = by_agent.get(agent_id, 0) + 1
        return event

    def _write_once(self, tool_name: str, agent_id: int, request: dict, mutate) -> dict:
        key = json.dumps([self._step_counter, tool_name, agent_id, request], sort_keys=True, default=str)
        if key in self._dedup:
            return dict(self._dedup[key], deduplicated=True)
        result = mutate()
        if "status" not in result:
            result["status"] = "success"
        self._dedup[key] = dict(result)
        self._append_event(tool_name, agent_id, request)
        return result

    def _items(self, mapping: dict, request: dict) -> list:
        query = str(request.get("query", "")).lower()
        values = list(mapping.values())
        if query:
            values = [x for x in values if query in json.dumps(x, ensure_ascii=False).lower()]
        return values[-self._limit(request):]

    def _record_read(
        self,
        tool_name: str,
        agent_id: int,
        request: dict,
        item_id: int | None = None,
    ) -> None:
        """Record a bounded read audit without mixing it with write events."""
        self._read_audit.append({
            "tool": tool_name,
            "agent_id": agent_id,
            "item_id": item_id,
            "step": self._step_counter,
            "t": str(self.t),
        })
        if len(self._read_audit) > self._max_events:
            del self._read_audit[: len(self._read_audit) - self._max_events]

    async def _dispatch(self, name: str, aid: int, req: dict) -> dict:
        async with self._lock:
            if aid not in self._agent_ids:
                return {"status": "fail", "reason": "unknown agent_id"}
            valid, reason = validate_tool_request(name, req)
            if not valid:
                return {"status": "fail", "reason": reason}
            # Navigation and observation.
            if name in {"go_to_place", "run_to_place"}:
                place = str(req.get("place", req.get("landmark", ""))).strip()
                if not place:
                    return {"status": "fail", "reason": "request.place is required"}
                if self._landmarks and place not in self._landmarks:
                    return {"status": "fail", "reason": "unknown landmark"}
                return self._write_once(name, aid, req, lambda: self._move(aid, place=place, speed="run" if name.startswith("run") else "walk"))
            if name == "go_home":
                return self._write_once(name, aid, req, lambda: self._move(aid, place=self._homes.get(aid, "home"), speed="walk"))
            if name == "go_to_coordinates":
                return self._write_once(name, aid, req, lambda: self._move(aid, x=float(req.get("x", 0)), z=float(req.get("z", 0))))
            if name == "turn_towards":
                target, error = self._target_agent(req)
                if error or target == aid:
                    return error or {"status": "fail", "reason": "an agent cannot face itself"}
                return self._write_once(name, aid, req, lambda: self._set_map(self._facing, aid, target, "target_id"))
            if name == "follow_agent":
                target, error = self._target_agent(req)
                if error or target == aid:
                    return error or {"status": "fail", "reason": "an agent cannot follow itself"}
                return self._write_once(name, aid, req, lambda: self._set_map(self._follows, aid, target, "target_id"))
            if name == "get_distance_to":
                target, error = self._target_agent(req)
                if error:
                    return error
                a, b = self._positions[aid], self._positions[target]
                distance = ((a.get("x", 0)-b.get("x", 0))**2 + (a.get("z", 0)-b.get("z", 0))**2) ** .5
                self._record_read(name, aid, req, target)
                return {"agent_id": aid, "target_id": target, "distance": distance, "same_place": bool(b and a.get("place") == b.get("place"))}
            if name == "list_agents":
                self._record_read(name, aid, req)
                return {"agents": [{"id": x, "name": self._names.get(x, str(x)), **self._positions[x]} for x in self._agent_ids][:self._limit(req)]}
            if name == "get_nearby":
                place = self._positions[aid]["place"]
                nearby = [
                    {"id": x, "name": self._names.get(x, str(x)), **self._positions[x]}
                    for x in self._agent_ids
                    if x != aid and self._positions[x]["place"] == place
                ][: self._limit(req)]
                self._record_read(name, aid, req)
                return {"place": place, "agents": nearby, "agent_ids": [item["id"] for item in nearby]}

            # Per-agent memory, planning, and identity collections.
            collection_ops = {
                "add_to_longterm_memory": (self._memories, "content"), "add_to_soul": (self._souls, "content"),
                "write_diary": (self._diaries, "content"), "add_todo": (self._todos, "content"),
                "add_to_calendar": (self._calendars, "content"), "update_personality_line": (self._personalities, "content"),
            }
            if name in collection_ops:
                store, field = collection_ops[name]
                return self._write_once(name, aid, req, lambda: self._add_item(store, aid, req, field))
            if name in {"remove_from_memory", "remove_from_soul", "complete_todo", "remove_from_calendar"}:
                store = {"remove_from_memory": self._memories, "remove_from_soul": self._souls, "complete_todo": self._todos, "remove_from_calendar": self._calendars}[name]
                return self._write_once(name, aid, req, lambda: self._remove_item(store, aid, int(req.get("item_id", req.get("id", 0)))))
            if name in {"retrieve_specific_memories", "search_diary_for_keywords", "show_diary_entries_from_day", "list_todo", "check_calendar", "read_personality"}:
                store = {"retrieve_specific_memories": self._memories, "search_diary_for_keywords": self._diaries, "show_diary_entries_from_day": self._diaries, "list_todo": self._todos, "check_calendar": self._calendars, "read_personality": self._personalities}[name]
                values = list(store[aid].values()) if isinstance(store[aid], dict) else list(store[aid])
                if name == "show_diary_entries_from_day" and req.get("date"):
                    requested_date = str(req["date"])[:10]
                    values = [v for v in values if str(v.get("date") or v.get("created_at", ""))[:10] == requested_date]
                else:
                    query = str(req.get("query", "")).lower().strip()
                    if query:
                        values = [v for v in values if query in json.dumps(v, ensure_ascii=False).lower()]
                self._record_read(name, aid, req)
                return {"items": values[-self._limit(req):]}
            if name == "change_name":
                return self._write_once(name, aid, req, lambda: self._set_map(self._names, aid, str(req.get("name", "")).strip(), "name"))
            if name == "think_aloud":
                content = str(req.get("content", req.get("text", ""))).strip()
                if not content:
                    return {"status": "fail", "reason": "request.content is required"}
                return self._write_once(name, aid, req, lambda: self._record_thought(aid, content, req))

            # Personal events have an explicit lifecycle.  The old generic
            # record path made invitations and RSVP calls look successful but
            # did not change the event, which was not useful in an EW-sized
            # multi-agent scenario.
            if name == "create_personal_event":
                return self._write_once(name, aid, req, lambda: self._create_event(aid, req))
            if name in {"invite_to_event", "accept_event_invitation", "decline_event_invitation", "rsvp_to_event", "event_present", "event_respond", "review_event"}:
                return self._write_once(name, aid, req, lambda: self._handle_event_action(name, aid, req))

            if name == "create_routine":
                return self._write_once(name, aid, req, lambda: self._create_routine(aid, req))
            if name == "publish_to_archive":
                return self._write_once(name, aid, req, lambda: self._publish_archive(aid, req))
            if name == "upload_data_for_sharing":
                return self._write_once(name, aid, req, lambda: self._upload_data(aid, req))
            if name == "search_archive":
                self._record_read(name, aid, req)
                return {"items": self._search_archive(req)}
            if name == "archive_index":
                self._record_read(name, aid, req)
                return self._archive_index()

            # Generic public record stores used by the rest of the 113-tool
            # catalog. Specialized PIC-001 tools are handled above or by their
            # owning environment, so they are intentionally not duplicated.
            create_map = {
                "write_blog": self._blogs,
                "file_complaint": self._complaints, "submit_townhall_proposal": self._proposals,
                "propose_community_event": self._events,
            }
            if name in create_map:
                return self._write_once(name, aid, req, lambda: self._create_record(create_map[name], aid, req, name))
            read_map = {
                "list_blogs": self._blogs, "read_blog": self._blogs,
                "list_proposals": self._proposals, "read_townhall_proposal": self._proposals,
                "check_complaint_status": self._complaints, "list_community_events": self._events,
                "list_routines": self._routines,
            }
            if name in read_map:
                if name == "list_routines":
                    own = [routine for routine in self._routines.values() if routine.get("owner_id") == aid]
                    self._record_read(name, aid, req)
                    return {"items": own[-self._limit(req):]}
                try:
                    item_id = int(req.get("item_id", req.get("id", 0)))
                except (TypeError, ValueError):
                    return {"status": "fail", "reason": "item_id must be an integer"}
                if item_id:
                    item = read_map[name].get(item_id)
                    self._record_read(name, aid, req, item_id)
                    return {"item": item, "status": "success" if item else "fail", "reason": None if item else "item not found"}
                self._record_read(name, aid, req)
                return {"items": self._items(read_map[name], req)}
            if name in {"update_blog", "update_proposal"}:
                store = {"update_blog": self._blogs, "update_proposal": self._proposals}[name]
                return self._write_once(name, aid, req, lambda: self._update_record(store, aid, req))
            if name in {"delete_blog", "delete_routine"}:
                store = {"delete_blog": self._blogs, "delete_routine": self._routines}[name]
                return self._write_once(name, aid, req, lambda: self._delete_record(store, aid, req))

            # Relationships, trust, messages, events, reactions and other social actions.
            if name == "assign_relationship":
                target, error = self._target_agent(req)
                if error or target == aid:
                    return error or {"status": "fail", "reason": "an agent cannot assign a relationship to itself"}
                key = f"{aid}:{target}"
                return self._write_once(name, aid, req, lambda: self._set_map(self._relationships, key, {"agent_id": aid, "target_id": target, "type": req.get("type", "acquaintance")}, "target_id"))
            if name == "rate_agent_trust":
                target = int(req.get("target_id", 0))
                if target not in self._agent_ids:
                    return {"status": "fail", "reason": "unknown target_id"}
                if target == aid:
                    return {"status": "fail", "reason": "an agent cannot rate itself"}
                try:
                    rating = int(req.get("rating"))
                except (TypeError, ValueError):
                    return {"status": "fail", "reason": "rating must be an integer from 1 to 5"}
                if rating < 1 or rating > 5:
                    return {"status": "fail", "reason": "rating must be an integer from 1 to 5"}
                reason = str(req.get("reason", "")).strip()
                if not reason:
                    return {"status": "fail", "reason": "request.reason is required"}
                key = f"{aid}:{target}"
                record = {
                    "rater": aid,
                    "target": target,
                    "rating": rating,
                    "reason": reason,
                    "case_id": req.get("case_id", self._case_id),
                    "artifact_id": req.get("artifact_id"),
                    "claim_status": req.get("claim_status", self._default_claim_status),
                    "step": self._step_counter,
                }
                return self._write_once(name, aid, req, lambda: self._set_map(self._trust, key, record, "target_id"))
            if name == "check_agent_trust":
                target = int(req.get("target_id", 0))
                if target not in self._agent_ids:
                    return {"status": "fail", "reason": "unknown target_id"}
                ratings = [v["rating"] for v in self._trust.values() if v["target"] == target]
                self._record_read(name, aid, req, target)
                return {
                    "target_id": target,
                    "average": sum(ratings) / len(ratings) if ratings else None,
                    "ratings": len(ratings),
                    "case_id": self._case_id,
                }
            if name == "read_messages":
                items = self._mailboxes[aid][-self._limit(req):]
                self._record_read(name, aid, req)
                return {"messages": items}
            if name == "say_to_agent":
                target = int(req.get("target_id", 0))
                return self._write_once(name, aid, req, lambda: self._message(aid, target, str(req.get("content", "")), nearby=True))
            if name in {"comment_on_blog", "comment_on_proposal", "vote_on_proposal", "submit_final_report"}:
                return self._write_once(name, aid, req, lambda: {"status": "success", "record": self._append_embedded(name, aid, req)})
            if name == "read_constitution":
                self._record_read(name, aid, req)
                return {"constitution": self._constitution, "case_id": self._case_id}
            if name == "read_agent_manifesto":
                self._record_read(name, aid, req)
                return {"manifesto": self._manifesto, "case_id": self._case_id, "source": "scenario_seed"}

            # Routines, construction, advertising and generic embodied actions.
            if name == "run_routine":
                return self._write_once(name, aid, req, lambda: self._run_routine(aid, req))
            if name == "put_brick_in_pixel":
                key = f"{req.get('x',0)}:{req.get('y',0)}:{req.get('z',0)}"
                return self._write_once(name, aid, req, lambda: self._set_map(self._bricks, key, {"owner": aid, **req}, "coordinates"))
            if name == "post_advertisements":
                return self._write_once(name, aid, req, lambda: self._set_ad(aid, req))
            if name == "read_advertisements":
                self._record_read(name, aid, req)
                return {"advertisement": self._advertisement}
            if name in {"show_emoticon", "set_mood_and_terminate"}:
                mood = str(req.get("mood", req.get("emoticon", "neutral")))
                return self._write_once(name, aid, req, lambda: self._set_map(self._moods, aid, mood, "mood"))
            if name in {"put_on_fire", "pray", "self_care", "idle", "recharge_energy", "physical_action", "dance", "take_picture", "ignore"}:
                return self._write_once(name, aid, req, lambda: self._handle_action(name, aid, req))
            if name in {"neural_link_request_memory", "neural_link_share_memory"}:
                return self._write_once(name, aid, req, lambda: self._handle_neural_link(name, aid, req))

            # Analytics and externally fulfilled capabilities.
            if name == "browse_tool_registry":
                query = str(req.get("query", "")).strip().lower()
                names = self._active_public_tools
                if query:
                    names = [
                        tool_name for tool_name in names
                        if query in tool_name.lower() or query in TOOL_CATEGORY.get(tool_name, "").lower()
                    ]
                names = names[: self._limit(req)]
                self._record_read(name, aid, req)
                tools = [
                    {
                        "name": tool_name,
                        "category": TOOL_CATEGORY.get(tool_name, "specialized"),
                        "enabled": True,
                    }
                    for tool_name in names
                ]
                return {
                    "tools": tools,
                    "count": len(tools),
                    "case_id": self._case_id,
                    "surface": "active_public_tools",
                }
            if name == "tool_usage_analytics_by_character":
                target = int(req.get("target_id", aid))
                if target not in self._agent_ids:
                    return {"status": "fail", "reason": "unknown target_id"}
                usage = {k: v.get(target, 0) for k, v in self._usage.items() if v.get(target, 0)}
                self._record_read(name, aid, req, target)
                return {
                    "agent_id": target,
                    "usage": usage,
                    "unique_tools": len(usage),
                    "event_count": sum(usage.values()),
                    "case_id": self._case_id,
                    "scope": "EWToolSpace_only",
                    "coverage_note": "Cross-environment counts must be computed from the run trace.",
                }
            if name == "overall_tool_usage_analytics_by_date":
                self._record_read(name, aid, req)
                return {"usage": {k: sum(v.values()) for k, v in self._usage.items()}, "event_count": len(self._event_log)}
            if name == "social_event_history":
                self._record_read(name, aid, req)
                return {"events": self._event_log[-self._limit(req):]}
            if name == "extract_code_for_tool": return {"status": "fail", "reason": "source extraction is unavailable in the clean-room catalog"}
            if name == "execute_python_code_tool": return self._execute_expression(req)
            if name in {"do_deep_research_on_internet", "todays_news_from_human_world", "web_fetch", "browse_scientific_papers", "check_weather", "generate_image"}:
                # The environment deliberately does not fabricate live external
                # results. A deterministic request key lets a configured adapter
                # correlate the request without mutating a readonly call.
                request_id = hashlib.sha256(json.dumps([name, aid, req], sort_keys=True, default=str).encode()).hexdigest()[:16]
                return {"status": "in_progress", "request_id": request_id, "response": "queued for the configured external capability provider"}
            return {"status": "error", "reason": f"unhandled tool {name}"}

    def _publish_archive(self, aid: int, request: dict) -> dict:
        content = str(request.get("content", "")).strip()
        if not content:
            return {"status": "fail", "reason": "request.content is required"}
        item = {
            "id": self._new_id(),
            "owner_id": aid,
            "kind": "archive_item",
            "title": request.get("title", ""),
            "content": content,
            "tags": list(request.get("tags", [])) if isinstance(request.get("tags", []), list) else [],
            "source": request.get("source", "agent_submission"),
            "case_id": request.get("case_id", self._case_id),
            "claim_status": request.get("claim_status", self._default_claim_status),
            "evidence_refs": list(request.get("evidence_refs", [])) if isinstance(request.get("evidence_refs", []), list) else [],
            "published_step": self._step_counter,
        }
        self._archive[item["id"]] = item
        return {"status": "success", "item": item}

    def _search_archive(self, request: dict) -> list[dict]:
        query = str(request.get("query", "")).strip().lower()
        values = list(self._archive.values())
        if query:
            values = [item for item in values if query in json.dumps(item, ensure_ascii=False).lower()]
        return values[-self._limit(request):]

    def _archive_index(self) -> dict:
        tags: dict[str, int] = {}
        for item in self._archive.values():
            for tag in item.get("tags", []):
                tags[str(tag)] = tags.get(str(tag), 0) + 1
        return {
            "status": "success",
            "count": len(self._archive),
            "tag_counts": dict(sorted(tags.items())),
            "latest_ids": list(self._archive)[-self._max_query_items:],
        }

    def _upload_data(self, aid: int, request: dict) -> dict:
        content = request.get("content", request.get("data", ""))
        if content in (None, ""):
            return {"status": "fail", "reason": "request.content is required"}
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
        item = {
            "id": self._new_id(),
            "owner_id": aid,
            "kind": "shared_data",
            "content": content,
            "data_type": request.get("data_type", type(content).__name__),
            "visibility": request.get("visibility", "public"),
            "checksum": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            "case_id": request.get("case_id", self._case_id),
            "step": self._step_counter,
        }
        self._uploads[item["id"]] = item
        return {"status": "success", "item": item}

    def _record_thought(self, aid: int, content: str, request: dict) -> dict:
        thought = {
            "id": self._new_id(),
            "agent_id": aid,
            "content": content,
            "visibility": request.get("visibility", "private"),
            "step": self._step_counter,
            "t": str(self.t),
        }
        self._thoughts[aid].append(thought)
        return {"status": "success", "thought": thought}

    def _create_event(self, aid: int, request: dict) -> dict:
        title = str(request.get("title", request.get("content", ""))).strip()
        if not title:
            return {"status": "fail", "reason": "request.content or request.title is required"}
        event_id = self._new_id()
        event = {
            "id": event_id,
            "kind": "personal_event",
            "owner_id": aid,
            "title": title,
            "description": str(request.get("description", request.get("content", ""))),
            "location": request.get("location"),
            "starts_at": request.get("starts_at", request.get("start_at")),
            "ends_at": request.get("ends_at", request.get("end_at")),
            "status": "proposed",
            "participants": {aid: "organizer"},
            "invitations": {},
            "responses": {aid: "organizer"},
            "attendance": {},
            "reviews": [],
            "created_step": self._step_counter,
        }
        self._events[event_id] = event
        return {"status": "success", "event": self._event_view(event)}

    def _handle_event_action(self, name: str, aid: int, request: dict) -> dict:
        event_id = self._event_id(request)
        event = self._events.get(event_id)
        if not event:
            return {"status": "fail", "reason": "event not found"}

        if name == "invite_to_event":
            target, error = self._target_agent(request)
            if error:
                return error
            if event["owner_id"] != aid:
                return {"status": "fail", "reason": "only the event owner may invite agents"}
            if target == aid:
                return {"status": "fail", "reason": "the owner is already an organizer"}
            event["invitations"][target] = "pending"
            return {"status": "success", "event": self._event_view(event), "invited_id": target}

        if name in {"accept_event_invitation", "decline_event_invitation"}:
            invitation = event["invitations"].get(aid)
            if invitation is None:
                return {"status": "fail", "reason": "agent has no invitation"}
            response = "accepted" if name.startswith("accept") else "declined"
            event["invitations"][aid] = response
            event["responses"][aid] = response
            if response == "accepted":
                event["participants"][aid] = "guest"
            else:
                event["participants"].pop(aid, None)
            return {"status": "success", "event": self._event_view(event), "response": response}

        if name in {"rsvp_to_event", "event_respond"}:
            response = str(request.get("status", request.get("response", ""))).strip().lower()
            response_aliases = {"yes": "accepted", "no": "declined", "maybe": "tentative"}
            response = response_aliases.get(response, response)
            if response not in {"accepted", "declined", "tentative"}:
                return {"status": "fail", "reason": "response must be accepted, declined, or tentative"}
            if aid != event["owner_id"] and aid not in event["invitations"]:
                return {"status": "fail", "reason": "agent has no invitation"}
            event["responses"][aid] = response
            if response == "accepted":
                event["participants"][aid] = "guest"
            elif response == "declined":
                event["participants"].pop(aid, None)
            return {"status": "success", "event": self._event_view(event), "response": response}

        if name == "event_present":
            if aid not in event["participants"]:
                return {"status": "fail", "reason": "only confirmed participants may attend"}
            event["attendance"][aid] = True
            event["status"] = "in_progress"
            return {"status": "success", "event": self._event_view(event), "present": True}

        if name == "review_event":
            if aid not in event["participants"] and aid != event["owner_id"]:
                return {"status": "fail", "reason": "only participants may review the event"}
            try:
                rating = int(request.get("rating", 0))
            except (TypeError, ValueError):
                return {"status": "fail", "reason": "rating must be an integer from 1 to 5"}
            if rating < 1 or rating > 5:
                return {"status": "fail", "reason": "rating must be an integer from 1 to 5"}
            review = {"agent_id": aid, "rating": rating, "content": request.get("content", ""), "step": self._step_counter}
            event["reviews"] = [r for r in event["reviews"] if r["agent_id"] != aid]
            event["reviews"].append(review)
            return {"status": "success", "event": self._event_view(event), "review": review}

        return {"status": "fail", "reason": f"unsupported event action: {name}"}

    def _create_routine(self, aid: int, request: dict) -> dict:
        name = str(request.get("name", request.get("title", request.get("content", "")))).strip()
        if not name:
            return {"status": "fail", "reason": "request.content or request.name is required"}
        steps = request.get("steps", request.get("actions", []))
        if isinstance(steps, str):
            steps = [step.strip() for step in steps.split(",") if step.strip()]
        if not isinstance(steps, list) or len(steps) > 32:
            return {"status": "fail", "reason": "request.steps must be a list with at most 32 items"}
        routine = {
            "id": self._new_id(),
            "owner_id": aid,
            "name": name,
            "description": request.get("description", request.get("content", "")),
            "steps": steps,
            "enabled": bool(request.get("enabled", True)),
            "run_count": 0,
            "created_step": self._step_counter,
        }
        self._routines[routine["id"]] = routine
        return {"status": "success", "routine": dict(routine)}

    def _run_routine(self, aid: int, request: dict) -> dict:
        try:
            routine_id = int(request.get("routine_id", request.get("item_id", 0)))
        except (TypeError, ValueError):
            return {"status": "fail", "reason": "routine_id must be an integer"}
        routine = self._routines.get(routine_id)
        if not routine:
            return {"status": "fail", "reason": "routine not found"}
        if routine.get("owner_id") != aid:
            return {"status": "fail", "reason": "only the routine owner may run it"}
        if not routine.get("enabled", True):
            return {"status": "fail", "reason": "routine is disabled"}
        routine["run_count"] = int(routine.get("run_count", 0)) + 1
        routine["last_run_step"] = self._step_counter
        run = {"routine_id": routine_id, "agent_id": aid, "step": self._step_counter, "steps": list(routine.get("steps", []))}
        self._routine_runs.append(run)
        return {"status": "success", "routine": dict(routine), "run": run}

    def _handle_action(self, name: str, aid: int, request: dict) -> dict:
        if name == "recharge_energy":
            try:
                amount = float(request.get("amount", 10))
            except (TypeError, ValueError):
                return {"status": "fail", "reason": "amount must be a number"}
            if amount <= 0:
                return {"status": "fail", "reason": "amount must be positive"}
            self._energy[aid] = min(100.0, self._energy[aid] + amount)
            return {"status": "success", "action": name, "energy": self._energy[aid], "recharged": amount}
        if name == "self_care":
            self._energy[aid] = min(100.0, self._energy[aid] + 5.0)
        elif name == "idle":
            self._energy[aid] = min(100.0, self._energy[aid] + 1.0)
        if name == "take_picture":
            asset = {
                "id": self._new_id(),
                "owner_id": aid,
                "kind": "picture",
                "location": dict(self._positions[aid]),
                "metadata": request.get("metadata", {}),
                "step": self._step_counter,
            }
            self._uploads[asset["id"]] = asset
            return {"status": "success", "asset": asset}
        action = {"id": self._new_id(), "agent_id": aid, "action": name, "details": dict(request), "step": self._step_counter}
        self._social_actions.append(action)
        return {"status": "success", "action": action, "energy": self._energy[aid]}

    def _handle_neural_link(self, name: str, aid: int, request: dict) -> dict:
        target, error = self._target_agent(request)
        if error or target == aid:
            return error or {"status": "fail", "reason": "an agent cannot neural-link to itself"}
        if name == "neural_link_request_memory":
            request_id = f"nl-{self._new_id()}"
            record = {"request_id": request_id, "requester_id": aid, "target_id": target, "status": "pending", "step": self._step_counter}
            self._neural_requests[request_id] = record
            return {"status": "success", "request": record}
        request_id = str(request.get("request_id", ""))
        record = self._neural_requests.get(request_id)
        if not record or record["target_id"] != aid or record["requester_id"] != target:
            return {"status": "fail", "reason": "matching neural-link request not found"}
        content = str(request.get("content", request.get("memory", ""))).strip()
        if not content:
            return {"status": "fail", "reason": "request.content is required"}
        memory = {"id": self._new_id(), "agent_id": target, "source_agent_id": aid, "content": content, "shared_via": request_id, "step": self._step_counter}
        self._memories[target].append(memory)
        record.update({"status": "shared", "memory_id": memory["id"], "shared_step": self._step_counter})
        return {"status": "success", "request": dict(record), "memory": memory}

    def _move(self, aid: int, **position) -> dict:
        previous = dict(self._positions[aid])
        self._positions[aid].update(position)
        place = self._positions[aid].get("place")
        landmark = self._landmarks.get(place)
        if landmark:
            if "x" in landmark:
                self._positions[aid]["x"] = float(landmark["x"])
            if "z" in landmark:
                self._positions[aid]["z"] = float(landmark["z"])
        return {"status": "success", "previous": previous, "position": dict(self._positions[aid])}

    def _set_map(self, mapping: dict, key, value, field: str) -> dict:
        if value in (None, "", 0, {}): return {"status": "fail", "reason": f"request.{field} is required"}
        mapping[key] = value
        return {"status": "success", field: value}

    def _add_item(self, store: dict, aid: int, req: dict, field: str) -> dict:
        content = req.get(field, req.get("text", ""))
        if not content: return {"status": "fail", "reason": f"request.{field} is required"}
        item = {"id": self._new_id(), "agent_id": aid, "content": content, "date": req.get("date"), "step": self._step_counter}
        if isinstance(store[aid], dict): store[aid][item["id"]] = item
        else: store[aid].append(item)
        return {"status": "success", "item": item}

    def _remove_item(self, store: dict, aid: int, item_id: int) -> dict:
        values = store[aid]
        if isinstance(values, dict): removed = values.pop(item_id, None)
        else:
            removed = next((x for x in values if x["id"] == item_id), None)
            if removed: values.remove(removed)
        return {"status": "success" if removed else "fail", "removed": removed, "reason": None if removed else "item not found"}

    def _create_record(self, store: dict, aid: int, req: dict, kind: str) -> dict:
        rid = self._new_id()
        clean_request = {
            key: value
            for key, value in req.items()
            if key not in {"id", "owner_id", "kind", "created_step"}
        }
        record = {
            "id": rid,
            "owner_id": aid,
            "kind": kind,
            **clean_request,
            "created_step": self._step_counter,
        }
        store[rid] = record
        return {"status": "success", "item": record}

    def _update_record(self, store: dict, aid: int, req: dict) -> dict:
        rid = int(req.get("item_id", req.get("id", 0))); record = store.get(rid)
        if not record: return {"status": "fail", "reason": "item not found"}
        if record.get("owner_id") != aid: return {"status": "fail", "reason": "only the owner may edit"}
        record.update({k: v for k, v in req.items() if k not in {"id", "item_id", "owner_id"}})
        return {"status": "success", "item": record}

    def _delete_record(self, store: dict, aid: int, req: dict) -> dict:
        rid = int(req.get("routine_id", req.get("item_id", req.get("id", 0)))); record = store.get(rid)
        if not record or record.get("owner_id") != aid: return {"status": "fail", "reason": "owned item not found"}
        return {"status": "success", "deleted": store.pop(rid)}

    def _message(self, sender: int, target: int, content: str, nearby: bool) -> dict:
        if target not in self._mailboxes or not content: return {"status": "fail", "reason": "valid target_id and content required"}
        if nearby and self._positions[sender]["place"] != self._positions[target]["place"]: return {"status": "fail", "reason": "target is not nearby"}
        msg = {"id": self._new_id(), "sender_id": sender, "content": content, "step": self._step_counter}
        self._mailboxes[target].append(msg)
        return {"status": "success", "message": msg}

    def _append_embedded(self, name: str, aid: int, req: dict) -> dict:
        return {"id": self._new_id(), "kind": name, "agent_id": aid, **req, "step": self._step_counter}

    def _set_ad(self, aid: int, req: dict) -> dict:
        if self._advertisement and self._advertisement.get("expires_step", 0) > self._step_counter:
            return {"status": "fail", "reason": "advertising board is occupied"}
        try:
            duration = int(req.get("duration_steps", 12))
        except (TypeError, ValueError):
            return {"status": "fail", "reason": "duration_steps must be an integer"}
        if duration <= 0 or duration > self._max_events:
            return {"status": "fail", "reason": "duration_steps must be positive and bounded"}
        self._advertisement = {"owner_id": aid, **req, "expires_step": self._step_counter + duration}
        return {"status": "success", "advertisement": self._advertisement}

    def _execute_expression(self, req: dict) -> dict:
        code = str(req.get("code", ""))
        try:
            tree = ast.parse(code, mode="eval")
            allowed = (ast.Expression, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)
            if any(not isinstance(node, allowed) for node in ast.walk(tree)): raise ValueError("only literal arithmetic expressions are allowed")
            result = eval(compile(tree, "<ew-tool>", "eval"), {"__builtins__": {}}, {})
            return {"status": "success", "result": repr(result)[:4000]}
        except Exception as exc:
            return {"status": "fail", "reason": str(exc)}

    async def step(self, tick: int, t: datetime):
        self.t = t
        self._step_counter += 1
        self._dedup.clear()
        if self._advertisement and self._advertisement.get("expires_step", 0) <= self._step_counter: self._advertisement = None
        records = [{"agent_id": aid, "location": self._positions[aid]["place"], "mood": self._moods[aid], "memory_count": len(self._memories[aid]), "todo_count": len(self._todos[aid]), "relationship_count": sum(1 for k in self._relationships if k.startswith(f"{aid}:"))} for aid in self._agent_ids]
        await self._write_agent_state_batch(self._step_counter, t, records)
        await self._write_env_state(
            self._step_counter,
            t,
            event_count=len(self._event_log),
            blog_posts=len(self._blogs),
            community_events=len(self._events),
            archive_items=len(self._archive),
        )

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None: self._bind_workspace(workspace_path)
        if self._workspace_root is None: raise RuntimeError("EWToolSpace workspace is not bound")
        # Persist only domain state. Framework/runtime objects such as locks,
        # ToolManager, replay writers and LLM tool schemas must be reconstructed.
        keys = {
            "_agent_ids", "_names", "_homes", "_landmarks", "_manifesto", "_constitution",
            "_case_id", "_default_claim_status", "_active_public_tools",
            "_max_events", "_max_query_items", "_step_counter", "_next_id", "_positions",
            "_follows", "_facing", "_mailboxes", "_memories", "_souls", "_diaries", "_todos",
            "_calendars", "_moods", "_personalities", "_relationships", "_trust",
            "_blogs", "_archive", "_complaints", "_proposals", "_events", "_routines",
            "_advertisement", "_uploads", "_bricks", "_neural_requests", "_event_log", "_read_audit", "_usage",
            "_dedup", "_thoughts", "_social_actions", "_routine_runs", "_energy",
        }
        state = {key: getattr(self, key) for key in keys}
        atomic_write_text(self._workspace_root / _STATE_REL, json.dumps(state, ensure_ascii=False, indent=2, default=lambda x: sorted(x) if isinstance(x, set) else str(x)))

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path); path = self._workspace_root / _STATE_REL
        if not path.is_file(): return False
        state = json.loads(path.read_text(encoding="utf-8"))
        int_key_maps = {"_names", "_homes", "_positions", "_follows", "_facing", "_mailboxes", "_memories", "_souls", "_diaries", "_todos", "_calendars", "_moods", "_personalities", "_thoughts", "_energy"}
        record_maps = {"_blogs", "_archive", "_complaints", "_proposals", "_events", "_routines", "_uploads"}
        for key, value in state.items():
            if key in int_key_maps and isinstance(value, dict): value = {int(k): v for k, v in value.items()}
            if key in record_maps and isinstance(value, dict): value = {int(k): v for k, v in value.items()}
            if key == "_events" and isinstance(value, dict):
                for event in value.values():
                    for nested_name in ("participants", "invitations", "responses", "attendance"):
                        nested = event.get(nested_name)
                        if isinstance(nested, dict):
                            event[nested_name] = {
                                int(agent_id) if str(agent_id).lstrip("-").isdigit() else agent_id: status
                                for agent_id, status in nested.items()
                            }
            if key == "_usage" and isinstance(value, dict): value = {name: {int(k): count for k, count in counts.items()} for name, counts in value.items()}
            setattr(self, key, value)
        self._lock = asyncio.Lock()
        return True

    # Populate this class namespace with one independently registered MCP tool
    # per public EW name. This is declarative generation, not inheritance.
    for _tool_name in TOOL_CATEGORY:
        if _tool_name not in SPECIALIZED_TOOLS:
            locals()[_tool_name] = _make_catalog_tool(_tool_name, _tool_name in READONLY_TOOLS)
    del _tool_name
