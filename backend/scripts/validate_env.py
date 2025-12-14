#!/usr/bin/env python3
"""Validate planner environment configuration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import Settings

REQUIRED_FOR_PROD = {
    "EXECUTOR_BASE_URL": "Executor endpoint is required when mock flag is false",
    "EXECUTOR_CALLBACK_SECRET": "Callback secret is required for signature validation",
    "BENCHMARK_API_BASE_URL": "Benchmark API endpoint cannot be empty",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate planner env configuration")
    parser.add_argument("--env-file", default=".env", help="Path to env file (defaults to .env)")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))

    try:
        settings = Settings()
    except ValidationError as exc:
        print("❌ Invalid configuration:")
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            print(f"  - {loc}: {err['msg']}")
        raise SystemExit(1)

    errors: Dict[str, str] = {}
    if not settings.feature_flag_mock_integrations:
        for env_key, message in REQUIRED_FOR_PROD.items():
            if not os.environ.get(env_key):
                errors[env_key] = message

    if settings.message_bus_broker is None:
        print("⚠️  MESSAGE_BUS_BROKER is not set; planner will fall back to in-memory publisher.")
    if settings.redis_url is None:
        print("⚠️  PLANNER_REDIS_URL not configured; benchmark cache uses in-memory TTL cache.")

    if errors:
        print("❌ Missing production settings:")
        for key, msg in errors.items():
            print(f"  - {key}: {msg}")
        raise SystemExit(1)

    print("✅ Planner configuration looks good.")
    print(f"   Database: {settings.database_url}")
    print(f"   Executor base URL: {settings.executor_base_url}")
    print(f"   Benchmark base URL: {settings.benchmark_api_base_url}")
    print(f"   Message bus topic: {settings.message_bus_topic}")


if __name__ == "__main__":
    main()
