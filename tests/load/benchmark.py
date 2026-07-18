"""Small HTTP benchmark for a running local API.

Usage: python tests/load/benchmark.py
"""

import asyncio
import json
import os
import statistics
import time

import httpx

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
CONCURRENCY = int(os.getenv("CONCURRENCY", "20"))
REQUESTS = int(os.getenv("REQUESTS", "400"))


async def request_once(client: httpx.AsyncClient, latencies: list[float]) -> bool:
    started = time.perf_counter()
    try:
        response = await client.get("/api/analytics/overview")
        return response.status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        latencies.append((time.perf_counter() - started) * 1000)


async def main() -> None:
    latencies: list[float] = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10, trust_env=False) as client:
        async def guarded_request() -> bool:
            async with semaphore:
                return await request_once(client, latencies)

        started = time.perf_counter()
        results = await asyncio.gather(*(guarded_request() for _ in range(REQUESTS)))
        duration = time.perf_counter() - started

    ordered = sorted(latencies)
    percentile_index = max(0, int(len(ordered) * 0.95) - 1)
    report = {
        "endpoint": "GET /api/analytics/overview",
        "requests": REQUESTS,
        "concurrency": CONCURRENCY,
        "duration_seconds": round(duration, 3),
        "requests_per_second": round(REQUESTS / duration, 2),
        "success_rate": round(sum(results) / REQUESTS, 4),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2),
            "p50": round(statistics.median(latencies), 2),
            "p95": round(ordered[percentile_index], 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
