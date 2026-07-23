"""Compare two benchmark JSON reports without hiding regressions."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))["summary"]
    after = json.loads(args.after.read_text(encoding="utf-8"))["summary"]

    def change(old: float, new: float) -> float:
        return round((new - old) / old * 100, 2) if old else 0.0

    comparison = {
        "qps": {"before": before["requests_per_second"], "after": after["requests_per_second"], "change_percent": change(before["requests_per_second"], after["requests_per_second"])},
        "p95_ms": {"before": before["latency_ms"]["p95"], "after": after["latency_ms"]["p95"], "change_percent": change(before["latency_ms"]["p95"], after["latency_ms"]["p95"])},
        "success_rate": {"before": before["success_rate"], "after": after["success_rate"]},
    }
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
