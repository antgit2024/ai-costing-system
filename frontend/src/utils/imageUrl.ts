/**
 * 商品图片 URL 规范化工具
 *
 * 解决三个常见显示失效问题：
 * 1. **HTTPS / HTTP 混合内容**：站点是 https, 但 ERP 存的图是 http://img.alicdn.com/...
 *    浏览器会拦截 (Mixed Content blocked) 显示「失效」。统一改写为 https://
 * 2. **原图超大 / 加载慢 / 失败率高**：alicdn 默认是原图 (1MB+),
 *    给 alicdn URL 末尾追加 `_<size>x<size>.jpg` 让 CDN 返回缩略, 命中率更高、加载更快、更耐用。
 * 3. **多协议 / 多 CDN 兼容**：京东 (360buyimg), 小红书 (xiaohongshu) 等也走相同的协议升级。
 *
 * 注意：本函数只做"无副作用"的 URL 改写, 不会触发网络请求。
 * 真正失效仍需 fallback 到「无图」占位 (Antd <Image fallback>)。
 *
 * 后续可加：
 * - 后端图片代理 (规避 token 过期 / 偶发 404)
 * - 异步抓取本地存储 (永不失效但成本高)
 */

/** 阿里 CDN host 列表 (alicdn / aliimg / mm.taobaocdn 等都属同源 CDN). */
const ALICDN_HOSTS = new Set([
  'img.alicdn.com',
  'gw.alicdn.com',
  'aeis.alicdn.com',
  'gmd.alicdn.com',
  'g-search1.alicdn.com',
  'g-search2.alicdn.com',
  'g-search3.alicdn.com',
])

/** 京东 CDN host 列表. */
const JD_HOSTS = new Set([
  'img10.360buyimg.com',
  'img11.360buyimg.com',
  'img12.360buyimg.com',
  'img13.360buyimg.com',
  'img14.360buyimg.com',
  'm.360buyimg.com',
])

interface NormalizeOptions {
  /** 缩略边长 (px). 默认 220. 仅对 alicdn 有效. */
  size?: number
}

/**
 * 把 ERP 存的商品图 URL 改写为浏览器更稳定加载的版本.
 *
 * @example
 *   normalizeImageUrl('http://img.alicdn.com/bao/uploaded/i3/.../O1CN01...item_pic.jpg')
 *   // → 'https://img.alicdn.com/bao/uploaded/i3/.../O1CN01...item_pic.jpg_220x220.jpg'
 */
export const normalizeImageUrl = (
  raw: string | null | undefined,
  options: NormalizeOptions = {},
): string => {
  if (!raw) return ''
  let url = String(raw).trim()
  if (!url) return ''

  // 1) 协议补全: //img.alicdn.com/... → https://img.alicdn.com/...
  if (url.startsWith('//')) {
    url = 'https:' + url
  }
  // 2) http → https (针对所有 host, 不止阿里)
  if (url.startsWith('http://')) {
    url = 'https://' + url.slice('http://'.length)
  }

  let host = ''
  try {
    host = new URL(url).host.toLowerCase()
  } catch {
    return url // 不是合法 URL, 原样返回
  }

  // 3) alicdn 缩略参数
  // 文档: https://img.alicdn.com/<path>.jpg → https://img.alicdn.com/<path>.jpg_<size>x<size>.jpg
  // 已有缩略参数 (`_xxx.jpg` 在末尾) 就不再叠加, 否则会变成 .jpg_50x50.jpg_220x220.jpg
  if (ALICDN_HOSTS.has(host)) {
    const size = options.size ?? 220
    // 已有缩略参数 (.jpg_NNNxNNN.jpg / _summ.jpg / _.webp 等) 跳过
    if (!/_\d+x\d+\.(jpg|jpeg|png|webp)$/i.test(url) && /\.(jpg|jpeg|png|webp)$/i.test(url)) {
      url = `${url}_${size}x${size}.jpg`
    }
  }

  // 4) 京东 CDN: /n0/ 是原图; 改成 /s220x220_jfs/ 拿缩略.
  // 例: img10.360buyimg.com/n0/jfs/t1/.../xxx.jpg → img10.360buyimg.com/n12/s220x220_jfs/...
  if (JD_HOSTS.has(host) && options.size !== 0) {
    const size = options.size ?? 220
    url = url.replace(/\/n\d+\/jfs\//, `/n12/s${size}x${size}_jfs/`)
  }

  return url
}

/**
 * 从一行 SkuMaster 拿到首选展示图 URL (已规范化).
 * 优先级: product_image > spec_image. 都为空返回 ''.
 */
export const pickRowImageUrl = (
  imagesJson: Record<string, unknown> | null | undefined,
  size: number = 220,
): string => {
  const obj = imagesJson || {}
  const candidate =
    (obj.product_image as string | undefined) || (obj.spec_image as string | undefined) || ''
  return normalizeImageUrl(candidate, { size })
}

/** 透明 1×1 SVG, 用作 <Image fallback> 防止 fallback 自身又触发新的网络请求. */
export const IMAGE_FALLBACK_SVG =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">
      <rect width="44" height="44" fill="#f5f5f5"/>
      <text x="22" y="20" font-size="9" text-anchor="middle" fill="#bbb" font-family="sans-serif">图片</text>
      <text x="22" y="30" font-size="9" text-anchor="middle" fill="#bbb" font-family="sans-serif">失效</text>
    </svg>`,
  )
