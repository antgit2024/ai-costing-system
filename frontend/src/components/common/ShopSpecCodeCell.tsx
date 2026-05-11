import React from 'react'
import { CheckCircleFilled } from '@ant-design/icons'
import { Tooltip, Typography, Tag, Space } from 'antd'

import {
  classifyShopSpecCode,
  type ShopSpecCodeClassification,
  type ShopSpecCodeKind,
} from '../../utils/shopSpecCode'

const { Text } = Typography

interface CellProps {
  value: string | null | undefined
  /**
   * 原始 ERP 商家编码（归一化前），如 "Q26041801KB8-001"。
   * 当 `value` 是被 mapper 归一化后的版本（如 "KB8-001"）时，
   * 把这个传进来会在 Tooltip 里加一行 "ERP 原始: ..." 给运营审计。
   */
  rawValue?: string | null | undefined
  /** When true, render the value as monospace + copyable (table cell mode). Default true. */
  copyable?: boolean
}

/**
 * Renders 商家编码 cell with **minimal** visual classification:
 *   - 可自动匹配（structured） : 绿色字 + ✓ 前缀
 *   - 平台默认ID / 不规范       : 灰色弱化字（不再加 Tag）
 *   - 未同步（empty）          : 灰色「未同步」
 *
 * Single source of truth for SKU master / DoneTab / PendingTab / ShipmentLedger.
 * 设计取舍：去掉了"可自动匹配 / 平台默认ID / 不规范"的 Tag 文字，
 * 因为运营只关心两件事：① 这条能不能自动绑（绿✓）② 还是得手工改吉客云（灰）。
 * Tag 文字反而占地方、稀释信息密度。
 *
 * 归一化提示（2026-05-12）：当 ``rawValue`` 与 ``value`` 不同时，在
 * Tooltip 末尾追加 "ERP 原始: <rawValue>"，让运营知道我们做了归一化。
 */
export const ShopSpecCodeCell: React.FC<CellProps> = ({ value, rawValue, copyable = true }) => {
  const cls: ShopSpecCodeClassification = classifyShopSpecCode(value)
  if (cls.kind === 'empty') {
    return (
      <Tooltip title={cls.tooltip}>
        <Text type="secondary">未同步</Text>
      </Tooltip>
    )
  }
  const text = (value ?? '').toString().trim()
  const rawText = (rawValue ?? '').toString().trim()
  const wasNormalized = !!rawText && rawText !== text
  const isStructured = cls.kind === 'structured'
  const tooltipNode = wasNormalized ? (
    <span>
      {cls.tooltip}
      <br />
      <span style={{ opacity: 0.85 }}>
        ERP 原始：<code>{rawText}</code>
        <br />
        （我们识别出末尾 <code>{text}</code> 是真实模型编码，已自动剥前缀；如错请联系研发）
      </span>
    </span>
  ) : (
    cls.tooltip
  )
  return (
    <Tooltip title={tooltipNode}>
      <Space size={4} wrap={false} align="center">
        {isStructured ? (
          <CheckCircleFilled style={{ color: '#52c41a', fontSize: 12 }} />
        ) : null}
        <Text
          type={isStructured ? undefined : 'secondary'}
          copyable={copyable ? { text } : false}
          style={{
            fontFamily: 'monospace',
            fontSize: 12,
            color: isStructured ? '#52c41a' : undefined,
          }}
        >
          {text}
        </Text>
        {wasNormalized ? (
          <Text type="secondary" style={{ fontSize: 11 }}>
            (已归一化)
          </Text>
        ) : null}
      </Space>
    </Tooltip>
  )
}

interface SummaryProps {
  /** Counts per kind. Pass partial; missing keys treated as 0. */
  summary: Partial<Record<ShopSpecCodeKind, number>>
  /** Total row count for percentage display. Optional. */
  total?: number
  /** Optional click handler so the strip can act as quick filters.
   *  Receives 'all' | 'structured' | 'nonstructured' | 'empty'.
   *  ('platform' / 'malformed' merged into 'nonstructured' for the strip.) */
  onSelect?: (kind: 'all' | 'structured' | 'nonstructured' | 'empty') => void
  /** Currently active kind filter (for highlight). */
  activeKind?: 'all' | 'structured' | 'nonstructured' | 'empty'
}

/**
 * Counter strip — 3 buckets only (not 4): "可自动匹配 / 非规范 / 未同步".
 * platform + malformed merged into "非规范" because for ops they share the
 * same remediation action ("go fix tradeGoodsno in 吉客云").
 */
export const ShopSpecCodeSummaryStrip: React.FC<SummaryProps> = ({
  summary,
  total,
  onSelect,
  activeKind = 'all',
}) => {
  const structured = summary.structured ?? 0
  const platform = summary.platform ?? 0
  const malformed = summary.malformed ?? 0
  const empty = summary.empty ?? 0
  const nonstructured = platform + malformed

  const fmt = (n: number) => {
    if (!total || total <= 0) return `${n}`
    return `${n}（${((100 * n) / total).toFixed(1)}%）`
  }
  const items: Array<{
    key: 'structured' | 'nonstructured' | 'empty'
    label: string
    count: number
  }> = [
    { key: 'structured', label: '✓ 可自动匹配', count: structured },
    { key: 'nonstructured', label: '非规范（待改）', count: nonstructured },
    { key: 'empty', label: '未同步', count: empty },
  ]
  return (
    <Space size={6} wrap>
      {onSelect ? (
        <Tag.CheckableTag
          checked={activeKind === 'all'}
          onChange={() => onSelect('all')}
        >
          全部 {total ?? 0}
        </Tag.CheckableTag>
      ) : (
        <Tag>全部 {total ?? 0}</Tag>
      )}
      {items.map((it) => {
        const tagText = `${it.label} ${fmt(it.count)}`
        if (onSelect) {
          return (
            <Tag.CheckableTag
              key={it.key}
              checked={activeKind === it.key}
              onChange={() => onSelect(it.key)}
            >
              {tagText}
            </Tag.CheckableTag>
          )
        }
        return <Tag key={it.key}>{tagText}</Tag>
      })}
    </Space>
  )
}
