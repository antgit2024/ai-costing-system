// @vitest-environment node
//
// 纯函数测试 —— 不需要 jsdom，避开仓库里 jsdom/parse5 ESM 兼容性的环境问题。
import { describe, expect, it } from 'vitest'

import {
  targetSelectionToTmallSourceCode,
  tmallSourceCodeToTargetSelection,
  type TargetSelection,
} from './TargetPicker'
import type { BindingTargetItem } from '@/services/planner'

// 模拟实际数据结构（精简版，仅含 helper 用到的字段）
const buildModelItem = (overrides: Partial<BindingTargetItem>): BindingTargetItem =>
  ({
    kind: 'model',
    id: overrides.id ?? 'mid-default',
    code: overrides.code ?? 'KB8',
    name: overrides.name ?? '通用包边垫类',
    published_version_id: overrides.published_version_id ?? 'pvid-1',
    version_label: overrides.version_label ?? '100×100×1',
    variants: overrides.variants ?? [],
    presets: [],
  }) as unknown as BindingTargetItem

const buildBundleItem = (
  overrides: Partial<BindingTargetItem> & { presets: BindingTargetItem['presets'] },
): BindingTargetItem =>
  ({
    kind: 'bundle',
    id: overrides.id ?? 'bid-default',
    code: overrides.code ?? '3U3P',
    name: overrides.name ?? '印花抱枕',
    published_version_id: null,
    version_label: null,
    variants: [],
    presets: overrides.presets,
  }) as unknown as BindingTargetItem

describe('targetSelectionToTmallSourceCode (正向)', () => {
  it('null/空 → 空串', () => {
    expect(targetSelectionToTmallSourceCode(null)).toBe('')
    expect(targetSelectionToTmallSourceCode(undefined)).toBe('')
  })

  it('model selection → model_code（变体维度被忽略，因为天猫 token 只到模型一级）', () => {
    const sel: TargetSelection = {
      kind: 'model',
      model_id: 'mid-1',
      model_code: 'KB8',
      model_name: '通用包边垫类',
      published_version_id: 'pv-1',
      version_label: '100×100×1',
      variant_code: 'KB8-001', // 即使选了变体
      variant_label: '仿羊绒(KB8-001)',
    }
    expect(targetSelectionToTmallSourceCode(sel)).toBe('KB8')
  })

  it('bundle parse 模式 → B-{code}{selector}', () => {
    const sel: TargetSelection = {
      kind: 'bundle',
      bundle_id: 'bid-1',
      bundle_code: '3U3P',
      bundle_name: '印花抱枕',
      preset_selector: 'AD',
      preset_label: '[{黄金绒}]45*45*3',
      preset_mode: 'parse',
    }
    expect(targetSelectionToTmallSourceCode(sel)).toBe('B-3U3PAD')
  })

  it('bundle force 模式 → Z-{code}{selector}', () => {
    const sel: TargetSelection = {
      kind: 'bundle',
      bundle_id: 'bid-1',
      bundle_code: 'DB9E',
      bundle_name: '印花抱枕（26前历史）',
      preset_selector: 'AG',
      preset_label: '雪尼尔抱枕双面印花45X45+羽丝绒枕芯',
      preset_mode: 'force',
    }
    expect(targetSelectionToTmallSourceCode(sel)).toBe('Z-DB9EAG')
  })

  it('bundle 缺 selector → 空串（避免生成无效 token）', () => {
    const sel: TargetSelection = {
      kind: 'bundle',
      bundle_id: 'bid-1',
      bundle_code: '3U3P',
      bundle_name: null,
      preset_selector: null,
      preset_label: null,
      preset_mode: 'parse',
    }
    expect(targetSelectionToTmallSourceCode(sel)).toBe('')
  })
})

describe('tmallSourceCodeToTargetSelection (反向, 无 candidates)', () => {
  it('空 → null', () => {
    expect(tmallSourceCodeToTargetSelection('')).toBeNull()
    expect(tmallSourceCodeToTargetSelection(null)).toBeNull()
  })

  it('B-DB9EAE → bundle DB9E + AE（不应切成 DB9 + EAE）', () => {
    const sel = tmallSourceCodeToTargetSelection('B-DB9EAE')
    expect(sel).toMatchObject({
      kind: 'bundle',
      bundle_code: 'DB9E',
      preset_selector: 'AE',
      preset_mode: 'parse',
    })
  })

  it('Z-DB9EAG → bundle DB9E + AG, force', () => {
    const sel = tmallSourceCodeToTargetSelection('Z-DB9EAG')
    expect(sel).toMatchObject({
      kind: 'bundle',
      bundle_code: 'DB9E',
      preset_selector: 'AG',
      preset_mode: 'force',
    })
  })

  it('B-3U3PAA → bundle 3U3P + AA（bundle code 末尾是字母 P）', () => {
    const sel = tmallSourceCodeToTargetSelection('B-3U3PAA')
    expect(sel).toMatchObject({ kind: 'bundle', bundle_code: '3U3P', preset_selector: 'AA' })
  })

  it('B-THRH2WAA / B-X794ZSAA → 6 字符 bundle code 也能正确切', () => {
    expect(tmallSourceCodeToTargetSelection('B-THRH2WAA')).toMatchObject({
      kind: 'bundle',
      bundle_code: 'THRH2W',
      preset_selector: 'AA',
    })
    expect(tmallSourceCodeToTargetSelection('B-X794ZSAA')).toMatchObject({
      kind: 'bundle',
      bundle_code: 'X794ZS',
      preset_selector: 'AA',
    })
  })

  it('KB8 → model（无前缀）', () => {
    const sel = tmallSourceCodeToTargetSelection('KB8')
    expect(sel).toMatchObject({ kind: 'model', model_code: 'KB8', model_id: '' })
  })

  it('MODEL-POSTER-A1（含 dash 但不以 B-/Z- 开头）→ model', () => {
    const sel = tmallSourceCodeToTargetSelection('MODEL-POSTER-A1')
    expect(sel).toMatchObject({ kind: 'model', model_code: 'MODEL-POSTER-A1' })
  })

  it('小写自动归一化为大写', () => {
    expect(tmallSourceCodeToTargetSelection('b-db9eae')).toMatchObject({
      kind: 'bundle',
      bundle_code: 'DB9E',
      preset_selector: 'AE',
    })
  })
})

describe('tmallSourceCodeToTargetSelection (带 candidates 精确匹配)', () => {
  const models = [
    buildModelItem({ id: 'm-kb8', code: 'KB8', name: '通用包边垫类' }),
    buildModelItem({ id: 'm-bdb9eae', code: 'B-DB9EAE', name: '历史保留：单品 26 前历史' }),
  ]
  const bundles = [
    buildBundleItem({
      id: 'b-3u3p',
      code: '3U3P',
      name: '印花抱枕',
      presets: [
        { selector: 'AA', label: '雪尼尔抱枕双面印花45X45+PP棉枕芯', mode: 'force' },
        { selector: 'AD', label: '[{黄金绒}{雪尼尔}]45*45*3 + ...', mode: 'parse' },
      ] as any,
    }),
    buildBundleItem({
      id: 'b-db9e',
      code: 'DB9E',
      name: '印花抱枕（26前历史）',
      presets: [
        { selector: 'AE', label: '[{}{毛球}][{黄金绒}{雪尼尔}]0*0*0', mode: 'parse' },
        { selector: 'AG', label: '雪尼尔抱枕双面印花45X45+羽丝绒枕芯', mode: 'force' },
      ] as any,
    }),
  ]

  it('B-DB9EAE 精确命中 standard model 表 → 走 model 路径（不被误判成 bundle DB9E+AE）', () => {
    const sel = tmallSourceCodeToTargetSelection('B-DB9EAE', { models, bundles })
    expect(sel).toMatchObject({
      kind: 'model',
      model_id: 'm-bdb9eae',
      model_code: 'B-DB9EAE',
      model_name: '历史保留：单品 26 前历史',
    })
  })

  it('Z-DB9EAG 在 model 表无精确命中 → 走 bundle 表精确命中（含 preset_label / preset_mode）', () => {
    const sel = tmallSourceCodeToTargetSelection('Z-DB9EAG', { models, bundles })
    expect(sel).toMatchObject({
      kind: 'bundle',
      bundle_id: 'b-db9e',
      bundle_code: 'DB9E',
      preset_selector: 'AG',
      preset_label: '雪尼尔抱枕双面印花45X45+羽丝绒枕芯',
      preset_mode: 'force',
    })
  })

  it('B-3U3PAA → bundle 表精确命中', () => {
    const sel = tmallSourceCodeToTargetSelection('B-3U3PAA', { models, bundles })
    expect(sel).toMatchObject({
      kind: 'bundle',
      bundle_id: 'b-3u3p',
      bundle_code: '3U3P',
      preset_selector: 'AA',
      preset_label: '雪尼尔抱枕双面印花45X45+PP棉枕芯',
      preset_mode: 'force',
    })
  })

  it('KB8 → model 表精确命中（model_id / version_label 完整回填）', () => {
    const sel = tmallSourceCodeToTargetSelection('KB8', { models, bundles })
    expect(sel).toMatchObject({
      kind: 'model',
      model_id: 'm-kb8',
      model_code: 'KB8',
      model_name: '通用包边垫类',
    })
  })

  it('B-XYZQAA bundle 表无对应 → 形态回退（bundle_id 为空、preset_label null）', () => {
    const sel = tmallSourceCodeToTargetSelection('B-XYZQAA', { models, bundles })
    expect(sel).toMatchObject({
      kind: 'bundle',
      bundle_id: '',
      bundle_code: 'XYZQ',
      preset_selector: 'AA',
      preset_label: null,
      preset_mode: 'parse',
    })
  })
})

describe('round-trip 一致性（拼装 → 反解 → 等价）', () => {
  it.each([
    ['B-3U3PAA', '3U3P', 'AA', 'parse'] as const,
    ['B-DB9EAE', 'DB9E', 'AE', 'parse'] as const,
    ['Z-DB9EAG', 'DB9E', 'AG', 'force'] as const,
    ['B-THRH2WAA', 'THRH2W', 'AA', 'parse'] as const,
    ['B-X794ZSAA', 'X794ZS', 'AA', 'parse'] as const,
  ])('%s → 反解 → 拼装 → 同字符串', (token, code, selector, mode) => {
    const sel = tmallSourceCodeToTargetSelection(token)
    expect(sel).toMatchObject({ kind: 'bundle', bundle_code: code, preset_selector: selector, preset_mode: mode })
    expect(targetSelectionToTmallSourceCode(sel)).toBe(token)
  })
})
