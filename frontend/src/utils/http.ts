/**
 * 全局 axios 拦截器(COSTING-C1) ·
 *  在 main.tsx 顶部 import 一次即可激活 · 零侵入兼容现有所有 services 中
 *  `import axios from 'axios'` 的裸写法。
 *
 *  Request:  注入 `Authorization: Bearer <accessToken>`(若已登录) ·
 *           不影响外部 absolute url 调用。
 *  Response: 401 自动登出 + 跳 /login(?next=<原 path>) ·
 *           白名单 path(如 /admin/auth/login) 不触发跳转。
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { useAuthStore } from '@/store/auth'

const LOGIN_PATH = '/login'
const ALLOWED_401_PATHS = ['/admin/auth/login']

axios.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers = config.headers ?? {}
    if (!('Authorization' in config.headers)) {
      ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
    }
  }
  return config
})

axios.interceptors.response.use(
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

export {}
