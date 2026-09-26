<template>
  <section class="page" data-module="instrument">
    <header class="page-head">
      <div>
        <h2>仪器设备管理</h2>
        <p class="page-desc">
          设备管理员维护设备编号、型号与量程；检测人员仅可查看设备，并对在运设备提交校准申请。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="session.isEquipmentAdmin" class="btn primary" type="button" @click="openCreate">
          登记仪器设备
        </button>
        <button class="btn" type="button" @click="exportRows">导出仪器设备清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="role-tip">当前身份：{{ session.role }} · {{ session.operator }}</p>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="filters.keyword" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>设备状态</span>
        <select v-model="filters.status">
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
          <th v-if="session.isEquipmentAdmin">维护操作</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td v-if="session.isEquipmentAdmin" class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">维护资料</button>
          </td>
          <td class="row-actions">
            <button
              v-for="action in allowedActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="handleAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!allowedActions(row).length" class="text-muted">无可执行操作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无仪器设备数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条仪器设备记录</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="editor.open" class="modal-backdrop">
      <div class="modal-card">
        <h3>{{ editor.mode === 'create' ? '登记仪器设备' : '维护仪器设备' }}</h3>
        <div class="form-grid">
          <label>
            <span>设备编号</span>
            <input v-model="editor.form.设备编号" placeholder="例如 INST-0004" />
          </label>
          <label>
            <span>设备名称</span>
            <input v-model="editor.form.设备名称" placeholder="设备名称" />
          </label>
          <label>
            <span>设备型号</span>
            <input v-model="editor.form.设备型号" placeholder="设备型号" />
          </label>
          <label>
            <span>量程范围</span>
            <input v-model="editor.form.量程范围" placeholder="例如 0-1000 ppm" />
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="editor.open = false">取消</button>
          <button class="btn primary" type="button" @click="saveEditor">保存</button>
        </div>
      </div>
    </div>

    <div v-if="disableTarget" class="modal-backdrop">
      <div class="modal-card">
        <h3>二次确认停用设备</h3>
        <p>
          设备「{{ disableTarget.设备编号 }} · {{ disableTarget.设备名称 }}」停用后将不能提交校准。
          该操作只生效一次，请设备管理员再次确认。
        </p>
        <label class="confirm-line">
          <input v-model="disableConfirmed" type="checkbox" />
          <span>我已核实设备状态，确认执行停用</span>
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="cancelDisable">取消</button>
          <button class="btn primary" type="button" :disabled="!disableConfirmed" @click="confirmDisable">
            确认停用
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | string[] | null>
type EditorMode = 'create' | 'edit'

const ENDPOINT = '/api/instrument'
const columns = ['设备编号', '设备名称', '设备型号', '量程范围', '校准周期', '校准到期日', '责任人', '设备状态']
const statuses = ['待校准', '在运正常', '故障停机', '已停用']

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })
const disableTarget = ref<Row | null>(null)
const disableConfirmed = ref(false)
const editor = reactive({
  open: false,
  mode: 'create' as EditorMode,
  id: 0,
  form: emptyForm(),
})

const stats = computed(() => [
  { label: '在运设备', value: countByStatus('在运正常') },
  { label: '待校准设备', value: countByStatus('待校准') },
  { label: '故障设备', value: countByStatus('故障停机') },
  { label: '已停用', value: countByStatus('已停用') },
])

function emptyForm() {
  return { 设备编号: '', 设备名称: '', 设备型号: '', 量程范围: '' }
}

function countByStatus(status: string): number {
  return rows.value.filter((row) => row.设备状态 === status).length
}

function allowedActions(row: Row): string[] {
  return Array.isArray(row.allowed_actions) ? (row.allowed_actions as string[]) : []
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  editor.mode = 'create'
  editor.id = 0
  editor.form = emptyForm()
  editor.open = true
}

function openEdit(row: Row) {
  editor.mode = 'edit'
  editor.id = Number(row.id)
  editor.form = {
    设备编号: String(row.设备编号 ?? ''),
    设备名称: String(row.设备名称 ?? ''),
    设备型号: String(row.设备型号 ?? ''),
    量程范围: String(row.量程范围 ?? ''),
  }
  editor.open = true
}

async function saveEditor() {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const url = editor.mode === 'create' ? ENDPOINT : `${ENDPOINT}/${editor.id}`
    const method = editor.mode === 'create' ? 'POST' : 'PATCH'
    const payload = editor.mode === 'create'
      ? { values: editor.form }
      : {
          values: {
            设备编号: editor.form.设备编号,
            设备型号: editor.form.设备型号,
            量程范围: editor.form.量程范围,
          },
        }
    const response = await request(url, { method, body: JSON.stringify(payload) })
    const result = await readActionResult(response)
    if (!result.ok) throw new Error(result.message)
    successMessage.value = result.message
    editor.open = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备保存失败'
  }
}

function handleAction(action: string, row: Row) {
  if (action === '停用设备') {
    disableTarget.value = row
    disableConfirmed.value = false
    return
  }
  void submitAction(String(row.id), action)
}

function cancelDisable() {
  disableTarget.value = null
  disableConfirmed.value = false
}

async function confirmDisable() {
  if (!disableTarget.value) return
  const id = String(disableTarget.value.id)
  await submitAction(id, '停用设备', { confirm: true })
  cancelDisable()
}

async function submitAction(id: string, action: string, extra: Record<string, unknown> = {}) {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...extra } }),
    })
    const result = await readActionResult(response)
    if (!result.ok) throw new Error(result.message)
    successMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备操作失败'
  }
}

async function readActionResult(response: Response) {
  if (!response.ok) {
    let detail = '仪器设备操作未生效，请稍后重试'
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // 使用默认错误说明
    }
    throw new Error(detail)
  }
  return (await response.json()) as { ok: boolean; message: string }
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword.trim()) query.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('仪器设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器设备列表读取失败'
  }
}

watch(() => session.role, () => {
  editor.open = false
  cancelDisable()
  void reload()
})

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.text-muted { color: var(--muted); font-size: 12px; }
.success-text { color: #067647; }
</style>
