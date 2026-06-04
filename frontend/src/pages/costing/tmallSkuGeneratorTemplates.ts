export type SpecModuleType = '家居布艺' | '家居饰品'

export type TmallSkuTemplateMeta = {
  id: string
  name: string
  type: SpecModuleType
  // 用于列表展示（先按更新时间作为“发布时间”占位）
  published_at: string | null
  matrix_count: number | null
  archived?: boolean
}

export type TmallSkuGeneratorPersistedConfigV1 = {
  merchantSkuPrefix: string
  merchantSkuSuffix: string
  sizes: any[]
  colors: any[]
  mainPatternTypes: any[]
  customSalesAttributes?: any[]
  ui?: {
    enableColorImages?: boolean
    enableSizeImages?: boolean
    enableColorRemarks?: boolean
    enableSizeRemarks?: boolean
    enablePatternRemarks?: boolean
    includeMainPatternType?: boolean
  }
}

const INDEX_KEY = 'tmall_sku_generator_templates_index_v1'
const CFG_PREFIX = 'tmall_sku_generator_template_config_v1:'

export const getTemplateConfigStorageKey = (templateId: string) => `${CFG_PREFIX}${String(templateId ?? '').trim() || 'mvp'}`

export const loadTemplateIndex = (): TmallSkuTemplateMeta[] => {
  try {
    const raw = localStorage.getItem(INDEX_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? (arr as TmallSkuTemplateMeta[]) : []
  } catch {
    return []
  }
}

export const saveTemplateIndex = (rows: TmallSkuTemplateMeta[]) => {
  try {
    localStorage.setItem(INDEX_KEY, JSON.stringify(rows ?? []))
  } catch {
    // ignore
  }
}

export const upsertTemplateMeta = (meta: TmallSkuTemplateMeta) => {
  const rows = loadTemplateIndex()
  const id = String(meta?.id ?? '').trim()
  if (!id) return
  const next = rows.filter((r) => String(r?.id ?? '').trim() !== id)
  next.unshift(meta)
  saveTemplateIndex(next)
}

export const computeMatrixCountFromConfig = (cfg: TmallSkuGeneratorPersistedConfigV1 | null | undefined): number | null => {
  try {
    const sizes = Array.isArray(cfg?.sizes) ? cfg?.sizes : []
    const colors = Array.isArray(cfg?.colors) ? cfg?.colors : []
    const customAttrs = Array.isArray(cfg?.customSalesAttributes)
      ? cfg.customSalesAttributes.filter((attr: any) => attr?.enabled !== false && Array.isArray(attr?.values) && attr.values.length)
      : []
    if (!sizes.length || !colors.length) return 0
    let cnt = 0
    for (const c of colors as any[]) {
      const enabledSizes = (c?.enabledSizes ?? {}) as Record<string, boolean>
      for (const s of sizes as any[]) {
        const sk = String((s as any)?.key ?? '').trim()
        if (!sk) continue
        if (enabledSizes?.[sk] !== false) cnt += 1
      }
    }
    for (const attr of customAttrs) {
      const values = (attr.values as any[]).filter((v) => String(v?.label ?? '').trim())
      cnt *= Math.max(values.length, 1)
    }
    return cnt
  } catch {
    return null
  }
}

export const loadTemplateConfig = (templateId: string): TmallSkuGeneratorPersistedConfigV1 | null => {
  try {
    const raw = localStorage.getItem(getTemplateConfigStorageKey(templateId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed as TmallSkuGeneratorPersistedConfigV1
  } catch {
    return null
  }
}

export const saveTemplateConfig = (templateId: string, cfg: TmallSkuGeneratorPersistedConfigV1) => {
  try {
    localStorage.setItem(getTemplateConfigStorageKey(templateId), JSON.stringify(cfg))
  } catch {
    // ignore
  }
}

