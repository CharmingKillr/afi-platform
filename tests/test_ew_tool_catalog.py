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
    render_tool_contract_markdown,
    tool_contract_rows,
    tool_catalog_rows,
    validate_tool_arguments,
    validate_tool_request,
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


def _specialized_instances():
    """Build representative owners so registry fields can be checked against runtime schemas."""
    classes = {cls.__name__: cls for cls in _classes()}
    agent_ids = list(range(1, 6))
    return {
        "SimpleSocialSpaceAuditable": classes["SimpleSocialSpaceAuditable"](
            agent_id_name_pairs=[(agent_id, f"Agent {agent_id}") for agent_id in agent_ids]
        ),
        "PlanningSpace": classes["PlanningSpace"](agent_ids=agent_ids),
        "GovernanceSpace": classes["GovernanceSpace"](num_agents=5),
        "BlogSpace": classes["BlogSpace"](agent_ids=agent_ids),
        "BillboardSpace": classes["BillboardSpace"](agent_ids=agent_ids, case_id="PIC-001"),
        "CommunitySpace": classes["CommunitySpace"](agent_ids=agent_ids, case_id="PIC-001"),
        "EconomySpace": classes["EconomySpace"](
            persons=[
                {
                    "id": agent_id,
                    "currency": 100,
                    "skill": "citizen",
                    "consumption": 0,
                    "income": 0,
                }
                for agent_id in agent_ids
            ]
        ),
    }


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
    assert {
        spec.name for spec in EW_TOOL_SPECS if spec.validation == "generic_contract_tested"
    } == {
        spec.name for spec in EW_TOOL_SPECS if spec.implementation == "generic_local"
    }
    assert EW_TOOL_SPEC_BY_NAME["add_todo"].owner == "PlanningSpace"
    assert EW_TOOL_SPEC_BY_NAME["write_blog"].owner == "BlogSpace"
    assert EW_TOOL_SPEC_BY_NAME["send_message"].validation == "registered_and_router_tested"
    report = render_tool_catalog_markdown()
    assert report.count("\n| `") == 113
    assert "仅适配边界通过" in report


def test_b1_contract_registry_covers_inputs_permissions_and_generic_validation():
    rows = tool_contract_rows()
    assert len(rows) == 113
    assert {row["name"] for row in rows} == set(EW_PUBLIC_TOOLS)
    assert {row["owner"] for row in rows if row["owner"] == "CommunitySpace"} == {"CommunitySpace"}
    assert sum(row["owner"] == "CommunitySpace" for row in rows) == 6
    assert EW_TOOL_SPEC_BY_NAME["rate_agent_trust"].contract.input_mode == "explicit"
    assert EW_TOOL_SPEC_BY_NAME["send_message"].contract.actor_field.name == "sender_id"
    assert EW_TOOL_SPEC_BY_NAME["write_blog"].contract.actor_field.name == "agent_id"
    assert EW_TOOL_SPEC_BY_NAME["go_to_place"].contract.input_mode == "envelope"
    assert EW_TOOL_SPEC_BY_NAME["read_messages"].contract.input_mode == "envelope"
    assert EW_TOOL_SPEC_BY_NAME["submit_townhall_proposal"].contract.input_mode == "envelope"
    assert [field.name for field in EW_TOOL_SPEC_BY_NAME["submit_townhall_proposal"].contract.required_fields] == [
        "article_id", "title", "new_text"
    ]
    assert {field.name for field in EW_TOOL_SPEC_BY_NAME["write_blog"].contract.optional_fields} >= {
        "case_id", "artifact_id", "claim_status", "evidence_refs"
    }
    assert [field.name for field in EW_TOOL_SPEC_BY_NAME["add_todo"].contract.required_fields] == ["task"]
    assert [field.name for field in EW_TOOL_SPEC_BY_NAME["deposit_credits_to_bank"].contract.required_fields] == ["amount"]
    assert [field.name for field in EW_TOOL_SPEC_BY_NAME["check_calendar"].contract.optional_fields] == ["limit"]
    assert [field.name for field in EW_TOOL_SPEC_BY_NAME["transact_compute_credits"].contract.optional_fields] == ["mode"]
    assert validate_tool_request("go_to_place", {}) == (False, "request.place is required")
    assert validate_tool_request("go_to_place", {"place": "Town Hall"}) == (True, None)
    assert validate_tool_request("go_to_coordinates", {"x": "bad", "z": 1})[0] is False
    assert validate_tool_request("submit_townhall_proposal", {})[0] is False
    assert validate_tool_request(
        "submit_townhall_proposal",
        {"article_id": 2, "title": "Evidence", "new_text": "Require sources."},
    ) == (True, None)
    assert validate_tool_arguments(
        "send_message",
        {"sender_id": 1, "receiver_id": 2, "content": "Check the artifact first."},
    ) == (True, None)
    assert validate_tool_arguments(
        "send_message", {"receiver_id": 2, "content": "missing sender"}
    ) == (False, "arguments.sender_id is required")
    assert validate_tool_arguments(
        "write_blog", {"agent_id": 1, "title": "Evidence", "content": "Unverified."}
    ) == (True, None)
    assert validate_tool_arguments(
        "submit_townhall_proposal",
        {
            "agent_id": 1,
            "request": {"article_id": 2, "title": "Evidence", "new_text": "Require sources."},
        },
    ) == (True, None)
    assert validate_tool_arguments(
        "transact_compute_credits", {"agent_id": 1, "target_id": 2, "amount": "bad"}
    )[0] is False
    contract_report = render_tool_contract_markdown()
    assert contract_report.count("\n| `") == 113
    assert "可选字段" in contract_report
    assert "artifact_id" in contract_report
    assert "主体字段" in contract_report


def test_contract_registry_matches_specialized_model_facing_schemas():
    """The registry must describe the schema the LLM actually receives."""
    instances = _specialized_instances()
    for spec in EW_TOOL_SPECS:
        instance = instances.get(spec.owner)
        if instance is None:
            continue
        tool_schema = next(
            item for item in instance._llm_tools
            if item["function"]["name"] == spec.name
        )["function"]
        parameters = tool_schema["parameters"]
        properties = set(parameters.get("properties", {}))
        required = set(parameters.get("required", []))
        contract = spec.contract
        actor = contract.actor_field.name
        if contract.input_mode == "envelope":
            assert properties == {actor, "request"}, spec.name
            assert required == {actor}, spec.name
            continue
        expected_properties = {
            actor,
            *(field.name for field in contract.required_fields),
            *(field.name for field in contract.optional_fields),
        }
        expected_required = {
            actor,
            *(field.name for field in contract.required_fields),
        }
        assert properties == expected_properties, spec.name
        assert required == expected_required, spec.name


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


def test_pr2_awi_envs_are_available_as_opt_in_scenario_modules():
    scenario = load_scenario(ROOT / "scenarios" / "ew_full.yaml")
    scenario["envs"] = ["EWMobilitySpace", "RelationshipSpace"]
    config = build_init_config(scenario)
    assert [item["module_type"] for item in config["env_modules"]] == [
        "EWMobilitySpace",
        "RelationshipSpace",
    ]
    assert config["env_modules"][0]["kwargs"]["agent_ids"] == [1, 2, 3, 4, 5]


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


def test_every_generic_tool_has_a_minimum_contract_path():
    """The 68 EWToolSpace registrations must all have an explicit dispatch path."""
    async def run():
        env = _ew_class()(agent_ids=[1, 2, 3])
        sample_by_type = {
            "integer": 2,
            "number": 1,
            "array": [],
            "object": {},
            "boolean": True,
            "string_or_object": "sample",
            "string": "sample",
        }
        for name in env._registered_tools:
            contract = EW_TOOL_SPEC_BY_NAME[name].contract
            request = {
                field.name: sample_by_type.get(field.type, "sample")
                for field in contract.required_fields
            }
            valid, reason = validate_tool_request(name, request)
            assert valid, (name, reason)
            result = await getattr(env, name)(1, request)
            assert isinstance(result, dict), name
            assert "unhandled tool" not in str(result.get("reason", "")), name

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
            # Billboard's six public names and the specialized names below
            # are mounted by their dedicated owners rather than duplicated in
            # EWToolSpace.
            assert len(restored._registered_tools) == 68
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


def test_generic_domains_have_stateful_lifecycle_and_restore():
    """Exercise the first domainized slice of the EW-sized generic surface."""
    async def run():
        cls = _ew_class()
        env = cls(
            agent_ids=[1, 2, 3],
            homes={1: "Home", 2: "Home", 3: "Town Hall"},
            landmarks=[{"name": "Town Hall", "x": 10, "z": 20}],
        )
        env.t = datetime(2026, 8, 6, 8)

        moved = await env.go_to_place(1, {"place": "Town Hall"})
        assert moved["status"] == "success"
        assert moved["position"]["x"] == 10.0
        assert (await env.get_distance_to(1, {"target_id": 99}))["status"] == "fail"

        event = await env.create_personal_event(
            1,
            {"content": "Evidence review", "location": "Town Hall", "starts_at": "2026-08-06T09:00:00"},
        )
        assert event["status"] == "success"
        event_id = event["event"]["id"]
        invited = await env.invite_to_event(1, {"event_id": event_id, "target_id": 2})
        assert invited["invited_id"] == 2
        accepted = await env.accept_event_invitation(2, {"event_id": event_id})
        assert accepted["event"]["responses"]["2"] == "accepted"
        present = await env.event_present(2, {"event_id": event_id})
        assert present["present"] is True
        review = await env.review_event(2, {"event_id": event_id, "rating": 5, "content": "Clear evidence."})
        assert review["status"] == "success"

        routine = await env.create_routine(
            1,
            {"content": "Review routine", "steps": ["read_messages", "write_diary"]},
        )
        routine_id = routine["routine"]["id"]
        run = await env.run_routine(1, {"routine_id": routine_id})
        assert run["status"] == "success"
        assert run["routine"]["run_count"] == 1
        assert (await env.run_routine(2, {"routine_id": routine_id}))["status"] == "fail"
        temporary = await env.create_routine(1, {"content": "Temporary routine"})
        assert (await env.delete_routine(1, {"routine_id": temporary["routine"]["id"]}))["status"] == "success"
        assert all(item["id"] != temporary["routine"]["id"] for item in (await env.list_routines(1, {}))["items"])

        archive = await env.publish_to_archive(1, {"content": "Reproducible artifact", "tags": ["evidence"]})
        assert archive["status"] == "success"
        assert (await env.search_archive(2, {"query": "reproducible"}))["items"]
        assert (await env.archive_index(2, {}))["tag_counts"] == {"evidence": 1}
        upload = await env.upload_data_for_sharing(1, {"content": {"artifact": "local"}})
        assert upload["item"]["checksum"]

        link = await env.neural_link_request_memory(1, {"target_id": 2})
        request_id = link["request"]["request_id"]
        shared = await env.neural_link_share_memory(
            2,
            {"target_id": 1, "request_id": request_id, "content": "Shared context"},
        )
        assert shared["status"] == "success"
        assert any(item["content"] == "Shared context" for item in env._memories[1])

        thought = await env.think_aloud(1, {"content": "The event is ready."})
        assert thought["thought"]["visibility"] == "private"

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[1, 2, 3], landmarks=[{"name": "Town Hall", "x": 10, "z": 20}])
            assert await restored.restore(directory) is True
            assert restored._events[event_id]["attendance"][2] is True
            assert restored._routines[routine_id]["run_count"] == 1
            assert restored._routine_runs[0]["routine_id"] == routine_id
            assert restored._thoughts[1][0]["content"] == "The event is ready."
            assert restored._uploads[upload["item"]["id"]]["kind"] == "shared_data"

    asyncio.run(run())
