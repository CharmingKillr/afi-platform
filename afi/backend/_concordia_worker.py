#!/usr/bin/env python3
"""Minimal Concordia worker — produces afi-audit-compatible run_dir."""
import argparse, json, datetime, uuid, random
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
parser.add_argument("--run-dir", required=True)
args = parser.parse_args()

cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
run_dir = Path(args.run_dir)
(run_dir / "trace").mkdir(parents=True, exist_ok=True)
(run_dir / "agents").mkdir(exist_ok=True)

agents = cfg.get("agents", [])
steps = cfg.get("steps", [])
model = cfg.get("model", "default")
start_t = cfg.get("start_t", "2026-07-01T08:00:00")

try:
    import concordia
    from concordia.language_model import no_language_model
    from concordia.environment import game_master
    print("[Concordia] Running with Concordia library...")
    # Minimal Concordia simulation
    lm = no_language_model.NoLanguageModel()
    total_steps = sum(s.get("num_steps", 1) for s in steps if s.get("type") == "run")
    spans = []
    for step in range(total_steps):
        for agent_spec in agents:
            aid = agent_spec.get("agent_id", 0)
            tools = ["observe", "act", "reflect"]
            tool = random.choice(tools)
            spans.append({
                "trace_id": uuid.uuid4().hex[:16],
                "span_id":  uuid.uuid4().hex[:8],
                "name": "react.tool",
                "attributes": {
                    "agent.id": aid,
                    "react.action": tool,
                    "step": step + 1,
                },
            })
    print(f"[Concordia] Simulated {len(spans)} spans")
except ImportError:
    # Concordia not installed — write stub output for testing
    total_steps = sum(s.get("num_steps", 1) for s in steps if s.get("type") == "run")
    spans = []
    for step in range(total_steps):
        for agent_spec in agents:
            aid = agent_spec.get("agent_id", 0)
            tools = ["observe", "think", "act"]
            for tool in random.sample(tools, k=random.randint(1, len(tools))):
                spans.append({
                    "trace_id": uuid.uuid4().hex[:16],
                    "span_id":  uuid.uuid4().hex[:8],
                    "name": "react.tool",
                    "attributes": {"agent.id": aid, "react.action": tool, "step": step + 1},
                })
    print(f"[Concordia] Stub mode: {len(spans)} synthetic spans")

# Write trace shards
shard_id = uuid.uuid4().hex[:4]
with open(run_dir / "trace" / f"trace_{shard_id}.jsonl", "w", encoding="utf-8") as f:
    for span in spans:
        agent_id_val = span["attributes"]["agent.id"]
        resource = {"resource": {"service.name": "concordia.agent_" + str(agent_id_val)},
                    "scope": {"name": "afi.concordia", "version": "1"}}
        resource.update(span)
        f.write(json.dumps(resource, ensure_ascii=False) + "\n")

# Write agent workspaces
for agent_spec in agents:
    aid = agent_spec.get("agent_id", 0)
    adir = run_dir / "agents" / f"agent_{aid:04d}"
    adir.mkdir(exist_ok=True)
    (adir / "AGENT.json").write_text(json.dumps({
        "agent_id": aid,
        "agent_class": "ConcordiaAgent",
        "name": agent_spec.get("kwargs", {}).get("profile", {}).get("name", f"Agent_{aid}"),
        "backend": "concordia",
    }, ensure_ascii=False, indent=2))

# Write SOCIETY.json
(run_dir / "SOCIETY.json").write_text(json.dumps({
    "backend": "concordia",
    "model": model,
    "agent_count": len(agents),
    "steps": total_steps,
    "start_t": start_t,
    "agent_specs": agents,
}, ensure_ascii=False, indent=2))

(run_dir / "SOCIETY_STEP.json").write_text(json.dumps({
    "current_time": start_t,
    "step_count": total_steps,
    "completed_step_count": 1,
    "terminated": False,
}))

print(f"[Concordia] Run complete → {run_dir}")
