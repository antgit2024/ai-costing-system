import { LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Avatar, Dropdown, type MenuProps, Space, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'

import { useAuthStore } from '@/store/auth'

const ROLE_LABEL: Record<string, { text: string; color: string }> = {
  admin: { text: '超管', color: 'red' },
  operator: { text: '运营', color: 'blue' },
  finance: { text: '财务', color: 'green' },
  cs: { text: '客服', color: 'orange' },
  designer: { text: '设计', color: 'purple' },
}

const UserMenu = () => {
  const navigate = useNavigate()
  const staff = useAuthStore((s) => s.staff)
  const clearAuth = useAuthStore((s) => s.clearAuth)

  if (!staff) return null

  const handleLogout = () => {
    clearAuth()
    navigate('/login', { replace: true })
  }

  const items: MenuProps['items'] = [
    {
      key: 'staff_id',
      disabled: true,
      label: (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          ID: {staff.staff_id.slice(0, 8)}…
        </Typography.Text>
      ),
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: handleLogout,
    },
  ]

  const role = ROLE_LABEL[staff.role] ?? { text: staff.role, color: 'default' }

  return (
    <Dropdown menu={{ items }} placement="bottomRight" trigger={['click']}>
      <Space size={8} style={{ cursor: 'pointer', padding: '0 8px' }}>
        <Avatar size="small" icon={<UserOutlined />} style={{ background: '#1677ff' }} />
        <span style={{ color: '#fff', fontWeight: 500 }}>{staff.username}</span>
        <Tag color={role.color} style={{ margin: 0 }}>
          {role.text}
        </Tag>
      </Space>
    </Dropdown>
  )
}

export default UserMenu
