import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type StaffRole = 'admin' | 'operator' | 'finance' | 'cs' | 'designer'

export interface StaffInfo {
  staff_id: string
  username: string
  role: StaffRole | string
}

interface AuthState {
  accessToken: string | null
  staff: StaffInfo | null
  setAuth: (token: string, staff: StaffInfo) => void
  clearAuth: () => void
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      staff: null,
      setAuth: (token, staff) => set({ accessToken: token, staff }),
      clearAuth: () => set({ accessToken: null, staff: null }),
      isAuthenticated: () => !!get().accessToken,
    }),
    {
      name: 'ai-costing-auth',
      partialize: (s) => ({ accessToken: s.accessToken, staff: s.staff }),
    },
  ),
)
