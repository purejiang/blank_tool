<template>
  <div class="record-panel">
    <n-button
      size="small"
      block
      :disabled="startDisabled"
      @click="startRecording"
    >
      {{ t('automation.recordStart') }}
    </n-button>
    <n-button
      v-if="recording"
      type="error"
      size="small"
      block
      @click="stop"
    >
      {{ t('automation.recordStop') }}
    </n-button>

    <div v-if="recording" class="record-count-line">
      <n-tag type="error" size="small" class="record-count">{{ liveSteps.length }}</n-tag>
    </div>

    <n-scrollbar v-if="liveSteps.length" class="record-list">
      <template v-for="(step, i) in liveSteps" :key="i">
        <div v-if="gapMs(i) > gap.thresholdMs" class="gap-line">
          + {{ Math.min(gapMs(i), gap.maxMs) }}ms
        </div>
        <div class="step-line">
          <span class="step-idx">#{{ i + 1 }}</span>
          <span class="step-act">{{ actLabel(step.action) }}</span>
          <span class="step-pos">{{ posSummary(step) }}</span>
        </div>
      </template>
    </n-scrollbar>
    <div v-else class="record-empty">{{ t('automation.recordEmpty') }}</div>

    <!-- 停止后仅展示；用户显式选择插入位置后才写入脚本步骤 -->
    <div v-if="lastRecord && !recording" class="record-actions">
      <n-select
        v-model:value="insertAt"
        size="small"
        class="insert-pos"
        :options="insertOptions"
      />
      <n-button
        size="small"
        type="primary"
        :disabled="!lastRecord.steps.length"
        @click="applyRecorded"
      >
        {{ t('automation.applySteps') }}
      </n-button>
      <n-button size="small" quaternary @click="clearRecorded">
        {{ t('automation.clearRecorded') }}
      </n-button>
    </div>

    <div class="gap-settings">
      <n-checkbox v-model:checked="gap.enabled" size="small">
        <span class="gap-label">{{ t('automation.autoWaitEnabled') }}</span>
      </n-checkbox>
      <n-tooltip trigger="hover" placement="top">
        <template #trigger>
          <span class="gap-field">
            <span class="gap-label">{{ t('automation.waitThreshold') }}</span>
            <n-input-number
              v-model:value="gap.thresholdMs"
              size="tiny"
              :min="0"
              :step="100"
              class="gap-num"
            />
          </span>
        </template>
        {{ t('automation.waitThresholdTip') }}
      </n-tooltip>
      <span class="gap-field">
        <span class="gap-label">{{ t('automation.waitMaxCap') }}</span>
        <n-input-number
          v-model:value="gap.maxMs"
          size="tiny"
          :min="gap.thresholdMs"
          :step="500"
          class="gap-num"
        />
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NCheckbox, NInputNumber, NScrollbar, NTag, NTooltip, useMessage,
} from 'naive-ui'
import serviceManager from '@services/ServiceManager'

// automation.record* i18n keys (zh-CN/en-US) landed in 4198cc3.
const props = defineProps<{
  disabled: boolean
  /** 步骤编辑器里是否有选中行（决定"插入到选中步骤之后"是否可选） */
  hasSelection?: boolean
  /** 录制目标设备 — 来自自动化页自己的选择，与设备页详情选中解耦 */
  deviceId?: string
}>()

export type InsertAt = 'end' | 'start' | 'after'

export interface RecordedGap {
  enabled: boolean
  thresholdMs: number
  maxMs: number
}

const emit = defineEmits<{
  (e: 'recording-start'): void
  (e: 'recorded', payload: { steps: any[]; gap: RecordedGap; insertAt: InsertAt }): void
  (e: 'recording-end'): void
}>()

const { t } = useI18n()
const message = useMessage()

const recording = ref(false)
const liveSteps = ref<any[]>([])
const recId = ref('')
const ended = ref(false)
let svc: any = null

/** auto-wait synthesis settings; threshold/cap editable while recording */
const gap = reactive<RecordedGap>({
  enabled: true,
  thresholdMs: 500,
  maxMs: 5000,
})

/** gap (ms) between the end of step i-1 and the START of step i. */
function gapMs(i: number): number {
  if (i <= 0) return 0
  const prev = liveSteps.value[i - 1]
  const cur = liveSteps.value[i]
  if (typeof prev?.ts !== 'number' || typeof cur?.ts !== 'number') return 0
  const startOfCur = cur.ts - (Number(cur.duration_ms) || 0) / 1000
  return Math.max(0, Math.round((startOfCur - prev.ts) * 1000))
}

/** 停止后暂存的录制结果；点击「插入到脚本」才交给页面按位置写入 */
const lastRecord = ref<{ steps: any[]; gap: RecordedGap } | null>(null)

/** 插入位置；"选中步骤之后"在编辑器无选中时禁用 */
const insertAt = ref<InsertAt>('end')
const insertOptions = computed(() => [
  { value: 'end', label: t('automation.insertEnd') },
  { value: 'start', label: t('automation.insertStart') },
  {
    value: 'after',
    label: t('automation.insertAfter'),
    disabled: !props.hasSelection,
  },
])

const startDisabled = computed(
  () => props.disabled || recording.value || !props.deviceId
)

function actLabel(action: unknown): string {
  const key = 'automation.act.' + action
  const v = t(key) as string
  return v === key ? String(action) : v
}

function posSummary(step: any): string {
  if (step?.action === 'swipe') {
    return `${step.x1 ?? ''},${step.y1 ?? ''}→${step.x2 ?? ''},${step.y2 ?? ''}`
  }
  return `${step?.x ?? ''},${step?.y ?? ''}`
}

async function startRecording(): Promise<void> {
  if (startDisabled.value) return
  const deviceId = props.deviceId
  // Synchronous state flip before ANY await (page precedent: runScript sets
  // running before awaiting) — a double click cannot issue a second
  // record_start; the catch below rolls both flags back via _reset.
  ended.value = false
  liveSteps.value = []
  lastRecord.value = null
  recording.value = true
  emit('recording-start')
  try {
    svc = await serviceManager.getService('recording')
    await svc.initialize()
    // Callbacks ride with the start call; the service registers them
    // before the backend call, so in-flight events stay routable.
    recId.value = await svc.startRecording(deviceId, {
      onStep,
      onError: onRecError,
      onStopped,
    })
  } catch (err: any) {
    onRecError(err?.message ?? String(err))
  }
}

function onStep(step: any): void {
  if (step && typeof step === 'object') {
    liveSteps.value.push(step)
  }
}

function onRecError(msg: string): void {
  message.error(t('automation.recordFailed') + ': ' + msg)
  _reset()
}

function onStopped(_payload: any): void {
  // record_stopped payload carries { count }, not steps — nothing to
  // forward here; recorded steps only arrive via the stop() call path.
  message.warning(t('automation.recordStopped'))
  _reset()
}

/** Stop action; also exposed for the page's ref-driven stop entry. */
async function stop(): Promise<void> {
  if (!recording.value || !recId.value) return
  try {
    const res = await svc.stopRecording(props.deviceId)
    // 只暂存展示，不自动写入脚本 —— 写入由「应用到脚本」按钮显式触发
    lastRecord.value = {
      steps: Array.isArray(res?.steps) ? res.steps : [],
      gap: { enabled: gap.enabled, thresholdMs: gap.thresholdMs, maxMs: gap.maxMs },
    }
  } catch (err: any) {
    // A rejected record_stop must reset the UI, not leak an unhandled
    // rejection into the page's click handler.
    message.error(t('automation.recordFailed') + ': ' + (err?.message ?? String(err)))
  } finally {
    _reset()
  }
}

function applyRecorded(): void {
  if (!lastRecord.value || recording.value) return
  // 无选中行时"选中之后"回落到追加末尾
  const at: InsertAt =
    insertAt.value === 'after' && !props.hasSelection ? 'end' : insertAt.value
  emit('recorded', { ...lastRecord.value, insertAt: at })
}

function clearRecorded(): void {
  lastRecord.value = null
  liveSteps.value = []
}

/**
 * Idempotent reset — record_stop's return and a late record_stopped event
 * can both arrive; the first one resets, the second is a no-op. The
 * `ended` flag keeps recording-end single-shot per session.
 */
function _reset(): void {
  if (recId.value) {
    try {
      svc?.finish(recId.value)
    } catch {
      // finish must never break the reset path
    }
    recId.value = ''
  }
  recording.value = false
  if (!ended.value) {
    ended.value = true
    emit('recording-end')
  }
}

defineExpose({ stop })

onBeforeUnmount(() => {
  // Navigating away mid-recording must not orphan the backend session.
  if (recording.value && recId.value) stop()
})
</script>

<style scoped>
.record-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}
.record-count-line {
  display: flex;
  justify-content: flex-end;
}
.record-list {
  max-height: 200px;
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  padding: 6px;
}
.step-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  padding: 2px 0;
  border-bottom: 1px dashed var(--app-card-border);
}
.step-idx {
  font-weight: 600;
  color: var(--app-text-primary);
}
.step-act {
  color: var(--app-text-primary);
  font-weight: 500;
}
.step-pos {
  color: var(--app-text-muted);
  flex: 1;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.record-empty {
  font-size: 12px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 10px 0;
  border: 1px dashed var(--app-card-border);
  border-radius: 8px;
}
.gap-line {
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 1px 0;
  font-variant-numeric: tabular-nums;
}
.record-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.insert-pos { flex: 1; min-width: 0; }
.gap-settings {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.gap-label { font-size: 11px; color: var(--app-text-muted); margin-right: 4px; }
.gap-field { display: inline-flex; align-items: center; }
.gap-num { width: 84px; }
</style>
