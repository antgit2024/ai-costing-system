import { Tag, Tooltip, Typography } from 'antd'

/**
 * Stage 2 物料取价数据质量徽章 + 价格来源列。
 *
 * 显示口径与 ``CostQualityBadge`` 视觉风格一致（绿/黄/红 三色 Tag）。
 *
 * 数据来源：BOM 行的 ``price_metadata`` 子对象（由后端
 * ``material_price_resolver.resolve_material_price`` 生成）。
 *
 * - 🟢 green = effective_from / tax_rate / price_source 全填
 * - 🟡 yellow = 老数据缺生效期或 price_source（已 fallback，可用但不可审计）
 * - 🔴 red = unit_price 缺失或非正（成本算 0）
 *
 * Hover 显示完整元数据（采购主体 / 含税 / 税率 / 生效期 / 数据质量 / 警告）。
 */

export type MaterialPriceQualityLevel = 'green' | 'yellow' | 'red'

export interface MaterialPriceMetadata {
  price_inclusive?: number | null
  price_exclusive?: number | null
  bom_unit_price_exclusive?: number | null
  tax_rate?: number | null
  tax_included_flag?: boolean | null
  purchase_entity_id?: string | null
  price_source?: string | null
  effective_from?: string | null
  effective_to?: string | null
  _data_quality?: MaterialPriceQualityLevel | string | null
  _warnings?: string[] | null
}

const PRICE_SOURCE_LABEL: Record<string, string> = {
  contract: '合同',
  invoice: '发票',
  po_avg_30d: '采购近 30 天均价',
  purchase_order: '采购单',
  manual: '手填',
  estimate: '估算',
}

const PURCHASE_ENTITY_LABEL: Record<string, string> = {
  一般纳税人: '一般纳税人',
  小规模A: '小规模 A',
  小规模B: '小规模 B',
}

const COLOR_MAP: Record<MaterialPriceQualityLevel, string> = {
  green: 'success',
  yellow: 'warning',
  red: 'error',
}

const LABEL_MAP: Record<MaterialPriceQualityLevel, string> = {
  green: '高',
  yellow: '中',
  red: '低',
}

const formatPct = (v?: number | null): string => {
  if (v === null || v === undefined) return '-'
  return `${(Number(v) * 100).toFixed(1)}%`
}

const formatDate = (v?: string | null): string => {
  if (!v) return '-'
  const s = String(v)
  if (s.length >= 10) return s.slice(0, 10)
  return s
}

export const priceSourceLabelCn = (code?: string | null): string => {
  if (!code) return '未填'
  const k = String(code).toLowerCase()
  return PRICE_SOURCE_LABEL[k] ?? String(code)
}

export interface MaterialPriceQualityBadgeProps {
  metadata?: MaterialPriceMetadata | null
  size?: 'default' | 'small'
  /** 是否在徽章左侧加上"价格来源"文字（合同/发票/...）。默认 true（节省一列）。 */
  withSourceLabel?: boolean
}

const normalizeLevel = (raw?: string | null): MaterialPriceQualityLevel => {
  const v = String(raw ?? '').toLowerCase()
  if (v === 'green' || v === 'yellow' || v === 'red') return v
  return 'yellow'
}

export const MaterialPriceQualityBadge = ({
  metadata,
  size = 'default',
  withSourceLabel = true,
}: MaterialPriceQualityBadgeProps) => {
  if (!metadata) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        -
      </Typography.Text>
    )
  }

  const level = normalizeLevel(metadata._data_quality)
  const sourceLabel = priceSourceLabelCn(metadata.price_source)
  const purchaseEntity = metadata.purchase_entity_id
    ? PURCHASE_ENTITY_LABEL[metadata.purchase_entity_id] ?? metadata.purchase_entity_id
    : '未填'

  const tooltipTitle = (
    <div style={{ lineHeight: 1.6, minWidth: 240 }}>
      <div>
        <b>价格来源</b>：{sourceLabel}
      </div>
      <div>
        <b>采购主体</b>：{purchaseEntity}
      </div>
      <div>
        <b>含税</b>：{metadata.tax_included_flag ? '是' : '否'}
      </div>
      <div>
        <b>税率</b>：{formatPct(metadata.tax_rate)}
      </div>
      <div>
        <b>生效期</b>：{formatDate(metadata.effective_from)} ~ {formatDate(metadata.effective_to) || '至今'}
      </div>
      {metadata.price_inclusive !== null && metadata.price_inclusive !== undefined ? (
        <div>
          <b>含税价</b>：{Number(metadata.price_inclusive).toFixed(4)}
        </div>
      ) : null}
      {metadata.price_exclusive !== null && metadata.price_exclusive !== undefined ? (
        <div>
          <b>不含税价</b>：{Number(metadata.price_exclusive).toFixed(4)}
        </div>
      ) : null}
      <div>
        <b>数据质量</b>：{LABEL_MAP[level]} ({level})
      </div>
      {metadata._warnings && metadata._warnings.length > 0 ? (
        <div style={{ marginTop: 4, color: '#fa8c16' }}>
          <b>警告</b>：
          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            {metadata._warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )

  return (
    <Tooltip title={tooltipTitle} placement="top">
      <Tag
        color={COLOR_MAP[level]}
        style={{
          marginInlineEnd: 0,
          ...(size === 'small' ? { padding: '0 6px', fontSize: 11, lineHeight: '18px' } : {}),
        }}
      >
        {withSourceLabel ? `${sourceLabel} · ${LABEL_MAP[level]}` : LABEL_MAP[level]}
      </Tag>
    </Tooltip>
  )
}

export default MaterialPriceQualityBadge
