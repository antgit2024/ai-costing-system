from __future__ import annotations


def test_upload_and_download_model_version_image(client):
    # create model
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "图片测试模型",
            "model_code": "IMG-001",
            "status": "draft",
            "metadata_json": {},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    # create a sample version
    r = client.post(
        f"/api/planner/product-models/{model_id}/versions",
        json={"version_kind": "sample", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]

    # upload an image
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    r = client.post(
        f"/api/planner/product-model-versions/{vid}/images",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version_id"] == vid
    assert len(body["images"]) == 1
    assert body["images"][0]["index"] == 0

    # download the uploaded image
    r = client.get(f"/api/planner/product-model-versions/{vid}/images/0")
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")


