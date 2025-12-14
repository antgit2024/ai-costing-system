from fastapi import APIRouter

from .routers import (
    approvals,
    assumptions,
    audit,
    base_config,
    benchmarks,
    callbacks,
    health,
    initiatives,
    jobs,
    line_items,
    packages,
    scenarios,
)

router = APIRouter(prefix="/planner")

router.include_router(health.router)
router.include_router(initiatives.router)
router.include_router(packages.router)
router.include_router(line_items.router)
router.include_router(assumptions.router)
router.include_router(scenarios.router)
router.include_router(approvals.router)
router.include_router(jobs.router)
router.include_router(benchmarks.router)
router.include_router(callbacks.router)
router.include_router(audit.router)
router.include_router(base_config.router)
