"""Bounded EWMA-driven weight updates with an auditable event log."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from cachepilot.algorithms.r3kv import WEIGHT_NAMES, clamp01


@dataclass
class AdaptiveWeightController:
    weights: dict[str, float]
    targets: Mapping[str, float]
    step: float = 0.04
    min_weight: float = 0.05
    max_weight: float = 0.50
    alpha: float = 0.45
    persistence: int = 2
    ewma: dict[str, float] = field(default_factory=dict)
    streaks: dict[str, int] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if set(self.weights) != set(WEIGHT_NAMES):
            raise ValueError(f"weights must contain {WEIGHT_NAMES}")
        if abs(sum(self.weights.values()) - 1.0) > 1e-8:
            raise ValueError("initial weights must sum to 1")
        if any(not self.min_weight <= w <= self.max_weight for w in self.weights.values()):
            raise ValueError("initial weights are outside configured bounds")

    def _increase(self, name: str) -> bool:
        old = self.weights[name]
        delta = min(self.step, self.max_weight - old)
        donors = [k for k in WEIGHT_NAMES if k != name and self.weights[k] > self.min_weight]
        remaining = delta
        for donor in sorted(donors, key=lambda k: self.weights[k], reverse=True):
            take = min(remaining, self.weights[donor] - self.min_weight)
            self.weights[donor] -= take
            remaining -= take
            if remaining <= 1e-12:
                break
        moved = delta - remaining
        self.weights[name] += moved
        return moved > 1e-12

    def update(self, metrics: Mapping[str, float], timestamp: float) -> list[dict]:
        rules = (
            ("memory_pressure", "size", "Memory pressure stayed above target."),
            ("p95_retrieval_ms", "saving", "Remote retrieval p95 stayed above target."),
            ("hotspot_ratio", "load", "Source hotspot ratio stayed above target."),
            ("recompute_time_ms", "saving", "Recompute time stayed above target."),
            ("repeated_reuse", "reuse", "Repeated reuse stayed above target."),
        )
        emitted = []
        for metric, weight, reason in rules:
            if metric not in metrics:
                continue
            value = float(metrics[metric])
            previous = self.ewma.get(metric, value)
            smooth = self.alpha * value + (1 - self.alpha) * previous
            self.ewma[metric] = smooth
            self.streaks[metric] = self.streaks.get(metric, 0) + 1 if smooth > self.targets[metric] else 0
            if self.streaks[metric] < self.persistence:
                continue
            old = dict(self.weights)
            if self._increase(weight):
                event = {
                    "timestamp": timestamp,
                    "old_weights": old,
                    "new_weights": dict(self.weights),
                    "trigger_metric": metric,
                    "trigger_value": round(smooth, 6),
                    "reason": reason,
                    "evidence": "SIMULATED_FEEDBACK",
                }
                self.events.append(event)
                emitted.append(event)
            self.streaks[metric] = 0
        return emitted
