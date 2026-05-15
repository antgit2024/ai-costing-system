"""Tests for /api/planner/ops-assumption-schemes (taxonomy domain='ops_assumption_scheme').

T1: seed 接口幂等（连调 2 次方案数=4，is_default 正好 1 个）
T2: CRUD 流程（POST 新建 → GET 列表含新行 → PUT 改百分比 → GET 验证 → DELETE
            → GET 不含；is_default=true 删除应 400）
"""
from __future__ import annotations


BASE = "/api/planner/ops-assumption-schemes"


# ---------------------------------------------------------------------------
# T1 — seed 接口幂等
# ---------------------------------------------------------------------------


def test_seed_is_idempotent_and_keeps_single_default(client):
    """连调 2 次 seed：每次都返回 4 条预置方案；is_default 正好 1 个；inserted/existed 累计正确。"""
    # 首次 seed — 4 个全新插入
    r1 = client.post(f"{BASE}/seed")
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["inserted"] == 4
    assert body1["existed"] == 0
    assert body1["total"] == 4
    items1 = body1["items"]
    assert len(items1) == 4
    names1 = sorted(it["name"] for it in items1)
    assert names1 == sorted(["默认标准", "大促降推广", "试涨价", "0 推广（最低边界）"])
    default_count1 = sum(1 for it in items1 if it.get("is_default"))
    assert default_count1 == 1, f"expected 1 default, got {default_count1}"
    default_item1 = next(it for it in items1 if it.get("is_default"))
    assert default_item1["name"] == "默认标准"
    # 6 个百分比都已落库
    assert abs(default_item1["promotion_pct"] - 0.17) < 1e-9
    assert abs(default_item1["platform_fee_pct"] - 0.061) < 1e-9
    assert abs(default_item1["tax_pct"] - 0.08) < 1e-9
    assert abs(default_item1["labor_pct"] - 0.20) < 1e-9
    assert abs(default_item1["venue_logistics_pct"] - 0.10) < 1e-9
    assert abs(default_item1["unmodeled_cost_pct"] - 0.50) < 1e-9

    # 第二次 seed — 全部已存在，inserted=0 existed=4 total=4
    r2 = client.post(f"{BASE}/seed")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["inserted"] == 0
    assert body2["existed"] == 4
    assert body2["total"] == 4
    items2 = body2["items"]
    default_count2 = sum(1 for it in items2 if it.get("is_default"))
    assert default_count2 == 1, f"expected 1 default after re-seed, got {default_count2}"

    # GET 列表也应返回 4 条 + 1 个默认
    r3 = client.get(BASE)
    assert r3.status_code == 200, r3.text
    items3 = r3.json()["items"]
    assert len(items3) == 4
    assert sum(1 for it in items3 if it.get("is_default")) == 1


# ---------------------------------------------------------------------------
# T2 — CRUD 流程 + is_default 不可删 400
# ---------------------------------------------------------------------------


def test_crud_flow_and_default_protection(client):
    """POST → GET → PUT → GET → DELETE → GET；is_default=true 删 400。"""
    # 先 seed 4 个预置方案，确保有一个 is_default
    client.post(f"{BASE}/seed")

    # 1) POST 新建一个自定义方案（不是默认）
    payload = {
        "name": "测试方案_T2",
        "description": "T2 单测用",
        "promotion_pct": 0.15,
        "platform_fee_pct": 0.05,
        "tax_pct": 0.06,
        "labor_pct": 0.22,
        "venue_logistics_pct": 0.08,
        "unmodeled_cost_pct": 0.45,
        "is_default": False,
    }
    r_create = client.post(BASE, json=payload)
    assert r_create.status_code == 201, r_create.text
    created = r_create.json()
    new_id = created["id"]
    assert created["name"] == "测试方案_T2"
    assert abs(created["promotion_pct"] - 0.15) < 1e-9
    assert created["is_default"] is False

    # 2) GET 列表包含新行
    r_list = client.get(BASE)
    assert r_list.status_code == 200
    listed = r_list.json()["items"]
    assert any(it["id"] == new_id for it in listed)
    assert len(listed) == 5  # 4 seed + 1 new

    # 3) PUT 改百分比 + 改名
    update_payload = {
        "name": "测试方案_T2_renamed",
        "promotion_pct": 0.10,
        "labor_pct": 0.25,
    }
    r_put = client.put(f"{BASE}/{new_id}", json=update_payload)
    assert r_put.status_code == 200, r_put.text
    updated = r_put.json()
    assert updated["name"] == "测试方案_T2_renamed"
    assert abs(updated["promotion_pct"] - 0.10) < 1e-9
    assert abs(updated["labor_pct"] - 0.25) < 1e-9
    # 没被改的字段保持原值
    assert abs(updated["platform_fee_pct"] - 0.05) < 1e-9

    # 4) GET 验证改后值
    r_list2 = client.get(BASE)
    assert r_list2.status_code == 200
    listed2 = r_list2.json()["items"]
    found = next((it for it in listed2 if it["id"] == new_id), None)
    assert found is not None
    assert found["name"] == "测试方案_T2_renamed"
    assert abs(found["promotion_pct"] - 0.10) < 1e-9

    # 5) is_default=true 删除应 400
    default_item = next(it for it in listed2 if it.get("is_default"))
    r_del_default = client.delete(f"{BASE}/{default_item['id']}")
    assert r_del_default.status_code == 400, r_del_default.text
    assert "default" in r_del_default.json().get("detail", "").lower()

    # 6) DELETE 非默认方案应 204
    r_del = client.delete(f"{BASE}/{new_id}")
    assert r_del.status_code == 204

    # 7) GET 不含已删除项
    r_list3 = client.get(BASE)
    assert r_list3.status_code == 200
    listed3 = r_list3.json()["items"]
    assert not any(it["id"] == new_id for it in listed3)
    assert len(listed3) == 4  # 回到 4 seed 行


def test_put_setting_is_default_unsets_others(client):
    """PUT is_default=true 时应该把其他方案的 is_default 改 false（全表只有 1 个 default）。"""
    client.post(f"{BASE}/seed")

    r_list = client.get(BASE).json()["items"]
    # 取一个非默认的方案
    non_default = next(it for it in r_list if not it.get("is_default"))
    old_default = next(it for it in r_list if it.get("is_default"))
    assert non_default["id"] != old_default["id"]

    # PUT 把它设为 default
    r = client.put(f"{BASE}/{non_default['id']}", json={"is_default": True})
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True

    # 重新查列表：default 数量仍为 1，且 ID 已切换
    r_list2 = client.get(BASE).json()["items"]
    defaults = [it for it in r_list2 if it.get("is_default")]
    assert len(defaults) == 1
    assert defaults[0]["id"] == non_default["id"]
    # 原 default 现在应该 is_default=false
    old_now = next(it for it in r_list2 if it["id"] == old_default["id"])
    assert old_now["is_default"] is False


def test_create_validation_rejects_out_of_range(client):
    """创建时 6 个百分比必须在 [0,1]，否则 422。"""
    bad = client.post(
        BASE,
        json={
            "name": "bad",
            "promotion_pct": 1.5,  # > 1.0 → 422
            "platform_fee_pct": 0.06,
            "tax_pct": 0.08,
            "labor_pct": 0.2,
            "venue_logistics_pct": 0.1,
            "unmodeled_cost_pct": 0.5,
        },
    )
    assert bad.status_code == 422


def test_create_duplicate_name_returns_409(client):
    """domain+name 唯一约束：同名应 409。"""
    payload = {
        "name": "重名方案",
        "promotion_pct": 0.1,
        "platform_fee_pct": 0.06,
        "tax_pct": 0.08,
        "labor_pct": 0.2,
        "venue_logistics_pct": 0.1,
        "unmodeled_cost_pct": 0.5,
    }
    r1 = client.post(BASE, json=payload)
    assert r1.status_code == 201
    r2 = client.post(BASE, json=payload)
    assert r2.status_code == 409


def test_delete_not_found_returns_404(client):
    """删除不存在的方案返回 404。"""
    r = client.delete(f"{BASE}/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
