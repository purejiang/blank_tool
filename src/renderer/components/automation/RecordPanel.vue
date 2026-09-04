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
      <div v-for="(step, i) in liveSteps" :key="i" class="step-line">
        <span class="step-idx">#{{ i + 1 }}</span>
        <span class="step-act">{{ actLabel(step.action) }}</span>
        <span class="step-pos">{{ posSummary(step) }}</span>
      </div>
    </n-scrollbar>
    <div v-else class="record-empty">{{ t('automation.recordEmpty') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NScrollbar, NTag, useMessage } from 'naive-ui'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'

// automation.record* i18n keys (zh-CN/en-US) landed in 4198cc3.
const props = defineProps<{ disabled: boolean }>()

const emit = defineEmits<{
  (e: 'recording-start'): void
  (e: 'recorded', steps: any[]): void
  (e: 'recording-end'): void
}>()

const { t } = useI18n()
const message = useMessage()
const deviceStore = useDeviceStore()

const recording = ref(false)
const liveSteps = ref<any[]>([])
const recId = ref('')
const ended = ref(false)
let svc: any = null

const startDisabled = computed(
  () => props.disabled || recording.value || !deviceStore.selectedDeviceId
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
  const deviceId = deviceStore.selectedDeviceId
  // Synchronous state flip before ANY await (page precedent: runScript sets
  // running before awaiting) — a double click cannot issue a second
  // record_start; the catch below rolls both flags back via _reset.
  ended.value = false
  liveSteps.value = []
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
    const res = await svc.stopRecording(deviceStore.selectedDeviceId)
    emit('recorded', Array.isArray(res?.steps) ? res.steps : [])
  } catch (err: any) {
    // A rejected record_stop must reset the UI, not leak an unhandled
    // rejection into the page's click handler.
    message.error(t('automation.recordFailed') + ': ' + (err?.message ?? String(err)))
  } finally {
    _reset()
  }
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
</style>
