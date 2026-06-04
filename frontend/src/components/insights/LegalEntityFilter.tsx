/**
 * Path A §A5 — 4 个 Insights 看板共享的"法人主体"筛选条。
 *
 * 拉 `/api/planner/finance/companies?is_active=true`，多选；选中的 company_id
 * 通过 onChange 上抛到父组件。父组件可以：
 *   1. 把 company_id 当作一个透传参数(等后端 v1.4 支持后端按主体聚合)
 *   2. 用 `matchRow` 工具做 client-side 模糊匹配——把 finance.companies
 *      的 short_name/name 当成"主体关键词"，看 row 的 channel/shop 字段
 *      是否包含这些关键词(对当前店铺命名习惯"家居饰品-轻物旗舰店-杭州"
 *      足够实用，且对 0 选时短路返回 true)
 *
 * 样式遵循现有 Insights 顶部 toolbar(Form.Item label + Select)。
 */

import { Select, Space, Tooltip, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { fetchFinanceCompanies } from '../../services/financeC1'
import type { FinanceCompanyDTO } from '../../types/financeC1'

const { Text } = Typography

export interface LegalEntityOption {
  value: string
  label: string
  keywords: string[]
}

export interface LegalEntityFilterProps {
  value: string[]
  onChange: (next: string[]) => void
  width?: number | string
  /** 隐藏 tooltip(很挤的 toolbar 用) */
  compact?: boolean
}

/** Hook 形态——在 page 顶层用一次，把 options + value/setValue 暴露出来。 */
export function useLegalEntityFilter() {
  const q = useQuery({
    queryKey: ['planner', 'finance', 'companies', 'forFilter'],
    queryFn: () => fetchFinanceCompanies({ is_active: true }),
    staleTime: 60_000,
  })

  const options: LegalEntityOption[] = useMemo(() => {
    const items = (q.data?.data ?? []) as FinanceCompanyDTO[]
    return items.map(c => {
      // legal_name 通常带"杭州轻物有限公司"这种长串；提取主体短称做客户端模糊匹配的关键词。
      const shortName = c.legal_name
        .replace(/有限公司|股份公司|公司|集团|杭州|上海|北京|深圳|广州/g, '')
        .trim()
      return {
        value: c.id,
        label: c.legal_name,
        keywords: Array.from(
          new Set(
            [shortName, c.legal_name, c.id]
              .filter((s): s is string => Boolean(s && s.trim()))
              .map(s => s.trim())
              .filter(s => s.length >= 2),
          ),
        ),
      }
    })
  }, [q.data])

  return { options, isLoading: q.isLoading, error: q.error }
}

/** 工具：判断一行(其 channel/shop 字段)是否命中选中的法人主体集合。 */
export function rowMatchesLegalEntity(
  rowText: string | null | undefined,
  selectedKeywords: string[],
): boolean {
  if (!selectedKeywords.length) return true
  if (!rowText) return false
  const normalized = rowText.toLowerCase()
  return selectedKeywords.some(kw => normalized.includes(kw.toLowerCase()))
}

export function LegalEntityFilter(props: LegalEntityFilterProps) {
  const { value, onChange, width = 240, compact = false } = props
  const { options, isLoading } = useLegalEntityFilter()

  const select = (
    <Select
      mode="multiple"
      allowClear
      maxTagCount="responsive"
      style={{ width }}
      placeholder="按 法人主体 筛选（留空=全部）"
      loading={isLoading}
      value={value}
      onChange={onChange}
      options={options}
      optionFilterProp="label"
    />
  )

  if (compact) return select

  return (
    <Space size={4}>
      {select}
      <Tooltip
        title={
          <div>
            <div>
              <b>v1 实现</b>：客户端按"店铺名包含主体短称"的模糊匹配过滤当前
              已加载的看板行；选 0 个 = 不过滤；选 N 个 = 任一命中即保留。
            </div>
            <div style={{ marginTop: 4 }}>
              当前页通常按 <code>channel/shop</code> 维度聚合，命中粒度对店铺级足够；
              v1.4 后端按 company_id 聚合上线后，这里会自动升级为真过滤。
            </div>
          </div>
        }
      >
        <Text type="secondary" style={{ fontSize: 12 }}>ⓘ</Text>
      </Tooltip>
    </Space>
  )
}

export default LegalEntityFilter
