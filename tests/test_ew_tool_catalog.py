"""B1 full-catalog, router registration, state, and scale tests."""
from __future__ import annotations

import asyncio
import importlib.util
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from afi.world.ew_tools import EW_PUBLIC_TOOLS
from afi.world.scenario import build_init_config, load_scenario


ROOT = Path(__file__).parents[1]
PY_FILES = sorted((ROOT / "custom" / "envs").glob("*.py"))


def _classes():
    classes = []
    for index, path in enumerate(PY_FILES):
        spec = importlib.util.spec_from_file_location(f"afi_test_env_{index}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        classes.extend(
            value for value in vars(module).values()
            if isinstance(value, type) and value.__module__ == module.__name__ and hasattr(value, "_registered_tools")
        )
    return classes


def _ew_class():
    return next(cls for cls in _classes() if cls.__name__ == "EWToolSpace")


def test_all_113_public_ew_tools_are_codegen_registered():
    registered = set()
    for cls in _classes():
        registered.update(cls._registered_tools)
    assert set(EW_PUBLIC_TOOLS) <= registered
    assert len(EW_PUBLIC_TOOLS) == len(set(EW_PUBLIC_TOOLS)) == 113


def test_full_scenario_mounts_catalog_with_scalable_bounds():
    config = build_init_config(load_scenario(ROOT / "scenarios" / "ew_full.yaml"))
    module = next(x for x in config["env_modules"] if x["module_type"] == "EWToolSpace")
    assert len(module["kwargs"]["agent_ids"]) == 5  # current public afi profile subset
    assert module["kwargs"]["max_events"] == 20000
    assert module["kwargs"]["max_query_items"] == 100
    assert module["kwargs"]["enabled_categories"] is None


def test_category_gating_reduces_active_router_surface():
    env = _ew_class()(enabled_categories=["navigation", "memory"])
    active = {item["function"]["name"] for item in env._llm_tools}
    assert active == {
        "go_to_place", "go_home", "run_to_place", "go_to_coordinates", "turn_towards",
        "get_distance_to", "list_agents", "get_nearby", "follow_agent",
        "add_to_longterm_memory", "remove_from_memory", "retrieve_specific_memories",
        "add_to_soul", "remove_from_soul", "write_diary", "search_diary_for_keywords",
        "show_diary_entries_from_day",
    }


def test_every_catalog_handler_returns_without_unhandled_error():
    async def run():
        env = _ew_class()(agent_ids=list(range(1, 11)))
        request = {
            "target_id": 2, "content": "test", "title": "test", "query": "test",
            "place": "Central Plaza", "item_id": 1, "rating": 4, "code": "1 + 2",
            "x": 1, "y": 1, "z": 1,
        }
        for name in env._registered_tools:
            result = await getattr(env, name)(1, request)
            assert isinstance(result, dict), name
            assert not (result.get("status") == "error" and "unhandled" in result.get("reason", "")), name
            if not env._readonly_tools[name]:
                assert result.get("status") in {"success", "fail", "in_progress", "error"}, name
    asyncio.run(run())


def test_same_step_idempotency_bounded_queries_and_360_step_scale():
    async def run():
        env = _ew_class()(agent_ids=list(range(1, 101)), max_events=1000, max_query_items=25)
        first = await env.add_to_longterm_memory(1, {"content": "same"})
        second = await env.add_to_longterm_memory(1, {"content": "same"})
        assert first["item"]["id"] == second["item"]["id"]
        assert second["deduplicated"] is True
        start = datetime(2026, 1, 1)
        for step in range(360):
            env._step_counter += 1
            env._dedup.clear()
            await env.think_aloud(1, {"content": f"step-{step}"})
        assert len(env._event_log) <= 1000
        listing = await env.list_agents(1, {"limit": 500})
        assert len(listing["agents"]) == 25
    asyncio.run(run())


def test_m4_counts_catalog_actions():
    from afi.audit.awi import _m4_tools
    spans = [
        {"name": "react.tool", "resource": {"agent.id": 1}, "attributes": {"react.action": name}}
        for name in ("go_to_place", "write_blog", "rate_agent_trust", "create_routine")
    ]
    assert _m4_tools(spans) == ({1: 4}, 4.0)


def test_resume_restores_domain_state_without_clobbering_router():
    async def run():
        cls = _ew_class()
        env = cls(agent_ids=[1, 2])
        await env.add_to_longterm_memory(1, {"content": "persistent"})
        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[1, 2])
            assert await restored.restore(directory)
            assert restored._memories[1][0]["content"] == "persistent"
            assert restored._tool_manager is not None
            assert len(restored._registered_tools) == 101
    asyncio.run(run())
