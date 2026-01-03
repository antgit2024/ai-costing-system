from __future__ import annotations

from src.planner import models


API_PREFIX = "/api/planner"


def test_process_modules_filter_by_structure_tag_and_code(client, db_session):
    m1 = models.ProcessModule(
        module_code="PMOD-STRUCT-001",
        module_name="结构模块-拉链",
        status="active",
        tags=[],
        metadata_json={"structure_tags": ["pillowcase_v1:zipper", "pillowcase_v1"]},
    )
    m2 = models.ProcessModule(
        module_code="PMOD-STRUCT-002",
        module_name="结构模块-无关",
        status="active",
        tags=[],
        metadata_json={"structure_tags": ["decoration_combo_painting_v1:frame"]},
    )
    db_session.add_all([m1, m2])
    db_session.commit()

    # exact tag match
    resp = client.get(
        f"{API_PREFIX}/process-modules",
        params={"structure_tag": "pillowcase_v1:zipper", "page": 1, "page_size": 50},
    )
    assert resp.status_code == 200, resp.text
    codes = [x["module_code"] for x in resp.json()["items"]]
    assert "PMOD-STRUCT-001" in codes
    assert "PMOD-STRUCT-002" not in codes

    # structure_code match should hit both "code" and "code:*"
    resp2 = client.get(
        f"{API_PREFIX}/process-modules",
        params={"structure_code": "pillowcase_v1", "page": 1, "page_size": 50},
    )
    assert resp2.status_code == 200, resp2.text
    codes2 = [x["module_code"] for x in resp2.json()["items"]]
    assert codes2 == ["PMOD-STRUCT-001"]


def test_product_model_versions_filter_by_structure_standard_code(client, db_session):
    model = models.ProductModel(
        model_code="PM-STRUCT-001",
        model_name="结构标准测试模型",
        status="active",
        metadata_json={},
    )
    db_session.add(model)
    db_session.commit()

    v1 = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="v1",
        metadata_json={"structure_standard_code": "pillowcase_v1"},
    )
    v2 = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="v2",
        metadata_json={"structure_standard_code": "decoration_combo_painting_v1"},
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    resp = client.get(
        f"{API_PREFIX}/product-model-versions",
        params={
            "structure_standard_code": "pillowcase_v1",
            "page": 1,
            "page_size": 50,
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["version_label"] == "v1"


