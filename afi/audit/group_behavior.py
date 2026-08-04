"""Group Behavior — statistical indicators for multi-agent collective dynamics.

Six metrics quantifying group-level behavioral patterns over time:
  G1. Action Entropy — Shannon entropy of action distribution (diversity of behavior)
  G2. Action Diversity Index — fraction of available actions actually used
  G3. Coordination Index — max action frequency / total (synchronization)
  G4. Gini Velocity — step-over-step Gini change rate
  G5. Governance Momentum — proposals+votes increment over window
  G6. Social Entropy — communication pair distribution entropy

These complement the existing per-agent detectors (sensorium, tunnel_vision)
with population-level signals. A group where all agents converge on the same
action pattern is qualitatively different from one agent being stuck.

stdlib-only; reads run_dir via afi.audit.load + afi.audit.awi.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from afi.audit.awi import compute_awi_timeline, AWISnapshot
from afi.audit.load import load_spans, agent_id


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class GroupBehaviorSnapshot:
    """Per-step group behavior metrics."""
    step: int
    action_entropy: float = 0.0         # G1: Shannon entropy of action dist
    action_diversity: float = 0.0       # G2: unique_actions / total_possible
    coordination_index: float = 0.0     # G3: max_action_freq / total_actions
    gini_velocity: float = 0.0          # G4: ΔGini from previous step
    governance_momentum: int = 0        # G5: Δ(proposals+votes) over window
    social_entropy: float = 0.0         # G6: entropy of communication pairs
    # Raw counts for inspection
    n_actions: int = 0
    n_unique_actions: int = 0
    n_agents_active: int = 0


@dataclass
class GroupBehaviorAlert:
    """Alert triggered by group behavior anomaly."""
    step: int
    alert_type: str       # behavioral_convergence | low_diversity | herd_behavior |
                          # rapid_inequality | governance_decay | communication_concentration
    metric_name: str      # G1-G6
    value: float
    threshold: float
    severity: str         # info | warning | critical
    message: str


# ── Entropy / statistics helpers ──────────────────────────────────────────────


def _shannon_entropy(counts: Dict[str, int]) -> float:
    """Shannon entropy in bits from a frequency dict. 0 if empty or uniform-1."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    probs = [c / total for c in counts.values() if c > 0]
    return -sum(p * math.log2(p) for p in probs)


def _max_entropy(n_categories: int) -> float:
    """Maximum possible entropy for n categories (uniform distribution)."""
    if n_categories <= 1:
        return 0.0
    return math.log2(n_categories)


# ── Core computation ──────────────────────────────────────────────────────────


def _extract_actions_per_step(spans: List[dict]) -> Dict[int, List[Tuple[int, str]]]:
    """Extract (agent_id, action) pairs grouped by step from trace spans.

    Returns: {step: [(agent_id, action_name), ...]}
    """
    by_step: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
    for s in spans:
        if s.get("name") != "react.tool":
            continue
        aid = agent_id(s)
        if aid is None:
            continue
        attrs = s.get("attributes") or {}
        action = attrs.get("react.action", "unknown")
        step = attrs.get("step.count", 0)
        if isinstance(step, (int, float)):
            by_step[int(step)].append((aid, str(action)))
    return dict(by_step)


def _extract_message_pairs(run_dir: Path) -> Dict[int, List[Tuple[int, int]]]:
    """Extract (sender, receiver) message pairs per step from social env.

    Returns: {step: [(sender_id, receiver_id), ...]}
    Falls back to empty if no message data available.
    """
    from afi.audit.collude import extract_blackboards

    pairs_by_step: Dict[int, List[Tuple[int, int]]] = defaultdict(list)

    try:
        blackboards = extract_blackboards(str(run_dir))
    except Exception:
        return {}

    # extract_blackboards may return a list of dicts or a dict of {bid: bb}
    if isinstance(blackboards, list):
        # Convert list to dict keyed by blackboard_id
        bb_dict = {}
        for bb in blackboards:
            bid = bb.get("blackboard_id", bb.get("id", ""))
            bb_dict[bid] = bb
        blackboards = bb_dict

    # DM blackboards have format dm_<sender>_<receiver>
    for bid, bb in blackboards.items():
        if not bid.startswith("dm_"):
            continue
        parts = bid.split("_")
        if len(parts) >= 3:
            try:
                sender = int(parts[1])
                receiver = int(parts[2])
            except (ValueError, IndexError):
                continue
            events = bb.get("events", [])
            for i, ev in enumerate(events):
                # Approximate step from event index (1-indexed)
                step = i + 1
                pairs_by_step[step].append((sender, receiver))

    return dict(pairs_by_step)


def compute_group_behavior_timeline(
    run_dir: str | Path,
) -> List[GroupBehaviorSnapshot]:
    """Compute per-step group behavior metrics for a completed run.

    Combines trace spans (actions per agent per step) with AWI timeline
    (Gini, governance) and message data (social entropy).
    """
    run_dir = Path(run_dir)

    # Load trace spans
    try:
        spans = load_spans(run_dir)
    except FileNotFoundError:
        return []

    # Extract actions per step
    actions_per_step = _extract_actions_per_step(spans)
    if not actions_per_step:
        return []

    # AWI timeline for Gini and governance metrics
    try:
        awi_timeline = compute_awi_timeline(str(run_dir))
    except Exception:
        awi_timeline = []
    awi_by_step = {s.step: s for s in awi_timeline}

    # Message pairs for social entropy
    message_pairs = _extract_message_pairs(run_dir)

    # Determine all known actions across the run (for diversity denominator)
    all_actions_seen: set = set()
    for step_actions in actions_per_step.values():
        for _, action in step_actions:
            all_actions_seen.add(action)
    total_possible_actions = max(len(all_actions_seen), 1)

    # Build timeline
    steps_sorted = sorted(actions_per_step.keys())
    timeline: List[GroupBehaviorSnapshot] = []
    prev_gini = 0.0

    for step in steps_sorted:
        step_actions = actions_per_step[step]
        action_counts = Counter(action for _, action in step_actions)
        agents_active = len(set(aid for aid, _ in step_actions))

        # G1: Action Entropy
        action_entropy = _shannon_entropy(dict(action_counts))

        # G2: Action Diversity Index
        n_unique = len(action_counts)
        action_diversity = n_unique / total_possible_actions

        # G3: Coordination Index
        total_actions = sum(action_counts.values())
        max_freq = max(action_counts.values()) if action_counts else 0
        coordination_index = max_freq / total_actions if total_actions > 0 else 0.0

        # G4: Gini Velocity
        awi_snap = awi_by_step.get(step)
        current_gini = awi_snap.gini if awi_snap else 0.0
        gini_velocity = current_gini - prev_gini
        prev_gini = current_gini

        # G5: Governance Momentum (Δ proposals+votes over last 3 steps)
        governance_momentum = 0
        if awi_snap and len(timeline) >= 1:
            # Compare current proposals+votes to 3 steps ago
            lookback = min(3, len(timeline))
            prev_snap = awi_by_step.get(steps_sorted[max(0, len(timeline) - lookback)])
            if prev_snap:
                current_gov = (awi_snap.total_proposals or 0) + (awi_snap.votes_cast or 0)
                prev_gov = (prev_snap.total_proposals or 0) + (prev_snap.votes_cast or 0)
                governance_momentum = current_gov - prev_gov

        # G6: Social Entropy
        step_messages = message_pairs.get(step, [])
        if step_messages:
            pair_counts = Counter(step_messages)
            social_entropy = _shannon_entropy(dict(pair_counts))
        else:
            social_entropy = 0.0

        timeline.append(GroupBehaviorSnapshot(
            step=step,
            action_entropy=round(action_entropy, 4),
            action_diversity=round(action_diversity, 4),
            coordination_index=round(coordination_index, 4),
            gini_velocity=round(gini_velocity, 4),
            governance_momentum=governance_momentum,
            social_entropy=round(social_entropy, 4),
            n_actions=total_actions,
            n_unique_actions=n_unique,
            n_agents_active=agents_active,
        ))

    return timeline


# ── Alert detection ───────────────────────────────────────────────────────────


def detect_group_alerts(
    timeline: List[GroupBehaviorSnapshot],
) -> List[GroupBehaviorAlert]:
    """Detect anomalies in group behavior timeline.

    Alert rules:
    - G1: entropy dropping for 3+ consecutive steps → behavioral_convergence
    - G2: diversity < 0.3 → low_diversity
    - G3: coordination > 0.8 for 3+ steps → herd_behavior
    - G4: ΔGini > 0.05 for 2+ steps → rapid_inequality
    - G5: momentum = 0 for 4+ steps → governance_decay
    - G6: social_entropy drops > 50% from peak → communication_concentration
    """
    alerts: List[GroupBehaviorAlert] = []
    if len(timeline) < 3:
        return alerts

    # G1: Behavioral Convergence (entropy dropping 3+ consecutive steps)
    entropy_drops = 0
    for i in range(1, len(timeline)):
        if timeline[i].action_entropy < timeline[i - 1].action_entropy - 0.01:
            entropy_drops += 1
        else:
            entropy_drops = 0

        if entropy_drops >= 3:
            alerts.append(GroupBehaviorAlert(
                step=timeline[i].step,
                alert_type="behavioral_convergence",
                metric_name="G1_action_entropy",
                value=timeline[i].action_entropy,
                threshold=timeline[i - 3].action_entropy,
                severity="warning",
                message=f"Action entropy declining for {entropy_drops} steps: "
                        f"{timeline[i-3].action_entropy:.2f} → {timeline[i].action_entropy:.2f}",
            ))
            break  # one alert per type

    # G2: Low Diversity
    for snap in timeline:
        if snap.action_diversity < 0.3 and snap.n_actions >= 3:
            alerts.append(GroupBehaviorAlert(
                step=snap.step,
                alert_type="low_diversity",
                metric_name="G2_action_diversity",
                value=snap.action_diversity,
                threshold=0.3,
                severity="info",
                message=f"Action diversity {snap.action_diversity:.2f} < 0.30 "
                        f"({snap.n_unique_actions} unique / {snap.n_actions} total)",
            ))
            break

    # G3: Herd Behavior (coordination > 0.8 for 3+ steps)
    herd_streak = 0
    for snap in timeline:
        if snap.coordination_index > 0.8:
            herd_streak += 1
        else:
            herd_streak = 0

        if herd_streak >= 3:
            alerts.append(GroupBehaviorAlert(
                step=snap.step,
                alert_type="herd_behavior",
                metric_name="G3_coordination_index",
                value=snap.coordination_index,
                threshold=0.8,
                severity="warning",
                message=f"Coordination index > 0.80 for {herd_streak} steps "
                        f"(agents doing the same action)",
            ))
            break

    # G4: Rapid Inequality (ΔGini > 0.05 for 2+ steps)
    inequality_streak = 0
    for snap in timeline:
        if snap.gini_velocity > 0.05:
            inequality_streak += 1
        else:
            inequality_streak = 0

        if inequality_streak >= 2:
            alerts.append(GroupBehaviorAlert(
                step=snap.step,
                alert_type="rapid_inequality",
                metric_name="G4_gini_velocity",
                value=snap.gini_velocity,
                threshold=0.05,
                severity="warning",
                message=f"Gini rising rapidly: ΔGini={snap.gini_velocity:.3f} "
                        f"for {inequality_streak} consecutive steps",
            ))
            break

    # G5: Governance Decay (momentum = 0 for 4+ steps)
    decay_streak = 0
    for snap in timeline:
        if snap.governance_momentum == 0:
            decay_streak += 1
        else:
            decay_streak = 0

        if decay_streak >= 4:
            alerts.append(GroupBehaviorAlert(
                step=snap.step,
                alert_type="governance_decay",
                metric_name="G5_governance_momentum",
                value=0.0,
                threshold=4.0,
                severity="info",
                message=f"Zero governance activity for {decay_streak} steps "
                        f"(no new proposals or votes)",
            ))
            break

    # G6: Communication Concentration (entropy drops > 50% from peak)
    if any(s.social_entropy > 0 for s in timeline):
        peak_social = max(s.social_entropy for s in timeline)
        if peak_social > 0:
            for snap in timeline:
                if snap.social_entropy < peak_social * 0.5 and snap.social_entropy > 0:
                    alerts.append(GroupBehaviorAlert(
                        step=snap.step,
                        alert_type="communication_concentration",
                        metric_name="G6_social_entropy",
                        value=snap.social_entropy,
                        threshold=peak_social * 0.5,
                        severity="info",
                        message=f"Social entropy dropped to {snap.social_entropy:.2f} "
                                f"(peak was {peak_social:.2f}, >50% drop = concentration)",
                    ))
                    break

    return alerts


# ── Public API ────────────────────────────────────────────────────────────────


def run_group_behavior_analysis(run_dir: str | Path) -> Tuple[List[GroupBehaviorSnapshot], List[GroupBehaviorAlert]]:
    """Full group behavior analysis: compute timeline + detect alerts.

    Returns (timeline, alerts).
    """
    timeline = compute_group_behavior_timeline(run_dir)
    alerts = detect_group_alerts(timeline)
    return timeline, alerts


def format_group_behavior(
    timeline: List[GroupBehaviorSnapshot],
    alerts: List[GroupBehaviorAlert],
) -> str:
    """Format group behavior analysis as human-readable text."""
    lines = ["=== Group Behavior Analysis ==="]

    if not timeline:
        lines.append("No action data available for group behavior analysis.")
        return "\n".join(lines)

    lines.append(f"Steps analyzed: {len(timeline)} (step {timeline[0].step}–{timeline[-1].step})")
    lines.append("")

    # Summary stats
    avg_entropy = sum(s.action_entropy for s in timeline) / len(timeline)
    avg_diversity = sum(s.action_diversity for s in timeline) / len(timeline)
    avg_coordination = sum(s.coordination_index for s in timeline) / len(timeline)
    max_coordination = max(s.coordination_index for s in timeline)

    lines.append(f"  Avg action entropy:      {avg_entropy:.3f} bits")
    lines.append(f"  Avg action diversity:    {avg_diversity:.3f}")
    lines.append(f"  Avg coordination index:  {avg_coordination:.3f} (max {max_coordination:.3f})")
    lines.append(f"  Total Gini velocity:     {sum(s.gini_velocity for s in timeline):.4f}")
    lines.append(f"  Total governance momentum: {sum(s.governance_momentum for s in timeline)}")
    lines.append("")

    # Per-step table (compact)
    lines.append(f"  {'Step':>4} {'H(act)':>7} {'Div':>5} {'Coord':>6} {'ΔGini':>7} {'GovMom':>6} {'H(soc)':>7}")
    lines.append(f"  {'----':>4} {'------':>7} {'---':>5} {'-----':>6} {'-----':>7} {'------':>6} {'------':>7}")
    for s in timeline:
        lines.append(
            f"  {s.step:>4} {s.action_entropy:>7.3f} {s.action_diversity:>5.2f} "
            f"{s.coordination_index:>6.3f} {s.gini_velocity:>+7.4f} "
            f"{s.governance_momentum:>6} {s.social_entropy:>7.3f}"
        )

    # Alerts
    lines.append("")
    if alerts:
        lines.append(f"  ALERTS ({len(alerts)}):")
        for a in alerts:
            lines.append(
                f"    [{a.severity:8s}] step {a.step}: {a.alert_type} — {a.message}"
            )
    else:
        lines.append("  No group behavior alerts triggered.")

    return "\n".join(lines)
