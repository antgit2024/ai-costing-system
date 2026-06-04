from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.planner import models
from src.planner.services import sku_master_service


def _seed_shipment_sample(db_session, *, sku_code: str, spec_text: str) -> None:
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-01-01",
        requested_by="tester",
        status="done",
        total_rows=1,
        inserted_rows=1,
        skipped_rows=0,
        exception_rows=0,
    )
    db_session.add(batch)
    db_session.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no="S-SEED",
        order_no="O-SEED",
        product_link_id="L-SEED",
        completed_at=datetime.now(timezone.utc),
        channel="seed",
        sku_code=sku_code,
        spec_text=spec_text,
        spec_hash=None,
        qty=1,
        revenue_amount=1,
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        superseded_by_id=None,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db_session.add(line)
    db_session.commit()


def test_manual_bind_by_model_and_auto_bind_preview_execute(client, db_session, monkeypatch):
    # Mock _trigger_pending_snapshots_for_sku to avoid db.rollback() inside conftest
    # nested transaction (known infra issue: service-level commit/rollback conflicts
    # with pytest fixture's outer SAVEPOINT).
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )
    # Prepare: one model + one published standard version
    model = models.ProductModel(model_code="A1B", model_name="标准模型A1B", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="A1B-20251223-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    # Two sku masters: one manual bind, one for auto bind
    sm1 = models.SkuMaster(erp_sku_barcode="BC-100", spec_text="whatever", metadata_json={})
    sm2 = models.SkuMaster(
        erp_sku_barcode="BC-200",
        # model code is NOT in the first segment; should still be detected by scanner.
        spec_text="50*140;A1B;xxx",
        metadata_json={},
    )
    db_session.add_all([sm1, sm2])
    db_session.commit()

    # Seed latest shipment spec samples (binding now enforces validation)
    _seed_shipment_sample(db_session, sku_code="BC-100", spec_text="50*140;A1B;xxx")
    _seed_shipment_sample(db_session, sku_code="BC-200", spec_text="50*140;A1B;xxx")

    # Manual bind by model should bind sm1 barcode to published standard version
    resp = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm1.id], "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bound_count"] == 1
    mapping = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-100", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert mapping.model_version_id == v.id

    # Auto bind preview should find sm2 (unbound) and match model_code_hint to published version
    prev = client.post("/api/planner/sku-master/auto-bind/preview", json={"limit": 50})
    assert prev.status_code == 200, prev.text
    prev_body = prev.json()
    assert prev_body["candidates"] >= 1
    assert any(it["erp_sku_barcode"] == "BC-200" and it["model_code"] == "A1B" for it in prev_body["items"])

    # Execute should bind BC-200
    exe = client.post(
        "/api/planner/sku-master/auto-bind/execute",
        json={"limit": 50, "requested_by": "tester", "sku_master_ids": [sm2.id]},
    )
    assert exe.status_code == 200, exe.text
    m2 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-200", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert m2.model_version_id == v.id

    # Ensure manual bind won't overwrite existing active binding
    resp2 = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm2.id], "requested_by": "tester"},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["skipped_already_bound"] == 1


def test_manual_bulk_bind_by_filters_with_exclusions(client, db_session, monkeypatch):
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )
    # Prepare: one model + one published standard version
    model = models.ProductModel(model_code="OZU", model_name="丝圈地垫", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="OZU-STANDARD-20260111-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    # SKU masters (unbound) - two hit include_terms, one doesn't
    sm1 = models.SkuMaster(erp_sku_barcode="BC-OZU-1", spec_text="竖140CM*横200CM;丝圈地垫", metadata_json={})
    sm2 = models.SkuMaster(erp_sku_barcode="BC-OZU-2", spec_text="丝圈地垫 60*90", metadata_json={})
    sm3 = models.SkuMaster(erp_sku_barcode="BC-OTHER", spec_text="皮革地垫 60*90", metadata_json={})
    db_session.add_all([sm1, sm2, sm3])
    db_session.commit()

    _seed_shipment_sample(db_session, sku_code="BC-OZU-1", spec_text="60*90;丝圈地垫")
    _seed_shipment_sample(db_session, sku_code="BC-OZU-2", spec_text="60*90;丝圈地垫")

    # Exclude sm2 (simulate user unchecked)
    resp = client.post(
        "/api/planner/sku-master/bind-by-model/bulk",
        json={
            "model_id": model.id,
            "limit": 200,
            "include_terms": "丝圈地垫",
            "match_scope": "spec",
            "excluded_sku_master_ids": [sm2.id],
            "requested_by": "tester",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["batch_candidates"] >= 1
    assert body["bound_count"] == 1
    assert body["has_more"] is False

    # sm1 should be bound, sm2 excluded should remain unbound, sm3 doesn't match
    m1 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OZU-1", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert m1.model_version_id == v.id

    assert (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OZU-2", models.SkuModelVersionMapping.is_active.is_(True))
        .count()
        == 0
    )
    assert (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OTHER", models.SkuModelVersionMapping.is_active.is_(True))
        .count()
        == 0
    )


def test_auto_bind_preview_uses_shop_spec_code_variant(client, db_session):
    """
    回归：商家编码（shop_spec_code）形如 KB8-001 / KB8-001-TMALL 时，
    sku-master 自动绑定预览应：
      1) 抽取出模型码 KB8 → 命中已发布标准模型 KB8 ；
      2) 抽出变体短码 KB8-001 作为 variant_code_hint 暴露给前端；
      3) match_method 标记为 shop_spec_code（最高优先级）。
    """
    model = models.ProductModel(model_code="KB8", model_name="麻感吸水垫", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    sm = models.SkuMaster(
        erp_sku_barcode="BC-KB8-001",
        spec_text="40*60",
        metadata_json={"shop_spec_code": "KB8-001-TMALL"},
    )
    db_session.add(sm)
    db_session.commit()

    prev = client.post("/api/planner/sku-master/auto-bind/preview", json={"limit": 50})
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["candidates"] >= 1
    hit = next((it for it in body["items"] if it["erp_sku_barcode"] == "BC-KB8-001"), None)
    assert hit is not None, "未在自动绑定预览中命中 BC-KB8-001"
    assert hit["model_code"] == "KB8"
    assert hit["match_method"] == "shop_spec_code"
    assert hit.get("variant_code_hint") == "KB8-001"


def test_manual_bind_persists_variant_code_and_list_returns_display_label(client, db_session, monkeypatch):
    """
    人工审核：用户在 TargetPickerBrowserButton 选了 KB8 → 仿羊绒(KB8-001) 时：
      1) service 接 variant_code 入参；
      2) 落库到 SkuMaster.metadata_json.bound_variant_code（大写归一化）；
      3) 列表/详情查询时 _attach_costing_summary_to_rows 计算 bound_variant_code +
         bound_variant_label；
      4) bound_variant_label 优先用 ProductModelLineVariant.metadata_json.display_name，
         没有则回退到 items[0].material_name；都没有则只显示编码。

    NOTE：直接调 service 层而非 router；并 monkeypatch `_trigger_pending_snapshots_for_sku`
    为 noop——本仓库 conftest 用嵌套事务做隔离，trigger 内部偶发的 db.rollback() 会把
    外层 conftest transaction 一并回滚（同类问题：test_bind_preview_allows_and_auto_preparse_on_success
    也是 pre-existing 失败）。本测试只验证"variant_code 字段能落库 + 读路径能拼出
    display label"，与 trigger 的快照副作用无关。
    """
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )
    model = models.ProductModel(model_code="KB8", model_name="转印包边垫类", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    base_line = models.ModelVersionMaterial(
        version_id=v.id,
        material_type="virtual",
        material_ref_id=str(uuid.uuid4()),
        material_code="VM00001",
        material_name="占位物料",
        unit_of_measure="m2",
        calculation_method="area",
        sequence_order=1,
        metadata_json={},
    )
    db_session.add(base_line)
    db_session.flush()

    # 变体 KB8-001：填了 display_name="麻感冰丝"，应优先于 material_name 展示
    var1 = models.ProductModelLineVariant(
        version_id=v.id,
        base_line_id=base_line.id,
        priority=100,
        enabled=True,
        action="replace_self",
        stop_on_hit=True,
        conditions_json={"spec_contains_any": ["冰丝凉感"]},
        metadata_json={"variant_code": "KB8-001", "display_name": "麻感冰丝"},
    )
    db_session.add(var1)
    db_session.flush()
    db_session.add(
        models.ProductModelLineVariantItem(
            variant_id=var1.id,
            sequence_order=1,
            material_kind="real",
            material_code="WB02030",
            material_name="布料隔針蜂窝本白",
            unit_of_measure="m2",
            calculation_method="area",
        )
    )
    db_session.flush()

    sm = models.SkuMaster(erp_sku_barcode="BC-KB8-MANUAL", spec_text="冰丝凉感-沙发垫;90*180cm", metadata_json={})
    db_session.add(sm)
    db_session.flush()
    sm_id = str(sm.id)
    _seed_shipment_sample(db_session, sku_code="BC-KB8-MANUAL", spec_text="冰丝凉感-沙发垫;90*180cm")

    # 人工绑定：传 variant_code（来自 TargetPickerBrowserButton 的 selection.variant_code）
    result = sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
        variant_code="kb8-001",  # 故意小写，验证 service 端归一化
    )
    assert result["bound_count"] == 1

    # 1) 落库：metadata_json.bound_variant_code 大写
    sm_reread = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    assert (sm_reread.metadata_json or {}).get("bound_variant_code") == "KB8-001"

    # 2) 读路径：service.list_sku_masters 内部走 _attach_costing_summary_to_rows，
    #    会计算 bound_variant_code + bound_variant_label 暴露给前端
    _total, items = sku_master_service.list_sku_master(
        db_session,
        search="BC-KB8-MANUAL",
        channel=None,
        match_status=None,
        page=1,
        page_size=20,
    )
    hit = next((it for it in items if it.id == sm_id), None)
    assert hit is not None, "新绑定的 SKU Master 应能在列表查询中读出"
    assert hit.bound_model_code == "KB8"
    assert hit.bound_variant_code == "KB8-001"
    # 优先 display_name "麻感冰丝"，覆盖物料名 "布料隔針蜂窝本白"
    assert hit.bound_variant_label == "麻感冰丝(KB8-001)"


def test_manual_bind_with_empty_variant_code_clears_existing(client, db_session, monkeypatch):
    """传 variant_code=None / 空串时，应清掉历史落库的 bound_variant_code，避免脏数据。

    同上，直接调 service 层 + monkeypatch 绕开 conftest nested-transaction 限制。
    """
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )
    model = models.ProductModel(model_code="F6A", model_name="皮革桌垫", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="F6A-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    sm = models.SkuMaster(
        erp_sku_barcode="BC-F6A-RESET",
        spec_text="whatever",
        metadata_json={"bound_variant_code": "F6A-OLD"},  # 模拟历史脏数据
    )
    db_session.add(sm)
    db_session.flush()
    sm_id = str(sm.id)
    _seed_shipment_sample(db_session, sku_code="BC-F6A-RESET", spec_text="whatever")

    sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
        allow_rebind=True,
        variant_code=None,  # 不指定变体 → 应清掉旧 F6A-OLD
    )

    sm_reread = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    assert "bound_variant_code" not in (sm_reread.metadata_json or {})

    _total, items = sku_master_service.list_sku_master(
        db_session,
        search="BC-F6A-RESET",
        channel=None,
        match_status=None,
        page=1,
        page_size=20,
    )
    hit = next((it for it in items if it.id == sm_id), None)
    assert hit is not None
    assert hit.bound_variant_code is None
    assert hit.bound_variant_label is None


def test_bind_with_shipment_sample_keeps_variant_code(client, db_session, monkeypatch):
    """
    回归"变体编码被 _apply_preparse_no_commit 抹掉"的 bug。

    原 bug 链路：
      1) bind_sku_master_by_model 调 product_model_service.bind_sku_to_version；
      2) bind_sku_to_version 内部 db.commit() 触发 SQLAlchemy expire_on_commit；
      3) service 接着 row.metadata_json = meta（含 bound_variant_code='KB8-001'）；
      4) 然后调 _apply_preparse_no_commit，它内部 meta = dict(row.metadata_json or {})
         触发 lazy reload → 拿到的是 stale 的 baseline metadata（没 bound_variant_code）；
      5) preparse update 后写回 row.metadata_json，**把 bound_variant_code 抹掉**；
      6) 最终 db.commit() 持久化的是 step 5 的版本，bound_variant_code 永远 None。

    修复：把"我们要落的字段"放到最后写入（即 _apply_preparse_no_commit 之后），
    避免 read-modify-write 顺序覆盖问题。

    这条测试通过"必须有 shipment_sample 才会跑 _apply_preparse_no_commit"来精确触发该路径。
    """
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )

    model = models.ProductModel(model_code="KB8", model_name="转印包边垫类", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-PREPARSE-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    sm = models.SkuMaster(erp_sku_barcode="BC-KB8-PREPARSE", spec_text="冰丝凉感-沙发垫;90*180cm", metadata_json={})
    db_session.add(sm)
    db_session.flush()
    sm_id = str(sm.id)
    # 必须有 shipment sample，service 才会跑 _apply_preparse_no_commit（也就是触发 bug 的路径）
    _seed_shipment_sample(db_session, sku_code="BC-KB8-PREPARSE", spec_text="冰丝凉感-沙发垫;90*180cm")

    sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
        variant_code="KB8-001",
    )

    sm_reread = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    meta = sm_reread.metadata_json or {}
    # 关键断言：bound_variant_code + model_bound_at + preparse 字段必须并存
    assert meta.get("bound_variant_code") == "KB8-001", (
        "bound_variant_code 被 _apply_preparse_no_commit 的 read-modify-write 抹掉了"
    )
    assert meta.get("model_bound_at"), "model_bound_at 也应同时落库"
    assert meta.get("preparse_saved_at"), "preparse 也应顺利落库"
    assert meta.get("preparse_spec_text") == "冰丝凉感-沙发垫;90*180cm"


def test_rebind_same_version_only_updates_variant_code(client, db_session, monkeypatch):
    """
    回归"运营想补 variant_code"场景：SKU 已绑到 KB8 模型的发布版本，运营在
    TargetPickerBrowserButton 重选了 KB8 → 仿羊绒(KB8-001)。

    要求：
      1) allow_rebind=True 且目标版本与已绑版本相同时，**不再** silently 跳过；
      2) 仅 patch sku_master.metadata_json.bound_variant_code，不重建 SkuModelVersionMapping
         （保留绑定历史 effective_from / 不动 mapping.id）；
      3) bound_count=1（运营在 UI 上能看到"绑定成功"反馈）；
      4) 后续相同 variant_code 重复提交才走 skipped_already_bound。
    """
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )

    model = models.ProductModel(model_code="KB8", model_name="转印包边垫类", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-REBIND-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    sm = models.SkuMaster(erp_sku_barcode="BC-KB8-REBIND", spec_text="x", metadata_json={})
    db_session.add(sm)
    db_session.flush()
    sm_id = str(sm.id)
    _seed_shipment_sample(db_session, sku_code="BC-KB8-REBIND", spec_text="x")

    # 第一次绑定：不带 variant_code，模拟历史"只绑模型不绑变体"
    sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
    )
    sm_after_1 = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    assert "bound_variant_code" not in (sm_after_1.metadata_json or {})
    mapping_1 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code == "BC-KB8-REBIND",
            models.SkuModelVersionMapping.is_active.is_(True),
        )
        .one()
    )
    mapping_1_id = str(mapping_1.id)

    # 重绑：勾上 allow_rebind，目标模型相同，但补 variant_code=KB8-001
    result = sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
        allow_rebind=True,
        variant_code="KB8-001",
    )
    assert result["bound_count"] == 1, result  # 不能再静默 skip
    assert result["skipped_already_bound"] == 0

    sm_after_2 = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    assert (sm_after_2.metadata_json or {}).get("bound_variant_code") == "KB8-001"
    assert (sm_after_2.metadata_json or {}).get("model_binding_method") == "manual_variant_only_update"

    # mapping 仍是同一条，没被重建
    mapping_2 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code == "BC-KB8-REBIND",
            models.SkuModelVersionMapping.is_active.is_(True),
        )
        .one()
    )
    assert str(mapping_2.id) == mapping_1_id, "只 patch metadata 时不应重建 mapping"

    # 再来第三次：同样的 KB8-001，要 skipped
    result3 = sku_master_service.bind_sku_master_by_model(
        db_session,
        model_id=model.id,
        sku_master_ids=[sm_id],
        requested_by="tester",
        allow_rebind=True,
        variant_code="KB8-001",
    )
    assert result3["bound_count"] == 0
    assert result3["skipped_already_bound"] == 1


def test_auto_bind_execute_persists_variant_code_from_shop_spec_code(client, db_session, monkeypatch):
    """
    自动识别：商家编码 KB8-001-TMALL → preview 抽出 variant_code_hint=KB8-001 →
    auto-bind/execute 应把 KB8-001 写入 SkuMaster.metadata_json.bound_variant_code，
    并在列表读路径里拼出 "麻感冰丝(KB8-001)" label，与人工模式走同一份字段。
    """
    from src.planner.services import product_model_service as pms_local
    monkeypatch.setattr(
        pms_local,
        "_trigger_pending_snapshots_for_sku",
        lambda db, *, sku, operator_id="bind_hook": {"scanned": 0, "created": 0, "skipped": 0, "failed": 0},
    )

    model = models.ProductModel(model_code="KB8", model_name="转印包边垫类", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="KB8-AUTO-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    base_line = models.ModelVersionMaterial(
        version_id=v.id,
        material_type="virtual",
        material_ref_id=str(uuid.uuid4()),
        material_code="VM00001",
        material_name="占位物料",
        unit_of_measure="m2",
        calculation_method="area",
        sequence_order=1,
        metadata_json={},
    )
    db_session.add(base_line)
    db_session.flush()
    var1 = models.ProductModelLineVariant(
        version_id=v.id,
        base_line_id=base_line.id,
        priority=100,
        enabled=True,
        action="replace_self",
        stop_on_hit=True,
        conditions_json={"spec_contains_any": ["冰丝凉感"]},
        metadata_json={"variant_code": "KB8-001", "display_name": "麻感冰丝"},
    )
    db_session.add(var1)
    db_session.flush()
    db_session.add(
        models.ProductModelLineVariantItem(
            variant_id=var1.id,
            sequence_order=1,
            material_kind="real",
            material_code="WB02030",
            material_name="布料隔針蜂窝本白",
            unit_of_measure="m2",
            calculation_method="area",
        )
    )
    db_session.flush()

    sm = models.SkuMaster(
        erp_sku_barcode="BC-AUTO-KB8-001",
        spec_text="40*60",
        metadata_json={"shop_spec_code": "KB8-001-TMALL"},
    )
    db_session.add(sm)
    db_session.flush()
    sm_id = str(sm.id)

    result = sku_master_service.auto_bind_execute(
        db_session,
        limit=50,
        requested_by="auto-tester",
        sku_master_ids=[sm_id],
    )
    assert result["bound_count"] == 1, result

    sm_reread = db_session.query(models.SkuMaster).filter(models.SkuMaster.id == sm_id).one()
    assert (sm_reread.metadata_json or {}).get("bound_variant_code") == "KB8-001"

    _total, items = sku_master_service.list_sku_master(
        db_session,
        search="BC-AUTO-KB8-001",
        channel=None,
        match_status=None,
        page=1,
        page_size=20,
    )
    hit = next((it for it in items if it.id == sm_id), None)
    assert hit is not None
    assert hit.bound_model_code == "KB8"
    assert hit.bound_variant_code == "KB8-001"
    assert hit.bound_variant_label == "麻感冰丝(KB8-001)"
