import { Drawer, Form, Input, Space, Button, Typography, Divider, Card, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { fetchProcess, fetchProcessModule, updateProcessModule } from '@/services/planner'
import type { ProcessDetail, ProcessModuleDetail, ProcessModuleStepInput, ProcessModuleUpdatePayload } from '@/types/planner'

const { Text } = Typography

type AIPartial = {
  intent?: string
  inputs?: string
  outputs?: string
  quality_points?: string
  constraints?: string
  tools?: string
  parameter_schema?: any
}

type StepAIEdit = {
  step_id: string
  ai_intent?: string
  ai_inputs?: string
  ai_outputs?: string
  ai_quality_points?: string
  ai_constraints?: string
  ai_tools?: string
  ai_parameter_schema_json?: string
}

type ModuleAIFormValues = {
  ai_intent?: string
  ai_inputs?: string
  ai_outputs?: string
  ai_quality_points?: string
  ai_constraints?: string
  ai_tools?: string
  ai_parameter_schema_json?: string
}

type Props = {
  open: boolean
  moduleId?: string | null
  onClose: () => void
  onSaved?: () => void
}

const normalizeAiSpecToForm = (ai: any): ModuleAIFormValues => {
  return {
    ai_intent: String(ai?.intent ?? ''),
    ai_inputs: String(ai?.inputs ?? ''),
    ai_outputs: String(ai?.outputs ?? ''),
    ai_quality_points: String(ai?.quality_points ?? ''),
    ai_constraints: String(ai?.constraints ?? ''),
    ai_tools: String(ai?.tools ?? ''),
    ai_parameter_schema_json: ai?.parameter_schema ? JSON.stringify(ai?.parameter_schema, null, 2) : '',
  }
}

const buildAiSpecFromValues = (values: {
  ai_intent?: any
  ai_inputs?: any
  ai_outputs?: any
  ai_quality_points?: any
  ai_constraints?: any
  ai_tools?: any
  ai_parameter_schema_json?: any
}): AIPartial | null => {
  const s = (v: any) => String(v ?? '').trim()
  const ai_spec: any = {}
  if (s(values.ai_intent)) ai_spec.intent = s(values.ai_intent)
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
      throw new Error('参数模板必须是合法 JSON')
    }
  }

  return Object.keys(ai_spec).length ? ai_spec : null
}

export default function ProcessModuleAIDrawer({ open, moduleId, onClose, onSaved }: Props) {
  const [form] = Form.useForm<ModuleAIFormValues>()
  const [stepEdits, setStepEdits] = useState<StepAIEdit[]>([])

  const moduleQuery = useQuery<ProcessModuleDetail>({
    queryKey: ['process-module', moduleId],
    enabled: open && !!moduleId,
    queryFn: () => fetchProcessModule(String(moduleId)),
  })

  const module = moduleQuery.data

  const initialModuleAI = useMemo(() => {
    const meta = (module?.metadata_json ?? {}) as any
    const ai = (meta?.ai_spec ?? {}) as any
    // 兜底：模块意图为空时，先用模块描述提示用户
    const base = normalizeAiSpecToForm(ai)
    if (!String(base.ai_intent ?? '').trim() && module?.description) {
      base.ai_intent = String(module.description)
    }
    return base
  }, [module?.description, module?.metadata_json])

  useEffect(() => {
    if (!open) return
    if (!module) return
    form.setFieldsValue(initialModuleAI)

    const nextSteps: StepAIEdit[] = (module.steps ?? []).map((s) => {
      const meta = (s.metadata_json ?? {}) as any
      const ai = (meta?.ai_spec ?? {}) as any
      const base = normalizeAiSpecToForm(ai)
      // 步骤意图为空时，用步骤描述兜底
      if (!String(base.ai_intent ?? '').trim() && s.description) {
        base.ai_intent = String(s.description)
      }
      return { step_id: s.id, ...base }
    })
    setStepEdits(nextSteps)
  }, [form, initialModuleAI, module, open])

  const updateMutation = useMutation({
    mutationFn: async (payload: ProcessModuleUpdatePayload) => {
      if (!moduleId) throw new Error('缺少 moduleId')
      return await updateProcessModule(String(moduleId), payload)
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

  const handleImportFromProcess = async (stepIndex: number) => {
    if (!module) return
    const step = module.steps[stepIndex]
    const pid = String(step?.process_id ?? '').trim()
    if (!pid) {
      message.warning('该步骤未选择工序')
      return
    }
    const hide = message.loading('读取工序 AI 语义...', 0)
    try {
      const detail: ProcessDetail = await fetchProcess(pid)
      const meta = (detail.metadata_json ?? {}) as any
      const ai = (meta?.ai_spec ?? {}) as any
      const next = normalizeAiSpecToForm(ai)
      // 如果工序没有 intent，用工序描述兜底
      if (!String(next.ai_intent ?? '').trim() && detail.description) next.ai_intent = String(detail.description)
      setStepEdits((prev) => {
        const base = prev.slice()
        const targetId = module.steps[stepIndex]?.id
        const idx = base.findIndex((x) => x.step_id === targetId)
        if (idx >= 0) base[idx] = { step_id: targetId, ...next }
        return base
      })
      message.success('已引用工序 AI 语义（可继续修改后保存）')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '读取工序失败')
    } finally {
      hide()
    }
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    if (!module) {
      message.error('模块数据未加载')
      return
    }

    let moduleAi: AIPartial | null = null
    try {
      moduleAi = buildAiSpecFromValues(values)
    } catch (e: any) {
      message.error(e?.message ?? '参数模板 JSON 不合法')
      return
    }

    const baseModuleMeta = (module.metadata_json ?? {}) as Record<string, unknown>
    const nextModuleMeta: Record<string, unknown> = { ...baseModuleMeta }
    if (moduleAi) {
      ;(nextModuleMeta as any).ai_spec = moduleAi
    } else {
      delete (nextModuleMeta as any).ai_spec
    }

    const stepsPayload: ProcessModuleStepInput[] = (module.steps ?? []).map((s, idx) => {
      const base = (s.metadata_json ?? {}) as Record<string, unknown>
      const next = { ...base }
      const edit = stepEdits.find((x) => x.step_id === s.id)

      let stepAi: AIPartial | null = null
      if (edit) {
        try {
          stepAi = buildAiSpecFromValues(edit)
        } catch (e: any) {
          throw e
        }
      }

      if (stepAi) {
        ;(next as any).ai_spec = stepAi
      } else {
        delete (next as any).ai_spec
      }

      return {
        sequence_order: s.sequence_order ?? idx,
        team_name: s.team_name,
        pricing_method: s.pricing_method,
        work_minutes: s.work_minutes,
        unit_of_measure: s.unit_of_measure,
        description: s.description,
        notes: s.notes,
        process_id: s.process_id,
        metadata_json: next,
      }
    })

    updateMutation.mutate({
      metadata_json: nextModuleMeta,
      steps: stepsPayload,
    })
  }

  return (
    <Drawer
      title={
        <Space direction="vertical" size={0}>
          <div>AI 语义（工艺模块）</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {module?.module_code ? `${module.module_code} / ` : ''}
            {module?.module_name ?? ''}
          </Text>
        </Space>
      }
      open={open}
      onClose={onClose}
      width={920}
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
      <Card size="small" title="模块级 AI 语义" bordered={false}>
        <Form form={form} layout="vertical" preserve={false} initialValues={initialModuleAI}>
          <Form.Item label="模块意图/目的" name="ai_intent">
            <Input.TextArea rows={3} placeholder="用于说明该工艺模块产出什么半成品、为什么这样做、适用场景" />
          </Form.Item>
          <Form.Item label="输入" name="ai_inputs">
            <Input.TextArea rows={2} placeholder="输入物料/前置半成品/工装等" />
          </Form.Item>
          <Form.Item label="输出" name="ai_outputs">
            <Input.TextArea rows={2} placeholder="输出半成品/状态/交付物" />
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
          <Form.Item label="参数模板（JSON）" name="ai_parameter_schema_json" tooltip="用于后续自动生成步骤参数表单；需为合法 JSON。">
            <Input.TextArea rows={6} placeholder='例如：[{"name":"宽度","type":"number","unit":"cm"}]' />
          </Form.Item>
        </Form>
      </Card>

      <Divider />

      <Card size="small" title="步骤级 AI 语义（每一步可覆盖/补充）" bordered={false}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {(module?.steps ?? []).map((s, idx) => {
            const edit = stepEdits.find((x) => x.step_id === s.id) ?? { step_id: s.id }
            const processLabel = s.process ? `${s.process.process_code} / ${s.process.process_name}` : String(s.process_id ?? '').trim() || '-'
            return (
              <Card
                key={s.id}
                size="small"
                title={
                  <Space direction="vertical" size={0}>
                    <div>步骤 {idx + 1}</div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {processLabel}
                    </Text>
                  </Space>
                }
                extra={
                  <Button size="small" onClick={() => handleImportFromProcess(idx)}>
                    从工序引用 AI
                  </Button>
                }
              >
                <Space direction="vertical" style={{ width: '100%' }} size={10}>
                  <Input.TextArea
                    rows={2}
                    value={edit.ai_intent}
                    onChange={(e) =>
                      setStepEdits((prev) =>
                        prev.map((x) => (x.step_id === s.id ? { ...x, ai_intent: e.target.value } : x)),
                      )
                    }
                    placeholder="步骤意图/目的"
                  />
                  <Input.TextArea
                    rows={2}
                    value={edit.ai_quality_points}
                    onChange={(e) =>
                      setStepEdits((prev) =>
                        prev.map((x) => (x.step_id === s.id ? { ...x, ai_quality_points: e.target.value } : x)),
                      )
                    }
                    placeholder="质量要点 / QC（步骤级）"
                  />
                  <Input.TextArea
                    rows={2}
                    value={edit.ai_constraints}
                    onChange={(e) =>
                      setStepEdits((prev) =>
                        prev.map((x) => (x.step_id === s.id ? { ...x, ai_constraints: e.target.value } : x)),
                      )
                    }
                    placeholder="禁忌/边界条件（步骤级）"
                  />
                  <Input.TextArea
                    rows={2}
                    value={edit.ai_tools}
                    onChange={(e) =>
                      setStepEdits((prev) =>
                        prev.map((x) => (x.step_id === s.id ? { ...x, ai_tools: e.target.value } : x)),
                      )
                    }
                    placeholder="设备/工具（步骤级）"
                  />
                  <Input.TextArea
                    rows={4}
                    value={edit.ai_parameter_schema_json}
                    onChange={(e) =>
                      setStepEdits((prev) =>
                        prev.map((x) =>
                          x.step_id === s.id ? { ...x, ai_parameter_schema_json: e.target.value } : x,
                        ),
                      )
                    }
                    placeholder='参数模板(JSON)，步骤级可覆盖。例如：[{"name":"速度","type":"number","unit":"mm/s"}]'
                  />
                </Space>
              </Card>
            )
          })}
          {!module?.steps?.length ? <Text type="secondary">暂无步骤（先在主抽屉里添加工序组）</Text> : null}
        </Space>
      </Card>
    </Drawer>
  )
}


