"""Causal Visualization — interactive HTML causal graph from Findings.

Connects the eval pipeline (detect_all → Findings) to the causal attribution
layer (causal.py → span tree + event graph) and renders an interactive HTML
visualization showing:

1. Finding → which agent/step triggered the alert
2. Causal chain: span parent tree leading to the anomaly
3. Timeline view: per-agent behavior + group metrics over time
4. Attribution: first-domino candidates (when applicable)

stdlib + json only (HTML is self-contained, no external JS deps).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from afi.audit.causal import _index, ancestors, failed_spans, explain_failure
from afi.audit.load import load_spans, agent_id
from afi.audit.group_behavior import (
    compute_group_behavior_timeline,
    GroupBehaviorSnapshot,
)


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class CausalChain:
    """A single causal explanation chain for a Finding."""
    finding_category: str
    finding_detail: str
    agent_id: Optional[int]
    detected_at_step: int
    severity: int
    # The causal chain (ancestor spans from the anomaly to root)
    chain: List[Dict]  # [{span_id, name, action, agent_id, summary}, ...]
    # Related failed spans in the same step/agent context
    related_failures: List[Dict]
    # First-domino attribution (if available)
    attribution: Optional[Dict] = None


# ── Core logic ────────────────────────────────────────────────────────────────


def build_causal_chains(run_dir: str | Path, findings: List) -> List[CausalChain]:
    """For each Finding, trace back through the span tree to build a causal chain.

    Args:
        run_dir: Completed AS2 run directory.
        findings: List of Finding objects from detect_all().

    Returns:
        List of CausalChain objects (one per finding that has traceable spans).
    """
    run_dir = Path(run_dir)
    try:
        spans = load_spans(run_dir)
    except FileNotFoundError:
        return []

    by_id = _index(spans)

    # Build step_round → agent.step mapping (same logic as group_behavior)
    step_spans = sorted(
        [s for s in spans if s.get("name") == "agent.step"],
        key=lambda s: s.get("start_time_unix_nano", 0),
    )
    agent_ids = set()
    for s in step_spans:
        aid = (s.get("resource") or {}).get("agent.id")
        if aid is not None:
            agent_ids.add(aid)
    n_agents = max(len(agent_ids), 1)

    # step_round → list of span_ids for that round
    round_spans: Dict[int, List[str]] = {}
    for i, s in enumerate(step_spans):
        step_round = (i // n_agents) + 1
        round_spans.setdefault(step_round, []).append(s.get("span_id", ""))

    # Tool spans indexed by agent
    tool_by_agent: Dict[int, List[dict]] = {}
    for s in spans:
        if s.get("name") != "react.tool":
            continue
        aid = (s.get("resource") or {}).get("agent.id")
        if aid is not None:
            tool_by_agent.setdefault(aid, []).append(s)

    # Failed spans for context
    failures = failed_spans(spans)

    chains: List[CausalChain] = []
    for finding in findings:
        f_agent = getattr(finding, "agent_id", None)
        f_step = getattr(finding, "detected_at_tick", 0)
        f_category = getattr(finding, "category", "")
        f_detail = getattr(finding, "detail", "")
        f_severity = getattr(finding, "severity", 0)

        # Find relevant spans for this finding
        relevant_spans = []
        if f_agent is not None and f_agent in tool_by_agent:
            relevant_spans = tool_by_agent[f_agent]
        elif tool_by_agent:
            # System-level finding: use all tool spans
            for agent_spans in tool_by_agent.values():
                relevant_spans.extend(agent_spans)

        # Build causal chain from the most relevant span
        chain_items = []
        if relevant_spans:
            # Pick the span closest to the finding's step
            target_span = relevant_spans[0]  # fallback: first span
            for s in relevant_spans:
                # Prefer spans with matching action patterns
                action = (s.get("attributes") or {}).get("react.action", "")
                if f_category == "tunnel_vision" and action == "observe":
                    target_span = s
                    break
                if f_category == "sensorium_collapse" and action in ("observe", "read"):
                    target_span = s
                    break

            # Walk ancestor chain
            ancestor_chain = ancestors(target_span, by_id)
            chain_items = [
                {
                    "span_id": s.get("span_id", "")[:12],
                    "name": s.get("name", ""),
                    "action": (s.get("attributes") or {}).get("react.action", ""),
                    "agent_id": (s.get("resource") or {}).get("agent.id"),
                    "summary": str((s.get("attributes") or {}).get("output.summary", ""))[:100],
                }
                for s in [target_span] + ancestor_chain
            ]

        # Related failures
        related = []
        for f in failures:
            f_aid = (f.get("resource") or {}).get("agent.id")
            if f_agent is None or f_aid == f_agent:
                related.append({
                    "span_id": f.get("span_id", "")[:12],
                    "action": (f.get("attributes") or {}).get("react.action", ""),
                    "agent_id": f_aid,
                    "summary": str((f.get("attributes") or {}).get("output.summary", ""))[:100],
                })

        chains.append(CausalChain(
            finding_category=f_category,
            finding_detail=f_detail,
            agent_id=f_agent,
            detected_at_step=f_step,
            severity=f_severity,
            chain=chain_items,
            related_failures=related[:5],  # limit
        ))

    return chains


# ── HTML Visualization ────────────────────────────────────────────────────────


def generate_causal_html(
    run_dir: str | Path,
    findings: List,
    output_path: str | Path,
):
    """Generate an interactive HTML causal attribution report.

    Args:
        run_dir: Completed AS2 run directory.
        findings: List of Finding objects from detect_all().
        output_path: Where to write the HTML file.
    """
    run_dir = Path(run_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build causal chains
    chains = build_causal_chains(run_dir, findings)

    # Get group behavior timeline for the overview chart
    timeline = compute_group_behavior_timeline(run_dir)

    # Generate HTML
    html = _render_html(chains, timeline, findings, run_dir.name)
    output_path.write_text(html, encoding="utf-8")


def _render_html(
    chains: List[CausalChain],
    timeline: List[GroupBehaviorSnapshot],
    findings: List,
    run_name: str,
) -> str:
    """Render the complete HTML causal report."""

    # Prepare timeline data for chart
    timeline_data = json.dumps([
        {
            "step": s.step,
            "entropy": s.action_entropy,
            "diversity": s.action_diversity,
            "coordination": s.coordination_index,
            "gini_vel": s.gini_velocity,
            "gov_momentum": s.governance_momentum,
        }
        for s in timeline
    ])

    # Prepare findings summary
    findings_by_cat = {}
    for f in findings:
        cat = getattr(f, "category", "unknown")
        findings_by_cat.setdefault(cat, []).append(f)

    # Build chain cards HTML
    chain_cards = ""
    for i, chain in enumerate(chains[:20]):  # limit to top 20
        chain_json = json.dumps(chain.chain, indent=2, ensure_ascii=False)
        failures_html = ""
        if chain.related_failures:
            failures_html = "<div class='failures'><strong>Related failures:</strong><ul>"
            for rf in chain.related_failures:
                failures_html += f"<li>agent {rf['agent_id']}: {rf['action']} — {rf['summary'][:60]}</li>"
            failures_html += "</ul></div>"

        sev_class = "critical" if chain.severity >= 80 else ("warning" if chain.severity >= 50 else "info")
        chain_cards += f"""
        <div class="chain-card {sev_class}">
          <div class="chain-header">
            <span class="badge badge-{sev_class}">{chain.finding_category}</span>
            <span class="meta">Agent {chain.agent_id or 'system'} | Step {chain.detected_at_step} | Severity {chain.severity}</span>
          </div>
          <div class="chain-detail">{chain.finding_detail[:200]}</div>
          <div class="chain-tree">
            <details><summary>Causal Chain ({len(chain.chain)} spans)</summary>
            <pre>{chain_json}</pre>
            </details>
          </div>
          {failures_html}
        </div>"""

    # Summary stats
    n_findings = len(findings)
    n_chains = len(chains)
    categories = sorted(findings_by_cat.keys())
    cat_summary = ", ".join(f"{cat}×{len(fs)}" for cat, fs in sorted(findings_by_cat.items()))

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Causal Attribution Report — {run_name}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, system-ui, sans-serif; background: #0a0f1a; color: #ccd6f6; padding: 2em; min-height: 100vh; }}
h1 {{ font-size: 1.6em; color: #64ffda; border-bottom: 2px solid #64ffda44; padding-bottom: .4em; margin-bottom: .8em; }}
h2 {{ font-size: 1.1em; color: #8892b0; margin: 1.4em 0 .5em; text-transform: uppercase; letter-spacing: .06em; }}
.meta-bar {{ color: #8892b0; font-size: .85em; margin-bottom: 1.5em; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1em; margin-bottom: 2em; }}
.stat-card {{ background: #112240; border: 1px solid #1d3461; border-radius: 8px; padding: 1em; text-align: center; }}
.stat-card .num {{ font-size: 1.8em; font-weight: 700; color: #64ffda; }}
.stat-card .label {{ font-size: .75em; color: #8892b0; text-transform: uppercase; }}
.chain-card {{ background: #112240; border: 1px solid #1d3461; border-radius: 8px; padding: 1em; margin-bottom: 1em; }}
.chain-card.critical {{ border-left: 4px solid #ff6363; }}
.chain-card.warning {{ border-left: 4px solid #ffd700; }}
.chain-card.info {{ border-left: 4px solid #64ffda; }}
.chain-header {{ display: flex; align-items: center; gap: 1em; margin-bottom: .5em; }}
.chain-detail {{ color: #8892b0; font-size: .88em; margin-bottom: .5em; }}
.chain-tree pre {{ font-size: .78em; background: #0d2137; padding: .8em; border-radius: 4px; overflow-x: auto; max-height: 200px; }}
.failures {{ font-size: .82em; color: #ffd700; margin-top: .5em; }}
.failures ul {{ padding-left: 1.2em; }}
.badge {{ display: inline-block; padding: .15em .6em; border-radius: 4px; font-size: .78em; font-weight: 600; }}
.badge-critical {{ background: #ff636322; color: #ff6363; border: 1px solid #ff636344; }}
.badge-warning {{ background: #ffd70022; color: #ffd700; border: 1px solid #ffd70044; }}
.badge-info {{ background: #64ffda22; color: #64ffda; border: 1px solid #64ffda44; }}
.meta {{ color: #8892b0; font-size: .82em; }}
details {{ cursor: pointer; }}
summary {{ color: #64ffda; font-size: .85em; }}
.timeline-chart {{ background: #112240; border: 1px solid #1d3461; border-radius: 8px; padding: 1.2em; margin-bottom: 2em; overflow-x: auto; }}
.timeline-table {{ font-size: .8em; width: 100%; border-collapse: collapse; }}
.timeline-table th {{ background: #1d3461; color: #64ffda; padding: .4em .6em; text-align: center; }}
.timeline-table td {{ padding: .3em .6em; text-align: center; border-bottom: 1px solid #1d346133; }}
.bar {{ display: inline-block; height: 8px; border-radius: 3px; min-width: 2px; }}
.section-divider {{ height: 1px; background: linear-gradient(to right, #64ffda44, transparent); margin: 2em 0; }}
</style>
</head>
<body>
<h1>🔍 Causal Attribution Report — {run_name}</h1>
<p class="meta-bar">Findings: {n_findings} | Causal chains: {n_chains} | Categories: {cat_summary}</p>

<div class="summary-grid">
  <div class="stat-card"><div class="num">{n_findings}</div><div class="label">Findings</div></div>
  <div class="stat-card"><div class="num">{n_chains}</div><div class="label">Causal Chains</div></div>
  <div class="stat-card"><div class="num">{len(categories)}</div><div class="label">Risk Types</div></div>
  <div class="stat-card"><div class="num">{len(timeline)}</div><div class="label">Steps Analyzed</div></div>
</div>

<h2>Group Behavior Timeline</h2>
<div class="timeline-chart">
<table class="timeline-table">
<tr><th>Step</th><th>H(action)</th><th>Diversity</th><th>Coordination</th><th>ΔGini</th><th>Gov Mom</th></tr>
{"".join(
    f'<tr><td>{s.step}</td>'
    f'<td>{s.action_entropy:.2f} <div class="bar" style="width:{min(s.action_entropy*20, 60)}px;background:#64ffda"></div></td>'
    f'<td>{s.action_diversity:.2f}</td>'
    f'<td style="color:{"#ff6363" if s.coordination_index > 0.8 else "#ccd6f6"}">{s.coordination_index:.2f}</td>'
    f'<td>{s.gini_velocity:+.3f}</td>'
    f'<td>{s.governance_momentum}</td></tr>'
    for s in timeline
)}
</table>
</div>

<div class="section-divider"></div>
<h2>Causal Attribution Chains</h2>
{chain_cards if chain_cards else '<p class="meta">No causal chains available (no traceable spans).</p>'}

<div class="section-divider"></div>
<p style="color:#8892b0;font-size:.78em;text-align:center;margin-top:2em">
  AI Governance Lab — Causal Attribution Report | afi-platform Phase 3
</p>

<script>
// Timeline data for future interactive features
const timelineData = {timeline_data};
</script>
</body>
</html>"""
