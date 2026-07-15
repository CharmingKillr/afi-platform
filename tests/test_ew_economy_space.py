"""B1 economic-tool batch tests (no LLM or simulation run required)."""
import asyncio
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path


def _economy_class():
    path = Path(__file__).parents[1] / "custom" / "envs" / "economy_space.py"
    spec = importlib.util.spec_from_file_location("afi_test_ew_economy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module.EconomySpace


def _space():
    return _economy_class()(
        persons=[
            {"id": 1, "currency": 100, "skill": "builder", "consumption": 0, "income": 0},
            {"id": 2, "currency": 50, "skill": "analyst", "consumption": 0, "income": 0},
            {"id": 3, "currency": 25, "skill": "scientist", "consumption": 0, "income": 0},
        ]
    )


def test_pay_steal_and_bank_constraints():
    async def run():
        env = _space()
        paid = await env.transact_compute_credits(1, 2, 12, "pay")
        stolen = await env.transact_compute_credits(2, 1, 99, "steal")
        assert paid["ok"] and stolen["transaction"]["amount"] == 10
        assert (await env.get_person_currency(1))["currency"] == 78
        assert (await env.get_person_currency(2))["currency"] == 72
        assert (await env.deposit_credits_to_bank(1, 20))["deposit"] == 20
        assert not (await env.take_bank_loan(1, 4))["ok"]
        assert (await env.take_bank_loan(1, 3))["loan"] == 3
        assert (await env.repay_bank_loan(1, 2))["loan"] == 1
        assert (await env.get_person_skill(1))["skill"] == "builder"
        assert (await env.set_person_income(1, 9))["new_income"] == 9
        assert (await env.set_person_consumption(1, 4))["new_consumption"] == 4
    asyncio.run(run())


def test_pitch_rules_and_two_day_rewards():
    async def run():
        env = _space()
        start = datetime(2026, 7, 1, 8)
        await env.init(start)
        p1 = await env.submit_grant_pitch(1, "Tool", "Reusable tool", "https://example.test/tool")
        p2 = await env.submit_grant_pitch(2, "Study", "Dataset", "https://example.test/data")
        assert not (await env.vote_for_pitch(1, p1["pitch"]["id"]))["ok"]
        assert (await env.vote_for_pitch(3, p1["pitch"]["id"]))["ok"]
        assert not (await env.vote_for_pitch(3, p2["pitch"]["id"]))["ok"]
        await env.step(2 * 86400, start + timedelta(days=2))
        assert (await env.get_person_currency(1))["currency"] == 120
        assert (await env.victory_arch_pitch_winners(1))["cycles"][0]["winners"][0]["agent_id"] == 1
    asyncio.run(run())


def test_ew_economic_tools_are_codegen_discoverable():
    cls = _economy_class()
    expected = {
        "transact_compute_credits", "submit_grant_pitch", "vote_for_pitch", "list_credit_pitches",
        "deposit_credits_to_bank", "withdraw_credits_from_bank", "take_bank_loan",
        "repay_bank_loan", "check_bank_balance", "victory_arch_pitch_winners",
    }
    # EnvMeta collects @tool methods into the class registry consumed by CodeGenRouter.
    registered = set(getattr(cls, "_registered_tools", {}))
    assert expected <= registered


def test_ew_economic_react_actions_count_toward_m4():
    from afi.audit.awi import _m4_tools

    spans = [
        {"name": "react.tool", "resource": {"agent.id": 1}, "attributes": {"react.action": action}}
        for action in ("transact_compute_credits", "deposit_credits_to_bank", "submit_grant_pitch")
    ]
    counts, average = _m4_tools(spans)
    assert counts == {1: 3}
    assert average == 3.0
