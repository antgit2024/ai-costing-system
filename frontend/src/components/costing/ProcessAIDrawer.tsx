import { Drawer, Form, Input, Space, Button, Typography, message } from 'antd'
import { useEffect, useMemo } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { fetchProcess, updateProcess } from '@/services/planner'
import type { ProcessDetail, ProcessUpdatePayload } from '@/types/planner'

const { Text } = Typography

type Props = {
  open: boolean
  processId?: string | null
  onClose: () => void
  onSaved?: () => void
}

type FormValues = {
  ai_intent?: string
  ai_inputs?: string
  ai_outputs?: string
  ai_quality_points?: string
  ai_constraints?: string
  ai_tools?: string
  ai_parameter_schema_json?: string
}

export default function ProcessAIDrawer({ open, processId, onClose, onSaved }: Props) {
  const [form] = Form.useForm<FormValues>()

  const processQuery = useQuery<ProcessDetail>({
    queryKey: ['process', processId],
    enabled: open && !!processId,
    queryFn: () => fetchProcess(String(processId)),
  })

  const process = processQuery.data

  const initialValues = useMemo(() => {
    const meta = (process?.metadata_json ?? {}) as any
    const ai = (meta?.ai_spec ?? {}) as any
    return {
      ai_intent: String(ai?.intent ?? process?.description ?? ''),
      ai_inputs: String(ai?.inputs ?? ''),
      ai_outputs: String(ai?.outputs ?? ''),
      ai_quality_points: String(ai?.quality_points ?? ''),
      ai_constraints: String(ai?.constraints ?? ''),
      ai_tools: String(ai?.tools ?? ''),
      ai_parameter_schema_json: ai?.parameter_schema ? JSON.stringify(ai?.parameter_schema, null, 2) : '',
    } satisfies FormValues
  }, [process?.description, process?.metadata_json])

  useEffect(() => {
    if (!open) return
    if (!process) return
    form.setFieldsValue(initialValues)
  }, [form, initialValues, open, process])

  const updateMutation = useMutation({
    mutationFn: async (payload: ProcessUpdatePayload) => {
      if (!processId) throw new Error('缺少 processId')
      return await updateProcess(String(processId), payload)
    },
    onSuccess: () => {
      message.success('AI 语义已保存')
      onSaved?.()
      onClose()
    },
    onError: (error) => {
      if (isAxiosError(error)) {
        message.error(error.response?.data?.detail ?? error.message)
        return
      }
      message.error('保存失败')
    },
  })

  const handleSave = async () => {
    const values = await form.validateFields()
    if (!process) {
      message.error('工序数据未加载')
      return
    }

    const s = (v: any) => String(v ?? '').trim()
    const baseMetadata = (process.metadata_json ?? {}) as Record<string, unknown>
    const metadata: Record<string, unknown> = { ...baseMetadata }

    const ai_spec: any = {}
    const intentValue = s(values.ai_intent) || s(process.description)
    if (intentValue) ai_spec.intent = intentValue
    if (s(values.ai_inputs)) ai_spec.inputs = s(values.ai_inputs)
    if (s(values.ai_outputs)) ai_spec.outputs = s(values.ai_outputs)
    if (s(values.ai_quality_points)) ai_spec.quality_points = s(values.ai_quality_points)
    if (s(values.ai_constraints)) ai_spec.constraints = s(values.ai_constraints)
    if (s(values.ai_tools)) ai_spec.tools = s(values.ai_tools)

    const rawSchema = s(values.ai_parameter_schema_json)
    if (rawSchema) {
      try {
        ai_spec.parameter_schema = JSON.parse(rawSchema)
      } catch {
        message.error('参数模板必须是合法 JSON')
        return
      }
    }

    if (Object.keys(ai_spec).length) {
      ;(metadata as any).ai_spec = ai_spec
    } else {
      delete (metadata as any).ai_spec
    }

    updateMutation.mutate({ metadata_json: metadata })
  }

  return (
    <Drawer
      title={
        <Space direction="vertical" size={0}>
          <div>AI 语义</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {process?.process_code ? `${process.process_code} / ` : ''}
            {process?.process_name ?? ''}
          </Text>
        </Space>
      }
      open={open}
      onClose={onClose}
      width={720}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={updateMutation.isPending} onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={initialValues}
      >
        <Form.Item label="工序意图/目的" name="ai_intent">
          <Input.TextArea rows={3} placeholder="一句话说明：为什么做/要达到什么效果（为空则默认用“描述”兜底）" />
        </Form.Item>

        <Form.Item label="输入" name="ai_inputs">
          <Input.TextArea rows={2} placeholder="输入物料/半成品/工装/前置条件" />
        </Form.Item>

        <Form.Item label="输出" name="ai_outputs">
          <Input.TextArea rows={2} placeholder="输出物/交付物/状态" />
        </Form.Item>

        <Form.Item label="关键质量点 / QC" name="ai_quality_points">
          <Input.TextArea rows={2} placeholder="关键检验点、容差、常见缺陷" />
        </Form.Item>

        <Form.Item label="安全/禁忌/边界" name="ai_constraints">
          <Input.TextArea rows={2} placeholder="风险、禁忌、注意事项、边界条件" />
        </Form.Item>

        <Form.Item label="设备/工具" name="ai_tools">
          <Input.TextArea rows={2} placeholder="设备、工具、工装夹具" />
        </Form.Item>

        <Form.Item
          label="参数模板（JSON）"
          name="ai_parameter_schema_json"
          tooltip="用于后续自动生成步骤参数表单；需为合法 JSON。"
        >
          <Input.TextArea rows={8} placeholder='例如：[{"name":"宽度","type":"number","unit":"cm"}]' />
        </Form.Item>
      </Form>
    </Drawer>
  )
}


