from __future__ import annotations

from pathlib import Path

import pytest

from src.config import settings
from src.planner import models
from src.planner.routers import sku_master as sku_master_router


def test_sku_master_image_proxy_download_and_cache(client, db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Route will read settings.planner_media_dir at runtime; point it to temp dir for test isolation.
    monkeypatch.setattr(settings, "planner_media_dir", str(tmp_path))
    monkeypatch.setattr(settings, "planner_persist_sku_images", True)
    monkeypatch.setattr(settings, "planner_sku_image_cache_max_files", 1000)
    monkeypatch.setattr(settings, "planner_sku_image_cache_ttl_days", 365)

    calls = {"n": 0}

    def fake_download(url: str):
        calls["n"] += 1
        assert url == "https://img.example.com/a.webp"
        return b"fake-bytes", "image/webp"

    monkeypatch.setattr(sku_master_router, "_download_image", fake_download)

    sm = models.SkuMaster(
        erp_sku_barcode="BC-IMG-1",
        spec_text="whatever",
        images_json={"spec_image": "https://img.example.com/a.webp"},
        metadata_json={},
    )
    db_session.add(sm)
    db_session.commit()

    # First request: triggers download and persists
    r1 = client.get(f"/api/planner/sku-master/{sm.id}/images/spec")
    assert r1.status_code == 200, r1.text
    assert r1.content == b"fake-bytes"
    assert calls["n"] == 1

    # Second request: should hit local cache (no extra download)
    r2 = client.get(f"/api/planner/sku-master/{sm.id}/images/spec")
    assert r2.status_code == 200, r2.text
    assert r2.content == b"fake-bytes"
    assert calls["n"] == 1


