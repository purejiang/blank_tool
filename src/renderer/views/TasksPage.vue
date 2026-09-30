<template>
  <!-- 任务中心（docs/08 §2.1）：默认 tab 是**任务定义**，`?tab=runs` 是运行记录。
       两个 tab 是同一个任务对象的两种视图（与 /tools 三页的区段切换有意不同）。 -->
  <div class="screen tasks-page">
    <PageHeader :title="t('tasks.title')" :description="t('tasks.subtitle')" />

    <n-tabs :value="tab" type="line" size="small" @update:value="onTabChange">
      <n-tab-pane name="tasks" :tab="t('tasks.tabs.tasks')" />
      <n-tab-pane name="runs" :tab="t('tasks.tabs.runs')" />
    </n-tabs>

    <TaskListView
      v-if="tab === 'tasks'"
      @new-task="goNewTask"
      @edit-task="goEditTask"
      @view-runs="goRuns"
    />
    <RunListView
      v-else
      :initial-task="runTaskFilter"
      @new-task="goNewTask"
      @save-as-task="goSaveAsTask"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTabPane, NTabs } from 'naive-ui'

import TaskListView from '@components/tasks/TaskListView.vue'
import RunListView from '@components/tasks/RunListView.vue'
import PageHeader from '@components/ui/PageHeader.vue'
import type { RunRecord } from '../../shared/ipc/protocol'

/**
 * `/tasks` — tab shell over S3.1 (task definitions) and S4 (run records).
 *
 * The active tab and the run-list task filter live in the **query string**
 * (`?tab=runs&task=<name>`) so "查看运行记录" and the history page can be
 * linked to directly.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

type Tab = 'tasks' | 'runs'

const tab = computed<Tab>(() => (route.query.tab === 'runs' ? 'runs' : 'tasks'))
const runTaskFilter = computed(() =>
  typeof route.query.task === 'string' && route.query.task ? route.query.task : undefined,
)

function onTabChange(value: string) {
  const next: Tab = value === 'runs' ? 'runs' : 'tasks'
  void router.replace({
    path: '/tasks',
    query: next === 'runs' ? { tab: 'runs', ...(runTaskFilter.value ? { task: runTaskFilter.value } : {}) } : {},
  })
}

function goNewTask() {
  void router.push('/tasks/editor')
}

function goEditTask(id: string) {
  // 路由上是任务 id（显示名可以重复，按名字打开会认错任务）。
  void router.push(`/tasks/editor/${encodeURIComponent(id)}`)
}

function goRuns(taskRef: string) {
  void router.push({ path: '/tasks', query: { tab: 'runs', task: taskRef } })
}

/** S5「存为任务」：把工作流与本次入参预填到任务编辑页。 */
function goSaveAsTask(run: RunRecord) {
  void router.push({
    path: '/tasks/editor',
    query: {
      // 优先用工作流 id（按名字绑定在改名/重名后会失联）。
      workflow: run.workflow_id || run.workflow_name || '',
      inputs: JSON.stringify(run.inputs ?? {}),
    },
  })
}

// 旧链接/手写 query 兜底：`?tab` 非法值直接回到任务 tab。
watch(
  () => route.query.tab,
  (value) => {
    if (value !== undefined && value !== 'runs' && value !== 'tasks') {
      void router.replace({ path: '/tasks' })
    }
  },
)
</script>

<style scoped>
.tasks-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}


</style>
