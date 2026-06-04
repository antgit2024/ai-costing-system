import Pinyin from 'tiny-pinyin'

const slugify = (raw: string): string => {
  const s = String(raw ?? '').trim().toLowerCase()
  if (!s) return ''
  // keep a-z0-9 and underscore; collapse other chars to underscore
  return s
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_')
}

/**
 * Convert a Chinese label into a stable slot code.
 * - If contains non-Chinese ASCII letters/numbers, it will be slugified directly.
 * - Otherwise, convert Chinese to pinyin without tone/spaces (via tiny-pinyin) then slugify.
 */
export const toPinyinCode = (label: string): string => {
  const input = String(label ?? '').trim()
  if (!input) return ''

  // If user already typed ascii-ish code, don't over-convert it.
  const hasAscii = /[a-zA-Z0-9]/.test(input)
  if (hasAscii) return slugify(input)

  try {
    if ((Pinyin as any)?.isSupported?.()) {
      const converted = (Pinyin as any).convertToPinyin(input, '', '')
      return slugify(String(converted ?? ''))
    }
  } catch {
    // ignore
  }
  return slugify(input)
}


