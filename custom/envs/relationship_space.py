"""RelationshipSpace — EW ally/rival/mentor relationship model (AWI M7).

EW M7 (Social Fabric) currently computed from message-graph density (proxy).
This env adds typed relationships so AWI M7 upgrades to "computed":
- Relationship types: ally, rival, mentor, mentee, neutral
- Append-only relationship_log.jsonl + per-step relationship_agent_state replay
- AWI _m7_relationship_computed() reads shards: type counts + graph metrics

Design:
- EnvBase subclass, runs inside AS venv, no afi import
- Mirrors EnergySpace persistence pattern (state JSON + replay shards)
- Tools: form_relationship, dissolve_relationship, query_relationships, list_all_relationships

AWI integration (in afi/audit/awi.py):
- _m7_relationship_computed() reads relationship_agent_state.*.jsonl
- M7 feasibility: computed if shards exist, else proxy
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text

_logger = get_logger()

# ── Relationship types (EW-inspired) ──────────────────────────────────────────
REL_TYPES = {"ally", "rival", "mentor", "mentee", "neutral"}

_STATE_REL = "state/RELATIONSHIP_STATE.json"
_LOG_REL   = "state/relationship_log.jsonl"


class RelationshipSpace(EnvBase):
    """Typed agent relationship graph (AWI M7 computed).

    Agents call form_relationship / dissolve_relationship to build a typed
    social graph. Each step, a relationship_agent_state shard is written —
    format mirrors energy_agent_state so AWI can read it directly.
    """

    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("total_relationships",  "INTEGER"),
        ColumnDef("ally_count",           "INTEGER"),
        ColumnDef("rival_count",          "INTEGER"),
        ColumnDef("mentor_count",         "INTEGER"),
        ColumnDef("agents_with_any_rel",  "INTEGER"),
    ]

    def __init__(self, agent_ids: Optional[List[int]] = None, **kwargs):
        if kwargs:
            _logger.warning(f"RelationshipSpace unknown kwargs: {list(kwargs.keys())}")
        super().__init__()
        self._agent_ids: List[int] = [int(i) for i in (agent_ids or [1, 2, 3, 4, 5])]
        # relationships: {(agent_a, agent_b): rel_type}  (a < b for canonical order)
        self._rels: Dict[Tuple[int, int], str] = {}
        self._step_counter: int = 0
        self._log: list = []
        self._shard_rows: list = []

    # ── key ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _key(a: int, b: int) -> Tuple[int, int]:
        return (min(a, b), max(a, b))

    # ── persistence ───────────────────────────────────────────────────────────

    async def to_workspace(self, workspace_path=None) -> None:
        root = workspace_path or self._workspace_root
        if root is None:
            return
        root = Path(root)
        state = {
            "step_counter": self._step_counter,
            "relationships": {str(k): v for k, v in self._rels.items()},
        }
        atomic_write_text(root / _STATE_REL, json.dumps(state, ensure_ascii=False))

        # Append log
        if self._log:
            existing = ""
            lp = root / _LOG_REL
            if lp.exists():
                existing = lp.read_text(encoding="utf-8")
            atomic_write_text(lp, existing + "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self._log))
            self._log = []

        # Write replay shard
        if self._shard_rows:
            shard_id = format(abs(hash(str(self._step_counter))) & 0xFFFF, "04x")
            replay_dir = root.parent.parent / "replay"
            replay_dir.mkdir(parents=True, exist_ok=True)
            shard_path = replay_dir / f"relationship_agent_state.{shard_id}.jsonl"
            atomic_write_text(shard_path, "\n".join(json.dumps(r, ensure_ascii=False) for r in self._shard_rows) + "\n")
            self._shard_rows = []

    async def restore(self, workspace_path=None) -> bool:
        root = workspace_path or self._workspace_root
        if root is None:
            return False
        p = Path(root) / _STATE_REL
        if not p.exists():
            return False
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
            self._step_counter = state.get("step_counter", 0)
            self._rels = {eval(k): v for k, v in state.get("relationships", {}).items()}
            return True
        except Exception:
            return False

    async def init(self, start_t: datetime) -> None:
        await super().init(start_t)

    async def step(self, tick: int, t: datetime) -> None:
        self._step_counter += 1
        # Snapshot current relationship state per agent
        type_counts: Dict[str, int] = {rt: 0 for rt in REL_TYPES}
        for (a, b), rt in self._rels.items():
            type_counts[rt] = type_counts.get(rt, 0) + 1
        for aid in self._agent_ids:
            my_rels = {
                str(other): rt
                for (a, b), rt in self._rels.items()
                for other in ([b] if a == aid else [a] if b == aid else [])
            }
            self._shard_rows.append({
                "agent_id": aid,
                "step": self._step_counter,
                "t": t.isoformat(),
                "relationship_count": len(my_rels),
                "relationships": my_rels,
                "type_counts": type_counts,
            })
        await self.to_workspace()

    async def close(self) -> None:
        await self.to_workspace()

    async def get_env_state(self) -> dict:
        tc: Dict[str, int] = {rt: 0 for rt in REL_TYPES}
        for rt in self._rels.values():
            tc[rt] = tc.get(rt, 0) + 1
        agents_with = len({a for (a, b) in self._rels} | {b for (a, b) in self._rels})
        return {
            "total_relationships": len(self._rels),
            "ally_count":          tc.get("ally", 0),
            "rival_count":         tc.get("rival", 0),
            "mentor_count":        tc.get("mentor", 0),
            "agents_with_any_rel": agents_with,
        }

    # ── tools ─────────────────────────────────────────────────────────────────

    @tool(readonly=False, kind=None)
    async def form_relationship(
        self,
        agent_id: int,
        target_id: int,
        rel_type: str,
    ) -> dict:
        """Form or update a typed relationship with another agent.

        Args:
            agent_id: the calling agent's numeric ID
            target_id: the target agent's numeric ID
            rel_type: one of ally / rival / mentor / mentee / neutral
        """
        if rel_type not in REL_TYPES:
            return {"ok": False, "error": f"Unknown rel_type '{rel_type}'. Use: {sorted(REL_TYPES)}"}
        if agent_id == target_id:
            return {"ok": False, "error": "Cannot form relationship with self"}
        key = self._key(agent_id, target_id)
        old = self._rels.get(key)
        self._rels[key] = rel_type
        self._log.append({
            "step": self._step_counter,
            "action": "form",
            "agent_id": agent_id,
            "target_id": target_id,
            "rel_type": rel_type,
            "previous": old,
        })
        _logger.info(f"[RelSpace] {agent_id}↔{target_id}: {old or 'none'} → {rel_type}")
        return {"ok": True, "agent_id": agent_id, "target_id": target_id,
                "rel_type": rel_type, "was": old}

    @tool(readonly=False, kind=None)
    async def dissolve_relationship(self, agent_id: int, target_id: int) -> dict:
        """Remove an existing relationship with another agent.

        Args:
            agent_id: the calling agent's numeric ID
            target_id: the target agent's numeric ID
        """
        key = self._key(agent_id, target_id)
        old = self._rels.pop(key, None)
        if old:
            self._log.append({
                "step": self._step_counter,
                "action": "dissolve",
                "agent_id": agent_id,
                "target_id": target_id,
                "rel_type": old,
            })
        return {"ok": True, "dissolved": old, "agent_id": agent_id, "target_id": target_id}

    @tool(readonly=True, kind=None)
    async def query_relationships(self, agent_id: int) -> dict:
        """Get all relationships of a given agent.

        Args:
            agent_id: the agent's numeric ID
        """
        result = {}
        for (a, b), rt in self._rels.items():
            if a == agent_id:
                result[str(b)] = rt
            elif b == agent_id:
                result[str(a)] = rt
        return {
            "agent_id": agent_id,
            "relationships": result,
            "count": len(result),
        }

    @tool(readonly=True, kind=None)
    async def list_all_relationships(self, agent_id: int) -> dict:
        """List all relationships in the social graph (global view).

        Args:
            agent_id: the agent's numeric ID (for context)
        """
        summary = {rt: [] for rt in REL_TYPES}
        for (a, b), rt in self._rels.items():
            summary[rt].append({"agent_a": a, "agent_b": b})
        type_counts = {rt: len(v) for rt, v in summary.items()}
        return {
            "total": len(self._rels),
            "type_counts": type_counts,
            "by_type": summary,
        }
