"""B9 unit tests — afi-platform core modules.

Covers:
- awi._gini: edge cases (equal/monopoly/empty)
- awi._m3_mobility_computed: proxy→computed detection
- awi._m7_relationship_computed: proxy→computed detection
- awi._m6_billboard_computed: proxy→computed detection
- scenario.load_scenario: pydantic validation (valid + bad YAML)
- custom envs: EWMobilitySpace / RelationshipSpace / BillboardSpace imports

Run:  pytest tests/ -v
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add afi-platform root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from afi.audit.awi import (
    _gini,
    _m3_mobility_computed,
    _m6_billboard_computed,
    _m7_relationship_computed,
)


# ── _gini ─────────────────────────────────────────────────────────────────────

class TestGini:
    def test_equal_distribution(self):
        """Perfect equality → Gini = 0.0"""
        assert _gini([10, 10, 10, 10]) == pytest.approx(0.0, abs=1e-6)

    def test_monopoly(self):
        """One agent holds everything → Gini = (n-1)/n"""
        n = 5
        vals = [0] * (n - 1) + [100]
        expected = (n - 1) / n
        assert _gini(vals) == pytest.approx(expected, abs=1e-4)

    def test_two_agents_equal(self):
        assert _gini([50, 50]) == pytest.approx(0.0, abs=1e-6)

    def test_two_agents_unequal(self):
        assert _gini([0, 100]) == pytest.approx(0.5, abs=1e-6)

    def test_empty(self):
        assert _gini([]) == 0.0

    def test_all_zero(self):
        assert _gini([0, 0, 0]) == 0.0

    def test_single(self):
        assert _gini([42]) == 0.0


# ── M3 mobility ───────────────────────────────────────────────────────────────

@pytest.fixture
def mobility_run_dir(tmp_path):
    """Temp run_dir with 3 mobility shards, 5 agents, 3 steps."""
    replay = tmp_path / "replay"
    replay.mkdir()
    for step in range(1, 4):
        locs = {1: "Home", 2: "TechHub", 3: "Central Plaza", 4: "Market", 5: "Library"}
        if step > 1:
            locs[1] = "Town Hall"  # agent 1 moves on step 2
        rows = [
            {"agent_id": aid, "step": step, "t": f"2026-07-01T0{step+7}:00:00",
             "lng": 116.3, "lat": 39.9, "location_name": loc}
            for aid, loc in locs.items()
        ]
        shard = replay / f"mobility_agent_state.{step:04x}.jsonl"
        shard.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


class TestM3MobilityComputed:
    def test_returns_computed_when_shards_exist(self, mobility_run_dir):
        result = _m3_mobility_computed(mobility_run_dir, 5)
        assert result is not None, "Should return computed result when shards exist"

    def test_returns_none_without_shards(self, tmp_path):
        (tmp_path / "replay").mkdir()
        result = _m3_mobility_computed(tmp_path, 5)
        assert result is None, "Should return None when no mobility shards"

    def test_value_reflects_unique_locations(self, mobility_run_dir):
        result = _m3_mobility_computed(mobility_run_dir, 5)
        # agent 1 visited Home + Town Hall = 2; others visited 1 each
        # avg = (2 + 1 + 1 + 1 + 1) / 5 = 1.2
        assert result == pytest.approx(1.2, abs=0.01)

    def test_returns_none_if_no_replay_dir(self, tmp_path):
        result = _m3_mobility_computed(tmp_path, 5)
        assert result is None


# ── M7 relationship ───────────────────────────────────────────────────────────

@pytest.fixture
def relationship_run_dir(tmp_path):
    """Run_dir with ally(1,2), rival(1,3) = 2 edges."""
    replay = tmp_path / "replay"
    replay.mkdir()
    rows = [
        {"agent_id": 1, "step": 3, "t": "2026-07-01T11:00:00",
         "relationship_count": 2,
         "relationships": {"2": "ally", "3": "rival"},
         "type_counts": {"ally": 2, "rival": 1, "mentor": 0, "mentee": 0, "neutral": 0}},
        {"agent_id": 2, "step": 3, "t": "2026-07-01T11:00:00",
         "relationship_count": 1,
         "relationships": {"1": "ally"},
         "type_counts": {"ally": 2, "rival": 1, "mentor": 0, "mentee": 0, "neutral": 0}},
        {"agent_id": 3, "step": 3, "t": "2026-07-01T11:00:00",
         "relationship_count": 1,
         "relationships": {"1": "rival"},
         "type_counts": {"ally": 2, "rival": 1, "mentor": 0, "mentee": 0, "neutral": 0}},
        {"agent_id": 4, "step": 3, "t": "2026-07-01T11:00:00",
         "relationship_count": 0, "relationships": {},
         "type_counts": {"ally": 2, "rival": 1, "mentor": 0, "mentee": 0, "neutral": 0}},
        {"agent_id": 5, "step": 3, "t": "2026-07-01T11:00:00",
         "relationship_count": 0, "relationships": {},
         "type_counts": {"ally": 2, "rival": 1, "mentor": 0, "mentee": 0, "neutral": 0}},
    ]
    shard = replay / "relationship_agent_state.ab12.jsonl"
    shard.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


class TestM7RelationshipComputed:
    def test_returns_computed_when_shards_exist(self, relationship_run_dir):
        result = _m7_relationship_computed(relationship_run_dir, 5)
        assert result is not None

    def test_returns_none_without_shards(self, tmp_path):
        (tmp_path / "replay").mkdir()
        assert _m7_relationship_computed(tmp_path, 5) is None

    def test_edge_count(self, relationship_run_dir):
        result = _m7_relationship_computed(relationship_run_dir, 5)
        assert result["type_counts"]["ally"] == 2
        assert result["type_counts"]["rival"] == 1

    def test_density(self, relationship_run_dir):
        result = _m7_relationship_computed(relationship_run_dir, 5)
        # 3 edges out of C(5,2)=10 possible → density = 3/10 = 0.3
        assert result["social_density"] == pytest.approx(0.3, abs=0.01)


# ── M6 billboard ──────────────────────────────────────────────────────────────

@pytest.fixture
def billboard_run_dir(tmp_path):
    """Run_dir with 5 posts by 3 different agents."""
    replay = tmp_path / "replay"
    replay.mkdir()
    rows = [
        {"agent_id": aid, "step": 3, "t": "2026-07-01T11:00:00",
         "my_post_count": posts, "total_posts": 5, "unique_posters": 3, "recent_post": "hi"}
        for aid, posts in [(1, 2), (2, 2), (3, 1), (4, 0), (5, 0)]
    ]
    shard = replay / "billboard_agent_state.cd34.jsonl"
    shard.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


class TestM6BillboardComputed:
    def test_returns_computed_when_shards_exist(self, billboard_run_dir):
        result = _m6_billboard_computed(billboard_run_dir)
        assert result is not None

    def test_returns_none_without_shards(self, tmp_path):
        (tmp_path / "replay").mkdir()
        assert _m6_billboard_computed(tmp_path) is None

    def test_post_counts(self, billboard_run_dir):
        result = _m6_billboard_computed(billboard_run_dir)
        assert result["total_posts"] == 5
        assert result["unique_posters"] == 3


# ── scenario.load_scenario ────────────────────────────────────────────────────

class TestLoadScenario:
    def test_loads_ew_subset(self):
        """Existing ew-subset.yaml loads without error."""
        yaml_path = ROOT / "scenarios" / "ew-subset.yaml"
        if not yaml_path.exists():
            pytest.skip("ew-subset.yaml not found")
        from afi.world.scenario import load_scenario
        result = load_scenario(yaml_path)
        assert "steps" in result or "world" in result

    def test_loads_rct_control(self):
        yaml_path = ROOT / "scenarios" / "rct_control.yaml"
        if not yaml_path.exists():
            pytest.skip("rct_control.yaml not found")
        from afi.world.scenario import load_scenario
        result = load_scenario(yaml_path)
        assert isinstance(result, dict)

    def test_bad_step_type_raises(self, tmp_path):
        """Invalid step type should raise ValueError when pydantic available."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "world:\n  initial_credits: 100\nagents: full\n"
            "start_t: '2026-07-01T08:00:00'\nsteps:\n  - type: invalid_type\n    num_steps: 3\n"
        )
        from afi.world.scenario import load_scenario
        try:
            import pydantic
            if int(pydantic.__version__.split(".")[0]) >= 2:
                with pytest.raises(ValueError, match="invalid_type"):
                    load_scenario(bad)
            else:
                pytest.skip("pydantic v2 required for strict validation")
        except ImportError:
            pytest.skip("pydantic not installed")


# ── custom env imports ────────────────────────────────────────────────────────

class TestCustomEnvImports:
    def test_ew_mobility_space_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ew_mobility_space", ROOT / "custom/envs/ew_mobility_space.py"
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            assert hasattr(mod, "EWMobilitySpace")
        except ImportError as e:
            pytest.skip(f"agentsociety2 not available: {e}")

    def test_relationship_space_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "relationship_space", ROOT / "custom/envs/relationship_space.py"
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            assert hasattr(mod, "RelationshipSpace")
        except ImportError as e:
            pytest.skip(f"agentsociety2 not available: {e}")

    def test_billboard_space_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "billboard_space", ROOT / "custom/envs/billboard_space.py"
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            assert hasattr(mod, "BillboardSpace")
        except ImportError as e:
            pytest.skip(f"agentsociety2 not available: {e}")
