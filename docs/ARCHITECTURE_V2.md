# CachePilot 2.0 Architecture and Evidence

## Data flow

`workloads/*.json` → seeded request trace → `KVObject` state → reuse / retrieve / recompute estimates → R³-KV score and action → simulated local/remote tier → feedback window → bounded adaptive update → JSONL replay and policy summary → Streamlit.

The V1 Mooncake Store benchmark remains independent and unchanged. `CostModel` reads its historical CSV for calibration. There is no live Mooncake KV mutation in V2.

## R³-KV

For object `k`, `P_reuse(k)` combines bounded frequency, recency, reuse-interval and history signals. `C_retrieve(k,n)` is estimated from the closest historical Store size/batch-1 row, adjusted by an explicit scenario network factor and simulated source load. `C_recompute(k)` equals `prefix_tokens × prefill_ms_per_token` from the V1 prefix model. All costs are milliseconds.

`B(k) = P_reuse(k) × max(C_recompute(k) − C_retrieve(k,n), 0)`

`ValueDensity(k) = B(k) / size_MiB(k)`

The normalized score is:

`Score = w_reuse × P_reuse + w_saving × clamp(B/C_recompute) + w_locality × locality − w_load × load − w_size × clamp(size/capacity)`

Every component, input cost, score, action, and reason is logged in each replay event. Thresholds and initial weights are configurable in `configs/default.json`. A local hit may be RETAIN, REMOTE_KEEP, or EVICT; complete EVICT requires both low reuse probability and cheap recomputation, while other low-scoring objects are offloaded. On a miss, FETCH wins only if a remote copy exists and estimated retrieve cost is below recompute; otherwise RECOMPUTE. PREFETCH is a separate proactive simulated action for a previously reused remote object with high predicted near-term reuse, available bandwidth/capacity, and cheaper retrieval. The action names in JSONL are **recommendations and simulated state transitions**, not executed Mooncake API operations.

## Adaptive controller

Every 12 requests, feedback uses memory pressure, retrieval p95, source hotspot ratio, recompute time and repeated reuse. EWMA smooths each metric; two consecutive windows above its target trigger a bounded increase to the related weight. The controller takes mass from other weights down to their minimum, keeps each weight in `[0.05, 0.50]`, and preserves sum 1. An event contains old/new weights, timestamp, trigger metric/value and reason. These defaults are demonstration settings, not scientifically optimized parameters.

## Policy Lab fairness

All policies use the same seeded object/request trace, capacity and cost model. Random, Nearest, Reuse-aware and CachePilot V1 adapt the V1 **source-selection** logic to a common LRU cache-admission layer. R³-KV additionally decides admission/retention/recompute/prefetch; thus the comparison shows an end-to-end prototype policy difference, not an isolated source-selection ablation. Random has an independent reproducible RNG stream. Simulation outputs must not be quoted as live Mooncake or model-serving gains.

## Evidence audit

- Historical V1 Store CSV/PNG: **HISTORICAL REAL MOONCAKE**, measured on AutoDL RTX 4090 in July 2026.
- V2 retrieve cost: **ESTIMATED FROM HISTORICAL MOONCAKE**, with scenario assumptions; not current GPU latency.
- V2 recompute and TTFT: **ESTIMATED FROM V1 PREFIX MODEL**; no PyTorch model is timed here.
- V2 cache state, actions, traffic, hit rate, source hotspot, comparison: **SIMULATED SHARED TRACE**.
- Dashboard playback: **REPLAY OF SIMULATION**, reading precomputed JSONL. It is not a live service.

## Known limits

No online vLLM/SGLang adapter, real Mooncake tier actions, multi-node serving, trained reuse predictor, or end-to-end LLM TTFT measurement. The original Store benchmark can still be rerun separately when a Mooncake service is available. Prefetch and eviction policies need validation on real traces and stronger cost calibration; some current scenarios do not beat Nearest or V1. Negative results are retained rather than hidden.
