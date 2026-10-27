"""Generate reproducible JSONL replay and shared-trace policy summaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from cachepilot.cost.models import CostModel
from cachepilot.replay.engine import POLICIES, load_scenario, simulate


ROOT = Path(__file__).resolve().parents[2]


def generate(output_dir: Path, scenario_names: list[str] | None = None) -> None:
    config = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
    costs = CostModel(ROOT / "results" / "csv" / "store_benchmark.csv", config["prefill_ms_per_token"])
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    names = scenario_names or [p.stem for p in sorted((ROOT / "workloads").glob("*.json"))]
    for name in names:
        scenario = load_scenario(ROOT / "workloads" / f"{name}.json")
        for policy in POLICIES:
            events, summary = simulate(scenario, policy, config, costs)
            summaries.append(summary)
            if policy == "R3-KV + Adaptive":
                path = output_dir / f"{name}.jsonl"
                with path.open("w", encoding="utf-8") as handle:
                    for event in events:
                        handle.write(json.dumps(event, ensure_ascii=True) + "\n")
                print(f"Replay: {path} ({len(events)} requests)")
    fields = [key for key in summaries[0] if key != "action_distribution"] + ["action_distribution"]
    with (output_dir / "policy_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            summary = dict(summary)
            summary["action_distribution"] = json.dumps(summary["action_distribution"], sort_keys=True)
            writer.writerow(summary)
    print(f"Policy summary: {output_dir / 'policy_summary.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CachePilot 2.0 simulated demo replay")
    parser.add_argument("--scenario", choices=[p.stem for p in (ROOT / "workloads").glob("*.json")])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results" / "replay")
    args = parser.parse_args()
    generate(args.out_dir, [args.scenario] if args.scenario else None)


if __name__ == "__main__":
    main()
