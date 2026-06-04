import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import axios from 'axios'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { loginStaff } from '@/services/auth'
import { useAuthStore } from '@/store/auth'

interface LoginFormValues {
  username: string
  password: string
}

const LoginPage = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const nextParam = new URLSearchParams(location.search).get('next')
  const next = nextParam ? decodeURIComponent(nextParam) : '/'

  const onFinish = async (values: LoginFormValues) => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      const resp = await loginStaff(values)
      setAuth(resp.token, {
        staff_id: resp.staff_id,
        username: resp.username,
        role: resp.role,
      })
      navigate(next, { replace: true })
    } catch (err) {
      const detail =
        (axios.isAxiosError(err) &&
          (err.response?.data as { detail?: string } | undefined)?.detail) ||
        '登录失败，请检查账号密码'
      setErrorMsg(typeof detail === 'string' ? detail : JSON.stringify(detail))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f5f6fa',
      }}
    >
      <Card style={{ width: 380, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            AI Costing 后台登录
          </Typography.Title>
          <Typography.Text type="secondary">使用 POD 平台员工账号登录</Typography.Text>
        </div>
        {errorMsg && (
          <Alert
            type="error"
            message={errorMsg}
            showIcon
            closable
            style={{ marginBottom: 16 }}
            onClose={() => setErrorMsg(null)}
          />
        )}
        <Form<LoginFormValues>
          layout="vertical"
          onFinish={onFinish}
          autoComplete="on"
          requiredMark={false}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="username" autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
        <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', fontSize: 12 }}>
          忘记密码？请联系 POD 平台管理员重置。
        </Typography.Text>
      </Card>
    </div>
  )
}

export default LoginPage
