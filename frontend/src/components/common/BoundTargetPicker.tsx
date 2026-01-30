import { useEffect, useMemo, useState } from 'react'
import { Select, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { fetchBundleTemplates, fetchPublishedStandardModels } from '@/services/planner'
import type { BundleTemplateRead } from '@/services/planner'
import type { PublishedStandardModelCandidate } from '@/types/planner'

export type BoundTargetKind = 'any' | 'model' | 'bundle'

export type BoundTargetPickerValue = {
  kind: BoundTargetKind
  // model
  model_id?: string
  model_code?: string
  model_name?: string
  published_version_label?: string | null
  // bundle
  bundle_template_code?: string
  bundle_template_name?: string
  bundle_preset_selector?: string
  bundle_preset_phrase?: string
}

export type BoundTargetPickerFilters = {
  bound_target_kind?: 'model' | 'bundle'
  bound_model_code?: string
  bound_version_label?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
}

export interface BoundTargetPickerProps {
  value: BoundTargetPickerValue
  onChange: (next: BoundTargetPickerValue, filters: BoundTargetPickerFilters) => void
  size?: 'small' | 'middle' | 'large'
  allowAny?: boolean
  compact?: boolean
}

const { Text } = Typography

const toFilters = (v: BoundTargetPickerValue): BoundTargetPickerFilters => {
  if (v.kind === 'model') {
    const code = String(v.model_code ?? '').trim()
    const label = String(v.published_version_label ?? '').trim()
    return {
      bound_target_kind: code ? 'model' : undefined,
      bound_model_code: code || undefined,
      bound_version_label: label || undefined,
    }
  }
  if (v.kind === 'bundle') {
    const tpl = String(v.bundle_template_code ?? '').trim().toUpperCase()
    const sel = String(v.bundle_preset_selector ?? '').trim().toUpperCase()
    return {
      bound_target_kind: tpl ? 'bundle' : undefined,
      bound_model_code: tpl ? `B-${tpl}` : undefined,
      bundle_template_code: tpl || undefined,
      bundle_preset_selector: sel || undefined,
    }
  }
  return {}
}

const BoundTargetPicker = ({ value, onChange, size = 'small', allowAny = true, compact = true }: BoundTargetPickerProps) => {
  const [modelSearch, setModelSearch] = useState('')
  const [bundleSearch, setBundleSearch] = useState('')

  useEffect(() => {
    if (value.kind !== 'model') setModelSearch('')
    if (value.kind !== 'bundle') setBundleSearch('')
  }, [value.kind])

  const publishedModelsQuery = useQuery({
    queryKey: ['bound-target-picker', 'published-standard-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    enabled: value.kind === 'model',
  })

  const modelOptions = useMemo(() => {
    const items = ((publishedModelsQuery.data as any)?.items ?? []) as PublishedStandardModelCandidate[]
    return items
      .map((m) => ({
        label: `${String(m.model_code ?? '').trim()} ${String(m.model_name ?? '').trim()}`.trim(),
        value: String(m.model_id ?? '').trim(),
        raw: m,
      }))
      .filter((x) => x.value)
  }, [publishedModelsQuery.data])

  const bundleTemplatesQuery = useQuery({
    queryKey: ['bound-target-picker', 'bundle-templates', bundleSearch],
    queryFn: () => fetchBundleTemplates({ search: bundleSearch || undefined, page: 1, page_size: 50 }),
    enabled: value.kind === 'bundle',
  })

  const bundleTemplates = useMemo(() => {
    return (((bundleTemplatesQuery.data as any)?.items ?? []) as BundleTemplateRead[]).slice()
  }, [bundleTemplatesQuery.data])

  const bundleTemplateOptions = useMemo(() => {
    return bundleTemplates
      .map((t) => ({
        label: `${String((t as any)?.code ?? '').trim()} ${String((t as any)?.name ?? '').trim()}`.trim(),
        value: String((t as any)?.code ?? '').trim().toUpperCase(),
      }))
      .filter((x) => x.value)
  }, [bundleTemplates])

  const selectedBundleTemplate = useMemo(() => {
    const code = String(value.bundle_template_code ?? '').trim().toUpperCase()
    if (!code) return null
    return bundleTemplates.find((t: any) => String(t?.code ?? '').trim().toUpperCase() === code) || null
  }, [bundleTemplates, value.bundle_template_code])

  const bundleSelectorOptions = useMemo(() => {
    const meta = (selectedBundleTemplate as any)?.metadata ?? {}
    const presets = (meta?.phrase_presets ?? meta?.presets ?? []) as any[]
    return presets
      .map((p: any) => {
        const selector = String(p?.selector ?? p?.key ?? '').trim().toUpperCase()
        const phrase = String(p?.phrase ?? p?.label ?? '').trim()
        return { value: selector, label: phrase ? `${selector} ${phrase}` : selector, phrase }
      })
      .filter((x: any) => x.value)
  }, [selectedBundleTemplate])

  const kindOptions = useMemo(() => {
    const items: Array<{ value: BoundTargetKind; label: string }> = []
    if (allowAny) items.push({ value: 'any', label: '模型/套装(全部)' })
    items.push({ value: 'model', label: '标准模型' })
    items.push({ value: 'bundle', label: '套装模块' })
    return items
  }, [allowAny])

  const setValue = (next: BoundTargetPickerValue) => onChange(next, toFilters(next))

  return (
    <Space size={compact ? 6 : 10} wrap>
      <Select
        size={size}
        value={value.kind}
        style={{ width: 140 }}
        options={kindOptions as any}
        onChange={(k) => {
          const kind = (String(k || 'any') as BoundTargetKind) || 'any'
          if (kind === 'model') {
            setValue({ kind: 'model' })
            return
          }
          if (kind === 'bundle') {
            setValue({ kind: 'bundle' })
            return
          }
          setValue({ kind: 'any' })
        }}
      />

      {value.kind === 'model' ? (
        <Space size={6} wrap>
          <Select
            size={size}
            showSearch
            allowClear
            style={{ width: 240 }}
            placeholder="目标对象：标准模型"
            filterOption={false}
            onSearch={(s) => setModelSearch(String(s || ''))}
            options={modelOptions as any}
            value={value.model_id}
            onChange={(id) => {
              const v0 = String(id ?? '').trim() || undefined
              const hit = modelOptions.find((x: any) => x.value === v0)?.raw as PublishedStandardModelCandidate | undefined
              const next: BoundTargetPickerValue = {
                kind: 'model',
                model_id: v0,
                model_code: hit?.model_code,
                model_name: hit?.model_name,
                published_version_label: hit?.version_label ?? null,
              }
              setValue(next)
            }}
          />
          {value.published_version_label ? <Tag color="green">发布版本：{String(value.published_version_label)}</Tag> : <Text type="secondary">发布版本：-</Text>}
        </Space>
      ) : null}

      {value.kind === 'bundle' ? (
        <Space size={6} wrap>
          <Select
            size={size}
            showSearch
            allowClear
            style={{ width: 240 }}
            placeholder="目标对象：套装模板"
            filterOption={false}
            onSearch={(s) => setBundleSearch(String(s || ''))}
            options={bundleTemplateOptions as any}
            value={value.bundle_template_code ? String(value.bundle_template_code).trim().toUpperCase() : undefined}
            onChange={(code) => {
              const tpl = String(code ?? '').trim().toUpperCase() || undefined
              const t = bundleTemplates.find((x: any) => String(x?.code ?? '').trim().toUpperCase() === tpl)
              setValue({
                kind: 'bundle',
                bundle_template_code: tpl,
                bundle_template_name: String((t as any)?.name ?? '').trim() || undefined,
                bundle_preset_selector: undefined,
                bundle_preset_phrase: undefined,
              })
            }}
          />
          <Select
            size={size}
            allowClear
            showSearch
            mode="tags"
            maxTagCount={1}
            style={{ width: 220 }}
            placeholder="二级：selector(可选，如 AC)"
            options={bundleSelectorOptions as any}
            value={value.bundle_preset_selector ? [String(value.bundle_preset_selector).trim().toUpperCase()] : []}
            onChange={(vals) => {
              const v0 = Array.isArray(vals) ? String(vals?.[0] ?? '').trim().toUpperCase() : String(vals ?? '').trim().toUpperCase()
              const sel = v0 || undefined
              const hit = bundleSelectorOptions.find((x: any) => String(x.value).trim().toUpperCase() === String(sel ?? '').trim().toUpperCase())
              setValue({
                ...value,
                kind: 'bundle',
                bundle_preset_selector: sel,
                bundle_preset_phrase: hit?.phrase || undefined,
              })
            }}
          />
          {value.bundle_preset_phrase ? (
            <Tag color="green" title={String(value.bundle_preset_phrase)}>
              {String(value.bundle_preset_phrase)}
            </Tag>
          ) : null}
        </Space>
      ) : null}
    </Space>
  )
}

export default BoundTargetPicker

