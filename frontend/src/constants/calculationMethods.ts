import type { CalculationMethod } from '@/types/planner'

export const CALCULATION_METHOD_OPTIONS: Array<{
  label: string
  value: CalculationMethod
  unit: string
}> = [
  // IMPORTANT: value 必须是规范值（不要用 ㎡/m 作为 value），避免在各处出现单位不统一/回归。
  { label: '面积', value: 'area', unit: '平米' },
  { label: '周长', value: 'perimeter', unit: '米' },
  { label: '数量', value: 'count', unit: '个' },
  { label: '宽度', value: 'width', unit: '米' },
  { label: '高度', value: 'height', unit: '米' },
]

export const BOM_UNIT_SELECT_OPTIONS = [
  { label: '平米', value: '平米' },
  { label: '米', value: '米' },
  { label: '个', value: '个' },
  { label: '套', value: '套' },
]

export const getCalculationMethodLabel = (value?: string | null) => {
  const option = CALCULATION_METHOD_OPTIONS.find((item) => item.value === value)
  return option?.label ?? value ?? '-'
}

export const getDefaultUnitByCalculationMethod = (value?: string | null) => {
  const option = CALCULATION_METHOD_OPTIONS.find((item) => item.value === value)
  return option?.unit
}

