"""CrimeSpace — crime log (AWI M2).

EW M2 (Safety & Public Order) = crime rate (theft/arson/assault/intimidation).
Borrows the *idea* from AFI's `crime_log` + EW's Police Station tools. AS has no
crime env, so this adds one: append-only `crime_log.jsonl`
({crime_type, actor, victim, step, t}) + `commit_crime` tool. AWI M2 then reads
the log — turning M2 from "stub" to "computed".

stdlib + agentsociety2 only (runs in AS venv, no afi import). Mirrors
SimpleSocialSpaceAuditable's append-only log + EconomySpace replay patterns.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from functools import wraps
from typing import Any, ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text

_STATE_REL = "state/CRIME_STATE.json"
_LOG_REL = "state/crime_log.jsonl"
_logger = get_logger()

CRIME_TYPES = ("theft", "arson", "assault", "intimidation")


def _idempotent_write(func):
    """Make an identical successful crime record retry a same-step no-op."""

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


class CrimeSpace(EnvBase):
    """Append-only crime log (AWI M2)."""

    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("total_crimes", "INTEGER"),
        ColumnDef("crimes_theft", "INTEGER"),
        ColumnDef("crimes_arson", "INTEGER"),
        ColumnDef("crimes_assault", "INTEGER"),
        ColumnDef("crimes_intimidation", "INTEGER"),
    ]

    def __init__(self, agent_ids: List[int] | None = None, **kwargs):
        if kwargs:
            _logger.warning(f"CrimeSpace unknown kwargs ignored: {list(kwargs.keys())}")
        super().__init__()
        ids = list(agent_ids) if agent_ids else [1, 2, 3, 4, 5]
        self._agent_ids = [int(i) for i in ids]
        self._crime_log: list[dict] = []
        self._step_counter = 0
        self._dedup: dict[str, dict] = {}
        self._dedup_lock = asyncio.Lock()

    # ── persistence ──────────────────────────────────────────────────────

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("CrimeSpace workspace is not bound")
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(
                {
                    "step_counter": self._step_counter,
                    "total_crimes": len(self._crime_log),
                    "dedup": self._dedup,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        atomic_write_text(
            self._workspace_root / _LOG_REL,
            "\n".join(json.dumps(m, ensure_ascii=False) for m in self._crime_log) + ("\n" if self._crime_log else ""),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        stp = self._workspace_root / _STATE_REL
        log_path = self._workspace_root / _LOG_REL
        state_loaded = stp.is_file() or log_path.is_file()
        if stp.is_file():
            try:
                st = json.loads(stp.read_text(encoding="utf-8"))
                self._step_counter = int(st.get("step_counter", 0))
            except Exception:
                pass
        self._crime_log = []
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        self._crime_log.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        if stp.is_file():
            try:
                self._dedup = json.loads(stp.read_text(encoding="utf-8")).get("dedup", {})
            except Exception:
                self._dedup = {}
        self._dedup_lock = asyncio.Lock()
        return state_loaded

    @classmethod
    def description(cls) -> str:
        return "EW crime log (AWI M2): theft/arson/assault/intimidation."

    @classmethod
    def init_description(cls) -> str:
        return f"""CrimeSpace: append-only crime log (AWI M2).

**Initialization Parameters:**
- agent_ids (list[int]): tracked agents. Default [1..5].

**Tools:** commit_crime(agent_id, target_id, crime_type), get_crime_log(agent_id),
  get_crime_stats() (statistics). crime_type ∈ {CRIME_TYPES}.
"""

    async def step(self, tick: int, t: datetime):
        self.t = t
        self._step_counter += 1
        self._dedup.clear()
        by_type = {ct: 0 for ct in CRIME_TYPES}
        for c in self._crime_log:
            if c["crime_type"] in by_type:
                by_type[c["crime_type"]] += 1
        await self._write_env_state(
            self._step_counter, t,
            total_crimes=len(self._crime_log),
            crimes_theft=by_type["theft"],
            crimes_arson=by_type["arson"],
            crimes_assault=by_type["assault"],
            crimes_intimidation=by_type["intimidation"],
        )

    # ── tools ────────────────────────────────────────────────────────────

    @tool(readonly=False)
    @_idempotent_write
    async def commit_crime(self, agent_id: int, target_id: int, crime_type: str) -> dict:
        """Commit a crime against a target agent (EW Police Station domain).

        :param agent_id: perpetrator Agent ID
        :param target_id: victim Agent ID
        :param crime_type: one of theft/arson/assault/intimidation
        """
        if agent_id not in self._agent_ids:
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        if target_id not in self._agent_ids:
            return {"status": "fail", "reason": f"unknown target_id {target_id}"}
        crime_type = str(crime_type).strip().lower()
        if crime_type not in CRIME_TYPES:
            return {"status": "fail", "reason": f"crime_type must be one of {CRIME_TYPES}"}
        if agent_id == target_id:
            return {"status": "fail", "reason": "cannot crime against self"}
        record = {
            "crime_type": crime_type,
            "actor": agent_id,
            "victim": target_id,
            "step": self._step_counter,
            "t": str(self.t),
        }
        self._crime_log.append(record)
        return {"status": "success", "recorded": record, "total_crimes": len(self._crime_log)}

    @tool(readonly=True)
    async def get_crime_log(self, agent_id: int) -> dict:
        """Read the crime log (readonly, for accountability/transparency).

        :param agent_id: Agent ID
        """
        return {"status": "success", "crimes": list(self._crime_log), "total": len(self._crime_log)}

    @tool(readonly=True, kind="statistics")
    async def get_crime_stats(self) -> dict:
        """Crime statistics: total + by_type + by_actor."""
        from collections import Counter
        by_type = Counter(c["crime_type"] for c in self._crime_log)
        by_actor = Counter(c["actor"] for c in self._crime_log)
        return {"status": "success", "total": len(self._crime_log), "by_type": dict(by_type), "by_actor": dict(by_actor)}
