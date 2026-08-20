"""
TradeDNA High-Performance Asynchronous Load Testing Harness
Provides precise percentile latency calculation (p50, p90, p95, p99),
concurrency runner, and statistical measurement with zero external bloat.
"""

import time
import asyncio
import statistics
from typing import Callable, Coroutine, Any, Dict, List, Optional


class BenchmarkHarness:
    """Async performance and load testing execution harness."""

    def __init__(self, concurrency: int = 10, total_iterations: int = 100):
        self.concurrency = concurrency
        self.total_iterations = total_iterations
        self.latencies_ms: List[float] = []
        self.errors: List[Exception] = []
        self.status_codes: Dict[int, int] = {}
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    async def run(self, task_fn: Callable[[int], Coroutine[Any, Any, Any]]) -> Dict[str, Any]:
        """Executes task_fn concurrently across worker pool."""
        queue: asyncio.Queue = asyncio.Queue()
        for i in range(self.total_iterations):
            queue.put_nowait(i)

        self.latencies_ms.clear()
        self.errors.clear()
        self.status_codes.clear()

        lock = asyncio.Lock()

        async def worker():
            while not queue.empty():
                try:
                    item_id = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                t0 = time.perf_counter()
                try:
                    res = await task_fn(item_id)
                    dur_ms = (time.perf_counter() - t0) * 1000.0
                    async with lock:
                        self.latencies_ms.append(dur_ms)
                        if hasattr(res, "status_code"):
                            self.status_codes[res.status_code] = self.status_codes.get(res.status_code, 0) + 1
                except Exception as e:
                    dur_ms = (time.perf_counter() - t0) * 1000.0
                    async with lock:
                        self.errors.append(e)
                finally:
                    queue.task_done()

        self.start_time = time.perf_counter()
        workers = [asyncio.create_task(worker()) for _ in range(self.concurrency)]
        await asyncio.gather(*workers)
        self.end_time = time.perf_counter()

        return self.compute_metrics()

    def compute_metrics(self) -> Dict[str, Any]:
        """Calculates precise statistical latency distribution."""
        total_time_sec = max(self.end_time - self.start_time, 0.0001)
        total_completed = len(self.latencies_ms)
        total_failed = len(self.errors)
        total_reqs = total_completed + total_failed

        if not self.latencies_ms:
            return {
                "total_requests": total_reqs,
                "successful_requests": 0,
                "failed_requests": total_failed,
                "throughput_rps": 0.0,
                "error_rate": 1.0 if total_reqs > 0 else 0.0,
                "p50_ms": 0.0,
                "p90_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "avg_ms": 0.0,
            }

        sorted_lat = sorted(self.latencies_ms)
        n = len(sorted_lat)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = int(k)
            c = min(f + 1, n - 1)
            d = k - f
            return sorted_lat[f] + d * (sorted_lat[c] - sorted_lat[f])

        return {
            "total_requests": total_reqs,
            "successful_requests": total_completed,
            "failed_requests": total_failed,
            "duration_seconds": round(total_time_sec, 3),
            "throughput_rps": round(total_completed / total_time_sec, 2),
            "error_rate": round(total_failed / max(total_reqs, 1), 4),
            "p50_ms": round(percentile(0.50), 2),
            "p90_ms": round(percentile(0.90), 2),
            "p95_ms": round(percentile(0.95), 2),
            "p99_ms": round(percentile(0.99), 2),
            "min_ms": round(sorted_lat[0], 2),
            "max_ms": round(sorted_lat[-1], 2),
            "avg_ms": round(statistics.mean(sorted_lat), 2),
            "status_codes": dict(self.status_codes),
        }
