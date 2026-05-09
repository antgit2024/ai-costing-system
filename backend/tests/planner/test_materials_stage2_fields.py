"""Materials Stage 2 字段扩展（Migration 0039）—— 行为测试

覆盖任务单 §4 五条完成标准里"用代码能验证"的部分：

1. ORM 默认值：老物料创建后 6 字段全 NULL（tax_included_flag 默认 False）
2. PATCH /base-config/materials/{id} 能写入 6 个新字段；GET 能读回
3. tax_rate 字段值校验：0~1 区间外应被拒（422）
4. 宜搭同步 3 种 mode（full / new_only / core_fields）：6 个新字段不被覆盖

UI / Migration 自身的双向跑通在任务单 §5 命令里手工/CI 验证。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.planner import models
from src.planner.services.yida_sync import (
    MaterialSyncResult,
    MaterialSyncService,
    NormalizedMaterial,
    YidaConfig,
    YidaFormClient,
)


API_PREFIX = "/api/planner/base-config"


def _make_material(db, **overrides) -> models.Material:
    """Build a Material with calculation_method/unit consistent with backend guardrail.

    `_validate_calc_method_unit` rejects e.g. count + 平米; the path runs on
    every PATCH (not just when calc_method/unit change), so the seed row must
    already be self-consistent before we PATCH the new Stage 2 fields.
    """
    defaults: dict[str, Any] = dict(
        material_code="MAT-S2-001",
        material_name="Stage2 测试物料",
        material_type="raw",
        calculation_method="area",
        unit="平米",
        purchase_unit="米",
        unit_price=Decimal("12.34"),
        currency="CNY",
        status="active",
        is_active=True,
    )
    defaults.update(overrides)
    material = models.Material(**defaults)
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


# ---------------------------------------------------------------------------
# 1) 默认值：老数据 / 新建物料 6 字段都应为 NULL（含 tax_included_flag = False）
# ---------------------------------------------------------------------------


def test_default_values_for_legacy_material(db_session) -> None:
    material = _make_material(db_session)

    assert material.purchase_entity_id is None
    assert material.tax_included_flag is False
    assert material.tax_rate is None
    assert material.price_source is None
    assert material.effective_from is None
    assert material.effective_to is None


def test_get_materials_exposes_stage2_fields(client: TestClient, db_session) -> None:
    material = _make_material(db_session)

    resp = client.get(f"{API_PREFIX}/materials/{material.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for key in (
        "purchase_entity_id",
        "tax_included_flag",
        "tax_rate",
        "price_source",
        "effective_from",
        "effective_to",
    ):
        assert key in body, f"GET response missing Stage 2 field: {key}"

    assert body["purchase_entity_id"] is None
    assert body["tax_included_flag"] is False
    assert body["tax_rate"] is None
    assert body["price_source"] is None
    assert body["effective_from"] is None
    assert body["effective_to"] is None


# ---------------------------------------------------------------------------
# 2) PATCH 能写入 6 个新字段；GET 能读回；列表也能拿到
# ---------------------------------------------------------------------------


def test_patch_writes_stage2_fields_and_get_reads_them_back(
    client: TestClient, db_session
) -> None:
    material = _make_material(db_session)

    patch_resp = client.patch(
        f"{API_PREFIX}/materials/{material.id}",
        json={
            "purchase_entity_id": "一般纳税人",
            "tax_included_flag": True,
            "tax_rate": "0.13",
            "price_source": "manual",
            "effective_from": "2026-05-10",
            "effective_to": "2026-12-31",
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    payload = patch_resp.json()
    assert payload["purchase_entity_id"] == "一般纳税人"
    assert payload["tax_included_flag"] is True
    assert Decimal(str(payload["tax_rate"])) == Decimal("0.13")
    assert payload["price_source"] == "manual"
    assert payload["effective_from"] == "2026-05-10"
    assert payload["effective_to"] == "2026-12-31"

    db_session.refresh(material)
    assert material.purchase_entity_id == "一般纳税人"
    assert material.tax_included_flag is True
    assert material.tax_rate == Decimal("0.1300")
    assert material.price_source == "manual"
    assert material.effective_from == date(2026, 5, 10)
    assert material.effective_to == date(2026, 12, 31)

    # 列表里也能拿到（前端列表新增 2 列要靠这个）
    list_resp = client.get(f"{API_PREFIX}/materials", params={"search": material.material_code})
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert items, list_resp.text
    item = next(i for i in items if i["material_code"] == material.material_code)
    assert item["purchase_entity_id"] == "一般纳税人"
    assert item["tax_included_flag"] is True


def test_patch_can_clear_stage2_fields_explicitly(client: TestClient, db_session) -> None:
    material = _make_material(
        db_session,
        purchase_entity_id="小规模A",
        tax_included_flag=True,
        tax_rate=Decimal("0.06"),
        price_source="contract",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
    )

    resp = client.patch(
        f"{API_PREFIX}/materials/{material.id}",
        json={
            "purchase_entity_id": None,
            "tax_rate": None,
            "price_source": None,
            "effective_from": None,
            "effective_to": None,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchase_entity_id"] is None
    assert body["tax_rate"] is None
    assert body["price_source"] is None
    assert body["effective_from"] is None
    assert body["effective_to"] is None
    # 没传的字段不变
    assert body["tax_included_flag"] is True


def test_patch_omitting_stage2_fields_keeps_existing_values(
    client: TestClient, db_session
) -> None:
    material = _make_material(
        db_session,
        purchase_entity_id="一般纳税人",
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="manual",
        effective_from=date(2026, 1, 1),
    )

    resp = client.patch(
        f"{API_PREFIX}/materials/{material.id}",
        json={"status": "inactive"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "inactive"
    # 原 Stage 2 字段保持不变（向后兼容老前端）
    assert body["purchase_entity_id"] == "一般纳税人"
    assert body["tax_included_flag"] is True
    assert Decimal(str(body["tax_rate"])) == Decimal("0.13")
    assert body["price_source"] == "manual"
    assert body["effective_from"] == "2026-01-01"


# ---------------------------------------------------------------------------
# 3) 字段值校验：tax_rate 0~1 区间外（含负数/超过 1）应被 Pydantic 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_rate", ["1.5", "-0.01", "2"])
def test_patch_rejects_invalid_tax_rate(client: TestClient, db_session, bad_rate: str) -> None:
    material = _make_material(db_session)
    resp = client.patch(
        f"{API_PREFIX}/materials/{material.id}",
        json={"tax_rate": bad_rate},
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 4) 宜搭同步 3 种 mode：6 个新字段不被覆盖
# ---------------------------------------------------------------------------


class _StubClient(YidaFormClient):
    """Bypass network — sync service only needs `client.config.field_mapping`."""

    def __init__(self) -> None:
        # 不调父类 __init__，避免触发 requests.Session
        self.config = YidaConfig(
            app_key="x",
            app_secret="x",
            system_token="x",
            app_type="x",
            user_id="x",
            form_uuid="x",
            field_mapping={},
        )


def _normalized(material_code: str = "MAT-S2-001") -> NormalizedMaterial:
    """Build a NormalizedMaterial that matches what YidaMaterialMapper emits.

    宜搭目前并不映射 6 个新字段（任务单 §3.5），所以这里也不会写入它们。
    """
    return NormalizedMaterial(
        material_code=material_code,
        material_name="Stage2 测试物料 (yida)",
        material_type="raw",
        category="metal",
        model_category=None,
        unit="平米",
        unit_price=Decimal("99.99"),
        currency="CNY",
        purchase_unit="米",
        inventory_unit=None,
        supplier_code="SUP-001",
        supplier_name="Vendor",
        status="active",
        is_active=True,
        source_created_at=None,
        source_updated_at=None,
        usage_scope=None,
        bom_notes=None,
        metadata={"raw_form_data": {"some_field": "v"}},
    )


@pytest.mark.parametrize("mode", ["full", "new_only", "core_fields"])
def test_yida_sync_does_not_overwrite_stage2_fields(db_session, mode: str) -> None:
    """3 种 mode 都应保留本地手填的 6 个新字段值（任务单 §3.5）。"""
    material = _make_material(
        db_session,
        material_code="MAT-S2-SYNC",
        purchase_entity_id="一般纳税人",
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="manual",
        effective_from=date(2026, 5, 1),
        effective_to=date(2027, 5, 1),
    )
    original_id = material.id

    service = MaterialSyncService(db_session, _StubClient())
    result = MaterialSyncResult()
    service._upsert_material(_normalized("MAT-S2-SYNC"), result, mode=mode)  # noqa: SLF001
    db_session.flush()
    db_session.refresh(material)

    # 本地手填的 6 字段必须原样保留
    assert material.id == original_id
    assert material.purchase_entity_id == "一般纳税人", f"mode={mode}"
    assert material.tax_included_flag is True, f"mode={mode}"
    assert material.tax_rate == Decimal("0.1300"), f"mode={mode}"
    assert material.price_source == "manual", f"mode={mode}"
    assert material.effective_from == date(2026, 5, 1), f"mode={mode}"
    assert material.effective_to == date(2027, 5, 1), f"mode={mode}"


def test_yida_sync_creates_new_material_with_null_stage2_fields(db_session) -> None:
    """new_only / full mode 首次创建物料时，6 个新字段默认 NULL（tax_included_flag = False）。"""
    service = MaterialSyncService(db_session, _StubClient())
    result = MaterialSyncResult()
    service._upsert_material(_normalized("MAT-S2-NEW"), result, mode="full")  # noqa: SLF001
    db_session.flush()

    created = (
        db_session.query(models.Material)
        .filter(models.Material.material_code == "MAT-S2-NEW")
        .one()
    )
    assert created.purchase_entity_id is None
    assert created.tax_included_flag is False
    assert created.tax_rate is None
    assert created.price_source is None
    assert created.effective_from is None
    assert created.effective_to is None
