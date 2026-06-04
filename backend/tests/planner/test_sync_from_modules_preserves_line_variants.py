from __future__ import annotations

from src.planner import models


API_PREFIX = "/api/planner"


def test_sync_from_modules_preserves_line_variants(client, db_session):
    # Create a module with one material row
    mod = models.ProcessModule(
        module_code="PMOD-VAR-PRESERVE-001",
        module_name="模块-变体不丢",
        status="active",
        tags=[],
        metadata_json={},
    )
    db_session.add(mod)
    db_session.flush()
    mm = models.ProcessModuleMaterial(
        module_id=mod.id,
        material_kind="bom",
        material_ref_id="MAT-1",
        material_code="M001",
        material_name="物料1",
        unit_of_measure="米",
        calculation_method="count",
        quantity=1,
        loss_rate=0,
        sequence_order=1,
        selection_notes="n1",
        metadata_json={},
    )
    db_session.add(mm)
    db_session.commit()

    # Create model and bind module
    model = models.ProductModel(
        model_code="VTM",
        model_name="测试模型-同步不丢变体",
        status="draft",
        metadata_json={},
    )
    db_session.add(model)
    db_session.flush()
    db_session.add(
        models.ModelProcessModule(
            model_id=model.id,
            module_id=mod.id,
            sequence_order=1,
            notes=None,
            metadata_json={},
        )
    )
    db_session.commit()

    # Create version
    r = client.post(
        f"{API_PREFIX}/product-models/{model.id}/versions",
        json={"version_kind": "standard", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]

    # First sync => material line exists
    r = client.post(f"{API_PREFIX}/product-model-versions/{vid}/sync-from-modules", json={"keep_overrides": True})
    assert r.status_code == 200, r.text
    lines = r.json()
    assert len(lines["materials"]) == 1
    base_line_id = lines["materials"][0]["id"]

    # Create a line variant on that base line
    r = client.post(
        f"{API_PREFIX}/product-model-versions/{vid}/line-variants",
        json={
            "version_id": vid,
            "base_line_id": base_line_id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "notes": "v0",
            "conditions": {"spec_contains_any": ["A"]},
            "metadata": {},
            "items": [
                {
                    "sequence_order": 1,
                    "material_kind": "bom",
                    "material_ref_id": "MAT-2",
                    "material_code": "M002",
                    "material_name": "物料2",
                    "unit_of_measure": "米",
                    "calculation_method": "count",
                    "base_quantity": "1",
                    "fixed_quantity": "0",
                    "coverage_ratio": "1",
                    "loss_rate": "0",
                    "metadata_json": {},
                }
            ],
            "operator_id": "test",
        },
    )
    assert r.status_code == 201, r.text

    # Sync again => base_line_id must remain stable; variants should remain
    r = client.post(f"{API_PREFIX}/product-model-versions/{vid}/sync-from-modules", json={"keep_overrides": True})
    assert r.status_code == 200, r.text
    lines2 = r.json()
    assert len(lines2["materials"]) == 1
    assert lines2["materials"][0]["id"] == base_line_id

    r = client.get(
        f"{API_PREFIX}/product-model-versions/{vid}/line-variants",
        params={"base_line_id": base_line_id},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


