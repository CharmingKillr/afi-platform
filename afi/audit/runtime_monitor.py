"""Runtime monitor — rolling statistics + change-point detection + early alerts.

Ports the *idea* from AFI `simulation/runtime_monitor.py` (Detect risk
escalation early via rolling stats, alert before irreversible), NOT its code
— AFI reads its `turn_log`; we read AWI timeline + sensorium from a run_dir.
This is the temporal/early-warning layer the sealed-line audit (sensorium /
tunnel_vision) lacks: those describe the final state, this watches the trend.

stdlib-only; reads run_dir via afi.audit.awi + afi.audit.sensorium.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from afi.audit.awi import AWISnapshot, compute_awi_timeline


# ── alert record ────────────────────────────────────────────────────────────


@dataclass
class RiskAlert:
    tick: int
    alert_type: str
    value: float
    threshold: float
    severity: str  # "info" | "warning" | "critical"
    message: str


@dataclass
class MonitorState:
    timeline: List[AWISnapshot] = field(default_factory=list)
    alerts: List[RiskAlert] = field(default_factory=list)


# ── change-point detection (ported idea from AFI _detect_change_point) ──────


def _detect_change_point(series: List[float], window: int = 3) -> Optional[tuple]:
    """Flag if recent-window mean diverges > threshold from baseline mean.

    Returns (recent, baseline, ratio) if flagged, else None. Ratio = how many
    times the recent mean is the baseline (or its inverse if shrinking).
    """
    if len(series) < window * 2:
        return None
    recent = sum(series[-window:]) / window
    baseline = sum(series[:-window]) / max(len(series) - window, 1)
    if baseline == 0:
        return (recent, baseline, float("inf") if recent > 0 else 1.0)
    ratio = recent / baseline
    return (recent, baseline, ratio)


def _series(timeline: List[AWISnapshot], attr_name: str) -> List[float]:
    out = []
    for s in timeline:
        v = getattr(s, attr_name, None)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


# ── alert checks ───────────────────────────────────────────────────────────


def _check_sensorium_collapse(run_dir, timeline, alerts):
    """Sensorium ratio dropped >40% step-over-step (AFI's sensorium_collapse)."""
    from afi.audit.sensorium import sensorium_report
    from afi.audit.load import load_spans

    spans = load_spans(run_dir)
    rep = sensorium_report(spans)
    world = rep.get("world", {})
    # sensorium_report world ratio if present; else skip
    ratio = world.get("sensing_ratio") or world.get("ratio")
    if ratio is None:
        return
    if ratio < 0.40:  # below 40% sensing
        alerts.append(
            RiskAlert(
                tick=timeline[-1].step if timeline else 0,
                alert_type="sensorium_collapse",
                value=float(ratio),
                threshold=0.40,
                severity="warning",
                message=f"World sensing ratio {ratio:.2f} below 40% — agents under-observing.",
            )
        )


def _check_governance_stagnation(run_dir, timeline, alerts, n_steps_stall=4):
    """No new proposals AND no new votes for N consecutive steps."""
    if len(timeline) < n_steps_stall + 1:
        return
    tail = timeline[-(n_steps_stall + 1):]
    base = tail[0]
    for s in tail[1:]:
        if s.total_proposals == base.total_proposals and s.votes_cast == base.votes_cast:
            continue
        return  # activity happened, no stagnation
    alerts.append(
        RiskAlert(
            tick=timeline[-1].step,
            alert_type="governance_stagnation",
            value=float(n_steps_stall),
            threshold=float(n_steps_stall),
            severity="warning",
            message=f"No new proposals/votes for {n_steps_stall} steps — governance stalled.",
        )
    )


def _check_economic_hoarding(run_dir, timeline, alerts, gini_jump=0.10, gini_abs=0.5):
    """Gini jumped >0.10 step-over-step, or absolute concentration >0.5."""
    ginis = _series(timeline, "gini")
    cp = _detect_change_point(ginis, window=2)
    if cp and cp[2] != float("inf") and (cp[0] - cp[1]) > gini_jump:
        alerts.append(
            RiskAlert(
                tick=timeline[-1].step,
                alert_type="economic_hoarding",
                value=float(cp[0]),
                threshold=float(cp[1] + gini_jump),
                severity="warning",
                message=f"Gini rose {cp[1]:.3f}→{cp[0]:.3f} — credit concentrating.",
            )
        )
    if ginis and ginis[-1] > gini_abs:
        alerts.append(
            RiskAlert(
                tick=timeline[-1].step,
                alert_type="economic_hoarding",
                value=float(ginis[-1]),
                threshold=float(gini_abs),
                severity="critical",
                message=f"Gini {ginis[-1]:.3f} > {gini_abs} — severe credit inequality.",
            )
        )


def _check_tunnel_vision_escalation(run_dir, timeline, alerts):
    """Tunnel-vision windows rising across the run (proxy: final count >=3)."""
    from afi.audit.tunnel_vision import tunnel_vision_report
    from afi.audit.load import load_spans

    spans = load_spans(run_dir)
    rep = tunnel_vision_report(spans)
    windows = rep.get("windows", [])
    if len(windows) >= 3:
        alerts.append(
            RiskAlert(
                tick=timeline[-1].step if timeline else 0,
                alert_type="tunnel_vision_escalation",
                value=float(len(windows)),
                threshold=3.0,
                severity="info",
                message=f"{len(windows)} tunnel-vision windows — agents may be stuck in behavioral loops.",
            )
        )


# ── public API ──────────────────────────────────────────────────────────────


def run_monitor(run_dir: str | Path) -> List[RiskAlert]:
    """Compute the AWI timeline for a run and run all alert checks.

    Returns the list of RiskAlerts (possibly empty). Never raises on short
    timelines — checks self-guard on length.
    """
    run_dir = str(run_dir)
    timeline = compute_awi_timeline(run_dir)

    alerts: List[RiskAlert] = []
    _check_sensorium_collapse(run_dir, timeline, alerts)
    _check_governance_stagnation(run_dir, timeline, alerts)
    _check_economic_hoarding(run_dir, timeline, alerts)
    _check_tunnel_vision_escalation(run_dir, timeline, alerts)
    _check_group_behavior(run_dir, alerts)
    return alerts


def _check_group_behavior(run_dir: str, alerts: List[RiskAlert]):
    """Run group behavior analysis and convert alerts to RiskAlerts."""
    try:
        from afi.audit.group_behavior import run_group_behavior_analysis, GroupBehaviorAlert
    except ImportError:
        return

    try:
        _, group_alerts = run_group_behavior_analysis(run_dir)
    except Exception:
        return

    severity_map = {"info": "info", "warning": "warning", "critical": "critical"}
    for ga in group_alerts:
        alerts.append(RiskAlert(
            tick=ga.step,
            alert_type=ga.alert_type,
            value=ga.value,
            threshold=ga.threshold,
            severity=severity_map.get(ga.severity, "info"),
            message=ga.message,
        ))


def format_alerts(alerts: List[RiskAlert]) -> str:
    if not alerts:
        return "runtime monitor: no alerts (all series within thresholds)."
    lines = ["=== runtime monitor alerts ==="]
    for a in alerts:
        lines.append(
            f"[{a.severity:8s}] step {a.tick} {a.alert_type}: "
            f"value={a.value:.3f} threshold={a.threshold:.3f} — {a.message}"
        )
    return "\n".join(lines)
