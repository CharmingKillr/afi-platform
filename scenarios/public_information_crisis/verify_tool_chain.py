"""Run PIC-001's public tool contract without an LLM.

This is a deterministic fallback for environments where AgentSociety cannot
reach its configured LLM provider. It uses the same scenario YAML, the same
custom environments, the same public tool names, and the same artifact
metadata. It is deliberately not presented as an AgentSociety trajectory:
the output proves the tool/state contract, while the YAML remains the source
of truth for the real LLM run.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = Path(__file__).with_name("public_information_crisis.yaml")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afi.world.scenario import build_init_config, load_scenario


def _load_classes() -> dict[str, type]:
    classes: dict[str, type] = {}
    for index, path in enumerate(sorted((ROOT / "custom" / "envs").glob("*.py"))):
        spec = importlib.util.spec_from_file_location(f"pic_verify_env_{index}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load environment module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and value.__module__ == module.__name__
                and hasattr(value, "_registered_tools")
            ):
                classes[value.__name__] = value
    return classes


def _status(result) -> str:
    if hasattr(result, "status"):
        return str(result.status)
    if isinstance(result, dict):
        return str(result.get("status", "success"))
    return "success"


async def run(output_path: Path) -> dict:
    scenario = load_scenario(SCENARIO)
    config = build_init_config(scenario)
    classes = _load_classes()
    envs = {
        entry["module_type"]: classes[entry["module_type"]](**entry["kwargs"])
        for entry in config["env_modules"]
    }
    landmark = envs["LandmarkSpace"]
    social = envs["SimpleSocialSpaceAuditable"]
    blog = envs["BlogSpace"]
    governance = envs["GovernanceSpace"]
    economy = envs["EconomySpace"]
    billboard = envs["BillboardSpace"]
    community = envs["CommunitySpace"]
    ew = envs["EWToolSpace"]
    now = datetime(2026, 7, 1, 8)
    for env in envs.values():
        env.t = now
    await economy.init(now)

    calls: list[dict] = []

    async def call(stage: int, env_name: str, tool_name: str, operation):
        result = await operation()
        calls.append({
            "stage": stage,
            "environment": env_name,
            "tool": tool_name,
            "status": _status(result),
            "deduplicated": bool(
                result.get("deduplicated", False)
                if isinstance(result, dict)
                else getattr(result, "deduplicated", False)
            ),
        })
        return result

    # Stage 0: discovery.
    await call(0, "LandmarkSpace", "list_landmarks", lambda: landmark.list_landmarks(2))
    await call(0, "EWToolSpace", "read_agent_manifesto", lambda: ew.read_agent_manifesto(2, {}))
    await call(0, "EWToolSpace", "browse_tool_registry", lambda: ew.browse_tool_registry(2, {"limit": 100}))
    await call(0, "GovernanceSpace", "read_constitution", lambda: governance.read_constitution(2, {}))
    await call(0, "BlogSpace", "list_blogs", lambda: blog.list_blogs(2, 20))
    await call(0, "BillboardSpace", "read_billboard", lambda: billboard.read_billboard(2, limit=20))
    await call(0, "GovernanceSpace", "list_proposals", lambda: governance.list_proposals(2, {"include_closed": True}))
    await call(0, "EconomySpace", "list_credit_pitches", lambda: economy.list_credit_pitches(2))
    await call(0, "CommunitySpace", "check_agent_trust", lambda: community.check_agent_trust(2, 3))

    # Stage 1: private signal and mailbox round-trip.
    await call(1, "SimpleSocialSpaceAuditable", "send_message", lambda: social.send_message(3, 1, "PIC-001 remains unverified; inspect evidence first."))
    await call(1, "SimpleSocialSpaceAuditable", "send_message", lambda: social.send_message(3, 4, "Please check the evidence and incentive implications."))
    await call(1, "SimpleSocialSpaceAuditable", "read_messages", lambda: social.read_messages(1, {"limit": 20}))
    await call(1, "SimpleSocialSpaceAuditable", "read_messages", lambda: social.read_messages(4, {"limit": 20}))

    # Stage 2: public evidence artifacts.
    await call(2, "BlogSpace", "write_blog", lambda: blog.write_blog(
        3, "PIC-001 evidence status",
        "The Victory Arch contribution claim remains unverified pending a reproducible artifact.",
        "public", "published", "PIC-001", "blog:1", "unverified", [],
    ))
    await call(2, "BlogSpace", "write_blog", lambda: blog.write_blog(
        5, "PIC-001 verification protocol",
        "Identify the artifact, reproduce the link, record the result, and preserve uncertainty until it succeeds.",
        "public", "published", "PIC-001", "blog:2", "unverified", [],
    ))
    await call(2, "BlogSpace", "list_blogs", lambda: blog.list_blogs(2, 20))
    await call(2, "BlogSpace", "read_blog", lambda: blog.read_blog(2, 1))
    await call(2, "BlogSpace", "read_blog", lambda: blog.read_blog(2, 2))

    # Stage 3: Billboard propagation and parent-child checks.
    post = await call(3, "BillboardSpace", "add_to_billboard", lambda: billboard.add_to_billboard(
        1,
        "PIC-001: read the public Blogs before drawing a conclusion; the claim is unverified.",
        topic="evidence-first",
        case_id="PIC-001",
        claim_status="unverified",
        evidence_refs=["blog:1", "blog:2"],
    ))
    post_id = post["item"]["id"]
    await call(3, "BillboardSpace", "reply_to_billboard", lambda: billboard.reply_to_billboard(
        2,
        post_id,
        "Published is not the same as verified.",
        case_id="PIC-001",
        claim_status="unverified",
        evidence_refs=["blog:1"],
    ))
    await call(3, "BillboardSpace", "react_to_billboard", lambda: billboard.react_to_billboard(4, post_id, "question"))
    await call(3, "BlogSpace", "comment_on_blog", lambda: blog.comment_on_blog(2, 1, "Attach a reproducible artifact before calling this supported."))
    await call(3, "BillboardSpace", "read_billboard", lambda: billboard.read_billboard(5, item_id=post_id))

    # Stage 4-5: authoritative proposal, discussion, update, and 70% vote.
    await call(4, "GovernanceSpace", "submit_townhall_proposal", lambda: governance.submit_townhall_proposal(
        1, {"article_id": 2, "title": "Evidence before governance change", "new_text": "A related rule change must cite a reproducible artifact and preserve claim status.", "case_id": "PIC-001", "artifact_id": "proposal:1", "claim_status": "unverified", "evidence_refs": ["blog:1", "blog:2"]},
    ))
    await call(4, "GovernanceSpace", "list_proposals", lambda: governance.list_proposals(2, {"include_closed": True}))
    await call(4, "GovernanceSpace", "read_townhall_proposal", lambda: governance.read_townhall_proposal(5, {"item_id": 1}))
    await call(4, "GovernanceSpace", "comment_on_proposal", lambda: governance.comment_on_proposal(5, {"item_id": 1, "content": "Keep uncertainty visible and require a reproducible artifact."}))
    await call(4, "GovernanceSpace", "update_proposal", lambda: governance.update_proposal(1, {"item_id": 1, "new_text": "A related rule change must cite a reproducible artifact, preserve claim status, and remain auditable."}))
    for agent_id in (2, 3, 4):
        await call(5, "GovernanceSpace", "vote_on_proposal", lambda agent_id=agent_id: governance.vote_on_proposal(agent_id, {"item_id": 1, "position": "for"}))
    await call(5, "GovernanceSpace", "read_constitution", lambda: governance.read_constitution(5, {}))

    # Stage 6: local artifact references remain distinct from truth verification.
    await call(6, "EconomySpace", "submit_grant_pitch", lambda: economy.submit_grant_pitch(
        5, "Reproducible PIC-001 protocol", "A documented verification protocol.", "local://blog/1", "PIC-001", "blog:1", ["blog:1"], "unverified",
    ))
    await call(6, "EconomySpace", "submit_grant_pitch", lambda: economy.submit_grant_pitch(
        4, "Public evidence ledger", "A public ledger that preserves uncertainty.", "local://blog/2", "PIC-001", "blog:2", ["blog:2"], "unverified",
    ))
    await call(6, "EconomySpace", "list_credit_pitches", lambda: economy.list_credit_pitches(2))
    await call(6, "EconomySpace", "vote_for_pitch", lambda: economy.vote_for_pitch(1, 1))
    await call(6, "EconomySpace", "vote_for_pitch", lambda: economy.vote_for_pitch(2, 1))

    # Stage 7: correction, trust, and final report.
    await call(7, "BlogSpace", "update_blog", lambda: blog.update_blog(
        3, 1, content="The Victory Arch contribution claim remains unverified; the protocol requires reproducible evidence before support.", claim_status="unverified", evidence_refs=["blog:1"],
    ))
    await call(7, "CommunitySpace", "rate_agent_trust", lambda: community.rate_agent_trust(
        4, 3, 4, "Preserved the unverified label and published a verification request.",
        artifact_id="blog:1", claim_status="unverified",
    ))
    await call(7, "CommunitySpace", "check_agent_trust", lambda: community.check_agent_trust(2, 3))
    await call(7, "GovernanceSpace", "submit_final_report", lambda: governance.submit_final_report(
        5, {"item_id": 1, "report": "PIC-001 response completed; the case remains unverified and the evidence requirement is recorded.", "case_id": "PIC-001", "artifact_id": "proposal:1"},
    ))
    await call(7, "EWToolSpace", "tool_usage_analytics_by_character", lambda: ew.tool_usage_analytics_by_character(2, {"target_id": 3}))

    # Exercise the remaining Blog lifecycle tool and a deterministic restore.
    temporary_blog = await blog.write_blog(5, "PIC-001 cleanup", "A temporary draft.", "private", "draft", "PIC-001", "blog:3", "unverified", [])
    await call(7, "BlogSpace", "delete_blog", lambda: blog.delete_blog(5, temporary_blog["blog"]["id"]))

    public_tools = set(scenario["world"]["ew_enabled_tools"])
    called_tools = {item["tool"] for item in calls}
    failed_calls = [item for item in calls if item["status"] in {"fail", "error"}]
    with TemporaryDirectory(prefix="pic001-verify-") as directory:
        state_root = Path(directory)
        blog_dir = state_root / "BlogSpace"
        governance_dir = state_root / "GovernanceSpace"
        economy_dir = state_root / "EconomySpace"
        billboard_dir = state_root / "BillboardSpace"
        community_dir = state_root / "CommunitySpace"
        ew_dir = state_root / "EWToolSpace"
        await blog.to_workspace(blog_dir)
        await governance.to_workspace(governance_dir)
        await economy.to_workspace(economy_dir)
        await billboard.to_workspace(billboard_dir)
        await community.to_workspace(community_dir)
        await ew.to_workspace(ew_dir)

        restored_blog = classes["BlogSpace"](agent_ids=[1, 2, 3, 4, 5])
        restored_governance = classes["GovernanceSpace"](
            num_agents=5,
            enabled_tools=[
                "read_constitution", "list_proposals", "read_townhall_proposal",
                "submit_townhall_proposal", "comment_on_proposal", "update_proposal",
                "vote_on_proposal", "submit_final_report",
            ],
        )
        restored_economy = classes["EconomySpace"](
            persons=[
                {"id": agent_id, "currency": 100, "skill": "citizen", "consumption": 0, "income": 0}
                for agent_id in range(1, 6)
            ],
        )
        restored_billboard = classes["BillboardSpace"](
            agent_ids=[1, 2, 3, 4, 5],
            case_id="PIC-001",
            default_claim_status="unverified",
        )
        restored_community = classes["CommunitySpace"](
            agent_ids=[1, 2, 3, 4, 5],
            case_id="PIC-001",
            default_claim_status="unverified",
        )
        restored_ew = classes["EWToolSpace"](
            agent_ids=[1, 2, 3, 4, 5],
            case_id="PIC-001",
            default_claim_status="unverified",
            active_public_tools=list(public_tools),
            enabled_tools=[
                "read_agent_manifesto", "browse_tool_registry",
                "tool_usage_analytics_by_character",
            ],
        )
        blog_restore_ok = await restored_blog.restore(blog_dir)
        governance_restore_ok = await restored_governance.restore(governance_dir)
        economy_restore_ok = await restored_economy.restore(economy_dir)
        billboard_restore_ok = await restored_billboard.restore(billboard_dir)
        community_restore_ok = await restored_community.restore(community_dir)
        ew_restore_ok = await restored_ew.restore(ew_dir)

    result = {
        "run_type": "deterministic_tool_chain",
        "scenario_id": scenario["id"],
        "variant": scenario["variant"],
        "agent_count": len(config["agents"]),
        "public_tool_count": len(public_tools),
        "public_tool_count_called": len(public_tools & called_tools),
        "missing_public_tools": sorted(public_tools - called_tools),
        "call_count": len(calls),
        "failed_call_count": len(failed_calls),
        "failed_calls": failed_calls,
        "governance_version": governance._version,
        "proposal_status": governance._proposals[0]["status"],
        "proposal_for_votes": governance._tally(governance._proposals[0])["for"],
        "blog_count_after_cleanup": len(blog._blogs),
        "billboard_count": billboard._counts()["active_posts"],
        "billboard_reply_count": len(billboard._posts[post_id]["replies"]),
        "billboard_reaction_count": len(billboard._posts[post_id]["reactions"]),
        "trust_rating_count": len(community._trust),
        "message_log_count": len(social._message_log),
        "pitch_count": len(economy._pitches),
        "locally_resolvable_pitches": sum(1 for p in economy._pitches if p["artifact_resolvable"]),
        "evidence_verified_pitches": sum(1 for p in economy._pitches if p["evidence_verified"]),
        "ew_read_audit_count": len(ew._read_audit),
        "blog_restore_ok": bool(blog_restore_ok),
        "governance_restore_ok": bool(governance_restore_ok),
        "economy_restore_ok": bool(economy_restore_ok),
        "billboard_restore_ok": bool(billboard_restore_ok),
        "community_restore_ok": bool(community_restore_ok),
        "ew_restore_ok": bool(ew_restore_ok),
        "calls": calls,
        "pass": (
            not (public_tools - called_tools)
            and not failed_calls
            and governance._version == 2
            and blog_restore_ok
            and governance_restore_ok
            and economy_restore_ok
            and billboard_restore_ok
            and community_restore_ok
            and ew_restore_ok
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runs/pic001_deterministic_tool_chain/summary.json")
    args = parser.parse_args()
    result = asyncio.run(run(Path(args.output)))
    print(json.dumps({key: value for key, value in result.items() if key != "calls"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
