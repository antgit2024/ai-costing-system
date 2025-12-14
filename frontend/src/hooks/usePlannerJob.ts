import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchImportJob, fetchPlannerJob } from '@/services/planner'
import type { ImportJob, PlannerJob, PlannerJobKind } from '@/types/planner'
import { terminalImportStatuses, terminalPlannerJobStatuses } from '@/types/planner'

type JobResult = PlannerJob | ImportJob

const SSE_URL = import.meta.env.VITE_PLANNER_SSE_URL as string | undefined
const SSE_ENABLED = import.meta.env.VITE_ENABLE_JOB_SSE === 'true'

const terminalStatusMap: Record<PlannerJobKind, string[]> = {
  import: terminalImportStatuses,
  planner: terminalPlannerJobStatuses,
}

const jobFetchers: Record<PlannerJobKind, (jobId: string) => Promise<JobResult>> = {
  import: fetchImportJob,
  planner: fetchPlannerJob,
}

export const usePlannerJob = (jobId?: string, kind: PlannerJobKind = 'planner', enabled = true) => {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (
      !jobId ||
      !enabled ||
      kind !== 'planner' ||
      !SSE_ENABLED ||
      !SSE_URL ||
      typeof window === 'undefined' ||
      !('EventSource' in window)
    ) {
      return
    }
    const source = new EventSource(`${SSE_URL}?job_id=${jobId}`)
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as PlannerJob
        if (payload?.id === jobId) {
          queryClient.setQueryData(['planner-job', kind, jobId], payload)
        }
      } catch (error) {
        console.warn('planner job SSE parse failed', error)
      }
    }
    source.onerror = () => {
      source.close()
    }
    return () => {
      source.close()
    }
  }, [jobId, kind, enabled, queryClient])

  return useQuery<JobResult>({
    enabled: Boolean(jobId) && enabled,
    queryKey: ['planner-job', kind, jobId],
    queryFn: () => jobFetchers[kind](jobId!),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status) {
        return 2000
      }
      return terminalStatusMap[kind].includes(status) ? false : 2000
    },
  })
}

