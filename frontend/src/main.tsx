import { Component, StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import App from './App.tsx'
import 'antd/dist/reset.css'
import './index.css'
import './utils/http'
import { appTheme } from './theme/appTheme'

const queryClient = new QueryClient()

class FatalErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('[fatal] react render error', error)
  }

  render() {
    if (!this.state.error) return this.props.children
    const e = this.state.error
    return (
      <div style={{ padding: 16, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>
        <h2 style={{ margin: 0, color: '#b42318' }}>页面发生致命错误（已捕获）</h2>
        <p style={{ margin: '8px 0 0', color: '#475467' }}>
          请把下面这段报错截图/复制给研发（包含 message/stack）。你也可以先点“刷新页面”试一次。
        </p>
        <div style={{ marginTop: 12 }}>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              border: '1px solid #d0d5dd',
              background: '#fff',
              padding: '6px 10px',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            刷新页面
          </button>
        </div>
        <pre
          style={{
            marginTop: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            background: '#f9fafb',
            border: '1px solid #eaecf0',
            padding: 12,
            borderRadius: 8,
          }}
        >
          {String(e?.message || e)}
          {'\n\n'}
          {String(e?.stack || '')}
        </pre>
      </div>
    )
  }
}

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

/**
 * 若出现“白屏但 Console 无红字”的场景（例如某些环境吞掉了错误），
 * 这里增加一个轻量覆盖层：捕获到非 chunkload 类错误时，直接把第一条错误显示到页面上。
 */
function installFatalOverlay() {
  if (typeof window === 'undefined') return
  const OVERLAY_ID = '__fatal_overlay__'
  let shown = false

  const extractMessage = (value: unknown): string => {
    if (value instanceof Error) return value.message
    if (typeof value === 'string') return value
    if (typeof value === 'object' && value) {
      const maybeMessage = (value as Record<string, unknown>).message
      if (typeof maybeMessage === 'string') return maybeMessage
    }
    return String(value ?? '')
  }

  const isChunkLoadLike = (msg: string) => {
    const m = (msg || '').toLowerCase()
    return (
      m.includes('failed to fetch dynamically imported module') ||
      m.includes('importing a module script failed') ||
      m.includes('loading chunk') ||
      m.includes('chunkloaderror') ||
      m.includes('unable to preload css')
    )
  }

  const show = (title: string, detail: unknown) => {
    if (shown) return
    const msg = extractMessage(detail)
    if (isChunkLoadLike(msg)) return // 交给 installChunkLoadRecovery 自动刷新兜底
    shown = true

    try {
      // eslint-disable-next-line no-console
      console.error('[fatal] overlay', detail)
    } catch {
      // ignore
    }

    const el = document.createElement('div')
    el.id = OVERLAY_ID
    el.style.position = 'fixed'
    el.style.left = '0'
    el.style.top = '0'
    el.style.right = '0'
    el.style.bottom = '0'
    el.style.zIndex = '2147483647'
    el.style.background = 'rgba(0,0,0,0.65)'
    el.style.color = '#fff'
    el.style.padding = '16px'
    el.style.overflow = 'auto'
    el.style.fontFamily = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'

    const pre = document.createElement('pre')
    pre.style.whiteSpace = 'pre-wrap'
    pre.style.wordBreak = 'break-word'
    pre.textContent = `${title}\n\n${msg}`
    el.appendChild(pre)

    const btn = document.createElement('button')
    btn.textContent = '刷新页面'
    btn.style.marginTop = '12px'
    btn.style.padding = '6px 10px'
    btn.style.borderRadius = '6px'
    btn.style.border = '1px solid #d0d5dd'
    btn.style.cursor = 'pointer'
    btn.onclick = () => window.location.reload()
    el.appendChild(btn)

    document.body.appendChild(el)
  }

  window.addEventListener('error', (e: ErrorEvent) => {
    show('页面发生致命错误（error）', e.error ?? e.message ?? e)
  })
  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    show('页面发生致命错误（unhandledrejection）', e.reason ?? e)
  })
}

installFatalOverlay()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={appTheme}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <FatalErrorBoundary>
            <App />
          </FatalErrorBoundary>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
