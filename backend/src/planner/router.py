from fastapi import APIRouter, Depends

from .dependencies import require_staff_role
from .routers import (
    after_sales,
    analytics,
    approvals,
    ai,
    assumptions,
    audit,
    base_config,
    benchmarks,
    bom,
    bundle_templates,
    callbacks,
    codes,
    health,
    initiatives,
    jobs,
    line_items,
    line_variants,
    packages,
    process_modules,
    processes,
    product_models,
    product_model_versions,
    reports,
    scenarios,
    shipping_rules,
    shipments,
    sku_master,
    specs,
    taxonomy,
    tmall_sku_template,
)

router = APIRouter(prefix="/planner")

router.include_router(health.router)
router.include_router(callbacks.router)

guarded = APIRouter(dependencies=[Depends(require_staff_role)])
guarded.include_router(after_sales.router)
guarded.include_router(analytics.router)
guarded.include_router(initiatives.router)
guarded.include_router(packages.router)
guarded.include_router(line_items.router)
guarded.include_router(assumptions.router)
guarded.include_router(scenarios.router)
guarded.include_router(approvals.router)
guarded.include_router(jobs.router)
guarded.include_router(benchmarks.router)
guarded.include_router(audit.router)
guarded.include_router(codes.router)
guarded.include_router(base_config.router)
guarded.include_router(process_modules.router)
guarded.include_router(processes.router)
guarded.include_router(ai.router)
guarded.include_router(product_models.router)
guarded.include_router(product_model_versions.router)
guarded.include_router(reports.router)
guarded.include_router(line_variants.router)
guarded.include_router(shipping_rules.router)
guarded.include_router(shipments.router)
guarded.include_router(sku_master.router)
guarded.include_router(specs.router)
guarded.include_router(taxonomy.router)
guarded.include_router(bundle_templates.router)
guarded.include_router(bom.router)
guarded.include_router(tmall_sku_template.router)

router.include_router(guarded)
