/**
 * 全局 axios 拦截器(COSTING-C1) ·
 *  Request:  注入 `Authorization: Bearer <accessToken>`(若已登录).
 *  Response: 401 自动登出 + 跳 /login(?next=<原 path>) ·
 *           白名单 path(如 /admin/auth/login) 不触发跳转.
 *
 * 关键: axios v1+ 里 `axios.create()` 出来的实例 *不继承* default 实例的拦截器.
 *      因此本模块导出 `installAuthInterceptors()` · 让所有手动 create 的 instance
 *      (如 services/planner.ts 的 plannerClient) 也能调一遍生效.
 */
import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'

import { useAuthStore } from '@/store/auth'

const LOGIN_PATH = '/login'
const ALLOWED_401_PATHS = ['/admin/auth/login']

const setHeader = (config: InternalAxiosRequestConfig, name: string, value: string) => {
  // axios v1 的 config.headers 通常是 AxiosHeaders 实例(有 .set 方法).
  // 老路径或某些第三方拦截器后可能退化成 plain object · 双兼容.
  if (config.headers instanceof AxiosHeaders) {
    config.headers.set(name, value)
    return
  }
  if (config.headers && typeof (config.headers as { set?: unknown }).set === 'function') {
    ;(config.headers as AxiosHeaders).set(name, value)
    return
  }
  config.headers = {
    ...(config.headers as Record<string, string> | undefined),
    [name]: value,
  } as InternalAxiosRequestConfig['headers']
}

const headerHas = (config: InternalAxiosRequestConfig, name: string): boolean => {
  if (!config.headers) return false
  if (config.headers instanceof AxiosHeaders) return config.headers.has(name)
  if (typeof (config.headers as { has?: unknown }).has === 'function') {
    return (config.headers as AxiosHeaders).has(name)
  }
  const lc = name.toLowerCase()
  return Object.keys(config.headers as Record<string, string>).some((k) => k.toLowerCase() === lc)
}

export function installAuthInterceptors(client: AxiosInstance): void {
  client.interceptors.request.use((config) => {
    const token = useAuthStore.getState().accessToken
    if (token && !headerHas(config, 'Authorization')) {
      setHeader(config, 'Authorization', `Bearer ${token}`)
    }
    return config
  })

  client.interceptors.response.use(
    (resp) => resp,
    (error: AxiosError) => {
      const status = error.response?.status
      const url = (error.config?.url ?? '').toString()
      if (status === 401 && !ALLOWED_401_PATHS.some((p) => url.includes(p))) {
        useAuthStore.getState().clearAuth()
        if (typeof window !== 'undefined' && window.location.pathname !== LOGIN_PATH) {
          const next = encodeURIComponent(window.location.pathname + window.location.search)
          window.location.replace(`${LOGIN_PATH}?next=${next}`)
        }
      }
      return Promise.reject(error)
    },
  )
}

installAuthInterceptors(axios)
