from fastapi import APIRouter

from .routers import (
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
router.include_router(codes.router)
router.include_router(base_config.router)
router.include_router(process_modules.router)
router.include_router(processes.router)
router.include_router(ai.router)
router.include_router(product_models.router)
router.include_router(product_model_versions.router)
router.include_router(line_variants.router)
router.include_router(shipping_rules.router)
router.include_router(shipments.router)
router.include_router(sku_master.router)
router.include_router(specs.router)
router.include_router(taxonomy.router)
router.include_router(bundle_templates.router)
router.include_router(bom.router)
router.include_router(tmall_sku_template.router)
