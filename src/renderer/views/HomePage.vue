<template>
  <!-- 首页（新）：概览数字 → 快捷入口 + 系统状态 → 最近运行。
       数据源：template.list / task.list / history.list / workflow.list_tools / env.list
       与后端健康探针；任一接口失败不影响其它卡片（allSettled + 局部错误提示）。 -->
  <div class="screen home">
    <PageHeader :title="t('home.title')" :description="t('home.subtitle')" />

    <AppNotice v-if="loadError" tone="danger" :title="t('home.loadFailed')">
      {{ loadError }}
      <template #action>
        <AppButton variant="outline" size="tiny" @click="load">{{ t('home.retry') }}</AppButton>
      </template>
    </AppNotice>

    <!-- 概览 -->
    <section class="home-stats" :aria-label="t('home.stats.title')">
      <StatCard
        :label="t('home.stats.workflows')"
        :value="loading && !loaded ? '—' : templates.length"
        tone="primary"
      >
        <template #icon><AppIcon name="wf" size="lg" /></template>
      </StatCard>
      <StatCard :label="t('home.stats.tasks')" :value="loading && !loaded ? '—' : tasks.length" tone="primary">
        <template #icon><AppIcon name="task" size="lg" /></template>
      </StatCard>
      <StatCard
        :label="t('home.stats.runs7d')"
        :value="loading && !loaded ? '—' : recentRunCount"
        :hint="t('home.stats.runs7dHint')"
        tone="success"
      >
        <template #icon><AppIcon name="activity" size="lg" /></template>
      </StatCard>
      <StatCard
        :label="t('home.stats.failed7d')"
        :value="loading && !loaded ? '—' : failedRunCount"
        tone="danger"
      >
        <template #icon><AppIcon name="alert" size="lg" /></template>
      </StatCard>
    </section>

    <div class="home-cols">
      <!-- 快捷入口 -->
      <AppCard :title="t('home.quick.title')">
        <div class="home-actions">
          <AppButton variant="primary" size="tiny" @click="go('/workflows/editor')">
            <template #icon><AppIcon name="plus" size="sm" /></template>
            {{ t('home.quick.newWorkflow') }}
          </AppButton>
          <AppButton variant="secondary" size="tiny" @click="go('/tasks/editor')">
            <template #icon><AppIcon name="plus" size="sm" /></template>
            {{ t('home.quick.newTask') }}
          </AppButton>
          <AppButton variant="outline" size="tiny" @click="go('/workflows')">
            <template #icon><AppIcon name="folder-in" size="sm" /></template>
            {{ t('home.quick.import') }}
          </AppButton>
          <AppButton variant="ghost" size="tiny" @click="go('/tasks?tab=runs')">
            <template #icon><AppIcon name="clock" size="sm" /></template>
            {{ t('home.quick.runs') }}
          </AppButton>
        </div>
      </AppCard>

      <!-- 系统状态 -->
      <AppCard :title="t('home.system.title')">
        <ul class="home-system">
          <li>
            <span class="home-system-label">{{ t('home.system.backend') }}</span>
            <AppBadge :tone="backendTone">
              <template #icon>
                <AppIcon name="dot" size="sm" />
              </template>
              {{ backendLabel }}
            </AppBadge>
          </li>
          <li>
            <span class="home-system-label">{{ t('home.system.tools') }}</span>
            <span class="home-system-value">{{ validToolCount }} / {{ tools.length }}</span>
          </li>
          <li>
            <span class="home-system-label">{{ t('home.system.envs') }}</span>
            <span class="home-system-value">{{ validEnvCount }} / {{ envs.length }}</span>
          </li>
        </ul>
      </AppCard>
    </div>

    <!-- 最近运行 -->
    <AppCard :title="t('home.recent.title')" flush-body>
      <div v-if="recentRuns.length === 0" class="home-recent-empty">
        <EmptyState :title="t('home.recent.empty')" :description="t('home.recent.emptyHint')">
          <template #actions>
            <AppButton variant="primary" size="tiny" @click="go('/workflows/editor')">
              {{ t('home.recent.goCreate') }}
            </AppButton>
          </template>
        </EmptyState>
      </div>

      <ul v-else class="home-runs">
        <li v-for="run in recentRuns" :key="run.run_id" class="home-run">
          <StatusBadge :status="runStatusOf(run)" />
          <span class="home-run-workflow">{{ run.workflow_name || '—' }}</span>
          <span class="home-run-task">{{ run.task_name || t('tasks.runs.oneShot') }}</span>
          <span class="home-run-time">{{ formatTime(run.started_at) }}</span>
          <span class="home-run-duration">{{ formatMs(run.duration_ms) }}</span>
        </li>
      </ul>
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppIcon from '@components/ui/AppIcon.vue'
import { storeToRefs } from 'pinia'

import AppBadge from '@components/ui/AppBadge.vue'
import AppButton from '@components/ui/AppButton.vue'
import AppCard from '@components/ui/AppCard.vue'
import AppNotice from '@components/ui/AppNotice.vue'
import EmptyState from '@components/ui/EmptyState.vue'
import PageHeader from '@components/ui/PageHeader.vue'
import StatCard from '@components/ui/StatCard.vue'
import StatusBadge from '@components/ui/StatusBadge.vue'
import { formatMs, runStatusOf } from '@components/tasks/runFormat'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import type { EnvEntry, RunSummary, TaskDefinitionSummary, ToolEntry } from '../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import { log } from '@utils/logger'

const { t } = useI18n()
const router = useRouter()
const health = useBackendHealthStore()
const { isHealthy } = storeToRefs(health)

const templates = ref<Array<{ name: string }>>([])
const tasks = ref<TaskDefinitionSummary[]>([])
const runs = ref<RunSummary[]>([])
const tools = ref<ToolEntry[]>([])
const envs = ref<EnvEntry[]>([])
const loading = ref(false)
const loaded = ref(false)
const loadError = ref('')

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

/** 近 7 天的运行（按 started_at 过滤；老记录的 started_at 可能为 null）。 */
const recentRunWindow = computed(() => {
  const cutoff = Date.now() - SEVEN_DAYS_MS
  return runs.value.filter((run) => {
    if (!run.started_at) return false
    const time = new Date(run.started_at).getTime()
    return !Number.isNaN(time) && time >= cutoff
  })
})

const recentRunCount = computed(() => recentRunWindow.value.length)

const failedRunCount = computed(
  () => recentRunWindow.value.filter((run) => runStatusOf(run) === 'failed').length,
)

/** 最近 5 条（history.list 已按时间倒序，这里再兜一次序以防后端换实现）。 */
const recentRuns = computed(() =>
  [...runs.value]
    .sort((a, b) => String(b.started_at ?? '').localeCompare(String(a.started_at ?? '')))
    .slice(0, 5),
)

const validToolCount = computed(() => tools.value.filter((tool) => tool.is_valid !== false).length)
const validEnvCount = computed(() => envs.value.filter((env) => env.is_valid).length)

const backendTone = computed<'success' | 'danger' | 'neutral'>(() => {
  if (isHealthy.value === null) return 'neutral'
  return isHealthy.value ? 'success' : 'danger'
})

const backendLabel = computed(() => {
  if (isHealthy.value === null) return t('home.system.backendUnknown')
  return isHealthy.value ? t('home.system.backendOk') : t('home.system.backendDown')
})

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

function go(path: string) {
  void router.push(path)
}

/**
 * 一次并行拉齐首页所需数据。用 allSettled：任一接口挂了只影响对应卡片，
 * 顶部给一条可重试的错误提示。
 */
async function load() {
  loading.value = true
  loadError.value = ''
  const results = await Promise.allSettled([
    unifiedApi.call<{ templates?: Array<{ name: string }> }>('template.list', {}),
    unifiedApi.call<{ tasks?: TaskDefinitionSummary[] }>('task.list'),
    unifiedApi.call<{ runs?: RunSummary[] }>('history.list', { limit: 100, offset: 0 }),
    unifiedApi.call<{ tools?: ToolEntry[] }>('workflow.list_tools', {}),
    unifiedApi.call<{ environments?: EnvEntry[] }>('env.list'),
  ])

  const [templateRes, taskRes, runRes, toolRes, envRes] = results
  const failures: string[] = []
  if (templateRes.status === 'fulfilled') templates.value = templateRes.value?.templates ?? []
  else failures.push('template.list')
  if (taskRes.status === 'fulfilled') tasks.value = taskRes.value?.tasks ?? []
  else failures.push('task.list')
  if (runRes.status === 'fulfilled') runs.value = runRes.value?.runs ?? []
  else failures.push('history.list')
  if (toolRes.status === 'fulfilled') tools.value = toolRes.value?.tools ?? []
  else failures.push('workflow.list_tools')
  if (envRes.status === 'fulfilled') envs.value = envRes.value?.environments ?? []
  else failures.push('env.list')

  if (failures.length > 0) {
    loadError.value = failures.join(', ')
    log.warn('[HomePage] some endpoints failed:', failures)
  }
  loading.value = false
  loaded.value = true
}

onMounted(() => {
  void health.check()
  void load()
})
</script>

<style scoped>
.home-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.home-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.home-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.home-system {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-system li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.home-system-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.home-system-value {
  font-family: var(--font-family-monospace);
  font-size: 12.5px;
  color: var(--text);
}

.home-recent-empty {
  display: flex;
  min-height: 220px;
}

.home-runs {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-run {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--border);
}

.home-run:last-child {
  border-bottom: 0;
}

.home-run-workflow {
  flex: none;
  width: 170px;
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-run-task {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 11.5px;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-run-time,
.home-run-duration {
  flex: none;
  font-family: var(--font-family-monospace);
  font-size: 11.5px;
  color: var(--text-muted);
}

.home-run-duration {
  width: 64px;
  text-align: right;
}

/* 平板：概览两列 */
@media (max-width: 1023px) {
  .home-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* 手机：全部单列，运行行折行 */
@media (max-width: 767px) {
  .home-stats,
  .home-cols {
    grid-template-columns: minmax(0, 1fr);
  }

  .home-run {
    flex-wrap: wrap;
    gap: 6px 10px;
  }

  .home-run-workflow {
    width: auto;
    flex: 1;
  }
}
</style>
