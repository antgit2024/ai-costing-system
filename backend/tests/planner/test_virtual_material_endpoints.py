from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from src.planner import models

API_PREFIX = "/api/planner/base-config"


def _create_material(db, *, code: str, name: str, is_active: bool = True) -> models.Material:
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="test",
        unit="pcs",
        unit_price=Decimal("1.23"),
        currency="CNY",
        status="active" if is_active else "inactive",
        is_active=is_active,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def test_virtual_material_create_duplicate_code_returns_409(client: TestClient):
    payload = {
        "virtual_code": "VM-DUP-001",
        "name": "Dup VM",
        "virtual_kind": "kit",
        "unit": "套",
        "status": "draft",
        "metadata_json": {},
    }
    resp1 = client.post(f"{API_PREFIX}/virtual-materials", json=payload)
    assert resp1.status_code == 201, resp1.text

    resp2 = client.post(f"{API_PREFIX}/virtual-materials", json=payload)
    assert resp2.status_code == 409, resp2.text
    assert "虚拟物料编码已存在" in resp2.json()["detail"]


def test_virtual_material_bindings_reject_inactive_material(client: TestClient, db_session):
    # Create VM
    vm_resp = client.post(
        f"{API_PREFIX}/virtual-materials",
        json={
            "virtual_code": "VM-BIND-001",
            "name": "Binding VM",
            "virtual_kind": "kit",
            "unit": "套",
            "status": "draft",
            "metadata_json": {},
        },
    )
    assert vm_resp.status_code == 201, vm_resp.text
    vm_id = vm_resp.json()["id"]

    inactive = _create_material(db_session, code="MAT-INACTIVE", name="Inactive", is_active=False)

    bind_resp = client.put(
        f"{API_PREFIX}/virtual-materials/{vm_id}/bindings",
        json={
            "bindings": [
                {
                    "material_id": inactive.id,
                    "quantity_ratio": "1",
                    "loss_rate": "0",
                    "binding_type": "quantity",
                }
            ]
        },
    )
    assert bind_resp.status_code == 400, bind_resp.text
    assert "inactive" in bind_resp.json()["detail"].lower()


def test_virtual_material_update_persists_virtual_kind_in_metadata(client: TestClient):
    # Create VM as kit
    vm_resp = client.post(
        f"{API_PREFIX}/virtual-materials",
        json={
            "virtual_code": "VM-KIND-001",
            "name": "Kind VM",
            "virtual_kind": "kit",
            "unit": "套",
            "status": "draft",
            "metadata_json": {},
        },
    )
    assert vm_resp.status_code == 201, vm_resp.text
    vm_id = vm_resp.json()["id"]

    # Switch to recipe: backend stores virtual_kind in metadata_json.virtual_kind
    patch_resp = client.patch(
        f"{API_PREFIX}/virtual-materials/{vm_id}",
        json={
            "virtual_kind": "recipe",
            "unit": "平米",
            "metadata_json": {"note": "switch-to-recipe"},
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["virtual_kind"] == "recipe"

    # Reload: must remain recipe (regression for JSON in-place mutation not persisted)
    get_resp = client.get(f"{API_PREFIX}/virtual-materials/{vm_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["virtual_kind"] == "recipe"


