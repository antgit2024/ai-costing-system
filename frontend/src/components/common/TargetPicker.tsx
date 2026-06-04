/**
 * <TargetPicker /> —— 通用"绑定目标"选择器（阶段 1）
 *
 * 业务背景
 * --------
 * 本组件用于解决"我要在系统里指定一个'货品/SKU 标的'"的通用问题。
 * 标的有且只有两类，但都呈现"二级"结构：
 *
 *   1) 标准模型 (model)
 *      - 一级：模型编码 + 模型名（如 "KB8 麻感吸水垫"）
 *      - 二级：变体编码（如 "仿羊绒(KB8-001)"）—— **可空**，表示"不指定具体变体"
 *      - 一个标准模型只有一个 published 标准版本（已由 publish 流程保证）
 *
 *   2) 套装模板 (bundle)
 *      - 一级：模板编码 + 名称（如 "KIT01 床上用品三件套"）
 *      - 二级：preset selector（如 "B:KIT01:A 三件标准"）—— 通常**必选**
 *
 * 为什么单独抽组件
 * -----------------
 * - SKU 主档绑定、笛卡尔属性绑定、各类筛选器、天猫 SKU 模板生成等多个场景都需要"二选一选目标"，
 *   旧实现都是各自调 published-standard-models + bundle-templates 两个接口、自己合并，重复且漂移。
 * - 旧的 BoundTargetPicker 只支持模型一级（无变体二级），且强制运营先选"种类(模型/套装)"再搜索，
 *   人工成本高。本组件统一一个搜索框，跨两类候选模糊匹配，输出统一的 `TargetSelection`。
 *
 * 阶段 1 范围
 * -----------
 * - 提供 `<TargetPicker />` + `TargetSelection` 类型 + 后端 `/binding-targets` 客户端
 * - **不**改任何业务页面调用方，避免回归风险
 * - 后续阶段：把 SKU 主档绑定 / 笛卡尔属性绑定 / 三个分析页筛选器逐步迁移过来
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Button,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Tree,
  Typography,
} from 'antd'
import type { ButtonProps, SelectProps } from 'antd'
import type { DataNode } from 'antd/es/tree'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchBindingTargets } from '@/services/planner'
import type { BindingTargetItem, BindingTargetPreset } from '@/services/planner'

const { Text } = Typography

/**
 * 选择结果。统一描述"标的是什么 + 选了哪个二级"，与后端 schemas.BindingTargetItem 同源。
 *
 * - 当 kind="model"：必有 model_id/model_code；variant_code 可空（表示"不限定变体"，按基础线匹配）
 * - 当 kind="bundle"：必有 bundle_id/bundle_code；preset_selector 通常必填（业务方自行校验）
 */
export type TargetSelection =
  | {
      kind: 'model'
      model_id: string
      model_code: string
      model_name: string | null
      published_version_id: string | null
      version_label: string | null
      variant_code: string | null // 可空：不指定具体变体
      variant_label: string | null // 仿羊绒(KB8-001) 之类的展示名，便于业务页面回显
    }
  | {
      kind: 'bundle'
      bundle_id: string
      bundle_code: string
      bundle_name: string | null
      preset_selector: string | null // 业务上通常必填，但本组件不强制（让调用方按需校验）
      preset_label: string | null
      // 'force' = 指定（天猫 token 前缀 Z-）；'parse' = 解析（天猫 token 前缀 B-）；
      // null 表示无 preset 选择（无法派生 token）。
      preset_mode: 'force' | 'parse' | null
    }

export interface TargetPickerProps {
  value?: TargetSelection | null
  onChange?: (next: TargetSelection | null) => void
  /** 限定只搜某类。默认 undefined = 两类都要 */
  kind?: 'model' | 'bundle'
  /** 模板默认 240 px；compact 用于嵌在表格行内 */
  size?: SelectProps['size']
  width?: number | string
  /** 是否允许选择 model 但不指定变体（默认允许；业务上 model 的变体本就可空） */
  allowModelWithoutVariant?: boolean
  placeholder?: string
  disabled?: boolean
}

type Choice = {
  /** unique key per choice in the dropdown */
  value: string
  label: React.ReactNode
  /** original target item & secondary key (variant_code or preset_selector) */
  raw: {
    item: BindingTargetItem
    secondary: string | null // null = 一级本身（用于 model "无变体"选项）
  }
}

// 把一行 BindingTargetItem 展开成"一级 + 各二级"多个候选；
// 比如 KB8 + [KB8-001, KB8-002] → 3 个候选项（"KB8 麻感吸水垫(无变体)" + 2 个变体）
// KIT01 + [B:KIT01:A, B:KIT01:B] → 2 个候选（不再生成"无 preset" 选项，因为 preset 通常必填）
const expandItem = (item: BindingTargetItem, allowModelWithoutVariant: boolean): Choice[] => {
  const out: Choice[] = []
  const codeText = `${item.code}${item.name ? ` ${item.name}` : ''}`

  if (item.kind === 'model') {
    if (allowModelWithoutVariant) {
      out.push({
        value: `model::${item.id}::__none__`,
        label: (
          <Space size={4}>
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              模型
            </Tag>
            <Text>{codeText}</Text>
            <Text type="secondary">（不指定变体）</Text>
          </Space>
        ),
        raw: { item, secondary: null },
      })
    }
    for (const v of item.variants ?? []) {
      out.push({
        value: `model::${item.id}::${v.variant_code}`,
        label: (
          <Space size={4}>
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              模型
            </Tag>
            <Text>{codeText}</Text>
            <Text type="secondary"> · </Text>
            <Tag color="purple" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>
              {v.label}
            </Tag>
          </Space>
        ),
        raw: { item, secondary: v.variant_code },
      })
    }
  } else if (item.kind === 'bundle') {
    const presets = item.presets ?? []
    if (presets.length === 0) {
      // 没有 preset 的套装：仍然给一个候选项（业务方自行决定是否允许保存）
      out.push({
        value: `bundle::${item.id}::__none__`,
        label: (
          <Space size={4}>
            <Tag color="orange" style={{ marginInlineEnd: 0 }}>
              套装
            </Tag>
            <Text>{codeText}</Text>
            <Text type="secondary">（无 preset）</Text>
          </Space>
        ),
        raw: { item, secondary: null },
      })
    } else {
      for (const p of presets) {
        out.push({
          value: `bundle::${item.id}::${p.selector}`,
          label: (
            <Space size={4}>
              <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                套装
              </Tag>
              <Text>{codeText}</Text>
              <Text type="secondary"> · </Text>
              <Tag color="cyan" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>
                {p.label}
              </Tag>
            </Space>
          ),
          raw: { item, secondary: p.selector },
        })
      }
    }
  }
  return out
}

const choiceToSelection = (choice: Choice): TargetSelection => {
  const { item, secondary } = choice.raw
  if (item.kind === 'model') {
    const variant = (item.variants ?? []).find((v) => v.variant_code === secondary) || null
    return {
      kind: 'model',
      model_id: item.id,
      model_code: item.code,
      model_name: item.name ?? null,
      published_version_id: item.published_version_id ?? null,
      version_label: item.version_label ?? null,
      variant_code: variant?.variant_code ?? null,
      variant_label: variant?.label ?? null,
    }
  }
  const preset = (item.presets ?? []).find((p: BindingTargetPreset) => p.selector === secondary) || null
  return {
    kind: 'bundle',
    bundle_id: item.id,
    bundle_code: item.code,
    bundle_name: item.name ?? null,
    preset_selector: preset?.selector ?? null,
    preset_label: preset?.label ?? null,
    preset_mode: preset?.mode ?? null,
  }
}

const selectionToValueKey = (sel: TargetSelection | null | undefined): string | undefined => {
  if (!sel) return undefined
  if (sel.kind === 'model') {
    return `model::${sel.model_id}::${sel.variant_code ?? '__none__'}`
  }
  return `bundle::${sel.bundle_id}::${sel.preset_selector ?? '__none__'}`
}

const TargetPicker = ({
  value,
  onChange,
  kind,
  size = 'middle',
  width = 360,
  allowModelWithoutVariant = true,
  placeholder = '搜索 模型/套装 编码、名称、变体或 preset',
  disabled,
}: TargetPickerProps) => {
  const [search, setSearch] = useState('')

  const query = useQuery({
    queryKey: ['binding-targets', kind ?? 'all', search],
    queryFn: () => fetchBindingTargets({ search: search || undefined, kind, limit: 50 }),
    placeholderData: keepPreviousData,
  })

  const choices: Choice[] = useMemo(() => {
    const items = query.data?.items ?? []
    const out: Choice[] = []
    for (const it of items) {
      out.push(...expandItem(it, allowModelWithoutVariant))
    }
    return out
  }, [query.data, allowModelWithoutVariant])

  const valueKey = selectionToValueKey(value)
  const isLoading = query.isFetching

  return (
    <Tooltip
      title={
        query.data?.truncated
          ? '候选已被限制为 50 条，请输入关键词进一步收敛（搜索支持模型编码/名称/变体编码/材质名/套装编码/名称/preset selector）'
          : null
      }
    >
      <Select
        showSearch
        allowClear
        size={size}
        disabled={disabled}
        style={{ width }}
        placeholder={placeholder}
        filterOption={false}
        notFoundContent={isLoading ? <Spin size="small" /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        value={valueKey}
        onSearch={(s) => setSearch(String(s || ''))}
        onClear={() => onChange?.(null)}
        onChange={(v) => {
          const c = choices.find((x) => x.value === v)
          if (!c) {
            onChange?.(null)
            return
          }
          onChange?.(choiceToSelection(c))
        }}
        options={choices.map((c) => ({ value: c.value, label: c.label, key: c.value }))}
        optionLabelProp="label"
      />
    </Tooltip>
  )
}

export default TargetPicker

/**
 * 工具：把 TargetSelection 渲染成只读 Tag 组合，便于业务页面回显（不强制使用）。
 */
export const renderTargetSelectionTags = (sel: TargetSelection | null | undefined) => {
  if (!sel) return <Text type="secondary">未选</Text>
  if (sel.kind === 'model') {
    return (
      <Space size={4} wrap>
        <Tag color="blue" style={{ marginInlineEnd: 0 }}>
          模型
        </Tag>
        <Text>{sel.model_code}</Text>
        {sel.model_name ? <Text type="secondary">{sel.model_name}</Text> : null}
        {sel.variant_label ? (
          <Tag color="purple" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>
            {sel.variant_label}
          </Tag>
        ) : (
          <Tooltip title="当前选的是「⚠ 兜底」那行——绑定时不会写 bound_variant_code，列表只会显示模型级标签（KB8 转印包边垫类），不会出现 麻感冰丝(KB8-001) 这种二级标签。如需落变体，请重新打开选择器并改选具体变体行。">
            <Tag color="error" style={{ marginInlineEnd: 0 }}>
              ⚠ 未选变体（不会落 variant_code）
            </Tag>
          </Tooltip>
        )}
      </Space>
    )
  }
  return (
    <Space size={4} wrap>
      <Tag color="orange" style={{ marginInlineEnd: 0 }}>
        套装
      </Tag>
      <Text>{sel.bundle_code}</Text>
      {sel.bundle_name ? <Text type="secondary">{sel.bundle_name}</Text> : null}
      {sel.preset_label ? (
        <Tag color="cyan" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>
          {sel.preset_label}
        </Tag>
      ) : (
        <Tag color="default" style={{ marginInlineEnd: 0 }}>
          未选 preset
        </Tag>
      )}
    </Space>
  )
}

// ============================================================
// 浏览模式：<TargetPickerBrowserButton />
// ============================================================
//
// 为什么再加一个组件？
// - 上面 <TargetPicker /> 是"知道关键词的人"的体验：单个搜索 Select、扁平展开。
// - 当二级很多（比如 1 个套装 7 个 preset、10+ 个变体）或运营**不知道叫什么**只想"先看清都有什么"时，
//   树形浏览体验明显更好。
// - 因此本组件提供按钮触发的 Modal，里面是 Tabs(标准模型 / 套装模板) + 搜索 + Tree（一级展开二级）。
// - 输出类型完全复用 TargetSelection，业务方可以无缝替换。
//
// 设计要点
// - 每个 Tab 独立懒加载：切到哪个 Tab 才拉哪类候选（避免一打开就拉双倍数据）
// - 点击叶子（变体/preset）= 选中 + 立即关闭 Modal（一步到位）
// - 一级节点（model 父节点）也可点——表示"不指定变体"（与 inline 模式语义一致）
//   套装一级节点不可点——业务上 preset 必填（避免误选）
// - 已选项在 Tree 里高亮，并在 Modal 底部回显
// - 数据量大时 Tree 默认仅展开"包含已选 / 包含搜索命中"的一级，避免一屏一片

export interface TargetPickerBrowserButtonProps {
  value?: TargetSelection | null
  onChange?: (next: TargetSelection | null) => void
  /** 按钮自定义 props（size/type/disabled 等都直接透传） */
  buttonProps?: Omit<ButtonProps, 'onClick'>
  /** Modal 标题，默认 "选择绑定目标" */
  modalTitle?: string
  /** 默认打开的 Tab，默认 'model' */
  defaultTab?: 'model' | 'bundle'
  /** 一级 model 节点是否可选（即"不指定变体"），默认 true */
  allowModelWithoutVariant?: boolean
  /** 触发按钮显示已选目标文案；为 false 则只显示 placeholder */
  showSelectedOnButton?: boolean
  placeholder?: string
}

const buildModelTree = (
  items: BindingTargetItem[],
  allowModelWithoutVariant: boolean,
): DataNode[] => {
  return items
    .filter((it) => it.kind === 'model')
    .map<DataNode>((it) => {
      const variants = it.variants ?? []
      const headTitle = (
        <Space size={6}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>
            模型
          </Tag>
          <Text strong>{it.code}</Text>
          {it.name ? <Text type="secondary">{it.name}</Text> : null}
          {variants.length > 0 ? (
            <Badge count={variants.length} style={{ backgroundColor: '#52c41a' }} />
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              （无变体）
            </Text>
          )}
        </Space>
      )
      const children: DataNode[] = []
      // 各变体优先排在前面（运营心智里"具体变体"才是常规选择），
      // "不指定变体"作为兜底放最后并加警示色，避免被误点。
      for (const v of variants) {
        children.push({
          key: `model::${it.id}::${v.variant_code}`,
          title: (
            <Space size={6}>
              <Tag color="purple" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>
                {v.variant_code}
              </Tag>
              {v.material_name ? <Text>{v.material_name}</Text> : <Text type="secondary">（未配置替换物料）</Text>}
            </Space>
          ),
          isLeaf: true,
        })
      }
      if (allowModelWithoutVariant) {
        children.push({
          key: `model::${it.id}::__none__`,
          title: (
            <Tooltip title="不会写入 bound_variant_code，列表/详情只会显示模型级标签（KB8 转印包边垫类），不会出现 麻感冰丝(KB8-001) 这种二级标签。仅在该 SKU 真的不属于任何已配置变体时使用。">
              <Space size={4}>
                <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                  ⚠ 兜底
                </Tag>
                <Text type="warning">不指定变体（按模型基础线，不落变体编码）</Text>
              </Space>
            </Tooltip>
          ),
          isLeaf: true,
        })
      }
      return {
        key: `model-group::${it.id}`,
        title: headTitle,
        // 一级节点本身不可选（强制选择具体二级，避免运营漏选；
        // "不指定变体"这一行已经作为子节点单独提供）
        selectable: false,
        children,
      }
    })
}

const buildBundleTree = (items: BindingTargetItem[]): DataNode[] => {
  return items
    .filter((it) => it.kind === 'bundle')
    .map<DataNode>((it) => {
      const presets = it.presets ?? []
      const headTitle = (
        <Space size={6}>
          <Tag color="orange" style={{ marginInlineEnd: 0 }}>
            套装
          </Tag>
          <Text strong>{it.code}</Text>
          {it.name ? <Text type="secondary">{it.name}</Text> : null}
          {presets.length > 0 ? (
            <Badge count={presets.length} style={{ backgroundColor: '#fa8c16' }} />
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              （无 preset）
            </Text>
          )}
        </Space>
      )
      const children: DataNode[] = presets.map((p) => {
        // 中文 phrase 是真正的"运营心智"——优先大字号显示，token 作为副标签贴在末尾。
        // 当 phrase 为空（label === selector，纯字母 preset）时，仅显示 token。
        const hasPhrase = p.label && p.label !== p.selector
        // 天猫 SKU 模板生成时的真实落库 token：`{B|Z}-{bundle_code}{selector}`，
        // 与 targetSelectionToTmallSourceCode 拼装规则、生产侧 source_code 字段 100% 一致。
        // 显示完整 token（B-3U3PAA / Z-DB9EAG）让运营一眼对得上 SKU Master / 后台落库的字符串。
        const isForce = p.mode === 'force'
        const token = `${isForce ? 'Z' : 'B'}-${(it.code ?? '').toUpperCase()}${(p.selector ?? '').toUpperCase()}`
        return {
          key: `bundle::${it.id}::${p.selector}`,
          title: (
            <Space size={8} align="start" style={{ maxWidth: 680, lineHeight: 1.6 }} wrap>
              {hasPhrase ? (
                <Text style={{ wordBreak: 'break-all' }}>{p.label}</Text>
              ) : null}
              <Tooltip title={isForce ? '指定模式（Z-）：强制走该 preset 的 components，不参与 SKU 笛卡尔积' : '解析模式（B-）：参与 SKU 笛卡尔积'}>
                <Tag color={isForce ? 'magenta' : 'geekblue'} style={{ marginInlineEnd: 0, fontFamily: 'monospace', fontWeight: 600 }}>
                  {token}
                </Tag>
              </Tooltip>
            </Space>
          ),
          isLeaf: true,
        }
      })
      return {
        key: `bundle-group::${it.id}`,
        title: headTitle,
        // 一级节点不可选——业务上套装离开 preset 没有可执行 BOM
        selectable: false,
        children,
      }
    })
}

// 模块级稳定空数组：所有 fallback 共用同一个引用，避免 ?? [] 每次 render 都生成新引用，
// 进而引起 useMemo 失效 → useEffect 反复 setState → React #185 死循环。
const EMPTY_ITEMS: BindingTargetItem[] = Object.freeze([]) as unknown as BindingTargetItem[]
const EMPTY_KEYS: React.Key[] = Object.freeze([]) as unknown as React.Key[]

const treeKeyToSelection = (
  key: string,
  modelItems: BindingTargetItem[],
  bundleItems: BindingTargetItem[],
): TargetSelection | null => {
  const parts = key.split('::')
  if (parts.length !== 3) return null
  const [k, id, secondary] = parts
  if (k === 'model') {
    const item = modelItems.find((x) => x.id === id)
    if (!item) return null
    if (secondary === '__none__') {
      return {
        kind: 'model',
        model_id: item.id,
        model_code: item.code,
        model_name: item.name ?? null,
        published_version_id: item.published_version_id ?? null,
        version_label: item.version_label ?? null,
        variant_code: null,
        variant_label: null,
      }
    }
    const v = (item.variants ?? []).find((x) => x.variant_code === secondary) || null
    return {
      kind: 'model',
      model_id: item.id,
      model_code: item.code,
      model_name: item.name ?? null,
      published_version_id: item.published_version_id ?? null,
      version_label: item.version_label ?? null,
      variant_code: v?.variant_code ?? null,
      variant_label: v?.label ?? null,
    }
  }
  if (k === 'bundle') {
    const item = bundleItems.find((x) => x.id === id)
    if (!item) return null
    const p = (item.presets ?? []).find((x) => x.selector === secondary) || null
    return {
      kind: 'bundle',
      bundle_id: item.id,
      bundle_code: item.code,
      bundle_name: item.name ?? null,
      preset_selector: p?.selector ?? null,
      preset_label: p?.label ?? null,
      preset_mode: p?.mode ?? null,
    }
  }
  return null
}

const TargetPickerBrowserButton = ({
  value,
  onChange,
  buttonProps,
  modalTitle = '选择绑定目标',
  defaultTab = 'model',
  allowModelWithoutVariant = true,
  showSelectedOnButton = true,
  placeholder = '选择标的（标准模型 / 套装模板）',
}: TargetPickerBrowserButtonProps) => {
  const [open, setOpen] = useState(false)
  const initialTab: 'model' | 'bundle' = value?.kind === 'bundle' ? 'bundle' : defaultTab
  const [tab, setTab] = useState<'model' | 'bundle'>(initialTab)
  const [search, setSearch] = useState('')

  // 关掉再打开时把搜索清空，但保留 tab（贴近运营心智）
  useEffect(() => {
    if (open) {
      setSearch('')
      // 如果外部已选目标，自动切到对应 Tab，方便看到上下文
      if (value?.kind === 'model') setTab('model')
      else if (value?.kind === 'bundle') setTab('bundle')
    }
  }, [open, value])

  const modelQuery = useQuery({
    queryKey: ['binding-targets', 'browser', 'model', search],
    queryFn: () => fetchBindingTargets({ search: search || undefined, kind: 'model', limit: 200 }),
    enabled: open && tab === 'model',
    placeholderData: keepPreviousData,
  })

  const bundleQuery = useQuery({
    queryKey: ['binding-targets', 'browser', 'bundle', search],
    queryFn: () => fetchBindingTargets({ search: search || undefined, kind: 'bundle', limit: 200 }),
    enabled: open && tab === 'bundle',
    placeholderData: keepPreviousData,
  })

  // 注意：data?.items ?? [] 每次 render 都创建新空数组引用，会让下游 useMemo 重算、
  // useEffect 反复触发 setState→新数组→state 不等→re-render→死循环（React #185）。
  // 通过 useMemo 收敛 modelItems / bundleItems 的引用稳定性，问题就消失。
  const modelItems = useMemo(() => modelQuery.data?.items ?? EMPTY_ITEMS, [modelQuery.data])
  const bundleItems = useMemo(() => bundleQuery.data?.items ?? EMPTY_ITEMS, [bundleQuery.data])

  const modelTree = useMemo(
    () => buildModelTree(modelItems, allowModelWithoutVariant),
    [modelItems, allowModelWithoutVariant],
  )
  const bundleTree = useMemo(() => buildBundleTree(bundleItems), [bundleItems])

  const selectedKey = selectionToValueKey(value)

  // 默认展开策略 —— 受控 expandedKeys + 用户操作时回写：
  // - Modal 打开 / search 变化时按规则重新计算（有搜索词全展、无搜索词只展开已选所在分组）
  // - 用户手工点折叠/展开时通过 onExpand 回写 state，保持响应
  const [expandedKeysModel, setExpandedKeysModel] = useState<React.Key[]>([])
  const [expandedKeysBundle, setExpandedKeysBundle] = useState<React.Key[]>([])

  // 同样的死循环陷阱：setExpandedKeysModel([]) 每次都是新数组引用，React state 不等
  // → re-render → useEffect 又跑 → 又 set 新 [] → React #185。统一回退到 EMPTY_KEYS 单例。
  useEffect(() => {
    if (!open || tab !== 'model') return
    if (search) setExpandedKeysModel(modelTree.map((n) => n.key as string))
    else if (selectedKey?.startsWith('model::')) {
      const id = selectedKey.split('::')[1]
      setExpandedKeysModel([`model-group::${id}`])
    } else setExpandedKeysModel(EMPTY_KEYS)
  }, [open, tab, search, selectedKey, modelTree])

  useEffect(() => {
    if (!open || tab !== 'bundle') return
    if (search) setExpandedKeysBundle(bundleTree.map((n) => n.key as string))
    else if (selectedKey?.startsWith('bundle::')) {
      const id = selectedKey.split('::')[1]
      setExpandedKeysBundle([`bundle-group::${id}`])
    } else setExpandedKeysBundle(EMPTY_KEYS)
  }, [open, tab, search, selectedKey, bundleTree])

  const onTreeSelect = (selectedKeys: React.Key[]) => {
    const k = String(selectedKeys[0] ?? '')
    if (!k) return
    const sel = treeKeyToSelection(k, modelItems, bundleItems)
    if (!sel) return
    onChange?.(sel)
    setOpen(false)
  }

  const buttonLabel = useMemo(() => {
    if (!showSelectedOnButton || !value) return placeholder
    if (value.kind === 'model') {
      // 已选具体变体：显式把 variant_code 加到文本里，让运营在按钮上一眼看到
      // "我即将提交的就是 KB8-001 这个变体"，避免昨天 picker 误选"兜底"行的事故重演。
      if (value.variant_code) {
        const label = value.variant_label || value.variant_code
        return `${value.model_code}｜${label}`
      }
      // 兜底状态用 ⚠ 提示，与 picker 弹窗里的红字警告对齐。
      return `${value.model_code}（⚠ 不指定变体）`
    }
    return value.preset_label
      ? `${value.bundle_code}｜${value.preset_label}`
      : `${value.bundle_code}（未选 preset）`
  }, [value, placeholder, showSelectedOnButton])

  const isLoading = (tab === 'model' ? modelQuery.isFetching : bundleQuery.isFetching)
  const truncated = (tab === 'model' ? modelQuery.data?.truncated : bundleQuery.data?.truncated) ?? false

  return (
    <>
      <Button {...buttonProps} onClick={() => setOpen(true)}>
        {buttonLabel}
      </Button>
      <Modal
        open={open}
        title={modalTitle}
        onCancel={() => setOpen(false)}
        footer={
          <Space wrap>
            <Text type="secondary">当前选中：</Text>
            {renderTargetSelectionTags(value)}
            {value ? (
              <Button
                size="small"
                danger
                onClick={() => {
                  onChange?.(null)
                  setOpen(false)
                }}
              >
                清除
              </Button>
            ) : null}
            <Button onClick={() => setOpen(false)}>取消</Button>
          </Space>
        }
        width={780}
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Tabs
            activeKey={tab}
            onChange={(k) => setTab(k as 'model' | 'bundle')}
            items={[
              { key: 'model', label: '标准模型' },
              { key: 'bundle', label: '套装模板' },
            ]}
          />
          <Input.Search
            allowClear
            placeholder={
              tab === 'model'
                ? '搜索 模型编码/名称/变体编码/材质名'
                : '搜索 套装编码/名称/preset selector'
            }
            onSearch={(s) => setSearch(String(s || ''))}
            onChange={(e) => {
              const v = String(e.target.value || '')
              if (!v) setSearch('')
            }}
          />
          {truncated ? (
            <Text type="warning" style={{ fontSize: 12 }}>
              结果已截断为 200 条，请输入关键词进一步收敛。
            </Text>
          ) : null}
          <div style={{ maxHeight: 460, overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: 4, padding: 8 }}>
            {isLoading && (tab === 'model' ? modelTree : bundleTree).length === 0 ? (
              <div style={{ textAlign: 'center', padding: 32 }}>
                <Spin />
              </div>
            ) : (tab === 'model' ? modelTree : bundleTree).length === 0 ? (
              <Empty description={isLoading ? '加载中…' : '没有匹配的候选'} />
            ) : tab === 'model' ? (
              <Tree
                treeData={modelTree}
                selectedKeys={selectedKey?.startsWith('model::') ? [selectedKey] : []}
                expandedKeys={expandedKeysModel}
                onExpand={(keys) => setExpandedKeysModel(keys)}
                onSelect={onTreeSelect}
                blockNode
                showLine={{ showLeafIcon: false }}
              />
            ) : (
              <Tree
                treeData={bundleTree}
                selectedKeys={selectedKey?.startsWith('bundle::') ? [selectedKey] : []}
                expandedKeys={expandedKeysBundle}
                onExpand={(keys) => setExpandedKeysBundle(keys)}
                onSelect={onTreeSelect}
                blockNode
                showLine={{ showLeafIcon: false }}
              />
            )}
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            说明：标准模型一级下展开后<Text type="warning" strong>请优先选具体变体</Text>（KB8-001 仿羊绒、KB8-002 多尼尔…），
            列表/详情才会显示 <Text code>麻感冰丝(KB8-001)</Text> 这种二级标签；
            选到末尾那行 <Text type="warning">⚠ 兜底</Text> 只会按模型基础线计算、不落变体编码。
            套装模板必须选到 preset 才算完成选择。
          </Text>
        </Space>
      </Modal>
    </>
  )
}

export { TargetPickerBrowserButton }

/**
 * 工具：转换为筛选用扁平参数（业务方按需选用，不必所有字段都传给后端）。
 */
export const targetSelectionToFilters = (sel: TargetSelection | null | undefined) => {
  if (!sel) return {} as Record<string, string | undefined>
  if (sel.kind === 'model') {
    return {
      bound_target_kind: 'model' as const,
      bound_model_id: sel.model_id,
      bound_model_code: sel.model_code,
      bound_variant_code: sel.variant_code ?? undefined,
    }
  }
  return {
    bound_target_kind: 'bundle' as const,
    bound_bundle_id: sel.bundle_id,
    bound_bundle_code: sel.bundle_code,
    bound_preset_selector: sel.preset_selector ?? undefined,
  }
}

/**
 * 工具：转换为旧 `BoundTargetPickerFilters` 兼容字段，用于 SalesInsights / ShipmentLedger / AfterSalesInsights
 * 这些已存在的分析页 — 后端 query 还在按 `bound_model_code / bundle_template_code / bundle_preset_selector` 接收。
 *
 * 替换原 BoundTargetPicker 时，业务页**只需**改 UI 与状态类型，filters 消费侧（拼到查询体里）零改动。
 *
 * 字段对照：
 *   model:  { bound_target_kind: 'model',  bound_model_code, bound_version_label }
 *   bundle: { bound_target_kind: 'bundle', bundle_template_code, bundle_preset_selector }
 *
 * 备注：bound_version_label 来自 selection.version_label（当前 published 版本号），保留是为兼容
 * ShipmentLedger 历史里"按版本号筛选"的能力；新选择器只允许 published 版本，绝大部分场景用不上。
 */
export type BoundTargetCompatFilters = {
  bound_target_kind?: 'model' | 'bundle'
  bound_model_code?: string
  bound_version_label?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
}

export const targetSelectionToBoundFilters = (
  sel: TargetSelection | null | undefined,
): BoundTargetCompatFilters => {
  if (!sel) return {}
  if (sel.kind === 'model') {
    return {
      bound_target_kind: 'model',
      bound_model_code: sel.model_code || undefined,
      bound_version_label: sel.version_label || undefined,
    }
  }
  return {
    bound_target_kind: 'bundle',
    bundle_template_code: sel.bundle_code || undefined,
    bundle_preset_selector: sel.preset_selector || undefined,
  }
}

/**
 * 工具：把 selection 转为天猫 SKU 模板生成器使用的"商家编码锚点 token 字符串"：
 *   - 标准模型 → `${model_code}`（如 "KB8"）。**变体维度被忽略**：天猫 token 体系只到模型一级，
 *     选了 KB8-001 与 KB8 等价；如运营要按变体生成，需要扩展 token 体系。
 *   - 套装模板 → `${preset_mode === 'force' ? 'Z' : 'B'}-${bundle_code}${preset_selector}`
 *     （如 "B-3U3PAA" 或 "Z-3U3PAA"）。preset 必须有 selector + mode，否则返回 ''。
 */
export const targetSelectionToTmallSourceCode = (sel: TargetSelection | null | undefined): string => {
  if (!sel) return ''
  if (sel.kind === 'model') return (sel.model_code || '').trim().toUpperCase()
  const tpl = (sel.bundle_code || '').trim().toUpperCase()
  const sel2 = (sel.preset_selector || '').trim().toUpperCase()
  if (!tpl || !sel2) return ''
  const prefix = sel.preset_mode === 'force' ? 'Z' : 'B'
  return `${prefix}-${tpl}${sel2}`
}

/**
 * 工具：把"商家编码锚点 token 字符串"反向解析为 selection 描述（用于回显已存的 token 值）。
 *
 * 业务约定（实测核对，2026-05 数据）：
 *   - 套装 token 形态：`{B|Z}-{bundle_code}{selector}`，selector **严格 2 个大写字母**（AA/AB/…）；
 *     bundle_code 长 4–6 字符，可能以字母结尾（DB9E、3U3P、THRH2W、X794ZS）。
 *     正则 `^([BZ])-([A-Z0-9]{2,})([A-Z]{2})$`：第二组贪婪匹配，第三组严格 2 字母 → 唯一切分。
 *     例：`B-DB9EAE` → code=DB9E, selector=AE；`Z-3U3PAG` → code=3U3P, selector=AG。
 *   - 模型 token：直接 model_code（如 `KB8`、`MODEL-POSTER-A1`），不带 `B-/Z-` 前缀。
 *   - **歧义**：数据库里 `B-DB9EAE` / `B-DB9EAK` 同时也是真实存在的 standard model（早期工作流
 *     把套装 token 当 model code 落库）。本函数靠纯字符串无法区分，必须**配合 candidates 查表**。
 *
 * 调用规约：
 *   - 若传 `candidates`，先按 model_code 精确命中真实 standard model（优先级最高，因为表里
 *     真有记录就该按 model 走），再按 bundle_code + preset_selector 精确命中 bundle preset。
 *     精确命中能填上 model_id / bundle_id / preset_label / preset_mode / variant 等完整信息，
 *     回显效果最佳。
 *   - 都没命中（或不传 candidates）时，按上面的正则做"形态推断"——bundle_id / preset_label
 *     为空，用户重新打开 Modal 选时会刷新完整 selection。
 */
type TmallTokenCandidates = {
  models?: BindingTargetItem[] | null
  bundles?: BindingTargetItem[] | null
}

export const tmallSourceCodeToTargetSelection = (
  token: string | undefined | null,
  candidates?: TmallTokenCandidates,
): TargetSelection | null => {
  const t = String(token ?? '').trim().toUpperCase()
  if (!t) return null

  // ---- 1) 优先：在真实 standard model 表里找 model_code 完全等于 token 的项 ----
  // 这覆盖了"早期把 B-DB9EAE 当 model code 落库"的历史数据与"KB8 / MODEL-POSTER-A1"等正常 case。
  if (candidates?.models?.length) {
    const hit = candidates.models.find(
      (m) => String(m.code ?? '').trim().toUpperCase() === t,
    )
    if (hit) {
      return {
        kind: 'model',
        model_id: hit.id,
        model_code: hit.code,
        model_name: hit.name ?? null,
        published_version_id: hit.published_version_id ?? null,
        version_label: hit.version_label ?? null,
        variant_code: null,
        variant_label: null,
      }
    }
  }

  // ---- 2) 再试 bundle 反解 ----
  // selector 严格 2 字母；bundle_code 贪婪吃掉中间剩下的字母数字。
  const m = t.match(/^([BZ])-([A-Z0-9]{2,})([A-Z]{2})$/)
  if (m) {
    const [, prefix, code, selector] = m
    const mode: 'force' | 'parse' = prefix === 'Z' ? 'force' : 'parse'

    // 在 bundle 列表里找精确匹配（bundle_code + preset.selector 双键），命中则填完整信息
    if (candidates?.bundles?.length) {
      const bundle = candidates.bundles.find(
        (b) => String(b.code ?? '').trim().toUpperCase() === code,
      )
      if (bundle) {
        const preset = (bundle.presets ?? []).find(
          (p) => String(p.selector ?? '').trim().toUpperCase() === selector,
        )
        if (preset) {
          return {
            kind: 'bundle',
            bundle_id: bundle.id,
            bundle_code: bundle.code,
            bundle_name: bundle.name ?? null,
            preset_selector: preset.selector,
            preset_label: preset.label,
            preset_mode: preset.mode,
          }
        }
      }
    }

    // 没在 bundle 表精确命中 → 形态回退（适合 modal 一时未拉到数据 / token 是脏数据的情况）
    return {
      kind: 'bundle',
      bundle_id: '',
      bundle_code: code,
      bundle_name: null,
      preset_selector: selector,
      preset_label: null,
      preset_mode: mode,
    }
  }

  // ---- 3) 兜底：当作 model_code 形态 ----
  return {
    kind: 'model',
    model_id: '',
    model_code: t,
    model_name: null,
    published_version_id: null,
    version_label: null,
    variant_code: null,
    variant_label: null,
  }
}

/**
 * 工具：把 selection 渲染成短字符串（用于 ShipmentLedger 折叠时的 Tag 文案）。
 */
export const targetSelectionToShortLabel = (sel: TargetSelection | null | undefined): string => {
  if (!sel) return ''
  if (sel.kind === 'model') {
    const code = sel.model_code || ''
    const variant = sel.variant_code ? `｜${sel.variant_label || sel.variant_code}` : ''
    const ver = sel.version_label ? ` (${sel.version_label})` : ''
    return `模型：${code}${variant}${ver}`
  }
  const tpl = sel.bundle_code || ''
  const sel2 = sel.preset_selector ? `｜${sel.preset_label || sel.preset_selector}` : ''
  return `套装：${tpl}${sel2}`
}
