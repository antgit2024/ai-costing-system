import { Drawer, Form, Input, Space, Button, Typography, Divider, Card, message, Modal } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  narrative_short?: string
  narrative_long?: string
  _manual_overrides?: Record<string, boolean>
  _sources?: any
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
  ai_narrative_short?: string
  ai_narrative_long?: string
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
    ai_narrative_short: String(ai?.narrative_short ?? ''),
    ai_narrative_long: String(ai?.narrative_long ?? ''),
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
  ai_narrative_short?: any
  ai_narrative_long?: any
}): AIPartial | null => {
  const s = (v: any) => String(v ?? '').trim()
  const ai_spec: any = {}
  if (s(values.ai_intent)) ai_spec.intent = s(values.ai_intent)
  if (s(values.ai_inputs)) ai_spec.inputs = s(values.ai_inputs)
  if (s(values.ai_outputs)) ai_spec.outputs = s(values.ai_outputs)
  if (s(values.ai_quality_points)) ai_spec.quality_points = s(values.ai_quality_points)
  if (s(values.ai_constraints)) ai_spec.constraints = s(values.ai_constraints)
  if (s(values.ai_tools)) ai_spec.tools = s(values.ai_tools)
  if (s(values.ai_narrative_short)) ai_spec.narrative_short = s(values.ai_narrative_short)
  if (s(values.ai_narrative_long)) ai_spec.narrative_long = s(values.ai_narrative_long)

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

const toLines = (value: unknown): string[] => {
  const raw = String(value ?? '').trim()
  if (!raw) return []
  return raw
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
}

const uniq = (items: string[]) => Array.from(new Set(items.map((x) => x.trim()).filter(Boolean)))

const joinAsBullets = (items: string[]) => {
  const u = uniq(items)
  if (!u.length) return ''
  return u.map((x) => `- ${x}`).join('\n')
}

export default function ProcessModuleAIDrawer({ open, moduleId, onClose, onSaved }: Props) {
  const [form] = Form.useForm<ModuleAIFormValues>()
  const [stepEdits, setStepEdits] = useState<StepAIEdit[]>([])
  const initialFormRef = useRef<ModuleAIFormValues | null>(null)
  const initialStepEditsRef = useRef<StepAIEdit[] | null>(null)

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
    initialFormRef.current = initialModuleAI

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
    initialStepEditsRef.current = nextSteps
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

  const handleAggregateFromProcesses = async (mode: 'fill_empty' | 'overwrite') => {
    if (!module) return
    const steps = module.steps ?? []
    const processIds = uniq(steps.map((s) => String(s.process_id ?? '').trim()).filter(Boolean))
    if (!processIds.length) {
      message.warning('该模块尚未选择工序，无法汇总')
      return
    }

    const baseModuleMeta = (module.metadata_json ?? {}) as any
    const baseAi = (baseModuleMeta?.ai_spec ?? {}) as any
    const locked: Record<string, boolean> = (baseAi?._manual_overrides ?? {}) as any

    const hide = message.loading('正在从工序库汇总 AI 语义...', 0)
    try {
      const details = await Promise.all(processIds.map((pid) => fetchProcess(pid)))
      const aiList = details.map((d) => {
        const meta = (d.metadata_json ?? {}) as any
        const ai = (meta?.ai_spec ?? {}) as any
        return { description: d.description, ai }
      })

      const aggregated: Partial<ModuleAIFormValues> = {
        ai_intent: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.intent || x.description))),
        ai_inputs: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.inputs))),
        ai_outputs: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.outputs))),
        ai_quality_points: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.quality_points || x.ai?.qc))),
        ai_constraints: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.constraints || x.ai?.safety))),
        ai_tools: joinAsBullets(aiList.flatMap((x) => toLines(x.ai?.tools))),
      }

      const current = form.getFieldsValue() as ModuleAIFormValues
      const next: ModuleAIFormValues = { ...current }

      const applyField = (field: keyof ModuleAIFormValues, lockKey: string) => {
        const incoming = String((aggregated as any)[field] ?? '').trim()
        if (!incoming) return
        const cur = String((current as any)[field] ?? '').trim()
        const isLocked = !!locked[lockKey]
        if (isLocked) return
        if (mode === 'fill_empty') {
          if (!cur) (next as any)[field] = incoming
          return
        }
        ;(next as any)[field] = incoming
      }

      applyField('ai_intent', 'intent')
      applyField('ai_inputs', 'inputs')
      applyField('ai_outputs', 'outputs')
      applyField('ai_quality_points', 'quality_points')
      applyField('ai_constraints', 'constraints')
      applyField('ai_tools', 'tools')

      form.setFieldsValue(next)
      message.success(mode === 'fill_empty' ? '已从工序汇总（只填空）' : '已从工序汇总（覆盖未锁定字段）')
    } catch (e: any) {
      message.error(e?.response?.data?.detail ?? e?.message ?? '汇总失败')
    } finally {
      hide()
    }
  }

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
    const baseAi = ((baseModuleMeta as any)?.ai_spec ?? {}) as any
    const prevOverrides = (baseAi?._manual_overrides ?? {}) as Record<string, boolean>
    const nextOverrides: Record<string, boolean> = { ...prevOverrides }

    const initial = initialFormRef.current
    const markOverride = (formKey: keyof ModuleAIFormValues, aiKey: string) => {
      const cur = String((values as any)[formKey] ?? '').trim()
      const prev = String((initial as any)?.[formKey] ?? '').trim()
      if (cur && cur !== prev) nextOverrides[aiKey] = true
    }
    markOverride('ai_narrative_short', 'narrative_short')
    markOverride('ai_narrative_long', 'narrative_long')
    markOverride('ai_intent', 'intent')
    markOverride('ai_inputs', 'inputs')
    markOverride('ai_outputs', 'outputs')
    markOverride('ai_quality_points', 'quality_points')
    markOverride('ai_constraints', 'constraints')
    markOverride('ai_tools', 'tools')
    const nextModuleMeta: Record<string, unknown> = { ...baseModuleMeta }
    if (moduleAi) {
      moduleAi._manual_overrides = nextOverrides
      moduleAi._sources = { updated_at: new Date().toISOString() }
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
        const stepMeta: any = (s.metadata_json ?? {}) as any
        const stepBaseAi: any = stepMeta?.ai_spec ?? {}
        const stepPrevOverrides: Record<string, boolean> = (stepBaseAi?._manual_overrides ?? {}) as any
        const stepNextOverrides: Record<string, boolean> = { ...stepPrevOverrides }
        const initialSteps = initialStepEditsRef.current ?? []
        const initEdit = initialSteps.find((x) => x.step_id === s.id) ?? {}
        const markStep = (k: keyof StepAIEdit, aiKey: string) => {
          const cur = String((edit as any)?.[k] ?? '').trim()
          const prev = String((initEdit as any)[k] ?? '').trim()
          if (cur && cur !== prev) stepNextOverrides[aiKey] = true
        }
        markStep('ai_intent', 'intent')
        markStep('ai_inputs', 'inputs')
        markStep('ai_outputs', 'outputs')
        markStep('ai_quality_points', 'quality_points')
        markStep('ai_constraints', 'constraints')
        markStep('ai_tools', 'tools')
        if (
          String(edit?.ai_parameter_schema_json ?? '').trim() &&
          String(edit?.ai_parameter_schema_json ?? '').trim() !==
            String((initEdit as any).ai_parameter_schema_json ?? '').trim()
        ) {
          stepNextOverrides['parameter_schema'] = true
        }
        stepAi._manual_overrides = stepNextOverrides
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
        <Space style={{ marginBottom: 12 }} wrap>
          <Button onClick={() => handleAggregateFromProcesses('fill_empty')}>从工序自动汇总（只填空）</Button>
          <Button
            onClick={() =>
              Modal.confirm({
                title: '确认汇总并覆盖未锁定字段？',
                content: '将基于工序库 AI 语义汇总模块级字段；不会覆盖已手工锁定的字段。',
                okText: '继续',
                cancelText: '取消',
                onOk: () => handleAggregateFromProcesses('overwrite'),
              })
            }
          >
            从工序自动汇总（覆盖）
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            建议：先在工序库维护好 AI 字段，再在模块里一键汇总；模块里仅维护差异化内容。
          </Text>
        </Space>
        <Form form={form} layout="vertical" preserve={false} initialValues={initialModuleAI}>
          <Form.Item
            label="AI工艺说明（短）"
            name="ai_narrative_short"
            tooltip="用于主页面“描述/列表”快速浏览（建议 1-2 句）。"
          >
            <Input.TextArea rows={2} placeholder="例如：用于地垫卷材外包装，按最短边+预留长度套袋并扎带固定，降低运输破损。" />
          </Form.Item>
          <Form.Item
            label="AI工艺说明（长）"
            name="ai_narrative_long"
            tooltip="用于沉淀工艺知识（长文档），建议由 AI 生成后再人工微调。"
          >
            <Input.TextArea rows={8} placeholder="这里放刚才那种详细的工艺说明（目的/流程/关键物料/计量口径/QC/禁忌/工具等）。" />
          </Form.Item>
          <Divider />
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
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          步骤级用于“该模块场景下此工序的特殊要求/差异”。默认可不填；如需带入工序库 AI 语义，点击每步右上角按钮。
        </Text>
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
                    引用工序AI→步骤
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


