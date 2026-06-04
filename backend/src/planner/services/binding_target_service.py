"""
Unified "binding target" search service.

业务背景
--------
"绑定目标"指：一个对外的"货品/SKU 标的"在系统里可能落到两类对象上：
  1) **标准模型 (model)**：一级=model_code（KB8），二级=variant_code（KB8-001）。
     - 一级总是必选。
     - 二级是"材质变体"，业务上**可空**（表示"不指定具体变体，按模型基础线计算"）。
  2) **套装模板 (bundle)**：一级=bundle_template_code（KIT01），二级=preset_selector（B:KIT01:A）。
     - 一级总是必选。
     - 二级是 phrase preset，业务上**通常必选**（套装离开 preset 没有可执行 BOM）。

这两类对象在多个业务场景下都需要"二选一选目标"：
  - SKU 主档人工绑定 / 列表筛选
  - 笛卡尔属性绑定（即将到来）
  - 天猫 SKU 模板生成
  - 其他需要"按一个目标过滤/索引"的视图

历史上，每个页面都会**单独**调用 `published-standard-models` 和 `bundle-templates` 两个候选接口、
自己再合并/分组，造成大量重复代码并易漂移。本 service 提供统一的搜索能力，
允许前端 `<TargetPicker />` 用一个端点拿到完整候选树。

不变量
------
- 仅返回**未归档**的对象。
- 标准模型仅返回**存在 published 标准版本**的（与 sku_master 自动绑定一致，避免选到草稿 / 未发布模型）。
- 变体码 / preset_selector 列表会去重并按字典序升序。
- 总返回长度受 `limit` 控制（防止前端一次拉爆），默认 50、上限 500。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models


def _bundle_presets(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 BundleTemplate.metadata_json.phrase_presets 提取规范化的 preset 列表。

    源数据每条来自 BundleTemplatesPage 的 phrase_presets 编辑器，字段：
      - selector: 字母短码（AA/AB/…）
      - phrase:   **实际生产字段** —— 中文短语（"黄金绒抱枕双面印花45X45+PP棉枕芯"）
      - label:    历史/兼容字段
      - mode:     'force' / 'parse'，决定天猫 SKU 模板生成时 token 前缀（Z- / B-）
                  - 'force' = 指定（不参与 SKU 笛卡尔积，强制走该 preset 的 components）
                  - 其它/缺省 = 'parse'

    本函数统一规范：
      - selector trim + 大写
      - label 优先级：phrase > label > selector （兼容历史/未来字段）
      - mode trim 并归一化为 'force' / 'parse'
      - 去掉 selector 为空的项
      - 按 selector 升序
    """
    raw = (meta or {}).get("phrase_presets") or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for it in raw:
        if not isinstance(it, dict):
            continue
        sel = str(it.get("selector") or "").strip().upper()
        if not sel or sel in seen:
            continue
        seen.add(sel)
        # 同 BoundTargetPicker：phrase 优先（业务上是中文短语），其次 label，最后回退到 selector
        phrase = str(it.get("phrase") or "").strip()
        legacy_label = str(it.get("label") or "").strip()
        label = phrase or legacy_label or sel
        mode_raw = str(it.get("mode") or "").strip().lower()
        mode = "force" if mode_raw == "force" else "parse"
        out.append({"selector": sel, "label": label, "mode": mode})
    out.sort(key=lambda x: x["selector"])
    return out


def _model_variants(version_id: str, db: Session) -> List[Dict[str, Any]]:
    """抽取已发布标准版本下所有 token 一级变体的 (variant_code, material_name) 摘要。

    与 ProductModelRead.current_published_variant_codes 同语义，单独抽出供本 service 使用。
    展示名优先级（与 _serialize_model 一致）：
      1. metadata_json.display_name（用户显式填的"对客显示名"，如"麻感冰丝"）
      2. items[0].material_name（兜底：实际替换物料的内部库存名）
    label 形如 "麻感冰丝(KB8-001)"；若都为空则退化为 "KB8-001"。
    """
    rows = (
        db.query(models.ProductModelLineVariant)
        .filter(
            models.ProductModelLineVariant.version_id == version_id,
            models.ProductModelLineVariant.is_archived.is_(False),
        )
        .all()
    )
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for vr in rows:
        meta = vr.metadata_json or {}
        code = str(meta.get("variant_code") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        display_name = str(meta.get("display_name") or "").strip() or None
        material_name: Optional[str] = display_name
        if not material_name:
            for it in vr.items or []:
                name = str(getattr(it, "material_name", "") or "").strip()
                if name:
                    material_name = name
                    break
        label = f"{material_name}({code})" if material_name else code
        out.append({"variant_code": code, "material_name": material_name, "label": label})
    out.sort(key=lambda x: x["variant_code"])
    return out


def _normalize_search(search: Optional[str]) -> Optional[str]:
    """搜索词全交给 Python 端做小写子串匹配。
    （早期实现尝试在 SQL 端用 ilike 收敛 code/name，但 search 也可能命中变体编码/材质名/preset 文本，
    SQL 收敛会把承载它们的模型/套装排除掉，故改为统一在 Python 端兜底。）
    """
    s = (search or "").strip()
    return s.lower() if s else None


def search_binding_targets(
    db: Session,
    *,
    search: Optional[str],
    kind: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    """
    Returns a unified candidate list for the "binding target" picker.

    Args:
        search: free text matched against {model_code, model_name, bundle_code, bundle_name,
                variant_code, variant material_name, preset_selector, preset_label}.
                Match is case-insensitive substring on code/name (DB) and text fields (Python).
        kind:   limit to a kind: "model" | "bundle". None = both.
        limit:  cap on total returned items (sum across kinds), defaults to 50, max 500.

    Returns:
        {
          "items": [
            {"kind": "model",  ...},
            {"kind": "bundle", ...},
          ],
          "truncated": bool,           # True 表示因 limit 截断、还有更多可加 search 收敛
        }
    """
    limit = max(min(int(limit or 50), 500), 1)
    requested_kind = (kind or "").strip().lower() or None
    if requested_kind not in (None, "model", "bundle"):
        raise ValueError("kind 必须是 'model' / 'bundle' 之一，或不传")

    lower_term = _normalize_search(search)

    items: List[Dict[str, Any]] = []
    truncated = False

    # 当存在 search 时，SQL 端**不再**用 ilike(code/name) 收敛，
    # 因为 search 可能命中变体编码（KB8-001）或材质名（仿羊绒）—— SQL 收敛会把承载它们的模型排除掉。
    # 取而代之：SQL 端只按 archived/published 过滤（基础硬约束），
    # 然后在 Python 端按 lower_term 跨字段匹配（code/name + 任意变体 code/material_name/label）。
    # 兜底用 SQL 上限避免极端规模下 OOM。
    SCAN_CAP = max(limit * 8, 200)

    # ---------- 标准模型 ----------
    if requested_kind in (None, "model"):
        q = (
            db.query(models.ProductModel, models.ProductModelVersion)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.model_id == models.ProductModel.id,
            )
            .filter(
                models.ProductModel.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModelVersion.version_kind == "standard",
                models.ProductModelVersion.version_status == "published",
            )
            .order_by(models.ProductModel.model_code.asc())
        )
        rows = q.limit(SCAN_CAP).all()

        for m, v in rows:
            variants = _model_variants(v.id, db)
            # 当 search 命中模型 code/name 时，无论变体文本是否匹配都保留；
            # 当 search 没命中模型 code/name（即 ilike 没过滤生效，或者匹配在变体上），
            # 才按变体文本兜底。这样在 search="KB8-001" 时也能找回 KB8。
            if lower_term:
                code_hit = lower_term in str(m.model_code or "").lower()
                name_hit = lower_term in str(m.model_name or "").lower()
                vari_hit = any(
                    lower_term in (vv["variant_code"] or "").lower()
                    or lower_term in (vv.get("material_name") or "").lower()
                    or lower_term in (vv.get("label") or "").lower()
                    for vv in variants
                )
                if not (code_hit or name_hit or vari_hit):
                    continue
            items.append(
                {
                    "kind": "model",
                    "id": m.id,
                    "code": m.model_code,
                    "name": m.model_name,
                    "published_version_id": v.id,
                    "version_label": v.version_label,
                    "variants": variants,
                }
            )
            if len(items) >= limit:
                break

        if len(items) >= limit and len(rows) > limit:
            truncated = True

    # ---------- 套装模板 ----------
    if requested_kind in (None, "bundle") and len(items) < limit:
        # 同模型那段：search 时不用 SQL 收敛，让 Python 端兜底匹配 preset 文本。
        q2 = (
            db.query(models.BundleTemplate)
            .filter(models.BundleTemplate.is_archived.is_(False))
            .order_by(models.BundleTemplate.code.asc())
        )
        rows2 = q2.limit(SCAN_CAP).all()

        for t in rows2:
            presets = _bundle_presets(getattr(t, "metadata_json", None) or {})
            if lower_term:
                code_hit = lower_term in str(t.code or "").lower()
                name_hit = lower_term in str(t.name or "").lower()
                pres_hit = any(
                    lower_term in (p["selector"] or "").lower() or lower_term in (p["label"] or "").lower()
                    for p in presets
                )
                if not (code_hit or name_hit or pres_hit):
                    continue
            items.append(
                {
                    "kind": "bundle",
                    "id": t.id,
                    "code": t.code,
                    "name": t.name,
                    "presets": presets,
                }
            )
            if len(items) >= limit:
                truncated = truncated or len(rows2) > (len(items) - sum(1 for x in items if x["kind"] != "bundle"))
                break

    return {"items": items, "truncated": truncated}
