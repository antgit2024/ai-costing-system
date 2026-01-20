import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import App from './App.tsx'
import 'antd/dist/reset.css'
import './index.css'
import { appTheme } from './theme/appTheme'

const queryClient = new QueryClient()

/**
 * 线上偶发“切换栏目白屏”，最常见原因是动态 import chunk / 预加载失败：
 * - Failed to fetch dynamically imported module
 * - Loading chunk <id> failed
 * - Vite preload error（vite:preloadError）
 *
 * 这里做兜底：检测到上述错误时，自动刷新一次（避免用户手动刷新多次）。
 * 使用 sessionStorage 防止无限刷新循环。
 */
function installChunkLoadRecovery() {
  if (typeof window === 'undefined') return

  const KEY = '__vite_chunk_load_recovered__'
  const already = () => window.sessionStorage?.getItem(KEY) === '1'
  const mark = () => window.sessionStorage?.setItem(KEY, '1')

  const extractMessage = (value: unknown): string => {
    if (value instanceof Error) return value.message
    if (typeof value === 'string') return value
    if (typeof value === 'object' && value) {
      const maybeMessage = (value as Record<string, unknown>).message
      if (typeof maybeMessage === 'string') return maybeMessage
    }
    return String(value ?? '')
  }

  const shouldRecover = (msg: string) => {
    const m = (msg || '').toLowerCase()
    return (
      m.includes('failed to fetch dynamically imported module') ||
      m.includes('importing a module script failed') ||
      m.includes('loading chunk') ||
      m.includes('chunkloaderror') ||
      // Vite 预加载 CSS 失败也会导致页面卡死/白屏
      m.includes('unable to preload css')
    )
  }

  const recover = (reason: unknown) => {
    const msg = extractMessage(reason)
    if (!shouldRecover(msg)) return
    if (already()) return

    try {
      mark()
    } catch {
      // ignore
    }
    // 给浏览器一点点时间把错误日志打出来
    setTimeout(() => {
      window.location.reload()
    }, 50)
  }

  // Vite build 里会 dispatch 该事件（见 dist/assets/index-*.js）
  window.addEventListener('vite:preloadError', (e: Event) => {
    const ev = e as Event & { payload?: unknown; preventDefault?: () => void }
    try {
      ev.preventDefault?.()
    } catch {
      // ignore
    }
    recover(ev.payload ?? ev)
  })

  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    recover(e.reason ?? e)
  })

  // 有些浏览器会把 module load error 抛到 error 事件
  window.addEventListener('error', (e: ErrorEvent) => {
    recover(e.error ?? e.message ?? e)
  })
}

installChunkLoadRecovery()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={appTheme}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
