from __future__ import annotations

from src.planner import models
from src.planner.services import product_model_service


def _make_model(db_session, code: str = "K7Q") -> models.ProductModel:
    m = models.ProductModel(
        model_code=code,
        model_name="结构标准继承测试模型",
        status="active",
        metadata_json={},
    )
    db_session.add(m)
    db_session.flush()
    return m


def test_derive_standard_inherits_structure_standard_code(db_session):
    """
    打样 → 标准 推导：必须把源 sample 版本的 structure_standard_code
    复制到目标 standard 版本的 metadata_json 里，否则前端"结构"列会全部是空位。
    """
    model = _make_model(db_session, "K7Q")

    sample_ver = product_model_service.create_model_version(
        db=db_session,
        model=model,
        version_kind="sample",
        metadata={
            "structure_standard_code": "pillowcase_v1",
            "sample": {"width_mm": "1000", "height_mm": "1000", "quantity": "1"},
        },
    )
    assert (sample_ver.metadata_json or {}).get("structure_standard_code") == "pillowcase_v1"

    target, _stats = product_model_service.derive_standard_version(
        db_session,
        source_sample_version=sample_ver,
        target_mode="create_new",
        target_standard_version_id=None,
        apply_to="both",
    )

    assert target.version_kind == "standard"
    assert (target.metadata_json or {}).get("structure_standard_code") == "pillowcase_v1", (
        "派生标准版本必须继承源打样版本的 structure_standard_code，"
        "否则结构标准在 UI 上会全部丢失（行级 structure_slot 也会无法正确显示）"
    )


def test_derive_standard_overwrite_draft_overrides_structure_code_from_sample(db_session):
    """
    overwrite_draft 模式：以 sample 的 structure_standard_code 为准，
    覆盖目标草稿上既有的不同结构标准。语义符合"派生 = 完全继承 sample"。
    """
    model = _make_model(db_session, "K7R")

    sample_ver = product_model_service.create_model_version(
        db=db_session,
        model=model,
        version_kind="sample",
        metadata={"structure_standard_code": "pillowcase_v1"},
    )
    draft_std = product_model_service.create_model_version(
        db=db_session,
        model=model,
        version_kind="standard",
        metadata={"structure_standard_code": "decoration_combo_painting_v1"},
    )

    target, _stats = product_model_service.derive_standard_version(
        db_session,
        source_sample_version=sample_ver,
        target_mode="overwrite_draft",
        target_standard_version_id=draft_std.id,
        apply_to="both",
    )

    assert target.id == draft_std.id
    assert (target.metadata_json or {}).get("structure_standard_code") == "pillowcase_v1"


def test_derive_standard_keeps_target_structure_code_when_sample_missing(db_session):
    """
    源 sample 未设 structure_standard_code 时，应保留目标 draft 上的既有值，
    而不是清空（避免误伤用户在 draft 上手动配置的结构标准）。
    """
    model = _make_model(db_session, "K7S")

    sample_ver = product_model_service.create_model_version(
        db=db_session,
        model=model,
        version_kind="sample",
        metadata={},
    )
    assert "structure_standard_code" not in (sample_ver.metadata_json or {})

    draft_std = product_model_service.create_model_version(
        db=db_session,
        model=model,
        version_kind="standard",
        metadata={"structure_standard_code": "tablecloth_v1"},
    )

    target, _stats = product_model_service.derive_standard_version(
        db_session,
        source_sample_version=sample_ver,
        target_mode="overwrite_draft",
        target_standard_version_id=draft_std.id,
        apply_to="both",
    )

    assert (target.metadata_json or {}).get("structure_standard_code") == "tablecloth_v1"
