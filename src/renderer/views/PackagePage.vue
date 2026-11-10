<template>
  <div class="package-page app-page">
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('package.title') }}</h1>
        <p class="app-page-sub">{{ t('package.subtitle') }}</p>
      </div>
    </div>

    <!-- New Task Bar -->
    <div class="new-task-bar">
      <div class="task-bar-row">
        <n-input
          v-model:value="newTarget"
          :placeholder="t('task.inputPlaceholder')"
          size="small"
          clearable
          class="task-source-input"
          @dragover.prevent
          @drop.prevent="onPathDrop"
        >
          <template #suffix>
            <IconButton
              v-if="!isUrlLike"
              :icon="FolderOpen"
              :label="needsDirectory ? t('task.selectDir') : t('task.selectFile')"
              size="tiny"
              text
              class="task-pick-btn"
              @click="pickLocalFile"
            />
          </template>
        </n-input>

        <n-select v-model:value="newOperation" :options="operationOptions" size="small" style="width:120px" />

        <n-tooltip :disabled="canStart" trigger="hover">
          <template #trigger>
            <span class="task-start-wrap">
              <n-button type="primary" size="small" @click="startNewTask" :disabled="!canStart">
                <template #icon><n-icon><Play /></n-icon></template>
                {{ t('task.start') }}
              </n-button>
            </span>
          </template>
          {{ startDisabledHint }}
        </n-tooltip>
      </div>

      <div class="task-bar-opts">
        <span class="op-desc">{{ t('task.' + newOperation + 'Desc') }}</span>

        <template v-if="newOperation === 'install'">
          <span class="op-label">{{ t('task.targetDevice') }}</span>
          <n-select
            v-model:value="installDeviceId"
            :options="deviceOptions"
            size="tiny"
            style="width:220px"
            :placeholder="t('task.selectDevice')"
            filterable
            @update:value="installDeviceTouched = true"
          />
        </template>

        <template v-if="newOperation === 'resign' || newOperation === 'recompile'">
          <span class="op-label">{{ t('task.signConfig') }}</span>
          <n-select v-model:value="newSignId" :options="signOptions" size="tiny" style="width:180px" :placeholder="t('signature.select')" />
        </template>

        <template v-if="newOperation === 'decompile'">
          <span class="op-label">{{ t('task.decompileOpts') }}</span>
          <n-checkbox v-model:checked="decompileResources" size="small">{{ t('task.decompileResources') }}</n-checkbox>
          <n-checkbox v-model:checked="decompileSources" size="small">{{ t('task.decompileSources') }}</n-checkbox>
        </template>
      </div>
    </div>

    <!-- Two-column task workspace -->
    <div class="workspace">
      <aside class="rail" :aria-label="t('task.railTitle')">
        <div class="rail-head">
          <div class="rail-title">{{ t('task.railTitle') }}</div>
          <IconButton
            :icon="Trash2"
            :label="taskStore.hasActive ? t('task.clearAllDisabledHint') : t('task.clearAll')"
            size="small"
            quaternary
            type="error"
            :disabled="taskStore.tasks.length === 0 || taskStore.hasActive"
            @click="confirmClearAll"
          />
        </div>

        <div class="rail-search">
          <n-input v-model:value="taskQuery" size="small" clearable :placeholder="t('task.searchPlaceholder')">
            <template #prefix><n-icon size="14"><Search /></n-icon></template>
          </n-input>
        </div>

        <div class="rail-filters" role="group" :aria-label="t('task.filterAll')">
          <button
            v-for="filter in filterDefs"
            :key="filter.key"
            type="button"
            class="rail-chip"
            :class="{ on: taskFilter === filter.key }"
            @click="taskFilter = filter.key"
          >
            {{ filter.label }} <span>{{ filterCounts[filter.key] }}</span>
          </button>
        </div>

        <div class="rail-list" role="listbox" :aria-label="t('task.railTitle')">
          <div v-if="taskStore.tasks.length === 0" class="rail-empty">
            <n-icon size="32" color="var(--app-text-dim)"><Inbox /></n-icon>
            <p>{{ t('task.empty') }}</p>
          </div>
          <div v-else-if="filteredTasks.length === 0" class="rail-empty">
            <n-icon size="28" color="var(--app-text-dim)"><Inbox /></n-icon>
            <p>{{ t('task.noMatch') }}</p>
          </div>

          <button
            v-for="task in filteredTasks"
            :key="task.id"
            type="button"
            class="task-item"
            :class="{ selected: task.id === selectedTaskId }"
            role="option"
            :aria-selected="task.id === selectedTaskId"
            :aria-label="taskAriaLabel(task)"
            @click="selectTask(task)"
          >
            <div class="file-tile" :class="taskKind(task)">
              <n-icon v-if="taskKind(task) === 'dir'" size="16"><FolderOpen /></n-icon>
              <template v-else>{{ taskKind(task).toUpperCase() }}</template>
            </div>
            <span class="ti-body">
              <span class="ti-row1">
                <span class="ti-name" :title="task.fileName">{{ task.fileName }}</span>
                <span class="ti-glyph" :class="statusClass(task)" :title="statusLabel(task)">
                  <n-icon size="13" :class="{ spin: statusSpin(task) }">
                    <component :is="statusIcon(task)" />
                  </n-icon>
                  <span class="sr-only">{{ statusLabel(task) }}</span>
                </span>
              </span>
              <span class="ti-row2">
                <n-tag :type="opTagType(task.operation)" size="tiny" :bordered="false">{{ task.operationLabel }}</n-tag>
                <n-icon size="11" class="ti-source" :title="task.source === 'url' ? t('task.urlSource') : t('task.localSource')">
                  <Link v-if="task.source === 'url'" />
                  <FolderOpen v-else />
                </n-icon>
                <span class="ti-time" :title="fmtDateTime(task.createdAt)">{{ fmtRelative(task.createdAt) }}</span>
              </span>
            </span>
            <span v-if="task.status === 'downloading'" class="ti-progress"><i :style="{ width: Math.max(2, task.progress) + '%' }"></i></span>
            <span v-else-if="task.status === 'running' || task.status === 'cancelling'" class="ti-progress indeterminate"><i></i></span>
            <span class="ti-id" :title="`#${task.id}`">#{{ task.id }}</span>
          </button>
        </div>
      </aside>

      <section v-if="selectedTask" class="detail">
        <div class="detail-head">
          <div class="file-tile lg" :class="taskKind(selectedTask)">
            <n-icon v-if="taskKind(selectedTask) === 'dir'" size="20"><FolderOpen /></n-icon>
            <template v-else>{{ taskKind(selectedTask).toUpperCase() }}</template>
          </div>
          <div class="dh-main">
            <div class="dh-title-row">
              <h2 class="dh-title">{{ selectedTask.fileName }}</h2>
              <span class="status-pill" :class="statusClass(selectedTask)">
                <n-icon v-if="statusShowIcon(selectedTask)" size="11" :class="{ spin: statusSpin(selectedTask) }">
                  <component :is="statusIcon(selectedTask)" />
                </n-icon>
                {{ statusLabel(selectedTask) }}
              </span>
            </div>
            <div class="dh-path">
              <n-icon size="12"><Link v-if="selectedTask.source === 'url'" /><FolderOpen v-else /></n-icon>
              <span class="path-text" :title="taskPath(selectedTask)">{{ taskPath(selectedTask) }}</span>
              <span class="path-actions">
                <IconButton :icon="Copy" :label="t('task.copyPath')" size="tiny" quaternary @click="copyTaskPath(selectedTask)" />
                <IconButton
                  v-if="selectedTask.source === 'local'"
                  :icon="ExternalLink"
                  :label="t('common.openInFolder')"
                  size="tiny"
                  quaternary
                  @click="openTaskSource(selectedTask)"
                />
              </span>
            </div>
            <div class="dh-badges">
              <n-tag :type="opTagType(selectedTask.operation)" size="tiny" :bordered="false">{{ selectedTask.operationLabel }}</n-tag>
              <span class="soft-tag">{{ selectedTask.source === 'url' ? t('task.urlSource') : t('task.localSource') }}</span>
            </div>
          </div>
          <div class="dh-actions">
            <IconButton
              v-if="isActiveTask(selectedTask)"
              :icon="StopCircle"
              :label="t('task.cancel')"
              size="small"
              quaternary
              type="warning"
              @click="cancelTask(selectedTask)"
            />
            <template v-else-if="isTerminalTask(selectedTask)">
              <IconButton :icon="RefreshCw" :label="t('task.rerunFromStart')" size="small" quaternary type="warning" @click="retryTask(selectedTask)" />
              <IconButton :icon="Trash2" :label="t('task.delete')" size="small" quaternary type="error" @click="confirmRemoveTask(selectedTask)" />
            </template>
          </div>
        </div>

        <div class="detail-tabs">
          <div class="detail-tab-list" role="tablist">
            <button
              type="button"
              class="detail-tab"
              :class="{ active: activeDetailTab === 'process' }"
              role="tab"
              :aria-selected="activeDetailTab === 'process'"
              aria-controls="task-detail-panel"
              @click="setDetailTab('process')"
            >{{ t('task.tabProcess') }}</button>
            <button
              type="button"
              class="detail-tab"
              :class="{ active: activeDetailTab === 'info' }"
              role="tab"
              :aria-selected="activeDetailTab === 'info'"
              aria-controls="task-detail-panel"
              @click="setDetailTab('info')"
            >
              {{ t('task.tabInfoLogs') }}
              <span v-if="isLiveTask(selectedTask)" class="tab-live" aria-hidden="true"></span>
            </button>
          </div>
          <span v-if="showTaskTimer(selectedTask)" class="detail-timer" role="timer">
            <span class="timer-label">{{ taskTimerLabel(selectedTask) }}</span>
            <span class="timer-value">{{ taskTimerValue(selectedTask) }}</span>
          </span>
        </div>

        <div id="task-detail-panel" class="detail-scroll" :class="{ 'detail-scroll--fill': detailFills(selectedTask) }" role="tabpanel">
          <template v-if="activeDetailTab === 'process'">
            <div
              v-if="selectedPhaseSteps.length"
              class="phase-strip"
              :class="{ 'phase-strip--download': selectedTask.status === 'downloading' }"
              :aria-label="t('task.phases')"
            >
              <template v-for="(step, index) in selectedPhaseSteps" :key="`${selectedTask.id}-${index}`">
                <span v-if="index > 0" class="phase-line" :class="{ done: selectedPhaseSteps[index - 1].state === 'done' }"></span>
                <span class="phase-step" :class="step.state">
                  <span class="phase-dot">
                    <n-icon v-if="step.state === 'done'" size="9"><CheckCircle /></n-icon>
                    <n-icon v-else-if="step.state === 'current'" size="9" class="spin"><Loader /></n-icon>
                    <n-icon v-else-if="step.state === 'failed'" size="9"><XCircle /></n-icon>
                  </span>
                  <span class="phase-label">{{ step.label }}</span>
                </span>
              </template>
            </div>

            <div v-if="isActiveTask(selectedTask)" class="process-center">
              <div class="process-loading" role="status" :aria-label="loadingLabel(selectedTask)">
                <div
                  v-if="selectedTask.status === 'downloading'"
                  class="loading-progress-circle"
                  :style="{ '--pct': selectedTask.progress }"
                >
                  <span class="loading-percent">{{ selectedTask.progress }}%</span>
                </div>
                <span v-else-if="selectedTask.status === 'queued'" class="loading-queued-circle">
                  <n-icon size="26"><Clock /></n-icon>
                </span>
                <span v-else class="loading-spinner" :class="{ yellow: selectedTask.status === 'cancelling' }"></span>
                <span class="loading-label">{{ loadingLabel(selectedTask) }}</span>
              </div>
            </div>

            <div v-else-if="selectedTask.status === 'failed'" class="process-center">
              <div class="error-card">
                <div class="error-label"><n-icon size="13"><XCircle /></n-icon>{{ t('task.failedReason') }}</div>
                <div class="error-msg">{{ selectedTask.error || t('task.operationFailed') }}</div>
                <div class="error-hint">{{ taskFailureHint(selectedTask) }}</div>
                <div class="error-actions">
                  <n-button type="primary" size="small" @click="retryFailedStage(selectedTask)">
                    <template #icon><n-icon><RotateCcw /></n-icon></template>
                    {{ t('task.retryStage') }}
                  </n-button>
                </div>
              </div>
            </div>

            <div v-else-if="selectedTask.status === 'cancelled'" class="process-center">
              <div class="cancelled-card">{{ t('task.cancelledHint') }}</div>
            </div>

            <template v-else-if="selectedTask.status === 'completed' && selectedTask.operation === 'analyze'">
              <div class="section-head">
                <div class="section-title"><n-icon size="14"><Package /></n-icon>{{ t('task.analysisResult') }}</div>
                <div v-if="selectedTask.result" class="section-actions">
                  <n-button size="small" quaternary @click="exportReport(selectedTask)">
                    <template #icon><n-icon><FileDown /></n-icon></template>
                    {{ t('task.exportReport') }}
                  </n-button>
                </div>
              </div>

              <template v-if="selectedAnalyzeSummary">
                <div class="report-hero">
                  <img
                    v-if="selectedAppIcon"
                    class="app-icon-big"
                    :src="selectedAppIcon"
                    :alt="selectedAnalyzeSummary.appLabel"
                  />
                  <div v-else class="app-icon-big">{{ appIconInitial(selectedTask) }}</div>
                  <div class="rh-main">
                    <div class="rh-name">{{ selectedAnalyzeSummary.appLabel }}</div>
                    <div class="rh-pkg" :title="selectedAnalyzeSummary.pkg">{{ selectedAnalyzeSummary.pkg }}</div>
                    <div class="rh-chips">
                      <span class="chip-static">{{ t('task.version') }} {{ selectedAnalyzeSummary.version }}<template v-if="selectedAnalyzeSummary.code"> ({{ selectedAnalyzeSummary.code }})</template></span>
                      <span class="chip-static">minSdk {{ selectedAnalyzeSummary.minSdk }}</span>
                      <span class="chip-static">targetSdk {{ selectedAnalyzeSummary.targetSdk }}</span>
                      <span class="chip-static">{{ selectedAnalyzeSummary.sizeText }}</span>
                    </div>
                  </div>
                </div>

                <div class="stat-grid">
                  <div class="stat-tile">
                    <div class="stat-label">{{ t('task.permissions') }}</div>
                    <div class="stat-value">{{ selectedAnalyzeSummary.permissions }}</div>
                    <div class="stat-note danger">{{ t('task.dangerPermCount', { count: selectedAnalyzeSummary.dangerous }) }}</div>
                  </div>
                  <div class="stat-tile">
                    <div class="stat-label">{{ t('task.signature') }}</div>
                    <div class="stat-value">
                      {{ selectedAnalyzeSummary.signed === null ? '—' : selectedAnalyzeSummary.signed ? t('task.signed') : t('task.unsigned') }}
                    </div>
                    <div class="stat-note ok">
                      {{ selectedTask.resultData?.sig_sha256 && selectedTask.resultData.sig_sha256 !== '-' ? 'SHA256' : '' }}
                    </div>
                  </div>
                  <div class="stat-tile">
                    <div class="stat-label">{{ t('task.nativeAnalysis') }}</div>
                    <div class="stat-value">{{ selectedAnalyzeSummary.soCount }} <small>.so</small></div>
                    <div class="stat-note">{{ selectedAnalyzeSummary.archCount }} {{ t('task.architecture') }}</div>
                  </div>
                  <div class="stat-tile">
                    <div class="stat-label">{{ t('task.compressionAnalysis') }}</div>
                    <div class="stat-value">{{ selectedAnalyzeSummary.compressionRate }}</div>
                    <div class="stat-note">{{ t('task.compressionRateHint') }}</div>
                  </div>
                </div>
              </template>

              <div v-if="selectedTask.result" class="task-report" @click="onResultClick" v-html="selectedTask.result"></div>
              <div v-else class="app-empty-hint">{{ t('task.reportUnavailable') }}</div>
            </template>

            <template v-else-if="selectedTask.status === 'completed'">
              <div class="section-head">
                <div class="section-title">
                  <n-icon size="14"><component :is="selectedTask.operation === 'install' ? Smartphone : Package" /></n-icon>
                  {{ selectedTask.operation === 'install' ? t('task.installResult') : t('task.artifact') }}
                </div>
                <div v-if="selectedTask.outputPath" class="section-actions">
                  <n-button size="small" quaternary @click="openTaskOutput(selectedTask)">
                    <template #icon><n-icon><FolderOpen /></n-icon></template>
                    {{ t('task.openOutput') }}
                  </n-button>
                </div>
              </div>
              <div class="output-card">
                <div v-if="selectedTask.operation === 'install'" class="output-row">
                  <span class="output-key">{{ t('task.targetDevice') }}</span>
                  <span class="output-device"><n-icon size="14"><Smartphone /></n-icon>{{ selectedTask.deviceLabel || '—' }}</span>
                </div>
                <div v-if="selectedTask.outputPath" class="output-row">
                  <span class="output-key">{{ selectedTask.operation === 'decompile' ? t('task.outputDir') : t('task.outputFile') }}</span>
                  <span class="output-path" :title="selectedTask.outputPath">{{ selectedTask.outputPath }}</span>
                  <IconButton :icon="Copy" :label="t('task.copyPath')" size="tiny" quaternary @click="copyPathValue(selectedTask.outputPath)" />
                </div>
                <div v-if="selectedTask.operation === 'decompile'" class="output-row">
                  <span class="output-key">{{ t('task.decompiledItems') }}</span>
                  <span class="output-tags">
                    <span class="soft-tag">{{ t('task.decompileResources') }}</span>
                    <span class="soft-tag">{{ t('task.decompileSources') }}</span>
                  </span>
                </div>
              </div>
            </template>
          </template>

          <template v-else>
            <div class="section-head">
              <div class="section-title"><n-icon size="14"><Activity /></n-icon>{{ t('task.taskInfo') }}</div>
            </div>
            <div class="info-card">
              <div class="info-kv"><div class="info-k">{{ t('task.createdAt') }}</div><div class="info-v mono">{{ fmtDateTime(selectedTask.createdAt) }}</div></div>
              <div class="info-kv"><div class="info-k">{{ t('task.startedAt') }}</div><div class="info-v mono">{{ fmtDateTime(selectedTask.startedAt || selectedTask.createdAt) }}</div></div>
              <div class="info-kv"><div class="info-k">{{ t('task.finishedAt') }}</div><div class="info-v mono">{{ selectedTask.finishedAt ? fmtDateTime(selectedTask.finishedAt) : '—' }}</div></div>
              <div class="info-kv"><div class="info-k">{{ t('task.fileSize') }}</div><div class="info-v">{{ fileSizeText(selectedTask) }}</div></div>
            </div>

            <div class="log-card fill">
              <div class="log-head">
                <div class="log-title">{{ t('task.logTitle') }} <span class="log-count">{{ displayLog(selectedTask).length }} {{ t('task.logLines') }}</span></div>
                <div class="log-actions">
                  <IconButton
                    :icon="Search"
                    :label="t('task.logSearch')"
                    size="tiny"
                    quaternary
                    :type="logSearchOpenMap.get(selectedTask.id) ? 'info' : 'default'"
                    @click="toggleLogSearch(selectedTask)"
                  />
                  <IconButton :icon="Copy" :label="t('task.copyLog')" size="tiny" quaternary @click="copyLog(selectedTask)" />
                  <IconButton :icon="Download" :label="t('task.exportLog')" size="tiny" quaternary @click="exportTaskLog(selectedTask)" />
                </div>
              </div>
              <n-input
                v-if="logSearchOpenMap.get(selectedTask.id)"
                :value="logSearchMap.get(selectedTask.id) || ''"
                :placeholder="t('task.logSearch')"
                size="tiny"
                clearable
                class="log-search-input"
                @update:value="(value: string) => logSearchMap.set(selectedTask.id, value)"
              />
              <div v-if="logTruncatedMap.get(selectedTask.id)" class="log-trunc-hint">{{ t('task.logTruncatedHint') }}</div>
              <div class="log-body" tabindex="0">
                <n-virtual-list
                  :ref="(el: any) => onLogListRef(selectedTask.id, el)"
                  :key="'log-' + selectedTask.id"
                  :items="displayLog(selectedTask)"
                  :item-size="18"
                  item-resizable
                  style="height: 100%"
                >
                  <template #default="{ item }">
                    <div class="log-line">{{ item.text }}</div>
                  </template>
                </n-virtual-list>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section v-else class="detail detail-empty">
        <div class="empty-icon"><n-icon size="26"><Inbox /></n-icon></div>
        <h3>{{ t('task.selectTask') }}</h3>
        <p>{{ t('task.selectTaskDesc') }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NVirtualList, useDialog, NInput } from 'naive-ui'
import {
  Play, Link, FolderOpen, CheckCircle, XCircle, Loader,
  ChevronDown, ChevronRight, Trash2, Inbox, ExternalLink, StopCircle, AlertCircle, Download, RefreshCw, Smartphone,
  Search, Copy, RotateCcw, FileDown, Clock, Package, Activity
} from 'lucide-vue-next'
import { useNotification } from '@composables/useNotification'
import { useTaskStore } from '@stores/index'
import { useSignatureStore } from '@stores/signatureStore'
import { useDeviceStore } from '@stores/deviceStore'
import type { Task } from '@stores/taskStore'
import { formatDuration as formatDurationUtil } from '@utils/formatDuration'
import { formatBytes } from '@utils/format'
import { log as logUtil } from '@utils/logger'
import serviceManager from '@services/ServiceManager'
import { colorTokens, staticTokens } from '@/theme/tokens'
import { enqueueTask } from '@services/TaskExecutionService'
import IconButton from '@components/common/IconButton.vue'

const { t, locale } = useI18n()
const dialog = useDialog()
const taskStore = useTaskStore()
const sigStore = useSignatureStore()
const deviceStore = useDeviceStore()
if (sigStore.configs.length === 0) sigStore.loadConfigs()

const { showError, showWarning, showSuccess, showInfo } = useNotification()

const OP_TAG_MAP: Record<Task['operation'], string> = {
  analyze: 'info', install: 'success', decompile: 'warning', recompile: 'warning', resign: 'error'
}

// Permissions Android treats as dangerous. Shared by renderApkInfo() and the
// right-pane summary tiles so the two never drift apart.
const DANGEROUS_PERMISSIONS = new Set([
  'android.permission.READ_CONTACTS', 'android.permission.WRITE_CONTACTS', 'android.permission.GET_ACCOUNTS',
  'android.permission.READ_CALENDAR', 'android.permission.WRITE_CALENDAR',
  'android.permission.CAMERA',
  'android.permission.BODY_SENSORS',
  'android.permission.ACCESS_FINE_LOCATION', 'android.permission.ACCESS_COARSE_LOCATION', 'android.permission.ACCESS_BACKGROUND_LOCATION',
  'android.permission.RECORD_AUDIO',
  'android.permission.READ_PHONE_STATE', 'android.permission.READ_PHONE_NUMBERS', 'android.permission.CALL_PHONE', 'android.permission.ANSWER_PHONE_CALLS',
  'android.permission.READ_CALL_LOG', 'android.permission.WRITE_CALL_LOG',
  'android.permission.SEND_SMS', 'android.permission.RECEIVE_SMS', 'android.permission.READ_SMS', 'android.permission.RECEIVE_MMS', 'android.permission.RECEIVE_WAP_PUSH',
  'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE', 'android.permission.MANAGE_EXTERNAL_STORAGE',
  'android.permission.ACTIVITY_RECOGNITION',
  'android.permission.BLUETOOTH_CONNECT', 'android.permission.BLUETOOTH_SCAN', 'android.permission.BLUETOOTH_ADVERTISE',
  'android.permission.POST_NOTIFICATIONS',
  'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_MEDIA_AUDIO',
  'android.permission.NEARBY_WIFI_DEVICES',
  'android.permission.UWB_RANGING',
])

const activeIntervals = new Set<ReturnType<typeof setInterval>>()


// Reactive clock for real-time duration display.
// Updated every 1s when there are active (non-terminal) tasks.
const now = ref(Date.now())
let nowIv: ReturnType<typeof setInterval> | null = null
const taskLogCache = ref<Map<number, { key: number; text: string }[]>>(new Map())
// Per-task inline log search state + virtual-list refs
const logSearchMap = ref<Map<number, string>>(new Map())
const logSearchOpenMap = ref<Map<number, boolean>>(new Map())
// Per-task flag: log panel default-truncates (tail 100KB); export yields the full file.
const logTruncatedMap = ref<Map<number, boolean>>(new Map())
const logListRefs = new Map<number, any>()

/* ======================= v2 task workspace state ======================= */

type TaskFilter = 'all' | 'active' | 'completed' | 'failed'
type DetailTab = 'process' | 'info'

const selectedTaskId = ref<number | null>(null)
const detailTabs = ref<Record<number, DetailTab>>({})
const taskQuery = ref('')
const taskFilter = ref<TaskFilter>('all')
const relativeNow = ref(Date.now())
let relativeIv: ReturnType<typeof setInterval> | null = null
const appIconMap = ref<Map<number, string>>(new Map())

const selectedTask = computed(() => taskStore.tasks.find((task) => task.id === selectedTaskId.value) || null)
const activeDetailTab = computed<DetailTab>(() => {
  const task = selectedTask.value
  return task ? (detailTabs.value[task.id] || 'process') : 'process'
})
const filterDefs = computed(() => [
  { key: 'all' as TaskFilter, label: t('task.filterAll') },
  { key: 'active' as TaskFilter, label: t('task.filterActive') },
  { key: 'completed' as TaskFilter, label: t('task.filterCompleted') },
  { key: 'failed' as TaskFilter, label: t('task.filterFailed') },
])
const filterCounts = computed(() => ({
  all: taskStore.tasks.length,
  active: taskStore.tasks.filter((task) => isActiveTask(task)).length,
  completed: taskStore.tasks.filter((task) => task.status === 'completed').length,
  failed: taskStore.tasks.filter((task) => task.status === 'failed' || task.status === 'cancelled').length,
}))
const filteredTasks = computed(() => {
  const query = taskQuery.value.trim().toLowerCase()
  return taskStore.tasks.filter((task) => {
    const matchesFilter =
      taskFilter.value === 'all' ? true
        : taskFilter.value === 'active' ? isActiveTask(task)
        : taskFilter.value === 'completed' ? task.status === 'completed'
        : task.status === 'failed' || task.status === 'cancelled'
    if (!matchesFilter) return false
    if (!query) return true
    return `${task.fileName} ${task.filePath || ''} ${task.url || ''}`.toLowerCase().includes(query)
  })
})
const selectedPhaseSteps = computed(() => (selectedTask.value ? phaseSteps(selectedTask.value) : []))
const selectedAnalyzeSummary = computed(() => (selectedTask.value ? analyzeSummary(selectedTask.value) : null))
const selectedAppIcon = computed(() => (selectedTask.value ? appIconMap.value.get(selectedTask.value.id) || '' : ''))

function isActiveTask(task: Task): boolean {
  return ['queued', 'downloading', 'running', 'cancelling'].includes(task.status)
}
function isLiveTask(task: Task): boolean {
  return ['downloading', 'running', 'cancelling'].includes(task.status)
}
function isTerminalTask(task: Task): boolean {
  return isTerminal(task.status)
}

function statusLabel(task: Task): string {
  return (t(`task.${task.status}`) as string).replace(/\.+$/, '')
}
function statusClass(task: Task): string {
  return task.status
}
function statusSpin(task: Task): boolean {
  return task.status === 'running' || task.status === 'cancelling'
}
function statusShowIcon(task: Task): boolean {
  return task.status !== 'running' && task.status !== 'cancelling'
}
function statusIcon(task: Task) {
  switch (task.status) {
    case 'running':
    case 'cancelling':
      return Loader
    case 'downloading':
      return Download
    case 'completed':
      return CheckCircle
    case 'failed':
      return XCircle
    case 'cancelled':
      return AlertCircle
    default:
      return Clock
  }
}

function taskKind(task: Task): 'apk' | 'aab' | 'dir' {
  if (task.operation === 'recompile') return 'dir'
  const ext = task.fileName.split('.').pop()?.toLowerCase()
  return ext === 'aab' ? 'aab' : 'apk'
}
function taskAriaLabel(task: Task): string {
  return `${task.fileName}，#${task.id}，${statusLabel(task)}，${task.operationLabel}`
}
function taskPath(task: Task): string {
  return task.filePath || task.url || ''
}
function fileSizeText(task: Task): string {
  return task.fileSize ? formatBytes(task.fileSize) : '—'
}
function taskFailureHint(task: Task): string {
  return task.operation === 'resign' ? t('task.failedHintResign') : t('task.failedHint')
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}
function fmtDateTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}
function fmtRelative(ts: number): string {
  const diff = Math.max(0, relativeNow.value - ts)
  if (diff < 60000) return t('task.justNow') as string
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return t('task.minutesAgo', { count: mins }) as string
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return t('task.hoursAgo', { count: hrs }) as string
  const days = Math.floor(hrs / 24)
  if (days === 1) return t('task.yesterday') as string
  if (days < 7) return t('task.daysAgo', { count: days }) as string
  return formatTime(ts)
}
function fmtElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0
  const total = Math.floor(ms / 1000)
  const hrs = Math.floor(total / 3600)
  const mins = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return hrs > 0 ? `${hrs}:${pad2(mins)}:${pad2(secs)}` : `${pad2(mins)}:${pad2(secs)}`
}

/** 实时计时：排队不计时；开始后显示「已用时」，结束后冻结为「耗时」。 */
function showTaskTimer(task: Task): boolean {
  return task.status !== 'queued'
}
function taskTimerLabel(task: Task): string {
  return isTerminalTask(task) ? t('task.duration') : t('task.elapsed')
}
function taskTimerValue(task: Task): string {
  const end = task.finishedAt ?? now.value
  const start = task.startedAt || task.createdAt
  return fmtElapsed(end - start)
}

function loadingLabel(task: Task): string {
  if (task.status === 'downloading') return t('task.downloading') as string
  if (task.status === 'queued') return `${t('task.queued')}...`
  if (task.status === 'cancelling') return t('task.cancelling') as string
  const keyByOp: Record<Task['operation'], string> = {
    analyze: 'analyzing',
    install: 'installing',
    decompile: 'decompiling',
    recompile: 'recompiling',
    resign: 'resigningLoading',
  }
  return t(`task.${keyByOp[task.operation]}`) as string
}

interface PhaseStep {
  label: string
  state: 'done' | 'current' | 'pending' | 'failed'
}
function phaseSteps(task: Task): PhaseStep[] {
  if (task.status === 'completed' || task.status === 'cancelled' || task.status === 'queued') return []
  const steps: PhaseStep[] = [{ label: t('task.phaseQueue') as string, state: 'pending' }]
  if (task.source === 'url') steps.push({ label: t('task.download') as string, state: 'pending' })
  steps.push({ label: t(`task.${task.operation}`) as string, state: 'pending' })
  const opIndex = task.source === 'url' ? 2 : 1
  if (task.status === 'downloading') {
    steps[0].state = 'done'
    steps[1].state = 'current'
  } else if (task.status === 'running' || task.status === 'cancelling') {
    for (let i = 0; i < opIndex; i++) steps[i].state = 'done'
    steps[opIndex].state = 'current'
  } else if (task.status === 'failed') {
    const failIndex = task.failedPhase === 'download' && task.source === 'url' ? 1 : opIndex
    for (let i = 0; i < failIndex; i++) steps[i].state = 'done'
    steps[failIndex].state = 'failed'
  }
  return steps
}

interface AnalyzeSummary {
  appLabel: string
  pkg: string
  version: string
  code: string
  minSdk: string
  targetSdk: string
  sizeText: string
  permissions: number
  dangerous: number
  signed: boolean | null
  soCount: number
  archCount: number
  compressionRate: string
}
function analyzeSummary(task: Task): AnalyzeSummary | null {
  const data = task.resultData
  if (!data) return null
  const permissions: string[] = Array.isArray(data.permissions) ? data.permissions : []
  const dangerous = permissions.filter((permission) => DANGEROUS_PERMISSIONS.has(permission)).length
  const soComp = data.so_comparison || {}
  const archCount = soComp.arches
    ? Object.keys(soComp.arches).length
    : Array.isArray(data.native_libs) ? data.native_libs.length : 0
  const soCount = Array.isArray(soComp.baseline) && soComp.baseline.length
    ? soComp.baseline.length
    : soComp.arches
      ? Object.values(soComp.arches).reduce((total: number, arch: any) => total + (arch?.count || arch?.so_files?.length || 0), 0)
      : archCount
  const compression = data.compression_analysis || {}
  let raw = 0
  let zip = 0
  for (const entry of Object.values(compression) as any[]) {
    raw += Number(entry?.uncompressed) || 0
    zip += Number(entry?.compressed) || 0
  }
  const compressionRate = raw > 0 ? `${((zip / raw) * 100).toFixed(1)}%` : '—'
  const signed = data.is_bundle
    ? null
    : !!(data.sig_md5 && data.sig_md5 !== '-' && data.sig_sha1 && data.sig_sha1 !== '-' && data.sig_sha256 && data.sig_sha256 !== '-')
  const size = data.file_size || task.fileSize
  return {
    appLabel: data.application_label || '—',
    pkg: data.package_name || '',
    version: data.version_name || '—',
    code: data.version_code || '',
    minSdk: data.min_sdk_version || '—',
    targetSdk: data.target_sdk_version || '—',
    sizeText: size ? formatBytes(size) : '—',
    permissions: permissions.length,
    dangerous,
    signed,
    soCount,
    archCount,
    compressionRate,
  }
}

function appIconInitial(task: Task): string {
  const data = task.resultData
  const label = String(data?.application_label || task.fileName || 'A').trim()
  return (label.charAt(0) || 'A').toUpperCase()
}

async function ensureAppIcon(task: Task) {
  if (!task || task.operation !== 'analyze' || appIconMap.value.has(task.id)) return
  const raw = task.resultData?.app_icon
  if (!raw || raw === '-') {
    appIconMap.value.set(task.id, '')
    return
  }
  if (String(raw).startsWith('data:')) {
    appIconMap.value.set(task.id, String(raw))
    return
  }
  appIconMap.value.set(task.id, '')
  try {
    const api = window.electronAPI as any
    if (!api?.readImageAsDataURL) return
    const result = await api.readImageAsDataURL(String(raw))
    if (result?.success && result.dataUrl) appIconMap.value.set(task.id, result.dataUrl)
  } catch {
    // Keep the letter fallback.
  }
}

function getDetailTab(task: Task): DetailTab {
  return detailTabs.value[task.id] || 'process'
}
function selectTask(task: Task) {
  selectedTaskId.value = task.id
  void ensureAppIcon(task)
  if (getDetailTab(task) === 'info') void ensureTaskLog(task)
}
function setDetailTab(tab: DetailTab) {
  const task = selectedTask.value
  if (!task) return
  detailTabs.value[task.id] = tab
  if (tab === 'info') void ensureTaskLog(task)
}
async function ensureTaskLog(task: Task) {
  if (!task) return
  if (isTerminalTask(task) && !taskLogCache.value.has(task.id)) await loadTaskLog(task)
  await nextTick()
  scrollLogToBottom(task.id)
}
function detailFills(task: Task): boolean {
  return activeDetailTab.value === 'info'
    || isActiveTask(task)
    || task.status === 'failed'
    || task.status === 'cancelled'
}

async function copyPathValue(value: string) {
  if (!value) return
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(value)
    }
    showSuccess(t('task.copyPath'), value)
  } catch (e) {
    showWarning(t('task.copyPath'), String(e))
  }
}
function copyTaskPath(task: Task) {
  void copyPathValue(taskPath(task))
}
function openTaskSource(task: Task) {
  if (task.source === 'local' && task.filePath) {
    void openInExplorerChecked(task.filePath, t('task.source'), t('task.sourceFileMissing'))
  }
}
function openTaskOutput(task: Task) {
  if (task.outputPath) {
    void openInExplorerChecked(task.outputPath, t('task.output'), t('task.outputMissing'))
  }
}
function selectNextTask() {
  const next = filteredTasks.value[0] || taskStore.tasks[0] || null
  selectedTaskId.value = next?.id ?? null
}

/** Toggle the inline log search box; closing it clears the active filter. */
function toggleLogSearch(task: Task) {
  const open = !logSearchOpenMap.value.get(task.id)
  logSearchOpenMap.value.set(task.id, open)
  if (!open) logSearchMap.value.set(task.id, '')
}

function getLogArray(task: Task): { key: number; text: string }[] {
  if (isTerminal(task.status) && taskLogCache.value.has(task.id) && taskLogCache.value.get(task.id)?.length) {
    return taskLogCache.value.get(task.id)!
  }
  return task.logs.map((text, i) => ({ key: i, text }))
}

function displayLog(task: Task): { key: number; text: string }[] {
  const arr = getLogArray(task)
  const q = (logSearchMap.value.get(task.id) || '').trim().toLowerCase()
  if (!q) return arr
  return arr.filter((l) => l.text.toLowerCase().includes(q))
}

function onLogListRef(taskId: number, el: any) {
  if (el) logListRefs.set(taskId, el)
  else logListRefs.delete(taskId)
}

function scrollLogToBottom(taskId: number) {
  const task = taskStore.tasks.find((t) => t.id === taskId)
  if (!task) return
  const el = logListRefs.get(taskId)
  if (!el || typeof el.scrollTo !== 'function') return
  const len = displayLog(task).length
  if (len > 0) {
    try { el.scrollTo({ index: len - 1 }) } catch { /* ignore */ }
  }
}

async function copyLog(task: Task) {
  const lines = displayLog(task).map((l) => l.text)
  if (lines.length === 0) return
  const text = lines.join('\n')
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(text)
    }
    showSuccess(t('task.copyLog'), t('task.logCopied'))
  } catch (e) {
    showWarning(t('task.copyLog'), String(e))
  }
}

// Delegated click handler for the analysis result card (rendered via v-html).
// - Clicking the app icon (`.apk-icon`) opens a lightbox zoom.
// - Clicking any element carrying `data-copy` copies that value to the
//   clipboard; `data-fb-hash` is kept as a fallback.
let lightboxKeyHandler: ((ev: KeyboardEvent) => void) | null = null

function openIconLightbox(src: string) {
  if (!src) return
  let overlay = document.getElementById('apk-icon-lightbox') as HTMLElement | null
  if (!overlay) {
    overlay = document.createElement('div')
    overlay.id = 'apk-icon-lightbox'
    overlay.className = 'apk-lightbox'
    overlay.addEventListener('click', closeIconLightbox)
    document.body.appendChild(overlay)
  }
  overlay.innerHTML = `<img class="apk-lightbox-img" src="${src}" alt="app icon">`
  overlay.style.display = 'flex'
  lightboxKeyHandler = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape') closeIconLightbox()
  }
  document.addEventListener('keydown', lightboxKeyHandler)
}

function closeIconLightbox() {
  const overlay = document.getElementById('apk-icon-lightbox')
  if (overlay) overlay.style.display = 'none'
  if (lightboxKeyHandler) {
    document.removeEventListener('keydown', lightboxKeyHandler)
    lightboxKeyHandler = null
  }
}

function onResultClick(e: MouseEvent) {
  const el = e.target as HTMLElement | null
  // App icon → lightbox zoom (handled first so it doesn't trigger copy).
  const icon = el?.closest?.('.apk-icon') as HTMLImageElement | null
  if (icon && icon.src) {
    // The icon lives inside <summary>, so stop the click from also toggling
    // the parent <details> open/closed when we only want the lightbox.
    e.preventDefault()
    e.stopPropagation()
    openIconLightbox(icon.src)
    return
  }
  const node = el?.closest?.('[data-copy], [data-fb-hash]') as HTMLElement | null
  const value = node?.getAttribute('data-copy') ?? node?.getAttribute('data-fb-hash')
  if (!value) return
  const copy = async () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(value)
      else throw new Error('clipboard unavailable')
    }
  }
  copy()
    .then(() => showSuccess(t('task.copyLog'), t('task.logCopied')))
    .catch((err) => showWarning(t('task.copyLog'), String(err)))
}

// Lazy-load APK launcher icons whose path is persisted in task.result (instead
// of an inline base64 blob). For each <img data-icon-path> we fetch the bytes
// via IPC and inline them as a data URL, then drop the attribute so the pass
// is idempotent. Falls back silently when the file is gone (e.g. task deleted).
function fallbackIcon(img: HTMLImageElement) {
  const alt = img.getAttribute('alt') || ''
  const ch = (alt.trim()[0] || 'A').toUpperCase()
  const span = document.createElement('span')
  span.className = 'apk-icon apk-icon--fallback'
  span.textContent = ch
  span.title = img.getAttribute('title') || ''
  img.replaceWith(span)
}

// Lazy-load APK launcher icons whose path is persisted in task.result (instead
// of an inline base64 blob). For each <img data-icon-path> we fetch the bytes
// via IPC and inline them as a data URL, then drop the attribute so the pass
// is idempotent. Falls back to a letter tile when the file is gone (e.g. task deleted).
function hydrateResultIcons() {
  const imgs = document.querySelectorAll('.task-report img.apk-icon[data-icon-path]') as NodeListOf<HTMLImageElement>
  imgs.forEach((img) => {
    const p = img.getAttribute('data-icon-path')
    if (!p) return
    const api = window.electronAPI as any
    if (!api?.readImageAsDataURL) {
      fallbackIcon(img)
      return
    }
    api.readImageAsDataURL(p)
      .then((res: any) => {
        if (res && res.success && res.dataUrl) {
          img.src = res.dataUrl
          img.removeAttribute('data-icon-path')
        } else {
          fallbackIcon(img)
        }
      })
      .catch(() => fallbackIcon(img))
  })
}

// Re-hydrate whenever any task's result HTML (re)renders OR a task is
// expanded/collapsed. Fresh analyses hydrate fine because the task is expanded
// while it runs, but tasks restored from the persisted store default to
// collapsed — their result <img> only enters the DOM once the detail panel is
// shown, so we must also react to `collapsed` flips, not just `result` changes.
// Re-render persisted analysis reports when the UI language changes.
// `task.result` is a static HTML snapshot produced by renderApkInfo() at
// analysis time, so it is frozen in whatever language was active then — the
// v-html binding cannot react to locale on its own. Tasks that still carry the
// raw payload are re-rendered here; ones whose payload was shed for storage
// quota keep showing their original snapshot.
watch(locale, () => {
  let changed = false
  for (const task of taskStore.tasks) {
    if (task.operation !== 'analyze' || !task.resultData) continue
    taskStore.updateTask(task.id, { result: renderApkInfo(task.resultData) })
    changed = true
  }
  // updateTask only persists on terminal-state changes, so flush explicitly.
  if (changed) taskStore.persist()
})

watch(
  () => [selectedTask.value?.id, activeDetailTab.value, selectedTask.value?.result],
  async () => {
    await nextTick()
    hydrateResultIcons()
  },
  { immediate: true }
)

// Keep the icon/log cache in sync with the selected task. The report is only in
// the DOM for the selected task now, so hydration is scoped to it as well.
watch(() => selectedTask.value?.id, () => {
  const task = selectedTask.value
  if (!task) return
  void ensureAppIcon(task)
  if (getDetailTab(task) === 'info') void ensureTaskLog(task)
})
watch(() => selectedTask.value?.status, (status) => {
  const task = selectedTask.value
  if (!task) return
  void ensureAppIcon(task)
  if (isTerminal(status) && getDetailTab(task) === 'info') void ensureTaskLog(task)
})
watch(() => taskStore.tasks.length, () => {
  if (selectedTaskId.value != null && !taskStore.tasks.some((task) => task.id === selectedTaskId.value)) {
    selectNextTask()
  }
})

async function exportTaskLog(task: Task) {
  try {
    const api = window.electronAPI as any
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    const def = `task-${task.id}-${ts}.log`
    let filePath = ''
    if (api?.showSaveDialog) {
      const res = await api.showSaveDialog({ title: t('task.exportLog'), defaultPath: def, filters: [{ name: 'Log', extensions: ['log', 'txt'] }] })
      if (!res || res.canceled) return
      filePath = res.filePath || ''
    }
    if (!filePath) return
    const result = await api.callBackendAPI('task.export_log', { task_id: String(task.id), file_path: filePath })
    if (result?.success) {
      showSuccess(t('task.exportLog'), result.file_path || '')
    } else {
      showError(t('task.exportLog'), result?.error || 'failed')
    }
  } catch (e) {
    showError(t('task.exportLog'), String(e))
  }
}

// ===== Standalone report.html =====
// The report fragment (task.result) is persisted in renderer localStorage,
// which prunes history beyond 100 terminal tasks. To keep a durable second
// copy we wrap the fragment in a self-contained HTML document (inline CSS +
// base64 icons) and write it next to the task's other files on disk.
//
// KEEP IN SYNC with the global <style> block at the bottom of this file —
// REPORT_DOC_CSS must stay a superset of the selectors the report HTML uses.
// 报告产物（exportReport 写到磁盘、用浏览器打开）的 CSS 变量：从 app tokens
// 生成，消灭最后一份手写调色板。报告没有 data-theme，所以暗色走
// prefers-color-scheme（这是该产物的正确机制，不是遗漏）。
// --apk-accent 是报告专属的架构色（app token 表里没有），保持报告局部。
const reportVars = (t: Record<string, string>): string =>
  Object.entries(t).map(([k, v]) => `--app-${k}: ${v};`).join('\n  ')

const REPORT_DOC_CSS = `
:root {
  ${reportVars(colorTokens.light)}
  ${reportVars(staticTokens)}
  --apk-accent: #3b82f6;
}
@media (prefers-color-scheme: dark) {
  :root {
    ${reportVars(colorTokens.dark)}
    --apk-accent: #60a5fa;
  }
}
body { margin: 0; padding: 16px; background: var(--app-body-bg); color: var(--app-text-secondary);
  font-family: var(--app-font); }
.apk-info { display: flex; flex-direction: column; gap: 8px; font-size: var(--app-font-size-md); line-height: 1.6; }
.apk-card { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-radius: 10px; padding: 10px 14px; }
.apk-card > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: var(--app-font-size-md); font-weight: 600; }
.apk-card > summary::-webkit-details-marker { display: none; }
.apk-card[open] > .apk-card-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); }
.apk-card-body { display: flex; flex-direction: column; gap: 6px; }
.apk-card-h { display: flex; align-items: center; gap: 8px; font-size: var(--app-font-size-md); font-weight: 600; color: var(--app-text-secondary); }
.apk-sum-grp { display: flex; align-items: center; gap: 8px; min-width: 0; }
.apk-group { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-left: 3px solid var(--apk-accent, var(--app-card-border)); border-radius: 10px; padding: 10px 14px; }
.apk-group > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: var(--app-font-size-md); font-weight: 700; }
.apk-group > summary::-webkit-details-marker { display: none; }
.apk-group[open] > .apk-group-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); display: flex; flex-direction: column; gap: 10px; }
.apk-group-body .apk-card { background: transparent; border: none; border-radius: 0; padding: 0; }
.apk-group-body .apk-card[open] > .apk-card-body { margin-top: 6px; padding-top: 6px; }
.apk-icon { width: 38px; height: 38px; border-radius: 8px; object-fit: contain; box-shadow: 0 1px 2px rgba(0,0,0,.18); flex: 0 0 auto; }
.apk-icon--fallback { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 8px; background: var(--app-card-border); color: var(--app-text-dim); font-weight: 600; font-size: var(--app-font-size-xl); flex: 0 0 auto; }
.apk-sum { font-size: var(--app-font-size-xs); color: var(--app-text-dim); font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.apk-table { width: 100%; border-collapse: collapse; font-size: var(--app-font-size-sm); }
.apk-table th { text-align: left; color: var(--app-text-dim); font-weight: 600; font-size: var(--app-font-size-xs); border-bottom: 1px solid var(--app-card-border); padding: 5px 8px; white-space: nowrap; }
.apk-table td { padding: 5px 8px; border-bottom: 1px solid var(--app-card-border); color: var(--app-text-secondary); vertical-align: top; word-break: break-word; }
.apk-table tr:last-child td { border-bottom: none; }
.apk-table tbody tr:hover { background: var(--app-hover); }
.apk-table .mono { font-family: var(--app-font-mono); }
.apk-table .nowrap { white-space: nowrap; }
.apk-parent { font-family: var(--app-font-mono); font-size: var(--app-font-size-xs); color: var(--app-text-dim); white-space: nowrap; }
.apk-res { font-size: var(--app-font-size-xs); color: var(--app-text-muted); font-family: var(--app-font-mono); }
.apk-archchip { display: inline-block; font-size: var(--app-font-size-xs); font-weight: 600; border-radius: 4px; padding: 1px 6px; margin: 1px 3px 1px 0; }
.apk-lv { display: inline-block; font-size: var(--app-font-size-xs); border-radius: 4px; padding: 1px 7px; font-weight: 600; white-space: nowrap; }
.apk-lv--danger { background: var(--app-red-bg); color: var(--app-red); }
.apk-lv--normal { background: var(--app-storage-bg); color: var(--app-text-dim); }
.apk-lv--ok { background: var(--app-green-bg); color: var(--app-green); }
.apk-lv--warn { background: var(--app-yellow-bg); color: var(--app-yellow); }
.apk-mini { display: inline-block; font-family: var(--app-font-mono); font-size: var(--app-font-size-xs); background: var(--app-yellow-bg); color: var(--app-yellow); border-radius: 3px; padding: 0 5px; margin: 0 2px; }
.apk-warn { background: var(--app-yellow-bg); border: 1px solid var(--app-yellow); color: var(--app-yellow); border-radius: 6px; padding: 6px 10px; font-size: var(--app-font-size-sm); margin-top: 6px; }
.apk-muted { color: var(--app-text-dim); font-size: var(--app-font-size-sm); }
.apk-copy { color: var(--app-text-dim); opacity: 0.4; margin-left: 6px; display: inline-flex; align-items: center; vertical-align: middle; }
.apk-copy svg { display: block; }
.chev { color: var(--app-text-dim); transition: transform .2s; }
details[open] > summary .chev { transform: rotate(90deg); }
.apk-card details > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px; color: var(--app-text-dim); font-size: var(--app-font-size-sm); }
.apk-card details > summary::-webkit-details-marker { display: none; }
`

function escDoc(s: string): string {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
}

// Wrap the report fragment into a self-contained document: inline CSS plus
// base64-inlined disk icons (img[data-icon-path] would otherwise be broken
// outside the app, since the lazy hydration only runs in the renderer).
async function buildReportDocument(resultHtml: string, docTitle = ''): Promise<string> {
  const dom = new DOMParser().parseFromString(resultHtml, 'text/html')
  const imgs = Array.from(dom.querySelectorAll('img.apk-icon[data-icon-path]')) as HTMLImageElement[]
  const api = window.electronAPI as any
  for (const img of imgs) {
    const p = img.getAttribute('data-icon-path')
    if (!p) continue
    const toFallback = () => {
      const alt = img.getAttribute('alt') || ''
      const span = dom.createElement('span')
      span.className = 'apk-icon apk-icon--fallback'
      span.textContent = (alt.trim()[0] || 'A').toUpperCase()
      img.replaceWith(span)
    }
    if (!api?.readImageAsDataURL) { toFallback(); continue }
    try {
      const res = await api.readImageAsDataURL(p)
      if (res?.success && res.dataUrl) {
        img.src = res.dataUrl
        img.removeAttribute('data-icon-path')
      } else {
        toFallback()
      }
    } catch {
      toFallback()
    }
  }
  const body = dom.body.innerHTML
  const title = escDoc(docTitle || t('task.reportTitle'))
  return `<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>${title}</title>\n<style>\n${REPORT_DOC_CSS}\n</style>\n</head>\n<body>\n${body}\n</body>\n</html>\n`
}

// Auto-persist a durable copy right after an analyze completes (best-effort,
// fire-and-forget — a failure only costs the on-disk copy, never the UI).
async function persistReportFile(task: Task, resultHtml: string): Promise<void> {
  try {
    const api = window.electronAPI as any
    if (!resultHtml || !api?.callBackendAPI) return
    const doc = await buildReportDocument(resultHtml, `${task.fileName || task.id} · ${t('task.report')}`)
    const res = await api.callBackendAPI('task.save_report', { task_id: String(task.id), html: doc })
    if (!res?.success) logUtil.warn('[report] persist report.html failed', res?.error || 'unknown')
  } catch (e) {
    logUtil.warn('[report] persist report.html failed', e)
  }
}

async function exportReport(task: Task) {
  try {
    const api = window.electronAPI as any
    if (!task?.result) return
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`
    const base = (task.fileName || `task-${task.id}`).replace(/\.(apk|aab)$/i, '')
    let filePath = ''
    if (api?.showSaveDialog) {
      const res = await api.showSaveDialog({
        title: t('task.exportReport'),
        defaultPath: `${base}-report-${ts}.html`,
        filters: [{ name: 'HTML', extensions: ['html'] }],
      })
      if (!res || res.canceled) return
      filePath = res.filePath || ''
    }
    if (!filePath) return
    const doc = await buildReportDocument(task.result, `${base} · ${t('task.report')}`)
    const result = await api.callBackendAPI('task.save_report', { task_id: String(task.id), html: doc, target: filePath })
    if (result?.success) {
      showSuccess(t('task.exportReport'), result.file_path || filePath)
    } else {
      showError(t('task.exportReport'), result?.error || 'failed')
    }
  } catch (e) {
    showError(t('task.exportReport'), String(e))
  }
}

// Log buffering: batch high-volume stream events to avoid UI jank
const logBuffers = new Map<number, string[]>()
const logTimers = new Map<number, ReturnType<typeof setTimeout>>()

function flushLogBuffer(taskId: number) {
  const buf = logBuffers.get(taskId)
  if (buf && buf.length > 0) {
    taskStore.appendLogBatch(taskId, [...buf])
    buf.length = 0
    nextTick(() => scrollLogToBottom(taskId))
  }
  logTimers.delete(taskId)
}

function startNowTimer() {
  if (nowIv !== null) return
  const iv = setInterval(() => { now.value = Date.now() }, 1000)
  activeIntervals.add(iv)
  nowIv = iv
}

function stopNowTimer() {
  if (nowIv !== null) {
    clearInterval(nowIv)
    activeIntervals.delete(nowIv)
    nowIv = null
  }
}

function syncNowTimer() {
  const activeStatuses = ['running', 'downloading', 'queued', 'cancelling']
  const hasActive = taskStore.tasks.some(t => activeStatuses.includes(t.status))
  if (hasActive && nowIv === null) {
    startNowTimer()
  } else if (!hasActive && nowIv !== null) {
    stopNowTimer()
  }
}

onMounted(() => {
  logUtil.debug('任务管理页面已挂载')
  selectedTaskId.value = taskStore.tasks[0]?.id ?? null
  const task = selectedTask.value
  if (task) {
    void ensureAppIcon(task)
    if (getDetailTab(task) === 'info') void ensureTaskLog(task)
  }
  syncNowTimer()
  relativeIv = setInterval(() => { relativeNow.value = Date.now() }, 60_000)
  activeIntervals.add(relativeIv)
})

onUnmounted(() => {
  stopNowTimer()
  activeIntervals.forEach(clearInterval)
  activeIntervals.clear()
  relativeIv = null
})

// Reactively start/stop the duration clock based on active tasks
watch(() => taskStore.tasks, () => { syncNowTimer() }, { deep: true })

// New task form
const newOperation = ref<Task['operation']>('analyze')
// Single merged source input: http(s):// -> remote URL, anything else -> local
// path. Kept in one field so users can paste either without switching modes.
const newTarget = ref('')
const newSignId = ref('')
const decompileResources = ref(true)
const decompileSources = ref(true)

const signOptions = computed(() =>
  sigStore.configs.map((c: any) => ({ label: c.name, value: c.id }))
)

const OPERATIONS_ORDERED: Task['operation'][] = ['analyze', 'install', 'decompile', 'recompile', 'resign']
const operationOptions = computed(() =>
  OPERATIONS_ORDERED.map(op => ({ label: t(`task.${op}`), value: op }))
)

// 安装目标设备下拉：置顶设备排前面，默认选中设备列表当前选中项（或第一个在线设备）
const installDeviceId = ref('')
// 用户在下拉里显式选过设备后就不再自动跟随设备列表的选中变化
const installDeviceTouched = ref(false)
const deviceOptions = computed(() =>
  deviceStore.sortedDevices.map(d => ({
    label: `${d.name || d.id} (${d.id})${d.status === 'device' ? '' : ` · ${t('device.offline')}`}`,
    value: d.id,
    disabled: d.status !== 'device'
  }))
)
// 设备列表变化（插拔/连接）时校正下拉默认值：仅当当前值失效才改，不覆盖用户显式选择
watch(() => deviceStore.firstOnlineDeviceId, (first) => {
  const valid = deviceStore.devices.some(d => d.id === installDeviceId.value)
  if (!valid) installDeviceId.value = deviceStore.selectedDeviceId || first || ''
}, { immediate: true })
// 用户在设备列表切换选中设备时，下拉未手动选过则跟随
watch(() => deviceStore.selectedDeviceId, (id) => {
  if (!installDeviceTouched.value && id) installDeviceId.value = id
})

const canStart = computed(() =>
  !!newTarget.value.trim() && (newOperation.value !== 'install' || !!installDeviceId.value))

// http(s):// -> remote download; everything else is treated as a local path.
const isUrlLike = computed(() => /^https?:\/\//i.test(newTarget.value.trim()))

// recompile consumes a decompiled project directory; every other op a file.
const needsDirectory = computed(() => newOperation.value === 'recompile')

const startDisabledHint = computed(() =>
  newOperation.value === 'install' && !installDeviceId.value
    ? t('task.noDeviceSelected')
    : t('task.startHint'))

/** Resolve a path's existence + type via the main process (null = not found). */
async function statLocalPath(p: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.getFileStats === 'function') {
      const r = await svc.getFileStats(p)
      if (r?.success === true) return r as { isFile: boolean; isDirectory: boolean; size?: number }
    }
  } catch {
    // An IPC failure is treated the same as "path not found".
  }
  return null
}

// Switching the operation can invalidate an already-picked path (e.g. a file
// held while switching to recompile, which needs a directory). Drop it instead
// of letting startNewTask run with the wrong kind of target. URL targets are
// unaffected — they have no file/dir duality.
watch(newOperation, async () => {
  if (isUrlLike.value) return
  const p = newTarget.value.trim()
  if (!p) return
  const st = await statLocalPath(p)
  if (!st) return // non-existent paths are validated on start
  if (needsDirectory.value ? !st.isDirectory : !st.isFile) {
    newTarget.value = ''
    showWarning(t('task.pathTypeMismatch'), needsDirectory.value ? t('task.pathNeedDir') : t('task.pathNeedFile'))
  }
})

function opTagType(op: string) {
  return OP_TAG_MAP[op as Task['operation']] || 'default'
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}-${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function formatDuration(task: Task): string {
  return formatDurationUtil(task, now.value)
}

async function openInExplorer(filePath: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.openPath === 'function') svc.openPath(filePath)
  } catch (e) { /* ignore */ }
}

// getFileStats returns {success:false} for ANY stat error (ENOENT, EACCES —
// wording is slightly imprecise for permission errors but acceptable)
async function openInExplorerChecked(filePath: string, missingTitle: string, missingMsg: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.getFileStats === 'function') {
      const result = await svc.getFileStats(filePath)
      if (result?.success !== true) {
        showWarning(missingTitle, missingMsg)
        return
      }
    }
    await openInExplorer(filePath)
  } catch (e) {
    await openInExplorer(filePath)
  }
}

function isTerminal(status: string): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status)
}

function toggleTask(task: Task) {
  task.collapsed = !task.collapsed
  if (!task.collapsed && isTerminal(task.status) && !taskLogCache.value.has(task.id)) {
    loadTaskLog(task)
  }
}

async function loadTaskLog(task: Task) {
  try {
    const api = window.electronAPI as any
    // Default to a truncated tail (100KB) so the panel stays light; the export
    // button calls task.export_log which copies the *full* file to disk.
    const result = await api.callBackendAPI('task.read_log', {
      task_id: String(task.id),
      tail_bytes: 100 * 1024,
    })
    const content = (result.content || '').trim()
    logTruncatedMap.value.set(task.id, !!result.truncated)
    if (content) {
      taskLogCache.value.set(task.id, splitLogLines(content))
    }
    await nextTick()
    scrollLogToBottom(task.id)
  } catch (e) {
    logTruncatedMap.value.set(task.id, false)
    taskLogCache.value.set(task.id, [{ key: 0, text: `[Error loading log: ${e}]` }])
  }
}

function splitLogLines(content: string): { key: number; text: string }[] {
  return content.split('\n').map((text, i) => ({ key: i, text }))
}

async function refreshTaskLog(task: Task) {
  taskLogCache.value.delete(task.id)
  await loadTaskLog(task)
}

async function pickLocalFile() {
  try {
    const svc = await serviceManager.getService('system') as any
    const result = needsDirectory.value
      ? await svc.selectDirectory({ title: t('task.selectDir') })
      : await svc.selectFile({ title: t('task.selectFile'), filters: [{ name: 'APK/AAB', extensions: ['apk', 'aab'] }] })
    if (result && !result.canceled && result.filePaths?.length) {
      newTarget.value = result.filePaths[0]
    }
  } catch (e) {
    logUtil.error('pickLocalFile error:', e)
  }
}

// Dropping a file onto the path input fills in its absolute path. Chromium
// gives no useful default behaviour here, so we read it off the File object.
function onPathDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0] as (File & { path?: string }) | undefined
  if (file?.path) newTarget.value = file.path
}

async function startNewTask() {
  const raw = newTarget.value.trim()
  if (!raw) return
  let source: Task['source'], url: string | undefined, fp: string, fn: string
  let fileSize = 0

  if (/^https?:\/\//i.test(raw)) {
    source = 'url'
    url = raw
    // Strip any query/hash: the backend replaces '?' with '_' when sanitizing
    // the name, which would silently destroy the extension (app.apk?x=1 ->
    // app.apk_x=1).
    fn = (url.split('/').pop() || 'app.apk').split('?')[0].split('#')[0] || 'app.apk'
    fp = ''
  } else {
    source = 'local'
    fp = raw
    // A hand-typed or stale path is validated before it reaches the backend.
    const st = await statLocalPath(fp)
    if (!st) {
      showWarning(t('task.pathNotExist'), fp)
      return
    }
    if (needsDirectory.value && !st.isDirectory) {
      showWarning(t('task.pathNeedDir'), fp)
      return
    }
    if (!needsDirectory.value && !st.isFile) {
      showWarning(t('task.pathNeedFile'), fp)
      return
    }
    fn = fp.split(/[/\\]/).pop() || 'file'
    if (st.isFile && typeof st.size === 'number') fileSize = st.size
  }

  const opLabel = operationOptions.value.find(o => o.value === newOperation.value)?.label || newOperation.value
  const task = taskStore.createTask({
    source,
    url,
    filePath: fp,
    fileName: fn,
    operation: newOperation.value,
    operationLabel: opLabel,
    fileSize,
  })
  selectedTaskId.value = task.id
  detailTabs.value[task.id] = 'process'

  // Clear inputs
  newTarget.value = ''

  // Queue the task — TaskExecutionService starts it when a slot frees up
  // (bounded concurrency, default 3). The task stays 'queued' until then.
  enqueueTask(task.id, () => executeTask(task))
}

async function executeTask(task: Task, opts: { skipDownload?: boolean } = {}) {
  try {
    let localPath = task.filePath
    const api = window.electronAPI as any

    const taskStream = await serviceManager.getService('taskStream') as any
    // bind is idempotent (retry auto-unbinds stale)
    taskStream.bindTask(String(task.id))
    taskStream.setCallbacks(String(task.id), {
      onDownloadProgress: (p: number, _dl: number, _tot: number, _spd: number) => {
        taskStore.transition(task.id, 'download_progress', { progress: p })
      },
      onComplete: (payload: any, phase: string) => {
        if (phase === 'download') {
          taskStore.transition(task.id, 'download_complete', payload)
        } else {
          // Extract operation-specific fields from the complete payload.
          // Backend payloads (per apk_handler.py):
          //   analyze    → {package_name, permissions, native_libs, application_label, ...}
          //   decompile  → {output_dir}
          //   recompile  → {output_apk}
          //   sign       → {apk_path}
          const transitionPayload: any = {}
          if (payload?.output_dir) transitionPayload.output_dir = payload.output_dir
          if (payload?.output_apk) transitionPayload.output_apk = payload.output_apk
          if (payload?.apk_path) transitionPayload.apk_path = payload.apk_path
          // analyze: render the rich analysis card HTML via renderApkInfo. The
          // raw payload is kept too — `result` is a frozen HTML snapshot, so
          // switching the UI language re-renders from the source data.
          if (payload?.package_name) {
            transitionPayload.result = renderApkInfo(payload)
            transitionPayload.resultData = payload
          }
          // install: attach device label (model + serial) for notification & display
          if (task.operation === 'install' && payload?.device_id) {
            const dev = deviceStore.devices.find(d => d.id === payload.device_id)
            const model = dev?.name || payload.device_id
            const serial = payload.device_id
            transitionPayload.deviceLabel = `${model} (${serial})`
            taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] ${t('task.installedToDevice', { label: transitionPayload.deviceLabel })}`)
          }
          taskStore.transition(task.id, 'operation_complete', transitionPayload)
          // Persist a standalone report.html next to the task's other files so
          // the report survives renderer localStorage pruning (100-task cap).
          if (transitionPayload.result) {
            void persistReportFile(task, transitionPayload.result)
          }
        }
      },
      onError: (msg: string, phase: string) => {
        taskStore.transition(task.id, 'operation_error', { message: msg, failedPhase: phase })
      },
      onCancelled: () => {
        taskStore.transition(task.id, 'cancel_ack')
      },
      onLog: (line: string) => {
        // Backend-mirrored task log line (apk/install/aab handlers).
        // The Python backend already persisted it, so we only mirror it
        // into memory for live display — batched to avoid UI jank.
        const buf = logBuffers.get(task.id) ?? []
        buf.push(line)
        logBuffers.set(task.id, buf)
        if (!logTimers.has(task.id)) {
          logTimers.set(task.id, setTimeout(() => flushLogBuffer(task.id), 200))
        }
      },
    })

    // Note: latch pattern in TaskStreamService guarantees events arriving
    // before await waitForPhase() are not lost — they're stashed and resolved immediately.

    // --- Download phase (URL source only) ---
    // "Retry failed stage" skips a completed download and reuses the file
    // already fetched in the previous attempt.
    if (opts.skipDownload && task.source === 'url') {
      log(task, t('task.reuseDownloaded'))
    } else if (task.source === 'url' && task.url) {
      taskStore.transition(task.id, 'start_download')
      taskStream.setPhase(String(task.id), 'download')
      log(task, t('task.downloading') + ' ' + task.url)

      if (!api || typeof api.downloadFile !== 'function') throw new Error(t('task.downloadAPINotAvailable'))
      api.downloadFile(task.url, task.fileName, String(task.id))

      const dlResult: any = await taskStream.waitForPhase(String(task.id), 'download')
      localPath = dlResult.file_path
      log(task, t('task.completed') + ` (${(dlResult.size / 1024 / 1024).toFixed(1)}MB)`)
    }

    // --- Operation phase ---
    taskStore.transition(task.id, 'start_operation')
    taskStream.setPhase(String(task.id), 'operation')
    log(task, t('task.running') + ' ' + task.operationLabel)

    // No fake progress: operations emit no real progress events, so the
    // progress bar renders as indeterminate (see template) until completion.
    await runOperation(task, localPath)
    await taskStream.waitForPhase(String(task.id), 'operation')
  } catch (e: any) {
    const isCancelled = e?.message === 'cancelled' || e?.message === 'unbound'
    if (!isCancelled) {
      const rawMsg = e?.message ?? String(e ?? '')
      // Guard against a literal "null"/"None"/empty message ever being shown
      // or persisted as the task error.
      const errMsg = (rawMsg && rawMsg !== 'null' && rawMsg !== 'None')
        ? rawMsg
        : t('task.operationFailed')
      const currentTask = taskStore.tasks.find(t => t.id === task.id)
      if (currentTask && currentTask.status !== 'failed') {
        const failedPhase = currentTask?.phase === 'download' ? 'download' : 'operation'
        taskStore.transition(task.id, 'operation_error', { message: errMsg, failedPhase })
      }
      log(task, t('task.failed') + ': ' + errMsg)
      showError(task.operationLabel, errMsg)
    }
  }
}

function log(task: Task, msg: string) {
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] ${msg}`)
}

async function cancelTask(task: Task) {
  const name = task.fileName || task.operationLabel
  const prevStatus = task.status
  dialog.warning({
    title: t('task.cancel'),
    content: t('task.cancelConfirm', { name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      const api = window.electronAPI as any
      taskStore.transition(task.id, 'cancel_request')
      if (api && typeof api.cancelApkTask === 'function') {
        try {
          const result = await api.cancelApkTask(String(task.id))
          if (result && !result.cancelled) {
            // Task already finished — restore previous status
            const current = taskStore.tasks.find(t => t.id === task.id)
            if (current?.status === ('cancelling' as any)) {
              taskStore.updateTask(task.id, { status: prevStatus, progressLabel: '' })
            }
            showInfo(name, t('task.alreadyFinished'))
          }
        } catch (e) {
          logUtil.error('Cancel error:', e)
          // Restore on error too
          const current = taskStore.tasks.find(t => t.id === task.id)
          if (current?.status === ('cancelling' as any)) {
            taskStore.updateTask(task.id, { status: prevStatus, progressLabel: '' })
          }
        }
      }
    }
  })
}

async function retryTask(task: Task) {
  // Full re-run from scratch: reset task state to queued, keep existing logs
  // and append below them. URL tasks re-download; queued via the executor.
  taskStore.appendLog(task.id, `--- ${t('task.rerunFromStart')} ---`)
  taskStore.transition(task.id, 'reset_for_retry')
  task.collapsed = true
  enqueueTask(task.id, () => executeTask(task))
}

async function retryFailedStage(task: Task) {
  // Stage-level retry: if the download already succeeded in the previous
  // attempt (or the source is local), skip straight to the operation phase
  // and reuse the fetched file. Otherwise this equals a full re-run.
  taskStore.appendLog(task.id, `--- ${t('task.retryStage')} ---`)
  taskStore.transition(task.id, 'reset_for_retry')
  task.collapsed = true
  const skipDownload = task.source === 'url' ? !!task.filePath : false
  enqueueTask(task.id, () => executeTask(task, { skipDownload }))
}

async function confirmClearAll() {
  const del = await window.electronAPI?.appConfig?.get('autoDeleteOutputOnTaskRemove')
  dialog.error({
    title: t('task.clearAll'),
    content: del === true ? t('task.clearAllConfirmDelete') : t('task.clearAllConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      taskStore.clearAll()
      selectedTaskId.value = null
      detailTabs.value = {}
      appIconMap.value.clear()
    }
  })
}

async function confirmRemoveTask(task: Task) {
  const del = await window.electronAPI?.appConfig?.get('autoDeleteOutputOnTaskRemove')
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(task.status)
  const removeTask = () => {
    taskLogCache.value.delete(task.id)
    logTruncatedMap.value.delete(task.id)
    detailTabs.value && delete detailTabs.value[task.id]
    appIconMap.value.delete(task.id)
    const wasSelected = selectedTaskId.value === task.id
    taskStore.removeTask(task.id)
    if (wasSelected) selectNextTask()
  }
  if (del === true && isTerminal) {
    dialog.warning({
      title: t('task.clearCompleted'),
      content: t('task.removeConfirmDelete'),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: removeTask
    })
  } else {
    removeTask()
  }
}

async function runOperation(task: Task, localPath: string) {
  const op = task.operation
  const ingLabel = t(`task.${op}ing`)
  const svcName = op === 'install' ? 'device' : 'apk'
  const methodName = op === 'analyze' ? 'analyzeApk'
    : op === 'install' ? 'installApp'
    : op === 'decompile' ? 'decompileApk'
    : op === 'recompile' ? 'recompileApk'
    : 'signApk'

  const svc = await serviceManager.getService(svcName) as any
  if (typeof svc?.[methodName] !== 'function') throw new Error(t(`task.${op}SvcUnavailable`))

  // Prepare operation-specific options (include task_id for cancellation)
  let opts: any = undefined
  let logExtra = ''
  if (op === 'decompile') {
    opts = { resources: decompileResources.value, sources: decompileSources.value, task_id: String(task.id) }
    logExtra = ` (${t('task.decompileResources')}:${opts.resources}, ${t('task.decompileSources')}:${opts.sources})`
  } else if (op === 'recompile') {
    opts = { sign: false, align: true, optimize: true, task_id: String(task.id) }
    const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
    if (cfg) {
      opts = { ...opts, sign: true, v2: true, keystore: { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass } }
      logExtra = ` (${t('task.resign')}:${cfg.name})`
    }
  } else if (op === 'resign') {
    const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
    if (!cfg) throw new Error(t('task.noSignConfig'))
    opts = { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass, task_id: String(task.id) }
    logExtra = ` (${cfg.name})`
  } else if (op === 'install') {
    opts = { task_id: String(task.id), device_id: installDeviceId.value }
  }

  log(task, ingLabel + logExtra)

  // Call the service — returns {stream_id} immediately
  // Result comes via TaskStreamService → phaseResolve
  try {
    await svc[methodName](localPath, opts || { task_id: String(task.id) })
  } catch (err) {
    throw err
  }
}

function renderApkInfo(data: any) {
  if (!data) return ''
  const perms: string[] = data.permissions || []
  const nativeLibs: string[] = data.native_libs || []

  // Classify permissions (the shared set lives at module scope; the summary
  // tiles on the page use the same list).
  const DANGEROUS = DANGEROUS_PERMISSIONS
  const dangerous = perms.filter(p => DANGEROUS.has(p))
  const normal = perms.filter(p => !DANGEROUS.has(p))

  const label = (k: string, params?: any) => t(`task.${k}`, params)
  const esc = (s: string) => s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : '-'
  const fmtSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '-'
    const u = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + u[i]
  }

  const archColors: Record<string, string> = {
    arm64: '#22c55e', armeabi: '#3b82f6', x86_64: '#f59e0b', x86: '#ef4444', mips: '#8b5cf6', riscv: '#ec4899'
  }
  const archChips = nativeLibs.map(abi => {
    const prefix = Object.keys(archColors).find(k => abi.startsWith(k)) || ''
    const color = archColors[prefix] || '#6b7280'
    return `<span class="apk-archchip" style="background:${color}18;color:${color};border:1px solid ${color}40">${esc(abi)}</span>`
  }).join('')

  const lv = (danger: boolean) =>
    `<span class="apk-lv ${danger ? 'apk-lv--danger' : 'apk-lv--normal'}">${danger ? label('levelDanger') : label('levelNormal')}</span>`

  const soComp = data.so_comparison
  const comp = data.compression_analysis
  const page16 = data.page_size_16kb

  // summaries computed inline per section below

  const metaData = data.meta_data
  const fileMd5 = data.file_md5
  const sigMd5 = data.sig_md5
  const sigSha1 = data.sig_sha1
  const sigSha256 = data.sig_sha256
  const hasAnyHash = (fileMd5 && fileMd5 !== '-') || (sigMd5 && sigMd5 !== '-') || (sigSha1 && sigSha1 !== '-') || (sigSha256 && sigSha256 !== '-')
  const unsigned = sigMd5 === '-' || sigSha1 === '-' || sigSha256 === '-'
  const hasSoCompFull = soComp && !soComp.single_arch && !soComp.no_native && soComp.arches && Object.keys(soComp.arches).length > 0
  const hasComp = comp && Object.keys(comp).length > 0
  // page_size_16kb mixes per-ABI .so details with package-level check results
  // (manifest/zipalign for APK, bundle for AAB). Reserved keys were added
  // later; older persisted payloads only carry the per-ABI keys plus "skipped".
  const PAGE16_RESERVED = ['skipped', 'manifest', 'zipalign', 'bundle', 'supported', 'no_64bit_native', 'container']
  const page16Abis: string[] = page16
    ? Object.keys(page16).filter(k => !PAGE16_RESERVED.includes(k))
    : []
  const hasPage16 = !!page16 && (
    page16Abis.length > 0
    || !!page16.bundle
    || page16.manifest?.ok === false
    || page16.zipalign?.ok === false
  )

  const table = (headers: string[], rows: string[]) =>
    `<table class="apk-table"><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`
  const trow = (cells: string[]) => `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`
  const head = (title: string, summary = '', icon = '') =>
    `<summary><span class="apk-sum-grp">${icon}${title}${summary ? `<span class="apk-sum">${summary}</span>` : ''}</span><span class="chev">▸</span></summary>`
  const card = (title: string, summary: string, body: string) =>
    `<details class="apk-card" open>${head(title, summary)}<div class="apk-card-body">${body}</div></details>`
  const simpleCard = (title: string, summary: string, body: string) =>
    `<div class="apk-card"><div class="apk-card-h">${title}${summary ? `<span class="apk-sum">${summary}</span>` : ''}</div>${body}</div>`
  // Parent section that groups several related sub-analyses under one
  // collapsible card (e.g. native libraries: SO / compression / 16KB).
  const group = (title: string, summary: string, body: string, icon = '', accent = '', open = true, section = '') =>
    `<details class="apk-group"${open ? ' open' : ''}${accent ? ` style="--apk-accent:${accent}"` : ''}${section ? ` data-section="${section}"` : ''}>${head(title, summary, icon)}<div class="apk-group-body">${body}</div></details>`

  // dim, subtle copy affordance appended after values for one-click copy
  const COPY_ICO = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="5.5" y="5.5" width="8" height="8" rx="1.4"/><path d="M3.5 10.5h-1a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v1"/></svg>'
  const copyBtn = (value: string) =>
    `<span class="apk-copy" data-copy="${esc(value)}" title="${label('copyLog')}">${COPY_ICO}</span>`

  let html = '<div class="apk-info">'

  // ===== BASIC INFO =====
  {
    const rows: string[] = []
    rows.push(trow([label('version'), `${esc(data.version_name)} <span style="color:var(--app-text-dim);font-weight:400">(${esc(data.version_code)})</span>`]))
    rows.push(trow([label('fileSize'), fmtSize(data.file_size)]))
    rows.push(trow([`${label('minSdk')} / ${label('targetSdk')}`, `${esc(data.min_sdk_version)} / ${esc(data.target_sdk_version)}`]))
    if (archChips) rows.push(trow([label('architecture'), archChips]))
    let body = table([label('colItem'), label('colValue')], rows)
    if (data.warnings && Array.isArray(data.warnings) && data.warnings.length > 0) {
      body += `<div class="apk-warn"><b>${label('warnings')}</b>：${data.warnings.map((w: any) => esc(String(w))).join('；')}</div>`
    }
    const appIconTitle = [data.application_label, data.package_name].filter(Boolean).join(' · ')
    // Disk-path icons (persisted result HTML only stores the short path to
    // keep localStorage small); the data: URIs are legacy/inline fallbacks.
    const isDataUri = data.app_icon && data.app_icon.startsWith('data:')
    const appIconFallbackChar = (data.application_label || 'A').trim()[0] || 'A'
    const appIcon = (data.app_icon && data.app_icon !== '-')
      ? (isDataUri
          ? `<img class="apk-icon" src="${esc(data.app_icon)}" alt="${esc(data.application_label || 'app')}" title="${esc(appIconTitle)}">`
          : `<img class="apk-icon" data-icon-path="${esc(data.app_icon)}" alt="${esc(data.application_label || 'app')}" title="${esc(appIconTitle)}">`)
      : `<span class="apk-icon apk-icon--fallback" title="${esc(appIconTitle)}">${esc(appIconFallbackChar)}</span>`
    // Basic info becomes the first top-level group so all four sections share
    // one collapsible-card style (icon + app name in the header, package name
    // as the summary, the detail table inside the body).
    html += group(esc(data.application_label), esc(data.package_name), body, appIcon, '#3b82f6', true, 'basic')
  }

  // ===== SIGNATURE (accumulated into the Security group) =====
  // perms/dangerous/normal are classified at function scope, so permissions
  // can be folded into the same Security group right here, next to signing.
  let securityBody = ''
  let signStatus = ''
  let signPill = ''
  // AAB signing is not analysed (jarsigner/apksigner step is separate), so the
  // signature card would otherwise misreport an unsigned bundle as "signed"
  // just because a file MD5 exists. Show it for APKs only.
  if (hasAnyHash && !data.is_bundle) {
    const rows: string[] = []
    if (fileMd5 && fileMd5 !== '-') rows.push(trow([label('apkMd5'), `<span class="mono">${esc(fileMd5)}</span>` + copyBtn(fileMd5)]))
    if (sigMd5 && sigMd5 !== '-') rows.push(trow([label('sigMd5'), `<span class="mono">${esc(sigMd5)}</span>` + copyBtn(sigMd5)]))
    if (sigSha1 && sigSha1 !== '-') rows.push(trow([label('sigSha1'), `<span class="mono">${esc(sigSha1)}</span>` + copyBtn(sigSha1)]))
    if (sigSha256 && sigSha256 !== '-') rows.push(trow([label('sigSha256'), `<span class="mono">${esc(sigSha256)}</span>` + copyBtn(sigSha256)]))
    const fbHashKey = data.fb_hash_key
    if (fbHashKey && fbHashKey !== '-') {
      rows.push(trow([label('fbHashKey'), `<span class="mono">${esc(fbHashKey)}</span>` + copyBtn(fbHashKey)]))
    }
    let body = table([label('colField'), label('colValue')], rows)
    if (unsigned) body += `<div class="apk-warn">${label('unsignedApk')}</div>`
    signStatus = unsigned ? label('unsigned') : label('signed')
    // Signing status as a status pill (same language as 16KB / permission
    // levels) so the security posture reads at a glance instead of as plain text.
    const signPillLocal = unsigned
      ? '<span class="apk-lv apk-lv--danger">' + label('unsigned') + '</span>'
      : '<span class="apk-lv apk-lv--ok">' + label('signed') + '</span>'
    signPill = signPillLocal
    securityBody += card(label('signatureInfo'), signPill, body)
  }
  // Permissions folded into the Security group (dangerous first, then normal).
  {
    const prows: string[] = []
    for (const p of dangerous) {
      prows.push(trow([`<span class="mono" title="${esc(p)}">${esc(p.replace('android.permission.', ''))}</span>`, lv(true)]))
    }
    for (const p of normal) {
      prows.push(trow([`<span class="mono" title="${esc(p)}">${esc(p.replace('android.permission.', ''))}</span>`, lv(false)]))
    }
    const permCard = perms.length > 0
      ? card(label('permissions'), label('permCount', { count: perms.length, danger: dangerous.length }), table([label('permissions'), label('colLevel')], prows))
      : simpleCard(label('permissions'), '', `<div class="apk-muted">${label('noPermissions')}</div>`)
    const secSummary = signStatus
      ? `${signPill} · ${label('permsSummary', { count: perms.length, danger: dangerous.length })}`
      : label('permsSummary', { count: perms.length, danger: dangerous.length })
    html += group(label('signingSecurity'), secSummary, securityBody + permCard, '', '#22c55e', false)
  }

  // ===== NATIVE LIBRARIES (SO comparison + 16KB page) =====
  // Grouped under one collapsible parent so the related binary analyses read as
  // a single section. Compression is deliberately NOT here: only its `lib`
  // category is native — assets/dex are whole-package concerns, so it gets its
  // own top-level group further down.
  let nativeBody = ''
  const nativeSum: string[] = []
  if (hasSoCompFull) {
    const rows: string[] = []
    for (const [arch, info] of Object.entries(soComp.arches)) {
      const a = info as any
      const archColor = Object.keys(archColors).find(k => arch.startsWith(k)) || '#6b7280'
      const count = a.count || a.so_files?.length || 0
      const missing = a.missing || []
      const status = missing.length > 0
        ? label('missingCount', { count: missing.length }) + missing.map(s => `<span class="apk-mini">${esc(s)}</span>`).join('')
        : '<span style="color:var(--app-green)">✓ ' + label('complete') + '</span>'
      rows.push(trow([`<span style="color:${archColor};font-weight:600">${esc(arch)}</span>`, `${count} .so`, status]))
    }
    const sum = `${Object.keys(soComp.arches).length} ${label('architecture')} · ${soComp.baseline?.length || 0} .so`
    nativeBody += card(label('soComparison'), sum, table([label('architecture'), label('colSoCount'), label('colStatus')], rows))
    nativeSum.push(sum)
  } else if (soComp && soComp.single_arch) {
    nativeBody += simpleCard(label('soComparison'), label('singleArch'), `<div class="apk-muted">${label('singleArch')}</div>`)
    nativeSum.push(label('singleArch'))
  } else if (soComp && soComp.no_native) {
    nativeBody += simpleCard(label('soComparison'), label('noNativeLibs'), `<div class="apk-muted">${label('noNativeLibs')}</div>`)
    nativeSum.push(label('noNativeLibs'))
  }
  if (hasPage16) {
    // ---- Per-.so ELF alignment rows (PT_LOAD + GNU_RELRO) ----
    const soRows: string[] = []
    let total = 0, supported = 0
    for (const arch of page16Abis) {
      for (const [file, info] of Object.entries((page16[arch] || {}) as any)) {
        const fi = info as any
        const ok = fi.supports_16kb
        total++; if (ok) supported++
        // RELRO: risk = 16KB 页内存在可写数据（运行期可能 SIGSEGV）；
        // unknown = 段表被裁剪无法确认。旧持久化 payload 没有 relro_status，
        // 用 relro_ok 回退推断。
        const relroStatus = fi.relro_status || (
          fi.relro_ok === false ? 'risk'
            : (fi.relro_ok === true
                ? (fi.gnu_relro_present === false ? 'none' : 'ok')
                : undefined))
        const loadOk = fi.load_ok !== false
        // 状态：LOAD 对齐失败 → 不支持；仅 RELRO 风险 → 风险；否则支持
        const st = !loadOk
          ? '<span class="apk-lv apk-lv--danger">' + label('notSupported') + '</span>'
          : (relroStatus === 'risk'
              ? '<span class="apk-lv apk-lv--warn">' + label('relroRisk') + '</span>'
              : '<span class="apk-lv apk-lv--ok">' + label('supported') + '</span>')
        // max_align is the largest PT_LOAD p_align; old payloads lack the
        // GNU_RELRO fields entirely, in which case the cell stays "-".
        const loadAlign = fi.max_align ? `0x${Number(fi.max_align).toString(16)}` : '-'
        // GNU_RELRO 关注结束地址所在 16KB 页内是否还有可写数据，不是 p_align
        // （LLD 恒为 1），所以展示判定结果，风险时把命中的段名放进 tooltip。
        let relroCell = '-'
        if (relroStatus === 'none') {
          relroCell = label('notPresent')
        } else if (relroStatus === 'ok') {
          relroCell = '<span class="apk-lv apk-lv--ok">' + label('checkPassed') + '</span>'
        } else if (relroStatus === 'risk') {
          const secs = (fi.relro_risk_sections || []).join(', ')
          relroCell = `<span class="apk-lv apk-lv--warn" title="${esc(secs)}">${label('relroRisk')}</span>`
        } else if (relroStatus === 'unknown') {
          relroCell = '<span class="apk-lv apk-lv--warn" title="' + esc(label('relroUnknownTitle')) + '">' + label('relroUnknown') + '</span>'
        }
        soRows.push(trow([
          `<span style="color:var(--app-text-dim)">${esc(arch)}</span>`,
          `<span class="mono">${esc(file)}</span>`,
          loadAlign,
          relroCell,
          st,
        ]))
      }
    }

    // ---- Package-level checks: AAB alignment / manifest / APK zipalign ----
    const pkgRows: string[] = []
    // AAB: bundletool 生成 APK 时实际生效的页对齐（显式值或按 bundle 记录的
    // bundletool 版本取的默认值，见 backend parse_bundle_config）。
    const bundle16 = page16.bundle
    if (bundle16) {
      // 无 64 位原生库时（纯 Java/Kotlin 应用）该项不适用：官方明确这类应用
      // 已兼容 16KB，BundleConfig 的对齐设置不影响判定。
      const notApplicable = bundle16.applied === false
      const ok = bundle16.ok !== false
      const details: string[] = []
      details.push(`<span class="mono">${esc(bundle16.alignment || label('notDeclared'))}</span>`)
      // 对齐不是显式声明时，标出来源，避免被误读成"用户配置成 4K"
      if (bundle16.alignment_source === 'default_by_bundletool_version') {
        details.push(label('bundleAlignmentDefault', { version: bundle16.bundletool_version || '-' }))
      } else if (bundle16.alignment_source === 'default_current_tool') {
        details.push(label('bundleAlignmentDefaultCurrent'))
      }
      if (bundle16.uncompress_enabled === false) {
        details.push(label('bundleCompressedLibs'))
      }
      if (bundle16.error) {
        details.push(label('bundleConfigUnavailable'))
      }
      const cell = notApplicable
        ? '<span class="apk-lv apk-lv--ok">' + label('notApplicable') + '</span>'
        : (ok
            ? '<span class="apk-lv apk-lv--ok">' + label('checkPassed') + '</span>'
            : '<span class="apk-lv apk-lv--danger">' + label('checkFailed') + '</span>')
      pkgRows.push(trow([label('aabAlignment'), details.join(' · '), cell]))
    }
    // Google Play 的 16KB 校验 = ELF LOAD 对齐 + 未压缩 .so 的 ZIP 对齐；
    // RELRO 结束地址属于运行期风险，不在 Play 上传门禁内。
    if (page16.container === 'aab') {
      const gateOk = page16.gate_ok !== false
      pkgRows.push(trow([
        label('playGate'),
        `<span class="apk-muted">${esc(label('playGateBasis'))}</span>`,
        gateOk
          ? '<span class="apk-lv apk-lv--ok">' + label('checkPassed') + '</span>'
          : '<span class="apk-lv apk-lv--danger">' + label('checkFailed') + '</span>',
      ]))
    }
    // RELRO 运行风险汇总（有 64 位 .so 时才展示）
    if (soRows.length > 0
      && (Array.isArray(page16.relro_risk) || Array.isArray(page16.relro_unknown))) {
      const riskList = page16.relro_risk || []
      const unknownList = page16.relro_unknown || []
      const fmt = (items: any[]) =>
        items.map((it: any) => `${it.arch}/${it.file}`).join(', ')
      const relroDetails: string[] = []
      if (riskList.length > 0) {
        relroDetails.push(label('relroRiskList', {
          count: riskList.length,
          files: fmt(riskList),
        }))
      }
      if (unknownList.length > 0) {
        relroDetails.push(label('relroUnknownList', {
          count: unknownList.length,
          files: fmt(unknownList),
        }))
      }
      let relroPill = ''
      if (riskList.length > 0) {
        relroPill = '<span class="apk-lv apk-lv--warn">' + label('relroRisk') + '</span>'
      } else if (unknownList.length > 0) {
        relroPill = '<span class="apk-lv apk-lv--warn">' + label('relroUnknown') + '</span>'
      } else {
        relroPill = '<span class="apk-lv apk-lv--ok">' + label('relroNoRisk') + '</span>'
      }
      pkgRows.push(trow([
        label('relroRiskRow'),
        `<span class="apk-muted">${esc(relroDetails.join(' · ') || label('relroNoRisk'))}</span>`,
        relroPill,
      ]))
    }
    const manifest16 = page16.manifest
    if (manifest16) {
      const ok = manifest16.ok !== false
      const declared = manifest16.present !== false && manifest16.extract_native_libs != null
      const value = declared ? String(manifest16.extract_native_libs) : label('notDeclared')
      pkgRows.push(trow([
        label('manifestExtractNativeLibs'),
        `<span class="mono">${esc(value)}</span>`,
        ok
          ? '<span class="apk-lv apk-lv--ok">' + label('checkPassed') + '</span>'
          : '<span class="apk-lv apk-lv--danger">' + label('checkFailed') + '</span>',
      ]))
    }
    const zipalign16 = page16.zipalign
    if (zipalign16) {
      const ok = zipalign16.ok !== false
      const details: string[] = []
      if (typeof zipalign16.checked === 'number') {
        details.push(label('zipChecked', {
          count: zipalign16.checked,
          so: zipalign16.so_checked || 0,
        }))
      }
      if (zipalign16.misaligned_count > 0) {
        details.push(label('zipMisalignedCount', { count: zipalign16.misaligned_count }))
      }
      if (zipalign16.compressed_so > 0) {
        details.push(label('zipCompressedSo', { count: zipalign16.compressed_so }))
      }
      if (zipalign16.unreadable > 0) {
        details.push(label('zipUnreadable', { count: zipalign16.unreadable }))
      }
      pkgRows.push(trow([
        label('apkZipalign'),
        `<span class="apk-muted">${esc(details.join(' · '))}</span>`,
        ok
          ? '<span class="apk-lv apk-lv--ok">' + label('checkPassed') + '</span>'
          : '<span class="apk-lv apk-lv--danger">' + label('checkFailed') + '</span>',
      ]))
    }

    let body = ''
    if (soRows.length > 0) {
      body += table(
        [label('architecture'), label('colFile'), label('colLoadAlignment'),
         label('colRelroAlignment'), label('colStatus')],
        soRows,
      )
    } else {
      body += `<div class="apk-muted">${label('no64bitNative')}</div>`
    }
    if (pkgRows.length > 0) {
      body += `<div style="margin-top:8px">${table(
        [label('colItem'), label('colDetail'), label('colStatus')], pkgRows)}</div>`
    }
    if (page16.skipped && page16.skipped.length > 0) {
      body += `<div class="apk-muted" style="margin-top:4px">${label('pageSizeSkipped', { count: page16.skipped.length })}</div>`
    }
    const pkgFailed = (bundle16 && bundle16.ok === false && bundle16.applied !== false)
      || (manifest16 && manifest16.ok === false)
      || (zipalign16 && zipalign16.ok === false)
    const relroRiskCount = (page16.relro_risk || []).length
    const sum = total > 0
      ? label('page16Supported', { supported, total })
        + (relroRiskCount > 0
            ? ' · ' + label('relroRiskCount', { count: relroRiskCount })
            : '')
      : (pkgFailed
          ? `${label('no64bitNative')} · ${label('checkFailed')}`
          : label('no64bitNative'))
    nativeBody += card(label('pageSize16kb'), sum, body)
    nativeSum.push(sum)
  }
  if (nativeBody) html += group(label('nativeAnalysis'), nativeSum.join(' · '), nativeBody, '', '#8b5cf6', true)

  // ===== COMPRESSION (whole-package: assets / dex / lib) =====
  // Own top-level group, not nested under native libraries: only the `lib`
  // category is a native-library concern, while assets/dex describe the whole
  // APK — sharing the native parent misrepresented their scope.
  if (hasComp) {
    const rows: string[] = []
    let totUnc = 0
    let totCmp = 0
    let totStored = 0
    let totDeflated = 0
    // Compression rate = compressed / uncompressed (e.g. 70% means the
    // on-disk payload is 70% of the raw size). Distinct from "saved" which is
    // (1 - rate). The UI shows the rate per the user's preference.
    const ratePct = (unc: number, cmp: number) =>
      unc > 0 ? ((cmp / unc) * 100).toFixed(1) + '%' : '-'
    for (const [category, info] of Object.entries(comp)) {
      const c = info as any
      const uncompressed = c.uncompressed || 0
      const compressed = c.compressed || 0
      const stored = c.stored || 0
      const deflated = c.deflated || 0
      totUnc += uncompressed
      totCmp += compressed
      totStored += stored
      totDeflated += deflated
      rows.push(trow([
        esc(category),
        uncompressed > 0 ? fmtSize(uncompressed) : '-',
        compressed > 0 ? fmtSize(compressed) : '-',
        ratePct(uncompressed, compressed),
        `${stored}`,
        `${deflated}`,
      ]))
    }
    // Totals across all categories — overall compression health at a glance.
    rows.push(trow([
      `<b>${esc(label('total'))}</b>`,
      `<b>${totUnc > 0 ? fmtSize(totUnc) : '-'}</b>`,
      `<b>${totCmp > 0 ? fmtSize(totCmp) : '-'}</b>`,
      `<b>${ratePct(totUnc, totCmp)}</b>`,
      `<b>${totStored}</b>`,
      `<b>${totDeflated}</b>`,
    ]))
    const compSum = `${label('catCount', { count: Object.keys(comp).length })} · ${label('compressionDesc')}`
    html += group(
      label('compressionAnalysis'),
      compSum,
      table(
        [label('colCategory'), label('colUncompressed'), label('colCompressed'), label('colRate'), label('colStoredCount'), label('colDeflatedCount')],
        rows,
      ),
      '',
      '#0ea5e9',
      false,
    )
  }

  // ===== META DATA =====
  if (metaData && Array.isArray(metaData) && metaData.length > 0) {
    const rows: string[] = []
    for (const item of metaData) {
      const parent = item.parent || 'unknown'
      const name = item.name || ''
      const value = item.value || ''
      const resValue = item.resource_value || ''
      const resContent = item.resource_content
      const resResolved = item.resource_resolved
      let valCell = ''
      if (value && !value.startsWith('@')) valCell = esc(value)
      else if (resValue) valCell = esc(resValue)
      else valCell = '-'
      let resCell = ''
      if (resResolved || (resContent && resContent.length > 0)) {
        if (resResolved) resCell += `<div class="apk-muted">${esc(resResolved)}</div>`
        if (resContent && resContent.length > 0) {
          for (const ci of resContent) resCell += `<div class="apk-res">${esc(ci.element)}: ${esc(ci.name)} → ${esc(ci.value)}</div>`
        }
      }
      rows.push(trow([
        `<span class="apk-parent">&lt;${esc(parent)}&gt;</span>`,
        esc(name),
        valCell,
        resCell
      ]))
    }
    const metaCard = card(label('metaData'), label('itemCount', { count: metaData.length }), table([label('colParent'), label('colName'), label('colValue'), label('colResource')], rows))
    html += group(label('manifestResources'), label('itemCount', { count: metaData.length }), metaCard, '', '#f59e0b', false)
  }

  html += '</div>'
  return html
}


</script>

<style scoped>
/* The page owns its height (the app shell scrolls the page container only when
   the viewport is too narrow; the two-column workspace manages its own scroll). */
.package-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

/* ======================= New task bar ======================= */
.new-task-bar {
  flex: none;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.task-bar-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.task-source-input { flex: 1 1 240px; min-width: 0; }
.task-source-input :deep(.task-pick-btn) { --n-text-color: var(--app-text-dim); cursor: pointer; }
.task-source-input :deep(.task-pick-btn:hover) { --n-text-color-hover: var(--app-green); }
.task-start-wrap { display: inline-flex; }
.task-bar-opts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--app-card-border);
}
.op-desc { font-size: var(--app-font-size-sm); color: var(--app-text-dim); }
.op-label { font-size: var(--app-font-size-xs); color: var(--app-text-dim); white-space: nowrap; }
.hidden-input { display: none; }

/* ======================= Two-column workspace ======================= */
.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 16px;
}

/* ---- left rail ---- */
.rail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  overflow: hidden;
}
.rail-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px 14px;
  border-bottom: 1px solid var(--app-card-border);
}
.rail-title {
  font-size: var(--app-font-size-sm);
  font-weight: 600;
  color: var(--app-text-secondary);
}
/* n-input 自身带 width:100%，如果直接给它加左右 margin，宽度会按 100%
   计算再叠 margin，导致右侧超框。用 padding 包装容器，n-input 始终按
   容器内容宽度收缩。 */
.rail-search {
  flex: none;
  min-width: 0;
  box-sizing: border-box;
  padding: 10px 12px 8px;
}
.rail-search :deep(.n-input) {
  --n-height: 30px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.rail-filters {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 0 12px 8px;
  border-bottom: 1px solid var(--app-card-border);
}
.rail-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 23px;
  padding: 0 7px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--app-text-dim);
  font-size: 10.5px;
  cursor: pointer;
  white-space: nowrap;
}
.rail-chip:hover { background: var(--app-hover); color: var(--app-text-secondary); }
.rail-chip.on { background: var(--app-green-bg); color: var(--app-green); }
.rail-chip span {
  min-width: 14px;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--app-storage-bg);
  color: var(--app-text-dim);
  font-family: var(--app-font-mono);
  font-size: 9px;
  text-align: center;
}
.rail-chip.on span { background: var(--app-card-bg); color: var(--app-green); }
.rail-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}
.rail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 42px 16px;
  text-align: center;
  color: var(--app-text-dim);
  font-size: var(--app-font-size-sm);
}
.rail-empty p { margin: 0; }

/* ---- task item ---- */
.task-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 9px 12px 10px 14px;
  border: 0;
  border-bottom: 1px solid var(--app-card-border);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background .15s;
}
.task-item:hover { background: var(--app-hover); }
.task-item.selected { background: var(--app-green-bg); }
.task-item.selected::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 2px;
  border-radius: 0 2px 2px 0;
  background: var(--app-green);
}
.file-tile {
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--app-font-mono);
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: -.02em;
}
.file-tile.apk { background: var(--app-green-bg); color: var(--app-green); }
.file-tile.aab { background: var(--app-blue-bg); color: var(--app-blue); }
.file-tile.dir { background: var(--app-yellow-bg); color: var(--app-yellow); }
.file-tile.lg { width: 36px; height: 36px; border-radius: 8px; font-size: 9px; }
.ti-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.ti-row1 { display: flex; align-items: center; gap: 6px; min-width: 0; min-height: 18px; }
.ti-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--app-font-size-sm);
  font-weight: 500;
  color: var(--app-text-primary);
}
.ti-glyph { flex: none; width: 14px; height: 14px; display: inline-flex; align-items: center; justify-content: center; }
.ti-row2 {
  display: flex;
  align-items: center;
  gap: 5px;
  min-height: 14px;
  color: var(--app-text-dim);
  font-size: 9.5px;
}
.ti-row2 :deep(.n-tag) { height: 14px; border-radius: 3px; font-size: 9.5px; }
.ti-source { flex: none; color: var(--app-text-dim); }
.ti-time { margin-left: auto; flex: none; color: var(--app-text-dim); white-space: nowrap; font-size: 9.5px; }
.ti-progress {
  position: absolute;
  left: 14px;
  right: 12px;
  bottom: 0;
  height: 2px;
  background: var(--app-storage-bg);
  overflow: hidden;
}
.ti-progress i { display: block; height: 100%; background: var(--app-blue); border-radius: 2px; transition: width .3s; }
.ti-progress.indeterminate i { width: 42%; background: var(--app-green); animation: task-indeterminate 1.5s ease-in-out infinite; }
.ti-id {
  position: absolute;
  left: 15px;
  bottom: 2px;
  font-family: var(--app-font-mono);
  font-size: 9px;
  line-height: 1;
  letter-spacing: .02em;
  color: var(--app-text-dim);
  opacity: .7;
  pointer-events: none;
}
.ti-glyph.completed { color: var(--app-green); }
.ti-glyph.failed { color: var(--app-red); }
.ti-glyph.downloading { color: var(--app-blue); }
.ti-glyph.running, .ti-glyph.cancelling { color: var(--app-green); }
.ti-glyph.queued, .ti-glyph.cancelled { color: var(--app-text-dim); }

/* ---- right detail ---- */
.detail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  overflow: hidden;
}
.detail-head {
  flex: none;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--app-card-border);
}
.dh-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.dh-title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; }
.dh-title {
  margin: 0;
  font-size: var(--app-font-size-lg);
  font-weight: 600;
  color: var(--app-text-primary);
  overflow-wrap: anywhere;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--app-storage-bg);
  color: var(--app-text-secondary);
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
}
.status-pill.running, .status-pill.downloading { background: var(--app-blue-bg); color: var(--app-blue); }
.status-pill.completed { background: var(--app-green-bg); color: var(--app-green); }
.status-pill.failed { background: var(--app-red-bg); color: var(--app-red); }
.status-pill.cancelling { background: var(--app-yellow-bg); color: var(--app-yellow); }
.status-pill.cancelled { background: var(--app-storage-bg); color: var(--app-text-dim); }
.dh-path {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  color: var(--app-text-dim);
  font-size: 10.5px;
}
.path-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--app-font-mono);
  color: var(--app-text-secondary);
}
.path-actions { display: flex; align-items: center; gap: 1px; flex: none; }
.dh-badges { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; }
.dh-badges :deep(.n-tag) { height: 16px; border-radius: 3px; font-size: 9.5px; }
.soft-tag {
  display: inline-flex;
  align-items: center;
  height: 16px;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--app-storage-bg);
  color: var(--app-text-dim);
  font-size: 9.5px;
  white-space: nowrap;
}
.dh-actions { flex: none; display: flex; align-items: center; gap: 2px; }

/* ---- tabs + live timer ---- */
.detail-tabs {
  flex: none;
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 16px;
  border-bottom: 1px solid var(--app-card-border);
}
.detail-tab-list { display: flex; align-items: center; gap: 2px; min-width: 0; }
.detail-tab {
  position: relative;
  height: 35px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 6px 6px 0 0;
  border: 0;
  background: transparent;
  font-size: var(--app-font-size-sm);
  color: var(--app-text-dim);
  cursor: pointer;
  white-space: nowrap;
}
.detail-tab:hover { background: var(--app-hover); color: var(--app-text-secondary); }
.detail-tab.active { color: var(--app-text-primary); font-weight: 600; }
.detail-tab.active::after {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: -1px;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: var(--app-green);
}
.tab-live {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--app-green);
  animation: task-pulse 1.2s ease-in-out infinite;
}
.detail-timer {
  margin-left: auto;
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding-left: 12px;
  white-space: nowrap;
  font-size: 10.5px;
  color: var(--app-text-dim);
}
.detail-timer .timer-value {
  font-family: var(--app-font-mono);
  font-size: 11.5px;
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* ---- scroll body ---- */
.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px 16px;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}
.detail-scroll--fill {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding-bottom: 14px;
}
.detail-scroll--fill > .section-head,
.detail-scroll--fill > .info-card { flex: none; }

/* ---- phase rail: compact, top-centred ---- */
.phase-strip {
  flex: none;
  align-self: center;
  display: inline-flex;
  align-items: center;
  width: auto;
  max-width: 100%;
  padding: 7px 12px;
  margin-bottom: 14px;
  background: var(--app-storage-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
}
.phase-step {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  font-size: 10.5px;
  color: var(--app-text-dim);
  white-space: nowrap;
}
.phase-step.done { color: var(--app-text-secondary); }
.phase-step.current { color: var(--app-green); font-weight: 600; }
.phase-step.failed { color: var(--app-red); font-weight: 600; }
.phase-dot {
  width: 14px;
  height: 14px;
  flex: none;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--app-card-bg);
  color: var(--app-text-dim);
}
.phase-step.done .phase-dot { border-color: var(--app-green); background: var(--app-green-bg); color: var(--app-green); }
.phase-step.current .phase-dot { border: 0; background: transparent; color: var(--app-green); }
.phase-step.failed .phase-dot { border-color: var(--app-red); background: var(--app-red-bg); color: var(--app-red); }
.phase-line { width: 30px; height: 1px; margin: 0 8px; background: var(--app-card-border); flex: none; }
.phase-line.done { background: var(--app-green-border); }
.phase-strip--download .phase-step.current { color: var(--app-blue); }
.phase-strip--download .phase-step.current .phase-dot { color: var(--app-blue); }

/* ---- loading / failed / cancelled ---- */
.process-center {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.process-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.loading-spinner {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 4px solid var(--app-green-bg);
  border-top-color: var(--app-green);
  animation: task-spin .9s linear infinite;
}
.loading-spinner.yellow { border-color: var(--app-yellow-bg); border-top-color: var(--app-yellow); }
.loading-progress-circle {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: conic-gradient(var(--app-blue) calc(var(--pct, 0) * 1%), var(--app-blue-bg) 0);
}
.loading-progress-circle::after {
  content: '';
  position: absolute;
  inset: 5px;
  border-radius: 50%;
  background: var(--app-card-bg);
}
.loading-percent {
  position: relative;
  z-index: 1;
  font-family: var(--app-font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-secondary);
}
.loading-queued-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-storage-bg);
  color: var(--app-text-dim);
}
.loading-label {
  font-size: var(--app-font-size-md);
  font-weight: 500;
  color: var(--app-text-secondary);
  text-align: center;
  letter-spacing: .01em;
}
.error-card {
  width: min(560px, 100%);
  margin: 0 auto;
  padding: 14px 16px;
  border: 1px solid var(--app-red-border);
  border-radius: 10px;
  background: var(--app-red-bg);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.error-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-red);
}
.error-msg {
  font-size: var(--app-font-size-sm);
  line-height: 1.6;
  color: var(--app-text-primary);
  overflow-wrap: anywhere;
}
.error-hint { font-size: 10.5px; line-height: 1.6; color: var(--app-text-dim); }
.error-actions { display: flex; justify-content: flex-end; margin-top: 4px; }
.cancelled-card {
  width: min(560px, 100%);
  margin: 0 auto;
  padding: 16px 18px;
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  background: var(--app-storage-bg);
  color: var(--app-text-secondary);
  font-size: var(--app-font-size-sm);
  line-height: 1.7;
  text-align: center;
}
.app-empty-hint {
  padding: 28px 16px;
  text-align: center;
  font-size: var(--app-font-size-sm);
  color: var(--app-text-dim);
}

/* ---- result / artifact ---- */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 10px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--app-font-size-sm);
  font-weight: 600;
  color: var(--app-text-secondary);
}
.section-title :deep(.n-icon) { color: var(--app-green); }
.section-actions { display: flex; align-items: center; gap: 2px; }
.report-hero {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  background: var(--app-card-bg);
}
.app-icon-big {
  width: 42px;
  height: 42px;
  flex: none;
  border-radius: 9px;
  background: var(--app-green-bg);
  color: var(--app-green);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  font-weight: 700;
  object-fit: cover;
}
.rh-main { flex: 1; min-width: 0; }
.rh-name { font-size: var(--app-font-size-lg); font-weight: 600; color: var(--app-text-primary); }
.rh-pkg { margin-top: 1px; font-family: var(--app-font-mono); font-size: 10px; color: var(--app-text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rh-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.chip-static {
  display: inline-flex;
  align-items: center;
  height: 17px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--app-storage-bg);
  color: var(--app-text-secondary);
  font-size: 9.5px;
  white-space: nowrap;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0 12px;
}
.stat-tile {
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  background: var(--app-card-bg);
}
.stat-label { font-size: 9.5px; color: var(--app-text-dim); }
.stat-value { margin-top: 1px; font-family: var(--app-font-mono); font-size: 15px; font-weight: 600; color: var(--app-text-primary); line-height: 1.3; }
.stat-value small { font-family: var(--app-font); font-size: 9px; font-weight: 400; color: var(--app-text-dim); }
.stat-note { margin-top: 1px; font-size: 9px; color: var(--app-text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat-note.danger { color: var(--app-red); }
.stat-note.ok { color: var(--app-green); }
.task-report { font-size: var(--app-font-size-md); }
/* The report's first group repeats the hero/summary above; keep it for the
   exported standalone report, hide it only in the page. New snapshots carry
   data-section="basic"; the :first-child fallback covers pre-existing snapshots. */
.task-report :deep([data-section="basic"]),
.task-report :deep(.apk-info > .apk-group:first-child) { display: none; }

.output-card {
  padding: 4px 12px;
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  background: var(--app-card-bg);
}
.output-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 4px 0;
  border-bottom: 1px solid var(--app-card-border);
}
.output-row:last-child { border-bottom: 0; }
.output-key { width: 64px; flex: none; font-size: 10.5px; color: var(--app-text-dim); }
.output-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--app-font-mono);
  font-size: 11px;
  color: var(--app-text-secondary);
}
.output-device { display: flex; align-items: center; gap: 6px; font-size: var(--app-font-size-sm); color: var(--app-text-secondary); }
.output-tags { display: flex; flex-wrap: wrap; gap: 6px; }

/* ---- info + log ---- */
.info-card {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px 18px;
  padding: 12px 14px;
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  background: var(--app-card-bg);
}
.info-k { font-size: 10px; color: var(--app-text-dim); }
.info-v { margin-top: 2px; font-size: var(--app-font-size-sm); color: var(--app-text-secondary); }
.info-v.mono { font-family: var(--app-font-mono); font-size: 10.5px; }
.log-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  background: var(--app-code-bg);
  margin-top: 12px;
}
.log-card.fill { flex: 1; overflow: hidden; }
.log-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.log-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--app-text-secondary);
}
.log-count { font-family: var(--app-font-mono); font-size: 9.5px; font-weight: 400; color: var(--app-text-dim); }
.log-actions { display: flex; align-items: center; gap: 2px; }
.log-search-input { flex: none; margin-bottom: 6px; }
.log-trunc-hint { flex: none; margin-bottom: 4px; font-size: 9.5px; color: var(--app-text-dim); }
.log-body { flex: 1; min-height: 0; overflow: hidden; }
.log-line {
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-xs);
  line-height: 18px;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* ---- empty right pane ---- */
.detail-empty {
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px;
  text-align: center;
}
.empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--app-storage-bg);
  color: var(--app-text-dim);
  display: flex;
  align-items: center;
  justify-content: center;
}
.detail-empty h3 { margin: 0; font-size: var(--app-font-size-lg); color: var(--app-text-secondary); }
.detail-empty p { max-width: 360px; margin: 0; font-size: var(--app-font-size-sm); line-height: 1.7; color: var(--app-text-dim); }

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.spin { animation: task-spin .9s linear infinite; }

@keyframes task-spin { to { transform: rotate(360deg); } }
@keyframes task-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes task-indeterminate {
  0% { margin-left: -42%; }
  100% { margin-left: 100%; }
}

/* ======================= Responsive ======================= */
@media (max-width: 1320px) {
  .workspace { grid-template-columns: 340px minmax(0, 1fr); }
}
@media (max-width: 1060px) {
  .package-page { height: auto; min-height: 100%; }
  .workspace { display: flex; flex-direction: column; }
  .rail { max-height: 320px; }
  .detail { min-height: 560px; }
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .stat-grid { grid-template-columns: 1fr; }
  .dh-path { flex-wrap: wrap; }
  .phase-line { width: 18px; margin: 0 5px; }
}
</style>

<style>
/* APK analysis result card — NON-SCOPED on purpose.
   The card is rendered via v-html (task.result is a persisted HTML string),
   so scoped styles in this SFC do not reach its dynamic DOM. */
.apk-info { display: flex; flex-direction: column; gap: 8px; font-size: var(--app-font-size-md); line-height: 1.6; }
.apk-card { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-radius: 10px; padding: 10px 14px; }
.apk-card > summary {
  list-style: none; cursor: pointer; user-select: none;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  color: var(--app-text-secondary); font-size: var(--app-font-size-md); font-weight: 600;
}
.apk-card > summary::-webkit-details-marker { display: none; }
.apk-card[open] > .apk-card-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); }
.apk-card-body { display: flex; flex-direction: column; gap: 6px; }

.apk-card-h { display: flex; align-items: center; gap: 8px; font-size: var(--app-font-size-md); font-weight: 600; color: var(--app-text-secondary); }
.apk-sum-grp { display: flex; align-items: center; gap: 8px; min-width: 0; }

/* parent section grouping several related sub-analyses (e.g. native libs).
   --apk-accent (set per section via group()'s 5th arg) paints a left stripe
   so the four top-level blocks are scannable at a glance. */
.apk-group { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-left: 3px solid var(--apk-accent, var(--app-card-border)); border-radius: 10px; padding: 10px 14px; }
.apk-group > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: var(--app-font-size-md); font-weight: 700; }
.apk-group > summary::-webkit-details-marker { display: none; }
.apk-group[open] > .apk-group-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); display: flex; flex-direction: column; gap: 10px; }
/* nested sub-cards lose their own box so the group is the single container */
.apk-group-body .apk-card { background: transparent; border: none; border-radius: 0; padding: 0; }
.apk-group-body .apk-card[open] > .apk-card-body { margin-top: 6px; padding-top: 6px; }
.apk-icon { width: 38px; height: 38px; border-radius: 8px; object-fit: contain; box-shadow: var(--app-shadow-icon); flex: 0 0 auto; cursor: zoom-in; }
.apk-icon--fallback { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 8px; background: var(--app-card-border); color: var(--app-text-dim); font-weight: 600; font-size: var(--app-font-size-xl); flex: 0 0 auto; cursor: default; }

/* click-to-zoom lightbox for the app icon (overlay lives on <body>) */
.apk-lightbox { position: fixed; inset: 0; z-index: 9999; display: none; align-items: center; justify-content: center; background: var(--app-overlay-bg); cursor: zoom-out; }
/* Show at the icon's NATURAL size and only shrink if it exceeds the cap —
   width/height:auto (not a fixed box) prevents object-fit from upscaling a
   small source and turning it blurry. */
.apk-lightbox-img { width: auto; height: auto; max-width: min(420px, 80vw); max-height: min(420px, 80vh); border-radius: 20px; box-shadow: var(--app-shadow-overlay); background: transparent; }
.apk-sum { font-size: var(--app-font-size-xs); color: var(--app-text-dim); font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* uniform table for every analysis section */
.apk-table { width: 100%; border-collapse: collapse; font-size: var(--app-font-size-sm); }
.apk-table th { text-align: left; color: var(--app-text-dim); font-weight: 600; font-size: var(--app-font-size-xs); border-bottom: 1px solid var(--app-card-border); padding: 5px 8px; white-space: nowrap; }
.apk-table td { padding: 5px 8px; border-bottom: 1px solid var(--app-card-border); color: var(--app-text-secondary); vertical-align: top; word-break: break-word; }
.apk-table tr:last-child td { border-bottom: none; }
/* hover affordance so long tables (permissions / metadata) stay scannable */
.apk-table tbody tr:hover { background: var(--app-hover); }
.apk-table .mono { font-family: var(--app-font-mono); }
.apk-table .nowrap { white-space: nowrap; }

/* metadata parent column stays on one line */
.apk-parent { font-family: var(--app-font-mono); font-size: var(--app-font-size-xs); color: var(--app-text-dim); white-space: nowrap; }
.apk-res { font-size: var(--app-font-size-xs); color: var(--app-text-muted); font-family: var(--app-font-mono); }

.apk-archchip { display: inline-block; font-size: var(--app-font-size-xs); font-weight: 600; border-radius: 4px; padding: 1px 6px; margin: 1px 3px 1px 0; }

.apk-lv { display: inline-block; font-size: var(--app-font-size-xs); border-radius: 4px; padding: 1px 7px; font-weight: 600; white-space: nowrap; }
.apk-lv--danger { background: var(--app-red-bg); color: var(--app-red); }
.apk-lv--normal { background: var(--app-storage-bg); color: var(--app-text-dim); }
.apk-lv--ok { background: var(--app-green-bg); color: var(--app-green); }
.apk-lv--warn { background: var(--app-yellow-bg); color: var(--app-yellow); }

.apk-mini { display: inline-block; font-family: var(--app-font-mono); font-size: var(--app-font-size-xs); background: var(--app-yellow-bg); color: var(--app-yellow); border-radius: 3px; padding: 0 5px; margin: 0 2px; }

.apk-warn { background: var(--app-yellow-bg); border: 1px solid var(--app-yellow); color: var(--app-yellow); border-radius: 6px; padding: 6px 10px; font-size: var(--app-font-size-sm); margin-top: 6px; }
.apk-muted { color: var(--app-text-dim); font-size: var(--app-font-size-sm); }

.apk-copy { color: var(--app-text-dim); opacity: 0.4; cursor: pointer; margin-left: 6px; display: inline-flex; align-items: center; vertical-align: middle; transition: opacity .15s, color .15s; }
.apk-copy:hover { opacity: 1; color: var(--app-green); }
.apk-copy svg { display: block; }

.chev { color: var(--app-text-dim); transition: transform .2s; }
details[open] > summary .chev { transform: rotate(90deg); }

/* nested details (e.g. "other permissions") */
.apk-card details > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px; color: var(--app-text-dim); font-size: var(--app-font-size-sm); }
.apk-card details > summary::-webkit-details-marker { display: none; }
</style>
