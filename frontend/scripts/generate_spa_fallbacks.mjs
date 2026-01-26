import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const PROJECT_ROOT = path.resolve(__dirname, '..')
const DIST_DIR = path.join(PROJECT_ROOT, 'dist')
const APP_FILE = path.join(PROJECT_ROOT, 'src', 'App.tsx')

const readText = async (p) => {
  return await fs.readFile(p, 'utf8')
}

const exists = async (p) => {
  try {
    await fs.access(p)
    return true
  } catch {
    return false
  }
}

const extractRoutePaths = (appSource) => {
  // Match: <Route path="/xxx" ... />
  const re = /<Route\s+path="([^"]+)"/g
  const out = new Set()
  let m
  while ((m = re.exec(appSource)) !== null) {
    const raw = String(m[1] ?? '').trim()
    if (!raw.startsWith('/')) continue
    if (raw === '/' || raw === '/*') continue
    // Skip dynamic / catch-all routes, they can't be materialized as static directories
    if (raw.includes(':') || raw.includes('*')) continue
    out.add(raw)
  }
  return Array.from(out).sort((a, b) => a.localeCompare(b))
}

const main = async () => {
  if (!(await exists(DIST_DIR))) {
    throw new Error(`[spa-fallbacks] dist 目录不存在：${DIST_DIR}（请先运行 npm run build）`)
  }
  const indexHtml = path.join(DIST_DIR, 'index.html')
  if (!(await exists(indexHtml))) {
    throw new Error(`[spa-fallbacks] dist/index.html 不存在：${indexHtml}（请先运行 npm run build）`)
  }
  const appSource = await readText(APP_FILE)
  const routes = extractRoutePaths(appSource)

  let written = 0
  for (const route of routes) {
    const dir = path.join(DIST_DIR, route.replace(/^\//, ''))
    const target = path.join(dir, 'index.html')
    await fs.mkdir(dir, { recursive: true })
    await fs.copyFile(indexHtml, target)
    written += 1
  }

  // eslint-disable-next-line no-console
  console.log(`[spa-fallbacks] wrote ${written} route index.html files`)
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(String(err?.stack ?? err?.message ?? err))
  process.exit(1)
})

