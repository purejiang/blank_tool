<template>
  <div class="record-panel">
    <!-- 标题与关闭 X 由外层 AppModal 统一提供（这里再画一遍就会出现两个关闭按钮） -->
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
      <div v-for="(step, i) in liveSteps" :key="i" class="step-line">
        <span class="step-idx">#{{ i + 1 }}</span>
        <span class="step-act">{{ actLabel(step.action) }}</span>
        <span class="step-pos">{{ posSummary(step) }}</span>
      </div>
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

    <!-- 录制只记录「操作」本身，不合成等待步骤 —— 但每步的实际停顿会随步骤一起
         记下来（store 由 ts 差值算出 recorded_gap_ms），运行时叠加在运行配置的
         默认步骤间隔之上：节奏不丢，脚本里也不会凭空多出一堆 wait 步骤。 -->
    <div class="record-hint">{{ t('automation.recordIntervalHint') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NScrollbar, NSelect, NTag, useMessage,
} from 'naive-ui'
import serviceManager from '@services/ServiceManager'

// automation.record* i18n keys (zh-CN/en-US) landed in 4198cc3.
const props = defineProps<{
  disabled: boolean
  /** 步骤编辑器里是否有选中行（"插入到选中步骤之后"是否可选） */
  hasSelection?: boolean
  /** 录制目标设备 — 来自自动化页自己的选择，与设备页详情选中解耦 */
  deviceId?: string
  /** 落点默认值，由入口决定：顶部「插入位」= 'start'（插到开头），
   *  行内「+」= 'after'（插在选中行之后）。面板里仍可手动改。 */
  defaultInsertAt?: 'end' | 'start' | 'after'
}>()

export type InsertAt = 'end' | 'start' | 'after'

const emit = defineEmits<{
  (e: 'recording-start'): void
  /** 录到的原始步骤（扁平形状，由 store 转成 v2）。这里**原样透传**，包括 `ts`：
   *  面板不做等待合成，实测停顿由 store 换算成 `recorded_gap_ms`，运行时叠加在
   *  默认步骤间隔之上。 */
  (e: 'recorded', payload: { steps: any[]; insertAt: InsertAt }): void
  (e: 'recording-end'): void
}>()

const { t } = useI18n()
const message = useMessage()

const recording = ref(false)
const liveSteps = ref<any[]>([])
const recId = ref('')
const ended = ref(false)
let svc: any = null

/**
 * 录制只暂存步骤本身（不合成等待步骤）：每步的实测停顿随步骤一起交给 store
 * 落成 `recorded_gap_ms`，运行时叠加在运行配置的默认步骤间隔之上；个别需要
 * 更久等待的步骤在自己的编辑表单里设「间隔」（那会整体覆盖这两者）。
 * 所以这里没有阈值/上限这类设置 —— 它们只在合成等待步骤时才有意义。
 */
const lastRecord = ref<{ steps: any[] } | null>(null)

/** 插入位置：默认由**入口**决定（顶部「插入位」= 开头，行内「+」= 该行下方），
 *  入口每次打开面板都会改写它；用户仍可在下拉里手动改。applyRecorded 兜底
 *  防失效位置（无选中行时 'after' 降级为末尾）。 */
const insertAt = ref<InsertAt>(props.defaultInsertAt ?? 'end')
watch(
  () => props.defaultInsertAt,
  (v) => { if (v) insertAt.value = v },
  { immediate: true },
)
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
  emit('recorded', { steps: lastRecord.value.steps, insertAt: at })
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
  font-size: var(--app-font-size-sm);
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
  font-size: var(--app-font-size-sm);
  color: var(--app-text-muted);
  text-align: center;
  padding: 10px 0;
  border: 1px dashed var(--app-card-border);
  border-radius: 8px;
}
/* 功能按钮统一靠右下（弹窗的底部动作区） */
.record-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.insert-pos { flex: none; width: 168px; }
/* 节奏解释：录制不合成等待步骤，实测停顿由 store 记进步骤并叠加默认间隔 */
.record-hint {
  font-size: var(--app-font-size-xs);
  line-height: 1.55;
  color: var(--app-text-dim);
}
</style>
