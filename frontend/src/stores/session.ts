import { defineStore } from 'pinia'

import { ROLE_EQUIPMENT_ADMIN, ROLE_INSPECTOR } from '@/api/auth'

export const SESSION_ROLE_KEY = 'lab.session.role'
export const SESSION_OPERATOR_KEY = 'lab.session.operator'

const DEFAULT_OPERATORS: Record<string, string> = {
  [ROLE_EQUIPMENT_ADMIN]: '李设备',
  [ROLE_INSPECTOR]: '王检测',
}

function readRole(): string {
  return window.localStorage.getItem(SESSION_ROLE_KEY) ?? ROLE_EQUIPMENT_ADMIN
}

function readOperator(role: string): string {
  return window.localStorage.getItem(SESSION_OPERATOR_KEY) ?? DEFAULT_OPERATORS[role] ?? role
}

export const useSessionStore = defineStore('session', {
  state: () => {
    const role = readRole()
    return {
      operator: readOperator(role),
      role,
      shiftLabel: '白班 08:00-20:00',
      scope: '实验室样品检测平台',
    }
  },
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isEquipmentAdmin: (state) => state.role === ROLE_EQUIPMENT_ADMIN,
    isInspector: (state) => state.role === ROLE_INSPECTOR,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: string) {
      this.role = role
      this.operator = DEFAULT_OPERATORS[role] ?? role
      window.localStorage.setItem(SESSION_ROLE_KEY, role)
      window.localStorage.setItem(SESSION_OPERATOR_KEY, this.operator)
    },
    setOperator(operator: string) {
      this.operator = operator.trim() || DEFAULT_OPERATORS[this.role] || this.role
      window.localStorage.setItem(SESSION_OPERATOR_KEY, this.operator)
    },
  },
})
