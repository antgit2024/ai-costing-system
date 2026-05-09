"""
GET /api/planner/binding-targets 通用绑定目标搜索的回归测试。

覆盖：
  1) 标准模型基础展示（含变体编码 + material_name 拼装的 label）
  2) 没有任何变体的标准模型（variants=[]）
  3) 草稿/归档模型不会出现在候选里
  4) 套装模板基础展示（含 phrase_presets，selector 大写规范化）
  5) kind 过滤：仅返回模型 / 仅返回套装
  6) search 命中：模型 code、模型 name、变体 code、变体材质名、套装 code、套装 name、preset selector
  7) limit 截断：truncated=true
"""

from __future__ import annotations

from decimal import Decimal

from src.planner import models

API = "/api/planner/binding-targets"


def _add_published_model(db_session, *, code: str, name: str):
    m = models.ProductModel(model_code=code, model_name=name, status="active", metadata_json={})
    db_session.add(m)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label=f"{code}-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    return m, v


def _add_material(db_session, *, code: str, name: str) -> models.Material:
    mat = models.Material(
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
    db_session.add(mat)
    db_session.commit()
    return mat


def _add_base_line(db_session, version_id: str, mat: models.Material) -> models.ModelVersionMaterial:
    base_line = models.ModelVersionMaterial(
        version_id=version_id,
        material_type="real",
        material_ref_id=mat.id,
        material_code=mat.material_code,
        material_name=mat.material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(base_line)
    db_session.flush()
    return base_line


def _add_variant(
    db_session,
    version_id: str,
    base_line_id: str,
    *,
    variant_code: str,
    material_name: str,
    display_name: str | None = None,
):
    meta: dict = {"variant_code": variant_code}
    if display_name is not None:
        meta["display_name"] = display_name
    v = models.ProductModelLineVariant(
        version_id=version_id,
        base_line_id=base_line_id,
        priority=100,
        enabled=True,
        action="replace_self",
        stop_on_hit=True,
        conditions_json={"spec_contains_any": [variant_code]},
        metadata_json=meta,
    )
    db_session.add(v)
    db_session.flush()
    item = models.ProductModelLineVariantItem(
        variant_id=v.id,
        sequence_order=1,
        material_kind="real",
        material_code="VARMAT-" + variant_code,
        material_name=material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        metadata_json={},
    )
    db_session.add(item)
    db_session.flush()
    return v


def test_binding_targets_returns_models_and_bundles_with_secondary(client, db_session):
    # 标准模型 KB8 + 两个变体（覆盖：material_name 存在 / 缺失两种情况）
    m_kb8, v_kb8 = _add_published_model(db_session, code="KB8", name="麻感吸水垫")
    mat = _add_material(db_session, code="WB-BASE-KB8", name="基础布")
    base_kb8 = _add_base_line(db_session, v_kb8.id, mat)
    _add_variant(db_session, v_kb8.id, base_kb8.id, variant_code="KB8-001", material_name="仿羊绒")
    _add_variant(db_session, v_kb8.id, base_kb8.id, variant_code="KB8-002", material_name="多尼尔")

    # 标准模型 F6A + 没有变体（验证 variants=[]）
    _add_published_model(db_session, code="F6A", name="皮革桌垫")

    # 套装模板（含 preset；selector 故意大小写混用，验证规范化；
    # 故意混用 phrase（实际生产字段）/ label（兼容字段）/ 都为空 三种情况）
    bundle = models.BundleTemplate(
        code="KIT01",
        name="床上用品三件套",
        components_json=[],
        metadata_json={
            "phrase_presets": [
                # 实际生产数据：phrase + 缺省 mode → parse
                {"selector": "b:kit01:a", "phrase": "三件标准（黄金绒）"},
                # 历史兼容字段：用 label，并显式 mode='force'（天猫 token 前缀变 Z）
                {"selector": "B:KIT01:B", "label": "四件加大", "mode": "force"},
                # 全空 + 大写非法 mode → label 回退 selector，mode 归一化为 parse
                {"selector": "B:KIT01:C", "phrase": "", "label": "", "mode": "FORCE_INVALID"},
                # selector 为空 → 丢弃
                {"selector": "", "phrase": "应被丢弃"},
            ]
        },
    )
    db_session.add(bundle)
    db_session.commit()

    resp = client.get(API)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    assert body["truncated"] is False
    kinds = {x["kind"] for x in items}
    assert "model" in kinds and "bundle" in kinds

    # ---- 校验 KB8 ----
    kb8 = next(x for x in items if x["kind"] == "model" and x["code"] == "KB8")
    assert kb8["name"] == "麻感吸水垫"
    assert kb8["published_version_id"] == v_kb8.id
    codes = [v["variant_code"] for v in kb8["variants"]]
    assert codes == ["KB8-001", "KB8-002"]
    labels = {v["variant_code"]: v["label"] for v in kb8["variants"]}
    assert labels["KB8-001"] == "仿羊绒(KB8-001)"
    assert labels["KB8-002"] == "多尼尔(KB8-002)"

    # ---- 校验 F6A：没有变体 ----
    f6a = next(x for x in items if x["kind"] == "model" and x["code"] == "F6A")
    assert f6a["variants"] == []

    # ---- 校验 套装：preset 规范化（phrase 优先 / label 回退 / 全空回退 / mode 归一化）----
    kit01 = next(x for x in items if x["kind"] == "bundle" and x["code"] == "KIT01")
    presets = kit01["presets"]
    selectors = [p["selector"] for p in presets]
    assert selectors == ["B:KIT01:A", "B:KIT01:B", "B:KIT01:C"]  # 大写 + 字典序
    label_map = {p["selector"]: p["label"] for p in presets}
    assert label_map["B:KIT01:A"] == "三件标准（黄金绒）"  # 来自 phrase（实际生产字段）
    assert label_map["B:KIT01:B"] == "四件加大"  # 来自 label（兼容字段）
    assert label_map["B:KIT01:C"] == "B:KIT01:C"  # phrase + label 都空 → 回退 selector
    mode_map = {p["selector"]: p["mode"] for p in presets}
    assert mode_map["B:KIT01:A"] == "parse"  # 缺省
    assert mode_map["B:KIT01:B"] == "force"  # 显式
    assert mode_map["B:KIT01:C"] == "parse"  # 非法 mode → 归一化为 parse


def test_binding_targets_variant_label_prefers_display_name_over_material_name(client, db_session):
    """变体的对客显示名（metadata_json.display_name）优先级高于 items[0].material_name。

    业务场景：兜底变体的实际替换物料是内部库存名（如 "布料隔針蜂窝本白"），但运营希望
    在 SKU Master / 筛选器里给客人展示成"麻感冰丝"。本测试验证：
      - 当变体填了 display_name="麻感冰丝" 时，binding-targets 接口返回的 label 是 "麻感冰丝(KB8-001)"
      - 当变体没填 display_name 时，回退到 material_name（向后兼容旧数据）
    """
    m_kb8, v_kb8 = _add_published_model(db_session, code="KB8", name="转印包边垫类")
    mat = _add_material(db_session, code="WB-BASE-KB8", name="基础布")
    base_kb8 = _add_base_line(db_session, v_kb8.id, mat)
    # 兜底变体：物料名是内部库存名，但 display_name 是对客的卖家秀名字
    _add_variant(
        db_session,
        v_kb8.id,
        base_kb8.id,
        variant_code="KB8-001",
        material_name="布料隔針蜂窝本白",
        display_name="麻感冰丝",
    )
    # 第二个变体：没填 display_name → 走旧的 material_name 兜底路径
    _add_variant(
        db_session,
        v_kb8.id,
        base_kb8.id,
        variant_code="KB8-002",
        material_name="仿羊绒",
    )
    db_session.commit()

    resp = client.get(API)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    kb8 = next(x for x in items if x["kind"] == "model" and x["code"] == "KB8")

    labels = {v["variant_code"]: v["label"] for v in kb8["variants"]}
    materials = {v["variant_code"]: v["material_name"] for v in kb8["variants"]}

    # KB8-001：用了 display_name，覆盖物料名
    assert labels["KB8-001"] == "麻感冰丝(KB8-001)"
    assert materials["KB8-001"] == "麻感冰丝"

    # KB8-002：没填 display_name，照常用物料名
    assert labels["KB8-002"] == "仿羊绒(KB8-002)"
    assert materials["KB8-002"] == "仿羊绒"


def test_binding_targets_excludes_draft_and_archived_models(client, db_session):
    # draft 模型不应出现
    m1 = models.ProductModel(model_code="DR1", model_name="草稿模型", status="active", metadata_json={})
    db_session.add(m1)
    db_session.flush()
    db_session.add(
        models.ProductModelVersion(
            model_id=m1.id,
            version_kind="standard",
            version_status="draft",
            version_label="DR1-STANDARD-001",
            metadata_json={},
        )
    )
    # archived 模型也不应出现
    m2 = models.ProductModel(
        model_code="AR1", model_name="归档模型", status="active", is_archived=True, metadata_json={}
    )
    db_session.add(m2)
    db_session.flush()
    db_session.add(
        models.ProductModelVersion(
            model_id=m2.id,
            version_kind="standard",
            version_status="published",
            version_label="AR1-STANDARD-001",
            is_archived=True,
            metadata_json={},
        )
    )
    db_session.commit()

    resp = client.get(API)
    body = resp.json()
    codes = {x["code"] for x in body["items"] if x["kind"] == "model"}
    assert "DR1" not in codes
    assert "AR1" not in codes


def test_binding_targets_kind_filter(client, db_session):
    _add_published_model(db_session, code="KB1", name="模型1")
    db_session.add(models.BundleTemplate(code="KIT_A", name="套装A", components_json=[], metadata_json={}))
    db_session.commit()

    only_models = client.get(API, params={"kind": "model"}).json()
    assert {x["kind"] for x in only_models["items"]} == {"model"}

    only_bundles = client.get(API, params={"kind": "bundle"}).json()
    assert {x["kind"] for x in only_bundles["items"]} == {"bundle"}


def test_binding_targets_search_matches_model_code_name_variant_and_preset(client, db_session):
    # 模型 + 一个变体（仿羊绒）；模型名包含 "麻感"
    m, v = _add_published_model(db_session, code="KB8", name="麻感吸水垫")
    mat = _add_material(db_session, code="WB-BASE-KB8B", name="基础布")
    base = _add_base_line(db_session, v.id, mat)
    _add_variant(db_session, v.id, base.id, variant_code="KB8-001", material_name="仿羊绒")
    # 另一个噪声模型，避免假阳
    _add_published_model(db_session, code="ZZZ", name="无关模型")

    # 套装：name 包含 "床品"
    db_session.add(
        models.BundleTemplate(
            code="KIT01",
            name="床品三件套",
            components_json=[],
            metadata_json={"phrase_presets": [{"selector": "B:KIT01:STD", "label": "标准"}]},
        )
    )
    db_session.commit()

    # 1) 命中模型 code
    body = client.get(API, params={"search": "KB8"}).json()
    codes = {x["code"] for x in body["items"]}
    assert "KB8" in codes
    assert "ZZZ" not in codes

    # 2) 命中模型 name 子串
    body = client.get(API, params={"search": "麻感"}).json()
    assert any(x["kind"] == "model" and x["code"] == "KB8" for x in body["items"])

    # 3) 命中变体 code（即使 search 是 KB8-001 完整短码也应找回 KB8）
    body = client.get(API, params={"search": "KB8-001"}).json()
    assert any(x["kind"] == "model" and x["code"] == "KB8" for x in body["items"])

    # 4) 命中材质名
    body = client.get(API, params={"search": "仿羊绒"}).json()
    hit_models = [x for x in body["items"] if x["kind"] == "model"]
    assert any(x["code"] == "KB8" for x in hit_models)

    # 5) 命中套装 code
    body = client.get(API, params={"search": "KIT01"}).json()
    assert any(x["kind"] == "bundle" and x["code"] == "KIT01" for x in body["items"])

    # 6) 命中套装 name
    body = client.get(API, params={"search": "床品"}).json()
    assert any(x["kind"] == "bundle" and x["code"] == "KIT01" for x in body["items"])

    # 7) 命中 preset selector
    body = client.get(API, params={"search": "B:KIT01:STD"}).json()
    assert any(x["kind"] == "bundle" and x["code"] == "KIT01" for x in body["items"])


def test_binding_targets_limit_truncates(client, db_session):
    # 造 5 个模型
    for i in range(5):
        _add_published_model(db_session, code=f"X{i:02d}", name=f"模型{i}")
    db_session.commit()
    body = client.get(API, params={"limit": 3}).json()
    assert len(body["items"]) == 3
    assert body["truncated"] is True
