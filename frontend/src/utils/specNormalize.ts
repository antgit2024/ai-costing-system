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

// 半角方括号注释 [xxx] — 天猫"颜色分类"经常写成 <款号>[<颜色名>], 如 J26051102A[夏野漫花].
// 档案规格里只有款号 → 必须剥掉 [...] 才能正确判等价.
// 保留全角【】(常出现于规格描述, 如 "【适用于0.6~0.8米方桌】") 与圆括号 () (材质组合).
const BRACKET_ANNOTATION_PATTERN = /\[[^\[\]\n]{1,40}\]/g

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
  // 剥半角方括号注释 (颜色名等天猫附加注释)
  t = t.replace(BRACKET_ANNOTATION_PATTERN, '')
  // 分隔符统一
  t = t.replace(TOKEN_SPLIT_PATTERN, ';').replace(/;{2,}/g, ';')
  t = t.replace(/\s+/g, ' ').trim()
  // 修剪首尾分号 / 空格
  while (t.startsWith(';') || t.startsWith(' ')) t = t.slice(1)
  while (t.endsWith(';') || t.endsWith(' ')) t = t.slice(0, -1)
  return t
}

/**
 * 比较友好版归一化 — 在 normalizeSpecText 之上把所有空格也视为分隔符.
 *
 * 适用场景: 档案规格 vs 最后发货规格 的等价性判定. 不影响 parser/hashing.
 *
 * 举例:
 *   档案 "Q25120402C皮革桌垫;80*160"     → "Q25120402C皮革桌垫;80*160"
 *   发货 "Q25120402C皮革桌垫 80*160"     → "Q25120402C皮革桌垫;80*160"
 *   一致 ✓
 *
 * 与后端 `spec_parser_service.normalize_for_compare` 保持同语义.
 */
export const normalizeSpecForCompare = (input: unknown): string => {
  let t = normalizeSpecText(input)
  if (!t) return ''
  t = t.replace(/\s+/g, ';').replace(/;{2,}/g, ';')
  return t.replace(/^;+|;+$/g, '')
}

/**
 * 显示用的轻量美化 — 只剥中文属性标签前缀, 其他原貌保留.
 *
 * 用途: 列表/抽屉里展示"最后发货规格"等天猫订单字段时, 把
 *   "颜色分类:xxx;规格:yyy;组合形式:zzz;尺寸:..."
 * 这种刺眼的标签前缀剥掉, 看起来与"商品规格(网店)"一致.
 *
 * 与 normalizeSpecText / normalizeSpecForCompare 不同:
 *   - 后两者是给比对/解析用的, 会做激进归一化 (全角→半角 / 剥 [] / 空格→分号 / 分隔符统一为 ;)
 *   - 本函数只剥前缀, 视觉上最接近原文, 给"看"用的
 */
export const prettifyDisplaySpec = (input: unknown): string => {
  const raw = String(input ?? '').trim()
  if (!raw) return ''
  // 跟 ATTR_LABEL_PREFIX_PATTERN 同规则, 但单独构造一份: 不依赖前面已经做过其他 normalize
  // (因为本函数要保留原文风格, 不替换全角/半角)
  const RE = new RegExp(
    `(^|[${TOKEN_SEP_CHARS}])\\s*([^${TOKEN_SEP_CHARS}:：]{1,40}[\\u4e00-\\u9fff][^${TOKEN_SEP_CHARS}:：]{0,40})\\s*[：:]\\s*`,
    'g',
  )
  let t = raw.replace(RE, '$1')
  // 修剪首尾遗留的分隔符 / 空白 (可能因为剥前缀后行首多出来)
  t = t.replace(/^[;；\s]+/, '').replace(/[;；\s]+$/, '')
  return t
}

/** 等价比较 — normalize_for_compare 后字面相等 (大小写敏感, 因为有 KB8-001 这种码) */
export const isSpecTextEquivalent = (a: unknown, b: unknown): boolean => {
  const na = normalizeSpecForCompare(a)
  const nb = normalizeSpecForCompare(b)
  if (!na && !nb) return true
  if (!na || !nb) return false
  return na === nb
}
