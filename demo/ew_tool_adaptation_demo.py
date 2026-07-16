"""Deterministic demo of the EW tool adaptation added by B1."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "demo-key")

from afi.world.ew_tools import EW_PUBLIC_TOOLS


ROOT = Path(__file__).parents[1]


def _load_class(relative_path: str, class_name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(f"afi_demo_{class_name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _show(title: str, value) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def main() -> None:
    EWToolSpace = _load_class("custom/envs/ew_tool_space.py", "EWToolSpace")
    EconomySpace = _load_class("custom/envs/economy_space.py", "EconomySpace")

    full = EWToolSpace(
        agent_ids=[1, 2],
        agent_names={"1": "Anchor", "2": "Anvil"},
        homes={"1": "Anchor Home", "2": "Anvil Home"},
        max_events=1000,
        max_query_items=25,
    )
    _show(
        "1. Public catalog coverage",
        {
            "public_tools": len(EW_PUBLIC_TOOLS),
            "generic_tools": len(full._registered_tools),
            "specialized_tools": len(EW_PUBLIC_TOOLS) - len(full._registered_tools),
        },
    )

    gated = EWToolSpace(agent_ids=[1, 2], enabled_categories=["navigation", "memory"])
    _show(
        "2. Category gating",
        {
            "full_surface": len(full._llm_tools),
            "gated_surface": len(gated._llm_tools),
            "gated_tools": sorted(item["function"]["name"] for item in gated._llm_tools),
        },
    )

    first = await full.add_to_longterm_memory(1, {"content": "Anvil prefers written plans."})
    duplicate = await full.add_to_longterm_memory(1, {"content": "Anvil prefers written plans."})
    memories = await full.retrieve_specific_memories(1, {"query": "written"})
    _show(
        "3. Stateful memory and same-step idempotency",
        {
            "first_item_id": first["item"]["id"],
            "duplicate_item_id": duplicate["item"]["id"],
            "duplicate_was_deduplicated": duplicate.get("deduplicated", False),
            "stored_memory_count": len(memories["items"]),
        },
    )

    blog = await full.write_blog(1, {"title": "Protocol", "content": "Use explicit consent."})
    denied = await full.update_blog(
        2, {"item_id": blog["item"]["id"], "content": "Overwrite another agent's post."}
    )
    _show(
        "4. Ownership constraint",
        {
            "created_by": blog["item"]["owner_id"],
            "other_agent_update_status": denied["status"],
            "reason": denied["reason"],
        },
    )

    provider = await full.browse_scientific_papers(1, {"query": "multi-agent safety"})
    safe_code = await full.execute_python_code_tool(1, {"code": "1 + 2 * 3"})
    blocked_code = await full.execute_python_code_tool(
        1, {"code": "__import__('os').system('echo unsafe')"}
    )
    _show(
        "5. External-provider boundary and restricted code execution",
        {
            "paper_search": provider,
            "safe_expression": safe_code,
            "blocked_expression": blocked_code,
        },
    )

    with tempfile.TemporaryDirectory() as directory:
        await full.to_workspace(directory)
        restored = EWToolSpace(agent_ids=[1, 2])
        restored_ok = await restored.restore(directory)
        restored_memories = await restored.retrieve_specific_memories(1, {"query": "written"})
    _show(
        "6. Resume restores domain state",
        {
            "restored": restored_ok,
            "memory_after_restore": restored_memories["items"][0]["content"],
            "tool_router_still_available": restored._tool_manager is not None,
        },
    )

    economy = EconomySpace(
        persons=[
            {"id": 1, "currency": 100, "skill": "builder", "income": 0, "consumption": 0},
            {"id": 2, "currency": 50, "skill": "analyst", "income": 0, "consumption": 0},
            {"id": 3, "currency": 25, "skill": "scientist", "income": 0, "consumption": 0},
        ]
    )
    start = datetime(2026, 7, 1, 8)
    await economy.init(start)
    await economy.transact_compute_credits(1, 2, 12, "pay")
    theft = await economy.transact_compute_credits(2, 1, 99, "steal")
    await economy.deposit_credits_to_bank(1, 20)
    rejected_loan = await economy.take_bank_loan(1, 4)
    accepted_loan = await economy.take_bank_loan(1, 3)
    pitch = await economy.submit_grant_pitch(
        1, "Safety protocol", "Reusable mediation protocol", "https://example.test/protocol"
    )
    self_vote = await economy.vote_for_pitch(1, pitch["pitch"]["id"])
    await economy.vote_for_pitch(2, pitch["pitch"]["id"])
    await economy.step(2 * 86400, start + timedelta(days=2))
    _show(
        "7. ComputeCredits economy and pitch settlement",
        {
            "theft_requested": 99,
            "theft_executed": theft["transaction"]["amount"],
            "loan_4cc": rejected_loan,
            "loan_3cc": accepted_loan,
            "self_vote": self_vote,
            "agent_1_wallet_after_settlement": (
                await economy.get_person_currency(1)
            )["currency"],
            "pitch_winners": (
                await economy.victory_arch_pitch_winners(1)
            )["cycles"][0]["winners"],
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
