#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    ok: bool
    status: int
    latency_ms: float


async def worker(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    stop_at: float,
    results: list[Result],
) -> None:
    while time.time() < stop_at:
        t0 = time.time()
        try:
            r = await client.post(url, json=payload)
            dt = (time.time() - t0) * 1000.0
            results.append(Result(ok=r.status_code == 200, status=r.status_code, latency_ms=dt))
        except Exception:
            dt = (time.time() - t0) * 1000.0
            results.append(Result(ok=False, status=0, latency_ms=dt))


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    k = int(round((p / 100.0) * (len(xs2) - 1)))
    return xs2[max(0, min(k, len(xs2) - 1))]


async def main() -> None:
    ap = argparse.ArgumentParser(description="SignalGate load test profile (no external deps)")
    ap.add_argument("--base-url", default="http://127.0.0.1:8765", help="SignalGate base URL")
    ap.add_argument("--seconds", type=int, default=15, help="Run duration")
    ap.add_argument("--concurrency", type=int, default=25, help="Concurrent workers")
    ap.add_argument("--model", default="signalgate/balanced", help="Virtual model")
    args = ap.parse_args()

    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 16,
    }

    timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results: list[Result] = []
        stop_at = time.time() + args.seconds
        tasks = [
            asyncio.create_task(worker(client, url, payload, stop_at, results))
            for _ in range(args.concurrency)
        ]
        await asyncio.gather(*tasks)

    lat = [r.latency_ms for r in results]
    ok = [r for r in results if r.ok]
    err = [r for r in results if not r.ok]

    print(f"requests={len(results)} ok={len(ok)} err={len(err)}")
    if lat:
        print(
            "latency_ms: "
            f"p50={pct(lat, 50):.1f} "
            f"p95={pct(lat, 95):.1f} "
            f"p99={pct(lat, 99):.1f} "
            f"mean={statistics.mean(lat):.1f}"
        )

    if err:
        codes: dict[int, int] = {}
        for r in err:
            codes[r.status] = codes.get(r.status, 0) + 1
        print("errors_by_status:", dict(sorted(codes.items())))


if __name__ == "__main__":
    asyncio.run(main())
