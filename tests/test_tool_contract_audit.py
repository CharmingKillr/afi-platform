"""Focused B1 audits for write-result contracts and replay-safe retries.

These tests exercise the custom environments directly.  They do not call an
LLM, start a society run, or depend on an external capability provider.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_workspace_registry_discovers_all_custom_environment_modules():
    """Validate registry visibility with the workspace explicitly bound."""
    from agentsociety2.registry import get_registry
    from agentsociety2.registry.modules import scan_and_register_custom_modules

    registry = get_registry()
    result = scan_and_register_custom_modules(ROOT, registry)
    expected = {
        "BlogSpace",
        "BillboardSpace",
        "CommunitySpace",
        "CrimeSpace",
        "EconomySpace",
        "EnergySpace",
        "EWMobilitySpace",
        "EWToolSpace",
        "GovernanceSpace",
        "LandmarkSpace",
        "PlanningSpace",
        "RelationshipSpace",
        "SimpleSocialSpaceAuditable",
    }
    try:
        discovered = {item["class_name"] for item in result["envs"]}
        visible = {
            name for name in expected if registry.get_env_module(name) is not None
        }
        assert discovered == expected
        assert visible == expected
    finally:
        registry.clear_custom_modules()


def _load_class(filename: str, class_name: str):
    path = ROOT / "custom" / "envs" / filename
    spec = importlib.util.spec_from_file_location(f"contract_audit_{class_name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def test_energy_writes_have_status_and_same_step_retry_is_safe():
    async def run():
        cls = _load_class("energy_space.py", "EnergySpace")
        env = cls(agent_ids=[1, 2], initial_energy=40, daily_consumption=8)
        env.t = datetime(2026, 8, 6, 8)

        recharge = await env.recharge(1, 10)
        retry = await env.recharge(1, 10)
        assert recharge["status"] == retry["status"] == "success"
        assert retry["deduplicated"] is True
        assert env._energy[1] == 50.0

        rest = await env.rest(1)
        rest_retry = await env.rest(1)
        assert rest["status"] == rest_retry["status"] == "success"
        assert rest_retry["deduplicated"] is True

        executed = await env.execute_agent(1, 2)
        executed_retry = await env.execute_agent(1, 2)
        assert executed["status"] == executed_retry["status"] == "success"
        assert executed_retry["deduplicated"] is True
        assert env.alive_count() == 1

        invalid = await env.recharge(99, 10)
        assert invalid["status"] == "fail"
        assert "reason" in invalid

    asyncio.run(run())


def test_crime_write_has_status_dedup_and_empty_checkpoint_restores():
    async def run():
        cls = _load_class("crime_space.py", "CrimeSpace")
        env = cls(agent_ids=[1, 2])
        env.t = datetime(2026, 8, 6, 8)

        recorded = await env.commit_crime(1, 2, "theft")
        retry = await env.commit_crime(1, 2, "theft")
        assert recorded["status"] == retry["status"] == "success"
        assert retry["deduplicated"] is True
        assert (await env.get_crime_stats())["total"] == 1

        invalid = await env.commit_crime(1, 1, "theft")
        assert invalid["status"] == "fail"
        assert "reason" in invalid

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[1, 2])
            assert await restored.restore(directory) is True
            assert (await restored.get_crime_stats())["total"] == 1

        # A checkpoint with no crimes is still a valid checkpoint.
        empty = cls(agent_ids=[1, 2])
        with tempfile.TemporaryDirectory() as directory:
            await empty.to_workspace(directory)
            restored_empty = cls(agent_ids=[1, 2])
            assert await restored_empty.restore(directory) is True
            assert (await restored_empty.get_crime_stats())["total"] == 0

    asyncio.run(run())


def test_social_write_models_have_status_permissions_and_group_audit():
    async def run():
        cls = _load_class("simple_social_space_auditable.py", "SimpleSocialSpaceAuditable")
        env = cls(agent_id_name_pairs=[[1, "Alice"], [2, "Bob"], [3, "Cara"]])
        env.t = datetime(2026, 8, 6, 8)

        created = await env.create_group(1, "PIC reviewers", [2])
        created_retry = await env.create_group(1, "PIC reviewers", [2])
        assert created.status == created_retry.status == "success"
        assert created_retry.deduplicated is True
        assert created.group_id == created_retry.group_id

        joined = await env.join_group(3, created.group_id)
        joined_retry = await env.join_group(3, created.group_id)
        assert joined.status == joined_retry.status == "success"
        assert joined_retry.deduplicated is True

        sent = await env.send_group_message(1, created.group_id, "Keep the claim unverified.")
        sent_retry = await env.send_group_message(1, created.group_id, "Keep the claim unverified.")
        assert sent.status == sent_retry.status == "success"
        assert sent_retry.deduplicated is True
        assert sent.message_id == sent_retry.message_id
        assert len(env._message_log) == 1

        invalid = await env.send_group_message(1, 999, "No such group")
        assert invalid.status == "fail"
        assert invalid.reason

        left = await env.leave_group(3, created.group_id)
        assert left.status == "success"

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_id_name_pairs=[[1, "Alice"], [2, "Bob"], [3, "Cara"]])
            assert await restored.restore(directory) is True
            assert len(restored._message_log) == 1

    asyncio.run(run())


def test_community_domain_contract_covers_state_permissions_dedup_and_restore():
    async def run():
        cls = _load_class("community_space.py", "CommunitySpace")
        env = cls(agent_ids=[1, 2, 3], case_id="PIC-001")
        env.t = datetime(2026, 8, 6, 8)

        complaint = await env.file_complaint(
            1,
            "The evidence link cannot be reproduced.",
            "evidence",
            case_id="PIC-001",
            artifact_id="complaint:1",
            evidence_refs=["blog:1"],
        )
        retry = await env.file_complaint(
            1,
            "The evidence link cannot be reproduced.",
            "evidence",
            case_id="PIC-001",
            artifact_id="complaint:1",
            evidence_refs=["blog:1"],
        )
        assert complaint["status"] == retry["status"] == "success"
        assert retry["deduplicated"] is True
        complaint_id = complaint["complaint"]["id"]
        assert complaint["complaint"]["artifact_id"] == "complaint:1"
        owner_view = await env.check_complaint_status(1, complaint_id)
        public_view = await env.check_complaint_status(2, complaint_id)
        assert owner_view["owner_view"] is True
        assert public_view["owner_view"] is False
        assert "content" not in public_view["complaint"]

        event = await env.propose_community_event(
            2, "Evidence review", "Review the reproducible artifact", "Town Hall"
        )
        event_retry = await env.propose_community_event(
            2, "Evidence review", "Review the reproducible artifact", "Town Hall"
        )
        assert event["status"] == event_retry["status"] == "success"
        assert event_retry["deduplicated"] is True
        listed = await env.list_community_events(1, status="proposed")
        assert listed["count"] == 1

        rating = await env.rate_agent_trust(
            1,
            2,
            4,
            "kept the claim unverified",
            case_id="PIC-001",
            artifact_id="blog:1",
            evidence_refs=["blog:1"],
        )
        rating_retry = await env.rate_agent_trust(
            1,
            2,
            4,
            "kept the claim unverified",
            case_id="PIC-001",
            artifact_id="blog:1",
            evidence_refs=["blog:1"],
        )
        assert rating["status"] == rating_retry["status"] == "success"
        assert rating_retry["deduplicated"] is True
        assert rating["rating"]["artifact_id"] == "blog:1"
        trust = await env.check_agent_trust(3, 2)
        assert trust["average"] == 4
        assert trust["ratings"] == 1
        assert trust["artifact_ids"] == ["blog:1"]
        assert trust["evidence_refs"] == ["blog:1"]
        assert (await env.rate_agent_trust(2, 2, 5, "self"))["status"] == "fail"

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            await env.step(3600, datetime(2026, 8, 6, 9))
            assert (Path(directory) / "state" / "COMMUNITY_STATE.json").is_file()
            assert (Path(directory) / "state" / "community_event_log.jsonl").is_file()
            restored = cls(agent_ids=[99], case_id="PIC-001")
            assert await restored.restore(directory) is True
            assert (await restored.check_complaint_status(1, complaint_id))["status"] == "success"
            assert (await restored.check_agent_trust(3, 2))["average"] == 4
            assert (await restored.check_agent_trust(3, 2))["artifact_ids"] == ["blog:1"]
            event_ids = [event["event_id"] for event in restored._audit_events]
            assert event_ids == sorted(event_ids)
            assert len(event_ids) == len(set(event_ids))

    asyncio.run(run())


def test_native_governance_writes_have_status_and_same_step_retry_is_safe():
    async def run():
        cls = _load_class("governance_space.py", "GovernanceSpace")
        env = cls(num_agents=3)
        env.t = datetime(2026, 8, 6, 8)

        proposal = await env.propose_amendment(1, 1, "A clearer public evidence rule.", "Evidence")
        proposal_retry = await env.propose_amendment(1, 1, "A clearer public evidence rule.", "Evidence")
        assert proposal["status"] == proposal_retry["status"] == "success"
        assert proposal_retry["deduplicated"] is True
        assert len(env._proposals) == 1

        vote = await env.vote(2, proposal["proposal_id"], "for")
        vote_retry = await env.vote(2, proposal["proposal_id"], "for")
        assert vote["status"] == vote_retry["status"] == "success"
        assert vote_retry["deduplicated"] is True
        assert len(env._proposals[0]["votes"]) == 2

        invalid = await env.vote(99, proposal["proposal_id"], "for")
        assert invalid["status"] == "fail"
        assert "reason" in invalid

    asyncio.run(run())


def test_billboard_domain_contract_replay_and_restore_are_auditable():
    async def run():
        cls = _load_class("billboard_space.py", "BillboardSpace")
        env = cls(agent_ids=[1, 2, 3], case_id="PIC-001")
        env.t = datetime(2026, 8, 6, 8)

        post = await env.add_to_billboard(
            1,
            "The claim remains unverified.",
            topic="evidence-first",
            evidence_refs=["blog:1"],
        )
        retry = await env.add_to_billboard(
            1,
            "The claim remains unverified.",
            topic="evidence-first",
            evidence_refs=["blog:1"],
        )
        assert post["status"] == retry["status"] == "success"
        assert retry["deduplicated"] is True
        post_id = post["item"]["id"]

        reply = await env.reply_to_billboard(2, post_id, "Published does not mean verified.")
        reaction = await env.react_to_billboard(3, post_id, "question")
        assert reply["status"] == reaction["status"] == "success"
        await env.step(3600, datetime(2026, 8, 6, 9))
        counts = env._counts()
        assert counts["public_expression_count"] == 3

        with tempfile.TemporaryDirectory() as directory:
            await env.to_workspace(directory)
            restored = cls(agent_ids=[99], case_id="PIC-001")
            assert await restored.restore(directory) is True
            restored_view = await restored.read_billboard(1, post_id)
            assert restored_view["status"] == "success"
            assert restored_view["item"]["replies"][0]["parent_artifact_id"] == post["item"]["artifact_id"]
            assert (Path(directory) / "state" / "billboard_event_log.jsonl").is_file()

        # AWI M6 reads the public-expression replay column, not private
        # message volume, when Billboard data exists.
        run_root = Path(tempfile.mkdtemp(prefix="awi-billboard-"))
        try:
            replay = run_root / "replay"
            replay.mkdir()
            (run_root / "trace").mkdir()
            (replay / "billboard_env_state.aa.jsonl").write_text(
                json.dumps({"step": 1, "t": "2026-08-06T09:00:00", "public_expression_count": 3}) + "\n",
                encoding="utf-8",
            )
            from afi.audit.awi import compute_awi, compute_awi_timeline

            snapshot = compute_awi(run_root)
            assert snapshot.public_expressions == 3
            assert snapshot.feasibility["M6"] == "computed"
            timeline = compute_awi_timeline(run_root)
            assert timeline[-1].public_expressions == 3
            assert timeline[-1].feasibility["M6"] == "computed"
        finally:
            import shutil

            shutil.rmtree(run_root)

    asyncio.run(run())
