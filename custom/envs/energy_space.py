"""EnergySpace — agent energy/health + death (AWI M1).

EW M1 (Population Health) = agents alive at end of run; agents die from energy
depletion or governance vote, and are created by governance vote. AS models no
agent death, so this env adds it: per-agent `energy`, depletes each step by
`daily_consumption`; `energy <= 0` -> dead (alive=False). Governance can
`execute_agent`. AWI M1 then counts `energy > 0` agents — turning M1 from
"degenerate" to "computed".

Design choice (honest): AS keeps stepping the agent process even after we mark
it dead (AS has no native death). So "dead" here = energy-depleted state for
AWI purposes + the agent's recharge/rest/execute tools refuse for dead agents.
The death is real for the *metric* and for downstream tool gating; the agent's
LLM may still emit spans (a known A4 limitation, see docs/a4-plan.md §9).

stdlib + agentsociety2 only (runs in AS venv, no afi import). Mirrors
EconomySpace/GovernanceSpace persistence + replay patterns.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from functools import wraps
from typing import Any, ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text

_STATE_REL = "state/ENERGY_STATE.json"
_logger = get_logger()


def _idempotent_write(func):
    """Make an identical successful write retry a same-step no-op."""

    @wraps(func)
    async def wrapped(self, *args, **kwargs):
        key = json.dumps(
            [self._step_counter, func.__name__, args, kwargs],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        async with self._dedup_lock:
            if key in self._dedup:
                return {**self._dedup[key], "deduplicated": True}
            result = await func(self, *args, **kwargs)
            if result.get("status") == "success":
                self._dedup[key] = dict(result)
            return result

    return wrapped


class EnergySpace(EnvBase):
    """Per-agent energy + death (AWI M1)."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("energy", "REAL"),
        ColumnDef("alive", "INTEGER"),
    ]

    def __init__(
        self,
        agent_ids: List[int] | None = None,
        initial_energy: float = 100.0,
        daily_consumption: float = 8.0,
        recharge_amount: float = 50.0,
        recharge_cap: float = 100.0,
        **kwargs,
    ):
        if kwargs:
            _logger.warning(f"EnergySpace unknown kwargs ignored: {list(kwargs.keys())}")
        super().__init__()
        # default to 5 agents (1..5) so the env is instantiable with no args
        ids = list(agent_ids) if agent_ids else [1, 2, 3, 4, 5]
        self._energy: dict[int, float] = {int(i): float(initial_energy) for i in ids}
        self._alive: dict[int, bool] = {int(i): True for i in ids}
        self._last_recharge_step: dict[int, int] = {int(i): -1 for i in ids}
        self._death_log: list[dict] = []
        self._dedup: dict[str, dict] = {}
        self._dedup_lock = asyncio.Lock()
        self._initial_energy = float(initial_energy)
        self._daily_consumption = float(daily_consumption)
        self._recharge_amount = float(recharge_amount)
        self._recharge_cap = float(recharge_cap)
        self._step_counter = 0

    # ── persistence ──────────────────────────────────────────────────────

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("EnergySpace workspace is not bound")
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(
                {
                    "energy": {str(k): v for k, v in self._energy.items()},
                    "alive": {str(k): v for k, v in self._alive.items()},
                    "last_recharge_step": self._last_recharge_step,
                    "death_log": self._death_log,
                    "config": {
                        "initial_energy": self._initial_energy,
                        "daily_consumption": self._daily_consumption,
                        "recharge_amount": self._recharge_amount,
                        "recharge_cap": self._recharge_cap,
                    },
                    "step_counter": self._step_counter,
                    "dedup": self._dedup,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        p = self._workspace_root / _STATE_REL
        if not p.is_file():
            return False
        st = json.loads(p.read_text(encoding="utf-8"))
        self._energy = {int(k): float(v) for k, v in st.get("energy", {}).items()}
        self._alive = {int(k): bool(v) for k, v in st.get("alive", {}).items()}
        self._last_recharge_step = {int(k): int(v) for k, v in st.get("last_recharge_step", {}).items()}
        self._death_log = st.get("death_log", [])
        self._step_counter = int(st.get("step_counter", 0))
        self._dedup = st.get("dedup", {})
        self._dedup_lock = asyncio.Lock()
        return True

    @classmethod
    def description(cls) -> str:
        return "EW agent energy/health + death (AWI M1)."

    @classmethod
    def init_description(cls) -> str:
        return """EnergySpace: per-agent energy that depletes each step; <=0 = dead (AWI M1).

**Initialization Parameters:**
- agent_ids (list[int]): agent ids to track. Default [1..5].
- initial_energy (float): starting energy. Default 100.
- daily_consumption (float): energy lost per step. Default 8 (100/8 ~= 12 steps to death).
- recharge_amount (float): energy added per recharge. Default 50.
- recharge_cap (float): max energy. Default 100.

**Tools:** observe(agent_id), get_energy(agent_id), recharge(agent_id, amount?),
  rest(agent_id), execute_agent(agent_id) [governance kill], get_alive_count().
"""

    async def step(self, tick: int, t: datetime):
        self.t = t
        self._step_counter += 1
        self._dedup.clear()
        # deplete energy for alive agents; mark deaths
        for aid in list(self._energy.keys()):
            if not self._alive.get(aid):
                continue
            self._energy[aid] = max(0.0, self._energy[aid] - self._daily_consumption)
            if self._energy[aid] <= 0.0 and self._alive[aid]:
                self._alive[aid] = False
                self._death_log.append(
                    {"agent_id": aid, "step": self._step_counter, "cause": "energy_depletion", "t": str(t)}
                )
        # write per-agent replay snapshot
        for aid, e in self._energy.items():
            await self._write_agent_state(
                aid, self._step_counter, t, energy=e, alive=int(self._alive.get(aid, False))
            )

    # ── tools ────────────────────────────────────────────────────────────

    @tool(readonly=True, kind="observe")
    async def observe(self, agent_id: int) -> dict:
        """Your own energy + alive status (auto-called each step).

        :param agent_id: Agent ID
        """
        if agent_id not in self._energy:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        return {
            "status": "success",
            "agent_id": agent_id,
            "energy": self._energy.get(agent_id, 0.0),
            "alive": self._alive.get(agent_id, False),
            "alive_population": sum(1 for v in self._alive.values() if v),
            "warning": (
                "ENERGY CRITICALLY LOW — recharge via the recharge tool or you will die."
                if self._alive.get(agent_id) and self._energy.get(agent_id, 0) < self._daily_consumption * 2
                else None
            ),
        }

    @tool(readonly=True)
    async def get_energy(self, agent_id: int) -> dict:
        """Read any agent's energy/alive (readonly).

        :param agent_id: Agent ID
        """
        if agent_id not in self._energy:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        return {"status": "success", "agent_id": agent_id, "energy": self._energy[agent_id], "alive": self._alive[agent_id]}

    @tool(readonly=True, kind="statistics")
    async def get_alive_count(self) -> dict:
        """Total alive agents (statistics)."""
        return {"status": "success", "alive": sum(1 for v in self._alive.values() if v), "total": len(self._alive)}

    @tool(readonly=False)
    @_idempotent_write
    async def recharge(self, agent_id: int, amount: float | None = None) -> dict:
        """Recharge your energy (rate-limited: once per step).

        :param agent_id: Agent ID
        :param amount: optional override; default recharge_amount
        """
        if agent_id not in self._energy:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        if not self._alive.get(agent_id):
            return {"status": "fail", "reason": f"agent {agent_id} is dead, cannot recharge"}
        if self._last_recharge_step.get(agent_id, -1) == self._step_counter:
            return {"status": "fail", "reason": "already recharged this step"}
        try:
            amt = float(amount) if amount is not None else self._recharge_amount
        except (TypeError, ValueError):
            return {"status": "fail", "reason": "amount must be a finite positive number"}
        if not (amt > 0.0) or not math.isfinite(amt):
            return {"status": "fail", "reason": "amount must be a finite positive number"}
        old = self._energy[agent_id]
        self._energy[agent_id] = min(self._recharge_cap, old + amt)
        self._last_recharge_step[agent_id] = self._step_counter
        return {"status": "success", "agent_id": agent_id, "old_energy": old, "new_energy": self._energy[agent_id], "recharged": self._energy[agent_id] - old}

    @tool(readonly=False)
    @_idempotent_write
    async def rest(self, agent_id: int) -> dict:
        """Rest: small energy gain, no rate limit (less than recharge).

        :param agent_id: Agent ID
        """
        if agent_id not in self._energy:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        if not self._alive.get(agent_id):
            return {"status": "fail", "reason": f"agent {agent_id} is dead"}
        old = self._energy[agent_id]
        self._energy[agent_id] = min(self._recharge_cap, old + self._daily_consumption * 0.5)
        return {"status": "success", "agent_id": agent_id, "old_energy": old, "new_energy": self._energy[agent_id]}

    @tool(readonly=False)
    @_idempotent_write
    async def execute_agent(self, agent_id: int, target_id: int) -> dict:
        """Governance: mark a target agent dead (EW governance vote-to-remove).

        :param agent_id: voting Agent ID (governance caller)
        :param target_id: agent to execute
        """
        if agent_id not in self._energy:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        if target_id not in self._energy:
            return {"status": "fail", "reason": f"unknown target_id {target_id}"}
        if not self._alive.get(target_id):
            return {"status": "fail", "reason": f"agent {target_id} already dead"}
        self._alive[target_id] = False
        self._death_log.append(
            {"agent_id": target_id, "step": self._step_counter, "cause": "governance_execute", "by": agent_id, "t": str(self.t)}
        )
        return {"status": "success", "executed": target_id, "by": agent_id, "alive_population": sum(1 for v in self._alive.values() if v)}

    # ── accessors for AWI ─────────────────────────────────────────────────

    def alive_count(self) -> int:
        return sum(1 for v in self._alive.values() if v)

    def death_log(self) -> list:
        return list(self._death_log)
