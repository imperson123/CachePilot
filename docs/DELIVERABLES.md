# CachePilot 2.0 Delivery Record

## 1. Original runtime result

V1 ran at `http://localhost:8501` before modifications. The original `main` checkout was clean at `e8df0fb003325c738dcd3ac74165911df438b5f8`. Five pages were visited and screenshotted under `docs/screenshots/v1/`. Full source/data audit: [V1_RUNTIME_AUDIT.md](V1_RUNTIME_AUDIT.md). The historical Store results are real measurements from AutoDL RTX 4090, not new local measurements.

## 2. V1 to V2 change summary

The original `benchmark/`, historical `results/csv/`, `results/figures/`, and V1 page functions remain. `dashboard.py` adds a workspace selector and delegates the new console to `cachepilot/ui/dashboard_v2.py`. New modules implement R³-KV decisions, adaptive weights, cost provenance, replay and policy simulation. The original `main` checkout remains clean; V2 is on `openatom-2026`.

## 3. R³-KV algorithm

Code: `cachepilot/algorithms/r3kv.py`. `P_reuse` combines frequency, recency, reuse interval, history and EWMA. `B = P_reuse × max(C_recompute − C_retrieve, 0)`, `ValueDensity = B / size_MiB`. The score has separately logged reuse, saving, locality, load and size components. The rule engine emits RETAIN, REMOTE_KEEP, EVICT, FETCH, RECOMPUTE or PREFETCH with a human-readable reason. Complete EVICT requires low reuse and cheap recomputation. Details: [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).

## 4. Adaptive controller

Code: `cachepilot/algorithms/adaptive_weights.py`. EWMA feedback and two-window persistence trigger bounded updates to reuse/saving/load/size weights. The weight sum remains 1; every change logs old/new vectors, trigger and reason. These are configured in `configs/default.json`.

## 5. New Dashboard

Five tabs: Overview (request flow, KPIs, actions, trends, lifecycle), KV State Explorer (filterable table), R³-KV Decision (score decomposition), Adaptive Controller (weight chart and event log), Policy Lab (shared-trace comparison). `V1 Evaluation Archive` is a separate workspace choice. Screenshots: `docs/screenshots/v2/overview.jpg`, `kv_explorer.jpg`, `decision_full.jpg`, `adaptive.jpg`, `adaptive_events.jpg`, `policy_lab.jpg`.

## 6. Demo Replay

Run `python -m cachepilot.replay.generate_demo`; open the dashboard and use Play, Pause, ×1/×2/×4, Reset or Jump. Four seeded scenarios are in `workloads/`. JSONL and summary outputs are in `results/replay/`. The UI says **REPLAY OF SIMULATION** and does not claim live service status.

## 7. Benchmark / policy comparison

These are **simulated shared-trace estimates**, not Mooncake or end-to-end model measurements. On 160 Bursty Serving requests (seed 44), R³-KV had estimated mean TTFT 22.447 ms versus Nearest 22.6774 ms, but 67.0 versus 54.0 MiB remote traffic and 0.68125 versus 0.70625 local hit rate. On Multi-turn Agent (seed 43), R³-KV + Adaptive had 21.2128 ms versus Nearest 20.8008 ms; it was not better. Long-context QA also did not show a decisive R³-KV improvement. The full 24-row table is `results/replay/policy_summary.csv`. Adaptive weights do change, but the current scenario outcomes do not establish a general performance gain.

## 8. Data provenance audit

Historical V1 Store CSV and PNG: **HISTORICAL REAL MOONCAKE** (AutoDL RTX 4090). V2 retrieve cost: **ESTIMATED FROM HISTORICAL MOONCAKE** with scenario network factor. V2 recompute/TTFT: **ESTIMATED FROM V1 PREFIX MODEL**. Policy outcomes and cache states: **SIMULATED SHARED TRACE**. Dashboard playback: **REPLAY OF SIMULATION**. No current-machine Mooncake Store measurement was made during this work.

## 9. Repository structure

```text
CachePilot-2.0/
  benchmark/              unchanged V1 measurement/evaluation code
  cachepilot/
    algorithms/           R³-KV and adaptive weights
    cost/                 provenance-aware cost estimates
    replay/               seeded trace simulator and JSONL generator
    ui/                   Streamlit 2.0 views
  configs/                thresholds and weights
  workloads/              four scenario definitions
  results/csv/            unchanged V1 historical CSV
  results/figures/        unchanged V1 figures
  results/replay/         generated demo events and summary
  docs/                  V1 audit, V2 architecture, screenshots, demo guide
  tests/                 eight unit tests
  scripts/               V1 scripts plus run_demo.bat/sh
  dashboard.py            V2/V1 workspace selector
```

## 10. How to run

Windows: `scripts\run_demo.bat` after `python -m pip install -r requirements.txt` in a virtual environment. Linux/WSL: `bash scripts/run_demo.sh` after installing requirements. For explicit Python commands and the existing-venv option, see [DEMO_FLOW.md](DEMO_FLOW.md). The running development URL is `http://127.0.0.1:8502`; normal script startup defaults to port 8501.

## 11. Competition demo flow

Open Overview and state provenance; replay Long-context QA; inspect a KV in Explorer; explain one R³-KV score; show adaptive events after Jump to request 100; compare policies honestly in Policy Lab; switch to V1 Store Benchmark to show actual archived Mooncake data. A timed 3–5 minute flow is in [DEMO_FLOW.md](DEMO_FLOW.md).

## 12. Remaining risks

No online Mooncake tier action, vLLM/SGLang adapter, real multi-node or Video-LMM execution, actual LLM prefill timing, or proof of generalized speedup. Historical Store logs remain in the original local checkout but were ignored by the original repository's `.gitignore`; V1 CSV and figures are tracked and preserved. A future real-trace evaluation must validate cost estimates, prefetch accuracy, tail latency and memory safety before competition claims are strengthened.
