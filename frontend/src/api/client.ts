/** 统一请求封装：拼后端地址、附带当前角色、抛网络错误、给页脚留一句可读的说明。 */
import { ROLE_EQUIPMENT_ADMIN } from '@/api/auth'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const SESSION_ROLE_KEY = 'lab.session.role'
const SESSION_OPERATOR_KEY = 'lab.session.operator'
const DEFAULT_OPERATOR = '李设备'

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const role = window.localStorage.getItem(SESSION_ROLE_KEY) ?? ROLE_EQUIPMENT_ADMIN
  const operator = window.localStorage.getItem(SESSION_OPERATOR_KEY) ?? DEFAULT_OPERATOR
  return fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(role ? { 'X-User-Role': role } : {}),
      ...(operator ? { 'X-User-Name': operator } : {}),
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    },
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  if (!response.ok) {
    let detail = `接口返回 ${response.status}，数据未更新`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // 保留通用错误说明
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}
