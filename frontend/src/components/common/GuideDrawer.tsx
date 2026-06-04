import { Button, Drawer, Space, Typography, message } from 'antd'
import { isValidElement, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import type { Components } from 'react-markdown'

import 'highlight.js/styles/github-dark.css'
import './GuideDrawer.css'

const { Text } = Typography

export type GuideDrawerProps = {
  open: boolean
  title: string
  content: string
  onClose: () => void
  tip?: string
}

const GuideDrawer = ({ open, title, content, onClose, tip }: GuideDrawerProps) => {
  const contentRef = useRef<HTMLDivElement | null>(null)

  const components: Components = {
    pre({ children, ...props }) {
      // react-markdown wraps fenced code blocks as <pre><code class="language-xxx">...</code></pre>.
      // For our special `guozong` block, we want a normal div (auto-wrapping), not a <pre>.
      const child = Array.isArray(children) ? children[0] : children
      if (isValidElement(child)) {
        const className = String((child.props as any)?.className ?? '')
        if (className.includes('language-guozong')) {
          return <>{child}</>
        }
      }
      return (
        <pre {...props}>
          {children}
        </pre>
      )
    },
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      const lang = match?.[1]?.toLowerCase()

      // Special block for "郭总交待" — rendered as yellow summary box.
      // Usage in markdown (in every guide):
      //
      // ```guozong
      // - 一句话总结...
      // - 要点...
      // ```
      //
      if (lang === 'guozong') {
        const raw = String(children ?? '').replace(/\n$/, '')
        const lines = raw
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean)

        return (
          <div className="guide-guozong">
            <div className="guide-guozong-title">郭总交待</div>
            <ul>
              {lines.map((line, idx) => (
                <li key={idx}>{line.replace(/^[-*]\s+/, '')}</li>
              ))}
            </ul>
          </div>
        )
      }

      // Default behavior for regular code blocks/inline code
      return (
        <code className={className} {...props}>
          {children}
        </code>
      )
    },
  }

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
                // Copy rendered plain text (what user sees), not the raw markdown.
                const plainText = contentRef.current?.innerText?.trim()
                await navigator.clipboard.writeText(plainText && plainText.length > 0 ? plainText : content)
                message.success('已复制（纯文本）')
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
      <div className="guide-markdown" ref={contentRef}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]} components={components}>
          {content}
        </ReactMarkdown>
      </div>
    </Drawer>
  )
}

export default GuideDrawer




