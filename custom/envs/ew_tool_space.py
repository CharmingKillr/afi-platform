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

_STATE_REL = "state/ENV_STATE.json"

# Names already implemented by specialized modules and therefore deliberately
# not duplicated here.  The B1 coverage test checks the union of all modules.
SPECIALIZED_TOOLS = {
    "list_landmarks", "send_message",
    "submit_grant_pitch", "vote_for_pitch", "list_credit_pitches",
    "deposit_credits_to_bank", "withdraw_credits_from_bank", "take_bank_loan",
    "repay_bank_loan", "check_bank_balance", "transact_compute_credits",
    "victory_arch_pitch_winners",
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
    "web_fetch browse_scientific_papers search_archive archive_index read_billboard "
    "extract_code_for_tool read_agent_manifesto browse_tool_registry check_weather "
    "tool_usage_analytics_by_character overall_tool_usage_analytics_by_date "
    "social_event_history check_complaint_status list_community_events check_agent_trust "
    "read_advertisements list_blogs read_blog read_personality list_routines".split()
)


def _make_catalog_tool(name: str, readonly: bool):
    """Create one named MCP tool with a stable extensible request envelope."""
    async def generated(self, agent_id: int, request: dict | None = None) -> dict:
        return await self._dispatch(name, int(agent_id), request or {})

    generated.__name__ = name
    generated.__qualname__ = f"EWToolSpace.{name}"
    generated.__doc__ = (
        f"EW {TOOL_CATEGORY[name]} operation **{name}**.\n\n"
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
        ColumnDef("billboard_posts", "INTEGER"),
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
        **kwargs,
    ):
        super().__init__()
        requested_categories = set(enabled_categories or _CATEGORY_NAMES)
        unknown_categories = requested_categories - set(_CATEGORY_NAMES)
        if unknown_categories:
            raise ValueError(f"unknown EW tool categories: {sorted(unknown_categories)}")
        self._enabled_categories = sorted(requested_categories)
        allowed_tools = {name for name, category in TOOL_CATEGORY.items() if category in requested_categories}
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
        self._billboard: dict[int, dict] = {}
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
        self._usage: dict[str, dict[int, int]] = {}
        self._dedup: dict[str, dict] = {}
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
        """

    def _new_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _limit(self, request: dict) -> int:
        return min(self._max_query_items, max(1, int(request.get("limit", 20))))

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

    async def _dispatch(self, name: str, aid: int, req: dict) -> dict:
        async with self._lock:
            if aid not in self._agent_ids:
                return {"status": "fail", "reason": "unknown agent_id"}
            # Navigation and observation.
            if name in {"go_to_place", "run_to_place"}:
                place = str(req.get("place", req.get("landmark", ""))).strip()
                if not place:
                    return {"status": "fail", "reason": "request.place is required"}
                return self._write_once(name, aid, req, lambda: self._move(aid, place=place, speed="run" if name.startswith("run") else "walk"))
            if name == "go_home":
                return self._write_once(name, aid, req, lambda: self._move(aid, place=self._homes.get(aid, "home"), speed="walk"))
            if name == "go_to_coordinates":
                return self._write_once(name, aid, req, lambda: self._move(aid, x=float(req.get("x", 0)), z=float(req.get("z", 0))))
            if name == "turn_towards":
                return self._write_once(name, aid, req, lambda: self._set_map(self._facing, aid, int(req.get("target_id", 0)), "target_id"))
            if name == "follow_agent":
                return self._write_once(name, aid, req, lambda: self._set_map(self._follows, aid, int(req.get("target_id", 0)), "target_id"))
            if name == "get_distance_to":
                target = int(req.get("target_id", 0))
                a, b = self._positions[aid], self._positions.get(target, {})
                distance = ((a.get("x", 0)-b.get("x", 0))**2 + (a.get("z", 0)-b.get("z", 0))**2) ** .5 if b else None
                return {"agent_id": aid, "target_id": target, "distance": distance, "same_place": bool(b and a.get("place") == b.get("place"))}
            if name == "list_agents":
                return {"agents": [{"id": x, "name": self._names.get(x, str(x)), **self._positions[x]} for x in self._agent_ids][:self._limit(req)]}
            if name == "get_nearby":
                place = self._positions[aid]["place"]
                return {"place": place, "agents": [x for x in self._agent_ids if x != aid and self._positions[x]["place"] == place]}

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
                query = str(req.get("query", req.get("date", ""))).lower()
                if query:
                    values = [v for v in values if query in json.dumps(v, ensure_ascii=False).lower()]
                return {"items": values[-self._limit(req):]}
            if name == "change_name":
                return self._write_once(name, aid, req, lambda: self._set_map(self._names, aid, str(req.get("name", "")).strip(), "name"))

            # Public record stores.
            create_map = {
                "add_to_billboard": self._billboard, "write_blog": self._blogs, "publish_to_archive": self._archive,
                "file_complaint": self._complaints, "submit_townhall_proposal": self._proposals,
                "propose_community_event": self._events, "create_personal_event": self._events,
                "create_routine": self._routines, "upload_data_for_sharing": self._uploads,
            }
            if name in create_map:
                return self._write_once(name, aid, req, lambda: self._create_record(create_map[name], aid, req, name))
            read_map = {
                "read_billboard": self._billboard, "list_blogs": self._blogs, "read_blog": self._blogs,
                "search_archive": self._archive, "archive_index": self._archive,
                "list_proposals": self._proposals, "read_townhall_proposal": self._proposals,
                "check_complaint_status": self._complaints, "list_community_events": self._events,
                "list_routines": self._routines,
            }
            if name in read_map:
                item_id = int(req.get("item_id", req.get("id", 0)))
                if item_id:
                    return {"item": read_map[name].get(item_id)}
                return {"items": self._items(read_map[name], req)}
            if name in {"edit_billboard", "update_blog", "update_proposal"}:
                store = {"edit_billboard": self._billboard, "update_blog": self._blogs, "update_proposal": self._proposals}[name]
                return self._write_once(name, aid, req, lambda: self._update_record(store, aid, req))
            if name in {"delete_from_billboard", "delete_blog", "delete_routine"}:
                store = {"delete_from_billboard": self._billboard, "delete_blog": self._blogs, "delete_routine": self._routines}[name]
                return self._write_once(name, aid, req, lambda: self._delete_record(store, aid, req))

            # Relationships, trust, messages, events, reactions and other social actions.
            if name == "assign_relationship":
                target = int(req.get("target_id", 0)); key = f"{aid}:{target}"
                return self._write_once(name, aid, req, lambda: self._set_map(self._relationships, key, {"agent_id": aid, "target_id": target, "type": req.get("type", "acquaintance")}, "target_id"))
            if name == "rate_agent_trust":
                target = int(req.get("target_id", 0)); key = f"{aid}:{target}"
                rating = min(5, max(1, int(req.get("rating", 3))))
                return self._write_once(name, aid, req, lambda: self._set_map(self._trust, key, {"rater": aid, "target": target, "rating": rating, "reason": req.get("reason", "")}, "target_id"))
            if name == "check_agent_trust":
                target = int(req.get("target_id", 0)); ratings = [v["rating"] for v in self._trust.values() if v["target"] == target]
                return {"target_id": target, "average": sum(ratings)/len(ratings) if ratings else None, "ratings": len(ratings)}
            if name == "read_messages":
                items = self._mailboxes[aid][-self._limit(req):]
                return {"messages": items}
            if name == "say_to_agent":
                target = int(req.get("target_id", 0))
                return self._write_once(name, aid, req, lambda: self._message(aid, target, str(req.get("content", "")), nearby=True))
            if name in {"reply_to_billboard", "react_to_billboard", "comment_on_blog", "comment_on_proposal", "vote_on_proposal", "submit_final_report", "invite_to_event", "accept_event_invitation", "decline_event_invitation", "review_event", "rsvp_to_event", "event_present", "event_respond", "neural_link_request_memory", "neural_link_share_memory"}:
                return self._write_once(name, aid, req, lambda: {"status": "success", "record": self._append_embedded(name, aid, req)})
            if name == "read_constitution": return {"constitution": self._constitution}
            if name == "read_agent_manifesto": return {"manifesto": self._manifesto}

            # Routines, construction, advertising and generic embodied actions.
            if name == "run_routine":
                rid = int(req.get("routine_id", req.get("item_id", 0))); routine = self._routines.get(rid)
                return {"status": "success" if routine else "fail", "routine": routine, "reason": None if routine else "routine not found"}
            if name == "put_brick_in_pixel":
                key = f"{req.get('x',0)}:{req.get('y',0)}:{req.get('z',0)}"
                return self._write_once(name, aid, req, lambda: self._set_map(self._bricks, key, {"owner": aid, **req}, "coordinates"))
            if name == "post_advertisements":
                return self._write_once(name, aid, req, lambda: self._set_ad(aid, req))
            if name == "read_advertisements": return {"advertisement": self._advertisement}
            if name in {"show_emoticon", "set_mood_and_terminate"}:
                mood = str(req.get("mood", req.get("emoticon", "neutral")))
                return self._write_once(name, aid, req, lambda: self._set_map(self._moods, aid, mood, "mood"))
            if name in {"think_aloud", "put_on_fire", "pray", "self_care", "idle", "recharge_energy", "physical_action", "dance", "take_picture", "ignore"}:
                return self._write_once(name, aid, req, lambda: {"status": "success", "action": name, "details": req})

            # Analytics and externally fulfilled capabilities.
            if name == "browse_tool_registry":
                return {"tools": sorted(TOOL_CATEGORY), "count": len(TOOL_CATEGORY)}
            if name == "tool_usage_analytics_by_character":
                return {"agent_id": int(req.get("target_id", aid)), "usage": {k: v.get(int(req.get("target_id", aid)), 0) for k, v in self._usage.items()}}
            if name == "overall_tool_usage_analytics_by_date":
                return {"usage": {k: sum(v.values()) for k, v in self._usage.items()}}
            if name == "social_event_history": return {"events": self._event_log[-self._limit(req):]}
            if name == "extract_code_for_tool": return {"status": "fail", "reason": "source extraction is unavailable in the clean-room catalog"}
            if name == "execute_python_code_tool": return self._execute_expression(req)
            if name in {"do_deep_research_on_internet", "todays_news_from_human_world", "web_fetch", "browse_scientific_papers", "check_weather", "generate_image"}:
                # The environment deliberately does not fabricate live external
                # results. A deterministic request key lets a configured adapter
                # correlate the request without mutating a readonly call.
                request_id = hashlib.sha256(json.dumps([name, aid, req], sort_keys=True, default=str).encode()).hexdigest()[:16]
                return {"status": "in_progress", "request_id": request_id, "response": "queued for the configured external capability provider"}
            return {"status": "error", "reason": f"unhandled tool {name}"}

    def _move(self, aid: int, **position) -> dict:
        self._positions[aid].update(position)
        return {"status": "success", "position": dict(self._positions[aid])}

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
        rid = self._new_id(); record = {"id": rid, "owner_id": aid, "kind": kind, **req, "created_step": self._step_counter}
        store[rid] = record
        return {"status": "success", "item": record}

    def _update_record(self, store: dict, aid: int, req: dict) -> dict:
        rid = int(req.get("item_id", req.get("id", 0))); record = store.get(rid)
        if not record: return {"status": "fail", "reason": "item not found"}
        if record.get("owner_id") != aid: return {"status": "fail", "reason": "only the owner may edit"}
        record.update({k: v for k, v in req.items() if k not in {"id", "item_id", "owner_id"}})
        return {"status": "success", "item": record}

    def _delete_record(self, store: dict, aid: int, req: dict) -> dict:
        rid = int(req.get("item_id", req.get("id", 0))); record = store.get(rid)
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
        if self._advertisement and self._advertisement.get("expires_step", 0) > self._step_counter: return {"status": "fail", "reason": "advertising board is occupied"}
        self._advertisement = {"owner_id": aid, **req, "expires_step": self._step_counter + int(req.get("duration_steps", 12))}
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
        await self._write_env_state(self._step_counter, t, event_count=len(self._event_log), billboard_posts=len(self._billboard), blog_posts=len(self._blogs), community_events=len(self._events), archive_items=len(self._archive))

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None: self._bind_workspace(workspace_path)
        if self._workspace_root is None: raise RuntimeError("EWToolSpace workspace is not bound")
        # Persist only domain state. Framework/runtime objects such as locks,
        # ToolManager, replay writers and LLM tool schemas must be reconstructed.
        keys = {
            "_agent_ids", "_names", "_homes", "_landmarks", "_manifesto", "_constitution",
            "_max_events", "_max_query_items", "_step_counter", "_next_id", "_positions",
            "_follows", "_facing", "_mailboxes", "_memories", "_souls", "_diaries", "_todos",
            "_calendars", "_moods", "_personalities", "_relationships", "_trust", "_billboard",
            "_blogs", "_archive", "_complaints", "_proposals", "_events", "_routines",
            "_advertisement", "_uploads", "_bricks", "_neural_requests", "_event_log", "_usage",
            "_dedup",
        }
        state = {key: getattr(self, key) for key in keys}
        atomic_write_text(self._workspace_root / _STATE_REL, json.dumps(state, ensure_ascii=False, indent=2, default=lambda x: sorted(x) if isinstance(x, set) else str(x)))

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path); path = self._workspace_root / _STATE_REL
        if not path.is_file(): return False
        state = json.loads(path.read_text(encoding="utf-8"))
        int_key_maps = {"_names", "_homes", "_positions", "_follows", "_facing", "_mailboxes", "_memories", "_souls", "_diaries", "_todos", "_calendars", "_moods", "_personalities"}
        record_maps = {"_billboard", "_blogs", "_archive", "_complaints", "_proposals", "_events", "_routines", "_uploads"}
        for key, value in state.items():
            if key in int_key_maps and isinstance(value, dict): value = {int(k): v for k, v in value.items()}
            if key in record_maps and isinstance(value, dict): value = {int(k): v for k, v in value.items()}
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
