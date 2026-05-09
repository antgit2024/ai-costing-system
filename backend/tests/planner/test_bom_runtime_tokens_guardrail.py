from __future__ import annotations

from decimal import Decimal

from src.planner import models

API_PREFIX = "/api/planner"


def _create_material(db_session, *, code: str, name: str) -> models.Material:
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="fabric",
        unit="m2",
        unit_price=Decimal("1.0"),
        currency="CNY",
        is_bom_material=True,
        is_active=True,
        status="active",
        metadata_json={},
    )
    db_session.add(material)
    db_session.commit()
    return material


def test_bom_generate_injects_model_token_for_variant_matching(client, db_session):
    """
    Guardrail: variant rules can be anchored to the bound model code even if spec_text doesn't contain it.

    This prevents cross-model false hits when materials are reused across categories.
    """
    model = models.ProductModel(
        model_code="PI5",
        model_name="抱枕 PI5",
        status="active",
        unit_of_measure="套",
        metadata_json={},
    )
    db_session.add(model)
    db_session.flush()

    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="PI5-STANDARD-TEST-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(version)
    db_session.flush()

    base_material = _create_material(db_session, code="FAB-BASE", name="基础面料")
    replacement_material = _create_material(db_session, code="WB01176", name="棉麻布300本白防水")

    base_line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(base_line)
    db_session.flush()

    # Bind SKU barcode to this published standard version
    sku = "1003433256386"
    db_session.add(
        models.SkuModelVersionMapping(
            sku_code=sku,
            model_version_id=version.id,
            is_active=True,
            metadata_json={},
        )
    )
    db_session.flush()

    # Create a variant anchored to MODEL:PI5 (not present in spec_text)
    create_variant = client.post(
        f"{API_PREFIX}/product-model-versions/{version.id}/line-variants",
        json={
            "version_id": version.id,
            "base_line_id": base_line.id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "conditions": {"spec_contains_all": ["MODEL:PI5"]},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "material_code": replacement_material.material_code,
                    "material_name": replacement_material.material_name,
                    "unit_of_measure": "m2",
                    "calculation_method": "area",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_variant.status_code == 201, create_variant.text
    variant_id = create_variant.json()["id"]

    # Spec text doesn't contain "PI5" at all; match should still happen via runtime token injection.
    bom_resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "sku_code": sku,
            "spec_text": "枕套 / 黄金绒双面印花（棕色毛球） 45X45",
            "quantity": "1",
        },
    )
    assert bom_resp.status_code == 200, bom_resp.text
    body = bom_resp.json()
    assert body["final_material_lines"][0]["variant_id"] == variant_id
    assert body["final_material_lines"][0]["material_code"] == replacement_material.material_code

    trace = body.get("trace") or {}
    runtime_tokens = trace.get("runtime_tokens") or []
    assert "MODEL:PI5" in runtime_tokens
    assert any(t.startswith("BOUND_VERSION:") for t in runtime_tokens)
    assert f"SKU:{sku}" in runtime_tokens


def test_bom_generate_extracts_structured_variant_code_from_merchant_sku(client, db_session):
    """
    商家编码可承载模型-变体短码（如 KB8-001）。
    即使线上商家编码带后缀，运行时 token 也要抽取 SKU:KB8-001 供材质变体命中。
    """
    model = models.ProductModel(
        model_code="KB8",
        model_name="通用包边垫类",
        status="active",
        unit_of_measure="件",
        metadata_json={},
    )
    db_session.add(model)
    db_session.flush()

    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-STANDARD-TEST-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(version)
    db_session.flush()

    base_material = _create_material(db_session, code="WB02030", name="基础布")
    replacement_material = _create_material(db_session, code="WB02384", name="麻感布")

    base_line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(base_line)
    db_session.flush()

    merchant_sku = "KB8-001-TMALL"
    db_session.add(
        models.SkuModelVersionMapping(
            sku_code=merchant_sku,
            model_version_id=version.id,
            is_active=True,
            metadata_json={},
        )
    )
    db_session.flush()

    create_variant = client.post(
        f"{API_PREFIX}/product-model-versions/{version.id}/line-variants",
        json={
            "version_id": version.id,
            "base_line_id": base_line.id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "conditions": {
                "spec_contains_all": ["MODEL:KB8"],
                "spec_contains_any": ["KB8-001", "SKU:KB8-001"],
            },
            "metadata_json": {"variant_code": "KB8-001"},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "material_code": replacement_material.material_code,
                    "material_name": replacement_material.material_name,
                    "unit_of_measure": "m2",
                    "calculation_method": "area",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_variant.status_code == 201, create_variant.text
    variant_id = create_variant.json()["id"]

    bom_resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "sku_code": merchant_sku,
            "spec_text": "沙发垫 45X45",
            "quantity": "1",
        },
    )
    assert bom_resp.status_code == 200, bom_resp.text
    body = bom_resp.json()
    assert body["final_material_lines"][0]["variant_id"] == variant_id
    assert body["final_material_lines"][0]["material_code"] == replacement_material.material_code

    runtime_tokens = (body.get("trace") or {}).get("runtime_tokens") or []
    assert "MODEL:KB8" in runtime_tokens
    assert "KB8-001" in runtime_tokens
    assert "SKU:KB8-001" in runtime_tokens


def test_bom_generate_variant_code_is_independent_of_token_any(client, db_session):
    """
    回归：variant.metadata_json.variant_code 是变体的"身份证"，与 spec_contains_any/all（中文 token）独立。
    场景：变体 spec_contains_any 里**只有中文属性 token "仿羊绒"**（与商家编码毫无关系），
          运营把变体编码 KB8-001 单独写在 metadata_json.variant_code；
          出货 sku_code = "KB8-001-TMALL" 时，只要商家编码命中变体编码，就直接命中本变体，
          无需在 spec_text 里出现"仿羊绒"。

    这保证：
      - "自动生成变体编码" 不再污染 token_any（用户原本输入的中文属性保持不动）
      - 变体编码独立成为一条短路命中通道
    """
    model = models.ProductModel(
        model_code="KB9",
        model_name="独立变体编码-测试",
        status="active",
        unit_of_measure="件",
        metadata_json={},
    )
    db_session.add(model)
    db_session.flush()

    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB9-STANDARD-TEST-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(version)
    db_session.flush()

    base_material = _create_material(db_session, code="WB-BASE-2", name="基础布2")
    replacement_material = _create_material(db_session, code="WB-REPL-2", name="仿羊绒")

    base_line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(base_line)
    db_session.flush()

    merchant_sku = "KB9-001-TMALL"
    db_session.add(
        models.SkuModelVersionMapping(
            sku_code=merchant_sku,
            model_version_id=version.id,
            is_active=True,
            metadata_json={},
        )
    )
    db_session.flush()

    create_variant = client.post(
        f"{API_PREFIX}/product-model-versions/{version.id}/line-variants",
        json={
            "version_id": version.id,
            "base_line_id": base_line.id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            # ⚠️ 关键：spec_contains_any 只放中文属性 token，没有任何 KB9-001 / SKU: 别名
            "conditions": {"spec_contains_any": ["仿羊绒"]},
            "metadata_json": {"variant_code": "KB9-001"},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "material_code": replacement_material.material_code,
                    "material_name": replacement_material.material_name,
                    "unit_of_measure": "m2",
                    "calculation_method": "area",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_variant.status_code == 201, create_variant.text
    variant_id = create_variant.json()["id"]

    # 出货规格里**没有**"仿羊绒"，但商家编码含 KB9-001 → 走 variant_code 短路通道命中
    bom_resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "sku_code": merchant_sku,
            "spec_text": "沙发坐垫 45X45",
            "quantity": "1",
        },
    )
    assert bom_resp.status_code == 200, bom_resp.text
    body = bom_resp.json()
    assert body["final_material_lines"][0]["variant_id"] == variant_id, (
        "商家编码 KB9-001-TMALL 应通过 variant_code 短路通道命中，但未命中"
    )
    assert body["final_material_lines"][0]["material_code"] == replacement_material.material_code


