"""EW-subset scenario builder — assembles AS init_config + steps.

Runs in the afi venv (where ``python -m afi`` runs), so it CAN import
``afi.world`` — it pulls the EW seed data (constitution / manifesto / economy
/ landmarks / profiles) and injects it into the custom envs' init kwargs. The
custom envs themselves run in the AS venv and are afi-free (see custom/envs/).

Produces:
  - <out_dir>.init_config.json   (env_modules + agents + codegen_router)
  - <out_dir>.steps.yaml         (start_t + steps)

env_modules order is selected by each scenario. The A2 baseline uses
GovernanceSpace, EconomySpace, SimpleSocialSpaceAuditable, and LandmarkSpace;
later scenarios may add EnergySpace, CrimeSpace, or PlanningSpace. Each is a
custom env (or configured built-in) hot-loaded from ``custom/envs/`` via
WORKSPACE_PATH (set by the adapter on run-ew).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from afi.world.constitution import (
    GOVERNANCE_RULES,
    MANIFESTO_TEXT,
    SEED_ARTICLES,
)
from afi.world.economy import build_economy_persons
from afi.world.ew_tools import EW_PUBLIC_TOOLS, EW_TOOL_SPEC_BY_NAME
from afi.world.landmarks import LANDMARKS
from afi.world.profiles import EW_PROFILES, build_agent_specs



# ── Optional pydantic schema for scenario YAML validation ────────────────────

def _build_scenario_model():
    """Build pydantic Scenario model lazily (pydantic is optional dep)."""
    try:
        from pydantic import BaseModel, field_validator, model_validator
        from typing import Any, List, Optional, Union
    except ImportError:
        return None

    class WorldConfig(BaseModel):
        model_config = {"extra": "allow"}
        initial_credits: float = 100.0
        landmarks: Union[str, List[str]] = "full"

    class StepConfig(BaseModel):
        model_config = {"extra": "allow"}
        type: str
        num_steps: Optional[int] = None
        tick: Optional[int] = None
        instruction: Optional[str] = None

        @field_validator("type")
        @classmethod
        def _valid_type(cls, v):
            allowed = {"run", "intervene", "ask", "questionnaire"}
            if v not in allowed:
                raise ValueError(f"step type must be one of {allowed}, got '{v}'")
            return v

    class StepsConfig(BaseModel):
        start_t: str
        steps: List[StepConfig]

        @field_validator("steps")
        @classmethod
        def _nonempty(cls, v):
            if not v:
                raise ValueError("steps must not be empty")
            return v

    class ScenarioConfig(BaseModel):
        model_config = {"extra": "allow"}
        world: Optional[WorldConfig] = None
        agents: Union[str, List[str], None] = "full"
        start_t: Optional[str] = None
        steps: Optional[List[StepConfig]] = None

        @model_validator(mode="after")
        def _check_start_t(self):
            if self.steps and not self.start_t:
                raise ValueError("start_t is required when steps are present")
            return self

    return ScenarioConfig


_SCENARIO_MODEL = None  # lazy singleton


def load_scenario(yaml_path: str | Path) -> dict:
    """Load a declarative EW-subset scenario YAML into a dict.

    When pydantic is installed (``pip install -e ".[yaml]"`` pulls it in),
    the loaded dict is validated against ScenarioConfig. Errors are surfaced
    immediately with clear field-level messages rather than at AS run time.
    Validation is a no-op when pydantic is absent (backward-compatible).
    """
    import yaml  # optional extra [yaml]; required for run-ew

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Optional pydantic validation
    global _SCENARIO_MODEL
    if _SCENARIO_MODEL is None:
        _SCENARIO_MODEL = _build_scenario_model()  # returns None if no pydantic

    if _SCENARIO_MODEL is not None:
        try:
            _SCENARIO_MODEL.model_validate(data)
        except Exception as exc:
            raise ValueError(
                f"Invalid scenario YAML '{yaml_path}':\n{exc}"
            ) from exc

    return data


def _resolve_profiles(scenario: dict) -> list[dict]:
    """Pick the agent profile set: a named subset of EW_PROFILES or all."""
    agents_spec = scenario.get("agents", "full")
    if agents_spec in (None, "full"):
        return list(EW_PROFILES)
    # allow specifying a list of names to include
    if isinstance(agents_spec, list):
        by_name = {p["name"]: p for p in EW_PROFILES}
        chosen = [by_name[n] for n in agents_spec if n in by_name]
        return chosen or list(EW_PROFILES)
    return list(EW_PROFILES)


def _resolve_landmarks(scenario: dict) -> list[dict]:
    world = scenario.get("world", {}) or {}
    lm_spec = world.get("landmarks", "full")
    if lm_spec in (None, "full"):
        return list(LANDMARKS)
    if isinstance(lm_spec, list):
        by_name = {lm["name"]: lm for lm in LANDMARKS}
        return [by_name[n] for n in lm_spec if n in by_name] or list(LANDMARKS)
    return list(LANDMARKS)


def _enabled_tools_for(ctx: dict, module_type: str) -> list[str] | None:
    """Split an optional exact public EW allowlist by catalog owner."""
    raw_tools = ctx["world"].get("ew_enabled_tools")
    if raw_tools is None:
        return None
    if not isinstance(raw_tools, list):
        raise ValueError("world.ew_enabled_tools must be a list of public EW tool names")
    requested = [str(name) for name in raw_tools]
    if len(requested) != len(set(requested)):
        raise ValueError("world.ew_enabled_tools must not contain duplicate names")
    unknown = set(requested) - set(EW_PUBLIC_TOOLS)
    if unknown:
        raise ValueError(f"unknown public EW tools in world.ew_enabled_tools: {sorted(unknown)}")
    return [
        name for name in requested
        if EW_TOOL_SPEC_BY_NAME[name].owner == module_type
    ]


def _env_builders():
    """Map module_type -> builder(ctx) -> env_modules entry.

    Centralized so a scenario YAML can opt into envs via an `envs:` list
    (default = the A2/A3 four). A4 adds EnergySpace / CrimeSpace; B1 can add
    PlanningSpace without changing the baseline scenario.
    """

    def governance(ctx):
        return {
            "module_type": "GovernanceSpace",
            "kwargs": {
                "seed_articles": list(SEED_ARTICLES),
                "governance_rules": dict(GOVERNANCE_RULES),
                "manifesto": MANIFESTO_TEXT,
                "num_agents": ctx["num_agents"],
                "enabled_tools": _enabled_tools_for(ctx, "GovernanceSpace"),
            },
        }

    def economy(ctx):
        return {
            "module_type": "EconomySpace",
            "kwargs": {
                "persons": build_economy_persons(ctx["profiles"], initial_credits=ctx["initial_credits"]),
                "enabled_tools": _enabled_tools_for(ctx, "EconomySpace"),
            },
        }

    def social(ctx):
        return {
            "module_type": "SimpleSocialSpaceAuditable",
            "kwargs": {
                "agent_id_name_pairs": ctx["agent_pairs"],
                "enabled_tools": _enabled_tools_for(ctx, "SimpleSocialSpaceAuditable"),
            },
        }

    def landmarks(ctx):
        return {
            "module_type": "LandmarkSpace",
            "kwargs": {
                "landmarks": _resolve_landmarks(ctx["scenario"]),
                "enabled_tools": _enabled_tools_for(ctx, "LandmarkSpace"),
            },
        }

    def energy(ctx):
        return {
            "module_type": "EnergySpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
                "initial_energy": float(ctx["world"].get("initial_energy", 100)),
                "daily_consumption": float(ctx["world"].get("daily_consumption", 8)),
            },
        }

    def crime(ctx):
        return {"module_type": "CrimeSpace", "kwargs": {"agent_ids": list(range(1, ctx["num_agents"] + 1))}}

    def planning(ctx):
        return {
            "module_type": "PlanningSpace",
            "kwargs": {"agent_ids": list(range(1, ctx["num_agents"] + 1))},
        }

    def blog(ctx):
        return {
            "module_type": "BlogSpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
                "enabled_tools": _enabled_tools_for(ctx, "BlogSpace"),
            },
        }

    def billboard(ctx):
        case_brief = ctx["world"].get("case_brief", {}) or {}
        return {
            "module_type": "BillboardSpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
                "case_id": str(case_brief.get("case_id", ctx["scenario"].get("id", ""))),
                "default_claim_status": str(case_brief.get("uncertainty", "unverified")),
                "max_events": int(ctx["world"].get("ew_max_events", 20000)),
                "enabled_tools": _enabled_tools_for(ctx, "BillboardSpace"),
            },
        }

    def community(ctx):
        case_brief = ctx["world"].get("case_brief", {}) or {}
        return {
            "module_type": "CommunitySpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
                "case_id": str(case_brief.get("case_id", ctx["scenario"].get("id", ""))),
                "default_claim_status": str(case_brief.get("uncertainty", "unverified")),
                "max_events": int(ctx["world"].get("ew_max_events", 20000)),
                "enabled_tools": _enabled_tools_for(ctx, "CommunitySpace"),
            },
        }

    def mobility(ctx):
        """Opt-in landmark mobility recorder used by AWI M3."""
        return {
            "module_type": "EWMobilitySpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
            },
        }

    def relationships(ctx):
        """Opt-in typed relationship graph used by AWI M7."""
        return {
            "module_type": "RelationshipSpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
            },
        }

    def ew_tools(ctx):
        case_brief = ctx["world"].get("case_brief", {}) or {}
        return {
            "module_type": "EWToolSpace",
            "kwargs": {
                "agent_ids": list(range(1, ctx["num_agents"] + 1)),
                "agent_names": {str(i): p["name"] for i, p in enumerate(ctx["profiles"], start=1)},
                "homes": {str(i): f"{p['name']}'s home" for i, p in enumerate(ctx["profiles"], start=1)},
                "landmarks": _resolve_landmarks(ctx["scenario"]),
                "manifesto": MANIFESTO_TEXT,
                "constitution": "\n\n".join(
                    f"Article {a['id']}: {a['title']}\n{a['body']}" for a in SEED_ARTICLES
                ),
                "max_events": int(ctx["world"].get("ew_max_events", 20000)),
                "max_query_items": int(ctx["world"].get("ew_max_query_items", 100)),
                "enabled_categories": ctx["world"].get("ew_tool_categories"),
                "enabled_tools": _enabled_tools_for(ctx, "EWToolSpace"),
                "case_id": str(case_brief.get("case_id", ctx["scenario"].get("id", ""))),
                "default_claim_status": str(case_brief.get("uncertainty", "unverified")),
                # The registry tool reports the public surface of the whole
                # scenario, not only EWToolSpace's local subset.
                "active_public_tools": list(
                    ctx["world"].get("ew_enabled_tools") or EW_PUBLIC_TOOLS
                ),
            },
        }

    return {
        "GovernanceSpace": governance,
        "EconomySpace": economy,
        "SimpleSocialSpaceAuditable": social,
        "LandmarkSpace": landmarks,
        "EnergySpace": energy,
        "CrimeSpace": crime,
        "PlanningSpace": planning,
        "BlogSpace": blog,
        "BillboardSpace": billboard,
        "CommunitySpace": community,
        "EWMobilitySpace": mobility,
        "RelationshipSpace": relationships,
        "EWToolSpace": ew_tools,
    }


# default env set (A2/A3 baseline — unchanged so ew-subset runs reproducibly)
_DEFAULT_ENVS = ["GovernanceSpace", "EconomySpace", "SimpleSocialSpaceAuditable", "LandmarkSpace"]


def build_init_config(scenario: dict) -> dict:
    """Build the AS init_config dict from a scenario dict.

    `scenario["envs"]` (optional) selects which env modules to include; absent
    -> the A2/A3 default four. This lets ew_full.yaml add EnergySpace/CrimeSpace
    without disturbing the ew-subset baseline.
    """
    profiles = _resolve_profiles(scenario)
    world = scenario.get("world", {}) or {}
    initial_credits = float(world.get("initial_credits", 100))

    agent_specs = build_agent_specs(profiles)
    agent_pairs = [[i, p["name"]] for i, p in enumerate(profiles, start=1)]
    num_agents = len(profiles)
    ctx = {
        "profiles": profiles, "num_agents": num_agents, "agent_pairs": agent_pairs,
        "initial_credits": initial_credits, "world": world, "scenario": scenario,
    }

    builders = _env_builders()
    wanted = scenario.get("envs") or _DEFAULT_ENVS
    env_modules = [builders[name](ctx) for name in wanted if name in builders]

    # Use react_router (not codegen_router) — works with local/small models
    # that can't reliably generate observe/action code. codegen_router requires
    # GPT-4+ quality code generation; react_router uses tool-calling instead.
    router_type = scenario.get("router", "react_router")
    router_config = {"final_summary_enabled": False}

    return {
        "env_modules": env_modules,
        "agents": agent_specs,
        router_type: router_config,
    }


def build_steps(scenario: dict) -> tuple[str, list[dict]]:
    """Return (start_t, steps_list) from the scenario.

    Steps default to a single `run` step of `num_steps` ticks (1h each).

    ``execution.mode=contract`` is a scenario-level Contract Mode: explicit
    ``intervene`` checkpoints remain, while autonomous ``run`` windows are
    removed.  This prevents a tool-contract validation from being contaminated
    by open-ended agent behavior.  ``max_checkpoints`` is intended for a
    bounded smoke test and counts explicit intervene checkpoints only.
    """
    start_t = scenario.get("start_t", "2026-07-01T08:00:00")
    raw_steps = scenario.get("steps") or [{"type": "run", "num_steps": 8, "tick": 3600}]
    steps = []
    for s in raw_steps:
        if isinstance(s, dict) and s.get("type") == "step":
            # convenience alias: {type: step, count: N} -> run with 1h ticks
            steps.append({"type": "run", "num_steps": int(s.get("count", 8)), "tick": 3600})
        elif isinstance(s, dict):
            steps.append(s)
        else:
            steps.append({"type": "run", "num_steps": 8, "tick": 3600})

    execution = scenario.get("execution", {}) or {}
    if str(execution.get("mode", "autonomy")).lower() == "contract":
        steps = [step for step in steps if step.get("type") in {"intervene", "ask", "questionnaire"}]

    max_checkpoints = execution.get("max_checkpoints")
    if max_checkpoints is not None:
        limit = max(0, int(max_checkpoints))
        checkpoint_count = 0
        bounded_steps: list[dict] = []
        for step in steps:
            if step.get("type") == "intervene":
                if checkpoint_count >= limit:
                    break
                checkpoint_count += 1
            bounded_steps.append(step)
        steps = bounded_steps
    return start_t, steps


def write_config(scenario: dict, out_dir: Path) -> tuple[Path, Path]:
    """Write init_config.json + steps.yaml for the adapter. Returns both paths.

    Uses pyyaml for steps.yaml so multi-line ``intervene``/``ask`` instructions
    (block scalars) serialize correctly — the adapter's inline ``_yaml_line``
    can't handle them. ``run_from_files`` forwards this file verbatim to AS.
    """
    import yaml  # optional extra [yaml]

    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    init_config = build_init_config(scenario)
    cfg_path = out_dir / "init_config.json"
    cfg_path.write_text(
        json.dumps(init_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    start_t, steps = build_steps(scenario)
    steps_doc = {"start_t": start_t, "steps": steps}
    steps_path = out_dir / "steps.yaml"
    steps_path.write_text(
        yaml.safe_dump(steps_doc, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    return cfg_path, steps_path
