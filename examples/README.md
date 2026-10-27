# Examples

Run `python -m cachepilot.replay.generate_demo --scenario burst` to create `results/replay/burst.jsonl` and `policy_summary.csv`. Each JSONL line is a replay event with request ID, KV ID, action, state transitions, score components, weights, metrics, and evidence tags. Open `dashboard.py` and select Bursty Serving to inspect it interactively.

For a real Mooncake Store run, follow the original `README.md` setup for `mooncake_master` and `benchmark/mooncake_store_runner.py`; do not present replay output as a Store measurement.
