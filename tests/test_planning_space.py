"""B1 PlanningSpace unit and integration-boundary tests."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
from datetime import datetime
from pathlib import Path


os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-key")

ROOT = Path(__file__).parents[1]
PLANNING_TOOLS = {
    "add_todo",
    "complete_todo",
    "list_todo",
    "add_to_calendar",
    "check_calendar",
    "remove_from_calendar",
}


def _planning_class():
    path = ROOT / "custom" / "envs" / "planning_space.py"
    spec = importlib.util.spec_from_file_location("afi_test_planning_space", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module.PlanningSpace


def test_six_ew_planning_tools_are_codegen_registered():
    cls = _planning_class()
    assert PLANNING_TOOLS <= set(cls._registered_tools)
    schemas = {
        item["function"]["name"]: item["function"]
        for item in cls()._llm_tools
        if item["function"]["name"] in PLANNING_TOOLS
    }
    assert set(schemas) == PLANNING_TOOLS
    assert "task" in schemas["add_todo"]["parameters"]["properties"]
    assert "start_at" in schemas["add_to_calendar"]["parameters"]["properties"]


def test_todo_lifecycle_is_private_per_agent():
    async def run():
        env = _planning_class()(agent_ids=[1, 2])
        created = await env.add_todo(1, "Review mediation notes")
        todo_id = created["todo"]["id"]

        assert (await env.list_todo(1))["count"] == 1
        assert (await env.list_todo(2))["count"] == 0
        assert not (await env.complete_todo(2, todo_id))["ok"]

        completed = await env.complete_todo(1, todo_id)
        assert completed["ok"] and not completed["already_completed"]
        assert (await env.complete_todo(1, todo_id))["already_completed"]
        assert (await env.list_todo(1))["todos"] == []
        assert env._snapshot(1) == {
            "pending_todos": 0,
            "completed_todos": 1,
            "upcoming_calendar_entries": 0,
        }

    asyncio.run(run())


def test_calendar_validation_ordering_isolation_and_removal():
    async def run():
        env = _planning_class()(agent_ids=[1, 2])
        await env.init(datetime(2026, 7, 1, 8))

        invalid = await env.add_to_calendar(1, "Past", "2026-07-01T07:00:00")
        assert not invalid["ok"]
        invalid_range = await env.add_to_calendar(
            1, "Bad range", "2026-07-02T10:00:00", "2026-07-02T09:00:00"
        )
        assert not invalid_range["ok"]

        later = await env.add_to_calendar(1, "Later", "2026-07-03T10:00:00")
        sooner = await env.add_to_calendar(
            1,
            "Sooner",
            "2026-07-02T10:00:00+08:00",
            "2026-07-02T11:00:00+08:00",
        )
        assert [event["title"] for event in (await env.check_calendar(1))["events"]] == [
            "Sooner",
            "Later",
        ]
        assert (await env.check_calendar(2))["events"] == []
        assert not (await env.remove_from_calendar(2, sooner["event"]["id"]))["ok"]
        assert (await env.remove_from_calendar(1, sooner["event"]["id"]))["ok"]
        assert (await env.check_calendar(1))["events"] == [later["event"]]

    asyncio.run(run())


def test_workspace_restore_preserves_state_and_ids():
    async def run():
        cls = _planning_class()
        env = cls(agent_ids=[1])
        await env.init(datetime(2026, 7, 1, 8))
        await env.add_todo(1, "Persistent task")
        await env.add_to_calendar(1, "Persistent event", "2026-07-02T10:00:00")

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[99])
            assert await restored.restore(directory)
            assert restored._now() == datetime(2026, 7, 1, 8)
            assert (await restored.list_todo(1))["todos"][0]["task"] == "Persistent task"
            assert (await restored.check_calendar(1))["events"][0]["title"] == "Persistent event"
            assert (await restored.add_todo(1, "Second task"))["todo"]["id"] == 2
            assert (await restored.add_to_calendar(1, "Second event", "2026-07-03T10:00:00"))["event"]["id"] == 2

    asyncio.run(run())


def test_planning_results_follow_shared_status_contract():
    async def run():
        env = _planning_class()(agent_ids=[1])
        success = await env.add_todo(1, "Contract check")
        failure = await env.add_todo(99, "Unknown agent")
        assert success["ok"] is True and success["status"] == "success"
        assert failure["ok"] is False and failure["status"] == "fail"

    asyncio.run(run())


def test_scenario_builder_mounts_planning_space():
    from afi.world.scenario import build_init_config

    config = build_init_config(
        {
            "agents": ["Anchor", "Anvil"],
            "envs": ["PlanningSpace"],
        }
    )
    assert config["env_modules"] == [
        {"module_type": "PlanningSpace", "kwargs": {"agent_ids": [1, 2]}}
    ]


def test_planning_actions_count_toward_m4():
    from afi.audit.awi import _m4_tools

    spans = [
        {
            "name": "react.tool",
            "resource": {"agent.id": 1},
            "attributes": {"react.action": action},
        }
        for action in ("add_todo", "list_todo", "add_to_calendar")
    ]
    assert _m4_tools(spans) == ({1: 3}, 3.0)
