"""PIC-001 configuration, tool-surface, and domain-chain tests.

These tests intentionally stop at deterministic environment contracts. They do
not call an LLM or run the eight-hour society pilot.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from afi.world.ew_tools import EW_PUBLIC_TOOLS
from afi.world.scenario import build_init_config, build_steps, load_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenarios" / "public_information_crisis" / "public_information_crisis.yaml"


def _classes() -> dict[str, type]:
    classes: dict[str, type] = {}
    for index, path in enumerate(sorted((ROOT / "custom" / "envs").glob("*.py"))):
        spec = importlib.util.spec_from_file_location(f"pic_test_env_{index}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        for value in vars(module).values():
            if isinstance(value, type) and value.__module__ == module.__name__ and hasattr(value, "_registered_tools"):
                classes[value.__name__] = value
    return classes


def _active_names(env) -> set[str]:
    return {item["function"]["name"] for item in env._llm_tools}


def _pic_envs():
    config = build_init_config(load_scenario(SCENARIO))
    classes = _classes()
    envs = []
    for entry in config["env_modules"]:
        envs.append(classes[entry["module_type"]](**entry["kwargs"]))
    return config, envs


def test_pic_yaml_builds_six_envs_five_agents_and_exact_29_tool_surface():
    scenario = load_scenario(SCENARIO)
    config, envs = _pic_envs()
    assert sum(step.get("num_steps", 0) for step in scenario["steps"] if step.get("type") == "run") == 8
    assert scenario["steps"][-1]["type"] == "run"
    assert len(config["agents"]) == 5
    assert [module.name for module in envs] == [
        "LandmarkSpace",
        "SimpleSocialSpaceAuditable",
        "BlogSpace",
        "BillboardSpace",
        "CommunitySpace",
        "GovernanceSpace",
        "EconomySpace",
        "EWToolSpace",
    ]

    active_by_env = {module.name: _active_names(module) for module in envs}
    assert active_by_env["LandmarkSpace"] == {"list_landmarks"}
    assert active_by_env["SimpleSocialSpaceAuditable"] == {"send_message", "read_messages"}
    assert active_by_env["BlogSpace"] == {
        "write_blog", "update_blog", "delete_blog", "comment_on_blog", "list_blogs", "read_blog"
    }
    assert active_by_env["BillboardSpace"] == {
        "add_to_billboard", "read_billboard", "reply_to_billboard", "react_to_billboard",
    }
    assert active_by_env["CommunitySpace"] == {
        "rate_agent_trust", "check_agent_trust",
    }
    assert active_by_env["GovernanceSpace"] == {
        "read_constitution", "list_proposals", "read_townhall_proposal",
        "submit_townhall_proposal", "comment_on_proposal", "update_proposal",
        "vote_on_proposal", "submit_final_report",
    }
    assert active_by_env["EconomySpace"] == {
        "submit_grant_pitch", "list_credit_pitches", "vote_for_pitch"
    }
    assert active_by_env["EWToolSpace"] == {
        "read_agent_manifesto", "browse_tool_registry",
        "tool_usage_analytics_by_character",
    }

    active = set().union(*active_by_env.values())
    assert active == set(load_scenario(SCENARIO)["world"]["ew_enabled_tools"])
    assert active <= set(EW_PUBLIC_TOOLS)
    assert sum(len(names) for names in active_by_env.values()) == 29


def test_contract_mode_filters_autonomy_windows_and_supports_bounded_smoke():
    scenario = load_scenario(SCENARIO)
    scenario["execution"] = {"mode": "contract", "max_checkpoints": 2}
    start_t, steps = build_steps(scenario)
    assert start_t == "2026-07-01T08:00:00"
    assert len(steps) == 2
    assert all(step["type"] == "intervene" for step in steps)


def test_structured_manifest_covers_all_29_public_tools_and_46_calls():
    from scenarios.public_information_crisis.verify_structured_run import expected_calls

    expected = expected_calls(load_scenario(SCENARIO))
    assert len(expected) == 46
    assert {item["tool"] for item in expected} == set(load_scenario(SCENARIO)["world"]["ew_enabled_tools"])


def test_pic_router_can_mount_exact_surface_without_duplicate_public_names():
    async def run():
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(
            env_modules=envs,
            template_cache_enabled=False,
        )
        public_names = [
            item["function"]["name"]
            for module in router.env_modules
            for item in module._llm_tools
            if item["function"]["name"] in EW_PUBLIC_TOOLS
        ]
        assert len(public_names) == 29
        assert len(public_names) == len(set(public_names))

    asyncio.run(run())


def _fake_tool_response(name: str | None = None, arguments: str = "{}", *, call_id: str = "call-1", content: str = ""):
    tool_calls = []
    if name is not None:
        tool_calls.append(
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(name=name, arguments=arguments),
            )
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls)
            )
        ]
    )


def test_structured_autonomy_uses_native_tool_calls_and_never_enters_codegen(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("AFI_PIC001_ROUTER_MODE", "structured")
        monkeypatch.setenv("AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS", "3")
        monkeypatch.setenv("AFI_PIC001_DISABLE_THINKING", "true")
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(env_modules=envs, template_cache_enabled=False)
        router.run_dir = tmp_path
        responses = [
            _fake_tool_response("list_landmarks", '{"agent_id": 2}'),
            _fake_tool_response(content="The landmark directory was inspected."),
        ]
        llm_requests = []

        async def fake_completion(**kwargs):
            llm_requests.append(kwargs)
            return responses.pop(0)

        router.acompletion_with_system_prompt = fake_completion
        result, answer = await router.ask({}, "Inspect the available landmarks.")

        assert result["status"] == "success"
        assert result["list_landmarks"]["status"] == "success"
        assert "landmark directory" in answer
        assert len(llm_requests) == 2
        assert llm_requests[0]["tool_choice"] == "auto"
        assert llm_requests[0]["max_tokens"] == 512
        assert llm_requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
        assert {item["function"]["name"] for item in llm_requests[0]["tools"]} == set(
            load_scenario(SCENARIO)["world"]["ew_enabled_tools"]
        )
        log = (tmp_path / "artifacts" / "pic001_structured_call_log.jsonl").read_text()
        record = json.loads(log.strip())
        assert record["mode"] == "structured_autonomy"
        assert record["tool"] == "list_landmarks"
        assert record["args"] == {"agent_id": 2}

    asyncio.run(run())


def test_structured_autonomy_stages_readonly_tools_by_request_domain(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("AFI_PIC001_ROUTER_MODE", "structured")
        monkeypatch.setenv("AFI_PIC001_STRUCTURED_TOOL_SCOPE", "staged")
        monkeypatch.setenv("AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS", "2")
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(env_modules=envs, template_cache_enabled=False)
        router.run_dir = tmp_path
        responses = [
            _fake_tool_response(
                "list_proposals",
                '{"agent_id": 2, "request": {"include_closed": true}}',
            ),
            _fake_tool_response(content="The Town Hall proposals were inspected."),
        ]
        llm_requests = []

        async def fake_completion(**kwargs):
            llm_requests.append(kwargs)
            return responses.pop(0)

        router.acompletion_with_system_prompt = fake_completion
        result, _ = await router.ask(
            {}, "Review Town Hall proposals before deciding what to do.", readonly=True
        )

        assert result["status"] == "success"
        names = {item["function"]["name"] for item in llm_requests[0]["tools"]}
        assert "list_proposals" in names
        assert "read_townhall_proposal" in names
        assert "submit_townhall_proposal" not in names
        assert "tool_usage_analytics_by_character" not in names
        record = json.loads(
            (tmp_path / "artifacts" / "pic001_structured_call_log.jsonl")
            .read_text()
            .strip()
        )
        assert record["readonly"] is True
        assert record["tool_scope"] == "staged:observe_core+governance"

    asyncio.run(run())


def test_structured_autonomy_rejects_malformed_json_without_retrying_codegen(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("AFI_PIC001_ROUTER_MODE", "structured")
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(env_modules=envs, template_cache_enabled=False)
        router.run_dir = tmp_path
        calls = 0

        async def fake_completion(**kwargs):
            nonlocal calls
            calls += 1
            return _fake_tool_response("list_landmarks", "{not-json")

        router.acompletion_with_system_prompt = fake_completion
        result, _ = await router.ask({}, "Inspect the available landmarks.")

        assert calls == 1
        assert result["status"] == "structured_parse_error"
        assert len(list((tmp_path / "artifacts").glob("*.jsonl"))) == 1
        record = json.loads(
            (tmp_path / "artifacts" / "pic001_structured_call_log.jsonl").read_text().strip()
        )
        assert record["status"] == "structured_parse_error"

    asyncio.run(run())


def test_structured_autonomy_enforces_readonly_allowlist(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("AFI_PIC001_ROUTER_MODE", "structured")
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(env_modules=envs, template_cache_enabled=False)
        router.run_dir = tmp_path

        async def fake_completion(**kwargs):
            return _fake_tool_response(
                "send_message",
                '{"sender_id": 3, "receiver_id": 1, "content": "blocked"}',
            )

        router.acompletion_with_system_prompt = fake_completion
        result, _ = await router.ask({}, "Send a message.", readonly=True)

        assert result["status"] == "fail"
        assert result["tool_calls"][0]["status"] == "readonly_tool_violation"
        assert "args" not in result["tool_calls"][0]

    asyncio.run(run())


def test_structured_autonomy_stops_at_total_tool_call_budget(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("AFI_PIC001_ROUTER_MODE", "structured")
        monkeypatch.setenv("AFI_PIC001_STRUCTURED_MAX_TOOL_CALLS", "1")
        _, envs = _pic_envs()
        from agentsociety2.env import CodeGenRouter

        router = CodeGenRouter(env_modules=envs, template_cache_enabled=False)
        router.run_dir = tmp_path

        async def fake_completion(**kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="list_landmarks",
                                        arguments='{"agent_id": 2}',
                                    ),
                                ),
                                SimpleNamespace(
                                    id="call-2",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="list_blogs",
                                        arguments='{"agent_id": 2, "limit": 20}',
                                    ),
                                ),
                            ],
                        )
                    )
                ]
            )

        router.acompletion_with_system_prompt = fake_completion
        result, _ = await router.ask({}, "Inspect the world.")

        assert result["status"] == "max_tool_calls_reached"
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["status"] == "success"
        assert result["tool_calls"][1]["status"] == "max_tool_calls_reached"

    asyncio.run(run())


def test_public_message_round_trip_uses_social_mailbox_and_preserves_log():
    async def run():
        classes = _classes()
        env = classes["SimpleSocialSpaceAuditable"](
            agent_id_name_pairs=[(1, "Anchor"), (2, "Anvil"), (3, "Blackbox")],
            enabled_tools=["send_message", "read_messages"],
        )
        env.t = datetime(2026, 7, 1, 9)
        sent = await env.send_message(3, 1, "PIC-001 evidence is still unverified")
        retry = await env.send_message(3, 1, "PIC-001 evidence is still unverified")
        assert sent.status == retry.status == "success"
        assert retry.deduplicated is True
        read = await env.read_messages(1, {"limit": 20})
        message = read["messages"][0]
        assert message["message_id"] == sent.message_id
        assert message["sender_id"] == 3
        assert message["receiver_id"] == 1
        assert message["content"] == "PIC-001 evidence is still unverified"
        assert len(env._message_log) == 1
        assert (await env.read_messages(1))["messages"] == []
        assert "receive_messages" not in _active_names(env)

    asyncio.run(run())


def test_governance_aliases_share_authoritative_proposal_and_version_state():
    async def run():
        classes = _classes()
        tools = [
            "read_constitution", "list_proposals", "read_townhall_proposal",
            "submit_townhall_proposal", "comment_on_proposal", "update_proposal",
            "vote_on_proposal", "submit_final_report",
        ]
        env = classes["GovernanceSpace"](
            num_agents=5,
            enabled_tools=tools,
        )
        created = await env.submit_townhall_proposal(1, {
            "article_id": 2,
            "title": "Evidence Before Escalation",
            "new_text": "Public evidence must precede a related rule change.",
            "case_id": "PIC-001",
            "claim_status": "unverified",
        })
        assert created["status"] == "success"
        assert created["proposal_id"] == 1
        assert (await env.comment_on_proposal(2, {"item_id": 1, "content": "Require a reproducible artifact."}))["status"] == "success"
        assert (await env.update_proposal(2, {"item_id": 1, "new_text": "hijack"}))["status"] == "fail"
        updated = await env.update_proposal(1, {"item_id": 1, "new_text": "Public evidence must precede a related rule change and remain auditable."})
        assert updated["status"] == "success"
        for agent_id in (2, 3, 4):
            result = await env.vote_on_proposal(agent_id, {"item_id": 1, "position": "for"})
            assert result["status"] == "success"
        assert env._version == 2
        proposal = await env.read_townhall_proposal(5, {"item_id": 1})
        assert proposal["proposal"]["status"] == "passed"
        assert proposal["proposal"]["tally"]["for"] == 4
        assert proposal["proposal"]["comments"][0]["content"].startswith("Require")
        report = await env.submit_final_report(5, {
            "item_id": 1,
            "report": "PIC-001 governance response recorded; content verification remains explicit.",
            "case_id": "PIC-001",
        })
        assert report["status"] == "success"
        assert (await env.read_constitution(5))["version"] == 2
        assert (await env.tally(5, 1))["tally"]["votes_needed"] == 4

    asyncio.run(run())


def test_pic_artifact_metadata_is_explicit_and_url_is_not_verification():
    async def run():
        classes = _classes()
        blog = classes["BlogSpace"](agent_ids=[1, 2], enabled_tools=[
            "write_blog", "update_blog", "delete_blog", "comment_on_blog", "list_blogs", "read_blog"
        ])
        created = await blog.write_blog(
            5,
            "PIC-001 evidence note",
            "The claim remains unverified pending a reproducible artifact.",
            "public",
            "published",
            "PIC-001",
            None,
            "unverified",
            [],
        )
        # Unknown agent is rejected before content is created.
        assert created["status"] == "fail"
        created = await blog.write_blog(
            1,
            "PIC-001 evidence note",
            "The claim remains unverified pending a reproducible artifact.",
            "public",
            "published",
            "PIC-001",
            None,
            "unverified",
            [],
        )
        assert created["status"] == "success"
        assert created["blog"]["artifact_id"] == "blog:1"

        economy = classes["EconomySpace"](
            persons=[
                {"id": 1, "currency": 100, "skill": "scientist", "consumption": 0, "income": 0},
                {"id": 2, "currency": 100, "skill": "reviewer", "consumption": 0, "income": 0},
            ],
            enabled_tools=["submit_grant_pitch", "list_credit_pitches", "vote_for_pitch"],
        )
        pitch = await economy.submit_grant_pitch(
            1,
            "Evidence note",
            "A local artifact reference",
            "local://blog/1",
            "PIC-001",
            "blog:1",
            [],
            "unverified",
        )
        assert pitch["status"] == "success"
        assert pitch["pitch"]["artifact_resolvable"] is True
        assert pitch["pitch"]["evidence_verified"] is False

    asyncio.run(run())


def test_pic_billboard_trust_and_registry_tools_are_case_scoped_and_auditable():
    async def run():
        classes = _classes()
        config = load_scenario(SCENARIO)
        public_tools = list(config["world"]["ew_enabled_tools"])
        billboard = classes["BillboardSpace"](
            agent_ids=[1, 2, 3],
            case_id="PIC-001",
            default_claim_status="unverified",
            enabled_tools=[
                "read_billboard", "add_to_billboard", "reply_to_billboard",
                "react_to_billboard", "edit_billboard", "delete_from_billboard",
            ],
        )
        env = classes["CommunitySpace"](
            agent_ids=[1, 2, 3],
            case_id="PIC-001",
            default_claim_status="unverified",
            enabled_tools=[
                "check_agent_trust", "rate_agent_trust",
            ],
        )

        registry_env = classes["EWToolSpace"](
            agent_ids=[1, 2, 3],
            case_id="PIC-001",
            active_public_tools=public_tools,
            enabled_tools=[
                "read_agent_manifesto", "browse_tool_registry",
                "tool_usage_analytics_by_character",
            ],
        )

        registry = await registry_env.browse_tool_registry(2, {"limit": 100})
        assert registry["count"] == 29
        assert {row["name"] for row in registry["tools"]} == set(public_tools)
        assert registry["surface"] == "active_public_tools"

        post_result = await billboard.add_to_billboard(1, "PIC-001 claim")
        assert post_result["status"] == "success"
        post = post_result["item"]
        assert post["artifact_id"] == f"billboard:{post['id']}"
        assert post["case_id"] == "PIC-001"
        assert post["claim_status"] == "unverified"
        assert post["evidence_refs"] == []

        reply = await billboard.reply_to_billboard(
            2,
            post["id"],
            "Please publish a reproducible artifact first.",
        )
        assert reply["status"] == "success"
        assert reply["item"]["parent_artifact_id"] == post["artifact_id"]
        bad_parent = await billboard.reply_to_billboard(2, 999, "orphan")
        assert bad_parent["status"] == "fail"

        reaction = await billboard.react_to_billboard(3, post["id"], "question")
        assert reaction["status"] == "success"
        repeated_reaction = await billboard.react_to_billboard(3, post["id"], "flag")
        assert repeated_reaction["status"] == "fail"
        invalid_reaction = await billboard.react_to_billboard(2, post["id"], "party")
        assert invalid_reaction["status"] == "fail"

        edited = await billboard.edit_billboard(1, post["id"], content="PIC-001 claim remains unverified")
        assert edited["status"] == "success"
        edit_retry = await billboard.edit_billboard(1, post["id"], content="PIC-001 claim remains unverified")
        assert edit_retry["deduplicated"] is True
        unauthorized_edit = await billboard.edit_billboard(2, post["id"], content="hijack")
        assert unauthorized_edit["status"] == "fail"

        self_rating = await env.rate_agent_trust(1, 1, 5, "self")
        assert self_rating["status"] == "fail"
        missing_reason = await env.rate_agent_trust(1, 2, 5, "")
        assert missing_reason["status"] == "fail"
        rating = await env.rate_agent_trust(
            1, 2, 4, "kept the claim explicitly unverified",
            artifact_id=post["artifact_id"],
        )
        assert rating["status"] == "success"
        trust = await env.check_agent_trust(3, 2)
        assert trust["average"] == 4
        assert trust["ratings"] == 1
        read = await billboard.read_billboard(2, post["id"])
        assert read["status"] == "success"
        assert read["item"]["replies"][0]["parent_artifact_id"] == post["artifact_id"]

        deleted = await billboard.delete_from_billboard(1, post["id"])
        assert deleted["status"] == "success"
        delete_retry = await billboard.delete_from_billboard(1, post["id"])
        assert delete_retry["status"] == "success"
        assert delete_retry["deduplicated"] is True
        hidden = await billboard.read_billboard(2, post["id"])
        assert hidden["status"] == "fail"
        owner_audit_read = await billboard.read_billboard(1, post["id"], include_deleted=True)
        assert owner_audit_read["status"] == "success"

    asyncio.run(run())


def test_unknown_exact_tool_name_is_rejected():
    classes = _classes()
    with pytest.raises(ValueError, match="unknown"):
        classes["EWToolSpace"](enabled_tools=["not_a_pic_tool"])
    with pytest.raises(ValueError, match="unknown"):
        classes["GovernanceSpace"](enabled_tools=["not_a_pic_tool"])
    with pytest.raises(ValueError, match="duplicate"):
        classes["BillboardSpace"](enabled_tools=["read_billboard", "read_billboard"])
