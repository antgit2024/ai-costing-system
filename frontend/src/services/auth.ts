import axios from 'axios'

import type { StaffInfo } from '@/store/auth'

export interface LoginPayload {
  username: string
  password: string
}

/**
 * POD `/admin/staff/login` 响应格式 ·
 * ai-costing 后端 `/admin/auth/login` 直接透传 (见 routers/admin_auth.py)。
 */
export interface LoginResponse {
  token: string
  expire_at: string
  staff_id: string
  username: string
  display_name: string
  role: string
}

export async function loginStaff(payload: LoginPayload): Promise<LoginResponse> {
  const { data } = await axios.post<LoginResponse>('/admin/auth/login', payload)
  return data
}

export async function fetchCurrentStaff(): Promise<StaffInfo> {
  const { data } = await axios.get<StaffInfo>('/admin/auth/me')
  return data
}
