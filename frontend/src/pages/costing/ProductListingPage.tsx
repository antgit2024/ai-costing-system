import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Divider, Empty, Input, InputNumber, Modal, Radio, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { isAxiosError } from 'axios'

import BundlePhraseListPanel from '@/components/costing/BundlePhraseListPanel'
import {
  fetchProductModelVersionLines,
  fetchProductModels,
  fetchProductModelVersions,
  fetchBundleTemplates,
  fetchBundleTemplateByCode,
  fetchProductModelVersionsPaged,
  generateBom,
  generateBomBySpec,
  generateBomBySpecDebug,
  listLineVariants,
  parseSpec,
} from '@/services/planner'
import type { BomGenerateResponse, LineVariantCondition, LineVariantDetailRead, ProductModel, ProductModelLinesResponse, ProductModelVersionRead, SpecParseResponse } from '@/types/planner'

const { Text } = Typography

const toNumberOrNull = (v: any): number | null => {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const formatMoney2 = (v: any): string => {
  const n = toNumberOrNull(v)
  if (n == null) return '-'
  return n.toFixed(2)
}

const clamp01 = (n: number) => Math.max(0, Math.min(1, n))

const computeMaterialCostFromLines = (lines: any[]): number => {
  return (lines ?? []).reduce((acc, r) => {
    const qty = toNumberOrNull((r as any)?.computed_quantity) ?? 0
    const unit = toNumberOrNull((r as any)?.bom_unit_price) ?? 0
    const lineCost = toNumberOrNull((r as any)?.line_cost)
    const v = lineCost != null ? lineCost : qty * unit
    return acc + (Number.isFinite(v) ? v : 0)
  }, 0)
}

const getErrorMessage = (error: unknown) => {
  if (isAxiosError(error)) {
    const detail = (error as any)?.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((item) => (typeof item?.msg === 'string' ? item.msg : JSON.stringify(item))).join('; ')
    }
  }
  return (error as any)?.message ? String((error as any).message) : String(error)
}

type ProductListingDraft = {
  sku_code: string
  model_id: string | null
  model_version_id: string | null
  spec_text: string
}

type BundleTestDraft = {
  bundle_code: string | null
  bundle_selector: string | null
  bundle_input: string
  spec_text: string
}

type SalesPricingDraft = {
  channel: 'tmall' | 'jd' | 'xhs' | 'douyin'
  // 商品定位（用于预设参数，不落库）
  product_tier: 'traffic' | 'profit' | 'brand'

  // 税制（用于税金口径切换，不落库）
  taxpayer_kind: 'general' | 'small'

  // 计算模式：
  // - solve: 反推“券后成交价(GMV)”满足目标净利%
  // - diagnose: 给定券后成交价/标价，诊断净利率与成本拆解
  // - target_cost: 给定“券后成交价(GMV)”与目标净利%，反推“允许的最大进厂价/单位成本”（目标成本法）
  pricing_mode: 'solve' | 'diagnose' | 'target_cost'
  deal_gmv_input: number | null
  list_price_input: number | null

  // 目标与比例（均以“含税成交价（GMV）”为分母；毛利/利润按“不含税收入”展示）
  target_net_profit_pct: number
  platform_fee_pct: number
  ad_fee_pct: number
  // 备注：快递费改为“按件固定金额”，不再用百分比（低客单价更贴近现实）
  // 支付费：视为已包含在平台扣点中，不再单列
  fixed_cost_pct: number
  sales_commission_pct: number

  // 退货：价值折损单列（快递费为按件固定，不再用百分比）
  return_rate_pct: number
  unsellable_ratio_pct: number

  // 税金：一般纳税人，按不含税收入计
  vat_rate_pct: number
  vat_surcharge_ratio_pct: number // 附加税≈增值税的 12%（可调）
  // 进项可抵扣比例（用于估算：应纳增值税 = 销项增值税 - 可抵扣进项税额）
  // 进项税额从“进厂价/单位成本（含税）”反推：inputVatBase = factoryCost * vat/(1+vat)
  // 再按该比例抵扣：inputVatCredit = inputVatBase * input_vat_credit_pct
  input_vat_credit_pct: number
  // 平台扣点/广告费（服务类）按 6% 专票估算进项税（业务确认可抵扣）
  // 用于：inputVatFromServices = service_fee_gmv_based * serviceVat/(1+serviceVat)
  service_vat_rate_pct: number

  // 标价与活动
  promo_discount_pct: number

  // 固定金额项（按件）
  shipping_fee_fixed: number
  packaging_fee_fixed: number
  aftersale_fee_fixed: number

  // 场景字段（后续可对接字典/同步）
  city: string
  courier: string
  campaign: string
}

type SalesPricingPreset = {
  id: string
  name: string
  updated_at: string // ISO
  data: SalesPricingDraft
}

type StorePreviewDraft = {
  monthly_gmv: number
  target_net_profit_pct: number
  fixed_cost_pct: number
  ad_fee_pct: number
  platform_fee_pct: number
  platform_promo_pct: number
  shipping_fee_pct: number

  // 结构（按 GMV 占比）
  traffic_share_pct: number
  profit_share_pct: number
  brand_share_pct: number

  // 角色贡献毛利目标（贡献毛利=GMV-变动成本-产品成本-税费/退货等；此处先用“目标贡献毛利率%”表达）
  traffic_cm_pct: number
  brand_cm_pct: number
}

const SALES_PRICING_PRESETS_STORAGE_KEY = 'ai_costing_sales_pricing_presets_v1'

const loadSalesPricingPresets = (): SalesPricingPreset[] => {
  try {
    const raw = localStorage.getItem(SALES_PRICING_PRESETS_STORAGE_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    return arr
      .map((x) => ({
        id: String(x?.id ?? ''),
        name: String(x?.name ?? ''),
        updated_at: String(x?.updated_at ?? ''),
        data: x?.data as SalesPricingDraft,
      }))
      .filter((x) => x.id && x.name && x.data)
  } catch {
    return []
  }
}

const saveSalesPricingPresets = (items: SalesPricingPreset[]) => {
  try {
    localStorage.setItem(SALES_PRICING_PRESETS_STORAGE_KEY, JSON.stringify(items))
  } catch {
    // ignore
  }
}

const CHANNEL_PRESETS: Record<
  SalesPricingDraft['channel'],
  {
    label: string
    platform_fee_pct: number
    ad_fee_pct: number
  }
> = {
  tmall: { label: '天猫', platform_fee_pct: 9, ad_fee_pct: 15 },
  jd: { label: '京东', platform_fee_pct: 9, ad_fee_pct: 12 },
  xhs: { label: '小红书', platform_fee_pct: 9, ad_fee_pct: 15 },
  douyin: { label: '抖店', platform_fee_pct: 9, ad_fee_pct: 18 },
}

const TIER_PRESETS: Record<
  SalesPricingDraft['product_tier'],
  {
    label: string
    target_net_profit_pct: number
    fixed_cost_pct: number
    return_rate_pct: number
    unsellable_ratio_pct: number
  }
> = {
  traffic: { label: '引流款', target_net_profit_pct: 2, fixed_cost_pct: 15, return_rate_pct: 10, unsellable_ratio_pct: 30 },
  profit: { label: '利润款', target_net_profit_pct: 10, fixed_cost_pct: 18, return_rate_pct: 15, unsellable_ratio_pct: 50 },
  brand: { label: '形象款', target_net_profit_pct: 15, fixed_cost_pct: 20, return_rate_pct: 12, unsellable_ratio_pct: 40 },
}

const CITY_OPTIONS = ['上海', '北京', '杭州', '深圳', '广州', '成都', '武汉', '苏州', '南京', '重庆', '西安'].map((x) => ({
  label: x,
  value: x,
}))

const COURIER_OPTIONS = ['中通', '圆通', '申通', '韵达', '顺丰', '京东物流', '极兔'].map((x) => ({ label: x, value: x }))

const CAMPAIGN_OPTIONS = [
  { label: '日常', value: 'daily' },
  { label: '大促', value: 'promo' },
  { label: '直播', value: 'live' },
  { label: '达人', value: 'kol' },
]

const toSelector2 = (idx: number): string => {
  if (idx < 0 || idx >= 26 * 26) return ''
  const a = Math.floor(idx / 26)
  const b = idx % 26
  return String.fromCharCode('A'.charCodeAt(0) + a) + String.fromCharCode('A'.charCodeAt(0) + b)
}

const toBundleTokenDash = (code: string, selector?: string | null, prefix: 'B' | 'Z' = 'B'): string => {
  const c = String(code ?? '')
    .trim()
    .toUpperCase()
    .replace(/^B:/, '')
    .replace(/^Z:/, '')
    .replace(/^BUNDLE:/, 'B:')
    .replace(/^B-/, '')
    .replace(/^Z-/, '')
  const sel = String(selector ?? '').trim().toUpperCase()
  // Format rules:
  // - New short form (only when CODE length==4 and selector length==2): B-XXXXAA
  // - Legacy/compat selector form (any CODE): B-CODE-AA
  if (sel) {
    if (c.length === 4 && sel.length === 2) return `${prefix}-${c}${sel}`
    return `${prefix}-${c}-${sel}`
  }
  return `${prefix}-${c}`
}

const extractTokensForVariant = (v: any): string[] => {
  const cond = (v?.conditions ?? {}) as any
  const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
  const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
  const out: string[] = []
  for (const t of [...anyTokens, ...allTokens]) {
    const s = String(t ?? '').trim()
    if (!s) continue
    const up = s.toUpperCase()
    // runtime-only binding tokens (not customer-facing)
    if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) continue
    out.push(s)
  }
  const seen = new Set<string>()
  const uniq: string[] = []
  for (const x of out) {
    const k = String(x).trim()
    if (!k || seen.has(k)) continue
    seen.add(k)
    uniq.push(k)
  }
  return uniq
}

const normalizeSingleToken = (raw: string): string => {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  // 运营口径：{} 内只允许 1 个 TOKEN。这里把空格/逗号/顿号/分号等作为分隔符，取第一个。
  const parts = s
    .split(/[\s,，、;；]+/)
    .map((x) => String(x).trim())
    .filter(Boolean)
  return parts[0] ?? ''
}

type AttributeGroup = { key: string; options: string[]; isZeroCostGroup: boolean }
type AttributeComponentGroups = { componentIndex: number; groups: AttributeGroup[] }

const getDefaultSelectionForGroup = (g: AttributeGroup): string => {
  // zero-cost 互斥组默认空（不计入自动生成）
  if (g.isZeroCostGroup) return ''
  // 其它互斥组默认第一个非空项（兜底token优先）
  const uniq: string[] = []
  const seen = new Set<string>()
  for (const x of g.options ?? []) {
    const t = normalizeSingleToken(x)
    const k = t || '__EMPTY__'
    if (seen.has(k)) continue
    seen.add(k)
    uniq.push(t)
  }
  return uniq.find((x) => !!String(x).trim()) ?? ''
}

const getEffectiveSelection = (args: {
  presetIndex: number
  componentIndex: number
  group: AttributeGroup
  attributeGroupSelections: Record<string, string>
}): string => {
  const { presetIndex, componentIndex, group, attributeGroupSelections } = args
  const selKey = `${presetIndex}:${componentIndex}:${group.key}`
  if (Object.prototype.hasOwnProperty.call(attributeGroupSelections, selKey)) {
    return normalizeSingleToken(String(attributeGroupSelections[selKey] ?? ''))
  }
  return getDefaultSelectionForGroup(group)
}

const formatCm = (n: any): string => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  const rounded = Math.round(v * 100) / 100
  const s = String(rounded)
  // avoid trailing .0/.00
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s
}

const copyTextToClipboard = async (text: string) => {
  const s = String(text ?? '')
  if (!s) return false
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(s)
      return true
    }
  } catch {
    // ignore and fallback
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = s
    ta.style.position = 'fixed'
    ta.style.left = '-99999px'
    ta.style.top = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

const buildAttributeFormulaAndGroups = (args: {
  presetIndex: number
  presetSelector: string
  componentOrder?: number[]
  componentRows: any[]
  presetSelectedByIdx: Record<string, Record<string, any>>
  fallbackTokenOverrides: Record<string, string>
  variantTokenOptionsByVersionBaseLine: Record<string, Record<string, string[]>>
  baseLineInfoByVersionBaseLine: Record<string, Record<string, { orderIndex: number; isZeroCost: boolean }>>
  variantTokenAliasOverrides: Record<string, Record<string, string>>
}): { formula: string; components: AttributeComponentGroups[] } => {
  const {
    presetIndex,
    presetSelector,
    componentOrder,
    componentRows,
    presetSelectedByIdx,
    fallbackTokenOverrides,
    variantTokenOptionsByVersionBaseLine,
    baseLineInfoByVersionBaseLine,
    variantTokenAliasOverrides,
  } = args
  if (!Array.isArray(componentRows) || componentRows.length <= 0) return { formula: '', components: [] }

  const displayToken = (raw: string): string => {
    const t = normalizeSingleToken(raw)
    const sel = String(presetSelector ?? '').trim().toUpperCase()
    const alias = sel ? String((variantTokenAliasOverrides?.[sel] ?? {})?.[t] ?? '').trim() : ''
    return alias || t
  }

  const parts: string[] = []
  const components: AttributeComponentGroups[] = []
  const defaultOrder = componentRows.map((_, i) => i)
  const order = Array.isArray(componentOrder) && componentOrder.length ? componentOrder : defaultOrder
  for (const cIdx of order) {
    if (cIdx < 0 || cIdx >= componentRows.length) continue
    const rr = componentRows[cIdx] as any
    const versionId = String(rr?.model_version_id ?? '').trim()
    const k = `${presetIndex}:${cIdx}`
    const sel = (presetSelectedByIdx?.[k] ?? {}) as Record<string, any>

    const rawBaseLineIds: string[] = []
    const activeBaseLineIdSet = new Set<string>() // 仅“已筛选/已强制”的基准行
    for (const [baseLineId, v] of Object.entries(sel ?? {})) {
      const id = String(baseLineId ?? '').trim()
      if (!id) continue
      const parent = String((v as any)?.parent_variant_id ?? '').trim()
      const forced = String((v as any)?.forced_child_variant_id ?? '').trim()
      if (!parent && !forced) continue
      rawBaseLineIds.push(id)
      activeBaseLineIdSet.add(id)
    }
    const fm = rr?.force_variant_by_base_line && typeof rr.force_variant_by_base_line === 'object' ? rr.force_variant_by_base_line : {}
    for (const baseLineId of Object.keys(fm ?? {})) {
      const id = String(baseLineId ?? '').trim()
      if (id) {
        rawBaseLineIds.push(id)
        activeBaseLineIdSet.add(id)
      }
    }

    const infoByBase0 = (baseLineInfoByVersionBaseLine?.[versionId] ?? {}) as Record<string, { orderIndex: number; isZeroCost: boolean }>
    for (const baseLineId of Object.keys(infoByBase0 ?? {})) {
      const id = String(baseLineId ?? '').trim()
      if (!id) continue
      const isZeroCost = !!infoByBase0?.[id]?.isZeroCost
      if (isZeroCost) continue
      const overrideKey = `${versionId}:${id}`
      const defaultToken = String(fallbackTokenOverrides?.[overrideKey] ?? '').trim()
      if (!defaultToken) continue
      rawBaseLineIds.push(id)
    }
    const seenId = new Set<string>()
    const uniqBaseLineIds = rawBaseLineIds.filter((x) => (seenId.has(x) ? false : (seenId.add(x), true)))

    const infoByBase = infoByBase0
    const baseLineIdsSorted = uniqBaseLineIds.slice().sort((a, b) => {
      const ia = infoByBase?.[a]
      const ib = infoByBase?.[b]
      const za = ia?.isZeroCost ? 1 : 0
      const zb = ib?.isZeroCost ? 1 : 0
      if (za !== zb) return zb - za // zero-cost first
      const oa = Number.isFinite(ia?.orderIndex) ? Number(ia.orderIndex) : 1e9
      const ob = Number.isFinite(ib?.orderIndex) ? Number(ib.orderIndex) : 1e9
      return oa - ob
    })

    const groupsInOrder: AttributeGroup[] = []
    const seenGroupKey = new Set<string>()

    for (const baseLineId of baseLineIdsSorted) {
      const isZeroCost = !!infoByBase?.[baseLineId]?.isZeroCost
      const isActive = activeBaseLineIdSet.has(String(baseLineId))
      const overrideKey = `${versionId}:${baseLineId}`
      const defaultToken = String(fallbackTokenOverrides?.[overrideKey] ?? '').trim()
      const alt = (variantTokenOptionsByVersionBaseLine?.[versionId] ?? {})?.[baseLineId] ?? []
      const altTokens = isActive ? (Array.isArray(alt) ? alt.map((x) => String(x ?? '').trim()).filter(Boolean) : []) : []

      const seenOpt = new Set<string>()
      const opts: string[] = []
      if (isZeroCost) {
        opts.push('') // force empty default
        seenOpt.add('__EMPTY__')
      } else if (defaultToken) {
        const d = normalizeSingleToken(defaultToken)
        if (d) {
          opts.push(d)
          seenOpt.add(d)
        }
      }
      const rest = altTokens
        .map((x) => normalizeSingleToken(x))
        .filter((x) => x && !seenOpt.has(x))
        .sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      for (const t of rest) {
        seenOpt.add(t)
        opts.push(t)
      }

      if (isZeroCost) {
        const hasNonEmpty = opts.some((x) => !!String(x).trim())
        if (!hasNonEmpty) continue
      } else {
        if (!opts.length) continue
      }

      const key = opts.map((x) => (normalizeSingleToken(x) ? normalizeSingleToken(x) : '__EMPTY__')).join('|')
      if (seenGroupKey.has(key)) continue
      seenGroupKey.add(key)
      groupsInOrder.push({ key, options: opts, isZeroCostGroup: isZeroCost })
    }

    const componentFormula = groupsInOrder
      .map((g) => `[${g.options.map((t) => (normalizeSingleToken(t) ? `{${displayToken(t)}}` : '{}')).join('')}]`)
      .join('')

    const dims = `${formatCm(rr?.width_cm)}*${formatCm(rr?.height_cm)}*${formatCm(rr?.quantity)}`
    if (componentFormula) parts.push(`${componentFormula}${dims}`)
    if (groupsInOrder.length) components.push({ componentIndex: cIdx, groups: groupsInOrder })
  }
  return { formula: parts.join(' + '), components }
}

const buildAutoRuleMetaFromSelections = (args: {
  presetIndex: number
  presetSelector: string
  components: AttributeComponentGroups[]
  componentRows: any[]
  attributeGroupSelections: Record<string, string>
  componentOrder?: number[]
  groupOrderByPresetComponent?: Record<string, string[]>
  variantTokenAliasOverrides: Record<string, Record<string, string>>
}): { text: string; items: Array<{ tokens: Array<{ text: string; isFromDropdown: boolean }>; dims: string; dimsIsMissing: boolean }> } => {
  const { presetIndex, presetSelector, components, componentRows, attributeGroupSelections, componentOrder, groupOrderByPresetComponent, variantTokenAliasOverrides } = args
  const byComp = new Map<number, AttributeGroup[]>()
  for (const c of components) byComp.set(c.componentIndex, c.groups)
  const defaultOrder = componentRows.map((_: any, i: number) => i)
  const order = Array.isArray(componentOrder) && componentOrder.length ? componentOrder : defaultOrder

  const displayToken = (raw: string): string => {
    const t = normalizeSingleToken(raw)
    const sel = String(presetSelector ?? '').trim().toUpperCase()
    const alias = sel ? String((variantTokenAliasOverrides?.[sel] ?? {})?.[t] ?? '').trim() : ''
    return alias || t
  }

  const items: Array<{ tokens: Array<{ text: string; isFromDropdown: boolean }>; dims: string; dimsIsMissing: boolean }> = []
  const textParts: string[] = []

  for (const cIdx of order) {
    if (cIdx < 0 || cIdx >= componentRows.length) continue
    const rr = componentRows[cIdx] as any
    let groups = byComp.get(cIdx) ?? []
    if (!groups.length) continue
    const groupOrderKey = `${presetIndex}:${cIdx}`
    const groupOrder = groupOrderByPresetComponent?.[groupOrderKey] ?? []
    if (Array.isArray(groupOrder) && groupOrder.length) {
      const idxMap = new Map<string, number>()
      for (let i = 0; i < groupOrder.length; i++) idxMap.set(String(groupOrder[i]), i)
      groups = groups.slice().sort((a, b) => (idxMap.get(a.key) ?? 1e9) - (idxMap.get(b.key) ?? 1e9))
    }

    const tokens: Array<{ text: string; isFromDropdown: boolean }> = []
    const tokenTextParts: string[] = []
    for (const g of groups) {
      const selKey = `${presetIndex}:${cIdx}:${g.key}`
      const isFromDropdown = Object.prototype.hasOwnProperty.call(attributeGroupSelections, selKey)
      const selected = getEffectiveSelection({ presetIndex, componentIndex: cIdx, group: g, attributeGroupSelections })
      const t = displayToken(selected)
      if (!t) continue
      tokens.push({ text: t, isFromDropdown })
      tokenTextParts.push(t)
    }
    if (!tokens.length) continue
    const w = Number(rr?.width_cm ?? 0)
    const h = Number(rr?.height_cm ?? 0)
    const q = Number(rr?.quantity ?? 0)
    const dimsIsMissing = !(w > 0 && h > 0 && q > 0)
    const dims = `${formatCm(rr?.width_cm)}*${formatCm(rr?.height_cm)}*${formatCm(rr?.quantity)}`
    const tokenText = tokenTextParts.join('')
    items.push({ tokens, dims, dimsIsMissing })
    textParts.push(`${tokenText}${dims}`)
  }

  return { text: textParts.join(' + '), items }
}

export default function ProductListingPage() {
  const [mode, setMode] = useState<'single' | 'multi' | 'spec_gen' | 'sales' | 'store'>('single')
  const [specGenGeneratingSelector, setSpecGenGeneratingSelector] = useState<string | null>(null)
  const [singleModelKind, setSingleModelKind] = useState<'sample' | 'standard'>('standard')
  const [salesModelKind, setSalesModelKind] = useState<'sample' | 'standard'>('standard')
  const [draft, setDraft] = useState<ProductListingDraft>({
    sku_code: '',
    model_id: null,
    model_version_id: null,
    spec_text: '',
  })
  const [bundleDraft, setBundleDraft] = useState<BundleTestDraft>({
    bundle_code: null,
    bundle_selector: null,
    bundle_input: '',
    spec_text: '',
  })
  const [bundleAttributeGroupSelections, setBundleAttributeGroupSelections] = useState<Record<string, string>>({})
  const [bundleComponentOrderByPreset, setBundleComponentOrderByPreset] = useState<Record<string, number[]>>({})
  const [bundleGroupOrderByPresetComponent, setBundleGroupOrderByPresetComponent] = useState<Record<string, string[]>>({})

  const [parsed, setParsed] = useState<SpecParseResponse | null>(null)
  const [bom, setBom] = useState<BomGenerateResponse | null>(null)
  const [bundleComponentsDebug, setBundleComponentsDebug] = useState<any[] | null>(null)
  const [bundleDebugRaw, setBundleDebugRaw] = useState<any | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const [bundleDebugMode, setBundleDebugMode] = useState(true)

  const [salesDraft, setSalesDraft] = useState<SalesPricingDraft>({
    channel: 'tmall',
    platform_fee_pct: CHANNEL_PRESETS.tmall.platform_fee_pct,
    ad_fee_pct: CHANNEL_PRESETS.tmall.ad_fee_pct,
    fixed_cost_pct: TIER_PRESETS.profit.fixed_cost_pct,
    target_net_profit_pct: TIER_PRESETS.profit.target_net_profit_pct,
    sales_commission_pct: 0,
    product_tier: 'profit',
    taxpayer_kind: 'general',
    return_rate_pct: TIER_PRESETS.profit.return_rate_pct,
    unsellable_ratio_pct: TIER_PRESETS.profit.unsellable_ratio_pct,
    vat_rate_pct: 13,
    vat_surcharge_ratio_pct: 12,
    input_vat_credit_pct: 60,
    service_vat_rate_pct: 6,
    promo_discount_pct: 0,
    pricing_mode: 'solve',
    deal_gmv_input: null,
    list_price_input: null,
    shipping_fee_fixed: 8,
    packaging_fee_fixed: 2,
    aftersale_fee_fixed: 0,
    city: '上海',
    courier: '中通',
    campaign: 'daily',
  })

  const [storeDraft, setStoreDraft] = useState<StorePreviewDraft>({
    monthly_gmv: 600_000,
    target_net_profit_pct: 8,
    fixed_cost_pct: 15,
    ad_fee_pct: 15,
    platform_fee_pct: 6.1,
    platform_promo_pct: 10,
    shipping_fee_pct: 10,

    traffic_share_pct: 30,
    profit_share_pct: 60,
    brand_share_pct: 10,

    traffic_cm_pct: 5,
    brand_cm_pct: 40,
  })

  const [salesPresets, setSalesPresets] = useState<SalesPricingPreset[]>(() => loadSalesPricingPresets())
  const [salesPresetId, setSalesPresetId] = useState<string | null>(null)
  const [salesPresetCreateOpen, setSalesPresetCreateOpen] = useState(false)
  const [salesPresetCreateName, setSalesPresetCreateName] = useState('')

  const modelsQuery = useQuery({
    queryKey: ['product-models', 'listing', 'search', draft.sku_code ? '' : ''],
    // 这里不做自动 search（避免每次输入就请求）；先给 50 条兜底，用户用下拉搜索即可。
    queryFn: () => fetchProductModels({ page: 1, page_size: 50 }),
  })
  const models = (modelsQuery.data?.items ?? []) as ProductModel[]

  const versionsQuery = useQuery({
    queryKey: ['product-model-versions', draft.model_id],
    queryFn: () => fetchProductModelVersions(String(draft.model_id)),
    enabled: !!draft.model_id,
  })
  const versions = (versionsQuery.data ?? []) as ProductModelVersionRead[]

  const [showAllStandardVersions, setShowAllStandardVersions] = useState(false)

  const standardVersions = useMemo(() => {
    return versions.filter((v) => String(v.version_kind) === 'standard')
  }, [versions])

  const sampleVersions = useMemo(() => {
    return versions.filter((v) => String(v.version_kind) === 'sample')
  }, [versions])

  const selectableStandardVersions = useMemo(() => {
    if (showAllStandardVersions) return standardVersions
    return standardVersions.filter((v) => String(v.version_status) === 'published')
  }, [showAllStandardVersions, standardVersions])

  const bundleTemplatesQuery = useQuery({
    queryKey: ['product-listing', 'bundle-templates', 'for-test'],
    queryFn: () =>
      fetchBundleTemplates({
        include_archived: true,
        page: 1,
        page_size: 200,
      }),
  })
  const bundleTemplateOptions = useMemo(() => {
    const items = (bundleTemplatesQuery.data?.items ?? []) as any[]
    return items.map((x) => ({
      value: String(x?.code ?? '').trim(),
      label: `${toBundleTokenDash(String(x?.code ?? '').trim())} / ${String(x?.name ?? '').trim() || '-'}${x?.is_archived ? ' (archived)' : ''}`,
    }))
  }, [bundleTemplatesQuery.data])

  const bundleTokenFromBundleInput = useMemo(() => {
    const t = String(bundleDraft.bundle_input || bundleDraft.spec_text || '').trim()
    if (!t) return { code: null as string | null, selector: null as string | null }
    // Supported:
    // - B:CODE(:A) / BUNDLE:CODE(:A)
    // - B-CODE(-A)
    // - B-XXXXAA (new short, CODE length fixed to 4; selector 2 letters)
    const m = t.match(
      /(?:BUNDLE:|B:)([A-Z0-9]{4,16})(?::([A-Za-z]{1,2}))?|\bB-([A-Z0-9]{4})([A-Za-z]{2})\b|\bB-([A-Z0-9]{4,16})(?:-([A-Za-z]{1,2}))?\b/i,
    )
    if (!m) return { code: null, selector: null }
    let code = String(m[1] || m[3] || m[5] || '').toUpperCase() || null
    let sel = String(m[2] || m[4] || m[6] || '').toUpperCase() || null

    // Compat: if user pasted "B-LPYJK9AA" (missing dash before selector) for legacy 6-char codes,
    // try to split last 2 letters IF the prefix matches an existing template code.
    if (code && !sel && code.length > 4 && /^[A-Z]{2}$/.test(code.slice(-2))) {
      const maybeSel = code.slice(-2)
      const maybeCode = code.slice(0, -2)
      const exists = bundleTemplateOptions.some((x: any) => String(x?.value ?? '').trim().toUpperCase() === maybeCode)
      if (exists) {
        code = maybeCode
        sel = maybeSel
      }
    }
    return { code, selector: sel }
  }, [bundleDraft.bundle_input, bundleDraft.spec_text, bundleTemplateOptions])

  // Auto-fill: when user types/pastes B-XXXXAA or B:CODE:AA into the bundle input/spec text,
  // automatically select template code + selector (only when user hasn't explicitly chosen them yet).
  useEffect(() => {
    const code = String(bundleTokenFromBundleInput.code ?? '').trim()
    const sel = String(bundleTokenFromBundleInput.selector ?? '').trim().toUpperCase()
    if (!code) return
    setBundleDraft((d) => {
      const next: BundleTestDraft = { ...d }
      let changed = false
      if (!String(d.bundle_code ?? '').trim()) {
        next.bundle_code = code
        changed = true
      }
      if (sel && !String(d.bundle_selector ?? '').trim()) {
        next.bundle_selector = sel
        changed = true
      }
      return changed ? next : d
    })
  }, [bundleTokenFromBundleInput.code, bundleTokenFromBundleInput.selector])

  const effectiveBundleCode = useMemo(() => {
    const selected = String(bundleDraft.bundle_code ?? '').trim()
    if (selected) return selected
    return bundleTokenFromBundleInput.code
  }, [bundleDraft.bundle_code, bundleTokenFromBundleInput.code])

  const bundleTemplateDetailQuery = useQuery({
    queryKey: ['product-listing', 'bundle-template-by-code', effectiveBundleCode],
    queryFn: () => fetchBundleTemplateByCode(String(effectiveBundleCode)),
    enabled: !!effectiveBundleCode,
  })

  const bundlePhraseOptions = useMemo(() => {
    const meta: any = (bundleTemplateDetailQuery.data as any)?.metadata ?? {}
    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
    return pp.slice(0, 26 * 26).map((p: any, idx: number) => {
      const sel = String(p?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
      const phrase = String(p?.phrase ?? '').trim()
      const mode = String(p?.mode ?? '').trim()
      const tokenPrefix: 'B' | 'Z' = mode === 'force' ? 'Z' : 'B'
      const codeOnly = String(effectiveBundleCode ?? '').trim()
      const tokenDash = codeOnly ? toBundleTokenDash(codeOnly, sel, tokenPrefix) : sel
      return {
        value: sel,
        label: (
          <Space size={8}>
            <Tag
              color={tokenPrefix === 'Z' ? 'volcano' : 'blue'}
              style={{ marginInlineEnd: 0, fontSize: 12, lineHeight: '18px', padding: '0 8px', borderRadius: 999 }}
            >
              {tokenDash}
            </Tag>
            <Text ellipsis style={{ maxWidth: 260 }}>
              {phrase || '-'}
            </Text>
          </Space>
        ),
        raw: p,
        tokenPrefix,
        tokenDash,
      }
    })
  }, [bundleTemplateDetailQuery.data, effectiveBundleCode])

  const selectedBundlePresetPrefix = useMemo(() => {
    const sel = String(bundleDraft.bundle_selector ?? '').trim().toUpperCase()
    if (!sel) return 'B' as const
    const meta: any = (bundleTemplateDetailQuery.data as any)?.metadata ?? {}
    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
    const hit =
      pp.find((x: any) => String(x?.selector ?? '').trim().toUpperCase() === sel) ??
      (() => {
        if (sel.length !== 2) return null
        const a = sel.charCodeAt(0) - 'A'.charCodeAt(0)
        const b = sel.charCodeAt(1) - 'A'.charCodeAt(0)
        const idx = a * 26 + b
        return idx >= 0 ? pp[idx] : null
      })()
    const mode = String((hit as any)?.mode ?? '').trim()
    return mode === 'force' ? ('Z' as const) : ('B' as const)
  }, [bundleDraft.bundle_selector, bundleTemplateDetailQuery.data])

  const bundleSelectedPhrase = useMemo(() => {
    const sel = String(bundleDraft.bundle_selector ?? '').trim().toUpperCase()
    if (!sel) return null
    const meta: any = (bundleTemplateDetailQuery.data as any)?.metadata ?? {}
    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
    const hit =
      pp.find((x: any) => String(x?.selector ?? '').trim().toUpperCase() === sel) ??
      (() => {
        // backward compat: if presets have no selector, allow AA/AB.. map to index
        if (sel.length !== 2) return null
        const a = sel.charCodeAt(0) - 'A'.charCodeAt(0)
        const b = sel.charCodeAt(1) - 'A'.charCodeAt(0)
        const idx = a * 26 + b
        return idx >= 0 ? pp[idx] : null
      })()
    if (!hit) return null
    const phrase = String(hit?.phrase ?? '').trim()
    return phrase || null
  }, [bundleDraft.bundle_selector, bundleTemplateDetailQuery.data])

  const bundlePresetComponents = useMemo(() => {
    const sel = String(bundleDraft.bundle_selector ?? '').trim().toUpperCase()
    if (!sel) return []
    const meta: any = (bundleTemplateDetailQuery.data as any)?.metadata ?? {}
    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
    const hit =
      pp.find((x: any) => String(x?.selector ?? '').trim().toUpperCase() === sel) ??
      (() => {
        // backward compat: if presets have no selector, allow AA/AB.. map to index
        if (sel.length !== 2) return null
        const a = sel.charCodeAt(0) - 'A'.charCodeAt(0)
        const b = sel.charCodeAt(1) - 'A'.charCodeAt(0)
        const idx = a * 26 + b
        return idx >= 0 ? pp[idx] : null
      })()
    const rows = Array.isArray(hit?.components) ? hit.components : []
    return rows
  }, [bundleDraft.bundle_selector, bundleTemplateDetailQuery.data])

  const bundleTemplateMeta = useMemo(() => {
    return ((bundleTemplateDetailQuery.data as any)?.metadata ?? {}) as any
  }, [bundleTemplateDetailQuery.data])

  const bundlePhraseVariantPresets = useMemo(() => {
    const vp = bundleTemplateMeta?.phrase_variant_presets
    if (!vp || typeof vp !== 'object') return {} as Record<string, Record<string, any>>
    // Backward compatibility:
    // - legacy: { [k]: { [base_line_id]: variant_id|null } }
    // - new:    { [k]: { [base_line_id]: { parent_variant_id, child_variant_ids?, forced_child_variant_id? } } }
    const out: Record<string, Record<string, any>> = {}
    for (const [k, m] of Object.entries(vp as any)) {
      if (!m || typeof m !== 'object') continue
      const inner: Record<string, any> = {}
      for (const [baseLineId, rawSel] of Object.entries(m as any)) {
        if (!baseLineId) continue
        if (rawSel && typeof rawSel === 'object' && 'parent_variant_id' in (rawSel as any)) {
          inner[String(baseLineId)] = rawSel as any
          continue
        }
        const vid = String(rawSel ?? '').trim()
        inner[String(baseLineId)] = { parent_variant_id: vid || null }
      }
      out[String(k)] = inner
    }
    return out
  }, [bundleTemplateMeta])

  const bundleFallbackTokenOverrides = useMemo(() => {
    const fo = bundleTemplateMeta?.fallback_token_overrides ?? bundleTemplateMeta?.fallback_display_overrides
    return fo && typeof fo === 'object' ? (fo as Record<string, string>) : {}
  }, [bundleTemplateMeta])

  const bundleVariantTokenAliasOverrides = useMemo(() => {
    const vtao = bundleTemplateMeta?.variant_token_alias_overrides
    return vtao && typeof vtao === 'object' ? (vtao as Record<string, Record<string, string>>) : {}
  }, [bundleTemplateMeta])

  useEffect(() => {
    const co = bundleTemplateMeta?.component_order_by_preset
    const go = bundleTemplateMeta?.group_order_by_preset_component
    setBundleComponentOrderByPreset(co && typeof co === 'object' ? (co as any) : {})
    setBundleGroupOrderByPresetComponent(go && typeof go === 'object' ? (go as any) : {})
    setBundleAttributeGroupSelections({})
  }, [bundleTemplateMeta])

  const bundlePresetVersionIds = useMemo(() => {
    const ids = new Set<string>()
    for (const r of (bundlePresetComponents ?? []) as any[]) {
      const vid = String((r as any)?.model_version_id ?? '').trim()
      if (vid) ids.add(vid)
    }
    return Array.from(ids)
  }, [bundlePresetComponents])

  const bundlePresetVersionLinesSummaryQuery = useQuery({
    queryKey: ['product-listing', 'bundle-preset', 'version-lines-summary', bundlePresetVersionIds.join(',')],
    queryFn: async () => {
      const rows = await Promise.all(
        bundlePresetVersionIds.map(async (version_id) => {
          const data = await fetchProductModelVersionLines(String(version_id))
          return { version_id, data }
        }),
      )
      return rows
    },
    enabled: mode === 'multi' && bundlePresetVersionIds.length > 0,
  })

  const baseLineInfoByVersionBaseLineForBundle = useMemo(() => {
    const out: Record<string, Record<string, { orderIndex: number; isZeroCost: boolean }>> = {}
    for (const r of (bundlePresetVersionLinesSummaryQuery.data ?? []) as Array<{ version_id: string; data: any }>) {
      const versionId = String((r as any)?.version_id ?? '').trim()
      if (!versionId) continue
      const mats = ((r as any)?.data?.materials ?? []) as any[]
      const inner: Record<string, { orderIndex: number; isZeroCost: boolean }> = {}
      for (let i = 0; i < mats.length; i++) {
        const it = mats[i]
        const id = String(it?.id ?? '').trim()
        if (!id) continue
        const name = String(it?.material_name ?? '').trim()
        const code = String(it?.material_code ?? '').trim()
        const isZeroCost = name.includes('兜底-零成本') || code.includes('兜底-零成本')
        inner[id] = { orderIndex: i, isZeroCost }
      }
      out[versionId] = inner
    }
    return out
  }, [bundlePresetVersionLinesSummaryQuery.data])

  const bundleVariantsSummaryQuery = useQuery({
    queryKey: ['product-listing', 'bundle-preset', 'variants-summary', bundlePresetVersionIds.join(',')],
    queryFn: async () => {
      const rows = await Promise.all(
        bundlePresetVersionIds.map(async (version_id) => {
          const items = await listLineVariants({ version_id })
          return { version_id, items }
        }),
      )
      return rows
    },
    enabled: mode === 'multi' && bundlePresetVersionIds.length > 0,
  })

  const variantTokenOptionsByVersionBaseLineForBundle = useMemo(() => {
    const out: Record<string, Record<string, string[]>> = {}
    for (const x of (bundleVariantsSummaryQuery.data ?? []) as any[]) {
      const versionId = String((x as any)?.version_id ?? '').trim()
      if (!versionId) continue
      const items = Array.isArray((x as any)?.items) ? (x as any).items : []
      const byBase: Record<string, Set<string>> = {}
      for (const v of items) {
        const baseLineId = String((v as any)?.base_line_id ?? '').trim()
        if (!baseLineId) continue
        const tokens = extractTokensForVariant(v)
        if (!tokens.length) continue
        if (!byBase[baseLineId]) byBase[baseLineId] = new Set<string>()
        for (const t of tokens) byBase[baseLineId].add(String(t))
      }
      const inner: Record<string, string[]> = {}
      for (const [baseLineId, set] of Object.entries(byBase)) {
        inner[baseLineId] = Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      }
      out[versionId] = inner
    }
    return out
  }, [bundleVariantsSummaryQuery.data])

  const versionsPagedQuery = useQuery({
    queryKey: ['product-model-versions-paged', 'listing', 'standard', 'for-bundle-preview'],
    queryFn: () => fetchProductModelVersionsPaged({ version_kind: 'standard', page: 1, page_size: 200 }),
  })
  const versionIdToModelLabel = useMemo(() => {
    const m = new Map<string, string>()
    const items = (versionsPagedQuery.data?.items ?? []) as any[]
    for (const it of items) {
      const vid = String(it?.version_id ?? '').trim()
      const mc = String(it?.model_code ?? '').trim()
      const mn = String(it?.model_name ?? '').trim()
      if (!vid) continue
      const label = mc && mn ? `${mc}:${mn}` : mc || mn || vid.slice(0, 8)
      m.set(vid, label)
    }
    return m
  }, [versionsPagedQuery.data])

  const selectedModel = useMemo(() => models.find((m) => m.id === draft.model_id) ?? null, [models, draft.model_id])
  const selectedVersion = useMemo(
    () => selectableStandardVersions.find((v) => v.id === draft.model_version_id) ?? null,
    [selectableStandardVersions, draft.model_version_id],
  )

  const salesSelectableVersions = useMemo(() => {
    if (salesModelKind === 'sample') return sampleVersions
    return selectableStandardVersions
  }, [salesModelKind, sampleVersions, selectableStandardVersions])

  const salesSelectedVersion = useMemo(() => {
    return salesSelectableVersions.find((v) => v.id === draft.model_version_id) ?? null
  }, [salesSelectableVersions, draft.model_version_id])

  const bundleTokenInSpec = useMemo(() => {
    const t = String(draft.spec_text || '')
    const m = t.match(
      /(?:BUNDLE:|B:)([A-Z0-9]{4,16})|(?:\bB-([A-Z0-9]{4})(?:[A-Za-z])\b)|(?:\bB-([A-Z0-9]{4,16})(?:-[A-Za-z])?\b)/i,
    )
    if (!m) return null
    const code = String(m[1] || m[2] || m[3] || '').toUpperCase()
    return code ? `B:${code}` : null
  }, [draft.spec_text])

  const parseMutation = useMutation({
    mutationFn: async () => {
      const spec_text = String(draft.spec_text ?? '').trim()
      if (!spec_text) throw new Error('请先输入交易规格（spec_text）')
      setLastError(null)
      const res = await parseSpec({ spec_text, sku_code: draft.sku_code || undefined })
      setParsed(res)
      return res
    },
    onError: (e: any) => setLastError(getErrorMessage(e)),
  })

  const previewMutation = useMutation({
    mutationFn: async () => {
      const spec_text = String(draft.spec_text ?? '').trim()
      if (!spec_text) throw new Error('请先输入交易规格（spec_text）')
      setLastError(null)

      // 优先：交易规格中的套装编码（运营口径，避免依赖SKU/ERP同步）
      if (bundleTokenInSpec) {
        const bomRes = await generateBomBySpec({
          spec_text,
          sku_code: draft.sku_code || undefined,
        })
        setBom(bomRes)
        setParsed(((bomRes as any)?.trace ?? {})?.parsed ?? null)
        return bomRes
      }

      const model_version_id = String(draft.model_version_id ?? '').trim()
      if (!model_version_id) throw new Error('请先选择“已发布标准版本”（或在交易规格中提供套装短码 B-XXXXAA / B:CODE:AA）')

      const parsedRes = await parseSpec({ spec_text, sku_code: draft.sku_code || undefined })
      setParsed(parsedRes)
      const bomRes = await generateBom({ spec_text, model_version_id, sku_code: draft.sku_code || undefined, quantity: 1 })
      setBom(bomRes)
      return bomRes
    },
    onSuccess: () => message.success('解析+预演完成'),
    onError: (e: any) => setLastError(getErrorMessage(e)),
  })

  const bundlePreviewMutation = useMutation({
    mutationFn: async () => {
      setLastError(null)
      setBundleComponentsDebug(null)
      setBundleDebugRaw(null)
      const code = String(effectiveBundleCode ?? '').trim()
      if (!code) throw new Error('请先选择套装，或在输入框中包含 B-XXXXAA / B-CODE-AA / B:CODE(:AA)')
      // UI 已选择套装编码：这里允许用户在输入里直接写 B:CODE:A，
      // 我们会优先从用户输入提取 selector（避免 selector 丢失导致“模板无组件”）。
      const inputSelector =
        String(bundleDraft.spec_text || '')
          .match(
            /(?:BUNDLE:|B:|Z:)[A-Z0-9]{4,16}:([A-Za-z]{1,2})|\b(?:B|Z)-[A-Z0-9]{4,16}-([A-Za-z]{1,2})\b|\b(?:B|Z)-[A-Z0-9]{4}([A-Za-z]{2})\b/i,
          )
          ?.[1]?.toUpperCase() ??
        String(bundleDraft.spec_text || '')
          .match(
            /(?:BUNDLE:|B:|Z:)[A-Z0-9]{4,16}:([A-Za-z]{1,2})|\b(?:B|Z)-[A-Z0-9]{4,16}-([A-Za-z]{1,2})\b|\b(?:B|Z)-[A-Z0-9]{4}([A-Za-z]{2})\b/i,
          )
          ?.[2]?.toUpperCase() ??
        String(bundleDraft.spec_text || '')
          .match(
            /(?:BUNDLE:|B:|Z:)[A-Z0-9]{4,16}:([A-Za-z]{1,2})|\b(?:B|Z)-[A-Z0-9]{4,16}-([A-Za-z]{1,2})\b|\b(?:B|Z)-[A-Z0-9]{4}([A-Za-z]{2})\b/i,
          )
          ?.[3]?.toUpperCase() ??
        ''
      const extra = String(bundleDraft.spec_text ?? '')
        .replace(/(?:BUNDLE:|B:|Z:)[A-Z0-9]{4,16}/gi, '')
        // Remove legacy and new short tokens
        .replace(/\b(?:B|Z)-[A-Z0-9]{4,16}(?:-[A-Za-z]{1,2})?\b/gi, '')
        .replace(/\b(?:B|Z)-[A-Z0-9]{4}[A-Za-z]{2}\b/gi, '')
        .trim()
      const sel =
        String(bundleDraft.bundle_selector ?? '').trim().toUpperCase() ||
        inputSelector ||
        String(bundleTokenFromBundleInput.selector ?? '').trim().toUpperCase()
      const token = toBundleTokenDash(code, sel && (sel.length === 1 || sel.length === 2) ? sel : null, selectedBundlePresetPrefix)
      // 不强制使用“；”分隔，直接拼接 (B:CODE[:A]) 即可
      const spec_text = extra ? `${extra}(${token})` : `${token}`
      if (bundleDebugMode) {
        const dbg = await generateBomBySpecDebug({
        spec_text,
        sku_code: draft.sku_code || undefined,
      })
        const merged = (dbg?.merged ?? null) as any
        setBundleDebugRaw(dbg)
        setBundleComponentsDebug(Array.isArray(dbg?.components) ? dbg.components : [])
        setBom(merged as any)
        setParsed(((merged as any)?.trace ?? {})?.parsed ?? null)
        return merged
      }
      const bomRes = await generateBomBySpec({ spec_text, sku_code: draft.sku_code || undefined })
      setBom(bomRes)
      setParsed(((bomRes as any)?.trace ?? {})?.parsed ?? null)
      return bomRes
    },
    onSuccess: () => message.success('套装预演完成'),
    onError: (e: any) => setLastError(getErrorMessage(e)),
    onSettled: () => setSpecGenGeneratingSelector(null),
  })

  const matchedVariants = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.matched_variants
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const matchedBaseLineIds = useMemo(() => {
    const ids = new Set<string>()
    for (const r of matchedVariants as any[]) {
      const id = String((r as any)?.base_line_id ?? '').trim()
      if (id) ids.add(id)
    }
    return Array.from(ids)
  }, [matchedVariants])

  const versionLinesQuery = useQuery({
    queryKey: ['product-listing', 'version-lines', draft.model_version_id],
    queryFn: () => fetchProductModelVersionLines(String(draft.model_version_id)),
    enabled: mode === 'single' && !!draft.model_version_id && !!bom,
  })

  const variantsByBaseLineQuery = useQuery({
    queryKey: ['product-listing', 'line-variants-by-base-line', draft.model_version_id, matchedBaseLineIds.join(',')],
    queryFn: async () => {
      const version_id = String(draft.model_version_id)
      const res = await Promise.all(
        matchedBaseLineIds.map(async (base_line_id) => {
          const items = await listLineVariants({ version_id, base_line_id })
          return { base_line_id, items }
        }),
      )
      return res
    },
    enabled: mode === 'single' && !!draft.model_version_id && !!bom && matchedBaseLineIds.length > 0,
  })

  const baseLineMaterialMap = useMemo(() => {
    const data = versionLinesQuery.data as ProductModelLinesResponse | undefined
    const mats = (data?.materials ?? []) as any[]
    const m = new Map<string, any>()
    for (const r of mats) {
      const id = String(r?.id ?? '').trim()
      if (!id) continue
      m.set(id, r)
    }
    return m
  }, [versionLinesQuery.data])

  const variantMap = useMemo(() => {
    const m = new Map<string, LineVariantDetailRead>()
    const groups = (variantsByBaseLineQuery.data ?? []) as Array<{ base_line_id: string; items: LineVariantDetailRead[] }>
    for (const g of groups) {
      for (const v of g.items ?? []) {
        if (!v?.id) continue
        m.set(String(v.id), v)
      }
    }
    return m
  }, [variantsByBaseLineQuery.data])

  const formatBetween = (pair: any, unit: string) => {
    if (!Array.isArray(pair) || pair.length < 2) return null
    const [a, b] = pair
    const hasA = a != null && a !== ''
    const hasB = b != null && b !== ''
    if (!hasA && !hasB) return null
    if (hasA && hasB) return `${a}~${b}${unit}`
    if (hasA) return `>=${a}${unit}`
    return `<=${b}${unit}`
  }

  const formatTrigger = (condRaw: any): string => {
    const cond = (condRaw ?? {}) as LineVariantCondition
    const any = Array.isArray(cond.spec_contains_any) ? cond.spec_contains_any.filter(Boolean) : []
    const all = Array.isArray(cond.spec_contains_all) ? cond.spec_contains_all.filter(Boolean) : []
    const parts: string[] = []
    if (any.length) parts.push(`TOKEN(any): ${any.join('、')}`)
    if (all.length) parts.push(`TOKEN(all): ${all.join('、')}`)
    const w = formatBetween((cond as any).width_between, 'cm')
    const h = formatBetween((cond as any).height_between, 'cm')
    const a = formatBetween((cond as any).area_between, 'm²')
    const p = formatBetween((cond as any).perimeter_between, 'm')
    if (w) parts.push(`宽: ${w}`)
    if (h) parts.push(`高: ${h}`)
    if (a) parts.push(`面积: ${a}`)
    if (p) parts.push(`周长: ${p}`)
    return parts.join('；') || '-'
  }

  const processLines = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.costing?.process_lines
    if (Array.isArray(arr) && arr.length) return arr
    // 套装合并BOM：后端可能把工序明细放在 components.trace.costing.process_lines
    const comps = traceAny?.components
    if (!Array.isArray(comps) || !comps.length) return []
    const out: any[] = []
    for (let i = 0; i < comps.length; i += 1) {
      const c = comps[i] as any
      const lines = (((c?.trace ?? {}) as any)?.costing ?? {})?.process_lines
      if (!Array.isArray(lines) || !lines.length) continue
      for (const r of lines) {
        out.push({ ...(r as any), component_index: c?.component_index ?? i })
      }
    }
    return out
  }, [bom])

  const inventoryLines = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.inventory?.inventory_lines
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const finalLines = useMemo(() => bom?.final_material_lines ?? [], [bom])

  const costingSummary = useMemo(() => {
    if (!bom) return null
    const traceAny = (bom.trace ?? {}) as any
    const costing = (traceAny?.costing ?? {}) as any

    const material_cost_total =
      toNumberOrNull(costing?.material_cost_total) ??
      computeMaterialCostFromLines((bom.final_material_lines ?? []) as any[])
    const process_cost_total =
      toNumberOrNull(costing?.process_cost_total) ??
      (processLines ?? []).reduce((acc: number, r: any) => acc + (toNumberOrNull(r?.total_cost) ?? 0), 0)

    const overhead_rate = 0.3
    const overhead_cost =
      toNumberOrNull(costing?.overhead_cost) ?? (material_cost_total + process_cost_total) * overhead_rate
    const total_cost =
      toNumberOrNull(costing?.total_cost) ?? material_cost_total + process_cost_total + overhead_cost
    const unit_cost = toNumberOrNull(costing?.unit_cost) ?? total_cost

    return {
      material_cost_total,
      process_cost_total,
      overhead_rate,
      overhead_cost,
      total_cost,
      unit_cost,
      priced_material_lines: costing?.priced_material_lines ?? costing?.priced_lines ?? null,
      missing_price_material_lines: costing?.missing_price_material_lines ?? costing?.missing_price_lines ?? null,
      missing_price_material_codes: Array.isArray(costing?.missing_price_material_codes)
        ? costing.missing_price_material_codes.map((x: any) => String(x)).filter(Boolean)
        : [],
      missing_price_process_lines: costing?.missing_price_process_lines ?? null,
    }
  }, [bom, processLines])

  const storeCalc = useMemo(() => {
    const gmv = Math.max(0, Number(storeDraft.monthly_gmv ?? 0))
    if (!gmv) return null
    const targetNp = clamp01(Number(storeDraft.target_net_profit_pct ?? 0) / 100)
    const fixedPct = clamp01(Number(storeDraft.fixed_cost_pct ?? 0) / 100)
    const adPct = clamp01(Number(storeDraft.ad_fee_pct ?? 0) / 100)
    const platformPct = clamp01(Number(storeDraft.platform_fee_pct ?? 0) / 100)
    const promoPct = clamp01(Number(storeDraft.platform_promo_pct ?? 0) / 100)
    const shipPct = clamp01(Number(storeDraft.shipping_fee_pct ?? 0) / 100)

    const variablePct = platformPct + promoPct + shipPct
    const targetNetProfit = gmv * targetNp
    const fixedCost = gmv * fixedPct
    const adCost = gmv * adPct
    const variableCost = gmv * variablePct

    // 贡献毛利（店铺级）要求：覆盖 固定成本 + 广告费 + 目标净利
    const requiredCm = fixedCost + adCost + targetNetProfit
    const requiredCmPct = requiredCm / gmv

    // 在仅考虑“平台/活动/快递”为变动费的简化下，可承受的“产品成本总额”
    const productCostBudget = gmv - variableCost - requiredCm
    const productCostBudgetPct = productCostBudget / gmv

    const trafficShare = clamp01(Number(storeDraft.traffic_share_pct ?? 0) / 100)
    const profitShare = clamp01(Number(storeDraft.profit_share_pct ?? 0) / 100)
    const brandShare = clamp01(Number(storeDraft.brand_share_pct ?? 0) / 100)
    const shareSum = trafficShare + profitShare + brandShare

    const trafficCm = Number(storeDraft.traffic_cm_pct ?? 0) / 100
    const brandCm = Number(storeDraft.brand_cm_pct ?? 0) / 100
    const profitCmRequired =
      profitShare > 0
        ? (requiredCmPct - trafficShare * trafficCm - brandShare * brandCm) / profitShare
        : NaN

    return {
      monthly_gmv: gmv,
      target_net_profit: targetNetProfit,
      target_net_profit_pct: targetNp * 100,
      fixed_cost: fixedCost,
      fixed_cost_pct: fixedPct * 100,
      ad_cost: adCost,
      ad_cost_pct: adPct * 100,
      variable_cost: variableCost,
      variable_cost_pct: variablePct * 100,
      variable_breakdown_pct: {
        platform_fee_pct: platformPct * 100,
        platform_promo_pct: promoPct * 100,
        shipping_fee_pct: shipPct * 100,
      },
      required_cm: requiredCm,
      required_cm_pct: requiredCmPct * 100,
      product_cost_budget: productCostBudget,
      product_cost_budget_pct: productCostBudgetPct * 100,
      mix: {
        traffic_share_pct: trafficShare * 100,
        profit_share_pct: profitShare * 100,
        brand_share_pct: brandShare * 100,
        share_sum_pct: shareSum * 100,
        traffic_cm_pct: trafficCm * 100,
        brand_cm_pct: brandCm * 100,
        profit_cm_required_pct: profitCmRequired * 100,
      },
    }
  }, [storeDraft])

  const salesCalc = useMemo(() => {
    // 进厂价（单位成本，含制造费等）：从 BOM 预演得到
    const currentFactoryCost = toNumberOrNull(costingSummary?.total_cost)
    if (currentFactoryCost == null) return null

    // All % are based on GMV (tax-included deal price)
    const targetNp = clamp01(Number(salesDraft.target_net_profit_pct ?? 0) / 100)
    const pf = clamp01(Number(salesDraft.platform_fee_pct ?? 0) / 100)
    const ad = clamp01(Number(salesDraft.ad_fee_pct ?? 0) / 100)
    const commission = clamp01(Number(salesDraft.sales_commission_pct ?? 0) / 100)
    const shippingFeeFixed = Math.max(0, Number(salesDraft.shipping_fee_fixed ?? 0))
    const fixedPct = clamp01(Number(salesDraft.fixed_cost_pct ?? 0) / 100)

    const vat = clamp01(Number(salesDraft.vat_rate_pct ?? 0) / 100)
    const surchargeRatio = clamp01(Number(salesDraft.vat_surcharge_ratio_pct ?? 0) / 100)
    const inputVatCreditPct = clamp01(Number(salesDraft.input_vat_credit_pct ?? 0) / 100)
    const serviceVat = clamp01(Number(salesDraft.service_vat_rate_pct ?? 0) / 100)

    // 一般纳税人口径（简化）：税金不再按“销项全额”计入成本，而是按“应纳增值税”计算
    // - 销项增值税：outputVat = netRevenue * vat
    // - 可抵扣进项税：从进厂价（含税）反推进项税额：inputVatBase = factoryCost * vat/(1+vat)
    //   再按“进项可抵扣比例%”估算可抵扣额：inputVatCredit = inputVatBase * inputVatCreditPct
    // - 应纳增值税：payableVat = max(0, outputVat - inputVatCredit)
    // - 附加税：surcharge = payableVat * surchargeRatio
    const a = vat > 0 ? vat / (1 + vat) : 0

    // Returns: value loss approx = return_rate * unsellable_ratio * factoryCost
    const rr = clamp01(Number(salesDraft.return_rate_pct ?? 0) / 100)
    const uns = clamp01(Number(salesDraft.unsellable_ratio_pct ?? 0) / 100)
    const returnValueLossCurrent = currentFactoryCost * rr * uns

    const fixedFees =
      Math.max(0, Number(salesDraft.packaging_fee_fixed ?? 0)) +
      Math.max(0, Number(salesDraft.aftersale_fee_fixed ?? 0))

    // Solve GMV (when pricing_mode=solve):
    // GMV - (pct_costs*GMV) - taxTotal(GMV) - factoryCost - fixedFees - shippingFeeFixed - returnValueLoss = targetNp*GMV
    // 其中 taxTotal(GMV) = (max(0, outputVat(GMV) - inputVatCredits(GMV)) * (1+surchargeRatio))
    // - outputVat(GMV) = a*GMV
    // - inputVatCredits(GMV) = 进厂价进项抵扣（常数项） + 平台扣点/广告费(6%专票)进项抵扣（随 GMV 线性）
    // 说明：快递费为按件固定金额；支付费视为已包含在平台扣点中，不再单列
    const pctCosts = pf + ad + fixedPct + commission
    const baseCosts = currentFactoryCost + fixedFees + shippingFeeFixed + returnValueLossCurrent

    // 分段闭式解（避免迭代）：
    // - 平台扣点/广告费：按 6% 专票估算可抵扣进项税（默认全额可抵扣，业务确认）
    // - payableVat(GMV) = max(0, (a - k)*GMV - inputVatCreditGoods)
    const denom0 = 1 - pctCosts - targetNp
    if (!(denom0 > 0)) {
      return { error: '占比过高：平台/广告/固定成本/目标净利 合计必须 < 100%' }
    }
    const solved0 = baseCosts / denom0

    const taxpayerKind = (salesDraft.taxpayer_kind ?? 'general') as SalesPricingDraft['taxpayer_kind']

    // 小规模：不抵扣进项（应纳增值税=销项增值税），税金段为线性
    const solveSmall = () => {
      if (vat <= 0) return solved0
      const taxSlopeSmall = a * (1 + surchargeRatio)
      const denom = 1 - pctCosts - taxSlopeSmall - targetNp
      return denom > 0 ? baseCosts / denom : null
    }

    // 一般纳税人：分段闭式解（应纳增值税= max(0, 销项 - 进项抵扣)）
    const solveGeneral = () => {
      const serviceA = serviceVat > 0 ? serviceVat / (1 + serviceVat) : 0
      const k = (pf + ad) * serviceA
      const a2 = a - k
      // - 若 (a2*GMV) <= inputVatCreditGoods，则应纳增值税=0 ⇒ taxTotal=0（税金段为 0）
      // - 若 (a2*GMV) > inputVatCreditGoods，则 taxTotal = ((a2*GMV - inputVatCreditGoods) * (1+surchargeRatio))（线性）
      // 进项可抵扣：从“进厂价（含税）”反推
      const inputVatCreditGoodsCurrent = currentFactoryCost * a * inputVatCreditPct
      const thresholdGmv = a2 > 0 ? inputVatCreditGoodsCurrent / a2 : 0

      const taxSlope = a2 * (1 + surchargeRatio)
      const creditAdj = inputVatCreditGoodsCurrent * (1 + surchargeRatio)
      const denomPos = 1 - pctCosts - taxSlope - targetNp
      const solvedPos = denomPos > 0 ? (baseCosts - creditAdj) / denomPos : NaN

      if (vat <= 0) return solved0
      if (solved0 <= thresholdGmv) return solved0
      if (Number.isFinite(solvedPos) && solvedPos > thresholdGmv) return solvedPos
      return null
    }

    const solvedDealGmv = taxpayerKind === 'small' ? solveSmall() : solveGeneral()

    const mode = String(salesDraft.pricing_mode) as SalesPricingDraft['pricing_mode']
    const isDiagnose = mode === 'diagnose'
    const isTargetCost = mode === 'target_cost'
    const dealInput = toNumberOrNull(salesDraft.deal_gmv_input)
    const listInput = toNumberOrNull(salesDraft.list_price_input)

    // 诊断模式输入口径（以券后成交价为主）：
    // - 只填券后：可运行（券前=券后，折扣=0）
    // - 券后+券前都填：自动计算折扣
    // - 只填券前：自动视为“无折扣”，券后=券前
    let dealDiagnose: number | null = dealInput
    let listDiagnose: number | null = listInput
    if (dealDiagnose == null && listDiagnose != null) dealDiagnose = listDiagnose
    if (dealDiagnose != null && listDiagnose == null) listDiagnose = dealDiagnose
    // target_cost 复用相同的输入口径（给定市场价）
    let dealTarget: number | null = dealInput
    let listTarget: number | null = listInput
    if (dealTarget == null && listTarget != null) dealTarget = listTarget
    if (dealTarget != null && listTarget == null) listTarget = dealTarget

    const dealGmv = isTargetCost
      ? Math.max(0, Number(dealTarget ?? 0))
      : isDiagnose
        ? Math.max(0, Number(dealDiagnose ?? 0))
        : solvedDealGmv ?? NaN
    if (!Number.isFinite(dealGmv) || dealGmv <= 0) {
      if (isDiagnose || isTargetCost) return { error: '请填写“券后成交价(含税)”或“优惠前标价(含税)”后再计算。' }
      return { error: '无法反推出合理成交价：税率/抵扣/费率组合导致解无效，请调整参数。' }
    }

    const netRevenue = vat > 0 ? dealGmv / (1 + vat) : dealGmv
    const outputVat = netRevenue * vat

    const platformFee = dealGmv * pf
    const adFee = dealGmv * ad
    const commissionFee = dealGmv * commission
    const shippingFee = shippingFeeFixed
    const fixedCost = dealGmv * fixedPct

    let inputVatCreditPlatform = 0
    let inputVatCreditAd = 0
    let inputVatCreditTotal = 0
    let payableVat = 0
    const inputVatCreditGoodsCurrent = currentFactoryCost * a * inputVatCreditPct

    if (taxpayerKind === 'small') {
      // 小规模：不抵扣进项
      inputVatCreditPlatform = 0
      inputVatCreditAd = 0
      inputVatCreditTotal = 0
      payableVat = outputVat
    } else {
      // 平台扣点/广告费：按 6% 专票估算可抵扣进项税额（默认全额可抵扣，业务确认）
      const serviceA = serviceVat > 0 ? serviceVat / (1 + serviceVat) : 0
      inputVatCreditPlatform = platformFee * serviceA
      inputVatCreditAd = adFee * serviceA
      inputVatCreditTotal = inputVatCreditGoodsCurrent + inputVatCreditPlatform + inputVatCreditAd
      payableVat = Math.max(0, outputVat - inputVatCreditTotal)
    }

    const surchargeTax = payableVat * surchargeRatio
    const taxTotal = payableVat + surchargeTax
    const taxEffectivePct = dealGmv > 0 ? taxTotal / dealGmv : 0

    const targetNetProfit = dealGmv * targetNp

    // 标价：如果有活动折扣（标价 * (1-折扣)=成交价）
    const disc = clamp01(Number(salesDraft.promo_discount_pct ?? 0) / 100)
    const listPrice = isDiagnose || isTargetCost
      ? Math.max(0, Number((isTargetCost ? listTarget : listDiagnose) ?? dealGmv))
      : disc > 0
        ? dealGmv / (1 - disc)
        : dealGmv
    const effectiveDiscPct = listPrice > 0 ? ((listPrice - dealGmv) / listPrice) * 100 : disc * 100

    // 毛利（不含税口径）：(不含税收入 - 产品成本) / 不含税收入
    const grossProfitExTax = netRevenue - currentFactoryCost
    const grossMarginExTaxPct = netRevenue > 0 ? (grossProfitExTax / netRevenue) * 100 : 0

    // 实际净利（在给定成交价下，基于“当前进厂价/单位成本”计算）
    const actualNetProfitCurrent =
      dealGmv -
      (currentFactoryCost +
        fixedFees +
        returnValueLossCurrent +
        platformFee +
        adFee +
        commissionFee +
        shippingFee +
        fixedCost +
        taxTotal)
    const actualNetProfitPctCurrent = dealGmv > 0 ? (actualNetProfitCurrent / dealGmv) * 100 : 0

    // 目标成本模式：反推“允许的最大进厂价/单位成本”（满足目标净利%）
    const solveMaxFactoryCostByDeal = (): number | null => {
      const deal = dealGmv
      const target = deal * targetNp
      const serviceA = serviceVat > 0 ? serviceVat / (1 + serviceVat) : 0
      const platformVatCredit = taxpayerKind === 'small' ? 0 : platformFee * serviceA
      const adVatCredit = taxpayerKind === 'small' ? 0 : adFee * serviceA

      const profitGivenCost = (factoryCost: number) => {
        const returnLoss = factoryCost * rr * uns
        const inputVatCreditGoods = taxpayerKind === 'small' ? 0 : factoryCost * a * inputVatCreditPct
        const inputVatTotal = inputVatCreditGoods + platformVatCredit + adVatCredit
        const payable = taxpayerKind === 'small' ? outputVat : Math.max(0, outputVat - inputVatTotal)
        const tax = payable * (1 + surchargeRatio)
        return deal - (factoryCost + fixedFees + returnLoss + platformFee + adFee + commissionFee + shippingFee + fixedCost + tax)
      }

      // f(cost)=profit(cost)-target，求 f=0 的根（最大可承受成本）
      const f = (c: number) => profitGivenCost(c) - target
      const f0 = f(0)
      if (!(f0 >= 0)) return null // 即使成本=0也达不到目标净利

      let lo = 0
      let hi = Math.max(1, currentFactoryCost * 2, deal * 2)
      // 扩展上界直到 f(hi) <= 0
      for (let i = 0; i < 20 && f(hi) > 0; i++) hi = hi * 1.8
      if (f(hi) > 0) return hi // 极端情况下仍满足目标（返回一个较大值作为上限）

      for (let i = 0; i < 60; i++) {
        const mid = (lo + hi) / 2
        if (f(mid) >= 0) lo = mid
        else hi = mid
      }
      return lo
    }

    const targetFactoryCostMax = isTargetCost ? solveMaxFactoryCostByDeal() : null
    const targetCostGap =
      isTargetCost && targetFactoryCostMax != null ? Math.max(0, currentFactoryCost - targetFactoryCostMax) : null
    const targetCostGapPct =
      isTargetCost && targetFactoryCostMax != null && currentFactoryCost > 0 ? (targetCostGap! / currentFactoryCost) * 100 : null

    return {
      pricing_mode: mode,
      factory_cost: currentFactoryCost,
      deal_gmv: dealGmv,
      list_price: listPrice,
      promo_discount_pct: effectiveDiscPct,

      net_revenue_ex_tax: netRevenue,
      vat_output: outputVat,
      input_vat_credit: inputVatCreditTotal,
      input_vat_credit_goods: inputVatCreditGoodsCurrent,
      input_vat_credit_platform: inputVatCreditPlatform,
      input_vat_credit_ad: inputVatCreditAd,
      payable_vat: payableVat,
      tax_surcharge: surchargeTax,
      tax_total: taxTotal,
      tax_effective_pct: taxEffectivePct * 100,

      platform_fee: platformFee,
      ad_fee: adFee,
      commission_fee: commissionFee,
      shipping_fee: shippingFee,
      fixed_cost: fixedCost,
      fixed_fees: fixedFees,
      return_value_loss: returnValueLossCurrent,

      target_net_profit: targetNetProfit,
      target_net_profit_pct: targetNp * 100,
      gross_margin_ex_tax_pct: grossMarginExTaxPct,
      actual_net_profit: actualNetProfitCurrent,
      actual_net_profit_pct: actualNetProfitPctCurrent,

      // 目标成本模式输出（允许成本与降本缺口）
      target_factory_cost_max: targetFactoryCostMax,
      target_cost_gap: targetCostGap,
      target_cost_gap_pct: targetCostGapPct,

      pct_platform: pf * 100,
      pct_ad: ad * 100,
      pct_commission: commission * 100,
      pct_fixed: fixedPct * 100,
      return_rate_pct: rr * 100,
      unsellable_ratio_pct: uns * 100,
      vat_rate_pct: vat * 100,
      vat_surcharge_ratio_pct: surchargeRatio * 100,
      input_vat_credit_pct: inputVatCreditPct * 100,
      service_vat_rate_pct: serviceVat * 100,
      taxpayer_kind: taxpayerKind,
    }
  }, [costingSummary?.total_cost, salesDraft])

  const modelOptions = useMemo(
    () =>
      models.map((m) => ({
        value: m.id,
        label: (
          <Space size={8}>
            <Text strong>{m.model_code}</Text>
            <Text>{m.model_name}</Text>
            {m.status && m.status !== 'active' ? <Tag color="orange">{m.status}</Tag> : null}
          </Space>
        ),
        raw: m,
      })),
    [models],
  )

  const versionOptions = useMemo(
    () =>
      selectableStandardVersions.map((v) => ({
        value: v.id,
        label: (
          <Space size={8}>
            <Text strong>{v.version_label || v.id.slice(0, 8)}</Text>
            {String(v.version_status) === 'published' ? (
              <Tag color="green">published</Tag>
            ) : (
              <Tag color="orange">{String(v.version_status || 'draft')}</Tag>
            )}
          </Space>
        ),
      })),
    [selectableStandardVersions],
  )

  const sampleVersionOptions = useMemo(
    () =>
      sampleVersions.map((v) => ({
        value: v.id,
        label: (
          <Space size={8}>
            <Text strong>{v.version_label || v.id.slice(0, 8)}</Text>
            <Tag color={String(v.version_status) === 'published' ? 'green' : 'orange'}>{String(v.version_status || 'draft')}</Tag>
          </Space>
        ),
      })),
    [sampleVersions],
  )

  const salesVersionOptions = useMemo(() => {
    if (salesModelKind === 'sample') return sampleVersionOptions
    return versionOptions
  }, [salesModelKind, sampleVersionOptions, versionOptions])

  const singleVersionOptions = useMemo(() => {
    if (singleModelKind === 'sample') return sampleVersionOptions
    return versionOptions
  }, [singleModelKind, sampleVersionOptions, versionOptions])

  return (
    <div style={{ padding: 16 }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card
            title="产品上架（测试台）"
            extra={<Text type="secondary">输入交易规格 → 解析 → 预演最终 BOM（用于运营自测命中与口径）</Text>}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Tabs
                className="product-listing-tabs product-listing-tabs--left"
                activeKey={mode}
                onChange={(k) => {
                  setMode(k as any)
                  setLastError(null)
                  setParsed(null)
                  setBom(null)
                }}
                items={[
                  { key: 'single', label: '模型测试' },
                  { key: 'multi', label: '套装测试' },
                  { key: 'spec_gen', label: '规格生成' },
                  { key: 'sales', label: '利润推演' },
                  { key: 'store', label: '店铺预演' },
                ]}
              />

              <Input
                placeholder="货品编码（可选，仅用于标记/复制）"
                value={draft.sku_code}
                onChange={(e) => setDraft((d) => ({ ...d, sku_code: e.target.value }))}
              />

              {mode === 'store' ? (
                <Card size="small" title="店铺预演（组合模型）">
                  <Space direction="vertical" style={{ width: '100%' }} size={10}>
                    <Alert
                      type="info"
                      showIcon
                      message="口径：店铺独立核算（组合层），用于推导“所需贡献毛利/利润款要求/引流亏损池”。"
                      description="说明：此处不把固定成本/广告费机械摊到每个SKU，而是用“全店贡献毛利”覆盖固定+广告+目标净利；再通过角色结构（引流/利润/形象）反推利润款需要的贡献毛利率。"
                    />

                    <Card size="small" title="店铺参数（按 GMV 占比）" bodyStyle={{ padding: 12 }}>
                      <Space wrap>
                        <InputNumber
                          addonBefore="月GMV(元)"
                          min={0}
                          precision={0}
                          value={storeDraft.monthly_gmv}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, monthly_gmv: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="目标净利%"
                          min={0}
                          max={20}
                          precision={2}
                          value={storeDraft.target_net_profit_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, target_net_profit_pct: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="固定成本%"
                          min={0}
                          max={40}
                          precision={2}
                          value={storeDraft.fixed_cost_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, fixed_cost_pct: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="广告费%"
                          min={0}
                          max={40}
                          precision={2}
                          value={storeDraft.ad_fee_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, ad_fee_pct: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="平台扣款%"
                          min={0}
                          max={30}
                          precision={2}
                          value={storeDraft.platform_fee_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, platform_fee_pct: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="平台活动%"
                          min={0}
                          max={40}
                          precision={2}
                          value={storeDraft.platform_promo_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, platform_promo_pct: Number(v ?? 0) }))}
                        />
                        <InputNumber
                          addonBefore="快递费%"
                          min={0}
                          max={40}
                          precision={2}
                          value={storeDraft.shipping_fee_pct}
                          onChange={(v) => setStoreDraft((d) => ({ ...d, shipping_fee_pct: Number(v ?? 0) }))}
                        />
                      </Space>
                    </Card>

                    <Card size="small" title="结构与角色假设（按 GMV）" bodyStyle={{ padding: 12 }}>
                      <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        <Space wrap>
                          <InputNumber
                            addonBefore="引流占比%"
                            min={0}
                            max={100}
                            precision={2}
                            value={storeDraft.traffic_share_pct}
                            onChange={(v) => setStoreDraft((d) => ({ ...d, traffic_share_pct: Number(v ?? 0) }))}
                          />
                          <InputNumber
                            addonBefore="利润占比%"
                            min={0}
                            max={100}
                            precision={2}
                            value={storeDraft.profit_share_pct}
                            onChange={(v) => setStoreDraft((d) => ({ ...d, profit_share_pct: Number(v ?? 0) }))}
                          />
                          <InputNumber
                            addonBefore="形象占比%"
                            min={0}
                            max={100}
                            precision={2}
                            value={storeDraft.brand_share_pct}
                            onChange={(v) => setStoreDraft((d) => ({ ...d, brand_share_pct: Number(v ?? 0) }))}
                          />
                        </Space>
                        <Space wrap>
                          <InputNumber
                            addonBefore="引流目标贡献毛利%"
                            min={-30}
                            max={50}
                            precision={2}
                            value={storeDraft.traffic_cm_pct}
                            onChange={(v) => setStoreDraft((d) => ({ ...d, traffic_cm_pct: Number(v ?? 0) }))}
                          />
                          <InputNumber
                            addonBefore="形象目标贡献毛利%"
                            min={0}
                            max={80}
                            precision={2}
                            value={storeDraft.brand_cm_pct}
                            onChange={(v) => setStoreDraft((d) => ({ ...d, brand_cm_pct: Number(v ?? 0) }))}
                          />
                        </Space>
                        <Text type="secondary">
                          说明：这里的“贡献毛利%”指单品在扣除【平台扣款/活动/快递/产品成本（及退货税费等）】后的剩余比例，用于覆盖【广告费+固定成本+净利】。
                        </Text>
                      </Space>
                    </Card>

                    <Card size="small" title="结果（只读）">
                      {!storeCalc ? (
                        <Text type="secondary">请先填写月GMV</Text>
                      ) : (
                        <Descriptions bordered size="small" column={2}>
                          <Descriptions.Item label="月GMV">{formatMoney2((storeCalc as any).monthly_gmv)}</Descriptions.Item>
                          <Descriptions.Item label="目标净利润">{formatMoney2((storeCalc as any).target_net_profit)}</Descriptions.Item>

                          <Descriptions.Item label="固定成本">{formatMoney2((storeCalc as any).fixed_cost)}</Descriptions.Item>
                          <Descriptions.Item label="广告费">{formatMoney2((storeCalc as any).ad_cost)}</Descriptions.Item>

                          <Descriptions.Item label="平台+活动+快递(合计)">
                            {formatMoney2((storeCalc as any).variable_cost)}（{String(Number((storeCalc as any).variable_cost_pct ?? 0).toFixed(2))}%）
                          </Descriptions.Item>
                          <Descriptions.Item label="变动费拆分(%)">
                            平台{String(Number((storeCalc as any).variable_breakdown_pct?.platform_fee_pct ?? 0).toFixed(2))}% / 活动
                            {String(Number((storeCalc as any).variable_breakdown_pct?.platform_promo_pct ?? 0).toFixed(2))}% / 快递
                            {String(Number((storeCalc as any).variable_breakdown_pct?.shipping_fee_pct ?? 0).toFixed(2))}%
                          </Descriptions.Item>

                          <Descriptions.Item label="全店所需贡献毛利(元)">
                            <b>{formatMoney2((storeCalc as any).required_cm)}</b>
                          </Descriptions.Item>
                          <Descriptions.Item label="全店所需贡献毛利率(%)">
                            <b>{String(Number((storeCalc as any).required_cm_pct ?? 0).toFixed(2))}%</b>
                          </Descriptions.Item>

                          <Descriptions.Item label="产品成本预算(元)">
                            <b>{formatMoney2((storeCalc as any).product_cost_budget)}</b>
                          </Descriptions.Item>
                          <Descriptions.Item label="产品成本预算占比(%)">
                            <b>{String(Number((storeCalc as any).product_cost_budget_pct ?? 0).toFixed(2))}%</b>
                          </Descriptions.Item>

                          <Descriptions.Item label="结构占比合计(%)">
                            {String(Number((storeCalc as any).mix?.share_sum_pct ?? 0).toFixed(2))}%
                          </Descriptions.Item>
                          <Descriptions.Item label="利润款需达到的贡献毛利率(%)">
                            <b>{String(Number((storeCalc as any).mix?.profit_cm_required_pct ?? 0).toFixed(2))}%</b>
                          </Descriptions.Item>
                        </Descriptions>
                      )}
                      <Divider style={{ margin: '10px 0' }} />
                      <Text type="secondary">
                        操作建议：先用这里把“利润款需要多高贡献毛利率”算清楚；具体到单个SKU时，再去“利润推演 → 目标成本（给定市场售价）”输入市场价，算可承受进厂价与降本缺口。
                      </Text>
                    </Card>
                  </Space>
                </Card>
              ) : mode === 'single' ? (
                <>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={6}>
                      <Select
                        value={singleModelKind}
                        style={{ width: '100%' }}
                        options={[
                          { value: 'sample', label: '打样模型' },
                          { value: 'standard', label: '标准模型' },
                        ]}
                        onChange={(v) => {
                          setSingleModelKind(v as any)
                          setDraft((d) => ({ ...d, model_version_id: null }))
                          setBom(null)
                          setParsed(null)
                        }}
                      />
                    </Col>
                    <Col xs={24} lg={9}>
                      <Select
                        showSearch
                        allowClear
                        placeholder="模型名称"
                        options={modelOptions as any}
                        value={draft.model_id ?? undefined}
                        loading={modelsQuery.isLoading}
                        style={{ width: '100%' }}
                        filterOption={(input, option: any) => {
                          const raw = option?.raw as ProductModel | undefined
                          const q = String(input ?? '').trim().toLowerCase()
                          if (!raw) return false
                          return String(raw.model_code ?? '').toLowerCase().includes(q) || String(raw.model_name ?? '').toLowerCase().includes(q)
                        }}
                        onChange={(v) => {
                          setDraft((d) => ({ ...d, model_id: (v as string) ?? null, model_version_id: null }))
                          setBom(null)
                          setParsed(null)
                        }}
                      />
                    </Col>
                    <Col xs={24} lg={9}>
                      <Space.Compact style={{ width: '100%' }}>
                        <Select
                          showSearch
                          allowClear
                          placeholder="版本名称"
                          options={singleVersionOptions as any}
                          value={draft.model_version_id ?? undefined}
                          loading={versionsQuery.isLoading}
                          disabled={!draft.model_id}
                          style={{ width: '100%' }}
                          onChange={(v) => {
                            setDraft((d) => ({ ...d, model_version_id: (v as string) ?? null }))
                            setBom(null)
                            setParsed(null)
                          }}
                        />
                        {singleModelKind === 'standard' ? (
                          <Button
                            onClick={() => {
                              setShowAllStandardVersions((x) => !x)
                              setDraft((d) => ({ ...d, model_version_id: null }))
                              setBom(null)
                              setParsed(null)
                            }}
                          >
                            {showAllStandardVersions ? '仅发布' : '全部'}
                          </Button>
                        ) : null}
                      </Space.Compact>
                    </Col>
                  </Row>
                </>
              ) : mode === 'multi' ? (
                <>
                  <Input
                    placeholder="套装短码（可直接输入）：例如 B-3U3PAA / Z-3U3PAA / B-CODE-AA / B:CODE:AA"
                    value={bundleDraft.bundle_input}
                    onChange={(e) => setBundleDraft((d) => ({ ...d, bundle_input: e.target.value }))}
                  />
                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={12}>
                      <Select
                        showSearch
                        allowClear
                        placeholder="套装选择"
                        options={bundleTemplateOptions as any}
                        value={bundleDraft.bundle_code ?? undefined}
                        loading={bundleTemplatesQuery.isLoading}
                        onChange={(v) =>
                          setBundleDraft((d) => ({ ...d, bundle_code: (v as string) ?? null, bundle_selector: null, spec_text: '' }))
                        }
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col xs={24} lg={12}>
                      <Select
                        allowClear
                        placeholder="属性规格"
                        options={bundlePhraseOptions as any}
                        value={bundleDraft.bundle_selector ?? undefined}
                        loading={bundleTemplateDetailQuery.isLoading}
                        onChange={(v) => setBundleDraft((d) => ({ ...d, bundle_selector: (v as string) ?? null }))}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  </Row>
                  {!bundleDraft.bundle_code && bundleTokenFromBundleInput.code ? (
                    <Alert
                      type="info"
                      showIcon
                      message={`已从输入框识别套装编码：${toBundleTokenDash(bundleTokenFromBundleInput.code, bundleTokenFromBundleInput.selector)}`}
                      description="已自动联动套装与短语 selector；可直接查看短语/组件行预览并点击“套装：预演 BOM”。"
                    />
                  ) : null}
                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="属性规格">
                        <Space direction="vertical" style={{ width: '100%' }} size={8}>
                          {bundleDraft.bundle_selector ? (
                            <Text>
                              <Tag color={selectedBundlePresetPrefix === 'Z' ? 'volcano' : 'blue'} style={{ marginInlineEnd: 6 }}>
                                {bundleDraft.bundle_code
                                  ? toBundleTokenDash(bundleDraft.bundle_code, bundleDraft.bundle_selector, selectedBundlePresetPrefix)
                                  : String(bundleDraft.bundle_selector ?? '').trim().toUpperCase()}
                              </Tag>
                              <Text>{bundleSelectedPhrase || '-'}</Text>
                            </Text>
                          ) : null}
                          {bundleDraft.bundle_code && bundleDraft.bundle_selector ? (
                            selectedBundlePresetPrefix === 'Z' ? (
                              <Alert
                                type="info"
                                showIcon
                                message={<span style={{ fontSize: 12 }}>Z 指定型：无需 TOKEN 和尺寸编码，直接解析。</span>}
                                description={
                                  <span style={{ fontSize: 12 }}>
                                    说明：Z 模式不依赖交易规格里的触发词/尺寸段来命中组件；系统会自动按 Z 前缀选择对应属性规格并生成最终 BOM。
                                  </span>
                                }
                              />
                            ) : (
                              (() => {
                                const sel = String(bundleDraft.bundle_selector ?? '').trim().toUpperCase()
                                const meta: any = (bundleTemplateDetailQuery.data as any)?.metadata ?? {}
                                const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
                                const hitInfo = (() => {
                                  const directIdx = pp.findIndex((x: any) => String(x?.selector ?? '').trim().toUpperCase() === sel)
                                  if (directIdx >= 0) return { hit: pp[directIdx], presetIndex: directIdx }
                                  if (sel.length !== 2) return { hit: null, presetIndex: -1 }
                                  const a = sel.charCodeAt(0) - 'A'.charCodeAt(0)
                                  const b = sel.charCodeAt(1) - 'A'.charCodeAt(0)
                                  const idx = a * 26 + b
                                  return { hit: idx >= 0 ? pp[idx] : null, presetIndex: idx }
                                })()
                                const hit = hitInfo.hit
                                const presetIndex = hitInfo.presetIndex
                                const presetSelector2 = String((hit as any)?.selector ?? '').trim().toUpperCase() || (presetIndex >= 0 ? toSelector2(presetIndex) : sel)
                                const componentRowsRaw = Array.isArray((hit as any)?.components) ? ((hit as any).components as any[]) : []
                                const componentRows = componentRowsRaw.map((c: any) => ({
                                  ...c,
                                  width_cm: Number(c?.width_mm ?? 0) / 10,
                                  height_cm: Number(c?.height_mm ?? 0) / 10,
                                  quantity: Number(c?.quantity ?? 0),
                                }))
                                const built = presetIndex >= 0
                                  ? buildAttributeFormulaAndGroups({
                                      presetIndex,
                                      presetSelector: presetSelector2,
                                      componentOrder: bundleComponentOrderByPreset?.[String(presetIndex)],
                                      componentRows,
                                      presetSelectedByIdx: bundlePhraseVariantPresets as any,
                                      fallbackTokenOverrides: bundleFallbackTokenOverrides,
                                      variantTokenOptionsByVersionBaseLine: variantTokenOptionsByVersionBaseLineForBundle,
                                      baseLineInfoByVersionBaseLine: baseLineInfoByVersionBaseLineForBundle,
                                      variantTokenAliasOverrides: bundleVariantTokenAliasOverrides,
                                    })
                                  : { formula: '', components: [] as any[] }
                                const builtComponents = built.components as AttributeComponentGroups[]
                                const autoMeta = presetIndex >= 0
                                  ? buildAutoRuleMetaFromSelections({
                                      presetIndex,
                                      presetSelector: presetSelector2,
                                      components: builtComponents,
                                      componentRows,
                                      attributeGroupSelections: bundleAttributeGroupSelections,
                                      componentOrder: bundleComponentOrderByPreset?.[String(presetIndex)],
                                      groupOrderByPresetComponent: bundleGroupOrderByPresetComponent,
                                      variantTokenAliasOverrides: bundleVariantTokenAliasOverrides,
                                    })
                                  : { text: '', items: [] as any[] }
                                return (
                                  <div
                                    style={{
                                      background: 'rgba(255, 255, 255, 0.035)',
                                      border: '1px solid var(--color-theme-border-quaternary)',
                                      borderRadius: 8,
                                      padding: 10,
                                    }}
                                  >
                                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                      <style>{`
                                        .bt-model-pill {
                                          display: inline-flex;
                                          align-items: center;
                                          padding: 1px 6px;
                                          border-radius: 999px;
                                          font-weight: 700;
                                          background: rgba(22,119,255,0.12);
                                          border: 1px solid rgba(22,119,255,0.35);
                                          color: #0958d9;
                                          line-height: 16px;
                                          font-size: 12px;
                                        }
                                      `}</style>

                                      {builtComponents.length ? (
                                        <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                          <Space wrap size={8}>
                                            <Text type="secondary">自动生成：</Text>
                                            {autoMeta.text ? (
                                              <Text code>
                                                <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>
                                                  {autoMeta.items.map((it: any, i2: number) => (
                                                    <span key={`ar-${presetIndex}-${i2}`}>
                                                      {i2 > 0 ? <span>{' + '}</span> : null}
                                                      {it.tokens.map((tk: any, j: number) => (
                                                        <span
                                                          key={`ar-tk-${presetIndex}-${i2}-${j}`}
                                                          style={{ color: '#cf1322', fontWeight: 700 }}
                                                        >
                                                          {tk.text}
                                                        </span>
                                                      ))}
                                                      <span style={it.dimsIsMissing ? { color: '#cf1322', fontWeight: 700 } : undefined}>
                                                        {it.dims}
                                                      </span>
                                                    </span>
                                                  ))}
                                                </span>
                                              </Text>
                                            ) : (
                                              <Text code>-</Text>
                                            )}
                                            <Button
                                              size="small"
                                              type="text"
                                              icon={<CopyOutlined />}
                                              disabled={!autoMeta.text}
                                              onClick={async () => {
                                                if (!autoMeta.text) return
                                                const ok = await copyTextToClipboard(autoMeta.text)
                                                if (ok) message.success('已复制自动生成内容')
                                                else message.error('复制失败：请手动复制')
                                              }}
                                            />
                                          </Space>

                                          {(() => {
                                            const orderKey = String(presetIndex)
                                            const rawOrder = bundleComponentOrderByPreset?.[orderKey]
                                            const defaultOrder = builtComponents.map((c) => c.componentIndex)
                                            const order = Array.isArray(rawOrder) && rawOrder.length ? rawOrder : defaultOrder
                                            const seen = new Set<number>()
                                            const ordered = order
                                              .map((i) => Number(i))
                                              .filter((i) => Number.isFinite(i))
                                              .filter((i) => (seen.has(i) ? false : (seen.add(i), true)))
                                              .map((i) => builtComponents.find((c) => c.componentIndex === i))
                                              .filter(Boolean) as AttributeComponentGroups[]
                                            const rest = builtComponents.filter((c) => !seen.has(c.componentIndex))
                                            return [...ordered, ...rest]
                                          })().map((c) => {
                                            const versionId = String((componentRowsRaw?.[c.componentIndex] as any)?.model_version_id ?? '').trim()
                                            const label = versionId ? String(versionIdToModelLabel.get(versionId) ?? '') : ''
                                            const modelCode = label.includes(':') ? label.split(':')[0] : label
                                            return (
                                              <Space key={`attr-comp-${presetIndex}-${c.componentIndex}`} wrap size={8}>
                                                <Space size={4} align="center">
                                                  <span className="bt-model-pill">{modelCode || '组件'}</span>
                                                </Space>
                                                {(() => {
                                                  const groupOrderKey = `${presetIndex}:${c.componentIndex}`
                                                  const order = bundleGroupOrderByPresetComponent?.[groupOrderKey] ?? []
                                                  if (!Array.isArray(order) || !order.length) return c.groups
                                                  const idxMap = new Map<string, number>()
                                                  for (let i = 0; i < order.length; i++) idxMap.set(String(order[i]), i)
                                                  return c.groups.slice().sort((a, b) => (idxMap.get(a.key) ?? 1e9) - (idxMap.get(b.key) ?? 1e9))
                                                })().map((g) => {
                                                  const selKey = `${presetIndex}:${c.componentIndex}:${g.key}`
                                                  const options = (g.options ?? []).map((x) => normalizeSingleToken(x))
                                                  const uniq: string[] = []
                                                  const seen = new Set<string>()
                                                  for (const t of options) {
                                                    const k = t || '__EMPTY__'
                                                    if (seen.has(k)) continue
                                                    seen.add(k)
                                                    uniq.push(t)
                                                  }
                                                  const value = getEffectiveSelection({
                                                    presetIndex,
                                                    componentIndex: c.componentIndex,
                                                    group: g,
                                                    attributeGroupSelections: bundleAttributeGroupSelections,
                                                  })
                                                  const displayVariantToken = (selector2: string, rawToken: string): string => {
                                                    const sel = String(selector2 ?? '').trim().toUpperCase()
                                                    const t = normalizeSingleToken(rawToken)
                                                    const alias = sel ? String((bundleVariantTokenAliasOverrides?.[sel] ?? {})?.[t] ?? '').trim() : ''
                                                    return alias || t
                                                  }
                                                  return (
                                                    <Space key={`attr-sel-${selKey}`} size={2} align="center">
                                                      <Select
                                                        size="small"
                                                        style={{ width: 100 }}
                                                        value={value}
                                                        onChange={(v) =>
                                                          setBundleAttributeGroupSelections((prev) => ({
                                                            ...(prev ?? {}),
                                                            [selKey]: String(v ?? ''),
                                                          }))
                                                        }
                                                        options={uniq
                                                          .filter((x) => (g.isZeroCostGroup ? true : !!String(x).trim()))
                                                          .map((t) => ({
                                                            value: t,
                                                            label: t ? displayVariantToken(presetSelector2, t) : '（无）',
                                                          }))}
                                                      />
                                                    </Space>
                                                  )
                                                })}
                                              </Space>
                                            )
                                          })}
                                        </Space>
                                      ) : (
                                        <Text type="secondary">提示：该属性规格暂无可用的互斥组下拉（可能尚未配置筛选/强制或兜底别名）。</Text>
                                      )}
                                    </Space>
                                  </div>
                                )
                              })()
                            )
                          ) : null}
                          <Text type="secondary">
                            预演时会按选择器拼接：{' '}
                            <Text code>
                              {bundleDraft.bundle_code
                                ? bundleDraft.bundle_selector
                                  ? toBundleTokenDash(bundleDraft.bundle_code, bundleDraft.bundle_selector, selectedBundlePresetPrefix)
                                  : toBundleTokenDash(bundleDraft.bundle_code, null, selectedBundlePresetPrefix)
                                : selectedBundlePresetPrefix === 'Z'
                                  ? 'Z-XXXXAA'
                                  : 'B-XXXXAA'}
                            </Text>
                          </Text>
                        </Space>
                      </Card>
                      {/* 已移除：短语生成器（运营可改词+验证） */}
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="组件行预览（来自该短语）">
                        {bundleDraft.bundle_selector ? (
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(_, i) => `pc-${i}`}
                            dataSource={bundlePresetComponents as any}
                            locale={{ emptyText: '该短语未配置组件行' }}
                            columns={[
                              {
                                title: '模型',
                                width: 220,
                                render: (_: any, r: any) => {
                                  const vid = String(r?.model_version_id ?? '').trim()
                                  return vid ? versionIdToModelLabel.get(vid) || vid.slice(0, 8) : '-'
                                },
                              },
                              {
                                title: '宽(cm)',
                                width: 80,
                                render: (_: any, r: any) => {
                                  const v = toNumberOrNull(r?.width_mm)
                                  return v != null ? String(v / 10) : '-'
                                },
                              },
                              {
                                title: '高(cm)',
                                width: 80,
                                render: (_: any, r: any) => {
                                  const v = toNumberOrNull(r?.height_mm)
                                  return v != null ? String(v / 10) : '-'
                                },
                              },
                              { title: '数量', width: 70, render: (_: any, r: any) => String(r?.quantity ?? '-') },
                            ]}
                          />
                        ) : (
                          <Empty description="先选择 A/B/C…" />
                        )}
                      </Card>
                    </Col>
                  </Row>
                  <Input.TextArea
                    rows={4}
                    placeholder="交易规格（可选）：可直接粘贴对客规格；不需要写“；”。点击预演会自动拼接 (B:CODE[:A])"
                    value={bundleDraft.spec_text}
                    onChange={(e) => setBundleDraft((d) => ({ ...d, spec_text: e.target.value }))}
                  />
                </>
              ) : mode === 'sales' ? (
                <>
                  <Alert
                    type="info"
                    showIcon
                    message="售价测算（测试台）：先选标准模型/版本并预演 BOM 得到进厂价，再填写渠道与费用参数反推售价。"
                  />

                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={6}>
                      <Select
                        value={salesModelKind}
                        style={{ width: '100%' }}
                        options={[
                          { value: 'sample', label: '打样模型' },
                          { value: 'standard', label: '标准模型' },
                        ]}
                        onChange={(v) => {
                          setSalesModelKind(v as any)
                          setDraft((d) => ({ ...d, model_version_id: null }))
                          setBom(null)
                          setParsed(null)
                        }}
                      />
                    </Col>
                    <Col xs={24} lg={9}>
                      <Select
                        showSearch
                        allowClear
                        placeholder="模型名称"
                        options={modelOptions as any}
                        value={draft.model_id ?? undefined}
                        loading={modelsQuery.isLoading}
                        style={{ width: '100%' }}
                        filterOption={(input, option: any) => {
                          const raw = option?.raw as ProductModel | undefined
                          const q = String(input ?? '').trim().toLowerCase()
                          if (!raw) return false
                          return String(raw.model_code ?? '').toLowerCase().includes(q) || String(raw.model_name ?? '').toLowerCase().includes(q)
                        }}
                        onChange={(v) => {
                          setDraft((d) => ({ ...d, model_id: (v as string) ?? null, model_version_id: null }))
                          setBom(null)
                          setParsed(null)
                        }}
                      />
                    </Col>
                    <Col xs={24} lg={9}>
                      <Space.Compact style={{ width: '100%' }}>
                        <Select
                          showSearch
                          allowClear
                          placeholder="版本名称"
                          options={salesVersionOptions as any}
                          value={draft.model_version_id ?? undefined}
                          loading={versionsQuery.isLoading}
                          disabled={!draft.model_id}
                          style={{ width: '100%' }}
                          onChange={(v) => {
                            setDraft((d) => ({ ...d, model_version_id: (v as string) ?? null }))
                            setBom(null)
                            setParsed(null)
                          }}
                        />
                        {salesModelKind === 'standard' ? (
                          <Button
                            onClick={() => {
                              setShowAllStandardVersions((x) => !x)
                              setDraft((d) => ({ ...d, model_version_id: null }))
                              setBom(null)
                              setParsed(null)
                            }}
                          >
                            {showAllStandardVersions ? '仅发布' : '全部'}
                          </Button>
                        ) : null}
                      </Space.Compact>
                    </Col>
                  </Row>

                  <Input.TextArea
                    rows={4}
                    placeholder="粘贴运营的交易规格（spec_text）"
                    value={draft.spec_text}
                    onChange={(e) => setDraft((d) => ({ ...d, spec_text: e.target.value }))}
                  />

                  <Card size="small" title="成本构成分析与利润模型推演（输入）">
                    <Space direction="vertical" style={{ width: '100%' }} size={10}>
                      <Card size="small" title="模式" bodyStyle={{ padding: 12 }}>
                        <Space direction="vertical" style={{ width: '100%' }} size={10}>
                          <Radio.Group
                            value={salesDraft.pricing_mode}
                            onChange={(e) => setSalesDraft((d) => ({ ...d, pricing_mode: e.target.value }))}
                            options={[
                              { label: '反推售价（满足目标净利%）', value: 'solve' },
                              { label: '利润诊断（按券后价/标价）', value: 'diagnose' },
                              { label: '目标成本（给定市场售价）', value: 'target_cost' },
                            ]}
                            optionType="button"
                            buttonStyle="solid"
                          />
                          {salesDraft.pricing_mode === 'diagnose' || salesDraft.pricing_mode === 'target_cost' ? (
                            <Space wrap>
                              <InputNumber
                                addonBefore="券后成交价(含税)"
                                min={0}
                                precision={2}
                                value={salesDraft.deal_gmv_input}
                                placeholder={salesDraft.pricing_mode === 'target_cost' ? '必填（市场到手价）' : '必填（或仅填券前）'}
                                onChange={(v) => setSalesDraft((d) => ({ ...d, deal_gmv_input: v == null ? null : Number(v) }))}
                              />
                              <InputNumber
                                addonBefore="优惠前标价(含税)"
                                min={0}
                                precision={2}
                                value={salesDraft.list_price_input}
                                placeholder="可选（用于自动算折扣）"
                                onChange={(v) => setSalesDraft((d) => ({ ...d, list_price_input: v == null ? null : Number(v) }))}
                              />
                            </Space>
                          ) : null}
                        </Space>
                      </Card>

                      <Space wrap>
                        <Select
                          style={{ width: 140 }}
                          value={salesDraft.channel}
                          options={(Object.keys(CHANNEL_PRESETS) as SalesPricingDraft['channel'][]).map((k) => ({
                            value: k,
                            label: CHANNEL_PRESETS[k].label,
                          }))}
                          onChange={(v) => {
                            const ch = v as SalesPricingDraft['channel']
                            const preset = CHANNEL_PRESETS[ch]
                            setSalesDraft((d) => ({
                              ...d,
                              channel: ch,
                              platform_fee_pct: preset.platform_fee_pct,
                              ad_fee_pct: preset.ad_fee_pct,
                            }))
                          }}
                        />
                        <Select style={{ width: 120 }} options={CITY_OPTIONS as any} value={salesDraft.city} onChange={(v) => setSalesDraft((d) => ({ ...d, city: String(v) }))} />
                        <Select style={{ width: 120 }} options={COURIER_OPTIONS as any} value={salesDraft.courier} onChange={(v) => setSalesDraft((d) => ({ ...d, courier: String(v) }))} />
                        <Select style={{ width: 120 }} options={CAMPAIGN_OPTIONS as any} value={salesDraft.campaign} onChange={(v) => setSalesDraft((d) => ({ ...d, campaign: String(v) }))} />
                      </Space>

                      {/* 单独一行：目标净利% + 预设选择/新建/保存 */}
                      <Space wrap>
                        <Select
                          style={{ width: 140 }}
                          value={salesDraft.product_tier}
                          options={(Object.keys(TIER_PRESETS) as SalesPricingDraft['product_tier'][]).map((k) => ({
                            value: k,
                            label: TIER_PRESETS[k].label,
                          }))}
                          onChange={(v) => {
                            const tier = v as SalesPricingDraft['product_tier']
                            const preset = TIER_PRESETS[tier]
                            setSalesDraft((d) => ({
                              ...d,
                              product_tier: tier,
                              target_net_profit_pct: preset.target_net_profit_pct,
                              fixed_cost_pct: preset.fixed_cost_pct,
                              return_rate_pct: preset.return_rate_pct,
                              unsellable_ratio_pct: preset.unsellable_ratio_pct,
                            }))
                          }}
                        />
                        <InputNumber
                          addonBefore="目标净利%"
                          min={0}
                          max={30}
                          precision={2}
                          value={salesDraft.target_net_profit_pct}
                          disabled={salesDraft.pricing_mode === 'diagnose'}
                          onChange={(v) => setSalesDraft((d) => ({ ...d, target_net_profit_pct: Number(v ?? 0) }))}
                        />
                        <Select
                          style={{ width: 220 }}
                          allowClear
                          placeholder="选择预设（利润推演输入）"
                          value={salesPresetId ?? undefined}
                          options={salesPresets.map((p) => ({
                            value: p.id,
                            label: `${p.name}${p.updated_at ? `（${p.updated_at.slice(0, 10)}）` : ''}`,
                          }))}
                          onChange={(v) => {
                            const id = (v as string) ?? null
                            setSalesPresetId(id)
                            if (!id) return
                            const hit = salesPresets.find((x) => x.id === id)
                            if (!hit) return
                            setSalesDraft(hit.data)
                            message.success(`已应用预设：${hit.name}`)
                          }}
                        />
                        <Button
                          onClick={() => {
                            setSalesPresetCreateName('')
                            setSalesPresetCreateOpen(true)
                          }}
                        >
                          新建
                        </Button>
                        <Button
                          type="primary"
                          onClick={() => {
                            const id = String(salesPresetId ?? '').trim()
                            if (!id) {
                              message.warning('请先选择一个预设，或点“新建”')
                              return
                            }
                            const idx = salesPresets.findIndex((x) => x.id === id)
                            if (idx < 0) {
                              message.warning('预设不存在（可能被清理），请重新选择或新建')
                              return
                            }
                            const now = new Date().toISOString()
                            const next = [...salesPresets]
                            next[idx] = { ...next[idx], updated_at: now, data: salesDraft }
                            setSalesPresets(next)
                            saveSalesPricingPresets(next)
                            message.success('已保存到当前预设')
                          }}
                        >
                          保存
                        </Button>
                      </Space>

                      <Divider style={{ margin: '4px 0' }} />
                      <Space wrap align="center">
                        <Text strong style={{ minWidth: 72 }}>平台相关</Text>
                        <InputNumber addonBefore="广告费%" min={0} max={50} precision={2} value={salesDraft.ad_fee_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, ad_fee_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="平台扣点%" min={0} max={50} precision={2} value={salesDraft.platform_fee_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, platform_fee_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="活动折扣%" min={0} max={90} precision={2} value={salesDraft.promo_discount_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, promo_discount_pct: Number(v ?? 0) }))} />
                      </Space>

                      <Divider style={{ margin: '4px 0' }} />
                      <Space wrap align="center">
                        <Text strong style={{ minWidth: 72 }}>发货成本</Text>
                        <InputNumber addonBefore="包装(元)" min={0} precision={2} value={salesDraft.packaging_fee_fixed} onChange={(v) => setSalesDraft((d) => ({ ...d, packaging_fee_fixed: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="快递费(元/件)" min={0} precision={2} value={salesDraft.shipping_fee_fixed} onChange={(v) => setSalesDraft((d) => ({ ...d, shipping_fee_fixed: Number(v ?? 0) }))} />
                      </Space>

                      <Divider style={{ margin: '4px 0' }} />
                      <Space wrap align="center">
                        <Text strong style={{ minWidth: 72 }}>售后预估</Text>
                        <InputNumber addonBefore="退货率%" min={0} max={60} precision={2} value={salesDraft.return_rate_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, return_rate_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="不可售占比%" min={0} max={100} precision={2} value={salesDraft.unsellable_ratio_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, unsellable_ratio_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="售后(元)" min={0} precision={2} value={salesDraft.aftersale_fee_fixed} onChange={(v) => setSalesDraft((d) => ({ ...d, aftersale_fee_fixed: Number(v ?? 0) }))} />
                      </Space>

                      <Divider style={{ margin: '4px 0' }} />
                      <Space wrap align="center">
                        <Text strong style={{ minWidth: 72 }}>管理费用</Text>
                        <InputNumber addonBefore="固定成本%" min={0} max={40} precision={2} value={salesDraft.fixed_cost_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, fixed_cost_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="销售提成%" min={0} max={20} precision={2} value={salesDraft.sales_commission_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, sales_commission_pct: Number(v ?? 0) }))} />
                      </Space>

                      <Divider style={{ margin: '4px 0' }} />
                      <Space wrap align="center">
                        <Text strong style={{ minWidth: 72 }}>交纳税费</Text>
                        <Select
                          style={{ width: 140 }}
                          value={salesDraft.taxpayer_kind}
                          options={[
                            { value: 'general', label: '一般纳税人' },
                            { value: 'small', label: '小规模' },
                          ]}
                          onChange={(v) =>
                            setSalesDraft((d) => ({
                              ...d,
                              taxpayer_kind: v as any,
                              // 默认税率联动：小规模=3%，一般纳税人=13%
                              vat_rate_pct: v === 'small' ? 3 : 13,
                            }))
                          }
                        />
                        <InputNumber addonBefore="增值税%" min={0} max={20} precision={2} value={salesDraft.vat_rate_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, vat_rate_pct: Number(v ?? 0) }))} />
                        <InputNumber addonBefore="附加税/增值税%" min={0} max={50} precision={2} value={salesDraft.vat_surcharge_ratio_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, vat_surcharge_ratio_pct: Number(v ?? 0) }))} />
                        {salesDraft.taxpayer_kind === 'general' ? (
                          <>
                            <InputNumber
                              addonBefore="进项可抵扣%"
                              min={0}
                              max={100}
                              precision={2}
                              value={salesDraft.input_vat_credit_pct}
                              onChange={(v) => setSalesDraft((d) => ({ ...d, input_vat_credit_pct: Number(v ?? 0) }))}
                            />
                            <InputNumber addonBefore="服务进项税率%" min={0} max={20} precision={2} value={salesDraft.service_vat_rate_pct} onChange={(v) => setSalesDraft((d) => ({ ...d, service_vat_rate_pct: Number(v ?? 0) }))} />
                          </>
                        ) : (
                          <Text type="secondary">小规模：不抵扣进项（进项可抵扣%按 0 处理）</Text>
                        )}
                      </Space>
                    </Space>
                  </Card>

                  <Modal
                    title="新建预设（利润推演输入）"
                    open={salesPresetCreateOpen}
                    onCancel={() => setSalesPresetCreateOpen(false)}
                    okText="创建"
                    cancelText="取消"
                    onOk={() => {
                      const name = String(salesPresetCreateName ?? '').trim()
                      if (!name) {
                        message.warning('请先填写预设名称')
                        return
                      }
                      const id = `p_${Date.now()}_${Math.random().toString(16).slice(2)}`
                      const now = new Date().toISOString()
                      const next: SalesPricingPreset[] = [{ id, name, updated_at: now, data: salesDraft }, ...salesPresets]
                      setSalesPresets(next)
                      saveSalesPricingPresets(next)
                      setSalesPresetId(id)
                      setSalesPresetCreateOpen(false)
                      message.success(`已新建预设：${name}`)
                    }}
                  >
                    <Input
                      placeholder="例如：利润款-天猫-上海中通-日常（含税率/费率）"
                      value={salesPresetCreateName}
                      onChange={(e) => setSalesPresetCreateName(e.target.value)}
                      onPressEnter={() => {
                        // let Modal OK handle
                      }}
                    />
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">说明：该预设会保存“成本构成分析与利润模型推演（输入）”区域的全部参数，用于下次选模型/尺寸后直接复算。</Text>
                    </div>
                  </Modal>
                </>
              ) : (
                <>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="模块（套装模板）">
                        <Select
                          showSearch
                          allowClear
                          placeholder="选择套装（B-XXXXAA）"
                          options={bundleTemplateOptions as any}
                          value={bundleDraft.bundle_code ?? undefined}
                          loading={bundleTemplatesQuery.isLoading}
                          onChange={(v) =>
                            setBundleDraft((d) => ({ ...d, bundle_code: (v as string) ?? null, bundle_selector: null, spec_text: '' }))
                          }
                          style={{ width: '100%' }}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="版本（短语 selector）">
                        <Select
                          allowClear
                          placeholder="选择 AA/AB/…（对应运营短语）"
                          options={bundlePhraseOptions as any}
                          value={bundleDraft.bundle_selector ?? undefined}
                          loading={bundleTemplateDetailQuery.isLoading}
                          onChange={(v) => setBundleDraft((d) => ({ ...d, bundle_selector: (v as string) ?? null }))}
                          style={{ width: '100%' }}
                          disabled={!bundleDraft.bundle_code}
                        />
                      </Card>
                    </Col>
                  </Row>
                  <Button
                    type="primary"
                    disabled={!bundleDraft.bundle_code}
                    onClick={() => {
                      if (!bundleDraft.bundle_code) {
                        message.warning('请先选择套装模板')
                        return
                      }
                      message.success('已生成规格列表（可编辑/可校验）')
                    }}
                  >
                    生成规格
                  </Button>
                  <BundlePhraseListPanel
                    title="规格生成"
                    bundleCode={effectiveBundleCode}
                    phrasePresets={(((bundleTemplateDetailQuery.data as any)?.metadata ?? {})?.phrase_presets ?? []) as any}
                    activeSelector={bundleDraft.bundle_selector}
                    defaultOpen
                    showGenerateBom
                    generateBomLoading={bundlePreviewMutation.isPending}
                    generatingSelector={specGenGeneratingSelector}
                    onGenerateBom={(args: { selector: string; phrase: string }) => {
                      const selector = args.selector
                      const phrase = args.phrase
                      // 关键：spec_text 只写“对客短语”，不要拼 B码；bundlePreviewMutation 会自动拼 token
                      setSpecGenGeneratingSelector(String(selector))
                      setBundleDraft((d) => ({ ...d, bundle_selector: selector, spec_text: String(phrase || '').trim() }))
                      // 直接预演并在右侧展示最终BOM（原界面不变）
                      bundlePreviewMutation.mutate()
                    }}
                  />
                </>
              )}

              {mode === 'single' && bundleTokenInSpec ? (
                <Alert
                  type="success"
                  showIcon
                  message={`检测到套装编码：${bundleTokenInSpec}`}
                  description="将优先按交易规格中的 BUNDLE 编码生成合并BOM（无需选择模型/版本，也不解析尺寸）。"
                />
              ) : null}

              {mode === 'single' ? (
                <>
                  {!draft.model_id ? (
                    <Alert
                      type="info"
                      showIcon
                      message={
                        singleModelKind === 'standard'
                          ? '提示：先选择一个标准模型，再选择“已发布标准版本”用于预演。'
                          : '提示：先选择一个打样模型，再选择一个版本用于预演。'
                      }
                    />
                  ) : singleModelKind === 'standard' && !showAllStandardVersions && selectableStandardVersions.length === 0 ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="该模型暂无已发布标准版本（published）。请先发布标准版本，否则无法用于生产级预演。"
                    />
                  ) : null}
                </>
              ) : null}

              {mode === 'single' ? (
                <Input.TextArea
                  rows={4}
                  placeholder="粘贴运营的交易规格（spec_text）"
                  value={draft.spec_text}
                  onChange={(e) => setDraft((d) => ({ ...d, spec_text: e.target.value }))}
                />
              ) : null}

              <Space>
                <Button
                  onClick={() => {
                    setParsed(null)
                    setBom(null)
                    setLastError(null)
                  }}
                >
                  清空结果
                </Button>
                {mode === 'single' || mode === 'sales' ? (
                  <>
                    <Button loading={parseMutation.isPending} onClick={() => parseMutation.mutate()}>
                      仅解析（spec/parse）
                    </Button>
                    <Button type="primary" loading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                      解析 + 预演 BOM（bom/generate）
                    </Button>
                  </>
                ) : (
                  <Button type="primary" loading={bundlePreviewMutation.isPending} onClick={() => bundlePreviewMutation.mutate()}>
                    套装：预演 BOM（B:编码）
                  </Button>
                )}
              </Space>
              {mode === 'multi' ? (
                <Alert
                  type="info"
                  showIcon
                  message={
                    <Space wrap size={10}>
                      <Text>Debug：</Text>
                      <Button size="small" type={bundleDebugMode ? 'primary' : 'default'} onClick={() => setBundleDebugMode((v) => !v)}>
                        {bundleDebugMode ? '已开启（返回组件明细）' : '关闭'}
                      </Button>
                      <Button
                        size="small"
                        disabled={!bundleDebugRaw}
                        onClick={async () => {
                          try {
                            const text = JSON.stringify(bundleDebugRaw ?? {}, null, 2)
                            await navigator.clipboard.writeText(text)
                            message.success('已复制套装 debug 诊断 JSON（可直接发给任何人/新AGENT排障）')
                          } catch (e: any) {
                            message.error(`复制失败：${String(e?.message ?? e)}`)
                          }
                        }}
                      >
                        复制诊断
                      </Button>
                      <Text type="secondary">开启后会展示每个组件的命中明细（含 forced_by_bundle），便于定位 30×50/45×45 配对问题。</Text>
                    </Space>
                  }
                />
              ) : null}

              {lastError ? <Alert type="error" showIcon message="执行失败" description={lastError} /> : null}

              <Divider style={{ margin: '8px 0' }} />

              {mode === 'single' ? (
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="模型">
                    {selectedModel ? (
                      <Space size={8}>
                        <Text strong>{selectedModel.model_code}</Text>
                        <Text>{selectedModel.model_name}</Text>
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="版本">
                    {selectedVersion ? (
                      <Space size={8}>
                        <Text strong>{selectedVersion.version_label || selectedVersion.id}</Text>
                        {String(selectedVersion.version_status) === 'published' ? (
                          <Tag color="green">published</Tag>
                        ) : (
                          <Tag color="orange">{String(selectedVersion.version_status || 'draft')}</Tag>
                        )}
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                </Descriptions>
              ) : mode === 'sales' ? (
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="模型">
                    {selectedModel ? (
                      <Space size={8}>
                        <Text strong>{selectedModel.model_code}</Text>
                        <Text>{selectedModel.model_name}</Text>
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="版本">
                    {salesSelectedVersion ? (
                      <Space size={8}>
                        <Text strong>{salesSelectedVersion.version_label || salesSelectedVersion.id}</Text>
                        {String(salesSelectedVersion.version_status) === 'published' ? (
                          <Tag color="green">published</Tag>
                        ) : (
                          <Tag color="orange">{String(salesSelectedVersion.version_status || 'draft')}</Tag>
                        )}
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="进厂价（合计成本）">
                    <Text strong>{formatMoney2(costingSummary?.total_cost)}</Text>
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="套装">
                    {bundleDraft.bundle_code ? <Text code>{`B:${bundleDraft.bundle_code}`}</Text> : <Text type="secondary">未选择</Text>}
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="诊断结果（只读）">
            {mode === 'sales' ? (
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <Alert
                  type="info"
                  showIcon
                  message="利润推演结果（只读）"
                  description={
                    (salesDraft.taxpayer_kind === 'small'
                      ? '小规模：不抵扣进项（进项可抵扣按 0），税金=销项增值税+附加税。'
                      : '一般纳税人：税金按“销项-进项抵扣”估算。') +
                    ' 毛利/利润按不含税收入口径展示；成交价为“含税到手价（GMV）”；退货损失按“退货率×不可售占比×产品成本”估算。'
                  }
                />
                {!costingSummary ? (
                  <Alert type="warning" showIcon message="请先在左侧点“解析 + 预演 BOM”生成合计成本（进厂价）。" />
                ) : salesCalc && (salesCalc as any).error ? (
                  <Alert type="error" showIcon message="无法计算" description={String((salesCalc as any).error)} />
                ) : salesCalc ? (
                  <Card size="small" title="测算结果（建议）">
                    <Descriptions bordered size="small" column={3}>
                      <Descriptions.Item label="进厂价/单位成本">{formatMoney2((salesCalc as any).factory_cost)}</Descriptions.Item>
                      <Descriptions.Item label="含税到手价（成交）">
                        <b>{formatMoney2((salesCalc as any).deal_gmv)}</b>
                      </Descriptions.Item>
                      <Descriptions.Item label="建议标价">
                        <b>{formatMoney2((salesCalc as any).list_price)}</b>
                      </Descriptions.Item>

                      <Descriptions.Item label="不含税收入">{formatMoney2((salesCalc as any).net_revenue_ex_tax)}</Descriptions.Item>
                      <Descriptions.Item label="增值税(销项)">{formatMoney2((salesCalc as any).vat_output)}</Descriptions.Item>
                      <Descriptions.Item label="进项可抵扣(估算)">
                        {formatMoney2((salesCalc as any).input_vat_credit)}
                        <div style={{ fontSize: 12, color: '#888' }}>
                          进厂:{formatMoney2((salesCalc as any).input_vat_credit_goods)} / 平台(6%):{formatMoney2((salesCalc as any).input_vat_credit_platform)} / 广告(6%):
                          {formatMoney2((salesCalc as any).input_vat_credit_ad)}
                        </div>
                      </Descriptions.Item>
                      <Descriptions.Item label="应纳增值税(估算)">{formatMoney2((salesCalc as any).payable_vat)}</Descriptions.Item>
                      <Descriptions.Item label="附加税">{formatMoney2((salesCalc as any).tax_surcharge)}</Descriptions.Item>
                      <Descriptions.Item label="税金合计">{formatMoney2((salesCalc as any).tax_total)}</Descriptions.Item>
                      <Descriptions.Item label="税金等效占比(含税)">{String(Number((salesCalc as any).tax_effective_pct ?? 0).toFixed(2))}%</Descriptions.Item>
                      <Descriptions.Item label="不含税毛利率">{String(Number((salesCalc as any).gross_margin_ex_tax_pct ?? 0).toFixed(2))}%</Descriptions.Item>

                      <Descriptions.Item label="平台费(元)">{formatMoney2((salesCalc as any).platform_fee)}</Descriptions.Item>
                      <Descriptions.Item label="广告费(元)">{formatMoney2((salesCalc as any).ad_fee)}</Descriptions.Item>
                      <Descriptions.Item label="销售提成(元)">{formatMoney2((salesCalc as any).commission_fee)}</Descriptions.Item>
                      <Descriptions.Item label="快递费(元)">{formatMoney2((salesCalc as any).shipping_fee)}</Descriptions.Item>
                      <Descriptions.Item label="固定成本(元)">{formatMoney2((salesCalc as any).fixed_cost)}</Descriptions.Item>
                      <Descriptions.Item label="固定费用(元)">{formatMoney2((salesCalc as any).fixed_fees)}</Descriptions.Item>
                      <Descriptions.Item label="退货价值损失(元)">{formatMoney2((salesCalc as any).return_value_loss)}</Descriptions.Item>
                      <Descriptions.Item label="目标净利(元)">{formatMoney2((salesCalc as any).target_net_profit)}</Descriptions.Item>
                      <Descriptions.Item label="目标净利%(含税)">{String(Number((salesCalc as any).target_net_profit_pct ?? 0).toFixed(2))}%</Descriptions.Item>
                      {salesDraft.pricing_mode === 'diagnose' || salesDraft.pricing_mode === 'target_cost' ? (
                        <>
                          <Descriptions.Item label="实际净利(元)">
                            <b>{formatMoney2((salesCalc as any).actual_net_profit)}</b>
                          </Descriptions.Item>
                          <Descriptions.Item label="实际净利%(含税)">
                            <b>{String(Number((salesCalc as any).actual_net_profit_pct ?? 0).toFixed(2))}%</b>
                          </Descriptions.Item>
                          {salesDraft.pricing_mode === 'target_cost' ? (
                            <>
                              <Descriptions.Item label="可承受进厂价(元)">
                                <b>{formatMoney2((salesCalc as any).target_factory_cost_max)}</b>
                              </Descriptions.Item>
                              <Descriptions.Item label="需降本(元)">
                                <b>{formatMoney2((salesCalc as any).target_cost_gap)}</b>
                              </Descriptions.Item>
                              <Descriptions.Item label="需降本%（相对当前）">
                                <b>{String(Number((salesCalc as any).target_cost_gap_pct ?? 0).toFixed(2))}%</b>
                              </Descriptions.Item>
                            </>
                          ) : null}
                          <Descriptions.Item label="提示">
                            <Text type="secondary">
                              {salesDraft.pricing_mode === 'diagnose'
                                ? '诊断模式：净利=GMV-所有成本项合计（含税金与退货价值损失）。'
                                : '目标成本模式：给定市场价，反推“允许的最大进厂价/单位成本”（满足目标净利%）；对比当前进厂价给出需降本缺口。'}
                            </Text>
                          </Descriptions.Item>
                        </>
                      ) : null}
                    </Descriptions>
                    <Divider style={{ margin: '10px 0' }} />
                    <Text type="secondary">
                      {salesDraft.pricing_mode === 'solve'
                        ? '反推公式：GMV = (产品成本 + 快递费(元) + 固定费用 + 退货价值损失) / (1 − 平台费% − 广告费% − 销售提成% − 固定成本% − 税金等效% − 目标净利%)'
                        : salesDraft.pricing_mode === 'target_cost'
                          ? '目标成本：在给定 GMV 下，反推“允许的最大进厂价/单位成本”，使净利满足目标净利%。'
                          : '诊断：在给定 GMV 下，计算各成本项与净利率。'}
                    </Text>
                    <div style={{ marginTop: 6 }}>
                      <Text type="secondary">
                        税金等效% = 税金合计 / GMV；一般纳税人：税金合计=（应纳增值税+附加税），应纳增值税≈max(0, 销项增值税−进项可抵扣)；小规模：应纳增值税=销项增值税（不抵扣）。
                      </Text>
                    </div>
                  </Card>
                ) : null}
              </Space>
            ) : (
              <Tabs
                className="product-listing-tabs product-listing-tabs--right"
                items={[
                ...(mode === 'single'
                  ? ([
                      {
                        key: 'parse',
                        label: '解析结果',
                        children: parsed ? (
                          <>
                            <Space wrap style={{ marginBottom: 8 }}>
                              <Tag color="blue">tokens: {(parsed.tokens ?? []).length}</Tag>
                              {parsed.width_cm != null ? <Tag>宽(cm)：{String(parsed.width_cm)}</Tag> : null}
                              {parsed.height_cm != null ? <Tag>高(cm)：{String(parsed.height_cm)}</Tag> : null}
                              {parsed.area_m2 != null ? <Tag>面积(m²)：{String(parsed.area_m2)}</Tag> : null}
                              {parsed.perimeter_m != null ? <Tag>周长(m)：{String(parsed.perimeter_m)}</Tag> : null}
                            </Space>
                            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(parsed, null, 2)}</pre>
                          </>
                        ) : (
                          <Text type="secondary">暂无（先点“仅解析”或“解析+预演”）</Text>
                        ),
                      },
                      {
                        key: 'matched',
                        label: '命中情况',
                        children: bom ? (
                    <>
                      <Space wrap style={{ marginBottom: 8 }}>
                        {variantsByBaseLineQuery.isLoading ? <Tag>加载规则详情中…</Tag> : null}
                        {versionLinesQuery.isLoading ? <Tag>加载基准清单中…</Tag> : null}
                      </Space>
                      <Table
                        rowKey={(r: any, idx) => String(r?.variant_id ?? idx)}
                        size="small"
                        pagination={false}
                        dataSource={matchedVariants}
                        columns={[
                          {
                            title: '触发条件',
                            key: 'trigger',
                            width: 320,
                            render: (_: any, r: any) => {
                              const v = variantMap.get(String(r?.variant_id ?? ''))
                              return <Text>{formatTrigger((v as any)?.conditions)}</Text>
                            },
                          },
                          {
                            title: '基准物料',
                            key: 'base_material',
                            width: 220,
                            render: (_: any, r: any) => {
                              const base = baseLineMaterialMap.get(String(r?.base_line_id ?? ''))
                              if (!base) return <Text type="secondary">-</Text>
                              return (
                                <Space size={6}>
                                  <Text code>{String(base.material_code ?? base.material_ref_id ?? '-')}</Text>
                                  <Text>{String(base.material_name ?? '')}</Text>
                                </Space>
                              )
                            },
                          },
                          {
                            title: '替换物料',
                            key: 'target_material',
                            width: 240,
                            render: (_: any, r: any) => {
                              const v = variantMap.get(String(r?.variant_id ?? ''))
                              const it = (v?.items ?? [])[0]
                              if (!it) return <Text type="secondary">-</Text>
                              return (
                                <Space size={6}>
                                  <Text code>{String(it.material_code ?? it.material_ref_id ?? '-')}</Text>
                                  <Text>{String(it.material_name ?? '')}</Text>
                                  {it.unit_of_measure ? <Tag>{String(it.unit_of_measure)}</Tag> : null}
                                </Space>
                              )
                            },
                          },
                          { title: 'variant_id', dataIndex: 'variant_id', width: 240, render: (v) => <Text code>{String(v)}</Text> },
                          { title: 'base_line_id', dataIndex: 'base_line_id', width: 240, render: (v) => <Text code>{String(v)}</Text> },
                          { title: 'action', dataIndex: 'action', width: 120 },
                          {
                            title: 'matched',
                            dataIndex: 'matched',
                            width: 90,
                            render: (v) => (v ? <Tag color="green">true</Tag> : <Tag>false</Tag>),
                          },
                          { title: 'effect', dataIndex: 'effect', width: 120, render: (v) => String(v ?? '') },
                        ]}
                      />
                      <Divider style={{ margin: '12px 0' }} />
                      <Text type="secondary">trace（完整）</Text>
                      <pre style={{ whiteSpace: 'pre-wrap', margin: '6px 0 0' }}>
                        {JSON.stringify(bom.trace ?? {}, null, 2)}
                      </pre>
                    </>
                  ) : (
                    <Text type="secondary">暂无（先点“解析+预演”）</Text>
                  ),
                      },
                    ] as any[])
                  : []),
                {
                  key: 'bom',
                  label: '最终 BOM（final_material_lines）',
                  children: bom ? (
                    <Space direction="vertical" style={{ width: '100%' }} size={12}>
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>{formatMoney2(costingSummary?.total_cost)}</b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">{formatMoney2(costingSummary?.material_cost_total)}</Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">{formatMoney2(costingSummary?.process_cost_total)}</Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY，23%）">{formatMoney2(costingSummary?.overhead_cost)}</Descriptions.Item>
                        <Descriptions.Item label="制造费率（展示）">{costingSummary ? '23%' : '-'}</Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">{formatMoney2(costingSummary?.unit_cost)}</Descriptions.Item>
                        <Descriptions.Item label="已计价物料行">{String(costingSummary?.priced_material_lines ?? '-')}</Descriptions.Item>
                        <Descriptions.Item label="缺物料单价行">{String(costingSummary?.missing_price_material_lines ?? '-')}</Descriptions.Item>
                        <Descriptions.Item label="缺工序单价行">{String(costingSummary?.missing_price_process_lines ?? '-')}</Descriptions.Item>
                      </Descriptions>
                      {(costingSummary?.missing_price_material_codes ?? []).length ? (
                        <Alert
                          type="error"
                          showIcon
                          message="存在缺失 BOM 单价的物料行（会导致行成本为空/0，影响总成本）"
                          description={
                            <Space wrap size={6}>
                              <Text type="secondary">缺单价编码：</Text>
                              {(costingSummary?.missing_price_material_codes ?? []).slice(0, 12).map((c: string) => (
                                <Tag key={c} color="red">
                                  {c}
                                </Tag>
                              ))}
                              {(costingSummary?.missing_price_material_codes ?? []).length > 12 ? <Text type="secondary">…</Text> : null}
                              <Text type="secondary">处理建议：为虚拟物料设置 metadata.bom_unit_price，或确保其展开后的真实物料有单价并在成本口径里使用展开成本。</Text>
                            </Space>
                          }
                        />
                      ) : null}

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>物料（{finalLines.length}）</Text>
                      <Table
                        rowKey={(r) =>
                          String((r as any)?.id ?? `${(r as any)?.material_ref_id ?? ''}-${(r as any)?.sequence_order ?? ''}`)
                        }
                        size="small"
                        pagination={false}
                        dataSource={finalLines}
                        columns={[
                          { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
                          { title: '名称', dataIndex: 'material_name', width: 220, ellipsis: true, render: (v) => v ?? '-' },
                          { title: '数量', dataIndex: 'computed_quantity', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
                          { title: '计量方式', dataIndex: 'calculation_method', width: 90, render: (v) => String(v ?? '-') },
                          { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                          {
                            title: 'BOM单价',
                            dataIndex: 'bom_unit_price',
                            width: 90,
                            render: (v) => {
                              const miss = v == null || v === ''
                              return (
                                <Space size={6}>
                                  <Text>{formatMoney2(v)}</Text>
                                  {miss ? <Tag color="red">缺单价</Tag> : null}
                                </Space>
                              )
                            },
                          },
                          {
                            title: '行成本',
                            dataIndex: 'line_cost',
                            // 最后一列不固定宽度，保持整体更自然
                            render: (v, r: any) => {
                              const miss = (r as any)?.bom_unit_price == null || (r as any)?.bom_unit_price === ''
                              return (
                                <Space size={6}>
                                  <Text>{formatMoney2(v)}</Text>
                                  {miss ? <Tag color="red">缺单价</Tag> : null}
                                </Space>
                              )
                            },
                          },
                        ]}
                      />

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>工序（{processLines.length}）</Text>
                      <Table
                          size="small"
                          pagination={false}
                          rowKey={(r: any, idx?: number) =>
                            String(r?.process_id ?? '') +
                            '-' +
                            String(r?.process_code ?? '') +
                            '-' +
                            String(r?.component_index ?? '') +
                            '-' +
                            String(idx ?? 0)
                          }
                          columns={[
                            { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                            { title: '工序名称', dataIndex: 'process_name', width: 220, ellipsis: true },
                            { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                            { title: '计量', dataIndex: 'pricing_method', width: 90 },
                            { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                            { title: '计价', dataIndex: 'cost_type', width: 90 },
                            { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                            { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                            { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                            { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney2(v) },
                            {
                              title: '警告',
                              dataIndex: 'warnings',
                              // 最后一列自然宽度：吸收剩余空间，避免把额外宽度挤到“工序名称”
                              render: (v) =>
                                Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                            },
                          ]}
                          dataSource={processLines}
                          locale={{ emptyText: '暂无工序明细（可先“解析+预演”或“套装：预演 BOM”）' }}
                        />

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>扣库单</Text>
                      {Array.isArray((bom?.trace as any)?.inventory?.warnings) && ((bom?.trace as any)?.inventory?.warnings ?? []).length ? (
                        <Alert
                          style={{ marginTop: 8 }}
                          type="warning"
                          showIcon
                          message="扣库展开存在提示（可能导致部分物料未展开）"
                          description={String(((bom?.trace as any)?.inventory?.warnings ?? []).slice(0, 5).join('；'))}
                        />
                      ) : null}
                      {inventoryLines.length ? (
                        <Table
                          size="small"
                          pagination={false}
                          rowKey={(r) => String((r as any)?.material_code ?? '')}
                          columns={[
                            { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
                            { title: '物料名称', dataIndex: 'material_name', width: 220, ellipsis: true },
                            { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                            { title: '扣库数量', dataIndex: 'quantity', width: 90 },
                            {
                              title: '来源(展开)',
                              dataIndex: 'sources',
                              // 最后一列不固定宽度，保持整体更自然
                              render: (v) => (Array.isArray(v) ? v.length : 0),
                            },
                          ]}
                          dataSource={inventoryLines}
                        />
                      ) : (
                        <Alert
                          type="info"
                          showIcon
                          message="暂未生成扣库单。"
                          description="当前“物料”表可能包含虚拟物料（VM）。若需要对账/扣库，请以“扣库单”为准。"
                        />
                      )}
                    </Space>
                  ) : (
                    <Text type="secondary">暂无（先点“解析+预演”）</Text>
                  ),
                },
                {
                  key: 'bundle_components',
                  label: '套装组件命中（debug）',
                  children:
                    mode === 'multi' ? (
                      bundleComponentsDebug && bundleComponentsDebug.length ? (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Alert
                            type="info"
                            showIcon
                            message="debug 返回：每个组件都有自己的 measurement_mm / runtime_tokens / matched_variants（含 forced_by_bundle）"
                          />
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(_, i) => `bc-${i}`}
                            dataSource={bundleComponentsDebug}
                            columns={[
                              {
                                title: '组件',
                                width: 70,
                                render: (_: any, r: any) => String(r?.component_index ?? '-'),
                              },
                              {
                                title: '版本',
                                width: 160,
                                render: (_: any, r: any) => {
                                  const vid = String((r?.trace ?? {})?.model_version_id ?? '').trim()
                                  return vid ? <Text code>{vid.slice(0, 8)}…</Text> : <Text type="secondary">-</Text>
                                },
                              },
                              {
                                title: '尺寸/数量',
                                width: 160,
                                render: (_: any, r: any) => {
                                  const mm = (r?.trace ?? {})?.measurement_mm ?? {}
                                  const w = toNumberOrNull((mm as any)?.width_mm)
                                  const h = toNumberOrNull((mm as any)?.height_mm)
                                  const q = toNumberOrNull((mm as any)?.quantity)
                                  const wcm = w != null ? (w / 10).toFixed(0) : '-'
                                  const hcm = h != null ? (h / 10).toFixed(0) : '-'
                                  return (
                                    <Space size={6}>
                                      <Tag>{wcm}×{hcm}</Tag>
                                      <Tag>qty:{q ?? '-'}</Tag>
                                    </Space>
                                  )
                                },
                              },
                              {
                                title: 'runtime_tokens（截断）',
                                render: (_: any, r: any) => {
                                  const toks = ((r?.trace ?? {})?.runtime_tokens ?? []) as any[]
                                  const show = toks.map((x) => String(x)).filter(Boolean).slice(0, 8)
                                  return show.length ? (
                                    <Space wrap size={6}>
                                      {show.map((t) => (
                                        <Tag key={t}>{t}</Tag>
                                      ))}
                                      {toks.length > 8 ? <Text type="secondary">…</Text> : null}
                                    </Space>
                                  ) : (
                                    <Text type="secondary">-</Text>
                                  )
                                },
                              },
                              {
                                title: '命中摘要',
                                width: 220,
                                render: (_: any, r: any) => {
                                  const hits = ((r?.trace ?? {})?.matched_variants ?? []) as any[]
                                  const forced = hits.find((x) => String(x?.reason ?? '') === 'forced_by_bundle')
                                  const matched = hits.filter((x) => x?.matched === true)
                                  return (
                                    <Space direction="vertical" size={2}>
                                      {forced ? <Tag color="volcano">FORCED</Tag> : <Tag>normal</Tag>}
                                      <Text type="secondary">matched: {matched.length}</Text>
                                    </Space>
                                  )
                                },
                              },
                            ]}
                            expandable={{
                              expandedRowRender: (r: any) => {
                                const hits = ((r?.trace ?? {})?.matched_variants ?? []) as any[]
                                return (
                                  <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                                    {JSON.stringify(hits.slice(0, 80), null, 2)}
                                  </pre>
                                )
                              },
                            }}
                          />
                        </Space>
                      ) : (
                        <Text type="secondary">暂无：请在左侧开启 Debug 后再点“套装：预演 BOM”。</Text>
                      )
                    ) : (
                      <Text type="secondary">仅套装模式可用</Text>
                    ),
                },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}


