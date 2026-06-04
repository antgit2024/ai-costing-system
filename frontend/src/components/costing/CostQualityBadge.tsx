import { Tag, Tooltip, Typography } from 'antd'
import type { CostQualityBadge as CostQualityBadgeData, CostQualityHitLayer, CostQualityLevel } from '@/types/planner'

/**
 * Insights 看板成本可信度徽章 (U7-A).
 *
 * 由后端 `Hub.resolve_overhead_rate` 的 `hit_layer` 推导：
 * - 🟢 model 命中 = 真实精准
 * - 🟡 category / cost_center / metadata_json = 同类近似
 * - 🔴 global / hard_fallback = 全局兜底 / 完全不可信
 *
 * Hover 显示命中层级 + 来源 + 更新时间。
 *
 * 旧前端忽略未知字段不会崩；本组件 `badge` 缺失时显示占位 `-`，避免列空白。
 */

const COLOR_MAP: Record<CostQualityLevel, string> = {
  green: 'success',
  yellow: 'warning',
  red: 'error',
}

const LABEL_MAP: Record<CostQualityLevel, string> = {
  green: '高',
  yellow: '中',
  red: '低',
}

const HIT_LAYER_LABEL: Record<CostQualityHitLayer, string> = {
  model: '模型级精确',
  category: '类目级近似',
  cost_center: '班组级近似',
  global: '全局兜底',
  metadata_json: '历史配置',
  hard_fallback: '硬编码 0.30',
}

const SOURCE_LABEL: Record<string, string> = {
  cost_rate_hub: 'Cost Rate Hub',
  manual: '手动配置',
  metadata_json: '历史 metadata',
  long_tail_legacy: '长尾旧表',
  hardcoded_0_30: '硬编码 0.30',
  'hardcoded_0.30': '硬编码 0.30',
}

const formatDate = (raw?: string | null): string => {
  if (!raw) return '未知'
  // ISO yyyy-mm-ddT… or yyyy-mm-dd → trim to date.
  const s = String(raw)
  if (s.length >= 10 && s[4] === '-' && s[7] === '-') return s.slice(0, 10)
  return s
}

export interface CostQualityBadgeProps {
  badge?: CostQualityBadgeData | null
  /** Optional column-condensed mode: smaller Tag for dense tables. */
  size?: 'default' | 'small'
}

export const CostQualityBadge = ({ badge, size = 'default' }: CostQualityBadgeProps) => {
  if (!badge) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        -
      </Typography.Text>
    )
  }
  const tooltipTitle = (
    <div style={{ lineHeight: 1.6 }}>
      <div>
        <b>命中</b>：{HIT_LAYER_LABEL[badge.hit_layer] ?? badge.hit_layer}
      </div>
      <div>
        <b>来源</b>：{SOURCE_LABEL[badge.source] ?? badge.source}
      </div>
      <div>
        <b>更新</b>：{formatDate(badge.updated_at)}
      </div>
    </div>
  )
  return (
    <Tooltip title={tooltipTitle} placement="top">
      <Tag
        color={COLOR_MAP[badge.level] ?? 'default'}
        style={{
          marginInlineEnd: 0,
          ...(size === 'small'
            ? { padding: '0 6px', fontSize: 11, lineHeight: '18px' }
            : {}),
        }}
      >
        {LABEL_MAP[badge.level] ?? badge.level}
      </Tag>
    </Tooltip>
  )
}

export default CostQualityBadge
