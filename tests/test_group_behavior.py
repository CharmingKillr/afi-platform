"""Unit tests for group_behavior module — population-level statistical indicators.

Tests:
- Shannon entropy calculation (uniform, skewed, empty)
- Action Diversity Index (all same, all different, partial)
- Coordination Index (single dominant, balanced)
- Gini Velocity (increasing, decreasing, stable)
- Alert detection (behavioral_convergence, herd_behavior, etc.)
- Timeline computation from synthetic spans
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from afi.audit.group_behavior import (
    _shannon_entropy,
    _max_entropy,
    GroupBehaviorSnapshot,
    GroupBehaviorAlert,
    detect_group_alerts,
    compute_group_behavior_timeline,
    format_group_behavior,
)


# ── Shannon Entropy Tests ─────────────────────────────────────────────────────


class TestShannonEntropy:
    def test_uniform_distribution(self):
        """Uniform distribution over 4 categories → log2(4) = 2.0 bits."""
        counts = {"a": 5, "b": 5, "c": 5, "d": 5}
        assert _shannon_entropy(counts) == pytest.approx(2.0, abs=0.01)

    def test_single_category(self):
        """All same → 0 entropy."""
        counts = {"observe": 10}
        assert _shannon_entropy(counts) == pytest.approx(0.0, abs=0.001)

    def test_two_equal(self):
        """Two equal categories → 1.0 bit."""
        counts = {"a": 50, "b": 50}
        assert _shannon_entropy(counts) == pytest.approx(1.0, abs=0.01)

    def test_empty(self):
        """Empty dict → 0."""
        assert _shannon_entropy({}) == 0.0

    def test_skewed(self):
        """Highly skewed → low entropy."""
        counts = {"observe": 100, "vote": 1}
        entropy = _shannon_entropy(counts)
        assert 0 < entropy < 0.1  # very low

    def test_three_categories(self):
        """Three equal → log2(3) ≈ 1.585."""
        counts = {"a": 10, "b": 10, "c": 10}
        assert _shannon_entropy(counts) == pytest.approx(1.585, abs=0.01)


class TestMaxEntropy:
    def test_one_category(self):
        assert _max_entropy(1) == 0.0

    def test_two_categories(self):
        assert _max_entropy(2) == pytest.approx(1.0, abs=0.01)

    def test_eight_categories(self):
        assert _max_entropy(8) == pytest.approx(3.0, abs=0.01)


# ── Alert Detection Tests ─────────────────────────────────────────────────────


class TestDetectGroupAlerts:
    def test_no_alerts_healthy(self):
        """Healthy timeline should not trigger alerts."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=2.0, action_diversity=0.6,
                                  coordination_index=0.3, gini_velocity=0.0,
                                  governance_momentum=1, social_entropy=1.5,
                                  n_actions=10, n_unique_actions=5, n_agents_active=5)
            for i in range(10)
        ]
        alerts = detect_group_alerts(timeline)
        assert len(alerts) == 0

    def test_behavioral_convergence(self):
        """Entropy dropping 4 consecutive steps → behavioral_convergence."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=2.0 - i * 0.3,
                                  action_diversity=0.5, coordination_index=0.3,
                                  gini_velocity=0.0, governance_momentum=1,
                                  social_entropy=1.0, n_actions=10,
                                  n_unique_actions=5, n_agents_active=5)
            for i in range(8)
        ]
        alerts = detect_group_alerts(timeline)
        convergence = [a for a in alerts if a.alert_type == "behavioral_convergence"]
        assert len(convergence) >= 1

    def test_herd_behavior(self):
        """Coordination > 0.8 for 3+ steps → herd_behavior."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=0.5,
                                  action_diversity=0.2,
                                  coordination_index=0.85,
                                  gini_velocity=0.0, governance_momentum=0,
                                  social_entropy=0.0, n_actions=10,
                                  n_unique_actions=2, n_agents_active=5)
            for i in range(5)
        ]
        alerts = detect_group_alerts(timeline)
        herd = [a for a in alerts if a.alert_type == "herd_behavior"]
        assert len(herd) >= 1

    def test_rapid_inequality(self):
        """ΔGini > 0.05 for 2 steps → rapid_inequality."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=2.0,
                                  action_diversity=0.5, coordination_index=0.3,
                                  gini_velocity=0.08 if i >= 3 else 0.0,
                                  governance_momentum=1, social_entropy=1.0,
                                  n_actions=10, n_unique_actions=5, n_agents_active=5)
            for i in range(8)
        ]
        alerts = detect_group_alerts(timeline)
        inequality = [a for a in alerts if a.alert_type == "rapid_inequality"]
        assert len(inequality) >= 1

    def test_governance_decay(self):
        """Momentum = 0 for 4+ steps → governance_decay."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=2.0,
                                  action_diversity=0.5, coordination_index=0.3,
                                  gini_velocity=0.0,
                                  governance_momentum=0,
                                  social_entropy=1.0, n_actions=10,
                                  n_unique_actions=5, n_agents_active=5)
            for i in range(8)
        ]
        alerts = detect_group_alerts(timeline)
        decay = [a for a in alerts if a.alert_type == "governance_decay"]
        assert len(decay) >= 1

    def test_low_diversity(self):
        """Diversity < 0.3 → low_diversity."""
        timeline = [
            GroupBehaviorSnapshot(step=i, action_entropy=0.5,
                                  action_diversity=0.2,
                                  coordination_index=0.5,
                                  gini_velocity=0.0, governance_momentum=1,
                                  social_entropy=1.0, n_actions=10,
                                  n_unique_actions=2, n_agents_active=5)
            for i in range(5)
        ]
        alerts = detect_group_alerts(timeline)
        low_div = [a for a in alerts if a.alert_type == "low_diversity"]
        assert len(low_div) >= 1

    def test_short_timeline_no_crash(self):
        """Timeline < 3 steps should return empty alerts, not crash."""
        timeline = [
            GroupBehaviorSnapshot(step=0, action_entropy=1.0, action_diversity=0.5,
                                  coordination_index=0.5, gini_velocity=0.0,
                                  governance_momentum=0, social_entropy=0.0,
                                  n_actions=5, n_unique_actions=3, n_agents_active=3)
        ]
        alerts = detect_group_alerts(timeline)
        assert alerts == []


# ── Timeline Computation Tests ────────────────────────────────────────────────


class TestComputeTimeline:
    def _make_run_dir(self, tmp_path, spans_data: list) -> Path:
        """Create a minimal run_dir with trace spans."""
        run_dir = tmp_path / "test_run"
        (run_dir / "trace").mkdir(parents=True)
        (run_dir / "agents" / "agent_0001").mkdir(parents=True)
        (run_dir / "agents" / "agent_0002").mkdir(parents=True)
        (run_dir / "agents" / "agent_0003").mkdir(parents=True)
        (run_dir / "env" / "GovernanceSpace" / "state").mkdir(parents=True)

        # Write governance state
        gov_state = {"articles": [], "proposals": [], "version": 1}
        (run_dir / "env" / "GovernanceSpace" / "state" / "GOVERNANCE_STATE.json").write_text(
            json.dumps(gov_state), encoding="utf-8"
        )

        # Write trace spans
        lines = [json.dumps(s) for s in spans_data]
        (run_dir / "trace" / "trace_00.jsonl").write_text(
            "\n".join(lines), encoding="utf-8"
        )

        return run_dir

    def test_diverse_actions(self, tmp_path):
        """Diverse actions → high entropy, high diversity, low coordination."""
        spans = []
        actions = ["observe", "propose", "vote", "send_message", "explore"]
        for step in range(1, 4):
            for i, agent in enumerate([1, 2, 3]):
                spans.append({
                    "name": "react.tool",
                    "start_time_unix_nano": step * 1_000_000_000 + i,
                    "resource": {"agent.id": agent},
                    "attributes": {"react.action": actions[i % len(actions)], "step.count": step},
                })

        run_dir = self._make_run_dir(tmp_path, spans)
        timeline = compute_group_behavior_timeline(run_dir)

        assert len(timeline) == 3
        # With 3 different actions per step, entropy should be > 1.0
        assert timeline[0].action_entropy > 1.0
        # Coordination should be low (no dominant action)
        assert timeline[0].coordination_index < 0.5

    def test_uniform_actions(self, tmp_path):
        """All agents do same action → zero entropy, max coordination."""
        spans = []
        for step in range(1, 4):
            for agent in [1, 2, 3]:
                spans.append({
                    "name": "react.tool",
                    "start_time_unix_nano": step * 1_000_000_000,
                    "resource": {"agent.id": agent},
                    "attributes": {"react.action": "observe", "step.count": step},
                })

        run_dir = self._make_run_dir(tmp_path, spans)
        timeline = compute_group_behavior_timeline(run_dir)

        assert len(timeline) == 3
        # All same action → entropy = 0
        assert timeline[0].action_entropy == pytest.approx(0.0, abs=0.01)
        # Coordination = 1.0 (perfect sync)
        assert timeline[0].coordination_index == pytest.approx(1.0, abs=0.01)

    def test_empty_run_dir(self, tmp_path):
        """Missing trace dir → empty timeline."""
        run_dir = tmp_path / "empty_run"
        run_dir.mkdir()
        timeline = compute_group_behavior_timeline(run_dir)
        assert timeline == []


# ── Format Tests ──────────────────────────────────────────────────────────────


class TestFormat:
    def test_format_output(self):
        """format_group_behavior produces readable text."""
        timeline = [
            GroupBehaviorSnapshot(step=1, action_entropy=1.8, action_diversity=0.5,
                                  coordination_index=0.4, gini_velocity=0.01,
                                  governance_momentum=2, social_entropy=1.2,
                                  n_actions=10, n_unique_actions=5, n_agents_active=5)
        ]
        text = format_group_behavior(timeline, [])
        assert "Group Behavior Analysis" in text
        assert "1.800" in text  # entropy value
        assert "No group behavior alerts" in text

    def test_format_empty(self):
        text = format_group_behavior([], [])
        assert "No action data" in text
