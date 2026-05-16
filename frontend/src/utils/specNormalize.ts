/**
 * 规格文本归一化 — 前端版本, 与后端 `spec_parser_service.normalize_tx_spec_text` 保持同语义.
 *
 * 用途
 * ----
 * 商品档案列表里, 前端要判断 "档案规格 (spec_text) vs 最后发货规格 (last_shipment_spec_text)"
 * 是否真正不同 (用于决定是否显示红色 "规格不一致" 标签). 仅做标点空格统一是不够的,
 * 必须把天猫订单字段里常见的属性标签前缀 (颜色分类:/规格:/组合形式: …) 也剥掉, 否则会
 * 把语义上完全等价的两条规格误报为不一致.
 *
 * 同语义的后端正则:
 *   ATTR_LABEL_PREFIX_PATTERN = re.compile(
 *       r"(^|[;\n\r,，/\\\+|、])\s*(?P<label>[^;\n\r,，/\\\+|、:：]{1,40}[\u4e00-\u9fff][^;\n\r,，/\\\+|、:：]{0,40})\s*[：:]\s*"
 *   )
 *
 * 任何对此函数的修改, 都应该同步检查后端 `backend/src/planner/services/spec_parser_service.py`
 * 的 `normalize_tx_spec_text`, 保证前后端结果一致 — 否则列表会出现 UI 误报.
 */

const TOKEN_SEP_CHARS = ';\\n\\r,，/\\\\+|、'

// 中文属性标签前缀剥离 — 仅剥"含至少一个中文字符 + 紧跟 : / ：" 的标签, 避免误伤
// 内部 token 如 "BUNDLE:DB9EAE"
const ATTR_LABEL_PREFIX_PATTERN = new RegExp(
  `(^|[${TOKEN_SEP_CHARS}])\\s*([^${TOKEN_SEP_CHARS}:：]{1,40}[\\u4e00-\\u9fff][^${TOKEN_SEP_CHARS}:：]{0,40})\\s*[：:]\\s*`,
  'g',
)

const TOKEN_SPLIT_PATTERN = new RegExp(`[${TOKEN_SEP_CHARS}]`, 'g')

/**
 * 把规格文本归一化为可比对/可哈希的形式:
 *   1) 统一全角标点 → 半角
 *   2) 剥掉天猫属性标签前缀 (颜色分类:/规格:/组合形式: …)
 *   3) 把所有分隔符统一为 ';' 并去重连续分号
 *   4) 折叠空白, 修剪首尾分隔符
 */
export const normalizeSpecText = (input: unknown): string => {
  const raw = String(input ?? '').trim()
  if (!raw) return ''
  let t = raw
    .replace(/；/g, ';')
    .replace(/：/g, ':')
    .replace(/，/g, ',')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
  // 剥中文属性标签前缀, 保留前导分隔符
  t = t.replace(ATTR_LABEL_PREFIX_PATTERN, '$1')
  // 分隔符统一
  t = t.replace(TOKEN_SPLIT_PATTERN, ';').replace(/;{2,}/g, ';')
  t = t.replace(/\s+/g, ' ').trim()
  // 修剪首尾分号 / 空格
  while (t.startsWith(';') || t.startsWith(' ')) t = t.slice(1)
  while (t.endsWith(';') || t.endsWith(' ')) t = t.slice(0, -1)
  return t
}

/** 等价比较 — 归一化后字面相等 (大小写敏感, 因为有 KB8-001 这种码) */
export const isSpecTextEquivalent = (a: unknown, b: unknown): boolean => {
  const na = normalizeSpecText(a)
  const nb = normalizeSpecText(b)
  if (!na && !nb) return true
  if (!na || !nb) return false
  return na === nb
}
