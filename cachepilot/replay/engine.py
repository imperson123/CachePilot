"""Shared-trace policy simulation; never presented as live Mooncake serving."""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from cachepilot.algorithms.adaptive_weights import AdaptiveWeightController
from cachepilot.algorithms.r3kv import KVObject, clamp01, decide, estimate_reuse_probability
from cachepilot.cost.models import CostModel


POLICIES = ("Random", "Nearest", "Reuse-aware", "CachePilot V1", "R3-KV", "R3-KV + Adaptive")


@dataclass(frozen=True)
class TraceRequest:
    index: int
    kv_id: str
    local_node: int


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def make_trace(scenario: dict) -> tuple[dict[str, KVObject], list[TraceRequest]]:
    rng = random.Random(scenario["seed"])
    objects = {}
    for index in range(scenario["objects"]):
        kv_id = f"KV-{index:03d}"
        size_mb = rng.choice(scenario["size_mb"])
        objects[kv_id] = KVObject(
            kv_id=kv_id,
            prefix_id=f"P-{index // 3:03d}",
            size_bytes=int(size_mb * 1048576),
            prefix_tokens=rng.choice(scenario["prefix_tokens"]),
            source_node=index % 4,
        )
    hot_count = max(1, int(scenario["objects"] * scenario["hot_fraction"]))
    trace = []
    for index in range(scenario["requests"]):
        if "Video-like" in scenario["name"] and index % 25 < 8:
            chosen = (index // 25 * 7 + index % 8) % scenario["objects"]
        elif rng.random() < scenario["hot_probability"]:
            chosen = rng.randrange(hot_count)
        else:
            chosen = rng.randrange(scenario["objects"])
        trace.append(TraceRequest(index, f"KV-{chosen:03d}", rng.randrange(4)))
    return objects, trace


def _clone_objects(objects: dict[str, KVObject]) -> dict[str, KVObject]:
    return {key: KVObject(**{k: v for k, v in vars(obj).items() if k != "reuse_interval_history"}) for key, obj in objects.items()}


def _choose_source(
    policy: str,
    kv: KVObject,
    local_node: int,
    base_cost: float,
    loads: Counter,
    weights: dict[str, float],
    rng: random.Random,
) -> tuple[int, float]:
    replicas = sorted({kv.source_node, (kv.source_node + 2) % 4})
    latencies = {
        node: base_cost * (1.0 + 0.12 * abs(node - local_node)) + 0.15 * loads[node]
        for node in replicas
    }
    if policy == "Random":
        chosen = rng.choice(replicas)
    elif policy in ("Nearest", "Reuse-aware"):
        chosen = min(replicas, key=lambda node: latencies[node])
    elif policy == "CachePilot V1":
        # Reuse and importance are object-constant here; this mirrors V1 source scoring.
        chosen = max(
            replicas,
            key=lambda node: 0.5 * min(kv.access_count / 10, 1)
            + 0.3 * min(kv.reuse_count / 10, 1)
            - 0.2 * clamp01(latencies[node] / 100)
            - 0.05 * loads[node]
            + (0.15 if node == local_node else 0),
        )
    else:
        chosen = min(
            replicas,
            key=lambda node: weights["saving"] * clamp01(latencies[node] / 100)
            + weights["load"] * clamp01(loads[node] / 20)
            - weights["locality"] * (1 if node == local_node else 0),
        )
    return chosen, latencies[chosen]


def simulate(
    scenario: dict,
    policy: str,
    config: dict,
    cost_model: CostModel,
) -> tuple[list[dict], dict]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    template, trace = make_trace(scenario)
    objects = _clone_objects(template)
    rng = random.Random(scenario["seed"] + POLICIES.index(policy) * 1009)
    capacity = int(config["capacity_mb"] * 1048576)
    adaptive = policy == "R3-KV + Adaptive"
    is_r3 = policy.startswith("R3-KV")
    controller = AdaptiveWeightController(dict(config["weights"]), **config["adaptive"])
    events: list[dict] = []
    latencies: list[float] = []
    retrieval_latencies: list[float] = []
    actions: Counter = Counter()
    loads: Counter = Counter()
    total_loads: Counter = Counter()
    remote_bytes = 0
    recompute_count = 0
    recompute_time = 0.0
    saved_prefill = 0.0
    local_hits = 0
    prefetch_count = 0
    prefetch_hits = 0
    prefetched: set[str] = set()

    def local_bytes() -> int:
        return sum(obj.size_bytes for obj in objects.values() if obj.current_location == "LOCAL")

    def make_room(needed: int, protected_id: str) -> list[dict]:
        transitions = []
        while local_bytes() + needed > capacity:
            candidates = [obj for obj in objects.values() if obj.current_location == "LOCAL" and obj.kv_id != protected_id]
            if not candidates:
                break
            if policy == "Random":
                victim = rng.choice(candidates)
            elif is_r3:
                victim = min(candidates, key=lambda item: (item.value_score, item.last_access_timestamp or -1))
            else:
                victim = min(candidates, key=lambda item: item.last_access_timestamp or -1)
            old = victim.current_location
            cheap_to_recompute = (
                victim.predicted_reuse_probability <= config["thresholds"]["evict_max_reuse_probability"]
                and victim.estimated_recompute_latency_ms <= config["thresholds"]["evict_max_recompute_ms"]
            )
            victim.current_location = "EVICTED" if is_r3 and cheap_to_recompute else "REMOTE"
            victim.actual_action = "EVICT" if victim.current_location == "EVICTED" else "REMOTE_KEEP"
            actions[victim.actual_action] += 1
            transitions.append({"kv_id": victim.kv_id, "from": old, "to": victim.current_location, "reason": "capacity"})
            prefetched.discard(victim.kv_id)
        return transitions

    for request in trace:
        now = float(request.index)
        kv = objects[request.kv_id]
        before = kv.current_location
        local_hit = before == "LOCAL"
        if local_hit:
            local_hits += 1
            if kv.kv_id in prefetched:
                prefetch_hits += 1
                prefetched.remove(kv.kv_id)
        retrieve_base, retrieve_evidence = cost_model.retrieve(kv.size_bytes, config["network_factor"])
        if scenario["latency_spike_at"] >= 0 and request.index >= scenario["latency_spike_at"]:
            retrieve_base *= scenario["latency_spike_factor"]
        source, retrieve_ms = _choose_source(policy, kv, request.local_node, retrieve_base, loads, controller.weights, rng)
        recompute_ms, recompute_evidence = cost_model.recompute(kv.prefix_tokens)
        kv.locality = 1.0 if source == request.local_node else 0.0
        decision = None
        if is_r3:
            decision = decide(
                kv, now=now, weights=controller.weights, thresholds=config["thresholds"],
                retrieve_cost_ms=retrieve_ms, recompute_cost_ms=recompute_ms,
                node_load=clamp01(loads[source] / max(config["control_window"], 1)),
                capacity_bytes=capacity, local_capacity_available=local_hit or local_bytes() + kv.size_bytes <= capacity,
                remote_available=before != "EVICTED", on_demand=True,
            )
            action = decision.action
        else:
            action = "RETAIN" if local_hit else ("FETCH" if before == "REMOTE" else "RECOMPUTE")
        transitions = []
        processing_state = None
        if local_hit:
            service_ms = config["local_hit_ms"]
            saved_prefill += max(recompute_ms - service_ms, 0)
            if action in ("REMOTE_KEEP", "EVICT"):
                kv.current_location = "REMOTE" if action == "REMOTE_KEEP" else "EVICTED"
                transitions.append({"kv_id": kv.kv_id, "from": before, "to": kv.current_location, "reason": "R3-KV value"})
        elif action == "FETCH":
            processing_state = "FETCHING"
            transitions.append({"kv_id": kv.kv_id, "from": before, "to": processing_state, "reason": action})
            service_ms = retrieve_ms
            retrieval_latencies.append(retrieve_ms)
            loads[source] += 1
            total_loads[source] += 1
            if source != request.local_node:
                remote_bytes += kv.size_bytes
            saved_prefill += max(recompute_ms - retrieve_ms, 0)
        else:
            processing_state = "RECOMPUTING"
            transitions.append({"kv_id": kv.kv_id, "from": before, "to": processing_state, "reason": action})
            service_ms = recompute_ms
            recompute_count += 1
            recompute_time += recompute_ms

        kv.record_access(now, local_hit)
        if not local_hit and kv.size_bytes <= capacity:
            should_admit = not is_r3 or (decision is not None and decision.score >= config["thresholds"]["remote_keep_score"])
            if should_admit:
                transitions.extend(make_room(kv.size_bytes, kv.kv_id))
                if local_bytes() + kv.size_bytes <= capacity:
                    kv.current_location = "LOCAL"
                    transitions.append({"kv_id": kv.kv_id, "from": processing_state, "to": "LOCAL", "reason": action})
        if processing_state and kv.current_location != "LOCAL":
            transitions.append({"kv_id": kv.kv_id, "from": processing_state, "to": kv.current_location, "reason": "not admitted"})
        kv.actual_action = action
        actions[action] += 1
        ttft_ms = service_ms + 20.0
        latencies.append(ttft_ms)
        used = local_bytes()
        recent = retrieval_latencies[-config["control_window"]:]
        adaptive_events = []
        control_feedback = None
        if adaptive and (request.index + 1) % config["control_window"] == 0:
            window = trace[max(0, request.index + 1 - config["control_window"]):request.index + 1]
            repeated = sum(1 for req in window if objects[req.kv_id].reuse_count > 0) / len(window)
            control_feedback = {
                "cache_hit_rate": local_hits / (request.index + 1),
                "p50_retrieval_ms": percentile(recent, 50),
                "memory_pressure": used / capacity,
                "p95_retrieval_ms": percentile(recent, 95),
                "p99_retrieval_ms": percentile(recent, 99),
                "remote_traffic_mb": remote_bytes / 1048576,
                "hotspot_ratio": max(loads.values(), default=0) / max(sum(loads.values()) / 4, 1),
                "recompute_time_ms": recompute_time / max(recompute_count, 1),
                "repeated_reuse": repeated,
                "prefetch_accuracy": prefetch_hits / prefetch_count if prefetch_count else 0.0,
                "estimated_ttft_ms": ttft_ms,
            }
            adaptive_events = controller.update(control_feedback, now)
        if (request.index + 1) % config["control_window"] == 0:
            loads.clear()

        prefetch = None
        if is_r3 and request.index % 5 == 0:
            candidates = [
                obj for obj in objects.values()
                if obj.current_location == "REMOTE" and obj.access_count > 1 and obj.kv_id != kv.kv_id
            ]
            candidates.sort(key=lambda obj: estimate_reuse_probability(obj, now), reverse=True)
            for candidate in candidates:
                base, _ = cost_model.retrieve(candidate.size_bytes, config["network_factor"])
                rec, _ = cost_model.recompute(candidate.prefix_tokens)
                candidate.locality = 0.0
                pd = decide(
                    candidate, now=now, weights=controller.weights, thresholds=config["thresholds"],
                    retrieve_cost_ms=base, recompute_cost_ms=rec, node_load=0,
                    capacity_bytes=capacity, local_capacity_available=candidate.size_bytes <= capacity,
                    remote_available=True, on_demand=False,
                )
                if pd.action == "PREFETCH":
                    transitions.extend(make_room(candidate.size_bytes, candidate.kv_id))
                    if local_bytes() + candidate.size_bytes <= capacity:
                        candidate.current_location = "LOCAL"
                        candidate.actual_action = "PREFETCH"
                        prefetched.add(candidate.kv_id)
                        prefetch_count += 1
                        actions["PREFETCH"] += 1
                        remote_bytes += candidate.size_bytes
                        prefetch = {"kv_id": candidate.kv_id, "decision": pd.as_dict()}
                        transitions.append({"kv_id": candidate.kv_id, "from": "REMOTE", "to": "PREFETCHING", "reason": "PREFETCH"})
                        transitions.append({"kv_id": candidate.kv_id, "from": "PREFETCHING", "to": "LOCAL", "reason": "PREFETCH"})
                        break

        events.append({
            "timestamp": request.index,
            "request_id": f"REQ-{request.index:04d}",
            "kv_id": kv.kv_id,
            "event": "REQUEST",
            "scenario": scenario["name"],
            "policy": policy,
            "evidence": "REPLAY_OF_SIMULATION",
            "cost_evidence": {"retrieve": retrieve_evidence, "recompute": recompute_evidence},
            "state_before": before,
            "state_after": kv.current_location,
            "transitions": transitions,
            "source_node": source,
            "decision": decision.as_dict() if decision else {"action": action, "reason": "V1 baseline on shared simulated trace."},
            "actual_action": action,
            "prefetch": prefetch,
            "adaptive_events": adaptive_events,
            "control_feedback": control_feedback,
            "weights": dict(controller.weights),
            "kv_state": {
                "prefix_id": kv.prefix_id,
                "size_mb": round(kv.size_bytes / 1048576, 3),
                "prefix_tokens": kv.prefix_tokens,
                "reuse_probability": round(kv.predicted_reuse_probability, 4),
                "frequency": kv.access_count,
                "recency": 0,
                "retrieve_cost_ms": round(retrieve_ms, 3),
                "recompute_cost_ms": round(recompute_ms, 3),
                "value_score": round(kv.value_score, 4),
                "location": kv.current_location,
            },
            "metrics": {
                "cache_hit_rate": round(local_hits / (request.index + 1), 6),
                "estimated_ttft_ms": round(ttft_ms, 4),
                "p50_retrieval_ms": round(percentile(retrieval_latencies, 50), 4),
                "p95_retrieval_ms": round(percentile(retrieval_latencies, 95), 4),
                "p99_retrieval_ms": round(percentile(retrieval_latencies, 99), 4),
                "remote_traffic_mb": round(remote_bytes / 1048576, 4),
                "memory_pressure": round(used / capacity, 4),
                "hotspot_ratio": round(max(total_loads.values(), default=0) / max(sum(total_loads.values()) / 4, 1), 4),
                "recompute_volume": recompute_count,
                "recompute_time_ms": round(recompute_time, 4),
                "prefetch_accuracy": round(prefetch_hits / prefetch_count, 4) if prefetch_count else None,
                "active_kv_objects": sum(obj.access_count > 0 for obj in objects.values()),
            },
        })

    summary = {
        "scenario": scenario["name"],
        "policy": policy,
        "evidence": "SIMULATED_SHARED_TRACE",
        "seed": scenario["seed"],
        "requests": len(trace),
        "cache_hit_rate": round(local_hits / len(trace), 6),
        "avg_estimated_ttft_ms": round(sum(latencies) / len(latencies), 4),
        "p95_estimated_ttft_ms": round(percentile(latencies, 95), 4),
        "p99_estimated_ttft_ms": round(percentile(latencies, 99), 4),
        "p50_retrieval_ms": round(percentile(retrieval_latencies, 50), 4),
        "p95_retrieval_ms": round(percentile(retrieval_latencies, 95), 4),
        "p99_retrieval_ms": round(percentile(retrieval_latencies, 99), 4),
        "remote_traffic_mb": round(remote_bytes / 1048576, 4),
        "hotspot_ratio": round(max(total_loads.values(), default=0) / max(sum(total_loads.values()) / 4, 1), 4),
        "recompute_volume": recompute_count,
        "recompute_time_ms": round(recompute_time, 4),
        "saved_prefill_time_ms": round(saved_prefill, 4),
        "memory_occupancy_mb": round(local_bytes() / 1048576, 4),
        "prefetch_hit_rate": round(prefetch_hits / prefetch_count, 4) if prefetch_count else None,
        "action_distribution": dict(actions),
    }
    return events, summary


def load_scenario(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
