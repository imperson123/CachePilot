# CachePilot V1 Runtime Audit

Audited on Windows on 2026-10-27 before any functional code changes. The original V1 checkout was on branch `main`, commit `e8df0fb003325c738dcd3ac74165911df438b5f8`, with a clean worktree. A `cachepilot-v1-backup` ref points to that commit. The 2.0 implementation uses an isolated `openatom-2026` worktree.

The repository's `scripts/run_dashboard.bat` launched successfully at `http://localhost:8501`. Its existing `.venv` had Python 3.10.11, Streamlit 1.59.1, pandas 2.3.3, NumPy 2.2.6, and Matplotlib 3.10.9. All five original pages were opened. Screenshots are in `docs/screenshots/v1/`.

| Path | Verified role | Evidence type | 2.0 treatment |
|---|---|---|---|
| `benchmark/mooncake_store_runner.py` | Subprocess wrapper around official `mooncake-store/benchmarks/store_kv_bench.py` | Real benchmark **when Mooncake service is running** | Retained unchanged |
| `benchmark/parse_store_output.py`, `metrics.py`, `plot_results.py` | Parse logs, write CSV/figures | Data processing | Retained unchanged |
| `benchmark/prefix_reuse_benchmark.py` | Formula over prefix tokens, hit ratio, assumed prefill/get cost | Controlled evaluation / estimated | Retained unchanged; recompute model reused |
| `benchmark/retrieval_scheduler_sim.py` | Generated blocks/requests; four source-selection policies | Offline simulation | Retained unchanged; V1 baseline concept reused in shared trace |
| `dashboard.py` | Five-page CSV/PNG viewer | Frontend, not an online controller | V1 page functions retained; 2.0 entry added |
| `results/csv/` | 7 CSV files: five Store files, Prefix 25 rows, Scheduler 4 rows | Historical real Store vs simulated Prefix/Scheduler | Retained unchanged |
| `results/figures/` | 7 PNG plots | Mixed provenance matching CSV | Retained unchanged |
| `results/logs/` | Raw Store logs and scheduler decision logs in original checkout | Historical raw evidence | Original checkout retained; `.gitignore` excludes bulk logs from worktree tracking |
| `scripts/` | Store verify/perf, Prefix, Scheduler, plot, run_all, Windows/Linux dashboard launch | Reproduction | Retained; V2 demo launch added |
| `README.md`, `DESIGN.md`, `EVALUATION.md` | V1 purpose, architecture, metrics and historical results | Documentation | Preserved; V2 intro/docs added |

## Original Dashboard

| Page | Source | Interaction | Limitation |
|---|---|---|---|
| Overview | `store_verify_real.csv`, `store_benchmark.csv` | Read-only metrics | Historical RTX 4090 environment is hard-coded as page content |
| Store Benchmark | `store_benchmark.csv`, two PNGs | Table and CSV-derived line charts | No experiment launch or live measurement |
| Prefix Reuse Evaluation | `prefix_reuse.csv`, two PNGs | Table viewer | Estimated TTFT, no timed LLM prefill |
| Retrieval Scheduler Evaluation | `retrieval_scheduler.csv`, three PNGs | Table viewer | Offline simulated policy results; no real cluster |
| Implementation | Static text | None | Commands and topology are documentation only |

No replay, live refresh, cache-state explorer, action policy, or adaptive controller existed. The original Store path is genuinely backed by `MooncakeDistributedStore` through the official benchmark, but **opening the Dashboard did not rerun it**. The original source and historical CSV/figures were not overwritten.
