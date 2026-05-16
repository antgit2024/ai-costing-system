/**
 * 三标签分类工具 — 系统标签 / 商家标签 / ERP 标签
 *
 * 设计背景 (2026-05-16 与用户对齐, 见 jackyun_erp_goods_master_sync_backlog.md §17)
 * - 系统标签 (sys) = 真源 (Source of Truth)
 *   bound_variant_code (OZU-004) 或 bound_model_code (OZU) — 我们权威识别出的标准模型变体
 * - 商家标签 (shop) = 信息来源, 不是真源
 *   shop_spec_code — 网店运营录入的"商家编码"
 *   * 历史脏数据 (Q24091001PGZD-...) 几十万 → 不可解, 用"脏"颜色标
 *   * 新上架的归一化值 (KB8-001) → 闭环干净
 * - ERP 标签 = 下游镜像, 给工厂用
 *   out_sku_code — ERP 那边的 outSkuCode, 反写后才有值
 *
 * 三者数据只能单向流动: 商家 → 系统 → ERP. 严禁 ERP 反推系统.
 */

import type { SkuMaster } from '@/types/planner'

// ============================================================================
// 各标签的状态枚举
// ============================================================================

export type SysTagState =
  | { kind: 'matched'; modelCode: string; variantCode?: string; modelName?: string } // 已绑定到 standard model
  | { kind: 'bundle'; bundleCode: string; presetSelector?: string; bundleName?: string } // 已绑定到 bundle template
  | { kind: 'unmatched' } // 未匹配 / 未绑定

export type ShopTagState =
  | { kind: 'clean'; value: string; rawIfChanged?: string } // 归一化后是标准变体码 (KB8-001)
  | { kind: 'dirty'; value: string; rawIfChanged?: string } // 历史脏值 / 网店随手填的款号
  | { kind: 'empty' } // 没有商家编码

export type ErpTagState =
  | { kind: 'synced'; value: string } // 已反写, ERP 的 outSkuCode = 我们系统值
  | { kind: 'mismatch'; erpValue: string; sysExpected: string } // ERP 有值但跟系统不一致
  | { kind: 'waiting' } // 待反写 (ERP 端为空)

export interface TripleTagState {
  sys: SysTagState
  shop: ShopTagState
  erp: ErpTagState
  // 行总体状态: 用于行底色 / 排序 / 一眼概览
  // - closed: 三标签全绿 (闭环完成)
  // - ready_to_writeback: 系统标签已识别, 但 ERP 还没反写
  // - shop_dirty_only: 只有商家原值且是脏的, 需要运营梳理
  // - shop_clean_only: 有干净的商家原值但还没绑定到 standard model
  // - empty: 三个都没有, 完全未整理
  overall: 'closed' | 'ready_to_writeback' | 'shop_dirty_only' | 'shop_clean_only' | 'empty'
}

// ============================================================================
// 判定函数
// ============================================================================

/**
 * 判断商家编码是否"干净" — 即归一化后的标准变体码格式.
 *
 * 规则: 形如 `MMM-XXX` / `MMM-XXX-YYY`, 其中 MMM 是 3 位字母数字 (模型码),
 * XXX 是 2-8 位变体码, 可选 -YYY 后缀.
 * 例子:
 *   - KB8-001 ✓
 *   - OZU-004 ✓
 *   - KB8-001-TMALL ✓
 *   - Q24091001 ✗ (没有横线)
 *   - Q24091001PGZD-Q24091001A-2525 ✗ (前缀过长, 不是 3 字符)
 */
const CLEAN_PATTERN = /^[A-Z0-9]{3}-[A-Z0-9]{2,8}(-[A-Z0-9]{1,16})?$/

export const isShopSpecCodeClean = (v: string | null | undefined): boolean => {
  if (!v) return false
  const s = String(v).trim().toUpperCase()
  return CLEAN_PATTERN.test(s)
}

/**
 * 从 SkuMaster 行计算三标签状态.
 *
 * 注意: SkuMaster 类型上 bundle_template_name / shop_spec_code_raw 等可能是 metadata
 * 嵌套字段, 这里都按 (sku as any).fallback 兼容.
 */
export const computeTripleTagState = (sku: SkuMaster | Record<string, any>): TripleTagState => {
  const m = sku as any

  // ---- 系统标签 ----
  const modelCode = String(m.bound_model_code || '').trim()
  const variantCode = String(m.bound_variant_code || '').trim()
  const modelName = String(m.bound_model_name || '').trim()
  const bundleCode = String(m.bundle_template_code || m.metadata_json?.bundle_template_code || '').trim()
  const bundleSelector = String(m.bundle_preset_selector || m.metadata_json?.bundle_preset_selector || '').trim()
  const bundleName = String(m.bundle_template_name || m.metadata_json?.bundle_template_name || '').trim()

  let sys: SysTagState
  if (modelCode) {
    sys = { kind: 'matched', modelCode, variantCode: variantCode || undefined, modelName: modelName || undefined }
  } else if (bundleCode) {
    sys = { kind: 'bundle', bundleCode, presetSelector: bundleSelector || undefined, bundleName: bundleName || undefined }
  } else {
    sys = { kind: 'unmatched' }
  }

  // ---- 商家标签 ----
  const shopValueRaw = String(m.shop_spec_code || '').trim()
  const shopRaw = String(m.metadata_json?.shop_spec_code_raw || m.shop_spec_code_raw || '').trim()
  let shop: ShopTagState
  if (!shopValueRaw) {
    shop = { kind: 'empty' }
  } else if (isShopSpecCodeClean(shopValueRaw)) {
    shop = { kind: 'clean', value: shopValueRaw, rawIfChanged: shopRaw || undefined }
  } else {
    shop = { kind: 'dirty', value: shopValueRaw, rawIfChanged: shopRaw || undefined }
  }

  // ---- ERP 标签 ----
  const outSkuCode = String(m.out_sku_code || '').trim()
  // 系统期望的反写值 (按优先级: bound_variant_code > shop_spec_code clean > bound_model_code)
  // 这是 M4 反写源的判定逻辑, 用户已对齐: 反写源 = bound_variant_code (干净的标模变体码)
  let sysExpected = ''
  if (variantCode) sysExpected = variantCode
  else if (shop.kind === 'clean') sysExpected = shop.value
  else if (modelCode) sysExpected = modelCode

  let erp: ErpTagState
  if (!outSkuCode) {
    erp = { kind: 'waiting' }
  } else if (sysExpected && outSkuCode.toUpperCase() === sysExpected.toUpperCase()) {
    erp = { kind: 'synced', value: outSkuCode }
  } else if (sysExpected) {
    erp = { kind: 'mismatch', erpValue: outSkuCode, sysExpected }
  } else {
    // ERP 有值但系统侧没有任何期望值 (罕见: 早期手动从 ERP 同步过来的)
    erp = { kind: 'synced', value: outSkuCode }
  }

  // ---- 行总体状态 ----
  let overall: TripleTagState['overall']
  const sysOk = sys.kind === 'matched' || sys.kind === 'bundle'
  const shopOk = shop.kind === 'clean'
  const erpOk = erp.kind === 'synced'

  if (sysOk && erpOk) overall = 'closed'
  else if (sysOk && !erpOk) overall = 'ready_to_writeback'
  else if (!sysOk && shopOk) overall = 'shop_clean_only'
  else if (!sysOk && shop.kind === 'dirty') overall = 'shop_dirty_only'
  else overall = 'empty'

  return { sys, shop, erp, overall }
}

// ============================================================================
// 展示用 — 标签颜色 / 文案常量
// ============================================================================

/** Ant Design Tag color name. 集中定义便于改色. */
export const TAG_COLORS = {
  sys_matched: 'blue', // 系统 已识别 标准模型
  sys_bundle: 'purple', // 系统 已识别 套装模板
  sys_unmatched: 'default', // 系统 未匹配 (灰色)
  shop_clean: 'green', // 商家 干净格式 (KB8-001)
  shop_dirty: 'orange', // 商家 脏值 (历史 Q24091001)
  shop_empty: 'default', // 商家 没有 (灰)
  erp_synced: 'green', // ERP 已反写
  erp_mismatch: 'red', // ERP 不一致
  erp_waiting: 'default', // ERP 待反写 (灰)
} as const

export const OVERALL_LABEL: Record<TripleTagState['overall'], { text: string; color: string }> = {
  closed: { text: '✓ 全闭环', color: '#52c41a' },
  ready_to_writeback: { text: '⏳ 待反写 ERP', color: '#1890ff' },
  shop_clean_only: { text: '◌ 待绑定标模', color: '#faad14' },
  shop_dirty_only: { text: '⚠ 商家原值脏, 需梳理', color: '#fa8c16' },
  empty: { text: '◯ 未整理', color: '#bfbfbf' },
}
