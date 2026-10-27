# Demo and Run Guide

## Run

Windows PowerShell from repository root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m cachepilot.replay.generate_demo
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Linux / WSL:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m cachepilot.replay.generate_demo
python -m streamlit run dashboard.py
```

Use `--scenario burst` to regenerate one scenario, or omit it for all four. Use `--out-dir` to redirect replay output. The committed sample replay files allow opening the Dashboard without regeneration. Run tests with `python -m unittest discover -s tests -v`.

## 3–5 minute competition flow

1. Open 2.0 Console. State clearly that the animated view is a **replay of simulation**, while archived Mooncake Store results are historical real measurements. Show Workload, memory, hit rate and estimated TTFT.
2. Select Long-context QA. Play at ×4, then Jump to request 100. Point out request → KV profiler → R³-KV → action → tier and the lifecycle transition list.
3. Open KV State Explorer. Filter HOT/WARM/COLD, inspect a KV's size, reuse probability, retrieve/recompute cost and current tier.
4. Open R³-KV Decision. Explain `B=P_reuse×max(C_recompute−C_retrieve,0)` and the positive/negative score components. State that FETCH/RECOMPUTE/RETAIN are simulated decisions, not Mooncake mutations.
5. Open Adaptive Controller at request 100. Show EWMA-triggered weight changes and event reasons; switch to Bursty Serving to show a latency/load shift.
6. Open Policy Lab. Compare six policies on the same seed. Acknowledge where R³-KV is weaker; the current value is an auditable decision framework, not a proven speedup.
7. Switch to V1 Evaluation Archive, open Store Benchmark, and show the historical real Mooncake CSV/plots. Close by stating the next engineering step: real serving adapter and online validation.

## Reproducibility and safety

Do not run `scripts/run_all.sh` merely to start the Dashboard: it invokes Store experiments and can overwrite `results/csv/store_benchmark.csv` if a Mooncake service is configured. Use `scripts/run_demo.*` or the commands above for the replay. The V1 Store scripts require a running `mooncake_master` and matching Python binding. No project script performs model training or downloads an LLM.
