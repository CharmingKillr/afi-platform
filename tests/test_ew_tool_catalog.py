"""B1 full-catalog, router registration, state, and scale tests."""
from __future__ import annotations

import asyncio
import importlib.util
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from afi.world.ew_tools import (
    EW_PUBLIC_TOOLS,
    EW_TOOL_SPECS,
    EW_TOOL_SPEC_BY_NAME,
    render_tool_catalog_markdown,
    tool_catalog_rows,
)
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


def _blog_class():
    return next(cls for cls in _classes() if cls.__name__ == "BlogSpace")


def test_all_113_public_ew_tools_are_codegen_registered():
    registered = set()
    for cls in _classes():
        registered.update(cls._registered_tools)
    assert set(EW_PUBLIC_TOOLS) <= registered
    assert len(EW_PUBLIC_TOOLS) == len(set(EW_PUBLIC_TOOLS)) == 113


def test_all_public_tools_have_auditable_specs_and_honest_validation_status():
    assert len(EW_TOOL_SPECS) == len(tool_catalog_rows()) == 113
    assert set(EW_TOOL_SPEC_BY_NAME) == set(EW_PUBLIC_TOOLS)
    assert all(spec.purpose and spec.owner and spec.validation for spec in EW_TOOL_SPECS)
    external = {spec.name for spec in EW_TOOL_SPECS if spec.validation == "provider_boundary_only"}
    assert external == {
        "do_deep_research_on_internet", "todays_news_from_human_world", "web_fetch",
        "browse_scientific_papers", "check_weather", "generate_image",
    }
    assert EW_TOOL_SPEC_BY_NAME["add_todo"].owner == "PlanningSpace"
    assert EW_TOOL_SPEC_BY_NAME["write_blog"].owner == "BlogSpace"
    assert EW_TOOL_SPEC_BY_NAME["send_message"].validation == "registered_and_router_tested"
    report = render_tool_catalog_markdown()
    assert report.count("\n| `") == 113
    assert "仅适配边界通过" in report


def test_full_scenario_has_one_owner_for_every_public_tool():
    config = build_init_config(load_scenario(ROOT / "scenarios" / "ew_full.yaml"))
    mounted = {item["module_type"] for item in config["env_modules"]}
    owners: dict[str, list[str]] = {}
    for cls in _classes():
        if cls.__name__ not in mounted:
            continue
        for name in cls._registered_tools:
            if name in EW_PUBLIC_TOOLS:
                owners.setdefault(name, []).append(cls.__name__)

    assert set(owners) == set(EW_PUBLIC_TOOLS)
    assert {name: values for name, values in owners.items() if len(values) != 1} == {}
    assert owners["add_todo"] == ["PlanningSpace"]
    assert owners["write_blog"] == ["BlogSpace"]


def test_full_scenario_mounts_catalog_with_scalable_bounds():
    config = build_init_config(load_scenario(ROOT / "scenarios" / "ew_full.yaml"))
    module = next(x for x in config["env_modules"] if x["module_type"] == "EWToolSpace")
    assert len(module["kwargs"]["agent_ids"]) == 5  # current public afi profile subset
    assert module["kwargs"]["max_events"] == 20000
    assert module["kwargs"]["max_query_items"] == 100
    assert module["kwargs"]["enabled_categories"] is None
    assert {x["module_type"] for x in config["env_modules"]} >= {"PlanningSpace", "BlogSpace"}


def test_generated_agentsociety_metadata_is_not_versioned():
    assert not (ROOT / ".agentsociety" / "env_modules" / "ewtoolspace.json").exists()
    assert ".agentsociety/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


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
            assert len(restored._registered_tools) == 89
    asyncio.run(run())


def test_blog_tools_have_a_single_specialized_owner():
    blog_tools = {"write_blog", "update_blog", "delete_blog", "comment_on_blog", "list_blogs", "read_blog"}
    assert blog_tools <= set(_blog_class()._registered_tools)
    assert not blog_tools & set(_ew_class()._registered_tools)


def test_blog_domain_contract_permissions_lifecycle_and_restore():
    async def run():
        cls = _blog_class()
        env = cls(agent_ids=[1, 2])
        draft = await env.write_blog(1, "Protocol", "Use explicit consent.")
        assert draft["ok"] and draft["blog"]["status"] == "draft"
        blog_id = draft["blog"]["id"]
        assert (await env.read_blog(2, blog_id))["ok"] is True
        assert (await env.update_blog(2, blog_id, title="Hijack"))["status"] == "fail"
        assert (await env.comment_on_blog(2, blog_id, "Useful."))["ok"] is True
        duplicate = await env.comment_on_blog(2, blog_id, "Useful.")
        assert duplicate["deduplicated"] is True
        published = await env.update_blog(1, blog_id, status="published", visibility="public")
        assert published["blog"]["status"] == "published"
        assert (await env.write_blog(1, "", "body"))["status"] == "fail"
        assert (await env.write_blog(1, "Title", "body", visibility="team"))["status"] == "fail"
        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[99])
            assert await restored.restore(directory)
            restored_blog = await restored.read_blog(1, blog_id)
            assert restored_blog["blog"]["title"] == "Protocol"
            assert len(restored_blog["blog"]["comments"]) == 1
            assert (await restored.list_blogs(2))["count"] == 1
    asyncio.run(run())
