import json
import unittest
from pathlib import Path

from cachepilot.algorithms.adaptive_weights import AdaptiveWeightController
from cachepilot.algorithms.r3kv import KVObject, decide, estimate_reuse_probability
from cachepilot.cost.models import CostModel
from cachepilot.replay.engine import load_scenario, simulate


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))


class R3KVTests(unittest.TestCase):
    def test_reuse_probability_is_bounded(self):
        kv = KVObject("x", "p", 1048576, 2048)
        for now in (0, 1, 1000):
            self.assertGreaterEqual(estimate_reuse_probability(kv, now), 0)
            self.assertLessEqual(estimate_reuse_probability(kv, now), 1)
            kv.record_access(now, local_hit=False)

    def test_retrieve_or_recompute_is_deterministic(self):
        kv = KVObject("x", "p", 1048576, 2048)
        common = dict(now=10, weights=CONFIG["weights"], thresholds=CONFIG["thresholds"],
                      node_load=0, capacity_bytes=24 * 1048576,
                      local_capacity_available=True, remote_available=True)
        fetch = decide(kv, retrieve_cost_ms=5, recompute_cost_ms=50, **common)
        recompute = decide(kv, retrieve_cost_ms=50, recompute_cost_ms=5, **common)
        self.assertEqual(fetch.action, "FETCH")
        self.assertEqual(recompute.action, "RECOMPUTE")
        self.assertEqual(fetch.action, decide(kv, retrieve_cost_ms=5, recompute_cost_ms=50, **common).action)

    def test_valuable_kv_scores_above_cold_kv(self):
        hot = KVObject("hot", "p", 1048576, 8192, current_location="LOCAL")
        cold = KVObject("cold", "p", 4 * 1048576, 512, current_location="LOCAL")
        for now in range(8):
            hot.record_access(now, True)
        result_hot = decide(hot, now=8, weights=CONFIG["weights"], thresholds=CONFIG["thresholds"],
                            retrieve_cost_ms=5, recompute_cost_ms=650,
                            node_load=0, capacity_bytes=24 * 1048576,
                            local_capacity_available=True, remote_available=True)
        result_cold = decide(cold, now=8, weights=CONFIG["weights"], thresholds=CONFIG["thresholds"],
                             retrieve_cost_ms=5, recompute_cost_ms=40,
                             node_load=0, capacity_bytes=24 * 1048576,
                             local_capacity_available=True, remote_available=True)
        self.assertGreater(result_hot.score, result_cold.score)
        self.assertNotEqual(result_hot.action, "EVICT")

    def test_prefetch_only_when_proactive_and_likely_reuse(self):
        kv = KVObject("hot", "p", 1048576, 4096, current_location="REMOTE")
        for now in range(10):
            kv.record_access(now, local_hit=False)
        common = dict(now=10, weights=CONFIG["weights"], thresholds=CONFIG["thresholds"],
                      retrieve_cost_ms=5, recompute_cost_ms=300, node_load=0,
                      capacity_bytes=24 * 1048576, local_capacity_available=True,
                      remote_available=True)
        self.assertEqual(decide(kv, on_demand=False, **common).action, "PREFETCH")
        self.assertEqual(decide(kv, on_demand=True, **common).action, "FETCH")

    def test_complete_eviction_requires_cheap_recompute(self):
        kv = KVObject("cold", "p", 1048576, 1024, current_location="LOCAL")
        common = dict(now=10, weights=CONFIG["weights"], thresholds=CONFIG["thresholds"],
                      node_load=1, capacity_bytes=24 * 1048576,
                      local_capacity_available=True, remote_available=True)
        self.assertEqual(decide(kv, retrieve_cost_ms=60, recompute_cost_ms=50, **common).action, "EVICT")
        self.assertEqual(decide(kv, retrieve_cost_ms=600, recompute_cost_ms=500, **common).action, "REMOTE_KEEP")

    def test_same_seed_is_reproducible(self):
        scenario = load_scenario(ROOT / "workloads" / "agent.json")
        costs = CostModel(ROOT / "results" / "csv" / "store_benchmark.csv")
        one = simulate(scenario, "R3-KV + Adaptive", CONFIG, costs)
        two = simulate(scenario, "R3-KV + Adaptive", CONFIG, costs)
        self.assertEqual(one, two)


class AdaptiveTests(unittest.TestCase):
    def controller(self):
        return AdaptiveWeightController(dict(CONFIG["weights"]), **CONFIG["adaptive"])

    def test_pressure_increases_size_weight_with_bounds(self):
        controller = self.controller()
        old = controller.weights["size"]
        for step in range(20):
            controller.update({"memory_pressure": 0.95}, step)
        self.assertGreater(controller.weights["size"], old)
        self.assertAlmostEqual(sum(controller.weights.values()), 1.0)
        self.assertTrue(all(controller.min_weight <= w <= controller.max_weight for w in controller.weights.values()))
        self.assertLessEqual(controller.weights["size"] - old, 10 * controller.step + 1e-9)

    def test_hotspot_increases_load_weight(self):
        controller = self.controller()
        old = controller.weights["load"]
        controller.update({"hotspot_ratio": 2.5}, 1)
        events = controller.update({"hotspot_ratio": 2.5}, 2)
        self.assertGreater(controller.weights["load"], old)
        self.assertEqual(events[0]["trigger_metric"], "hotspot_ratio")
        self.assertEqual(events[0]["evidence"], "SIMULATED_FEEDBACK")


if __name__ == "__main__":
    unittest.main()
