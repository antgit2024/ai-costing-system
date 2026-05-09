/**
 * Shop spec code (商家编码 / merchant SKU) classifier — shared by SKU master,
 * shipment management (Done/Pending), and shipment ledger pages.
 *
 * Goal: a single source of truth for "is this merchant code usable as the
 * P0 anchor for auto-binding?" so the UI can show consistent visual cues
 * across pages.
 *
 * Mirrors the strict extractor in
 * ``backend/src/planner/services/sku_master_service.py::_extract_model_code_from_shop_spec``.
 * If you change rules here, update both sides + the unit tests.
 */

export type ShopSpecCodeKind = 'structured' | 'platform' | 'malformed' | 'empty'

export interface ShopSpecCodeClassification {
  kind: ShopSpecCodeKind
  /** Detected model code prefix (e.g. "KB8") when kind === 'structured'. */
  modelCode?: string
  /** Short label for UI (e.g. "可自动匹配 / 平台ID / 不规范 / 未同步"). */
  label: string
  /** Antd color name suitable for <Tag color={...}>. */
  tagColor?: 'green' | 'default' | 'orange' | undefined
  /** Antd Typography type (used to render text variants without Tag). */
  textType?: 'success' | 'secondary' | 'warning' | undefined
  /** Tooltip explanation (full sentence). */
  tooltip: string
}

const STRUCTURED_PAIR_RE = /^([A-Z0-9]{3})-[A-Z0-9]{2,8}(?:-[A-Z0-9]{1,16})?$/
const PURE_DIGITS_RE = /^\d+$/

/**
 * Classify a shop spec code value.
 * Returns ``{kind:'empty'}`` when ``raw`` is null/undefined/blank.
 */
export function classifyShopSpecCode(
  raw: string | null | undefined,
): ShopSpecCodeClassification {
  const s = (raw ?? '').toString().trim()
  if (!s) {
    return {
      kind: 'empty',
      label: '未同步',
      textType: 'secondary',
      tooltip: '该 SKU 还没有商家编码——可能是吉客云上未维护 tradeGoodsno，或同步未抽取到。手工绑定后下次发货依然有效。',
    }
  }

  const upper = s.toUpperCase()

  // 1. structured — 3-char alnum (not pure digits) OR XXX-YYY[-ZZZ] structured variant code OR PM legacy
  if (upper.length === 3 && /^[A-Z0-9]{3}$/.test(upper) && !PURE_DIGITS_RE.test(upper)) {
    return {
      kind: 'structured',
      modelCode: upper,
      label: '可自动匹配',
      tagColor: 'green',
      textType: 'success',
      tooltip: `规范化商家编码（模型码 ${upper}）。自动匹配引擎已启用 P0 锚点，新发货同步即可自动绑定。`,
    }
  }
  const m = STRUCTURED_PAIR_RE.exec(upper)
  if (m && !PURE_DIGITS_RE.test(m[1])) {
    return {
      kind: 'structured',
      modelCode: m[1],
      label: '可自动匹配',
      tagColor: 'green',
      textType: 'success',
      tooltip: `规范化商家编码（模型码 ${m[1]} / 变体 ${upper}）。自动匹配引擎已启用 P0 锚点。`,
    }
  }
  if (upper.startsWith('PM') && /^[A-Z0-9_-]+$/.test(upper)) {
    return {
      kind: 'structured',
      modelCode: upper,
      label: '可自动匹配',
      tagColor: 'green',
      textType: 'success',
      tooltip: `传统 PM 前缀模型码（${upper}）。自动匹配引擎已启用 P0 锚点。`,
    }
  }

  // 2. platform — pure digits (淘宝/天猫平台默认 ID)
  if (PURE_DIGITS_RE.test(s)) {
    return {
      kind: 'platform',
      label: '平台默认ID',
      tagColor: 'default',
      textType: 'secondary',
      tooltip: `${s}\n\n这是淘宝/天猫平台默认生成的商品 ID，无法用于自动匹配。如需让该 SKU 自动绑定模型，请在吉客云后台把 tradeGoodsno 改成 KB8-001 等规范化商家编码。`,
    }
  }

  // 3. malformed — non-empty, non-digit, but doesn't match structured pattern
  return {
    kind: 'malformed',
    label: '不规范',
    tagColor: 'orange',
    textType: 'warning',
    tooltip: `${s}\n\n商家编码格式不规范（既不是 KB8-001 这种结构化码，也不是平台默认 ID）。无法用于自动匹配，建议在吉客云改成规范格式。`,
  }
}

/** Convenience: only "可自动匹配" returns true. */
export function isAutoMatchableShopSpecCode(raw: string | null | undefined): boolean {
  return classifyShopSpecCode(raw).kind === 'structured'
}
