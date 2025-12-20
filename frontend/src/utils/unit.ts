export type CanonicalUnit = '平米' | '米' | '个' | '套'

/**
 * 前端统一单位口径（展示/比较用）。
 * 后端已做落库归一化，但前端仍需兼容历史值与外部来源的同义词。
 */
export function normalizeUnit(value?: string | null): string {
  if (!value) return ''
  const v = String(value).trim().replace(/\s+/g, '')
  if (!v) return ''

  // Area
  if (['平米', '㎡', '平方', '平方米', 'm²', 'M2', 'm2', '米²', '米2'].includes(v)) return '平米'

  // Length
  if (['米', 'm', 'M'].includes(v)) return '米'

  // Count
  if (['个', 'pcs', 'PCS', 'piece', 'Piece'].includes(v)) return '个'

  // Set
  if (['套', 'set', 'SET'].includes(v)) return '套'

  return v
}







