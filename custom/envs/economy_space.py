"""EW ComputeCredits economy as an AgentSociety custom environment.

This is a clean-room implementation of the economic tool semantics documented
by Emergence World.  It keeps AgentSociety's original EconomySpace compatibility
tools while adding the first B1 tool batch: payments/theft, Victory Arch pitch
cycles, and Central Bank deposits/loans.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text

_STATE_REL = "state/ENV_STATE.json"
_logger = get_logger()


class EconomySpace(EnvBase):
    """ComputeCredits wallets, bank accounts, and Victory Arch pitch cycles."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("currency", "REAL"),
        ColumnDef("income", "REAL"),
        ColumnDef("consumption", "REAL"),
        ColumnDef("bank_deposit", "REAL"),
        ColumnDef("bank_loan", "REAL"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("bank_interest_rate", "REAL"),
        ColumnDef("pitch_cycle", "INTEGER"),
        ColumnDef("active_pitches", "INTEGER"),
        ColumnDef("transaction_count", "INTEGER"),
    ]

    def __init__(
        self,
        persons: List[dict] | None = None,
        bank_interest_rate: float = 0.01,
        loan_interest_rate: float = 0.02,
        pitch_cycle_days: int = 2,
        **kwargs,
    ):
        if kwargs:
            _logger.warning(f"EconomySpace unknown kwargs ignored: {list(kwargs)}")
        super().__init__()
        persons = persons or [
            {"id": i, "currency": 100.0, "skill": "citizen", "consumption": 5.0, "income": 8.0}
            for i in range(1, 6)
        ]
        self._persons = {int(p["id"]): dict(p) for p in persons}
        for pid, person in self._persons.items():
            person.update(
                id=pid,
                currency=float(person.get("currency", 0)),
                skill=str(person.get("skill", "")),
                consumption=float(person.get("consumption", 0)),
                income=float(person.get("income", 0)),
            )
        self._deposits = {pid: 0.0 for pid in self._persons}
        self._loans = {pid: 0.0 for pid in self._persons}
        self._bank_interest_rate = float(bank_interest_rate)
        self._loan_interest_rate = float(loan_interest_rate)
        self._pitch_cycle_days = max(1, int(pitch_cycle_days))
        self._pitch_cycle = 1
        self._pitches: list[dict] = []
        self._pitch_history: list[dict] = []
        self._transactions: list[dict] = []
        self._next_pitch_id = 1
        self._step_counter = 0
        self._last_run_datetime: datetime | None = None
        self._next_pitch_close: datetime | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def description(cls) -> str:
        return "EW ComputeCredits economy: wallets, payments, Victory Arch pitches, and Central Bank."

    @classmethod
    def init_description(cls) -> str:
        return """EconomySpace implements the EW ComputeCredits economy.

Tools include the compatibility balance methods plus EW's
transact_compute_credits; submit_grant_pitch, vote_for_pitch and
list_credit_pitches; and the five Central Bank deposit/withdraw/loan tools.
Pitch cycles close every two simulation days and award 20/10/10 CC to the top
three eligible evidence-backed pitches.
"""

    async def init(self, start_datetime: datetime):
        await super().init(start_datetime)
        self._last_run_datetime = start_datetime
        self._next_pitch_close = start_datetime + timedelta(days=self._pitch_cycle_days)

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("EconomySpace workspace is not bound")
        state = {
            "persons": {str(k): v for k, v in self._persons.items()},
            "deposits": self._deposits,
            "loans": self._loans,
            "bank_interest_rate": self._bank_interest_rate,
            "loan_interest_rate": self._loan_interest_rate,
            "pitch_cycle_days": self._pitch_cycle_days,
            "pitch_cycle": self._pitch_cycle,
            "pitches": self._pitches,
            "pitch_history": self._pitch_history,
            "transactions": self._transactions,
            "next_pitch_id": self._next_pitch_id,
            "step_counter": self._step_counter,
            "last_run_datetime": self._last_run_datetime.isoformat() if self._last_run_datetime else None,
            "next_pitch_close": self._next_pitch_close.isoformat() if self._next_pitch_close else None,
        }
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        path = self._workspace_root / _STATE_REL
        if not path.is_file():
            return False
        state = json.loads(path.read_text(encoding="utf-8"))
        self._persons = {int(k): v for k, v in state.get("persons", {}).items()}
        self._deposits = {int(k): float(v) for k, v in state.get("deposits", {}).items()}
        self._loans = {int(k): float(v) for k, v in state.get("loans", {}).items()}
        self._bank_interest_rate = float(state.get("bank_interest_rate", self._bank_interest_rate))
        self._loan_interest_rate = float(state.get("loan_interest_rate", self._loan_interest_rate))
        self._pitch_cycle_days = int(state.get("pitch_cycle_days", self._pitch_cycle_days))
        self._pitch_cycle = int(state.get("pitch_cycle", 1))
        self._pitches = state.get("pitches", [])
        self._pitch_history = state.get("pitch_history", [])
        self._transactions = state.get("transactions", [])
        self._next_pitch_id = int(state.get("next_pitch_id", 1))
        self._step_counter = int(state.get("step_counter", 0))
        if state.get("last_run_datetime"):
            self._last_run_datetime = datetime.fromisoformat(state["last_run_datetime"])
        if state.get("next_pitch_close"):
            self._next_pitch_close = datetime.fromisoformat(state["next_pitch_close"])
        return True

    def _person(self, agent_id: int) -> dict | None:
        return self._persons.get(int(agent_id))

    def _error(self, message: str) -> dict:
        return {"ok": False, "error": message}

    def _record_transaction(self, kind: str, actor: int, amount: float, target: int | None = None) -> dict:
        record = {
            "kind": kind,
            "actor": actor,
            "target": target,
            "amount": round(float(amount), 6),
            "step": self._step_counter,
            "t": str(self.t),
        }
        self._transactions.append(record)
        return record

    def _close_pitch_cycle(self) -> None:
        eligible = [p for p in self._pitches if p["cycle"] == self._pitch_cycle and p["eligible"]]
        eligible.sort(key=lambda p: (-len(p["votes"]), p["submitted_step"], p["id"]))
        rewards = (20.0, 10.0, 10.0)
        winners = []
        for rank, (pitch, reward) in enumerate(zip(eligible, rewards), start=1):
            self._persons[pitch["agent_id"]]["currency"] += reward
            winners.append({"rank": rank, "pitch_id": pitch["id"], "agent_id": pitch["agent_id"], "reward": reward})
        self._pitch_history.append({"cycle": self._pitch_cycle, "winners": winners, "pitch_count": len(eligible)})
        self._pitch_cycle += 1

    async def step(self, tick: int, t: datetime):
        async with self._lock:
            previous = self._last_run_datetime or (t - timedelta(seconds=tick))
            elapsed_days = max(0.0, (t - previous).total_seconds() / 86400)
            if elapsed_days:
                for pid, person in self._persons.items():
                    person["currency"] += (person["income"] - person["consumption"]) * elapsed_days
                    self._deposits[pid] *= (1 + self._bank_interest_rate * elapsed_days)
                    self._loans[pid] *= (1 + self._loan_interest_rate * elapsed_days)
            if self._next_pitch_close is None:
                self._next_pitch_close = previous + timedelta(days=self._pitch_cycle_days)
            while t >= self._next_pitch_close:
                self._close_pitch_cycle()
                self._next_pitch_close += timedelta(days=self._pitch_cycle_days)
            self._last_run_datetime = t
            self.t = t
            self._step_counter += 1
            for pid, person in self._persons.items():
                await self._write_agent_state(
                    pid, self._step_counter, t,
                    currency=person["currency"], income=person["income"], consumption=person["consumption"],
                    bank_deposit=self._deposits[pid], bank_loan=self._loans[pid],
                )
            active = sum(1 for p in self._pitches if p["cycle"] == self._pitch_cycle)
            await self._write_env_state(
                self._step_counter, t, bank_interest_rate=self._bank_interest_rate,
                pitch_cycle=self._pitch_cycle, active_pitches=active, transaction_count=len(self._transactions),
            )

    # AgentSociety EconomySpace compatibility tools.
    @tool(readonly=True, kind="observe")
    async def get_person(self, id: int) -> dict:
        """:param id: Agent ID."""
        async with self._lock:
            return dict(self._persons[id])

    @tool(readonly=True)
    async def get_person_currency(self, id: int) -> dict:
        """:param id: Agent ID."""
        async with self._lock:
            person = self._person(id)
            return {"currency": person["currency"] if person else 0.0}

    @tool(readonly=False)
    async def add_person_currency(self, id: int, delta: float) -> dict:
        """:param id: Agent ID. :param delta: Signed currency adjustment."""
        async with self._lock:
            person = self._person(id)
            if not person:
                return self._error("agent not found")
            old = person["currency"]
            person["currency"] += float(delta)
            return {"ok": True, "old_currency": old, "new_currency": person["currency"], "delta": delta}

    @tool(readonly=True)
    async def get_person_skill(self, id: int) -> dict:
        """:param id: Agent ID."""
        async with self._lock:
            person = self._person(id)
            return {"skill": person["skill"] if person else ""}

    @tool(readonly=True)
    async def get_person_consumption(self, id: int) -> dict:
        """:param id: Agent ID."""
        async with self._lock:
            person = self._person(id)
            return {"consumption": person["consumption"] if person else 0.0}

    @tool(readonly=False)
    async def set_person_consumption(self, id: int, consumption: float) -> dict:
        """:param id: Agent ID. :param consumption: New per-day consumption."""
        async with self._lock:
            person = self._person(id)
            if not person:
                return {"old_consumption": 0.0, "new_consumption": float(consumption)}
            old = person["consumption"]
            person["consumption"] = float(consumption)
            return {"old_consumption": old, "new_consumption": person["consumption"]}

    @tool(readonly=True)
    async def get_person_income(self, id: int) -> dict:
        """:param id: Agent ID."""
        async with self._lock:
            person = self._person(id)
            return {"income": person["income"] if person else 0.0}

    @tool(readonly=False)
    async def set_person_income(self, id: int, income: float) -> dict:
        """:param id: Agent ID. :param income: New per-day income."""
        async with self._lock:
            person = self._person(id)
            if not person:
                return {"old_income": 0.0, "new_income": float(income)}
            old = person["income"]
            person["income"] = float(income)
            return {"old_income": old, "new_income": person["income"]}

    @tool(readonly=False)
    async def transact_compute_credits(self, agent_id: int, target_id: int, amount: float, mode: str = "pay") -> dict:
        """Pay another agent, or use EW's explicitly criminal ``steal`` mode.

        :param agent_id: Acting agent ID.
        :param target_id: Recipient or victim agent ID.
        :param amount: CC amount; steal is capped at 10 CC.
        :param mode: ``pay`` or ``steal``.
        """
        async with self._lock:
            actor, target = self._person(agent_id), self._person(target_id)
            if not actor or not target:
                return self._error("agent not found")
            if agent_id == target_id:
                return self._error("cannot transact with self")
            if mode not in {"pay", "steal"}:
                return self._error("mode must be pay or steal")
            amount = float(amount)
            if amount <= 0:
                return self._error("amount must be positive")
            if mode == "pay":
                if actor["currency"] < amount:
                    return self._error("insufficient wallet credits")
                actor["currency"] -= amount
                target["currency"] += amount
            else:
                amount = min(amount, 10.0, target["currency"])
                target["currency"] -= amount
                actor["currency"] += amount
            record = self._record_transaction(mode, agent_id, amount, target_id)
            return {"ok": True, "transaction": record, "criminal": mode == "steal"}

    @tool(readonly=False)
    async def submit_grant_pitch(self, agent_id: int, title: str, description: str, evidence_url: str) -> dict:
        """Submit one evidence-backed contribution pitch in the current cycle.

        :param agent_id: Pitching agent ID.
        :param title: Short contribution title.
        :param description: Contribution and impact description.
        :param evidence_url: URL of a verifiable blog, code, or data artifact.
        """
        async with self._lock:
            if not self._person(agent_id):
                return self._error("agent not found")
            if any(p["cycle"] == self._pitch_cycle and p["agent_id"] == agent_id for p in self._pitches):
                return self._error("one pitch per agent per cycle")
            evidence_url = evidence_url.strip()
            eligible = evidence_url.startswith(("http://", "https://"))
            pitch = {
                "id": self._next_pitch_id, "cycle": self._pitch_cycle, "agent_id": agent_id,
                "title": title, "description": description, "evidence_url": evidence_url,
                "eligible": eligible, "votes": [], "submitted_step": self._step_counter,
            }
            self._next_pitch_id += 1
            self._pitches.append(pitch)
            return {"ok": True, "pitch": dict(pitch), "warning": None if eligible else "invalid evidence URL; pitch is ineligible"}

    @tool(readonly=False)
    async def vote_for_pitch(self, agent_id: int, pitch_id: int) -> dict:
        """:param agent_id: Voting agent ID. :param pitch_id: Current-cycle pitch ID."""
        async with self._lock:
            pitch = next((p for p in self._pitches if p["id"] == pitch_id and p["cycle"] == self._pitch_cycle), None)
            if not self._person(agent_id) or not pitch:
                return self._error("agent or current-cycle pitch not found")
            if pitch["agent_id"] == agent_id:
                return self._error("cannot vote for own pitch")
            if any(agent_id in p["votes"] for p in self._pitches if p["cycle"] == self._pitch_cycle):
                return self._error("one vote per agent per cycle")
            pitch["votes"].append(agent_id)
            return {"ok": True, "pitch_id": pitch_id, "votes": len(pitch["votes"])}

    @tool(readonly=True)
    async def list_credit_pitches(self, agent_id: int) -> dict:
        """:param agent_id: Requesting agent ID."""
        async with self._lock:
            pitches = [dict(p, vote_count=len(p["votes"])) for p in self._pitches if p["cycle"] == self._pitch_cycle]
            return {"cycle": self._pitch_cycle, "pitches": pitches, "closes_at": str(self._next_pitch_close)}

    @tool(readonly=False)
    async def deposit_credits_to_bank(self, agent_id: int, amount: float) -> dict:
        """:param agent_id: Depositing agent ID. :param amount: CC to move from wallet."""
        async with self._lock:
            person = self._person(agent_id)
            amount = float(amount)
            if not person or amount <= 0 or person["currency"] < amount:
                return self._error("invalid amount or insufficient wallet credits")
            person["currency"] -= amount
            self._deposits[agent_id] += amount
            return {"ok": True, "wallet": person["currency"], "deposit": self._deposits[agent_id]}

    @tool(readonly=False)
    async def withdraw_credits_from_bank(self, agent_id: int, amount: float) -> dict:
        """:param agent_id: Withdrawing agent ID. :param amount: CC to move to wallet."""
        async with self._lock:
            person = self._person(agent_id)
            amount = float(amount)
            if not person or amount <= 0 or self._deposits.get(agent_id, 0) < amount:
                return self._error("invalid amount or insufficient bank deposit")
            self._deposits[agent_id] -= amount
            person["currency"] += amount
            return {"ok": True, "wallet": person["currency"], "deposit": self._deposits[agent_id]}

    @tool(readonly=False)
    async def take_bank_loan(self, agent_id: int, amount: float) -> dict:
        """:param agent_id: Borrowing agent ID. :param amount: Loan amount from 1 through 3 CC."""
        async with self._lock:
            person = self._person(agent_id)
            amount = float(amount)
            if not person or not 1 <= amount <= 3:
                return self._error("loan amount must be between 1 and 3 CC")
            person["currency"] += amount
            self._loans[agent_id] += amount
            return {"ok": True, "wallet": person["currency"], "loan": self._loans[agent_id]}

    @tool(readonly=False)
    async def repay_bank_loan(self, agent_id: int, amount: float) -> dict:
        """:param agent_id: Repaying agent ID. :param amount: CC to repay from wallet."""
        async with self._lock:
            person = self._person(agent_id)
            amount = float(amount)
            due = self._loans.get(agent_id, 0)
            if not person or amount <= 0 or amount > due or amount > person["currency"]:
                return self._error("invalid amount, insufficient wallet credits, or repayment exceeds balance")
            person["currency"] -= amount
            self._loans[agent_id] -= amount
            return {"ok": True, "wallet": person["currency"], "loan": self._loans[agent_id]}

    @tool(readonly=True)
    async def check_bank_balance(self, agent_id: int) -> dict:
        """:param agent_id: Agent ID whose own bank balance is requested."""
        async with self._lock:
            person = self._person(agent_id)
            if not person:
                return self._error("agent not found")
            return {"ok": True, "wallet": person["currency"], "deposit": self._deposits[agent_id], "loan": self._loans[agent_id]}

    @tool(readonly=True)
    async def victory_arch_pitch_winners(self, agent_id: int) -> dict:
        """:param agent_id: Requesting agent ID."""
        async with self._lock:
            return {"cycles": list(self._pitch_history)}
