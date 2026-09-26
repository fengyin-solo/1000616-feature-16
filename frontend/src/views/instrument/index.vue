<template>
  <section class="page" data-module="instrument">
    <header class="page-head">
      <div>
        <h2>仪器设备管理</h2>
        <p class="page-desc">
          当前角色：{{ session.roleLabel }}。设备档案维护与停用由设备管理员负责，检测人员可查看并提交校准申请。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="session.isAdmin" class="btn primary" type="button" @click="openCreate">登记仪器设备</button>
        <button class="btn" type="button" @click="exportRows">导出仪器设备清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="keyword" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>设备状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button v-if="session.isAdmin" class="link" type="button" @click="openEdit(row)">维护档案</button>
            <span v-if="!rowActions(row).length && !session.isAdmin" class="empty-state">仅可查看</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无仪器设备数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条仪器设备记录</span>
      <span v-if="noticeMessage" class="notice-text">
        {{ noticeMessage }}
        <RouterLink v-if="showCalibrationLink" to="/calibration">前往校准记录</RouterLink>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="editing" class="modal-mask" @click.self="closeForm">
      <div class="modal-card">
        <h3>{{ isCreating ? '登记仪器设备' : `维护设备档案：${editing['设备编号'] ?? ''}` }}</h3>
        <div class="form-grid">
          <label v-for="field in maintainFields" :key="field">
            <span>{{ field }}</span>
            <input v-model="form[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="button" @click="submitForm">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null> & { id: number; allowed_actions?: string[] }

const ENDPOINT = '/api/instrument'
const columns = ["设备编号", "设备名称", "设备型号", "量程范围", "校准周期", "校准到期日", "责任人", "设备状态"]
const statuses = ["待校准", "在运正常", "故障停机", "已停用"]
const maintainFields = ["设备编号", "设备名称", "设备型号", "量程范围", "校准周期", "校准到期日", "责任人"]

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const showCalibrationLink = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([
  { label: '在运设备', value: 0 },
  { label: '待校准设备', value: 0 },
  { label: '故障设备', value: 0 },
])

const editing = ref<Row | null>(null)
const isCreating = computed(() => editing.value !== null && !editing.value.id)
const form = ref<Record<string, string>>({})

function rowActions(row: Row): string[] {
  return Array.isArray(row.allowed_actions) ? row.allowed_actions : []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  editing.value = { id: 0 } as Row
  form.value = Object.fromEntries(maintainFields.map((field) => [field, '']))
}

function openEdit(row: Row) {
  editing.value = row
  form.value = Object.fromEntries(maintainFields.map((field) => [field, String(row[field] ?? '')]))
}

function closeForm() {
  editing.value = null
}

async function submitForm() {
  if (!editing.value) return
  errorMessage.value = ''
  noticeMessage.value = ''
  const creating = isCreating.value
  const url = creating ? ENDPOINT : `${ENDPOINT}/${editing.value.id}`
  try {
    const response = await request(url, {
      method: creating ? 'POST' : 'PUT',
      body: JSON.stringify({ values: form.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '仪器设备保存未生效')
    }
    noticeMessage.value = payload.message ?? '仪器设备已保存'
    closeForm()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备保存失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  showCalibrationLink.value = false
  if (action === '停用设备') {
    const confirmed = window.confirm(`停用设备需设备管理员二次确认。\n确认停用 ${row['设备编号']}（${row['设备名称']}）吗？`)
    if (!confirmed) return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, confirm: action === '停用设备' } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '仪器设备动作未生效')
    }
    noticeMessage.value = payload.message ?? `仪器设备已${action}`
    showCalibrationLink.value = action === '提交校准'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('仪器设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备列表读取失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (!response.ok) return
    const payload = await response.json()
    const all: Row[] = payload.items ?? []
    stats.value = [
      { label: '在运设备', value: all.filter((row) => row.status === '在运正常').length },
      { label: '待校准设备', value: all.filter((row) => row.status === '待校准').length },
      { label: '故障设备', value: all.filter((row) => row.status === '故障停机').length },
    ]
  } catch {
    // 统计卡片失败不阻塞列表
  }
}

// 切换角色后重新拉取，确保可执行动作与按钮归属一致
watch(() => session.role, () => void reload())

onMounted(reload)
</script>
