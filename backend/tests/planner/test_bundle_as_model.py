from __future__ import annotations


from src.planner import models
from src.planner.services import bom_generation_service, bundle_template_service, product_model_service


def test_bundle_as_model_generates_bom_and_unifies_model_version_id(db_session):
    # 1) Prepare a component model version (published) referenced by bundle template presets
    comp_model = models.ProductModel(model_code="C1", model_name="组件模型", status="active", metadata_json={})
    db_session.add(comp_model)
    db_session.flush()
    comp_ver = models.ProductModelVersion(
        model_id=comp_model.id,
        version_kind="standard",
        version_status="published",
        version_label="C1-TEST-01",
        metadata_json={"standard": {"width_mm": "1000", "height_mm": "1000", "quantity": "1"}},
    )
    db_session.add(comp_ver)
    db_session.flush()

    # 2) Create a bundle template and publish a version snapshot
    tpl = models.BundleTemplate(
        code="TST1",
        name="测试套装",
        components_json=[],
        metadata_json={
            "phrase_presets": [
                {
                    "selector": "AA",
                    "mode": "force",  # Z-mode
                    "phrase": "测试",
                    "components": [
                        {"model_version_id": comp_ver.id, "width_mm": 300, "height_mm": 400, "quantity": 1, "tokens": []}
                    ],
                }
            ]
        },
    )
    db_session.add(tpl)
    db_session.commit()
    v = bundle_template_service.publish_template(db_session, template_id=tpl.id, published_by="tester", note="v1")

    # 3) Ensure bundle model version exists and bind a SKU to it (single exit)
    bundle_ver = product_model_service.ensure_bundle_model_version(
        db_session, template_version=v, preset_selector="AA", requested_by="tester"
    )
    product_model_service.bind_sku_to_version(
        db_session,
        sku_code="SKU123",
        version_id=bundle_ver.id,
        source_system="test",
        metadata={"skip_prefix_check": True},
    )

    # 4) Generate BOM: since the binding is to a bundle-kind version, generate_bom should use bundle template snapshot
    bom = bom_generation_service.generate_bom(
        db_session,
        spec_text="Z-TST1AA 测试套装",
        model_version_id=None,
        sku_code="SKU123",
        quantity=None,
    )
    assert isinstance(bom, dict)
    trace = bom.get("trace") or {}
    assert trace.get("model_version_id") == bundle_ver.id
    assert trace.get("sold_as_bundle") is True
    assert trace.get("bundle_template_version_id") == v.id

