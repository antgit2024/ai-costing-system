from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MockExecutorClient:
    def export_scenario(self, scenario_payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("mock_executor_export %s", scenario_payload)
        return {
            "status": "accepted",
            "reference_id": f"EXEC-{scenario_payload['scenario_id']}",
        }


def get_client() -> MockExecutorClient:
    return MockExecutorClient()
