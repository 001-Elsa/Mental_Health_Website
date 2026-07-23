"""Reproducible HTTP benchmark for a running API.

The command records environment metadata, warm-up settings and every latency
sample so reported percentiles can be recalculated instead of trusted as prose.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


async def run_benchmark(config: dict) -> dict:
    base_url = config["base_url"]
    endpoint = config["endpoint"]
    concurrency = config["concurrency"]
    request_count = config["requests"]
    warmup = config["warmup"]
    timeout = config["timeout_seconds"]
    token = config.get("token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    latencies: list[float] = []
    statuses: list[int] = []
    errors: Counter[str] = Counter()
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False, headers=headers) as client:
        for _ in range(warmup):
            try:
                await client.get(endpoint)
            except httpx.HTTPError:
                pass

        async def request_once() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(endpoint)
                    statuses.append(response.status_code)
                except httpx.HTTPError as exc:
                    errors[type(exc).__name__] += 1
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(request_once() for _ in range(request_count)))
        duration = time.perf_counter() - started

    ordered = sorted(latencies)

    def percentile(fraction: float) -> float:
        index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
        return round(ordered[index], 2)

    successes = sum(200 <= status < 300 for status in statuses)
    return {
        "schema_version": "1.0",
        "label": config.get("label", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "git_revision": git_revision(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or "unknown",
        },
        "config": {key: value for key, value in config.items() if key != "token"},
        "summary": {
            "duration_seconds": round(duration, 3),
            "requests_per_second": round(request_count / duration, 2),
            "success_rate": round(successes / request_count, 4),
            "status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
            "errors": dict(errors),
            "latency_ms": {
                "mean": round(statistics.mean(latencies), 2),
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "p99": percentile(0.99),
                "max": round(max(latencies), 2),
            },
        },
        "latency_samples_ms": [round(value, 3) for value in latencies],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--endpoint", default=os.getenv("ENDPOINT", "/api/health"))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "20")))
    parser.add_argument("--requests", type=int, default=int(os.getenv("REQUESTS", "400")))
    parser.add_argument("--warmup", type=int, default=int(os.getenv("WARMUP", "30")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TIMEOUT_SECONDS", "10")))
    parser.add_argument("--token", default=os.getenv("TOKEN", ""))
    parser.add_argument("--label", default=os.getenv("BENCHMARK_LABEL", ""))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.warmup < 0:
        raise SystemExit("requests/concurrency must be positive and warmup cannot be negative")
    config = {
        "base_url": args.base_url,
        "endpoint": args.endpoint,
        "concurrency": args.concurrency,
        "requests": args.requests,
        "warmup": args.warmup,
        "timeout_seconds": args.timeout,
        "token": args.token,
        "label": args.label,
    }
    report = asyncio.run(run_benchmark(config))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["summary"]["success_rate"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
