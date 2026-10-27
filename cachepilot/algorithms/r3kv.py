"""Explainable Reuse-Retrieve-Recompute decisions for KV objects."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping


WEIGHT_NAMES = ("reuse", "saving", "locality", "load", "size")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class KVObject:
    kv_id: str
    prefix_id: str
    size_bytes: int
    prefix_tokens: int
    access_count: int = 0
    last_access_timestamp: float | None = None
    reuse_count: int = 0
    reuse_ewma: float = 0.0
    reuse_interval_history: list[float] = field(default_factory=list)
    hit_count: int = 0
    miss_count: int = 0
    current_location: str = "REMOTE"
    locality: float = 0.0
    source_node: int = 0
    retrieve_latency_ms: float = 0.0
    estimated_recompute_latency_ms: float = 0.0
    predicted_reuse_probability: float = 0.0
    value_score: float = 0.0
    recommended_action: str = ""
    actual_action: str = ""
    decision_reason: str = ""

    def record_access(self, timestamp: float, local_hit: bool) -> None:
        reused = self.last_access_timestamp is not None
        self.reuse_ewma = 0.35 * float(reused) + 0.65 * self.reuse_ewma
        if reused:
            self.reuse_count += 1
            self.reuse_interval_history.append(timestamp - self.last_access_timestamp)
            self.reuse_interval_history = self.reuse_interval_history[-16:]
        self.access_count += 1
        self.last_access_timestamp = timestamp
        if local_hit:
            self.hit_count += 1
        else:
            self.miss_count += 1


def estimate_reuse_probability(kv: KVObject, now: float, horizon: float = 12.0) -> float:
    """A bounded, interpretable online estimate; no learned model is implied."""
    if kv.last_access_timestamp is None:
        return 0.08
    age = max(0.0, now - kv.last_access_timestamp)
    frequency = 1.0 - math.exp(-kv.access_count / 4.0)
    recency = math.exp(-age / max(horizon, 1.0))
    if kv.reuse_interval_history:
        mean_interval = sum(kv.reuse_interval_history) / len(kv.reuse_interval_history)
        interval = math.exp(-age / max(mean_interval * 2.0, 1.0))
    else:
        interval = 0.25
    history = 1.0 - math.exp(-kv.reuse_count / 3.0)
    return clamp01(0.08 + 0.24 * frequency + 0.20 * recency + 0.18 * interval + 0.16 * history + 0.14 * kv.reuse_ewma)


@dataclass(frozen=True)
class Decision:
    action: str
    score: float
    components: dict[str, float]
    reuse_probability: float
    expected_saved_ms: float
    value_density_ms_per_mb: float
    retrieve_cost_ms: float
    recompute_cost_ms: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "score": round(self.score, 6),
            "components": {k: round(v, 6) for k, v in self.components.items()},
            "reuse_probability": round(self.reuse_probability, 6),
            "expected_saved_ms": round(self.expected_saved_ms, 6),
            "value_density_ms_per_mb": round(self.value_density_ms_per_mb, 6),
            "retrieve_cost_ms": round(self.retrieve_cost_ms, 6),
            "recompute_cost_ms": round(self.recompute_cost_ms, 6),
            "reason": self.reason,
        }


def decide(
    kv: KVObject,
    *,
    now: float,
    weights: Mapping[str, float],
    thresholds: Mapping[str, float],
    retrieve_cost_ms: float,
    recompute_cost_ms: float,
    node_load: float,
    capacity_bytes: int,
    local_capacity_available: bool,
    remote_available: bool,
    bandwidth_available: bool = True,
    on_demand: bool = True,
) -> Decision:
    p_reuse = estimate_reuse_probability(kv, now)
    retrieve = max(0.0, retrieve_cost_ms)
    recompute = max(0.0, recompute_cost_ms)
    saved = p_reuse * max(recompute - retrieve, 0.0)
    size_mb = max(kv.size_bytes / 1048576.0, 1e-9)
    density = saved / size_mb
    normalized_saving = clamp01(saved / max(recompute, 1e-9))
    locality = clamp01(kv.locality)
    load = clamp01(node_load)
    size_cost = clamp01(kv.size_bytes / max(capacity_bytes, 1))
    components = {
        "reuse": weights["reuse"] * p_reuse,
        "saving": weights["saving"] * normalized_saving,
        "locality": weights["locality"] * locality,
        "load": -weights["load"] * load,
        "size": -weights["size"] * size_cost,
    }
    score = sum(components.values())

    if kv.current_location == "LOCAL":
        if score >= thresholds["retain_score"] and local_capacity_available:
            action = "RETAIN"
            reason = "High reuse-adjusted saving supports keeping this KV local."
        elif score >= thresholds["remote_keep_score"]:
            action = "REMOTE_KEEP"
            reason = "Moderate value favors the lower-cost remote tier."
        elif p_reuse <= thresholds["evict_max_reuse_probability"] and recompute <= thresholds["evict_max_recompute_ms"]:
            action = "EVICT"
            reason = "Low reuse and cheap recomputation favor complete eviction."
        else:
            action = "REMOTE_KEEP"
            reason = "Local value is low, but recomputation is costly enough to keep a remote copy."
    elif remote_available:
        near = bool(kv.reuse_interval_history) and kv.last_access_timestamp is not None and (
            now - kv.last_access_timestamp
            <= max(kv.reuse_interval_history[-1], 1.0) * thresholds["prefetch_interval_factor"]
        )
        if (
            not on_demand
            and
            p_reuse >= thresholds["prefetch_probability"]
            and near
            and bandwidth_available
            and local_capacity_available
            and retrieve < recompute
        ):
            action = "PREFETCH"
            reason = "Likely near-term reuse and cheaper retrieval justify prefetch."
        elif retrieve < recompute:
            action = "FETCH"
            reason = "Remote retrieval is cheaper than recomputing the prefix."
        else:
            action = "RECOMPUTE"
            reason = "Recomputing is no slower than remote retrieval."
    else:
        action = "RECOMPUTE"
        reason = "No remote copy is available, so the prefix must be recomputed."

    kv.predicted_reuse_probability = p_reuse
    kv.value_score = score
    kv.recommended_action = action
    kv.decision_reason = reason
    kv.retrieve_latency_ms = retrieve
    kv.estimated_recompute_latency_ms = recompute
    return Decision(action, score, components, p_reuse, saved, density, retrieve, recompute, reason)
