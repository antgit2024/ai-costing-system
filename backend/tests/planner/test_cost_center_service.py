"""Tests for cost_center_service (Path A §A1).

Covers:
- CRUD: create / get / list / update / soft_delete
- 6-seed expectations (seeded by Migration 0040 in production; in tests
  we hand-seed to keep SQLite create_all-only fixture paths simple)
- assign_processes batch update
- get_cost_centers_with_stats: process_count + employee_count via mock
  finance employees pull
- refresh_finance_department_mapping: matches departments and appends
  to metadata.finance_department_mapping; surfaces unmatched
- finance unavailability degrades gracefully
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.planner import models
from src.planner.services import cost_center_service as ccs


def _seed_cost_center(
    db,
    *,
    code: str,
    name: str,
    type_: str = "production",
    basis: str | None = "team_hours",
    legacy_keywords: List[str] | None = None,
    department_mapping: List[str] | None = None,
) -> models.CostCenter:
    return ccs.create_cost_center(
        db,
        payload={
            "code": code,
            "name": name,
            "type": type_,
            "default_allocation_basis": basis,
            "metadata": {
                "legacy_team_keywords": legacy_keywords or [],
                "finance_department_mapping": department_mapping or [],
            },
        },
        actor="test",
    )


def _seed_six_centers(db) -> List[models.CostCenter]:
    return [
        _seed_cost_center(
            db,
            code="CC_DECOR_PROD",
            name="家居饰品生产组",
            type_="production",
            basis="team_hours",
            legacy_keywords=["家居", "饰品", "画框"],
        ),
        _seed_cost_center(
            db,
            code="CC_FABRIC_PROD",
            name="布艺生产组",
            type_="production",
            basis="team_hours",
            legacy_keywords=["布艺", "窗帘", "缝纫"],
        ),
        _seed_cost_center(
            db,
            code="CC_PRINT",
            name="印花打印组",
            type_="auxiliary",
            basis="team_hours",
            legacy_keywords=["印花", "印染"],
        ),
        _seed_cost_center(
            db,
            code="CC_CUT_EDGE",
            name="裁剪包边组",
            type_="auxiliary",
            basis="team_hours",
            legacy_keywords=["裁剪", "切割", "包边"],
        ),
        _seed_cost_center(
            db,
            code="CC_PACK_SHIP",
            name="包装发货组",
            type_="auxiliary",
            basis="headcount",
            legacy_keywords=["包装", "发货", "质检"],
        ),
        _seed_cost_center(
            db,
            code="CC_ADMIN",
            name="公共管理",
            type_="admin",
            basis="headcount",
            legacy_keywords=["管理", "行政", "厂部"],
        ),
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_cost_center_minimal(db_session):
    cc = ccs.create_cost_center(
        db_session,
        payload={"code": "CC_TEST_1", "name": "测试", "type": "production"},
        actor="alice",
    )
    assert cc.id
    assert cc.code == "CC_TEST_1"
    assert cc.type == "production"
    log = (cc.metadata_json or {}).get("assignment_log") or []
    assert log and log[0]["action"] == "create" and log[0]["by"] == "alice"


def test_create_cost_center_validates_type(db_session):
    with pytest.raises(ValueError, match="invalid type"):
        ccs.create_cost_center(
            db_session, payload={"code": "X", "name": "X", "type": "bogus"}
        )


def test_create_cost_center_unique_code(db_session):
    ccs.create_cost_center(
        db_session, payload={"code": "CC_X", "name": "X", "type": "production"}
    )
    with pytest.raises(ValueError, match="already exists"):
        ccs.create_cost_center(
            db_session, payload={"code": "CC_X", "name": "Y", "type": "production"}
        )


def test_list_cost_centers_filters(db_session):
    _seed_six_centers(db_session)
    rows = ccs.list_cost_centers(db_session)
    assert len(rows) == 6
    # soft-delete one + filter
    rows[0].deleted_at = rows[0].created_at
    rows[0].is_active = False
    db_session.commit()
    rows2 = ccs.list_cost_centers(db_session)
    assert len(rows2) == 5
    # include_deleted=True returns 6 again (regardless of is_active)
    rows3 = ccs.list_cost_centers(
        db_session, include_inactive=True, include_deleted=True
    )
    assert len(rows3) == 6


def test_update_cost_center(db_session):
    cc = _seed_cost_center(
        db_session, code="CC_UP_1", name="原名", legacy_keywords=["a"]
    )
    out = ccs.update_cost_center(
        db_session,
        cost_center_id=cc.id,
        patch={"name": "新名", "default_allocation_basis": "revenue"},
        actor="bob",
    )
    assert out.name == "新名"
    assert out.default_allocation_basis == "revenue"
    log = (out.metadata_json or {}).get("assignment_log") or []
    assert any(e["action"] == "update" for e in log)


def test_soft_delete_cost_center(db_session):
    cc = _seed_cost_center(db_session, code="CC_DEL", name="ToDelete")
    ccs.soft_delete_cost_center(db_session, cost_center_id=cc.id, actor="ops")
    db_session.refresh(cc)
    assert cc.deleted_at is not None
    assert cc.is_active is False


def test_assign_processes_binds_rows(db_session):
    cc = _seed_cost_center(db_session, code="CC_BIND", name="Bind")
    p1 = models.Process(
        process_code="P_TEST_1", process_name="测试工序1", charging_mode="count"
    )
    p2 = models.Process(
        process_code="P_TEST_2", process_name="测试工序2", charging_mode="count"
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    bound = ccs.assign_processes(
        db_session, cost_center_id=cc.id, process_ids=[p1.id, p2.id], actor="ops"
    )
    assert bound == 2
    db_session.refresh(p1)
    db_session.refresh(p2)
    assert p1.cost_center_id == cc.id
    assert p2.cost_center_id == cc.id


# ---------------------------------------------------------------------------
# Stats — process_count + employee_count via finance pull
# ---------------------------------------------------------------------------


_FINANCE_EMPLOYEES_FIXTURE = [
    {"id": "e1", "name": "张某", "department": "缝纫一组", "is_active": True},
    {"id": "e2", "name": "李某", "department": "缝纫二组", "is_active": True},
    {"id": "e3", "name": "王某", "department": "印染组", "is_active": True},
    {"id": "e4", "name": "刘某", "department": "包装组", "is_active": True},
    {"id": "e5", "name": "陈某", "department": "切割组", "is_active": True},
]


def _fake_envelope(rows):
    class _Env:
        def __init__(self, data, source="mock"):
            self.data = data
            self.data_source = source

    return _Env(rows)


def test_stats_with_finance_employees_mocked(db_session):
    centers = _seed_six_centers(db_session)
    fab = [c for c in centers if c.code == "CC_FABRIC_PROD"][0]
    fab.metadata_json = {
        **(fab.metadata_json or {}),
        "finance_department_mapping": ["缝纫一组", "缝纫二组"],
    }
    db_session.commit()

    proc = models.Process(
        process_code="P_FAB_1",
        process_name="布艺工序",
        charging_mode="count",
        cost_center_id=fab.id,
    )
    db_session.add(proc)
    db_session.commit()

    with patch(
        "src.planner.services.cost_center_service.get_finance_c1_client"
    ) as mock_client:
        mock_client.return_value.list_employees.return_value = _fake_envelope(
            _FINANCE_EMPLOYEES_FIXTURE
        )
        rows = ccs.get_cost_centers_with_stats(db_session)
    by_code = {cc.code: stats for cc, stats in rows}
    assert by_code["CC_FABRIC_PROD"].employee_count == 2  # 缝纫一组 + 缝纫二组
    assert by_code["CC_FABRIC_PROD"].process_count == 1
    assert by_code["CC_PRINT"].employee_count == 1  # 印染组 (legacy keyword)
    assert by_code["CC_PACK_SHIP"].employee_count == 1  # 包装组 (legacy keyword)
    assert by_code["CC_FABRIC_PROD"].finance_data_source == "mock"


def test_stats_finance_unavailable_returns_zero_employees(db_session):
    centers = _seed_six_centers(db_session)
    from src.planner.services.finance_c1_client import FinanceC1Error

    with patch(
        "src.planner.services.cost_center_service.get_finance_c1_client"
    ) as mock_client:
        mock_client.return_value.list_employees.side_effect = FinanceC1Error("down")
        rows = ccs.get_cost_centers_with_stats(db_session)
    assert len(rows) == 6
    for _, stats in rows:
        assert stats.employee_count == 0
        assert stats.finance_data_source == "unavailable"
        assert any("finance_employees_unavailable" in w for w in stats.finance_warnings)


# ---------------------------------------------------------------------------
# refresh_finance_department_mapping
# ---------------------------------------------------------------------------


def test_refresh_finance_dept_mapping_appends_new(db_session):
    centers = _seed_six_centers(db_session)
    new_dept_rows = [
        {"id": "e1", "department": "缝纫一组", "is_active": True},
        {"id": "e2", "department": "缝纫二组", "is_active": True},
        {"id": "e3", "department": "印花组", "is_active": True},
        {"id": "e4", "department": "未匹配的怪名字", "is_active": True},
    ]
    with patch(
        "src.planner.services.cost_center_service.get_finance_c1_client"
    ) as mock_client:
        mock_client.return_value.list_employees.return_value = _fake_envelope(
            new_dept_rows
        )
        result = ccs.refresh_finance_department_mapping(db_session, actor="test")
    assert "未匹配的怪名字" in result.unmatched_departments
    assert result.cost_centers_updated >= 1
    fab = ccs.get_by_code(db_session, code="CC_FABRIC_PROD")
    mapped = (fab.metadata_json or {}).get("finance_department_mapping") or []
    assert "缝纫一组" in mapped
    assert "缝纫二组" in mapped


def test_refresh_finance_dept_mapping_unavailable_is_soft(db_session):
    centers = _seed_six_centers(db_session)
    from src.planner.services.finance_c1_client import FinanceC1Error

    with patch(
        "src.planner.services.cost_center_service.get_finance_c1_client"
    ) as mock_client:
        mock_client.return_value.list_employees.side_effect = FinanceC1Error("oops")
        result = ccs.refresh_finance_department_mapping(db_session, actor="ops")
    assert result.data_source == "unavailable"
    assert result.cost_centers_updated == 0
    # Pre-existing mappings (none here) untouched; warnings carries the cause.
    assert any("finance_employees_unavailable" in w for w in result.warnings)


def test_get_by_code_returns_none_for_missing(db_session):
    assert ccs.get_by_code(db_session, code="DOES_NOT_EXIST") is None


def test_list_active_excludes_deleted(db_session):
    centers = _seed_six_centers(db_session)
    ccs.soft_delete_cost_center(db_session, cost_center_id=centers[0].id, actor="ops")
    rows = ccs.list_active(db_session)
    assert len(rows) == 5
    assert centers[0].id not in {c.id for c in rows}
