<template>
  <section class="page" data-module="calibration">
    <header class="page-head">
      <div>
        <h2>校准记录管理</h2>
        <p class="page-desc">
          查看历史校准记录。检测人员请在仪器设备页提交申请；设备管理员在此开始校准并判定结果。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="session.isInspector" class="btn primary" type="button" @click="goToInstrument">
          提交校准申请
        </button>
        <button class="btn" type="button" @click="exportRows">导出校准记录清单</button>
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
        <span>校准编号</span>
        <input v-model="filters.keyword" placeholder="按校准编号检索" />
      </label>
      <label class="filter-item">
        <span>校准状态</span>
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
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in allowedActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!allowedActions(row).length" class="text-muted">
              {{ session.isInspector ? '请在仪器设备页提交申请' : '无待处理动作' }}
            </span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无校准记录数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条校准记录</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | string[] | null>

const ENDPOINT = '/api/calibration'
const columns = ['校准编号', '关联设备', '校准方式', '标准物质', '校准结果', '校准日期', '下次校准日', '校准状态']
const statuses = ['待校准', '校准中', '已合格', '不合格']

const router = useRouter()
const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const stats = computed(() => [
  { label: '待校准记录', value: countByStatus('待校准') },
  { label: '校准中', value: countByStatus('校准中') },
  { label: '已合格', value: countByStatus('已合格') },
  { label: '不合格', value: countByStatus('不合格') },
])

function countByStatus(status: string): number {
  return rows.value.filter((row) => row.校准状态 === status).length
}

function allowedActions(row: Row): string[] {
  return Array.isArray(row.allowed_actions) ? (row.allowed_actions as string[]) : []
}

function goToInstrument() {
  void router.push('/instrument')
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readActionResult(response)
    if (!result.ok) throw new Error(result.message)
    successMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '校准记录操作失败'
  }
}

async function readActionResult(response: Response) {
  if (!response.ok) {
    let detail = '校准记录动作未生效，请稍后重试'
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
      throw new Error('校准记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '校准记录列表读取失败'
  }
}

watch(() => session.role, () => {
  void reload()
})

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.text-muted { color: var(--muted); font-size: 12px; }
.success-text { color: #067647; }
</style>
