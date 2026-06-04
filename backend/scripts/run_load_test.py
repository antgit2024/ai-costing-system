#!/usr/bin/env python3
"""Ad-hoc load test runner for planner integrations."""

from __future__ import annotations

import os
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401
from fastapi.testclient import TestClient

os.environ.setdefault("PLANNER_DATABASE_URL", "sqlite:///./planner_loadtest.db")
os.environ.setdefault("PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS", "true")

from sqlalchemy.orm import Session

from src.database import Base, SessionLocal, configure_engine
from src.main import app
from src.planner import models

API_BASE = "/api/planner"
TOTAL_REQUESTS = 500
CONCURRENCY = 100


@dataclass
class LoadStats:
    latencies: list[float]
    failures: int

    def summary(self) -> str:
        if not self.latencies:
            return "No successful requests"
        sorted_lat = sorted(self.latencies)
        count = len(sorted_lat)
        p50 = statistics.median(sorted_lat)
        p95 = sorted_lat[max(0, int(count * 0.95) - 1)]
        return (
            f"count={count} min={sorted_lat[0]:.3f}s "
            f"p50={p50:.3f}s p95={p95:.3f}s "
            f"max={sorted_lat[-1]:.3f}s failures={self.failures}"
        )


def seed_data() -> str:
    engine = configure_engine(os.environ["PLANNER_DATABASE_URL"])
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:  # type: ignore
        initiative = models.CostInitiative(
            code="LOAD-INIT",
            name="Load Initiative",
            owner_id="owner",
            currency="CNY",
        )
        session.add(initiative)
        session.flush()
        scenario = models.ScenarioVersion(
            initiative_id=initiative.id,
            code="SC-LOAD",
            name="Scenario Load",
            status="approved",
            baseline_flag=True,
            total_cost=100,
        )
        session.add(scenario)
        session.commit()
        return scenario.id


def execute_requests(total: int, func) -> LoadStats:
    stats = LoadStats(latencies=[], failures=0)
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(func, i, stats) for i in range(total)]
        for future in as_completed(futures):
            future.result()
    return stats


def export_worker(idx: int, stats: LoadStats) -> None:
    client = TestClient(app)
    start = time.perf_counter()
    resp = client.post(
        f"{API_BASE}/scenarios/{export_worker.scenario_id}/export",
        json={"requested_by": f"load-{idx}", "comment": "load"},
    )
    if resp.status_code != 202:
        stats.failures += 1
    else:
        stats.latencies.append(time.perf_counter() - start)


def benchmark_worker(idx: int, stats: LoadStats) -> None:
    client = TestClient(app)
    start = time.perf_counter()
    resp = client.get(
        f"{API_BASE}/benchmarks/suggest",
        params={"category": "materials", "metric": "unit_cost"},
    )
    if resp.status_code != 200:
        stats.failures += 1
    else:
        stats.latencies.append(time.perf_counter() - start)


def main() -> None:
    scenario_id = seed_data()
    export_worker.scenario_id = scenario_id  # type: ignore[attr-defined]
    export_stats = execute_requests(TOTAL_REQUESTS, export_worker)
    benchmark_stats = execute_requests(TOTAL_REQUESTS, benchmark_worker)

    print("Scenario export load:", export_stats.summary())
    print("Benchmark suggest load:", benchmark_stats.summary())


if __name__ == "__main__":
    main()
