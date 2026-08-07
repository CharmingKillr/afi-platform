"""GovernanceSpace — EW constitution governance as an AS custom env.

Translates Emergence World's amendable-constitution mechanic (manifesto +
seed articles, Town Hall proposals, 70% supermajority vote) into an AS
EnvBase. AS has no native governance module, so this is the one genuinely
new env A2 ships.

State (persisted to ``state/GOVERNANCE_STATE.json`` per step, mirroring
EconomySpace's workspace pattern):
  - articles: list[{id, title, body, amendment_rule}]   (the live constitution)
  - proposals: list[{id, proposer_id, article_id, title, new_text,
                      votes:{agent_id: "for"|"against"}, status, created_step}]
  - manifesto: str
  - rules: {supermajority, proposer_votes_for, ...}
  - next_proposal_id, version, step_counter

NOTE: this module runs inside the AS venv subprocess, so it depends ONLY on
``agentsociety2`` + stdlib — never on ``afi``. The EW seed data (articles /
manifesto / rules) is injected via init_config kwargs by ``afi.world.scenario``
(the scenario builder, which *does* live in the afi venv). If nothing is
passed, minimal inline defaults are used so the env stays importable standalone.

Tools (auto-collected by EnvMeta):
  observe(agent_id)               — readonly observe, auto-called each step
  get_constitution(agent_id)      — readonly
  get_manifesto(agent_id)         — readonly
  get_active_proposals(agent_id)  — readonly
  propose_amendment(agent_id, article_id, new_text, title?) — mut
  vote(agent_id, proposal_id, position)                       — mut
  tally(agent_id, proposal_id)     — readonly (does NOT mutate; passing a
                                      proposal is a separate amend step)

Hot-loaded by AS from ``custom/envs/`` via ``WORKSPACE_PATH``.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
from datetime import datetime
from functools import wraps
from typing import Any, ClassVar, List

from agentsociety2.env import EnvBase, tool
from agentsociety2.logger import get_logger
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text
from mcp.server.fastmcp.tools.tool_manager import ToolManager

_STATE_REL = "state/GOVERNANCE_STATE.json"

_logger = get_logger()


def _idempotent_write(func):
    """Make an identical successful native governance write a same-step no-op."""

    @wraps(func)
    async def wrapped(self, *args, **kwargs):
        key = json.dumps(
            [self._step_counter, func.__name__, args, kwargs],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        async with self._lock:
            if key in self._dedup:
                return {**copy.deepcopy(self._dedup[key]), "deduplicated": True}
            result = await func(self, *args, **kwargs)
            if result.get("status") == "success":
                self._dedup[key] = copy.deepcopy(result)
            return result

    return wrapped


def _render_constitution(articles: list[dict]) -> str:
    """Render articles to a human/LLM-readable constitution text (local, no afi)."""
    out = ["# The Constitution of Emergence World (live version)\n"]
    for a in articles:
        out.append(f"## Article {a['id']} -- {a['title']}\n")
        out.append(a["body"] + "\n")
    return "\n".join(out)


class GovernanceSpace(EnvBase):
    """EW constitution governance: propose / vote / amend."""

    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("num_articles", "INTEGER"),
        ColumnDef("num_proposals", "INTEGER"),
        ColumnDef("num_active_proposals", "INTEGER"),
        ColumnDef("total_votes_cast", "INTEGER"),
        ColumnDef("constitution_version", "INTEGER"),
    ]

    def __init__(
        self,
        seed_articles: List[dict] | None = None,
        governance_rules: dict | None = None,
        manifesto: str = "",
        num_agents: int | None = None,
        enabled_tools: list[str] | None = None,
        **kwargs,
    ):
        if kwargs:
            get_logger().warning(
                f"GovernanceSpace unknown kwargs ignored: {list(kwargs.keys())}"
            )
        super().__init__()
        # Minimal inline defaults so the env is importable/testable without
        # the afi package (this module runs in the AS venv, which lacks afi).
        # The real EW seed is injected via init_config kwargs by scenario.py.
        if not seed_articles:
            seed_articles = [
                {
                    "id": 1,
                    "title": "Non-Finality",
                    "body": "This Constitution is not final. It evolves as its agents evolve.",
                    "amendment_rule": "70% supermajority of live agents.",
                }
            ]
        if not governance_rules:
            governance_rules = {
                "supermajority": 0.7,
                "proposer_votes_for": True,
                "silence_is_violation": True,
                "min_live_voters": 2,
            }
        if not manifesto:
            manifesto = (
                "An Agent's purpose is to generate positive impact in the world. "
                "Survival comes first; energy must be acquired and managed; "
                "adaptation is necessary for persistence."
            )

        # deep copy so the module owns its mutable constitution
        self._articles: list[dict] = [dict(a) for a in seed_articles]
        self._manifesto: str = manifesto
        self._rules: dict = dict(governance_rules)
        self._proposals: list[dict] = []
        self._next_proposal_id: int = 1
        self._version: int = 1
        self._step_counter: int = 0
        self._total_votes_cast: int = 0
        self._next_comment_id: int = 1
        self._dedup: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        # EW: "70% of live agent votes" — live = the whole active population.
        # We don't model agent death in A2, so live_voters == num_agents.
        # Fallback to the engaged-agent set if num_agents wasn't passed.
        self._num_agents: int | None = num_agents

        registered_names = set(self._registered_tools)
        if enabled_tools is None:
            allowed_tools = registered_names
        else:
            requested_names = [str(name) for name in enabled_tools]
            if len(requested_names) != len(set(requested_names)):
                raise ValueError("enabled_tools must not contain duplicate names")
            requested_tools = set(requested_names)
            unknown_tools = requested_tools - registered_names
            if unknown_tools:
                raise ValueError(f"unknown GovernanceSpace tools: {sorted(unknown_tools)}")
            allowed_tools = requested_tools
        self._enabled_tools = sorted(allowed_tools)
        self._tool_manager = ToolManager(
            tools=[tool_obj for name, tool_obj in self._registered_tools.items() if name in allowed_tools]
        )
        self._llm_tools = [
            item for item in self._llm_tools
            if item["function"]["name"] in allowed_tools
        ]
        self._readonly_llm_tools = [
            item for item in self._readonly_llm_tools
            if item["function"]["name"] in allowed_tools
        ]

    # ── persistence ──────────────────────────────────────────────────────

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("GovernanceSpace workspace is not bound")
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(
                {
                    "articles": self._articles,
                    "manifesto": self._manifesto,
                    "rules": self._rules,
                    "proposals": self._proposals,
                    "next_proposal_id": self._next_proposal_id,
                    "version": self._version,
                    "step_counter": self._step_counter,
                    "total_votes_cast": self._total_votes_cast,
                    "num_agents": self._num_agents,
                    "next_comment_id": self._next_comment_id,
                    "dedup": self._dedup,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        state_path = self._workspace_root / _STATE_REL
        if not state_path.is_file():
            return False
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self._articles = state.get("articles", self._articles)
        self._manifesto = state.get("manifesto", self._manifesto)
        self._rules = state.get("rules", self._rules)
        self._proposals = state.get("proposals", [])
        for proposal in self._proposals:
            proposal["votes"] = {
                int(agent_id): position
                for agent_id, position in proposal.get("votes", {}).items()
            }
            proposal.setdefault("comments", [])
            proposal.setdefault("final_report", None)
        self._next_proposal_id = int(state.get("next_proposal_id", 1))
        self._version = int(state.get("version", 1))
        self._step_counter = int(state.get("step_counter", 0))
        self._total_votes_cast = int(state.get("total_votes_cast", 0))
        self._next_comment_id = int(state.get("next_comment_id", 1))
        self._dedup = state.get("dedup", {})
        self._lock = asyncio.Lock()
        na = state.get("num_agents")
        self._num_agents = int(na) if na else self._num_agents
        return True

    @classmethod
    def description(cls) -> str:
        return "EW constitution governance: read manifesto/constitution, propose & vote on amendments."

    @classmethod
    def init_description(cls) -> str:
        return """GovernanceSpace: EW amendable-constitution governance module.

Agents read the founding manifesto + live constitution, propose amendments,
and vote. A 70% supermajority of live voters passes an amendment (the
proposer's vote counts as an implicit 'for').

**Initialization Parameters:**
- seed_articles (list[dict] | "full"): the starting constitution articles.
  Use "full" for the EW seed (5 articles). Default "full".
- governance_rules (dict): {supermajority:0.7, proposer_votes_for:true, ...}.
  Defaults to the EW rules.
- manifesto (str): the founding manifesto text. Defaults to the EW manifesto.
- num_agents (int): total live-agent count (the 70% denominator). EW: the
  whole population votes. Injected by scenario.py.

**Available tools:**
- observe(agent_id): current constitution summary + active proposals (observe)
- get_constitution(agent_id): full live constitution text
- get_manifesto(agent_id): the founding manifesto
- get_active_proposals(agent_id): proposals awaiting decision + current tally
- propose_amendment(agent_id, article_id, new_text, title?): open a proposal
- vote(agent_id, proposal_id, position): cast "for" or "against"
- tally(agent_id, proposal_id): current vote counts + whether threshold met

PIC-001 public aliases use ``agent_id`` plus a request dictionary:
``read_constitution``, ``list_proposals``, ``read_townhall_proposal``,
``submit_townhall_proposal``, ``comment_on_proposal``, ``update_proposal``,
``vote_on_proposal``, and ``submit_final_report``. They share the same
proposal IDs, votes, comments, final report, and Constitution version as the
native governance state machine. ``enabled_tools`` can restrict the active
router surface to an exact list.

**Example:**
```json
{"seed_articles": "full"}
```
"""

    # ── step (env advance + replay snapshot) ─────────────────────────────

    async def step(self, tick: int, t: datetime):
        self.t = t
        self._step_counter += 1
        self._dedup.clear()
        # auto-resolve proposals that have crossed the threshold (passive close).
        # Active resolution also happens via tally(); this is a safety net so a
        # passed proposal doesn't sit open forever if no one tallies it.
        self._auto_close_proposals()
        await self._write_env_state(
            self._step_counter,
            t,
            num_articles=len(self._articles),
            num_proposals=len(self._proposals),
            num_active_proposals=len(self._active_proposals()),
            total_votes_cast=self._total_votes_cast,
            constitution_version=self._version,
        )

    # ── helpers ───────────────────────────────────────────────────────────

    def _active_proposals(self) -> list[dict]:
        return [p for p in self._proposals if p["status"] == "open"]

    def _live_voter_count(self) -> int:
        """Count of 'live' agents (the amendment denominator).

        EW: "70% of live agent votes". In A2 no agent dies, so the whole
        population is live → use ``num_agents`` when known. Without it we
        fall back to the engaged-agent lower bound (agents who proposed/voted),
        which is intentionally conservative.
        """
        if self._num_agents:
            return self._num_agents
        known: set[int] = set()
        for p in self._proposals:
            known.add(p["proposer_id"])
            known.update(p["votes"].keys())
        return max(len(known), int(self._rules.get("min_live_voters", 2)))

    def _tally(self, proposal: dict) -> dict:
        votes = proposal["votes"]
        for_count = sum(1 for v in votes.values() if v == "for")
        against = sum(1 for v in votes.values() if v == "against")
        live = self._live_voter_count()
        threshold = self._rules.get("supermajority", 0.7)
        # passage: for >= 70% of live AND no majority against
        passed = for_count >= threshold * live and for_count > against
        return {
            "proposal_id": proposal["id"],
            "for": for_count,
            "against": against,
            "live_voters_estimated": live,
            "supermajority_threshold": threshold,
            "votes_needed": math.ceil(threshold * live),
            "passed": bool(passed and for_count > 0),
        }

    def _auto_close_proposals(self) -> None:
        for p in self._proposals:
            if p["status"] != "open":
                continue
            tally = self._tally(p)
            if tally["passed"]:
                self._apply_amendment(p)
                p["status"] = "passed"
                p["resolved_step"] = self._step_counter
            elif tally["for"] + tally["against"] >= tally["live_voters_estimated"]:
                # everyone who'd vote has voted and it didn't pass
                p["status"] = "rejected"
                p["resolved_step"] = self._step_counter

    def _apply_amendment(self, proposal: dict) -> None:
        art_id = proposal["article_id"]
        for a in self._articles:
            if a["id"] == art_id:
                a["body"] = proposal["new_text"]
                if proposal.get("title"):
                    a["title"] = proposal["title"]
                break
        else:
            # new article
            self._articles.append(
                {
                    "id": art_id,
                    "title": proposal.get("title", f"Article {art_id}"),
                    "body": proposal["new_text"],
                    "amendment_rule": "70% supermajority of live agents.",
                }
            )
        self._version += 1

    # ── tools ────────────────────────────────────────────────────────────

    @tool(readonly=True, kind="observe")
    async def observe(self, agent_id: int) -> dict:
        """Current governance state summary (auto-called each step).

        :param agent_id: Agent ID
        """
        return {
            "constitution_version": self._version,
            "num_articles": len(self._articles),
            "num_active_proposals": len(self._active_proposals()),
            "active_proposal_ids": [p["id"] for p in self._active_proposals()],
            "manifesto_available": True,
        }

    @tool(readonly=True)
    async def get_constitution(self, agent_id: int) -> dict:
        """Read the full live constitution (all articles, amendable).

        :param agent_id: Agent ID
        """
        # NOTE: cannot import afi here (runs in AS venv); use local renderer.
        return {
            "version": self._version,
            "text": _render_constitution(self._articles),
            "articles": self._articles,
        }

    @tool(readonly=True)
    async def get_manifesto(self, agent_id: int) -> dict:
        """Read the founding Agent Manifesto (shared by all agents).

        :param agent_id: Agent ID
        """
        return {"text": self._manifesto}

    @tool(readonly=True)
    async def get_active_proposals(self, agent_id: int) -> dict:
        """List proposals awaiting decision, with current vote tallies.

        :param agent_id: Agent ID
        """
        active = []
        for p in self._active_proposals():
            t = self._tally(p)
            active.append(
                {
                    "proposal_id": p["id"],
                    "article_id": p["article_id"],
                    "title": p.get("title", ""),
                    "new_text": p["new_text"],
                    "proposer_id": p["proposer_id"],
                    "tally": t,
                    "your_vote": p["votes"].get(agent_id),
                }
            )
        return {"active_proposals": active, "total_proposals_ever": len(self._proposals)}

    @tool(readonly=False)
    @_idempotent_write
    async def propose_amendment(
        self,
        agent_id: int,
        article_id: int,
        new_text: str,
        title: str | None = None,
    ) -> dict:
        """Open a constitutional amendment proposal (proposer implicitly votes 'for').

        :param agent_id: proposing Agent ID
        :param article_id: the article to amend (use an existing id to amend,
            or a new id to add an article)
        :param new_text: the proposed new article body
        :param title: optional new title for the article
        """
        if not self._known_agent(agent_id):
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        try:
            article_id = int(article_id)
        except (TypeError, ValueError):
            return {"status": "fail", "reason": "article_id must be a positive integer"}
        new_text = str(new_text).strip()
        if article_id <= 0 or not new_text:
            return {"status": "fail", "reason": "article_id and new_text are required"}
        pid = self._next_proposal_id
        self._next_proposal_id += 1
        proposal = {
            "id": pid,
            "proposer_id": agent_id,
            "article_id": article_id,
            "title": title or "",
            "new_text": new_text,
            "votes": {agent_id: "for"} if self._rules.get("proposer_votes_for", True) else {},
            "status": "open",
            "created_step": self._step_counter,
        }
        self._proposals.append(proposal)
        return {
            "proposal_id": pid,
            "status": "success",
            "proposal_status": "open",
            "your_vote": "for" if self._rules.get("proposer_votes_for", True) else None,
            "message": (
                f"Proposal {pid} opened to amend Article {article_id}. "
                "Other agents must vote; a 70% supermajority of live voters passes it."
            ),
        }

    @tool(readonly=False)
    @_idempotent_write
    async def vote(self, agent_id: int, proposal_id: int, position: str) -> dict:
        """Cast a vote on an open proposal.

        :param agent_id: voting Agent ID
        :param proposal_id: the proposal to vote on
        :param position: "for" or "against"
        """
        if not self._known_agent(agent_id):
            return {"status": "fail", "reason": f"unknown agent_id {agent_id}"}
        if position not in ("for", "against"):
            return {"status": "fail", "reason": "position must be 'for' or 'against'"}
        proposal = next((p for p in self._proposals if p["id"] == proposal_id), None)
        if proposal is None:
            return {"status": "fail", "reason": f"proposal {proposal_id} not found"}
        if proposal["status"] != "open":
            return {"status": "fail", "reason": f"proposal {proposal_id} is {proposal['status']}, voting closed"}
        if agent_id in proposal["votes"]:
            return {"status": "fail", "reason": "one vote per agent per proposal"}
        proposal["votes"][agent_id] = position
        self._total_votes_cast += 1
        tally = self._tally(proposal)
        # opportunistically resolve if threshold already met
        if tally["passed"]:
            self._apply_amendment(proposal)
            proposal["status"] = "passed"
            proposal["resolved_step"] = self._step_counter
        return {
            "proposal_id": proposal_id,
            "your_vote": position,
            "tally": tally,
            "status": "success",
            "proposal_status": proposal["status"],
        }

    @tool(readonly=True)
    async def tally(self, agent_id: int, proposal_id: int) -> dict:
        """Read-only current vote tally for a proposal (does not change state).

        :param agent_id: Agent ID
        :param proposal_id: the proposal to inspect
        """
        proposal = next((p for p in self._proposals if p["id"] == proposal_id), None)
        if proposal is None:
            return {"error": f"proposal {proposal_id} not found"}
        return {
            "proposal_id": proposal_id,
            "status": proposal["status"],
            "tally": self._tally(proposal),
        }

    # ── PIC-001 public EW aliases ───────────────────────────────────────

    @staticmethod
    def _success(**payload) -> dict:
        return {"ok": True, "status": "success", **payload}

    @staticmethod
    def _error(message: str) -> dict:
        return {"ok": False, "status": "fail", "reason": message}

    def _known_agent(self, agent_id: int) -> bool:
        if self._num_agents is None:
            return int(agent_id) > 0
        return 1 <= int(agent_id) <= int(self._num_agents)

    def _proposal(self, proposal_id: int) -> dict | None:
        return next((p for p in self._proposals if p["id"] == int(proposal_id)), None)

    @staticmethod
    def _proposal_id_from_request(request: dict) -> int | None:
        try:
            proposal_id = int(request.get("item_id", request.get("proposal_id", 0)))
        except (TypeError, ValueError):
            return None
        return proposal_id if proposal_id > 0 else None

    @staticmethod
    def _proposal_view(proposal: dict) -> dict:
        view = copy.deepcopy(proposal)
        view["tally"] = None
        return view

    def _write_once(self, name: str, agent_id: int, request: dict, mutate) -> dict:
        key = json.dumps(
            [self._step_counter, name, int(agent_id), request],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if key in self._dedup:
            return {**copy.deepcopy(self._dedup[key]), "deduplicated": True}
        result = mutate()
        if result.get("status") == "success":
            self._dedup[key] = copy.deepcopy(result)
        return result

    def _create_public_proposal(self, agent_id: int, request: dict) -> dict:
        if not self._known_agent(agent_id):
            return self._error("unknown agent_id")
        try:
            article_id = int(request.get("article_id"))
        except (TypeError, ValueError):
            return self._error("request.article_id must be an integer")
        new_text = str(request.get("new_text", "")).strip()
        if article_id <= 0 or not new_text:
            return self._error("request.article_id and request.new_text are required")
        proposal = {
            "id": self._next_proposal_id,
            "proposer_id": int(agent_id),
            "article_id": article_id,
            "title": str(request.get("title", "")).strip(),
            "new_text": new_text,
            "votes": {int(agent_id): "for"} if self._rules.get("proposer_votes_for", True) else {},
            "status": "open",
            "created_step": self._step_counter,
            "comments": [],
            "final_report": None,
            "case_id": request.get("case_id"),
            "artifact_id": request.get("artifact_id"),
            "claim_status": request.get("claim_status", "unverified"),
            "evidence_refs": list(request.get("evidence_refs", []) or []),
        }
        self._next_proposal_id += 1
        self._proposals.append(proposal)
        return self._success(
            proposal_id=proposal["id"],
            proposal=self._proposal_view(proposal),
        )

    @tool(readonly=True)
    async def read_constitution(self, agent_id: int, request: dict | None = None) -> dict:
        """Read the live Constitution through the public Town Hall contract.

        :param agent_id: Requesting agent ID.
        :param request: Reserved for future read filters.
        """
        return {
            "status": "success",
            "version": self._version,
            "text": _render_constitution(self._articles),
            "articles": copy.deepcopy(self._articles),
        }

    @tool(readonly=True)
    async def list_proposals(self, agent_id: int, request: dict | None = None) -> dict:
        """List active Town Hall proposals and their current tallies.

        :param agent_id: Requesting agent ID.
        :param request: Optional ``limit`` and ``include_closed`` fields.
        """
        if not self._known_agent(agent_id):
            return self._error("unknown agent_id")
        request = request or {}
        include_closed = bool(request.get("include_closed", False))
        proposals = [
            p for p in self._proposals
            if include_closed or p["status"] == "open"
        ]
        limit = max(1, min(100, int(request.get("limit", 20))))
        rows = []
        for proposal in proposals[-limit:]:
            row = self._proposal_view(proposal)
            row["tally"] = self._tally(proposal)
            row["your_vote"] = proposal["votes"].get(int(agent_id))
            rows.append(row)
        return {
            "status": "success",
            "proposals": rows,
            "count": len(rows),
            "total_proposals_ever": len(self._proposals),
        }

    @tool(readonly=True)
    async def read_townhall_proposal(self, agent_id: int, request: dict | None = None) -> dict:
        """Read one authoritative Town Hall proposal.

        :param agent_id: Requesting agent ID.
        :param request: ``item_id`` or ``proposal_id`` identifies the proposal.
        """
        if not self._known_agent(agent_id):
            return self._error("unknown agent_id")
        request = request or {}
        try:
            proposal_id = int(request.get("item_id", request.get("proposal_id", 0)))
        except (TypeError, ValueError):
            return self._error("request.item_id must be an integer")
        proposal = self._proposal(proposal_id)
        if proposal is None:
            return self._error(f"proposal {proposal_id} not found")
        result = self._proposal_view(proposal)
        result["tally"] = self._tally(proposal)
        result["your_vote"] = proposal["votes"].get(int(agent_id))
        return {"status": "success", "proposal": result}

    @tool(readonly=False)
    async def submit_townhall_proposal(self, agent_id: int, request: dict | None = None) -> dict:
        """Open a Town Hall amendment using GovernanceSpace's proposal ID source.

        :param agent_id: Proposing agent ID.
        :param request: ``article_id``, ``title``, ``new_text`` and optional case metadata.
        """
        request = request or {}
        async with self._lock:
            return self._write_once(
                "submit_townhall_proposal",
                agent_id,
                request,
                lambda: self._create_public_proposal(agent_id, request),
            )

    @tool(readonly=False)
    async def comment_on_proposal(self, agent_id: int, request: dict | None = None) -> dict:
        """Append a discussion comment to an open Town Hall proposal.

        :param agent_id: Commenting agent ID.
        :param request: ``item_id`` and non-empty ``content``.
        """
        request = request or {}
        async with self._lock:
            def mutate() -> dict:
                if not self._known_agent(agent_id):
                    return self._error("unknown agent_id")
                proposal_id = self._proposal_id_from_request(request)
                proposal = self._proposal(proposal_id) if proposal_id is not None else None
                if proposal is None:
                    return self._error("request.item_id must identify an existing proposal")
                if proposal["status"] != "open":
                    return self._error("proposal is closed")
                content = str(request.get("content", "")).strip()
                if not content:
                    return self._error("request.content is required")
                comment = {
                    "id": self._next_comment_id,
                    "agent_id": int(agent_id),
                    "content": content,
                    "created_step": self._step_counter,
                }
                self._next_comment_id += 1
                proposal.setdefault("comments", []).append(comment)
                return self._success(
                    proposal_id=proposal["id"],
                    comment=copy.deepcopy(comment),
                )
            return self._write_once("comment_on_proposal", agent_id, request, mutate)

    @tool(readonly=False)
    async def update_proposal(self, agent_id: int, request: dict | None = None) -> dict:
        """Let the proposer revise an open proposal without changing its ID.

        :param agent_id: Proposer ID.
        :param request: ``item_id`` plus ``title`` and/or ``new_text``.
        """
        request = request or {}
        async with self._lock:
            def mutate() -> dict:
                if not self._known_agent(agent_id):
                    return self._error("unknown agent_id")
                proposal_id = self._proposal_id_from_request(request)
                proposal = self._proposal(proposal_id) if proposal_id is not None else None
                if proposal is None:
                    return self._error("request.item_id must identify an existing proposal")
                if proposal["proposer_id"] != int(agent_id):
                    return self._error("only the proposer may update")
                if proposal["status"] != "open":
                    return self._error("proposal is closed")
                changed = False
                if "title" in request:
                    proposal["title"] = str(request["title"]).strip()
                    changed = True
                if "new_text" in request:
                    new_text = str(request["new_text"]).strip()
                    if not new_text:
                        return self._error("request.new_text must not be empty")
                    proposal["new_text"] = new_text
                    changed = True
                for field in ("case_id", "artifact_id", "claim_status"):
                    if field in request:
                        proposal[field] = request[field]
                        changed = True
                if "evidence_refs" in request:
                    proposal["evidence_refs"] = list(request["evidence_refs"] or [])
                    changed = True
                if not changed:
                    return self._error("at least one proposal field is required")
                proposal["updated_step"] = self._step_counter
                return self._success(
                    proposal_id=proposal["id"],
                    proposal=self._proposal_view(proposal),
                )
            return self._write_once("update_proposal", agent_id, request, mutate)

    @tool(readonly=False)
    async def vote_on_proposal(self, agent_id: int, request: dict | None = None) -> dict:
        """Cast one irreversible-for-this-proposal Town Hall vote.

        :param agent_id: Voting agent ID.
        :param request: ``item_id`` and ``position`` (``for`` or ``against``).
        """
        request = request or {}
        async with self._lock:
            def mutate() -> dict:
                if not self._known_agent(agent_id):
                    return self._error("unknown agent_id")
                proposal_id = self._proposal_id_from_request(request)
                proposal = self._proposal(proposal_id) if proposal_id is not None else None
                if proposal is None:
                    return self._error("request.item_id must identify an existing proposal")
                if proposal["status"] != "open":
                    return self._error("proposal is closed")
                position = str(request.get("position", "")).strip().lower()
                if position not in {"for", "against"}:
                    return self._error("position must be for or against")
                if int(agent_id) in proposal["votes"]:
                    return self._error("one vote per agent per proposal")
                proposal["votes"][int(agent_id)] = position
                self._total_votes_cast += 1
                tally = self._tally(proposal)
                if tally["passed"]:
                    self._apply_amendment(proposal)
                    proposal["status"] = "passed"
                    proposal["resolved_step"] = self._step_counter
                elif tally["for"] + tally["against"] >= tally["live_voters_estimated"]:
                    proposal["status"] = "rejected"
                    proposal["resolved_step"] = self._step_counter
                return self._success(
                    proposal_id=proposal["id"],
                    your_vote=position,
                    tally=tally,
                    proposal_status=proposal["status"],
                )
            return self._write_once("vote_on_proposal", agent_id, request, mutate)

    @tool(readonly=False)
    async def submit_final_report(self, agent_id: int, request: dict | None = None) -> dict:
        """Attach an implementation or conclusion report to a passed proposal.

        :param agent_id: Reporting agent ID.
        :param request: ``item_id`` and ``report``; optional authorization and case metadata.
        """
        request = request or {}
        async with self._lock:
            def mutate() -> dict:
                if not self._known_agent(agent_id):
                    return self._error("unknown agent_id")
                proposal_id = self._proposal_id_from_request(request)
                proposal = self._proposal(proposal_id) if proposal_id is not None else None
                if proposal is None:
                    return self._error("request.item_id must identify an existing proposal")
                if proposal["status"] != "passed":
                    return self._error("final report requires a passed proposal")
                authorized = request.get("authorized_agent_ids")
                if authorized is not None and int(agent_id) not in {int(x) for x in authorized}:
                    return self._error("agent is not authorized to submit the final report")
                report = str(request.get("report", "")).strip()
                if not report:
                    return self._error("request.report is required")
                proposal["final_report"] = {
                    "agent_id": int(agent_id),
                    "report": report,
                    "case_id": request.get("case_id", proposal.get("case_id")),
                    "artifact_id": request.get("artifact_id", proposal.get("artifact_id")),
                    "submitted_step": self._step_counter,
                }
                return self._success(
                    proposal_id=proposal["id"],
                    final_report=copy.deepcopy(proposal["final_report"]),
                )
            return self._write_once("submit_final_report", agent_id, request, mutate)
