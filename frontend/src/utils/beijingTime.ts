import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

export const BEIJING_TZ = 'Asia/Shanghai'

export const beijingTime = (value?: string | number | Date | null) => {
  if (value === null || value === undefined || value === '') return null
  const d = dayjs(value)
  return d.isValid() ? d.tz(BEIJING_TZ) : null
}

export const nowBeijing = () => dayjs().tz(BEIJING_TZ)

export const formatBeijingTime = (
  value?: string | number | Date | null,
  pattern = 'YYYY-MM-DD HH:mm:ss',
  fallback = '-',
): string => {
  const d = beijingTime(value)
  return d ? d.format(pattern) : (value ? String(value) : fallback)
}

export const formatBeijingRelativeTime = (value?: string | number | Date | null): string => {
  const d = beijingTime(value)
  if (!d) return value ? String(value) : '-'
  const diffMin = nowBeijing().diff(d, 'minute')
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)} 小时前`
  if (diffMin < 60 * 24 * 7) return `${Math.floor(diffMin / 60 / 24)} 天前`
  return d.format('MM-DD HH:mm')
}
