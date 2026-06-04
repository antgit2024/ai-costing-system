from __future__ import annotations

from src.planner import models


def _create_published_standard_model(db_session, *, code: str, name: str):
    m = models.ProductModel(model_code=code, model_name=name, status="active", metadata_json={})
    db_session.add(m)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label=f"{code}-20251223-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    db_session.commit()
    return m


def test_validate_recognition_keywords_conflict(client, db_session):
    m1 = _create_published_standard_model(db_session, code="OZU", name="丝圈地垫")
    m2 = _create_published_standard_model(db_session, code="AAA", name="别的模型")

    # Save keyword on model2 first
    resp = client.patch(f"/api/planner/product-models/{m2.id}", json={"metadata_json": {"recognition_keywords": ["丝圈"]}})
    assert resp.status_code == 200, resp.text

    # Validate for model1: should conflict on 丝圈
    v = client.post(
        f"/api/planner/product-models/{m1.id}/recognition/validate",
        json={"keywords": ["丝圈地垫", "丝圈"]},
    )
    assert v.status_code == 200, v.text
    body = v.json()
    assert body["ok"] is False
    assert body["conflicts"].get("丝圈") == "AAA"


