import { type ReactNode, useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { fetchCurrentStaff } from '@/services/auth'
import { useAuthStore } from '@/store/auth'

interface AuthGuardProps {
  children: ReactNode
}

const AuthGuard = ({ children }: AuthGuardProps) => {
  const location = useLocation()
  const accessToken = useAuthStore((s) => s.accessToken)
  const staff = useAuthStore((s) => s.staff)
  const setAuth = useAuthStore((s) => s.setAuth)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const [verifying, setVerifying] = useState(false)

  useEffect(() => {
    if (!accessToken) return
    if (staff) return
    setVerifying(true)
    fetchCurrentStaff()
      .then((info) => setAuth(accessToken, info))
      .catch(() => clearAuth())
      .finally(() => setVerifying(false))
  }, [accessToken, staff, setAuth, clearAuth])

  if (!accessToken) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  if (verifying) {
    return null
  }
  return <>{children}</>
}

export default AuthGuard
