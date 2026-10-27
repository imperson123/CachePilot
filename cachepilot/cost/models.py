"""Cost estimates with explicit provenance."""

from __future__ import annotations

import csv
from pathlib import Path


class CostModel:
    def __init__(self, store_csv: Path | None = None, prefill_ms_per_token: float = 0.08):
        self.prefill_ms_per_token = prefill_ms_per_token
        self.store_rows: list[dict] = []
        if store_csv and store_csv.exists():
            with store_csv.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    try:
                        if int(row["return_code"]) == 0 and int(row["batch_size"]) == 1:
                            self.store_rows.append({
                                "value_size": int(row["value_size"]),
                                "p50_ms": float(row["lat_p50"]),
                                "mib_s": float(row["mib_s"]),
                            })
                    except (ValueError, KeyError, TypeError):
                        continue

    def retrieve(self, size_bytes: int, network_factor: float = 1.3) -> tuple[float, str]:
        size_mb = size_bytes / 1048576.0
        if self.store_rows:
            row = min(self.store_rows, key=lambda r: abs(r["value_size"] - size_bytes))
            transfer_ms = size_mb / max(row["mib_s"], 1e-6) * 1000.0
            # Extra network factor is a scenario assumption, not a new measurement.
            return max(row["p50_ms"], transfer_ms) * network_factor, "ESTIMATED_FROM_HISTORICAL_MOONCAKE"
        return 2.0 + 0.15 * size_mb, "SIMULATED_FALLBACK"

    def recompute(self, prefix_tokens: int) -> tuple[float, str]:
        return max(0.0, prefix_tokens * self.prefill_ms_per_token), "ESTIMATED_FROM_V1_PREFIX_MODEL"
