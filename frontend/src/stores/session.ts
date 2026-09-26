import { defineStore } from 'pinia'

export type OperatorRole = 'admin' | 'inspector'

export const ROLE_LABELS: Record<OperatorRole, string> = {
  admin: '设备管理员',
  inspector: '检测人员',
}

const ROLE_STORAGE_KEY = 'lab-operator-role'

function loadRole(): OperatorRole {
  const saved = window.localStorage.getItem(ROLE_STORAGE_KEY)
  return saved === 'inspector' ? 'inspector' : 'admin'
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '实验室样品检测平台',
    role: loadRole() as OperatorRole,
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isAdmin: (state) => state.role === 'admin',
    roleLabel: (state) => ROLE_LABELS[state.role],
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: OperatorRole) {
      this.role = role
      window.localStorage.setItem(ROLE_STORAGE_KEY, role)
    },
  },
})

export { ROLE_STORAGE_KEY }
