import { Button, Drawer, Space, Typography, message } from 'antd'

const { Text } = Typography

export type GuideDrawerProps = {
  open: boolean
  title: string
  content: string
  onClose: () => void
  tip?: string
}

const GuideDrawer = ({ open, title, content, onClose, tip }: GuideDrawerProps) => {
  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width={760}
      destroyOnClose
      extra={
        <Space>
          <Button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(content)
                message.success('已复制指南内容')
              } catch {
                message.error('复制失败，请手动全选复制')
              }
            }}
          >
            复制全文
          </Button>
          <Button type="primary" onClick={onClose}>
            关闭
          </Button>
        </Space>
      }
    >
      {tip ? (
        <Typography style={{ marginBottom: 12 }}>
          <Text type="secondary">{tip}</Text>
        </Typography>
      ) : null}
      <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>{content}</pre>
    </Drawer>
  )
}

export default GuideDrawer




