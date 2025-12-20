import type { CalculationMethod } from '@/types/planner'

export const CALCULATION_METHOD_OPTIONS: Array<{
  label: string
  value: CalculationMethod
  unit: string
}> = [
  { label: '面积', value: 'area', unit: '㎡' },
  { label: '周长', value: 'perimeter', unit: 'm' },
  { label: '数量', value: 'count', unit: '个' },
  { label: '宽度', value: 'width', unit: 'm' },
  { label: '高度', value: 'height', unit: 'm' },
]

export const BOM_UNIT_SELECT_OPTIONS = [
  { label: '平米', value: '㎡' },
  { label: '米', value: 'm' },
  { label: '个', value: '个' },
]

export const getCalculationMethodLabel = (value?: string | null) => {
  const option = CALCULATION_METHOD_OPTIONS.find((item) => item.value === value)
  return option?.label ?? value ?? '-'
}

export const getDefaultUnitByCalculationMethod = (value?: string | null) => {
  const option = CALCULATION_METHOD_OPTIONS.find((item) => item.value === value)
  return option?.unit
}

