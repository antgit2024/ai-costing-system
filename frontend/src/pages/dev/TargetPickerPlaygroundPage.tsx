/**
 * /costing/system/target-picker-playground —— 模型筛选器（演练）
 * 旧路径 /dev/target-picker 已重定向到此（保留外链兼容）。
 *
 * 用途（系统运维场景）：
 *   1. 在线快速校验"标准模型 + 变体 / 套装模板 + preset"两类候选是否都能搜出来；
 *   2. 直观看到 token 拼装规则（套装行用 `B-{code}{selector}` / `Z-{code}{selector}`），
 *      便于排查 SKU Master / 天猫页 / 发货台账筛选器的 source_code 是否对得上；
 *   3. 不做任何写操作，仅展示选择结果。
 */

import { useState } from 'react'
import { Card, Col, Divider, Row, Space, Typography } from 'antd'

import TargetPicker, {
  TargetPickerBrowserButton,
  renderTargetSelectionTags,
  targetSelectionToFilters,
} from '@/components/common/TargetPicker'
import type { TargetSelection } from '@/components/common/TargetPicker'

const { Title, Paragraph, Text } = Typography

const TargetPickerPlaygroundPage = () => {
  const [both, setBoth] = useState<TargetSelection | null>(null)
  const [modelOnly, setModelOnly] = useState<TargetSelection | null>(null)
  const [bundleOnly, setBundleOnly] = useState<TargetSelection | null>(null)
  const [browser, setBrowser] = useState<TargetSelection | null>(null)

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>模型筛选器（演练）</Title>
      <Paragraph type="secondary">
        系统运维工具页 —— 直接在线验证标准模型/变体、套装模板/preset 的可搜性，并查看 token 拼装规则
        （套装行尾部胶囊 <code>B-3U3PAA</code> / <code>Z-DB9EAG</code> 即真实落库到 source_code 的字符串）。
        本页不做任何写操作，仅供运营/排错使用。
      </Paragraph>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            title="模式 0：弹窗浏览模式（推荐 — Tab 标准模型/套装模板，一级展开看二级）"
            extra={<Text type="secondary">适合"不知道叫什么、想看候选全集"的运营场景</Text>}
          >
            <Space size={12} wrap>
              <TargetPickerBrowserButton value={browser} onChange={setBrowser} buttonProps={{ type: 'primary' }} />
              <Divider type="vertical" />
              <Text type="secondary">已选：</Text>
              {renderTargetSelectionTags(browser)}
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card title="模式 1：模型 + 套装 都可选（下拉搜索 — 适合知道关键词时）">
            <Space size={12} wrap>
              <TargetPicker value={both} onChange={setBoth} width={420} />
              <Divider type="vertical" />
              <Text type="secondary">已选：</Text>
              {renderTargetSelectionTags(both)}
            </Space>
            <Divider />
            <Text type="secondary">扁平筛选参数：</Text>
            <pre style={{ background: '#fafafa', padding: 12, borderRadius: 4, marginTop: 8 }}>
              {JSON.stringify(targetSelectionToFilters(both), null, 2)}
            </pre>
          </Card>
        </Col>

        <Col span={12}>
          <Card title="模式 2：仅标准模型（kind='model'）">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <TargetPicker value={modelOnly} onChange={setModelOnly} kind="model" width="100%" />
              {renderTargetSelectionTags(modelOnly)}
            </Space>
          </Card>
        </Col>

        <Col span={12}>
          <Card title="模式 3：仅套装模板（kind='bundle'）">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <TargetPicker value={bundleOnly} onChange={setBundleOnly} kind="bundle" width="100%" />
              {renderTargetSelectionTags(bundleOnly)}
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card title="搜索词建议（手工验收）" size="small">
            <ul>
              <li>
                输入 <code>KB8</code> ：应同时拉到 KB8 模型本身（"不指定变体"）+ 它的所有变体
                （如 <code>仿羊绒(KB8-001)</code>、<code>多尼尔(KB8-002)</code>）。
              </li>
              <li>
                输入 <code>KB8-001</code>：应直接定位到 <code>仿羊绒(KB8-001)</code> 这一行。
              </li>
              <li>
                输入 <code>仿羊绒</code>：通过材质名命中变体行。
              </li>
              <li>
                输入 <code>KIT01</code> 或套装名子串：应拉到套装的所有 preset。
              </li>
              <li>
                输入 <code>B:KIT01:</code>：通过 preset selector 命中套装。
              </li>
            </ul>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default TargetPickerPlaygroundPage
