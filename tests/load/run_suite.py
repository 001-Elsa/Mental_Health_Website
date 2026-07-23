"""Run every benchmark scenario and keep a machine-readable aggregate."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from benchmark import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenarios", type=Path, default=Path(__file__).with_name("scenarios.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/latest.json"))
    args = parser.parse_args()
    definitions = json.loads(args.scenarios.read_text(encoding="utf-8"))
    reports = []
    for scenario in definitions["scenarios"]:
        config = {
            "base_url": args.base_url,
            "endpoint": scenario["endpoint"],
            "requests": scenario["requests"],
            "concurrency": scenario["concurrency"],
            "warmup": scenario["warmup"],
            "timeout_seconds": scenario.get("timeout_seconds", 10),
            "token": "",
        }
        reports.append({"name": scenario["name"], "report": asyncio.run(run_benchmark(config))})
    aggregate = {
        "schema_version": "1.0",
        "scenario_version": definitions["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(reports)} scenarios to {args.output}")
    return 0 if all(item["report"]["summary"]["success_rate"] == 1 for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
